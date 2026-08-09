"""Unit tests for backend/virustotal_client.py (Phase 55 Plan 05, INT-04).

Covers the full result-dict contract for scan_domain/scan_url/scan_file_hash
(mirroring scan_ip's already-tested shape), the error path, enrich_file_hashes
bulk keying/omission, key-absent graceful degrade, and a live TestClient
round-trip of POST /api/threat-intel/scan with scan_ip patched.

Hermetic: httpx.Client is patched per-test, never a real outbound request.
"""
import os
import sys
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import virustotal_client as vt_module
from virustotal_client import VirusTotalClient, enrich_file_hashes, get_virustotal_client


class _FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


class _FakeHttpxClient:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, headers=None):
        self.last_url = url
        self.last_headers = headers
        return self._response


def _patched_httpx_client(response):
    """Return a factory matching httpx.Client(timeout=...) call signature."""
    def _factory(*args, **kwargs):
        return _FakeHttpxClient(response)
    return _factory


VT_PAYLOAD = {
    "data": {
        "attributes": {
            "last_analysis_stats": {
                "malicious": 3,
                "suspicious": 1,
                "harmless": 60,
                "undetected": 5,
            },
            "reputation": -7,
            "last_analysis_date": 1700000000,
        }
    }
}


def _assert_full_contract(result):
    assert "error" not in result
    assert result["verdict"] == "Malicious"
    assert result["detectionRatio"] == "4/69"
    assert result["malicious"] == 3
    assert result["suspicious"] == 1
    assert result["harmless"] == 60
    assert result["undetected"] == 5
    assert result["scanDate"] == 1700000000
    assert result["reputation"] == -7
    assert isinstance(result["details"], dict)


class TestScanMethodsContract:
    def test_scan_domain_full_contract(self, monkeypatch):
        monkeypatch.setenv("VIRUSTOTAL_API_KEY", "test-key")
        client = VirusTotalClient()
        with patch("virustotal_client.httpx.Client", _patched_httpx_client(_FakeResponse(200, VT_PAYLOAD))):
            result = client.scan_domain("evil.example.com")
        _assert_full_contract(result)

    def test_scan_url_base64url_encodes_and_returns_contract(self, monkeypatch):
        monkeypatch.setenv("VIRUSTOTAL_API_KEY", "test-key")
        client = VirusTotalClient()
        fake_client = _FakeHttpxClient(_FakeResponse(200, VT_PAYLOAD))
        with patch("virustotal_client.httpx.Client", lambda *a, **k: fake_client):
            result = client.scan_url("http://evil.example.com/path")
        _assert_full_contract(result)
        assert "/urls/" in fake_client.last_url
        assert "http://" not in fake_client.last_url.split("/urls/")[1]

    def test_scan_file_hash_full_contract(self, monkeypatch):
        monkeypatch.setenv("VIRUSTOTAL_API_KEY", "test-key")
        client = VirusTotalClient()
        with patch("virustotal_client.httpx.Client", _patched_httpx_client(_FakeResponse(200, VT_PAYLOAD))):
            result = client.scan_file_hash("d" * 64)
        _assert_full_contract(result)

    def test_scan_file_hash_error_on_404(self, monkeypatch):
        monkeypatch.setenv("VIRUSTOTAL_API_KEY", "test-key")
        client = VirusTotalClient()
        with patch("virustotal_client.httpx.Client", _patched_httpx_client(_FakeResponse(404, {}))):
            result = client.scan_file_hash("nonexistent")
        assert "error" in result
        assert "verdict" not in result


class TestGracefulDegrade:
    def test_all_methods_return_error_when_key_unset(self, monkeypatch):
        monkeypatch.setenv("VIRUSTOTAL_API_KEY", "")
        client = VirusTotalClient()
        for method, arg in (
            (client.scan_ip, "8.8.8.8"),
            (client.scan_domain, "example.com"),
            (client.scan_url, "http://example.com"),
            (client.scan_file_hash, "abc123"),
        ):
            result = method(arg)
            assert "error" in result
            assert "verdict" not in result

    def test_get_virustotal_client_never_raises_without_key(self, monkeypatch):
        monkeypatch.setenv("VIRUSTOTAL_API_KEY", "")
        client = get_virustotal_client()
        assert isinstance(client, VirusTotalClient)


class TestEnrichFileHashes:
    def test_enrich_empty_input_returns_empty_dict(self):
        assert enrich_file_hashes([]) == {}
        assert enrich_file_hashes(None) == {}

    def test_enrich_keys_lowercased_and_omits_errors(self, monkeypatch):
        monkeypatch.setenv("VIRUSTOTAL_API_KEY", "test-key")

        def _fake_get(url, headers=None):
            if "ABCUPPER" in url or "abcupper" in url:
                return _FakeResponse(200, VT_PAYLOAD)
            return _FakeResponse(404, {})

        class _Client:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url, headers=None):
                return _fake_get(url, headers)

        with patch("virustotal_client.httpx.Client", lambda *a, **k: _Client()):
            result = enrich_file_hashes(["ABCUPPER", "willerror"])

        assert "abcupper" in result
        assert "error" not in result["abcupper"]
        assert "willerror" not in result

    def test_enrich_all_errored_returns_empty_when_key_unset(self, monkeypatch):
        monkeypatch.setenv("VIRUSTOTAL_API_KEY", "")
        result = enrich_file_hashes(["hash1", "hash2"])
        assert result == {}


class TestScanEndpointRoundTrip:
    """Live TestClient round-trip of POST /api/threat-intel/scan with
    scan_ip patched (not the real VirusTotal API)."""

    def _client(self, user):
        import threat_intel_endpoints as tie
        from authentication_service import get_current_user
        from database import get_database

        app = FastAPI()
        app.include_router(tie.router)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_database] = lambda: self._fake_db
        return app, tie

    def setup_method(self):
        class _InsertResult:
            inserted_id = "scan-doc-1"

        class _Collection:
            async def insert_one(self, doc):
                return _InsertResult()

        class _FakeDb:
            def __init__(self):
                self.threat_intel_scans = _Collection()

        self._fake_db = _FakeDb()

    def test_scan_success_returns_200(self, monkeypatch):
        from auth_types import TokenData

        user = TokenData(username="analyst", role="Super Admin", tenant_id="tenant-a", mfa_verified=True)
        app, tie = self._client(user)

        success_result = {
            "verdict": "Malicious",
            "detectionRatio": "4/69",
            "malicious": 3,
            "suspicious": 1,
            "harmless": 60,
            "undetected": 5,
            "scanDate": 1700000000,
            "reputation": -7,
            "details": {},
        }
        monkeypatch.setattr(
            tie,
            "get_virustotal_client",
            lambda: type("C", (), {"scan_ip": staticmethod(lambda ip: success_result)})(),
        )

        client = TestClient(app)
        response = client.post("/api/threat-intel/scan", json={"artifact": "8.8.8.8", "artifact_type": "ip"})

        assert response.status_code == 200
        body = response.json()
        assert body["verdict"] == "Malicious"
        assert body["detection_ratio"] == "4/69"

    def test_scan_error_returns_500(self, monkeypatch):
        from auth_types import TokenData

        user = TokenData(username="analyst", role="Super Admin", tenant_id="tenant-a", mfa_verified=True)
        app, tie = self._client(user)

        error_result = {"error": "VirusTotal API key not configured"}
        monkeypatch.setattr(
            tie,
            "get_virustotal_client",
            lambda: type("C", (), {"scan_ip": staticmethod(lambda ip: error_result)})(),
        )

        client = TestClient(app)
        response = client.post("/api/threat-intel/scan", json={"artifact": "8.8.8.8", "artifact_type": "ip"})

        assert response.status_code == 500
