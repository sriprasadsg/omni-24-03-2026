"""
TLS trust for connections to the platform.

Installers put the platform's certificate in config.yaml (``server_ca_cert``,
PEM). When it is set and ``api_base_url`` is https, every connection this agent
makes to the platform trusts that certificate and nothing else, so someone on
the network can't pose as the server:

- requests: calls to the platform's origin verify against it. Other hosts
  (VirusTotal, OSV) keep the system store.
- websocket-client (remote shell/desktop, the Socket.IO upgrade): through
  WEBSOCKET_CLIENT_CA_BUNDLE. Those sockets only ever reach the platform.
- websockets (asyncio): ``ssl_context_for(url)``.
"""
import logging
import os
import ssl
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)

_CA_FILENAME = "server_ca.pem"
_state = {"origin": None, "ca_file": None}
_original_request = None


def _origin(url: str):
    parts = urlsplit(url)
    scheme = {"wss": "https", "ws": "http"}.get(parts.scheme.lower(), parts.scheme.lower())
    return scheme, (parts.hostname or "").lower(), parts.port or (443 if scheme == "https" else 80)


def configure(cfg: dict, base_dir) -> Optional[str]:
    """Pin the platform certificate from ``cfg``. Returns the CA file path,
    or None when nothing is pinned (http URL or no certificate shipped)."""
    pem = (cfg.get("server_ca_cert") or "").strip()
    base_url = (cfg.get("api_base_url") or "").strip()
    if not pem or not base_url.lower().startswith("https://"):
        return None
    ca_file = Path(base_dir) / _CA_FILENAME
    ca_file.write_text(pem + "\n", encoding="ascii")
    ssl.create_default_context(cafile=str(ca_file))  # fail fast on a broken PEM
    _state.update(origin=_origin(base_url), ca_file=str(ca_file))
    _install_requests_hook()
    os.environ["WEBSOCKET_CLIENT_CA_BUNDLE"] = str(ca_file)
    logger.info("TLS: platform connections trust only the pinned server certificate")
    return str(ca_file)


def _install_requests_hook() -> None:
    global _original_request
    if _original_request is not None:
        return
    _original_request = requests.Session.request

    def request(self, method, url, *args, **kwargs):
        # Only an unset/default verify is replaced; a caller's own CA bundle
        # stays. Module-level requests.get/post land here too.
        if _state["ca_file"] and kwargs.get("verify") in (None, True) and _origin(str(url)) == _state["origin"]:
            kwargs["verify"] = _state["ca_file"]
        return _original_request(self, method, url, *args, **kwargs)

    requests.Session.request = request


def ssl_context_for(url: str) -> Optional[ssl.SSLContext]:
    """SSL context for an asyncio ``websockets`` connection to ``url``: the
    pinned certificate for the platform, None (library default) otherwise."""
    if _state["ca_file"] and _origin(url) == _state["origin"]:
        return ssl.create_default_context(cafile=_state["ca_file"])
    return None
