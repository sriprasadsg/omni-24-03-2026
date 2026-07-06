# Phase 26: Vendor and Risk Data Completeness - Research

**Researched:** 2026-07-06
**Domain:** Internal backend/frontend pattern extension (FastAPI + Motor/MongoDB + React/TypeScript) — no new external technology
**Confidence:** HIGH

## Summary

This phase closes three data-completeness gaps in the existing vendor and risk modules. All three gaps are additive extensions of patterns that already exist elsewhere in this codebase — no new libraries, no new architecture, no external research was needed. The work is a direct code-reading exercise: `backend/baa_endpoints.py` is the canonical create/sign/terminate lifecycle to clone for DPA (VRISK-01); `backend/vendor_service.py` already has an unused `update_vendor()` method and an `add_document`/`add_assessment` push-to-array pattern to extend for subprocessors (VRISK-02); and `backend/risk_service.py`'s single `risk_score = likelihood * impact` needs additive (not destructive) splitting into inherent/residual (RISK-01).

Three concrete findings materially change how the planner should scope tasks:
1. **DPA has zero existing persistence today** — it is only a checkbox *option string* inside the vendor questionnaire template (`"GDPR DPA"` in `vendor_endpoints.py`'s multiselect) and an unrelated generic `privacy_contracts` collection (`type: "DPA"` in `privacy_service.py`, a generic legal-document tracker with no vendor linkage). VRISK-01 requires a wholly new `dpa_agreements` collection and `dpa_endpoints.py` file, mirroring `baa_agreements`/`baa_endpoints.py` exactly, but should add a `vendor_id` field (BAA has none) so it can be surfaced against a specific vendor.
2. **`vendor_service.py` has a fully-implemented `update_vendor()` method with zero endpoint calling it** — there is no PATCH/PUT route in `vendor_endpoints.py` at all. VRISK-02 (subprocessors) should NOT go through this generic update path; it should follow the existing `add_assessment`/`add_document` push-to-array pattern (`POST /{vendor_id}/subprocessors`) for consistency and auditability.
3. **`VendorManagement.tsx` has no vendor detail view** — `selectedVendor` state is declared but never rendered, and the row's `MoreHorizontal` action button has no `onClick`. "Surfaced in the vendor risk view" (VRISK-02's stated requirement) means the planner must build a detail view that does not currently exist, not just add a field to an existing screen.

**Primary recommendation:** Build DPA as a new sibling file-pair (`dpa_service.py`/`dpa_endpoints.py` or endpoints-only mirroring `baa_endpoints.py`'s inline style) cloning BAA's lifecycle verbatim; extend `vendor_service.py` with a `subprocessors` push/list/remove trio mirroring `add_document`; and extend (never replace) the `Risk` model with `residual_likelihood`/`residual_impact`/`residual_risk_score` fields while keeping `risk_score`/`likelihood`/`impact` as the inherent representation for zero-breakage backward compatibility.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| DPA lifecycle (create/sign/terminate) | API / Backend | Database / Storage | Mirrors `baa_endpoints.py` — pure REST + Motor persistence, no client-side state machine |
| Subprocessor discovery (list on vendor) | API / Backend | Database / Storage | Sub-document array on the existing `vendors` collection, same tier as `assessments`/`documents` |
| Vendor risk view surfacing (DPA status + subprocessors) | Browser / Client (React) | API / Backend | New read-only detail view composes data already served by the API — no new backend logic needed for display |
| Inherent vs. residual risk scoring | API / Backend | Database / Storage | Pure computation (`likelihood × impact` for both scores) inside `risk_service.py`, persisted alongside existing fields |
| Risk register UI (score display, heatmap) | Browser / Client (React) | — | `RiskRegister.tsx` renders whatever the API returns; heatmap logic is presentation-only |

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VRISK-01 | DPA lifecycle (create/sign/terminate) tracked with same rigor as existing BAA lifecycle | `baa_endpoints.py` fully read and documented below as the exact pattern to clone; test harness in `test_automation_and_baa.py` identified for reuse |
| VRISK-02 | Subprocessor discovery — vendor record lists its own subprocessors, surfaced in vendor risk view | `vendor_service.py`'s existing `add_document`/`add_assessment` push-pattern identified as the template; confirmed no vendor detail view exists yet in `VendorManagement.tsx` — must be built |
| RISK-01 | Risk register scores both inherent and residual risk, not a single blended `risk_score` | `risk_service.py`'s `create_risk`/`update_risk` fully read; additive (non-breaking) field-split strategy documented below; confirmed no existing "treatment strategy" field beyond `status` enum |
</phase_requirements>

## Standard Stack

### Core
No new libraries are required. This phase extends existing, already-installed dependencies.

| Library | Version (verified installed) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.138.0 (constraint `>=0.110.0,<1.0.0` in `backend/requirements.txt`) [VERIFIED: local venv] | REST endpoints for DPA/subprocessor/risk routes | Already the framework for every sibling endpoint file in this repo |
| pydantic | 2.13.4 (constraint `>=2.5.0,<3.0.0`) [VERIFIED: local venv] | Request/response models (`RiskCreate`, `VendorCreate`, new `DPACreate`) | Already used throughout `backend/*_endpoints.py` |
| motor | 3.7.1 (constraint `>=3.3.0,<4.0.0`) [VERIFIED: local venv] | Async MongoDB driver for `dpa_agreements`, `vendors.subprocessors`, `risks` collections | Already the sole DB driver in this codebase |
| pymongo | 4.17.0 (constraint `>=4.6.0,<5.0.0`) [VERIFIED: local venv] | Sync fallback / types used by motor | Already a transitive requirement |

### Supporting
None — no new supporting libraries needed. `uuid` (stdlib) for ID generation, `time`/`datetime` (stdlib) for timestamps — both already used identically in `baa_endpoints.py`, `vendor_service.py`, and `risk_service.py`.

### Alternatives Considered
Not applicable — this phase is a pure pattern-replication task inside an existing, closed stack. No alternative libraries were evaluated because none are needed.

**Installation:** None required — no `pip install` or `npm install` commands needed for this phase.

## Package Legitimacy Audit

**Not applicable.** This phase installs zero new external packages (Node.js or Python). All work extends `fastapi`, `motor`, `pydantic`, and stdlib modules already present in `backend/requirements.txt` and verified installed in the venv above. The Package Legitimacy Gate protocol is skipped per its own trigger condition ("whenever this phase installs external packages").

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser (React)                                                    │
│                                                                       │
│  VendorManagement.tsx ──(new)──> VendorDetailModal.tsx (NEW)         │
│     │  fetchVendors()                │  shows: DPA status,          │
│     │                                │  subprocessors list           │
│     ▼                                ▼                              │
│  RiskRegister.tsx ──uses──> RiskFormModal.tsx                       │
│     │  fetchRisks()/createRisk()        (add residual fields)       │
│     │  renders inherent + residual score columns                    │
│     ▼                                                                │
│  DPAManagement.tsx (NEW, clone of BAAManagement.tsx)                 │
│     draft ──sign(us)──> pending ──sign(vendor)──> active ──terminate│
└──────────────┬──────────────────┬──────────────────┬────────────────┘
               │ authFetch         │ authFetch         │ authFetch
               ▼                  ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FastAPI Backend                                                     │
│                                                                       │
│  dpa_endpoints.py (NEW)      vendor_endpoints.py (extend)            │
│   POST   /api/dpa              POST /api/vendors/{id}/subprocessors  │
│   POST   /api/dpa/{id}/sign    GET  /api/vendors/{id}/subprocessors  │
│   POST   /api/dpa/{id}/terminate  DELETE .../subprocessors/{sub_id}  │
│   GET    /api/dpa, /api/dpa/stats                                    │
│                                                                       │
│  risk_endpoints.py (extend)                                          │
│   POST/PUT /api/risks — now accepts/returns                          │
│   inherent_risk_score + residual_likelihood/impact/risk_score        │
└──────────────┬──────────────────┬──────────────────┬────────────────┘
               │ Motor             │ Motor              │ Motor
               ▼                  ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MongoDB                                                              │
│   dpa_agreements (NEW collection, shape mirrors baa_agreements)       │
│   vendors.subprocessors (NEW array field, pattern mirrors .documents) │
│   risks (extend document shape — additive fields only)               │
└─────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure
```
backend/
├── dpa_endpoints.py        # NEW — clone of baa_endpoints.py; router prefix /api/dpa
├── vendor_service.py        # EXTEND — add add_subprocessor/list_subprocessors/remove_subprocessor
├── vendor_endpoints.py       # EXTEND — add 3 subprocessor routes
├── risk_service.py           # EXTEND — additive residual_* fields in create_risk/update_risk
├── risk_endpoints.py         # EXTEND — RiskCreate/RiskUpdate gain optional residual_likelihood/residual_impact
├── router_registry.py        # EXTEND — register dpa_endpoints (not in _REQUIRED_ROUTERS, same tier as baa_endpoints)
└── tests/
    ├── test_dpa_endpoints.py         # NEW — clone test_automation_and_baa.py's BAA test classes
    ├── test_vendor_subprocessors.py  # NEW
    └── test_risk_inherent_residual.py # NEW

components/
├── DPAManagement.tsx        # NEW — clone of BAAManagement.tsx (inline-style, authFetch pattern)
├── VendorDetailModal.tsx    # NEW — first-ever vendor detail view; shows DPA status + subprocessor list/add form
├── VendorManagement.tsx     # EXTEND — wire MoreHorizontal button to open VendorDetailModal
├── RiskRegister.tsx         # EXTEND — add "Residual Score" column
└── RiskFormModal.tsx        # EXTEND — add optional residual likelihood/impact inputs

types.ts                     # EXTEND — Risk interface gains residual_* fields; add DPA/Subprocessor interfaces
App.tsx / Sidebar.tsx        # EXTEND — new 'dpaManagement' view case + nav entry (see Pitfall 1)
```

### Pattern 1: BAA Lifecycle Clone for DPA (VRISK-01)
**What:** `baa_endpoints.py` implements a 4-state lifecycle (`draft` → `pending_signature`/`active` → `terminated`, plus a synthetic `expired` derived from date comparison in `/stats`) using a single flat MongoDB collection and 6 routes: list, stats, get-by-id, create, patch, sign, terminate.
**When to use:** Clone this exact shape for `dpa_agreements`. Do not invent a new state machine.
**Example (verified from `backend/baa_endpoints.py`, lines 94-168):**
```python
# Source: backend/baa_endpoints.py (existing, verified in this repo)
@router.post("")
async def create_baa(payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    tenant_id = _tenant(current_user)
    baa = {
        "id": f"baa-{int(time.time())}",
        "business_associate": payload.get("business_associate") or payload.get("vendor_name", ""),
        "status": "draft",
        "signed_by_vendor": False,
        "signed_by_us": False,
        "created_by": _sub(current_user),
        "created_at": time.time(),
        # ...
    }
    if tenant_id:
        baa["tenantId"] = tenant_id
    await db["baa_agreements"].insert_one(baa)
    baa.pop("_id", None)
    return baa

@router.post("/{baa_id}/sign")
async def sign_baa(baa_id: str, payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    # party="us" or party="vendor"; only activates when BOTH signed
    ...
    if doc and doc.get("signed_by_us") and doc.get("signed_by_vendor"):
        await db["baa_agreements"].update_one(baa_filter, {"$set": {"status": "active"}})
```
For DPA, add one field BAA does not have: `"vendor_id": payload.get("vendor_id")` on create, so the frontend can query `/api/dpa?vendor_id=X` (or filter client-side) and the vendor detail view can show DPA status per vendor. Everything else — draft/sign/terminate/stats — should be copied verbatim, including the field-name normalization shim (`_normalize()`) if the DPA payload accepts legacy key aliases.

### Pattern 2: Push-to-Array Sub-Resource (VRISK-02)
**What:** `vendor_service.py` already has two working examples of "attach a sub-record to a vendor" — `add_assessment` (line 79) and `add_document` (line 138) — both use `db.vendors.update_one(filt, {"$push": {"field": item}})`.
**When to use:** Use this exact pattern for subprocessors instead of the unused generic `update_vendor()`. A `$push` keeps the operation atomic and auditable (each subprocessor gets its own `id` and `timestamp`), consistent with how assessments/documents already work.
**Example (new code, following the verified existing pattern in `backend/vendor_service.py` lines 138-147):**
```python
# New method in vendor_service.py, modeled directly on add_document (verified pattern above)
async def add_subprocessor(self, vendor_id: str, sub_data: Dict[str, Any], tenant_id: Optional[str] = None, role: str = "") -> Optional[Dict]:
    db = get_database()
    sub = {
        "id": str(uuid.uuid4()),
        "name": sub_data.get("name", ""),
        "purpose": sub_data.get("purpose", ""),
        "data_categories": sub_data.get("data_categories", []),
        "location": sub_data.get("location", ""),
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    filt = {"id": vendor_id, **self._scope(role, tenant_id)}
    result = await db.vendors.update_one(filt, {"$push": {"subprocessors": sub}})
    return sub if result.matched_count > 0 else None

async def remove_subprocessor(self, vendor_id: str, subprocessor_id: str, tenant_id: Optional[str] = None, role: str = "") -> bool:
    db = get_database()
    filt = {"id": vendor_id, **self._scope(role, tenant_id)}
    result = await db.vendors.update_one(filt, {"$pull": {"subprocessors": {"id": subprocessor_id}}})
    return result.matched_count > 0
```
Add corresponding routes in `vendor_endpoints.py` mirroring `upload_vendor_document`'s RBAC gate (`_VENDOR_ADMIN_ROLES` for mutations; any authenticated tenant user for reads via `get_vendor`, which already returns the full vendor doc including whatever new `subprocessors` array is present — no extra GET route strictly required, though a dedicated `GET /{vendor_id}/subprocessors` convenience route is reasonable for the detail-view fetch).

### Pattern 3: Additive Field Split for Risk Scoring (RISK-01)
**What:** `risk_service.py`'s `create_risk`/`update_risk` compute a single `risk_score = likelihood * impact`. The least-disruptive split (per this repo's established pattern of adding trailing optional params/fields rather than renaming — see STATE.md decisions `02-01`, `03-01`, `04-00` etc. which repeatedly favor additive backward-compatible fields) is:
- Keep `likelihood`, `impact`, `risk_score` exactly as-is — they now explicitly represent **inherent** risk (pre-mitigation). Add `inherent_risk_score` as an always-equal alias of `risk_score` for forward-looking clarity (`RiskRegister.tsx` and any other consumer can migrate to the new name at its own pace since `risk_score` never disappears).
- Add new optional fields `residual_likelihood`, `residual_impact` (both `int`, default = the corresponding inherent value when the caller does not supply them — i.e., "no additional mitigation modeled yet" is the honest default, not a fabricated number).
- Compute `residual_risk_score = residual_likelihood * residual_impact` identically to how `risk_score` is computed today.
**When to use:** Every `create_risk`/`update_risk` call. This composes with the existing `status` field (Open/Mitigated/Accepted/Transferred/Avoided) rather than replacing it — `status` already represents treatment strategy loosely; residual scoring lets a user quantify the effect of that strategy instead of only labeling it.
**Example (extends the existing verified code in `backend/risk_service.py` lines 39-56):**
```python
# Extends backend/risk_service.py create_risk (verified existing code shown for context)
async def create_risk(self, risk_data: Dict[str, Any], tenant_id: Optional[str] = None) -> Dict:
    db = self._db()
    likelihood = int(risk_data.get("likelihood", 1))
    impact = int(risk_data.get("impact", 1))
    residual_likelihood = int(risk_data.get("residual_likelihood", likelihood))
    residual_impact = int(risk_data.get("residual_impact", impact))
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "created_at": now,
        "updated_at": now,
        "risk_score": likelihood * impact,               # unchanged — inherent, backward-compatible
        "inherent_risk_score": likelihood * impact,       # new alias, always == risk_score
        "residual_likelihood": residual_likelihood,
        "residual_impact": residual_impact,
        "residual_risk_score": residual_likelihood * residual_impact,  # new
        **risk_data,
    }
    doc["likelihood"] = likelihood
    doc["impact"] = impact
    doc["tenantId"] = tenant_id
    await db.risks.insert_one(doc)
    doc.pop("_id", None)
    return doc
```
`update_risk` needs the analogous change: recompute `residual_risk_score` whenever `residual_likelihood`/`residual_impact` (or, if the caller omits them, `likelihood`/`impact`) change, exactly the way the existing code already recomputes `risk_score` when `likelihood`/`impact` change (line 67-68).

### Anti-Patterns to Avoid
- **Renaming `risk_score` to `inherent_risk_score` and removing the old field:** `RiskRegister.tsx` (`risk.risk_score` referenced 4 times) and `types.ts`'s `Risk` interface both read `risk_score` directly. A hard rename breaks the existing frontend with no compile-time warning (it's a loose `any`-typed API response in places). Add, don't rename.
- **Routing subprocessors through the unused generic `update_vendor()`:** that method does a blanket `$set` of arbitrary caller-supplied keys — using it for subprocessors would let a caller silently overwrite the *entire* subprocessors array (data loss) instead of appending one entry, and bypasses the audit-friendly per-item `id`/timestamp shape the `add_document`/`add_assessment` pattern already establishes.
- **Building the DPA lifecycle as a sub-resource of `/api/vendors/{id}/dpa` instead of a standalone `/api/dpa` router:** BAA is standalone (not nested under any other resource) specifically so it can be listed/filtered/stat'd independently of which vendor it's tied to. Nesting DPA under vendors would create an inconsistent lifecycle-tracking pattern versus BAA and complicate the `/dpa/stats` aggregate endpoint the requirement implies by analogy.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DPA state machine (draft/pending/active/terminated) | A new bespoke status-transition validator | Copy `baa_endpoints.py`'s inline sign/terminate logic verbatim | The BAA lifecycle already handles the exact edge case this phase's context calls out — "single-party sign must not activate" — and has a regression test proving it (`test_single_party_sign_does_not_activate`). Reinventing this risks reintroducing that exact bug. |
| Subprocessor CRUD | A dedicated `subprocessors` MongoDB collection with its own service class | Sub-array on the existing `vendors` document via `$push`/`$pull` | Assessments and documents already prove this pattern works at this record's scale (a handful of sub-items per vendor, not paginated at scale) — a new collection adds join complexity for zero benefit here. |
| Risk score computation | A weighted risk-matrix library or FAIR-style Monte Carlo engine | Plain `likelihood * impact` multiplication, done twice (inherent + residual) | FAIR quantification is explicitly a **separate, later phase** (Phase 31: FAIR Risk Quantification) in this same milestone — building anything more sophisticated here duplicates that phase's scope and risks a rework collision. |

**Key insight:** Every "don't hand-roll" in this phase is really "don't diverge from the sibling pattern already proven in this exact codebase." The BAA/assessment/document patterns exist specifically to be cloned; the risk of this phase is over-engineering beyond what those patterns already solved.

## Common Pitfalls

### Pitfall 1: New dashboard built but never wired into navigation
**What goes wrong:** A fully-functional `DPAManagement.tsx` (or `VendorDetailModal.tsx`) component exists, builds cleanly, but is unreachable in the running app because no `App.tsx` route case or `Sidebar.tsx` nav entry references it.
**Why it happens:** This is not hypothetical — it is the single most repeated defect class in this project's own history. STATE.md's v2.0 milestone note: *"5 dashboards that were fully built but never reachable in the app (SaaSIntegrationsDashboard, PrivacyLegalDashboard, CloudAccountsDashboard, NotificationsDashboard, ApiExtensionsDashboard) were wired into App.tsx/Sidebar.tsx navigation"* — the exact same class of gap `16-VERIFICATION.md` caught a day earlier for `ProgramsDashboard`, and again for `24-IacContainerDashboard` in the most recent completed phase.
**How to avoid:** The plan MUST include an explicit task (not just "build the component") to: (1) add a `view` union member in `types.ts`, (2) add a `Sidebar.tsx` nav item, (3) add an `App.tsx` `case` statement wrapped in `<ErrorBoundary>`/`<Suspense>` per the `baaManagement` precedent (line 1898 of `App.tsx`), and (4) verify reachability by checking the production build's chunk output (the exact verification method used in the last two phases per STATE.md).
**Warning signs:** A plan whose only frontend task is "create DPAManagement.tsx component" with no corresponding App.tsx/Sidebar.tsx task.

### Pitfall 2: Missing RBAC gate on DPA create (mirroring an existing gap in BAA)
**What goes wrong:** `baa_endpoints.py`'s `create_baa` (line 94) performs **no role check at all** — any authenticated user, regardless of role, can create a BAA. `vendor_endpoints.py`'s `create_vendor`, by contrast, correctly gates on `_VENDOR_ADMIN_ROLES`. If DPA is cloned verbatim from BAA without noticing this discrepancy, the same gap is reproduced.
**Why it happens:** "Match the existing BAA lifecycle pattern" (as instructed) is ambiguous about whether to also match BAA's *bugs*.
**How to avoid:** When implementing `dpa_endpoints.py`, gate `create_dpa`/`sign_dpa`/`terminate_dpa` on an appropriate admin role set (reuse `_VENDOR_ADMIN_ROLES` from `vendor_endpoints.py`, since DPA is conceptually a vendor-governance artifact, or define an equivalent `_DPA_ADMIN_ROLES`). Do not silently propagate BAA's missing-RBAC gap into new code — flag this as a deliberate deviation from copy-verbatim, and note it in the plan's task description.
**Warning signs:** A DPA test suite that asserts 200 (not 403) when a `Viewer`-role user calls `POST /api/dpa`.

### Pitfall 3: Breaking `RiskRegister.tsx`'s existing `risk_score` consumer with a rename
**What goes wrong:** If `risk_service.py` is changed to rename `risk_score` → `inherent_risk_score` (rather than adding both), the risk table's score column, heatmap severity buckets (`getRiskLevel`), and stat tiles (`risks.filter(r => r.risk_score >= 20)`) in `RiskRegister.tsx` all silently render `undefined` — no compile error, since the fetch is typed as `Risk[]` but the runtime shape from a partially-updated backend would diverge from the TS interface.
**Why it happens:** "Split into inherent and residual" reads naturally as a rename; the codebase's own convention (verified across `02-01` through `10-02` STATE.md decisions) is consistently additive-only for exactly this reason.
**How to avoid:** Follow Pattern 3 above — add fields, never remove/rename `risk_score`.
**Warning signs:** Any diff that deletes the `risk_score` key from `risk_service.py`'s returned dict, or a `RiskCreate`/`RiskUpdate` pydantic model where `likelihood`/`impact` become optional/removed.

### Pitfall 4: Forgetting to register `dpa_endpoints` in `router_registry.py`
**What goes wrong:** A correctly-written `dpa_endpoints.py` never gets included in the FastAPI app because `register_all_routers()` never calls `_load(app, "dpa_endpoints", "router")`.
**Why it happens:** Router registration is centralized and easy to forget since it lives in a separate file from the endpoint module itself.
**How to avoid:** Add the load call near the existing `_load(app, "baa_endpoints", "router")` line (currently line 219) or near `risk_endpoints`/`vendor_endpoints` (lines 147-148) in `backend/router_registry.py`. `dpa_endpoints` does not need to be added to `_REQUIRED_ROUTERS` — BAA itself isn't in that frozenset, so a load failure should log-and-continue, not hard-fail startup, consistent with BAA's own tier.
**Warning signs:** `GET /api/dpa` returns 404 in manual testing despite the file existing and having no import errors.

## Code Examples

### DPA test harness (clone this pattern exactly)
```python
# Source: backend/tests/test_automation_and_baa.py (verified existing pattern in this repo, lines 21-52, 207-237)
def _col(**overrides):
    col = MagicMock()
    col.find_one   = AsyncMock(return_value=None)
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.delete_one = AsyncMock()
    col.find       = MagicMock()
    col.find.return_value.to_list = AsyncMock(return_value=[])
    col.find.return_value.sort    = MagicMock(return_value=MagicMock())
    col.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
    for k, v in overrides.items():
        setattr(col, k, v)
    return col

def _db(**collections):
    db = MagicMock()
    db.__getitem__ = lambda self, name: getattr(self, name, _col())
    for name, col in collections.items():
        setattr(db, name, col)
    return db

# Critical: baa_endpoints.py's _db() helper does `from database import get_database;
# return get_database()` LAZILY inside the function body — so tests must patch
# "database.get_database" (the module-level source), NOT "baa_endpoints.get_database"
# (which doesn't exist as a module-level name). Reuse this exact patch target for dpa_endpoints.py
# if dpa_endpoints.py copies the same lazy-import _db() helper.
with patch("database.get_database", return_value=db):
    res = TestClient(app).post("/api/baa", json={"business_associate": "ACME Corp"})
```

### Existing risk stat/heatmap consumer (do not break this shape)
```typescript
// Source: components/RiskRegister.tsx (verified existing code, lines 133-136, 188-206)
{ label: 'Critical', value: risks.filter(r => r.risk_score >= 20).length, color: 'text-red-600' },
// ...
const level = getRiskLevel(risk.risk_score);
<span>{risk.risk_score} ({level.label})</span>
// New: add a parallel "Residual" column using risk.residual_risk_score with the same getRiskLevel() bucketing
```

## State of the Art

Not applicable — this phase does not touch any third-party API or protocol whose best practice has shifted. It is internal pattern-consistency work.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | DPA agreements should carry a `vendor_id` field (unlike BAA, which has none) so they can be linked to a specific vendor record. | Architecture Patterns — Pattern 1 | If wrong, DPA becomes a standalone HIPAA-style tracker disconnected from the vendor risk view, which would fail the stated goal ("DPA lifecycle... on the vendor record" framing in the phase description) — low risk since this is additive and easy to correct in review. |
| A2 | Residual risk defaults to equal the inherent value when the caller doesn't supply `residual_likelihood`/`residual_impact` (i.e., "no mitigation modeled yet" rather than a guessed reduction). | Architecture Patterns — Pattern 3 | If wrong (e.g., stakeholders expect an automatic reduction formula tied to `status`), the default residual scores would overstate risk for already-mitigated items until a human manually re-enters residual values. Low risk — conservative default, correct starting point. |
| A3 | Subprocessors should use the push-array pattern (embedded in the vendor doc) rather than a separate top-level collection. | Don't Hand-Roll / Pattern 2 | If a subprocessor is expected to be independently queryable/searchable across all vendors (e.g., "which vendors use Subprocessor X"), the embedded-array design makes that a full collection scan instead of an indexed query. Given assessments/documents already use this pattern at similar or larger scale, risk is low. |
| A4 | DPA create/sign/terminate should be gated on `_VENDOR_ADMIN_ROLES` (borrowed from `vendor_endpoints.py`), not left ungated like BAA's current `create_baa`. | Common Pitfalls — Pitfall 2 | If the intended role set differs (e.g., a legal/compliance-specific role should own DPA), this needs correction during plan-check or code review. Security-side risk is asymmetric (better to be gated and loosen later than the reverse), so this defaults to the safer choice. |

## Open Questions

1. **Should DPA reuse the `baa_endpoints.py` inline-router style (all logic in the endpoints file) or should it get its own `dpa_service.py` like vendor/risk do?**
   - What we know: BAA keeps everything in one file (169 lines); vendor/risk split service from endpoints.
   - What's unclear: Whether the planner should follow BAA's single-file style for maximum pattern fidelity, or the service-split style for consistency with vendor/risk (which VRISK-01 is nominally paired with in this phase).
   - Recommendation: Given CLAUDE.md's 500-line file cap and that BAA's own file is well under that limit, a single `dpa_endpoints.py` (BAA style) is simplest and most faithful to "mirror the BAA pattern" as literally instructed. Planner should pick this unless the DPA feature set grows large enough to warrant a split.

2. **Does "subprocessor discovery" imply any external/automated discovery mechanism (e.g., scanning a vendor's published subprocessor list URL), or is it purely manual data entry?**
   - What we know: The phase description says "a vendor record can list its own subprocessors" — phrased as a data-completeness gap, not an automation gap. No existing code in this repo does any external subprocessor scraping/discovery.
   - What's unclear: Whether "discovery" is literal (automated) or just the noun used for the vendor-transparency-report feature common in GRC tools (Comp AI/Probo/OpenLane, per the audit that spawned this phase).
   - Recommendation: Scope as manual CRUD (add/list/remove) per Pattern 2 above — matches every comparable feature-parity audit finding in this milestone (all Tier 1 phases are "quick fixes," not new automation surfaces), and matches the "checkbox flag" → "tracked lifecycle" framing used for DPA (i.e., "make it trackable data," not "make it auto-detected").

## Environment Availability

No external service dependencies beyond what the existing test suite and dev environment already require (MongoDB via Motor, already relied upon by every sibling endpoint file).

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| fastapi | All new/extended endpoints | Yes | 0.138.0 [VERIFIED: local venv] | — |
| pydantic | Request/response models | Yes | 2.13.4 [VERIFIED: local venv] | — |
| motor | MongoDB persistence | Yes | 3.7.1 [VERIFIED: local venv] | — |
| pytest / pytest-asyncio mode | New test files | Yes | `asyncio_mode = auto` configured in `pytest.ini` [VERIFIED: pytest.ini] | — |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (asyncio_mode=auto, FastAPI TestClient) [VERIFIED: pytest.ini, test_automation_and_baa.py] |
| Config file | `pytest.ini` (repo root) |
| Quick run command | `pytest backend/tests/test_dpa_endpoints.py backend/tests/test_vendor_subprocessors.py backend/tests/test_risk_inherent_residual.py -x` |
| Full suite command | `pytest` (from repo root — `testpaths = . backend` per `pytest.ini`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VRISK-01 | DPA create starts in `draft`, unsigned | unit | `pytest backend/tests/test_dpa_endpoints.py::TestDPACreate -x` | ❌ Wave 0 |
| VRISK-01 | Single-party sign does NOT activate (regression, mirrors BAA's own known bug class) | unit | `pytest backend/tests/test_dpa_endpoints.py::TestDPASign::test_single_party_sign_does_not_activate -x` | ❌ Wave 0 |
| VRISK-01 | Both-parties-signed activates DPA | unit | `pytest backend/tests/test_dpa_endpoints.py::TestDPASign::test_both_parties_signed_activates -x` | ❌ Wave 0 |
| VRISK-01 | Terminate sets status + respects tenant filter | unit | `pytest backend/tests/test_dpa_endpoints.py::TestDPATerminate -x` | ❌ Wave 0 |
| VRISK-01 | Non-admin role forbidden from creating DPA (Pitfall 2 fix) | unit | `pytest backend/tests/test_dpa_endpoints.py::TestDPACreate::test_create_forbidden_for_non_admin -x` | ❌ Wave 0 |
| VRISK-02 | Adding a subprocessor pushes to vendor's `subprocessors` array | unit | `pytest backend/tests/test_vendor_subprocessors.py::TestAddSubprocessor -x` | ❌ Wave 0 |
| VRISK-02 | Removing a subprocessor pulls it from the array | unit | `pytest backend/tests/test_vendor_subprocessors.py::TestRemoveSubprocessor -x` | ❌ Wave 0 |
| VRISK-02 | Subprocessor mutation respects tenant scope + RBAC | unit | `pytest backend/tests/test_vendor_subprocessors.py::TestSubprocessorRBAC -x` | ❌ Wave 0 |
| RISK-01 | `create_risk` populates both `risk_score`/`inherent_risk_score` and `residual_risk_score` | unit | `pytest backend/tests/test_risk_inherent_residual.py::TestRiskCreate -x` | ❌ Wave 0 |
| RISK-01 | `update_risk` recomputes residual score when residual inputs change | unit | `pytest backend/tests/test_risk_inherent_residual.py::TestRiskUpdate -x` | ❌ Wave 0 |
| RISK-01 | Omitting residual inputs defaults residual == inherent (no silent risk overstatement/understatement) | unit | `pytest backend/tests/test_risk_inherent_residual.py::TestRiskDefaults -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** Quick run command above (new test files only).
- **Per wave merge:** Full suite command (`pytest` from repo root).
- **Phase gate:** Full suite green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `backend/tests/test_dpa_endpoints.py` — covers VRISK-01, reuse `_col`/`_db`/`_user`/`_app` helpers from `test_automation_and_baa.py` (either import them or copy inline — this repo's convention is to copy inline per-file, based on `test_automation_and_baa.py`'s self-contained helper pattern).
- [ ] `backend/tests/test_vendor_subprocessors.py` — covers VRISK-02 (first-ever test file for `vendor_service.py`/`vendor_endpoints.py` — currently untested).
- [ ] `backend/tests/test_risk_inherent_residual.py` — covers RISK-01 (first-ever test file for `risk_service.py`/`risk_endpoints.py` — currently untested).
- [ ] No framework install needed — pytest + TestClient + AsyncMock pattern already fully configured.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | No new auth surface — all new routes sit behind existing `get_current_user`/`Depends(get_current_user)` |
| V3 Session Management | No | Unchanged — reuses existing `TokenData`/JWT session handling |
| V4 Access Control | Yes | Tenant-scoped `filt = {"id": ..., **self._scope(role, tenant_id)}` pattern (already used in `vendor_service.py`/`risk_service.py`/`baa_endpoints.py`) MUST be applied to every new DPA/subprocessor route; explicit admin-role gate on DPA mutations (see Pitfall 2 — do not silently inherit BAA's ungated `create_baa`) |
| V5 Input Validation | Yes | Pydantic models (`DPACreate`, `SubprocessorCreate`, extended `RiskCreate`/`RiskUpdate`) for all new request bodies; `residual_likelihood`/`residual_impact` should be range-validated 1-5 exactly like existing `likelihood`/`impact` (currently unvalidated at the pydantic level in `RiskCreate` — an existing gap this phase should not widen, but also isn't required to fix beyond the new fields it introduces) |
| V6 Cryptography | No | No new secrets, tokens, or encrypted fields introduced by this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Cross-tenant DPA/subprocessor/risk read or write via crafted `{id}` path param | Tampering / Elevation of Privilege | Tenant filter (`{"id": x, "tenantId": tenant_id}` unless super-admin role) on every read/write — verified existing pattern in `baa_endpoints.py`/`vendor_service.py`/`risk_service.py`; new routes MUST follow identically (see `test_terminate_respects_tenant_filter` in `test_automation_and_baa.py` as the exact regression-test shape to replicate for DPA and subprocessors) |
| Missing RBAC gate silently inherited from BAA's ungated `create_baa` | Elevation of Privilege | Explicit role check (`_VENDOR_ADMIN_ROLES` or equivalent) on DPA create/sign/terminate — do not copy BAA's create route without adding this check (Pitfall 2) |
| Unbounded array growth on `vendors.subprocessors` (no pagination/limit) | Denial of Service (resource exhaustion) | Low risk at expected scale (a vendor has a handful of subprocessors, not thousands) — no action needed beyond noting it; matches the same unbounded-but-low-risk shape already accepted for `assessments`/`documents` |

## Sources

### Primary (HIGH confidence)
- `backend/baa_endpoints.py` (full file read) — BAA lifecycle reference pattern
- `backend/vendor_service.py`, `backend/vendor_endpoints.py` (full files read) — vendor data model, confirmed no DPA field, confirmed unused `update_vendor()`, confirmed push-array pattern
- `backend/risk_service.py`, `backend/risk_endpoints.py` (full files read) — confirmed single blended `risk_score`, confirmed no separate treatment-effectiveness field
- `components/RiskRegister.tsx`, `components/RiskFormModal.tsx`, `components/VendorManagement.tsx`, `components/VendorFormModal.tsx`, `components/BAAManagement.tsx` (full files read) — frontend consumption patterns and confirmed absence of a vendor detail view
- `backend/tests/test_automation_and_baa.py` (full BAA test section read) — exact test harness pattern to reuse
- `backend/router_registry.py` (relevant sections read) — router registration mechanics and `_REQUIRED_ROUTERS` tier confirmation
- `backend/privacy_service.py` (relevant section read) — confirmed the pre-existing generic `privacy_contracts` DPA/MSA/NDA/SCC tracker is unrelated/unlinked to vendors, ruling it out as a reusable base for VRISK-01
- Local venv (`python3 -c "import fastapi..."`) — verified installed package versions
- `.planning/STATE.md`, `.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md`, `.planning/config.json` — phase requirements, milestone context, workflow toggles

### Secondary (MEDIUM confidence)
None — no external documentation lookups were needed for this phase.

### Tertiary (LOW confidence)
None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; all versions verified directly against the installed venv.
- Architecture: HIGH — every recommended pattern is a direct extension of code already read in full in this repo, not an external best-practice inference.
- Pitfalls: HIGH — Pitfall 1 (nav wiring) is directly evidenced by this project's own STATE.md history across three prior phases; Pitfall 2 (RBAC gap) and Pitfall 3 (breaking rename) are directly observed in the current code, not speculative.

**Research date:** 2026-07-06
**Valid until:** No expiry driver — this is internal-codebase research tied to the current state of these exact files, not a time-sensitive external ecosystem. Re-verify only if `baa_endpoints.py`, `vendor_service.py`, or `risk_service.py` change before this phase is planned/executed.
