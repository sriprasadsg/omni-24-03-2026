from fastapi import APIRouter, HTTPException, Response, Depends
from export_service import ExportService
from authentication_service import get_current_user, TokenData

router = APIRouter(tags=["Export"])

@router.get("/api/reports/export")
async def export_report_endpoint(type: str, format: str, user: TokenData = Depends(get_current_user)):
    """
    Export report in CSV or PDF format
    """
    service = ExportService()
    try:
        content, filename, media_type = await service.generate_report(type, format, tenant_id=user.tenant_id)
        
        headers = {
            'Content-Disposition': f'attachment; filename="{filename}"'
        }
        
        return Response(content=content, media_type=media_type, headers=headers)
    except Exception as e:
        print(f"Export error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
