# Phase 31: FAIR Risk Quantification - Pattern Map

**Mapped:** 2026-07-08
**Files analyzed:** 5
**Analogs found:** 5 / 5

**⚠️ PHASE 26 COLLISION CHECK (performed live this session):** `backend/risk_service.py`, `backend/risk_endpoints.py`, `components/RiskFormModal.tsx`, and `components/RiskRegister.tsx` were all read fresh in this session (not from stale research). None contain `inherent_risk_score`, `residual_likelihood`, `residual_impact`, or `residual_risk_score` — **Phase 26 has NOT executed yet** as of this pattern-mapping pass. All line numbers/excerpts below are anchored to this **pre-Phase-26** state.
**The Phase 31 plan MUST re-run this same check (`grep -q "residual_risk_score" backend/risk_service.py`) at planning/execution time** — if Phase 26 has landed by then, these line numbers will have shifted (though the code shapes shown here, e.g. `update_risk`'s tenant-filter block, are additive and should still exist near where shown, just possibly offset by Phase 26's new fields/params).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|-----------------|---------------|
| `backend/risk_service.py` (add `run_fair_simulation()`) | service | batch (synchronous vectorized compute) | `backend/xai_service.py` (`_compute_rf_importance`/`_shap_explanation`, numpy used synchronously in service layer) | role-match (numpy-in-service pattern); same file also self-analogs for the additive-field/tenant-filter conventions (`update_risk`) |
| `backend/risk_endpoints.py` (new `POST /{risk_id}/fair-simulation`) | route | request-response | `backend/risk_endpoints.py`'s own `update_risk` route (same file, exact tenant/role pattern) | exact |
| `components/RiskFormModal.tsx` (FAIR input fields) | component (form) | CRUD (form state → onSubmit) | same file — existing Likelihood/Impact `grid-cols-2` number-input block | exact |
| `components/RiskRegister.tsx` (FAIR summary display) | component (table/display) | request-response (render fetched data) | same file — existing Score-column `<td>` badge cell driven by `getRiskLevel()` | exact |
| `backend/tests/test_risk_fair_simulation.py` (NEW) | test | request-response (TestClient integration) | `backend/tests/test_automation_and_baa.py` (`_col`/`_db`/`_user`/`_app` helper block) | exact |

## Pattern Assignments

### `backend/risk_service.py` — add `run_fair_simulation()` (service, batch/synchronous compute)

**Analog for numpy-in-service pattern:** `backend/xai_service.py`

**Imports pattern** (`backend/xai_service.py` line 25):
```python
import numpy as np
```
Import numpy at module top of `risk_service.py` the same way — no lazy/conditional import needed (numpy is an unconditional dependency here, unlike `xai_service.py`'s optional `shap` import elsewhere in that file).

**Core synchronous numpy pattern** (`backend/xai_service.py` lines 178-188, plain module-level function, no I/O, called directly from request-adjacent code):
```python
def _compute_rf_importance(_model_id: str) -> List[Dict[str, Any]]:
    """Real permutation importance from a fitted RF on proxy data."""
    rf, X, y = _build_rf_and_data()
    result = permutation_importance(rf, X, y, n_repeats=5, random_state=7, n_jobs=1)
    importances = result.importances_mean
    total = max(importances.sum(), 1e-9)
    return [
        {"feature": _FEATURES[i], "importance": round(float(importances[i] / total), 4)}
        for i in np.argsort(importances)[::-1]
    ]
```
This confirms the codebase's established shape for "a pure, synchronous, numpy-using helper function with no DB access, called from a service method." `run_fair_simulation()` should follow this exact shape — a free function (or `RiskService` method) taking a plain `dict` of inputs and returning a plain `dict` of results, matching RESEARCH.md's Pattern 1 code (already fully specified there — reproduced for convenience):
```python
def run_fair_simulation(inputs: dict) -> dict:
    """Pure function — no I/O, no DB access. Runs synchronously in the request handler."""
    n = inputs.get("iterations", 10000)
    rng = np.random.default_rng()
    lef_samples = rng.triangular(inputs["lef_min"], inputs["lef_likely"], inputs["lef_max"], n)
    lm_samples = rng.triangular(inputs["lm_min"], inputs["lm_likely"], inputs["lm_max"], n)
    annual_loss = lef_samples * lm_samples
    sorted_losses = np.sort(annual_loss)
    exceedance_curve = [
        {"loss": float(sorted_losses[i]), "probability": float(1 - i / n)}
        for i in range(0, n, max(1, n // 100))
    ]
    return {
        "mean": float(np.mean(annual_loss)),
        "p10": float(np.percentile(annual_loss, 10)),
        "p50": float(np.percentile(annual_loss, 50)),
        "p90": float(np.percentile(annual_loss, 90)),
        "exceedance_curve": exceedance_curve,
    }
```

**Additive-field / tenant-filter pattern to reuse for persisting `fair_inputs`/`fair_results`** — self-analog, `backend/risk_service.py` lines 58-70 (`update_risk`, current pre-Phase-26 state, read this session):
```python
async def update_risk(self, risk_id: str, updates: Dict[str, Any], tenant_id: Optional[str] = None, role: str = "") -> Optional[Dict]:
    db = self._db()
    filt: Dict[str, Any] = {"id": risk_id}
    if role not in _RISK_SUPER_ROLES:
        filt["tenantId"] = tenant_id
    existing = await db.risks.find_one(filt, {"_id": 0})
    if not existing:
        return None
    merged = {**existing, **updates, "updated_at": datetime.now(timezone.utc).isoformat()}
    if "likelihood" in updates or "impact" in updates:
        merged["risk_score"] = merged.get("likelihood", existing["likelihood"]) * merged.get("impact", existing["impact"])
    await db.risks.replace_one(filt, merged)
    return merged
```
A new `attach_fair_results(risk_id, fair_inputs, fair_results, tenant_id, role)` method should reuse this exact `filt`/tenant-scoping/`find_one`→merge→`replace_one` shape — do not write a new, separate lookup query (see Security Domain below, Pitfall 4 from RESEARCH.md).

**`Risk` Pydantic model** (`backend/risk_service.py` lines 6-24, current state — no Phase 26 fields present):
```python
class Risk(BaseModel):
    id: str
    title: str
    description: str
    category: str
    status: str
    likelihood: int
    impact: int
    risk_score: int
    owner: str
    mitigation_plan: Optional[str] = None
    created_at: str
    updated_at: str
    ai_system_id: Optional[str] = None
    vendor_id: Optional[str] = None
```
Add `fair_inputs: Optional[Dict[str, Any]] = None` and `fair_results: Optional[Dict[str, Any]] = None` as new optional fields — additive, matches this model's existing `Optional[...] = None` convention for `mitigation_plan`/`ai_system_id`/`vendor_id`. **If Phase 26 has executed by plan time, this model will already have `inherent_risk_score`/`residual_*` fields added the same way — add the FAIR fields alongside them, do not disturb them.**

---

### `backend/risk_endpoints.py` — new `POST /{risk_id}/fair-simulation` (route, request-response)

**Analog:** same file's `update_risk` route, lines 51-62 (current pre-Phase-26 state):
```python
@router.put("/{risk_id}")
async def update_risk(
    risk_id: str,
    risk: RiskUpdate,
    current_user: TokenData = Depends(get_current_user),
):
    role = getattr(current_user, "role", "")
    tenant_id = getattr(current_user, "tenant_id", None) or None
    updated_risk = await risk_service.update_risk(risk_id, risk.dict(exclude_unset=True), tenant_id=tenant_id, role=role)
    if not updated_risk:
        raise HTTPException(status_code=404, detail="Risk not found")
    return updated_risk
```
The new route must copy this exact `role`/`tenant_id` extraction + `if not updated: raise HTTPException(404, ...)` shape — do not write a separate, unscoped risk lookup (RESEARCH.md Pitfall 4 / Security Domain).

**`_risk_tenant` helper** (lines 31-35, used by `create_risk`, available for reuse):
```python
def _risk_tenant(current_user: TokenData) -> str:
    tid = getattr(current_user, "tenant_id", None) or None
    if not tid:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tid
```

**New `FairInputs` request model** — follow the existing `RiskUpdate`/`RiskCreate` BaseModel style (lines 9-19, 21-29) but with explicit `Field(ge=0)`/range validation per RESEARCH.md Pattern 1 and Pitfall 2/3 (min≤likely≤max validator, bounded `iterations`). Existing models use plain, unconstrained pydantic fields (`likelihood: int`, no `Field(...)`) — this is the first endpoint in this file needing `Field(...)` constraints; that's expected since RESEARCH.md flags V5 Input Validation as this phase's central risk, not a deviation to avoid.

**Import block** (lines 1-5, copy verbatim style):
```python
from fastapi import APIRouter, HTTPException, Depends
from risk_service import risk_service
from pydantic import BaseModel
from authentication_service import get_current_user
from auth_types import TokenData
```
Add `import numpy as np` only if any validation logic needs it directly (unlikely — `run_fair_simulation` lives in `risk_service.py` per RESEARCH.md's service/route split).

---

### `components/RiskFormModal.tsx` — FAIR input fields (component, CRUD form)

**Analog:** same file's existing Likelihood/Impact number-input grid, lines 92-115 (current 136-line pre-Phase-26 state):
```tsx
<div className="grid grid-cols-2 gap-4">
  <div>
    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Likelihood (1-5)</label>
    <input
      type="number"
      min="1"
      max="5"
      value={formData.likelihood}
      onChange={e => setFormData({ ...formData, likelihood: parseInt(e.target.value) })}
      className="w-full rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
    />
  </div>
  <div>
    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Impact (1-5)</label>
    <input
      type="number"
      min="1"
      max="5"
      value={formData.impact}
      onChange={e => setFormData({ ...formData, impact: parseInt(e.target.value) })}
      className="w-full rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
    />
  </div>
</div>
```
A new "Quantify with FAIR" section should copy this exact `grid grid-cols-2 gap-4` + labeled `<input type="number">` shape for the six LEF/LM min/likely/max fields (likely a `grid-cols-3` row per RESEARCH.md's min/likely/max triple, repeated for LEF and LM) — same Tailwind classes, same `formData`/`setFormData` spread-update convention.

**`formData` state shape** (lines 11-19):
```tsx
const [formData, setFormData] = useState({
  title: '',
  description: '',
  category: 'Enterprise',
  status: 'Open',
  likelihood: 1,
  impact: 1,
  owner: ''
});
```
Extend with an optional `fairInputs` sub-object (e.g., `fairInputs: null | { lef_min, lef_likely, lef_max, lm_min, lm_likely, lm_max }`), consistent with this feature being opt-in per RESEARCH.md — likely gated behind a toggle/checkbox ("Quantify with FAIR") that only appears in `RiskDetail`/edit context (this component is currently only used for **create**, per its single `onSubmit`/"New Risk" title — the FAIR-simulation trigger is a `POST .../fair-simulation` on an *existing* risk, so it may need to live in a follow-up edit view, not this create-only modal — **flag this for the planner**, see "No Analog Found" below).

**`handleSubmit`/`onSubmit` pattern** (lines 24-35): unchanged — FAIR fields, if collected here, would ride along in the same `formData` object passed to `onSubmit`.

---

### `components/RiskRegister.tsx` — FAIR summary display (component, request-response render)

**Analog:** same file's existing Score-column badge cell, lines 202-206 (current 246-line pre-Phase-26 state):
```tsx
<td className="px-6 py-4">
  <span className={`px-2 py-1 rounded-md text-xs font-semibold ${level.color}`}>
    {risk.risk_score} ({level.label})
  </span>
</td>
```
driven by `getRiskLevel()` (lines 48-53):
```tsx
const getRiskLevel = (score: number) => {
    if (score >= 20) return { label: 'Critical', color: 'text-red-600 bg-red-100 dark:text-red-400 dark:bg-red-900/30' };
    if (score >= 12) return { label: 'High', color: 'text-orange-600 bg-orange-100 dark:text-orange-400 dark:bg-orange-900/30' };
    if (score >= 6) return { label: 'Medium', color: 'text-yellow-600 bg-yellow-100 dark:text-yellow-400 dark:bg-yellow-900/30' };
    return { label: 'Low', color: 'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900/30' };
};
```
A new "FAIR" `<th>`/`<td>` column should copy this badge-cell shape, e.g. rendering `risk.fair_results ? "$${p10}–$${p90} (90% CI)" : "Not quantified"` with a neutral-gray badge when `fair_results` is absent — matches RESEARCH.md's Architecture Diagram exactly. Add the `<th>` next to the existing `<th className="px-6 py-3 font-medium">Score</th>` (line 181) and the `<td>` next to the Score `<td>` (lines 202-206).

**Frontend `Risk` interface** (lines 10-23, local to this file — "should eventually be moved to types.ts" per its own comment):
```tsx
interface Risk {
    id: string;
    title: string;
    description: string;
    category: 'Enterprise' | 'AI' | 'Compliance' | 'Third-Party' | 'Cyber';
    status: 'Open' | 'Mitigated' | 'Accepted' | 'Transferred' | 'Avoided';
    likelihood: number;
    impact: number;
    risk_score: number;
    owner: string;
    mitigation_plan?: string;
    created_at: string;
    updated_at: string;
}
```
Add `fair_inputs?: {...}` and `fair_results?: { mean: number; p10: number; p50: number; p90: number; exceedance_curve: {loss:number; probability:number}[] }` as optional fields, matching the existing `mitigation_plan?:` optional-field convention.

**API call convention** — `services/apiService.ts` lines 1369-1388 (`fetchRisks`/`createRisk`, current state, read this session):
```typescript
export const fetchRisks = async (): Promise<Risk[]> => {
    try {
        const res = await authFetch(`${API_BASE}/risks`);
        if (!res.ok) throw new Error("Failed to fetch risks");
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.error("Error fetching risks:", e);
        return [];
    }
};

export const createRisk = async (riskData: any): Promise<Risk> => {
    const res = await authFetch(`${API_BASE}/risks`, {
        method: 'POST',
        body: JSON.stringify(riskData)
    });
    if (!res.ok) throw new Error("Failed to create risk");
    return await res.json();
};
```
A new `runFairSimulation(riskId: string, inputs: FairInputs): Promise<Risk>` should copy `createRisk`'s exact `authFetch(..., {method:'POST', body: JSON.stringify(...)})` + `if (!res.ok) throw` shape, POSTing to `` `${API_BASE}/risks/${riskId}/fair-simulation` ``.

---

### `backend/tests/test_risk_fair_simulation.py` (NEW, test, request-response/TestClient integration)

**Analog:** `backend/tests/test_automation_and_baa.py` lines 1-62 (helper block + fixture pattern, read this session) — clone verbatim, changing only the router import target:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user
from auth_types import TokenData


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


def _user(role="security_analyst", tenant_id="t1"):
    return TokenData(username="test@example.com", role=role, tenant_id=tenant_id, mfa_verified=True)


def _app(router, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app
```
For this phase's tests, `_col(find_one=AsyncMock(return_value={...existing risk doc...}))` seeded with a `db.risks` collection (patched via `patch("risk_endpoints.get_database", return_value=db)` — verify the exact patch target matches how `risk_service.py`'s `_db()` imports `get_database`, mirroring `patch("automation_endpoints.get_database", ...)` at line 78 of the analog) is the pattern for the `valid_simulation`, `invalid_range`, `iteration_bound`, `tenant_isolation`, and `optional_no_regression` test cases RESEARCH.md's Validation Architecture section specifies. The `math_sanity` test (LEF fixed at 1, LM fixed at 100 → mean ≈ 100) should call `risk_service.run_fair_simulation()` directly (pure function, no mocking needed) rather than going through `TestClient`.

## Shared Patterns

### Tenant isolation / role-based super-admin bypass
**Source:** `backend/risk_service.py` `_RISK_SUPER_ROLES` (line 26) + `update_risk`'s `filt`/`role` block (lines 58-62)
**Apply to:** `run_fair_simulation`'s persistence path (`attach_fair_results`) and the new `POST /{risk_id}/fair-simulation` route — reuse `_RISK_SUPER_ROLES` and the identical `filt["tenantId"] = tenant_id` unless role in that set, do not duplicate or reinvent.

### Synchronous numpy-in-service computation (no BackgroundTasks/Celery)
**Source:** `backend/xai_service.py` (`import numpy as np` at module top, `_compute_rf_importance`/`_shap_explanation` as plain synchronous functions)
**Apply to:** `risk_service.run_fair_simulation()` — call directly inside the `async def` route handler without `run_in_threadpool`, matching this established in-repo precedent (contrast: `backend/tasks.py`'s `@celery_app.task` shape is explicitly the pattern NOT to follow here, per RESEARCH.md Anti-Patterns).

### Additive-optional-field convention on the `Risk` model / frontend `Risk` interface
**Source:** `backend/risk_service.py` `Risk.mitigation_plan: Optional[str] = None` / `RiskRegister.tsx`'s `mitigation_plan?: string`
**Apply to:** `fair_inputs`/`fair_results` on both the Pydantic model and the TS interface — same `Optional[...] = None` / `?:` shape, never required.

### `authFetch` + `if (!res.ok) throw` API-call convention
**Source:** `services/apiService.ts` `createRisk` (lines 1381-1388)
**Apply to:** New `runFairSimulation()` function in `apiService.ts`.

## No Analog Found / Planner Flags

| Concern | Detail |
|---------|--------|
| `RiskFormModal.tsx` is create-only | This component's single `onSubmit` prop and "New Risk" hardcoded title (line 41) indicate it is currently only wired for **creating** a risk (`RiskRegister.tsx`'s only usage, lines 236-243, passes `api.createRisk`). FAIR simulation is inherently a **post-creation** action (`POST /api/risks/{id}/fair-simulation` needs an existing `risk_id`). The planner must decide whether to (a) add FAIR fields to this modal reused in an edit mode (would need an `isEdit`/`initialData` prop this component doesn't currently have), (b) add a separate "Quantify with FAIR" trigger/panel in `RiskRegister.tsx`'s row-actions column (there's already an unwired `Edit2`/`Trash2` icon-button pair at lines 220-227 with no `onClick` handlers — those are themselves not yet functional), or (c) a new small `RiskFairPanel.tsx` component (RESEARCH.md's Recommended Project Structure already floats this as a fallback for CLAUDE.md's 500-line cap). No existing analog in this codebase currently threads a "select existing row → run async action → refresh row" flow for the Risk Register specifically; the closest analog for that *general* shape elsewhere in the codebase should be identified by the planner if needed (out of scope for this pattern map's 3-5-analog budget). |
| Phase 26 collision | Re-stated for emphasis: all excerpts above are pre-Phase-26. The plan's tasks should be written as **additive, append-style edits** (add new fields/routes/inputs near — not overwriting — existing ones) so they remain valid whether or not Phase 26 has landed by execution time, per RESEARCH.md Pitfall 1's explicit recommendation. |

## Metadata

**Analog search scope:** `backend/risk_service.py`, `backend/risk_endpoints.py`, `backend/xai_service.py`, `backend/tests/test_automation_and_baa.py`, `components/RiskFormModal.tsx`, `components/RiskRegister.tsx`, `services/apiService.ts`
**Files scanned:** 7 (all read fresh this session; `xai_service.py` targeted-read at lines 175-194 plus grep-located import at line 25)
**Pattern extraction date:** 2026-07-08
