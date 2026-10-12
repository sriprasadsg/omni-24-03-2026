---
status: testing
phase: 75-permission-resolver-single-source-of-truth
source: [75-VERIFICATION.md]
started: 2026-10-12T23:40:00Z
updated: 2026-10-12T23:40:00Z
---

## Current Test

number: 1
name: Live seeding of shared role documents after a backend restart
expected: |
  After the user restarts the backend, a read-only query of `omni_platform.roles` shows 11 shared role
  documents: 10 at `tenantId: "all"` (Tenant Admin, admin, analyst, security_analyst, incident_responder,
  user, viewer, itam_admin, itam_user, itam_viewer) whose permission lists equal `backend/rbac_defaults.py`,
  plus Super Admin at `tenantId: "platform"` with `["*"]`. Any tenant-scoped role document with the same
  name is unchanged.
awaiting: user response

## Tests

### 1. Live seeding of shared role documents after a backend restart
expected: 11 shared documents as described above; tenant-scoped same-name documents untouched.
result: [pending]

### 2. ITAM-role login through the deployed UI
expected: After restart and UI redeploy, users with itam_admin, itam_user and itam_viewer each sign in and get a non-empty permission list from `/api/auth/login` and `/api/auth/me` (the same list from both). The sidebar shows only catalogues in that list intersected with the tenant's enabledFeatures (ITAM console and Profile pages visible; no main dashboard). itam_viewer gets a handled 403 on the role list without breaking the page load.
result: [pending]

### 3. Policy sign-off on the code-review fixes
expected: The user confirms the intended policy for CR-01 (a non-super caller cannot change the password, status, role or tenant of, or delete, an account whose role holds permissions the caller lacks), WR-01 (role documents can never grant `*` or super-admin-only permissions), and accepts the deferred parts of WR-04 (apply-time re-check of tenant-level mapping roles needs a mapping-schema change) and WR-06 (whether `isEditable` should matter for shared role documents).
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
