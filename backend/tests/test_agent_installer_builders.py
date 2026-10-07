"""Installers pin the platform certificate instead of turning TLS checks off.

They used to set accept_invalid_certs for self-signed deployments, so agents
accepted any certificate and anyone on the path could pose as the server. Now
they ship the certificate from AGENT_CA_CERT_FILE (server_ca_cert in
config.yaml) and the agents trust it and nothing else; without it, https://
URLs are checked against the endpoint's normal trust store."""
import os
import subprocess
import sys
from unittest.mock import MagicMock

import pytest
import yaml
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent_installer_builders as m


@pytest.fixture
def cert_file(tmp_path, monkeypatch):
    path = tmp_path / "server.crt"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", os.devnull,
         "-out", str(path), "-days", "1", "-subj", "/CN=10.0.0.5", "-addext", "subjectAltName=IP:10.0.0.5"],
        check=True, capture_output=True,
    )
    monkeypatch.setenv("AGENT_CA_CERT_FILE", str(path))
    return path


def test_https_config_ships_the_pinned_certificate(cert_file):
    cfg = m._config_yaml("https://10.0.0.5", "reg_test123")
    assert cfg["server_ca_cert"].strip() == cert_file.read_text().strip()
    assert cfg["accept_invalid_certs"] is False
    assert cfg["agent_id"] is None and cfg["agent_token"] is None
    assert cfg["api_base_url"] == "https://10.0.0.5"
    assert cfg["registration_key"] == "reg_test123"


def test_config_text_round_trips(cert_file):
    text = m.config_yaml_text("https://10.0.0.5", "reg_test123")
    assert "server_ca_cert: |" in text  # readable literal block
    assert yaml.safe_load(text) == m._config_yaml("https://10.0.0.5", "reg_test123")


def test_plain_http_config_pins_nothing(cert_file):
    cfg = m._config_yaml("http://10.0.0.5:5000", "reg_test123")
    assert "server_ca_cert" not in cfg
    assert cfg["accept_invalid_certs"] is False


def test_https_without_a_configured_certificate_keeps_normal_checks(monkeypatch):
    """A CA-signed deployment: verify against the OS store, never skip checks."""
    monkeypatch.delenv("AGENT_CA_CERT_FILE", raising=False)
    cfg = m._config_yaml("https://agents.customer-domain.example", "reg_test123")
    assert "server_ca_cert" not in cfg
    assert cfg["accept_invalid_certs"] is False


def test_a_private_key_is_never_shipped(tmp_path, monkeypatch):
    path = tmp_path / "combined.pem"
    path.write_text("-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n"
                    "-----BEGIN PRIVATE KEY-----\nBBBB\n-----END PRIVATE KEY-----\n")
    monkeypatch.setenv("AGENT_CA_CERT_FILE", str(path))
    with pytest.raises(HTTPException) as exc:
        m._config_yaml("https://10.0.0.5", "reg_test123")
    assert exc.value.status_code == 503


def test_unreadable_certificate_fails_the_build(monkeypatch):
    monkeypatch.setenv("AGENT_CA_CERT_FILE", "/nonexistent/server.crt")
    with pytest.raises(HTTPException):
        m._config_yaml("https://10.0.0.5", "reg_test123")


def test_windows_setup_script_writes_the_same_config(cert_file):
    from agent_rust_builder import _setup_svc_rust_ps1
    script = _setup_svc_rust_ps1("https://10.0.0.5", "reg_test123", "2.0.0")
    start = script.index("@'\n") + 3
    end = script.index("\n'@", start) + 1
    # Literal here-string (no $-expansion) holding exactly the shipped config
    assert script[start:end] == m.config_yaml_text("https://10.0.0.5", "reg_test123")


async def test_default_agent_url_is_https_when_a_certificate_is_pinned(cert_file, monkeypatch):
    from agent_download_endpoints import _resolve_url
    monkeypatch.delenv("PLATFORM_URL", raising=False)
    request = MagicMock()
    request.headers = {"host": "10.0.0.5:5000"}
    assert await _resolve_url(request, None) == "https://10.0.0.5"


async def test_default_agent_url_stays_http_without_a_pin(monkeypatch):
    from agent_download_endpoints import _resolve_url
    monkeypatch.delenv("AGENT_CA_CERT_FILE", raising=False)
    monkeypatch.delenv("PLATFORM_URL", raising=False)
    request = MagicMock()
    request.headers = {"host": "10.0.0.5:5000"}
    assert await _resolve_url(request, None) == "http://10.0.0.5:5000"
