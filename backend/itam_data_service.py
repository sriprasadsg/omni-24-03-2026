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
from typing import Any, Dict, List

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
