import logging
from typing import Any, Dict
from database import get_database
from tenant_context import set_tenant_id

logger = logging.getLogger(__name__)

try:
    import msal
    import httpx
    _MSAL_AVAILABLE = True
except ImportError:
    _MSAL_AVAILABLE = False
    logger.warning("[M365] MSAL/httpx not installed — M365 ingest disabled")

async def poll_m365_secure_scores(config: Dict[str, Any], account_id: str, tenant_id: str) -> int:
    if not _MSAL_AVAILABLE:
        return 0

    az_tenant = config.get("tenant_id")
    client_id = config.get("client_id")
    client_secret = config.get("client_secret")

    if not all([az_tenant, client_id, client_secret]):
        return 0

    try:
        app = msal.ConfidentialClientApplication(
            client_id, authority=f"https://login.microsoftonline.com/{az_tenant}",
            client_credential=client_secret
        )
        token_result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in token_result:
            return 0

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://graph.microsoft.com/v1.0/security/secureScores",
                headers={"Authorization": f"Bearer {token_result['access_token']}"}
            )
            resp.raise_for_status()
            scores = resp.json().get("value", [])

        findings = []
        for score in scores:
            for control in score.get("controlScores", []):
                findings.append({
                    "accountId": account_id,
                    "tenantId": tenant_id,
                    "severity": control.get("score", 0) < 50 and "high" or "medium",
                    "title": control.get("controlName", "Unknown Control"),
                    "checkId": control.get("controlName", "").lower().replace(" ", "-"),
                    "provider": "microsoft365",
                    "ingested_at": datetime.now(timezone.utc).isoformat()
                })

        set_tenant_id(tenant_id)
        db = get_database()
        if findings:
            await db.cloud_findings.insert_many(findings)
        return len(findings)

    except Exception as e:
        logger.error("[M365] Poll failed: %s", e)
        return 0
