---
phase: "04"
fixed_at: 2026-07-02T18:23:44Z
review_path: .planning/phases/04-remediation-workflow/04-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 0
skipped: 8
status: none_fixed
---

# Phase 04: Code Review Fix Report

**Fixed at:** 2026-07-02T18:23:44Z
**Source review:** .planning/phases/04-remediation-workflow/04-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 8 (4 Critical, 4 Warning — the 2 Info findings are out of scope for this pass)
- Fixed (new commits this pass): 0
- Skipped: 8 — but see note below: all 8 are **already resolved** by prior, unrelated commits. None require action.

**Important note:** REVIEW.md was generated 2026-06-18, one of the earliest reviews in the
project. The codebase has moved on significantly since then. Re-verification against the
current file contents (inside a fresh isolated worktree) found that every in-scope finding's
root cause was already fixed by later commits — most explicitly, by a dedicated cleanup commit
made the same day as the review. No source edits were made in this pass because there was
nothing left to fix. This report exists to close the loop on REVIEW.md rather than to record
new changes.

## Fixed Issues

None — no new fixes were applied this pass (all in-scope findings were already resolved by
prior commits; see "Skipped Issues" below for details and provenance).

## Skipped Issues

All entries below are skipped in the sense that no *new* commit was made in this pass — each
finding's underlying defect no longer exists in the current code. This is a "pre-resolved"
skip, not a "could not fix" skip.

### CR-01: AI suggestion persist bypasses tenant scope — cross-tenant write

**File:** `backend/compliance_remediation_endpoints.py:164-167`
**Reason:** Already fixed. Current code reads:
```python
await db.compliance_remediation_tasks.update_one(
    {"id": task_id, **tf},
    {"$set": {"ai_suggestion": text}},
)
```
This matches the REVIEW.md fix suggestion exactly and carries an inline `# CR-01` comment.
**Resolved by:** commit `9d60a15` — `fix(04-cr): tenant-scope AI suggestion persist (CR-01); ...`
**Original issue:** Persist write used only `{"id": task_id}` without a tenant filter.

### CR-02: `agent_id` in `dispatch_rescan` is not validated — arbitrary agent targeting

**File:** `backend/compliance_remediation_service.py:30-42, 122-141`
**Reason:** Already fixed, via a different (equally valid) mechanism than REVIEW.md's suggested
patch. Rather than validating a user-submitted `agent_id` at dispatch time, `create_task` no
longer accepts `agent_id` from user input at all — `TaskCreate` has no `agent_id` field, and
`agent_id` is derived exclusively from a tenant-scoped `db.assets.find_one({"id": asset_id,
**tenant_filter})` lookup (lines 36-42, carrying an inline `# CR-02/WR-03` comment). Since the
stored `agent_id` can never originate from attacker-controlled input, `dispatch_rescan`
consuming `task.get("agent_id")` is safe by construction.
**Resolved by:** commit `9d60a15` — same commit as CR-01/CR-03.
**Original issue:** `agent_id` sourced from unverified user-submitted `data.get("agent_id", "")`.

### CR-03: `dispatch_rescan` inserts `agent_instructions` without `tenantId`

**File:** `backend/compliance_remediation_service.py:143-153`
**Reason:** Already fixed. The instruction document now includes
`"tenantId": task.get("tenantId", "")` with an inline `# CR-03: required by agent polling query`
comment, matching the REVIEW.md fix exactly.
**Resolved by:** commit `9d60a15`.
**Original issue:** Missing `tenantId` broke the tenant-scoped poll query in
`agent_tasks_endpoints.py`.

### CR-04: Hooks called after conditional early return — violates React Rules of Hooks

**File:** `components/RemediationTaskModal.tsx:26-64`
**Reason:** Already fixed. All `useState`/`useEffect` hooks are now declared before the
`if (!isOpen) return null;` guard (which is now at line 64, after every hook), with an inline
`// CR-04: all hooks must be called unconditionally before any early return` comment.
**Resolved by:** commit `9d60a15`.
**Original issue:** Early return preceded hook declarations, causing "Rendered fewer hooks than
expected" crashes.

### WR-01: `_tenant_filter` returns empty dict `{}` for users missing `tenantId`

**File:** `backend/compliance_remediation_endpoints.py:34-41`
**Reason:** Already fixed. Current code raises `HTTPException(status_code=403, detail="Tenant
context required")` when tenant is absent for a non-super-admin user, matching the REVIEW.md
fail-closed fix suggestion (adapted to use `getattr` since `current_user` is a `TokenData`
object, not a dict, in the current codebase).
**Resolved by:** commit `8bda523` — `fix(05-00): GAP-1 — _tenant_filter and created_by use
getattr on TokenData` (landed to fix an unrelated `AttributeError` bug, but the resulting
`_tenant_filter` body independently satisfies the WR-01 fail-closed requirement).
**Original issue:** Empty filter for users missing `tenantId` would remove all tenant scoping.

### WR-02: `status` and `priority` fields accept arbitrary strings — no enum validation

**File:** `backend/compliance_remediation_endpoints.py:57, 61`
**Reason:** Already fixed. `TaskCreate.priority` is now
`Literal["low", "medium", "high", "critical"]` and `TaskUpdate.status` is now
`Optional[Literal["open", "in_progress", "resolved"]]`, matching the REVIEW.md fix intent (the
`TaskUpdate` literal set omits `"dismissed"` relative to REVIEW.md's suggested snippet, but this
is a scope/enum-completeness nuance, not the arbitrary-string defect the finding described — the
core defect, unconstrained strings being persisted, is resolved).
**Resolved by:** commit `e52393a7` (`feat(phase-16): implement program control grouping`) —
landed as part of unrelated feature work.
**Original issue:** Plain `str` fields allowed arbitrary values like `status="hacked"`.

### WR-03: Asset lookup in `create_task` and `dispatch_rescan` is not tenant-scoped

**File:** `backend/compliance_remediation_service.py:36-42, 126-138`
**Reason:** Already fixed. `create_task`'s asset lookup is
`db.assets.find_one({"id": asset_id, **tenant_filter})`; `dispatch_rescan`'s lookup conditionally
adds `asset_filter["tenantId"] = tenant_id` (inline `# WR-03: tenant-scope asset lookup`
comment), matching the REVIEW.md fix.
**Resolved by:** commit `9d60a15`.
**Original issue:** Unscoped `find_one({"id": asset_id})` allowed cross-tenant asset/agent
resolution.

### WR-04: `handleMarkResolved` in `RemediationDashboard` has no error feedback to the user

**File:** `components/RemediationDashboard.tsx:60-69`
**Reason:** Already fixed. The `catch` block now calls
`showToast('Failed to update task — please try again', 'error')` in addition to
`console.error`, giving the user visible feedback on failure — functionally equivalent to the
REVIEW.md fix suggestion (a shared `showToast` utility is used instead of local `useState`
error text, which is consistent with the toast pattern used elsewhere in this component, e.g.
`fetchTasks`'s error handling).
**Resolved by:** commit `9d60a15`.
**Original issue:** Failures were only logged to console with no UI feedback.

## Out of Scope (Not Evaluated)

Per `fix_scope: critical_warning`, the 2 Info findings (IN-01, IN-02) were explicitly excluded
from this pass and were not evaluated or touched.

---

_Fixed: 2026-07-02T18:23:44Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
