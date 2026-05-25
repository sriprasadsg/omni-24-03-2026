"""
Compliance Report Endpoints
Generates CSV, Excel, and PDF compliance reports via ComplianceReportingService
and serves previously generated reports from the database.
"""
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import FileResponse

from authentication_service import get_current_user
from auth_types import TokenData
from compliance_reporting_service import compliance_reporting_service
from database import get_database

router = APIRouter(prefix="/api/compliance/reports", tags=["Compliance Reports"])

_REPORTS_DIR = os.path.join(os.path.dirname(__file__), "static", "reports")


def _ensure_reports_dir():
    os.makedirs(_REPORTS_DIR, exist_ok=True)


# ── Generate ──────────────────────────────────────────────────────────────────

@router.post("/generate")
async def generate_csv_report(
    framework_id: str = Form(...),
    current_user: TokenData = Depends(get_current_user),
):
    """Generate a CSV compliance report for the given framework."""
    _ensure_reports_dir()
    tenant_id = getattr(current_user, "tenant_id", None)
    try:
        result = await compliance_reporting_service.generate_report(tenant_id, framework_id)
        await _persist_report_meta(result, framework_id, tenant_id, "csv", current_user)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/generate/excel")
async def generate_excel_report(
    framework_id: str = Form(...),
    current_user: TokenData = Depends(get_current_user),
):
    """Generate an Excel compliance report for the given framework."""
    _ensure_reports_dir()
    tenant_id = getattr(current_user, "tenant_id", None)
    try:
        result = await compliance_reporting_service.generate_excel_report(tenant_id, framework_id)
        await _persist_report_meta(result, framework_id, tenant_id, "excel", current_user)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/generate/pdf")
async def generate_pdf_report(
    framework_id: str = Form(...),
    current_user: TokenData = Depends(get_current_user),
):
    """Generate a PDF compliance report for the given framework."""
    _ensure_reports_dir()
    tenant_id = getattr(current_user, "tenant_id", None)
    try:
        result = await compliance_reporting_service.generate_pdf_report(tenant_id, framework_id)
        await _persist_report_meta(result, framework_id, tenant_id, "pdf", current_user)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Generate All ──────────────────────────────────────────────────────────────

@router.post("/generate/all/csv")
async def generate_all_csv_report(
    current_user: TokenData = Depends(get_current_user),
):
    """Generate a combined CSV report covering all compliance frameworks."""
    _ensure_reports_dir()
    tenant_id = getattr(current_user, "tenant_id", None)
    try:
        result = await compliance_reporting_service.generate_all_csv_report(tenant_id)
        await _persist_report_meta(result, "all", tenant_id, "csv", current_user)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/generate/all/excel")
async def generate_all_excel_report(
    current_user: TokenData = Depends(get_current_user),
):
    """Generate a combined Excel report covering all compliance frameworks."""
    _ensure_reports_dir()
    tenant_id = getattr(current_user, "tenant_id", None)
    try:
        result = await compliance_reporting_service.generate_all_excel_report(tenant_id)
        await _persist_report_meta(result, "all", tenant_id, "excel", current_user)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Download ──────────────────────────────────────────────────────────────────

@router.get("/download/{filename}")
async def download_report(
    filename: str,
    _current_user: TokenData = Depends(get_current_user),
):
    """Stream a previously generated report file as a download."""
    # Reject path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = os.path.join(_REPORTS_DIR, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Report file not found")

    # Verify the report belongs to the caller's tenant
    db = get_database()
    caller_tenant = getattr(_current_user, "tenant_id", None)
    caller_role = getattr(_current_user, "role", "")
    _SUPER_ADMIN_ROLES = {"Super Admin", "super_admin", "superadmin", "platform-admin"}
    if caller_role not in _SUPER_ADMIN_ROLES:
        report_meta = await db.compliance_reports.find_one({"filename": filename})
        if not report_meta or report_meta.get("tenantId") != caller_tenant:
            raise HTTPException(status_code=403, detail="Not authorized to access this report")

    ext = filename.rsplit(".", 1)[-1].lower()
    media_types = {
        "csv": "text/csv",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
    }
    return FileResponse(
        path=file_path,
        media_type=media_types.get(ext, "application/octet-stream"),
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("")
async def list_reports(
    framework_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Return metadata for all previously generated compliance reports."""
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    query = {"tenantId": tenant_id}
    if framework_id:
        query["frameworkId"] = framework_id
    reports = await db.compliance_reports.find(query, {"_id": 0}).sort("generatedAt", -1).to_list(length=200)
    return reports


# ── Internal helper ───────────────────────────────────────────────────────────

async def _persist_report_meta(result: dict, framework_id: str, tenant_id: str, fmt: str, user: TokenData):
    """Store report metadata in MongoDB so the list endpoint can return it."""
    try:
        db = get_database()
        doc = {
            "id": str(uuid.uuid4()),
            "frameworkId": framework_id,
            "tenantId": tenant_id,
            "format": fmt,
            "filename": result.get("filename"),
            "url": result.get("url"),
            "rowCount": result.get("rowCount", 0),
            "generatedAt": result.get("generatedAt", datetime.now(timezone.utc).isoformat()),
            "generatedBy": getattr(user, "username", "system"),
        }
        await db.compliance_reports.insert_one(doc)
    except Exception:
        pass  # Metadata persistence is best-effort; don't fail the report generation
