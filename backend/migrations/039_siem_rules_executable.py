"""Migration 039: SIEM rules that run (siem_pipeline), and the log source every library rule waits for.

* Ten platform-library rules with executable ``logic`` for the logs agents send today (Linux auth lines, Windows
  heartbeat events). They start record-only for 7 days (``mode`` "record", ``alertAfter``), then raise alerts.
* The 26 descriptive library rules keep their text and get ``logSource`` (entra_id, m365, windows_security,
  network), so the console says what each one waits for. None is deleted or rewritten.
* Indexes for soc_log_events and siem_hits. A second run changes nothing (upsert by id, logSource set only if absent).
"""
import logging
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Executable SIEM library rules (record-only for 7 days) and log sources for the descriptive ones."

logger = logging.getLogger(__name__)


def _rule(rid, name, source, match, count, window, group_by, severity, technique, description, distinct=None):
    threshold = {"count": count, "windowSeconds": window, "groupBy": group_by, **({"distinct": distinct} if distinct else {})}
    return {"id": rid, "name": name, "logSource": source, "logic": {"match": match, "threshold": threshold},
            "severity": severity, "mitre_technique": technique, "description": description}


LIBRARY = [
    _rule("lib-linux-ssh-bruteforce", "SSH brute force from one address", "linux_auth", {"action": "login_failed"},
          10, 600, "srcIp", "High", "T1110.001 — Password Guessing", "10 or more failed SSH sign-ins from one IP in 10 minutes."),
    _rule("lib-linux-ssh-spray", "SSH password spraying across accounts", "linux_auth", {"action": "login_failed"},
          5, 600, "srcIp", "High", "T1110.003 — Password Spraying", "Failed SSH sign-ins for 5 or more accounts from one IP in 10 minutes.", "user"),
    _rule("lib-linux-new-account", "New local account on a Linux host", "linux_auth", {"action": "account_created"},
          1, 600, "user", "Medium", "T1136.001 — Create Account: Local Account", "useradd created an account."),
    _rule("lib-linux-admin-group", "User added to a Linux admin group", "linux_auth", {"action": "admin_group_add"},
          1, 600, "user", "High", "T1098 — Account Manipulation", "An account was added to sudo, admin, wheel or root."),
    _rule("lib-linux-sudo-failures", "Repeated sudo authentication failures", "linux_auth", {"action": "sudo_failed"},
          3, 600, "user", "Medium", "T1548.003 — Sudo and Sudo Caching", "3 or more failed sudo attempts by one user in 10 minutes."),
    _rule("lib-win-logon-failures", "Repeated failed Windows sign-ins", "windows_security", {"action": "login_failed"},
          10, 600, "agentId", "High", "T1110 — Brute Force", "10 or more failed sign-ins (event 4625) on one computer in 10 minutes."),
    _rule("lib-win-new-account", "New Windows account", "windows_security", {"action": "account_created"},
          1, 600, "user", "Medium", "T1136.001 — Create Account: Local Account", "A user account was created (event 4720)."),
    _rule("lib-win-admin-group", "Account added to Administrators", "windows_security",
          {"action": "admin_group_add", "group": "Administrators"}, 1, 600, "user", "High", "T1098 — Account Manipulation",
          "A member was added to the Administrators group (events 4728, 4732, 4756)."),
    _rule("lib-win-log-cleared", "Windows event log cleared", "windows_security", {"action": "log_cleared"},
          1, 600, "agentId", "Critical", "T1070.001 — Clear Windows Event Logs", "The Security log was cleared (event 1102)."),
    _rule("lib-win-service-installed", "New Windows service installed", "windows_security", {"action": "service_installed"},
          1, 600, "agentId", "Medium", "T1543.003 — Windows Service", "A service was installed (event 7045)."),
]

# Descriptive library rules: the log source each needs, by words in its name (first match wins).
SOURCES = (("entra_id", ("entra", "azure ad", "oauth", "mfa", "password spray")),
           ("m365", ("exchange", "m365", "teams", "inbox", "office macro", "phishing")),
           ("network", ("vpn", "beacon", "c2", "dns", "exfiltration", "network scan", "web protocols")),
           ("windows_security", ("",)))


def source_for(name: str) -> str:
    text = (name or "").lower()
    return next(src for src, words in SOURCES if any(w in text for w in words))


async def up(db: AsyncIOMotorDatabase) -> None:
    import siem_pipeline

    now = datetime.now(timezone.utc)
    for rule in LIBRARY:
        await db.siem_rules.update_one({"id": rule["id"]}, {"$setOnInsert": {
            **rule, "tenant_id": "platform-admin", "enabled": True, "mode": "record",
            "alertAfter": (now + timedelta(days=7)).isoformat(), "created_by": "system", "created_at": now.isoformat(),
            "match_count": 0}}, upsert=True)
    tagged = 0
    async for r in db.siem_rules.find({"logic": {"$exists": False}, "logSource": {"$exists": False}}, {"_id": 1, "name": 1}):
        await db.siem_rules.update_one({"_id": r["_id"]}, {"$set": {"logSource": source_for(r.get("name"))}})
        tagged += 1
    await siem_pipeline.ensure_indexes(db)
    logger.info("migration 039: %d executable library rules in place, %d descriptive rules given a log source", len(LIBRARY), tagged)
