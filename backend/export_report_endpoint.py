import logging

from fastapi import APIRouter, HTTPException, Request, Response, Depends
from export_service import ExportService
from authentication_service import TokenData
from rbac_utils import require_permission, verify_permission
from tenant_context import set_tenant_id
from auth_roles import SUPER_ROLES
from database import get_database
import dlp_service
import rbac_defaults

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
    "Autonomous Ops Activity": ("view:autonomous_ops",),
}
AO_REPORT = "Autonomous Ops Activity"
_FORMATS = ("csv", "pdf")


@router.get("/api/reports/export")
async def export_report_endpoint(type: str, format: str, request: Request,
                                 user: TokenData = Depends(require_permission("export:reports"))):
    """Export report in CSV or PDF format."""
    needs = REPORT_PERMISSIONS.get(type)
    if needs is None:
        raise HTTPException(status_code=400, detail=f"Unknown report type '{type}'")
    if format not in _FORMATS:
        raise HTTPException(status_code=400, detail="format must be 'csv' or 'pdf'")
    if not any([await verify_permission(user, p) for p in needs]):
        raise HTTPException(status_code=403, detail=f"Exporting '{type}' needs {' or '.join(needs)}")

    if type == AO_REPORT:
        return await _autonomous_ops_activity(user, format, request.client.host if request.client else None)

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


async def _autonomous_ops_activity(user: TokenData, format: str, ip) -> Response:
    """The organization's own Autonomous Ops activity (all states, last 30 days, newest 5,000). It runs before the
    Super Admin elevation above and refuses platform staff: this report is never cross-tenant (D-09)."""
    from autonomous_ops import PLATFORM_TENANT_ID
    from autonomous_ops.reporting import export
    tenant_id = getattr(user, "tenant_id", None)
    if (rbac_defaults.is_platform_role(user.role) or user.role in _SUPER_ROLES
            or not tenant_id or tenant_id == PLATFORM_TENANT_ID):
        raise HTTPException(status_code=403,
                            detail="Open an organization in Tenants, then export from its Autonomous Ops screen.")
    try:
        result = await export.build(get_database(), tenant_id, bucket="all", days="30", fmt=format,
                                    viewer_is_platform_staff=False, allow_empty=True)
        return await export.deliver(result, user=user, tenant_id=tenant_id, fmt=format, bucket="all", days="30",
                                    entry="registry", ip=ip)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Export of %s failed: %s", AO_REPORT, e)
        raise HTTPException(status_code=500, detail="Internal server error")
