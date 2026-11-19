"""Migration 046: SIEM library rules for the authentik log source (log_connectors, open-source identity provider).

Five platform-library rules over authentik events (source ``authentik``): repeated failed sign-ins, password spraying,
a request authentik itself flagged as suspicious, impersonation, and a token or secret being viewed. Like 039, 044 and
045 they record hits for 7 days before they raise alerts. Nothing existing is read or changed (upsert by id with
$setOnInsert), so a second run changes nothing.
"""
import logging
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Executable SIEM library rules for the authentik log source (record-only for 7 days)."

logger = logging.getLogger(__name__)


def _rule(rid, name, match, count, window, group_by, severity, technique, description, distinct=None):
    threshold = {"count": count, "windowSeconds": window, "groupBy": group_by, **({"distinct": distinct} if distinct else {})}
    return {"id": rid, "name": name, "logSource": "authentik", "logic": {"match": match, "threshold": threshold},
            "severity": severity, "mitre_technique": technique, "description": description}


LIBRARY = [
    _rule("lib-authentik-login-failures", "Repeated failed authentik sign-ins", {"action": "login_failed"},
          5, 600, "user", "High", "T1110 — Brute Force", "5 or more failed authentik sign-ins for one account in 10 minutes."),
    _rule("lib-authentik-spray", "authentik password spraying", {"action": "login_failed"},
          10, 1800, "srcIp", "High", "T1110.003 — Password Spraying", "Failed authentik sign-ins for 10 or more accounts from one IP in 30 minutes.", "user"),
    _rule("lib-authentik-suspicious", "authentik flagged a suspicious request", {"action": "login_suspicious"},
          1, 600, "srcIp", "Medium", "T1110 — Brute Force", "authentik's reputation policy marked a request as suspicious."),
    _rule("lib-authentik-impersonation", "authentik impersonation started", {"action": "impersonation"},
          1, 600, "user", "High", "T1078 — Valid Accounts", "An administrator started acting as another user."),
    _rule("lib-authentik-secret-view", "authentik token or secret viewed", {"action": "secret_view"},
          1, 600, "user", "Medium", "T1552 — Unsecured Credentials", "Someone revealed a token key or other secret in authentik."),
]


async def up(db: AsyncIOMotorDatabase) -> None:
    now = datetime.now(timezone.utc)
    for rule in LIBRARY:
        await db.siem_rules.update_one({"id": rule["id"]}, {"$setOnInsert": {
            **rule, "tenant_id": "platform-admin", "enabled": True, "mode": "record",
            "alertAfter": (now + timedelta(days=7)).isoformat(), "created_by": "system", "created_at": now.isoformat(),
            "match_count": 0}}, upsert=True)
    logger.info("migration 046: %d authentik library rules in place", len(LIBRARY))
