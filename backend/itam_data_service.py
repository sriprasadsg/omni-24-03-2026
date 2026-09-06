"""ITAM CSV import/export service — pure functions, no database I/O.

Companion to `itam_catalog_service.py`'s convention: this module takes plain
dicts/lists and returns plain values so `itam_data_endpoints.py` (the only
caller) stays free of CSV-shaping logic. `ASSET_EXPORT_COLUMNS` and the
`customFields.<key>` naming convention are defined once here — the export
and import halves in `itam_data_endpoints.py` both import from this module
so the two directions of the CSV format cannot drift apart.

Format-stability note (Phase 65 Plan 03): `ASSET_EXPORT_COLUMNS` becomes an
externally-visible file format the moment an admin builds a spreadsheet or
import template against an export. Adding columns later is safe; renaming
or reordering existing ones is not.
"""
import csv
import io
from typing import Any, Dict, List, Optional, Tuple

# Base column order for an asset export. Defined once, exported, and reused
# verbatim on the import side (Task 2) so the two directions cannot drift
# apart.
ASSET_EXPORT_COLUMNS: List[str] = [
    "id",
    "assetTag",
    "name",
    "serialNumber",
    "type",
    "lifecycleStatus",
    "manufacturerId",
    "modelId",
    "categoryId",
    "supplierId",
    "locationId",
    "notes",
    "purchaseCostCents",
    "purchaseDate",
    "poNumber",
    "warrantyMonths",
    "createdAt",
    "updatedAt",
]

CUSTOM_FIELD_COLUMN_PREFIX = "customFields."

# Columns that are always server-owned and never importable — dropped from
# an uploaded row's payload rather than forwarded (Task 2), mitigating
# T-65-03-07 (an uploader supplying its own id/tenantId/assetSource/
# createdAt).
SERVER_OWNED_IMPORT_COLUMNS = frozenset({
    "id", "createdAt", "updatedAt", "tenantId", "assetSource", "lastScanned", "warrantyAlertSentAt",
})

# T-65-03-02: the upload route reads in 64 KiB chunks and aborts as soon as
# the accumulated size passes this cap — no unbounded `await file.read()`.
MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 5000

# Leading characters a spreadsheet application (Excel, Sheets, LibreOffice)
# treats as the start of a formula or an escape sequence. T-65-03-01.
_FORMULA_LEAD_CHARS = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value: Any) -> str:
    """Coerce a value to a formula-safe CSV cell string.

    `None` becomes an empty string. Any other value is coerced with `str()`.
    When the resulting text's first character would make a spreadsheet
    treat the cell as a formula or escape sequence, the text is prefixed
    with a single apostrophe so it renders as literal text instead. Every
    other value passes through byte-identical. This is the sole mitigation
    for T-65-03-01 and is applied to every exported cell, base columns
    included.
    """
    text = "" if value is None else str(value)
    if text and text[0] in _FORMULA_LEAD_CHARS:
        return f"'{text}"
    return text


def asset_to_row(asset: dict, custom_field_keys: List[str]) -> dict:
    """Project an asset document onto the export column set.

    Reads custom-field values out of `asset.get("customFields") or {}` and
    names their columns `customFields.<key>`. Every value — base and custom
    — passes through `sanitize_csv_cell` before being placed in the row.
    """
    row: Dict[str, str] = {}
    for col in ASSET_EXPORT_COLUMNS:
        row[col] = sanitize_csv_cell(asset.get(col))

    custom_fields = asset.get("customFields") or {}
    for key in custom_field_keys:
        row[f"{CUSTOM_FIELD_COLUMN_PREFIX}{key}"] = sanitize_csv_cell(custom_fields.get(key))

    return row


def generate_assets_csv(assets: List[dict], custom_field_keys: List[str]) -> str:
    """Build a complete CSV document (header + rows) for an asset export.

    Writes the header even when `assets` is empty, so an empty export is
    still a valid, self-describing file an admin can open as a template.
    """
    fieldnames = list(ASSET_EXPORT_COLUMNS) + [
        f"{CUSTOM_FIELD_COLUMN_PREFIX}{key}" for key in custom_field_keys
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for asset in assets:
        writer.writerow(asset_to_row(asset, custom_field_keys))
    return output.getvalue()


def parse_csv_rows(text: str) -> List[Dict[str, str]]:
    """Parse CSV text into row dicts, in file order."""
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def row_to_asset_payload(row: dict) -> Tuple[dict, List[str]]:
    """Split one CSV row into a `ManualAssetCreate`-shaped payload.

    Server-owned columns (`SERVER_OWNED_IMPORT_COLUMNS`) are dropped rather
    than forwarded. `customFields.<key>` columns are collected into a
    nested `customFields` dict. Any other column name is forwarded
    verbatim — including one `ManualAssetCreate` does not declare — so the
    caller's `ManualAssetCreate(**payload)` construction (whose model
    forbids extra fields) is what rejects an unknown column; this function
    invents no validation of its own for that case.

    `purchaseCostCents` and `warrantyMonths` are coerced to `int`; a
    non-integer value is reported as a problem rather than raising.

    An empty-string cell is treated as "column left blank" and omitted from
    the payload entirely, so an optional field left blank never becomes an
    empty-string value.

    Returns `(payload, problems)` — `problems` covers only integer-coercion
    failures found here; unknown-column and other structural problems are
    surfaced by the caller's `ManualAssetCreate(**payload)` construction.
    """
    problems: List[str] = []
    payload: Dict[str, Any] = {}
    custom_fields: Dict[str, Any] = {}

    for raw_key, raw_value in row.items():
        if raw_key is None:
            continue
        key = raw_key.strip()
        value: Optional[str] = raw_value.strip() if isinstance(raw_value, str) else raw_value
        if value is None or value == "":
            continue  # blank cell -> field absent, not an empty string

        if key in SERVER_OWNED_IMPORT_COLUMNS:
            continue

        if key.startswith(CUSTOM_FIELD_COLUMN_PREFIX):
            field_key = key[len(CUSTOM_FIELD_COLUMN_PREFIX):]
            custom_fields[field_key] = value
            continue

        if key in ("purchaseCostCents", "warrantyMonths"):
            try:
                payload[key] = int(value)
            except (TypeError, ValueError):
                problems.append(f"'{key}' must be an integer, got {value!r}.")
            continue

        payload[key] = value

    if custom_fields:
        payload["customFields"] = custom_fields

    return payload, problems
