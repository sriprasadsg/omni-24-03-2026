"""
Feature Flag System
===================
Two-layer enforcement:

  Layer 1 — Subscription tier gate (unchanged behaviour)
  Layer 2 — Bundle/feature assignment gate (new)

A tenant has access to a feature when EITHER:
  - Their tier meets the minimum required tier for that feature, AND
    they have no explicit bundle assignment (legacy tier-only mode), OR
  - The feature is in their effective bundle set (assignedBundles resolved
    via feature_bundles.resolve_tenant_features).

This lets existing tenants keep working without touching their config, while
new bundle-based tenants are controlled purely by assigned bundles.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from fastapi import Depends, HTTPException
from authentication_service import get_current_user
from database import get_database

logger = logging.getLogger(__name__)

# Tier precedence — higher index = higher tier
TIER_ORDER: Dict[str, int] = {
    "Free":       0,
    "Pro":        1,
    "Enterprise": 2,
    "Custom":     3,
}

# feature_key → minimum tier required (kept for backward compatibility)
FEATURE_TIERS: Dict[str, str] = {
    # ── Always available (Free) ──────────────────────────────────────────────
    "dashboard":              "Free",
    "tickets":                "Free",
    "agents":                 "Free",
    "assets":                 "Free",
    "settings":               "Free",
    "users":                  "Free",
    "vulnerabilities":        "Free",
    "audit_log":              "Free",
    "knowledge_base":         "Free",
    "subscriptions":          "Free",
    "support_chat":           "Free",

    # ── Pro ──────────────────────────────────────────────────────────────────
    "observability":          "Pro",
    "apm":                    "Pro",
    "tracing":                "Pro",
    "logs":                   "Pro",
    "network":                "Pro",
    "web_monitoring":         "Pro",
    "edr":                    "Pro",
    "mdr":                    "Pro",
    "xdr":                    "Pro",
    "threat_hunting":         "Pro",
    "threat_intel":           "Pro",
    "ueba":                   "Pro",
    "dlp":                    "Pro",
    "siem":                   "Pro",
    "compliance":             "Pro",
    "playbooks":              "Pro",
    "automation":             "Pro",
    "ai_remediation":         "Pro",
    "sbom":                   "Pro",
    "reporting":              "Pro",
    "patching":               "Pro",
    "software_updates":       "Pro",
    "software_deployment":    "Pro",
    "remote_access":          "Pro",
    "devsecops":              "Pro",
    "supply_chain":           "Pro",
    "incident_response":      "Pro",
    "swarm":                  "Pro",
    "risk_register":          "Pro",
    "vendor_management":      "Pro",
    "sast":                   "Pro",
    "dast":                   "Pro",

    # ── Enterprise ───────────────────────────────────────────────────────────
    "chaos_engineering":      "Enterprise",
    "cissp_oracle":           "Enterprise",
    "hadr":                   "Enterprise",
    "custom_frameworks":      "Enterprise",
    "finops":                 "Enterprise",
    "mlops":                  "Enterprise",
    "llmops":                 "Enterprise",
    "automl":                 "Enterprise",
    "cxo_dashboard":          "Enterprise",
    "advanced_bi":            "Enterprise",
    "digital_twin":           "Enterprise",
    "zero_trust":             "Enterprise",
    "data_lake":              "Enterprise",
    "service_catalog":        "Enterprise",
    "attack_path":            "Enterprise",
    "dspm":                   "Enterprise",
    "ai_governance":          "Enterprise",
    "data_governance":        "Enterprise",
    "unified_ops":            "Enterprise",
    "sustainability":         "Enterprise",
    "goal_system":            "Enterprise",
}


def tenant_has_feature(tenant_tier: str, feature_key: str) -> bool:
    """Return True if the given tier meets the minimum required for feature_key."""
    required = TIER_ORDER.get(FEATURE_TIERS.get(feature_key, "Free"), 0)
    actual   = TIER_ORDER.get(tenant_tier or "Free", 0)
    return actual >= required


def get_enabled_features(tenant_tier: str) -> List[str]:
    """Return all feature keys available for the given tier (tier-only mode)."""
    return [k for k in FEATURE_TIERS if tenant_has_feature(tenant_tier, k)]


async def _get_tenant_effective_features(tenant_id: Optional[str]) -> Optional[Set[str]]:
    """
    If the tenant has assigned bundles, return their effective feature set.
    Returns None if tenant is in legacy tier-only mode (no bundles assigned).
    """
    if not tenant_id:
        return None
    try:
        from feature_bundles import resolve_tenant_features
        db = get_database()
        tenant = await db.tenants.find_one({"id": tenant_id}, {"assignedBundles": 1, "customFeatures": 1, "blockedFeatures": 1})
        if not tenant:
            return None
        assigned = tenant.get("assignedBundles") or []
        if not assigned and not tenant.get("customFeatures"):
            return None  # legacy mode — fall back to tier check
        return resolve_tenant_features(
            assigned,
            tenant.get("customFeatures") or [],
            tenant.get("blockedFeatures") or [],
        )
    except Exception as exc:
        logger.warning("Failed to resolve tenant bundle features: %s", exc)
        return None


def require_feature(feature_key: str):
    """
    FastAPI dependency — raises 403 if tenant doesn't have access to feature_key.

    Checks bundles first (if assigned), then falls back to subscription tier.

    Usage:
        @router.get("/some-endpoint")
        async def handler(_=Depends(require_feature("finops")), ...):
    """
    async def _check(current_user=Depends(get_current_user)):
        db = get_database()
        tenant_id = getattr(current_user, "tenant_id", None)
        tier = "Free"
        if tenant_id:
            tenant = await db.tenants.find_one({"id": tenant_id})
            if tenant:
                tier = tenant.get("subscriptionTier", "Free")

        # Layer 2: bundle-based check (takes priority if bundles are assigned)
        effective = await _get_tenant_effective_features(tenant_id)
        if effective is not None:
            if feature_key not in effective:
                raise HTTPException(
                    status_code=403,
                    detail=f"Feature '{feature_key}' is not included in your current plan.",
                )
            return current_user

        # Layer 1: legacy tier-based check
        if not tenant_has_feature(tier, feature_key):
            raise HTTPException(
                status_code=403,
                detail=f"Feature '{feature_key}' requires a higher subscription tier. Current: {tier}.",
            )
        return current_user
    return _check
