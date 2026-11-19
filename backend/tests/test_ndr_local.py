"""The server's own network sensor (ndr_local, migration 045; Wave 4 / 88.1). protects/fails_when/no_claim per test.
The EVE input is real Suricata 7.0.3 output (tests/fixtures/ndr: the uid=0(root) test signature, sid 2100498, and its
stats), plus lines shaped like it; MongoDB is real.
"""
import importlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import ndr_local
import ndr_sensors
import siem_pipeline
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "ndr", "suricata-7.0.3-uid-root.eve.json")
REAL_ALERT, REAL_STATS = open(FIXTURE, "rb").read().splitlines()
migration = importlib.import_module("migrations.045_network_ids_rules")


def _alert(ts, sid=2100498, severity=2, category="Potentially Bad Traffic", signature="GPL ATTACK_RESPONSE id check returned root",
           src="203.0.113.80", technique=None):
    meta = {"mitre_technique_id": [technique]} if technique else {}
    return json.dumps({"timestamp": ts, "event_type": "alert", "src_ip": src, "src_port": 80, "dest_ip": "10.0.0.4", "dest_port": 40000,
                       "proto": "TCP", "alert": {"signature_id": sid, "signature": signature, "category": category,
                                                 "severity": severity, "metadata": meta}}).encode()


def _stats(ts, packets, drops=0, uptime=600, rules=53432):
    return json.dumps({"timestamp": ts, "event_type": "stats", "stats": {"uptime": uptime, "capture": {"kernel_packets": packets, "kernel_drops": drops},
                       "decoder": {"pkts": packets}, "detect": {"engines": [{"id": 0, "rules_loaded": rules, "rules_failed": 0}]}}}).encode()


@pytest_asyncio.fixture
async def world(mongo_db, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    monkeypatch.setenv("SOC_AUTO_TRIAGE", "0")
    await siem_pipeline.ensure_indexes(mongo_db)
    await migration.up(mongo_db)
    return mongo_db, str(tmp_path / "eve.json")


def _write(path, *lines, mode="ab"):
    with open(path, mode) as f:
        f.write(b"".join(line + b"\n" for line in lines))


@pytest.mark.asyncio
async def test_the_real_test_signature_becomes_a_siem_event_and_one_soc_alert(world):
    """protects=Suricata's own alert for the uid=0(root) test signature is stored as a network SIEM event and raises
    one medium Platform alert per signature, a line read again stores nothing, and a new hit on the same signature
    counts as a repeat; fails_when=the test signature raises no alert, two alerts, or one per line read;
    no_claim=that Suricata on eth0 sees the traffic (enable_local_sensor.sh's check)"""
    db, path = world
    _write(path, REAL_ALERT, REAL_STATS)
    out = await ndr_local.read_once(db, path)
    assert (out["lines"], out["alerts"], out["stats"]) == (2, 1, 1)
    event = await db.soc_log_events.find_one({"source": "network"}, {"_id": 0})
    assert (event["tenantId"], event["action"], event["signatureId"], event["idsSeverity"], event["srcIp"]) == \
        ("platform-admin", "ids_alert", 2100498, 2, "203.0.113.80")
    assert event["at"].replace(tzinfo=timezone.utc) == datetime(2026, 11, 19, 3, 46, 40, 59000, tzinfo=timezone.utc)  # Mongo keeps ms
    alerts = await db.security_alerts.find({}, {"_id": 0}).to_list(10)
    assert len(alerts) == 1 and (alerts[0]["type"], alerts[0]["severity"], alerts[0]["tenantId"]) == ("ids_alert", "medium", "platform-admin")
    assert alerts[0]["title"] == "GPL ATTACK_RESPONSE id check returned root"
    assert (await ndr_local.read_once(db, path))["lines"] == 0
    _write(path, REAL_ALERT, _alert("2026-11-19T08:00:00.000000+0000"))  # the same line again, then a new hit
    out = await ndr_local.read_once(db, path)
    assert out["alerts"] == 1 and await db.soc_log_events.count_documents({"source": "network"}) == 2
    assert (await db.security_alerts.find_one({}))["occurrences"] == 2 and await db.security_alerts.count_documents({}) == 1


@pytest.mark.asyncio
async def test_severity_three_stays_in_the_siem_and_a_named_technique_reaches_the_alert(world):
    """protects=a low (severity 3) alert is an event only, a severity 1 alert is a high SOC alert carrying the MITRE
    technique its rule names, and the matching library rule records a hit; fails_when=every informational alert
    lands in the queue, or the technique is lost; no_claim=ET Open's own metadata quality"""
    db, path = world
    _write(path, _alert("2026-11-19T08:00:00+0000", sid=1, severity=3, category="Detection of a Network Scan"),
           _alert("2026-11-19T08:00:01+0000", sid=2, severity=1, category="Web Application Attack", signature="ET WEB_SERVER x",
                  technique="T1190"))
    out = await ndr_local.read_once(db, path)
    assert (out["alerts"], out["hits"]) == (2, 2)  # lib-ndr-scan and lib-ndr-web-attack, both recording
    alert = await db.security_alerts.find_one({}, {"_id": 0})
    assert await db.security_alerts.count_documents({}) == 1 and (alert["severity"], alert["mitre"]) == ("high", "T1190")
    hits = {h["ruleId"]: h["alerted"] for h in await db.siem_hits.find({}).to_list(10)}
    assert hits == {"lib-ndr-scan": False, "lib-ndr-web-attack": False}


@pytest.mark.asyncio
async def test_a_reputation_list_is_one_alert_not_one_per_group(world):
    """protects=hits on different "... group N" signatures of one reputation list (live on 19 Nov: ET CINS ships 300,
    ET TOR 840) count on one Platform alert titled by the list, while each event keeps its own signature;
    fails_when=the queue gets an alert per group; no_claim=whether reputation hits deserve alerts at all"""
    db, path = world
    cins = "ET CINS Active Threat Intelligence Poor Reputation IP group {}"
    _write(path, *(_alert(f"2026-11-19T08:00:0{i}+0000", sid=2403300 + g, category="Misc Attack", signature=cins.format(g), src=f"198.51.100.{g}")
                   for i, g in enumerate((38, 41, 202))))
    assert (await ndr_local.read_once(db, path))["alerts"] == 3
    alerts = await db.security_alerts.find({}, {"_id": 0}).to_list(10)
    assert len(alerts) == 1 and alerts[0]["occurrences"] == 3
    assert alerts[0]["title"] == "ET CINS Active Threat Intelligence Poor Reputation IP"
    assert sorted(await db.soc_log_events.distinct("signature")) == sorted(cins.format(g) for g in (38, 41, 202))


@pytest.mark.asyncio
async def test_stream_engine_notices_are_counted_not_stored(world):
    """protects=Suricata's TCP stream-engine notices (97% of live events on 19 Nov) never fill the SIEM store, while a
    real alert in the same pass is stored; fails_when=an out-of-window notice becomes an event or an alert;
    no_claim=other SURICATA decoder or app-layer events, which stay"""
    db, path = world
    _write(path, _alert("2026-11-19T08:00:00+0000", sid=2210020, severity=3, category="Generic Protocol Command Decode",
                        signature="SURICATA STREAM ESTABLISHED packet out of window"),
           _alert("2026-11-19T08:00:01+0000", sid=2210045, severity=3, category="Generic Protocol Command Decode",
                  signature="SURICATA STREAM Packet with invalid ack"),
           REAL_ALERT)
    out = await ndr_local.read_once(db, path)
    assert (out["engineNoise"], out["alerts"]) == (2, 1)
    assert await db.soc_log_events.distinct("signature") == ["GPL ATTACK_RESPONSE id check returned root"]


@pytest.mark.asyncio
async def test_stats_make_the_server_sensor_live_and_pass_the_ids_check(world):
    """protects=stats update the Platform's local sensor record and add one sample a minute, so sensor_health says
    LIVE and the Platform's ids_ips_enabled check passes, while another organization stays at fail;
    fails_when=a sample per stats line (30 s), a sensor without rules counted as watching, or ABC credited with the
    server's sensor; no_claim=the 24-hour boundaries (test_ndr_sensors.py)"""
    from tests.test_ids_ips_check import _check
    db, path = world
    t0 = datetime.now(timezone.utc) - timedelta(minutes=3)
    _write(path, *(_stats((t0 + timedelta(seconds=30 * i)).isoformat(), 1000 + 500 * i, uptime=600 + 30 * i) for i in range(5)))
    assert (await ndr_local.read_once(db, path))["stats"] == 5
    sensor = await db.ndr_sensors.find_one({"tenantId": "platform-admin", "sensorId": "local"}, {"_id": 0})
    samples = await db.ndr_sensor_stats.find({"sensorId": "local"}, {"_id": 0}).sort("sampledAt", -1).to_list(10)
    assert (sensor["packets"], sensor["rulesLoaded"], len(samples)) == (3000, 53432, 3)  # t0, +60 s, +120 s
    assert sensor["name"].endswith("(this server)")
    assert ndr_sensors.sensor_health(sensor, samples, datetime.now(timezone.utc))["state"] == ndr_sensors.LIVE
    assert (await _check(db, "platform-admin"))[0] == "pass"
    assert (await _check(db, "tenant_abc"))[0] == "fail"


@pytest.mark.asyncio
async def test_a_half_written_line_waits_and_a_truncated_log_is_read_from_the_start(world):
    """protects=only complete lines are read (Suricata may be mid-write), and after logrotate's copytruncate the
    reader starts again at the beginning instead of past the end; fails_when=a partial line is parsed and lost, or
    events after rotation are never read; no_claim=lines written between logrotate's copy and its truncate"""
    db, path = world
    line = _alert("2026-11-19T08:00:00+0000")
    with open(path, "wb") as f:
        f.write(line[:40])
    assert (await ndr_local.read_once(db, path))["alerts"] == 0
    with open(path, "ab") as f:
        f.write(line[40:] + b"\n")
    assert (await ndr_local.read_once(db, path))["alerts"] == 1
    with open(path, "r+b") as f:  # copytruncate
        f.truncate(0)
    _write(path, _alert("2026-11-19T09:00:00+0000", sid=7))
    assert (await ndr_local.read_once(db, path))["alerts"] == 1
    assert await db.soc_log_events.count_documents({"signatureId": 7}) == 1


@pytest.mark.asyncio
async def test_no_log_means_nothing_happens(world):
    """protects=a server without Suricata reads nothing and records no sensor; fails_when=a missing log raises or
    creates a sensor that then reads SILENT; no_claim=none beyond protects"""
    db, path = world
    assert await ndr_local.read_once(db, path) == {"lines": 0, "alerts": 0, "stats": 0, "hits": 0, "engineNoise": 0}
    assert await db.ndr_sensors.count_documents({}) == 0


@pytest.mark.asyncio
async def test_migration_045_adds_five_network_rules_once(world):
    """protects=5 network library rules, each with a MITRE technique, record for 7 days, and a second run keeps an
    analyst's change; fails_when=re-running resets a tuned rule; no_claim=the rules' noise on a real network"""
    db, _ = world
    rules = await db.siem_rules.find({"id": {"$regex": "^lib-ndr-"}}, {"_id": 0}).to_list(10)
    assert len(rules) == 5 and all(r["logSource"] == "network" and r["mode"] == "record" and r["mitre_technique"] for r in rules)
    await db.siem_rules.update_one({"id": "lib-ndr-recon"}, {"$set": {"enabled": False}})
    await migration.up(db)
    assert await db.siem_rules.count_documents({"id": {"$regex": "^lib-ndr-"}}) == 5
    assert (await db.siem_rules.find_one({"id": "lib-ndr-recon"}))["enabled"] is False
