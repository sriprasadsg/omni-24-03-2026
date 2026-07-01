"""
Tests for SSRF validation helpers in integrations_v2, webhook_endpoints,
and pentest_integration_service.

Each guard function must:
  - Block loopback and RFC-1918 private addresses
  - Block non-HTTP(S) schemes
  - Block empty / None inputs
  - Allow public IP addresses (mocked DNS to avoid network calls in CI)
"""
import sys
import os
import socket

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch


# ===========================================================================
# Helpers
# ===========================================================================

def _public_dns_mock(host, _port):
    """Simulate a DNS response that resolves to a public (non-private) IP."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("52.1.2.3", 0))]


def _loopback_dns_mock(host, _port):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0))]


def _private_10_dns_mock(host, _port):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 0))]


def _private_192_dns_mock(host, _port):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.1", 0))]


def _private_172_dns_mock(host, _port):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("172.16.0.1", 0))]


# ===========================================================================
# integrations_v2._validate_external_url
# ===========================================================================

class TestValidateExternalUrl:
    """Tests for the SSRF guard in integrations_v2."""

    def test_blocks_localhost_by_name(self):
        from integrations_v2 import _validate_external_url
        with patch("integrations_v2.socket.getaddrinfo", _loopback_dns_mock):
            assert _validate_external_url("http://localhost/evil") is False

    def test_blocks_loopback_ip_127_0_0_1(self):
        from integrations_v2 import _validate_external_url
        # getaddrinfo is not called for a raw IP; ipaddress handles it directly
        assert _validate_external_url("http://127.0.0.1/metadata") is False

    def test_blocks_loopback_ip_0_0_0_0(self):
        from integrations_v2 import _validate_external_url
        assert _validate_external_url("http://0.0.0.0/") is False

    def test_blocks_private_range_10_x(self):
        from integrations_v2 import _validate_external_url
        assert _validate_external_url("http://10.0.0.1/internal") is False

    def test_blocks_private_range_192_168(self):
        from integrations_v2 import _validate_external_url
        assert _validate_external_url("http://192.168.1.1/admin") is False

    def test_blocks_private_range_172_16(self):
        from integrations_v2 import _validate_external_url
        assert _validate_external_url("http://172.16.0.1/api") is False

    def test_blocks_ftp_scheme(self):
        from integrations_v2 import _validate_external_url
        assert _validate_external_url("ftp://example.com") is False

    def test_blocks_file_scheme(self):
        from integrations_v2 import _validate_external_url
        assert _validate_external_url("file:///etc/passwd") is False

    def test_blocks_empty_string(self):
        from integrations_v2 import _validate_external_url
        assert _validate_external_url("") is False

    def test_blocks_none(self):
        from integrations_v2 import _validate_external_url
        assert _validate_external_url(None) is False

    def test_blocks_hostname_that_resolves_to_loopback(self):
        """A hostname resolving to 127.0.0.1 must be rejected even if name looks public."""
        from integrations_v2 import _validate_external_url
        with patch("integrations_v2.socket.getaddrinfo", _loopback_dns_mock):
            assert _validate_external_url("https://internal.example.com/hook") is False

    def test_blocks_hostname_resolving_to_rfc1918_10(self):
        from integrations_v2 import _validate_external_url
        with patch("integrations_v2.socket.getaddrinfo", _private_10_dns_mock):
            assert _validate_external_url("https://corp.internal/api") is False

    def test_blocks_hostname_resolving_to_rfc1918_192_168(self):
        from integrations_v2 import _validate_external_url
        with patch("integrations_v2.socket.getaddrinfo", _private_192_dns_mock):
            assert _validate_external_url("https://internal.corp.lan/api") is False

    def test_allows_public_https_url(self):
        """A URL that resolves to a public IP must be allowed."""
        from integrations_v2 import _validate_external_url
        with patch("integrations_v2.socket.getaddrinfo", _public_dns_mock):
            assert _validate_external_url("https://hooks.slack.com/services/T000/B000/xxx") is True

    def test_allows_public_http_url(self):
        from integrations_v2 import _validate_external_url
        with patch("integrations_v2.socket.getaddrinfo", _public_dns_mock):
            assert _validate_external_url("http://api.example.com/webhook") is True

    def test_blocks_dns_lookup_failure(self):
        """If DNS resolution fails entirely, the URL must be rejected (fail-closed)."""
        from integrations_v2 import _validate_external_url

        def _fail_dns(host, _port):
            raise socket.gaierror("Name or service not known")

        with patch("integrations_v2.socket.getaddrinfo", _fail_dns):
            assert _validate_external_url("https://nonexistent.invalid/hook") is False


# ===========================================================================
# webhook_endpoints._is_safe_webhook_url
# ===========================================================================

class TestIsWebhookUrlSafe:
    """Tests for the SSRF guard in webhook_endpoints."""

    def test_blocks_localhost_port(self):
        from webhook_endpoints import _is_safe_webhook_url
        with patch("webhook_endpoints.socket.getaddrinfo", _loopback_dns_mock):
            assert _is_safe_webhook_url("http://localhost:27017") is False

    def test_blocks_loopback_direct_ip(self):
        from webhook_endpoints import _is_safe_webhook_url
        assert _is_safe_webhook_url("http://127.0.0.1:6379") is False

    def test_blocks_private_ip_10_x(self):
        from webhook_endpoints import _is_safe_webhook_url
        assert _is_safe_webhook_url("http://10.0.0.5/hook") is False

    def test_blocks_private_ip_192_168(self):
        from webhook_endpoints import _is_safe_webhook_url
        assert _is_safe_webhook_url("http://192.168.0.1/") is False

    def test_blocks_docker_service_name_resolving_to_private(self):
        """Docker internal service names (mongo, redis) resolving to private IPs must be blocked."""
        from webhook_endpoints import _is_safe_webhook_url
        with patch("webhook_endpoints.socket.getaddrinfo", _private_192_dns_mock):
            assert _is_safe_webhook_url("http://mongo:27017") is False
        with patch("webhook_endpoints.socket.getaddrinfo", _loopback_dns_mock):
            assert _is_safe_webhook_url("http://redis:6379") is False

    def test_blocks_javascript_scheme(self):
        from webhook_endpoints import _is_safe_webhook_url
        assert _is_safe_webhook_url("javascript:alert(1)") is False

    def test_blocks_data_uri(self):
        from webhook_endpoints import _is_safe_webhook_url
        assert _is_safe_webhook_url("data:text/html,<h1>xss</h1>") is False

    def test_blocks_empty_string(self):
        from webhook_endpoints import _is_safe_webhook_url
        assert _is_safe_webhook_url("") is False

    def test_blocks_none(self):
        from webhook_endpoints import _is_safe_webhook_url
        assert _is_safe_webhook_url(None) is False

    def test_allows_public_https(self):
        from webhook_endpoints import _is_safe_webhook_url
        with patch("webhook_endpoints.socket.getaddrinfo", _public_dns_mock):
            assert _is_safe_webhook_url("https://outlook.office.com/webhook/xxx") is True

    def test_guards_are_consistent_with_integrations_v2(self):
        """Both SSRF guards must agree on clearly-private addresses."""
        from integrations_v2 import _validate_external_url
        from webhook_endpoints import _is_safe_webhook_url
        # Raw private IPs — no DNS mock needed (ipaddress handles them)
        private_urls = [
            "http://10.0.0.1/",
            "http://192.168.1.1/",
            "http://172.16.0.1/",
            "http://127.0.0.1/",
        ]
        for url in private_urls:
            assert _validate_external_url(url) is False, f"integrations_v2 allowed {url}"
            assert _is_safe_webhook_url(url) is False, f"webhook_endpoints allowed {url}"


# ===========================================================================
# pentest_integration_service._validate_scan_target
# ===========================================================================

class TestPentestValidateScanTarget:
    """Tests for the nmap/nikto SSRF guard."""

    def test_rejects_empty_target(self):
        from pentest_integration_service import _validate_scan_target
        with pytest.raises(ValueError, match="required"):
            _validate_scan_target("")

    def test_rejects_whitespace_only_string(self):
        """Whitespace-only string has no valid hostname — DNS resolution fails and raises ValueError."""
        from pentest_integration_service import _validate_scan_target

        def _fail_dns(host, _port):
            # Whitespace is not a valid hostname — DNS refuses it
            raise socket.gaierror("Name or service not known")

        with patch("pentest_integration_service.socket.getaddrinfo", _fail_dns):
            with pytest.raises(ValueError):
                _validate_scan_target("   ")

    def test_rejects_hostname_resolving_to_loopback(self):
        from pentest_integration_service import _validate_scan_target
        with patch("pentest_integration_service.socket.getaddrinfo", _loopback_dns_mock):
            with pytest.raises(ValueError, match="non-public"):
                _validate_scan_target("internal-host")

    def test_rejects_hostname_resolving_to_10_network(self):
        from pentest_integration_service import _validate_scan_target
        with patch("pentest_integration_service.socket.getaddrinfo", _private_10_dns_mock):
            with pytest.raises(ValueError):
                _validate_scan_target("internal.corp")

    def test_rejects_hostname_resolving_to_192_168(self):
        from pentest_integration_service import _validate_scan_target
        with patch("pentest_integration_service.socket.getaddrinfo", _private_192_dns_mock):
            with pytest.raises(ValueError):
                _validate_scan_target("lan.host")

    def test_rejects_hostname_resolving_to_172_16(self):
        from pentest_integration_service import _validate_scan_target
        with patch("pentest_integration_service.socket.getaddrinfo", _private_172_dns_mock):
            with pytest.raises(ValueError):
                _validate_scan_target("intranet.host")

    def test_rejects_direct_loopback_ip(self):
        from pentest_integration_service import _validate_scan_target
        with pytest.raises(ValueError):
            _validate_scan_target("127.0.0.1")

    def test_rejects_direct_private_ip(self):
        from pentest_integration_service import _validate_scan_target
        with pytest.raises(ValueError):
            _validate_scan_target("10.10.10.10")

    def test_raises_on_unresolvable_hostname(self):
        """Unresolvable hostnames must raise rather than silently pass."""
        from pentest_integration_service import _validate_scan_target

        def _fail_dns(host, _port):
            raise socket.gaierror("Name or service not known")

        with patch("pentest_integration_service.socket.getaddrinfo", _fail_dns):
            with pytest.raises(ValueError, match="resolve"):
                _validate_scan_target("nonexistent.invalid")

    def test_accepts_public_target_via_mock(self):
        """A hostname that resolves to a public IP must be accepted."""
        from pentest_integration_service import _validate_scan_target
        with patch("pentest_integration_service.socket.getaddrinfo", _public_dns_mock):
            # Should not raise
            _validate_scan_target("scanme.nmap.org")
