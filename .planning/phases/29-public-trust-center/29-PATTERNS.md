# Phase 29: Public Trust Center - Pattern Map

**Mapped:** 2026-07-07
**Files analyzed:** 7 (all changed/created files from RESEARCH.md + UI-SPEC.md)
**Analogs found:** 7 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/trust_service.py` | service | CRUD | `backend/privacy_service.py` (`create_tia`/`list_tia` tenant-scoped helper shape) | role-match (flat CRUD, no versioning) |
| `backend/trust_endpoints.py` | route/controller | request-response (mixed: authenticated CRUD + public no-auth) | `backend/agent_registry_endpoints.py` (`register_agent`) for the new public pair; existing file itself for the unchanged admin routes | exact (public pattern), exact (admin pattern already in file) |
| `backend/static/trust-page.html` | static asset / view | request-response (fetch-rendered) | `backend/app.py`'s `/.well-known/security.txt` `FileResponse` route (for the serving route in `app.py`); no analog for the HTML/CSS/JS content itself (net-new, no in-codebase precedent) | role-match (serving mechanism only) |
| `backend/tests/test_trust_center.py` | test | request-response / unit | `backend/tests/test_automation_and_baa.py` (helper block: `_col`/`_db`/`_user`/`_app`) | exact |
| `components/TrustCenter.tsx` | component | CRUD (admin dashboard) | itself (incremental edit) — new sub-patterns borrowed from `tenant_endpoints.py`'s branding form (backend shape) and `utils/toast.ts`/`ToastContainer.tsx` (toast wiring) | exact (incremental) |
| `services/apiService.ts` (`updateTrustProfile`) | service (API client function) | request-response | `updateAgent`/`updateTenantVoiceBotSettings` (sibling `updateXxx` PUT/PATCH functions in same file) | exact |
| `app.py` | route/config | request-response (static file serving) | `/.well-known/security.txt` route (lines ~85-90) | exact |

## Pattern Assignments

### `backend/trust_service.py` (service, CRUD — retrofit in-memory singleton to Mongo)

**Analog:** `backend/privacy_service.py` (tenant-scoped CRUD helpers, not the versioned-document shape)

**Core CRUD pattern** (`backend/privacy_service.py` lines 291-306):
```python
def _fail_closed_tenant_id(tenant_id: Optional[str]) -> str:
    return tenant_id or "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"

async def create_tia(db, tenant_id: str, data: dict) -> dict:
    tenant_id = _fail_closed_tenant_id(tenant_id)
    doc = {"id": _gen_id("tia"), "tenantId": tenant_id, "created_at": _now_iso(), "updated_at": _now_iso(), **data}
    # ... await db._db.privacy_tia.insert_one(doc); return doc

async def list_tia(db, tenant_id: str) -> list:
    tenant_id = _fail_closed_tenant_id(tenant_id)
    return await db._db.privacy_tia.find({"tenantId": tenant_id}, {"_id": 0}).sort("created_at", -1).to_list(length=100)
```

**RESEARCH.md's own recommended replacement shape** (already the concrete target — clone directly, do not re-derive):
```python
# Source: 29-RESEARCH.md Pattern 1, adapted from backend/privacy_service.py's tenant-scoped find_one/update_one shape
async def get_profile(db, tenant_id: str) -> dict:
    profile = await db.trust_profiles.find_one({}, {"_id": 0})  # TenantIsolatedCollection injects tenantId
    return profile or _default_profile(tenant_id)

async def update_profile(db, tenant_id: str, updates: dict) -> dict:
    await db.trust_profiles.update_one({}, {"$set": {**updates, "updated_at": _now_iso()}}, upsert=True)
    return await get_profile(db, tenant_id)
```

**Existing model to preserve field-for-field** (`backend/trust_service.py` lines 6-23 — keep `TrustProfile`/`AccessRequest` Pydantic shapes, just back them with Mongo documents instead of `self.profile`/`self.requests`):
```python
class TrustProfile(BaseModel):
    company_name: str
    description: str
    contact_email: str
    logo_url: str
    compliance_frameworks: List[str]
    public_documents: List[Dict[str, str]]
    private_documents: List[Dict[str, str]]

class AccessRequest(BaseModel):
    id: str
    requester_email: str
    company: str
    reason: str
    status: str  # Pending, Approved, Denied
    requested_at: str
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
```
Add `trust_slug`/`trust_domain` fields to the tenant document (not to `TrustProfile` — those live on `db.tenants`, per Pattern 4 below), and add a `tenantId` field to both new Mongo collections implicitly via `TenantIsolatedCollection`.

---

### `backend/trust_endpoints.py` (controller, mixed request-response — add public GET/POST, keep existing admin routes unchanged)

**Analog for the new public pair:** `backend/agent_registry_endpoints.py`'s `register_agent`

**Imports pattern to add** (`backend/agent_registry_endpoints.py` lines 1-9):
```python
from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks, Request, Response
from database import get_database
from rate_limiter import limiter
```

**Public tenant-resolution + rate-limit pattern** (`backend/agent_registry_endpoints.py` lines 15-33 — the exact shape to clone):
```python
@router.post("/register")
@limiter.limit("10/minute")
async def register_agent(request: Request, response: Response, data: Dict[str, Any] = Body(...), background_tasks: BackgroundTasks = None):
    """Public endpoint, requires registrationKey."""
    db = get_database()
    registration_key = data.get("registrationKey")
    if not registration_key:
        raise HTTPException(status_code=400, detail="Registration key required")
    tenant = await db.tenants.find_one({"registrationKey": registration_key})
    if not tenant:
        raise HTTPException(status_code=404, detail="Invalid registration key")
    from tenant_context import set_tenant_id
    set_tenant_id(tenant["id"])
    # ...subsequent queries are now correctly tenant-scoped
```
**Note the `response: Response` parameter** — required by `@limiter.limit(...)` (slowapi), or the route 500s in production despite unit tests passing (Phase 25/CHK-03 regression). Both new routes (`GET /api/public/trust/{slug}` and `POST /api/public/trust/{slug}/requests`) must include it.

**Analog for public self-reported-identity capture:** `backend/cookie_consent_endpoints.py` lines 51-59:
```python
@router.post("/record")
async def record_consent(payload: ConsentRecord, request: Request):
    """Public endpoint — records visitor cookie consent. No auth required."""
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    meta = {"userId": payload.userId, "ipAddress": ip, "userAgent": ua}
    return await cookie_consent_service.record_consent(
        payload.tenantId, payload.sessionId, payload.consentedCategories, meta
    )
```

**Existing admin routes to leave structurally unchanged** (`backend/trust_endpoints.py` lines 1-48 — full current file; keep the `_TRUST_ADMIN_ROLES` gate and `Depends(get_current_user)` pattern exactly as-is, just swap the `trust_service.*` synchronous calls for `await`ed Mongo-backed equivalents):
```python
_TRUST_ADMIN_ROLES = {"Super Admin", "super_admin", "platform-admin", "admin", "Tenant Admin"}
router = APIRouter(prefix="/api/trust-center", tags=["Trust Center"])

@router.get("/profile", response_model=TrustProfile)
def get_profile(current_user: TokenData = Depends(get_current_user)):
    return trust_service.get_profile()

@router.put("/profile", response_model=TrustProfile)
def update_profile(updates: Dict[str, Any], current_user: TokenData = Depends(get_current_user)):
    if getattr(current_user, "role", "") not in _TRUST_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    return trust_service.update_profile(updates)
```

**Host-header custom-domain resolution** (RESEARCH.md Pattern 4, adapted from `backend/agent_download_endpoints.py`'s Host-header read + `tenant_endpoints.py`'s branding-update convention below):
```python
async def _resolve_tenant_from_request(db, request: Request, slug: Optional[str]) -> dict:
    host = (request.headers.get("host") or "").split(":")[0]
    tenant = await db.tenants.find_one({"trust_domain": host}, {"id": 1, "_id": 0}) if host else None
    if not tenant and slug:
        tenant = await db.tenants.find_one({"trust_slug": slug}, {"id": 1, "_id": 0})
    if not tenant:
        raise HTTPException(status_code=404, detail="Not found")
    return tenant
```

**Error handling pattern:** identical 404 message ("Not found") for both "no such tenant" and "tenant exists but has no public profile" — do not leak existence via differing error text (per Security Domain enumeration mitigation in RESEARCH.md).

**Private-document filtering (mandatory, no analog exists in-codebase — must be hand-built per Pitfall 3):**
```python
def _public_view(profile: dict) -> dict:
    return {
        **{k: v for k, v in profile.items() if k != "private_documents"},
        "private_documents": [{"name": d["name"]} for d in profile.get("private_documents", [])],
    }
```

---

### `backend/static/trust-page.html` (static asset, NEW — no in-codebase content analog)

**Analog for the serving mechanism only:** `backend/app.py`'s `/.well-known/security.txt` route (lines 85-90):
```python
@app.get("/.well-known/security.txt", include_in_schema=False)
async def security_txt():
    """Serve RFC 9116 security disclosure policy."""
    from fastapi.responses import FileResponse
    _path = os.path.join(os.path.dirname(__file__), "static", ".well-known", "security.txt")
    return FileResponse(_path, media_type="text/plain")
```
Clone this shape for the new route in `app.py`:
```python
@app.get("/trust/{slug}", include_in_schema=False)
async def public_trust_page(slug: str):
    from fastapi.responses import FileResponse
    _path = os.path.join(os.path.dirname(__file__), "static", "trust-page.html")
    return FileResponse(_path, media_type="text/html")
```
(`slug` is unused server-side in this route — it's consumed client-side by the page's own `fetch()` call against `/api/public/trust/{slug}`; keep it in the path only so the URL the admin copies matches what the visitor sees.)

**No content analog exists** — per UI-SPEC.md, this is a standalone HTML+CSS+vanilla-JS file (no React, no Tailwind, no npm dependency). Build from UI-SPEC.md's Typography/Color/Copywriting Contract (Surface A) directly; there is nothing elsewhere in this codebase to clone for the markup/JS itself.

---

### `backend/tests/test_trust_center.py` (test, NEW)

**Analog:** `backend/tests/test_automation_and_baa.py` — clone the helper block verbatim (lines 1-50+):
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
    # ... app.dependency_overrides[get_current_user] = lambda: user; return TestClient(app)
```
Per RESEARCH.md's Pitfall 2 warning, at least one test in this file MUST make a real `TestClient(app).get(...)`/`.post(...)` call through the full route (not a direct function call) to catch the `response: Response`-missing slowapi bug — mocked-function-only tests will not catch it.

---

### `components/TrustCenter.tsx` (component, CRUD — incremental additions only)

**Analog:** itself (existing file) + `utils/toast.ts`/`ToastContainer.tsx` for the new toast wiring + `backend/tenant_endpoints.py`'s branding form shape for the new domain/link settings field's backend-side pattern.

**Existing imports/state to extend, not replace** (`components/TrustCenter.tsx` lines 1, 4, 28-31):
```tsx
import React, { useState, useEffect } from 'react';
// ...
import { ..., ExternalLink, Eye, Download, UserCheck, Clock, XCircle } from 'lucide-react';
const [activeTab, setActiveTab] = useState<'profile' | 'requests'>('profile');
const [profile, setProfile] = useState<TrustProfile | null>(null);
const [requests, setRequests] = useState<AccessRequest[]>([]);
const [loading, setLoading] = useState(true);
```

**Toast wiring to add on approve/deny (missing today — no toast call exists on the current approve/deny handlers):**
```tsx
import { showToast } from '../utils/toast';
// on success: showToast('Request approved.', 'success'); / showToast('Request denied.', 'success');
// on failure: showToast('Could not update request status. Please try again.', 'error');
```
Add `aria-label="Approve request"` / `aria-label="Deny request"` to the existing icon-only `UserCheck`/`XCircle` buttons (lines ~227, 234) per UI-SPEC.md's checker-flagged accessibility requirement — do not add a confirmation modal.

**New "Edit Profile" form and "Trust domain + public link" field:** no existing form-edit UI exists in this file to clone (current `profile` render is read-only, lines ~105-155). Clone the **backend** branding-update field pattern's label/input conceptual shape (`backend/tenant_endpoints.py` lines 221-224 `BrandingConfig` model — mirrors the shape of settable simple string fields) for the new profile-edit form's field set (`company_name`, `description`, `contact_email`, `logo_url`, `compliance_frameworks[]`, `public_documents[]`, `private_documents[]`, plus the new `trust_domain` field). On the frontend, reuse existing Tailwind label/input conventions already in the file (`text-sm font-medium text-gray-900 dark:text-white mb-1` for labels, per UI-SPEC.md's explicit instruction) — no separate frontend analog component exists to clone verbatim; UI-SPEC.md's Component Inventory table is authoritative here.

**Save/error toast pattern to reuse for the new profile-save action:**
```tsx
// success: showToast('Trust profile saved.', 'success')  (or equivalent per Copywriting Contract)
// error:   showToast('Could not save trust profile. Please try again.', 'error')
```

---

### `services/apiService.ts` — new `updateTrustProfile()` function (service, request-response)

**Analog (sibling `updateXxx` PUT function, exact structural match):** `updateAgent` (lines 2122-2135):
```typescript
export const updateAgent = async (agent: Agent) => {
    try {
        const res = await authFetch(`${API_BASE}/agents/${agent.id}`, {
            method: 'PUT',
            body: JSON.stringify(agent)
        });
        if (!res.ok) throw new Error("Failed to update agent");
        const updated = await res.json();
        // Update local cache
        const index = AGENTS.findIndex(a => a.id === agent.id);
        if (index > -1) { AGENTS[index] = updated; }
        return updated;
    } catch (e) { ... }
};
```

**Closer no-local-cache analog (simpler — no in-memory array to sync), same file, adjacent to where `updateTrustProfile` should be added (near `updateTrustRequest`, lines 1421-1441):**
```typescript
export const fetchTrustRequests = async (): Promise<AccessRequest[]> => {
    try {
        const res = await authFetch(`${API_BASE}/trust-center/requests`);
        if (!res.ok) throw new Error("Failed to fetch trust requests");
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.error("Error fetching trust requests:", e);
        return [];
    }
};

export const updateTrustRequest = async (id: string, status: string, approvedBy: string): Promise<AccessRequest> => {
    const res = await authFetch(`${API_BASE}/trust-center/requests/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ status, approved_by: approvedBy })
    });
    if (!res.ok) throw new Error("Failed to update trust request");
    return await res.json();
};
```

**Recommended new function (matches `updateTrustRequest`'s existing sibling shape exactly, add directly below it):**
```typescript
export const updateTrustProfile = async (updates: Partial<TrustProfile>): Promise<TrustProfile> => {
    const res = await authFetch(`${API_BASE}/trust-center/profile`, {
        method: 'PUT',
        body: JSON.stringify(updates)
    });
    if (!res.ok) throw new Error("Failed to update trust profile");
    return await res.json();
};
```
`TrustProfile` is already imported/exported at the top of `services/apiService.ts` (line 10/22) — no new import needed. `authFetch` and `API_BASE` (`'/api'`, line ~29-30) are both already defined in this file; no header/base-URL boilerplate to invent.

---

### `app.py` — new `GET /trust/{slug}` route (route/config, request-response)

**Analog:** `/.well-known/security.txt` (lines 85-90, shown in full above under `trust-page.html`'s section). Clone directly, changing only the path parameter and file target, as already shown above.

## Shared Patterns

### Public-route tenant resolution (mandatory for both new public routes)
**Source:** `backend/agent_registry_endpoints.py` lines 15-33 (`register_agent`)
**Apply to:** `GET /api/public/trust/{slug}` and `POST /api/public/trust/{slug}/requests` in `trust_endpoints.py`
```python
tenant = await db.tenants.find_one({"trust_slug": slug}, {"id": 1, "_id": 0})
if not tenant:
    raise HTTPException(status_code=404, detail="Not found")
from tenant_context import set_tenant_id
set_tenant_id(tenant["id"])  # MUST run before any further tenant-scoped query
```
Do NOT add `trust_profiles`/`trust_access_requests` to `database.py`'s global-exemption allowlist to "fix" a silently-empty public route — that turns a correctness bug into a real cross-tenant leak (RESEARCH.md Pitfall 1).

### `@limiter.limit(...)` + `response: Response` (mandatory for both new public routes)
**Source:** `backend/agent_registry_endpoints.py` line 16-17; `backend/rate_limiter.py`'s shared `limiter`
**Apply to:** both new public routes in `trust_endpoints.py`
```python
from rate_limiter import limiter
@router.get("/public/trust/{slug}")
@limiter.limit("30/minute")
async def get_public_trust_profile(request: Request, response: Response, slug: str): ...

@router.post("/public/trust/{slug}/requests")
@limiter.limit("5/minute")
async def create_public_access_request(request: Request, response: Response, slug: str, payload: ...): ...
```
Verify with an actual `TestClient` HTTP call in `test_trust_center.py`, not just an import/unit check — this exact bug class was previously invisible to unit tests (Phase 25/CHK-03).

### Toast success/error feedback
**Source:** `utils/toast.ts` / `components/ToastContainer.tsx` (already wired app-wide)
**Apply to:** `components/TrustCenter.tsx`'s profile-save and approve/deny handlers
```tsx
showToast('Request approved.', 'success');
showToast('Could not update request status. Please try again.', 'error');
```

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `backend/static/trust-page.html` (content/markup itself, not the serving route) | static asset | request-response | This is the first standalone, non-React, non-bundled HTML page ever served by this backend outside `/.well-known/*` plain-text files — no HTML+CSS+vanilla-JS UI precedent exists anywhere in the codebase. Build directly from UI-SPEC.md's Surface A contract (typography, color, copy) rather than from a codebase analog. |

## Metadata

**Analog search scope:** `backend/*.py` (endpoints/service pairs), `backend/tests/*.py`, `components/*.tsx`, `services/apiService.ts`, `app.py`
**Files scanned:** `agent_registry_endpoints.py`, `cookie_consent_endpoints.py`, `privacy_service.py`, `tenant_endpoints.py`, `trust_service.py`, `trust_endpoints.py`, `test_automation_and_baa.py`, `apiService.ts`, `TrustCenter.tsx`, `app.py` (all read in full or targeted-section this session)
**Pattern extraction date:** 2026-07-07
