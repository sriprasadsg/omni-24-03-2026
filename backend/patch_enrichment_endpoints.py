from fastapi import APIRouter, HTTPException, Depends
import asyncio
import logging
from datetime import datetime, timezone
from database import get_database
from patch_service import get_patch_service
from authentication_service import get_current_user
from auth_types import TokenData
from patch_core_endpoints import _PATCH_ADMIN_ROLES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patches", tags=["Patch Management"])


@router.get("/cve/{cve_id}")
async def get_cve_info(
    cve_id: str,
    _current_user: TokenData = Depends(get_current_user),
):
    """Get detailed CVE information from NVD."""
    patch_service = get_patch_service()
    cve_data = await patch_service.get_cve_details(cve_id)
    if not cve_data:
        raise HTTPException(status_code=404, detail="CVE not found")
    return cve_data


@router.get("/{patch_id}/enrich")
async def enrich_patch(
    patch_id: str,
    _current_user: TokenData = Depends(get_current_user),
):
    """Enrich a patch with CVE/CVSS/EPSS intelligence."""
    try:
        db = get_database()
        patch = await db.patches.find_one({"id": patch_id}, {"_id": 0})
        if not patch:
            raise HTTPException(status_code=404, detail="Patch not found")

        patch_service = get_patch_service()
        enriched = await patch_service.enrich_patch_with_intelligence(patch)

        await db.patches.update_one(
            {"id": patch_id},
            {"$set": {
                "cvss_score":     enriched.get("cvss_score"),
                "epss_score":     enriched.get("epss_score"),
                "priority_score": enriched.get("priority_score"),
                "sla_hours":      enriched.get("sla_hours"),
                "patch_deadline": enriched.get("patch_deadline"),
                "cve_details":    enriched.get("cve_details"),
                "updated_at":     datetime.now(timezone.utc).isoformat(),
            }},
        )
        return enriched
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error enriching patch: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/enrich-all")
async def enrich_all_patches(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Batch enrich all pending patches with CVE intelligence."""
    try:
        db = get_database()
        is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
        caller_tenant = getattr(current_user, "tenant_id", None) or None
        if not caller_tenant and not is_admin:
            raise HTTPException(status_code=403, detail="Tenant context required")
        if tenant_id and not is_admin and tenant_id != caller_tenant:
            raise HTTPException(status_code=403, detail="Not authorized to access this tenant")
        effective_tenant = tenant_id if (tenant_id and is_admin) else caller_tenant

        patches = await db.patches.find(
            {"status": "Pending", "tenantId": effective_tenant}, {"_id": 0}
        ).to_list(length=500)

        patch_service = get_patch_service()
        enriched_count = 0
        for patch in patches:
            try:
                enriched = await patch_service.enrich_patch_with_intelligence(patch)
                await db.patches.update_one(
                    {"id": patch["id"]},
                    {"$set": {
                        "cvss_score":     enriched.get("cvss_score"),
                        "epss_score":     enriched.get("epss_score"),
                        "priority_score": enriched.get("priority_score"),
                        "sla_hours":      enriched.get("sla_hours"),
                        "severity":       enriched.get("severity", patch.get("severity")),
                        "updated_at":     datetime.now(timezone.utc).isoformat(),
                    }},
                )
                enriched_count += 1
                await asyncio.sleep(0.6)  # NVD rate limit: ~1.67 req/s with API key
            except Exception as e:
                logger.error("Error enriching patch %s: %s", patch["id"], e)
                continue

        return {
            "success":       True,
            "total_patches": len(patches),
            "enriched_count": enriched_count,
            "message":       f"Enriched {enriched_count} patches with CVE intelligence",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in batch enrichment: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/prioritized")
async def get_prioritized_patches(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Get patches sorted by intelligent priority score."""
    try:
        db = get_database()
        is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
        caller_tenant = getattr(current_user, "tenant_id", None) or None
        if not caller_tenant and not is_admin:
            raise HTTPException(status_code=403, detail="Tenant context required")
        if tenant_id and not is_admin and tenant_id != caller_tenant:
            raise HTTPException(status_code=403, detail="Not authorized to access this tenant")
        effective_tenant = tenant_id if (tenant_id and is_admin) else caller_tenant

        patches = await db.patches.find(
            {"status": "Pending", "tenantId": effective_tenant}, {"_id": 0}
        ).to_list(length=500)

        prioritized = sorted(patches, key=lambda p: p.get("priority_score", 0), reverse=True)
        return {"patches": prioritized, "total": len(prioritized)}
    except Exception as e:
        logger.error("Error getting prioritized patches: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/compliance-status")
async def get_compliance_status(
    tenant_id: str = None,
    framework: str = "SOC2",
    current_user: TokenData = Depends(get_current_user),
):
    """Get patch compliance status against regulatory framework."""
    try:
        db = get_database()
        is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
        caller_tenant = getattr(current_user, "tenant_id", None) or None
        if not caller_tenant and not is_admin:
            raise HTTPException(status_code=403, detail="Tenant context required")
        if tenant_id and not is_admin and tenant_id != caller_tenant:
            raise HTTPException(status_code=403, detail="Not authorized to access this tenant")
        effective_tenant = tenant_id if (tenant_id and is_admin) else caller_tenant

        patches = await db.patches.find(
            {"status": "Pending", "tenantId": effective_tenant}, {"_id": 0}
        ).to_list(length=500)

        now = datetime.now(timezone.utc).timestamp()
        patch_service = get_patch_service()
        compliant, at_risk, overdue = [], [], []

        for patch in patches:
            severity = patch.get("severity", "Medium")
            sla_hours = patch.get("sla_hours") or patch_service.calculate_patch_sla_hours(severity, framework)
            created_at = datetime.fromisoformat(
                patch.get("createdAt", datetime.now(timezone.utc).isoformat())
            ).timestamp()
            deadline = created_at + (sla_hours * 3600)
            time_remaining = deadline - now
            patch_with_sla = {**patch, "sla_hours": sla_hours, "deadline": deadline,
                              "time_remaining_hours": time_remaining / 3600}
            if time_remaining < 0:
                overdue.append(patch_with_sla)
            elif time_remaining < (sla_hours * 0.25 * 3600):
                at_risk.append(patch_with_sla)
            else:
                compliant.append(patch_with_sla)

        total = len(patches)
        compliance_rate = (len(compliant) / total * 100) if total > 0 else 100

        return {
            "framework":       framework,
            "compliance_rate": round(compliance_rate, 2),
            "total_patches":   total,
            "compliant":       len(compliant),
            "at_risk":         len(at_risk),
            "overdue":         len(overdue),
            "patches": {"compliant": compliant, "at_risk": at_risk, "overdue": overdue},
        }
    except Exception as e:
        logger.error("Error calculating compliance: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
