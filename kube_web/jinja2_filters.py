import colorsys
import datetime
import logging
import re

import pygments
import yaml as pyyaml
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name


logger = logging.getLogger(__name__)


def pluralize(singular):
    if singular.endswith("s"):
        # Ingress -> Ingresses
        return singular + "es"
    elif singular.endswith("y"):
        # NetworkPolicy -> NetworkPolicies
        return singular[:-1] + "ies"
    else:
        return singular + "s"


def yaml(value):
    return pyyaml.dump(value, default_flow_style=False)


iso8601_re = re.compile(
    # example:
    # 2021-02-09T21:28:00Z
    r"""(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)""",
)


def highlight(value, config, cluster="", namespace="", resource=None, linenos=False):

    if linenos:
        formatter = HtmlFormatter(
            lineanchors="line",
            anchorlinenos=True,
            linenos="table",
            linespans="yaml-line",
        )
    else:
        formatter = HtmlFormatter()

    html = pygments.highlight(value, get_lexer_by_name("yaml"), formatter)
    links = config.timestamp_links.get(resource.endpoint, [])
    if len(links) == 0:
        # No links configured, return directly.
        return html

    if len(links) > 1:
        logger.warning(
            f"More than one links configured in timestamp-links for {resource.endpoint}: {links}, only the first one will be used.",
        )

    link = links[0]
    repl = r"""<a href="{url}" title="{title}">\1</a>""".format(
        url=link["href"].format(
            cluster=cluster,
            namespace=namespace,
            name=resource.name,
            timestamp=r"\1",
        ),
        title=link["title"].format(
            cluster=cluster,
            namespace=namespace,
            name=resource.name,
            timestamp=r"\1",
        ),
    )
    return iso8601_re.sub(repl, html)


def age_color(date_time, days=7, hue=0.39, value=0.21):
    """Return HTML color calculated by age of input time value.

    :param d: datetime value to base color calculation on
    :param days: upper limit for color calculation, in days
    :return: HTML color value string
    """

    if not date_time:
        return "auto"
    if isinstance(date_time, str):
        date_time = datetime.datetime.strptime(date_time, "%Y-%m-%dT%H:%M:%SZ")
    d = datetime.datetime.utcnow() - date_time
    # we consider the last minute equal
    d = max(0, d.total_seconds() - 60)
    s = max(0, 1.0 - d / (days * 24.0 * 3600))
    # dates older than days are color #363636 (rgb(54, 54, 54))
    r, g, b = colorsys.hsv_to_rgb(hue, s, value + (s * (0.81 - value)))
    return (
        f"#{int(round(r * 255)):02x}{int(round(g * 255)):02x}{int(round(b * 255)):02x}"
    )


def cpu(value):
    return "{:,.0f}m".format(value * 1000)


def memory(value, fmt):
    if fmt == "GiB":
        return "{:,.01f}".format(value / (1024 ** 3))
    elif fmt == "MiB":
        return "{:,.0f}".format(value / (1024 ** 2))
    else:
        return value
