"""Migration 044: SIEM library rules for the cloud log connectors (log_connectors, Wave 3), and the connectors' index.

Twelve platform-library rules with executable ``logic`` for Entra ID, Microsoft 365, AWS CloudTrail and Google
Workspace events. Like 039's, they record hits for 7 days before they raise alerts. Nothing existing is read or
changed (upsert by id with $setOnInsert), so a second run changes nothing.
"""
import logging
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Executable SIEM library rules for cloud log connectors (record-only for 7 days); log_connectors index."

logger = logging.getLogger(__name__)


def _rule(rid, name, source, match, count, window, group_by, severity, technique, description, distinct=None):
    threshold = {"count": count, "windowSeconds": window, "groupBy": group_by, **({"distinct": distinct} if distinct else {})}
    return {"id": rid, "name": name, "logSource": source, "logic": {"match": match, "threshold": threshold},
            "severity": severity, "mitre_technique": technique, "description": description}


LIBRARY = [
    _rule("lib-entra-signin-failures", "Repeated failed Entra ID sign-ins", "entra_id", {"action": "login_failed"},
          5, 600, "user", "High", "T1110 — Brute Force", "5 or more failed Entra ID sign-ins for one account in 10 minutes."),
    _rule("lib-entra-spray", "Entra ID password spraying", "entra_id", {"action": "login_failed"},
          10, 1800, "srcIp", "High", "T1110.003 — Password Spraying", "Failed Entra ID sign-ins for 10 or more accounts from one IP in 30 minutes.", "user"),
    _rule("lib-entra-admin-role", "Entra ID admin role assigned", "entra_id", {"action": "admin_role_add"},
          1, 600, "user", "High", "T1098.003 — Additional Cloud Roles", "A directory role was assigned to an account."),
    _rule("lib-entra-app-credential", "Credential added to an Entra ID application", "entra_id", {"action": "app_credential_added"},
          1, 600, "user", "Medium", "T1098.001 — Additional Cloud Credentials", "A secret or certificate was added to a service principal."),
    _rule("lib-m365-forward-rule", "Mailbox forwarding set up", "m365", {"action": "mail_forward_rule"},
          1, 600, "user", "High", "T1114.003 — Email Forwarding Rule", "An inbox rule or mailbox setting forwards mail elsewhere."),
    _rule("lib-m365-login-failures", "Repeated failed Microsoft 365 sign-ins", "m365", {"action": "login_failed"},
          10, 600, "user", "Medium", "T1110 — Brute Force", "10 or more failed Microsoft 365 sign-ins for one account in 10 minutes."),
    _rule("lib-aws-root-use", "AWS root account used", "aws_cloudtrail", {"rootUser": True},
          1, 3600, "region", "High", "T1078.004 — Cloud Accounts", "The AWS account's root user made an API call or signed in."),
    _rule("lib-aws-console-failures", "Repeated failed AWS console sign-ins", "aws_cloudtrail", {"action": "login_failed"},
          5, 600, "user", "High", "T1110 — Brute Force", "5 or more failed AWS console sign-ins for one user in 10 minutes."),
    _rule("lib-aws-trail-stopped", "AWS CloudTrail logging stopped or deleted", "aws_cloudtrail", {"action": "log_disabled"},
          1, 600, "user", "Critical", "T1562.008 — Disable or Modify Cloud Logs", "StopLogging or DeleteTrail was called."),
    _rule("lib-aws-access-key", "New AWS access key created", "aws_cloudtrail", {"action": "access_key_created"},
          1, 600, "user", "Medium", "T1098.001 — Additional Cloud Credentials", "An IAM access key was created."),
    _rule("lib-gws-login-failures", "Repeated failed Google Workspace sign-ins", "google_workspace", {"action": "login_failed"},
          10, 600, "user", "High", "T1110 — Brute Force", "10 or more failed Google Workspace sign-ins for one account in 10 minutes."),
    _rule("lib-gws-admin-role", "Google Workspace admin role assigned", "google_workspace", {"action": "admin_role_add"},
          1, 600, "user", "High", "T1098.003 — Additional Cloud Roles", "An admin role or privilege was granted."),
]


async def up(db: AsyncIOMotorDatabase) -> None:
    now = datetime.now(timezone.utc)
    for rule in LIBRARY:
        await db.siem_rules.update_one({"id": rule["id"]}, {"$setOnInsert": {
            **rule, "tenant_id": "platform-admin", "enabled": True, "mode": "record",
            "alertAfter": (now + timedelta(days=7)).isoformat(), "created_by": "system", "created_at": now.isoformat(),
            "match_count": 0}}, upsert=True)
    await db.log_connectors.create_index([("tenantId", 1), ("provider", 1)], unique=True, name="log_connector_org")
    logger.info("migration 044: %d cloud log library rules in place", len(LIBRARY))
