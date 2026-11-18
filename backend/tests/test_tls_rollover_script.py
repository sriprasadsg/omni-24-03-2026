"""scripts/tls_rollover.sh moves through prepare, switch, rollback and finish as agent_tls_trust reads it.

Value: protects=the certificate change steps on the live server (nginx keeps a certificate it can serve, the
old one is kept until finish, the new one is one macOS accepts); fails_when=the next certificate is a CA,
lacks serverAuth, outlives 825 days or drops a subjectAltName, a step leaves the trust list or state the
backend cannot read, or rollback does not restore the old certificate; no_claim=a real nginx reload (the
sandbox replaces nginx with true).
"""
import json
import os
import subprocess
import sys
from datetime import timedelta

import pytest
from cryptography import x509

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent_tls_trust as m  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "tls_rollover.sh")


@pytest.fixture
def box(tmp_path, monkeypatch):
    ssl_dir = tmp_path / "ssl"
    ssl_dir.mkdir()
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(ssl_dir / "omni.key"),
                    "-out", str(ssl_dir / "omni.crt"), "-days", "1095", "-subj", "/O=OmniAgent/CN=135.237.98.107",
                    "-addext", "subjectAltName=IP:135.237.98.107,IP:10.0.0.4,IP:127.0.0.1,DNS:localhost"],
                   check=True, capture_output=True)
    env = dict(os.environ, TLS_ROLLOVER_SANDBOX="1", NGINX="true", RELOAD="true", TLS_DIR=str(tmp_path / "tls"),
               NGINX_SSL_DIR=str(ssl_dir), NGINX_SITES=str(tmp_path / "nginx"))
    monkeypatch.setattr(m, "TRUST_FILE", tmp_path / "tls" / "agent-trust.pem")
    monkeypatch.setattr(m, "STATE_FILE", tmp_path / "tls" / "rollover.json")
    monkeypatch.setattr(m, "SERVED_CERT_FILE", ssl_dir / "omni.crt")

    def run(step, ok=True):
        out = subprocess.run(["bash", SCRIPT, step], env=env, capture_output=True, text=True)
        assert (out.returncode == 0) is ok, out.stdout + out.stderr
        m._cache.update(key=None, value=None)
        return out

    old = (ssl_dir / "omni.crt").read_text()
    yield {"run": run, "tls": tmp_path / "tls", "ssl": ssl_dir, "site": tmp_path / "nginx" / "sites-enabled" / "omni-tls-probe",
           "old": old}
    m._cache.update(key=None, value=None)


def test_a_change_goes_prepare_switch_rollback_switch_finish(box):
    box["run"]("switch", ok=False)  # nothing prepared yet
    box["run"]("prepare")
    nxt = (box["tls"] / "next.crt").read_text()
    cert = x509.load_pem_x509_certificate(nxt.encode())
    assert cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
    assert x509.ExtendedKeyUsageOID.SERVER_AUTH in cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert cert.not_valid_after_utc - cert.not_valid_before_utc <= timedelta(days=825)
    sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert {str(ip) for ip in sans.get_values_for_type(x509.IPAddress)} == {"135.237.98.107", "10.0.0.4", "127.0.0.1"}
    assert oct(os.stat(box["tls"] / "next.key").st_mode & 0o777) == "0o600"
    ro = m.current()
    assert ro["phase"] == "prepared" and ro["probePort"] == 8443
    assert ro["fingerprints"] == [m.fingerprint(box["old"]), m.fingerprint(nxt)] and ro["next"] == [m.fingerprint(nxt)]
    assert "listen 8443 ssl" in box["site"].read_text()
    box["run"]("prepare", ok=False)  # one change at a time

    box["run"]("switch")
    assert (box["ssl"] / "omni.crt").read_text() == nxt and not box["site"].exists()
    assert m.current()["phase"] == "switched" and m.current()["probePort"] is None

    box["run"]("rollback")
    assert (box["ssl"] / "omni.crt").read_text() == box["old"] and box["site"].exists()
    assert m.current()["phase"] == "prepared"

    box["run"]("switch")
    box["run"]("finish")
    ro = m.current()
    assert ro["phase"] == "finished" and ro["fingerprints"] == [m.fingerprint(nxt)]
    assert not (box["tls"] / "previous.key").exists() and not (box["tls"] / "next.key").exists()
    assert json.loads((box["tls"] / "rollover.json").read_text())["probePort"] is None
    box["run"]("rollback", ok=False)


def test_a_prepared_change_can_be_withdrawn(box):
    box["run"]("prepare")
    box["run"]("rollback")
    assert m.current() is None and not box["site"].exists()
    assert (box["ssl"] / "omni.crt").read_text() == box["old"]
