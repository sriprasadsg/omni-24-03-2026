"""Open-source services the server's operator runs beside the platform (Mailpit, authentik, Fleet, a private ntfy).

Integrations that take a URL from an organization refuse private and loopback addresses (webhook_url_validator), so
a service on this server would be refused too. OMNI_SELF_HOSTED (in /etc/omni/self-hosted.env, root-only, written by
scripts/oss/oss.sh) names the exact origins allowed anyway, each optionally with the certificate the service presents,
which is then the only certificate trusted for that origin:

    OMNI_SELF_HOSTED=smtp://localhost:1025|/etc/omni/oss/mailpit.crt,http://127.0.0.1:9000,https://localhost:8412|/etc/omni/oss/fleet.crt

Only those origins (scheme, host and port) pass, plain http only on a loopback host, and nothing an organization
saves can add to the list.
"""
import os
import ssl
from typing import Dict, Optional, Union
from urllib.parse import urlsplit

DEFAULT_PORTS = {"http": 80, "https": 443, "smtp": 25}
LOOPBACK = ("127.0.0.1", "localhost", "::1")


def origin(url: str) -> Optional[str]:
    """scheme://host:port of url, lower case, or None when it has no scheme, host or port."""
    try:
        p = urlsplit((url or "").strip())
        port = p.port or DEFAULT_PORTS.get(p.scheme.lower())
    except ValueError:
        return None
    if not p.scheme or not p.hostname or not port:
        return None
    return f"{p.scheme.lower()}://{p.hostname.lower()}:{port}"


def allowed() -> Dict[str, Optional[str]]:
    """The operator's allowed origins, each with its pinned certificate file (or None)."""
    out: Dict[str, Optional[str]] = {}
    for item in os.environ.get("OMNI_SELF_HOSTED", "").split(","):
        url, _, cafile = item.strip().partition("|")
        key = origin(url)
        if key and not (key.startswith("http://") and urlsplit(key).hostname not in LOOPBACK):
            out[key] = cafile.strip() or None
    return out


def is_allowed(url: str) -> bool:
    return origin(url) in allowed()


def ssl_context(url: str) -> ssl.SSLContext:
    """A verifying TLS context for url: only the pinned certificate of an allowed service, else the system trust."""
    cafile = allowed().get(origin(url) or "")
    return ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()


def verify(url: str) -> Union[ssl.SSLContext, bool]:
    """httpx's ``verify=`` for url: the pinned certificate of an allowed service, else httpx's default trust."""
    cafile = allowed().get(origin(url) or "")
    return ssl.create_default_context(cafile=cafile) if cafile else True


async def check_url(url: str) -> None:
    """Raise ValueError unless url is on an allowed origin or is an https URL that resolves only to public addresses."""
    if is_allowed(url):
        return
    from webhook_url_validator import validate_webhook_url
    await validate_webhook_url(url)
