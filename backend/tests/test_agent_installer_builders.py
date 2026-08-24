"""Regression test for the Rust agent registration-stuck-forever bug: a
generated config.yaml never set accept_invalid_certs, so an agent pointed at
this platform's own self-signed https:// cert (start-all-services.sh's
default) failed every registration POST at the TLS handshake and never
persisted agent_id/agent_token — silently stuck null forever, indistinguishable
from a fresh unregistered install."""
import sys, os
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent_installer_builders as m


def test_accept_invalid_certs_true_for_https_when_self_signed_pair_present():
    with patch("agent_installer_builders.os.path.exists", return_value=True):
        assert m._accept_invalid_certs("https://192.168.10.70") is True


def test_accept_invalid_certs_false_for_http_even_when_self_signed_pair_present():
    with patch("agent_installer_builders.os.path.exists", return_value=True):
        assert m._accept_invalid_certs("http://192.168.10.70:5000") is False


def test_accept_invalid_certs_false_for_https_when_no_cert_pair_present():
    """A customer's own real CA-signed https:// endpoint must never get
    verification silently disabled just because it's https."""
    with patch("agent_installer_builders.os.path.exists", return_value=False):
        assert m._accept_invalid_certs("https://agents.customer-domain.example") is False


def test_config_yaml_includes_accept_invalid_certs_field():
    with patch("agent_installer_builders.os.path.exists", return_value=True):
        cfg = m._config_yaml("https://192.168.10.70", "reg_test123")
    assert cfg["accept_invalid_certs"] is True
    assert cfg["agent_id"] is None
    assert cfg["agent_token"] is None
    assert cfg["api_base_url"] == "https://192.168.10.70"
    assert cfg["registration_key"] == "reg_test123"
