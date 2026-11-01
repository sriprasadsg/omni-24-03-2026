"""Where a signal comes from, and how many different sources agree (Phase 83, plan 83-05, RESP-08 / D-01 / D-23).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=the origin table (native, three feeds, virustotal, onhost) counts a different source once and
the same event never twice; a mirrored alert collapses to its source; a tenant's own IOC rows, another
tenant's rows and free text never count; a feed listing without the thing on the host names no host;
fails_when=one native verdict plus the alert it writes reads as two origins, a tenant-added IOC becomes a
feed origin, a feed row alone makes a candidate, or a hostname shared by two agents picks one;
no_claim=a live feed (abuse.ch needs a key the tests do not have) or a real agent report.
"""
import importlib
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import signals
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import (seed_alert, seed_feed_ioc, seed_fim_event, seed_native_verdict,
                                    seed_response_agent, seed_telemetry, seed_tenant)

IP = "45.33.32.156"
SHA = "a" * 64
SHA2 = "b" * 64
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


async def _world(db, tenant="t1", host="host-1", agent="a1"):
    await signals.ensure_indexes(db)
    await seed_tenant(db, tenant, shadow=False)
    await seed_response_agent(db, tenant, agent, hostname=host, tokens=["block_ip_ttl"])


async def _observe(db, tenant="t1", now=NOW):
    return await signals.observe(db, tenant, await signals.agents_of(db, tenant), now)


def _origins(candidates):
    return {(c.agent_id, c.kind, c.indicator): set(c.origins) for c in candidates}


# ------------------------------------------------------------------ the origin of an alert

@pytest.mark.parametrize("row, origin", [
    ({"source": "native", "sha256": SHA}, "native"),
    ({"source": "native", "vt_detection_ratio": "3/70"}, "native"),
    ({"vt_detection_ratio": "12/70"}, "virustotal"),
    ({"sha256": SHA}, "onhost"),
    ({"sha256": SHA, "vt_detection_ratio": None}, "onhost"),
    ({"source": "FileWatcher", "sha256": SHA}, "onhost"),
    (None, "onhost"),
])
def test_alert_origin_collapses_a_mirror_to_its_source(row, origin):
    assert signals.alert_origin(row) == origin


@pytest.mark.parametrize("text, host", [
    ("45.33.32.156:443", "45.33.32.156"), ("[2606:4700::1]:443", "2606:4700::1"), ("45.33.32.156", "45.33.32.156"),
    ("*:*", "*"), ("2606:4700::1:443", None), ("", None), (None, None), (7, None), ("[::1", None)])
def test_remote_host_parses_the_address_out_of_host_port(text, host):
    assert signals.remote_host(text) == host


def test_the_origin_ids_are_the_six_the_plan_names():
    assert signals.ORIGIN_IDS == ("native", "feed:urlhaus", "feed:malwarebazaar", "feed:otx", "virustotal", "onhost")
    assert signals.KNOWN_FEEDS == ("urlhaus", "malwarebazaar", "otx")


# ------------------------------------------------------------------ one event is one origin

async def test_mirrored_native_alert_adds_no_second_origin(mongo_db):
    await _world(mongo_db)
    await seed_native_verdict(mongo_db, "t1", "host-1", kind="file", target="/tmp/x", sha256=SHA)
    await seed_alert(mongo_db, "t1", "host-1", sha256=SHA, source="native")
    got = _origins(await _observe(mongo_db))
    assert got == {("a1", "file", SHA): {"native"}}


async def test_mirrored_virustotal_alert_adds_no_second_origin(mongo_db):
    await _world(mongo_db)
    await seed_fim_event(mongo_db, "t1", "host-1", path="/opt/x", hash_after=SHA)
    await seed_alert(mongo_db, "t1", "host-1", sha256=SHA, vt_ratio="14/70")
    got = _origins(await _observe(mongo_db))
    assert got == {("a1", "file", SHA): {"virustotal"}}


async def test_an_alert_that_is_neither_is_onhost(mongo_db):
    await _world(mongo_db)
    await seed_alert(mongo_db, "t1", "host-1", sha256=SHA)
    assert _origins(await _observe(mongo_db)) == {("a1", "file", SHA): {"onhost"}}


async def test_native_alert_and_virustotal_alert_and_onhost_are_three_different_origins(mongo_db):
    await _world(mongo_db)
    await seed_alert(mongo_db, "t1", "host-1", sha256=SHA, source="native")
    await seed_alert(mongo_db, "t1", "host-1", sha256=SHA, vt_ratio="2/70")
    await seed_alert(mongo_db, "t1", "host-1", sha256=SHA)
    await seed_alert(mongo_db, "t1", "host-1", sha256=SHA)           # a second onhost entry is still one origin
    (cand,) = await _observe(mongo_db)
    assert set(cand.origins) == {"native", "virustotal", "onhost"}


async def test_two_rows_of_one_origin_at_the_same_instant_stay_one_origin(mongo_db):
    await _world(mongo_db)
    for _ in range(2):
        await seed_native_verdict(mongo_db, "t1", "host-1", kind="ip", target=IP, created_at=NOW - HOUR)
    (cand,) = await _observe(mongo_db)
    assert set(cand.origins) == {"native"} and not signals.corroborated(cand, two_signal=True)


# ------------------------------------------------------------------ feeds name a thing the host has

async def test_a_process_hash_and_a_malwarebazaar_row_give_the_feed_origin_with_the_exe_path(mongo_db):
    await _world(mongo_db)
    await seed_telemetry(mongo_db, "a1", processes=[{"sha256": SHA.upper(), "exe": "/usr/bin/evil"}, {"sha256": None}])
    await seed_feed_ioc(mongo_db, ioc_type="hash", value=SHA, feed="malwarebazaar", updated_at=NOW - HOUR)
    (cand,) = await _observe(mongo_db)
    assert (cand.kind, cand.indicator, cand.path) == ("file", SHA, "/usr/bin/evil")
    assert set(cand.origins) == {"feed:malwarebazaar"}


async def test_a_file_change_hash_and_a_feed_row_give_the_same_origin_with_the_changed_path(mongo_db):
    await _world(mongo_db)
    await seed_fim_event(mongo_db, "t1", "host-1", path="/etc/cron.d/evil", hash_after=SHA)
    await seed_feed_ioc(mongo_db, ioc_type="hash", value=SHA, feed="malwarebazaar", updated_at=NOW - HOUR)
    (cand,) = await _observe(mongo_db)
    assert cand.path == "/etc/cron.d/evil" and set(cand.origins) == {"feed:malwarebazaar"}


async def test_a_connection_and_a_url_row_give_the_urlhaus_origin_for_the_address(mongo_db):
    await _world(mongo_db)
    await seed_telemetry(mongo_db, "a1", connections=[{"remote_address": f"{IP}:443"}, {"remote_address": "10.1.1.1:80"}])
    await seed_feed_ioc(mongo_db, ioc_type="url", value=f"http://{IP}/x", source_ip=IP, feed="urlhaus", updated_at=NOW - HOUR)
    assert _origins(await _observe(mongo_db)) == {("a1", "ip", IP): {"feed:urlhaus"}}


async def test_a_feed_listing_on_no_host_makes_no_candidate(mongo_db):
    await _world(mongo_db)
    await seed_feed_ioc(mongo_db, ioc_type="hash", value=SHA, feed="malwarebazaar", updated_at=NOW - HOUR)
    await seed_feed_ioc(mongo_db, ioc_type="url", value=f"http://{IP}/x", source_ip=IP, feed="urlhaus", updated_at=NOW - HOUR)
    assert await _observe(mongo_db) == [] and await mongo_db.autonomy_signals.count_documents({}) == 0


async def test_a_url_row_whose_host_is_a_domain_and_a_private_address_row_are_ignored(mongo_db):
    await _world(mongo_db)
    await seed_telemetry(mongo_db, "a1", connections=[{"remote_address": "10.1.2.3:80"}, {"remote_address": "evil.example:80"}])
    await seed_feed_ioc(mongo_db, ioc_type="url", value="http://evil.example/x", source_ip="evil.example", feed="urlhaus",
                        updated_at=NOW - HOUR)
    await seed_feed_ioc(mongo_db, ioc_type="ip", value="10.1.2.3", source_ip="10.1.2.3", feed="otx", updated_at=NOW - HOUR)
    assert await _observe(mongo_db) == []


@pytest.mark.parametrize("age_hours, counts", [(47, True), (48, True), (49, False)])
async def test_a_feed_row_counts_for_48_hours_after_the_feed_last_listed_it(mongo_db, age_hours, counts):
    await _world(mongo_db)
    await seed_telemetry(mongo_db, "a1", processes=[{"sha256": SHA, "exe": "/x"}])
    await seed_feed_ioc(mongo_db, ioc_type="hash", value=SHA, feed="malwarebazaar", updated_at=NOW - age_hours * HOUR)
    assert bool(await _observe(mongo_db)) is counts


async def test_one_row_listed_by_two_feeds_is_two_origins_and_a_stale_listing_is_dropped(mongo_db):
    await _world(mongo_db)
    await seed_telemetry(mongo_db, "a1", processes=[{"sha256": SHA, "exe": "/x"}])
    await seed_feed_ioc(mongo_db, ioc_type="hash", value=SHA, feed="urlhaus", source_feeds=["urlhaus", "otx"],
                        updated_at=NOW - HOUR)
    (cand,) = await _observe(mongo_db)
    assert set(cand.origins) == {"feed:urlhaus", "feed:otx"}
    await mongo_db.edr_ioc.delete_many({})
    await mongo_db.autonomy_signals.delete_many({})
    await seed_feed_ioc(mongo_db, ioc_type="hash", value=SHA, feed="otx", source_feeds=["urlhaus", "otx"],
                        updated_at=NOW - HOUR, feed_seen={"urlhaus": NOW - 60 * HOUR, "otx": NOW - HOUR})
    (cand,) = await _observe(mongo_db)
    assert set(cand.origins) == {"feed:otx"}                          # urlhaus stopped listing it 60 hours ago


async def test_an_unknown_feed_name_is_not_an_origin(mongo_db):
    await _world(mongo_db)
    await seed_telemetry(mongo_db, "a1", processes=[{"sha256": SHA, "exe": "/x"}])
    await seed_feed_ioc(mongo_db, ioc_type="hash", value=SHA, feed="somebody", source_feeds=["somebody"], updated_at=NOW - HOUR)
    assert await _observe(mongo_db) == []


async def test_a_range_a_host_talks_into_becomes_a_range_candidate(mongo_db):
    await _world(mongo_db)
    await seed_telemetry(mongo_db, "a1", connections=[{"remote_address": f"{IP}:443"}])
    await seed_feed_ioc(mongo_db, ioc_type="ip", value="45.33.32.0/24", source_ip="45.33.32.0/24", feed="otx", updated_at=NOW - HOUR)
    await seed_feed_ioc(mongo_db, ioc_type="ip", value="10.0.0.0/8", source_ip="10.0.0.0/8", feed="otx", updated_at=NOW - HOUR)
    await seed_feed_ioc(mongo_db, ioc_type="ip", value="45.99.0.0/16", source_ip="45.99.0.0/16", feed="otx", updated_at=NOW - HOUR)
    assert _origins(await _observe(mongo_db)) == {("a1", "range", "45.33.32.0/24"): {"feed:otx"}}


# ------------------------------------------------------------------ native verdicts

async def test_a_native_url_verdict_becomes_an_ip_candidate_only_when_its_host_is_an_address(mongo_db):
    await _world(mongo_db)
    await seed_native_verdict(mongo_db, "t1", "host-1", kind="url", target=f"http://{IP}:8080/a.exe", created_at=NOW - HOUR)
    await seed_native_verdict(mongo_db, "t1", "host-1", kind="url", target="http://evil.example/a.exe", created_at=NOW - HOUR)
    await seed_native_verdict(mongo_db, "t1", "host-1", kind="url", target="http://10.1.1.1/a.exe", created_at=NOW - HOUR)
    assert _origins(await _observe(mongo_db)) == {("a1", "ip", IP): {"native"}}


async def test_a_clean_or_old_verdict_is_not_read(mongo_db):
    await _world(mongo_db)
    await seed_native_verdict(mongo_db, "t1", "host-1", kind="ip", target=IP, verdict="Clean", created_at=NOW - HOUR)
    await seed_native_verdict(mongo_db, "t1", "host-1", kind="ip", target="8.8.4.4", created_at=NOW - 26 * HOUR)
    assert await _observe(mongo_db) == []


# ------------------------------------------------------------------ what never counts (D-23, R7)

async def test_a_tenant_added_ioc_row_is_never_an_origin_for_any_tenant(mongo_db):
    for tenant, host, agent in (("t1", "host-1", "a1"), ("t2", "host-2", "a2")):
        await _world(mongo_db, tenant, host, agent)
        await seed_telemetry(mongo_db, agent, processes=[{"sha256": SHA, "exe": "/x"}], connections=[{"remote_address": f"{IP}:1"}])
    await seed_feed_ioc(mongo_db, ioc_type="hash", value=SHA, feed="malwarebazaar", updated_at=NOW - HOUR, tenant_id="t1")
    await seed_feed_ioc(mongo_db, ioc_type="url", value="x", source_ip=IP, feed="urlhaus", updated_at=NOW - HOUR, tenant_id="t2")
    assert await _observe(mongo_db, "t1") == [] and await _observe(mongo_db, "t2") == []


async def test_a_manual_ioc_in_its_own_shape_is_never_an_origin(mongo_db):
    await _world(mongo_db)
    await seed_telemetry(mongo_db, "a1", processes=[{"sha256": SHA, "exe": "/x"}], connections=[{"remote_address": f"{IP}:1"}])
    await mongo_db.edr_ioc.insert_one({"tenantId": "t1", "sha256": SHA, "ip_address": IP, "added_by": "admin",
                                       "added_at": NOW.isoformat()})
    assert await _observe(mongo_db) == []


async def test_deception_alerts_never_count(mongo_db):
    await _world(mongo_db)
    await mongo_db.deception_alerts.insert_one({"tenantId": "t1", "agent_id": "host-1", "sha256": SHA, "source_ip": IP,
                                                "created_at": NOW.isoformat()})
    assert await _observe(mongo_db) == []


async def test_free_text_never_names_an_indicator(mongo_db):
    await _world(mongo_db)
    await mongo_db.security_alerts.insert_one({"id": "x", "tenantId": "t1", "agent_id": "host-1", "type": "malware_detected",
                                               "title": f"blocked {IP}", "description": f"'/tmp/x' (SHA256 {SHA}) Malicious",
                                               "created_at": NOW.isoformat()})
    await seed_feed_ioc(mongo_db, ioc_type="url", value="x", source_ip=IP, feed="urlhaus", updated_at=NOW - HOUR)
    assert await _observe(mongo_db) == []


async def test_one_tenants_rows_never_reach_another_and_a_global_feed_row_serves_both(mongo_db):
    for tenant, host, agent in (("t1", "host-1", "a1"), ("t2", "host-2", "a2")):
        await _world(mongo_db, tenant, host, agent)
    await seed_native_verdict(mongo_db, "t1", "host-1", kind="ip", target=IP, created_at=NOW - HOUR)
    await seed_native_verdict(mongo_db, "t1", "host-2", kind="ip", target=IP, created_at=NOW - HOUR)   # t1 names t2's host
    await seed_alert(mongo_db, "t1", "host-2", sha256=SHA)
    await seed_feed_ioc(mongo_db, ioc_type="url", value="x", source_ip=IP, feed="urlhaus", updated_at=NOW - HOUR)
    assert _origins(await _observe(mongo_db, "t1")) == {("a1", "ip", IP): {"native", "feed:urlhaus"}}
    assert await _observe(mongo_db, "t2") == []
    await seed_telemetry(mongo_db, "a2", connections=[{"remote_address": f"{IP}:9"}])
    assert _origins(await _observe(mongo_db, "t2")) == {("a2", "ip", IP): {"feed:urlhaus"}}
    assert await mongo_db.autonomy_signals.count_documents({"tenantId": "t2", "agentId": "a1"}) == 0


async def test_a_hostname_shared_by_two_agents_is_skipped(mongo_db):
    await _world(mongo_db)
    await seed_response_agent(mongo_db, "t1", "a2", hostname="HOST-1", tokens=["block_ip_ttl"])
    await seed_native_verdict(mongo_db, "t1", "host-1", kind="ip", target=IP, created_at=NOW - HOUR)
    await seed_native_verdict(mongo_db, "t1", "a1", kind="ip", target="8.8.4.4", created_at=NOW - HOUR)
    assert _origins(await _observe(mongo_db)) == {("a1", "ip", "8.8.4.4"): {"native"}}


# ------------------------------------------------------------------ recording

async def test_a_tenant_with_nothing_ends_its_tick_with_no_writes(mongo_db):
    await seed_tenant(mongo_db, "t1", shadow=False)
    assert await _observe(mongo_db) == [] and await mongo_db.autonomy_signals.count_documents({}) == 0
    await _world(mongo_db, "t2", "h2", "a2")
    assert await _observe(mongo_db, "t2") == [] and await mongo_db.autonomy_signals.count_documents({}) == 0


async def test_observing_twice_changes_no_row_and_a_later_look_moves_no_first_sighting(mongo_db):
    await _world(mongo_db)
    await seed_native_verdict(mongo_db, "t1", "host-1", kind="ip", target=IP, created_at=NOW - HOUR)
    await seed_feed_ioc(mongo_db, ioc_type="url", value="x", source_ip=IP, feed="urlhaus", updated_at=NOW - HOUR)
    first = await _observe(mongo_db)
    assert {e["origin"] for e in first.new_evidence} == {"native", "feed:urlhaus"}
    before = await mongo_db.autonomy_signals.find_one({}, {"_id": 0})
    again = await _observe(mongo_db)
    assert again.new_evidence == [] and await mongo_db.autonomy_signals.find_one({}, {"_id": 0}) == before
    later = await _observe(mongo_db, now=NOW + 2 * HOUR)
    after = await mongo_db.autonomy_signals.find_one({}, {"_id": 0})
    assert later.new_evidence == []
    for name in ("native", "feed:urlhaus"):
        assert _utc(after["origins"][name]["firstSeenAt"]) == NOW
        assert _utc(after["origins"][name]["lastSeenAt"]) == NOW + 2 * HOUR
    assert _utc(after["lastSeenAt"]) == NOW + 2 * HOUR


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def test_evidence_time_is_the_sources_own_server_time_clamped_to_now(mongo_db):
    await _world(mongo_db)
    await seed_native_verdict(mongo_db, "t1", "host-1", kind="ip", target=IP, created_at=NOW + 5 * HOUR)
    (cand,) = await _observe(mongo_db)
    assert cand.origins["native"]["evidenceAt"] == NOW


async def test_candidates_come_back_in_sorted_order_and_are_capped(mongo_db, caplog, monkeypatch):
    await _world(mongo_db)
    for target in ("8.8.8.8", "1.1.1.1", "9.9.9.9"):
        await seed_native_verdict(mongo_db, "t1", "host-1", kind="ip", target=target, created_at=NOW - HOUR)
    got = await _observe(mongo_db)
    assert [c.indicator for c in got] == ["1.1.1.1", "8.8.8.8", "9.9.9.9"]
    monkeypatch.setattr(signals, "CANDIDATE_LIMIT", 2)
    with caplog.at_level("WARNING"):
        capped = await _observe(mongo_db)
    assert [c.indicator for c in capped] == ["1.1.1.1", "8.8.8.8"] and "taking the first 2" in caplog.text


async def test_the_decision_memory_survives_a_later_observation(mongo_db):
    await _world(mongo_db)
    await seed_native_verdict(mongo_db, "t1", "host-1", kind="ip", target=IP, created_at=NOW - HOUR)
    (cand,) = await _observe(mongo_db)
    key = {"tenantId": "t1", "agentId": cand.agent_id, "kind": "ip", "indicator": IP}
    await signals.remember(mongo_db, key, {"actionId": "AO-1", "at": NOW, "outcome": "blocked", "origins": ["native"]})
    (again,) = await _observe(mongo_db, now=NOW + HOUR)
    assert again.decision["actionId"] == "AO-1" and again.decision["origins"] == ["native"]


# ------------------------------------------------------------------ the rule

def _doc(**origins):
    return {"origins": {k: {"firstSeenAt": v[0], "evidenceAt": v[1]} for k, v in origins.items()}}


@pytest.mark.parametrize("gap, expected", [(timedelta(0), True), (timedelta(hours=23), True), (timedelta(hours=24), True),
                                           (timedelta(hours=24, seconds=1), False)])
@pytest.mark.parametrize("first", ["native", "feed:urlhaus"])
def test_two_origins_agree_when_their_first_sightings_are_at_most_24_hours_apart_in_either_order(first, gap, expected):
    other = "feed:urlhaus" if first == "native" else "native"
    doc = _doc(**{first: (NOW, NOW), other: (NOW + gap, NOW + gap)})
    assert signals.corroborated(doc, two_signal=True) is expected
    assert sorted(signals.counting_origins(doc)) == ["feed:urlhaus", "native"]


def test_evidence_before_a_block_began_does_not_count():
    doc = _doc(native=(NOW, NOW - HOUR), **{"feed:urlhaus": (NOW, NOW + HOUR)})
    assert signals.corroborated(doc, two_signal=True)
    assert not signals.corroborated(doc, two_signal=True, evidence_after=NOW)
    assert signals.corroborated(doc, two_signal=False, evidence_after=NOW)
    assert not signals.corroborated(doc, two_signal=False, evidence_after=NOW + 2 * HOUR)
    assert list(signals.counting_origins(doc, NOW)) == ["feed:urlhaus"]
    assert signals.counting_origins({"origins": {"native": {"firstSeenAt": NOW}}}, NOW) == {}


# ------------------------------------------------------------------ the migration

async def test_migration_028_creates_only_indexes_and_a_second_run_changes_nothing(mongo_db):
    migration = importlib.import_module("migrations.028_security_response")
    assert migration.DESCRIPTION
    await mongo_db.edr_ioc.insert_one({"ioc_type": "ip", "ioc_value": IP})
    before = [name for name in await mongo_db.list_collection_names()]
    await migration.up(mongo_db)
    first = {c: await mongo_db[c].index_information() for c in ("autonomy_signals", "edr_ioc")}
    await migration.up(mongo_db)
    second = {c: await mongo_db[c].index_information() for c in ("autonomy_signals", "edr_ioc")}
    assert first == second
    sig = first["autonomy_signals"]
    assert sig["signal_unique"]["unique"] is True
    assert sig["signal_unique"]["key"] == [("tenantId", 1), ("agentId", 1), ("kind", 1), ("indicator", 1)]
    assert sig["signal_ttl"]["expireAfterSeconds"] == 2592000 and sig["signal_ttl"]["key"] == [("lastSeenAt", 1)]
    assert first["edr_ioc"]["ioc_type_value"]["key"] == [("ioc_type", 1), ("ioc_value", 1)]
    assert first["edr_ioc"]["ioc_type_source_ip"]["key"] == [("ioc_type", 1), ("source_ip", 1)]
    # 83-11 adds the incident indexes (autonomy_incidents, and the incident lookup on autonomy_actions)
    assert sorted(await mongo_db.list_collection_names()) == sorted(
        set(before) | {"autonomy_signals", "autonomy_incidents", "autonomy_actions"})
    assert await mongo_db.edr_ioc.count_documents({}) == 1 and await mongo_db.autonomy_signals.count_documents({}) == 0
    assert await mongo_db.autonomy_incidents.count_documents({}) == 0 and await mongo_db.autonomy_actions.count_documents({}) == 0


def test_signals_module_stays_inside_its_size_and_source_rules():
    path = os.path.join(os.path.dirname(signals.__file__), "signals.py")
    text = open(path, encoding="utf-8").read()
    assert len(text.splitlines()) < 500 and "deception_alerts" not in text
    assert not re.search(r"\.description|\"description\"|\"title\"", text)
