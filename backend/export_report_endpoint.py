import logging

from fastapi import APIRouter, HTTPException, Response, Depends
from export_service import ExportService
from authentication_service import TokenData
from rbac_utils import require_permission, verify_permission
from tenant_context import set_tenant_id
from auth_roles import SUPER_ROLES
import dlp_service

router = APIRouter(tags=["Export"])
logger = logging.getLogger(__name__)

# Cross-tenant elevation is for platform super-admins only: "admin" is a
# tenant-scoped role that tenant admins can assign to their own users.
_SUPER_ROLES = SUPER_ROLES

# Exporting a report needs export:reports plus one permission of the screen its data comes
# from, so an export never hands out more than the caller may view.
REPORT_PERMISSIONS = {
    "Asset Inventory": ("view:assets",),
    "Patch Management": ("view:patching",),
    "Security Events": ("view:security",),
    "AI Risk Register": ("view:ai_governance",),
    "Vulnerability": ("view:vulnerabilities",),
    "Threat Intelligence": ("view:threat_intel",),
    "SBOM": ("view:sbom",),
    "Secrets Management": ("view:secrets",),
    "EDR Alerts": ("view:security",),
    "Incident Response": ("view:security",),
    "Change Management": ("view:security",),
    "Agent Health": ("view:agents",),
    "Support Chat": ("manage:agents",),
    "Endpoint Chat": ("manage:agents",),
    "Audit Log": ("view:audit_log",),
    "User Activity": ("manage:users", "manage:rbac"),
    "Automation Policies": ("view:automation",),
    "Cloud Security": ("view:cloud_security",),
}
_FORMATS = ("csv", "pdf")


@router.get("/api/reports/export")
async def export_report_endpoint(type: str, format: str,
                                 user: TokenData = Depends(require_permission("export:reports"))):
    """Export report in CSV or PDF format."""
    needs = REPORT_PERMISSIONS.get(type)
    if needs is None:
        raise HTTPException(status_code=400, detail=f"Unknown report type '{type}'")
    if format not in _FORMATS:
        raise HTTPException(status_code=400, detail="format must be 'csv' or 'pdf'")
    if not any([await verify_permission(user, p) for p in needs]):
        raise HTTPException(status_code=403, detail=f"Exporting '{type}' needs {' or '.join(needs)}")

    service = ExportService()
    is_admin = getattr(user, "role", "") in _SUPER_ROLES
    if is_admin:
        # Bypass tenant isolation so super-admins see all tenants' data
        set_tenant_id("platform-admin")
    tenant_id = None if is_admin else getattr(user, "tenant_id", None)
    try:
        rows = await service.fetch_rows(type, tenant_id=tenant_id)
        blocking, alerting = await dlp_service.scan_export(rows, tenant_id)
    except Exception as e:
        logger.error("Export of %s failed: %s", type, e)
        raise HTTPException(status_code=500, detail="Internal server error")

    if blocking or alerting:
        await dlp_service.record_export_incident(user.username, tenant_id or user.tenant_id, f"{type}.{format}",
                                                 blocking + alerting, blocked=bool(blocking))
    if blocking:
        names = ", ".join(sorted({f["name"] for f in blocking}))
        raise HTTPException(status_code=403, detail=f"Export blocked by DLP policy: {names}")

    content, filename, media_type = service.render(type, format, rows)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Export-Rows": str(len(rows))},
    )
