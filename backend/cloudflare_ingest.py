"""
Cloudflare Zero Trust Ingest
Polls Cloudflare Zero Trust events and ingests them into security_events.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from database import get_database
from tenant_context import set_tenant_id

logger = logging.getLogger(__name__)

try:
    import cloudflare
    _CLOUDFLARE_SDK_AVAILABLE = True
except ImportError:
    _CLOUDFLARE_SDK_AVAILABLE = False
    logger.warning("[Cloudflare] cloudflare SDK not installed — Cloudflare Zero Trust ingest disabled")


def _make_cloudflare_client(config: Dict[str, Any]):
    if not _CLOUDFLARE_SDK_AVAILABLE:
        return None
    # Real client — construction only needs the API token (no network call),
    # so this is safe to share with the still-live 2-arg SIEM poll function
    # below, which never reads anything off the returned client besides its
    # truthiness.
    return cloudflare.Cloudflare(api_token=config.get("cf_api_token"))


def _severity_map(cf_severity: str) -> str:
    return {
        "CRITICAL": "Critical",
        "HIGH": "High",
        "MEDIUM": "Medium",
        "LOW": "Low",
    }.get(cf_severity, "Medium")


async def poll_cloudflare_zero_trust_events(config: Dict[str, Any], omni_tenant_id: str) -> int:
    """
    Poll Cloudflare Zero Trust events for a configured integration.
    Returns count of new events ingested.

    No real SIEM-domain polling is wired here (32-REVIEW.md CR-01): this
    used to fabricate a hardcoded "Test Event" and write it into
    security_events unlabeled, corrupting the SIEM with an invented finding
    on every call. poll_cloudflare_cspm_findings() below is the real, tested
    zone-security integration (CSPM domain) — this SIEM-domain function
    fails safe (0 events) until it gets a real implementation.
    """
    if not _CLOUDFLARE_SDK_AVAILABLE:
        return 0

    required_fields = ["cf_account_id", "cf_api_token"]
    if not all(config.get(field) for field in required_fields):
        logger.warning("[Cloudflare] Incomplete credentials for tenant %s", omni_tenant_id)
        return 0

    logger.warning("[Cloudflare] SIEM poll for tenant %s: not implemented, no findings ingested", omni_tenant_id)
    return 0


# --- CSPM domain (cloud_accounts / cloud_findings) ---
# Real, account-scoped ingest — distinct from the SIEM 2-arg function above
# (Pattern 4 / Pitfall 3). Shares _make_cloudflare_client() since real
# construction with just an api_token never raises (verified against the
# installed SDK), unlike OCI.

_CLOUDFLARE_CSPM_SETTING_IDS = ["ssl", "min_tls_version", "waf"]


def _cloudflare_setting_is_compliant(setting_id: str, value: Any) -> bool:
    if setting_id == "ssl":
        return value in ("full", "strict", "origin_pull")
    if setting_id == "min_tls_version":
        return value in ("1.2", "1.3")
    if setting_id == "waf":
        return value == "on"
    return True


def _parse_cloudflare_setting(setting: Any, account_id: str, tenant_id: str) -> Dict[str, Any]:
    setting_id = getattr(setting, "id", "unknown")
    value = getattr(setting, "value", None)
    return {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "accountId": account_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": "cloudflare",
        "service": "zone_security",
        "checkId": f"CF-{setting_id}",
        "title": f"Cloudflare Zone Setting: {setting_id}",
        "description": f"Zone setting '{setting_id}' is non-compliant (value='{value}').",
        "severity": _severity_map("HIGH" if setting_id == "waf" else "MEDIUM"),
        "status": "FAIL",
        "remediation": f"Review and remediate the '{setting_id}' Cloudflare zone security setting.",
        "raw_message": str(setting),
    }


async def poll_cloudflare_cspm_findings(config: Dict[str, Any], account_id: str, tenant_id: str) -> int:
    """
    Poll Cloudflare zone security settings (SSL mode, minimum TLS version,
    legacy WAF managed rules) for real, account-scoped CSPM findings.
    Returns count of findings ingested into cloud_findings.
    """
    if not _CLOUDFLARE_SDK_AVAILABLE:
        return 0

    api_token = config.get("cf_api_token")
    zone_id = config.get("cf_zone_id") or config.get("cf_account_id")
    if not all([api_token, zone_id]):
        logger.warning("[Cloudflare] Incomplete CSPM credentials for tenant %s", tenant_id)
        return 0

    try:
        client = await asyncio.to_thread(_make_cloudflare_client, config)
        if not client:
            return 0

        non_compliant = []
        for setting_id in _CLOUDFLARE_CSPM_SETTING_IDS:
            setting = await asyncio.to_thread(client.zones.settings.get, setting_id, zone_id=zone_id)
            if setting is None:
                continue
            if not _cloudflare_setting_is_compliant(setting_id, getattr(setting, "value", None)):
                non_compliant.append(setting)

        if not non_compliant:
            return 0

        findings = [_parse_cloudflare_setting(s, account_id, tenant_id) for s in non_compliant]

        set_tenant_id(tenant_id)
        db = get_database()
        await db.cloud_findings.insert_many(findings)
        logger.info("[Cloudflare] Ingested %d CSPM findings for tenant %s", len(findings), tenant_id)
        return len(findings)

    except Exception as exc:
        logger.error("[Cloudflare] CSPM poll failed for tenant %s: %s", tenant_id, exc)
        return 0
