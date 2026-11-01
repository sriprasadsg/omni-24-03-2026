"""The threat-feed sync keeps each feed's name and sends the abuse.ch key only to abuse.ch (Phase 83, plan 83-05, D-26).

Value: protects=an IOC two feeds list keeps both names (so the sweep can count two feeds agreeing), the
ABUSE_CH_AUTH_KEY travels only as a request header to the two abuse.ch calls and never appears in a log
line, and with no key set the calls are exactly what they were; fails_when=the second feed overwrites the
first one's name, the key is logged, or the header is sent to OTX or when unset;
no_claim=the live abuse.ch service (a live count is a UAT item).
"""
import logging
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import threat_feed_sync
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

KEY = "k3y-secret-value-9f2c"
SHA = "c" * 64


class _Resp:
    def __init__(self, status, payload):
        self.status, self._payload = status, payload

    async def json(self, content_type=None):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    """Records the keyword arguments of every call and answers like abuse.ch / OTX would."""

    def __init__(self, status=200):
        self.calls, self.status = [], status

    def _answer(self, url, **kw):
        self.calls.append((url, kw))
        if "urlhaus" in url:
            return _Resp(self.status, {"urls": [{"url": "http://45.33.32.156/a", "host": "45.33.32.156"}]})
        if "abuse.ch" in url:
            return _Resp(self.status, {"data": [{"sha256_hash": SHA, "tags": ["x"]}]})
        return _Resp(self.status, {"results": []})

    post = get = _answer


def _headers(session):
    return [kw.get("headers") for _, kw in session.calls]


async def test_with_the_key_set_both_abuse_ch_calls_carry_it_as_a_header_and_nothing_logs_it(monkeypatch, caplog):
    monkeypatch.setattr(threat_feed_sync, "ABUSE_CH_AUTH_KEY", KEY)
    session = _Session()
    with caplog.at_level(logging.DEBUG):
        urlhaus = await threat_feed_sync._fetch_urlhaus(session)
        bazaar = await threat_feed_sync._fetch_malwarebazaar(session)
    assert len(urlhaus) == 1 and len(bazaar) == 1
    assert _headers(session) == [{"Auth-Key": KEY}, {"Auth-Key": KEY}]
    assert KEY not in caplog.text


async def test_a_rejected_key_is_reported_without_the_key(monkeypatch, caplog):
    monkeypatch.setattr(threat_feed_sync, "ABUSE_CH_AUTH_KEY", KEY)
    session = _Session(status=401)
    with caplog.at_level(logging.DEBUG):
        assert await threat_feed_sync._fetch_urlhaus(session) == []
        assert await threat_feed_sync._fetch_malwarebazaar(session) == []
    assert KEY not in caplog.text and "Auth-Key" in caplog.text


async def test_unset_the_calls_carry_no_header(monkeypatch):
    monkeypatch.setattr(threat_feed_sync, "ABUSE_CH_AUTH_KEY", "")
    session = _Session()
    await threat_feed_sync._fetch_urlhaus(session)
    await threat_feed_sync._fetch_malwarebazaar(session)
    assert all(not h for h in _headers(session)) and threat_feed_sync._abuse_headers() == {}


async def test_otx_never_receives_the_abuse_ch_key(monkeypatch):
    monkeypatch.setattr(threat_feed_sync, "ABUSE_CH_AUTH_KEY", KEY)
    monkeypatch.setattr(threat_feed_sync, "OTX_API_KEY", "otx-key")
    session = _Session()
    await threat_feed_sync._fetch_otx(session)
    assert _headers(session) == [{"X-OTX-API-KEY": "otx-key"}]


def test_the_module_never_formats_the_key_into_a_log_line():
    src = open(threat_feed_sync.__file__, encoding="utf-8").read()
    assert src.count("ABUSE_CH_AUTH_KEY") >= 1
    for line in src.splitlines():
        if "logger." in line:
            assert "ABUSE_CH_AUTH_KEY" not in line and "_abuse_headers" not in line


async def test_two_feeds_listing_one_indicator_keep_both_names_and_the_last_one_in_source_feed(mongo_db):
    first = {"ioc_type": "hash", "ioc_value": SHA, "source_ip": None, "source_feed": "malwarebazaar", "confidence": 0.9}
    second = {"ioc_type": "hash", "ioc_value": SHA, "source_ip": None, "source_feed": "otx", "confidence": 0.75}
    await threat_feed_sync._upsert_iocs(mongo_db, [dict(first)])
    await threat_feed_sync._upsert_iocs(mongo_db, [dict(second)])
    await threat_feed_sync._upsert_iocs(mongo_db, [dict(first)])           # the first feed lists it again
    (row,) = [r async for r in mongo_db.edr_ioc.find({}, {"_id": 0})]
    assert sorted(row["source_feeds"]) == ["malwarebazaar", "otx"] and row["source_feed"] == "malwarebazaar"
    assert set(row["feed_seen"]) == {"malwarebazaar", "otx"}
    seen = {k: datetime.fromisoformat(v) for k, v in row["feed_seen"].items()}
    assert seen["malwarebazaar"] >= seen["otx"] and datetime.fromisoformat(row["updated_at"]).tzinfo == timezone.utc
    assert await mongo_db.edr_ioc.count_documents({}) == 1


async def test_a_row_with_one_feed_gets_a_one_name_list(mongo_db):
    await threat_feed_sync._upsert_iocs(mongo_db, [{"ioc_type": "url", "ioc_value": "http://x/y", "source_ip": "1.2.3.4",
                                                    "source_feed": "urlhaus"}] * 2)
    (row,) = [r async for r in mongo_db.edr_ioc.find({}, {"_id": 0})]
    assert row["source_feeds"] == ["urlhaus"] and row["source_feed"] == "urlhaus"
