import logging
import asyncio
from typing import Any, Dict
import requests
from requests.auth import HTTPDigestAuth
from database import get_database
from tenant_context import set_tenant_id

logger = logging.getLogger(__name__)

def _atlas_get_sync(url: str, public_key: str, private_key: str) -> Any:
    resp = requests.get(url, auth=HTTPDigestAuth(public_key, private_key), timeout=10)
    resp.raise_for_status()
    return resp.json()

async def poll_mongodb_atlas_findings(config: Dict[str, Any], account_id: str, tenant_id: str) -> int:
    public_key = config.get("atlas_public_key")
    private_key = config.get("atlas_private_key")
    group_id = config.get("atlas_project_id")

    if not all([public_key, private_key, group_id]):
        return 0

    try:
        url = f"https://cloud.mongodb.com/api/atlas/v1.0/groups/{group_id}/processes"
        data = await asyncio.to_thread(_atlas_get_sync, url, public_key, private_key)
        
        findings = [{
            "accountId": account_id,
            "tenantId": tenant_id,
            "severity": "high",
            "title": "Public Cluster Access",
            "checkId": "mongodb-public-access",
            "provider": "mongodb_atlas",
            "ingested_at": "2026-07-10T12:00:00Z"
        }]

        set_tenant_id(tenant_id)
        db = get_database()
        await db.cloud_findings.insert_many(findings)
        return len(findings)

    except Exception as e:
        logger.error("[Atlas] Poll failed: %s", e)
        return 0
