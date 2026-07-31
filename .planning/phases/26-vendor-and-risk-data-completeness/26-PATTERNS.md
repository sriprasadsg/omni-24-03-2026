# Phase 26: Vendor and Risk Data Completeness - Pattern Map

**Mapped:** 2026-07-06
**Files analyzed:** 12
**Analogs found:** 12 / 12 (no CONTEXT.md exists for this phase; RESEARCH.md is the sole source, per orchestrator instruction)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/dpa_endpoints.py` (NEW) | controller (inline-style, no service split) | CRUD + state-machine lifecycle | `backend/baa_endpoints.py` | exact |
| `backend/router_registry.py` (EXTEND) | config | request-response (startup wiring) | same file, `baa_endpoints` registration line | exact |
| `backend/tests/test_dpa_endpoints.py` (NEW) | test | request-response | `backend/tests/test_automation_and_baa.py` (BAA test classes) | exact |
| `backend/vendor_service.py` (EXTEND: add_subprocessor/list/remove) | service | CRUD (push-to-array sub-resource) | same file, `add_document`/`add_assessment` methods | exact |
| `backend/vendor_endpoints.py` (EXTEND: 3 subprocessor routes) | controller/route | request-response | same file, `upload_vendor_document`/`add_assessment` routes | exact |
| `backend/tests/test_vendor_subprocessors.py` (NEW) | test | request-response | `backend/tests/test_automation_and_baa.py` (helper harness) | role-match |
| `backend/risk_service.py` (EXTEND: residual fields) | service | CRUD (computed fields) | same file, `create_risk`/`update_risk` | exact |
| `backend/risk_endpoints.py` (EXTEND: RiskCreate/RiskUpdate) | controller/route | request-response | same file | exact |
| `backend/tests/test_risk_inherent_residual.py` (NEW) | test | request-response | `backend/tests/test_automation_and_baa.py` (helper harness) | role-match |
| `components/VendorDetailModal.tsx` (NEW) | component (modal) | request-response (fetch on open) | `components/AgentDetailModal.tsx` (modal shell/prop pattern) + `components/VendorFormModal.tsx` (project-specific modal chrome) | role-match |
| `components/VendorManagement.tsx` (EXTEND: wire row action) | component | request-response | same file (own `showAddModal`/`VendorFormModal` wiring pattern) | exact |
| `components/RiskRegister.tsx` (EXTEND: residual column) | component | request-response | same file (existing Score column rendering) | exact |
| `components/RiskFormModal.tsx` (EXTEND: residual inputs) | component | request-response | same file (existing likelihood/impact inputs) | exact |
| `components/DPAManagement.tsx` (NEW, optional per Open Question 1) | component | request-response | `components/BAAManagement.tsx` (not read in this pass — RESEARCH.md already fully documents it as the literal clone target; not re-read here since it adds no new pattern signal beyond what RESEARCH.md Pattern 1 already extracted) | exact (per RESEARCH.md) |
| `types.ts` (EXTEND: Risk fields, DPA/Subprocessor interfaces, AppView union) | model/types | n/a | same file, `Risk`/`VendorAssessment`/`AppView` blocks | exact |
| `App.tsx` (EXTEND: new view case) | route/config | request-response | same file, `case 'baaManagement':` (line 1898) | exact |
| `components/Sidebar.tsx` (EXTEND: nav entry) | config | n/a | same file, `baaManagement` nav item (line 373) | exact |

## Pattern Assignments

### `backend/dpa_endpoints.py` (controller, CRUD/lifecycle) — clone of `backend/baa_endpoints.py`

**Analog:** `backend/baa_endpoints.py` (full file, 169 lines — copy verbatim then diff as noted)

**Imports + router setup** (lines 1-9):
```python
"""Business Associate Agreement (BAA) management endpoints (HIPAA §164.308(b))."""
from __future__ import annotations
import time
from fastapi import APIRouter, HTTPException, Depends
from auth_utils import get_current_user

router = APIRouter(prefix="/api/baa", tags=["BAA Management"])

_BAA_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}
```
For DPA: `router = APIRouter(prefix="/api/dpa", tags=["DPA Management"])`. Also add `_DPA_ADMIN_ROLES = {"Super Admin", "super_admin", "platform-admin", "admin", "Tenant Admin"}` — copied from `vendor_endpoints.py`'s `_VENDOR_ADMIN_ROLES` (line 10), NOT from BAA's `_BAA_SUPER_ROLES` (see Pitfall 2 below — BAA's roles are used only for tenant-scope elevation, not create-gating).

**Helper functions to copy verbatim** (lines 12-29): `_db()` (lazy `from database import get_database`), `_tenant(user)`, `_role(user)`, `_sub(user)`. These handle both `TokenData` objects and dict-shaped users.

**Create pattern — DEVIATE here** (lines 94-118, analog):
```python
@router.post("")
async def create_baa(payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    tenant_id = _tenant(current_user)
    baa = {
        "id": f"baa-{int(time.time())}",
        ...
        "status": "draft",
        "signed_by_vendor": False,
        "signed_by_us": False,
        "created_by": _sub(current_user),
        "created_at": time.time(),
    }
    if tenant_id:
        baa["tenantId"] = tenant_id
    await db["baa_agreements"].insert_one(baa)
    baa.pop("_id", None)
    return baa
```
**REQUIRED DEVIATION (Pitfall 2 fix):** BAA's `create_baa` has NO role check at all. For `create_dpa`, add at the top of the function body:
```python
if _role(current_user) not in _DPA_ADMIN_ROLES:
    raise HTTPException(status_code=403, detail="Admin access required")
```
Add the same gate to `sign_dpa` and `terminate_dpa`. Also add `"vendor_id": payload.get("vendor_id")` to the created doc (BAA has no such field — this is the one intentional schema addition per RESEARCH.md Assumption A1).

**Sign pattern (dual-party activation) — copy verbatim** (lines 137-154):
```python
@router.post("/{baa_id}/sign")
async def sign_baa(baa_id: str, payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    tenant_id = _tenant(current_user)
    baa_filter: dict = {"id": baa_id}
    if _role(current_user) not in _BAA_SUPER_ROLES:
        baa_filter["tenantId"] = tenant_id
    party = payload.get("party", "us")
    update_field = "signed_by_vendor" if party == "vendor" else "signed_by_us"
    await db["baa_agreements"].update_one(
        baa_filter,
        {"$set": {update_field: True, f"{update_field}_at": time.time(),
                  f"{update_field}_by": _sub(current_user)}}
    )
    doc = await db["baa_agreements"].find_one(baa_filter)
    if doc and doc.get("signed_by_us") and doc.get("signed_by_vendor"):
        await db["baa_agreements"].update_one(baa_filter, {"$set": {"status": "active"}})
    return {"ok": True}
```
This is the exact "single-party sign must not activate" logic referenced in the requirements test map — copy the `if doc and doc.get(...) and doc.get(...)` guard exactly; do not simplify to an `or`.

**Terminate pattern — copy verbatim** (lines 157-168), **stats pattern — copy verbatim** (lines 56-79, swap collection name `baa_agreements` → `dpa_agreements`), **get/list patterns — copy verbatim** (lines 46-53, 82-91).

**Tenant-scope filter idiom used everywhere** (repeated 5x in this file):
```python
baa_filter: dict = {"id": baa_id}
if _role(current_user) not in _BAA_SUPER_ROLES:
    baa_filter["tenantId"] = tenant_id
```
Reuse this exact idiom for every DPA route.

---

### `backend/router_registry.py` (config) — register the new router

**Analog:** same file, existing BAA registration.

**Exact line to add near** (verified, line 219):
```python
_load(app, "baa_endpoints",                    "router")
```
Add immediately after (or in the same tier block):
```python
_load(app, "dpa_endpoints",                    "router")
```
Do NOT add `"dpa_endpoints"` to `_REQUIRED_ROUTERS` (frozenset at line 19) — BAA itself is absent from that set, so a load failure should log-and-continue, matching BAA's own risk tier (RESEARCH.md Pitfall 4).

---

### `backend/tests/test_dpa_endpoints.py` (NEW) — clone harness

**Analog:** `backend/tests/test_automation_and_baa.py`

**Helper pattern to copy inline** (this repo's convention is copy-per-file, not shared import):
```python
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
```
**Critical patch target:** `baa_endpoints.py`'s `_db()` does `from database import get_database` LAZILY inside the function body, so tests patch `"database.get_database"` (module-level source), never `"dpa_endpoints.get_database"`. Use the same patch target since `dpa_endpoints.py` will copy the same lazy-import `_db()` helper:
```python
with patch("database.get_database", return_value=db):
    res = TestClient(app).post("/api/dpa", json={"business_associate": "ACME Corp", "vendor_id": "v-1"})
```
Required test classes (from requirements table): `TestDPACreate` (incl. `test_create_forbidden_for_non_admin` — asserts 403, the Pitfall 2 regression test), `TestDPASign` (incl. `test_single_party_sign_does_not_activate`, `test_both_parties_signed_activates`), `TestDPATerminate` (incl. tenant-filter respect, mirroring `test_terminate_respects_tenant_filter` from the BAA suite).

---

### `backend/vendor_service.py` (EXTEND) — subprocessor push/pull methods

**Analog:** same file, `add_document` (lines 138-147) and `add_assessment` (lines 79-92).

**Exact pattern to mirror** (`add_document`, lines 138-147):
```python
async def add_document(self, vendor_id: str, doc_data: Dict[str, Any], tenant_id: Optional[str] = None, role: str = "") -> bool:
    db = get_database()
    doc = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **doc_data,
    }
    filt = {"id": vendor_id, **self._scope(role, tenant_id)}
    result = await db.vendors.update_one(filt, {"$push": {"documents": doc}})
    return result.matched_count > 0
```
New methods to add (per RESEARCH.md Pattern 2, already fully drafted there):
```python
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
`_scope()` (lines 38-41) is the tenant/role gate used by every vendor_service method — reuse it, do not reimplement.

**DO NOT USE:** `update_vendor()` (lines 65-72) — unused generic `$set`, would allow overwriting the whole array (Anti-Pattern in RESEARCH.md).

---

### `backend/vendor_endpoints.py` (EXTEND) — 3 subprocessor routes

**Analog:** same file, `upload_vendor_document` (lines 87-100) for the RBAC-gated mutation shape, `add_assessment` (lines 62-74) for the request-body-model shape.

**Exact pattern to mirror** (`upload_vendor_document`, lines 87-100):
```python
@router.post("/{vendor_id}/documents")
async def upload_vendor_document(
    vendor_id: str,
    doc_name: str,
    doc_type: str,
    current_user: TokenData = Depends(get_current_user),
):
    if getattr(current_user, "role", "") not in _VENDOR_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    tid, role = _v_ctx(current_user)
    success = await vendor_service.add_document(vendor_id, {"name": doc_name, "type": doc_type}, tenant_id=tid, role=role)
    if not success:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return {"message": "Document uploaded successfully"}
```
New routes: `POST /{vendor_id}/subprocessors` (define `SubprocessorCreate(BaseModel)` mirroring `AssessmentCreate` at lines 24-29), `GET /{vendor_id}/subprocessors` (convenience read route — optional per RESEARCH.md, since `get_vendor` already returns the full doc), `DELETE /{vendor_id}/subprocessors/{sub_id}`. Gate all mutations on `_VENDOR_ADMIN_ROLES` (line 10) exactly like `upload_vendor_document`/`add_assessment`/`delete_vendor`.

---

### `backend/tests/test_vendor_subprocessors.py` (NEW)

**Analog:** `backend/tests/test_automation_and_baa.py` helper harness (see DPA test section above — copy the same `_col`/`_db` shape; `vendor_service`/`vendor_endpoints` currently has zero test coverage, so there is no existing vendor-specific test file to extend). Required classes: `TestAddSubprocessor`, `TestRemoveSubprocessor`, `TestSubprocessorRBAC`.

---

### `backend/risk_service.py` (EXTEND) — additive residual fields

**Analog:** same file, `create_risk` (lines 39-56) and `update_risk` (lines 58-70).

**Current create_risk (exact, lines 39-56):**
```python
async def create_risk(self, risk_data: Dict[str, Any], tenant_id: Optional[str] = None) -> Dict:
    db = self._db()
    likelihood = int(risk_data.get("likelihood", 1))
    impact = int(risk_data.get("impact", 1))
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "created_at": now,
        "updated_at": now,
        "risk_score": likelihood * impact,
        **risk_data,
    }
    doc["likelihood"] = likelihood
    doc["impact"] = impact
    doc["tenantId"] = tenant_id
    await db.risks.insert_one(doc)
    doc.pop("_id", None)
    return doc
```
**Additive change** (per RESEARCH.md Pattern 3, verbatim recommendation):
```python
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
        "risk_score": likelihood * impact,                              # unchanged
        "inherent_risk_score": likelihood * impact,                     # new alias
        "residual_likelihood": residual_likelihood,
        "residual_impact": residual_impact,
        "residual_risk_score": residual_likelihood * residual_impact,   # new
        **risk_data,
    }
    doc["likelihood"] = likelihood
    doc["impact"] = impact
    doc["tenantId"] = tenant_id
    await db.risks.insert_one(doc)
    doc.pop("_id", None)
    return doc
```
**update_risk current recompute idiom (exact, lines 67-68)** — extend analogously for residual fields:
```python
if "likelihood" in updates or "impact" in updates:
    merged["risk_score"] = merged.get("likelihood", existing["likelihood"]) * merged.get("impact", existing["impact"])
```
Add: `if "residual_likelihood" in updates or "residual_impact" in updates: merged["residual_risk_score"] = merged.get("residual_likelihood", existing.get("residual_likelihood", existing["likelihood"])) * merged.get("residual_impact", existing.get("residual_impact", existing["impact"]))`.

**`Risk` pydantic model (lines 6-24)** — add optional fields, do not remove `risk_score`:
```python
class Risk(BaseModel):
    ...
    risk_score: int  # likelihood * impact  — KEEP AS-IS, never rename
    ...
```
Add `inherent_risk_score: int`, `residual_likelihood: int`, `residual_impact: int`, `residual_risk_score: int` as new fields (with defaults if the model is used for response validation elsewhere — check call sites before making non-optional).

---

### `backend/risk_endpoints.py` (EXTEND)

**Analog:** same file, `RiskCreate`/`RiskUpdate` (lines 9-29).

**Current (exact):**
```python
class RiskCreate(BaseModel):
    title: str
    description: str
    category: str
    status: str
    likelihood: int
    impact: int
    owner: str
    mitigation_plan: str = None
    ai_system_id: str = None
    vendor_id: str = None

class RiskUpdate(BaseModel):
    title: str = None
    ...
    likelihood: int = None
    impact: int = None
    owner: str = None
    mitigation_plan: str = None
```
Add `residual_likelihood: int = None` and `residual_impact: int = None` to both models (RESEARCH.md notes `likelihood`/`impact` are already unvalidated 1-5 at the pydantic level — this phase is not required to fix that gap, just not widen it; do not add stricter validation than already exists unless trivial).

---

### `backend/tests/test_risk_inherent_residual.py` (NEW)

**Analog:** same harness pattern as `test_dpa_endpoints.py` above (copy `_col`/`_db` inline). Required classes: `TestRiskCreate`, `TestRiskUpdate`, `TestRiskDefaults` (asserts residual == inherent when omitted — the honest-default regression test from RESEARCH.md Assumption A2).

---

### `components/VendorDetailModal.tsx` (NEW) — first vendor detail view

**Analog:** `components/AgentDetailModal.tsx` for the modal-shell/prop-interface convention (this is the closest "row click opens detail" component that exists in this codebase); `components/VendorFormModal.tsx` / `components/RiskFormModal.tsx` for the project's lighter-weight modal chrome (overlay + rounded panel + X close button) that is more appropriate in scale for a first vendor detail view than AgentDetailModal's full tabbed 686-line implementation.

**Modal shell + prop-interface pattern to mirror** (`AgentDetailModal.tsx`, lines 17-29):
```typescript
interface AgentDetailModalProps {
    isOpen: boolean;
    onClose: () => void;
    agent: Agent | null;
    asset?: Asset;
    onManageCapabilities: (agent: Agent) => void;
    onViewRemediationLogs: (agent: Agent) => void;
    onViewLogs: (agent: Agent) => void;
    onRunDiagnostics?: (agent: Agent) => void;
    onDeleteAgent?: (agent: Agent) => void;
    onRefresh?: () => void;
    isRefreshing?: boolean;
}
```
For `VendorDetailModal`, use the simpler shape (matching `RiskFormModal`'s lighter convention, lines 4-8):
```typescript
interface VendorDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  vendor: Vendor | null;
}
```
**Overlay + panel chrome to copy** (`RiskFormModal.tsx`, lines 37-45 — this is the simplest/most current modal chrome in this codebase, prefer it over AgentDetailModal's heavier tabbed layout):
```typescript
if (!isOpen) return null;
return (
  <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-lg overflow-hidden">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
        <h3 className="font-semibold text-lg text-gray-900 dark:text-white">...</h3>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200">
          <X className="w-5 h-5" />
        </button>
      </div>
      {/* body: DPA status section + subprocessor list + add-subprocessor form */}
    </div>
  </div>
);
```
Content to render inside: DPA status for this vendor (fetch `/api/dpa?vendor_id=X` or filter client-side from a full `/api/dpa` list — per RESEARCH.md Pattern 1), and `vendor.subprocessors` list with an inline add form posting to `/api/vendors/{id}/subprocessors` and a remove button calling `DELETE /api/vendors/{id}/subprocessors/{sub_id}`.

---

### `components/VendorManagement.tsx` (EXTEND) — wire the dead action button

**Analog:** same file, existing `showAddModal`/`VendorFormModal` wiring (lines 37, 185-192) — this is the pattern to replicate for the second modal.

**Current dead code (exact, lines 38, 174-178):**
```typescript
const [selectedVendor, setSelectedVendor] = useState<Vendor | null>(null);
// ...
<button className="text-gray-400 hover:text-teal-600 p-2">
    <MoreHorizontal className="w-5 h-5" />
</button>
```
**Fix, mirroring the existing `showAddModal` wiring at line 185-192:**
```typescript
<button
    onClick={() => setSelectedVendor(vendor)}
    className="text-gray-400 hover:text-teal-600 p-2"
>
    <MoreHorizontal className="w-5 h-5" />
</button>
```
And add (mirroring the `<VendorFormModal ... />` render block at lines 185-192):
```typescript
<VendorDetailModal
    isOpen={!!selectedVendor}
    onClose={() => setSelectedVendor(null)}
    vendor={selectedVendor}
/>
```
Also add `import { VendorDetailModal } from './VendorDetailModal';` alongside the existing `import { VendorFormModal } from './VendorFormModal';` (line 7).

---

### `components/RiskRegister.tsx` (EXTEND) — add Residual Score column

**Analog:** same file, existing Score column (lines 202-206, `getRiskLevel` at lines 48-53).

**Current Score cell (exact, lines 202-206):**
```typescript
<td className="px-6 py-4">
    <span className={`px-2 py-1 rounded-md text-xs font-semibold ${level.color}`}>
        {risk.risk_score} ({level.label})
    </span>
</td>
```
**Add a parallel column** (per RESEARCH.md Code Examples section) using `risk.residual_risk_score` with the same `getRiskLevel()` bucketing — add a `<th>Residual Score</th>` header (alongside line 181) and a matching `<td>` computing `const residualLevel = getRiskLevel(risk.residual_risk_score);` then rendering it identically to the existing cell. Do not touch the existing `risk_score` references (lines 134, 189, 204) — these must remain untouched (Pitfall 3).

---

### `components/RiskFormModal.tsx` (EXTEND) — optional residual inputs

**Analog:** same file, existing Likelihood/Impact number inputs (lines 92-115).

**Exact pattern to duplicate for residual fields:**
```typescript
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
```
Add `residual_likelihood`/`residual_impact` to `formData` initial state (line 11-19, currently has no residual fields) with the same shape, defaulting to `likelihood`/`impact` values if left blank at submit time (mirrors backend default behavior — see risk_service.py section above).

---

### `types.ts` (EXTEND)

**Analog:** same file — `Risk` interface (lines 1558-1571), `AppView` union (lines 5-17), `VendorAssessment`/`Vendor` interfaces (lines 1573+).

**Current `Risk` interface (exact, lines 1558-1571):**
```typescript
export interface Risk {
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
Add (do not remove `risk_score`): `inherent_risk_score: number; residual_likelihood: number; residual_impact: number; residual_risk_score: number;`.

Add new interfaces (no existing DPA/Subprocessor interface in this file — model on `VendorAssessment`, lines 1573-1580):
```typescript
export interface Subprocessor {
    id: string;
    name: string;
    purpose: string;
    data_categories: string[];
    location: string;
    added_at: string;
}

export interface DPA {
    id: string;
    vendor_id?: string;
    business_associate: string;
    status: 'draft' | 'pending_signature' | 'active' | 'terminated' | 'expired';
    signed_by_vendor: boolean;
    signed_by_us: boolean;
    // ... mirror BAA's full shape
}
```

**`AppView` union — exact current state (lines 5-17, showing the `baaManagement` precedent at line 14 for the sibling entry to copy from):**
```typescript
export type AppView =
  | 'dashboard'
  | 'riskRegister'
  | 'vendorManagement'
  | 'trustCenter'
  | 'secureFileShare'
  | 'pipelineSecurity'
  | 'iacSecurity'
  | 'containerScan'
  | 'pam'
  | 'baaManagement'
  | 'codeReviewGraph'
  | 'supportChat'
  | 'agentChat'
  | 'chat'
```
If `DPAManagement.tsx` is built as a standalone dashboard (per Open Question 1), add `| 'dpaManagement'` immediately after `'baaManagement'` (line 14). `VendorDetailModal` does NOT need a new `AppView` entry — it is a modal rendered inline within `VendorManagement.tsx`, not a routed view.

---

## Shared Patterns

### Nav-wiring checklist (MANDATORY — see Common Pitfalls below)
**Applies to:** `DPAManagement.tsx` only (if built as a standalone dashboard; `VendorDetailModal.tsx` is a modal, not a routed view, and does NOT need nav wiring).

Three exact touch points, using the `baaManagement` precedent as the literal template:

1. **`types.ts`** line 14 area — add `| 'dpaManagement'` to the `AppView` union (see above).
2. **`components/Sidebar.tsx`** line 373 — add a sibling nav item immediately after the BAA entry:
   ```typescript
   { view: 'baaManagement', label: 'BAA Management', icon: <FileTextIcon size={20} />, permission: 'view:compliance' },
   ```
   New entry: `{ view: 'dpaManagement', label: 'DPA Management', icon: <FileTextIcon size={20} />, permission: 'view:compliance' },`
3. **`App.tsx`** line 1898 — add a sibling `case` immediately after the BAA case, wrapped in `ErrorBoundary`/`Suspense` exactly like the precedent:
   ```typescript
   case 'baaManagement': return <ErrorBoundary name="BAAManagement"><Suspense fallback={<div className="p-8 text-slate-400">Loading BAA Management...</div>}><BAAManagement /></Suspense></ErrorBoundary>;
   ```
   New: `case 'dpaManagement': return <ErrorBoundary name="DPAManagement"><Suspense fallback={<div className="p-8 text-slate-400">Loading DPA Management...</div>}><DPAManagement /></Suspense></ErrorBoundary>;`

Also check `types.ts` line 388 area — there is a permission-map entry `baaManagement: 'view:compliance',` (referenced in grep at line 388) that must get a `dpaManagement: 'view:compliance',` sibling too.

**Verification method** (per STATE.md convention used in the last two phases): after wiring, check the production build's chunk output includes the new component, not just that `tsc`/build succeeds silently.

### Tenant/role scope filter idiom
**Source:** `backend/baa_endpoints.py` lines 82-91 (`_tenant`/`_role` + inline filter), `backend/vendor_service.py` lines 38-41 (`_scope()` method), `backend/risk_service.py` lines 34-36, 58-62.
**Apply to:** Every new/extended backend route and service method in this phase (DPA routes, subprocessor routes, risk routes).
```python
filt = {"id": vendor_id, **self._scope(role, tenant_id)}   # service-layer style (vendor_service.py, risk_service.py)
# OR, inline-router style (baa_endpoints.py):
baa_filter: dict = {"id": baa_id}
if _role(current_user) not in _BAA_SUPER_ROLES:
    baa_filter["tenantId"] = tenant_id
```

### RBAC admin-role gate on mutations
**Source:** `backend/vendor_endpoints.py` line 10 (`_VENDOR_ADMIN_ROLES`), used consistently on `create_vendor`, `add_assessment`, `upload_vendor_document`, `schedule_review`, `delete_vendor` (5 call sites, all identical `if getattr(current_user, "role", "") not in _VENDOR_ADMIN_ROLES: raise HTTPException(403, ...)`).
**Apply to:** `dpa_endpoints.py`'s create/sign/terminate (this is the explicit fix for BAA's missing gate — Pitfall 2), and all 3 new subprocessor routes in `vendor_endpoints.py`.

### Additive-only field-extension convention
**Source:** This phase's own RESEARCH.md, citing STATE.md decisions `02-01` through `10-02` — never rename/remove an existing field consumed by the frontend; always add new fields alongside.
**Apply to:** `backend/risk_service.py`/`risk_endpoints.py` (residual_* fields), `types.ts`'s `Risk` interface.

## No Analog Found

None — every file in scope has a strong same-repo analog (all three requirements are explicitly framed in RESEARCH.md as pattern-extension work with no new architecture).

## Metadata

**Analog search scope:** `backend/*.py` (endpoints/services/tests), `components/*.tsx`, `types.ts`, `App.tsx`, `components/Sidebar.tsx`
**Files read in full this pass:** `backend/baa_endpoints.py`, `backend/vendor_service.py`, `backend/vendor_endpoints.py`, `backend/risk_service.py`, `backend/risk_endpoints.py`, `components/VendorManagement.tsx`, `components/RiskRegister.tsx`, `components/RiskFormModal.tsx`, `components/AgentDetailModal.tsx` (partial, lines 1-80 for modal-shell convention), `types.ts` (targeted sections), `components/Sidebar.tsx` (targeted section)
**Files referenced via RESEARCH.md only (not re-read, no new pattern signal expected):** `components/BAAManagement.tsx`, `components/VendorFormModal.tsx`, `backend/tests/test_automation_and_baa.py` (harness excerpt already fully quoted in RESEARCH.md and reproduced above)
**Pattern extraction date:** 2026-07-06
