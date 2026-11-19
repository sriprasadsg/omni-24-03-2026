"""The platform server's own network sensor (Wave 4, 88.1): Suricata on this server's interface, read from its EVE log.

Suricata runs here passively (scripts/ndr_local/enable_local_sensor.sh) and writes only alert and stats events to
``EVE_PATH``. Every POLL seconds ``read_once`` reads the lines added since the last pass (a byte offset per file in
``siem_cursors``; a truncated or replaced file, as logrotate's copytruncate leaves it, is read again from the start)
and only complete lines, so a line Suricata is still writing waits for the next pass.

* An alert becomes a SIEM event (source ``network``, action ``ids_alert``; unique per line) for rules and Hunting.
  Severity 1 and 2 alerts also raise a SOC alert (high, medium) for the Platform, one active alert per signature
  family with repeats counted (a reputation list ships as hundreds of "... group N" signatures: ET CINS 300, ET TOR
  840), carrying the rule's MITRE technique when the rule names one. Severity 3 stays in the SIEM.
* A stats event updates the sensor record (``ndr_sensors``: tenant platform-admin, sensor ``local``) and, at most
  once a minute, adds a sample (``ndr_sensor_stats``), so ndr_sensors.sensor_health and the ids_ips_enabled check
  see this sensor as LIVE, DEGRADED or SILENT. It watches the server only: no other organization's network.
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import socket
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

EVE_PATH = os.getenv("NDR_LOCAL_EVE", "/var/log/suricata/eve.json")
TENANT = "platform-admin"
SENSOR = "local"
POLL = 30
MAX_BYTES = 8 * 1024 * 1024  # per pass; a backlog is read over several passes
SAMPLE_EVERY = timedelta(seconds=55)
SEVERITY = {1: "high", 2: "medium"}
GROUP_SUFFIX = re.compile(r"\s+group \d+$")  # "ET DROP Spamhaus DROP Listed Traffic Inbound group 48"
# Suricata's own TCP stream-engine notices (out-of-window, invalid ack or timestamp) are not attacks; on this VM they
# were 97% of all events (about 107,000 of 110,000 on 19 Nov), so they are counted but not stored.
ENGINE_NOISE = ("SURICATA STREAM ",)


def _raw(db):
    return getattr(db, "_db", db)


def _ts(value: Any) -> Optional[datetime]:
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc)


def read_new(path: str, cursor: Dict[str, Any]) -> Tuple[List[bytes], Dict[str, Any]]:
    """Complete lines added to ``path`` since ``cursor`` ({inode, offset}), and the cursor after them."""
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return [], cursor
    offset = cursor.get("offset", 0) if cursor.get("inode") == st.st_ino and st.st_size >= cursor.get("offset", 0) else 0
    with open(path, "rb") as f:
        f.seek(offset)
        chunk = f.read(MAX_BYTES)
    end = chunk.rfind(b"\n") + 1
    return [line for line in chunk[:end].split(b"\n") if line.strip()], {"inode": st.st_ino, "offset": offset + end}


def _technique(alert: Dict[str, Any]) -> Optional[str]:
    meta = alert.get("metadata") if isinstance(alert.get("metadata"), dict) else {}
    ids = meta.get("mitre_technique_id") or []
    return ids[0] if isinstance(ids, list) and ids and isinstance(ids[0], str) else None


def alert_event(e: Dict[str, Any], line: bytes, host: str) -> Dict[str, Any]:
    a = e.get("alert") or {}
    return {"source": "network", "key": "suricata|" + hashlib.sha1(line).hexdigest(), "action": "ids_alert", "outcome": "detected",
            "timestamp": e.get("timestamp"), "user": None, "srcIp": e.get("src_ip"), "host": host,
            "destIp": e.get("dest_ip"), "srcPort": e.get("src_port"), "destPort": e.get("dest_port"), "proto": e.get("proto"),
            "appProto": e.get("app_proto"), "signature": a.get("signature"), "signatureId": a.get("signature_id"),
            "category": a.get("category"), "idsSeverity": a.get("severity"), "technique": _technique(a),
            "message": f"{a.get('signature')} ({a.get('category') or 'uncategorised'}): {e.get('src_ip')}:{e.get('src_port')} -> "
                       f"{e.get('dest_ip')}:{e.get('dest_port')} {e.get('proto') or ''}"[:500]}


def stats_fields(s: Dict[str, Any]) -> Dict[str, int]:
    """Cumulative counters from an EVE stats event (af-packet capture counters, else the decoder's for a pcap)."""
    stats = s.get("stats") or {}
    capture, decoder = stats.get("capture") or {}, stats.get("decoder") or {}
    engines = (stats.get("detect") or {}).get("engines") or [{}]
    packets = capture.get("kernel_packets", decoder.get("pkts", 0))
    return {"packets": int(packets or 0), "drops": int(capture.get("kernel_drops") or 0), "uptime": int(stats.get("uptime") or 0),
            "rulesLoaded": int(engines[-1].get("rules_loaded") or 0), "rulesFailed": int(engines[-1].get("rules_failed") or 0)}


async def _raise(db, event: Dict[str, Any]) -> None:
    import soc_alerts
    sev = SEVERITY.get(event.get("idsSeverity"))
    if not sev:
        return
    family = GROUP_SUFFIX.sub("", event.get("signature") or "Network IDS alert")
    await soc_alerts.record_alert(_raw(db), {
        "tenantId": TENANT, "type": "ids_alert", "severity": sev, "title": family,
        "description": event["message"], "mitre": event.get("technique"), "created_at": (_ts(event.get("timestamp")) or datetime.now(timezone.utc)).isoformat(),
        "metadata": {"signatureId": event.get("signatureId"), "category": event.get("category"), "remote_ip": event.get("srcIp"),
                     "destIp": event.get("destIp"), "destPort": event.get("destPort"), "sensor": SENSOR}}, group=f"ids:{family}")


async def _stats(db, e: Dict[str, Any], host: str, last_sample: Optional[datetime]) -> Optional[datetime]:
    raw, at = _raw(db), _ts(e.get("timestamp"))
    if not at:
        return last_sample
    fields = stats_fields(e)
    await raw.ndr_sensors.update_one({"tenantId": TENANT, "sensorId": SENSOR}, {
        "$set": {**fields, "name": f"{host} (this server)", "lastStatsAt": datetime.now(timezone.utc)},
        "$setOnInsert": {"createdAt": datetime.now(timezone.utc)}}, upsert=True)
    if last_sample and at - last_sample < SAMPLE_EVERY:
        return last_sample
    from pymongo.errors import DuplicateKeyError
    try:
        await raw.ndr_sensor_stats.insert_one({"tenantId": TENANT, "sensorId": SENSOR, "sampledAt": at,
                                               "packets": fields["packets"], "drops": fields["drops"], "uptime": fields["uptime"]})
    except DuplicateKeyError:
        pass
    return at


async def read_once(db, path: str = EVE_PATH) -> Dict[str, int]:
    """One pass over the EVE lines added since the last: events, SOC alerts, sensor stats, then the SIEM rules."""
    import siem_pipeline
    raw = _raw(db)
    cursor = await raw.siem_cursors.find_one({"id": f"eve:{path}"}, {"_id": 0}) or {}
    lines, after = read_new(path, cursor)
    if not lines and after == {k: cursor[k] for k in ("inode", "offset") if k in cursor}:
        return {"lines": 0, "alerts": 0, "stats": 0, "hits": 0, "engineNoise": 0}
    host = socket.gethostname()
    newest = await raw.ndr_sensor_stats.find_one({"tenantId": TENANT, "sensorId": SENSOR}, sort=[("sampledAt", -1)])
    last_sample = _ts(newest["sampledAt"].isoformat()) if newest else None
    events, counts = [], {"lines": len(lines), "alerts": 0, "stats": 0, "hits": 0, "engineNoise": 0}
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("event_type") == "alert" and str((e.get("alert") or {}).get("signature") or "").startswith(ENGINE_NOISE):
            counts["engineNoise"] += 1
        elif e.get("event_type") == "alert":
            event = alert_event(e, line, host)
            event["tenantId"], event["agentId"] = TENANT, None
            if await siem_pipeline._store(db, event):  # a line read twice is stored and raised once
                events.append(event)
                await _raise(db, event)
                counts["alerts"] += 1
        elif e.get("event_type") == "stats":
            last_sample = await _stats(db, e, host, last_sample)
            counts["stats"] += 1
    if events:
        counts["hits"] = len(await siem_pipeline.evaluate(db, events))
    await raw.siem_cursors.update_one({"id": f"eve:{path}"}, {"$set": after}, upsert=True)
    return counts


async def read_loop() -> None:
    """Every POLL seconds while the EVE log exists; quiet when this server runs no Suricata."""
    from database import get_database
    await asyncio.sleep(120)
    while True:
        if os.path.exists(EVE_PATH):
            try:
                out = await read_once(get_database())
                if out["alerts"]:
                    logger.info("Local network sensor: %s", out)
            except Exception as exc:  # the loop must survive a bad pass
                logger.warning("Local network sensor pass failed: %s", exc)
        await asyncio.sleep(POLL)
