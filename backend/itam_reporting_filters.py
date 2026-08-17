"""ITAM Custom Report Builder — closed-vocabulary filter translator and
asset-rooted query engine (Phase 72, Plan 03, ITAM-REP-01).

This module is the one subsystem in Phase 72 with no in-codebase analog
(RESEARCH.md/PATTERNS.md both flag it). It owns three things:

  - FIELD_CATALOG — an ordered, closed allowlist of selectable/filterable
    fields (D-01: every custom report is rooted in the assets collection;
    licence/component/consumable/finance data joins onto asset rows and
    never forms its own report root). Deliberately excludes productKey, the
    raw customFields mapping, tenantId and _id (T-72-07).
  - FilterCondition / CustomReportDefinition — Pydantic models that reject a
    field outside FIELD_CATALOG or an operator outside that field's type
    family before any database call (T-72-01).
  - _filters_to_mongo_query — translates asset-level conditions into a hand
    written Mongo fragment (never a client-supplied query string); every
    user value that reaches a regex passes through re.escape first, so a
    'contains'/'equals' value is always matched literally.
  - run_custom_report — the asset-rooted query + Python-side joins (never an
    aggregation sub-pipeline, per RESEARCH Pitfall 4 / T-72-02) that builds
    the report row set.

The comparison semantics used to build the Mongo fragment above and the
semantics used to re-verify every row in Python (_condition_passes) are the
same operator table, so the two paths cannot diverge.
"""
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from itam_finance_service import (
    compute_book_value,
    compute_warranty_status,
    get_warranty_alert_window,
)

_EM_DASH = "—"


def _dash(value: Any) -> Any:
    """Renders a None field as an em dash rather than a blank cell."""
    return value if value is not None else _EM_DASH


# ── Field catalogue (D-01, T-72-07) ─────────────────────────────────────────
#
# Every entry carries key (wire name), label (display header), entity (one
# of asset/finance/license/component/consumable), type (text/date/number/
# enum), and source (how the value is resolved — the real document field
# name for `asset` entries, the itam_finance_service result key for
# `finance`, the joined document's own field name for license/component/
# consumable). Deliberately excludes productKey, customFields, tenantId, _id.
FIELD_CATALOG: List[Dict[str, Any]] = [
    # Asset — direct fields on the assets collection.
    {"key": "asset.assetTag", "label": "Asset Tag", "entity": "asset", "type": "text", "source": "assetTag"},
    {"key": "asset.name", "label": "Name", "entity": "asset", "type": "text", "source": "name"},
    {"key": "asset.serialNumber", "label": "Serial Number", "entity": "asset", "type": "text", "source": "serialNumber"},
    {"key": "asset.type", "label": "Type", "entity": "asset", "type": "text", "source": "type"},
    {"key": "asset.lifecycleStatus", "label": "Lifecycle Status", "entity": "asset", "type": "enum", "source": "lifecycleStatus"},
    {"key": "asset.manufacturerId", "label": "Manufacturer Id", "entity": "asset", "type": "text", "source": "manufacturerId"},
    {"key": "asset.modelId", "label": "Model Id", "entity": "asset", "type": "text", "source": "modelId"},
    {"key": "asset.categoryId", "label": "Category Id", "entity": "asset", "type": "text", "source": "categoryId"},
    {"key": "asset.supplierId", "label": "Supplier Id", "entity": "asset", "type": "text", "source": "supplierId"},
    {"key": "asset.locationId", "label": "Location Id", "entity": "asset", "type": "text", "source": "locationId"},
    {"key": "asset.poNumber", "label": "PO Number", "entity": "asset", "type": "text", "source": "poNumber"},
    {"key": "asset.purchaseDate", "label": "Purchase Date", "entity": "asset", "type": "date", "source": "purchaseDate"},
    {"key": "asset.purchaseCostCents", "label": "Purchase Cost (cents)", "entity": "asset", "type": "number", "source": "purchaseCostCents"},
    {"key": "asset.warrantyMonths", "label": "Warranty Months", "entity": "asset", "type": "number", "source": "warrantyMonths"},
    {"key": "asset.notes", "label": "Notes", "entity": "asset", "type": "text", "source": "notes"},
    {"key": "asset.createdAt", "label": "Created At", "entity": "asset", "type": "date", "source": "createdAt"},
    {"key": "asset.updatedAt", "label": "Updated At", "entity": "asset", "type": "date", "source": "updatedAt"},
    # Finance — computed at read time via itam_finance_service, never stored.
    {"key": "finance.bookValueCents", "label": "Book Value (cents)", "entity": "finance", "type": "number", "source": "bookValueCents"},
    {"key": "finance.warrantyStatus", "label": "Warranty Status", "entity": "finance", "type": "enum", "source": "warrantyStatus"},
    {"key": "finance.warrantyExpiresAt", "label": "Warranty Expires", "entity": "finance", "type": "date", "source": "warrantyExpiresAt"},
    {"key": "finance.daysToExpiry", "label": "Days To Expiry", "entity": "finance", "type": "number", "source": "daysToExpiry"},
    # License — joined via license_assignments (targetType == "asset") -> licenses.
    {"key": "license.name", "label": "License", "entity": "license", "type": "text", "source": "name"},
    {"key": "license.seatCount", "label": "License Seat Count", "entity": "license", "type": "number", "source": "seatCount"},
    {"key": "license.expiryDate", "label": "License Expiry", "entity": "license", "type": "date", "source": "expiryDate"},
    # Component — joined via components.parentAssetId (the real attach/detach
    # field itam_component_service.py writes).
    {"key": "component.name", "label": "Component", "entity": "component", "type": "text", "source": "name"},
    {"key": "component.type", "label": "Component Type", "entity": "component", "type": "text", "source": "type"},
    {"key": "component.serialNumber", "label": "Component Serial", "entity": "component", "type": "text", "source": "serialNumber"},
    # Consumable — joined via itam_consumables.checkoutRecords (assignedToType == "asset").
    {"key": "consumable.name", "label": "Consumable", "entity": "consumable", "type": "text", "source": "name"},
    {"key": "consumable.checkedOutQuantity", "label": "Checked-Out Quantity", "entity": "consumable", "type": "number", "source": "checkedOutQuantity"},
]

_FIELD_CATALOG_BY_KEY: Dict[str, Dict[str, Any]] = {f["key"]: f for f in FIELD_CATALOG}

# Closed operator vocabulary per field type — the only families a
# FilterCondition may combine.
_OPERATORS_BY_TYPE: Dict[str, set] = {
    "text": {"equals", "contains"},
    "date": {"before", "after", "between"},
    "number": {"gt", "lt", "between"},
    "enum": {"equals"},
}


def list_report_fields() -> List[Dict[str, Any]]:
    """The field catalogue exposed to the picker — strips `source` (internal
    resolution detail) so the picker never sees more than a display-safe
    allowlist (T-72-07)."""
    return [{k: v for k, v in entry.items() if k != "source"} for entry in FIELD_CATALOG]


# ── Request models (T-72-01) ────────────────────────────────────────────────

class FilterCondition(BaseModel):
    """A single closed-vocabulary filter condition. `field` must name a key
    present in FIELD_CATALOG and `operator` must belong to that field's type
    family — both are rejected here, before any database call, so a
    client-supplied query fragment never reaches run_custom_report."""

    field: str
    operator: Literal["equals", "contains", "before", "after", "between", "gt", "lt"]
    value: Any = None
    value2: Any = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("field")
    @classmethod
    def _field_must_be_in_catalog(cls, v: str) -> str:
        if v not in _FIELD_CATALOG_BY_KEY:
            raise ValueError(f"Unknown report field: {v!r}")
        return v

    @model_validator(mode="after")
    def _operator_must_match_field_type(self) -> "FilterCondition":
        entry = _FIELD_CATALOG_BY_KEY.get(self.field)
        if entry is None:
            return self  # already rejected by the field validator above
        allowed = _OPERATORS_BY_TYPE[entry["type"]]
        if self.operator not in allowed:
            raise ValueError(
                f"Operator {self.operator!r} is not valid for field {self.field!r} "
                f"(type {entry['type']!r} allows: {sorted(allowed)})"
            )
        if self.operator == "between" and self.value2 is None:
            raise ValueError("'between' requires both value and value2")
        return self


class CustomReportDefinition(BaseModel):
    """A saved or unsaved custom report request: a set of columns (at least
    one) plus zero or more filter conditions (D-01's zero-filters-runs-
    unfiltered truth)."""

    name: str = Field(min_length=1, max_length=120)
    columns: List[str] = Field(min_length=1)
    filters: List[FilterCondition] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("columns")
    @classmethod
    def _columns_must_be_in_catalog(cls, v: List[str]) -> List[str]:
        unknown = [c for c in v if c not in _FIELD_CATALOG_BY_KEY]
        if unknown:
            raise ValueError(f"Unknown report column(s): {unknown}")
        return v


# ── Mongo fragment builder (asset-level conditions only) ──────────────────

def _filters_to_mongo_query(conditions: List[FilterCondition]) -> Dict[str, Any]:
    """Translates asset-level filter conditions into a hand-written Mongo
    query fragment. The caller (run_custom_report) only ever passes
    conditions whose FIELD_CATALOG entity is 'asset' — a computed/joined
    condition has no real collection field to filter on at this layer and is
    re-applied in Python instead. Every user-supplied string that reaches a
    regex passes through re.escape first, so a value is always matched
    literally, never as a pattern (T-72-01). Multiple conditions AND
    together at the top level."""
    clauses: List[Dict[str, Any]] = []
    for cond in conditions:
        entry = _FIELD_CATALOG_BY_KEY[cond.field]
        mongo_field = entry["source"]
        op = cond.operator
        if op == "equals":
            clauses.append({mongo_field: {"$regex": f"^{re.escape(str(cond.value))}$", "$options": "i"}})
        elif op == "contains":
            clauses.append({mongo_field: {"$regex": re.escape(str(cond.value)), "$options": "i"}})
        elif op == "gt":
            clauses.append({mongo_field: {"$gt": cond.value}})
        elif op == "lt":
            clauses.append({mongo_field: {"$lt": cond.value}})
        elif op == "before":
            clauses.append({mongo_field: {"$lt": cond.value}})
        elif op == "after":
            clauses.append({mongo_field: {"$gt": cond.value}})
        elif op == "between":
            lo, hi = cond.value, cond.value2
            if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo > hi:
                lo, hi = hi, lo
            elif isinstance(lo, str) and isinstance(hi, str) and lo > hi:
                lo, hi = hi, lo
            clauses.append({mongo_field: {"$gte": lo, "$lte": hi}})
        else:  # pragma: no cover — unreachable, Literal already restricts operator
            raise ValueError(f"Unsupported operator: {op!r}")
    if not clauses:
        return {}
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


# ── Shared comparison helper (Mongo path and Python path cannot diverge) ──

def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _condition_passes(field_type: str, operator: str, actual: Any, value: Any, value2: Any) -> bool:
    """Single source of truth for filter comparison semantics — reused by
    run_custom_report's Python-side re-verification pass so the rows the
    caller actually receives always agree with the operator table
    _filters_to_mongo_query encodes above (T-72-01). A missing (None) actual
    value never satisfies any condition. gt/lt/before/after are strict;
    between is inclusive on both ends, so min == max returns exact matches
    rather than an empty set."""
    if actual is None:
        return False

    if field_type in ("text", "enum"):
        if operator == "equals":
            return str(actual).lower() == str(value).lower()
        if operator == "contains":
            return str(value).lower() in str(actual).lower()
        raise ValueError(f"Unsupported operator {operator!r} for field type {field_type!r}")

    if field_type == "number":
        if operator == "gt":
            return actual > value
        if operator == "lt":
            return actual < value
        if operator == "between":
            lo, hi = (value, value2) if value <= value2 else (value2, value)
            return lo <= actual <= hi
        raise ValueError(f"Unsupported operator {operator!r} for field type {field_type!r}")

    if field_type == "date":
        actual_dt = _parse_dt(actual)
        if operator == "before":
            return actual_dt < _parse_dt(value)
        if operator == "after":
            return actual_dt > _parse_dt(value)
        if operator == "between":
            lo_dt, hi_dt = _parse_dt(value), _parse_dt(value2)
            if lo_dt > hi_dt:
                lo_dt, hi_dt = hi_dt, lo_dt
            return lo_dt <= actual_dt <= hi_dt
        raise ValueError(f"Unsupported operator {operator!r} for field type {field_type!r}")

    raise ValueError(f"Unsupported field type: {field_type!r}")  # pragma: no cover


# ── Finance + join resolution ──────────────────────────────────────────────

def _compute_finance_result(
    asset: Dict[str, Any], models_by_id: Dict[str, Dict[str, Any]], now: datetime, window_days: int,
) -> Dict[str, Any]:
    """Book value and warranty status computed exclusively via
    itam_finance_service.compute_book_value/compute_warranty_status — this
    report never re-derives either computation itself (must_haves truth)."""
    result: Dict[str, Any] = {
        "bookValueCents": None, "warrantyStatus": None,
        "warrantyExpiresAt": None, "daysToExpiry": None,
    }
    model_doc = models_by_id.get(asset.get("modelId"))
    if (
        model_doc
        and model_doc.get("usefulLifeYears") is not None
        and model_doc.get("salvageValueCents") is not None
        and asset.get("purchaseCostCents") is not None
        and asset.get("purchaseDate")
    ):
        try:
            book_value = compute_book_value(
                purchase_date=asset["purchaseDate"],
                purchase_cost_cents=asset["purchaseCostCents"],
                useful_life_years=model_doc["usefulLifeYears"],
                salvage_value_cents=model_doc["salvageValueCents"],
                now=now,
            )
            result["bookValueCents"] = book_value["bookValueCents"]
        except ValueError:
            pass

    warranty = compute_warranty_status(
        asset.get("purchaseDate"), asset.get("warrantyMonths"), now, window_days,
    )
    result["warrantyStatus"] = warranty["warrantyStatus"]
    result["warrantyExpiresAt"] = warranty["warrantyExpiresAt"]
    result["daysToExpiry"] = warranty["daysToExpiry"]
    return result


def _resolve_fields(
    asset: Dict[str, Any],
    finance_result: Dict[str, Any],
    license_by_asset_id: Dict[str, Dict[str, Any]],
    components_by_asset_id: Dict[str, Dict[str, Any]],
    consumables_by_asset_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Maps every FIELD_CATALOG key to this asset's resolved value, before
    column projection or filter evaluation — the one row shape both the
    filter pass and the column projection read from."""
    asset_id = asset.get("id")
    lic = license_by_asset_id.get(asset_id)
    comp = components_by_asset_id.get(asset_id)
    con = consumables_by_asset_id.get(asset_id)

    resolved: Dict[str, Any] = {}
    for entry in FIELD_CATALOG:
        entity, source, key = entry["entity"], entry["source"], entry["key"]
        if entity == "asset":
            resolved[key] = asset.get(source)
        elif entity == "finance":
            resolved[key] = finance_result.get(source)
        elif entity == "license":
            resolved[key] = lic.get(source) if lic else None
        elif entity == "component":
            resolved[key] = comp.get(source) if comp else None
        elif entity == "consumable":
            resolved[key] = con.get(source) if con else None
    return resolved


# ── Report runner (D-01, T-72-02) ──────────────────────────────────────────

async def run_custom_report(
    db,
    definition: Union[Dict[str, Any], CustomReportDefinition],
    tenant_id: Optional[str],
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Runs a closed-vocabulary custom report definition against db.assets,
    asset-rooted per D-01. Raises a Pydantic ValidationError (via
    CustomReportDefinition's own field/operator validators) before any
    database call when the definition names an unknown field, column or
    operator.

    Joins are performed as separate batched, tenant-isolated `find` calls
    merged in Python — never a Mongo aggregation with a sub-pipeline, since
    TenantIsolatedCollection.aggregate only tenant-scopes the top-level match
    (RESEARCH Pitfall 4 / T-72-02).

    `db` may be a request-scoped tenant-isolated handle or (for symmetry
    with itam_finance_service's own convention) a raw handle — every read
    below goes through `db.<collection>.find(...)`, so tenant scoping is
    supplied entirely by the caller's handle, never resolved here.
    """
    if isinstance(definition, CustomReportDefinition):
        parsed = definition
        report_id: Optional[str] = None
        report_name: Optional[str] = definition.name
    else:
        raw = dict(definition or {})
        report_id = raw.get("id")
        report_name = raw.get("name")
        parsed = CustomReportDefinition(
            name=raw.get("name") or "Custom Report",
            columns=raw.get("columns", []),
            filters=raw.get("filters", []),
        )

    conditions = parsed.filters
    asset_conditions = [c for c in conditions if _FIELD_CATALOG_BY_KEY[c.field]["entity"] == "asset"]

    mongo_query = _filters_to_mongo_query(asset_conditions)
    assets = await db.assets.find(mongo_query, {"_id": 0}).to_list(length=None)

    asset_ids = sorted({a["id"] for a in assets if a.get("id")})

    # Licence join: license_assignments (targetType == "asset") -> licenses.
    assignments: List[Dict[str, Any]] = []
    if asset_ids:
        assignments = await db.license_assignments.find(
            {"targetType": "asset", "targetId": {"$in": asset_ids}}, {"_id": 0},
        ).to_list(length=None)
    license_ids = sorted({a["licenseId"] for a in assignments if a.get("licenseId")})
    licenses_by_id: Dict[str, Dict[str, Any]] = {}
    if license_ids:
        license_docs = await db.licenses.find(
            {"id": {"$in": license_ids}}, {"_id": 0},
        ).to_list(length=None)
        licenses_by_id = {lic["id"]: lic for lic in license_docs}
    license_by_asset_id: Dict[str, Dict[str, Any]] = {}
    for a in assignments:
        target_id = a.get("targetId")
        lic = licenses_by_id.get(a.get("licenseId"))
        if target_id and lic and target_id not in license_by_asset_id:
            license_by_asset_id[target_id] = lic

    # Component join: components.parentAssetId — the real attach/detach
    # field itam_component_service.py writes (not the unused
    # ComponentCreate.assetIds request field).
    components_by_asset_id: Dict[str, Dict[str, Any]] = {}
    if asset_ids:
        component_docs = await db.components.find(
            {"parentAssetId": {"$in": asset_ids}}, {"_id": 0},
        ).to_list(length=None)
        for comp in component_docs:
            parent = comp.get("parentAssetId")
            if parent and parent not in components_by_asset_id:
                components_by_asset_id[parent] = comp

    # Consumable join: checkoutRecords is embedded on each consumable doc —
    # reads every tenant-scoped consumable once, then filters in Python for
    # assignedToType == "asset" records naming one of this run's assets.
    consumables_by_asset_id: Dict[str, Dict[str, Any]] = {}
    if asset_ids:
        consumable_docs = await db.itam_consumables.find({}, {"_id": 0}).to_list(length=None)
        for con in consumable_docs:
            for rec in con.get("checkoutRecords") or []:
                if rec.get("assignedToType") != "asset":
                    continue
                target_asset = rec.get("assignedTo")
                if target_asset in asset_ids and target_asset not in consumables_by_asset_id:
                    consumables_by_asset_id[target_asset] = {
                        "name": con.get("name"),
                        "checkedOutQuantity": rec.get("quantity"),
                    }

    # asset_models join for depreciation policy inputs.
    model_ids = sorted({a["modelId"] for a in assets if a.get("modelId")})
    models_by_id: Dict[str, Dict[str, Any]] = {}
    if model_ids:
        model_docs = await db.asset_models.find(
            {"id": {"$in": model_ids}}, {"_id": 0},
        ).to_list(length=None)
        models_by_id = {m["id"]: m for m in model_docs}

    now = datetime.now(timezone.utc)
    window_days = await get_warranty_alert_window(db, tenant_id)

    resolved_rows: List[Dict[str, Any]] = []
    for asset in assets:
        finance_result = _compute_finance_result(asset, models_by_id, now, window_days)
        resolved_rows.append(
            _resolve_fields(
                asset, finance_result, license_by_asset_id,
                components_by_asset_id, consumables_by_asset_id,
            )
        )

    # Re-verify every condition (asset-level and computed/joined alike)
    # against the fully resolved row. The Mongo query above only narrows the
    # asset-level subset for real-database scale; this pass — using the
    # identical operator semantics _filters_to_mongo_query encodes — is what
    # guarantees the rows returned actually satisfy the whole definition.
    filtered_rows: List[Dict[str, Any]] = []
    for resolved in resolved_rows:
        if all(
            _condition_passes(
                _FIELD_CATALOG_BY_KEY[cond.field]["type"], cond.operator,
                resolved.get(cond.field), cond.value, cond.value2,
            )
            for cond in conditions
        ):
            filtered_rows.append(resolved)

    # Stable default sort: asset tag ascending (D-01 pagination-boundary
    # truth). Rows with no asset tag sort last rather than raising on None.
    filtered_rows.sort(key=lambda r: (r.get("asset.assetTag") is None, r.get("asset.assetTag") or ""))

    from itam_reporting_service import MAX_REPORT_ROWS

    truncated = len(filtered_rows) > MAX_REPORT_ROWS
    if truncated:
        filtered_rows = filtered_rows[:MAX_REPORT_ROWS]
    if limit is not None:
        filtered_rows = filtered_rows[:limit]

    columns = parsed.columns
    declared_columns = [_FIELD_CATALOG_BY_KEY[c]["label"] for c in columns]
    rows = [
        {_FIELD_CATALOG_BY_KEY[c]["label"]: _dash(resolved.get(c)) for c in columns}
        for resolved in filtered_rows
    ]

    return {
        "key": report_id or "custom",
        "title": report_name or "Custom Report",
        "columns": declared_columns,
        "rows": rows,
        "rowCount": len(rows),
        "truncated": truncated,
    }
