from fastapi import APIRouter, HTTPException, Form, Depends
from fastapi.responses import FileResponse
import logging
import os
from datetime import datetime
from authentication_service import get_current_user
from compliance_reporting_service import compliance_reporting_service

logger = logging.getLogger(__name__)

router = APIRouter()

_REPORTS_DIR = "static/reports"


@router.post("/api/compliance/reports/generate")
async def generate_compliance_report(
    framework_id: str = Form(...),
    current_user=Depends(get_current_user),
):
    """Generate CSV compliance report."""
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    try:
        report = await compliance_reporting_service.generate_report(tenant_id, framework_id)
        return {"success": True, "report": report}
    except Exception as e:
        logger.error("Failed to generate CSV compliance report for tenant %s: %s", tenant_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/compliance/reports/generate/excel")
async def generate_excel_compliance_report(
    framework_id: str = Form(...),
    current_user=Depends(get_current_user),
):
    """Generate Excel compliance report with professional formatting."""
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    try:
        report = await compliance_reporting_service.generate_excel_report(tenant_id, framework_id)
        return {"success": True, "report": report}
    except Exception as e:
        logger.error("Failed to generate Excel compliance report for tenant %s: %s", tenant_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/compliance/reports/generate/pdf")
async def generate_pdf_compliance_report(
    framework_id: str = Form(...),
    current_user=Depends(get_current_user),
):
    """Generate PDF compliance report."""
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    try:
        report = await compliance_reporting_service.generate_pdf_report(tenant_id, framework_id)
        return {"success": True, "report": report}
    except Exception as e:
        logger.error("Failed to generate PDF compliance report for tenant %s: %s", tenant_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/compliance/reports/generate/all")
async def generate_all_compliance_report(
    format: str = Form(..., description="csv or excel"),
    current_user=Depends(get_current_user),
):
    """Generate a combined report for all frameworks."""
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    if format not in ("csv", "excel"):
        raise HTTPException(status_code=400, detail="Format must be 'csv' or 'excel'")
    try:
        report = await compliance_reporting_service.generate_all_frameworks_report(tenant_id, format)
        return {"success": True, "report": report}
    except Exception as e:
        logger.error("Failed to generate all-frameworks report for tenant %s: %s", tenant_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/compliance/reports/download/{filename}")
async def download_compliance_report(filename: str, current_user=Depends(get_current_user)):
    """Download compliance report with proper Content-Disposition header."""
    file_path = os.path.join(_REPORTS_DIR, filename)

    if not os.path.abspath(file_path).startswith(os.path.abspath(_REPORTS_DIR) + os.sep):
        raise HTTPException(status_code=404, detail="Report not found")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report not found")

    if filename.endswith(".pdf"):
        media_type = "application/pdf"
    elif filename.endswith(".xlsx"):
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif filename.endswith(".csv"):
        media_type = "text/csv"
    else:
        media_type = "application/octet-stream"

    return FileResponse(
        file_path,
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/api/compliance/reports")
async def list_compliance_reports(current_user=Depends(get_current_user)):
    """List all compliance reports (CSV, Excel, PDF)."""
    if not os.path.exists(_REPORTS_DIR):
        return []

    reports = []
    for f in os.listdir(_REPORTS_DIR):
        if f.endswith((".csv", ".xlsx", ".pdf")):
            reports.append({
                "filename": f,
                "url": f"/api/compliance/reports/download/{f}",
                "created": datetime.fromtimestamp(
                    os.path.getctime(os.path.join(_REPORTS_DIR, f))
                ).isoformat(),
            })
    reports.sort(key=lambda x: x["created"], reverse=True)
    return reports
