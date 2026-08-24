"""
MongoDB Atlas Findings Ingest
Polls MongoDB Atlas Admin API for security configuration findings and ingests them into cloud_findings.
Uses requests.auth.HTTPDigestAuth.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
from requests.auth import HTTPDigestAuth

from database import get_database
from tenant_context import set_tenant_id

logger = logging.getLogger(__name__)


def _atlas_get_sync(url: str, public_key: str, private_key: str) -> dict:
    """Sync helper for requests with digest auth."""
    resp = requests.get(url, auth=HTTPDigestAuth(public_key, private_key), timeout=10)
    resp.raise_for_status()
    return resp.json()


def _make_atlas_finding(
    cluster_name: str, check_id: str, title: str, description: str, severity: str,
    remediation: str, account_id: str, tenant_id: str, raw: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "accountId": account_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": "mongodb_atlas",
        "service": "cluster",
        "checkId": f"ATLAS-{cluster_name.upper().replace(' ', '-')}-{check_id}",
        "title": title,
        "description": description,
        "severity": severity,
        "status": "FAIL",
        "remediation": remediation,
        "raw_message": raw,
    }


def _evaluate_atlas_cluster(cluster: Dict[str, Any], account_id: str, tenant_id: str) -> List[Dict[str, Any]]:
    """
    Evaluate one Atlas cluster's real configuration and return only the
    findings for actual misconfigurations (WR-01: this used to hardcode
    every cluster as High/FAIL regardless of its config). A field is only
    checked when the Admin API actually returned it — a missing field is
    treated as "unknown" (not flagged), not assumed insecure, since some
    cluster tiers (e.g. serverless) don't return every field.
    """
    cluster_name = cluster.get("name", "Unknown Cluster")
    findings: List[Dict[str, Any]] = []

    if cluster.get("encryptionAtRestProvider") == "NONE":
        findings.append(_make_atlas_finding(
            cluster_name, "ENCRYPTION", f"Atlas Cluster Encryption at Rest Disabled: {cluster_name}",
            f"Atlas cluster '{cluster_name}' has encryption at rest disabled (encryptionAtRestProvider=NONE).",
            "High", "Enable encryption at rest for this cluster.", account_id, tenant_id, cluster,
        ))

    if cluster.get("backupEnabled") is False:
        findings.append(_make_atlas_finding(
            cluster_name, "BACKUP", f"Atlas Cluster Backups Disabled: {cluster_name}",
            f"Atlas cluster '{cluster_name}' has continuous backups disabled (backupEnabled=false).",
            "Medium", "Enable backups for this cluster.", account_id, tenant_id, cluster,
        ))

    if cluster.get("terminationProtectionEnabled") is False:
        findings.append(_make_atlas_finding(
            cluster_name, "TERMPROTECT", f"Atlas Cluster Termination Protection Disabled: {cluster_name}",
            f"Atlas cluster '{cluster_name}' has termination protection disabled (terminationProtectionEnabled=false).",
            "Medium", "Enable termination protection to prevent accidental or malicious cluster deletion.",
            account_id, tenant_id, cluster,
        ))

    return findings


async def poll_mongodb_atlas_findings(config: Dict[str, Any], account_id: str, tenant_id: str) -> int:
    """
    Poll MongoDB Atlas Admin API for security findings.
    Returns count of new findings ingested.
    """
    public_key = config.get("atlas_public_key", "")
    private_key = config.get("atlas_private_key", "")
    project_id = config.get("atlas_project_id", "")

    if not all([public_key, private_key, project_id]):
        logger.warning("[Atlas] Incomplete credentials for tenant %s", tenant_id)
        return 0

    try:
        url = f"https://cloud.mongodb.com/api/atlas/v2/groups/{project_id}/clusters"
        data = await asyncio.to_thread(_atlas_get_sync, url, public_key, private_key)

        findings: List[Dict[str, Any]] = []
        for cluster in data.get("results", []):
            findings.extend(_evaluate_atlas_cluster(cluster, account_id, tenant_id))

        if not findings:
            logger.info("[Atlas] No findings for tenant %s", tenant_id)
            return 0

        set_tenant_id(tenant_id)
        db = get_database()
        await db.cloud_findings.insert_many(findings)
        logger.info("[Atlas] Ingested %d findings for tenant %s", len(findings), tenant_id)
        return len(findings)

    except Exception as exc:
        logger.error("[Atlas] Poll failed for tenant %s: %s", tenant_id, exc)
        return 0
