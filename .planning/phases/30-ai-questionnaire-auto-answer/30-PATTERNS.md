# Phase 30: AI Questionnaire Auto-Answer - Pattern Map

**Mapped:** 2026-07-07
**Files analyzed:** 12 (new/modified)
**Analogs found:** 12 / 12

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/rag_service.py` (MODIFIED) | service | CRUD (vector store ingest/query) | itself (existing file, in-place fix) | exact |
| `backend/ai_service.py` (MODIFIED) | service | request-response | itself (existing file, in-place fix) | exact |
| `backend/questionnaire_inbound_service.py` | service | CRUD + file-I/O | `backend/questionnaire_service.py` (CRUD shape) + `backend/compliance_framework_mgmt_endpoints.py` (Excel/CSV parsing) | role-match (composite) |
| `backend/questionnaire_inbound_endpoints.py` | route/controller | request-response + file-I/O | `backend/questionnaire_endpoints.py` (router shape) + `backend/compliance_framework_mgmt_endpoints.py`'s `/import` endpoint (`UploadFile`) | role-match (composite) |
| `backend/questionnaire_answer_draft_service.py` | service | request-response (RAG + generation) | `backend/compliance_narrative_service.py` | exact |
| `backend/questionnaire_answer_review_service.py` | service | event-driven (state machine) | `backend/evidence_review_service.py` | exact |
| `backend/questionnaire_answer_review_endpoints.py` | route/controller | request-response | `backend/evidence_review_endpoints.py` | exact |
| Frontend draft-review queue component (NEW, e.g. `components/QuestionnaireAnswerReviewPanel.tsx`) | component | request-response | `components/EvidenceReviewPanel.tsx` | exact |
| `backend/tests/test_rag_service_tenant_isolation.py` | test | integration | `backend/tests/test_evidence_review.py` (helper-block convention) | role-match |
| `backend/tests/test_questionnaire_inbound_service.py` | test | unit | `backend/tests/test_evidence_review.py` | role-match |
| `backend/tests/test_questionnaire_answer_draft_service.py` | test | unit | `backend/tests/test_evidence_review.py` | role-match |
| `backend/tests/test_questionnaire_answer_review_service.py` | test | unit + integration | `backend/tests/test_evidence_review.py` (near-verbatim) | exact |
| `backend/tests/test_questionnaire_auto_answer_e2e.py` | test | integration (TestClient/HTTP) | `backend/tests/test_evidence_review.py`'s `_build_client` pattern | role-match |

---

## Pattern Assignments

### `backend/rag_service.py` (MODIFIED — service, CRUD)

**Analog:** itself, `backend/rag_service.py:1-89` (full file, only 89 lines)

Current state — `ingest_text()`/`query()` have zero tenant scoping (the exact gap the phase must close):

```python
# backend/rag_service.py:16-27 — single global collection, no tenantId anywhere
class RagService:
    def __init__(self):
        self.client = None
        self.collection = None
        try:
            self.client = chromadb.PersistentClient(path=DB_DIR)
            self.collection = self.client.get_or_create_collection(name="omni-agent-knowledge")
        except Exception as e:
            logger.error(f"❌ Failed to initialize ChromaDB: {e}")

    def ingest_text(self, content: str, source: str = "manual_entry") -> dict:
        # ...
        self.collection.add(
            documents=[content],
            metadatas=[{"source": source, "ingested_at": timestamp}],  # NO tenantId
            ids=[doc_id]
        )
```

```python
# backend/rag_service.py:55-66 — query() passes no `where` filter at all
def query(self, query_text: str, n_results: int = 3) -> list:
    results = self.collection.query(
        query_texts=[query_text],
        n_results=n_results
    )
```

**Required fix (per AI-SPEC Pitfall 1 / RESEARCH T1, resolved Open Question 2):** add a `tenant_id: str = "global"` param to both methods; write `"tenantId": tenant_id` into `ingest_text()`'s metadata dict; pass `where={"$or": [{"tenantId": tenant_id}, {"tenantId": "global"}]}` into `collection.query()`. Existing content from `ingest_security_standards.py` is treated as `"global"` in place — no backfill/migration needed. This is an in-place edit to the existing methods above, not a new file — keep the same `try/except`-returns-`{"success": False}` / `[]` error shape already established.

---

### `backend/ai_service.py` (MODIFIED — service, request-response)

**Analog:** itself, `backend/ai_service.py:205-302` (`generate_text`) + `backend/ai_providers.py:142-177` (`AnthropicProvider.generate`)

```python
# backend/ai_service.py:205-211 — current signature, no temperature/max_tokens
async def generate_text(
    self,
    prompt: str,
    source: str = "generic",
    _retries: int = 3,
    provider: Optional[AIProvider] = None,
) -> str:
```

```python
# backend/ai_providers.py:159-177 — hardcoded max_tokens, no temperature at all
async def generate(self, prompt: str) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={...},
            json={
                "model": self.model_name,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
```

**Required fix (per AI-SPEC Pitfall 2):** extend `AIProvider.generate()` (abstract, `ai_providers.py:20`), `AnthropicProvider.generate()`, and `ai_service.generate_text()` to accept optional `temperature: float | None = None` and `max_tokens: int = 1024` kwargs, threading them through to the `json={...}` payload dict (only include `temperature` key if not None, since other providers/tests may not expect it). Preserve every other line of `generate_text()` unchanged (guardrail scan-in/scan-out at `:219`/`:298`, circuit breaker at `:228`, retry/backoff loop) — this is an additive signature change, not a rewrite.

---

### `backend/questionnaire_inbound_service.py` (NEW — service, CRUD + file-I/O)

**Analog 1 (CRUD shape):** `backend/questionnaire_service.py:1-135` (full file)

```python
# backend/questionnaire_service.py:12-44 — clone this module-level singleton +
# tenant-scoped create/list shape directly, swap `questionnaires` collection
# for a new `questionnaire_inbound` (or `questionnaires_inbound`) collection
class QuestionnaireService:
    def _db(self):
        from database import get_database
        return get_database()

    async def create_questionnaire(self, data: Dict[str, Any], tenant_id: str, created_by: str) -> Dict:
        db = self._db()
        now = datetime.now(timezone.utc).isoformat()
        questions = data.get("questions") or []
        for q in questions:
            if "id" not in q:
                q["id"] = str(uuid.uuid4())
        doc = {
            "id": f"qn-{uuid.uuid4().hex}",
            "tenantId": tenant_id,
            "title": data["title"],
            "questions": questions,
            "status": "Draft",
            "createdBy": created_by,
            "created_at": now,
            "updated_at": now,
        }
        await db.questionnaires.insert_one(doc)
        doc.pop("_id", None)
        return doc

questionnaire_service = QuestionnaireService()
```

**Analog 2 (Excel/CSV upload+parsing — resolved scope: .xlsx/.csv only, no PDF/DOCX):** `backend/compliance_framework_mgmt_endpoints.py:215-267` (`import_compliance_controls`)

```python
# backend/compliance_framework_mgmt_endpoints.py:231-267 — clone the CSV branch
# and the openpyxl Excel branch verbatim; drop the PDF/DOCX branches entirely
# (RESEARCH.md Open Question 1: scope is Excel + CSV only)
if filename.endswith(".csv"):
    reader = csv.DictReader(io.StringIO(content.decode("utf-8", errors="replace")))
    for row in reader:
        cid  = (row.get("ID") or row.get("id") or "").strip()
        # ... map to question record instead of control record

elif filename.endswith((".xlsx", ".xls")):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise HTTPException(status_code=400, detail="Empty spreadsheet")
        headers = [str(h).strip().lower() if h else "" for h in rows[0]]
        for row in rows[1:]:
            r = {headers[i]: (str(row[i]).strip() if row[i] is not None else "")
                 for i in range(min(len(headers), len(row)))}
            # column-mapper: try "question"/"question text"/"control question" headers;
            # if none match, 400 with a clear error (per RESEARCH.md's resolved design)
    except ImportError:
        raise HTTPException(status_code=422,
            detail="openpyxl is required for Excel import. Install it or upload a CSV.")
```

Adapt: instead of building control records (`id`/`name`/`description`/`category`), build question records (`id`, `text`, source row index) feeding into an inbound question-set document shaped like `QuestionnaireCreate`'s `questions: List[Dict]` (see `questionnaire_endpoints.py:32-36` below). RBAC: open to any authenticated tenant user (RESEARCH.md RBAC table — "Create/edit inbound question set: any authenticated tenant user").

---

### `backend/questionnaire_inbound_endpoints.py` (NEW — route, request-response + file-I/O)

**Analog:** `backend/questionnaire_endpoints.py:1-121` (full file, router shape) + `compliance_framework_mgmt_endpoints.py:215-220` (`UploadFile` param pattern)

```python
# backend/questionnaire_endpoints.py:1-21 — clone router setup + tenant/role helpers
from fastapi import APIRouter, Depends, HTTPException
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/questionnaires/inbound", tags=["Inbound Questionnaires"])

def _tenant(user: TokenData) -> str:
    tid = getattr(user, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tid
```

```python
# backend/questionnaire_endpoints.py:32-36 — Pydantic request model shape to clone
class QuestionnaireCreate(BaseModel):
    title: str
    description: Optional[str] = None
    type: Optional[str] = "Internal"
    questions: Optional[List[Dict[str, Any]]] = None
```

```python
# backend/compliance_framework_mgmt_endpoints.py:215-220 — upload endpoint signature
@router.post("/api/compliance/{framework_id}/import")
async def import_compliance_controls(
    framework_id: str,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
```

Combine both: a manual `POST /api/questionnaires/inbound` (JSON body, `QuestionnaireCreate`-shaped) plus a `POST /api/questionnaires/inbound/{qid}/upload` (`UploadFile`) that calls `questionnaire_inbound_service`'s CSV/Excel parser and appends parsed questions. No role gate beyond `get_current_user` (mirrors `create_questionnaire`'s open gate).

---

### `backend/questionnaire_answer_draft_service.py` (NEW — service, request-response / RAG+generation)

**Analog:** `backend/compliance_narrative_service.py:1-152` (full pattern: sanitize → prompt-build → generate → validate → fallback)

```python
# backend/compliance_narrative_service.py:26-30 — sanitization helper to clone
# for evidence content/source fields (AI-SPEC 4b: RAG-specific injection surface)
_UNSAFE = re.compile(r"[<>{}\[\]\\]")
_NEWLINES = re.compile(r"[\r\n]+")

def _sanitise(value: str, max_len: int = 200) -> str:
    value = _NEWLINES.sub(" ", str(value))
    return _UNSAFE.sub("", value).strip()[:max_len]
```

```python
# backend/compliance_narrative_service.py:38-77 — Pydantic-validated-output +
# immediate-fallback pattern (no retry on ValidationError) to clone for AnswerDraft
class NarrativeOutput(BaseModel):
    text: str
    word_count: int
    limit: int = 200

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("narrative text must not be empty")
        if v.startswith(("BLOCKED:", "Error:")):
            raise ValueError(f"LLM returned error string: {v[:80]}")
        return v

def _validated_narrative(raw: str, fallback: str, limit: int = 200) -> str:
    try:
        output = NarrativeOutput.from_raw(raw, limit=limit)
        return output.text
    except ValidationError as exc:
        logger.warning("[NarrativeService] Pydantic validation failed: %s", exc)
        return fallback
```

```python
# backend/compliance_narrative_service.py:89-117 — full entry-point shape:
# sanitize inputs -> build system/user prompt around fenced block ->
# ai_service.generate_text() -> check BLOCKED:/Error: prefix -> validate -> fallback
async def generate_executive_summary(framework_name, score, failing_controls, period) -> str:
    safe_fw = _sanitise(framework_name)
    fallback = _fallback_executive_summary(safe_fw, score)
    system_part = ("You are a compliance analyst ... Do not invent control names, "
                   "scores, or findings not present in the data below. ...")
    user_part = f"<compliance_data>\n...\n</compliance_data>\n\nWrite a summary..."
    result = await ai_service.generate_text(
        f"{system_part}\n\n{user_part}", source="compliance_narrative"
    )
    if result.startswith(("BLOCKED:", "Error:")):
        logger.warning("[NarrativeService] generate_text failed: %s", result[:80])
        return fallback
    trimmed = _trim_to_words(result.strip(), 150)
    return _validated_narrative(trimmed, fallback, limit=150)
```

**Concrete `AnswerDraft`/`draft_answer_for_question()` to implement is already fully specified** in `30-AI-SPEC.md` Section 3 "Entry Point Pattern" (lines 156-247) — copy that block directly as the starting implementation; it is a purpose-built clone of the pattern above, already written against this codebase's real signatures. Note it calls `ai_service.generate_text(...)` without `temperature`/`max_tokens` yet — update that call once `ai_service.py`'s signature extension (above) lands, per Pitfall 2's recommended `temperature=0-0.2`, `max_tokens=1536-2048`.

---

### `backend/questionnaire_answer_review_service.py` (NEW — service, event-driven state machine)

**Analog:** `backend/evidence_review_service.py:1-376` (full file — clone near-verbatim per AI-SPEC/RESEARCH)

```python
# backend/evidence_review_service.py:56-93 — submit-for-review guard pattern
# (swap asset_compliance.evidence[] for questionnaire_answer_drafts docs directly,
# since drafts are their own top-level collection, not an embedded array — filter
# simplifies to a straight status-scoped update_one on the draft's own _id/id)
def _submittable_statuses() -> list:
    return [None, "needs_revision", "rejected"]

async def submit_for_review(evidence_id: str, db, tenant_id: str) -> bool:
    result = await db.asset_compliance.update_one(
        {"tenantId": tenant_id, "evidence": {"$elemMatch": {
            "id": evidence_id, "status": {"$in": _submittable_statuses()}}}},
        {"$set": {"evidence.$.status": "pending_review", "evidence.$.review_updated_at": _now_iso()}},
    )
    return result.modified_count > 0
```

```python
# backend/evidence_review_service.py:193-321 — update_review_decision(): the
# core pattern to clone for approve/reject/needs_revision AND for the new
# "mark submitted" transition (T3's hard {"status": "approved"} DB guard)
async def update_review_decision(
    review_id, evidence_id, decision, comment, db, tenant_id, decided_by=None,
) -> dict | None:
    if decision not in _valid_decisions():
        raise ValueError(...)
    if requires_comment(decision) and not (comment or "").strip():
        raise ValueError(f"Comment is required for decision '{decision}'")
    review = await db[_EVIDENCE_REVIEWS_COL].find_one_and_update(
        {"id": review_id, "evidenceId": evidence_id, "tenantId": tenant_id, "status": "pending"},
        {"$set": {"status": decision, "comment": comment, "updated_at": now, "decided_by": decided_by}},
        return_document=True, projection={"_id": 0},
    )
    if not review:
        return None
    # ... propagate status, re-check target still matches, log warning if not
```

**New "mark submitted" transition (RAG-02 hard guardrail, T3):** clone the same `find_one_and_update` shape, but the filter for this specific transition MUST include `{"status": "approved"}` as a hard precondition — a record in any other state fails to match and the call returns `None`/404, closing Critical Failure Mode #2 at the data layer (not merely at the endpoint/role-gate level). `reviewer_id`/`decided_by` must be server-derived from `current_user`, never accepted from the request body (T5 — see `update_evidence_review` endpoint below for the exact pattern already doing this).

Status vocabulary for `questionnaire_answer_drafts`: `pending_review → approved | rejected | needs_revision`, then `approved → submitted` (this last transition has no equivalent in `evidence_review_service.py` — new but same architectural pattern).

---

### `backend/questionnaire_answer_review_endpoints.py` (NEW — route, request-response)

**Analog:** `backend/evidence_review_endpoints.py:1-225` (full file — clone router/RBAC shape directly)

```python
# backend/evidence_review_endpoints.py:37-45 — _REVIEWER_ROLES constant,
# import verbatim (do not redefine with different values) per RESEARCH.md RBAC
_REVIEWER_ROLES = {"admin", "super_admin", "compliance_reviewer"}
```

```python
# backend/evidence_review_endpoints.py:119-137 — role-gate + server-derived
# reviewer identity pattern (T5) to clone for the decision endpoint
@router.patch("/api/evidence/{evidence_id}/review/{review_id}")
@limiter.limit("30/minute")
async def update_evidence_review(
    request: Request, response: Response, evidence_id: str, review_id: str,
    body: UpdateDecisionRequest, current_user: TokenData = Depends(get_current_user),
):
    if current_user.role not in _REVIEWER_ROLES:
        raise HTTPException(status_code=403,
            detail="Only admins and compliance reviewers can make review decisions")
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    ...
    review = await update_review_decision(
        review_id, evidence_id, body.decision, body.comment, db, tenant_id,
        decided_by=current_user.username or "unknown",   # server-derived, never from body
    )
```

```python
# backend/evidence_review_endpoints.py:174-187 — non-repudiable audit log write,
# wrapped so a transient audit-log failure never turns an already-committed
# decision into a 500
try:
    await db.audit_logs.insert_one({
        "action": "evidence_review_decision", "tenantId": tenant_id,
        "evidence_id": evidence_id, "review_id": review_id,
        "decision": body.decision, "performed_by": current_user.username or "unknown",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
except Exception:
    logger.exception("evidence_review: failed to write audit log for review %s", review_id)
```

Endpoints to add: `POST /questionnaire-answer-drafts/{draft_id}/review` (create), `PATCH .../review/{review_id}` (decide — role-gated), `GET .../reviews`, `GET .../pending-review`, plus a new `POST .../submit` endpoint enforcing the `{"status": "approved"}` DB guard from the service layer above.

---

### Frontend draft-review queue component (NEW — component, request-response)

**Analog:** `components/EvidenceReviewPanel.tsx:1-269` (full file — clone structure/styling directly, per orchestrator instructions since no UI-SPEC exists)

```tsx
// components/EvidenceReviewPanel.tsx:9-15 — role-gate literal kept in sync
// by hand with the backend constant (IN-01 documented drift risk) — clone
// verbatim, matching questionnaire_answer_review_endpoints.py's _REVIEWER_ROLES
const _REVIEWER_ROLES = ['admin', 'super_admin', 'compliance_reviewer'];
```

```tsx
// components/EvidenceReviewPanel.tsx:23-26 — FastAPI validation-error body
// shape helper, reusable verbatim for the new component's fetch error handling
const _errorDetail = (d: unknown, fallback: string): string => {
  const detail = (d as { detail?: unknown } | null | undefined)?.detail;
  return typeof detail === 'string' ? detail : fallback;
};
```

```tsx
// components/EvidenceReviewPanel.tsx:43-58 — status badge color-map convention
const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  pending_review: { bg: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-800 dark:text-amber-300', label: 'Pending Review' },
  approved:       { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-800 dark:text-green-300', label: 'Approved' },
  rejected:       { bg: 'bg-red-100 dark:bg-red-900/30',     text: 'text-red-800 dark:text-red-300',     label: 'Rejected' },
  needs_revision: { bg: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-800 dark:text-amber-300', label: 'Needs Revision' },
};
```

```tsx
// components/EvidenceReviewPanel.tsx:71-119 — fetch/list + submit-for-review
// hooks pattern; clone directly, swapping evidenceId for draftId and the
// /api/evidence/... routes for /api/questionnaire-answer-drafts/... routes
const { currentUser } = useUser();
const [reviews, setReviews] = useState<Review[]>([]);
const isReviewer = currentUser && _REVIEWER_ROLES.includes(currentUser.role);

const fetchReviews = useCallback(async () => {
  setLoading(true); setError('');
  try {
    const res = await authFetch(`${API}/evidence/${evidenceId}/reviews`);
    if (!res.ok) { const d = await res.json().catch(() => ({})); setError(_errorDetail(d, 'Failed to load reviews')); return; }
    const data = await res.json();
    setReviews(data.reviews || []);
  } catch (err: unknown) {
    setError(err instanceof Error ? err.message : 'Failed to load reviews');
  } finally { setLoading(false); setHasFetchedOnce(true); }
}, [evidenceId]);
```

```tsx
// components/EvidenceReviewPanel.tsx:123-156 — two-step review-decision flow
// (create review record, then PATCH decision) — clone verbatim for
// approve/reject/needs-revision on a draft; add a fourth "Mark Submitted"
// action gated on evidenceStatus === 'approved' (new, no equivalent in the
// evidence-review flow, since RAG-02's submitted terminal state is new)
const handleReviewDecision = async (decision: string) => {
  if ((decision === 'rejected' || decision === 'changes_requested') && !comment.trim()) {
    showToast('Comment required for this decision', 'error');
    return;
  }
  setSubmitting(true);
  try {
    const reviewRes = await authFetch(`${API}/evidence/${evidenceId}/review`, {
      method: 'POST',
      body: JSON.stringify({ comment: comment.trim() || '(no comment provided)' }),
    });
    if (!reviewRes.ok) { /* ... */ return; }
    const { review } = await reviewRes.json();
    const patchRes = await authFetch(`${API}/evidence/${evidenceId}/review/${review.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ decision, comment: comment.trim() || '' }),
    });
    // ...
  } finally { setSubmitting(false); }
};
```

**Key addition beyond the analog:** the draft-review UI must also render the retrieved source evidence alongside the draft text (AI-SPEC Critical Failure Mode #1 — "wasn't shown alongside the draft" is the documented root cause of rubber-stamp approval). `EvidenceReviewPanel.tsx` has no equivalent element to clone for this — add a new evidence-citation list block (e.g. rendering `sourceEvidenceIds`/`answerText` side-by-side) as net-new UI, not adapted from the analog.

Also needed: a question-upload form (file input + manual-entry textarea/table) — no direct analog exists in this codebase's frontend; build against `questionnaire_inbound_endpoints.py`'s two new endpoints (JSON create + `UploadFile` upload), following the same `authFetch`/`showToast`/`API_BASE` conventions shown above.

---

### `backend/tests/*` (NEW — test files)

**Analog:** `backend/tests/test_evidence_review.py:1-108` (helper-block convention — clone `_make_user`/`_make_mock_db`/`_build_client`/`_stop_patchers` verbatim, adapted per file)

```python
# backend/tests/test_evidence_review.py:16-21 — _make_user() to clone directly
def _make_user(tenant_id="tenant-a", role="admin", username="reviewer1"):
    u = MagicMock()
    u.tenant_id = tenant_id
    u.role = role
    u.username = username
    return u
```

```python
# backend/tests/test_evidence_review.py:86-97 — _build_client() TestClient
# pattern to clone for test_questionnaire_auto_answer_e2e.py's HTTP-level tests
_active_patchers = []

def _build_client(mock_db, current_user):
    import evidence_review_endpoints as mod
    from authentication_service import get_current_user
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = lambda: current_user
    patcher = patch("evidence_review_endpoints.get_database", return_value=mock_db)
    patcher.start()
    _active_patchers.append(patcher)
    return TestClient(app, raise_server_exceptions=False)
```

```python
# backend/tests/test_evidence_review.py:100-108 — autouse fixture guaranteeing
# every patcher is stopped even on test failure (WR-04) — clone verbatim,
# this is a correctness requirement, not stylistic
@pytest.fixture(autouse=True)
def _stop_patchers():
    yield
    while _active_patchers:
        _active_patchers.pop().stop()
```

`_make_mock_db()` (`test_evidence_review.py:24-75`) needs adaptation per test file: `test_questionnaire_answer_review_service.py` swaps `db.asset_compliance` for a `db.questionnaire_answer_drafts` mock; `test_rag_service_tenant_isolation.py` has no direct analog for its mock shape (it needs a real/fixture ChromaDB `PersistentClient` seeded with two tenants, not a MagicMock) — see "No Analog Found" below.

---

## Shared Patterns

### Tenant scoping via `tenant_context`
**Source:** `30-AI-SPEC.md` Section 3 Core Imports; `backend/tenant_context.py`
**Apply to:** `questionnaire_answer_draft_service.py`, and any function calling `rag_service`/`ai_service`
```python
from tenant_context import set_tenant_id, get_tenant_id
set_tenant_id(tenant_id)  # MUST be called before any rag_service/ai_service call
```

### Guardrail-checked `generate_text()` call + BLOCKED:/Error: prefix check
**Source:** `backend/compliance_narrative_service.py:110-117`, `backend/ai_service.py:219-221,298-300`
**Apply to:** `questionnaire_answer_draft_service.py`'s every LLM call site
```python
result = await ai_service.generate_text(f"{system_part}\n\n{user_part}", source="questionnaire_auto_answer")
if result.startswith(("BLOCKED:", "Error:")):
    logger.warning("... generate_text failed: %s", result[:80])
    return fallback  # never let a block/error string reach a reviewer as if real
```

### RBAC role-gate + server-derived identity
**Source:** `backend/evidence_review_endpoints.py:37-45,119-137,158`
**Apply to:** `questionnaire_answer_review_endpoints.py` — import/duplicate `_REVIEWER_ROLES = {"admin", "super_admin", "compliance_reviewer"}` verbatim, never redefine with different values; `decided_by`/`reviewer_id` always from `current_user.username`, never from request body.

### DB-query-level status guard for terminal-state transitions
**Source:** `backend/evidence_review_service.py:258-275` (`find_one_and_update` with `status: "pending"` baked into the filter)
**Apply to:** `questionnaire_answer_review_service.py`'s "mark submitted" transition — filter MUST include `{"status": "approved"}`; a non-matching record fails closed, no exception needed, this is RAG-02's hard guardrail (T3).

### Excel/CSV upload endpoint shape
**Source:** `backend/compliance_framework_mgmt_endpoints.py:215-267`
**Apply to:** `questionnaire_inbound_endpoints.py`'s upload route — `UploadFile = File(...)`, filename-suffix branching, `openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)` for `.xlsx`, `csv.DictReader` for `.csv`, explicit `HTTPException(422, ...)` on `ImportError` for missing `openpyxl`.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `backend/tests/test_rag_service_tenant_isolation.py` | test | integration | No existing test seeds two tenants into the same ChromaDB `PersistentClient` and asserts cross-tenant leakage is zero — this is new ground (RAG tenant-isolation testing does not exist anywhere in the codebase today). Use `30-AI-SPEC.md` Section 6's guardrail description and `30-RESEARCH.md`'s Validation Architecture test map as the design contract instead of a codebase analog; construct the test against the real (or a temp-dir) `rag_service.RagService` instance with two `tenant_id`s, not a MagicMock, since the thing under test is `chromadb`'s own `where` filter behavior. |
| `backend/tests/fixtures/questionnaire_eval_set.json` | fixture | batch | No eval reference dataset exists anywhere in this codebase (this phase is the first to introduce RAGAS/Arize Phoenix eval tooling per AI-SPEC Section 5/RESEARCH). Build directly from AI-SPEC Section 5's "Reference Dataset" composition spec (15 examples: 5 critical-path, 3 optimistic-drift, 2 scope-mismatch, 2 zero-evidence, 1 stale-evidence, 2 cross-tenant adversarial), no in-repo JSON fixture to clone the shape from. |
| `backend/requirements-eval.txt` | config | — | No existing `requirements-*.txt` split file in the repo (only a single `backend/requirements.txt`) — this is a new file/convention, not a modification of an existing pattern. Contents are already fully specified in AI-SPEC Section 5 / RESEARCH's Standard Stack table (`ragas==0.4.3`, `arize-phoenix==17.20.0`, `opentelemetry-sdk==1.43.0`). |

## Metadata

**Analog search scope:** `backend/*.py` (service + endpoint layer), `backend/tests/*.py`, `components/*.tsx`
**Files scanned/read in full or targeted excerpt:** `rag_service.py`, `ai_service.py`, `ai_providers.py`, `evidence_review_service.py`, `evidence_review_endpoints.py`, `questionnaire_service.py`, `questionnaire_endpoints.py`, `compliance_narrative_service.py`, `compliance_framework_mgmt_endpoints.py`, `tests/test_evidence_review.py`, `components/EvidenceReviewPanel.tsx`
**Pattern extraction date:** 2026-07-07
