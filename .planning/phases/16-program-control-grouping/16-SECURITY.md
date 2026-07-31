---
phase: 16
slug: program-control-grouping
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-07-04
---

# Phase 16 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
>
> **Mode: retroactive-STRIDE.** `16-01-PLAN.md` predates this project's `<threat_model>` convention, so no
> declared threat register existed. This register was built from scratch by reading the implementation
> (`backend/program_service.py`, `backend/program_endpoints.py`, `backend/tests/test_program_service.py`,
> `components/ProgramsDashboard.tsx`) plus the supporting trust-boundary code (`tenant_context.py`,
> `database.py`'s `TenantIsolatedCollection`, `rbac_service.py`, `authentication_service.py`), then each
> threat was independently verified against current code (not against `16-REVIEW.md`/`16-REVIEW-FIX.md`
> claims alone).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Tenant isolation on program CRUD | `/api/programs` reads/writes must never cross tenant boundaries | Program documents (name, description, owner, control_ids) |
| RBAC on program mutation endpoints | Only privileged roles may create/modify/delete programs; any authenticated user may read | JWT-derived role/permission claims |
| Input validation on control_ids/status fields | Request bodies for create/control-membership-update must not corrupt DB queries or state | `control_ids: list[str]`, `add`/`remove` arrays |
| ObjectId leakage in API responses | Mongo internal `_id` (ObjectId) must never reach the JSON response | Program documents returned by create/get/list/update |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-16-01 | Tampering / Elevation of Privilege | `program_service.py` create/get/list/delete | critical | mitigate | `tenant_id` sourced exclusively from `get_tenant_id()`, a contextvar set only from the decoded JWT `tenant_id` claim (`authentication_service.py:96,157`) — never from client-supplied body/query params. All 4 functions filter/stamp the Mongo op with this value (`program_service.py:11-20,23-29,32-37,57-59`; `program_endpoints.py:34,41,48,66`). | closed |
| T-16-02 | Tampering / Broken Object-Level Authorization | `program_service.py:49-52` `update_controls` write | low | mitigate (partial — see note) | `update_one({"id": program_id}, ...)` omits `tenantId` from its own filter, unlike `delete_one` (line 58) which correctly includes it. Not independently exploitable: the preceding `find_one({"id": program_id, "tenantId": tenant_id})` (line 41) already gates access — a foreign-tenant caller gets `None`→404 before `update_one` ever runs, and `program_id` is a random 48-bit UUID slug, not guessable/sequential. Flagged as a defense-in-depth deviation from the file's own established pattern, not a live authorization bypass. | open — below high threshold (non-blocking) |
| T-16-03 | Elevation of Privilege | `program_endpoints.py` create/update-controls/delete routes | high | mitigate | All 3 mutation routes wire `Depends(rbac_service.has_permission("manage:settings"))` (lines 30, 55, 64). `has_permission` resolves the user via the stable `get_current_user` singleton and 403s on missing permission (`rbac_service.py:115-129`); `manage:settings` is absent from `user`/`viewer`/`analyst` default roles, present only for `admin`/`Tenant Admin`/`super_admin`. The CR-02 defect (broken RBAC override) was a **test-harness** bug — a mismatched closure object in the test's `dependency_overrides` key — not a flaw in the router's actual `Depends()` wiring, which was correct before and after the fix. | closed |
| T-16-04 | Elevation of Privilege | `program_endpoints.py` list/get routes | informational | mitigate | `Depends(rbac_service.has_permission("view:dashboard"))` gates reads (lines 39, 46) — broad, authenticated-only, consistent with the codebase's convention for dashboard-adjacent read endpoints. | closed |
| T-16-05 | Tampering (mass assignment / NoSQL query corruption) | `program_endpoints.py:16-27` request bodies | high | mitigate | `ProgramCreate`/`ControlsUpdate` Pydantic models (not raw `dict = Body(...)`) type-enforce `control_ids`/`add`/`remove` as `list[str]`. Closes the original defect where a string payload (`"add": "CC6.2"`) would have its characters iterated as individual control IDs, and prevents a dict-shaped NoSQL operator (e.g. `{"$ne": null}`) from ever reaching the `{"controlId": {"$in": control_ids}}` query in `_compute_status_rollup` (`program_service.py:70`) — Pydantic 422s before the query layer. | closed |
| T-16-06 | Information Disclosure / Availability | `program_service.py` create/get/list/update response paths | high | mitigate | All 4 doc-returning paths verified `_id`-free: `create_program` pops `_id` post-insert (lines 18-19); `get_program`/`list_programs`/`update_controls`'s `find_one` all project `{"_id": 0}` (lines 24, 33, 41), and `update_controls`'s return reuses that already-projected dict rather than re-fetching. Pre-fix, `jsonable_encoder` raised on the raw `ObjectId`, so every real `POST`/`PUT` 500'd — this was an availability defect as much as a disclosure one. | closed |
| T-16-07 | Repudiation | `program_endpoints.py` — no audit trail on program create/update/delete | low | none (unaddressed) | `program_endpoints.py` imports `logging` but never calls it; the codebase's only audit-logging utility (`AuditService.log_event`, `audit.py`) is not invoked from any endpoint file in `backend/` currently — this is a pre-existing platform-wide gap, not a regression specific to this phase. | open — below high threshold (non-blocking) |
| T-16-08 | Denial of Service | `program_service.py:33,72` unbounded result caps | low | mitigate (partial) | `list_programs` caps at `to_list(length=100)`; status-rollup lookup caps at `to_list(length=1000)` — bounds exist but are unexplained magic numbers (16-REVIEW.md IN-01/IN-03, explicitly deferred as info-severity/out-of-scope for the fix pass). No cap on `control_ids` array length per request, but `MaxBodySizeMiddleware` bounds overall request body size as a blanket protection. | open — below high threshold (non-blocking) |

*Status: open · closed · open — below {block_on} threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

**Config:** `asvs_level: 1`, `block_on: high` → only OPEN threats rated `high` or `critical` count toward `threats_open`. T-16-02, T-16-07, T-16-08 are all `low` severity and OPEN, so they are tracked but non-blocking. **`threats_open: 0`.**

---

## Accepted Risks Log

No accepted risks. (T-16-02, T-16-07, T-16-08 are open-non-blocking findings, not formally accepted risks — see Threat Register for rationale; recommended follow-ups noted below.)

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-04 | 8 | 5 | 3 (all below block_on threshold) | gsd-security-auditor (retroactive-STRIDE) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer, or explicitly "none — unaddressed" for newly-identified gaps)
- [x] Accepted risks documented in Accepted Risks Log (none required — no formal risk acceptance was made)
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-04

## Recommended Follow-ups (non-blocking)

1. **T-16-02:** Add `"tenantId": tenant_id` to the `update_one` filter in `program_service.py:49-52` for defense-in-depth consistency with `delete_one` (line 58) — closes a theoretical IDOR path even though it is not currently reachable.
2. **T-16-03 (test gap, not a code gap):** None of the 7 tests in `test_program_service.py` exercise the "insufficient permission → 403" negative path — every test uses `role="super_admin"` (wildcard bypass). Recommend adding a negative-permission regression test so a future refactor that breaks the `has_permission` wiring is caught automatically.
3. **T-16-07:** Wire `AuditService.log_event` (or equivalent) into program create/update-controls/delete, given this platform's compliance/audit-evidence purpose — a program-grouping change with no forensic trail undercuts the product's own audit-readiness value proposition. This is a platform-wide gap, not unique to this phase; consider addressing at the framework level (e.g., middleware) rather than per-endpoint.
4. **T-16-08 / IN-03 (from 16-REVIEW.md):** Extract the `100`/`1000` result caps to named constants or implement real pagination.
