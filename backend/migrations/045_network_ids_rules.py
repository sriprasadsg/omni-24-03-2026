"""Migration 045: SIEM library rules for the server's own network sensor (ndr_local, Wave 4 / 88.1).

Five platform-library rules over Suricata alerts (source ``network``, action ``ids_alert``), each matching one
Suricata classification and naming the MITRE technique it stands for, so the coverage tab counts them once the
sensor sends events. Like 039 and 044 they record hits for 7 days before they raise alerts. Nothing existing is read
or changed (upsert by id with $setOnInsert), so a second run changes nothing.
"""
import logging
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Executable SIEM library rules for the local network sensor (record-only for 7 days)."

logger = logging.getLogger(__name__)


def _rule(rid, name, match, count, window, severity, technique, description):
    return {"id": rid, "name": name, "logSource": "network",
            "logic": {"match": {"action": "ids_alert", **match}, "threshold": {"count": count, "windowSeconds": window, "groupBy": "srcIp"}},
            "severity": severity, "mitre_technique": technique, "description": description}


LIBRARY = [
    _rule("lib-ndr-recon", "Reconnaissance against the server", {"category": "Attempted Information Leak"}, 1, 3600, "Low",
          "T1595 — Active Scanning", "Suricata saw a probe for information (classtype attempted-recon) from one address."),
    _rule("lib-ndr-scan", "Network scan of the server", {"category": "Detection of a Network Scan"}, 1, 3600, "Low",
          "T1046 — Network Service Discovery", "Suricata saw a port or service scan (classtype network-scan) from one address."),
    _rule("lib-ndr-web-attack", "Web application attack on the server", {"category": "Web Application Attack"}, 1, 600, "High",
          "T1190 — Exploit Public-Facing Application", "Suricata saw an attack on a web application (classtype web-application-attack)."),
    _rule("lib-ndr-admin-attempt", "Attempt to gain administrator rights over the network", {"category": "Attempted Administrator Privilege Gain"},
          1, 600, "High", "T1210 — Exploitation of Remote Services", "Suricata saw an exploit aimed at administrator access (classtype attempted-admin)."),
    _rule("lib-ndr-trojan", "Malware traffic on the server's network", {"category": "A Network Trojan was detected"}, 1, 600, "High",
          "T1071 — Application Layer Protocol", "Suricata matched known malware or command-and-control traffic (classtype trojan-activity)."),
]


async def up(db: AsyncIOMotorDatabase) -> None:
    now = datetime.now(timezone.utc)
    for rule in LIBRARY:
        await db.siem_rules.update_one({"id": rule["id"]}, {"$setOnInsert": {
            **rule, "tenant_id": "platform-admin", "enabled": True, "mode": "record",
            "alertAfter": (now + timedelta(days=7)).isoformat(), "created_by": "system", "created_at": now.isoformat(),
            "match_count": 0}}, upsert=True)
    logger.info("migration 045: %d network IDS library rules in place", len(LIBRARY))
