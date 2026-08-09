---
phase: 18-privacy-legal-modules
fixed_at: 2026-07-03T22:12:08Z
review_path: .planning/phases/18-privacy-legal-modules/18-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 18: Code Review Fix Report

**Fixed at:** 2026-07-03T22:12:08Z
**Source review:** .planning/phases/18-privacy-legal-modules/18-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (3 Critical + 6 Warning; the 3 Info findings were out of scope for this pass per `fix_scope: critical_warning`)
- Fixed: 9
- Skipped: 0

**Correctness gate re-verified:** `python3 -m pytest backend/tests/test_privacy_service.py -v` (using `backend/venv/bin/python`) now passes 8/8, matching the PLAN's explicit must-have. Baseline run before any fix reproduced the review's reported 8/8 failures exactly.

## Fixed Issues

### CR-01: All 8 required unit tests fail — `patch("privacy_endpoints.get_database", ...)` targets a name that doesn't exist on the module

**Files modified:** `backend/privacy_endpoints.py`
**Commit:** 42f06b8
**Applied fix:** Added `from database import get_database` at module scope and removed the 11 duplicate per-function local imports (`list_breaches`, `create_tia`, `list_tia`, `create_lia`, `list_lia`, `create_notice`, `list_notices`, `get_notice_versions`, `create_contract`, `list_contracts`, `get_expiring_contracts`), leaving `db = get_database()` calls intact. Verified: `test_privacy_service.py` went from 8 failed → 8 passed.

### CR-02: `POST /api/privacy/{tia,lia,notices,contracts}` will 500 in production — un-popped Mongo `ObjectId` in the response body

**Files modified:** `backend/privacy_service.py`
**Commit:** 79d68b9
**Applied fix:** Added `doc.pop("_id", None)` immediately after `insert_one(doc)` in `create_tia`, `create_lia`, `create_notice`, and `create_contract`, matching the existing pattern already used by `create_dsr`, `record_consent`, `create_processing_activity`, and `report_breach`. Verified with a standalone repro (`ObjectId` injected then popped) that `jsonable_encoder` no longer raises.

### CR-03: Frontend shows "success" toast for TIA/LIA/Notice/Contract creation regardless of actual HTTP status

**Files modified:** `components/PrivacyLegalDashboard.tsx`
**Commit:** 419f30a
**Applied fix:** `submitTia`, `submitLia`, `submitNotice`, and `submitContract` now capture the `Response`, parse the body, and check `res.ok` before showing a success toast — a non-2xx response now shows the backend's `detail` message (or a generic failure message) and does not clear the form or close it.

### WR-01: New privacy sub-collections bypass the platform's tenant-isolation wrapper, with a real cross-account collision for accounts without a `tenant_id`

**Files modified:** `backend/privacy_service.py`
**Commit:** d639776
**Applied fix:** Added a `_fail_closed_tenant_id()` helper that substitutes the same `NON_EXISTENT_TENANT_ISOLATION_EMERGENCY` sentinel already used by `TenantIsolatedCollection` in `database.py` whenever `tenant_id` is falsy, and applied it at the top of all 10 TIA/LIA/Notice/Contract functions that talk to the raw `db._db.<collection>`. Chose this option (over switching to `db.<collection>`) because the existing test doubles in `test_privacy_service.py` configure mocks on `db._db.<collection>` specifically — switching accessor would have broken the test harness. This still closes the fail-open gap: accounts with no `tenant_id` claim (e.g. `super_admin`) can no longer collide on a shared `tenantId: None` partition.

### WR-02: `create_lia` and `create_notice` perform no input validation

**Files modified:** `backend/privacy_endpoints.py`
**Commit:** 7732605
**Applied fix:** Added `if not payload.get("purpose"): raise HTTPException(400, ...)` to `create_lia` and `if not payload.get("title"): raise HTTPException(400, ...)` to `create_notice`, consistent with the required-field checks already used by sibling endpoints (`create_dsr`, `create_processing_activity`).

### WR-03: `create_tia` never validates the `status` field even though the PLAN specifies it as a constrained enum

**Files modified:** `backend/privacy_service.py`
**Commit:** 908745b
**Applied fix:** Added `valid_statuses = {"draft", "approved", "rejected"}` check to `create_tia`, mirroring the existing `create_contract` enum-validation pattern. Status remains optional (unset is allowed) but any non-empty invalid value is rejected.

### WR-04: `create_dsr` discards the specific validation error and returns a generic "Bad request"

**Files modified:** `backend/privacy_endpoints.py`
**Commit:** 6e14f8c
**Applied fix:** Changed `except ValueError: raise HTTPException(400, "Bad request")` to `except ValueError as e: raise HTTPException(400, detail=str(e))`, forwarding `svc.create_dsr`'s actual message, consistent with how `create_tia`/`create_contract` already handle their own `ValueError`s in the same file.

### WR-05: `fetchData` never checks `response.ok`, so backend errors silently render as an empty state

**Files modified:** `components/PrivacyLegalDashboard.tsx`
**Commit:** 8304b61
**Applied fix:** Added a `fetchJson(url)` helper that throws on non-2xx responses, and replaced all four inline `authFetch(...).json()` calls in `fetchData` with it, so the existing `catch { showToast('Failed to load data', 'error') }` block now actually fires on a failed fetch instead of rendering a false "No items yet" empty state.

### WR-06: `PrivacyLegalDashboard` create forms omit fields the PLAN explicitly lists as part of the record schema

**Files modified:** `components/PrivacyLegalDashboard.tsx`
**Commit:** 304752f
**Applied fix:** Added comma-separated text inputs for `data_categories` and `safeguards` to the TIA form (parsed to a `string[]` for `data_categories`), and a comma-separated `parties` input to the Contract form (parsed to `string[]`). Also added the previously-undeclared `safeguards?: string` field to the `TIARecord` interface so the new input type-checks cleanly.

## Skipped Issues

None — all 9 in-scope findings were fixed and verified.

---

_Fixed: 2026-07-03T22:12:08Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
