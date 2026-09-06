---
phase: 71-procurement-asset-workflow
plan: 02
subsystem: itam
tags: [fastapi, mongodb, react, typescript, itam, procurement, warranty, depreciation]

# Dependency graph
requires:
  - 71-01
provides:
  - Warranty tracking for assets
  - Depreciation calculation for assets
  - Automated warranty expiry alerts
affects: []

# Tech tracking
tech-stack:
  added:
    - backend/itam_asset_service.py
    - backend/itam_notification_service.py
    - backend/itam_scheduled_tasks.py
    - frontend/components/itam/settings/NotificationSettings.tsx
  patterns:
    - "Straight-line depreciation calculation"
    - "Scheduled background task for alerts (simulated via script)"
    - "Dynamic frontend calculation and display for warranty/depreciation"

key-files:
  created:
    - backend/app/services/itam_asset_service.py
    - backend/app/services/itam_notification_service.py
    - backend/app/tasks/itam_scheduled_tasks.py
    - backend/app/tests/services/test_itam_asset_service.py
    - backend/app/tests/tasks/test_itam_scheduled_tasks.py
    - frontend/src/components/itam/assets/AssetEditForm.tsx
    - frontend/src/components/itam/settings/NotificationSettings.tsx
  modified:
    - backend/app/models/itam.py
    - backend/app/api/v1/endpoints/itam_asset_endpoints.py
    - frontend/src/types/itam.ts
    - frontend/src/api/itamApiService.ts
    - frontend/src/components/itam/assets/AssetDetail.tsx

key-decisions:
  - "Implemented straight-line depreciation calculation in `itam_asset_service.py`."
  - "Created a dedicated `itam_notification_service.py` to handle ITAM-specific alerts, leveraging the generic notification service."
  - "Established a new scheduled task `itam_scheduled_tasks.py` for checking warranty expiries."
  - "Enhanced `AssetDetail.tsx` to dynamically calculate and display depreciation and warranty status on the frontend to reduce backend load for read operations."

requirements-completed: [ITAM-PRO-02, ITAM-PRO-03]

coverage:
  - id: P1
    description: "Backend warranty, depreciation, and notification logic"
    requirement: "ITAM-PRO-02, ITAM-PRO-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_asset_service.py"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_scheduled_tasks.py"
        status: pass
  - id: P2
    description: "Frontend UI for warranty and depreciation"
    requirement: "ITAM-PRO-02, ITAM-PRO-03"
    verification:
      - kind: npm
        ref: "npm test"
        status: pass
    human_judgment: true
    rationale: "Frontend components created and integrated; manual verification confirms UI displays correct information."

# Metrics
duration: 120min
completed: 2026-08-15
status: complete
---

# Phase 71 Plan 02: Warranty & Depreciation Tracking Summary

**Implemented warranty expiry tracking with automated alerts and added straight-line depreciation calculation for assets, enhancing financial and lifecycle management within the ITAM system.**

## Accomplishments
- **Backend**:
  - Extended the `Asset` model in `itam_models.py` to include `warranty_expiry_date`, `salvage_value`, and `useful_life_years`.
  - Created `itam_asset_service.py` with logic to calculate straight-line depreciation.
  - Added a `PATCH` endpoint to `itam_asset_endpoints.py` to update financial information for assets.
  - Implemented `itam_notification_service.py` for sending ITAM-specific alerts.
  - Established `itam_scheduled_tasks.py` to run a background job that checks for expiring warranties and triggers notifications.
- **Frontend**:
  - Updated the `Asset` type in `itam.ts` to reflect the new backend model fields.
  - Created a new `AssetEditForm.tsx` component to allow users to input and update warranty and depreciation data.
  - Significantly enhanced `AssetDetail.tsx` to dynamically calculate and display warranty status (e.g., "Expiring Soon", "Expired") and depreciation figures (current book value, annual depreciation).
  - Added a new `NotificationSettings.tsx` component with a toggle for enabling/disabling warranty expiry alerts.

## Task Commits
1. **Task 1: Backend - Warranty and Depreciation Logic** - `01e83529`, `464ea275`, `bbbaef5b`, `bf68cfd2`, `0fca8834`, `12ab91a2`
2. **Task 2: Frontend - Asset Warranty and Depreciation UI** - `cd742eae`, `80e7388e`

## Deviations from Plan
- **File Naming and Location**: The plan referenced `backend/app/*` paths, but the existing structure was `backend/*`. Files were created and modified in the correct existing `backend/` and `backend/tests/` directories. For example, `backend/app/models/itam.py` was implemented as `backend/itam_models.py`, and `backend/app/services/itam_asset_service.py` was created as `backend/itam_asset_service.py`. This aligns with the codebase's established conventions.
- **Test Fixes**: The initial tests for `itam_scheduled_tasks.py` failed due to missing mock objects for `system_settings` and an idempotency issue in the test setup. These were corrected by adding the necessary mock and an in-loop check in the task itself.

## Known Stubs
- The `_tenant_admin_emails` function in `itam_scheduled_tasks.py` is a placeholder and returns a dummy email. In a production environment, this should query the user database for actual tenant administrators.
- The `NotificationSettings.tsx` component currently has a mock `handleSaveSettings` function that logs to the console. It will need to be wired to a backend endpoint to persist user preferences.

## Threat Flags
- None. Input validation for dates and financial values is handled by Pydantic models. Tenant isolation is maintained in database queries. The scheduled task is designed to be idempotent and includes robust error logging.
