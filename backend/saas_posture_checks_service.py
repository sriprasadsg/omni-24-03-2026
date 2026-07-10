from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

# Importing saas_integration_service to access OAuthProvider and evidence pulls
from saas_integration_service import (
    OAuthProvider,
    saas_integration_service,
    _CTRL_SECURE_DEV,
    _CTRL_SOURCE_CODE,
    _CTRL_SEC_PATCH,
    _CTRL_CHANGE_MGMT,
    _CTRL_AUDIT_LOG,
    _CTRL_DATA_LEAKAGE,
    _OKTA_MFA_CTRL,
    _GWS_ACCOUNT_SEC,
)

logger = logging.getLogger(__name__)

# NOTE: The _evidence_control_id must EXACTLY match the control_id strings
#       emitted by saas_integration_service.pull_*_evidence().
GITHUB_POSTURE_CHECKS: List[Dict[str, Any]] = [
    {
        "id": "gh-sd-001",
        "name": "Secure Development Practices",
        "service": "GitHub",
        "severity": "medium",
        "frameworks": ["NIST-SC-7", "ISO-14.2.5"],
        "remediation": "Ensure pull requests are reviewed before merging.",
        "_evidence_control_id": _CTRL_SECURE_DEV,
    },
    {
        "id": "gh-sc-001",
        "name": "Source Code Access Control",
        "service": "GitHub",
        "severity": "high",
        "frameworks": ["NIST-AC-3", "ISO-9.2.3"],
        "remediation": "Enable branch protection rules for critical branches.",
        "_evidence_control_id": _CTRL_SOURCE_CODE,
    },
    {
        "id": "gh-sp-001",
        "name": "Security Patch Status",
        "service": "GitHub",
        "severity": "critical",
        "frameworks": ["NIST-SI-2", "ISO-12.6.1"],
        "remediation": "Address all critical code scanning alerts promptly.",
        "_evidence_control_id": _CTRL_SEC_PATCH,
    },
]

JIRA_POSTURE_CHECKS: List[Dict[str, Any]] = [
    {
        "id": "jr-cm-001",
        "name": "Change Management Process Adherence",
        "service": "Jira",
        "severity": "medium",
        "frameworks": ["NIST-CM-3", "ISO-14.2.2"],
        "remediation": "Ensure all significant changes are tracked and approved in Jira.",
        "_evidence_control_id": _CTRL_CHANGE_MGMT,
    },
]

OKTA_POSTURE_CHECKS: List[Dict[str, Any]] = [
    {
        "id": "ok-mfa-001",
        "name": "Multi-Factor Authentication Enforcement",
        "service": "Okta",
        "severity": "critical",
        "frameworks": ["NIST-AC-2", "PCI-8.3.1"],
        "remediation": "Enforce MFA for all users, especially those with privileged access.",
        "_evidence_control_id": _OKTA_MFA_CTRL,
    },
    {
        "id": "ok-ia-001",
        "name": "Identity & Authentication Management",
        "service": "Okta",
        "severity": "high",
        "frameworks": ["NIST-AC-1", "ISO-9.2.1"],
        "remediation": "Review and harden Okta identity and authentication policies.",
        "_evidence_control_id": "Identity & Authentication Simulation",
    },
]

GOOGLE_WORKSPACE_POSTURE_CHECKS: List[Dict[str, Any]] = [
    {
        "id": "gw-as-001",
        "name": "Account Security Configuration",
        "service": "Google Workspace",
        "severity": "high",
        "frameworks": ["NIST-AC-2", "ISO-9.2.1"],
        "remediation": "Ensure strong password policies and 2SV are enforced for all accounts.",
        "_evidence_control_id": _GWS_ACCOUNT_SEC,
    },
    {
        "id": "gw-dlp-001",
        "name": "Data Leakage Prevention Policies",
        "service": "Google Workspace",
        "severity": "high",
        "frameworks": ["NIST-DP-3", "ISO-13.2.3"],
        "remediation": "Configure and audit DLP policies to prevent sensitive data exfiltration.",
        "_evidence_control_id": _CTRL_DATA_LEAKAGE,
    },
]

SLACK_POSTURE_CHECKS: List[Dict[str, Any]] = [
    {
        "id": "sl-al-001",
        "name": "Audit Logging and Retention",
        "service": "Slack",
        "severity": "medium",
        "frameworks": ["NIST-AU-2", "ISO-12.4.1"],
        "remediation": "Ensure audit logs are enabled and retained for compliance purposes.",
        "_evidence_control_id": _CTRL_AUDIT_LOG,
    },
]

CHECKS_FOR: Dict[OAuthProvider, List[Dict[str, Any]]] = {
    OAuthProvider.GITHUB: GITHUB_POSTURE_CHECKS,
    OAuthProvider.JIRA: JIRA_POSTURE_CHECKS,
    OAuthProvider.OKTA: OKTA_POSTURE_CHECKS,
    OAuthProvider.GOOGLE_WORKSPACE: GOOGLE_WORKSPACE_POSTURE_CHECKS,
    OAuthProvider.SLACK: SLACK_POSTURE_CHECKS,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SaaSPostureChecksService:
    async def run_posture_checks(self, connection: Dict, db) -> Dict:
        """
        Runs posture checks for a given SaaS connection by reusing evidence
        collected by saas_integration_service.
        """
        tenant_id = connection.get("tenant_id")
        connection_id = connection.get("id")
        provider = connection.get("provider")

        if not all([tenant_id, connection_id, provider]):
            logger.error("Missing tenant_id, connection_id, or provider in connection: %s", connection)
            return {"error": "Invalid connection object", "ran": 0}

        # Reuse saas_integration_service to pull all evidence
        evidence = await saas_integration_service.pull_all_evidence(connection, db)
        ev_by_control = {e["control_id"]: e for e in evidence}
        results = []

        if provider not in CHECKS_FOR:
            logger.warning("No posture checks defined for provider: %s", provider)
            return {"ran": 0, "connectionId": connection_id, "provider": provider}

        for check in CHECKS_FOR[provider]:
            ev = ev_by_control.get(check["_evidence_control_id"])
            result = "PASS" if ev and ev.get("status") == "pass" else ("FAIL" if ev else "NO-DATA")

            doc = {
                "id": f"scr-{uuid.uuid4().hex}",
                "tenantId": tenant_id,
                "connectionId": connection_id,
                "provider": provider,
                "checkId": check["id"],
                "checkName": check["name"],
                "service": check["service"],
                "severity": check["severity"],
                "result": result,
                "frameworks": check["frameworks"],
                "remediation": check["remediation"],
                "detail": ev.get("content", "") if ev else "No evidence collected for this control.",
                "checked_at": _now_iso(),
            }
            await db.saas_check_results.update_one(
                {"tenantId": tenant_id, "connectionId": connection_id, "checkId": check["id"]},
                {"$set": doc},
                upsert=True,
            )
            results.append(doc)
        return {"ran": len(results), "connectionId": connection_id}


saas_posture_checks_service = SaaSPostureChecksService()
