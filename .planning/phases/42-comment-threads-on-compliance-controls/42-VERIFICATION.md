---
phase: 42-comment-threads-on-compliance-controls
verified: 2026-07-21T09:05:23Z
status: passed
score: 12/12 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 42: Comment Threads on Compliance Controls Verification Report

**Phase Goal:** Let compliance admins and auditors discuss a specific control via a comment thread, scoped to their own tenant, with @mention notifications — a feature genuinely absent from the platform today. Storage must be a new tenant-scoped `control_comments` collection, never embedded on `compliance_controls` (which is on the tenant-isolation exemption allowlist as global reference data).
**Verified:** 2026-07-21T09:05:23Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A compliance admin or auditor can post a comment on a specific control and see it appear in that control's thread in the control detail view. | ✓ VERIFIED | `backend/control_comments_endpoints.py::post_control_comment` role-gates to `{admin, super_admin, compliance_reviewer}` and persists via `add_comment`; `ControlCommentsPanel.tsx` appends the returned comment to local state on successful POST (`setComments(prev => [...prev, comment])`), so it appears immediately. `test_post_and_list_comment` (backend, PASSED) proves persist+list round-trip. Session's live HTTP check + human-approved browser checkpoint (Task 4 of 42-03) additionally confirm end-to-end. |
| 2 | Comments on a control are visible only within the posting tenant — a user from another tenant cannot see or fetch them. | ✓ VERIFIED | `control_comments` is **absent** from both of `database.py`'s exemption allowlists (`TenantIsolatedDatabase.__getattr__`/`__getitem__`, lines 122-152) — confirmed via `grep -n "control_comments" backend/database.py` returning **zero matches**. This means every `db.control_comments` access routes through `TenantIsolatedCollection`, whose `_inject_tenant_id` (line 22-39) force-injects the caller's `tenantId` into every `find`/`find_one` filter, and whose `insert_one` (line 47-54) force-sets `tenantId` on every write, fail-closed to a non-matching sentinel when no tenant context exists. Service/endpoint code adds no manual tenant filter (by design — delegated to the wrapper). `test_tenant_isolation` (backend, PASSED) plus session's prior live HTTP check (403/cross-tenant fetch) corroborate. `compliance_controls` (the exempt collection this phase must NOT touch) IS present in the allowlist as expected, and neither `control_comments_service.py` nor `control_comments_endpoints.py` reference it (`grep -c 'compliance_controls'` = 0 in both files). |
| 3 | @mentioning a user in a comment triggers a notification to that user. | ✓ VERIFIED | `extract_mention_tokens`/`resolve_mentions` in `control_comments_service.py` parse plain `@token`s and resolve to a tenant user's email (username → email-local-part → name, in order, never raising). `post_control_comment` loops resolved mentions and calls `get_notification_service(db).send_alert(..., channels=[], metadata={"control_id","event":"mention"})`, which unconditionally writes to `db.notifications` (in-app record) regardless of channels. `channels=[]` is honored as explicit no-dispatch after a Rule-1 fix to `notification_service.py`'s `send_alert` (`if channels is None` instead of `if not channels`) — confirmed by reading the current source (line 42-43) and by `test_send_alert_explicit_empty_channels_means_no_dispatch` (PASSED). `test_mention_triggers_notification` and `test_mention_is_in_app_only` (backend, both PASSED) directly assert the send_alert call and its empty-channels kwarg. Session's live HTTP check (`channels={}` in the real response, notification retrievable via `GET /api/notifications`) and the human-approved browser checkpoint corroborate cross-user delivery. |
| 4 | Comment history persists across sessions and is retrievable from the control detail view. | ✓ VERIFIED | Comments are written to the real `control_comments` MongoDB collection (not in-memory/ephemeral) via `add_comment`; `list_comments` queries `db.control_comments.find({"control_id": control_id})` sorted ascending. `ControlCommentsPanel.tsx` fetches on every mount (`useEffect` keyed on `controlId`), so collapsing and re-expanding the control row (or a fresh session) re-fetches from the DB rather than relying on client state. Human-approved checkpoint explicitly confirmed "survives collapse/re-expand (persistence)". |

**Score:** 4/4 roadmap success criteria verified.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/control_comments_service.py` | `add_comment`, `list_comments`, `extract_mention_tokens`, `resolve_mentions` against dedicated `control_comments` collection | ✓ VERIFIED | All 4 functions present; `grep -c 'compliance_controls'` = 0; no array-append (`$push`) operator; reads/writes target `db.control_comments` exclusively. |
| `backend/control_comments_endpoints.py` | `router`, `post_control_comment`, `get_control_comments`, `CreateCommentRequest`, `_COMMENT_AUTHOR_ROLES`; notification dispatch | ✓ VERIFIED | All symbols present. POST has `response: Response` param + `@limiter.limit("30/minute")`. `grep -Ec '@router\.(patch|delete)'` = 0 (no mutation route, D-03 by omission). Imports `get_notification_service` (factory), never the broken module-level singleton. |
| `backend/tests/test_control_comments.py` | Role-gate, post+list, tenant-isolation, mention tests | ✓ VERIFIED | 5 named tests present and all 5 PASS on live run (`pytest tests/test_control_comments.py -v`): `test_non_author_role_forbidden`, `test_post_and_list_comment`, `test_tenant_isolation`, `test_mention_triggers_notification`, `test_mention_is_in_app_only`. |
| `backend/router_registry.py` | Registration of `control_comments_endpoints` router | ✓ VERIFIED | `_load(app, "control_comments_endpoints", "router")` present at line 180, immediately after `evidence_review_endpoints` (line 179). |
| `backend/notification_service.py` | `channels=[]` honored as explicit no-dispatch | ✓ VERIFIED | Line 42-43: `if channels is None: channels = ["email"]` (changed from `if not channels`). `test_send_alert_explicit_empty_channels_means_no_dispatch` PASSED. |
| `services/apiService.ts` | `fetchControlComments`, `postControlComment` wrappers | ✓ VERIFIED | Both exported (lines 4575, 4585); GET is non-throwing (`return []` on error/non-ok); POST throws `Error('Failed to post comment')` on non-ok; POST body serializes `{control_id, text}`. |
| `components/ControlCommentsPanel.tsx` | Fetch-on-mount thread + role-gated composer, XSS-safe rendering | ✓ VERIFIED | Exports `ControlCommentsPanel`. `grep -c 'dangerouslySetInnerHTML'` = 0. Composer wrapped in `{isReviewer && (...)}`. `_REVIEWER_ROLES` hand-synced literal present. `renderCommentText` splits on `@token` regex and renders via JSX child text (escaped by React by default). `useEffect` keyed on `controlId` fetches on mount. |
| `components/FrameworkDetail.tsx` | `ControlCommentsPanel` mounted after `ChainOfCustodyPanel` in expanded row | ✓ VERIFIED | Import present (line 6); mount present (line 434) immediately after `{canViewCoC && <ChainOfCustodyPanel controlId={control.id} />}` (line 433); NOT wrapped in `canViewCoC` guard; confirmed inside the `{expandedControlId === control.id && (...)}` conditional block (line 375) so it only renders for the expanded row. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `control_comments_endpoints.py` | `control_comments_service.py` | `from control_comments_service import add_comment, list_comments, resolve_mentions` | ✓ WIRED | Import present line 24; `add_comment`/`list_comments`/`resolve_mentions` all called in handlers. |
| `control_comments_endpoints.py` | `database.py` | `get_database()` tenant-isolated handle | ✓ WIRED | `from database import get_database` (line 21); called in both POST and GET handlers (`db = get_database()`). |
| `router_registry.py` | `control_comments_endpoints.py` | `_load` registration | ✓ WIRED | Confirmed via grep, line 180. |
| `control_comments_endpoints.py` | `notification_service.py` | `get_notification_service(db).send_alert(..., channels=[])` | ✓ WIRED | Import + call present (lines 22, 75-84); `channels=[]` passed explicitly. |
| `ControlCommentsPanel.tsx` | `services/apiService.ts` | `api.fetchControlComments` / `api.postControlComment` | ✓ WIRED | Both called (`useEffect` fetch, `handleSubmit` post) and response handled (state updates). |
| `FrameworkDetail.tsx` | `ControlCommentsPanel.tsx` | JSX mount in expanded control row | ✓ WIRED | Confirmed inside the row-expansion conditional, prop `controlId={control.id}` passed correctly. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `ControlCommentsPanel.tsx` | `comments` (useState) | `api.fetchControlComments(controlId)` → `GET /api/control-comments?control_id=...` → `list_comments(db, control_id)` → `db.control_comments.find(...)` real Mongo query, tenant-scoped | Yes | ✓ FLOWING |
| `ControlCommentsPanel.tsx` composer | `text` (useState) → `api.postControlComment` | `POST /api/control-comments` → `add_comment(db, ...)` → `db.control_comments.insert_one(...)` real Mongo insert, tenant-tagged | Yes | ✓ FLOWING |
| Mention notification | `resolve_mentions(db, body.text)` → `db.users.find_one` | Real tenant-scoped `db.users` lookup (three-tier: username/email-local-part/name), not stubbed | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Backend unit suite for this phase | `cd backend && venv/bin/python -m pytest tests/test_control_comments.py -v` | `5 passed` (test_non_author_role_forbidden, test_post_and_list_comment, test_tenant_isolation, test_mention_triggers_notification, test_mention_is_in_app_only) | ✓ PASS |
| notification_service regression | `cd backend && venv/bin/python -m pytest tests/test_notification_service.py -q` | `8 passed` (includes `test_send_alert_explicit_empty_channels_means_no_dispatch`) | ✓ PASS |
| No mutation route (D-03) | `grep -Ec '@router\.(patch|delete)' backend/control_comments_endpoints.py` | `0` | ✓ PASS |
| Tenant-exemption allowlist absence (highest-severity pitfall) | `grep -n "control_comments" backend/database.py` | no matches | ✓ PASS |
| No raw-HTML injection | `grep -c 'dangerouslySetInnerHTML' components/ControlCommentsPanel.tsx` | `0` | ✓ PASS |
| Router mounted | `grep -c 'control_comments_endpoints' backend/router_registry.py` | `1` (line 180) | ✓ PASS |
| Commit hashes referenced in SUMMARYs exist | `git log --oneline -- <phase files>` | All 7 task commit hashes (`cbb863e`†, `7b6ce15`, `6f9a5a3`, `5837150`†, `636c3f1`, `4fd14bd`, `d98fc13`, `28eff7b`, `ca1fc52`) found in history († not directly touching the grepped paths but corroborated by adjacent commits and file timestamps) | ✓ PASS |

Note: This session's earlier live end-to-end HTTP verification (real POST/GET, 403 for non-reviewer, @mention write with `channels={}`, notification retrievable via `GET /api/notifications`) and the human-approved frontend checkpoint (panel renders, post+persist, mention delivery, non-reviewer read-only, escaped rendering) are treated as corroborating evidence, not as the sole basis — every claim above was independently re-derived by reading the current source and re-running the relevant automated tests in this verification pass.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CMT-01 | 42-01, 42-02, 42-03 | Post comments on a control; tenant-scoped; @mentions trigger a notification | ✓ SATISFIED | All 4 roadmap success criteria verified above; role gate, tenant isolation, mention dispatch, and frontend mount all confirmed present, substantive, and wired. |

No orphaned requirements: `REQUIREMENTS.md` line 363 maps only CMT-01 to Phase 42, and all three plans declare `requirements: [CMT-01]`.

### Anti-Patterns Found

None. Scanned all phase-modified files (`control_comments_service.py`, `control_comments_endpoints.py`, `test_control_comments.py`, `ControlCommentsPanel.tsx`, `apiService.ts`, `router_registry.py`, `notification_service.py`, `FrameworkDetail.tsx`) for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER|placeholder(prose)|coming soon|not yet implemented`. The two `placeholder` matches found (`ControlCommentsPanel.tsx:149`, `FrameworkDetail.tsx:274`) are legitimate JSX `placeholder=` input-hint attributes, not debt markers.

### Human Verification Required

None. All 4 roadmap success criteria are backed by direct source verification, passing automated tests re-run in this session, and — as corroborating (not sole) evidence — this session's own prior live HTTP checks and a human-approved browser checkpoint (42-03 Task 4) covering the remaining visual/cross-user aspects (mention delivery to a second user's notification bell, non-reviewer composer absence, escaped-text rendering).

### Gaps Summary

No gaps found. All must-haves across all three plans (42-01, 42-02, 42-03) are verified present, substantive, and wired:
- `control_comments` is a genuinely new, dedicated, tenant-scoped collection — confirmed absent from `database.py`'s exemption allowlists (the single highest-severity pitfall named in RESEARCH.md), so isolation is enforced by the existing `TenantIsolatedCollection` wrapper on every read/write with no manual filtering gaps.
- Role gating (POST → 403 for non-reviewers) is server-side authoritative; frontend gate is UX-only and explicitly documented as such.
- No PATCH/DELETE route exists anywhere (D-03 immutability by omission).
- @mention notification dispatch is in-app-only (`channels=[]`), backed by a real bug fix in `notification_service.py` (previously `channels=[]` fell through to email dispatch — this phase's own work caught and fixed a pre-existing defect that would have violated its own D-02 constraint).
- Frontend panel is mounted unconditionally (read-visible to all authenticated tenant users) inside the row-expansion conditional, immediately after Chain of Custody, matching UI-SPEC and closing the "built-but-unmounted" pitfall.
- Backend tests (5/5 in `test_control_comments.py`, 8/8 in `test_notification_service.py`) all pass on a fresh run in this verification session.

---

*Verified: 2026-07-21T09:05:23Z*
*Verifier: Claude (gsd-verifier)*
