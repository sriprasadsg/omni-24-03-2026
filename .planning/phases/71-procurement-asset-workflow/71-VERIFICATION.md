---
phase: 71-procurement-asset-workflow
verified: 2026-08-25T05:00:00Z
status: gaps_found
score: 11/12 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found (frontmatter) / passed (addendum's own claimed conclusion, never synced to frontmatter)
  previous_score: 7/12 (initial) — addendum claimed 12/12 after gap-closure
  gaps_closed:
    - "SC1 unreachable (Gap 1) — PurchaseOrdersPanel.tsx built, mounted as a real tab in ITAMConsole.tsx, wired to authFetch-based API calls; 7 substantive component tests pass; independently re-ran full frontend suite (457/457) and npm run build (clean)."
    - "Wire-shape bug (Gap 5) — response_model_by_alias=False confirmed present on all 4 PurchaseOrder response routes."
    - "SC5 notifications (Gap 3) — itam.asset_request_status confirmed registered in both notification_service.VALID_EVENTS and notification_endpoints.RuleCreate's Literal; the 2 new regression tests confirmed present and passing."
    - "Orphaned modules (Gap 4) — itam_scheduled_tasks.py and itam_asset_service.py plus their test files confirmed deleted; grep confirms zero dangling references anywhere in backend/; `python -c \"import app\"` succeeds cleanly."
  gaps_remaining:
    - "Asset-PurchaseOrder link visibility (part of Gap 2) — T-71-04 tenant-scoped validation is genuinely implemented and tested, but the must-have truth's second half (\"this link is visible in the asset detail view\") is still unmet. Exhaustive grep across components/ and services/apiService.ts finds zero references to purchase_order_id or purchaseOrderId anywhere in the reachable frontend. There is no longer even an 'asset detail view' surface in the real console (LifecyclePanel/CatalogPanel use table rows + action modals, not a detail page) for this to be displayed on. The addendum's own re-run table marked this truth '✓ VERIFIED (validation only; no dedicated read-path UI)' — self-contradictory, since the truth's own text requires visibility, not just validation. Treated here as still FAILED, not verified."
  regressions: []
gaps:
  - truth: "An asset can be linked to a purchase order, and this link is visible in the asset detail view (71-01 Task 3 tracer, must_haves.truths)"
    status: partial
    reason: >-
      The write+validate half is now solid: purchase_order_id is accepted on PATCH
      /api/assets/{id}/purchase, and itam_finance_endpoints.py now 400s when the
      supplied purchase_order_id does not resolve to a PurchaseOrder document via the
      tenant-scoped db handle (T-71-04, previously unmitigated, confirmed fixed and
      tested — 2 passing tests in test_itam_finance.py). But the display half was
      never built. No component under components/, and no function in
      services/apiService.ts, references purchase_order_id or purchaseOrderId
      anywhere. There is no reachable "asset detail view" in the real console at all
      (LifecyclePanel/CatalogPanel are table+modal based) for this link to surface on.
      A user can link an asset to a PO via the API but has no way to ever see that
      link in the product.
    artifacts:
      - path: "components/itam/LifecyclePanel.tsx"
        issue: "No purchase_order_id display anywhere; asset rows/modals show no PO linkage."
      - path: "components/itam/CatalogPanel.tsx"
        issue: "Same — no asset-level detail surface exists to host this."
      - path: "services/apiService.ts"
        issue: "No purchase_order_id read/display wiring; only PurchaseOrdersPanel's own CRUD functions exist."
    missing:
      - "A visible surface (a column, badge, or modal field on an existing asset-facing panel) showing the linked PurchaseOrder's order_number for assets that have purchase_order_id set."
    resolved: "PARTIAL — 2026-08-24 gap-closure session fixed the validation half only (T-71-04). The display half was explicitly and consciously deferred (see 71-VERIFICATION.md Re-verification Addendum, 'Residual, consciously not fixed'), but was then incorrectly rolled up as VERIFIED in the addendum's score. This verification pass keeps it as a gap since the must-have truth's own text requires visibility."
human_verification: []
---

# Phase 71: Procurement & Asset Workflow Verification Report

**Phase Goal:** Manage asset lifecycle from procurement to retirement with automated alerts and approval workflows.
**Success Criteria:** (1) Track purchase order details and supplier information. (2) Track warranty expiry and receive automated alerts. (3) View straight-line depreciation. (4) Request an asset and follow the approval workflow. (5) Receive email/Slack notifications for asset lifecycle events.
**Verified:** 2026-08-25
**Status:** gaps_found
**Re-verification:** Yes — this file already contained an initial pass (2026-08-24, `status: gaps_found`, 7/12) and a same-day "Re-verification Addendum" claiming all 5 gaps closed and `12/12`, but the frontmatter's `status:` field was never synced to that conclusion. This pass independently re-derives the verdict from the current codebase rather than trusting either the original frontmatter or the addendum's narrative.

## Independent Re-verification of the Addendum's Claims

The addendum claimed 5 gap-closure commits. All 5 were independently re-verified against the current codebase (not against the addendum's prose):

| Gap | Addendum's claim | Independent finding |
|---|---|---|
| 1 — SC1 unreachable | Built `components/itam/PurchaseOrdersPanel.tsx`, mounted as a tab, deleted dead `frontend/` tree, 457/457 frontend tests | **CONFIRMED.** `components/itam/PurchaseOrdersPanel.tsx` (269 lines) is a real CRUD component (list/create/edit/delete, computed totals, item rows), imported and rendered in `ITAMConsole.tsx:126` behind the `purchaseOrders` tab (`ITAMConsole.tsx:41`), with i18n labels in `itamI18n.tsx`, types in `types.ts` (`ItamPurchaseOrder`, `ItamPurchaseOrderItem`), and 4 `authFetch`-based functions in `apiService.ts:5984-6015`. `frontend/` directory confirmed deleted (`ls frontend/` → not found). Re-ran `npx vitest run` independently: **457 passed (457)**, matching the claim exactly. Re-ran `npm run build`: succeeded, `ITAMConsole-*.js` bundle present. `src/__tests__/PurchaseOrdersPanel.test.tsx` has 7 substantive behavioral tests (list, empty state, create with computed total, item add/remove, edit, delete, delete-error-toast) — not a stub. |
| 2 — T-71-04 validation | `update_asset_purchase` 400s on unresolvable `purchase_order_id`, 2 new tests pass | **CONFIRMED for validation; NOT confirmed for visibility.** `backend/itam_finance_endpoints.py:90-101` now looks up `db.purchase_orders.find_one({"id": ...})` (tenant-scoped via the `db` handle) and 400s if absent. Ran `test_itam_finance.py`: 22 passed. But the truth's second clause — "this link is visible in the asset detail view" — has zero supporting code anywhere in the reachable frontend (exhaustive grep across `components/`, `services/apiService.ts`, `types.ts` for `purchase_order_id`/`purchaseOrderId` found only the two backend model declarations). Kept as a gap — see above. |
| 3 — SC5 notifications | `itam.asset_request_status` added to `VALID_EVENTS` and `RuleCreate` Literal, 2 new tests | **CONFIRMED.** `backend/notification_service.py:481` and `backend/notification_endpoints.py:30` both list `"itam.asset_request_status"`. `tests/test_notification_service.py` contains the two claimed tests (`test_can_create_rule_for_asset_request_event`-style and a full `send_notification` round-trip). Ran the file: passes. |
| 4 — Orphaned modules deleted | `itam_scheduled_tasks.py`, `itam_asset_service.py` + tests deleted, full suite clean | **CONFIRMED.** Neither file exists on disk. `grep -rn "itam_scheduled_tasks\|itam_asset_service" backend --include="*.py"` (excluding `__pycache__`) returns zero hits — no dangling importer anywhere. `python -c "import app"` succeeds without error, confirming no broken import chain from the deletion. |
| 5 — Wire-shape bug | `response_model_by_alias=False` on all 4 PurchaseOrder routes | **CONFIRMED.** `grep -n "response_model_by_alias" backend/itam_procurement_endpoints.py` shows it present on all 4 routes (create/get/list/update) at lines 27, 45, 61, 76. |

**Net finding:** 4 of the addendum's 5 gap-closures are genuinely, fully closed. The 5th (Gap 2 / T-71-04) is half-closed — the addendum's own prose honestly discloses this in its "Residual, consciously not fixed" section, but its re-run truths table and final score then contradict that disclosure by marking the truth "✓ VERIFIED" and rolling it into "12/12". This verification corrects that: the truth is scored as a gap, because its own wording explicitly requires visibility, not just backend safety.

## Goal Achievement

### Observable Truths

Merged from ROADMAP.md Success Criteria and the `must_haves.truths` blocks of 71-01, 71-02, 71-03.

| # | Truth | Source | Status | Evidence |
|---|-------|--------|--------|----------|
| 1 | User can track purchase order details and supplier information | SC1 | ✓ VERIFIED | `PurchaseOrdersPanel` reachable via its own console tab; full CRUD backed by `authFetch` calls to registered, tenant-isolated backend routes. |
| 2 | Purchase orders can be created and persisted through the API | 71-01 | ✓ VERIFIED | `itam_procurement_service.create_purchase_order` sets explicit `id`; 8 service + 9 endpoint tests pass (re-ran independently). |
| 3 | User can view a list of all purchase orders | 71-01 | ✓ VERIFIED | `PurchaseOrdersPanel` list view, confirmed by `fetchPurchaseOrders` wiring and passing component test. |
| 4 | User can view the details of a specific purchase order | 71-01 | ✓ VERIFIED | Edit modal in `PurchaseOrdersPanel` pre-fills and displays full PO detail; confirmed by test. |
| 5 | An asset can be linked to a purchase order, and the link is visible in the asset detail view | 71-01 tracer | ✗ FAILED | Validation exists and is tenant-scoped (T-71-04 fixed). Visibility does not exist anywhere in the reachable frontend — see Gaps. |
| 6 | User can track warranty expiry and receive automated alerts | SC2 | ✓ VERIFIED | Reachable via `FinancePanel.tsx` → `GET /api/assets/{id}/warranty`; sweep registered at `app_startup.py:642-644` (Phase 59 mechanism, unaffected by this session's changes — regression-checked: `test_itam_finance_warranty.py`, `test_itam_finance_sweep*.py` all pass). |
| 7 | Assets can store warranty expiry dates | 71-02 | ✓ VERIFIED | `warranty_expiry_date` on `Asset` model, persisted via existing routes. |
| 8 | User can view straight-line depreciation | SC3 | ✓ VERIFIED | `FinancePanel.tsx` renders `bookValueCents` from `compute_book_value` (Phase 59); regression-checked via `test_itam_finance_bookvalue.py` (20 tests pass). |
| 9 | User can see warranty and depreciation information for an asset in the UI | 71-02 | ✓ VERIFIED | Finance tab's "Warranty & Book Value" section is the reachable surface, unchanged and unaffected by this phase's other fixes. |
| 10 | User can request an asset and follow the approval workflow | SC4 | ✓ VERIFIED | `RequestsPanel.tsx` confirmed still present and mounted (`ITAMConsole.tsx:127`); regression-checked, no changes since original pass. |
| 11 | Approvers can view and act on the queue; workflow enforces a real state machine and RBAC boundary | 71-03 | ✓ VERIFIED | Unchanged from original pass; 8+10 asset-request tests re-ran and pass. |
| 12 | User receives email/Slack notifications for asset lifecycle events | SC5 | ✓ VERIFIED | `itam.asset_request_status` now registered in `VALID_EVENTS` and `RuleCreate` Literal — confirmed by grep and passing regression tests exercising a real rule-creation + `send_notification` round trip. |

**Score:** 11/12 truths verified. 1 failed (partial — validation done, visibility not done). 0 present-behavior-unverified.

**Success-criteria roll-up:** SC1 ✓, SC2 ✓, SC3 ✓, SC4 ✓, SC5 ✓ — **all 5 ROADMAP success criteria are now met.** The one remaining failed truth is a plan-level (71-01) must-have that adds scope beyond the roadmap's SC1 wording (SC1 only requires PO/supplier tracking generally, which now works); it does not itself block any of the 5 ROADMAP success criteria, consistent with the addendum's own "Neither blocks any ROADMAP success criterion" note.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `components/itam/PurchaseOrdersPanel.tsx` | PO list/create/edit/delete UI | ✓ VERIFIED | 269 lines, real state + CRUD calls, mounted in `ITAMConsole.tsx`. |
| `backend/itam_procurement_endpoints.py` | PO routes, correct wire shape | ✓ VERIFIED | `response_model_by_alias=False` on all 4 response routes. |
| `backend/itam_finance_endpoints.py` | Validated asset↔PO link | ⚠️ PARTIAL | Validation present and tested; no consumer reads the field for display. |
| `backend/notification_service.py`, `notification_endpoints.py` | Asset-request event routable | ✓ VERIFIED | `itam.asset_request_status` in both `VALID_EVENTS` and `RuleCreate` Literal. |
| `backend/itam_scheduled_tasks.py`, `backend/itam_asset_service.py` | (previously orphaned) | ✓ DELETED, confirmed clean | No file, no dangling importer, `import app` succeeds. |
| `components/itam/RequestsPanel.tsx` | Request submit + approval queue | ✓ VERIFIED (regression) | Unchanged, still mounted, still passing tests. |
| `components/itam/FinancePanel.tsx` | Warranty + book-value display | ✓ VERIFIED (regression) | Unchanged, still the reachable SC2/SC3 surface. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `ITAMConsole.tsx` | `PurchaseOrdersPanel.tsx` | `purchaseOrders` tab | ✓ WIRED | Import + `{tab === 'purchaseOrders' && <PurchaseOrdersPanel />}` (`ITAMConsole.tsx:126`) |
| `PurchaseOrdersPanel.tsx` | `/api/v1/itam/purchase-orders` | `apiService` `authFetch` fns | ✓ WIRED | `apiService.ts:5984-6015`, all four consumed and using auth |
| `itam_finance_endpoints.update_asset_purchase` | `db.purchase_orders` | tenant-scoped existence check | ✓ WIRED | `itam_finance_endpoints.py:90-101` |
| `Asset.purchase_order_id` | any UI surface | display | ✗ NOT_WIRED | Zero references outside backend model declarations and the validation check itself |
| `notification_endpoints.RuleCreate` | `notification_service.VALID_EVENTS` | shared event vocabulary | ✓ WIRED | Both list `itam.asset_request_status`; confirmed via passing round-trip test |
| `app.py` startup | `backend/itam_scheduled_tasks.py` | — | N/A (deleted) | Confirmed no import references this module anywhere |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase-71 backend regression (procurement, asset-request, notification, finance) | `pytest tests/test_itam_procurement_{service,endpoints}.py tests/test_itam_asset_request_{service,endpoints}.py tests/test_notification_service.py tests/test_itam_finance.py -q` | `67 passed` | ✓ PASS |
| Finance regression (unaffected by this session, confirm no breakage) | `pytest tests/test_itam_finance_bookvalue.py tests/test_itam_finance_warranty.py tests/test_itam_finance_sweep.py tests/test_itam_finance_sweep_resilience.py -q` | `72 passed` | ✓ PASS |
| Backend app import (confirms orphan deletion left no dangling refs) | `python -c "import app"` | Loads cleanly, all routers initialize | ✓ PASS |
| Frontend full suite | `npx vitest run` | `457 passed (457)` | ✓ PASS |
| Frontend production build | `npm run build` | `✓ built in 4.42s`, `ITAMConsole-*.js` bundle present | ✓ PASS |
| Asset-PO link visibility | `grep -rn "purchase_order_id\|purchaseOrderId" components/ services/apiService.ts types.ts` | 0 matches | ✗ FAIL (confirms gap) |
| Dangling refs to deleted orphan modules | `grep -rn "itam_scheduled_tasks\|itam_asset_service" backend --include="*.py"` | 0 matches | ✓ PASS |
| Debt-marker scan (TBD/FIXME/XXX) on gap-closure files | `grep -nE "TBD\|FIXME\|XXX"` across 8 touched files | 0 matches | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| ITAM-PRO-01 | 71-01 | Purchase Order, Cost, and Supplier tracking | ✓ SATISFIED | Backend CRUD + reachable `PurchaseOrdersPanel` UI, tenant-isolated, correct wire shape, 17 backend + 7 frontend tests pass. The asset↔PO *display* link remains a residual gap (see truth #5) but is not part of this requirement's literal wording. |
| ITAM-PRO-02 | 71-02 | Warranty tracking + automated alerts | ✓ SATISFIED (via Phase 59) | Reachable and working through `FinancePanel` + the Phase 59 sweep; regression-confirmed unaffected by this session. |
| ITAM-PRO-03 | 71-02 | Straight-line depreciation modeling | ✓ SATISFIED (via Phase 59) | Reachable via `FinancePanel` + `compute_book_value`; regression-confirmed. |
| ITAM-PRO-04 | 71-03 | Asset Request + Approval Workflow | ✓ SATISFIED | End-to-end reachable, RBAC-correct, regression-confirmed, real browser UAT recorded in 71-03-SUMMARY.md. |
| ITAM-PRO-05 | 71-03 | Alerts/Notifications (Email/Slack) | ✓ SATISFIED | `itam.asset_request_status` now routable to Slack/email channels alongside warranty events; confirmed via code and passing round-trip test. |

`.planning/REQUIREMENTS.md:67-71` marks all five ITAM-PRO requirements "Complete" — this is now accurate; git history confirms `61da37332` corrected ITAM-PRO-04/05 from "Pending" to "Complete" as part of the same gap-closure session, and ITAM-PRO-01 is independently confirmed satisfied above.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/itam_procurement_endpoints.py` | 41 | `except Exception` → 500 around create | ⚠️ Warning | Pre-existing, unchanged by this session; same class 71-03 fixed for asset requests but not applied here. Not a gap-closure regression. |
| `Asset.purchase_order_id` field | `itam_models.py:152,287` | Write-only field, no display consumer | ⚠️ Warning | Root cause of the remaining gap (truth #5). |

No `TBD`, `FIXME`, or `XXX` debt markers found in any file touched by the gap-closure session.

### Human Verification Required

None. All findings in this pass were independently confirmed via direct code inspection, grep, and passing automated test runs (backend pytest, frontend vitest, production build) — no claim required a live server or browser session to adjudicate.

### Gaps Summary

This re-verification independently confirms that 4 of the 5 gaps recorded in the original 2026-08-24 pass are genuinely, fully closed: the Purchase Orders UI is real and reachable (not a stub — 269 lines, 7 substantive tests, mounted as a live tab, full 457/457 frontend suite and clean build independently re-run), the two orphaned backend modules are deleted with zero dangling references, the notification event vocabulary gap is closed with a passing round-trip test, and the wire-shape bug is fixed on all 4 routes.

The 5th gap (T-71-04 / asset-PurchaseOrder link) is only half-closed. The security-relevant half — tenant-scoped existence validation on `purchase_order_id` — is genuinely fixed and tested. But the original must-have truth from 71-01-PLAN.md explicitly reads "...and this link is visible in the asset detail view," and that half was never built: an exhaustive grep across every reachable frontend file finds zero references to `purchase_order_id`/`purchaseOrderId`. The addendum's own prose disclosed this honestly under "Residual, consciously not fixed," but its re-run truths table and final "12/12" score then contradicted that disclosure by marking the truth fully verified. This report corrects that inconsistency: the truth is scored as a gap.

This is a small, well-understood gap — closing it requires only a display surface (e.g., a column or badge on an existing asset-facing panel showing the linked PO's `order_number`), not new backend work. It does not block any of the 5 ROADMAP success criteria, all of which are now independently confirmed met. Given the addendum's explicit, disclosed decision to defer this and its narrow scope, this is a strong candidate for a human-accepted override rather than a blocking closure plan — see suggestion below.

**This looks intentional.** To accept this deviation, add to VERIFICATION.md frontmatter:

```yaml
overrides:
  - must_have: "An asset can be linked to a purchase order, and this link is visible in the asset detail view"
    reason: "Tenant-scoped validation (T-71-04) is implemented and tested; only the UI display of the link was deferred. The real console has no per-asset detail-page surface to host this on without new design work, and the gap does not block any ROADMAP success criterion."
    accepted_by: "{name}"
    accepted_at: "{ISO timestamp}"
```

---

_Verified: 2026-08-25_
_Verifier: Claude (gsd-verifier)_
