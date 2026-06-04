"""
Bundle Management API
Endpoints for browsing predefined bundles and assigning them to tenants.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from authentication_service import get_current_user
from database import get_database
from rate_limiter import limiter
from feature_bundles import (
    FEATURE_CATALOG,
    PREDEFINED_BUNDLES,
    get_bundle_list,
    get_feature_catalog,
    resolve_tenant_features,
)
from rbac_utils import require_permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bundles", tags=["Bundles"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class AssignBundlesRequest(BaseModel):
    assigned_bundles: List[str] = []
    custom_features: List[str] = []
    blocked_features: List[str] = []


class UpdateTenantFeaturesRequest(BaseModel):
    """Partial update — only provided fields are changed."""
    assigned_bundles: Optional[List[str]] = None
    custom_features: Optional[List[str]] = None
    blocked_features: Optional[List[str]] = None


# ── Bundle catalogue routes ───────────────────────────────────────────────────

@router.get("")
@limiter.limit("60/minute")
async def list_bundles(request: Request, _=Depends(get_current_user)):
    """Return all predefined bundles with their feature lists."""
    return {"bundles": get_bundle_list(), "total": len(PREDEFINED_BUNDLES)}


@router.get("/catalog")
@limiter.limit("30/minute")
async def list_feature_catalog(request: Request, _=Depends(get_current_user)):
    """Return the full feature catalog grouped by category."""
    features = get_feature_catalog()
    grouped: dict = {}
    for f in features:
        cat = f["category"]
        grouped.setdefault(cat, []).append(f)
    return {"catalog": grouped, "total": len(features)}


@router.get("/{bundle_key}")
@limiter.limit("60/minute")
async def get_bundle(request: Request, bundle_key: str, _=Depends(get_current_user)):
    """Return details for a single predefined bundle."""
    bundle = PREDEFINED_BUNDLES.get(bundle_key)
    if not bundle:
        raise HTTPException(status_code=404, detail=f"Bundle '{bundle_key}' not found.")
    features_detail = [
        {"key": f, **FEATURE_CATALOG[f]}
        for f in bundle["features"]
        if f in FEATURE_CATALOG
    ]
    return {"key": bundle_key, **{k: v for k, v in bundle.items() if k != "features"}, "features": features_detail}


# ── Tenant feature assignment routes ─────────────────────────────────────────

@router.get("/tenant/{tenant_id}/features")
@limiter.limit("60/minute")
async def get_tenant_features(
    request: Request,
    tenant_id: str,
    current_user=Depends(get_current_user),
):
    """
    Return the effective feature set for a tenant, computed from their
    assigned bundles + custom_features - blocked_features.
    """
    db = get_database()
    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    assigned = tenant.get("assignedBundles", [])
    custom = tenant.get("customFeatures", [])
    blocked = tenant.get("blockedFeatures", [])

    effective = resolve_tenant_features(assigned, custom, blocked)
    feature_detail = [
        {"key": k, **FEATURE_CATALOG[k]}
        for k in sorted(effective)
        if k in FEATURE_CATALOG
    ]
    return {
        "tenant_id": tenant_id,
        "assigned_bundles": assigned,
        "custom_features": custom,
        "blocked_features": blocked,
        "effective_features": feature_detail,
        "feature_keys": sorted(effective),
    }


@router.put("/tenant/{tenant_id}/assign")
@limiter.limit("20/minute")
async def assign_bundles_to_tenant(
    request: Request,
    tenant_id: str,
    body: AssignBundlesRequest,
    _=Depends(require_permission("manage:tenants")),
):
    """
    Replace the tenant's full bundle assignment (bundles + custom + blocked).
    Requires manage:tenants permission (Super Admin / Tenant Admin).
    """
    db = get_database()
    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    unknown = [b for b in body.assigned_bundles if b not in PREDEFINED_BUNDLES]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown bundle keys: {unknown}")

    unknown_feat = [f for f in body.custom_features if f not in FEATURE_CATALOG]
    if unknown_feat:
        raise HTTPException(status_code=400, detail=f"Unknown feature keys: {unknown_feat}")

    await db.tenants.update_one(
        {"id": tenant_id},
        {"$set": {
            "assignedBundles": body.assigned_bundles,
            "customFeatures": body.custom_features,
            "blockedFeatures": body.blocked_features,
        }},
    )
    effective = resolve_tenant_features(
        body.assigned_bundles, body.custom_features, body.blocked_features
    )
    logger.info(
        "Tenant %s assigned bundles %s → %d effective features",
        tenant_id, body.assigned_bundles, len(effective),
    )
    return {
        "success": True,
        "tenant_id": tenant_id,
        "assigned_bundles": body.assigned_bundles,
        "effective_feature_count": len(effective),
        "effective_feature_keys": sorted(effective),
    }


@router.patch("/tenant/{tenant_id}/assign")
@limiter.limit("20/minute")
async def patch_tenant_bundles(
    request: Request,
    tenant_id: str,
    body: UpdateTenantFeaturesRequest,
    _=Depends(require_permission("manage:tenants")),
):
    """Partial update — only the fields you provide are changed."""
    db = get_database()
    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    update: dict = {}
    if body.assigned_bundles is not None:
        unknown = [b for b in body.assigned_bundles if b not in PREDEFINED_BUNDLES]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown bundle keys: {unknown}")
        update["assignedBundles"] = body.assigned_bundles
    if body.custom_features is not None:
        update["customFeatures"] = body.custom_features
    if body.blocked_features is not None:
        update["blockedFeatures"] = body.blocked_features

    if update:
        await db.tenants.update_one({"id": tenant_id}, {"$set": update})

    # Re-read to compute effective
    tenant = await db.tenants.find_one({"id": tenant_id})
    effective = resolve_tenant_features(
        tenant.get("assignedBundles", []),
        tenant.get("customFeatures", []),
        tenant.get("blockedFeatures", []),
    )
    return {
        "success": True,
        "tenant_id": tenant_id,
        "effective_feature_count": len(effective),
        "effective_feature_keys": sorted(effective),
    }


@router.delete("/tenant/{tenant_id}/assign")
@limiter.limit("10/minute")
async def clear_tenant_bundles(
    request: Request,
    tenant_id: str,
    _=Depends(require_permission("manage:tenants")),
):
    """Remove all bundle assignments from a tenant (reverts to tier-only access)."""
    db = get_database()
    result = await db.tenants.update_one(
        {"id": tenant_id},
        {"$set": {"assignedBundles": [], "customFeatures": [], "blockedFeatures": []}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    return {"success": True, "tenant_id": tenant_id}
