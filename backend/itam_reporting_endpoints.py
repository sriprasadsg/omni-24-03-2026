"""ITAM Reporting Endpoints (Phase 72, ITAM-REP-02/03).

Structural clone of compliance_report_endpoints.py: a pre-built-report
list/run/export route trio plus a tenant-safe download route. Every route
carries Depends(_require_itam_admin) — imported (not redefined) from
itam_asset_endpoints.py per D-07/RESEARCH Pitfall 1, the same admin gate
every other itam_*_endpoints.py router uses.
"""
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from auth_types import TokenData
from database import get_database
from itam_asset_endpoints import _require_itam_admin
from itam_reporting_prebuilt import list_prebuilt_reports
from itam_reporting_service import (
    RENDERERS,
    _REPORTS_DIR,
    _ensure_reports_dir,
    build_report_rows,
    itam_reporting_service,
)

router = APIRouter(prefix="/api/itam/reports", tags=["ITAM Reports"])

# Mirrors compliance_report_endpoints.download_report's exemption set verbatim
# — a platform super-admin may download any tenant's report file.
_SUPER_ADMIN_ROLES = {"Super Admin", "super_admin", "superadmin", "platform-admin"}


@router.get("")
async def list_reports(current_user: TokenData = Depends(_require_itam_admin)):
    """The pre-built section's card list — fixed, code-defined metadata,
    never a database read (D-09)."""
    return list_prebuilt_reports()


@router.post("/prebuilt/{report_key}/run")
async def run_prebuilt_report(
    report_key: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: TokenData = Depends(_require_itam_admin),
):
    """On-screen paginated preview (D-06). Builds the full row set with
    limit=None and slices the page in Python, so the preview and the export
    (below) always run the exact same underlying query — the D-20 guarantee.
    """
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    try:
        report = await build_report_rows(db, "prebuilt", report_key, tenant_id, limit=None)
    except ValueError:
        raise HTTPException(status_code=404, detail="Report not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")

    all_rows = report["rows"]
    row_count = report["rowCount"]
    total_pages = max(1, (row_count + page_size - 1) // page_size)
    start = (page - 1) * page_size
    page_rows = all_rows[start:start + page_size]

    return {
        "key": report["key"],
        "title": report["title"],
        "columns": report["columns"],
        "rows": page_rows,
        "rowCount": row_count,
        "page": page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "truncated": report["truncated"],
    }


@router.post("/prebuilt/{report_key}/export")
async def export_prebuilt_report(
    report_key: str,
    format: str = Query("csv"),
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Format is validated against RENDERERS up front (never a hardcoded
    literal tuple) so an unregistered format is unambiguously a 400,
    distinct from a 404 unknown report key raised further down inside
    itam_reporting_service.generate."""
    if format not in RENDERERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported export format '{format}'. Available formats: {sorted(RENDERERS.keys())}",
        )
    _ensure_reports_dir()
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    try:
        result = await itam_reporting_service.generate(
            kind="prebuilt",
            key=report_key,
            fmt=format,
            tenant_id=tenant_id,
            username=getattr(current_user, "username", "system"),
            db=db,
        )
        return result
    except ValueError:
        raise HTTPException(status_code=404, detail="Report not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/download/{filename}")
async def download_report(
    filename: str,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Cloned verbatim from compliance_report_endpoints.download_report
    (T-72-03/T-72-04): path-traversal-safe resolution rejected with 400
    before any filesystem read, then a tenant-ownership check against the
    persisted itam_report_exports document rejected with 403."""
    _safe_dir = Path(_REPORTS_DIR).resolve()
    _resolved = (_safe_dir / filename).resolve()
    if not str(_resolved).startswith(str(_safe_dir)):
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = str(_resolved)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Report file not found")

    caller_tenant = getattr(current_user, "tenant_id", None)
    caller_role = getattr(current_user, "role", "")
    if caller_role not in _SUPER_ADMIN_ROLES:
        db = get_database()
        report_meta = await db.itam_report_exports.find_one({"filename": filename})
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
