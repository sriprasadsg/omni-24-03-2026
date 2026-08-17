"""ITAM Reporting Endpoints (Phase 72, ITAM-REP-02/03, ITAM-REP-01).

Structural clone of compliance_report_endpoints.py: a pre-built-report
list/run/export route trio plus a tenant-safe download route. Every route
carries Depends(_require_itam_admin) — imported (not redefined) from
itam_asset_endpoints.py per D-07/RESEARCH Pitfall 1, the same admin gate
every other itam_*_endpoints.py router uses.

Plan 72-03 (ITAM-REP-01) adds the custom report builder's routes below the
pre-built trio: GET /fields (the field catalogue), POST /custom (save),
GET /custom (list, tenant-shared per D-04), POST /custom/preview (unsaved
run), GET/DELETE /custom/{report_id}, POST /custom/{report_id}/run, and
POST /custom/{report_id}/export. The literal-segment routes ("/fields",
"/custom", "/custom/preview") are declared before the parameterised
"/custom/{report_id}" route so path matching is unambiguous — the same
literal-before-parameterised hazard itam_lifecycle_endpoints.py documents
for its own routes.
"""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from auth_types import TokenData
from database import get_database
from itam_asset_endpoints import _require_itam_admin
from itam_reporting_filters import CustomReportDefinition, list_report_fields
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
    try:
        _resolved.relative_to(_safe_dir)
    except ValueError:
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


# ── Custom report builder routes (Plan 72-03, ITAM-REP-01) ────────────────
#
# Declared in this order — the literal segments ("/fields", "/custom",
# "/custom/preview") must be registered before the parameterised
# "/custom/{report_id}" route, or "/custom/preview" would resolve as a
# report id.

def _paginate(report: Dict[str, Any], page: int, page_size: int) -> Dict[str, Any]:
    """Shared pagination envelope for /custom/preview and
    /custom/{report_id}/run — both build the full row set with limit=None
    and slice the page in Python here, so preview and export (which calls
    generate() with no limit) always run the exact same underlying query
    (the D-20 guarantee, mirrored from run_prebuilt_report's own route)."""
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


@router.get("/fields")
async def get_report_fields(current_user: TokenData = Depends(_require_itam_admin)):
    """The closed field allowlist the builder's picker renders and the
    filter translator validates against — the picker can never offer a
    field the backend would refuse (T-72-07)."""
    return list_report_fields()


@router.post("/custom", status_code=201)
async def create_custom_report(
    payload: CustomReportDefinition,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Saves a report definition. No name-uniqueness check and no
    per-tenant count check — D-04 shares definitions tenant-wide and D-05
    sets no cap, so two saves with an identical name both succeed and both
    appear in the list with distinct ids."""
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    doc = {
        "id": f"rpt-{uuid.uuid4().hex[:8]}",
        "tenantId": tenant_id,
        "name": payload.name,
        "columns": payload.columns,
        "filters": [f.model_dump() for f in payload.filters],
        "createdAt": now,
        "createdBy": getattr(current_user, "username", "system"),
    }
    await db.itam_reports.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/custom")
async def list_custom_reports(current_user: TokenData = Depends(_require_itam_admin)):
    """Lists the tenant's saved definitions, newest first — visible to and
    re-runnable by any user in the tenant with builder access, not only
    their creator (D-04)."""
    db = get_database()
    docs = await db.itam_reports.find({}, {"_id": 0}).to_list(length=None)
    docs.sort(key=lambda d: d.get("createdAt") or "", reverse=True)
    return docs


@router.post("/custom/preview")
async def preview_custom_report(
    payload: CustomReportDefinition,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Runs an unsaved definition and returns a page of rows — the payload
    is already validated against the closed field/operator vocabulary by
    CustomReportDefinition/FilterCondition before this handler runs."""
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    report = await build_report_rows(
        db, "custom", "preview", tenant_id, definition=payload.model_dump(), limit=None,
    )
    return _paginate(report, page, page_size)


@router.get("/custom/{report_id}")
async def get_custom_report(
    report_id: str,
    current_user: TokenData = Depends(_require_itam_admin),
):
    db = get_database()
    doc = await db.itam_reports.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    return doc


@router.delete("/custom/{report_id}", status_code=204)
async def delete_custom_report(
    report_id: str,
    current_user: TokenData = Depends(_require_itam_admin),
):
    db = get_database()
    result = await db.itam_reports.delete_one({"id": report_id})
    if getattr(result, "deleted_count", 0) == 0:
        raise HTTPException(status_code=404, detail="Report not found")


@router.post("/custom/{report_id}/run")
async def run_saved_custom_report(
    report_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Loading the definition first means a run-after-delete is a plain 404
    — the same answer an unknown id would ever produce, not a crash or a
    stale result."""
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    doc = await db.itam_reports.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    try:
        report = await build_report_rows(db, "custom", report_id, tenant_id, definition=doc, limit=None)
    except ValueError:
        raise HTTPException(status_code=404, detail="Report not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    return _paginate(report, page, page_size)


@router.post("/custom/{report_id}/export")
async def export_custom_report(
    report_id: str,
    format: str = Query("csv"),
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Exports the full matching row set (no limit), never just the preview
    page — calls the same RENDERERS registry pre-built reports use, so a
    format registered once is available to both (D-14/D-20)."""
    if format not in RENDERERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported export format '{format}'. Available formats: {sorted(RENDERERS.keys())}",
        )
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    doc = await db.itam_reports.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    _ensure_reports_dir()
    try:
        result = await itam_reporting_service.generate(
            kind="custom",
            key=report_id,
            fmt=format,
            tenant_id=tenant_id,
            username=getattr(current_user, "username", "system"),
            definition=doc,
            db=db,
        )
        return result
    except ValueError:
        raise HTTPException(status_code=404, detail="Report not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
