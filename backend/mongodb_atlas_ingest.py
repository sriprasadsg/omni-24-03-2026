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


def _parse_atlas_finding(finding: Dict[str, Any], account_id: str, tenant_id: str) -> Dict[str, Any]:
    # Simplified parsing logic for cluster configuration findings
    cluster_name = finding.get("name", "Unknown Cluster")
    # Determine severity based on configuration (example: if IP Access List has 0.0.0.0/0)
    severity = "High" # Default for security configuration findings

    return {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "accountId": account_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": "mongodb_atlas",
        "service": "cluster",
        "checkId": f"ATLAS-{cluster_name.upper().replace(' ', '-')}",
        "title": f"Atlas Cluster Setting: {cluster_name}",
        "description": f"Atlas cluster '{cluster_name}' configuration finding.",
        "severity": severity,
        "status": "FAIL", # Assume failing for the POC finding
        "remediation": "Review cluster security configuration settings.",
        "raw_message": finding,
    }


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
            findings.append(_parse_atlas_finding(cluster, account_id, tenant_id))

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
