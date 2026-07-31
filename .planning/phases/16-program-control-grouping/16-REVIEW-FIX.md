---
phase: 16-program-control-grouping
fixed_at: 2026-07-02T18:12:15Z
review_path: .planning/phases/16-program-control-grouping/16-REVIEW.md
iteration: 1
findings_in_scope: 13
fixed: 13
skipped: 0
status: all_fixed
---

# Phase 16: Code Review Fix Report

**Fixed at:** 2026-07-02T18:12:15Z
**Source review:** .planning/phases/16-program-control-grouping/16-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 13 (7 critical + 6 warning; the 3 Info findings were out of scope for this pass per `fix_scope: critical_warning`)
- Fixed: 13
- Skipped: 0

## Fixed Issues

### CR-01: Test module fails to import — `TestClient` is not exported by `fastapi`

**Files modified:** `backend/tests/test_program_service.py`
**Commit:** `4eb56be`
**Applied fix:** Changed the import to `from fastapi.testclient import TestClient`, matching the convention used by every other test file in `backend/tests/`. Verified pytest can now collect the module (confirmed via direct pytest run before/after).

### CR-02: RBAC dependency override never applies — every test request gets 401/500, none exercise real logic

**Files modified:** `backend/tests/test_program_service.py`
**Commit:** `c8bbd91`
**Applied fix:** Changed `_build()` to override the stable `get_current_user` singleton (imported from `authentication_service`) instead of a freshly-constructed `rbac_service.has_permission(...)` closure, and changed the default mock-user role to `super_admin` so `rbac_service.get_user_permissions()` short-circuits via the wildcard-permission path before touching the (un-mocked) database — exactly as the review's fix guidance specified. Verified: the previous 401 Unauthorized failures on every request disappeared immediately after this change (`test_create_program` and `test_delete_program` began passing; remaining failures were the separate ObjectId/mock-wiring issues fixed by CR-03/CR-04/CR-05).

### CR-03: Required status-rollup tests are missing; existing tests assert nothing about behavior

**Files modified:** `backend/tests/test_program_service.py`
**Commit:** `aa2c728`
**Applied fix:** Rewrote the test file to contain exactly the 7 tests required by `16-01-PLAN.md`'s TDD spec (`test_create_program`, `test_add_controls_to_program`, `test_remove_controls_from_program`, `test_status_rollup_compliant`, `test_status_rollup_at_risk`, `test_list_programs_includes_rollup`, `test_tenant_isolation`), each with concrete body/state assertions instead of the previous `in (200, 400)`/`in (200, 404)` tautologies. Added the two missing rollup-threshold tests with concrete mocked `asset_compliance` data (5 controls/4 Compliant → `compliant`; 1 Non-Compliant → `at_risk`). Also fixed a latent bug in the `_mkdb()` test helper where `programs` and `asset_compliance` mock collections were accidentally aliased to the same `MagicMock` object (`col if c == "asset_compliance" else col` — both branches returned `col`), which silently clobbered the `programs.find` mock whenever `asset_compliance.find` was configured; this was blocking every rollup-touching test from passing regardless of the RBAC fix. Discovered and fixed a second gap where `program_endpoints.py` reads tenant scope from the `tenant_context` contextvar (not from the injected mock user), so `_build()` now also calls `set_tenant_id()` to prime it the way the real `get_current_user` would in production. Verified: all 7 required tests pass (`python3 -m pytest tests/test_program_service.py -v` → 7 passed), and a full `tests/` run shows no new failures versus the pre-existing baseline on `main` (39 pre-existing unrelated failures confirmed present on unmodified `main` too, e.g. `test_iac_scanner.py`, `test_notification_service.py`, `test_privacy_service.py`).

### CR-04: `POST /api/programs` returns a document with a raw, non-serializable Mongo `ObjectId`

**Files modified:** `backend/program_service.py`
**Commit:** `89af48a`
**Applied fix:** Added `doc.pop("_id", None)` immediately after `insert_one` mutates `doc` in place, before returning it. Verified by reproducing the exact scenario from the review with `mongomock` + `jsonable_encoder`: before the fix, `jsonable_encoder` raised `TypeError("'ObjectId' object is not iterable")`; after the fix, encoding succeeds and no `_id` key is present in the returned document.

### CR-05: `PUT /api/programs/{id}/controls` returns a document with a raw, non-serializable Mongo `ObjectId`

**Files modified:** `backend/program_service.py`
**Commit:** `9071d39`
**Applied fix:** Added the `{"_id": 0}` projection to the `find_one` call in `update_controls`, matching the pattern already used in `get_program`/`list_programs`. Verified with the same `mongomock` + `jsonable_encoder` reproduction as CR-04 — a create-then-update-controls round trip now encodes cleanly.

### CR-06: Frontend reports false "success" for create/delete regardless of actual HTTP outcome

**Files modified:** `components/ProgramsDashboard.tsx`
**Commit:** `4c96695`
**Applied fix:** Both `submit()` and `del()` now capture the `Response` object, check `res.ok`, and `throw` (routing to the existing `catch` → error toast) before declaring success, exactly as the review's suggested fix specified.

### CR-07: "Manage Controls" feature is entirely non-functional — no modal, no PUT call

**Files modified:** `components/ProgramsDashboard.tsx`
**Commit:** `cec30cd`
**Applied fix:** Implemented the control-picker modal inline in `ProgramsDashboard.tsx` (kept in the same file rather than adding a new component file, per CLAUDE.md's "prefer editing existing files" / "never create files unless absolutely necessary" — the file remains well under the 500-line limit at 170 lines). The modal fetches `/api/compliance`, flattens all frameworks' `controls` into a searchable checkbox list pre-seeded with the program's existing `control_ids`, and on Save computes `add`/`remove` diffs and calls `PUT /api/programs/{id}/controls` with `{add, remove}`, checking `res.ok` before closing and refreshing (consistent with the CR-06 fix). The "Controls" button now opens this modal instead of silently setting unused state.

### WR-01: `_compute_status_rollup` silently ignores its own `tenant_id` parameter for the `asset_compliance` query

**Files modified:** `backend/program_service.py`, `backend/tests/test_program_service.py`
**Commit:** `eedeb17`
**Applied fix:** Changed the `asset_compliance` query to use `db._db.asset_compliance.find(...)` (raw Motor access, matching the rest of the file's pattern for `programs`) instead of `db.asset_compliance.find(...)` (which goes through `TenantIsolatedCollection` and silently overwrites the explicit `tenant_id` filter with the `tenant_context` contextvar). Updated the `_mkdb()` test helper in the same commit so its mock structure matches the corrected access pattern (`asset_compliance` now lives under `db._db`, as a distinct mock object from `programs` — also closing the aliasing bug noted under CR-03). All 7 required tests still pass after this change.

### WR-02: Status rollup ignores "latest" semantics and silently drops results

**Files modified:** `backend/program_service.py`, `backend/tests/test_program_service.py`
**Commit:** `7909bc6`
**Applied fix:** Added `.sort("lastUpdated", -1)` to the `asset_compliance` query (the field name confirmed from `compliance_status_endpoints.py`'s write path, which stamps every status change with `lastUpdated`), so the existing "keep first per controlId" dedupe logic now deterministically retains the most-recently-updated result per control rather than an arbitrary cursor-order pick. Updated the `_mkdb()` test mock to support the new `.sort()` chain in the same commit.

### WR-03: No schema/type validation on program-mutation request bodies

**Files modified:** `backend/program_endpoints.py`
**Commit:** `8093652`
**Applied fix:** Replaced the raw `dict = Body(...)` parameters with Pydantic models `ProgramCreate` (`name: str`, `description/framework_id/owner: str = ""`, `control_ids: list[str] = []`) and `ControlsUpdate` (`add/remove: list[str] = []`), matching the codebase's existing convention (e.g. `compliance_status_endpoints.py`'s `ComplianceStatusUpdate`). Verified the exact defect from the review is now closed: sending `{"add": "CC6.2", "remove": []}` (a string instead of a list) now returns a clean `422` (`"Input should be a valid list"`) instead of silently corrupting `control_ids` by iterating the string's characters.

### WR-04: `Pending_Evidence` status is counted as "failing", inflating false "at_risk" signals

**Files modified:** `backend/program_service.py`
**Commit:** `15f6682`
**Applied fix:** Split the status-counting branch so only `"Non-Compliant"` increments `failing`; `"Pending_Evidence"` now increments a separate `pending` counter that is folded into `not_assessed` (`not_assessed = total - len(seen) + pending`), keeping the returned rollup shape unchanged (`{total, passing, failing, not_assessed, status}`) as required by the plan's documented schema. Verified with a standalone reproduction: a program where every control is `Pending_Evidence` now reports `status: "in_progress"` (not `"at_risk"`) with `failing: 0`.

### WR-05: Local `fetch` callback shadows the global `window.fetch`

**Files modified:** `components/ProgramsDashboard.tsx`
**Commit:** `bfe78f5`
**Applied fix:** Renamed the local refresh callback from `fetch` to `loadPrograms` and updated all 4 call sites (the `useEffect` mount hook, and after `submit`/`del`/`saveControls` complete). No references to the shadowed name remain.

### WR-06: No confirmation before destructive delete

**Files modified:** `components/ProgramsDashboard.tsx`
**Commit:** `22d04cf`
**Applied fix:** Added `if (!window.confirm('Delete this program? This cannot be undone.')) return;` as the first line of `del()`, consistent with the review's suggested fix.

## Skipped Issues

None — all 13 in-scope findings were fixed.

---

_Fixed: 2026-07-02T18:12:15Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
