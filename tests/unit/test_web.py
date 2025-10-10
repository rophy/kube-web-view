import argparse
import asyncio
import os
import re
import time
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
from kube_web.web import refresh_access_token


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


@patch("aioauth_client.OAuth2Client.get_access_token")
def test_oauth_callback_stores_refresh_token(get_access_token):
    access_token = "access-token"
    refresh_token = "refresh-token"

    get_access_token.return_value = (
        access_token,
        {"refresh_token": refresh_token, "expires_in": 3600},
    )

    state = "eyJvcmlnaW5hbF91cmwiOiAiaHR0cHM6Ly9leGFtcGxlLmNvbS9vcmlnaW5hbF91cmwifQ=="
    code = "12345"
    url = f"{OAUTH2_CALLBACK_PATH}?state={state}&code={code}"
    callback_request, handler = setup_oauth_test("POST", url)

    asyncio.run(auth(callback_request, handler))

    session = callback_request.get(SESSION_KEY)
    assert session["access_token"] == access_token
    assert session["refresh_token"] == refresh_token


@patch("aioauth_client.OAuth2Client.get_access_token")
def test_oauth_refresh_token_success(get_access_token):
    """Test successful token refresh with new access token and refresh token"""
    new_access_token = "new-access-token"
    new_refresh_token = "new-refresh-token"
    expires_in = 3600  # 1 hour

    get_access_token.return_value = (
        new_access_token,
        {"expires_in": expires_in, "refresh_token": new_refresh_token},
    )

    session = {"refresh_token": "old-refresh-token", "access_token": "old-token"}

    result = asyncio.run(refresh_access_token(session))

    assert result is True
    get_access_token.assert_called_with("old-refresh-token", grant_type="refresh_token")
    assert session["access_token"] == new_access_token
    assert session["refresh_token"] == new_refresh_token
    # Should set expiry with 5 minute buffer
    assert session["expires"] <= time.time() + expires_in
    assert session["expires"] > time.time() + expires_in - 600  # within 10 min range


@patch("aioauth_client.OAuth2Client.get_access_token")
def test_oauth_refresh_token_no_new_refresh_token(get_access_token):
    """Test token refresh when no new refresh token is returned"""
    new_access_token = "new-access-token"
    expires_in = 3600

    # No refresh_token in response
    get_access_token.return_value = (new_access_token, {"expires_in": expires_in})

    session = {"refresh_token": "old-refresh-token"}

    result = asyncio.run(refresh_access_token(session))

    assert result is True
    assert session["access_token"] == new_access_token
    # Old refresh token should remain
    assert session["refresh_token"] == "old-refresh-token"


def test_oauth_refresh_token_missing():
    """Test refresh fails when no refresh token in session"""
    session = {"access_token": "some-token"}

    result = asyncio.run(refresh_access_token(session))

    assert result is False
    # Session should remain unchanged
    assert "refresh_token" not in session


@patch("aioauth_client.OAuth2Client.get_access_token")
def test_oauth_refresh_token_failure(get_access_token):
    """Test refresh fails and clears invalid refresh token"""
    get_access_token.side_effect = Exception("Invalid refresh token")

    session = {"refresh_token": "invalid-token", "access_token": "old-token"}

    result = asyncio.run(refresh_access_token(session))

    assert result is False
    # Should clear the invalid refresh token
    assert "refresh_token" not in session
    # Old access token should remain
    assert session["access_token"] == "old-token"


@patch("kube_web.web.refresh_access_token")
def test_auth_middleware_refreshes_expired_token(mock_refresh):
    """Test auth middleware attempts refresh when token is expired"""
    mock_refresh.return_value = True  # Simulate successful refresh

    expired_time = time.time() - 100  # Token expired 100 seconds ago
    request, _ = setup_oauth_test("GET", "/some-path")
    session = request.get(SESSION_KEY)
    session["access_token"] = "expired-token"
    session["expires"] = expired_time
    session["refresh_token"] = "valid-refresh-token"

    # Should call handler without redirecting since refresh succeeds
    async def mock_handler(req):
        return web.Response(text="OK")

    response = asyncio.run(auth(request, mock_handler))

    mock_refresh.assert_called_once_with(session)
    assert response.text == "OK"


def test_is_allowed_namespace():
    assert is_allowed_namespace("a", [], [])
    assert is_allowed_namespace("a", [re.compile("a")], [])
    assert is_allowed_namespace("a", [], [re.compile("b")])
    assert not is_allowed_namespace("a", [re.compile("b")], [])
    assert not is_allowed_namespace("a", [], [re.compile("a")])

    assert not is_allowed_namespace("default-foo", [re.compile("default")], [])
