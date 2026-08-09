---
phase: 29-public-trust-center
plan: 02
status: complete
---

# SUMMARY — 29-02 Public routes + custom domain resolution

- Added to `backend/trust_endpoints.py`:
  - `_resolve_tenant_from_request`: Host-header/slug resolver.
  - `_public_view`: filter for public-safe profile view (private documents name-only).
  - `get_public_trust_profile`: `GET /api/public/trust/{slug}` with `@limiter.limit("30/minute")`.
  - `AccessRequestCreate` Pydantic model.
  - `create_public_access_request`: `POST /api/public/trust/{slug}/requests` with `@limiter.limit("5/minute")`.
  - `public_router` added and registered to `router_registry.py`.

- Updated `backend/tests/test_trust_center.py` with passing tests:
  - `TestPublicTrustGet`: verifies public GET with slug resolution.
  - `TestCustomDomainResolution`: verifies Host-header custom domain resolution.
  - `TestPrivateDocFilter`: verifies private document URLs are stripped.
  - `TestPublicAccessRequestPost`: verifies public POST for access requests, consent, and server-derived metadata.
  - `TestPublicRateLimit`: verifies rate-limit enforcement for both public GET and POST routes.

- Key changes:
  - Public routes resolve tenant safely (exempt lookup → set_tenant_id), serve private-URL-stripped view, 404 cleanly on unknown slug, and resolve custom domains by Host header.
  - External visitors can submit consented NDA access requests; consent is enforced; ip/ua/timestamp are server-derived and un-forgeable.
  - Both public routes are rate-limited and reachable end-to-end (429 on over-limit, never a 500 from a missing response param).