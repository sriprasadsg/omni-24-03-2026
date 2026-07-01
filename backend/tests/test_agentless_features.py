"""Tests for agentless data-collection and integration features.

Covers: syslog_receiver, ndr_service, threat_feed_sync,
        integration_service_siem, integration_service_edr
"""
import sys
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import syslog_receiver
from ndr_service import NDRService, _is_private_ip
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


def _ndr_db(flows=None, prior_count=0, open_count=5, critical_count=2):
    flows_col = MagicMock()
    anom_col = MagicMock()

    flow_cur = MagicMock()
    flow_cur.to_list = AsyncMock(return_value=flows or [])
    flows_col.find = MagicMock(return_value=flow_cur)
    flows_col.insert_one = AsyncMock()
    flows_col.count_documents = AsyncMock(return_value=prior_count)

    anom_limited = MagicMock()
    anom_limited.to_list = AsyncMock(return_value=[])
    anom_sorted = MagicMock()
    anom_sorted.limit = MagicMock(return_value=anom_limited)
    anom_cur = MagicMock()
    anom_cur.sort = MagicMock(return_value=anom_sorted)
    anom_col.find = MagicMock(return_value=anom_cur)
    anom_col.insert_one = AsyncMock()
    anom_col.delete_many = AsyncMock()
    anom_col.count_documents = AsyncMock(side_effect=[open_count, critical_count] * 4)

    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda k: {
        "network_flows": flows_col,
        "ndr_anomalies": anom_col,
        "ndr_baselines": MagicMock(),
    }[k])
    return db, flows_col, anom_col


def _make_flow(src="10.0.0.5", dst="8.8.8.8", dst_port=443,
               bytes_sent=1024, proto="HTTPS"):
    return {
        "src_ip": src, "dst_ip": dst, "dst_port": dst_port,
        "bytes_sent": bytes_sent, "protocol": proto,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


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


# ── NDR Service — helpers ─────────────────────────────────────────────────────

class TestIsPrivateIp:
    def test_rfc1918_addresses_private(self):
        for ip in ("10.0.0.1", "192.168.1.100", "172.16.0.1"):
            assert _is_private_ip(ip), ip

    def test_public_addresses_not_private(self):
        for ip in ("8.8.8.8", "1.1.1.1", "45.33.32.156"):
            assert not _is_private_ip(ip), ip

    def test_invalid_address_treated_as_private(self):
        assert _is_private_ip("not-an-ip")


# ── NDR Service — ingest ──────────────────────────────────────────────────────

class TestNDRIngestFlow:
    async def test_ingest_returns_doc_with_tenant(self):
        db, flows_col, _ = _ndr_db()
        svc = NDRService(db)
        doc = await svc.ingest_flow("tenant-1", {"src_ip": "10.0.0.1", "dst_ip": "8.8.8.8",
                                                  "bytes_sent": 1024, "protocol": "HTTPS"})
        flows_col.insert_one.assert_called_once()
        assert doc["tenant_id"] == "tenant-1"
        assert doc["src_ip"] == "10.0.0.1"
        assert "_id" in doc

    async def test_ingest_fills_defaults_for_missing_fields(self):
        db, _, _ = _ndr_db()
        doc = await NDRService(db).ingest_flow("t1", {})
        assert doc["src_ip"] == ""
        assert doc["bytes_sent"] == 0
        assert doc["protocol"] == "TCP"


# ── NDR Service — detection ───────────────────────────────────────────────────

class TestNDRDetection:
    async def test_no_flows_returns_empty(self):
        db, _, _ = _ndr_db(flows=[])
        assert await NDRService(db).run_detection("tenant-1") == []

    async def test_port_scan_detected(self):
        # 16 distinct dst_ports from one source → port_scan
        flows = [_make_flow(dst="10.0.1.1", dst_port=i, bytes_sent=100) for i in range(1, 17)]
        db, _, anom_col = _ndr_db(flows=flows)
        result = await NDRService(db).run_detection("tenant-1")
        hits = [r for r in result if r["type"] == "port_scan"]
        assert len(hits) == 1
        assert hits[0]["severity"] == "high"
        assert hits[0]["mitre_technique"] == "T1046"
        anom_col.insert_one.assert_called()

    async def test_data_exfiltration_detected(self):
        # Two flows totalling >50 MB to external IP
        flows = [
            _make_flow(bytes_sent=30 * 1024 * 1024),
            _make_flow(bytes_sent=25 * 1024 * 1024),
        ]
        db, _, _ = _ndr_db(flows=flows)
        result = await NDRService(db).run_detection("tenant-1")
        hits = [r for r in result if r["type"] == "data_exfiltration"]
        assert len(hits) == 1
        assert hits[0]["severity"] == "critical"
        assert hits[0]["mitre_technique"] == "T1048"

    async def test_c2_beacon_detected(self):
        # 12 small periodic flows to same external dst → C2 beacon
        flows = [_make_flow(bytes_sent=200) for _ in range(12)]
        db, _, _ = _ndr_db(flows=flows)
        result = await NDRService(db).run_detection("tenant-1")
        hits = [r for r in result if r["type"] == "c2_beacon"]
        assert len(hits) == 1
        assert hits[0]["severity"] == "critical"
        assert hits[0]["mitre_technique"] == "T1071"

    async def test_internal_traffic_no_exfil_anomaly(self):
        # Large bytes but to private IP — no exfiltration
        flows = [_make_flow(dst="192.168.1.50", bytes_sent=60 * 1024 * 1024)]
        db, _, _ = _ndr_db(flows=flows)
        result = await NDRService(db).run_detection("tenant-1")
        assert not any(r["type"] == "data_exfiltration" for r in result)


class TestNDRTrafficSummary:
    async def test_summary_returns_expected_keys(self):
        db, flows_col, anom_col = _ndr_db()
        flows_col.count_documents = AsyncMock(return_value=100)
        anom_col.count_documents = AsyncMock(side_effect=[7, 3])
        summary = await NDRService(db).get_traffic_summary("tenant-1")
        assert summary["flows_24h"] == 100
        assert summary["open_anomalies"] == 7
        assert summary["critical_anomalies"] == 3
        assert summary["detection_running"] is True
        assert summary["protocols_monitored"] > 0


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
        with patch("integration_service_siem.aiohttp.ClientSession", return_value=sess):
            result = await svc.send_to_siem("alert", "high", {"host": "srv1"}, "splunk")
        assert result["success"] is True

    async def test_splunk_http_error_returns_failure(self):
        resp = _ctx_resp(400, text_data="Bad request")
        sess = _ctx_session(resp)
        svc = _SiemSvc(cfg={"enabled": True, "endpoint": "https://splunk:8088", "token": "tok"})
        with patch("integration_service_siem.aiohttp.ClientSession", return_value=sess):
            result = await svc.send_to_siem("alert", "high", {}, "splunk")
        assert result["success"] is False
        assert "400" in result["error"]

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
