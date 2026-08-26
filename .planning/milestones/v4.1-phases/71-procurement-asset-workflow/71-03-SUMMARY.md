---
phase: 71-procurement-asset-workflow
plan: 03
subsystem: itam
tags: [fastapi, mongodb, react, typescript, itam, procurement, approval-workflow, notifications]

# Dependency graph
requires:
  - 71-02
provides:
  - Asset request submission (any authenticated user)
  - Approval/rejection workflow for asset requests (itam_admin-gated)
  - Lifecycle notifications on submit/approve/reject
affects: []

# Tech tracking
tech-stack:
  added:
    - backend/itam_asset_request_service.py
    - backend/itam_asset_request_endpoints.py
    - components/itam/RequestsPanel.tsx
  patterns:
    - "AssetRequest lifecycle gated by request:assets (itam_user) / manage:procurement (itam_admin) — no new RBAC permission strings, reused existing seeded ones"
    - "Approval-service integration is fire-and-forget audit trail; the actual state transition is owned by ItamAssetRequestService, not approval_service's own approve/reject"

key-files:
  created:
    - backend/itam_asset_request_service.py
    - backend/itam_asset_request_endpoints.py
    - backend/tests/test_itam_asset_request_service.py
    - backend/tests/test_itam_asset_request_endpoints.py
    - components/itam/RequestsPanel.tsx
  modified:
    - backend/itam_models.py (AssetRequest/AssetRequestCreate/AssetRequestUpdate/AssetRequestStatus — already present from a prior paused session, unchanged)
    - backend/itam_notification_service.py (send_asset_request_notification — already present from a prior paused session, unchanged)
    - backend/router_registry.py (registered itam_asset_request_endpoints router)
    - types.ts (ItamAssetRequest, ItamAssetRequestStatus)
    - services/apiService.ts (fetchAssetRequests, createAssetRequest, approveAssetRequest, rejectAssetRequest; fetchCloudAccounts res.ok check — UAT fix, see below)
    - components/itam/ITAMConsole.tsx (new "Requests" tab)
    - components/itam/itamI18n.tsx (tabs.requests label, en/es)
    - backend/rbac_utils.py (added itam_admin/itam_user/itam_viewer to DEFAULT_PERMISSIONS — UAT fix)
    - components/Sidebar.tsx (itam nav gate manage:itam → view:itam — UAT fix)
    - App.tsx (viewPermissionMap.itam manage:itam → view:itam — UAT fix)
  deleted:
    - backend/app/ (entire tree — orphaned scaffold from a prior paused session; never wired into main.py/router_registry.py, off-convention vs. this codebase's flat backend/*.py + router_registry._load pattern)
    - backend/tests/api/, backend/tests/services/ (nested test dirs for the orphaned app/ tree — all real ITAM tests are flat under backend/tests/)

key-decisions:
  - "Built the UI in the real, running app tree (components/itam/ITAMConsole.tsx + types.ts + services/apiService.ts) rather than frontend/routes/itamRoutes.tsx, per explicit user direction after discovering the latter is disconnected from the app (App.tsx only lazy-loads ./components/itam/ITAMConsole; nothing imports frontend/routes/itamRoutes.tsx). Same finding applies to 71-01 (PurchaseOrderList/Detail) and 71-02 (NotificationSettings.tsx warranty toggle) — both were built in that same disconnected frontend/ tree and are NOT reachable in the product. Left as flagged, unaddressed debt per user's choice — not fixed in this plan."
  - "Skipped the notification-toggle UI from the plan's Task 2. No backend setting exists to gate asset-request notifications on/off (itam_notification_service sends unconditionally, same as the Phase 71-02 warranty alerts) — a toggle with nothing to bind to would be fake UI. ITAM-PRO-05's actual requirement (notifications ARE sent) is already satisfied."
  - "Approve/Reject buttons are shown to every viewer on pending rows (no client-side role check) — the backend 403s non-itam_admin callers. Matches the established EvidenceSettings.tsx / Phase 62 pattern referenced in the plan."

requirements-completed: [ITAM-PRO-04, ITAM-PRO-05]

coverage:
  - id: P1
    description: "Backend asset-request CRUD + approval workflow + notifications"
    requirement: "ITAM-PRO-04, ITAM-PRO-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_asset_request_service.py"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_asset_request_endpoints.py"
        status: pass
      - kind: unit
        ref: "backend/tests/ (full suite)"
        status: pass
        note: "2176 passed / 34 skipped / 11 failed — all 11 failures verified pre-existing and unrelated (Vault client, rotate_key wiring, itam_audit purchase-log, powershell_evidence order-dependent pollution); none touch asset-requests."
  - id: P2
    description: "Frontend Requests tab in the real ITAM console"
    requirement: "ITAM-PRO-04, ITAM-PRO-05"
    verification:
      - kind: npm
        ref: "npm run build"
        status: pass
      - kind: npm
        ref: "npx vitest run"
        status: pass
        note: "407/407 pass"
      - kind: tsc
        ref: "npx tsc --noEmit"
        status: pass
        note: "0 errors in any file this plan touched; 241 pre-existing errors remain in src/router/routes.tsx, an unrelated half-finished router-migration scaffold from the same paused session (imported-but-unused ROUTE_MAP in App.tsx — doesn't affect the real vite build)."
      - kind: human
        ref: "live browser session, two real UAT accounts (itam_user requester + itam_admin approver) against a live uvicorn+MongoDB backend and Vite frontend"
        status: pass
        note: "Submitted 'Standing Desk' as requester → visible Pending in Requests tab. Approved as admin → green Approved badge, correct approver_id/approval_date. Submitted 'Gaming Chair' → rejected as admin → red Rejected badge. Confirmed 4 itam.asset_request_status documents in db.notifications with correct severities. Confirmed the RBAC boundary: requester's own Approve click correctly 403s with a toast, status stays Pending. 5 real bugs found and fixed along the way — see below."
    human_judgment: true
    rationale: "Full click-through UAT completed and passed after fixing 5 bugs the mocked unit tests couldn't catch (see 'Human UAT' section below)."

# Metrics
duration: ~240min
completed: 2026-08-16
status: complete
---

# Phase 71 Plan 03: Asset Request & Approval Workflow Summary

**Completed the asset request + approval workflow left paused mid-session: fixed several real bugs in the already-drafted backend, restored a FastAPI entrypoint file that the same paused session had accidentally deleted, removed an orphaned dead-code scaffold, and built the frontend directly into the real (reachable) ITAM console instead of a disconnected tree.**

## Starting State

`.continue-here.md` indicated Task 1 (backend) was mostly drafted but untested. Investigation found the actual state was more serious than "untested":

1. **`backend/app.py` — the main FastAPI entrypoint (`app = FastAPI(...)`, 180 lines) — had been deleted** in the paused commit (`a3919391`) as a side effect of creating `backend/app/` (a directory can't coexist with a file of the same name). This broke every test importing `from app import _fastapi_app`, i.e. all ITAM endpoint tests, not just this plan's. Restored from `a3919391^`.
2. **`backend/app/` was an orphaned duplicate** of the real flat `backend/itam_asset_request_*.py` files — never wired into `main.py` or `router_registry.py`, using a `backend/app/api/v1/...` FastAPI-boilerplate structure this codebase doesn't otherwise use. Deleted, along with the nested `backend/tests/api/`, `backend/tests/services/` test dirs built against it.
3. **The frontend plan target (`frontend/routes/itamRoutes.tsx` + `frontend/components/itam/procurement/`) is disconnected from the running app.** `App.tsx` only lazy-loads `./components/itam/ITAMConsole` via a `case 'itam':` switch; nothing imports the `frontend/` tree's router. This also means 71-01's Purchase Orders UI and 71-02's warranty notification toggle were built but are not reachable in the product — confirmed via `SettingsPanel.tsx` having zero warranty/notification code. Surfaced to the user; by their direction, this plan builds correctly in the real tree and leaves 71-01/71-02's gap unaddressed.

## Accomplishments

- **Backend** (`backend/itam_asset_request_service.py`, `backend/itam_asset_request_endpoints.py`):
  - Fixed `create_asset_request` never setting an `id` field on insert — `get`/`approve`/`reject` all query `{"id": ...}`, so every request would have been unfindable after creation (same latent bug exists in the shipped 71-01 `itam_procurement_service.py`, not touched here — out of scope).
  - Fixed RBAC permission strings: the drafted code checked for `create:asset_request` / `approve:asset_request`, which don't exist anywhere in `rbac_service.py` or `rbac_utils.py` — every request would 403 for every non-super-admin. Replaced with the already-seeded `request:assets` (on `itam_user`) and `manage:procurement` (on `itam_admin`, same gate as 71-01's procurement router).
  - Fixed `current_user.email` (5 call sites) — `TokenData` is a dataclass with no `email` field, only `username`; every approve/reject/create call would have raised `AttributeError`. This exact class of bug (`.username` vs `.email`) is a documented recurring pitfall in this codebase.
  - Fixed intentional `400` responses (bad-state approve/reject) getting caught by a bare `except Exception` and rethrown as `500`.
  - Registered the router in `router_registry.py` (was drafted but never wired in).
  - Wrote `backend/tests/test_itam_asset_request_service.py` (8 tests) and `test_itam_asset_request_endpoints.py` (9 tests) — flat, matching the sibling `test_itam_procurement_*.py` convention (the drafted nested versions under the deleted `backend/app/` tree used the wrong import paths).
- **Frontend**: New `components/itam/RequestsPanel.tsx` (submit request via modal, table of requests, inline Approve/Reject on pending rows) mounted as a new "Requests" tab in `ITAMConsole.tsx`, with real types in `types.ts` and real API functions in `services/apiService.ts`. i18n labels added for en/es.

## Task Commits

1. `78e5009d` — feat(71-03): asset request & approval workflow (backend + frontend, drafted-code fixes, restored backend/app.py)
2. `2b206e3e` — fix(71-01): purchase order create never set id field (same latent bug class as 71-03's, found while fixing 71-03's)
3. `1c8637c4` — fix(71-03): five real bugs found driving the human UAT for asset requests (see below)

## Human UAT

Drove the app end-to-end in a real browser against a live `uvicorn` backend (restored `backend/app.py`, port 5000) and `vite dev` frontend (plain HTTP on `127.0.0.1:3000` — the self-signed HTTPS dev cert blocks the browser-automation tool's screenshot/DOM tools; `VITE_HTTPS=false` sidesteps this for testing only, no code change). Created two throwaway tenant-scoped accounts (`uat-itam-requester@uatverify.test` role `itam_user`, `uat-itam-71-03@uatverify.test` role `itam_admin`) via normal signup + a direct `role` field update, since neither `itam_user` nor `itam_admin` auto-provisions a `db.roles` document for a fresh tenant (a separate, unfixed gap — see Known Stubs).

Five real bugs surfaced this way, none caught by the mocked unit suite because every test patches `verify_permission`/service calls wholesale rather than exercising real permission strings or real Mongo documents:

1. **`fetchCloudAccounts()` crashed the entire app for any restricted-permission login.** No `res.ok` check before `.json()` — a 403 (missing `view:cloud_security`) resolved to an error object, `cloudAccounts.filter()` in `App.tsx` then threw uncaught above every `ErrorBoundary`, blanking the whole UI. Not itam_user-specific: any role without full cloud-security access would hit this on login.
2. **`rbac_utils.DEFAULT_PERMISSIONS` was missing `itam_admin`/`itam_user`/`itam_viewer`** despite a comment claiming it mirrors `rbac_service.py`'s `default_roles` — those roles had zero effective permissions via `verify_permission` whenever no `db.roles` document exists for the tenant (the default state; nothing seeds one).
3. **The ITAM console's own sidebar/route gates required `manage:itam`**, the only entry in the entire sidebar not gated on its `view:*` counterpart — so `itam_user`/`itam_viewer` (the exact scoped-access roles Phase 69 built) could never even open the console.
4. **List/get asset-request endpoints required `request:assets`**, same as create — so `itam_admin` (has `manage:procurement`, not `request:assets`) could approve/reject in principle but never see the queue. Added an either/or `_require_asset_viewer` dependency.
5. **`AssetRequest.id` never reached the client correctly.** `response_model_by_alias` (FastAPI default `True`) serialized the Pydantic `alias="_id"` field as JSON key `_id`, so `RequestsPanel.tsx`'s `r.id` was `undefined` and every approve/reject PATCH hit `.../undefined/approve`. Setting `response_model_by_alias=False` fixed the key name but exposed a second, deeper mismatch: the *value* was Mongo's raw auto-`_id` ObjectId, not the `"ar-xxxxxxxx"` string `get`/`approve`/`reject` query by — approve/reject 400'd on every real request. Fixed at the source: `create_asset_request` now sets Mongo's real `_id` to the generated string instead of maintaining a redundant, disconnected parallel `"id"` field.

All five fixed, full loop re-verified working (submit → list → approve/reject → status badge → notification record), committed as `1c8637c4`.

## Deviations from Plan

- Frontend built in `components/itam/`, `types.ts`, `services/apiService.ts` instead of the plan's `frontend/components/itam/procurement/AssetRequestForm.tsx` / `AssetRequestApprovalQueue.tsx` / `frontend/routes/itamRoutes.tsx` — see "Starting State" above. User-confirmed direction.
- Single `RequestsPanel.tsx` component (list + create modal + inline approve/reject) instead of two separate `AssetRequestForm.tsx` / `AssetRequestApprovalQueue.tsx` components — matches this console's existing per-tab-single-component pattern (e.g. `LicensesPanel.tsx` covers licenses+consumables+components in one file with internal sections).
- `NotificationSettings.tsx` toggle from Task 2 not built — no backend setting exists to bind it to (see key-decisions).
- Schema file `backend/schemas/itam_asset_request_schemas.py` from the plan's file list was never created (nor needed) — `AssetRequestCreate`/`AssetRequestUpdate` already live in `itam_models.py`, matching the sibling `PurchaseOrder` schemas' location.

## Known Stubs / Pre-existing Debt (not fixed in this plan)

- `itam_procurement_service.py`'s (71-01) `_id`-never-set-on-insert bug was fixed separately (commit `2b206e3e`), but `itam_procurement_endpoints.py` still has the *other* half of asset-requests' bug 5: `response_model=PurchaseOrder` with no `response_model_by_alias=False`, so `GET`/`POST /purchase-orders` still return the wire key `_id` instead of `id` today. Not fixed — 71-01's frontend is unreachable (see next line) so nothing currently depends on the wire shape, but it'll bite whoever eventually reconnects that UI.
- 71-01 (Purchase Orders UI) and 71-02 (warranty notification toggle) frontend work lives in the disconnected `frontend/` tree and is not reachable from the running app.
- `src/router/routes.tsx` (unrelated to this phase, same paused session) has ~149 lazy-loaded component imports with broken relative paths (`./components/X` instead of `../../components/X`), producing 241 `tsc --noEmit` errors. Doesn't break `npm run build` because the only consumer (`App.tsx`'s `ROUTE_MAP` import) is unused and gets tree-shaken, but blocks using `tsc --noEmit` as a clean whole-project gate.
- The asset-request approver list passed to `approval_service.create_approval_request` is a hardcoded placeholder (`itam.approver@example.com`) — same precedent as `itam_scheduled_tasks._tenant_admin_emails`'s dummy-email stub already accepted in 71-02. `approval_service`'s own approve/reject flow is never actually invoked (the real state transition happens in `ItamAssetRequestService.approve_asset_request`/`reject_asset_request`); the approval-service record is an audit trail only, so this placeholder has no functional impact.

## Threat Flags

- None new. RBAC gates now correctly point at real, seeded permissions (T-71-10 mitigation from the plan's threat model is now actually in effect — previously a nonexistent permission string meant a broken 403 that happened to close, not a designed one). Tenant isolation unchanged (`tenant_id` filter on every query, `TokenData.tenant_id` server-derived, `approver_id`/`requester_id` server-derived from `current_user.username`, never client input).
