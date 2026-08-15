# Phase 57: Lifecycle & Check-In/Out - Pattern Map

**Mapped:** 2026-08-04
**Files analyzed:** 6 (5 new, 1 modified pair)
**Analogs found:** 6 / 6

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/itam_lifecycle_endpoints.py` (checkout/checkin/audit-mark/history/overdue routes) | controller/route | request-response + CRUD (atomic transition) | `backend/itam_asset_endpoints.py` + `backend/compliance_status_endpoints.py` | exact (structure) / exact (atomic-transition logic) |
| `backend/itam_lifecycle_service.py` (optional — only if endpoints file would exceed 500 lines) | service | event-driven (append-only insert) | `backend/remediation_audit_service.py` | exact |
| `backend/itam_models.py` (extend: `CheckoutRequest`, `CheckinRequest`, `AuditMarkRequest`) | model | request-response (validation contracts) | `backend/itam_models.py` `ManualAssetCreate` (same file, same convention) | exact |
| `backend/router_registry.py` (modify: register new router) | config | request-response (route mount) | existing `_load(app, "itam_asset_endpoints", "router")` line | exact |
| `backend/database.py` (modify: add `assignment_history` indexes) | config | batch (index creation at startup) | existing `connect_to_mongo()` index-creation block | exact |
| `backend/tests/test_itam_lifecycle.py` | test | request-response (endpoint-level async tests) | `backend/tests/test_itam_foundation.py` | exact |

## Pattern Assignments

### `backend/itam_lifecycle_endpoints.py` (controller, request-response)

**Analogs:** `backend/itam_asset_endpoints.py` (router scaffolding, RBAC dependency, target-existence validation) + `backend/compliance_status_endpoints.py` (atomic guarded transition)

**Imports pattern** (`backend/itam_asset_endpoints.py` lines 1-16):
```python
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from auth_types import TokenData
from authentication_service import get_current_user
from database import get_database, TenantIsolatedDatabase
from itam_models import ManualAssetCreate, ASSET_SOURCE_MANUAL, DEFAULT_LIFECYCLE_STATUS, ASSET_TAG_PREFIX
from itam_catalog_service import collect_field_defs, validate_custom_field_values
from cache_service import invalidate_cache
from rbac_utils import verify_permission
```
For the new file, swap `itam_models` imports to the new `CheckoutRequest`/`CheckinRequest`/`AuditMarkRequest` and add `from pymongo import ReturnDocument` (already imported by the analog — reuse the same import path).

**Router + RBAC dependency pattern** (`backend/itam_asset_endpoints.py` lines 18-40):
```python
router = APIRouter(prefix="/api/assets", tags=["ITAM Assets"])

# Note: This router shares the /api/assets prefix with backend/asset_endpoints.py.
# [VERIFIED: backend/router_registry.py:82-84] actual order is
# itam_catalog_endpoints -> itam_asset_endpoints -> asset_endpoints (ITAM first).
# New routes here are all multi-segment (/{asset_id}/checkout etc.) so they never
# collide with asset_endpoints.py's single-segment GET /{asset_id} regardless of order.

async def _require_itam_admin(current_user: TokenData = Depends(get_current_user)):
    """
    Dependency to ensure the current user has 'manage:assets' permission.
    """
    if not await verify_permission(current_user, "manage:assets"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have permission to manage ITAM assets."
        )
    return current_user
```
**Import this dependency directly from `itam_asset_endpoints` rather than redefining it** (`from itam_asset_endpoints import _require_itam_admin`) — CONTEXT.md explicitly locks reuse, not reimplementation.

**Target-existence validation pattern** (`backend/itam_asset_endpoints.py` lines 82-102, catalog-reference validation on `create_manual_asset`):
```python
if payload.manufacturerId:
    if not await db.manufacturers.find_one({"id": payload.manufacturerId}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"manufacturerId '{payload.manufacturerId}' not found."
        )
```
Adapt for `CheckoutRequest.targetType`/`targetId`:
```python
if payload.targetType == "user":
    target = await db.users.find_one({"id": payload.targetId})
    if not target:
        raise HTTPException(status_code=400, detail=f"targetId '{payload.targetId}' (user) not found.")
else:
    target = await db.locations.find_one({"id": payload.targetId})
    if not target:
        raise HTTPException(status_code=400, detail=f"targetId '{payload.targetId}' (location) not found.")
```
`db.users` and `db.locations` are NOT in the `TenantIsolatedDatabase` exemption allowlist (see Shared Patterns below), so these calls are auto-tenant-scoped — no extra IDOR guard code needed.

**Core atomic-transition pattern** (`backend/compliance_status_endpoints.py` lines 69-100):
```python
now = datetime.now(timezone.utc)

# find_one_and_update returns the document as it existed *before* the
# update (return_document=BEFORE is the pymongo/motor default), making
# the previous-state capture atomic with the write itself and
# eliminating the TOCTOU window that a separate find_one()+update_one()
# pair would introduce.
prior_doc = await db.asset_compliance.find_one_and_update(
    {"assetId": asset_id, "controlId": body.control_id, "tenantId": resolved_tenant_id},
    {
        "$set": {
            "status": body.status,
            "lastUpdated": now.isoformat(),
            "manual_override": True,
            "overriddenBy": actor,
            "overriddenAt": now.isoformat(),
        },
    },
    upsert=True,
)
previous_status = prior_doc.get("status", "Unknown") if prior_doc else "Unknown"
```
Adapt for checkout (guard clause in the filter, per Pattern 1 of RESEARCH.md):
```python
prior_doc = await db.assets.find_one_and_update(
    {"id": asset_id, "lifecycleStatus": "deployable"},   # guard clause — TOCTOU-safe
    {"$set": {
        "lifecycleStatus": "deployed",
        "assignedToUserId": target_id if payload.targetType == "user" else None,
        "locationId": target_id if payload.targetType == "location" else asset_doc.get("locationId"),
        "checkedOutAt": now.isoformat(),
        "checkedOutBy": actor_user_id,
        "updatedAt": now.isoformat(),
    }},
    return_document=ReturnDocument.BEFORE,
)
if prior_doc is None:
    # Disambiguate 404 (asset missing) vs 409 (not deployable) with a
    # preceding find_one({"id": asset_id}) only for this error path.
    existing = await db.assets.find_one({"id": asset_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Asset not found")
    raise HTTPException(status_code=409, detail="Asset is not in a deployable status")
```
**Never set `assets.status`** — only `lifecycleStatus` (Pitfall 1, restated in `itam_asset_endpoints.py` line 28-29 comment).

**Error handling pattern** (`backend/itam_asset_endpoints.py` lines 141-151):
```python
try:
    await db.assets.insert_one(document)
    await invalidate_cache("assets:*")
    document.pop("_id", None)
    return document
except DuplicateKeyError:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="...")
except Exception as e:
    logger.error(f"Failed to create manual asset: {e}")
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create manual asset.")
```
Mirror this try/except shape around the `assignment_history` insert step (log-and-500 for unexpected DB errors; explicit 4xx for business-rule violations raised earlier).

**Action-endpoint route naming convention** (`backend/remediation_control_endpoints.py` lines 19, 42-43, 52-53):
```python
router = APIRouter(prefix="/api/remediation", tags=["Remediation Control"])

@router.post("/{remediation_id}/approve")
async def approve_remediation(remediation_id: str, current_user=Depends(_require_ops_permission)):
    ...

@router.post("/{remediation_id}/deny")
async def deny_remediation(remediation_id: str, ...):
    ...
```
Confirms the dedicated-action-verb-suffix route convention (`/checkout`, `/checkin`, `/audit`) over a generic `PATCH /{asset_id}` — matches the Anti-Pattern warning in RESEARCH.md.

---

### `backend/itam_lifecycle_service.py` (service, event-driven — only if needed to stay under 500 lines)

**Analog:** `backend/remediation_audit_service.py` (full file, 46 lines)

**Full append-only module pattern** (lines 1-46):
```python
"""Append-only remediation audit trail (Phase 53-03/53-04, AUTO-04).

Only `write_audit` (insert) and `list_audit` (read) are exposed — there is
no update/delete function anywhere in this module, so a record, once
written, can never be altered or removed by anything importing it.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


async def write_audit(db, tenant_id: str, record: Dict[str, Any]) -> str:
    doc = dict(record)
    doc.setdefault("tenantId", tenant_id)
    doc.setdefault("ts", datetime.now(timezone.utc).isoformat())
    result = await db.remediation_audit.insert_one(doc)
    return str(result.inserted_id)


async def list_audit(
    db,
    tenant_id: str,
    filters: Optional[Dict[str, Any]] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {"tenantId": tenant_id}
    if filters:
        query.update(filters)
    cursor = db.remediation_audit.find(query, {"_id": 0}).sort("ts", -1).limit(limit)
    return await cursor.to_list(length=limit)
```
Copy 1:1, renaming `write_audit`/`list_audit` -> `write_history`/`list_history` and `db.remediation_audit` -> `db.assignment_history`, filtered by `assetId` instead of arbitrary `filters` (per RESEARCH.md Pattern 2). Drop the OCSF/SOC push side-effect block (lines 24-30 of the analog) — that is remediation-specific, not needed for assignment history. **Do not add an update or delete function to this module** — its absence is the append-only guarantee (Pitfall 3).

---

### `backend/itam_models.py` (model, request-response — extend existing file)

**Analog:** same file, `ManualAssetCreate` (lines 74-92)

**Convention to copy:**
```python
class ManualAssetCreate(BaseModel):
    """
    Model for creating a manual ITAM asset.
    """
    name: str
    assetTag: Optional[str] = None
    ...
    lifecycleStatus: LifecycleStatus = DEFAULT_LIFECYCLE_STATUS
    customFields: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")
```
Add near the bottom of the same file, matching this exact style (plain field declarations, `Literal` for closed-set fields, `model_config = ConfigDict(extra="forbid")` on every new model):
```python
class CheckoutRequest(BaseModel):
    targetType: Literal["user", "location"]
    targetId: str
    note: Optional[str] = None
    expectedReturnDate: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class CheckinRequest(BaseModel):
    note: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class AuditMarkRequest(BaseModel):
    auditedAt: Optional[str] = None

    model_config = ConfigDict(extra="forbid")
```
`Literal` is already imported at the top of `itam_models.py` (line 9), no new import needed.

---

### `backend/router_registry.py` (config, request-response — modify)

**Analog:** existing registration lines (`backend/router_registry.py` lines 82-84):
```python
_load(app, "itam_catalog_endpoints", "router")  # ITAM Phase 56 Catalog Router
_load(app, "itam_asset_endpoints", "router")    # ITAM Phase 56 Asset Router
_load(app, "asset_endpoints",          "router")
```
Insert the new router immediately after line 83 (adjacent to `itam_asset_endpoints`, per Pitfall 4 in RESEARCH.md — do not scatter elsewhere):
```python
_load(app, "itam_lifecycle_endpoints", "router")  # ITAM Phase 57 Lifecycle Router
```

---

### `backend/database.py` (config, batch — modify `connect_to_mongo()`)

**Analog:** `TenantIsolatedDatabase`/`TenantIsolatedCollection` exemption allowlist (`backend/database.py` lines 117-150, confirmed present at lines 122-134 and mirrored in `__getitem__`):
```python
# EXEMPTION: global reference data (shared across all tenants)
if name in [
    "compliance_frameworks",
    "compliance_controls",
    "ai_governance_frameworks",
    "system_features",
    "tenants",
    "roles",
    "response_policies",
    "playbooks",
    "ip_bans",
    "crypto_inventory",
]:
    return collection
return TenantIsolatedCollection(collection)
```
`assignment_history` (and `users`, `locations`) are absent from this list — confirms they are auto-tenant-isolated by construction. **Do not add `assignment_history` to this list.**

For index creation, find the existing `tickets`-style compound-index precedent in `connect_to_mongo()` (referenced in RESEARCH.md as `tickets.create_index([("tenantId", 1), ("due_date", 1), ("status", 1)])`) and add analogous indexes:
```python
await db.assignment_history.create_index([("tenantId", 1), ("assetId", 1)])
await db.assignment_history.create_index([("tenantId", 1), ("ts", -1)])
await db.assets.create_index([("tenantId", 1), ("lastAuditedAt", 1)])
```

---

### `backend/tests/test_itam_lifecycle.py` (test, request-response)

**Analog:** `backend/tests/test_itam_foundation.py`

**Fixture pattern to reuse** (class/fixture names found at lines 24, 59, 71, 82, 118):
```python
class MockTenantIsolatedCollection:
    ...  # async _find_one, _insert_one, _count_documents, _find_one_and_update, _delete_one

class MockTenantIsolatedDatabase:
    ...

@pytest.fixture
def mock_db(): ...

@pytest.fixture(autouse=True)
def patch_get_database_globally(): ...  # patches get_database in each module's imported name

@pytest.fixture
def itam_app(): ...
```
Reuse these fixtures verbatim (import from `test_itam_foundation.py` or promote to `conftest.py` if not already present — check first per RESEARCH.md Wave 0 Gaps note before duplicating). Follow the same `@pytest.mark.asyncio` bare-decorator style (no `asyncio_mode` config, no `asyncio.run()` wrapper).

Existing test naming patterns to mirror (from `test_itam_foundation.py`): `test_manual_asset_does_not_write_agent_status_field` (line 337) is the direct analog for this phase's required `does_not_write_status` test; `test_concurrent_manual_asset_creation_gets_distinct_tags` (line 419) is the direct analog for the required concurrent-checkout race test; `test_manufacturer_cross_tenant_isolation` (line 257) is the direct analog for the required `history_tenant_isolation` test; `test_catalog_and_asset_routes_require_permission` (line 473) is the direct analog for the required `rbac` 403 tests.

---

## Shared Patterns

### RBAC gate (`manage:assets`)
**Source:** `backend/itam_asset_endpoints.py` lines 31-40 (`_require_itam_admin`)
**Apply to:** Every new route in `itam_lifecycle_endpoints.py` (`checkout`, `checkin`, `audit`, `history`, `overdue-audit`) — import the function, do not redefine it.
```python
async def _require_itam_admin(current_user: TokenData = Depends(get_current_user)):
    if not await verify_permission(current_user, "manage:assets"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have permission to manage ITAM assets.")
    return current_user
```

### Tenant isolation
**Source:** `backend/database.py` lines 110-150 (`TenantIsolatedDatabase`/`TenantIsolatedCollection`, exemption allowlist)
**Apply to:** All DB access in the new endpoints/service — `db = get_database()`; every `db.assets`, `db.users`, `db.locations`, `db.assignment_history` call is auto-scoped. Never construct a manual `tenantId` filter by hand except where the analog itself does so explicitly (e.g., resolving `resolved_tenant_id` from the asset document before an upsert, as in `compliance_status_endpoints.py` lines 56-67).

### Atomic guarded state transition
**Source:** `backend/compliance_status_endpoints.py` lines 76-88
**Apply to:** `checkout` and `checkin` handlers — bake the `lifecycleStatus` guard into the `find_one_and_update` filter; never do a separate `find_one` read followed by a conditional `update_one` (TOCTOU, Pitfall 2).

### Append-only audit trail
**Source:** `backend/remediation_audit_service.py` (full file)
**Apply to:** `assignment_history` writes from `checkout`/`checkin` handlers — insert-only two-function module contract (`write_history`/`list_history`), no update/delete function ever defined.

### Error handling / HTTPException shape
**Source:** `backend/itam_asset_endpoints.py` lines 135-151
**Apply to:** All new endpoint handlers — explicit 4xx `HTTPException` for business-rule violations (not-found, not-deployable, duplicate), `logger.error` + generic 500 `HTTPException` for unexpected exceptions in a `try/except Exception` wrapping the final DB write.

### Router registration
**Source:** `backend/router_registry.py` lines 82-84
**Apply to:** `router_registry.py` modification — insert `_load(app, "itam_lifecycle_endpoints", "router")` immediately after the `itam_asset_endpoints` line, not elsewhere in the file (Pitfall 4).

## No Analog Found

None — all 6 files/modifications have a strong in-repo analog; the phase is disciplined reuse per RESEARCH.md's own conclusion ("Three in-repo analogs cover the entire phase").

## Metadata

**Analog search scope:** `backend/` (itam_*.py, compliance_status_endpoints.py, remediation_audit_service.py, remediation_control_endpoints.py, router_registry.py, database.py, tests/test_itam_foundation.py) — scope was pre-narrowed by RESEARCH.md's own Primary Sources list, confirmed via direct Read of each file this session.
**Files scanned:** 7 (itam_asset_endpoints.py, itam_models.py, compliance_status_endpoints.py, remediation_audit_service.py, remediation_control_endpoints.py, router_registry.py, database.py) + test_itam_foundation.py fixture/test-name grep
**Pattern extraction date:** 2026-08-04
