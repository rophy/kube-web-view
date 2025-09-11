import argparse
import asyncio
import os
import re
import urllib
from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from aiohttp_session import SESSION_KEY

from kube_web.web import auth
from kube_web.web import CONFIG
from kube_web.web import is_allowed_namespace
from kube_web.web import OAUTH2_CALLBACK_PATH


def setup_oauth_test(method, url):
    def handler():
        assert False

    session = {}

    def request_get(key):
        if key == SESSION_KEY:
            return session
        return None

    os.environ["OAUTH2_AUTHORIZE_URL"] = "https://example.com/auth"
    os.environ["OAUTH2_ACCESS_TOKEN_URL"] = "https://example.com/token"

    request = make_mocked_request(method, url)
    request = request.clone(
        rel_url=url, host="kube-web-view.readthedocs.io", scheme="https"
    )
    request.app[CONFIG] = argparse.Namespace(oauth2_authorized_hook=None)
    request.get = request_get

    return request, handler


def test_oauth_login():
    login_request, handler = setup_oauth_test("GET", "/")

    with pytest.raises(web.HTTPFound) as e:
        asyncio.run(auth(login_request, handler))

    url = urllib.parse.urlparse(e.value.location)
    query = urllib.parse.parse_qs(str(url.query))

    assert url.hostname == "example.com"
    assert url.path == "/auth"
    assert (
        query["redirect_uri"][0]
        == "https://kube-web-view.readthedocs.io/oauth2/callback"
    )
    assert query["state"][0] == "eyJvcmlnaW5hbF91cmwiOiAiLyJ9"
    assert len(query["state"][0]) > 8
    assert query["response_type"][0] == "code"


@patch("aioauth_client.OAuth2Client.get_access_token")
def test_oauth_callback(get_access_token):
    token = "fake-token"
    get_access_token.return_value = (token, {})

    state = "eyJvcmlnaW5hbF91cmwiOiAiaHR0cHM6Ly9leGFtcGxlLmNvbS9vcmlnaW5hbF91cmwifQ=="
    code = "12345"
    url = f"{OAUTH2_CALLBACK_PATH}?state={state}&code={code}"
    callback_request, handler = setup_oauth_test("POST", url)

    response = asyncio.run(auth(callback_request, handler))

    redirect_uri = "https://kube-web-view.readthedocs.io{}".format(OAUTH2_CALLBACK_PATH)

    get_access_token.assert_called_with(code, redirect_uri=redirect_uri)
    assert type(response) == web.HTTPFound
    assert response.location == "https://example.com/original_url"
    assert callback_request.get(SESSION_KEY)["access_token"] == token


def test_is_allowed_namespace():
    assert is_allowed_namespace("a", [], [])
    assert is_allowed_namespace("a", [re.compile("a")], [])
    assert is_allowed_namespace("a", [], [re.compile("b")])
    assert not is_allowed_namespace("a", [re.compile("b")], [])
    assert not is_allowed_namespace("a", [], [re.compile("a")])

    assert not is_allowed_namespace("default-foo", [re.compile("default")], [])
