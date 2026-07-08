# Phase 15 — Evidence Review Workflow

## Context

Currently, evidence is uploaded and displayed but has no formal review lifecycle. Closing the gap vs Comp AI and OpenLane Core which both support evidence review with comments before it counts toward compliance score.

**Review lifecycle:**
```
Uploaded → [submit for review] → pending_review
  → [reviewer approves]     → approved   (counts toward score)
  → [reviewer rejects]      → rejected
  → [reviewer requests edits] → needs_revision → [uploader resubmits] → pending_review
```

## Architecture

- **`evidence_reviews` collection** stores review records (thread)
- **`asset_compliance.evidence[].status`** field tracks current review state on each evidence record
- **Role-gated**: `admin`, `super_admin`, `compliance_reviewer` can review; any user can submit
- **Evidence `status` values**: `undefined` (legacy/no review needed), `pending_review`, `approved`, `rejected`, `needs_revision`

## Files

### 1. `backend/evidence_review_service.py` (NEW)
Service layer, ~200 lines:
- `_generate_id()` — `rev-{uuid4 hex}`
- `_now_iso()` — datetime helper
- `submit_for_review(evidence_id, db, tenant_id)` — sets `asset_compliance.evidence.$.status = "pending_review"` via positional `$` operator on `evidence.id`
- `create_review(evidence_id, reviewer, comment, db, tenant_id)` — inserts into `evidence_reviews`
- `update_review_decision(review_id, decision, comment, db)` — updates review status + sets evidence status via positional `$`:
  - approved → `evidence.$.status = "approved"` + `updated_at`
  - rejected → `evidence.$.status = "rejected"` + `updated_at`
  - changes_requested → `evidence.$.status = "needs_revision"` + `updated_at`
- `get_reviews(evidence_id, db, tenant_id)` — returns reviews sorted `created_at` desc
- `get_pending_evidence(db, tenant_id)` — aggregation: `$unwind evidence`, `$match {"evidence.status": "pending_review"}`, `$project`
- `submit_requires_comment(decision)` — returns True for rejected/changes_requested

### 2. `backend/evidence_review_endpoints.py` (NEW)
FastAPI router at `/api/evidence`, ~150 lines:
- `POST /api/evidence/{evidence_id}/submit-for-review` — sets `pending_review`, returns `{"success": true}`
- `POST /api/evidence/{evidence_id}/review` — creates review record (requires `comment`), sets review status to `pending`
- `PATCH /api/evidence/{evidence_id}/review/{review_id}` — updates decision; `comment` required for reject/changes_requested; validates decision enum
- `GET /api/evidence/{evidence_id}/reviews` — returns review thread
- `GET /api/evidence/pending-review` — returns all pending-review evidence + associated asset info

Auth: `get_current_user` for all endpoints, role check in review decision endpoints.

Schema for `evidence_reviews`:
```json
{
  "id": "rev-{uuid4hex}",
  "tenantId": "...",
  "evidenceId": "...",
  "reviewer": "...",
  "status": "pending|approved|rejected|changes_requested",
  "comment": "...",
  "created_at": "ISO datetime",
  "updated_at": "ISO datetime"
}
```

### 3. `backend/tests/test_evidence_review.py` (NEW)
8 TDD tests (~200 lines):
1. `test_submit_for_review_sets_status` — POST submit-for-review → evidence.status = pending_review
2. `test_create_review_record` — POST review → review inserted in evidence_reviews
3. `test_approve_evidence_updates_status` — PATCH approved → evidence.status = approved
4. `test_reject_requires_comment` — reject without comment → 422
5. `test_changes_requested_sets_needs_revision` — changes_requested → evidence.status = needs_revision
6. `test_get_reviews_sorted_by_date` — GET reviews → sorted desc by created_at
7. `test_get_pending_returns_only_pending_review` — GET pending-review → only pending items
8. `test_tenant_isolation` — tenant-a cannot see tenant-b's reviews

Uses `asyncio.run()` pattern (consistent with `test_powershell_evidence.py`).

### 4. `backend/router_registry.py` (MODIFY)
Add `_load(app, "evidence_review_endpoints", "router")` in Compliance & Governance section, after `powershell_evidence_endpoints` (line 143).

### 5. `components/EvidenceReviewPanel.tsx` (NEW)
Collapsible panel (~250 lines), displays within `AssetComplianceList` evidence row:
- **Submit for Review button** — shown when evidence.status is undefined/needs_revision; shown to any authenticated user
- **Review thread** — list of past reviews, each showing: reviewer name, decision badge (colored), comment, timestamp
- **Action buttons** (role-gated: admin/super_admin/compliance_reviewer):
  - **Approve** (green) — PATCH decision=approved
  - **Reject** (red) — shows comment textarea, requires comment
  - **Request Changes** (amber) — shows comment textarea, requires comment
- **Status badges**: pending_review=amber, approved=green, rejected=red, needs_revision=amber striped
- **Loading/error/empty states**: skeleton on pending, toast on error, empty message if no reviews

Reuses existing `showToast` and `authFetch` patterns. Uses `useEffect` + `useState` for data fetching.

### 6. `types.ts` (MODIFY)
Extend `AssetComplianceEvidence` interface:
```typescript
export interface AssetComplianceEvidence {
  id: string;
  name: string;
  url: string;
  date: string;
  status?: 'pending_review' | 'approved' | 'rejected' | 'needs_revision';  // NEW
}
```

## Verification

1. `cd backend && python -m pytest tests/test_evidence_review.py -v` — all 8 pass
2. `npx tsc --noEmit` — no TypeScript errors in modified/new frontend files
3. Manual: submit evidence → submit-for-review → approve → verify status badge updates
