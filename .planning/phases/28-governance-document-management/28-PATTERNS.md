# Phase 28: Governance Document Management - Pattern Map

**Mapped:** 2026-07-07
**Files analyzed:** 8 (new/modified)
**Analogs found:** 8 / 8

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/governance_document_service.py` | service | CRUD + event-driven (state machine) | `backend/privacy_service.py` (`create_notice`/`get_notice_versions`) + `backend/approval_service.py` (delegation) | role-match (composed from two exact analogs) |
| `backend/governance_document_endpoints.py` | route/controller | request-response | `backend/baa_endpoints.py` + `backend/cookie_consent_endpoints.py` + `backend/approval_endpoints.py` | role-match (composed) |
| `backend/tests/test_governance_documents.py` | test | request-response | `backend/tests/test_automation_and_baa.py` | exact (helper block to clone) |
| `backend/router_registry.py` (modified) | config | — | existing `_load(app, "baa_endpoints", "router")` line (line 219) | exact |
| Signed-PDF export function (in `governance_document_service.py` or sibling module) | utility/transform | file-I/O | `backend/compliance_reporting_pdf.py` | exact |
| `components/GovernanceDocumentsDashboard.tsx` | component | request-response | `components/PrivacyLegalDashboard.tsx` (tab-list) + `components/BAAManagement.tsx` (fetch/sign pattern) | role-match (composed) |
| `App.tsx` (modified) | route registration | — | `baaManagement`/`privacyLegal` lazy-import + switch-case entries | exact |
| `components/Sidebar.tsx` (modified) | config/nav | — | "Governance & Compliance" section, lines 346-375 | exact |
| `types.ts` (modified) | config | — | `AppView` union + permission map | exact |

## Pattern Assignments

### `backend/governance_document_service.py` (service, CRUD + state machine)

**Analog 1 — versioning:** `backend/privacy_service.py` lines 328-341 (`create_notice`)

```python
# Source: backend/privacy_service.py lines 328-341
async def create_notice(db, tenant_id: str, data: dict) -> dict:
    tenant_id = _fail_closed_tenant_id(tenant_id)
    notice_id = _gen_id("notice")
    version = data.get("version", 1)
    doc = {
        "id": notice_id, "tenantId": tenant_id, "title": data.get("title", ""),
        "effective_date": data.get("effective_date"), "applies_to": data.get("applies_to", ""),
        "current_version": version,
        "versions": [{"version": version, "content_html": data.get("content_html", ""), "published_at": _now_iso()}],
        "created_at": _now_iso(), "updated_at": _now_iso(),
    }
    await db._db.privacy_notices.insert_one(doc)
    doc.pop("_id", None)
    return doc
```
```python
# Source: backend/privacy_service.py lines 349-352 (retrieving version history)
async def get_notice_versions(db, notice_id: str, tenant_id: str) -> list:
    tenant_id = _fail_closed_tenant_id(tenant_id)
    notice = await db._db.privacy_notices.find_one({"id": notice_id, "tenantId": tenant_id}, {"_id": 0})
    return sorted(notice.get("versions", []), key=lambda v: v.get("version", 0), reverse=True) if notice else []
```
Adapt for governance documents: add top-level `status` field (`draft` → `pending_approval` → `approved` → `published`), `approval_request_id` (nullable), and `signatures: []` (empty at creation, per Pattern 3 below). Each `versions[]` entry gets `{version, content, status, author, created_at}` instead of privacy's `{version, content_html, published_at}`.

**Analog 2 — approval delegation (do not reimplement):** `backend/approval_service.py` lines 13-61 (`create_approval_request`, full signature) and lines 83-181 (`submit_decision` — read-only reference, never modify this shared file)

```python
# Source: backend/approval_service.py lines 13-61
async def create_approval_request(
    self, tenant_id: str, requester: str, action_type: str, description: str,
    details: Dict[str, Any], workflow_steps: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """workflow_steps: [{"role": "SecurityAdmin", "approvers": ["user@example.com"]}]"""
    request_id = f"req-{uuid.uuid4().hex[:8]}"
    steps = []
    for i, step in enumerate(workflow_steps):
        steps.append({
            "step_number": i + 1, "role": step.get("role"),
            "approvers": step.get("approvers", []),
            "status": "pending" if i == 0 else "waiting",
            "decided_by": None, "decided_at": None, "decision": None, "comments": None
        })
    request = {
        "id": request_id, "tenantId": tenant_id, "requester": requester,
        "actionType": action_type, "description": description, "details": details,
        "status": "pending", "createdAt": ..., "updatedAt": ..., "currentStep": 1, "steps": steps
    }
    await self.db.approval_requests.insert_one(request)
    await self._notify_approvers(request, steps[0])
    return request
```

Governance document call shape (from RESEARCH.md Pattern 1, already-verified against this exact file):
```python
from approval_service import get_approval_service

async def submit_document_for_approval(db, tenant_id, doc_id, requester, approvers):
    service = get_approval_service(db)
    request = await service.create_approval_request(
        tenant_id=tenant_id, requester=requester,
        action_type="governance_document_approval",
        description=f"Approve governance document {doc_id}",
        details={"document_id": doc_id},
        workflow_steps=[{"role": "ComplianceOfficer", "approvers": approvers}],
    )
    await db.governance_documents.update_one(
        {"id": doc_id, "tenantId": tenant_id},
        {"$set": {"status": "pending_approval", "approval_request_id": request["id"]}},
    )
    return request
```
**Approval-resolution re-check (Pitfall 2, mandatory):** the "sign" and "publish" service functions must re-read the linked `db.approval_requests` doc (via `service.get_request(approval_request_id, tenant_id)`, lines 63-67 of `approval_service.py`) and verify `status == "approved"` before proceeding — never trust the document's locally cached `status` field alone.

### `backend/governance_document_endpoints.py` (route, request-response)

**Analog 1 — imports + tenant/role helpers + normalize pattern:** `backend/baa_endpoints.py` lines 1-43

```python
# Source: backend/baa_endpoints.py lines 1-29
from __future__ import annotations
import time
from fastapi import APIRouter, HTTPException, Depends
from auth_utils import get_current_user

router = APIRouter(prefix="/api/baa", tags=["BAA Management"])

async def _db():
    from database import get_database
    return get_database()

def _tenant(user) -> str | None:
    return getattr(user, "tenant_id", None) or (user.get("tenant_id") if isinstance(user, dict) else None)

def _sub(user) -> str | None:
    """Return user identifier — works for both TokenData (username) and dict (sub/email)."""
    if isinstance(user, dict):
        return user.get("sub") or user.get("email") or user.get("username")
    return getattr(user, "username", None) or getattr(user, "email", None)
```
Use `_tenant`/`_sub` verbatim-adapted; every read/write must filter `{"id": doc_id, "tenantId": tenant_id}` (see `baa_endpoints.py` lines 82-91, `get_baa`).

**Analog 2 — server-derived signature capture (Pitfall 3, mandatory):** `backend/cookie_consent_endpoints.py` lines 51-59 combined with the sign-endpoint shape from RESEARCH.md Pattern 3 (already codebase-verified against `baa_endpoints.py` lines 137-154 `sign_baa`):

```python
# Source: backend/cookie_consent_endpoints.py lines 51-59 (IP/UA capture)
@router.post("/record")
async def record_consent(payload: ConsentRecord, request: Request):
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    meta = {"userId": payload.userId, "ipAddress": ip, "userAgent": ua}
```
```python
# Composed sign endpoint (adapt from baa_endpoints.py sign_baa lines 137-154 + cookie_consent capture above)
@router.post("/documents/{doc_id}/sign")
async def sign_document(doc_id: str, payload: dict, request: Request,
                         current_user: TokenData = Depends(get_current_user)):
    if not payload.get("consent"):
        raise HTTPException(400, "Explicit consent checkbox is required to sign")
    typed_name = (payload.get("typed_name") or "").strip()
    if not typed_name:
        raise HTTPException(400, "Typed full name is required")
    signature = {
        "signer_email": getattr(current_user, "username", None),
        "typed_name": typed_name,
        "consented": True,
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "")[:512],
        "signed_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.governance_documents.update_one(
        {"id": doc_id, "tenantId": tenant_id},
        {"$push": {"signatures": signature}},
    )
    return {"success": True, "signature": signature}
```
**Never accept** `payload.get("ip_address")`, `payload.get("signed_at")`, or `payload.get("signer_email")` — derive all three server-side (per `approval_endpoints.py` line 65 comment: "Always derive email from the verified JWT — never accept it from the request body").

**Analog 3 — decision/error-handling shape:** `backend/approval_endpoints.py` lines 51-86 (`submit_approval_decision`) — shows the `try/except ValueError → 400 / except Exception → 500` convention and the explicit JWT-derived-identity comment to replicate verbatim in the sign endpoint's docstring/comment.

**Auth pattern (shared, all routes):** every route depends on `Depends(get_current_user)` (BAA/cookie-consent style, no route-level `require_permission` used in those two sibling files) OR `Depends(require_permission("view:approvals"))`/`Depends(require_permission("manage:approvals"))` (approval_endpoints.py lines 19-23, 51-56) if the phase decides to gate governance-document routes behind `manage:compliance` explicitly at the route-decorator level rather than only checking role membership in a helper — RESEARCH.md's RBAC note (Assumption A3, resolved) says reuse `manage:compliance`, so prefer the `require_permission("manage:compliance")` / `require_permission("view:compliance")` decorator style from `approval_endpoints.py` over BAA's looser `_role(current_user) in _BAA_SUPER_ROLES` set-check.

### Signed-PDF export (new function, file-I/O)

**Analog:** `backend/compliance_reporting_pdf.py` (full file, 152 lines)

```python
# Source: backend/compliance_reporting_pdf.py lines 1-16 (imports)
import html
import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table as PDFTable, TableStyle,
    Paragraph, Spacer, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
```
```python
# Source: backend/compliance_reporting_pdf.py lines 82-86 — the CR-01 escaping fix, MANDATORY to replicate
hdr_row = [Paragraph(html.escape(str(h), quote=False), hdr_style) for h in headers]
table_data = [hdr_row] + [
    [Paragraph(html.escape(str(v), quote=False), cell_style) for v in row]
    for row in rows_plain
]
```
```python
# Source: backend/compliance_reporting_pdf.py lines 148-152 — output/return shape
doc.build(elements)
return {
    "filename": filename, "url": f"/static/reports/{filename}",
    "generatedAt": datetime.now().isoformat(), "rowCount": len(control_rows),
}
```
Adapted function per RESEARCH.md Pattern 4 (already codebase-verified):
```python
def export_signed_pdf(doc: dict, filepath: str) -> None:
    styles = getSampleStyleSheet()
    elements = [
        Paragraph(html.escape(doc["title"], quote=False), styles["Title"]),
        Paragraph(f"Version {doc['current_version']} — Status: {doc['status']}", styles["Normal"]),
        Spacer(1, 12),
    ]
    for sig in doc.get("signatures", []):
        elements.append(Paragraph(
            html.escape(
                f"Signed by: {sig['typed_name']} ({sig['signer_email']}) "
                f"at {sig['signed_at']} from {sig['ip_address']}",
                quote=False,
            ),
            styles["Normal"],
        ))
    SimpleDocTemplate(filepath).build(elements)
```
**Every** `Paragraph(...)` call on user-controlled content (title, typed_name, signer_email, content) MUST be wrapped in `html.escape(str(v), quote=False)` — no exceptions (Pitfall 4).

### `backend/router_registry.py` (modified, config)

**Analog:** existing sibling registrations

```python
# Source: backend/router_registry.py line 153
_load(app, "cookie_consent_endpoints",  "router")
# Source: backend/router_registry.py line 219
_load(app, "baa_endpoints",                    "router")
```
Add one line: `_load(app, "governance_document_endpoints", "router")` in the same optional-router section as `baa_endpoints`/`cookie_consent_endpoints` (not in `_REQUIRED_ROUTERS`, lines 19-38 — this is not a startup-critical router).

### `backend/tests/test_governance_documents.py` (test)

**Analog:** `backend/tests/test_automation_and_baa.py` lines 1-52 — clone the entire helper block verbatim

```python
# Source: backend/tests/test_automation_and_baa.py lines 21-52
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
Add a `governance_documents` collection fixture and a matched `approval_requests` collection fixture (mock `db.approval_requests.find_one` to return `{"status": "approved", ...}` for the "sign gated behind approval" tests, per Pitfall 2's test coverage requirement).

### `components/GovernanceDocumentsDashboard.tsx` (component, request-response)

**Analog 1 — tab-list-modal shape:** `components/PrivacyLegalDashboard.tsx` lines 1-65 (state + fetch pattern) and lines 61-74 (tab bar JSX)

```typescript
// Source: components/PrivacyLegalDashboard.tsx lines 1-13
import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

type Tab = 'tia' | 'lia' | 'notices' | 'contracts';
// ... adapt to: type Tab = 'documents' | 'pending_approval' | 'signed';

export const PrivacyLegalDashboard: React.FC = () => {
  const [tab, setTab] = useState<Tab>('tia');
  const [loading, setLoading] = useState(false);
```
```typescript
// Source: components/PrivacyLegalDashboard.tsx lines 40-54 (fetch-by-tab pattern)
const fetchData = useCallback(async () => {
  setLoading(true);
  try {
    if (tab === 'tia') { const r = await fetchJson('/api/privacy/tia'); setTiaItems(r.items || []); }
    // ...
  } catch { showToast('Failed to load data', 'error'); }
  finally { setLoading(false); }
}, [tab]);
useEffect(() => { fetchData(); }, [fetchData]);
```
```typescript
// Source: components/PrivacyLegalDashboard.tsx lines 61-74 (tab bar)
const TABS: { key: Tab; label: string }[] = [
  { key: 'tia', label: 'TIA' }, { key: 'lia', label: 'LIA' },
];
// ... {TABS.map(t => <button ... className={tab===t.key ? 'active' : ''}>{t.label}</button>)}
```

**Analog 2 — fetch/toast + sign-action pattern:** `components/BAAManagement.tsx` lines 56-81 (fetch-all with `Promise.all` + fallback) — use for the initial document-list + stats load, and for the "sign" button's POST call (`authFetch('/api/governance/documents/{id}/sign', { method: 'POST', body: JSON.stringify({ typed_name, consent }) })`) matching the same `authFetch` + JSON error-toast convention shown across both analogs.

```typescript
// Source: components/BAAManagement.tsx lines 56-81
const fetchAll = useCallback(async () => {
  setLoading(true);
  const [b, s] = await Promise.all([
    authFetch('/api/baa').then(r => r.ok ? r.json() : []),
    authFetch('/api/baa/stats').then(r => r.ok ? r.json() : null),
  ]).catch(() => [[], null]);
  setBaas(Array.isArray(b) ? b : []);
  setStats(s);
  setLoading(false);
}, []);
```

## Shared Patterns

### Approval delegation (never reimplement)
**Source:** `backend/approval_service.py` (full file) via `get_approval_service(db)` factory (line 213-214)
**Apply to:** `governance_document_service.py`'s submit-for-approval function and endpoint. Do not create a `governance_document_approvals` collection.

### Tenant-scoped query filter
**Source:** `backend/baa_endpoints.py` lines 82-91 (`{"id": baa_id, "tenantId": tenant_id}` filter, 404 on miss)
**Apply to:** every governance-document read/write route — return identical 404 for wrong-tenant vs. nonexistent, per RESEARCH.md's security-domain note.

### Server-derived identity/IP/timestamp (never client-supplied)
**Source:** `backend/approval_endpoints.py` line 65 comment + `backend/cookie_consent_endpoints.py` lines 54-56
**Apply to:** the `/sign` endpoint exclusively — reject any `payload` field named `ip_address`, `signed_at`, or `signer_email`.

### html.escape before every reportlab Paragraph
**Source:** `backend/compliance_reporting_pdf.py` lines 82-86 (CR-01 fix)
**Apply to:** the new signed-PDF export function — no `Paragraph(...)` call on user content without `html.escape(str(v), quote=False)` first.

### Nav wiring (mandatory, 6-instance documented history of omission)
**Source:** `App.tsx` lines 41, 197 (lazy imports), 388/404 (permission map), 1869/1898 (switch-case render); `components/Sidebar.tsx` lines 346-375 (nav section); `types.ts` lines 140-146, 184 (AppView union)
**Apply to:** `GovernanceDocumentsDashboard.tsx` — three files must all be touched in the same task/commit, not deferred.

**Exact insertion points:**
- `App.tsx`: add a lazy import near line 197 (`const GovernanceDocumentsDashboard = React.lazy(() => import('./components/GovernanceDocumentsDashboard').then(m => ({ default: m.GovernanceDocumentsDashboard })));`), add `governanceDocuments: 'view:compliance'` to the permission map near line 388, add a `case 'governanceDocuments': return <ErrorBoundary name="GovernanceDocumentsDashboard"><Suspense fallback={<div className="p-8 text-slate-400">Loading Governance Documents...</div>}><GovernanceDocumentsDashboard /></Suspense></ErrorBoundary>;` near line 1898 (sibling to `baaManagement` case).
- `components/Sidebar.tsx`: add `{ view: 'governanceDocuments', label: 'Governance Documents', icon: <FileTextIcon size={20} />, permission: 'view:compliance' },` as a new item inside the existing `"Governance & Compliance"` section's `items` array (lines 348-374), immediately after the `baaManagement` entry at line 373 — do NOT create a new top-level nav section.
- `types.ts`: add `| 'governanceDocuments'` to the `AppView` union, adjacent to `| 'baaManagement'` at line 144.

## No Analog Found

None — every file in scope has at least one direct or composed analog in the existing codebase.

## Metadata

**Analog search scope:** `backend/` (service/endpoints/tests), `components/`, `App.tsx`, `Sidebar.tsx`, `types.ts`, `router_registry.py`
**Files scanned:** `approval_service.py`, `approval_endpoints.py`, `privacy_service.py`, `baa_endpoints.py`, `cookie_consent_endpoints.py`, `compliance_reporting_pdf.py`, `router_registry.py`, `test_automation_and_baa.py`, `PrivacyLegalDashboard.tsx`, `BAAManagement.tsx`, `Sidebar.tsx`, `App.tsx`, `types.ts`
**Pattern extraction date:** 2026-07-07
