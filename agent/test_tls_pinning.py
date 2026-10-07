"""
tls_pinning: platform connections trust only the shipped certificate.

The live tests run against this host's nginx (https://127.0.0.1, certificate
/etc/nginx/ssl/omni.crt) and skip when it isn't there. The backend behind it
may be down: a completed TLS handshake followed by a 502 still proves the pin.
"""
import os
import socket
import ssl
import subprocess

import pytest
import requests

import tls_pinning

NGINX_CERT = "/etc/nginx/ssl/omni.crt"
PEM = "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    original = requests.Session.request
    monkeypatch.delenv("WEBSOCKET_CLIENT_CA_BUNDLE", raising=False)
    yield
    requests.Session.request = original
    tls_pinning._original_request = None
    tls_pinning._state.update(origin=None, ca_file=None)


def _decoy_pem(tmp_path) -> str:
    out = tmp_path / "decoy.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", os.devnull,
         "-out", str(out), "-days", "1", "-subj", "/CN=127.0.0.1",
         "-addext", "subjectAltName=IP:127.0.0.1"],
        check=True, capture_output=True,
    )
    return out.read_text()


def _record_verify(monkeypatch):
    seen = {}

    def fake(self, method, url, *args, **kwargs):
        seen[url] = kwargs.get("verify")
        return requests.Response()
    monkeypatch.setattr(tls_pinning, "_original_request", fake)
    return seen


def test_nothing_is_pinned_for_plain_http(tmp_path):
    assert tls_pinning.configure({"api_base_url": "http://10.0.0.5:5000", "server_ca_cert": PEM}, tmp_path) is None
    assert "WEBSOCKET_CLIENT_CA_BUNDLE" not in os.environ


def test_nothing_is_pinned_without_a_certificate(tmp_path):
    assert tls_pinning.configure({"api_base_url": "https://10.0.0.5"}, tmp_path) is None


def test_only_the_platform_origin_uses_the_pin(tmp_path, monkeypatch):
    nginx_pem = open(NGINX_CERT).read() if os.access(NGINX_CERT, os.R_OK) else _decoy_pem(tmp_path)
    ca = tls_pinning.configure({"api_base_url": "https://10.0.0.5/", "server_ca_cert": nginx_pem}, tmp_path)
    assert ca == str(tmp_path / "server_ca.pem")
    assert os.environ["WEBSOCKET_CLIENT_CA_BUNDLE"] == ca
    seen = _record_verify(monkeypatch)
    requests.get("https://10.0.0.5/api/heartbeat")
    requests.post("https://10.0.0.5:443/api/x", json={})
    requests.get("https://api.osv.dev/v1/query")  # third party: system store
    requests.get("https://10.0.0.5:8443/other")  # different port, different origin
    requests.get("https://10.0.0.5/explicit", verify="/custom/bundle.pem")  # caller's own choice stays
    assert seen["https://10.0.0.5/api/heartbeat"] == ca
    assert seen["https://10.0.0.5:443/api/x"] == ca
    assert seen["https://api.osv.dev/v1/query"] in (None, True)
    assert seen["https://10.0.0.5:8443/other"] in (None, True)
    assert seen["https://10.0.0.5/explicit"] == "/custom/bundle.pem"
    assert isinstance(tls_pinning.ssl_context_for("wss://10.0.0.5/api/ws"), ssl.SSLContext)
    assert tls_pinning.ssl_context_for("wss://elsewhere.example/ws") is None


def test_a_broken_certificate_stops_startup(tmp_path):
    with pytest.raises(ssl.SSLError):
        tls_pinning.configure({"api_base_url": "https://10.0.0.5", "server_ca_cert": PEM}, tmp_path)


def _nginx_up() -> bool:
    if not os.access(NGINX_CERT, os.R_OK):
        return False
    try:
        socket.create_connection(("127.0.0.1", 443), timeout=1).close()
        return True
    except OSError:
        return False


live = pytest.mark.skipif(not _nginx_up(), reason="no local nginx with the platform certificate")


@live
def test_pinned_platform_certificate_verifies(tmp_path):
    tls_pinning.configure({"api_base_url": "https://127.0.0.1", "server_ca_cert": open(NGINX_CERT).read()}, tmp_path)
    requests.get("https://127.0.0.1/api/agents/version", timeout=5)  # no SSLError
    import websocket
    with pytest.raises(websocket.WebSocketBadStatusException):  # TLS passed; the upgrade got an HTTP answer
        websocket.create_connection("wss://127.0.0.1/api/agents/remote/ws/agent/x", timeout=5)


@live
def test_any_other_certificate_is_refused(tmp_path):
    tls_pinning.configure({"api_base_url": "https://127.0.0.1", "server_ca_cert": _decoy_pem(tmp_path)}, tmp_path)
    with pytest.raises(requests.exceptions.SSLError):
        requests.get("https://127.0.0.1/api/agents/version", timeout=5)
    import websocket
    with pytest.raises(ssl.SSLCertVerificationError):
        websocket.create_connection("wss://127.0.0.1/api/agents/remote/ws/agent/x", timeout=5)
