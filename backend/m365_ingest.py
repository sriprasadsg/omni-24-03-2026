"""
M365 Secure Score Ingest
Polls Microsoft Graph for Secure Score controls and ingests them as cloud_findings.
Falls back gracefully when msal/httpx are not installed or credentials missing.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from database import get_database
from tenant_context import set_tenant_id

logger = logging.getLogger(__name__)

_MSAL_AVAILABLE = False
try:
    from msal import ConfidentialClientApplication
    import httpx
    _MSAL_AVAILABLE = True
except ImportError:
    logger.warning("[M365] msal or httpx not installed — M365 Secure Score ingest disabled")


def _severity_map(score: int) -> str:
    # Example thresholds, adjust as per M365 Secure Score control impact
    if score < 40:
        return "Critical"
    if score < 70:
        return "High"
    return "Medium"


def _parse_m365_secure_score_control(control: Dict[str, Any], account_id: str, tenant_id: str) -> Dict[str, Any]:
    control_id_raw = control.get("id", str(uuid.uuid4()))
    control_name = control.get("controlName", "Unknown Control")
    current_score = control.get("currentScore", 0)
    max_score = control.get("maxScore", 100)

    # Secure Score controls usually have a 'controlCategory', 'controlType' etc.
    # For simplicity, we'll map based on currentScore against maxScore.
    # A control is considered 'failing' if its current score is not max.
    is_failing = current_score < max_score
    severity = _severity_map(current_score) # map based on current score

    return {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "accountId": account_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": "microsoft365",
        "service": "secure_score",
        "checkId": f"M365-{control_id_raw.upper()}", # Use uppercase ID for consistency
        "title": f"M365 Secure Score: {control_name}",
        "description": f"Secure Score control '{control_name}' has score {current_score}/{max_score}. Category: {control.get('controlCategory', 'General')}.",
        "severity": severity,
        "status": "FAIL" if is_failing else "PASS",
        "remediation": f"Improve secure score for control '{control_name}'. Current score: {current_score}/{max_score}.",
        "raw_message": control,
    }


async def poll_m365_secure_scores(config: Dict[str, Any], account_id: str, tenant_id: str) -> int:
    """
    Poll Microsoft Graph Security API for Secure Score controls.
    Returns count of new findings ingested.
    """
    if not _MSAL_AVAILABLE:
        logger.debug("[M365] SDK unavailable, skipping poll")
        return 0

    m365_tenant_id = config.get("tenant_id", "")
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")

    if not all([m365_tenant_id, client_id, client_secret]):
        logger.warning("[M365] Incomplete credentials for tenant %s", tenant_id)
        return 0

    try:
        app = ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{m365_tenant_id}",
            client_credential=client_secret,
        )
        # acquire_token_for_client is synchronous, so run in a thread
        result = await asyncio.to_thread(app.acquire_token_for_client, scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in result:
            logger.error("[M365] Could not acquire access token: %s", result.get("error_description", "Unknown error"))
            return 0

        headers = {"Authorization": f"Bearer {result['access_token']}"}

        async with httpx.AsyncClient() as client:
            # First, fetch secureScores (high-level summary)
            # This is more for context, actual findings will come from control profiles
            # secure_scores_response = await client.get("https://graph.microsoft.com/v1.0/security/secureScores", headers=headers, timeout=10)
            # secure_scores_response.raise_for_status()
            # secure_scores_data = secure_scores_response.json()

            # Second, fetch secureScoreControlProfiles for detailed control info
            controls_response = await client.get("https://graph.microsoft.com/v1.0/security/secureScoreControlProfiles", headers=headers, timeout=10)
            controls_response.raise_for_status()
            controls_data = controls_response.json()

        findings: List[Dict[str, Any]] = []
        for control in controls_data.get("value", []):
            findings.append(_parse_m365_secure_score_control(control, account_id, tenant_id))

        if not findings:
            logger.info("[M365] No Secure Score control profiles found for tenant %s", tenant_id)
            return 0

        set_tenant_id(tenant_id)
        db = get_database()
        await db.cloud_findings.insert_many(findings)
        logger.info("[M365] Ingested %d Secure Score findings for tenant %s", len(findings), tenant_id)
        return len(findings)

    except Exception as exc:
        logger.error("[M365] Poll failed for tenant %s: %s", tenant_id, exc)
        return 0
