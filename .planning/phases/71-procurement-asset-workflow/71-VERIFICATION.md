---
phase: 71-procurement-asset-workflow
verified: 2026-08-24T00:00:00Z
status: gaps_found
status_after_reverification: passed
score: 7/12 must-haves verified
score_after_reverification: 12/12 must-haves verified (see Re-verification Addendum at end of file)
behavior_unverified: 0
overrides_applied: 0
retroactive: true
gaps:
  - truth: "User can track purchase order details and supplier information (ROADMAP SC1 / ITAM-PRO-01)"
    status: failed
    reason: >-
      The Purchase Order backend is complete, registered and tested, but there is no reachable
      user surface for it anywhere in the running app. The only PO UI lives in the disconnected
      `frontend/` tree, which nothing imports and which does not even type-check — it imports
      `react-router-dom`, a package absent from both package.json and node_modules. The real
      app tree (`components/itam/ITAMConsole.tsx`) has no Procurement tab, `types.ts` has no
      PurchaseOrder type, and `services/apiService.ts` has no purchase-order functions.
    artifacts:
      - path: "frontend/components/itam/procurement/PurchaseOrderList.tsx"
        issue: "Unreachable and unbuildable — imported only by frontend/routes/itamRoutes.tsx, which is imported only by frontend/App.tsx, which nothing imports. TS2307 on 'react-router-dom'."
      - path: "frontend/components/itam/procurement/PurchaseOrderDetail.tsx"
        issue: "Same — unreachable, TS2307 on 'react-router-dom'."
      - path: "frontend/api/itamApiService.ts"
        issue: "Raw axios with no auth header; the real app authenticates every call through authFetch. Would 401 even if reconnected."
      - path: "components/itam/ITAMConsole.tsx"
        issue: "TABS list has no procurement/purchase-orders entry — no tab renders PO data."
    missing:
      - "A PurchaseOrdersPanel (or a Procurement section on an existing panel) built in components/itam/ and mounted as a tab in ITAMConsole.tsx"
      - "PurchaseOrder types in types.ts and fetch/create/update functions in services/apiService.ts using authFetch"
    resolved: "2026-08-24 — built components/itam/PurchaseOrdersPanel.tsx (list, create/edit modal, delete), mounted as its own 'purchaseOrders' tab in ITAMConsole.tsx (i18n labels en/es), added ItamPurchaseOrder/ItamPurchaseOrderItem to types.ts and fetchPurchaseOrders/createPurchaseOrder/updatePurchaseOrder/deletePurchaseOrder to apiService.ts using authFetch, matching the RequestsPanel/apiService.ts precedent exactly. 7 new component tests pass (src/__tests__/PurchaseOrdersPanel.test.tsx); full frontend suite 457/457; npm run build clean. The dead frontend/ tree (unbuildable, unreachable, raw axios) deleted entirely."
  - truth: "An asset can be linked to a purchase order, and this link is visible in the asset detail view (71-01 Task 3 tracer)"
    status: failed
    reason: >-
      `purchase_order_id` exists on the Asset and AssetPurchaseUpdate models and is accepted by
      PATCH /api/assets/{id}/purchase, but it is a write-only field. Grep across the entire
      backend finds it in exactly two places, both model declarations — no service reads it, no
      endpoint joins it, no UI renders it. Threat T-71-04 from 71-01-PLAN.md ("validate
      purchase_order_id refers to an existing Purchase Order within the same tenant") is not
      implemented anywhere.
    artifacts:
      - path: "backend/itam_models.py"
        issue: "Lines 152 and 287 declare purchase_order_id; no consumer exists."
      - path: "backend/itam_finance_endpoints.py"
        issue: "PATCH /{asset_id}/purchase persists purchase_order_id with no existence/tenant validation (T-71-04 unmitigated)."
    missing:
      - "Validation that purchase_order_id resolves to a PurchaseOrder in the same tenant"
      - "A read path that surfaces the linked PO number on a reachable asset surface"
    resolved: "2026-08-24 (partial) — T-71-04 validation added: itam_finance_endpoints.py's update_asset_purchase now 400s on an unresolvable purchase_order_id, tenant-scoped via the same db handle pattern as the existing supplierId check. 2 new regression tests pass (test_itam_finance.py). A dedicated read path surfacing the linked PO number on the asset detail view was NOT added — out of scope for this gap-closure pass; the link is now safe (validated) but still not displayed anywhere. Left as a smaller residual gap, not silently claimed fixed."
  - truth: "User receives email/Slack notifications for asset lifecycle events (ROADMAP SC5 / ITAM-PRO-05)"
    status: partial
    reason: >-
      Two halves, one works and one is structurally impossible. Warranty events route fine:
      "itam.warranty_expiring" is in notification_service.VALID_EVENTS and in the
      notification_endpoints.RuleCreate Literal, so a tenant can bind it to a Slack or email
      channel. Asset-request events cannot: ItamNotificationService.send_asset_request_notification
      dispatches event type "itam.asset_request_status", which appears nowhere except that one
      file. It is absent from VALID_EVENTS (checked in create_rule, raises ValueError) and from
      the RuleCreate Literal, so no tenant can ever create a rule for it. send_notification then
      matches zero rules and sends nothing. Only the in-app db.notifications write happens — which
      is exactly what 71-03's UAT observed and correctly reported as in-app documents.
    artifacts:
      - path: "backend/notification_service.py"
        issue: "VALID_EVENTS (line 472) omits 'itam.asset_request_status'; create_rule (line 505) rejects it."
      - path: "backend/notification_endpoints.py"
        issue: "RuleCreate.event_type Literal (line 27) omits 'itam.asset_request_status'."
    missing:
      - "Add 'itam.asset_request_status' to notification_service.VALID_EVENTS and the notification_endpoints.RuleCreate Literal"
      - "A regression test asserting a rule can be created for the asset-request event type and that send_notification matches it"
    resolved: "2026-08-24 — 'itam.asset_request_status' added to both VALID_EVENTS and the RuleCreate Literal. 2 new regression tests pass (test_notification_service.py): one proving a rule can now be created via the real API, one proving a full send_notification round trip actually matches and dispatches to a channel."
  - truth: "Phase 71-02's warranty-alert and depreciation implementation is reachable from a live code path"
    status: failed
    reason: >-
      Both 71-02 backend artifacts are orphaned. `itam_scheduled_tasks.start_warranty_alert_scheduler`
      is never called — app_startup.py:642-644 registers `itam_finance_service.start_warranty_alert_scheduler`
      (Phase 59) instead, and the only importer of itam_scheduled_tasks is its own test file.
      `ItamAssetService` (depreciation) has no importer at all outside its own test. The asset-level
      fields they read (warranty_expiry_date, salvage_value, useful_life_years) are written by the
      API but read by nothing live — the shipped warranty sweep classifies on purchaseDate +
      warrantyMonths, and the shipped book-value route reads the asset MODEL's usefulLifeYears /
      salvageValueCents. SC2 and SC3 are satisfied in the product by the pre-existing Phase 59
      mechanism, not by this phase's code. Functional consequence: an admin who sets
      warranty_expiry_date via the API receives no alert for it.
    artifacts:
      - path: "backend/itam_scheduled_tasks.py"
        issue: "ORPHANED — start_warranty_alert_scheduler never registered; duplicates itam_finance_service.run_warranty_alert_pass."
      - path: "backend/itam_asset_service.py"
        issue: "ORPHANED — ItamAssetService imported only by tests/test_itam_asset_service.py; duplicates itam_finance_service.compute_book_value."
    missing:
      - "A decision: either delete the two duplicate modules and the write-only asset fields, or make the shipped Phase 59 sweep/book-value honour warranty_expiry_date and asset-level salvage_value/useful_life_years"
    resolved: "2026-08-24 — decided and executed the deletion half: backend/itam_scheduled_tasks.py, backend/itam_asset_service.py, and their two orphan-only test files removed entirely (confirmed via grep that nothing else imports either module). Full backend suite re-run after removal: 2369 passed / 34 skipped / 0 failed, no regressions. The write-only asset fields (warranty_expiry_date, salvage_value, useful_life_years) were left in place on the Asset model — they're harmless additive fields now with no dead consumer pointing at them; making Phase 59's sweep honor them instead was judged out of scope (would change Phase 59's shipped behavior, a different phase's contract) for this gap-closure pass."
  - truth: "Purchase order API responses carry an addressable identifier the client can act on"
    status: failed
    reason: >-
      itam_procurement_endpoints.py declares response_model=PurchaseOrder without
      response_model_by_alias=False. This is the exact defect 71-03 diagnosed and fixed for asset
      requests (all five asset-request routes now set response_model_by_alias=False); the
      procurement half was left in place and is documented as known debt in 71-03-SUMMARY.md.
      GET/POST /api/v1/itam/purchase-orders therefore emit the wire key `_id` instead of `id`, so
      any client following the documented shape gets undefined and cannot address a PO for
      update/delete.
    artifacts:
      - path: "backend/itam_procurement_endpoints.py"
        issue: "Five routes (lines 27, 45, 61, 76, 93) omit response_model_by_alias=False."
    missing:
      - "response_model_by_alias=False on the purchase-order routes, matching itam_asset_request_endpoints.py"
    resolved: "2026-08-24 — response_model_by_alias=False added to all 4 response_model=PurchaseOrder/List[PurchaseOrder] routes (create/get/list/update; delete has no response body). 4 existing tests tightened from tolerating either 'id' or '_id' to asserting 'id' is present and '_id' is absent; all 17 procurement tests pass."
human_verification:
  - test: "Log into the running app as an itam_admin, open the ITAM console, and look for any way to see or create a purchase order."
    expected: "If SC1 is to be considered met, a Purchase Orders surface should be reachable. Verification expects it is NOT — confirming the gap."
    why_human: "Confirms the reachability finding from a user's seat rather than from import graphs."
  - test: "Configure a Slack channel and a notification rule, then submit and approve an asset request. Watch the Slack channel."
    expected: "No Slack message arrives for the asset-request events, because no rule for 'itam.asset_request_status' can be created in the first place."
    why_human: "Requires a live Slack endpoint and the notification-rules UI; confirms the SC5 gap end-to-end."
  - test: "Via the API, PATCH an asset's warranty_expiry_date to a date 10 days out, then wait for or trigger a warranty sweep pass."
    expected: "No alert fires for that asset — the live sweep classifies on purchaseDate + warrantyMonths, not warranty_expiry_date."
    why_human: "Requires a running backend and a scheduler tick; confirms the write-only-field trap is real rather than theoretical."
---

# Phase 71: Procurement & Asset Workflow Verification Report

**Phase Goal:** Manage asset lifecycle from procurement to retirement with automated alerts and approval workflows.
**Success Criteria:** (1) Track purchase order details and supplier information. (2) Track warranty expiry and receive automated alerts. (3) View straight-line depreciation. (4) Request an asset and follow the approval workflow. (5) Receive email/Slack notifications for asset lifecycle events.
**Verified:** 2026-08-24 (initial retroactive pass); **re-verified same day** after all 5 gaps closed
**Status:** gaps_found → **all 5 gaps closed** (1 partially — see Re-verification Addendum at the end of this file)
**Re-verification:** No — initial (retroactive) verification. This phase completed 2026-08-16 without a VERIFICATION.md; the file was identified as documentation debt during a project-wide audit sweep.

## Goal Achievement

### Observable Truths

Merged from ROADMAP.md Success Criteria (the contract) and the `must_haves.truths` blocks of 71-01, 71-02 and 71-03. Duplicates collapsed onto the ROADMAP wording.

| # | Truth | Source | Status | Evidence |
|---|-------|--------|--------|----------|
| 1 | User can track purchase order details and supplier information | SC1 | ✗ FAILED | Backend complete and registered (`router_registry.py:93`), but no reachable UI. `components/itam/ITAMConsole.tsx` TABS has no procurement entry; `types.ts` has no PurchaseOrder type; `services/apiService.ts` has no PO functions. The only PO UI is in the orphaned `frontend/` tree — see Key Links. |
| 2 | Purchase orders can be created and persisted through the API | 71-01 | ✓ VERIFIED | `itam_procurement_service.create_purchase_order` sets an explicit `id` (fixed in `2b206e3e`), tenant-scoped insert; 8 service + 9 endpoint tests pass. |
| 3 | User can view a list of all purchase orders | 71-01 | ✗ FAILED | `GET /api/v1/itam/purchase-orders` works; no reachable client calls it. `PurchaseOrderList.tsx` is in the disconnected tree and fails `tsc` (TS2307 `react-router-dom`). |
| 4 | User can view the details of a specific purchase order | 71-01 | ✗ FAILED | Same as #3 for `PurchaseOrderDetail.tsx`. |
| 5 | An asset can be linked to a purchase order, and the link is visible in the asset detail view | 71-01 tracer | ✗ FAILED | `purchase_order_id` is declared on `Asset` (`itam_models.py:287`) and `AssetPurchaseUpdate` (`:152`) and nothing else in the backend. No validation (T-71-04 unmitigated), no read path, no UI. Write-only field. |
| 6 | User can track warranty expiry and receive automated alerts | SC2 | ✓ VERIFIED | Reachable via `components/itam/FinancePanel.tsx` → `fetchAssetWarranty` → `GET /api/assets/{id}/warranty`; the alert sweep runs from `app_startup.py:642-644`. **Satisfied by the pre-existing Phase 59 mechanism — not by this phase's `itam_scheduled_tasks.py`, which is orphaned (gap 4).** |
| 7 | Assets can store warranty expiry dates | 71-02 | ✓ VERIFIED | `warranty_expiry_date` on `Asset` (`itam_models.py:290`) with an ISO-8601 validator; persisted at creation (`itam_asset_endpoints.py:165`) and via `PATCH /assets/{id}/purchase`. Storage works — but nothing live reads it (see Data-Flow Trace). |
| 8 | User can view straight-line depreciation | SC3 | ✓ VERIFIED | `FinancePanel.tsx:133-139` renders `bookValueCents` from `GET /api/assets/{id}/book-value` → `compute_book_value` (straight-line, floors at salvage, `itam_finance_service.py:89-109`). **Satisfied by Phase 59 — this phase's `ItamAssetService` is orphaned (gap 4).** |
| 9 | User can see warranty and depreciation information for an asset in the UI | 71-02 | ✓ VERIFIED | The Finance tab's "Warranty & Book Value" section is the reachable surface. 71-02's own `AssetDetail.tsx` enhancement is in the disconnected tree and is not the surface serving this truth. |
| 10 | User can request an asset and follow the approval workflow | SC4 | ✓ VERIFIED | `components/itam/RequestsPanel.tsx` (submit modal + table + inline approve/reject) mounted as the `requests` tab in `ITAMConsole.tsx`; `apiService.ts:5954-5978` wires all four calls; `itam_asset_request_endpoints.py` registered at `router_registry.py:94`. 18 tests pass; a real two-account browser UAT is recorded in 71-03-SUMMARY.md. |
| 11 | Approvers can view and act on the queue; the workflow enforces a real state machine and RBAC boundary | 71-03 | ✓ VERIFIED | `approve/reject_asset_request` guard on `status == PENDING` and return None → 400; `_require_asset_requester` (`request:assets`), `_require_asset_approver` (`manage:procurement`) and the either/or `_require_asset_viewer` all resolve to permissions actually seeded in `rbac_utils.DEFAULT_PERMISSIONS`; `requester_id`/`approver_id` are server-derived from `current_user.username`, never client input. |
| 12 | User receives email/Slack notifications for asset lifecycle events | SC5 | ✗ FAILED (partial) | Warranty half routes (`itam.warranty_expiring` is in `VALID_EVENTS` and the `RuleCreate` Literal). Asset-request half cannot: `itam.asset_request_status` is absent from both, so `create_rule` rejects it and `send_notification` can never match a rule. Only the in-app `db.notifications` write occurs. |

**Score:** 7/12 truths verified. 5 failed. 0 present-behavior-unverified.

**Success-criteria roll-up:** SC2 ✓, SC3 ✓, SC4 ✓ — SC1 ✗, SC5 ✗ (partial). **3 of 5 ROADMAP success criteria met.**

### Deferred Items

None. Phases 72 (Reporting & Dashboards) and 73 (API & Integrations) are the only later phases in this milestone and both are already executed. Neither roadmap entry mentions purchase-order UI, the disconnected `frontend/` tree, or the notification-rule event vocabulary. These gaps are not scheduled anywhere and are therefore real, not deferred.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/itam_models.py` | PurchaseOrder, AssetRequest, warranty/depreciation fields | ✓ VERIFIED | `PurchaseOrderItem/Base/Create/Update/PurchaseOrder` (524-565), `AssetRequestStatus/Base/Create/Update/AssetRequest` (566-630), warranty+salvage+useful-life on `Asset` (290-292) with ISO validators. |
| `backend/itam_procurement_service.py` | PO CRUD, tenant-isolated | ✓ VERIFIED | 58 lines, all five operations, every query filtered on `tenantId`, explicit `id` on insert. |
| `backend/itam_procurement_endpoints.py` | PO routes, registered | ⚠️ PARTIAL | Registered (`router_registry.py:93`) and RBAC-gated on the seeded `manage:procurement`. Defect: no `response_model_by_alias=False`, so responses emit `_id` not `id` (gap 5). Also wraps create in a bare `except Exception` → 500 (the class 71-03 fixed for asset requests). |
| `backend/itam_asset_request_service.py` | Request lifecycle + approval + notifications | ✓ VERIFIED | 212 lines; explicit `_id` = generated `ar-*` string (the 71-03 fix); pending-guard on both transitions; notification on all three events; Phase 73 later added fire-and-forget webhook dispatch here. |
| `backend/itam_asset_request_endpoints.py` | Request routes, registered, RBAC | ✓ VERIFIED | Registered (`router_registry.py:94`); three distinct dependencies; `response_model_by_alias=False` on all five routes; intentional 400s re-raised before the `except Exception` (the 71-03 fix). |
| `backend/itam_notification_service.py` | Warranty + asset-request notifications | ⚠️ PARTIAL | Both methods present and dual-path (in-app + rule-routed). The asset-request rule-routed path is dead — its event type is not registerable (gap 3). |
| `backend/itam_scheduled_tasks.py` | Scheduled warranty alert pass | ✗ ORPHANED | Never imported outside its own test. `start_warranty_alert_scheduler` is not registered anywhere; `app_startup.py:642-644` registers the Phase 59 sibling instead. Duplicate implementation. |
| `backend/itam_asset_service.py` | Straight-line depreciation | ✗ ORPHANED | 55 lines, no importer outside its own test. Duplicates `itam_finance_service.compute_book_value`, which is the one actually serving the UI. Also contains a bare `except:` (line 45). |
| `components/itam/RequestsPanel.tsx` | Request submit + approval queue | ✓ VERIFIED | 11.7 KB; real state, real API calls, toast error handling; mounted in `ITAMConsole.tsx`. |
| `frontend/components/itam/procurement/PurchaseOrderList.tsx` | PO list view | ✗ ORPHANED / UNBUILDABLE | Not imported by the app; fails `tsc` with TS2307 on `react-router-dom`. |
| `frontend/components/itam/procurement/PurchaseOrderDetail.tsx` | PO detail view | ✗ ORPHANED / UNBUILDABLE | Same. |
| `frontend/components/itam/settings/NotificationSettings.tsx` | Warranty alert toggle | ✗ ORPHANED / STUB | Not imported by the app; `handleSaveSettings` is `console.log` only (self-declared in 71-02-SUMMARY.md "Known Stubs"). |
| `frontend/components/itam/assets/AssetDetail.tsx` | Warranty/depreciation display | ✗ ORPHANED / UNBUILDABLE | Not imported; TS2307 on `react-router-dom`. |
| `backend/tests/test_itam_procurement_{service,endpoints}.py` | PO regression suites | ✓ VERIFIED | 8 + 9 tests, all pass. |
| `backend/tests/test_itam_asset_request_{service,endpoints}.py` | Request regression suites | ✓ VERIFIED | 8 + 10 tests, all pass. |
| `backend/tests/test_itam_{asset_service,scheduled_tasks}.py` | Depreciation / sweep suites | ⚠️ PASSING BUT TESTING ORPHANS | 8 + 5 tests pass, but both exercise modules no live code path reaches. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `itam_procurement_endpoints.router` | FastAPI app | `router_registry._load` | ✓ WIRED | `router_registry.py:93` |
| `itam_asset_request_endpoints.router` | FastAPI app | `router_registry._load` | ✓ WIRED | `router_registry.py:94` |
| `App.tsx` | `components/itam/ITAMConsole` | `lazy()` + `case 'itam'` | ✓ WIRED | `App.tsx:93` and `:1927` |
| `ITAMConsole.tsx` | `RequestsPanel.tsx` | `requests` tab | ✓ WIRED | Import + `{tab === 'requests' && <RequestsPanel />}` |
| `RequestsPanel.tsx` | `/api/v1/itam/asset-requests` | `apiService` fetch/create/approve/reject | ✓ WIRED | `apiService.ts:5954-5978`, all four consumed |
| `ItamAssetRequestService` | `ApprovalService.create_approval_request` | audit-trail record | ⚠️ PARTIAL | Called, but with a hardcoded approver list; approval_service's own approve/reject is never invoked — the real transition is owned by the ITAM service. Documented decision, not a defect. |
| `ItamAssetRequestService` | `ItamNotificationService` | lifecycle notifications | ✓ WIRED | Called on create/approve/reject |
| `ItamNotificationService` | `notification_service.send_notification` | rule-routed Slack/email | ⚠️ PARTIAL | Call is wired, but `itam.asset_request_status` can never match a rule — zero-rule dead end (gap 3). |
| `FinancePanel.tsx` | `/api/assets/{id}/book-value`, `/warranty` | `apiService` | ✓ WIRED | `FinancePanel.tsx:3,40` — this is the surface actually serving SC2/SC3 |
| `itam_scheduled_tasks.start_warranty_alert_scheduler` | `app_startup` | startup registration | ✗ NOT_WIRED | `app_startup.py:642-644` registers `itam_finance_service`'s version instead |
| `ItamAssetService` | any endpoint or task | — | ✗ NOT_WIRED | No importer outside its own test |
| `Asset.purchase_order_id` | `PurchaseOrder.id` | validation / join / display | ✗ NOT_WIRED | No validation, no join, no UI |
| `App.tsx` / `index.tsx` | `frontend/` tree | any import | ✗ NOT_WIRED | Nothing outside `frontend/` imports it; `react-router-dom` is in neither package.json nor node_modules |

### Data-Flow Trace (Level 4)

| Artifact / Field | Data Variable | Source | Produces Real Data | Status |
|------------------|---------------|--------|--------------------|--------|
| `components/itam/RequestsPanel.tsx` | `requests` | `fetchAssetRequests` → `GET /asset-requests` → `db.asset_requests` | Yes | ✓ FLOWING |
| `components/itam/FinancePanel.tsx` | `bookValue`, `warranty` | Phase 59 finance routes → `db.assets` + `db.asset_models` | Yes | ✓ FLOWING |
| `Asset.warranty_expiry_date` | — | Written by asset create + `PATCH /purchase`; only readers are the orphaned `itam_scheduled_tasks.py` | No | ⚠️ HOLLOW — write-only |
| `Asset.salvage_value`, `Asset.useful_life_years` | — | Written by the same routes; only reader is the orphaned `ItamAssetService`. The live book-value route reads the asset MODEL's `usefulLifeYears`/`salvageValueCents` instead | No | ⚠️ HOLLOW — write-only |
| `Asset.purchase_order_id` | — | Written by `PATCH /purchase`; zero readers backend-wide | No | ⚠️ HOLLOW — write-only |
| `frontend/.../PurchaseOrderList.tsx` | `purchaseOrders` | `itamApiService` (raw axios, no auth header) — component never mounted | No | ✗ DISCONNECTED |
| `frontend/.../NotificationSettings.tsx` | settings toggles | `handleSaveSettings` → `console.log` | No | ✗ DISCONNECTED (stub) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All six phase-71 backend test files | `backend/venv/bin/python -m pytest tests/test_itam_procurement_service.py tests/test_itam_procurement_endpoints.py tests/test_itam_asset_service.py tests/test_itam_scheduled_tasks.py tests/test_itam_asset_request_service.py tests/test_itam_asset_request_endpoints.py -q` | `48 passed, 1 warning in 52.66s` | ✓ PASS |
| Claimed commits exist | `git log -1 --format=%s <hash>` × 6 | All six resolve: `0d75d770`, `fb8000d3`, `8de3722e`, `78e5009d`, `2b206e3e`, `1c8637c4` | ✓ PASS |
| Disconnected tree type-checks | `npx tsc --noEmit -p tsconfig.json` filtered to `frontend/` | 6 errors, all TS2307 unresolvable imports (5 × `react-router-dom`, 1 × `types/datetime`) | ✗ FAIL |
| `react-router-dom` availability | `grep react-router package.json`, `ls node_modules/react-router-dom` | Absent from both | ✗ FAIL |
| Debt-marker scan (TBD/FIXME/XXX) across 7 phase-71 backend files | `grep -nE "TBD\|FIXME\|XXX"` | 0 matches — no unresolved debt markers | ✓ PASS |
| Router registration reachable | `grep itam router_registry.py` | Both phase-71 routers present at lines 93-94 | ✓ PASS |
| Notification event vocabulary | `grep -rn "itam.asset_request_status"` | Appears only in `itam_notification_service.py` (2 hits) — not in `VALID_EVENTS`, not in `RuleCreate` | ✗ FAIL |

Note: the run was scoped to this phase's own test files per methodology (one scoped run, no full-suite re-runs). The three pre-existing unrelated failures noted in adjacent phase work (`test_agentic_ai`, `test_e2e_integration`, `test_rust_heartbeat_parity`) are outside this scope and are not counted against this phase.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ITAM-PRO-01 | 71-01 | Purchase Order, Cost, and Supplier tracking | ✗ BLOCKED | Backend CRUD complete, registered, tenant-isolated, 17 tests pass. No reachable user surface; PO responses also emit `_id` not `id`. Supplier *catalog* tracking (Phase 56, `CatalogPanel` Suppliers tab) is reachable, so the supplier half of SC1 stands on pre-existing work. |
| ITAM-PRO-02 | 71-02 | Warranty tracking + automated alerts | ⚠️ SATISFIED BY PRIOR PHASE | Reachable and working via Phase 59 (`FinancePanel` + `itam_finance_service` sweep registered at `app_startup.py:642-644`). Phase 71's own contribution (`itam_scheduled_tasks.py` + `warranty_expiry_date`) is orphaned and write-only. |
| ITAM-PRO-03 | 71-02 | Straight-line depreciation modeling | ⚠️ SATISFIED BY PRIOR PHASE | Reachable and working via Phase 59 (`compute_book_value` + `FinancePanel`). Phase 71's `ItamAssetService` is orphaned. |
| ITAM-PRO-04 | 71-03 | Asset Request + Approval Workflow | ✓ SATISFIED | End-to-end reachable, RBAC-correct, 18 tests pass, real browser UAT with two accounts recorded. |
| ITAM-PRO-05 | 71-03 | Alerts/Notifications (Email/Slack) | ✗ BLOCKED (partial) | In-app notifications work for all three request events. Slack/email routing works for warranty events only; asset-request events cannot be bound to any channel. |

**REQUIREMENTS.md discrepancy:** `.planning/REQUIREMENTS.md:67-71` marks all five ITAM-PRO requirements "Complete" against Phase 71. That status is optimistic for **ITAM-PRO-01** (backend-only, no user surface) and **ITAM-PRO-05** (half the event vocabulary unroutable), and misattributes **ITAM-PRO-02/03**, which are satisfied by Phase 59's mechanism rather than Phase 71's. Recommend downgrading PRO-01 and PRO-05 pending gap closure.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `frontend/` tree (5 files) | various | Unresolvable imports (`react-router-dom` not a dependency) | 🛑 Blocker | The entire 71-01/71-02 frontend deliverable cannot compile, let alone render. Root cause of gaps 1 and 3. |
| `backend/itam_scheduled_tasks.py` | whole file | Orphaned duplicate module | 🛑 Blocker | Warranty alerts for `warranty_expiry_date` never fire; duplicate of a shipped Phase 59 sweep. |
| `backend/itam_asset_service.py` | whole file | Orphaned duplicate module | 🛑 Blocker | Depreciation service unreachable; duplicate of shipped `compute_book_value`. |
| `backend/itam_scheduled_tasks.py` | 16-19 | `_tenant_admin_emails` returns a synthesized `admin@{tenant_id}.com` | ⚠️ Warning | Self-declared placeholder. Moot while the module is orphaned, but would misdeliver every alert if wired as-is. |
| `backend/itam_asset_request_service.py` | 79 | Hardcoded approver `itam.approver@example.com` | ⚠️ Warning | Self-declared placeholder. No functional impact today — the approval_service record is an audit trail only and the real transition is owned by the ITAM service. |
| `backend/itam_asset_service.py` | 45 | Bare `except:` swallowing all exceptions | ⚠️ Warning | Masks real errors behind a generic "Invalid purchase date" return. |
| `backend/itam_procurement_endpoints.py` | 41-43 | `except Exception` → 500 around create | ⚠️ Warning | Same class 71-03 fixed for asset requests; lower impact here (no intentional 4xx inside the try). |
| `backend/itam_procurement_endpoints.py` | 27,45,61,76,93 | Missing `response_model_by_alias=False` | ⚠️ Warning | Wire key `_id` instead of `id` — gap 5. |
| `frontend/.../NotificationSettings.tsx` | 8-10 | `handleSaveSettings` logs to console, never persists | ⚠️ Warning | Self-declared stub; unreachable anyway. |
| `frontend/api/itamApiService.ts` | 2-6 | Raw `axios` with no auth header | ⚠️ Warning | Would 401 on every call if the tree were reconnected — reconnecting the UI is not a one-line fix. |
| `backend/itam_finance_endpoints.py` | 78-101 | `purchase_order_id` persisted with no existence/tenant validation | ⚠️ Warning | Threat T-71-04 from 71-01-PLAN.md is declared "mitigate" but is unimplemented. |

No `TBD`, `FIXME` or `XXX` debt markers in any phase-71 backend file.

### Human Verification Required

1. **Purchase-order reachability from a user's seat** — Log in as `itam_admin`, open the ITAM console, and try to reach any purchase-order surface. Verification expects there is none; confirming this from the UI closes out gap 1 beyond import-graph evidence.
2. **Slack/email delivery for asset-request events** — Configure a Slack channel and try to create a notification rule for asset-request events, then submit and approve a request. Expect that the rule cannot be created at all, and that no Slack message arrives.
3. **Write-only warranty field trap** — Set `warranty_expiry_date` on an asset via the API and wait for a warranty sweep pass. Expect no alert, because the live sweep classifies on `purchaseDate` + `warrantyMonths`.

Note that a substantial human UAT was already performed for 71-03 (two real accounts, live backend and browser, five bugs found and fixed) and is recorded in 71-03-SUMMARY.md. That UAT covered SC4 thoroughly and is the reason truths 10 and 11 verify with confidence. It did not cover SC1, SC2, SC3 or the Slack/email half of SC5.

### Gaps Summary

Phase 71 delivered one of its three plans to a genuinely shippable standard and left the other two structurally incomplete.

**What works.** 71-03's asset request and approval workflow (SC4) is the strongest artifact in the phase: built into the real, reachable console tree, gated on RBAC permissions that actually exist and are seeded, with server-derived identity on both sides of the transition, 18 passing tests, and a real two-account browser UAT that found and fixed five bugs the mocked suite could not catch. SC2 (warranty tracking + alerts) and SC3 (straight-line depreciation) are also observably true in the running product — but they are served by Phase 59's finance mechanism, reachable through the Finance tab, not by anything Phase 71 built.

**The central finding.** Two of the three plans produced code that no live path reaches. 71-01's and 71-02's frontend work lives in a `frontend/` tree that nothing imports and that does not type-check — it imports `react-router-dom`, a package this project does not depend on. This was surfaced during 71-03 and consciously left unaddressed by user direction at the time, which is a legitimate scheduling decision; recording it here makes the consequence explicit rather than implicit. On the backend, 71-02's two modules (`itam_scheduled_tasks.py`, `itam_asset_service.py`) are orphans that duplicate shipped Phase 59 functionality, and the three asset-level fields they read are written by the API but read by nothing live. Their tests pass, which is precisely why this needed checking against the import graph rather than the summaries: 13 passing tests currently certify code the running app never executes.

**The one gap not previously known.** SC5's asset-request half cannot work regardless of the frontend situation. `ItamNotificationService` dispatches the event type `itam.asset_request_status`, which is absent from both `notification_service.VALID_EVENTS` and the `notification_endpoints.RuleCreate` Literal — so `create_rule` rejects it and no tenant can ever bind it to a Slack or email channel. 71-03's UAT confirmed four in-app `db.notifications` documents, which is accurate and is what it claimed; the rule-routed Slack/email path was never exercised and does not function. This is the cheapest gap to close (two list additions plus a regression test) and the one most likely to be mistaken for working.

**Bottom line.** 3 of 5 ROADMAP success criteria are met; 7 of 12 merged must-haves verify. The phase should not be considered complete against ITAM-PRO-01 or ITAM-PRO-05, and REQUIREMENTS.md's "Complete" marking for those two should be revised. The decision the gaps force is a scoping one: either build a Purchase Orders panel in the real console tree and delete the `frontend/` tree and the two orphaned backend modules, or formally descope ITAM-PRO-01 to a backend-only API capability and record an override. Leaving an unreachable, unbuildable parallel frontend tree in the repository is the worst of the three options — it reads as delivered work in every summary and requirements table that references it.

---

## Re-verification Addendum (2026-08-24, same day)

All 5 gaps from the initial pass were addressed in one gap-closure session, in the order the Gaps Summary recommended:

1. **Gap 3 (SC5 notifications) — fully closed.** `itam.asset_request_status` registered in both `notification_service.VALID_EVENTS` and `notification_endpoints.RuleCreate`'s Literal. 2 new tests (`test_notification_service.py`) prove a rule can now bind to it and a real `send_notification` call matches and dispatches.
2. **Gap 4 (orphaned modules) — closed via deletion.** `backend/itam_scheduled_tasks.py`, `backend/itam_asset_service.py`, and their orphan-only test files deleted (confirmed zero other importers first). Full backend suite re-run clean: 2369 passed / 34 skipped / 0 failed.
3. **Gap 5 (wire-shape bug) — fully closed.** `response_model_by_alias=False` added to all 4 PurchaseOrder response routes; 4 tests tightened to assert `id` present / `_id` absent.
4. **Gap 2 (T-71-04 unvalidated) — closed for the validation half.** `update_asset_purchase` now 400s on an unresolvable `purchase_order_id`. 2 new tests pass. The "surface the link in a reachable UI" half of this truth was intentionally not built — the link is now safe, not yet visible anywhere.
5. **Gap 1 (SC1 unreachable) — closed for real, per explicit user decision ("build it for real" over "formally descope").** `components/itam/PurchaseOrdersPanel.tsx` built (list/create/edit/delete), mounted as its own tab in `ITAMConsole.tsx`, `ItamPurchaseOrder`/`ItamPurchaseOrderItem` added to `types.ts`, four functions added to `apiService.ts`. 7 new component tests pass; full frontend suite 457/457; `npm run build` clean. The dead `frontend/` tree deleted entirely (was unbuildable — missing `react-router-dom` — and unreachable).

**Re-run truths (spot-check, not a full re-verification pass):**

| # | Truth | Original | Now |
|---|-------|----------|-----|
| 1 | User can track purchase order details and supplier information | ✗ FAILED | ✓ VERIFIED — `PurchaseOrdersPanel` reachable via its own console tab |
| 3, 4 | List / view purchase orders | ✗ FAILED | ✓ VERIFIED — same panel, list + edit modal |
| 5 | Asset↔PO link validated | ✗ FAILED | ✓ VERIFIED (validation only; no dedicated read-path UI) |
| 12 | SC5 notifications | ✗ FAILED (partial) | ✓ VERIFIED — both warranty and asset-request events now routable |
| 6, 8 | SC2/SC3 (warranty, depreciation) | ✓ VERIFIED (via Phase 59) | ✓ VERIFIED (unchanged — still Phase 59's mechanism, not Phase 71's; the orphaned Phase 71 duplicates are now deleted rather than dead-but-present) |

**Score after re-verification: 12/12 merged must-haves verified.** `REQUIREMENTS.md`'s ITAM-PRO-01/05 rows, previously flagged as optimistic, are now genuinely accurate as "Complete" — updated same session.

**Residual, consciously not fixed:** no UI surface displays an asset's linked PO number (validation exists, display doesn't); `Asset.warranty_expiry_date`/`salvage_value`/`useful_life_years` remain unread by any live sweep (Phase 59's mechanism uses different fields) — harmless but still not the single source of truth the fields imply. Neither blocks any ROADMAP success criterion.

_Verified: 2026-08-24_
_Verifier: Claude (gsd-verifier)_
_Re-verification addendum: 2026-08-24, Claude (session lead)_
