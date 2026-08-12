"""ITAM CSV import/export routes (Phase 65 Plan 03, ITAM-DAT-03).

Both routes route safety through code that already exists rather than
reimplementing it:
  - customFields validation reuses `itam_catalog_service.collect_field_defs`
    + `validate_custom_field_values`, the identical pair
    `itam_asset_endpoints.create_manual_asset` calls (T-65-03-03).
  - document assembly reuses `itam_asset_endpoints.build_asset_document` and
    `next_asset_tag`, the same helpers the manual-create route uses.
  - every query runs through the tenant-isolated `get_database()` wrapper,
    never a raw internal database handle (T-65-03-04).
  - both routes depend on `_require_itam_admin`, imported from
    `itam_asset_endpoints` rather than a new gate (T-65-03-05).

Task 1 wired the export half. Task 2 (this addition) adds `POST /import`.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from auth_types import TokenData
from cache_service import invalidate_cache
from database import get_database
from itam_asset_endpoints import _require_itam_admin, build_asset_document, next_asset_tag
from itam_audit_service import log_itam_action
from itam_catalog_service import collect_field_defs, validate_custom_field_values
from itam_data_service import (
    MAX_IMPORT_BYTES,
    MAX_IMPORT_ROWS,
    generate_assets_csv,
    parse_csv_rows,
    row_to_asset_payload,
)
from itam_models import ManualAssetCreate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/itam/data", tags=["ITAM Data"])

# Bounds a single export response — a separate, independent cap from the
# import side's MAX_IMPORT_ROWS.
MAX_EXPORT_ROWS = 10000

# Caps the size of the per-row error report returned from an import.
MAX_IMPORT_ERRORS = 100

_READ_CHUNK_SIZE = 65536  # 64 KiB


@router.get("/export")
async def export_assets(
    entity: str = Query("assets"),
    modelId: Optional[str] = Query(None),
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Export the tenant's asset inventory to CSV.

    `entity` is reserved for future entity types; only `"assets"` is
    supported today. The query runs through `get_database()` — the
    tenant-isolated wrapper — never a raw internal database handle, so an
    export can never carry another tenant's rows (T-65-03-04).
    """
    if entity != "assets":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported entity for export. Only 'assets' is supported.",
        )

    db = get_database()
    query: Dict[str, Any] = {"modelId": modelId} if modelId else {}
    assets = await db.assets.find(query, {"_id": 0}).limit(MAX_EXPORT_ROWS).to_list(length=MAX_EXPORT_ROWS)

    if modelId:
        model_doc = await db.asset_models.find_one({"id": modelId})
        custom_field_keys = sorted(collect_field_defs(model_doc or {}).keys())
    else:
        keys = set()
        for asset in assets:
            keys.update((asset.get("customFields") or {}).keys())
        custom_field_keys = sorted(keys)

    csv_text = generate_assets_csv(assets, custom_field_keys)
    filename = f"itam-assets-{datetime.now(timezone.utc).date().isoformat()}.csv"

    await log_itam_action(
        current_user,
        action="itam_export.assets",
        resource_type="itam_export",
        resource_id="assets",
        details=f"Exported {len(assets)} assets",
    )

    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def import_assets(
    file: UploadFile = File(...),
    dryRun: bool = Query(False),
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Import assets from an uploaded CSV.

    Reads the upload in bounded chunks (T-65-03-02: never a bare
    `await file.read()`), validates every row through the same
    `ManualAssetCreate` + `collect_field_defs`/`validate_custom_field_values`
    pair the manual-create route uses (T-65-03-03), and writes nothing when
    `dryRun` is true.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant ID not found for the current user.",
        )

    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .csv files are supported.")

    buf = bytearray()
    while chunk := await file.read(_READ_CHUNK_SIZE):
        buf.extend(chunk)
        if len(buf) > MAX_IMPORT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Upload exceeds the {MAX_IMPORT_BYTES}-byte limit.",
            )

    text = bytes(buf).decode("utf-8", errors="replace")
    rows = parse_csv_rows(text)
    if len(rows) > MAX_IMPORT_ROWS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Upload exceeds the {MAX_IMPORT_ROWS}-row limit.",
        )

    db = get_database()
    model_cache: Dict[str, Optional[dict]] = {}
    created = 0
    skipped = 0
    errors: List[Dict[str, Any]] = []
    batch_id = f"import-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    for idx, row in enumerate(rows, start=1):
        payload_dict, coercion_problems = row_to_asset_payload(row)
        problems: List[str] = list(coercion_problems)

        validated: Optional[ManualAssetCreate] = None
        try:
            validated = ManualAssetCreate(**payload_dict)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(part) for part in err.get("loc", ())) or "payload"
                problems.append(f"{loc}: {err.get('msg')}")

        if validated is not None and validated.modelId:
            if validated.modelId not in model_cache:
                model_cache[validated.modelId] = await db.asset_models.find_one({"id": validated.modelId})
            model_doc = model_cache[validated.modelId]
            if not model_doc:
                problems.append(f"modelId '{validated.modelId}' not found.")
            else:
                problems.extend(validate_custom_field_values(collect_field_defs(model_doc), validated.customFields))

        asset_tag = None
        if validated is not None and not problems:
            asset_tag = validated.assetTag
            if asset_tag:
                existing = await db.assets.find_one({"assetTag": asset_tag})
                if existing:
                    problems.append(f"Asset with tag '{asset_tag}' already exists in this tenant.")

        if problems:
            skipped += 1
            if len(errors) < MAX_IMPORT_ERRORS:
                errors.append({"row": idx, "problems": problems})
            continue

        if not dryRun:
            resolved_tag = asset_tag or await next_asset_tag(db, tenant_id)
            document = build_asset_document(validated, tenant_id, resolved_tag, now)
            try:
                await db.assets.insert_one(document)
            except DuplicateKeyError:
                skipped += 1
                if len(errors) < MAX_IMPORT_ERRORS:
                    errors.append(
                        {"row": idx, "problems": [f"Asset with tag '{resolved_tag}' already exists in this tenant."]}
                    )
                continue
            await log_itam_action(
                current_user,
                action="itam_asset.create",
                resource_type="itam_asset",
                resource_id=document["id"],
                details=f"Created via CSV import {batch_id}",
            )
        created += 1

    if not dryRun:
        if created > 0:
            invalidate_cache("assets:*")
        await log_itam_action(
            current_user,
            action="itam_import.assets",
            resource_type="itam_import",
            resource_id=batch_id,
            details=f"Imported {created} assets, skipped {skipped}",
        )

    return {
        "created": created,
        "skipped": skipped,
        "dryRun": dryRun,
        "errors": errors,
        "errorsTruncated": skipped > len(errors),
    }
