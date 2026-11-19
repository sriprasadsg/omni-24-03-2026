"""The operator's allowlist of self-hosted open-source services (self_hosted). protects/fails_when/no_claim per test."""
import os
import ssl
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import self_hosted as sh


def test_only_the_listed_origins_pass_and_plain_http_only_on_loopback(monkeypatch):
    """protects=an origin passes only with its exact scheme, host and port, a cert file pins it, and a plain-http
    entry on a non-loopback host is ignored; fails_when=another port or scheme on the same host, or http to a LAN
    address, is allowed; no_claim=what the service behind the origin is"""
    monkeypatch.setenv("OMNI_SELF_HOSTED", " smtp://localhost:1025|/etc/omni/oss/mailpit.crt , http://127.0.0.1:9000,"
                                           "http://10.0.0.9:80,https://LOCALHOST:8412|/x.crt,not a url")
    assert sh.allowed() == {"smtp://localhost:1025": "/etc/omni/oss/mailpit.crt", "http://127.0.0.1:9000": None,
                            "https://localhost:8412": "/x.crt"}
    assert sh.is_allowed("http://127.0.0.1:9000/api/v3/events/") and sh.is_allowed("https://localhost:8412/api/v1/fleet/hosts")
    for url in ("http://127.0.0.1:9001/", "https://127.0.0.1:9000/", "http://10.0.0.9/", "https://localhost/", ""):
        assert not sh.is_allowed(url)
    assert sh.verify("http://127.0.0.1:9000/x") is True


@pytest.mark.asyncio
async def test_anything_not_listed_still_goes_through_the_public_https_check(monkeypatch):
    """protects=check_url passes a listed loopback origin and refuses an unlisted private, loopback or plain-http URL
    exactly as webhook_url_validator does; fails_when=allowlisting one service opens loopback in general;
    no_claim=DNS rebinding (the validator's concern)"""
    monkeypatch.setenv("OMNI_SELF_HOSTED", "http://127.0.0.1:2586")
    await sh.check_url("http://127.0.0.1:2586/omni-oncall")
    for url in ("http://127.0.0.1:2587/x", "https://127.0.0.1/x", "https://10.0.0.5/x", "http://ntfy.sh/x"):
        with pytest.raises(ValueError):
            await sh.check_url(url)


def test_a_pinned_certificate_is_the_only_trust_for_its_origin(monkeypatch, tmp_path):
    """protects=a pinned origin's context trusts only that certificate (not the system store) and still checks the
    host name; fails_when=a pinned service is also trusted through public CAs, or verification is switched off;
    no_claim=the handshake itself (covered by the live Mailpit check)"""
    import certifi
    pem = tmp_path / "pin.pem"
    pem.write_text(open(certifi.where()).read().split("-----END CERTIFICATE-----")[0] + "-----END CERTIFICATE-----\n")
    monkeypatch.setenv("OMNI_SELF_HOSTED", f"smtp://localhost:1025|{pem}")
    pinned, default = sh.ssl_context("smtp://localhost:1025"), sh.ssl_context("smtp://smtp.example.com:587")
    assert pinned.verify_mode == ssl.CERT_REQUIRED and pinned.check_hostname
    assert len(pinned.get_ca_certs()) == 1 and len(default.get_ca_certs()) != 1
