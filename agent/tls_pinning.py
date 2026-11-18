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

Certificate changes: a heartbeat reply may carry ``serverTrust.certs``, the whole
list the platform wants trusted. It is taken only while the agent pins (the reply
came over a pinned connection) and only if it keeps a certificate trusted now; it
then replaces the CA file and config.yaml. With ``next`` and ``probePort`` the
agent connects to the probe port trusting only the next certificate and reports
the result (``tls_probe``), so the platform switches once its agents have passed.
"""
import hashlib
import logging
import os
import re
import ssl
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)

_CA_FILENAME = "server_ca.pem"
_NEXT_FILENAME = "server_ca_next.pem"
_state = {"origin": None, "ca_file": None}
_original_request = None
_probe = {"ask": None, "result": None, "at": 0.0}
_PROBE_RETRY_SECONDS = 1800
_CERT_RE = re.compile(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", re.S)


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


def split_pem(text: str) -> list:
    """The certificates in a PEM text, each with its armor."""
    return _CERT_RE.findall(text or "")


def fingerprint(cert_pem: str) -> str:
    """SHA-256 of the certificate's DER, lowercase hex. Raises ValueError for a broken certificate."""
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert_pem)).hexdigest()


def _pinned_pem() -> str:
    if not _state["ca_file"]:
        return ""
    try:
        return Path(_state["ca_file"]).read_text(encoding="ascii")
    except OSError:
        return ""


def fingerprints() -> list:
    """What this agent trusts for the platform (empty when nothing is pinned), sent with each heartbeat."""
    out = []
    for cert in split_pem(_pinned_pem()):
        try:
            out.append(fingerprint(cert))
        except ValueError:
            pass
    return out


def accept_bundle(current_fps: list, bundle: str):
    """The PEM list to trust instead, or None when it holds the same certificates. Raises ValueError when
    it is empty or too long, a certificate does not parse, or it keeps none of the current ones."""
    certs = split_pem(bundle)
    if not 1 <= len(certs) <= 8:
        raise ValueError(f"{len(certs)} certificates (1 to 8 expected)")
    fps = [fingerprint(c) for c in certs]
    try:
        ssl.create_default_context(cadata="\n".join(certs))
    except ssl.SSLError as exc:
        raise ValueError(f"a certificate does not parse ({exc})") from exc
    if not set(fps) & set(current_fps):
        raise ValueError("it keeps none of the certificates trusted now")
    return None if set(fps) == set(current_fps) else "\n".join(certs) + "\n"


def update_from_heartbeat(cfg: dict, body, save_config) -> bool:
    """Take the certificate list a heartbeat reply carries; True when the trust changed."""
    trust = body.get("serverTrust") if isinstance(body, dict) else None
    if not isinstance(trust, dict):
        return False
    _note_probe(cfg, trust)
    bundle = trust.get("certs")
    if not isinstance(bundle, str):
        return False
    if not _state["ca_file"]:
        logger.warning("TLS: ignored a certificate list from the platform: nothing is pinned, so the reply is not authenticated")
        return False
    try:
        pem = accept_bundle(fingerprints(), bundle)
    except ValueError as exc:
        logger.warning("TLS: refused a certificate list from the platform: %s", exc)
        return False
    if pem is None:
        return False
    Path(_state["ca_file"]).write_text(pem, encoding="ascii")
    cfg["server_ca_cert"] = pem
    save_config(cfg)
    logger.info("TLS: the platform changed the trusted certificates to %s", ", ".join(fingerprints()))
    return True


def probe_url(api_base_url: str, port: int) -> Optional[str]:
    """The platform's own host on ``port``, path /api/health; None for a non-https platform."""
    parts = urlsplit((api_base_url or "").strip())
    if parts.scheme.lower() != "https" or not parts.hostname or not 0 < port < 65536:
        return None
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    return f"https://{host}:{port}/api/health"


def _note_probe(cfg: dict, trust: dict) -> None:
    nxt = [f.lower() for f in (trust.get("next") or []) if isinstance(f, str) and re.fullmatch(r"[0-9a-fA-F]{64}", f)]
    port = trust.get("probePort")
    url = probe_url(cfg.get("api_base_url", ""), port) if nxt and isinstance(port, int) else None
    _probe["ask"] = (url, tuple(nxt)) if url else None


def probe_report():
    """The last probe result for the current ask, else None."""
    result = _probe["result"]
    return result[1] if result and result[0] == _probe["ask"] else None


def probe_if_due() -> None:
    """Connect to the probe port trusting only the next certificate(s), when asked and not done recently."""
    ask = _probe["ask"]
    if not ask:
        return
    done = _probe["result"]
    if done and done[0] == ask and (done[1]["ok"] or time.time() - _probe["at"] < _PROBE_RETRY_SECONDS):
        return
    url, nxt = ask
    certs = [c for c in split_pem(_pinned_pem()) if fingerprint(c) in nxt]
    ok, status, error = False, None, None
    if not certs:
        error = "the next certificate is not in this agent's trusted list"
    else:
        next_file = Path(_state["ca_file"]).with_name(_NEXT_FILENAME)
        next_file.write_text("\n".join(certs) + "\n", encoding="ascii")
        try:
            status = requests.get(url, verify=str(next_file), timeout=15).status_code
            ok = True
        except requests.exceptions.SSLError as exc:
            error = f"certificate: {exc}"[:300]
        except requests.exceptions.RequestException as exc:
            error = f"could not connect: {exc}"[:300]
    report = {"url": url, "fingerprints": list(nxt), "ok": ok, "status": status, "error": error,
              "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (logger.info if ok else logger.warning)("TLS: the next certificate %s on %s%s", "passed" if ok else "failed",
                                            url, "" if ok else f": {error}")
    _probe.update(result=(ask, report), at=time.time())
