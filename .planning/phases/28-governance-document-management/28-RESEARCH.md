# Phase 28: Governance Document Management - Research

**Researched:** 2026-07-07
**Domain:** Versioned document management + generic approval-workflow reuse + electronic signature capture + signed-PDF export (Python/FastAPI/Motor backend, React/TypeScript frontend)
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DOC-01 | Versioned policy/procedure documents with an approval workflow, reusing the existing generic `approval_service.py` engine | See Architecture Patterns → Pattern 1 (reuse `ApprovalService`) and Pattern 2 (embedded `versions[]` array cloned from `privacy_service.create_notice`); confirmed `policy_endpoints.py` is unrelated (Pitfall 5) so a new file is required |
| DOC-02 | Electronic signature capture on approved documents, with a signed-PDF export proving who signed and when | See Architecture Patterns → Pattern 3 (typed-name + consent + server-derived IP/UA/timestamp capture, cloned from `cookie_consent_endpoints.py` + `baa_endpoints.py`) and Pattern 4 (reportlab signed-PDF export, cloned from `compliance_reporting_pdf.py` with the CR-01 `html.escape` fix preserved) |
</phase_requirements>

## Summary

This phase adds a genuinely new backend surface — versioned governance documents (policies/procedures) with an approval workflow and e-signature capture — to a codebase that already has every building block it needs, just scattered across five existing files. `backend/approval_service.py` provides a generic, already-proven multi-step approval-request engine (`create_approval_request` / `submit_decision` / `get_pending_for_user`) that must be reused verbatim, not reimplemented — its only current caller is `approval_endpoints.py`, so there is no other integration pattern to reconcile with. `backend/policy_endpoints.py` is confirmed to be unrelated automation-rule CRUD (`automation_policies` collection: conditions/actions/priority) — it has zero conceptual overlap with governance documents and must not be extended; a new file is correct. The closest existing "versioned document" shape in the codebase is `privacy_service.py`'s `create_notice`/`get_notice_versions` (an embedded `versions: []` array with a `current_version` pointer) — this is the pattern to clone, not evidence-file storage. The closest existing "signature capture" shape is `baa_endpoints.py`'s boolean-flag-plus-timestamp-plus-actor pattern (`signed_by_us`/`signed_by_vendor` + `_at` + `_by`), combined with `cookie_consent_endpoints.py`'s IP+user-agent capture pattern (`request.client.host`, `request.headers.get("user-agent")`) — together these satisfy the ESIGN Act/UETA baseline (intent to sign, consent, association of signature with signer+record, retention) without building cryptographic PKI signing, which would be over-engineering for this scope. Signed-PDF export reuses `compliance_reporting_pdf.py`'s reportlab pattern verbatim, including the `html.escape(..., quote=False)` injection-safety fix already learned in this codebase (the "CR-01" fix noted in STATE.md).

No new pip packages are required. No coupling was found with Phases 25/26/27 — Phase 28 needs two entirely new files (`backend/governance_document_service.py` + `backend/governance_document_endpoints.py`) plus one new frontend dashboard, none of which are touched by any Phase 25/26/27 plan.

**Primary recommendation:** Build `governance_document_service.py` (data model: embedded `versions[]` array cloned from `privacy_service.create_notice`, `status` state machine `draft → pending_approval → approved → published`) + `governance_document_endpoints.py` (FastAPI router calling into the existing `get_approval_service(db)` for the approval step, never a new approval mechanism) + a signed-PDF export function added to (or alongside) `compliance_reporting_pdf.py`'s reportlab pattern + a new `GovernanceDocumentsDashboard.tsx` following `PrivacyLegalDashboard.tsx`'s tab-list-modal shape, wired into `App.tsx`/`Sidebar.tsx`/`types.ts` under the existing "Governance & Compliance" nav section.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Versioned document storage + state machine | API / Backend | Database / Storage | Documents (metadata + version history) live in a MongoDB collection, mutated only through backend endpoints — matches every existing GRC module in this codebase (privacy notices, BAAs, DPAs) |
| Approval workflow orchestration | API / Backend | — | Must delegate entirely to the existing `ApprovalService` (`approval_service.py`) — this phase adds a caller, not a new engine |
| E-signature capture (typed name, consent checkbox, IP, user-agent, timestamp) | API / Backend | — | Signature metadata must be captured server-side from the authenticated request (`request.client.host`, JWT-derived identity) — never trusted from client-supplied body fields, matching `approval_endpoints.py`'s "always derive email from the verified JWT" pattern |
| Signed-PDF generation | API / Backend | — | Reuses `compliance_reporting_pdf.py`'s reportlab `SimpleDocTemplate` pattern; PDF is generated server-side and served via the existing `/static/reports/` static mount |
| Document list / approval / signature UI | Browser / Client | — | New `GovernanceDocumentsDashboard.tsx`, client-rendered React component fetching via `authFetch`, matching `BAAManagement.tsx`/`PrivacyLegalDashboard.tsx` |
| Nav registration | Frontend Server (SSR: N/A — SPA) | Browser / Client | `App.tsx` (lazy import + route case) + `Sidebar.tsx` (nav entry) + `types.ts` (View union) — this project has 5 documented instances (STATE.md) of shipping a dashboard component with zero nav wiring; must not repeat |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| reportlab | 5.0.0 (installed; `requirements.txt` pins `>=4.0.0`) [VERIFIED: `pip show reportlab` in this environment] | Signed-PDF generation | Already the platform's only PDF library (`compliance_reporting_pdf.py`, `compliance_reporting_excel.py`'s sibling); reusing avoids adding a second PDF dependency and inherits the `html.escape(..., quote=False)` XSS/injection-safety fix already applied here (STATE.md "CR-01") |
| FastAPI + Motor (async pymongo) | already in `requirements.txt`, unpinned in this research (project-standard, not re-verified) [ASSUMED — version unchanged from prior phases, no phase-specific upgrade needed] | Async REST endpoints + MongoDB access | Matches every sibling endpoints/service file pair in this codebase |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `uuid` (stdlib) | n/a | Document ID + version ID generation | Matches `f"{prefix}-{uuid.uuid4().hex[:N]}"` convention used in `policy_endpoints.py`, `approval_service.py` |
| `datetime` (stdlib) | n/a | Timestamps | Matches `datetime.now(timezone.utc).isoformat()` convention used everywhere in this codebase (never `time.time()` in the newer files, though `baa_endpoints.py`/`privacy_endpoints.py` use epoch floats — either is acceptable, prefer ISO strings for new code per the majority convention) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Boolean-flag + IP/UA e-signature capture (recommended) | A dedicated e-signature SDK/service (e.g. DocuSign API, HelloSign API) | Massive over-engineering for an internal governance-document approval flow; adds an external paid dependency and OAuth integration for a capability the existing BAA/cookie-consent patterns already satisfy at the ESIGN Act/UETA baseline level |
| Boolean-flag + IP/UA e-signature capture (recommended) | Cryptographic PKI-based digital signatures (X.509 cert signing, detached signature blocks embedded in the PDF) | Out of scope per phase goal ("electronic signature capture," not "digital signature"); no existing pattern in this codebase does this; would require key management infrastructure that doesn't exist |
| Embedded `versions[]` array (recommended, cloned from `privacy_service.create_notice`) | A separate `governance_document_versions` collection with `document_id` foreign key | Only worth it if version count per document is expected to be large (hundreds); privacy notices and this phase's expected document counts are small — embedded array matches the one existing precedent in this codebase and keeps reads to a single query |

**Installation:**
```bash
# No new packages required — reportlab, FastAPI, Motor, uuid, datetime are all already installed and in use.
```

**Version verification:** `pip show reportlab` in this environment confirmed version 5.0.0 installed, satisfying `requirements.txt`'s `reportlab>=4.0.0` pin [VERIFIED: pip show reportlab, this session].

## Package Legitimacy Audit

No external packages are being introduced by this phase — every capability (approval workflow, versioned storage, e-signature metadata capture, PDF generation) reuses existing in-tree dependencies (`reportlab`, `fastapi`, `motor`, stdlib `uuid`/`datetime`). **No Package Legitimacy Gate run was needed; no packages to check.**

**Packages removed due to [SLOP] verdict:** none (no packages evaluated — none proposed)
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────┐
│  GovernanceDocumentsDashboard│  (new, React/TS)
│  .tsx  — list / create /     │
│  approve / sign / export     │
└──────────────┬───────────────┘
               │ authFetch (JWT bearer)
               ▼
┌──────────────────────────────────────────────────────────┐
│ governance_document_endpoints.py  (new, FastAPI router)   │
│                                                            │
│  POST /api/governance/documents            (create draft) │
│  GET  /api/governance/documents            (list)         │
│  GET  /api/governance/documents/{id}       (detail+vers.) │
│  POST /api/governance/documents/{id}/submit-for-approval  │
│         └─► delegates to ApprovalService.create_approval_ │
│             request()  (approval_service.py — REUSED)     │
│  POST /api/governance/documents/{id}/new-version          │
│  POST /api/governance/documents/{id}/sign                 │
│         └─► captures request.client.host + user-agent +   │
│             JWT-derived identity (cookie_consent pattern)  │
│  GET  /api/governance/documents/{id}/export-signed-pdf     │
│         └─► reportlab SimpleDocTemplate (compliance_       │
│             reporting_pdf.py pattern) → /static/reports/   │
└───────────────┬───────────────────────┬────────────────────┘
                │                       │
                ▼                       ▼
┌────────────────────────────┐  ┌──────────────────────────┐
│ db.governance_documents     │  │ db.approval_requests      │
│  { id, tenantId, title,     │  │  (EXISTING collection,    │
│    status, current_version, │  │   owned by approval_      │
│    versions:[{version,      │  │   service.py — not        │
│    content, author, ts}],   │  │   duplicated)             │
│    signatures:[{signer,     │  └──────────────────────────┘
│    typed_name, ip, ua, ts}] }│
└──────────────┬───────────────┘
               │
               ▼
     /static/reports/{doc_id}_{version}_signed.pdf
     (served by existing StaticFiles mount in app.py)
```

### Recommended Project Structure
```
backend/
├── governance_document_service.py     # NEW — data model, versioning, signature capture, PDF export
├── governance_document_endpoints.py   # NEW — FastAPI router, delegates approval step to approval_service
├── tests/
│   └── test_governance_documents.py   # NEW — TestClient + AsyncMock db pattern (test_automation_and_baa.py clone)
└── router_registry.py                 # MODIFIED — add one _load() line (optional-router section)

components/
└── GovernanceDocumentsDashboard.tsx    # NEW — tab-list-modal pattern (PrivacyLegalDashboard.tsx clone)

App.tsx        # MODIFIED — lazy import + route case + permission map entry
Sidebar.tsx    # MODIFIED — one nav item under "Governance & Compliance"
types.ts       # MODIFIED — add view union member
```

### Pattern 1: Reuse the generic ApprovalService — do not build a new approval engine
**What:** `governance_document_endpoints.py`'s "submit for approval" route calls `get_approval_service(db).create_approval_request(tenant_id, requester, action_type="governance_document_approval", description=..., details={"document_id": doc_id, "version": v}, workflow_steps=[...])`. The decision route (`approval_endpoints.py`'s existing `POST /api/approvals/{request_id}/decide`) is the ONE place decisions are made — the frontend must call that existing endpoint, not a new document-specific one.
**When to use:** Any time a governance document transitions from `draft` to `approved`.
**Example:**
```python
# Source: backend/approval_service.py (existing, read in full this session)
from approval_service import get_approval_service

async def submit_document_for_approval(db, tenant_id, doc_id, requester, approvers):
    service = get_approval_service(db)
    request = await service.create_approval_request(
        tenant_id=tenant_id,
        requester=requester,
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
The planner must include a task that **listens for approval resolution** — either (a) a lightweight poll/webhook where the document endpoint checks `approval_requests` status on read, or (b) a small hook inside `approval_service.submit_decision` — but **prefer (a)** to avoid modifying the shared `approval_service.py` file, keeping the generic engine untouched for its other caller.

### Pattern 2: Embedded versions array (clone of privacy_service.create_notice)
**What:** Each document is one Mongo doc with a `versions: []` array; every edit appends a new version entry rather than mutating in place.
**When to use:** DOC-01's "versioned policy/procedure documents" requirement.
**Example:**
```python
# Source: backend/privacy_service.py lines 328-341 (existing pattern, read in full this session)
async def create_notice(db, tenant_id: str, data: dict) -> dict:
    notice_id = _gen_id("notice")
    version = data.get("version", 1)
    doc = {
        "id": notice_id, "tenantId": tenant_id, "title": data.get("title", ""),
        "current_version": version,
        "versions": [{"version": version, "content_html": data.get("content_html", ""), "published_at": _now_iso()}],
        "created_at": _now_iso(), "updated_at": _now_iso(),
    }
    await db._db.privacy_notices.insert_one(doc)
    doc.pop("_id", None)
    return doc
```
Adapt field names for governance documents: `versions: [{version, content, status, author, created_at}]`, `current_version`, plus new top-level `status` (draft/pending_approval/approved/published) and `signatures: []`.

### Pattern 3: E-signature capture — boolean/metadata flag, not cryptographic signing
**What:** Capture typed full name (explicit re-entry, not auto-filled from session, to demonstrate deliberate intent), an explicit "I agree this constitutes my legal signature" consent checkbox, server-derived IP and user-agent, and a server-derived timestamp + authenticated identity. This satisfies the ESIGN Act/UETA four requirements (intent to sign, consent to do business electronically, association of signature with record+signer, retention) [CITED: general legal-tech consensus per Ironclad/DocuSign/Adobe explainers — this is **not** a substitute for legal counsel review; flag as an Assumption for user confirmation, see Assumptions Log].
**When to use:** DOC-02's "electronic signature capture" requirement.
**Example:**
```python
# Source: backend/cookie_consent_endpoints.py (existing pattern, read in full this session) +
#         backend/baa_endpoints.py sign_baa() (existing pattern, read in full this session)
@router.post("/documents/{doc_id}/sign")
async def sign_document(
    doc_id: str,
    payload: dict,               # {"typed_name": "...", "consent": true}
    request: Request,
    current_user: TokenData = Depends(get_current_user),
):
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

### Pattern 4: Signed-PDF export via reportlab (reuse compliance_reporting_pdf.py's escaping fix)
**What:** Build a `SimpleDocTemplate` with document title, version, approval metadata, full signature block (typed name, timestamp, IP), always passing user-controlled strings through `html.escape(str(v), quote=False)` before wrapping in `Paragraph(...)`.
**When to use:** DOC-02's "signed-PDF export proving who signed and when."
**Example:**
```python
# Source: backend/compliance_reporting_pdf.py (existing pattern, read in full this session) —
# the html.escape call is the CR-01 fix noted in STATE.md; do not omit it for new PDF code.
import html
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

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

### Anti-Patterns to Avoid
- **Building a second approval-request engine:** Do not create a `governance_document_approvals` collection with its own step/status logic — this duplicates `approval_service.py` and was explicitly called out in the phase goal as the wrong approach.
- **Extending `policy_endpoints.py`:** Confirmed (this session, full-file read) that it is `automation_policies` CRUD (conditions/actions/priority for remediation triggers) with zero conceptual overlap — adding governance-document routes there would conflate two unrelated domains under one 500-line-limited file.
- **Skipping the `html.escape` step in new PDF code:** This codebase has a documented prior XSS/injection issue in PDF generation (STATE.md "CR-01 reportlab-escaping fix" from Phase 13) — any new reportlab `Paragraph(...)` call on user-supplied content must escape first.
- **Trusting client-supplied signer identity/IP:** Per `approval_endpoints.py`'s explicit comment ("Always derive email from the verified JWT — never accept it from the request body"), the signer's email/identity and IP/user-agent must come from the authenticated request context, never from the request body.
- **Shipping the dashboard without nav wiring:** This exact class of bug has recurred 6 times in this codebase's history (5 dashboards in the v2.0 backfill, plus `ProgramsDashboard` caught separately per STATE.md) — the plan MUST include explicit `App.tsx`/`Sidebar.tsx`/`types.ts` tasks, not just the component file.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multi-step approval workflow (who approves next, notification on advance) | A new `governance_approval_state_machine` | `approval_service.py`'s `ApprovalService.create_approval_request`/`submit_decision` | Already handles multi-step sequencing, per-step approver notification via `email_service`, in-app notification fallback, and tenant scoping — exactly what DOC-01 asks for, and the phase goal explicitly mandates reuse |
| PDF rendering / table layout | A new PDF library or hand-rolled PDF byte generation | `reportlab` via the `compliance_reporting_pdf.py` pattern | Already the platform's PDF engine with a known-good escaping fix; adding a second PDF library would be pure duplication |
| E-signature legal validity plumbing (intent/consent/association/retention) | A cryptographic signing subsystem or third-party e-sign API integration | Typed-name + consent-checkbox + IP/UA + timestamp, per `cookie_consent_endpoints.py` + `baa_endpoints.py` patterns | Satisfies the ESIGN Act/UETA baseline at a fraction of the engineering cost; this codebase already has two working precedents for "capture consent/signature intent + IP + timestamp" |
| Document version history | A separate versions collection with joins | Embedded `versions: []` array, cloned from `privacy_service.create_notice` | One existing precedent in this exact codebase; avoids a join for what will typically be a small number of versions per document |

**Key insight:** Every piece DOC-01/DOC-02 needs already has a working, tested precedent somewhere in this codebase (`approval_service.py`, `privacy_service.py`'s notice versioning, `baa_endpoints.py`'s sign/terminate lifecycle, `cookie_consent_endpoints.py`'s IP/UA capture, `compliance_reporting_pdf.py`'s reportlab pattern). The engineering task for this phase is **composition, not invention** — cloning and adapting five known-good patterns rather than designing new ones.

## Common Pitfalls

### Pitfall 1: Building a parallel approval mechanism instead of calling into `approval_service.py`
**What goes wrong:** A new `governance_approvals` collection and status-transition logic gets built inside `governance_document_service.py`, duplicating what `approval_service.py` already does — directly contradicting the phase goal.
**Why it happens:** It can feel simpler to inline a 2-state (pending/approved) flow than to wire up the generic multi-step engine's `workflow_steps` shape.
**How to avoid:** The plan's first backend task must explicitly import and call `get_approval_service(db)` — grep the diff for `approval_service` import before considering the task done.
**Warning signs:** A new `db.<something>_approvals` collection name appears anywhere in the diff.

### Pitfall 2: Forgetting to re-check approval resolution before allowing signature/publish
**What goes wrong:** A document can be signed or published while its `approval_requests` entry is still `pending` or was `rejected`, because the document's own `status` field was set optimistically at submission time and never synced back.
**Why it happens:** `approval_service.submit_decision` updates `db.approval_requests`, not `db.governance_documents` — there is no built-in callback hook.
**How to avoid:** Either (a) have the document's "sign" and "publish" endpoints re-read the linked `approval_requests` doc and check `status == "approved"` before proceeding (recommended — no changes to the shared `approval_service.py`), or (b) accept a documented eventual-consistency window and reconcile on next list/GET. Do not silently trust a locally-cached `status` field on the document.
**Warning signs:** A document reaches `signed`/`published` state with no corresponding `approved` `approval_requests` record, or a rejected approval doesn't block signing.

### Pitfall 3: Trusting client-supplied timestamp/IP/identity for the signature record
**What goes wrong:** The signature payload accepts `signed_at`, `ip_address`, or `signer_email` from the request body, making the "who signed and when" claim in the exported PDF forgeable.
**Why it happens:** Convenient to let the frontend send a complete payload rather than deriving fields server-side.
**How to avoid:** Follow `approval_endpoints.py`'s explicit pattern — derive identity from `current_user` (JWT), IP from `request.client.host`, user-agent from `request.headers`, and timestamp from `datetime.now(timezone.utc)` — never from `payload`.
**Warning signs:** `payload.get("ip_address")` or `payload.get("signed_at")` appears anywhere in the sign endpoint.

### Pitfall 4: Skipping `html.escape` in the new signed-PDF export code
**What goes wrong:** A document title, typed signer name, or version content containing reportlab markup-like characters (`<`, `&`) breaks PDF rendering or is misinterpreted as XML markup by reportlab's `Paragraph`.
**Why it happens:** `Paragraph()` accepts a mini-XML-like markup language; unescaped user content can inject unintended formatting.
**How to avoid:** Every `Paragraph(str_value, style)` call on user-controlled content must first pass through `html.escape(str_value, quote=False)`, exactly as `compliance_reporting_pdf.py`'s `make_table()` and `_find_status_rows()` already do (this was the "CR-01" fix per STATE.md).
**Warning signs:** A `Paragraph(...)` call in the new export code with no `html.escape` wrapping.

### Pitfall 5: Extending `policy_endpoints.py` instead of creating new files
**What goes wrong:** A well-meaning "there's already a `/api/policies` router, let's add documents there" decision conflates automation-rule CRUD with governance-document CRUD in one file, likely also breaching the 500-line CLAUDE.md limit once document/version/approval/signature routes are added.
**Why it happens:** Naming similarity ("policy") is misleading — `policy_endpoints.py`'s "policy" means an if/then automation rule (`conditions`/`actions`/`priority` on `automation_policies`), not a governance policy document.
**How to avoid:** Confirmed this session by reading `policy_endpoints.py` in full (104 lines) — it is CRUD for `automation_policies` used by `PolicyManager.tsx`. New file `governance_document_endpoints.py` is correct.
**Warning signs:** Any diff touching `policy_endpoints.py` for this phase.

### Pitfall 6: Orphaned dashboard (no nav wiring)
**What goes wrong:** `GovernanceDocumentsDashboard.tsx` is built and works in isolation but has zero references from `App.tsx`/`Sidebar.tsx` — unreachable in the actual app, exactly like 5 dashboards caught in the v2.0 backfill and `ProgramsDashboard` before that (per STATE.md).
**Why it happens:** The component itself is the "interesting" work; nav wiring is easy to treat as an afterthought or skip silently.
**How to avoid:** The plan MUST include an explicit task (or explicit verification step) for `App.tsx` lazy import + route case + permission map entry, `Sidebar.tsx` nav item under "Governance & Compliance", and `types.ts` View union addition — and the phase's goal-verification step must confirm reachability via the production build's chunk output or an actual click-through, not just "component file exists."
**Warning signs:** `grep -rn "GovernanceDocumentsDashboard" App.tsx Sidebar.tsx` returns nothing after the frontend task is marked done.

## Code Examples

Verified patterns from this codebase (read in full this session):

### Multi-step approval creation (existing, reuse verbatim)
```python
# Source: backend/approval_service.py lines 13-61
async def create_approval_request(
    self, tenant_id, requester, action_type, description, details, workflow_steps
) -> Dict[str, Any]:
    # workflow_steps: [{"role": "SecurityAdmin", "approvers": ["user@example.com"]}]
    ...
    await self.db.approval_requests.insert_one(request)
    await self._notify_approvers(request, steps[0])
    return request
```

### BAA-style sign/terminate lifecycle (adapt for document signature + publish)
```python
# Source: backend/baa_endpoints.py lines 137-168
@router.post("/{baa_id}/sign")
async def sign_baa(baa_id: str, payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    party = payload.get("party", "us")
    update_field = "signed_by_vendor" if party == "vendor" else "signed_by_us"
    await db["baa_agreements"].update_one(
        baa_filter,
        {"$set": {update_field: True, f"{update_field}_at": time.time(), f"{update_field}_by": _sub(current_user)}}
    )
```

### IP + user-agent capture for a legal-consent record (existing, adapt for signature)
```python
# Source: backend/cookie_consent_endpoints.py lines 51-59
@router.post("/record")
async def record_consent(payload: ConsentRecord, request: Request):
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    meta = {"userId": payload.userId, "ipAddress": ip, "userAgent": ua}
```

### Frontend fetch + toast pattern (existing, clone for GovernanceDocumentsDashboard.tsx)
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

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| N/A — this is greenfield surface within the codebase | Compose existing `approval_service.py` + `privacy_service.py` versioning + `baa_endpoints.py` signature-flag + `cookie_consent_endpoints.py` IP/UA + `compliance_reporting_pdf.py` reportlab patterns | This phase (28) | First governance-document-management surface in the platform; establishes the reusable pattern combination other GRC-document-shaped future phases (e.g. Phase 29 Trust Center's document library) can clone |

**Deprecated/outdated:** None — no existing governance-document code is being replaced; this is additive.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Typed name + explicit consent checkbox + server-derived IP/UA/timestamp is a legally-sufficient "electronic signature capture" baseline (ESIGN Act/UETA) for this platform's compliance-governance use case | Architecture Patterns → Pattern 3 | **RESOLVED (user confirmed):** lightweight baseline accepted as sufficient for this phase's scope. Document in the plan as the ESIGN/UETA-baseline standard (not a DocuSign/qualified-signature replacement) so future readers know the deliberate scope boundary. |
| A2 | Embedding `versions[]` as an array inside the document doc (not a separate collection) will scale adequately for expected document/version counts | Architecture Patterns → Pattern 2 | If a tenant accumulates hundreds of versions per document (unlikely for policy/procedure documents, which typically revise a handful of times per year), the embedded-array read pattern could become a performance concern; low risk given the existing `privacy_notices` precedent has run without issue |
| A3 | Reusing `view:compliance`/`manage:compliance` RBAC permissions (already granted broadly to Security Analyst/Compliance/Admin roles) is sufficient rather than introducing a new `manage:governance_documents` permission | Common Pitfalls / RBAC (implicit) | **RESOLVED (user confirmed):** reuse existing `manage:compliance` role, matching every other Tier 1/2 phase's RBAC pattern in this milestone. No new role/permission surface for this phase. |

## Open Questions (RESOLVED)

1. **Does the approval workflow need to be role-configurable per tenant, or is a single fixed reviewer role (e.g. "ComplianceOfficer") sufficient for v1?**
   - What we know: `approval_service.create_approval_request` accepts an arbitrary `workflow_steps` list, so multi-role/multi-step is already supported by the engine.
   - What's unclear: Whether DOC-01 requires the tenant admin to configure approvers, or whether a fixed single-step "any compliance-role user can approve" flow is acceptable for this phase's scope.
   - Recommendation: Default to a single-step workflow (`approvers` = list of tenant users holding `manage:compliance`), matching Tier-2 "medium scope" sizing; defer configurable multi-step workflows to a later phase if requested.
   - **RESOLVED: single fixed-role workflow, as recommended (consistent with the manage:compliance RBAC decision above) — implement in 28-01-PLAN.md.**

2. **Should "publish" be a distinct state from "approved," or does approval == publish?**
   - What we know: `privacy_service.create_notice` treats "created" and "published" as the same event (no separate publish step); BAA's `sign` → `active` transition is the closer analog to "approval unlocks an active/effective state."
   - What's unclear: Whether the phase needs a document to be approved but held back from being tenant-visible until an explicit "publish" action, or whether `approved` should immediately make the document visible/effective.
   - Recommendation: Add a distinct `published` state gated behind `approved`, since governance documents (unlike privacy notices) often need a scheduled effective date — but treat this as Claude's discretion unless CONTEXT.md says otherwise (none exists for this phase).
   - **RESOLVED: distinct `published` state gated behind `approved`, as recommended — implement in 28-01-PLAN.md.**

3. **Does DOC-02's "signed-PDF export" need multiple signers (e.g. document owner AND approver both sign) or a single signer?**
   - What we know: BAA's two-party pattern (`signed_by_us`/`signed_by_vendor`) shows this codebase already has a working two-signer precedent.
   - What's unclear: Whether governance documents need multi-signer support (e.g. document author + approving officer) or a single acknowledging signature is sufficient for v1.
   - Recommendation: Design `signatures: []` as an array from the start (not fixed named fields like BAA's `signed_by_us`/`signed_by_vendor`) so it trivially supports 1-to-N signers without a schema migration later.
   - **RESOLVED: `signatures: []` array from the start, as recommended — implement in 28-02-PLAN.md (or wherever DOC-02 lands).**

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| reportlab | Signed-PDF export (DOC-02) | ✓ | 5.0.0 [VERIFIED: pip show reportlab] | — |
| MongoDB (via Motor) | Document/version/signature storage | ✓ (assumed running — used by every other phase in this milestone) [ASSUMED — not independently re-probed this session; no prior phase in this milestone flagged it unavailable] | — | — |
| Python 3 / FastAPI | Backend endpoints | ✓ (assumed — project-standard, unchanged since Phase 25/26/27) [ASSUMED] | — | — |

**Missing dependencies with no fallback:** none identified.
**Missing dependencies with fallback:** none identified — this phase introduces no new external dependency.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (project-standard; `pytest.ini` at repo root) [VERIFIED: `find` confirmed `pytest.ini` exists] |
| Config file | `pytest.ini` (repo root) |
| Quick run command | `cd backend && python -m pytest tests/test_governance_documents.py -x` |
| Full suite command | `cd backend && python -m pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DOC-01 | Create draft document, add version, submit for approval (delegates to `approval_service`), approval-resolution gates publish | unit + integration | `pytest tests/test_governance_documents.py -k "approval or version" -x` | ❌ Wave 0 |
| DOC-01 | Tenant isolation — a document/approval in tenant A is invisible/403 to tenant B | unit | `pytest tests/test_governance_documents.py -k tenant -x` | ❌ Wave 0 |
| DOC-02 | Sign endpoint captures typed name, consent, server-derived IP/UA/timestamp; rejects missing consent or empty typed name | unit | `pytest tests/test_governance_documents.py -k sign -x` | ❌ Wave 0 |
| DOC-02 | Signed-PDF export produces a valid PDF containing signer name/timestamp, with `html.escape` applied to all user content | unit | `pytest tests/test_governance_documents.py -k pdf -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_governance_documents.py -x`
- **Per wave merge:** `cd backend && python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_governance_documents.py` — new file; clone the `_col`/`_db`/`_user`/`_app` helper block from `backend/tests/test_automation_and_baa.py` (this repo copies test helpers per-file rather than sharing a conftest fixture module for these smaller GRC-module test files)
- [ ] Framework install: none — pytest already present and configured

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | yes | All routes require `get_current_user` (JWT bearer), matching every sibling GRC endpoint file in this codebase |
| V3 Session Management | no | No new session-management surface introduced |
| V4 Access Control | yes | Tenant-scoped queries (`{"id": doc_id, "tenantId": tenant_id}` filter, matching `baa_endpoints.py`/`privacy_endpoints.py`); approve/sign actions gated behind `manage:compliance` (or a narrower permission if the user chooses to introduce one per Assumption A3) |
| V5 Input Validation | yes | `typed_name` non-empty check, explicit `consent` boolean check, `html.escape` on all PDF-rendered content — mirrors the existing CR-01 fix |
| V6 Cryptography | no | This phase deliberately does not implement cryptographic signing (see Pattern 3 / Don't Hand-Roll) — no crypto library needed |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Cross-tenant document/signature read via guessable document ID | Information Disclosure | Explicit `{"id": doc_id, "tenantId": tenant_id}` filter on every read/write, returning identical 404 for wrong-tenant vs. nonexistent (matches `27-02-PLAN.md`'s T-27-03 precedent and `approval_endpoints.py`'s 403-not-404 precedent — pick one convention and apply consistently) |
| Client-forged signature metadata (IP, timestamp, signer identity) | Tampering / Spoofing | Server-derives all three from `request.client.host`, `datetime.now(timezone.utc)`, and JWT-derived `current_user` — never accept these fields from the request body (per `approval_endpoints.py`'s explicit existing comment) |
| Reportlab markup injection via unescaped user content in signed-PDF export | Tampering | `html.escape(str_value, quote=False)` before every `Paragraph(...)` call, reproducing the CR-01 fix already applied in `compliance_reporting_pdf.py` |
| Approval bypass — signing/publishing a document whose linked approval request is still pending or was rejected | Elevation of Privilege | Sign/publish endpoints must re-check `db.approval_requests` status == "approved" before proceeding (see Pitfall 2) rather than trusting a possibly-stale local `status` field |

## Sources

### Primary (HIGH confidence)
- `backend/approval_service.py` (full file read, this session) — generic approval-request engine
- `backend/approval_endpoints.py` (full file read, this session) — only existing caller of `approval_service.py`, establishes the JWT-derived-identity convention
- `backend/policy_endpoints.py` (full file read, this session) — confirmed unrelated automation-rule CRUD
- `backend/privacy_service.py` lines 320-360 (read, this session) — `create_notice`/`get_notice_versions` versioning pattern
- `backend/baa_endpoints.py` (full file read, this session) — sign/terminate lifecycle pattern
- `backend/cookie_consent_endpoints.py` (read, this session) — IP/user-agent legal-consent capture pattern
- `backend/compliance_reporting_pdf.py` (full file read, this session) — reportlab PDF generation + `html.escape` fix
- `backend/router_registry.py` (read, this session) — router registration pattern + confirmed no Phase 26/27 routers registered yet
- `components/BAAManagement.tsx`, `components/PrivacyLegalDashboard.tsx` (read, this session) — frontend fetch/tab/list pattern
- `components/Sidebar.tsx` lines 335-395 (read, this session) — "Governance & Compliance" nav section, exact insertion point
- `.planning/phases/26-vendor-and-risk-data-completeness/*.md`, `.planning/phases/27-compliance-export-formats-oscal-and-sbom/*.md` (read, this session) — confirmed zero file overlap with Phase 28
- `pip show reportlab` (run, this session) — version 5.0.0 confirmed installed

### Secondary (MEDIUM confidence)
- ESIGN Act / UETA four-requirement summary (WebSearch, this session, cross-referenced across Ironclad/Docusign/Adobe/SignWell explainer pages) — general industry consensus on e-signature legal baseline; not a substitute for actual legal review (see Assumptions Log A1)

### Tertiary (LOW confidence)
- None used as authoritative for any Standard Stack or Architecture recommendation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; every reused pattern verified by direct full-file reads this session
- Architecture: HIGH — composition of five directly-read, already-shipped-and-tested patterns in this exact codebase
- Pitfalls: HIGH — five of six pitfalls are drawn from this codebase's own documented history (STATE.md's CR-01 fix, the 6-instance orphaned-dashboard pattern, `approval_endpoints.py`'s explicit anti-spoofing comment)

**Research date:** 2026-07-07
**Valid until:** 30 days (stable internal codebase patterns; no fast-moving external dependency)
