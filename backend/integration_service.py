"""
Integration Service aggregator.

Logic is split across three mixin modules:
  integration_service_siem.py      — Splunk, ELK, Wazuh, QRadar
  integration_service_ticketing.py — Jira, ServiceNow, Zoho Desk, CMDB sync
  integration_service_edr.py       — CrowdStrike, SentinelOne, Defender, ChatOps, Okta, Entra ID
"""

import os as _os
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from integration_service_siem import IntegrationServiceSiemMixin
from integration_service_ticketing import IntegrationServiceTicketingMixin
from integration_service_edr import IntegrationServiceEdrMixin

_log = logging.getLogger(__name__)

# Credential-bearing config keys. A webhook URL is itself the credential for
# Slack/Teams, so it is masked too. get_all_configs returns SECRET_MASK in
# their place; save_config treats SECRET_MASK (or None) as "keep the stored
# value", so a settings UI can round-trip a masked config without wiping it.
SECRET_FIELDS = frozenset({
    "token", "password", "api_key", "api_token", "secret", "secret_key",
    "client_secret", "auth_token", "credentials_json", "webhook_url",
    # camelCase spellings used by the integrations_v2 catalog configs
    "apiKey", "apiToken", "secretKey", "accessKey", "accessToken",
    "clientSecret", "authToken", "webhookUrl",
})
SECRET_MASK = "********"


def redact_config(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Copy of an integration config with secret values (top level and nested
    ``config``) replaced by SECRET_MASK."""
    out = dict(doc)
    for key in SECRET_FIELDS:
        if out.get(key):
            out[key] = SECRET_MASK
    nested = out.get("config")
    if isinstance(nested, dict):
        out["config"] = redact_config(nested)
    return out


def _keep_stored_secrets(incoming: Dict[str, Any], stored: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(incoming)
    for key in SECRET_FIELDS:
        if merged.get(key) in (None, SECRET_MASK) and stored.get(key) is not None:
            merged[key] = stored[key]
        elif merged.get(key) == SECRET_MASK:
            merged.pop(key)  # never persist the mask itself
    nested_in, nested_stored = merged.get("config"), stored.get("config")
    if isinstance(nested_in, dict):
        merged["config"] = _keep_stored_secrets(nested_in, nested_stored if isinstance(nested_stored, dict) else {})
    return merged

if _os.getenv("DISABLE_SSL_VERIFY", "").lower() in ("1", "true", "yes"):
    _log.warning(
        "DISABLE_SSL_VERIFY is set but ignored — SSL certificate validation is enforced. "
        "Use per-integration verify_ssl config for self-signed cert environments."
    )


class IntegrationService(
    IntegrationServiceSiemMixin,
    IntegrationServiceTicketingMixin,
    IntegrationServiceEdrMixin,
):
    """External platform integration service."""

    def __init__(self, db):
        self.db = db

    async def _get_integration_config(
        self, integration_type: str, platform: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch integration configuration from the database."""
        return await self.db.integration_configs.find_one(
            {"type": integration_type, "platform": platform}, {"_id": 0}
        )

    async def get_all_configs(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Get all integration configurations for a tenant (secrets masked)."""
        docs = await self.db.integration_configs.find(
            {"tenantId": tenant_id}, {"_id": 0}
        ).to_list(length=1000)
        return [redact_config(d) for d in docs]

    async def save_config(
        self, tenant_id: str, config_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Save or update an integration configuration."""
        integration_type = config_data.get("type")
        platform = config_data.get("platform")
        if not integration_type or not platform:
            return {"success": False, "error": "Missing type or platform"}
        key = {"tenantId": tenant_id, "type": integration_type, "platform": platform}
        stored = await self.db.integration_configs.find_one(key, {"_id": 0}) or {}
        config_data = _keep_stored_secrets(config_data, stored)
        await self.db.integration_configs.update_one(
            key,
            {"$set": {**config_data, "tenantId": tenant_id,
                      "updatedAt": datetime.now(timezone.utc)}},
            upsert=True,
        )
        return {"success": True, "message": f"Configuration for {platform} saved"}


def get_integration_service(db) -> IntegrationService:
    """Get an integration service instance."""
    return IntegrationService(db)
