"""
Feature Bundle System
=====================
Single source of truth for:
  - PREDEFINED_BUNDLES — named, sellable groupings customers can be assigned
  - Bundle helpers     — resolve, list, catalog

FEATURE_CATALOG lives in feature_catalog.py (re-exported here for backward compatibility).

Bundles are stored on each tenant document as:
  {
    "assignedBundles": ["security", "compliance"],   # predefined bundle keys
    "customFeatures":  ["finops"],                   # one-off additions
    "blockedFeatures": ["cxo_dashboard"],            # explicit removals
  }

Effective feature list = union(bundles) + customFeatures - blockedFeatures
"""

from __future__ import annotations
from typing import Dict, List, Optional, Set

from feature_catalog import FEATURE_CATALOG  # noqa: F401 — re-exported for existing imports


# ── Predefined Bundles ────────────────────────────────────────────────────────

PREDEFINED_BUNDLES: Dict[str, dict] = {
    "ticketing_only": {
        "name": "Ticketing Only",
        "description": "Just the internal ticketing system — for teams that only need issue tracking.",
        "color": "#6366f1",
        "icon": "ticket",
        "features": ["dashboard", "tickets", "users", "settings", "audit_log"],
        "price_hint": "Starter",
    },
    "starter": {
        "name": "Starter",
        "description": "Essential tools for small teams getting started with security operations.",
        "color": "#10b981",
        "icon": "rocket",
        "features": [
            "dashboard", "tickets", "agents", "assets", "users",
            "settings", "audit_log", "knowledge_base", "vulnerabilities",
        ],
        "price_hint": "Free",
    },
    "security": {
        "name": "Security Bundle",
        "description": "Full threat detection, EDR, SIEM, and incident response capabilities.",
        "color": "#ef4444",
        "icon": "shield",
        "features": [
            "dashboard", "agents", "assets", "audit_log",
            "vulnerabilities", "edr", "mdr", "xdr",
            "threat_hunting", "threat_intel", "ueba", "dlp",
            "siem", "incident_response",
        ],
        "price_hint": "Pro",
    },
    "compliance": {
        "name": "Compliance Bundle",
        "description": "Everything needed to achieve and maintain compliance with major frameworks.",
        "color": "#f59e0b",
        "icon": "clipboard-check",
        "features": [
            "dashboard", "audit_log", "compliance", "risk_register",
            "vendor_management", "reporting", "knowledge_base",
        ],
        "price_hint": "Pro",
    },
    "observability": {
        "name": "Observability Bundle",
        "description": "Full-stack visibility — metrics, traces, logs, and network monitoring.",
        "color": "#3b82f6",
        "icon": "activity",
        "features": [
            "dashboard", "observability", "apm", "tracing",
            "logs", "network", "web_monitoring", "reporting",
        ],
        "price_hint": "Pro",
    },
    "devsecops": {
        "name": "DevSecOps Bundle",
        "description": "Secure the software supply chain from code to production.",
        "color": "#8b5cf6",
        "icon": "code",
        "features": [
            "dashboard", "devsecops", "supply_chain", "sbom",
            "sast", "dast", "patching", "software_updates", "software_deployment",
        ],
        "price_hint": "Pro",
    },
    "operations": {
        "name": "Operations Bundle",
        "description": "Automate response, manage patches, and streamline platform operations.",
        "color": "#06b6d4",
        "icon": "settings",
        "features": [
            "dashboard", "tickets", "agents", "assets",
            "patching", "software_updates", "software_deployment",
            "playbooks", "automation", "remote_access", "reporting",
        ],
        "price_hint": "Pro",
    },
    "ai_ml": {
        "name": "AI / ML Bundle",
        "description": "Govern, monitor, and orchestrate AI and machine learning workloads.",
        "color": "#ec4899",
        "icon": "brain",
        "features": [
            "dashboard", "ai_governance", "ai_remediation",
            "mlops", "llmops", "automl",
        ],
        "price_hint": "Enterprise",
    },
    "enterprise": {
        "name": "Enterprise Bundle",
        "description": "Advanced capabilities for large organisations — FinOps, HADR, chaos, digital twin.",
        "color": "#f97316",
        "icon": "building",
        "features": [
            "dashboard", "finops", "hadr", "chaos_engineering",
            "cxo_dashboard", "digital_twin", "zero_trust",
            "data_lake", "advanced_bi", "sustainability", "goal_system",
        ],
        "price_hint": "Enterprise",
    },
    "full_platform": {
        "name": "Full Platform",
        "description": "Every feature — the complete enterprise security and operations platform.",
        "color": "#64748b",
        "icon": "layers",
        "features": list(FEATURE_CATALOG.keys()),
        "price_hint": "Enterprise",
    },
}


# ── Helper Functions ──────────────────────────────────────────────────────────

def resolve_tenant_features(
    assigned_bundles: List[str],
    custom_features: Optional[List[str]] = None,
    blocked_features: Optional[List[str]] = None,
) -> Set[str]:
    """
    Compute the effective feature set for a tenant.
    effective = union(bundle features) + custom_features - blocked_features
    """
    effective: Set[str] = set()
    for bundle_key in (assigned_bundles or []):
        bundle = PREDEFINED_BUNDLES.get(bundle_key)
        if bundle:
            effective.update(bundle["features"])
    effective.update(custom_features or [])
    effective.difference_update(blocked_features or [])
    return effective


def get_bundle_list() -> List[dict]:
    """Return all predefined bundles as a list with their feature details."""
    result = []
    for key, bundle in PREDEFINED_BUNDLES.items():
        features_detail = [
            {"key": f, **FEATURE_CATALOG[f]}
            for f in bundle["features"]
            if f in FEATURE_CATALOG
        ]
        result.append({
            "key": key,
            **{k: v for k, v in bundle.items() if k != "features"},
            "features": features_detail,
            "feature_count": len(features_detail),
        })
    return result


def get_feature_catalog() -> List[dict]:
    """Return the full feature catalog as a list."""
    return [{"key": k, **v} for k, v in FEATURE_CATALOG.items()]
