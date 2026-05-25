from fastapi import APIRouter, HTTPException, Response, Depends
from export_service import ExportService
from authentication_service import get_current_user, TokenData
from tenant_context import set_tenant_id

router = APIRouter(tags=["Export"])

_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}

@router.get("/api/reports/export")
async def export_report_endpoint(type: str, format: str, user: TokenData = Depends(get_current_user)):
    """Export report in CSV or PDF format."""
    service = ExportService()
    try:
        is_admin = getattr(user, "role", "") in _ADMIN_ROLES
        if is_admin:
            # Bypass tenant isolation so admins see all tenants' data
            set_tenant_id("platform-admin")
        tenant_id = None if is_admin else getattr(user, "tenant_id", None)
        content, filename, media_type = await service.generate_report(type, format, tenant_id=tenant_id)
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        print(f"Export error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
