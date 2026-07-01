---
phase: 15-evidence-review-workflow
audited: 2026-07-02T00:00:00Z
mode: retroactive-stride
asvs_level: 1
block_on: high
threats_total: 12
threats_closed: 9
threats_open: 0
threats_open_nonblocking: 3
status: secured_with_nonblocking_gaps
---

# Phase 15: Evidence Review Workflow — Security Audit

**Mode:** Retroactive STRIDE. PLAN.md (`.planning/phases/15-evidence-review-workflow/15-01-PLAN.md`) was authored without a `<threat_model>` block, so this register was built directly from the implemented code (`backend/evidence_review_service.py`, `backend/evidence_review_endpoints.py`, `components/EvidenceReviewPanel.tsx`, `components/AssetComplianceList.tsx`, `backend/router_registry.py`, `backend/tests/test_evidence_review.py`), then cross-checked against `15-REVIEW.md` (found CR-01, WR-01..05) and `15-REVIEW-FIX.md` (claimed fixes) to confirm the fixes actually landed in code rather than trusting the fix report's prose.

Verification depth: ASVS L1 (grep/read-level — mitigation must be present in the cited file). Several items were additionally traced to the actual DB-query filter or JWT-decode boundary rather than stopping at "a check exists somewhere," since a surface grep match is insufficient for auth/tenancy claims even at L1.

`pytest backend/tests/test_evidence_review.py` re-run live during this audit: **8 passed** (confirms the SUMMARY.md claim and the REVIEW-FIX.md mock-repair commit `baf484e`).

## Threat Register

| ID | STRIDE Category | Severity | Disposition | Status | Evidence |
|----|------|----------|--------------|--------|----------|
| T-01 | Tampering / Elevation of Privilege | Critical | mitigate | **CLOSED** | Cross-tenant IDOR (review-review REVIEW.md CR-01). `evidence_review_service.py:150-151` — `find_one_and_update({"id": review_id, "tenantId": tenant_id}, ...)`; `:167-168` — `asset_compliance.update_one({"evidence.id": evidence_id, "tenantId": tenant_id}, ...)`. `evidence_review_endpoints.py:112-114,124` — `current_user.tenant_id` resolved from JWT and forwarded to the service call (400 if absent). Verified `update_review_decision` is the only function in the module that ever lacked tenant scoping and confirmed all 5 service functions now filter by `tenantId` (grep: 14 references). |
| T-02 | Spoofing | High | mitigate | **CLOSED** | Frontend auth-header gap (REVIEW.md WR-01). `EvidenceReviewPanel.tsx:4` imports `authFetch`; all 4 network calls (`:53` fetchReviews, `:69` handleSubmitForReview, `:89` create-review POST, `:96` decision PATCH) use `authFetch(...)`. Confirmed zero raw `fetch(` calls remain in the file (grep). `authFetch` (`services/apiService.ts:198-247`) attaches `Authorization: Bearer <token>` and retries once on 401. |
| T-03 | Elevation of Privilege | High | mitigate | **CLOSED** | Review-decision endpoint role gate. `evidence_review_endpoints.py:35` (`_REVIEWER_ROLES = {"admin","super_admin","compliance_reviewer"}`), `:106-110` (403 if `current_user.role not in _REVIEWER_ROLES`). Role is sourced server-side from the signed JWT payload (`authentication_service.py:106-113`, `payload.get("role", "user")`), not from client-supplied request body — frontend's `isReviewer` check (`EvidenceReviewPanel.tsx:42`) is UX-only and cannot be used to bypass the server check. |
| T-04 | Tampering | Medium | mitigate | **CLOSED** | evidence_id/review_id decoupling (REVIEW.md WR-03). `evidence_review_endpoints.py:129-133` — 404 returned if `review.get("evidenceId") != evidence_id` after lookup. |
| T-05 | Tampering | Medium | mitigate | **CLOSED** | Missing lifecycle-state guards / orphaned review records (REVIEW.md WR-04). `evidence_review_service.py:44-49` (`_submittable_statuses` = `[None, "needs_revision", "rejected"]`), `:64-81` (`$elemMatch` guard restricts `submit_for_review` transitions), `:96-100` (`create_review` requires evidence to exist for `tenant_id`, raises `ValueError` → mapped to HTTP 404 at `endpoints.py:90-91`). |
| T-06 | Information Disclosure (stack-trace leak) / DoS | Low | mitigate | **CLOSED** | Unhandled `ValueError` → raw 500 (REVIEW.md WR-05). `evidence_review_endpoints.py:123-126` — `try/except ValueError` → `HTTPException(422, ...)`. |
| T-07 | Tampering / Injection (boundary input validation) | Medium | mitigate | **CLOSED** | `evidence_review_endpoints.py:41-47` — `CreateReviewRequest.comment` (`min_length=1, max_length=2000`), `UpdateDecisionRequest.decision` constrained by Pydantic `pattern=r"^(approved|rejected|changes_requested)$"`, `comment` `max_length=2000`. Server independently re-validates the comment-required rule at `:116-120` (not solely reliant on the regex/frontend). |
| T-08 | Tampering (stored XSS) | Low | mitigate | **CLOSED** | Reviewer `comment` is rendered at `EvidenceReviewPanel.tsx:163` as a plain JSX text child (`{rv.comment}`); confirmed no `dangerouslySetInnerHTML` anywhere in the file (grep), so React's default escaping applies. |
| T-09 | Information Disclosure (broad in-tenant read access) | Low | accept | **CLOSED (accepted risk)** | Any authenticated user in a tenant — not just the evidence uploader or a reviewer — can `GET` a review thread or the tenant's pending-review queue (`evidence_review_endpoints.py:1-10` docstring: "GET reviews: any authenticated user (own tenant)"). This matches the plan's stated policy (only *decisions* are role-gated; visibility is not). Tenant boundary is still enforced on both read endpoints (`tenantId` filter present in `get_reviews` and `get_pending_evidence`). See Accepted Risks Log below. |
| T-10 | Repudiation | Medium | *(none declared)* | **OPEN — non-blocking** | No audit-log entry is written for approve/reject/request-changes decisions. Searched `evidence_review_service.py` and `evidence_review_endpoints.py`: zero `logger.*` calls in either file, no `audit_logs` collection write, no `audit_service.log_action_async` call. This codebase has an established pattern for comparable role-gated, state-changing actions: `agent_quarantine_endpoints.py:56,116` (`db.audit_logs.insert_one`), `agent_registry_endpoints.py:206`, `agent_download_endpoints.py:135,255,297`, `agent_remote_control.py:90-92` (`audit_service.log_action_async`). Evidence-review decisions directly affect a tenant's compliance score/status — exactly the class of action an auditor or regulator would expect a non-repudiable trail for. Mitigating factor: the `evidence_reviews` record itself retains `reviewer`, `comment`, `status`, and `updated_at`, giving a partial in-band trail, but it is mutable in place with no independent, append-only log. |
| T-11 | Denial of Service | Medium | *(none declared)* | **OPEN — non-blocking** | No rate limiting on the three state-mutating endpoints (`POST .../submit-for-review`, `POST .../review`, `PATCH .../review/{review_id}`). Searched `evidence_review_endpoints.py`: no `from rate_limiter import limiter`, no `@limiter.limit(...)` decorator. This codebase has an established per-route rate-limiting pattern for comparable write endpoints: `agent_approval_endpoints.py:14,161` (`@limiter.limit("60/minute")`), `auth_password_reset_endpoints.py:16,37,68`. An authenticated user (any role, since `create_review`/`submit_for_review` are open to "any user" by design) could spam `create_review` to grow the `evidence_reviews` collection unbounded. |
| T-12 | Denial of Service (unbounded query) | Low | *(none declared)* | **OPEN — non-blocking** | `get_reviews` (`evidence_review_service.py:191`) and `get_pending_evidence` (`:223`) both call `cursor.to_list(length=None)` with no page size or hard cap. For a tenant with a very large evidence/review volume, a single request loads the entire result set into memory. Scoped to the caller's own tenant (not a cross-tenant amplification vector), and compounded by T-11 (no rate limit to slow down repeated large requests). |

## Verification Notes (adversarial checks performed, not just "looks fixed")

- Re-ran `pytest backend/tests/test_evidence_review.py` live: 8/8 passed (not just trusted the SUMMARY.md claim).
- For T-01, did not stop at "a `tenant_id` parameter exists" — read the actual Mongo filter dict at both call sites (`find_one_and_update` and the evidence-status-propagation `update_one`) to confirm `tenantId` is in the filter, not merely passed through and unused.
- For T-02, grepped the full component file for any remaining raw `fetch(` call before accepting the mitigation as complete — none found. Also confirmed `authFetch` actually attaches the `Authorization` header (read `apiService.ts:198-247`) rather than assuming the helper does what its name implies.
- For T-03, traced role provenance to the JWT-decode boundary (`authentication_service.py:106-113`) to confirm `current_user.role` cannot be influenced by request body/query — closes the "check in the wrong layer" failure mode.
- `test_tenant_isolation` (test 8 in the suite) was read closely: it verifies **role-gating** (403 for non-admin PATCH) but does **not** exercise a genuine two-tenant scenario (no second tenant's data is set up in the mock, no assertion that a tenant-A admin is denied a tenant-B review). T-01's closure is therefore based on direct code/query inspection, not on this test providing proof — flagging this so it isn't mistaken for regression coverage of the IDOR fix.
- T-10/T-11/T-12 were not sourced from a SUMMARY.md `## Threat Flags` section (none exists in `15-01-SUMMARY.md` — confirmed via heading grep) and are not mentioned in `15-REVIEW.md`/`15-REVIEW-FIX.md`. They were identified independently during this audit's implementation review, by comparing this module's patterns against sibling modules in the same codebase that handle comparable actions.

## Unregistered Flags (from SUMMARY.md `## Threat Flags`)

None — `15-01-SUMMARY.md` has no `## Threat Flags` section.

## Accepted Risks Log

| ID | Risk | Rationale | Accepted By |
|----|------|-----------|-------------|
| T-09 | Any authenticated user within a tenant can read another user's evidence review thread and the tenant's pending-review queue (not restricted to uploader/reviewer). | Matches explicit plan/docstring policy ("any authenticated user, own tenant" for GET routes); only *decision-making* is role-gated. Tenant isolation is still enforced. Low severity — internal-to-tenant visibility of compliance review comments is a normal collaboration pattern for this feature, not an unintended leak. | Documented retroactively by `/gsd-secure-phase` audit, 2026-07-02. Should be re-confirmed by product/security owner if the compliance-reviewer role model changes. |

## Open — Non-Blocking (severity below `block_on: high`)

| ID | Category | Severity | Mitigation Expected | Files Searched | Recommendation |
|----|----------|----------|----------------------|-----------------|-----------------|
| T-10 | Repudiation | Medium | Audit-log write (`audit_logs` collection or `audit_service.log_action_async`) on every review decision | `backend/evidence_review_service.py`, `backend/evidence_review_endpoints.py` | Add an `audit_logs.insert_one(...)` (or `audit_service.log_action_async(...)`) call in `update_review_decision`, capturing `tenant_id`, `reviewer`, `evidence_id`, `review_id`, `decision`, `timestamp`. Follow the existing pattern in `agent_quarantine_endpoints.py`. |
| T-11 | Denial of Service | Medium | `@limiter.limit(...)` decorator from `rate_limiter.py` on the 3 write endpoints | `backend/evidence_review_endpoints.py` | Add `@limiter.limit("30/minute")` (or similar) to `submit_evidence_for_review`, `create_evidence_review`, and `update_evidence_review`, matching `agent_approval_endpoints.py`'s pattern. |
| T-12 | Denial of Service | Low | Pagination or a hard `limit()` on `get_reviews`/`get_pending_evidence` cursors | `backend/evidence_review_service.py:191,223` | Add a `limit` parameter (e.g. cap at 500) to both `to_list()` calls, or paginate via `skip`/`limit` at the endpoint layer. |

*No blocking-open threats. `threats_open` (gate field) = 0. Phase is not blocked from shipping under `block_on: high`, but T-10/T-11/T-12 should be tracked and scheduled — repudiation and DoS gaps on a compliance-evidence approval workflow are the kind of finding that tends to resurface in a real audit.*

---
*Audited: 2026-07-02*
*Auditor: Claude (gsd-security-auditor), retroactive-STRIDE mode*
