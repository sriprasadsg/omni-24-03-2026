---
phase: 29-public-trust-center
plan: 01
status: complete
---

# SUMMARY — 29-01 Trust Center DB Backend + Admin Routes

- Rewrote `backend/trust_service.py` as async Mongo-backed module-level helpers:
  - `get_profile(db, tenant_id)`, `update_profile(db, tenant_id, updates)`
  - `get_requests(db, tenant_id)`, `create_request(db, tenant_id, request_data)`
  - `update_request_status(db, tenant_id, request_id, status, approved_by)`
  - `_ensure_trust_slug(db, tenant_id)` auto-generates opaque `trust-{uuid}` on `db.tenants`
  - Removed old `TrustService` singleton; kept `TrustProfile`/`AccessRequest` Pydantic models

- Converted `backend/trust_endpoints.py` to async routes awaiting new service helpers:
  - `GET /api/trust-center/profile` returns profile + `trust_slug` + `trust_domain`
  - `PUT /api/trust-center/profile` persists optional `trust_domain` to `db.tenants`
  - `GET /api/trust-center/requests` (admin-gated)
  - `POST /api/trust-center/requests` (public create)
  - `PUT /api/trust-center/requests/{id}` (admin-gated status update)
  - Auth unchanged: `_TRUST_ADMIN_ROLES` + `Depends(get_current_user)`

- Created `backend/tests/test_trust_center.py` with 10 passing tests:
  - `TestTrustPersistence` (2 tests): profile & request round-trip across fresh DB handles
  - `TestTrustTenantIsolation` (2 tests): collections not exempt; tenant A data invisible to B
  - `TestTrustAdminAuth` (5 tests): 403 for non-admin, 200 for admin, 401 unauth
  - `TestTrustAdminSettings` (1 test): `trust_domain` persists to `db.tenants`; GET returns slug+domain

- Verified `trust_profiles` and `trust_access_requests` not added to `database.py` exemption allowlist (tenant isolation preserved).