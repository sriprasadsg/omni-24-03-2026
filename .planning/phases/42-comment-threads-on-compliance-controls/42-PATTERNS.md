# Phase 42: Comment Threads on Compliance Controls - Pattern Map

**Mapped:** 2026-07-21
**Files analyzed:** 8 (3 new backend, 1 modified backend, 2 new frontend, 2 modified frontend)
**Analogs found:** 8 / 8

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|-----------------|---------------|
| `backend/control_comments_service.py` | service | CRUD | `backend/evidence_review_service.py` (+ `database.py` tenant-isolation wrapper) | role-match |
| `backend/control_comments_endpoints.py` | controller/route | request-response | `backend/evidence_review_endpoints.py` (role gate) + `backend/tickets_endpoints.py` (comment shape) | exact (composite) |
| `backend/tests/test_control_comments.py` | test | request-response | `backend/tests/test_evidence_review.py` | exact |
| `backend/router_registry.py` | config | event-driven (app bootstrap) | itself, line 179 insertion point | exact |
| `components/ControlCommentsPanel.tsx` | component | request-response (fetch-on-mount) | `components/ChainOfCustodyPanel.tsx` (structure) + `components/EvidenceReviewPanel.tsx` (role-gate/composer) | role-match (composite) |
| `components/FrameworkDetail.tsx` | component | request-response | itself, line 432 mount point | exact |
| `services/apiService.ts` | service (frontend API client) | request-response | `fetchControlAuditLog` (lines 4564-4572) | exact |

## Pattern Assignments

### `backend/control_comments_service.py` (service, CRUD)

**Analog:** `backend/database.py` (`TenantIsolatedDatabase`/`TenantIsolatedCollection`) + `backend/evidence_review_service.py` shape

**Tenant-isolated collection access — clone verbatim (no manual tenant filter code needed):**
```python
# Source: backend/database.py:105-152 — TenantIsolatedDatabase.__getattr__/__getitem__
# CONFIRMED: "control_comments" is NOT in either exemption list (lines 122-135, 140-152).
# Exempt (global reference data, DO NOT add control_comments here):
#   compliance_frameworks, compliance_controls, ai_governance_frameworks,
#   system_features, tenants, roles, response_policies, playbooks, ip_bans,
#   crypto_inventory
# Everything else (including the new control_comments) is auto-wrapped in
# TenantIsolatedCollection, which injects/filters tenantId on every op.
db = get_database()
await db.control_comments.insert_one({...})   # tenantId auto-injected
await db.control_comments.find({"control_id": control_id}).sort("created_at", 1).to_list(200)
```

**Insert/list pattern (adapted, no `$push`):**
```python
# Pattern source: backend/evidence_review_service.py (get_reviews shape) +
# backend/database.py (TenantIsolatedCollection default path)
async def list_comments(db, control_id: str) -> list[dict]:
    cursor = db.control_comments.find({"control_id": control_id}, {"_id": 0})
    return await cursor.sort("created_at", 1).to_list(length=200)

async def add_comment(db, control_id: str, author: str, text: str) -> dict:
    comment = {
        "id": str(uuid.uuid4()),
        "control_id": control_id,
        "author": author,
        "text": text,
        "created_at": _now_iso(),
    }
    await db.control_comments.insert_one(comment)
    return comment
```

**DO NOT clone:** `backend/tickets_service.py:330-373` `add_comment()` — it does `$push` onto a shared/exempt parent document. Storage mechanism only, not the shape, is the anti-pattern here.

---

### `backend/control_comments_endpoints.py` (controller, request-response)

**Analogs:** `backend/evidence_review_endpoints.py` (role gate, rate limit) + `backend/tickets_endpoints.py` (comment endpoint shape)

**Imports pattern** (source: `backend/evidence_review_endpoints.py` lines 12-32):
```python
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
from rate_limiter import limiter
from control_comments_service import add_comment, list_comments, resolve_mentions
from notification_service import get_notification_service

logger = logging.getLogger(__name__)
router = APIRouter()
```

**Role-gate pattern — clone verbatim** (source: `backend/evidence_review_endpoints.py` lines 37-44, 133-137):
```python
# IN-01-style comment (kept in sync by hand with the frontend literal in
# components/ControlCommentsPanel.tsx). Backend always re-enforces
# authorization server-side regardless of the frontend list.
_COMMENT_AUTHOR_ROLES = {"admin", "super_admin", "compliance_reviewer"}   # D-01

...
if current_user.role not in _COMMENT_AUTHOR_ROLES:
    raise HTTPException(
        status_code=403,
        detail="Only admins and compliance reviewers can comment",
    )
```

**Rate-limit decorator pattern — clone verbatim** (source: `backend/evidence_review_endpoints.py` lines 118-120):
```python
@router.post("/api/control-comments")
@limiter.limit("30/minute")
async def post_control_comment(
    request: Request,
    response: Response,           # REQUIRED — slowapi silently no-ops without this param
    body: CreateCommentRequest,
    current_user: TokenData = Depends(get_current_user),
):
```

**Request model with length bound — clone verbatim** (source: `backend/evidence_review_endpoints.py` lines 55-62):
```python
class CreateCommentRequest(BaseModel):
    control_id: str
    text: str = Field(..., min_length=1, max_length=2000)
```

**Tenant-context guard pattern** (source: `backend/evidence_review_endpoints.py` lines 138-140):
```python
tenant_id = current_user.tenant_id
if not tenant_id:
    raise HTTPException(status_code=400, detail="No tenant context")
```

**Full endpoint pattern to build** (from RESEARCH.md, already synthesized — combines all of the above plus notification dispatch):
```python
@router.post("/api/control-comments")
@limiter.limit("30/minute")
async def post_control_comment(
    request: Request,
    response: Response,
    body: CreateCommentRequest,
    current_user: TokenData = Depends(get_current_user),
):
    if current_user.role not in _COMMENT_AUTHOR_ROLES:
        raise HTTPException(status_code=403, detail="Only admins and compliance reviewers can comment")
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    db = get_database()
    comment = await add_comment(db, body.control_id, author=current_user.username, text=body.text)
    # D-03: no PATCH/DELETE route exists for this resource anywhere — absence IS the enforcement.

    for mention_email in await resolve_mentions(db, body.text):   # NEW logic, see below
        svc = get_notification_service(db)
        try:
            await svc.send_alert(
                title="You were mentioned in a control comment",
                message=f"{current_user.username} mentioned you: \"{body.text[:120]}\"",
                severity="info",
                recipients=[mention_email],
                tenant_id=tenant_id,
                channels=[],   # D-02: in-app only — see notification_service.py note below
                metadata={"control_id": body.control_id, "event": "mention"},
            )
        except Exception:
            pass  # non-fatal, matches tickets_endpoints.py's mention-notification error handling
    return comment


@router.get("/api/control-comments")
async def get_control_comments(
    control_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    # No role gate — matches evidence_review_endpoints.py's GET routes (unrestricted read,
    # only the decision/write route is role-gated). Tenant isolation still applies via db.
    db = get_database()
    return await list_comments(db, control_id)
```

**@mention notification via `get_notification_service(db)` — verified signature** (source: `backend/notification_service.py` lines 26-43):
```python
async def send_alert(
    self,
    title: str,
    message: str,
    severity: str,
    recipients: List[str],
    tenant_id: Optional[str] = None,
    channels: List[str] = None,     # pass [] explicitly, NOT None — None defaults to ["email"] (line 42-43)
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
```
**CRITICAL:** `if not channels: channels = ["email"]` at line 42-43 means passing `channels=None` or omitting it silently defaults to email dispatch. Must pass `channels=[]` explicitly (a non-empty-check-safe empty list) to get in-app-only (only the unconditional `db.notifications.insert_one` side effect fires, no channel dispatch).

**DO NOT clone:** `backend/ticket_notifications.py::_send()` — its `from notification_service import notification_service` import raises `ImportError` (verified live). Use `from notification_service import get_notification_service` + `get_notification_service(db)` factory instead.

**@mention plain-text parsing — new, not a clone** (per D-04 / Pitfall 3, diverges from tickets' email-shaped regex `r'@([\w.+-]+@[\w.+-]+\.[a-z]+)'`):
```python
import re

def extract_mention_tokens(text: str) -> list[str]:
    return re.findall(r'@([\w.-]+)', text)

async def resolve_mentions(db, text: str) -> list[str]:
    """Resolve @token strings to recipient emails. Unresolved tokens are
    silently skipped (never error the whole comment POST)."""
    emails = []
    for token in extract_mention_tokens(text):
        user = await db.users.find_one({"username": token})
        if not user:
            user = await db.users.find_one({"email": {"$regex": f"^{re.escape(token)}@"}})
        if not user:
            user = await db.users.find_one({"name": {"$regex": f"^{re.escape(token)}$", "$options": "i"}})
        if user and user.get("email"):
            emails.append(user["email"])
    return emails
```

---

### `backend/router_registry.py` (config, event-driven/bootstrap)

**Analog:** itself — insertion point next to `evidence_review_endpoints`

**Registration pattern** (source: `backend/router_registry.py` line 179, "Governance & Compliance" group):
```python
    _load(app, "evidence_review_endpoints", "router")
    _load(app, "control_comments_endpoints", "router")   # NEW — add immediately after
```

---

### `backend/tests/test_control_comments.py` (test, request-response)

**Analog:** `backend/tests/test_evidence_review.py` (role-gate test shape, mock-db convention)

Reference test to clone the shape of: `test_non_reviewer_role_forbidden_from_decision` (lines 312-322) — uses `_make_user(role=...)` MagicMock + FastAPI `TestClient` with `dependency_overrides`, asserts `resp.status_code == 403`. Read that test directly when implementing (not excerpted here — RESEARCH.md already cites the exact lines and confirms it as the only usable clone target; `test_tickets.py` has zero comment-specific coverage).

Required test cases (from RESEARCH.md Validation Architecture):
- `test_non_author_role_forbidden` — 403 for non-reviewer role
- `test_post_and_list_comment` — persists and is retrievable
- `test_tenant_isolation` — Tenant A cannot see Tenant B's comments on same `control_id`
- `test_mention_triggers_notification` — `db.notifications` write occurs
- `test_mention_is_in_app_only` — no email/sms/slack channel dispatch (assert `channels=[]` passed / no channel side effects)

---

### `services/apiService.ts` (frontend service, request-response)

**Analog:** `fetchControlAuditLog` (source: `services/apiService.ts` lines 4564-4572)

**Fetch wrapper pattern — clone verbatim structure:**
```typescript
export const fetchControlAuditLog = async (controlId: string): Promise<{ entries: any[] }> => {
    try {
        const res = await authFetch(`${API_BASE}/compliance/controls/${controlId}/audit-log`);
        if (!res.ok) return { entries: [] };
        return await res.json();
    } catch {
        return { entries: [] };
    }
};
```

**New wrappers to add (already synthesized in RESEARCH.md, verified against the above shape):**
```typescript
export const fetchControlComments = async (controlId: string): Promise<any[]> => {
    try {
        const res = await authFetch(`${API_BASE}/control-comments?control_id=${controlId}`);
        if (!res.ok) return [];
        return await res.json();
    } catch {
        return [];
    }
};

export const postControlComment = async (controlId: string, text: string): Promise<any> => {
    const res = await authFetch(`${API_BASE}/control-comments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ control_id: controlId, text }),
    });
    if (!res.ok) throw new Error('Failed to post comment');
    return await res.json();
};
```

---

### `components/ControlCommentsPanel.tsx` (component, request-response / fetch-on-mount)

**Analogs:** `components/ChainOfCustodyPanel.tsx` (structure) + `components/EvidenceReviewPanel.tsx` (role-gate/composer)

**Imports pattern** (source: `components/ChainOfCustodyPanel.tsx` lines 1-3 — per UI-SPEC, use local `./icons` module not `lucide-react`, matching the adjacent panel):
```typescript
import React, { useState, useEffect } from 'react';
import { MessageSquareIcon, SendIcon, ClockIcon, ChevronDownIcon } from './icons';
import * as api from '../services/apiService';
```

**Timestamp formatting — clone verbatim** (source: `components/ChainOfCustodyPanel.tsx` lines 14-26):
```typescript
function formatTimestamp(ts: string): string {
    try {
        return new Date(ts).toLocaleString('en-US', {
            timeZone: 'UTC',
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch {
        return ts;
    }
}
```

**Panel structure to mirror — NOTE: unlike CoC's click-to-expand-then-fetch, this panel fetches on mount** (source structure: `components/ChainOfCustodyPanel.tsx` lines 29-49, adapted per RESEARCH.md Pattern 4 / UI-SPEC interaction note):
```typescript
interface ControlCommentsPanelProps {
    controlId: string;
}

export const ControlCommentsPanel: React.FC<ControlCommentsPanelProps> = ({ controlId }) => {
    const [comments, setComments] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [text, setText] = useState('');
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            setLoading(true);
            setError(null);
            try {
                const data = await api.fetchControlComments(controlId);
                if (!cancelled) setComments(data);
            } catch {
                if (!cancelled) setError('Failed to load comments. Retry by collapsing and expanding this panel.');
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => { cancelled = true; };
    }, [controlId]);

    // ... composer + submit handler below
};
```

**Role-gate mirror — clone verbatim comment convention + literal** (source: `components/EvidenceReviewPanel.tsx` lines 8-15):
```typescript
// Kept in sync by hand with backend/control_comments_endpoints.py's
// _COMMENT_AUTHOR_ROLES. Backend always re-enforces authorization
// server-side regardless of this list, so drift here is a UI-confusion
// risk (composer visibility), not an authz bypass.
const _REVIEWER_ROLES = ['admin', 'super_admin', 'compliance_reviewer'];
const isReviewer = currentUser && _REVIEWER_ROLES.includes(currentUser.role);

// Per UI-SPEC: composer hidden entirely for non-reviewers, no disabled
// input / no placeholder helper text — matches EvidenceReviewPanel.tsx's
// `{isReviewer && ... && (...)}` whole-block conditional render pattern.
{isReviewer && (
  <form onSubmit={handleSubmit}>...</form>
)}
```

**Submit-state label pattern** (source: `components/EvidenceReviewPanel.tsx` "Submitting..."/"Saving..." in-flight convention — apply as `Posting...` per UI-SPEC copy contract):
```typescript
<button type="submit" disabled={submitting}>
    {submitting ? 'Posting...' : 'Post Comment'}
</button>
```

**Safe @mention text rendering — hard constraint from RESEARCH.md Security Domain + UI-SPEC Component Notes:**
```typescript
// NEVER use dangerouslySetInnerHTML. Split on mention tokens and wrap in a span.
function renderCommentText(text: string) {
    const parts = text.split(/(@[\w.-]+)/g);
    return parts.map((part, i) =>
        /^@[\w.-]+$/.test(part)
            ? <span key={i} className="text-blue-600 dark:text-blue-400 font-medium">{part}</span>
            : <React.Fragment key={i}>{part}</React.Fragment>
    );
}
```

---

### `components/FrameworkDetail.tsx` (component, modified — mount point)

**Analog:** itself, line 432 (exact existing mount pattern for `ChainOfCustodyPanel`)

**Existing mount pattern to extend** (source: `components/FrameworkDetail.tsx` line 432):
```typescript
{canViewCoC && <ChainOfCustodyPanel controlId={control.id} />}
```

**New mount to add immediately after (no conditional — comment thread is visible to all authenticated tenant users per RESEARCH.md Assumption A2; composer visibility is gated inside the panel itself):**
```typescript
{canViewCoC && <ChainOfCustodyPanel controlId={control.id} />}
<ControlCommentsPanel controlId={control.id} />
```
Also add the import near the top of the file alongside the existing `ChainOfCustodyPanel` import.

**Toast-copy convention to reuse for post-error/success** (source: `components/FrameworkDetail.tsx` `onDeleteEvidence` handler pattern, `showToast("Failed to delete evidence.", 'error')` / `showToast('Evidence deleted.', 'success')`):
```typescript
showToast('Comment posted.', 'success');
showToast('Failed to post comment — please try again.', 'error');
```

---

## Shared Patterns

### Tenant isolation (database tier)
**Source:** `backend/database.py` lines 105-152
**Apply to:** `control_comments_service.py` — do NOT add `control_comments` to the exemption lists at lines 122-135/140-152. All reads/writes automatically get tenantId injection/filtering via `TenantIsolatedCollection`.

### Role gate (backend authoritative, frontend UX mirror)
**Source:** `backend/evidence_review_endpoints.py` lines 37-44 (backend) + `components/EvidenceReviewPanel.tsx` lines 8-15 (frontend)
**Apply to:** `control_comments_endpoints.py` POST handler (backend, authoritative) and `ControlCommentsPanel.tsx` composer visibility (frontend, UX-only). Literal role array `['admin', 'super_admin', 'compliance_reviewer']` must be manually duplicated in both places with the "kept in sync by hand" comment — no shared constants module exists.

### Rate limiting
**Source:** `backend/evidence_review_endpoints.py` lines 118-120
**Apply to:** `control_comments_endpoints.py`'s POST route. `@limiter.limit("30/minute")` requires a `response: Response` parameter on the handler or the rate limiter silently no-ops (documented pitfall in this codebase).

### In-app-only notification dispatch
**Source:** `backend/notification_service.py` lines 26-56 (`send_alert`), factory via `get_notification_service(db)`
**Apply to:** `control_comments_endpoints.py`'s mention-notification dispatch. Pass `channels=[]` explicitly (not `None`) to avoid the `["email"]` default at line 42-43.

### Append-only enforcement by omission
**Source:** `backend/evidence_coc.py` (chain-of-custody precedent) — pure convention, no DB-level enforcement, no PATCH/DELETE route ever written
**Apply to:** `control_comments_endpoints.py` — do not build any PATCH/DELETE route, even a stubbed one (D-03).

## No Analog Found

None — every file in this phase has a direct, high-confidence analog already identified in RESEARCH.md and confirmed by direct source reads above.

## Metadata

**Analog search scope:** `backend/evidence_review_endpoints.py`, `backend/evidence_review_service.py`, `backend/tickets_endpoints.py`, `backend/tickets_service.py`, `backend/notification_service.py`, `backend/database.py`, `backend/router_registry.py`, `backend/tests/test_evidence_review.py`, `components/ChainOfCustodyPanel.tsx`, `components/EvidenceReviewPanel.tsx`, `components/FrameworkDetail.tsx`, `services/apiService.ts`
**Files scanned:** 12 (all directly read in this session; RESEARCH.md's citations independently verified against live source)
**Pattern extraction date:** 2026-07-21
</content>
