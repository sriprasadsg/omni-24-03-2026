# Phase 59: Procurement & Finance (Warranty & Depreciation) - Research

**Researched:** 2026-08-05
**Domain:** FastAPI backend — additive financial fields on the existing `assets`/asset-Model catalog entities, a tenant-isolation-safe background sweep for warranty-expiry alerts, and a pure read-time straight-line depreciation calculator. Backend/API-only (Phase 61 is the sole frontend consumer).
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 (Money Representation, Claude's discretion, auto-selected):** Purchase cost and computed book value are stored/returned as integer cents (`purchaseCostCents`, not a bare float dollar amount) — avoids floating-point drift in depreciation arithmetic. CONTEXT.md states "No prior money-handling convention exists elsewhere in this codebase to follow instead" — **this research found that claim is not fully accurate; see Assumptions Log / Standard Stack for the correction.** The cents choice itself is still correct and is retained.

**D-02 (Supplier Reference, auto-selected):** Purchase record references the existing Phase 56 Supplier catalog entity by id (`supplierId`), not a free-text supplier name — consistent with how `AssetModelCreate` already references `manufacturerId`/`categoryId` by id rather than by name.

**D-03 (Warranty Expiry Alert Delivery, auto-selected):** A background sweep (mirroring `compliance_remediation_sla_service.py`'s `run_sla_pass`/`start_remediation_sla_scheduler` pattern — raw `db` handle + explicit per-tenant `set_tenant_id`, never `get_database()`) finds assets whose warranty expiry falls within a per-tenant-configurable alert window and calls `notification_service.send_notification(db, tenant_id, event_type, payload)`. This is the highest-severity risk class flagged in this milestone's research (STATE.md) — the scheduler MUST NOT use the tenant-isolated request-scoped `db` helper.
**Alert window default:** follow the same lookup-order precedent as `get_sla_at_risk_window` (per-tenant config doc → global config doc → hard-coded default) rather than a single hard-coded constant.

**Correction to D-03 required — see Common Pitfalls, Pitfall 1:** the literal call `notification_service.send_notification(db, tenant_id, event_type, payload)` **crashes** when `db` is the raw, unwrapped `mongodb.db` handle the sweep must use per this same decision's own tenant-isolation requirement (`send_notification` does `db._db.notification_rules...` with no defensive unwrap, unlike `get_sla_at_risk_window`). The actually-correct call for a raw-db background sweep, verified against the exact file D-03 says to clone, is `get_notification_service(db).send_alert(...)` — this is what `compliance_remediation_sla_service.py::run_sla_pass` itself calls, not `notification_service.send_notification`. Both delivery paths exist in this codebase and are documented below (Architecture Patterns, Pattern 3) so the planner can choose deliberately rather than by accident.

**D-04 (Depreciation Schedule, auto-selected):** Straight-line only (no reducing-balance or other method). Schedule params (useful-life years, salvage value) live on the Model entity (extend `AssetModelCreate`/`AssetModelUpdate` in `backend/itam_models.py`), not on the individual asset — matches ITAM-FIN-03's explicit "assigned at the model level" wording. Book value floors at the salvage value (never negative or below salvage) and is computed purely at read time from `purchaseDate`/`purchaseCostCents` + the Model's depreciation params — no stored/cached book value field, no background job for this part.

### Claude's Discretion

- Exact per-tenant config doc `type` string and field names for the warranty alert window (mirror `evidence_staleness`/`remediation_sla_at_risk` naming convention) — this research resolves it to `type: "itam_warranty_alert_window"`, field `windowDays` (see Pattern 2).
- Whether partial-year depreciation is prorated by day/month or only whole-year — this research resolves it to **whole-year-boundary** (simpler, matches D-04's own stated preference) — see Pattern 4.
- Exact webhook/notification `event_type` string for warranty-expiry alerts — this research resolves it to `itam.warranty_expiring` (see Pattern 3 and Pitfall 2 for why this string alone is not sufficient to make tenant-configurable rule-based routing work without an additional change).
- PO number format/validation (free text vs pattern) — no constraint specified, treated as free text (`Optional[str]`, no regex).

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope (per 59-CONTEXT.md).

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ITAM-FIN-01 | Asset carries purchase cost, purchase date, PO number, and supplier | Architecture Patterns Pattern 1 (nullable purchase fields on `ManualAssetCreate` + a dedicated PATCH-purchase route usable on any asset regardless of source), Standard Stack (cents representation + correction), Common Pitfalls 4/5 |
| ITAM-FIN-02 | Asset warranty is tracked (purchase date + warranty period) with expiry alerts, routed through the existing notification/webhook infrastructure | Architecture Patterns Pattern 2 (alert-window config lookup), Pattern 3 (corrected notification call + idempotency), Common Pitfalls 1/2/3, Runtime State Inventory (n/a — additive only) |
| ITAM-FIN-03 | Asset book value is computed via a straight-line depreciation schedule assigned at the model level, computed at read time (no external accounting/GL integration) | Architecture Patterns Pattern 4 (pure depreciation function, whole-year proration), Pattern 5 (Model-entity depreciation params, fieldset-collision avoidance), Don't Hand-Roll |

</phase_requirements>

## Summary

Phase 59 is disciplined extension of three already-established seams, plus one background sweep that must be built with unusual care because this exact milestone (v4.0) has already been flagged — twice, in STATE.md and again by name in this phase's own CONTEXT.md — as carrying the platform's highest-severity recurring bug class: a background scheduler that accidentally uses the request-scoped, ContextVar-based `TenantIsolatedDatabase` (`get_database()`) instead of a raw Motor handle with explicit per-document `tenantId` extraction. `compliance_remediation_sla_service.py` is the canonical correct pattern and this phase's warranty sweep should clone its shape almost line-for-line — but this research found that a literal clone would introduce a **new** bug: CONTEXT.md's locked D-03 wording calls `notification_service.send_notification(db, tenant_id, event_type, payload)`, and that specific function unconditionally does `db._db.notification_rules.find(...)` with no defensive "raw Motor db has no `._db`" fallback (unlike `get_sla_at_risk_window`, which does have that fallback and is the function D-03 also names as the pattern to clone for the alert window). Called with a raw `mongodb.db` handle — which D-03 requires the sweep to use — `send_notification` raises `AttributeError` on every single sweep pass. The actually-correct call, verified by reading `compliance_remediation_sla_service.py::run_sla_pass` itself (the exact function D-03 says to clone), is `get_notification_service(db).send_alert(...)` — this is what that file's own SLA-breach alert path calls, and it works correctly with either a raw or a wrapped `db` because `NotificationService` never unwraps or re-derives tenant context; it takes `tenant_id` as an explicit parameter and writes directly to `db.notifications` (the same collection `GET /api/notifications` reads from). This is documented in full in Pitfall 1 and Pattern 3 below, with a recommended dual-path design: `send_alert` for the guaranteed-to-work in-app notification, plus an optional second call into the tenant-isolation-safe wrapped path for the rule/channel-routed "real" notification/webhook infrastructure Phase 21 built (`notification_service.send_notification` + `notification_endpoints.py`'s `/rules`/`/channels`), which requires two small additive changes (`VALID_EVENTS` set, `RuleCreate.event_type` Literal) to actually be usable for a new event type — see Pitfall 2.

The purchase/warranty fields themselves are a straightforward, already-well-precedented extension: `ManualAssetCreate` in `backend/itam_models.py` (227 lines, plenty of headroom under the 500-line CLAUDE.md cap) already carries five `Optional[str]` catalog-reference fields (`manufacturerId`, `modelId`, `categoryId`, `supplierId`, `locationId`) — adding `purchaseCostCents: Optional[int]`, `purchaseDate: Optional[str]`, `poNumber: Optional[str]`, and reusing the already-present `supplierId` is a direct continuation of that shape, not a new pattern. Critically, `ASSET_SOURCE_AGENT` is never actually written anywhere in the codebase today (grep confirms zero call sites) — agent-discovered assets simply lack the `assetSource` key and every ITAM field is read-time-defaulted, exactly like `lifecycleStatus`'s Phase-56-established precedent. This confirms purchase/warranty/depreciation fields must be nullable on every asset regardless of source, and — because agent-discovered assets have no "creation" flow an ITAM admin controls — the primary way these fields get populated for *any* asset (manual or agent-discovered) is a dedicated `PATCH /api/assets/{asset_id}/purchase` route, not the `POST` creation body alone.

Depreciation params belong on the Model entity per D-04, extending `AssetModelCreate`/`AssetModelUpdate` (`backend/itam_models.py:141-160`) with `usefulLifeYears: Optional[int]` and `salvageValueCents: Optional[int]` — siblings of the existing `fieldsets: List[FieldsetDef]` field, not participants in it (the fieldset mechanism is a *user-defined custom-field* registry per ITAM-CAT-04; depreciation policy is a first-class typed field like `modelNumber`, and mixing the two would make `validate_fieldsets`'s key-uniqueness check silently interact with a field it was never designed to know about).

Every new route (purchase PATCH, warranty-status GET, book-value GET) is a new file, not an extension of `itam_asset_endpoints.py` (158 lines, has headroom) or `itam_lifecycle_endpoints.py` (534 lines — **already over the 500-line CLAUDE.md cap** as shipped in Phase 57) or `asset_endpoints.py` (511 lines — also already over cap). The established one-concern-per-file convention (`itam_catalog_endpoints.py` / `itam_asset_endpoints.py` / `itam_lifecycle_endpoints.py` / `itam_label_endpoints.py`, each with its own paired `*_service.py` where there is non-trivial pure logic) extends cleanly to a new `itam_finance_endpoints.py` + `itam_finance_service.py` pair, registered in `router_registry.py` immediately after `itam_label_endpoints` (currently the last ITAM entry, line 85).

**Primary recommendation:** Extend `backend/itam_models.py` with nullable purchase/warranty fields on `ManualAssetCreate` (for the manual-creation-time case) plus a new `AssetPurchaseUpdate` request model (for the PATCH-any-asset case), and `usefulLifeYears`/`salvageValueCents` on `AssetModelCreate`/`AssetModelUpdate`. Add `backend/itam_finance_service.py` (pure `compute_book_value`, pure `compute_warranty_status`, and the background sweep `run_warranty_alert_pass(db)` / `start_warranty_alert_scheduler(db)` cloned from `compliance_remediation_sla_service.py` but calling `get_notification_service(db).send_alert(...)`, not `notification_service.send_notification`) and `backend/itam_finance_endpoints.py` (RBAC-gated via the existing `_require_itam_admin` import from `itam_asset_endpoints.py`, multi-segment routes under `/api/assets/{asset_id}/...` so nothing shadows or is shadowed by `asset_endpoints.py`'s single-segment `GET /{asset_id}`). Register the new router in `router_registry.py` after `itam_label_endpoints`, and register the new scheduler in `app_startup.py` alongside the three existing raw-db schedulers (`start_escalation_scheduler`, `start_close_loop_scheduler`, `start_remediation_sla_scheduler`, lines 604-626). No new third-party dependency is required anywhere in this phase.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Purchase cost/date/PO/supplier storage on an asset | Database / Storage | API / Backend | Additive fields on the existing `assets` collection document — no new collection, mirrors how `manufacturerId`/`locationId` already live directly on the asset doc |
| Purchase-field write (create-time or PATCH) | API / Backend | Database / Storage | `ManualAssetCreate` extension + new `AssetPurchaseUpdate` PATCH route, RBAC-gated (`manage:assets`), tenant-scoped via `TenantIsolatedDatabase` |
| Warranty-expiry detection sweep | API / Backend | Database / Storage | A raw-db, tenant-isolation-safe background loop reading `assets` directly (never the request-scoped wrapper) — same tier split as `compliance_remediation_sla_service.py::run_sla_pass` |
| Warranty-expiry alert delivery | API / Backend | — | Routed through the existing `NotificationService`/`notification_manager`/`webhook_service` surfaces — no new delivery channel type is introduced this phase |
| Depreciation policy definition (useful life, salvage value) | Database / Storage | API / Backend | Lives on the Model entity (`asset_models` collection), not the asset — read once per asset-book-value computation, never duplicated per-asset |
| Book value computation | API / Backend | — | Pure function, computed at GET time from `purchaseDate`/`purchaseCostCents` (on the asset) + `usefulLifeYears`/`salvageValueCents` (on the asset's Model) — no persistence, no background job |
| Alert-window tenant configuration | Database / Storage | API / Backend | `system_settings` doc, tenant-doc → global-doc → hardcoded-default lookup order, cloned from `get_sla_at_risk_window` |

## Package Legitimacy Audit

**Not applicable this phase — no new third-party dependency is introduced.** Per the phase brief's explicit item 8, this research checked and confirms:

- Money-as-cents arithmetic needs no library (plain Python `int` arithmetic; see Pattern 4).
- The background-sweep scheduler pattern (`asyncio.sleep` polling loop) is already the established in-repo idiom (`compliance_remediation_sla_service.py`, `ticketing_bridge.py`, `tickets_escalation_service.py`) — no `apscheduler`/`celery`/cron-library is needed or should be introduced.
- Notification delivery reuses `notification_service.py`/`notification_manager.py`/`webhook_service.py` verbatim — no new notification/webhook client library.
- Date arithmetic reuses Python's stdlib `datetime`, exactly as `compliance_remediation_sla_service.py` and `itam_lifecycle_endpoints.py` already do — no `dateutil`/`arrow`/`pendulum`.

**Packages removed due to `[SLOP]` verdict:** none (none proposed).
**Packages flagged as suspicious `[SUS]`:** none (none proposed).

## Standard Stack

### Core
No new libraries. This phase is 100% additive Pydantic models, one new pure-computation service module, one new FastAPI router, and stdlib `datetime`/`asyncio` — all already installed and already exercised by the exact files this phase clones from.

### Money Representation — correction to CONTEXT.md's "no prior convention" claim
CONTEXT.md's D-01 states "No prior money-handling convention exists elsewhere in this codebase to follow instead." This research found that is not fully accurate, though it does not change the recommendation:

| File | Convention | Note |
|------|-----------|------|
| `backend/payment_billing_endpoints.py:29` | `amount: int = Field(..., gt=0, description="Charge amount in smallest currency unit (e.g. cents)...")` | **A real precedent for integer-cents exists** — this is the closest analog to D-01's `purchaseCostCents` choice, and its docstring even names "cents" explicitly. `[VERIFIED: backend/payment_billing_endpoints.py:29 — read this session]` |
| `backend/billing_endpoints.py:34` | `amount: float` (bare dollar float, e.g. `299`) | Contradicts the cents convention — this file uses plain float dollars throughout. `[VERIFIED: backend/billing_endpoints.py:34 — read this session]` |
| `backend/risk_fair_service.py` | Plain `float` loss-magnitude dollar values (FAIR quantification, Phase 31) | Also float dollars, not cents. `[VERIFIED: backend/risk_fair_service.py — read this session]` |
| `backend/finops_service.py` | Plain `float` spend amounts, `round(..., 2)` | Also float dollars. `[VERIFIED: backend/finops_service.py — read this session]` |

**Net assessment:** the codebase's money-handling convention is genuinely inconsistent (3 of 4 surfaces use float dollars; 1 uses integer cents with an explicit docstring naming the unit). D-01's cents choice is still the right call for this phase specifically — depreciation arithmetic (dividing a purchase cost by a useful-life-in-years count, subtracting a per-year depreciation amount repeatedly) is exactly the kind of repeated-division-then-subtraction pattern where float drift compounds — but the planner/task author should not claim "this establishes the codebase's first money convention" in commit messages or docs; it should be framed as "follows `payment_billing_endpoints.py`'s existing cents precedent," since that file already exists and already uses the word "cents" in its own field description.

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| stdlib `datetime`/`timezone` | n/a (stdlib) | ISO-8601 date parsing, `+00:00`-normalized comparisons | Reuse `itam_models.py::_validate_iso8601_date` (line 163) for `purchaseDate` — do not write a second date validator |
| stdlib `asyncio` | n/a (stdlib) | Polling-loop background sweep | `asyncio.sleep(N)` loop, identical shape to `start_remediation_sla_scheduler` |
| `pytest` + `pytest-asyncio` | already installed | Test framework | Matches `test_itam_lifecycle.py`/`test_compliance_remediation_sla.py` convention |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Integer cents (`purchaseCostCents`) | Plain float dollars, matching the more common in-repo pattern (`billing_endpoints.py`, `finops_service.py`, `risk_fair_service.py`) | Float dollars are more common in this codebase numerically, but every one of those existing float-money surfaces is a single-computation or accumulate-and-round context (a subscription price, a spend total), not a repeated per-year subtraction loop the way straight-line depreciation is. Cents avoids compounding rounding error across N years of subtraction and matches the one existing precedent that already names "cents" explicitly. Recommendation: keep D-01 as-is. |
| A dedicated `itam_finance_endpoints.py`/`itam_finance_service.py` pair (recommended) | Extending `itam_asset_endpoints.py` (158 lines) directly | `itam_asset_endpoints.py` has headroom, but mixing "create a manual asset" concerns with "manage an asset's financial record + compute book value" concerns in one file breaks the one-concern-per-file convention every other ITAM phase has followed (catalog / asset-create / lifecycle / label, each its own file). A new file is the lower-risk, more consistent choice, and it also sidesteps the fact that `itam_lifecycle_endpoints.py` and `asset_endpoints.py` are both already over the 500-line cap. |
| `run_warranty_alert_pass` calling `get_notification_service(db).send_alert(...)` (recommended) | Calling `notification_service.send_notification(db, tenant_id, event_type, payload)` literally as D-03's wording states | See Pitfall 1 — the literal call crashes with a raw db handle. `send_alert` is what the exact file D-03 names as the pattern to clone actually calls itself. |

**Installation:** None — no new dependency.

## Architecture Patterns

### System Architecture Diagram

```
Client (Phase 61 frontend, out of scope this phase)
        │
        │  PATCH /api/assets/{id}/purchase {purchaseCostCents, purchaseDate,
        │                                    poNumber, supplierId, warrantyMonths}
        │  GET   /api/assets/{id}/warranty        (status + days-to-expiry)
        │  GET   /api/assets/{id}/book-value       (computed depreciation)
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ itam_finance_endpoints.py (FastAPI router, /api/assets prefix)    │
│  - _require_itam_admin (RBAC: manage:assets) — reused verbatim    │
│  - tenant-scoped asset + asset-Model lookup via TenantIsolatedDB  │
│  - 404 for unknown/cross-tenant asset id (same pattern as         │
│    itam_lifecycle_endpoints.py / itam_label_endpoints.py)         │
└───────────────┬─────────────────────────────────────────────────┘
                │  asset dict + (if modelId set) model dict
                ▼
┌──────────────────────────────────────────────────────────────────┐
│ itam_finance_service.py (pure functions — no DB/FastAPI import,   │
│ except the two sweep entry points which take db as a parameter)   │
│                                                                    │
│  compute_warranty_status(purchase_date, warranty_months, now)     │
│    -> {"expiresAt": ..., "status": "active|expiring|expired|none"}│
│                                                                    │
│  compute_book_value(purchase_date, purchase_cost_cents,           │
│                      useful_life_years, salvage_value_cents, now) │
│    -> book_value_cents (int), floored at salvage_value_cents      │
│       whole-year straight-line: cost - (years_elapsed * annual)   │
│                                                                    │
│  run_warranty_alert_pass(db)         <- raw mongodb.db, never     │
│    for each asset with a warranty expiry inside the tenant's         wrapped
│    alert window: get_notification_service(db).send_alert(...)     │
│    idempotency: sets warrantyAlertSentAt on the asset so a         │
│    later pass in the same window never re-alerts (Pitfall 3)      │
│                                                                    │
│  start_warranty_alert_scheduler(db) <- asyncio.sleep loop, called  │
│    from app_startup.py with raw mongodb.db, mirrors                │
│    start_remediation_sla_scheduler exactly                        │
└───────────────┬─────────────────────────────────────────────────┘
                │
                ▼
        get_notification_service(db).send_alert(..., channels=[])
                │  writes db.notifications (in-app feed, GET /api/notifications)
                ▼
        (optional, additive) notification_service.send_notification(
            wrapped_db, tenant_id, "itam.warranty_expiring", payload)
                │  matches tenant-configured notification_rules -> channels
                │  (Slack/webhook/email) — requires VALID_EVENTS +
                │  RuleCreate.event_type Literal extension (Pitfall 2)
                ▼
        Tenant-configured Slack/webhook/email delivery (Phase 21 infra)
```

### Recommended Project Structure
```
backend/
├── itam_models.py              # EXTEND — purchase/warranty fields on ManualAssetCreate,
│                                #   new AssetPurchaseUpdate model, usefulLifeYears/
│                                #   salvageValueCents on AssetModelCreate/Update
├── itam_finance_service.py     # NEW — compute_warranty_status, compute_book_value
│                                #   (pure), run_warranty_alert_pass, start_warranty_
│                                #   alert_scheduler (raw-db sweep)
├── itam_finance_endpoints.py   # NEW — PATCH .../purchase, GET .../warranty,
│                                #   GET .../book-value
├── router_registry.py          # EXTEND — register itam_finance_endpoints after
│                                #   itam_label_endpoints
├── app_startup.py              # EXTEND — register start_warranty_alert_scheduler
│                                #   alongside the 3 existing raw-db schedulers
├── notification_service.py     # EXTEND (optional path only) — add
│                                #   "itam.warranty_expiring" to VALID_EVENTS
├── notification_endpoints.py   # EXTEND (optional path only) — add
│                                #   "itam.warranty_expiring" to RuleCreate.event_type
└── tests/
    └── test_itam_finance.py    # NEW — mirrors test_itam_lifecycle.py /
                                 #   test_compliance_remediation_sla.py conventions
```

### Pattern 1: Nullable purchase fields, populated at create-time OR via PATCH (ITAM-FIN-01)
**What:** `ManualAssetCreate` gains four `Optional` fields so a manual asset can carry purchase data from creation; a separate `AssetPurchaseUpdate` PATCH model lets *any* asset (manual or agent-discovered) have its purchase/warranty record set or corrected later, since agent-discovered assets have no admin-controlled "create" step to attach financial data to.
**When to use:** Both the manual-asset creation path (`itam_asset_endpoints.py::create_manual_asset`) and a new `PATCH /api/assets/{id}/purchase` route in `itam_finance_endpoints.py`.
**Example:**
```python
# Source: backend/itam_models.py:76-93 (ManualAssetCreate, existing shape being extended)
class ManualAssetCreate(BaseModel):
    name: str
    assetTag: Optional[str] = None
    manufacturerId: Optional[str] = None
    modelId: Optional[str] = None
    categoryId: Optional[str] = None
    supplierId: Optional[str] = None          # ITAM-FIN-01 (D-02): already present, reused verbatim
    locationId: Optional[str] = None
    serialNumber: Optional[str] = None
    type: Optional[str] = None
    notes: Optional[str] = None
    lifecycleStatus: LifecycleStatus = DEFAULT_LIFECYCLE_STATUS
    customFields: Dict[str, Any] = Field(default_factory=dict)
    # NEW (ITAM-FIN-01/02):
    purchaseCostCents: Optional[int] = Field(None, ge=0)
    purchaseDate: Optional[str] = None        # ISO-8601, validated below
    poNumber: Optional[str] = None            # free text, no format constraint (CONTEXT.md)
    warrantyMonths: Optional[int] = Field(None, ge=0)

    model_config = ConfigDict(extra="forbid")

    _validate_purchase_date = field_validator("purchaseDate")(_validate_iso8601_date)  # reuse, do not re-implement


class AssetPurchaseUpdate(BaseModel):
    """PATCH /api/assets/{asset_id}/purchase — the primary way an agent-discovered
    asset (which has no ITAM-admin-controlled creation step) gets its financial
    record populated. Also usable to correct a manual asset's record post-creation."""
    purchaseCostCents: Optional[int] = Field(None, ge=0)
    purchaseDate: Optional[str] = None
    poNumber: Optional[str] = None
    supplierId: Optional[str] = None
    warrantyMonths: Optional[int] = Field(None, ge=0)

    model_config = ConfigDict(extra="forbid")

    _validate_purchase_date = field_validator("purchaseDate")(_validate_iso8601_date)
```
`supplierId`, if supplied, should be validated to exist against `db.suppliers` before the write — same shape as `itam_asset_endpoints.py::create_manual_asset`'s existing `manufacturerId`/`modelId` existence checks (lines 87-100).

### Pattern 2: Per-tenant configurable warranty alert window (clones `get_sla_at_risk_window`)
**What:** A `system_settings` doc lookup: per-tenant doc → global doc → hardcoded default. Cloned field-for-field from `compliance_remediation_sla_service.py::get_sla_at_risk_window` (lines 112-152), which itself was cloned from `evidence_staleness.get_staleness_threshold()`.
**When to use:** Inside `run_warranty_alert_pass` before deciding whether a given asset's warranty falls inside the alert window.
**Example:**
```python
# Source: backend/compliance_remediation_sla_service.py:112-152 (pattern cloned, renamed)
_DEFAULT_WARRANTY_ALERT_WINDOW_DAYS = 30  # a small, justified default — tunable, not locked

async def get_warranty_alert_window(db, tenant_id) -> int:
    """Lookup order: per-tenant doc -> global doc -> hardcoded default (D-02 precedent).
    type: "itam_warranty_alert_window", field: "windowDays"."""
    def _safe_window(raw_val: int) -> int:
        return max(1, raw_val)

    # Dual call-site guard — identical to get_sla_at_risk_window's own comment:
    # this function may be called from either the raw-db sweep or (in principle)
    # a future request-scoped caller passing a TenantIsolatedDatabase.
    raw = db._db if hasattr(db, "_db") else db

    if tenant_id:
        doc = await raw.system_settings.find_one(
            {"type": "itam_warranty_alert_window", "tenantId": tenant_id}
        )
        if doc and isinstance(doc.get("windowDays"), int):
            return _safe_window(doc["windowDays"])
    doc = await raw.system_settings.find_one(
        {"type": "itam_warranty_alert_window", "tenantId": {"$exists": False}}
    )
    if doc and isinstance(doc.get("windowDays"), int):
        return _safe_window(doc["windowDays"])
    return _DEFAULT_WARRANTY_ALERT_WINDOW_DAYS
```

### Pattern 3: Corrected notification call for the raw-db sweep, with idempotency
**What:** The alert delivery call itself, plus the idempotency guard CONTEXT.md's D-03 explicitly calls out as a requirement ("avoid double-alerting").
**When to use:** Inside `run_warranty_alert_pass`, once an asset's warranty expiry is confirmed inside the tenant's alert window.
**Example:**
```python
# Source: backend/compliance_remediation_sla_service.py:211-306 (run_sla_pass, structure
# cloned) + backend/notification_service.py:26-86 (send_alert, the actually-correct call
# for a raw-db caller — see Pitfall 1 for why notification_service.send_notification
# is NOT the right call here despite CONTEXT.md D-03's literal wording)
from notification_service import get_notification_service

async def run_warranty_alert_pass(db) -> None:
    try:
        query = {
            "warrantyMonths": {"$exists": True, "$ne": None},
            "purchaseDate": {"$exists": True, "$ne": None},
        }
        cursor = db.assets.find(query, {"_id": 0})
        async for asset in cursor:
            tenant_id = asset.get("tenantId")
            if not tenant_id:
                continue  # same T-44-03-shaped guard as the SLA sweep

            window = await get_warranty_alert_window(db, tenant_id)
            status = compute_warranty_status(
                asset["purchaseDate"], asset["warrantyMonths"], datetime.now(timezone.utc)
            )
            if status["status"] not in ("expiring", "expired"):
                continue

            # Idempotency (D-03's explicit requirement): never re-alert for the
            # same asset while it stays in the same alert window pass-to-pass.
            # Cloned in spirit from run_sla_pass's `new_level <= current_level: continue`
            # tier-guard — here the "tier" is simply "already alerted this cycle".
            already_alerted_at = asset.get("warrantyAlertSentAt")
            if already_alerted_at:
                continue

            recipients = await _tenant_admin_emails(db, tenant_id)  # clone helper, same shape
            if recipients:
                try:
                    svc = get_notification_service(db)  # works with raw OR wrapped db —
                                                          # NotificationService never
                                                          # unwraps db, just uses it directly
                    await svc.send_alert(
                        title="Asset warranty expiring",
                        message=f"Asset {asset.get('assetTag', asset['id'])} warranty "
                                f"{status['status']} on {status['expiresAt']}.",
                        severity="warning",
                        recipients=recipients,
                        tenant_id=tenant_id,
                        channels=[],  # in-app only, mirrors run_sla_pass's own call
                        metadata={"asset_id": asset["id"], "event": "itam.warranty_expiring"},
                    )
                except Exception:
                    pass  # non-fatal — one failed alert never aborts the sweep

            await db.assets.update_one(
                {"id": asset["id"], "tenantId": tenant_id},
                {"$set": {"warrantyAlertSentAt": datetime.now(timezone.utc).isoformat()}},
            )
    except Exception as exc:
        logger.error("Warranty alert pass failed: %s", exc)


async def start_warranty_alert_scheduler(db) -> None:
    """Must receive db as a raw parameter — see module docstring precedent.
    Caller (app_startup.py) supplies the unwrapped mongodb.db handle."""
    while True:
        await run_warranty_alert_pass(db)
        await asyncio.sleep(3600)  # hourly is sufficient for a days-scale alert window
```
**Optional additive path (not required to satisfy ITAM-FIN-02, but closer to the literal "webhook infrastructure" wording):** to also route through the tenant-configured rule/channel system Phase 21 built (`notification_rules`/`notification_channels`, read by `notification_service.send_notification`), the sweep would need to build (or receive) a `TenantIsolatedDatabase(db._db if hasattr ... else db)`-equivalent wrapper with `set_tenant_id(tenant_id)` called first (the `autonomous_remediation_service.py` per-tenant-loop-iteration pattern, lines 144/185 etc.) so `send_notification`'s `db._db.notification_rules...` calls resolve correctly, and would additionally require the two `VALID_EVENTS`/`RuleCreate` extensions in Pitfall 2. This is a real, working option — just not the one-line drop-in D-03's wording implied, and it duplicates delivery (both the guaranteed in-app alert and the optional rule-routed one) rather than replacing it, since `send_alert`'s in-app write is what makes the "Admin sees each asset's warranty status" half of the ROADMAP success criterion true even for tenants who never configure a notification rule.

### Pattern 4: Pure straight-line book-value computation, whole-year proration (ITAM-FIN-03)
**What:** A pure function, no DB access, computed at GET time — never persisted.
**When to use:** `GET /api/assets/{asset_id}/book-value`.
**Example:**
```python
# New pattern for this codebase — no direct precedent, but structurally identical in
# spirit to itam_lifecycle_endpoints.py's overdue_audit_report: read-time-only
# computation against a fixed policy, never a background job or stored field.
def compute_book_value(
    purchase_date: str,
    purchase_cost_cents: int,
    useful_life_years: int,
    salvage_value_cents: int,
    now: datetime,
) -> Dict[str, Any]:
    """Straight-line depreciation, whole-year boundary proration (CONTEXT.md
    Claude's Discretion — simpler than day/month proration, and D-04's own
    wording implies a coarse-grained schedule is acceptable).

    Returns {"bookValueCents": int, "yearsElapsed": int, "annualDepreciationCents": int}.
    Floors at salvage_value_cents — never negative, never below salvage (D-04).
    """
    purchase_dt = datetime.fromisoformat(purchase_date.replace("Z", "+00:00"))
    if purchase_dt.tzinfo is None:
        purchase_dt = purchase_dt.replace(tzinfo=timezone.utc)

    years_elapsed = max(0, now.year - purchase_dt.year - (
        1 if (now.month, now.day) < (purchase_dt.month, purchase_dt.day) else 0
    ))
    years_elapsed = min(years_elapsed, useful_life_years)  # never depreciate past useful life

    if useful_life_years <= 0:
        annual_depreciation_cents = 0
    else:
        annual_depreciation_cents = (purchase_cost_cents - salvage_value_cents) // useful_life_years

    book_value_cents = purchase_cost_cents - (years_elapsed * annual_depreciation_cents)
    book_value_cents = max(book_value_cents, salvage_value_cents)  # D-04 floor, never below salvage

    return {
        "bookValueCents": book_value_cents,
        "yearsElapsed": years_elapsed,
        "annualDepreciationCents": annual_depreciation_cents,
    }
```
**Missing-policy handling:** if the asset has no `modelId`, or the referenced Model has no `usefulLifeYears`/`salvageValueCents` set, the endpoint should return a clear structured response (e.g. `{"bookValueCents": None, "reason": "no_depreciation_policy_assigned"}`) rather than a 500 or a silently wrong `0`/`purchaseCostCents` value — this is a direct analog of Phase 58's Pitfall 3 (barcode-on-invalid-tag: fail with a clear 4xx/structured response, never a raw exception).

### Pattern 5: Depreciation policy fields on the Model entity, kept separate from fieldsets (ITAM-FIN-03)
**What:** `usefulLifeYears`/`salvageValueCents` as first-class typed fields on `AssetModelCreate`/`AssetModelUpdate`, siblings of `modelNumber` — deliberately NOT participants in the `fieldsets: List[FieldsetDef]` user-defined custom-field mechanism.
**When to use:** Extending `backend/itam_models.py:141-160`.
**Example:**
```python
# Source: backend/itam_models.py:141-160 (AssetModelCreate/Update, existing shape extended)
class AssetModelCreate(CatalogEntityCreate):
    modelNumber: Optional[str] = None
    manufacturerId: Optional[str] = None
    categoryId: Optional[str] = None
    fieldsets: List[FieldsetDef] = Field(default_factory=list)
    # NEW (ITAM-FIN-03, D-04):
    usefulLifeYears: Optional[int] = Field(None, gt=0)
    salvageValueCents: Optional[int] = Field(None, ge=0)

    model_config = ConfigDict(extra="forbid")


class AssetModelUpdate(CatalogEntityUpdate):
    modelNumber: Optional[str] = None
    manufacturerId: Optional[str] = None
    categoryId: Optional[str] = None
    fieldsets: Optional[List[FieldsetDef]] = None
    usefulLifeYears: Optional[int] = Field(None, gt=0)
    salvageValueCents: Optional[int] = Field(None, ge=0)

    model_config = ConfigDict(extra="forbid")
```
**Why not fold into fieldsets:** `validate_fieldsets`/`collect_field_defs`/`validate_custom_field_values` (`itam_catalog_service.py`) treat every fieldset key as a *user-defined, tenant-authorable* field with its own `type`/`required`/`options` shape, validated against arbitrary `customFields` values on individual assets. Depreciation policy is a fixed, platform-defined pair of numeric fields with a specific arithmetic meaning (Pattern 4 above) — putting it through the generic fieldset/customFields machinery would mean `compute_book_value` has to read `model_doc["customFields"]["usefulLifeYears"]` (a `Dict[str, Any]` with no schema guarantee at read time) instead of a typed Pydantic field, and would make the fieldset key-uniqueness validator implicitly responsible for a concern (financial policy) it was never designed to reason about. `_validate_asset_model_references` (`itam_catalog_endpoints.py:88-114`) is the existing per-kind post-validation hook for the `"models"` kind — no changes needed there for this addition since these are just two more optional typed fields, not references needing existence checks.

### Anti-Patterns to Avoid
- **Calling `notification_service.send_notification(raw_db, ...)` from the sweep:** crashes with `AttributeError: 'AsyncIOMotorDatabase' object has no attribute '_db'` — see Pitfall 1.
- **Persisting a `bookValueCents` field on the asset document:** D-04 explicitly forbids this — book value is always computed at GET time, never cached/stored (mirrors `overdue_audit_report`'s "computed at request time, not a background sweep" precedent for a *different* reason — that one is about audit staleness semantics, but the "don't persist a derived value that would drift" principle is the same).
- **Mixing depreciation policy into the `fieldsets` custom-field mechanism:** see Pattern 5's rationale.
- **Requiring purchase fields at asset creation time (making them non-nullable):** would break both the "agent-discovered assets have no admin-controlled create step" reality and Snipe-IT-parity expectations that financial data is often entered well after physical receipt of an asset.
- **Day/month-prorated depreciation without an explicit CONTEXT.md instruction to do so:** CONTEXT.md's own Claude's-Discretion note prefers whole-year unless research finds a reason not to — this research found none; whole-year is simpler and sufficient for a v1 straight-line schedule with no external GL integration to reconcile against.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ISO-8601 date parsing/validation for `purchaseDate` | A second regex/parser | `itam_models.py::_validate_iso8601_date` (line 163), reused via `field_validator` | Already exists, already the exact validator `CheckoutRequest.expectedReturnDate`/`AuditMarkRequest.auditedAt` use — a second implementation would be pure duplication and a drift risk |
| Tenant-safe background polling loop | A new scheduling abstraction | The `asyncio.sleep(N)`-loop idiom already used by `start_remediation_sla_scheduler`/`start_close_loop_scheduler`/`start_escalation_scheduler` | Three working precedents exist in this exact codebase; introducing `apscheduler`/`celery` for a fourth instance of the same shape would be pure scope creep and a new legitimacy-audit burden for zero benefit |
| In-app + rule-routed notification delivery | A new alerting/notification module | `NotificationService.send_alert` (in-app) + optionally `notification_service.send_notification`/`notification_endpoints.py` (rule-routed) | Both already exist, are already tested, and are already the "existing notification/webhook infrastructure" ITAM-FIN-02 explicitly says to route through |
| Straight-line depreciation math | A generic financial/amortization library | ~10 lines of plain integer arithmetic (Pattern 4) | Straight-line depreciation with a whole-year floor is genuinely simple, fixed arithmetic — not a "deceptively complex" problem worth a dependency, and D-04 explicitly forbids anything beyond straight-line |

**Key insight:** every piece of new logic in this phase is either (a) a direct continuation of an existing typed-field pattern (purchase fields, depreciation-policy fields) or (b) a clone of an existing, already-battle-tested background-sweep/notification-delivery shape. The only place genuinely new arithmetic is written is the ~10-line depreciation function, which is intentionally simple per D-04's own scope boundary (straight-line only, no external GL).

## Runtime State Inventory

Not applicable — this phase is purely additive (new optional fields, new collection reads, no rename/refactor/migration of existing data). Per the mandatory trigger check:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no existing field is renamed, no existing collection's key/shape changes | None |
| Live service config | None — no external service configuration is touched | None |
| OS-registered state | None | None |
| Secrets/env vars | None — no new secret or env var is introduced | None |
| Build artifacts | None — no packaging/build config changes | None |

**Nothing found in any category** — verified by grep across the full `backend/` tree for every field/collection name this phase introduces (`purchaseCostCents`, `purchaseDate`, `poNumber`, `warrantyMonths`, `usefulLifeYears`, `salvageValueCents`, `warrantyAlertSentAt`) confirming zero existing usages, i.e. this phase only adds new optional keys, never repurposes existing ones.

## Common Pitfalls

### Pitfall 1: CONTEXT.md D-03's literal notification call crashes with a raw db handle
**What goes wrong:** `notification_service.send_notification(db, tenant_id, event_type, payload)` (`backend/notification_service.py:509-551`) does `await db._db.notification_rules.find(...)` unconditionally at line 511. When `db` is the raw `mongodb.db` Motor handle the sweep is required to use (per D-03's own tenant-isolation mandate — never `get_database()`), `db._db` raises `AttributeError: 'AsyncIOMotorDatabase' object has no attribute '_db'` on the very first line of the function body. Every warranty-alert pass would fail on the first matching asset, and since `run_sla_pass`-shaped sweeps wrap their body in a top-level `try/except` that only logs, this failure would be **silent** — no alerts would ever be delivered, and nothing in the running app would visibly indicate it.
**Why it happens:** `notification_service.send_notification` was written to be called from a request-scoped caller (`notification_endpoints.py`'s test-channel/rule routes always pass `get_database()`'s `TenantIsolatedDatabase`, which does have a `._db` attribute per `database.py:115`) and has no defensive unwrap, unlike `get_sla_at_risk_window` (which D-03 also names, and which *does* have the `db._db if hasattr(db, "_db") else db` guard at `compliance_remediation_sla_service.py:139`). CONTEXT.md's D-03 wording assumed the two functions behave symmetrically; they do not.
**How to avoid:** Use `get_notification_service(db).send_alert(...)` instead (Pattern 3) — this is what `compliance_remediation_sla_service.py::run_sla_pass` itself calls (line 279-291), and it works correctly with either a raw or wrapped `db` because `NotificationService.__init__` just stores whatever `db` it's given and later does `self.db.notifications.insert_one(...)` directly — no unwrap needed, because raw Motor databases and `TenantIsolatedDatabase` both support attribute-style collection access. If rule/channel-routed delivery is also wanted, explicitly wrap with `set_tenant_id(tenant_id)` before calling `notification_service.send_notification`, mirroring `autonomous_remediation_service.py`'s per-tenant-iteration `set_tenant_id`/`reset_tenant_id` pattern (lines 144/185).
**Warning signs:** A test that mocks `db` as an `AsyncMock()` with no `._db` attribute configured would pass trivially (the mock auto-creates any attribute access) — this bug will NOT be caught by a naive mock-based unit test. The test suite must specifically assert the sweep works against a **raw, unwrapped** db-shaped fixture (no `_db` attribute present) to catch this class of bug, exactly as `test_compliance_remediation_sla.py`'s own `raw_db_registration` test group does for its own sweep.

### Pitfall 2: A new `event_type` string alone does not make rule-based routing usable
**What goes wrong:** If the optional rule-routed delivery path (Pattern 3's "Optional additive path") is implemented by only picking a new `event_type` string (`itam.warranty_expiring`) and calling `notification_service.send_notification`, tenant admins will never be able to actually create a matching rule through the UI/API: `notification_endpoints.py::RuleCreate.event_type` is a hardcoded `Literal["finding_created", "control_failed", "evidence_expired", "review_overdue", "cert_expiring"]` (line 24), and `notification_service.py::VALID_EVENTS` is a matching hardcoded `set` (line 468) that `create_rule` validates against (raises `ValueError` -> 422 for anything outside it). A tenant admin attempting `POST /api/notifications/rules {"event_type": "itam.warranty_expiring", ...}` gets a 422 today.
**Why it happens:** Phase 21 (`NOTIF-01/02`) closed the event-type vocabulary at ship time and nothing since has needed to extend it — ITAM is the first phase to introduce a genuinely new alert-worthy event type through this specific subsystem.
**How to avoid:** If the plan includes the optional rule-routed path, add `"itam.warranty_expiring"` to both `VALID_EVENTS` (`notification_service.py:468`) and `RuleCreate.event_type`'s `Literal` (`notification_endpoints.py:24`) in the same change — a one-string addition each. If the plan does NOT include the rule-routed path (i.e. relies solely on the in-app `send_alert` delivery, which fully satisfies "Admin sees each asset's warranty status... receives an alert" per the ROADMAP success criterion wording), this pitfall is moot and no change to those two files is needed. This is a scope decision the planner should make explicitly rather than silently defaulting to the narrower in-app-only path.
**Warning signs:** A UAT step that tries to configure a Slack/webhook rule for warranty alerts through the existing `/api/notifications/rules` endpoint and gets a 422 with `"value is not a valid enumeration member"` in the error body.

### Pitfall 3: Missing idempotency guard causes an alert every sweep interval, not once per expiry
**What goes wrong:** Without a persisted "already alerted" marker, a naive sweep that simply re-evaluates "is this asset's warranty inside the alert window" on every pass (hourly, per Pattern 3's example interval) will send a fresh in-app/webhook alert every single pass for the entire duration an asset sits inside the window — e.g. a 30-day alert window at an hourly sweep interval would generate ~720 duplicate alerts for one asset before the warranty actually expires.
**Why it happens:** `run_sla_pass`'s own escalation-tier guard (`new_level <= current_level: continue`, line 246) exists for exactly this reason but is tier-shaped (only re-alerts on a tier *increase*); a warranty-expiry alert has no natural "tier" to key off unless one is invented. CONTEXT.md's D-03 explicitly calls out "avoid double-alerting" as a requirement without specifying the mechanism.
**How to avoid:** Persist a `warrantyAlertSentAt` timestamp on the asset document the first time it's alerted (Pattern 3's example), and skip any asset that already has one set. A "reset" only happens implicitly if the asset's warranty is extended (e.g. via a `PATCH /purchase` that changes `warrantyMonths` or `purchaseDate`) — the PATCH handler should explicitly clear `warrantyAlertSentAt` when either of those fields changes, so a genuinely-renewed warranty can alert again later. Document this reset rule directly in the PATCH endpoint's docstring so it isn't lost.
**Warning signs:** A test asserting `run_warranty_alert_pass` called twice in a row against the same fixture data produces exactly one `send_alert` call, not two.

### Pitfall 4: Asset-Model absence or missing depreciation policy must not silently compute a wrong book value
**What goes wrong:** An asset with no `modelId` set (very common — `modelId` is `Optional` on `ManualAssetCreate`), or a Model with no `usefulLifeYears`/`salvageValueCents` set (every existing Model created before this phase ships will have neither field, since they didn't exist), naively fed into `compute_book_value` would either raise an unhandled `TypeError`/`ZeroDivisionError` or, worse, silently return a book value based on a garbage default (e.g. treating `None` useful life as `0` and dividing by zero, or treating it as "fully depreciated instantly").
**Why it happens:** Every asset Model created in Phase 56/57/58 lacks these two new fields by construction — this is not a hypothetical edge case, it is the default state of every existing Model document in any tenant that adopts this phase.
**How to avoid:** `GET /api/assets/{asset_id}/book-value` must explicitly check for `modelId` presence, Model existence, and both policy fields' presence, returning a structured "no depreciation policy assigned" response (not a 500, not a wrong number) when any is missing — see Pattern 4's "Missing-policy handling" note.
**Warning signs:** A 500 (or a suspiciously round `bookValueCents: 0`) when requesting book value for any pre-Phase-59 asset/Model.

### Pitfall 5: `purchaseCostCents` as a caller-supplied integer needs a floor, not just a type check
**What goes wrong:** A caller (or a buggy future integration) supplying a negative `purchaseCostCents` would make `compute_book_value` produce a nonsensical negative book value, and a caller supplying `purchaseCostCents` without ever having set `salvageValueCents`/`usefulLifeYears` on the Model could produce a book value that never converges to anything meaningful.
**Why it happens:** Nothing about "purchase cost" in the domain model prevents a negative number from reaching Pydantic validation unless a constraint is explicitly added.
**How to avoid:** `Field(None, ge=0)` on both `purchaseCostCents` and `salvageValueCents`, `Field(None, gt=0)` on `usefulLifeYears` (a zero-year useful life is meaningless for straight-line depreciation) — all shown in Patterns 1 and 5's examples above.

## Code Examples

Verified patterns from official/in-repo sources (all four snippets below are read directly from the actual files this session, not reconstructed from memory):

### Existing raw-db background sweep registration (clone exactly for the warranty scheduler)
```python
# Source: backend/app_startup.py:620-626 (existing, already-shipped code)
try:
    from compliance_remediation_sla_service import start_remediation_sla_scheduler
    from database import mongodb as _mdb
    asyncio.create_task(start_remediation_sla_scheduler(_mdb.db))
    logger.info("[Remediation] SLA escalation scheduler started")
except Exception as _e:
    logger.warning("[Remediation] Escalation scheduler failed to start: %s", _e)

# Phase 59 adds an identically-shaped block immediately after it:
try:
    from itam_finance_service import start_warranty_alert_scheduler
    from database import mongodb as _mdb
    asyncio.create_task(start_warranty_alert_scheduler(_mdb.db))
    logger.info("[ITAM] Warranty alert scheduler started")
except Exception as _e:
    logger.warning("[ITAM] Warranty alert scheduler failed to start: %s", _e)
```

### Existing ISO-8601 date validator (reuse verbatim)
```python
# Source: backend/itam_models.py:163-175 (existing, already-shipped code)
def _validate_iso8601_date(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    try:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"must be an ISO-8601 date/datetime string, got {v!r}")
    return v
```

### Existing catalog-reference existence check (clone the shape for supplierId validation on PATCH)
```python
# Source: backend/itam_asset_endpoints.py:87-100 (existing, already-shipped code)
if payload.manufacturerId:
    if not await db.manufacturers.find_one({"id": payload.manufacturerId}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"manufacturerId '{payload.manufacturerId}' not found."
        )
# Phase 59's PATCH /purchase does the identical check against db.suppliers for supplierId.
```

### Existing router registration order (append after the current last ITAM entry)
```python
# Source: backend/router_registry.py:82-85 (existing, already-shipped code)
_load(app, "itam_catalog_endpoints", "router")     # ITAM Phase 56 Catalog Router
_load(app, "itam_asset_endpoints", "router")       # ITAM Phase 56 Asset Router
_load(app, "itam_lifecycle_endpoints", "router")   # ITAM Phase 57 Lifecycle Router
_load(app, "itam_label_endpoints",     "router")   # ITAM Phase 58 Label Router
# Phase 59 appends:
_load(app, "itam_finance_endpoints",   "router")   # ITAM Phase 59 Finance Router
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| N/A — no prior ITAM finance capability existed | N/A | N/A | This phase introduces purchase/warranty/depreciation tracking from scratch; there is no legacy approach to migrate away from |

**Deprecated/outdated:** None identified.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | CONTEXT.md's "no prior money-handling convention" claim is corrected here to note `payment_billing_endpoints.py` already uses integer-cents with an explicit docstring — this is a factual correction based on reading the file this session, not an assumption, but the *characterization* of it as "the closest analog" is this researcher's judgment call | Standard Stack | Low — does not change the D-01 recommendation (cents), only its framing/justification |
| A2 | An hourly sweep interval (`asyncio.sleep(3600)`) for the warranty-alert scheduler is reasonable for a days-scale alert window, by analogy to `start_remediation_sla_scheduler`'s 300-second interval for a days-scale SLA window — no explicit interval was specified in CONTEXT.md or ROADMAP.md | Pattern 3 | Low — a shorter interval (e.g. 300s, matching the SLA scheduler exactly) is a trivial one-constant change the planner can make without any other structural impact; either interval satisfies "proactive expiry alerts" |
| A3 | The optional rule-routed notification path (Pattern 3, `notification_service.send_notification` + `VALID_EVENTS`/`RuleCreate` extension) is presented as optional/discretionary rather than required, on the reasoning that the in-app `send_alert` path alone satisfies the ROADMAP's literal success-criterion wording ("receives an alert... through the existing notification/webhook infrastructure") | Pattern 3, Pitfall 2 | Medium — if the user/planner actually intends tenant-configurable Slack/webhook routing (not just an in-app notification) for warranty alerts specifically, the two-file `VALID_EVENTS`/`RuleCreate` extension becomes required, not optional; recommend surfacing this as an explicit planning decision rather than silently picking the narrower path |
| A4 | Whole-year depreciation proration treats "years elapsed" as `now.year - purchase.year`, decremented by 1 if the current month/day hasn't reached the purchase month/day yet (an anniversary-based whole-year count) — this specific tie-breaking rule was not specified anywhere in CONTEXT.md/ROADMAP.md beyond "whole-year, not day/month" | Pattern 4 | Low — any reasonable whole-year definition satisfies D-04's "simpler approach" instruction; this is a defensible, unambiguous interpretation, but the planner should state the exact rule in the plan so a UAT reviewer can verify against it deterministically |

**If this table is empty:** N/A — see rows above.

## Open Questions

1. **Should warranty alerts also route through the tenant-configurable rule/channel system (Phase 21), or is the guaranteed in-app `send_alert` sufficient?**
   - What we know: `send_alert` alone satisfies the literal ROADMAP success-criterion wording and requires no changes to `notification_service.py`/`notification_endpoints.py`. The rule-routed path additionally requires a `VALID_EVENTS`/`RuleCreate.event_type` extension (Pitfall 2) and a `set_tenant_id` wrapper around the raw-db sweep call (since `notification_service.send_notification` needs a `._db`-bearing handle).
   - What's unclear: Whether "webhook infrastructure" in ITAM-FIN-02's requirement text specifically means the tenant-configurable webhook channel system (Phase 21/33's `notification_channels`+`webhook_service.py`), or is satisfied by the in-app notification alone.
   - Recommendation: Default to in-app-only (`send_alert`) as the phase's minimum bar (satisfies the literal success criterion, is simpler, has no crash risk), and treat the rule-routed extension as a fast-follow the plan can include as an additional, clearly-labeled task if the planner judges "webhook infrastructure" requires it literally.

2. **Exact alert-window default value**
   - What we know: `_DEFAULT_AT_RISK_WINDOW_DAYS = 3` for remediation SLA (a much shorter-fuse concern than a hardware warranty). No numeric default was specified for warranty alerts anywhere in CONTEXT.md/ROADMAP.md.
   - What's unclear: Whether 30 days (this research's proposed default, matching a common "renew before it expires" convention) is the right number, versus something like 60 or 90 days which might be more appropriate for procurement lead times on hardware replacement.
   - Recommendation: 30 days as the hardcoded fallback (Pattern 2) is a reasonable, clearly-labeled placeholder — since it's tenant-configurable via the `system_settings` doc lookup from day one, getting the default slightly wrong has low cost and no migration burden.

## Environment Availability

No external dependencies beyond what's already installed and running. This phase touches only backend Python modules, MongoDB (already connected), and the existing notification/webhook subsystems (already present, already tested).

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Backend runtime | ✓ | 3.12.3 (per Phase 58 research, unchanged) | — |
| MongoDB (`system_settings`, `assets`, `asset_models`, `notifications` collections) | Alert-window config, asset/model lookups, in-app notification write | ✓ | Already connected, already used by every ITAM phase to date | — |
| `notification_service.py` / `notification_manager.py` / `webhook_service.py` | Alert delivery | ✓ | Already installed, already exercised in production | — |
| pytest / pytest-asyncio | Test suite | ✓ | Already installed, exercised by `test_itam_lifecycle.py` | — |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (`@pytest.mark.asyncio`), matching `test_itam_lifecycle.py`/`test_itam_labels.py` |
| Config file | none — no `pytest.ini`/`pyproject.toml [tool.pytest]` section in this repo (consistent with Phase 57/58 research findings) |
| Quick run command | `backend/venv/bin/python -m pytest backend/tests/test_itam_finance.py -q` |
| Full suite command | `backend/venv/bin/python -m pytest backend/tests -q` (per project memory: use `backend/venv/bin/python`, NOT system Python) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ITAM-FIN-01 | `PATCH /api/assets/{id}/purchase` sets purchaseCostCents/purchaseDate/poNumber/supplierId; rejects an unknown supplierId with 400 | unit | `pytest backend/tests/test_itam_finance.py -k purchase_patch -x` | ❌ Wave 0 |
| ITAM-FIN-01 | Fields are nullable/optional at manual-asset creation time (`POST /api/assets` with no purchase fields still succeeds) | unit | `pytest backend/tests/test_itam_finance.py -k create_no_purchase -x` | ❌ Wave 0 |
| ITAM-FIN-02 | `compute_warranty_status` returns correct status (`active`/`expiring`/`expired`/`none`) for boundary dates | unit | `pytest backend/tests/test_itam_finance.py -k warranty_status_compute -x` | ❌ Wave 0 |
| ITAM-FIN-02 | `run_warranty_alert_pass` against a raw (non-`._db`-bearing) db fixture does not raise — proves Pitfall 1 is actually fixed, not just documented | unit | `pytest backend/tests/test_itam_finance.py -k raw_db_no_crash -x` | ❌ Wave 0 |
| ITAM-FIN-02 | `run_warranty_alert_pass` called twice in a row against the same fixture sends exactly one alert (Pitfall 3 idempotency) | unit | `pytest backend/tests/test_itam_finance.py -k idempotent_alert -x` | ❌ Wave 0 |
| ITAM-FIN-02 | A task with no `tenantId` is skipped, never alerted (mirrors T-44-03) | unit | `pytest backend/tests/test_itam_finance.py -k skip_no_tenant -x` | ❌ Wave 0 |
| ITAM-FIN-02 | `app_startup.py` registers `start_warranty_alert_scheduler` with the raw `mongodb.db`, never `get_database()` (regression guard, cloned from `test_compliance_remediation_sla.py`'s `raw_db_registration` group) | unit | `pytest backend/tests/test_itam_finance.py -k raw_db_registration -x` | ❌ Wave 0 |
| ITAM-FIN-03 | `compute_book_value` straight-line arithmetic correct at 0/1/N/useful-life-boundary years elapsed, floors at salvage | unit | `pytest backend/tests/test_itam_finance.py -k book_value_compute -x` | ❌ Wave 0 |
| ITAM-FIN-03 | `GET /book-value` for an asset with no `modelId`, or a Model missing depreciation policy fields, returns a structured "no policy" response, not a 500 (Pitfall 4) | unit | `pytest backend/tests/test_itam_finance.py -k book_value_no_policy -x` | ❌ Wave 0 |
| ITAM-FIN-01/02/03 | Cross-tenant asset id on any of the 3 new routes returns 404, never another tenant's financial data | unit | `pytest backend/tests/test_itam_finance.py -k tenant_isolation -x` | ❌ Wave 0 |
| ITAM-FIN-01/02/03 | Caller without `manage:assets` gets 403 on all 3 new routes | unit | `pytest backend/tests/test_itam_finance.py -k rbac -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `backend/venv/bin/python -m pytest backend/tests/test_itam_finance.py -q`
- **Per wave merge:** `backend/venv/bin/python -m pytest backend/tests -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_itam_finance.py` — new file, covers all rows above. No shared `MockTenantIsolatedDatabase` fixture exists in `conftest.py` (confirmed by grep this session, consistent with Phase 58's own finding) — build a local raw-db-shaped fixture (a plain object/dict-backed stub with no `._db` attribute) specifically to exercise Pitfall 1's regression test, since an `AsyncMock()`-based fixture would auto-satisfy `hasattr(mock, "_db")` and silently mask the exact bug this phase must not reintroduce.
- [ ] Framework install: none — pytest/pytest-asyncio already installed.
- [ ] No new package install gate — see Package Legitimacy Audit.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (inherited) | `Depends(get_current_user)` via `_require_itam_admin` — unchanged, reused |
| V3 Session Management | no | No new session surface introduced |
| V4 Access Control | yes | `_require_itam_admin` (`manage:assets` permission) gates all 3 new routes; `TenantIsolatedDatabase` auto-scopes asset/model lookups to the caller's tenant |
| V5 Input Validation | yes | `AssetPurchaseUpdate`/extended `ManualAssetCreate`/`AssetModelCreate` fields all Pydantic-validated (`ge=0`/`gt=0` numeric floors, `ConfigDict(extra="forbid")`, reused ISO-8601 date validator); `supplierId` existence-checked before write |
| V6 Cryptography | no | No cryptographic operations in this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| IDOR — requesting purchase/warranty/book-value data for an `assetId` belonging to another tenant | Information Disclosure | `TenantIsolatedCollection` auto-injects `tenantId` into every `find_one`/`find` call on `db.assets` — a cross-tenant asset id resolves to "not found" (404), never another tenant's financial data. `[VERIFIED: backend/database.py:22-45]` |
| Background-sweep tenant-context leak (the milestone's flagged highest-severity risk class) | Information Disclosure / Tampering | The raw-db sweep never calls `get_database()`/`TenantIsolatedDatabase` inside its loop; every write is filtered by the `tenantId` extracted directly from the document being processed (`{"id": asset["id"], "tenantId": tenant_id}`), identical to `run_sla_pass`'s own pattern |
| Negative or absurd `purchaseCostCents`/`salvageValueCents` corrupting book-value arithmetic | Tampering | `Field(..., ge=0)` numeric floors (Pitfall 5) reject negative values at the Pydantic boundary before they ever reach `compute_book_value` |
| Unauthorized modification of another tenant's financial record via a guessed asset id | Elevation of Privilege / Tampering | `_require_itam_admin` RBAC gate + tenant-scoped `find_one_and_update` filter (same `{"id": ..., **tenant-injected}` shape as the lifecycle endpoints) — a cross-tenant PATCH resolves to 404, never a silent no-op write to the wrong tenant's document |

## Sources

### Primary (HIGH confidence — verified via Read/grep of the actual codebase this session)
- `backend/itam_models.py` — `ManualAssetCreate`, `AssetModelCreate`/`Update`, `SupplierCreate`, `_validate_iso8601_date`, existing "Phase 59 will reuse `next_asset_tag`" comment (`itam_asset_endpoints.py:30`)
- `backend/itam_asset_endpoints.py` — `_require_itam_admin`, `next_asset_tag`, catalog-reference existence-check pattern
- `backend/itam_catalog_endpoints.py` / `backend/itam_catalog_service.py` — catalog CRUD conventions, `_validate_asset_model_references`, fieldset validation (`validate_fieldsets`/`collect_field_defs`/`validate_custom_field_values`)
- `backend/itam_lifecycle_endpoints.py` (full read) — RBAC/tenant-isolation/`find_one_and_update`-guard/history-write conventions, `overdue_audit_report`'s read-time-computed-report precedent
- `backend/itam_lifecycle_service.py` — append-only history helper shape (not directly reused this phase, but confirms the one-concern-per-file convention)
- `backend/itam_label_endpoints.py` / `itam_label_service.py` (Phase 58, most recent ITAM precedent) — multi-segment route shadowing-avoidance reasoning, RBAC-dependency-reuse-not-redefinition convention
- `backend/compliance_remediation_sla_service.py` (full read) — the canonical raw-db background-sweep pattern this phase clones: `run_sla_pass`, `start_remediation_sla_scheduler`, `get_sla_at_risk_window`'s `hasattr(db, "_db")` guard, `_tenant_admin_emails`, the top-level non-fatal `try/except` shape
- `backend/notification_service.py` (full read) — `NotificationService.send_alert` (works with raw or wrapped db), the module-level `send_notification`/`VALID_EVENTS`/`create_rule` functions and their `db._db`-requiring, non-defensive shape (the Pitfall 1 finding)
- `backend/notification_manager.py` (full read) — `NotificationManager.send_notification`'s internal `get_database()` call (confirmed this is a second, separate tenant-isolation risk if used from a background sweep without explicit `set_tenant_id`)
- `backend/webhook_service.py` (full read) — `WebhookService.trigger_webhook`'s `db.webhooks` query shape, HMAC-signing, SSRF guard
- `backend/notification_endpoints.py` (full read) — `RuleCreate.event_type`'s hardcoded `Literal`, confirming Pitfall 2
- `backend/database.py:1-160` — `TenantIsolatedCollection`/`TenantIsolatedDatabase` mechanics, `get_database()`'s `TenantIsolatedDatabase(mongodb.db)` construction, exemption allowlist
- `backend/tenant_context.py` (full read) — `set_tenant_id`/`reset_tenant_id`/`get_tenant_id` ContextVar mechanics
- `backend/app_startup.py:604-626` — exact registration pattern for the 3 existing raw-db schedulers (escalation, close-loop, remediation SLA)
- `backend/autonomous_remediation_service.py` (grep) — the per-tenant-iteration `set_tenant_id`/`reset_tenant_id` pattern cited for the optional rule-routed delivery path
- `backend/router_registry.py:82-85` — exact ITAM router registration order
- `backend/asset_endpoints.py` (grep + targeted read) — confirmed 511 lines (already over the 500-line CLAUDE.md cap), `GET /{asset_id}` shape, `BulkUpdateAssetsRequest` precedent (cited by Phase 58's research, re-confirmed here)
- `backend/payment_billing_endpoints.py:25-29` / `backend/billing_endpoints.py:34` / `backend/risk_fair_service.py` / `backend/finops_service.py` — the money-representation precedent survey behind the Standard Stack correction
- `backend/rbac_utils.py` / `backend/rbac_service.py` — confirmed `manage:assets` is already a registered permission (no new permission needed)
- `backend/tests/test_compliance_remediation_sla.py` / `backend/tests/test_itam_lifecycle.py` — test-file conventions (`@pytest.mark.asyncio`, no shared conftest.py mock fixture, `asyncio.run` usage in the older test)
- `.planning/phases/58-asset-tags-offline-labels/58-RESEARCH.md` — structural template for this document
- `.planning/phases/59-procurement-finance-warranty-depreciation/59-CONTEXT.md` — locked decisions and canonical references
- `.planning/ROADMAP.md` (Phase 59 section, lines 901-919) — goal, requirements, success criteria, depends-on
- `.planning/REQUIREMENTS.md` — ITAM-FIN-01/02/03 locked text
- `.planning/STATE.md` — Session 2026-08-04 v4.0 roadmap-definition entry flagging the background-scheduler tenant-isolation bug class as this milestone's highest-severity risk

### Secondary (MEDIUM confidence)
None this phase — every claim above was directly verified by reading the cited file this session; no WebSearch was needed since this phase is 100% in-repo pattern-following with no new external library or unfamiliar API surface.

### Tertiary (LOW confidence — flagged for validation)
- The exact alert-window default (30 days) and sweep interval (hourly) — see Assumptions Log A2, Open Question 2.
- Whether the rule-routed notification path is actually required by "webhook infrastructure" wording — see Assumptions Log A3, Open Question 1.

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — no new dependency; every claim about existing library usage verified by direct file reads this session
- Architecture: HIGH — every pattern (RBAC gate reuse, tenant isolation, raw-db sweep shape, notification delivery) has a direct, already-shipped in-repo precedent verified by full-file reads, not just grep
- Pitfalls: HIGH — Pitfall 1 (the notification-call crash) and Pitfall 2 (the closed event-type vocabulary) were both discovered by actually reading the exact functions involved and tracing the `db._db` access path, not inferred from naming conventions; this is a genuine correction to a CONTEXT.md-locked decision's literal wording, not a hypothetical concern

**Research date:** 2026-08-05
**Valid until:** 2026-09-04 (30 days — stable domain: no external library, all patterns cloned from code that is not expected to change independently of this phase)
