---
phase: 59-procurement-finance-warranty-depreciation
verified: 2026-08-06T00:00:00Z
status: passed
score: 10/10 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 59: Procurement & Finance (Warranty & Depreciation) Verification Report

**Phase Goal:** Give every asset a financial record — purchase cost/date/PO/supplier, warranty tracking with proactive expiry alerts, and a computed book value — without any external accounting/GL integration.
**Verified:** 2026-08-06
**Status:** passed
**Re-verification:** No — initial verification

## Independent Audit Note

This phase's own SUMMARY.md files document an unusually messy execution history: two prior commits (`72a236f`, `490e850`) added sweep code and Phase 60 license code outside the normal plan/task/SUMMARY convention, and a code review this session (`59-REVIEW.md`) found a real critical defect (CR-01: warranty alerts written via the raw-handle in-app path had no `tenantId` field and were invisible to every tenant-scoped reader) that the phase's own test suite did not catch. Given that history, this verification did not take SUMMARY/REVIEW claims at face value — every claimed fix was independently re-derived from the current source tree, and the full backend test suite was run fresh rather than trusting reported pass counts.

**Independently confirmed:**
- CR-01 fix is genuinely present in `backend/notification_service.py`'s `send_alert` (lines ~80-84): it now writes `"tenantId": tenant_id` explicitly (camelCase) alongside the pre-existing `"tenant_id": tenant_id` (snake_case), with a comment explaining why. Regression assertions exist and pass in `test_itam_warranty_notify.py:249` (`assert inserted_doc["tenantId"] == "tenant-a"`) and `test_itam_finance_sweep_resilience.py:63` (`assert db._captured_notifications[0]["tenantId"] == "tenant-a"`).
- WR-03 fix (marker-write isolation) is present: `run_warranty_alert_pass`'s final `db.assets.update_one(...)` is wrapped in its own `try/except Exception` and uses `asset.get("id")` rather than `asset["id"]`, matching the two delivery-path try/excepts above it.
- WR-02 fix (EXPIRING branch test) — not independently re-derived line-by-line, but the full warranty-sweep test suite (106 phase tests) passes, including the sweep tests, and `run_warranty_alert_pass`'s classification branch (`WARRANTY_STATUS_EXPIRING` or `WARRANTY_STATUS_EXPIRED`) is unchanged and correctly wired.
- All commit hashes cited across the four SUMMARY.md files and REVIEW.md (`aec6ecb`, `2cd50e1`, `3106ac1`, `c08f3f7`, `ec58e1f`, `8cbf9eb`, `bbc78fa`, `235cd94`, `f4ccb67`, `69634e2`, `72a236f`, `490e850`) exist in git log — confirmed via `git cat-file -e`.
- `backend/tests/test_itam_license.py`'s claimed `IndentationError` at line 105 is real and reproducible (`ast.parse` fails at collection) — confirmed out of scope for Phase 59 (it belongs to Phase 60's bundled-in code) and does not affect Phase 59's own test collection since it's excluded via `--ignore`.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | An admin can record purchase cost, purchase date, PO number, and supplier on an asset via `PATCH /api/assets/{asset_id}/purchase` (ITAM-FIN-01, ROADMAP SC1) | ✓ VERIFIED | `backend/itam_finance_endpoints.py:54-103` implements the route; `AssetPurchaseUpdate` model confirmed to carry exactly `purchaseCostCents, purchaseDate, poNumber, supplierId, warrantyMonths`; 106/106 phase tests pass including `TestFinanceTracerEndToEnd`, `TestPurchasePatchValidation` |
| 2 | Purchase cost is integer cents, never a float; a bad supplierId is refused with 400; negative/invalid values are rejected with 422 before any write (D-01, D-02) | ✓ VERIFIED | `purchaseCostCents: Optional[int] = Field(None, ge=0)` in `itam_models.py`; supplier existence check at `itam_finance_endpoints.py:81-87`; `TestPurchasePatchValidation` asserts `find_one_and_update` never awaited on 422 paths — pass |
| 3 | Purchase fields are optional at manual-asset creation and persist when supplied (`POST /api/assets`) | ✓ VERIFIED | `ManualAssetCreate(name="x").model_dump(exclude_none=True)` independently run — emits no purchase keys; `TestPurchaseFieldsAtCreateTime` passes |
| 4 | `GET /api/assets/{asset_id}/book-value` computes straight-line book value at read time, floored at salvage, never persisted (ITAM-FIN-03, ROADMAP SC3) | ✓ VERIFIED | `itam_finance_endpoints.py:106-164`, `itam_finance_service.compute_book_value` independently executed — matches documented anniversary-year formula exactly; `TestBookValueCompute`/`TestBookValueNeverPersists` pass |
| 5 | A missing/partial depreciation policy or missing purchase record returns 200 with `bookValueCents: null` + machine-readable `reason` — never a 500, never a fabricated number | ✓ VERIFIED | Two structured-response branches confirmed in `get_asset_book_value`; `TestBookValueNoPolicy` (6+ degraded-state cases) passes |
| 6 | Cross-tenant asset access returns the same 404 as an unknown id; unauthorized callers get 403 across all three finance routes | ✓ VERIFIED | All three routes reuse `_require_itam_admin` and `TenantIsolatedDatabase`-scoped lookups via `_load_asset`; `TestFinanceRbacAndTenantIsolation`, `TestWarrantyRouteAccess` pass |
| 7 | `GET /api/assets/{asset_id}/warranty` reports expiry, status (none/active/expiring/expired), and days-to-expiry, derived at read time from `purchaseDate`+`warrantyMonths`, classified against a per-tenant configurable alert window (ITAM-FIN-02 first half, ROADMAP SC2 first half) | ✓ VERIFIED | `itam_finance_endpoints.py:167-209` is a provable pass-through onto `compute_warranty_status`/`get_warranty_alert_window`; independently executed `compute_warranty_status` and `_add_months` produce documented values (leap-year day-clamp confirmed: 2024-01-31 + 1 month = 2024-02-29); `TestWarrantyRouteEndToEnd`, `TestWarrantyStatusCompute`, `TestAddMonths`, `TestWarrantyAlertWindow` pass |
| 8 | A tenant admin can configure a notification rule for `itam.warranty_expiring` through the existing `/api/notifications/rules` API (ITAM-FIN-02, "routed through existing notification/webhook infrastructure") | ✓ VERIFIED | `itam.warranty_expiring` confirmed present in both `notification_service.VALID_EVENTS` and `notification_endpoints.RuleCreate.event_type`'s `Literal`, alongside all five legacy event types; `TestWarrantyEventVocabulary` passes |
| 9 | A background sweep alerts admins as a warranty approaches/passes expiry, without anyone opening a page, delivered on two independent paths (in-app + rule-routed), with per-asset tenant isolation and an idempotency marker so one warranty produces at most one alert (ITAM-FIN-02 second half, ROADMAP SC2 second half) | ✓ VERIFIED | `run_warranty_alert_pass` independently read line-by-line: per-document `tenant_id = asset.get("tenantId")` extraction with skip-if-missing, `warrantyAlertSentAt` written in its own try/except with both `id` and `tenantId` in the filter, module holds no FastAPI/DB import, `start_warranty_alert_scheduler` registered in `app_startup.py` with the raw `_mdb.db` handle wrapped in try/except (degrades to warning). CR-01's tenantId gap — the one real defect this phase's own tests missed — is independently confirmed fixed in `notification_service.py` and pinned by regression tests. Full sweep+resilience suite (19 tests) passes |
| 10 | An asset with no `tenantId` is never alerted; alert recipients are drawn only from that tenant's own admins; a failure in one delivery path never aborts the sweep for other tenants | ✓ VERIFIED | Guard clause confirmed at `itam_finance_service.py:312-315`; `_tenant_admin_emails` filters by `tenantId` and admin role set; each delivery path and the marker write are each independently try/excepted; `TestSweepResilienceAndTenantScope` (two-tenant isolation test) passes |

**Score:** 10/10 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/itam_finance_service.py` | Pure compute functions + sweep, no FastAPI/DB import | ✓ VERIFIED | 424 lines, under 500-line cap; `compute_book_value`, `compute_warranty_status`, `_add_months`, `get_warranty_alert_window`, `run_warranty_alert_pass`, `start_warranty_alert_scheduler`, `_RawDbForNotificationRules`, `_tenant_admin_emails`, `WARRANTY_EVENT_TYPE` all confirmed present |
| `backend/itam_finance_endpoints.py` | 3 RBAC-gated, tenant-scoped routes | ✓ VERIFIED | 209 lines; `PATCH /{asset_id}/purchase`, `GET /{asset_id}/book-value`, `GET /{asset_id}/warranty` all registered on `router` |
| `backend/itam_models.py` | Purchase/depreciation field extensions, single date validator | ✓ VERIFIED | 311 lines; `grep -c "def _validate_iso8601_date"` = 1; `AssetPurchaseUpdate` carries all 5 fields |
| `backend/notification_service.py` | `VALID_EVENTS` extended, CR-01 tenantId fix | ✓ VERIFIED | 561 lines (see Anti-Patterns note below — pre-existing overage, not introduced by Phase 59) |
| `backend/notification_endpoints.py` | `RuleCreate.event_type` Literal extended | ✓ VERIFIED | `itam.warranty_expiring` present alongside 5 legacy values |
| `backend/router_registry.py` | Finance router registered in correct order | ✓ VERIFIED | `itam_finance_endpoints` registered immediately after `itam_label_endpoints` and before `asset_endpoints` |
| `backend/app_startup.py` | Warranty scheduler registered with raw handle, graceful degradation | ✓ VERIFIED | Registration block matches the shape of the three existing raw-DB scheduler blocks exactly; `try/except` degrades to `logger.warning` |
| Phase test files (8 files, ~2000 lines) | Automated coverage of all must-haves | ✓ VERIFIED | All under 500 lines each; 106/106 tests pass on independent re-run |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `router_registry.py` | `itam_finance_endpoints.router` | `_load(app, "itam_finance_endpoints", "router")` | ✓ WIRED | Confirmed at correct line position; `import router_registry` exits 0 |
| `itam_finance_endpoints.py` | `itam_asset_endpoints._require_itam_admin` | import + `Depends()` on all 3 routes | ✓ WIRED | Confirmed — no redefined RBAC gate |
| `itam_finance_endpoints.py` | `itam_finance_service` (compute_book_value, compute_warranty_status, get_warranty_alert_window) | direct function calls, route is provable pass-through | ✓ WIRED | Confirmed via source read; route never re-implements classification logic |
| `notification_endpoints.RuleCreate` | `notification_service.VALID_EVENTS` | both carry `itam.warranty_expiring` | ✓ WIRED | Confirmed identical string in both locations |
| `app_startup.py` | `itam_finance_service.start_warranty_alert_scheduler` | `asyncio.create_task(start_warranty_alert_scheduler(_mdb.db))` | ✓ WIRED | Confirmed — raw unwrapped Motor handle passed, matching the sweep's structural no-self-resolved-handle contract |
| `run_warranty_alert_pass` | `notification_service.send_alert` / `send_notification` | raw handle direct / `_RawDbForNotificationRules` adapter | ✓ WIRED | Confirmed both call sites match the documented dual-path contract; CR-01 fix confirmed closing the tenantId gap on the in-app path |
| `PATCH /purchase` | `warrantyAlertSentAt` reset | `$unset` when `purchaseDate`/`warrantyMonths` in update_data | ✓ WIRED | Confirmed at `itam_finance_endpoints.py:91-93`; the reset half of the idempotency contract the sweep depends on |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `compute_book_value` anniversary-year math | Direct call with cost=150000, salvage=15000, life=3y, purchase 2023-01-15, now 2026-01-14 | `{'bookValueCents': 60000, 'yearsElapsed': 2, 'annualDepreciationCents': 45000}` | ✓ PASS |
| `compute_warranty_status` boundary classification | Same asset, window=30 | `{'warrantyStatus': 'expiring', 'daysToExpiry': 1, ...}` | ✓ PASS |
| `_add_months` day-clamp on month-end | `_add_months(2024-01-31, 1)` | `2024-02-29` (leap-year clamp correct) | ✓ PASS |
| Full phase test suite (106 tests across 6 files) | `pytest backend/tests/test_itam_finance*.py backend/tests/test_itam_warranty_notify.py -q` | 106 passed | ✓ PASS |
| Full backend suite regression check | `pytest backend/tests -q --ignore=test_graphql.py --ignore=test_itam_license.py` | 1805 passed / 35 skipped / 3 pre-existing unrelated failures (`test_agentic_ai`, `test_e2e_integration`, `test_rust_heartbeat_parity`) | ✓ PASS (matches documented baseline exactly, no new failures) |
| CR-01 fix presence | `grep -n tenantId backend/notification_service.py` (send_alert body) | `"tenantId": tenant_id,` present at insert site | ✓ PASS |
| Module import sanity | `import router_registry; import app_startup` | Both exit 0 | ✓ PASS |
| `test_itam_license.py` claimed break (Phase 60 bundled code, out of scope) | `pytest backend/tests/test_itam_license.py -q` | `IndentationError` at line 105, collection fails | Confirmed real, correctly excluded from Phase 59's suite runs |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ITAM-FIN-01 | 59-01 | Purchase cost, purchase date, PO number, supplier on asset | ✓ SATISFIED | `PATCH /purchase` + `POST /api/assets` both persist all 5 fields; REQUIREMENTS.md marked Complete |
| ITAM-FIN-02 | 59-02, 59-03, 59-04 | Warranty tracking + expiry alerts via existing notification/webhook infra | ✓ SATISFIED | Status/expiry route (59-03) + vocabulary extension (59-02) + background sweep with dual delivery paths and CR-01 fix (59-04); REQUIREMENTS.md marked Complete |
| ITAM-FIN-03 | 59-01 | Straight-line depreciation, model-level, computed at read time | ✓ SATISFIED | `GET /book-value` computed fresh per request, never persisted; REQUIREMENTS.md marked Complete |

No orphaned requirements — all three IDs REQUIREMENTS.md maps to Phase 59 appear in plan frontmatter and are independently confirmed delivered.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/notification_service.py` | whole file | 561 lines, over CLAUDE.md's 500-line cap | ℹ️ Info | Confirmed via `git show` that this file was already 551 lines *before* Phase 59 touched it (pre-existing violation from an earlier phase); Phase 59's CR-01 fix added only 10 net lines. REVIEW.md explicitly flags this as a deferred cleanup item, not attempted in this phase. Not a Phase 59 regression — noted for awareness only. |
| `backend/itam_finance_service.py` | 99-107 (WR-01, deferred) | `compute_book_value` can return a book value above purchase cost if a Model's `salvageValueCents` exceeds a specific asset's `purchaseCostCents` (no cross-field validation possible since these live on different documents) | ℹ️ Info | Edge case requiring a misconfigured Model; does not violate the plan's stated must-have ("floored at salvage, never below it") or the ROADMAP success criterion wording. Explicitly deferred in REVIEW.md to a future Model/depreciation cleanup pass — correctly out of Phase 59's committed scope. |
| `backend/itam_finance_endpoints.py` | 148-157 (WR-04, deferred) | A corrupt (unparseable) stored `purchaseDate` returns `reason: "no_depreciation_policy_assigned"` instead of a more accurate reason | ℹ️ Info | Low-likelihood (every write path validates the date); misleading but not a 500 or a wrong number. Explicitly deferred, does not block ITAM-FIN-03. |

No blockers found. No unresolved TBD/FIXME/XXX debt markers in any Phase 59 file.

### Human Verification Required

None required for the automated-testable surface. Two items are explicitly deferred by the plans themselves to a `/gsd-verify-work` conversational UAT pass (not required for this goal-backward code verification, since they concern live external delivery rather than code correctness):

1. **Real alert arrival via the notification bell / configured channel** — observing `GET /api/notifications` show a warranty alert, or a configured Slack/webhook channel actually receive one, in a running application with live data. The sweep's decisions and delivery-path wiring are fully proven against stubs (including the CR-01 regression, now fixed and pinned); only the live end-to-end delivery experience is unverified by this code-level pass. Deferred per `59-04-PLAN.md`'s own `<verification>` section — not a phase-goal gap.
2. **A real tenant's configured `system_settings` warranty alert-window document taking effect against live data** — deferred per `59-03-PLAN.md`'s own `<verification>` section, same reasoning.

### Gaps Summary

No gaps found. All 10 observable truths derived from ROADMAP.md's Phase 59 success criteria and the four plans' `must_haves.truths` are independently verified against the current codebase — not just SUMMARY.md's claims. The one real defect this phase's own execution history surfaced (CR-01: warranty alerts invisible to tenants due to a raw-handle `tenantId` gap) was independently confirmed both as a genuine finding and as genuinely fixed, with regression tests in place and passing. The phase's messy commit history (`72a236f`, `490e850` bypassing plan conventions, later reconciled by `235cd94`/`f4ccb67`) is fully accounted for in the current tree: the app_startup registration gap it left behind is confirmed present in `app_startup.py`, and the full backend suite (1805 passed, same 3 pre-existing unrelated failures as the documented baseline) shows no regressions. The one adjacent issue surfaced (`test_itam_license.py`'s `IndentationError`) belongs to Phase 60's bundled-in code, not Phase 59, and is correctly excluded from Phase 59's own suite runs.

---

*Verified: 2026-08-06*
*Verifier: Claude (gsd-verifier)*
