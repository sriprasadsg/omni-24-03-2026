# Phase 60: Licenses & Consumables - Research

**Researched:** 2026-08-05
**Domain:** FastAPI + MongoDB (Motor) backend — polymorphic seat/quantity sub-inventory CRUD with atomic concurrency guards, cloned from Phase 57's checkout/checkin lifecycle machinery. Backend/API-only (no frontend this phase — Phase 61 is the sole frontend consumer).
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 (Architectural Independence):** This phase is architecturally independent of Phases 57-59 — different collections, same tenant-isolation/RBAC conventions. Depends only on Phase 56.

**D-02 (Assignment/Checkout History Reuse):** License seat assign/reclaim and consumable checkout both write to the same append-only history pattern Phase 57 established (`backend/itam_lifecycle_service.py`'s `write_history`/`list_history` against `db.assignment_history`) rather than inventing a second history mechanism — reuse the collection and helper functions directly if the record shape generalizes, or clone the pattern into parallel `license_history`/`consumable_history` collections only if the record shape genuinely can't be shared (research to confirm which).

**D-03 (Seat/Quantity Model):** A license has a fixed total seat count; each assignment consumes one seat (assign to either a user id or an asset id — polymorphic target, mirroring Phase 57's `CheckoutRequest` targetType/targetId pattern per that phase's PD-01 decision, not two separate optional fields). Reclaiming a seat returns it to the available pool. Over-assignment (assigning past the seat count) is rejected, not silently allowed.

**D-04 (Consumable Quantity):** A consumable has a total quantity and an available quantity; checkout decrements available by the requested amount in one atomic operation (no partial/silent-drop fulfillment — if requested > available, the whole checkout is rejected, mirroring Phase 58's "no-silent-drop bulk contract" precedent for label sheets).

**D-05 (Component Attachment):** A component references its parent asset by id (`parentAssetId`) and appears on that asset's detail view/response — not a separate top-level "components" list disconnected from the asset. Detaching a component clears the reference (component record persists, not deleted) — mirrors how Phase 57's check-in clears an assignment without deleting the asset.

### Claude's Discretion

- Exact endpoint/router file names (`itam_license_endpoints.py` vs extending an existing file) — check line counts against the 500-line CLAUDE.md limit during research before deciding. **Resolved below: three new dedicated router files — see Standard Stack / Architecture Patterns.**
- Whether license expiry needs a proactive-alert sweep like Phase 59's warranty alerts, or whether ITAM-LIC-01's "expiry tracking" is satisfied by a read-time computed field only. **Resolved below: read-time computed field only, no scheduler — see Architecture Patterns, Pattern 4, and Open Questions.**
- Component "attached" vs "detached" as a status enum vs a nullable `parentAssetId` — pick whichever matches the codebase's existing lifecycleStatus-style conventions. **Resolved below: nullable `parentAssetId`, matching the asset document's own `assignedToType`/`assignedToId` present/absent convention (not a separate status enum) — see Pattern 3.**

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope (per 60-CONTEXT.md).

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ITAM-LIC-01 | Admin can manage software licenses with seat counts, assign/reclaim seats to a user or asset, and track license expiry | Pattern 1 (atomic seat guard + `$inc`/`$push`/`$pull`), Pattern 4 (read-time expiry computation), Code Examples, Common Pitfalls 1-2 |
| ITAM-LIC-02 | Admin can manage accessories/consumables with quantity-aware checkout (supports quantity > 1 per transaction, not limited to 1) | Pattern 2 (atomic quantity guard), Common Pitfall 3 (no-silent-drop), Code Examples |
| ITAM-LIC-03 | Admin can attach components (RAM/HDD/GPU-style sub-inventory) to a parent asset | Pattern 3 (nullable parentAssetId sub-resource route, mirrors `/history`), Common Pitfall 4 |

</phase_requirements>

## Summary

Phase 60 is disciplined extension of exactly the machinery Phase 57 already proved out, applied to a new numeric-threshold flavor of the same atomic-guard problem. Every primitive needed already has a working, already-shipped precedent in this codebase: the atomic guarded state transition (`itam_lifecycle_endpoints.py`'s `find_one_and_update` with the guard clause *inside* the filter, `ReturnDocument.BEFORE` pre-image capture, and `_revert_on_history_failure` compensation on a failed audit write), the append-only history collection (`db.assignment_history` + `write_history`), the polymorphic-target request-body pattern (`CheckoutRequest`'s `targetType`/`targetId` Literal pair), and the sub-resource-route-not-embedded-response pattern for surfacing one entity's children scoped under a parent (`GET /{asset_id}/history`, and — outside ITAM — `GET /api/compliance/controls/{control_id}/evidence`).

Two things need genuine new modeling, not just literal reuse, and this research resolves both with evidence from the actual code rather than assumption:

1. **History reuse is partial, not total.** `write_history(db, tenant_id, record)` is fully generic — it takes an arbitrary dict, only ever setting `id`/`tenantId`/`ts` via `setdefault`, so it accepts a record shaped around `licenseId` or `consumableId` exactly as readily as one shaped around `assetId`. But `list_history(db, tenant_id, asset_id, limit)` is **not** generic: its query is hardcoded to `{"tenantId": tenant_id, "assetId": asset_id}` (`itam_lifecycle_service.py:58`). The correct reuse is: same collection, same `write_history` verbatim, plus two new small read functions (`list_license_history`, `list_consumable_history`) that filter on `licenseId`/`consumableId` instead of `assetId` — not a parallel collection. Two new compound indexes (`{tenantId, licenseId}`, `{tenantId, consumableId}`) are needed in `database.py`, mirroring the existing `{tenantId, assetId}` index on the same collection.

2. **A license's "current assignment state" cannot live in flat fields the way an asset's does**, because a license has *N* concurrent seat-holders while an asset has at most one current assignee. Phase 57's asset document stores its one current assignment directly on the document (`assignedToType`/`assignedToId`); a license needs an array (`assignedSeats: [{targetType, targetId, assignedAt, assignedBy}]`) on the license document itself, mutated atomically alongside the `seatsAvailable` counter in the *same* `find_one_and_update` call (`$inc` + `$push` together, or `$inc` + `$pull` for reclaim) — this is standard MongoDB update-operator combination, not hand-rolled locking, and it preserves the WR-01 "guard inside the filter, no read-then-write TOCTOU" invariant Phase 57 established. Consumables need no equivalent array: nothing in ITAM-LIC-02 or the ROADMAP success criteria calls for tracking *who* holds which unit or returning consumables, only decrementing/checking out a pool — so consumable checkout is the simpler, direct numeric analog of Phase 57's status-equality guard (a `$gte` threshold guard instead of a status-equality guard).

License expiry is resolved to **read-time computed field only, no background scheduler** — with an explicit textual basis, not a guess: ITAM-LIC-01's locked requirement text says "...track license expiry" and the ROADMAP success criterion says "...see remaining/expired seats" — both are visibility language. Phase 59's sibling requirement (ITAM-FIN-02) explicitly says "...with expiry alerts, routed through the existing notification/webhook infrastructure" — alerting language. The presence of that language in one requirement and its conspicuous absence in the other, for two requirements written in the same requirements pass on the same day, is strong evidence the omission is deliberate, not an oversight.

**Primary recommendation:** Add three new router files (`itam_license_endpoints.py`, `itam_consumable_endpoints.py`, `itam_component_endpoints.py`), each under the `/api/assets` or a new `/api/itam` prefix as detailed in Architecture Patterns, registered in `router_registry.py` immediately after `itam_label_endpoints` and before `asset_endpoints` (matching the established ordering comment). Extend `itam_models.py` with the new request/response contracts (License/Consumable/Component Create/Update + SeatAssign/SeatReclaim/ConsumableCheckout/ComponentAttach requests) rather than forking a second models module — current 227 lines plus the new models estimates to roughly 390-430 lines, still under the 500-line cap, but the planner should verify the actual line count after drafting and split into `itam_license_models.py`/etc. only if it tips over. **Do not extend `itam_lifecycle_endpoints.py` (534 lines) or `asset_endpoints.py` (511 lines) — both already exceed the CLAUDE.md 500-line limit as pre-existing conditions; this phase must not make either worse.** No new third-party dependency is needed — this is pure CRUD over the already-installed FastAPI/Pydantic/Motor stack.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| License seat assign/reclaim (atomic guard + array mutation) | API / Backend | Database / Storage | Business rule (seat-availability guard, polymorphic target validation) belongs in the endpoint handler; atomicity is expressed as a Mongo filter+update, not application-level check-then-write |
| Consumable quantity checkout (atomic decrement) | API / Backend | Database / Storage | Same shape as license seats, one level simpler — no per-seat identity to track, just a threshold-guarded `$inc` |
| Component attach/detach (`parentAssetId` reference) | API / Backend | Database / Storage | A plain reference field, not a scarcity-guarded resource — no race-condition concern equivalent to seats/quantity |
| Append-only assignment/checkout history for licenses and consumables | Database / Storage | API / Backend | Same `db.assignment_history` collection Phase 57 already owns; API only ever inserts/reads via `write_history`/new list functions |
| License expiry visibility | API / Backend | — | Computed at read time from a stored `expiryDate` field — no new collection, no background scheduler (see Summary + Pattern 4) |
| RBAC gate (`manage:assets`) | API / Backend | — | Existing `_require_itam_admin` dependency in `itam_asset_endpoints.py`, imported and reused verbatim by every new router, exactly as `itam_lifecycle_endpoints.py` already does |
| Component visibility on the parent asset | API / Backend | Database / Storage | New sub-resource route `GET /api/assets/{asset_id}/components`, scoped by the asset id in the URL path — mirrors `GET /{asset_id}/history` and (outside ITAM) `GET /api/compliance/controls/{control_id}/evidence` |

## Package Legitimacy Audit

**Not applicable this phase.** No new third-party packages are introduced. This is pure FastAPI/Pydantic/Motor CRUD reusing the stack already installed and verified in production for Phases 56-58 (`fastapi==0.140.0`, `pydantic==2.13.4`, `pymongo==4.17.0`/`motor` — versions confirmed via `backend/venv/bin/python -c "import fastapi, pydantic, pymongo"` this session `[VERIFIED: backend/venv, direct import]`). No `npm view`/`pip index versions`/legitimacy-check invocation was needed because nothing new is being added to `backend/requirements.txt`.

## Standard Stack

### Core (already installed — verified via grep of Phase 56/57 code, not a new install)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | `>=0.110.0,<1.0.0` pinned; `0.140.0` installed `[VERIFIED: backend/requirements.txt:13; backend/venv import]` | Router/endpoint definitions | Already used by every ITAM module; no alternative considered |
| Pydantic v2 | `>=2.5.0,<3.0.0` pinned; `2.13.4` installed `[VERIFIED: backend/requirements.txt:36; backend/venv import]` | Request/response contracts, `ConfigDict(extra="forbid")` v2 idiom | Matches `itam_models.py` exactly — every new model must use the same v2 syntax and `extra="forbid"` |
| Motor (`motor.motor_asyncio`) | `>=3.3.0,<4.0.0` pinned `[VERIFIED: backend/requirements.txt:31]` | Async MongoDB driver, via `TenantIsolatedDatabase`/`TenantIsolatedCollection` | Sole DB access path in this codebase |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` + `pytest-asyncio` | already installed | `@pytest.mark.asyncio` test decoration | `test_itam_lifecycle.py`/`test_itam_labels*.py` already use this; new `test_itam_licenses.py`/`test_itam_consumables.py`/`test_itam_components.py` should match |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Three dedicated router files with real business logic (`itam_license_endpoints.py`, etc.) | Extend `itam_catalog_endpoints.py`'s generic `{kind}`-dispatched CRUD (adding `"licenses"`/`"consumables"`/`"components"` to `CATALOG_KINDS`) | Rejected — `itam_catalog_endpoints.py` (`backend/itam_catalog_endpoints.py:29-52`) is a bare model-validate-then-insert/find/patch/delete dispatcher with zero business logic hooks beyond one `if kind == "models"` reference-check special case. It has no mechanism for an atomic guarded numeric decrement, a polymorphic assign/reclaim action, or a sub-resource history route — bolting that in would turn a clean 5-kind generic CRUD router into a special-cased mess. Dedicated routers (matching Phase 57's own precedent of a dedicated `itam_lifecycle_endpoints.py` rather than extending the generic catalog router) are the right shape. |
| A `licenseId`/`consumableId`-keyed read into the shared `assignment_history` collection via two new thin functions | A parallel `license_history`/`consumable_history` collection, structurally cloned from `assignment_history` | Rejected per D-02's own preference order — `write_history` already accepts any record shape (verified: `itam_lifecycle_service.py:39-44` only ever sets `id`/`tenantId`/`ts` via `setdefault`, never assumes an `assetId` key exists). Only the *read* side (`list_history`) is asset-specific; forking the whole collection to fix a read-side limitation would be over-engineering when adding two ~10-line query functions solves it. |
| An `assignedSeats` array embedded on the license document, mutated via `$inc`+`$push`/`$pull` in the same atomic call | A separate `license_seats` collection, one document per assigned seat | Considered, not adopted as primary — a separate collection is a defensible alternative (avoids unbounded array growth risk on the license document, matches the codebase's own preference for separate collections over embedded arrays for `assignment_history` itself — see Phase 57's own "Alternatives Considered" entry). However a license's seat count is capped by `seatsTotal` (typically tens to low hundreds, never remotely close to MongoDB's 16MB document limit the way an ever-growing audit trail could be), so the array approach is simpler and keeps "how many seats does this license have assigned right now" a single-document read with no join/aggregation. **Flagged in Open Questions for the planner to make final call, since both are defensible engineering choices, not adjudicated in CONTEXT.md.** |

**Installation:** None — no new packages.

**Version verification:** Not applicable — no new packages recommended.

## Architecture Patterns

### System Architecture Diagram

```
Client (Phase 61 frontend, out of scope this phase)
        │
        │  POST /api/itam/licenses                    (create license)
        │  POST /api/itam/licenses/{id}/assign         (assign a seat)
        │  POST /api/itam/licenses/{id}/reclaim         (reclaim a seat)
        │  GET  /api/itam/licenses/{id}/history          (seat assign/reclaim trail)
        │  POST /api/itam/consumables                  (create consumable)
        │  POST /api/itam/consumables/{id}/checkout    (quantity-aware checkout)
        │  GET  /api/itam/consumables/{id}/history       (checkout trail)
        │  POST /api/itam/components                  (create component, optional parentAssetId)
        │  POST /api/itam/components/{id}/attach       (set parentAssetId)
        │  POST /api/itam/components/{id}/detach       (clear parentAssetId)
        │  GET  /api/assets/{asset_id}/components        (components attached to one asset)
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ itam_license_endpoints.py / itam_consumable_endpoints.py /         │
│ itam_component_endpoints.py  (3 new FastAPI routers)                │
│  - _require_itam_admin (RBAC: manage:assets) — imported, reused    │
│  - tenant_id from current_user, resolved exactly as itam_lifecycle │
│    _endpoints.py already does                                       │
│  - target/parent-asset existence validated (db.users/db.assets)     │
│    strictly BEFORE the guarded update — mirrors _resolve_target      │
└───────────────┬──────────────────────────────────────────────────┘
                │
                ▼
   ATOMIC guarded transition (find_one_and_update, guard IN the filter,
   ReturnDocument.BEFORE pre-image, _apply_known_delta rebuild,
   write_history + _revert_on_history_failure on failure) — cloned
   verbatim from itam_lifecycle_endpoints.py's checkout/checkin shape,
   with the guard clause changed from a status-equality check to a
   numeric $gte threshold check:
     licenses:    {"id": id, "seatsAvailable": {"$gte": 1}}
                  $inc seatsAvailable -1, $push assignedSeats
     consumables: {"id": id, "quantityAvailable": {"$gte": qty}}
                  $inc quantityAvailable -qty
        │
        ▼
   write_history(db, tenant_id, {"licenseId"|"consumableId": id, "action": ...})
   — SAME db.assignment_history collection + SAME write_history() helper
   Phase 57 already owns (itam_lifecycle_service.py), record shape is a
   plain dict so no generalization work needed on the write side.
        │
        ▼
   list_license_history() / list_consumable_history() — two NEW ~10-line
   read functions (itam_lifecycle_service.py or a new shared module),
   querying the SAME collection filtered on licenseId/consumableId
   instead of list_history()'s hardcoded assetId filter.
```

### Recommended Project Structure
```
backend/
├── itam_models.py                 # EXTEND — License/Consumable/Component Create/Update +
│                                   #   SeatAssignRequest/SeatReclaimRequest/
│                                   #   ConsumableCheckoutRequest/ComponentAttachRequest
├── itam_lifecycle_service.py      # EXTEND — add list_license_history / list_consumable_history
│                                   #   (write_history reused as-is, zero changes needed there)
├── itam_license_endpoints.py      # NEW — POST /api/itam/licenses, /{id}/assign, /{id}/reclaim,
│                                   #   GET /{id}/history, GET "" (list), GET /{id}
├── itam_consumable_endpoints.py   # NEW — POST /api/itam/consumables, /{id}/checkout,
│                                   #   GET /{id}/history, GET "" (list), GET /{id}
├── itam_component_endpoints.py    # NEW — POST /api/itam/components, /{id}/attach, /{id}/detach,
│                                   #   GET /api/assets/{asset_id}/components (sub-resource route)
├── router_registry.py             # EXTEND — register all 3 new routers after itam_label_endpoints,
│                                   #   before asset_endpoints (matches existing ordering comment)
├── database.py                    # EXTEND — 6 new indexes (see Common Pitfalls) + 3 new
│                                   #   {tenantId} single-field indexes for licenses/consumables/
│                                   #   components collections themselves
└── tests/
    ├── itam_license_test_support.py     # NEW — fixtures, mirrors itam_lifecycle_test_support.py
    ├── test_itam_licenses.py            # NEW
    ├── test_itam_consumables.py         # NEW
    └── test_itam_components.py          # NEW
```

**Endpoint prefix note:** Unlike Phases 57/58 (which mount sub-resource routes under the shared `/api/assets` prefix because they operate on *existing* asset documents), licenses/consumables/components are new top-level entity types with their own lifecycle, not asset sub-resources — `/api/itam/licenses`, `/api/itam/consumables`, `/api/itam/components` (mirroring `itam_catalog_endpoints.py`'s existing `/api/itam/catalog` prefix family) is the more consistent placement. The one exception is `GET /api/assets/{asset_id}/components`, which genuinely is asset-scoped (component-attached-to-asset lookup) and belongs under `/api/assets`, mirroring `GET /{asset_id}/history`.

### Pattern 1: License seat assign/reclaim — atomic guard cloned from checkout/checkin, numeric instead of status-equality
**What:** `find_one_and_update` with the seat-availability guard *inside* the filter (never a preceding read-then-check), combining the counter mutation and the assignment-array mutation in one atomic call.
**When to use:** `POST /api/itam/licenses/{id}/assign` and `/reclaim`.
**Example:**
```python
# Source: pattern cloned from backend/itam_lifecycle_endpoints.py:140-161 (checkout_asset's
# guard-in-filter + BEFORE pre-image + 404-vs-409 disambiguation), numeric guard substituted
# for the status-equality guard.
from pymongo import ReturnDocument

async def assign_seat(license_id: str, target_type: str, target_id: str, tenant_id: str, actor: str, db):
    # Target existence validated BEFORE the guarded update — same ordering as
    # itam_lifecycle_endpoints.py's _resolve_target, for the same TOCTOU reason.
    await _resolve_seat_target(db, target_type, target_id)  # db.users or db.assets lookup

    now = _now_iso()
    seat_entry = {"targetType": target_type, "targetId": target_id, "assignedAt": now, "assignedBy": actor}
    filt = {"id": license_id, "seatsAvailable": {"$gte": 1}}
    update = {
        "$inc": {"seatsAvailable": -1},
        "$push": {"assignedSeats": seat_entry},
        "$set": {"updatedAt": now},
    }
    pre_image = await db.licenses.find_one_and_update(filt, update, return_document=ReturnDocument.BEFORE)
    if not pre_image:
        existing = await db.licenses.find_one({"id": license_id})
        if not existing:
            raise HTTPException(status_code=404, detail="License not found")
        raise HTTPException(status_code=409, detail="No seats available on this license.")

    # write_history reused VERBATIM — record shape is licenseId-keyed, not assetId-keyed;
    # write_history has no opinion on the shape, it only sets id/tenantId/ts.
    history_record = {
        "licenseId": license_id, "action": "assign",
        "targetType": target_type, "targetId": target_id,
        "actorUsername": actor, "ts": now,
    }
    # try/except + _revert_on_history_failure-style compensation applies identically here —
    # revert both $inc and $push on a failed history write.
```

### Pattern 2: Consumable checkout — the same guard, one level simpler (no per-unit identity)
**What:** A pure numeric `$gte`-guarded `$inc`, no array mutation — consumables aren't individually tracked or reclaimed per REQUIREMENTS.md's wording.
**When to use:** `POST /api/itam/consumables/{id}/checkout`.
**Example:**
```python
# Source: same guard-in-filter shape as Pattern 1, minus the $push (no per-seat identity to
# track for consumables — checkout is a pool decrement, not an assignment record on the parent).
filt = {"id": consumable_id, "quantityAvailable": {"$gte": requested_qty}}
update = {"$inc": {"quantityAvailable": -requested_qty}, "$set": {"updatedAt": now}}
pre_image = await db.consumables.find_one_and_update(filt, update, return_document=ReturnDocument.BEFORE)
if not pre_image:
    existing = await db.consumables.find_one({"id": consumable_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Consumable not found")
    # D-04: the WHOLE checkout is rejected when requested > available — never partial fulfillment.
    raise HTTPException(status_code=409, detail="Requested quantity exceeds available stock.")
```
**Pydantic validation for the request quantity itself:**
```python
class ConsumableCheckoutRequest(BaseModel):
    targetType: Literal["user", "asset"]
    targetId: str
    quantity: int = Field(gt=0)   # V5 boundary: reject 0/negative before it ever reaches the guard
    note: Optional[str] = None
    model_config = ConfigDict(extra="forbid")
```

### Pattern 3: Component attach/detach — nullable `parentAssetId`, sub-resource route mirrors `/history`
**What:** `parentAssetId: Optional[str]` on the component document, set/cleared via dedicated action routes, plus a read-side sub-resource route scoped under the asset.
**When to use:** `POST /api/itam/components/{id}/attach {parentAssetId}`, `POST /api/itam/components/{id}/detach`, `GET /api/assets/{asset_id}/components`.
**Rationale for nullable field over a status enum:** The asset document's own established convention for "is this thing currently assigned" is presence/absence of `assignedToType`/`assignedToId` (Phase 57), not a separate `assignmentStatus` enum — `_deployed_guard()`/`_deployable_guard()` key off the *absence* of the field as a real state, not a sentinel value. A nullable `parentAssetId` on the component is the direct analog: `null`/absent means unattached, a non-null value means attached to that asset — one field, matching the pattern already established rather than introducing a parallel enum that duplicates the same information.
```python
# Source: sub-resource route pattern cloned from itam_lifecycle_endpoints.py:305-344
# (list_assignment_history) and, outside ITAM, backend/compliance_evidence_endpoints.py:416-421
# (GET /api/compliance/controls/{control_id}/evidence) — the established in-repo shape for
# "list a sub-resource scoped by its parent's id in the URL path."
@router.get("/{asset_id}/components", response_model=Dict[str, Any])
async def list_asset_components(asset_id: str, current_user: TokenData = Depends(_require_itam_admin)):
    db = get_database()
    asset = await db.assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    components = await db.components.find({"parentAssetId": asset_id}, {"_id": 0}).to_list(length=200)
    return {"assetId": asset_id, "components": components}
```
**Detach (record persists per D-05):**
```python
pre_image = await db.components.find_one_and_update(
    {"id": component_id, "parentAssetId": {"$ne": None}},
    {"$set": {"parentAssetId": None, "updatedAt": now}},
    return_document=ReturnDocument.BEFORE,
)
if not pre_image:
    existing = await db.components.find_one({"id": component_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Component not found")
    raise HTTPException(status_code=409, detail="Component is not currently attached to an asset.")
```

### Pattern 4: License expiry — read-time computed field, no scheduler
**What:** `expiryDate` is a stored ISO date field on the license document (validated with the same `_validate_iso8601_date` field validator already in `itam_models.py:163-175`); `isExpired`/`daysUntilExpiry` are computed at read time in the GET/list endpoint handler, never stored, never swept by a background job.
**When to use:** Every license GET/list response.
**Why not a scheduler:** See Summary — the requirement/success-criteria wording contrast with Phase 59's explicit "expiry alerts...routed through notification/webhook infrastructure" language is the deciding evidence. Building a scheduler here would also repeat the exact background-scheduler tenant-isolation risk class the codebase has already had to be careful about elsewhere (`compliance_remediation_sla_service.py`'s `run_sla_pass` iterates *all* tenants' tasks with no ambient tenant context, extracting `tenantId` per-document and skipping any doc missing it — `backend/compliance_remediation_sla_service.py:211-230`) for zero requirement-driven benefit in this phase.
```python
# Source: pattern for the read-time computation; _validate_iso8601_date reused from
# itam_models.py:163-175 for the expiryDate field itself.
def _enrich_license_expiry(doc: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    expiry_date = doc.get("expiryDate")
    if expiry_date:
        expiry_dt = datetime.fromisoformat(expiry_date.replace("Z", "+00:00"))
        if expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
        doc["daysUntilExpiry"] = (expiry_dt - now).days
        doc["isExpired"] = expiry_dt < now
    else:
        doc["daysUntilExpiry"] = None
        doc["isExpired"] = False
    return doc
```

### Anti-Patterns to Avoid
- **Read-then-check-then-write for seat/quantity availability:** The exact TOCTOU race Phase 57's own `57-01-PLAN.md`/`itam_lifecycle_endpoints.py` went out of its way to avoid for checkout — two concurrent seat-assign or consumable-checkout requests must never both observe availability and both write. The guard belongs *inside* the `find_one_and_update` filter, never in a preceding `find_one`.
- **Silently truncating an over-requested consumable quantity:** D-04 explicitly forbids "partial/silent-drop fulfillment" — the whole checkout must be rejected with 409 if `requested > available`, mirroring Phase 58's no-silent-drop bulk contract.
- **Forking a second `license_history`/`consumable_history` collection:** `write_history` already generalizes; only two small read-side functions are missing. Forking the collection would duplicate the append-only guarantee logic (and its `_revert_on_history_failure` compensation pattern) for no benefit.
- **Adding a background expiry-alert scheduler this phase:** Not called for by ITAM-LIC-01's actual wording (see Pattern 4) — would be scope creep relative to the locked requirement, and would introduce the tenant-isolation background-scheduler risk class for zero requirement-driven benefit.
- **Extending `itam_lifecycle_endpoints.py` (534 lines) or `asset_endpoints.py` (511 lines):** Both already exceed the CLAUDE.md 500-line cap as a pre-existing condition (verified via `wc -l` this session) — adding any code to either makes an existing violation worse. New capability goes in new files.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic seat/quantity concurrency guard | A custom locking mechanism, a `asyncio.Lock`, or a read-then-write check | MongoDB's `find_one_and_update` with the guard clause inside the filter (Pattern 1/2, cloned verbatim from `itam_lifecycle_endpoints.py`) | This exact problem was already solved correctly for asset checkout in Phase 57 — a second, differently-shaped solution for the numeric case would be inconsistent and a needless place for a subtle race to creep back in |
| Append-only audit trail for seat/checkout actions | A new insert-only collection + module, structurally cloned from `assignment_history`/`itam_lifecycle_service.py` | The existing `db.assignment_history` collection + `write_history()`, with two new thin read functions | `write_history` already generalizes (see Summary) — forking a second collection duplicates working code for a problem that doesn't exist |
| Polymorphic assign-target validation | Two separate optional id fields (`targetUserId`/`targetAssetId`) | A single `targetType: Literal[...]` / `targetId: str` pair, following PD-01 (`CheckoutRequest`'s own pattern) | This codebase has already made and documented this exact modeling decision once (Phase 57); repeating it with two optional fields would contradict an established, locked convention |

**Key insight:** Nothing in this phase is a "deceptively complex, actually has sharp edges" problem the way barcode encoding was for Phase 58 — every genuinely tricky piece (atomicity, TOCTOU, append-only history) has already been solved once in this exact codebase for a structurally identical problem. The discipline required here is recognizing which prior solution generalizes as-is (`write_history`) versus which needs a small, explicit modification (`list_history`'s hardcoded `assetId` filter) versus which needs genuinely new (but still well-precedented) modeling (the `assignedSeats` array, because a license's 1:N assignment cardinality has no direct analog in Phase 57's 1:1 asset-checkout model).

## Runtime State Inventory

**Not applicable — this is a greenfield capability, not a rename/refactor/migration phase.** No existing data, service config, OS-registered state, secrets, or build artifacts reference "license"/"consumable"/"component" concepts anywhere in this codebase today (confirmed via grep — the only pre-existing `"components"` usages found are in `sbom_endpoints.py`/`container_scanner_endpoints.py`/`export_service.py`, which is SBOM software-bill-of-materials data, an entirely unrelated domain from ITAM hardware sub-inventory; no collection name collision risk since MongoDB collection names are independent of JSON response keys in an unrelated module).

## Common Pitfalls

### Pitfall 1: Treating `seatsUsed` (count-up) as the guard field instead of `seatsAvailable` (count-down)
**What goes wrong:** If the license document stores `seatsTotal` + `seatsUsed` and the guard is expressed as `{"$expr": {"$lt": ["$seatsUsed", "$seatsTotal"]}}`, the guard requires a Mongo `$expr` cross-field comparison — more error-prone to get right under concurrent load than a direct field-vs-literal comparison, and harder to combine cleanly with `$inc` in the same atomic call the way Pattern 1 does.
**Why it happens:** "Used" feels like the more natural field to increment when assigning a seat, but it makes the guard clause structurally more complex than it needs to be.
**How to avoid:** Store `seatsAvailable` directly (decrement on assign, increment on reclaim) — the guard becomes a plain `{"seatsAvailable": {"$gte": 1}}` filter clause, identical in shape to `_deployable_guard()`'s equality check, just with a different comparison operator. Compute `seatsUsed = seatsTotal - seatsAvailable` only at read time for display, never store it as a second source of truth that could drift.
**Warning signs:** A `$expr` clause in the guard filter where a plain field comparison would do; two counter fields (`seatsUsed` and `seatsAvailable`) both being written on the same mutation (a drift risk — only one should ever be the write target).

### Pitfall 2: `write_history` record shape accidentally colliding with `list_history`'s hardcoded `assetId` key
**What goes wrong:** If a license-assign history record is written with an `assetId` key (e.g. because the target happens to be an asset, `targetType: "asset"`), it would accidentally become visible through the *existing* `list_history(db, tenant_id, asset_id, limit)` function (which queries on `assetId`) — polluting an asset's check-out/check-in history view with unrelated license-seat-assignment entries that used that asset as a seat target.
**Why it happens:** `targetId` (the seat assignee, which may itself be an asset id) is easy to confuse with `assetId` (the key `list_history` filters on) — they can hold the same *value* for an asset-target seat assignment, but must never share the same *key name* in the stored document.
**How to avoid:** License/consumable history records must use `licenseId`/`consumableId` as their primary lookup key (never `assetId`), even when `targetType == "asset"` — `targetId` (inside the record) is what happens to reference an asset in that case, not the top-level lookup key. Add a regression test asserting that assigning a license seat to `targetType: "asset"` does NOT make the assignment appear in that asset's own `GET /{asset_id}/history` response.
**Warning signs:** A license-seat-assign integration test that checks out to an asset target, and an asset history test that unexpectedly returns more entries than the asset's own checkout/checkin actions produced.

### Pitfall 3: Consumable checkout target validation being skipped because `CheckoutRequest`'s existing `_resolve_target` only knows `"user"`/`"location"`
**What goes wrong:** `itam_lifecycle_endpoints.py::_resolve_target` (line 75-90) is hardcoded to the Literal values `"user"`/`"location"` that Phase 57's `CheckoutRequest` uses. If a new consumable/license endpoint imports and calls this function directly with `targetType="asset"` (this phase's polymorphic pair per D-03 is `"user"`/`"asset"`, a *different* pair from Phase 57's `"user"`/`"location"`), it silently falls into the `else: target = None` branch and always raises 400, even for a legitimately-existing asset id.
**Why it happens:** The two phases' polymorphic target pairs are similar in shape (`targetType`/`targetId` Literal pair) but not identical in *values* — reusing the function by name without checking its Literal branches is an easy mistake.
**How to avoid:** Write a NEW `_resolve_seat_target`/`_resolve_checkout_target` function local to the new router(s) with `"user"`/`"asset"` branches (`db.users.find_one`/`db.assets.find_one`), following the same shape as `_resolve_target` but not importing/calling it directly.
**Warning signs:** Every seat-assign or consumable-checkout request to a valid asset id returning 400 "not found" — the tell that the wrong target-resolution function is in the call path.

### Pitfall 4: `db.components.find({"parentAssetId": asset_id})` returning cross-tenant components if the components collection isn't in the `TenantIsolatedDatabase` wrapper's default (wrapped) path
**What goes wrong:** `TenantIsolatedDatabase.__getattr__`/`__getitem__` auto-wraps any collection name NOT in its hardcoded exemption allowlist (`database.py:122-134`, `compliance_frameworks`/`tenants`/`roles`/etc.) — `components`/`licenses`/`consumables` are new collection names not yet in that allowlist, so by default they'll be correctly auto-wrapped and tenant-scoped. The risk is the *opposite* direction: someone adds them to the exemption list "to be safe" or "because it's new," which would actually remove tenant isolation.
**Why it happens:** The exemption list exists for genuinely global reference data (frameworks, roles, platform-wide seeded playbooks) — a contributor unfamiliar with why that list exists could plausibly add a new collection to it by mistaken analogy.
**How to avoid:** Do not add `licenses`/`consumables`/`components` to the exemption list in `database.py` under any circumstance — verify with a cross-tenant isolation test (tenant A cannot see tenant B's licenses/consumables/components) exactly as `itam_lifecycle_endpoints.py`'s own tenant-isolation tests do for assignment history.
**Warning signs:** A code review or PR diff touching `database.py`'s exemption list for any ITAM collection — this should be an automatic red flag requiring explanation.

## Code Examples

Verified patterns from official/in-repo sources:

### Existing generic guard-in-filter atomicity pattern (reused verbatim in shape, not literally imported)
```python
# Source: backend/itam_lifecycle_endpoints.py:140-161 (checkout_asset) — the guard clause lives
# inside find_one_and_update's filter argument, never in a preceding conditional read.
filt: Dict[str, Any] = {"id": asset_id, **_deployable_guard()}
pre_image = await db.assets.find_one_and_update(
    filt, update, return_document=ReturnDocument.BEFORE
)
if not pre_image:
    existing = await db.assets.find_one({"id": asset_id})
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset is not in a deployable status.")
```

### Existing write_history generic-record insertion (reused verbatim, no changes needed)
```python
# Source: backend/itam_lifecycle_service.py:31-44 — record is an arbitrary Dict[str, Any];
# only id/tenantId/ts are ever set by this function, via setdefault (never overwrites a
# caller-supplied value). A license-seat-assign record with a `licenseId` key (not `assetId`)
# passes through this function completely unmodified in shape.
async def write_history(db, tenant_id: str, record: Dict[str, Any]) -> str:
    doc = dict(record)
    doc["id"] = f"ah-{uuid.uuid4().hex[:8]}"
    doc.setdefault("tenantId", tenant_id)
    doc.setdefault("ts", _now_iso())
    await db.assignment_history.insert_one(doc)
    return doc["id"]
```

### New: list_license_history / list_consumable_history (the one genuinely new piece on the read side)
```python
# Source: pattern cloned from backend/itam_lifecycle_service.py:47-62 (list_history), with the
# hardcoded "assetId" filter key replaced. Add alongside list_history in
# itam_lifecycle_service.py — same file, same collection, same sort/projection shape.
async def list_license_history(db, tenant_id: str, license_id: str, limit: int = 100):
    cursor = (
        db.assignment_history.find({"tenantId": tenant_id, "licenseId": license_id}, {"_id": 0})
        .sort([("ts", -1), ("_id", -1)])
        .limit(limit)
    )
    return await cursor.to_list(length=limit)

async def list_consumable_history(db, tenant_id: str, consumable_id: str, limit: int = 100):
    cursor = (
        db.assignment_history.find({"tenantId": tenant_id, "consumableId": consumable_id}, {"_id": 0})
        .sort([("ts", -1), ("_id", -1)])
        .limit(limit)
    )
    return await cursor.to_list(length=limit)
```

### Existing sub-resource-scoped-by-parent-id route pattern (both in-ITAM and out-of-ITAM precedent)
```python
# Source: backend/itam_lifecycle_endpoints.py:305-344 (list_assignment_history) — an asset's
# sub-resource, never embedded into the asset's own GET /{asset_id} response.
@router.get("/{asset_id}/history", response_model=Dict[str, Any])
async def list_assignment_history(asset_id: str, limit: int = Query(100, ge=1, le=500), ...):
    ...
    entries = await list_history(db, tenant_id, asset_id, limit)
    return {"assetId": asset_id, "entries": entries}

# Source: backend/compliance_evidence_endpoints.py:416-421 (get_control_evidence) — the same
# shape outside ITAM entirely: GET /api/compliance/controls/{control_id}/evidence, not embedded
# into a hypothetical GET /api/compliance/controls/{control_id}.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| N/A — this is new capability for the codebase | N/A | N/A | This phase introduces license/consumable/component sub-inventory from scratch; the only "prior approach" is the structurally analogous Phase 57 asset-checkout machinery this research clones patterns from, not a legacy approach to migrate away from |

**Deprecated/outdated:** None identified.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | An `assignedSeats` array embedded on the license document (rather than a separate `license_seats` collection) is the right cardinality model, given license seat counts are bounded (tens-to-low-hundreds) and never approach MongoDB's 16MB document cap | Architecture Patterns — Pattern 1, Standard Stack Alternatives Considered | Low-medium — if a tenant somehow has a license with an extremely large seat count (thousands+), the embedded-array approach degrades write-amplification-wise the same way Phase 57 already rejected for `assignment_history`; the planner should confirm this is an acceptable v1 bound (matching D-03's fixed-seat-count model, which has no stated upper limit) or explicitly choose the separate-collection alternative instead |
| A2 | `/api/itam/licenses`, `/api/itam/consumables`, `/api/itam/components` (new top-level prefix family, not `/api/assets`) is the right route placement, since these are new entity types rather than asset sub-resources | Architecture Patterns — Recommended Project Structure | Low — this is a routing/URL-shape decision with no data-model consequence; if the planner or a plan-checker disagrees and prefers `/api/assets/licenses` etc., it's a mechanical rename with no downstream impact on the atomicity/history patterns this research is actually about |
| A3 | License expiry requires no proactive alert/scheduler this phase, based on a textual-wording contrast between ITAM-LIC-01 and ITAM-FIN-02 rather than an explicit CONTEXT.md ruling | Architecture Patterns — Pattern 4, Summary | Medium — CONTEXT.md explicitly left this to research/planning discretion rather than locking it; if a stakeholder actually wants proactive alerting for license expiry despite the wording, this is a real scope gap, not just an implementation detail — the planner should treat this as confirmed-by-research but flag it as a decision point for a final human check before considering ITAM-LIC-01 fully done (see Open Questions) |

**If this table is empty:** N/A — see rows above.

## Open Questions

1. **Embedded `assignedSeats` array vs. separate `license_seats` collection**
   - What we know: Both are defensible; the array keeps single-document reads simple and license seat counts are inherently bounded (a `seatsTotal` field the admin sets), unlike the audit-trail growth pattern that made Phase 57 reject embedding for `assignment_history`.
   - What's unclear: Whether any tenant's real usage could push a single license's seat count high enough to matter (e.g., an enterprise-wide OS license with thousands of seats) — no such scale requirement is stated anywhere in REQUIREMENTS.md/ROADMAP.md for this milestone.
   - Recommendation: Default to the embedded-array approach (Pattern 1) for v1 — it's simpler, and D-03 doesn't specify a seat-count ceiling that would make the array approach risky at the scale this milestone targets (SMB/mid-market ITAM, not enterprise-scale license management). If the planner is more conservative, the separate-collection alternative is a documented, ready-to-use fallback (see Standard Stack — Alternatives Considered).

2. **Should ITAM-LIC-01's "track license expiry" surface a UI-visible warning threshold (e.g. "expiring within 30 days") at read time, beyond just `isExpired`/`daysUntilExpiry`?**
   - What we know: ROADMAP's success criterion says "see remaining/expired seats" — doesn't explicitly mention a "near-expiry" warning tier, only expired-or-not.
   - What's unclear: Whether Phase 61 (frontend console) will want a distinct "expiring soon" visual state, which would need no new backend field (derivable client-side from `daysUntilExpiry`) but is worth flagging so Phase 61's research/planning doesn't have to re-derive this.
   - Recommendation: `daysUntilExpiry` (a signed integer, negative when already expired) plus `isExpired` (boolean) is sufficient backend surface — any "expiring within N days" *threshold* styling is a pure frontend concern for Phase 61, needing no additional backend field. No action needed this phase.

3. **A3 above — should this phase's read-only expiry field get a Phase 59-style proactive alert path in a later, explicitly-scoped follow-up?**
   - What we know: Phase 59 (Procurement & Finance, running concurrently with this research) is building the exact notification/webhook-routed expiry-alert infrastructure for warranty expiry — the same infrastructure could, in principle, be pointed at license expiry later with minimal new work, since Pattern 4's stored `expiryDate` field is exactly the kind of field such a sweep would key off.
   - What's unclear: Whether this is desired at all — REQUIREMENTS.md doesn't call for it and it would be additive scope.
   - Recommendation: Leave for a v2/backlog candidate if a stakeholder wants it later; do not build it speculatively into Phase 60. Note it in a Key Decisions / backlog note only if the planner or human checkpoint agrees this is worth flagging in PROJECT.md's v2 Backlog Candidates.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Backend runtime | ✓ | 3.12.3 `[VERIFIED: backend/venv/bin/python --version]` | — |
| FastAPI | Router/endpoint definitions | ✓ | 0.140.0 `[VERIFIED: backend/venv import]` | — |
| Pydantic | Request/response contracts | ✓ | 2.13.4 `[VERIFIED: backend/venv import]` | — |
| Motor / pymongo | Async MongoDB driver | ✓ | pymongo 4.17.0 `[VERIFIED: backend/venv import]` | — |
| mongod | Database | ✓ | running (`pgrep -a mongod` confirmed a live process this session) — kernel-workaround systemd drop-in already in place per project memory | — |
| pytest / pytest-asyncio | Test suite | ✓ | already installed, exercised by every prior ITAM test file | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (`@pytest.mark.asyncio`), matching `test_itam_lifecycle.py`/`test_itam_labels*.py` |
| Config file | none — no `pytest.ini`/`pyproject.toml [tool.pytest]` section found in this repo (consistent with Phase 57/58's research findings) |
| Quick run command | `backend/venv/bin/python -m pytest backend/tests/test_itam_licenses.py backend/tests/test_itam_consumables.py backend/tests/test_itam_components.py -q` |
| Full suite command | `backend/venv/bin/python -m pytest backend/tests -q` (per project memory: use `backend/venv/bin/python`, NOT system Python) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ITAM-LIC-01 | Assigning a seat when `seatsAvailable >= 1` succeeds, decrements the counter, and appends to `assignedSeats` | unit | `pytest backend/tests/test_itam_licenses.py -k assign_seat_success -x` | ❌ Wave 0 |
| ITAM-LIC-01 | Assigning a seat when `seatsAvailable == 0` is rejected with 409, no mutation occurs (concurrency-guard proof: two concurrent assign calls against a 1-seat license, exactly one succeeds) | unit | `pytest backend/tests/test_itam_licenses.py -k assign_seat_no_availability -x` | ❌ Wave 0 |
| ITAM-LIC-01 | Reclaiming a seat returns it to the available pool and removes the matching `assignedSeats` entry | unit | `pytest backend/tests/test_itam_licenses.py -k reclaim_seat -x` | ❌ Wave 0 |
| ITAM-LIC-01 | Seat-assign/reclaim writes exactly one `assignment_history` entry each, retrievable via `list_license_history`, keyed on `licenseId` (Pitfall 2 regression: not visible via an unrelated asset's `/history` route) | unit | `pytest backend/tests/test_itam_licenses.py -k history_isolation -x` | ❌ Wave 0 |
| ITAM-LIC-01 | `daysUntilExpiry`/`isExpired` computed correctly at read time for past/future/absent `expiryDate` (Pattern 4) | unit | `pytest backend/tests/test_itam_licenses.py -k expiry_computation -x` | ❌ Wave 0 |
| ITAM-LIC-02 | Checkout with `quantity <= quantityAvailable` succeeds and decrements exactly by that amount in one atomic op | unit | `pytest backend/tests/test_itam_consumables.py -k checkout_success -x` | ❌ Wave 0 |
| ITAM-LIC-02 | Checkout with `quantity > quantityAvailable` is rejected whole (409), zero partial decrement (D-04 no-silent-drop) | unit | `pytest backend/tests/test_itam_consumables.py -k checkout_over_quantity_rejected -x` | ❌ Wave 0 |
| ITAM-LIC-03 | Attaching a component sets `parentAssetId`; `GET /api/assets/{asset_id}/components` returns it | unit | `pytest backend/tests/test_itam_components.py -k attach_and_list -x` | ❌ Wave 0 |
| ITAM-LIC-03 | Detaching clears `parentAssetId` but the component record persists (not deleted) — a subsequent `GET /api/itam/components/{id}` still 200s | unit | `pytest backend/tests/test_itam_components.py -k detach_persists -x` | ❌ Wave 0 |
| All three | RBAC: every new route rejects a caller without `manage:assets` (403) | unit | `pytest backend/tests/test_itam_licenses.py backend/tests/test_itam_consumables.py backend/tests/test_itam_components.py -k rbac -x` | ❌ Wave 0 |
| All three | Tenant isolation: tenant A cannot read/mutate tenant B's licenses/consumables/components (Pitfall 4 regression) | unit | `pytest backend/tests/test_itam_licenses.py backend/tests/test_itam_consumables.py backend/tests/test_itam_components.py -k tenant_isolation -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `backend/venv/bin/python -m pytest backend/tests/test_itam_licenses.py backend/tests/test_itam_consumables.py backend/tests/test_itam_components.py -q`
- **Per wave merge:** `backend/venv/bin/python -m pytest backend/tests -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/itam_license_test_support.py` — new shared fixture module, mirrors `itam_lifecycle_test_support.py`'s `MockTenantIsolatedDatabase`/`mock_db`/`patch_get_database_globally` conventions, extended with `licenses`/`consumables`/`components` collections in the mock db
- [ ] `backend/tests/test_itam_licenses.py`, `test_itam_consumables.py`, `test_itam_components.py` — all new
- [ ] Framework install: none — pytest/pytest-asyncio already installed
- [ ] `database.py` index additions (see Common Pitfalls / Architecture) are a Wave 0 prerequisite so tenant-isolation query performance matches the existing `assignment_history` precedent from day one, not retrofitted later

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (inherited) | `Depends(get_current_user)` via `_require_itam_admin` — unchanged, reused |
| V3 Session Management | no | No new session surface introduced |
| V4 Access Control | yes | `_require_itam_admin` (`manage:assets` permission) gates every new route; `TenantIsolatedDatabase` auto-scopes all new collections (licenses/consumables/components/assignment_history reads) to the caller's tenant — must NOT be added to the exemption allowlist (Pitfall 4) |
| V5 Input Validation | yes | `ConsumableCheckoutRequest.quantity: int = Field(gt=0)`; polymorphic `targetType: Literal[...]` rejects any value outside the closed set at the Pydantic layer before it reaches business logic; `_validate_iso8601_date` reused for `expiryDate` |
| V6 Cryptography | no | No cryptographic operations in this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Race condition — two concurrent seat-assign or consumable-checkout requests both succeed past the actual available count | Tampering / Denial of Service (resource-exhaustion of a scarce pool) | Guard clause inside `find_one_and_update`'s filter (Pattern 1/2) — MongoDB's single-document atomicity guarantees exactly one of two concurrent racing writes observes the pre-decrement state and succeeds |
| IDOR — assigning/reclaiming/checking out a license/consumable/component belonging to another tenant | Information Disclosure / Elevation of Privilege | `TenantIsolatedCollection` auto-injects `tenantId` into every query on `db.licenses`/`db.consumables`/`db.components` — a cross-tenant id resolves to "not found" (404), never another tenant's data. Verified mechanism: `backend/database.py:22-45` |
| History-record key confusion polluting an unrelated asset's audit trail (Pitfall 2) | Tampering (of an audit trail's integrity/completeness) | `licenseId`/`consumableId` as the top-level lookup key, never `assetId`, even when the *value* of a `targetId` happens to reference an asset — enforced by the regression test in the Validation Architecture table |
| Unbounded seat-array growth via repeated assign/reclaim cycles inflating the license document | Denial of Service (document-size/write-amplification) | Bounded in practice by `seatsTotal` (an admin-set cap); no unbounded growth path exists since `assignedSeats` can never exceed `seatsTotal` entries at once (each entry consumed a seat that must be reclaimed before another can be assigned) |

## Sources

### Primary (HIGH confidence — verified via Read/grep of the actual codebase, this session)
- `backend/itam_lifecycle_service.py` — full read: `write_history` (fully generic), `list_history` (hardcoded `assetId` filter — the source of the D-02 partial-reuse finding), `_apply_known_delta`, `_revert_on_history_failure`
- `backend/itam_models.py` — full read: `CheckoutRequest`'s `targetType`/`targetId` Literal pattern (`"user"`/`"location"`, NOT `"user"`/`"asset"` — confirmed this phase needs a new Literal pair, not literal reuse of `CheckoutRequest`), `_validate_iso8601_date`, `ConfigDict(extra="forbid")` convention, `MAX_LABEL_SHEET_ASSETS`-style explicit-cap-in-handler convention
- `backend/itam_lifecycle_endpoints.py` — full read (535 lines — confirmed over the 500-line CLAUDE.md cap): `checkout_asset`/`checkin_asset`/`mark_asset_audited`'s guard-in-filter/BEFORE-pre-image/`_apply_known_delta`/`write_history`-with-revert-on-failure shape, `_resolve_target` (confirmed hardcoded to `"user"`/`"location"` — the source of Pitfall 3), `list_assignment_history` (sub-resource route pattern)
- `backend/itam_asset_endpoints.py` — full read (158 lines): `_require_itam_admin`, `next_asset_tag`, confirms this file has NO `GET /{asset_id}` (that lives in `asset_endpoints.py`)
- `backend/itam_catalog_endpoints.py` — full read: `CATALOG_KINDS`/`_resolve_models` generic-dispatch shape (the rejected alternative in Standard Stack)
- `backend/itam_catalog_service.py` — full read: fieldset validation pattern, confirms no existing sub-resource-attachment analog beyond what `itam_lifecycle_endpoints.py`'s `/history` route already demonstrates
- `backend/asset_endpoints.py:158-232` (`get_asset_details`) — confirms this file (511 lines — also over the CLAUDE.md cap) is where a literal embedded-components-in-detail-response approach would have to go, and why the sub-resource-route alternative (Pattern 3) is preferred instead
- `backend/compliance_evidence_endpoints.py:416-421` (`get_control_evidence`) — the out-of-ITAM precedent for a sub-resource route scoped by parent id in the URL path, not embedded in the parent's own GET response
- `backend/compliance_remediation_sla_service.py:112-230` — full read of the tenant-isolation-in-a-background-scheduler pattern (`run_sla_pass` iterating all tenants' tasks with no ambient tenant context), cited as evidence for why Phase 60 should NOT introduce an equivalent scheduler without a requirement-driven reason
- `backend/database.py:1-150` — `TenantIsolatedCollection`/`TenantIsolatedDatabase` full mechanics and the exact exemption allowlist (Pitfall 4's basis), plus existing `assignment_history` index definitions at lines 292-296
- `backend/rbac_utils.py:1-110` — confirms `manage:assets` is the only ITAM-specific permission that exists; no more granular sub-permission was introduced for Phases 56/57/58, supporting the "reuse `_require_itam_admin` as-is" recommendation for question 6
- `.planning/ROADMAP.md` (Phase 60 section, lines 921-937 and Phase 59 section, lines ~872-920 area) — exact requirement/success-criteria wording used for the expiry-alert-vs-visibility textual comparison
- `.planning/REQUIREMENTS.md` — exact ITAM-LIC-01/02/03 locked text
- `backend/venv/bin/python` direct import check — `fastapi==0.140.0`, `pydantic==2.13.4`, `pymongo==4.17.0` all installed and importable this session
- `pgrep -a mongod` — confirmed a live mongod process this session
- `wc -l` on every file discussed above — exact line counts confirmed, not estimated

### Secondary (MEDIUM confidence)
- None this session — every claim in this document traces to a direct Read/grep of the actual codebase or the locked CONTEXT.md/REQUIREMENTS.md/ROADMAP.md text, not an external web source. This phase's domain is entirely internal-codebase-pattern research, not a new external library/framework.

### Tertiary (LOW confidence — flagged for validation)
- A3 (license expiry scheduler decision) — grounded in a textual-wording comparison, not an explicit CONTEXT.md ruling; flagged in Open Questions for a final human/planner check
- A1 (embedded array vs. separate collection for `assignedSeats`) — both are defensible engineering choices; this research recommends one but flags the alternative as equally valid

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; every library version verified via direct import in `backend/venv` this session
- Architecture: HIGH — every pattern (atomic guard, append-only history reuse, polymorphic target, sub-resource route) is either a direct verified precedent already shipped in this exact codebase, or a small, explicitly-justified modification of one (the two new `list_*_history` functions, the `assignedSeats` array)
- Pitfalls: HIGH — all four pitfalls are grounded in concrete facts read directly from the actual source this session (hardcoded `assetId` filter key, hardcoded `"user"`/`"location"` Literal branches, the exemption allowlist's exact contents), not generic boilerplate

**Research date:** 2026-08-05
**Valid until:** 2026-09-04 (30 days — stable domain: this is internal-codebase-pattern reuse, not an external library whose API could change; the only expiry risk is if Phase 59, running concurrently, changes a shared file this research also reads, e.g. `itam_models.py` or `router_registry.py` — the planner should re-diff those two files against this research's line-count/content assumptions immediately before planning if Phase 59 has already merged by then)
