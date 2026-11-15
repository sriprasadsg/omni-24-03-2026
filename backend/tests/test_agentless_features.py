"""Tests for agentless data-collection and integration features.

Covers: syslog_receiver, threat_feed_sync,
        integration_service_siem, integration_service_edr
"""
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import syslog_receiver
from threat_feed_sync import (
    _normalise_otx_type, _fetch_urlhaus, _fetch_malwarebazaar,
    _upsert_iocs, run_threat_feed_sync,
)
from integration_service_siem import IntegrationServiceSiemMixin
from integration_service_edr import IntegrationServiceEdrMixin


# ── Shared mock helpers ───────────────────────────────────────────────────────

def _ctx_resp(status: int, json_data=None, text_data=""):
    """Async context-manager response for `async with session.post(...) as resp:`."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    resp.text = AsyncMock(return_value=text_data)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _await_resp(status: int, json_data=None):
    """Plain mock response for `resp = await session.post(...)`."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    return resp


def _ctx_session(post_resp):
    """Session mock for the `async with session.post(...)` pattern (SIEM / feeds)."""
    sess = MagicMock()
    sess.__aenter__ = AsyncMock(return_value=sess)
    sess.__aexit__ = AsyncMock(return_value=False)
    sess.post = MagicMock(return_value=post_resp)
    return sess


def _await_session(*post_responses):
    """Session mock for the `await session.post(...)` pattern (EDR)."""
    sess = MagicMock()
    sess.__aenter__ = AsyncMock(return_value=sess)
    sess.__aexit__ = AsyncMock(return_value=False)
    sess.post = AsyncMock(side_effect=list(post_responses))
    return sess


# ── Syslog Receiver ───────────────────────────────────────────────────────────

class TestSyslogReceiver:
    async def test_plain_syslog_stored_correctly(self):
        col = MagicMock()
        col.insert_one = AsyncMock()
        mock_db = MagicMock()
        mock_db.siem_logs = col

        proto = syslog_receiver.SyslogProtocol(tenant_id="t1")
        with patch("syslog_receiver.get_database", return_value=mock_db), \
             patch("tenant_context.set_tenant_id"):
            await proto.process_syslog_message("plain log message", ("10.0.0.1", 514))

        doc = col.insert_one.call_args[0][0]
        assert doc["log_type"] == "syslog"
        assert doc["source_ip"] == "10.0.0.1"
        assert doc["tenant_id"] == "t1"
        assert doc["raw_message"] == "plain log message"
        assert doc["device_vendor"] == "Unknown"

    async def test_cef_message_sets_log_type_cef(self):
        col = MagicMock()
        col.insert_one = AsyncMock()
        mock_db = MagicMock()
        mock_db.siem_logs = col

        cef = "CEF:0|Palo Alto|PAN-OS|10.1|threat|Threat Blocked|High|src=1.2.3.4"
        proto = syslog_receiver.SyslogProtocol(tenant_id="t1")
        with patch("syslog_receiver.get_database", return_value=mock_db), \
             patch("tenant_context.set_tenant_id"):
            await proto.process_syslog_message(cef, ("10.0.0.1", 514))

        doc = col.insert_one.call_args[0][0]
        assert doc["log_type"] == "cef"
        assert doc["device_vendor"] == "Palo Alto"
        assert doc["device_product"] == "PAN-OS"
        assert doc["severity"] == "High"

    async def test_cef_signature_and_name_extracted(self):
        col = MagicMock()
        col.insert_one = AsyncMock()
        mock_db = MagicMock()
        mock_db.siem_logs = col

        cef = "CEF:0|Vendor|Prod|1.0|SIG-001|Intrusion Attempt|Medium|"
        proto = syslog_receiver.SyslogProtocol(tenant_id="t2")
        with patch("syslog_receiver.get_database", return_value=mock_db), \
             patch("tenant_context.set_tenant_id"):
            await proto.process_syslog_message(cef, ("192.168.1.1", 514))

        doc = col.insert_one.call_args[0][0]
        assert doc["signature_id"] == "SIG-001"
        assert doc["name"] == "Intrusion Attempt"

    async def test_db_error_is_swallowed(self):
        mock_db = MagicMock()
        mock_db.siem_logs.insert_one = AsyncMock(side_effect=Exception("DB down"))
        proto = syslog_receiver.SyslogProtocol(tenant_id="t1")
        with patch("syslog_receiver.get_database", return_value=mock_db), \
             patch("tenant_context.set_tenant_id"):
            await proto.process_syslog_message("any log", ("10.0.0.1", 514))
        # Must not raise


# ── Threat Feed Sync ──────────────────────────────────────────────────────────

class TestNormaliseOtxType:
    def test_ipv4_and_ipv6(self):
        assert _normalise_otx_type("IPv4") == "ip"
        assert _normalise_otx_type("IPv6") == "ip"

    def test_domain_and_hostname(self):
        assert _normalise_otx_type("domain") == "domain"
        assert _normalise_otx_type("hostname") == "domain"

    def test_url(self):
        assert _normalise_otx_type("URL") == "url"

    def test_hash_variants(self):
        assert _normalise_otx_type("SHA256") == "hash"
        assert _normalise_otx_type("MD5") == "hash"
        assert _normalise_otx_type("FileHash-SHA1") == "hash"

    def test_unknown_returns_none(self):
        assert _normalise_otx_type("CERT") is None
        assert _normalise_otx_type("") is None


class TestFetchUrlhaus:
    async def test_success_returns_ioc_list(self):
        data = {"urls": [
            {"url": "http://evil.com/payload", "host": "evil.com",
             "threat": "malware_download", "date_added": "2024-01-01T00:00:00Z", "tags": ["malware"]},
        ]}
        sess = _ctx_session(_ctx_resp(200, json_data=data))
        result = await _fetch_urlhaus(sess)
        assert len(result) == 1
        ioc = result[0]
        assert ioc["ioc_type"] == "url"
        assert ioc["ioc_value"] == "http://evil.com/payload"
        assert ioc["source_feed"] == "urlhaus"
        assert ioc["confidence"] == 0.85

    async def test_non_200_returns_empty(self):
        sess = _ctx_session(_ctx_resp(503))
        assert await _fetch_urlhaus(sess) == []

    async def test_network_exception_returns_empty(self):
        sess = MagicMock()
        sess.post = MagicMock(side_effect=Exception("timeout"))
        assert await _fetch_urlhaus(sess) == []

    async def test_entries_without_url_skipped(self):
        data = {"urls": [{"host": "evil.com"}, {"url": "", "host": "x.com"}]}
        sess = _ctx_session(_ctx_resp(200, json_data=data))
        assert await _fetch_urlhaus(sess) == []


class TestFetchMalwarebazaar:
    async def test_success_returns_hash_iocs(self):
        data = {"data": [
            {"sha256_hash": "abc123", "tags": ["ransomware"],
             "first_seen": "2024-01-01T00:00:00Z",
             "file_name": "evil.exe", "file_type_mime": "application/x-msdownload",
             "signature": "Gandcrab"},
        ]}
        sess = _ctx_session(_ctx_resp(200, json_data=data))
        result = await _fetch_malwarebazaar(sess)
        assert len(result) == 1
        assert result[0]["ioc_type"] == "hash"
        assert result[0]["ioc_value"] == "abc123"
        assert result[0]["source_feed"] == "malwarebazaar"
        assert result[0]["confidence"] == 0.90

    async def test_non_200_returns_empty(self):
        sess = _ctx_session(_ctx_resp(404))
        assert await _fetch_malwarebazaar(sess) == []

    async def test_entries_without_hash_skipped(self):
        data = {"data": [{"tags": ["malware"]}]}
        sess = _ctx_session(_ctx_resp(200, json_data=data))
        assert await _fetch_malwarebazaar(sess) == []


class TestUpsertIocs:
    async def test_empty_list_returns_zero(self):
        db = MagicMock()
        assert await _upsert_iocs(db, []) == 0

    async def test_calls_update_one_per_ioc(self):
        db = MagicMock()
        db.edr_ioc.update_one = AsyncMock(
            return_value=MagicMock(upserted_id="new-id", modified_count=0)
        )
        iocs = [
            {"ioc_type": "url", "ioc_value": "http://bad.com"},
            {"ioc_type": "hash", "ioc_value": "deadbeef"},
        ]
        count = await _upsert_iocs(db, iocs)
        assert db.edr_ioc.update_one.call_count == 2
        assert count == 2

    async def test_db_error_per_ioc_is_swallowed(self):
        db = MagicMock()
        db.edr_ioc.update_one = AsyncMock(side_effect=Exception("write error"))
        count = await _upsert_iocs(db, [{"ioc_type": "url", "ioc_value": "http://x.com"}])
        assert count == 0

    async def test_upserted_id_increments_count(self):
        db = MagicMock()
        # First IOC: new insert (upserted_id set); second: no-op
        db.edr_ioc.update_one = AsyncMock(side_effect=[
            MagicMock(upserted_id="id-1", modified_count=0),
            MagicMock(upserted_id=None, modified_count=0),
        ])
        iocs = [
            {"ioc_type": "url", "ioc_value": "http://a.com"},
            {"ioc_type": "url", "ioc_value": "http://b.com"},
        ]
        count = await _upsert_iocs(db, iocs)
        assert count == 1


class TestRunThreatFeedSync:
    async def test_returns_summary_with_source_counts(self):
        db = MagicMock()
        db.edr_ioc.update_one = AsyncMock(
            return_value=MagicMock(upserted_id="x", modified_count=0)
        )
        db.signature_library.insert_one = AsyncMock()

        fake_urlhaus = [{"ioc_type": "url", "ioc_value": "http://e.com", "source_feed": "urlhaus",
                         "confidence": 0.85, "tags": [], "threat_type": "malware_download",
                         "source_ip": None, "last_seen": "2024-01-01"}]
        fake_bazaar = [{"ioc_type": "hash", "ioc_value": "abc123", "source_feed": "malwarebazaar",
                        "confidence": 0.90, "tags": [], "threat_type": "malware",
                        "source_ip": None, "last_seen": "2024-01-01"}]

        cs_mock = MagicMock()
        cs_mock.__aenter__ = AsyncMock(return_value=cs_mock)
        cs_mock.__aexit__ = AsyncMock(return_value=False)

        with patch("threat_feed_sync._fetch_urlhaus", AsyncMock(return_value=fake_urlhaus)), \
             patch("threat_feed_sync._fetch_malwarebazaar", AsyncMock(return_value=fake_bazaar)), \
             patch("threat_feed_sync._fetch_otx", AsyncMock(return_value=[])), \
             patch("threat_feed_sync.aiohttp.ClientSession", return_value=cs_mock):
            result = await run_threat_feed_sync(db)

        assert result["total_fetched"] == 2
        assert result["upserted"] == 2
        assert result["sources"]["urlhaus"] == 1
        assert result["sources"]["malwarebazaar"] == 1
        assert result["sources"]["otx"] == 0
        db.signature_library.insert_one.assert_called_once()


# ── SIEM Integration ──────────────────────────────────────────────────────────

class _SiemSvc(IntegrationServiceSiemMixin):
    def __init__(self, cfg=None):
        self._cfg = cfg

    async def _get_integration_config(self, category, platform):
        return self._cfg


class TestSiemIntegration:
    async def test_not_configured_returns_error(self):
        result = await _SiemSvc(cfg=None).send_to_siem("alert", "high", {}, platform="splunk")
        assert result["success"] is False
        assert "not configured" in result["error"]

    async def test_disabled_config_returns_error(self):
        result = await _SiemSvc(cfg={"enabled": False}).send_to_siem(
            "alert", "high", {}, platform="splunk"
        )
        assert result["success"] is False

    async def test_unsupported_platform_returns_error(self):
        result = await _SiemSvc(cfg={"enabled": True}).send_to_siem(
            "alert", "high", {}, platform="logstash"
        )
        assert result["success"] is False
        assert "Unsupported" in result["error"]

    async def test_splunk_success(self):
        resp = _ctx_resp(200, json_data={"text": "Success"})
        sess = _ctx_session(resp)
        svc = _SiemSvc(cfg={"enabled": True, "endpoint": "https://splunk:8088", "token": "tok"})
        # The endpoint passes the SSRF guard (patched: "splunk" does not resolve
        # here); delivery goes through the guarded session.
        with patch("integration_service_siem.avalidate_outbound_url", new=AsyncMock(side_effect=lambda u: u)), \
             patch("integration_service_siem.guarded_session", return_value=sess):
            result = await svc.send_to_siem("alert", "high", {"host": "srv1"}, "splunk")
        assert result["success"] is True

    async def test_splunk_http_error_returns_failure(self):
        resp = _ctx_resp(400, text_data="Bad request")
        sess = _ctx_session(resp)
        svc = _SiemSvc(cfg={"enabled": True, "endpoint": "https://splunk:8088", "token": "tok"})
        with patch("integration_service_siem.avalidate_outbound_url", new=AsyncMock(side_effect=lambda u: u)), \
             patch("integration_service_siem.guarded_session", return_value=sess):
            result = await svc.send_to_siem("alert", "high", {}, "splunk")
        assert result["success"] is False
        assert "400" in result["error"]
        assert "details" not in result  # the remote body is never relayed

    async def test_test_connection_unknown_platform_returns_error(self):
        result = await _SiemSvc(cfg={"enabled": True}).test_siem_connection("arcsight", {})
        assert result["success"] is False


# ── EDR Integration ───────────────────────────────────────────────────────────

class _EdrSvc(IntegrationServiceEdrMixin):
    def __init__(self, cfg=None):
        self._cfg = cfg

    async def _get_integration_config(self, category, platform):
        return self._cfg


class TestEdrIntegration:
    async def test_not_configured_returns_error(self):
        result = await _EdrSvc(cfg=None).send_to_edr("asset-1", "isolate", platform="crowdstrike")
        assert result["success"] is False
        assert "not configured" in result["error"]

    async def test_disabled_returns_error(self):
        result = await _EdrSvc(cfg={"enabled": False}).send_to_edr(
            "asset-1", "isolate", platform="sentinelone"
        )
        assert result["success"] is False

    async def test_unsupported_platform_returns_error(self):
        result = await _EdrSvc(cfg={"enabled": True}).send_to_edr(
            "asset-1", "isolate", platform="cylance"
        )
        assert result["success"] is False
        assert "Unsupported" in result["error"]

    async def test_crowdstrike_auth_failure(self):
        sess = _await_session(
            _await_resp(401),         # token request fails
        )
        cfg = {"enabled": True, "endpoint": "https://api.crowdstrike.com",
               "client_id": "id", "client_secret": "sec"}
        with patch("integration_service_edr.aiohttp.ClientSession", return_value=sess):
            result = await _EdrSvc(cfg=cfg).send_to_edr("host-1", "isolate", "crowdstrike")
        assert result["success"] is False
        assert "Auth failed" in result["error"]

    async def test_crowdstrike_action_success(self):
        sess = _await_session(
            _await_resp(201, {"access_token": "bearer-tok"}),   # token
            _await_resp(202, {"resources": [{"device_id": "host-1"}]}),  # action
        )
        cfg = {"enabled": True, "endpoint": "https://api.crowdstrike.com",
               "client_id": "cid", "client_secret": "csec"}
        with patch("integration_service_edr.aiohttp.ClientSession", return_value=sess):
            result = await _EdrSvc(cfg=cfg).send_to_edr("host-1", "isolate", "crowdstrike")
        assert result["success"] is True
        assert result["platform"] == "crowdstrike"

    async def test_crowdstrike_network_error_returns_failure(self):
        sess = MagicMock()
        sess.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
        sess.__aexit__ = AsyncMock(return_value=False)
        cfg = {"enabled": True, "endpoint": "https://api.crowdstrike.com",
               "client_id": "id", "client_secret": "sec"}
        with patch("integration_service_edr.aiohttp.ClientSession", return_value=sess):
            result = await _EdrSvc(cfg=cfg).send_to_edr("host-1", "isolate", "crowdstrike")
        assert result["success"] is False
