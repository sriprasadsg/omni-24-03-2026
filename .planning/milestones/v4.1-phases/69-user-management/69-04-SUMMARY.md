---
phase: 69-user-management
plan: "04"
subsystem: auth
tags: [saml, sso, fastapi, mongodb, python3-saml, rbac, encryption]

requires:
  - phase: 69-01
    provides: "User CRUD, users collection shape (tenantId/role/status), itam_asset_endpoints._require_itam_admin admin gating"
  - phase: 69-02
    provides: "rbac_service.default_roles (itam_admin/itam_user/itam_viewer), rbac_service._normalize_role single source of truth"
provides:
  - "saml_service.py: SAMLConfig (env or admin-saved DB config), SAMLAuthenticator (SP metadata, SP-initiated AuthnRequest/login, ACS validation with signature/audience/timestamp checks via python3-saml plus InResponseTo correlation and an independent assertion-ID replay cache, SLO handling), authenticate_saml() (ACS -> provision -> mint JWT), is_saml_sourced_user()"
  - "saml_mapping.py: SAMLUserProvisioner (attribute extraction, source=\"saml\" provisioning with role-clobber guard) and SAMLGroupMapper (group-attribute-value -> ITAM role mapping, admin CRUD)"
  - "sso_endpoints.py saml_router: 7 admin endpoints (POST/GET config, GET metadata, POST test, GET/POST/DELETE attribute-mapping) gated by _require_itam_admin, plus 4 public routes (GET metadata, GET login, POST acs, GET slo)"
  - "T-64-17 mitigation: local password changes/resets blocked for source=\"saml\" users in user_endpoints.update_user and auth_password_reset_endpoints.confirm_password_reset (extends the existing T-64-12 LDAP guard)"
affects: [69-06-mfa-and-login-rewrite, 70-core-data-audit-customization]

tech-stack:
  added: ["python3-saml==1.16.0 (human-approved via blocking checkpoint, pulls in lxml + xmlsec via prebuilt wheels — no C build issues)"]
  patterns:
    - "Module split up front (not reactive): saml_service.py (config/authenticator/full-flow) + saml_mapping.py (provisioning/group-mapping) mirrors ldap_service.py's shape, keeping every file under the CLAUDE.md 500-line cap"
    - "RelayState-token InResponseTo correlation: SP-initiated login stores the AuthnRequest ID in a short-lived MongoDB TTL collection keyed by an opaque RelayState token; the ACS handler pops it by the token the IdP echoes back, then passes it to process_response(request_id=...) for InResponseTo validation. IdP-initiated (unsolicited) responses skip this check, matching the SAML spec."
    - "Independent assertion-ID replay cache (saml_processed_assertions, insert-with-unique-_id race-free check) on top of python3-saml's own signature/audience/timestamp validation — closes T-64-13's replay-protection requirement explicitly"
    - "ACS reuses the existing sso_endpoints._store_sso_state/_consume_sso_state exchange-code pattern (already used by the Google OIDC flow) instead of returning a JWT directly in a browser-visible POST response"
    - "Two-router-per-file pattern (matches itam_component_endpoints.py's router/asset_components_router precedent): sso_endpoints.py now exports both `router` (/api/sso prefix) and `saml_router` (no prefix, absolute paths for /api/auth/saml/* and /api/admin/sso/saml/*), both registered separately in router_registry.py"

key-files:
  created:
    - backend/saml_service.py
    - backend/saml_mapping.py
    - backend/tests/test_sso_saml.py
  modified:
    - backend/sso_service.py
    - backend/sso_endpoints.py
    - backend/router_registry.py
    - backend/user_endpoints.py
    - backend/auth_password_reset_endpoints.py
    - backend/requirements.txt

key-decisions:
  - "python3-saml==1.16.0 chosen over pysaml2 and over the already-installed authlib, per RESEARCH.md's recommendation (simpler OneLogin_Saml2_Auth API) — human-approved via the plan's blocking checkpoint after confirming the SAML-Toolkits/python3-saml GitHub repo and PyPI legitimacy; installed cleanly via prebuilt manylinux wheels for its lxml/xmlsec dependencies, no C toolchain issues."
  - "saml_service.py / saml_mapping.py are a NEW module pair, not an extension of sso_service.py, per the plan's own <module_budget> — sso_service.py's old SAML block (231-289, self-described as \"no python3-saml dependency required\" and confirmed by RESEARCH.md Q1 to have zero real validation) is replaced with thin delegating wrappers (get_saml_sp_metadata/process_saml_response) so any theoretical existing importer keeps working, though a grep confirmed neither function is actually called anywhere in the codebase today."
  - "InResponseTo correlation implemented via an opaque RelayState token mapped server-side to the real AuthnRequest ID (a short-lived MongoDB TTL collection), rather than trusting a client-supplied value — RelayState is otherwise opaque per the SAML spec, so this is the only place to safely stash server state across the IdP redirect round trip."
  - "Assertion replay protection implemented as an INDEPENDENT check (a second MongoDB TTL collection keyed by assertion ID, insert-with-unique-_id) on top of whatever InResponseTo/timestamp checks python3-saml performs internally — the plan's threat_model (T-64-13) and action step 7 both call out replay protection explicitly as its own requirement, not assumed to be covered implicitly by signature validation."
  - "No SAML_DEFAULT_TENANT_ID equivalent to LDAP's LDAP_DEFAULT_TENANT_ID: authenticate_saml() resolves tenant_id from the caller (admin-triggered) or an existing local user's tenantId; first-time SAML-only provisioning with no pre-created user and no caller-supplied tenant_id raises SAMLProvisionError rather than guessing. This is a narrower default than LDAP's — flagged as a follow-up below, not silently matched to avoid scope creep beyond what this plan's must-haves require."
  - "SAML_IDP_METADATA_URL (documented in the plan's user_setup for 'auto-configuration') is NOT implemented — SAMLConfig only supports manually-configured idp_entity_id/idp_sso_url/idp_slo_url/idp_x509_cert. Fetching and parsing a live IdP metadata URL (via OneLogin_Saml2_IdPMetadataParser) was judged out of this plan's core scope (metadata/ACS/SLO/validation/provisioning) and is tracked as a deferred convenience feature, not a functional gap — manual IdP config is a complete, secure operator workflow on its own."
  - "POST /api/admin/sso/saml/test validates that the caller's stored/env config produces valid SP metadata (catches config typos, missing required fields, malformed certs) but does not perform a live round trip to the IdP — no test IdP is reachable in this sandbox, matching 64-03's LDAP test-connection endpoint's own accepted gap for a real directory."
  - "Extended scope to backend/user_endpoints.py and backend/auth_password_reset_endpoints.py (not in this plan's files_modified) to wire T-64-17 (block local password changes for source=\"saml\" users) into the actual enforcement points — exact same precedent as 64-03's Rule 2 extension into the same two files for the LDAP equivalent (T-64-12). Implemented as a single combined check (source in (\"ldap\", \"saml\")) rather than a second parallel if-block, since both share the identical 'external IdP owns credentials' logic."
  - "Extended scope to backend/router_registry.py (not in this plan's files_modified) to register the new saml_router — same Rule 3 precedent as 64-03's ldap_endpoints.router registration; without it, all 11 new SAML routes are unreachable dead code."

requirements-completed: [ITAM-USR-04]

coverage:
  - id: D1
    description: "Users can authenticate via SAML 2.0 SSO: SP metadata, SP-initiated AuthnRequest/login redirect, and ACS assertion processing all implemented via python3-saml's OneLogin_Saml2_Auth"
    requirement: "ITAM-USR-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_sso_saml.py::TestSAMLAuthenticatorMetadata, TestSAMLAuthenticatorLogin, TestSAMLAuthenticatorACS (5 tests)"
        status: pass
      - kind: unit
        ref: "backend/tests/test_sso_saml.py::TestSAMLLoginEndpointAuth, TestSAMLAcsEndpointAuth (5 endpoint tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "SAML assertions are validated: signature, audience, NotBefore/NotOnOrAfter (via python3-saml is_valid), InResponseTo correlation (RelayState-token store), and an independent assertion-ID replay cache"
    requirement: "ITAM-USR-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_sso_saml.py::TestSAMLAuthenticatorACS::test_process_acs_success_returns_nameid_and_attributes, test_process_acs_raises_on_validation_errors, test_process_acs_raises_on_replay"
        status: pass
    human_judgment: false
  - id: D3
    description: "SAML users are provisioned/updated in MongoDB with source=\"saml\" flag; local password changes/resets blocked for SAML-sourced users (T-64-17)"
    requirement: "ITAM-USR-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_sso_saml.py::TestSAMLUserProvisioner (4 tests), TestAuthenticateSamlFlowAuth (2 tests)"
        status: pass
      - kind: other
        ref: "backend/user_endpoints.py update_user / backend/auth_password_reset_endpoints.py confirm_password_reset — source==\"saml\" guard added; no new automated test written for these two files in this plan (mirrors 64-03's same accepted gap for the LDAP guard, logged to WINDOWS.md as unrun-verify id 10, still open)"
        status: unknown
    human_judgment: true
    rationale: "The password-change/reset block in user_endpoints.py/auth_password_reset_endpoints.py has no dedicated automated test asserting source=\"saml\" specifically (the LDAP equivalent added in 64-03 also has no test for the password-reset half); verified only by direct code inspection of the shared source-in-(\"ldap\",\"saml\") check."
  - id: D4
    description: "SAML NameID/attributes map to ITAM user fields (email/name) and roles via an admin-managed group-attribute-value -> role mapping (SAMLGroupMapper), matching the LDAP group-mapping pattern"
    requirement: "ITAM-USR-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_sso_saml.py::TestSAMLGroupMapper (4 tests), TestSAMLAttributeMappingEndpoint (3 endpoint tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Existing OIDC/OAuth2 in sso_service.py remains functional; the old SAML demo-stub is replaced with thin delegating wrappers, not deleted outright"
    requirement: "ITAM-USR-04"
    verification:
      - kind: unit
        ref: "Full backend suite (2039 passed / 35 skipped / 3 pre-existing unrelated fails) — no regressions in OIDC-related tests"
        status: pass
    human_judgment: false
  - id: D6
    description: "Manual end-to-end verification against a real SAML IdP (SP-initiated and IdP-initiated flows working live)"
    requirement: "ITAM-USR-04"
    verification: []
    human_judgment: true
    rationale: "No SAML IdP (Okta/Azure AD/Keycloak) is available in this sandbox environment. Only unit/endpoint tests with a mocked OneLogin_Saml2_Auth were run. Logged to WINDOWS.md (unrun-verify id 11), same accepted gap pattern as 64-03's LDAP directory verification (id 8)."

duration: 95min
completed: 2026-08-13
status: complete
---

# Phase 69 Plan 04: SAML 2.0 SSO Summary

**New `saml_service.py`/`saml_mapping.py` module pair built on `python3-saml` (human-approved via blocking checkpoint): full SP metadata/login/ACS/SLO with signature+audience+timestamp+InResponseTo+replay validation, `source="saml"` provisioning, and group-to-role mapping — replacing `sso_service.py`'s old no-validation demo stub with thin delegating wrappers while OIDC/OAuth2 stays untouched.**

## Performance

- **Duration:** ~95 min active work (across a human-verify checkpoint pause for SAML package legitimacy)
- **Tasks:** 2 (+ 1 blocking-human checkpoint, approved)
- **Files modified:** 9 (3 created, 6 modified)

## Accomplishments
- `saml_service.py`: `SAMLConfig` (env vars or admin-saved DB doc, SP private key decrypted via `encryption_service`), `SAMLAuthenticator` (SP metadata generation, SP-initiated `AuthnRequest`/login with RelayState-token request-ID correlation, ACS response validation with signature/audience/timestamp checks via python3-saml plus an independent MongoDB-TTL assertion-ID replay cache, SLO LogoutRequest/LogoutResponse handling), `authenticate_saml()` (ACS validate → provision → mint JWT by calling `authentication_service.create_access_token`/`create_refresh_token`, not duplicating token logic), `is_saml_sourced_user()`
- `saml_mapping.py`: `SAMLUserProvisioner` (NameID/attribute extraction with configurable attribute names, `source="saml"` upsert with role-clobber guard) and `SAMLGroupMapper` (group-attribute-value → ITAM role, admin CRUD, role validated against `rbac_service.default_roles`)
- `sso_endpoints.py` gained a second router (`saml_router`, no `/api/sso` prefix): 7 admin endpoints (`POST`/`GET /api/admin/sso/saml/config` with encrypted private-key storage, `GET /api/admin/sso/saml/metadata`, `POST /api/admin/sso/saml/test`, `GET`/`POST /api/admin/sso/saml/attribute-mapping` + `DELETE .../{id}`) gated by `itam_asset_endpoints._require_itam_admin`, plus 4 public routes (`GET /api/auth/saml/metadata`, `GET /api/auth/saml/login`, `POST /api/auth/saml/acs`, `GET /api/auth/saml/slo`) — ACS redirects via the existing exchange-code pattern (`_store_sso_state`/`_consume_sso_state`) instead of returning a JWT directly
- `sso_service.py`'s old SAML block (self-described "no python3-saml dependency required", confirmed by RESEARCH.md to have zero real validation) replaced with two thin delegating wrappers into `saml_service.py`; OIDC/OAuth2 (`KNOWN_OIDC_PROVIDERS`, `build_oidc_auth_url`, `handle_oidc_callback`) completely untouched
- T-64-17 (Pitfall 4 / threat_model mitigate): local password changes/resets now blocked for `source="saml"` users in `user_endpoints.update_user` and `auth_password_reset_endpoints.confirm_password_reset`, extending the existing 64-03 LDAP guard
- Registered `saml_router` in `router_registry.py` — confirmed reachable (11 routes present on the router object)
- 43 tests in `test_sso_saml.py` (25 unit from Task 1 + 18 endpoint from Task 2, all passing), full backend suite: 2039 passed / 35 skipped / 3 pre-existing unrelated failures (`test_agentic_ai` tool_choice kwarg, `test_e2e_integration` golden path, `test_rust_heartbeat_parity` agent_type field) — same baseline as 64-01/02/03, no regressions
- Both `backend/sso_service.py` (312 lines) and `backend/saml_service.py` (422 lines) verified at/under the CLAUDE.md 500-line cap per the plan's Task 1 gate

## Task Commits

Each task was committed atomically:

1. **Checkpoint: Verify SAML package legitimacy before install** — human approved `python3-saml==1.16.0` via PyPI/GitHub review (blocking-human, no code change; response: "approved — use python3-saml, not authlib-instead")
2. **Task 1: Install SAML library and build saml_service.py** - `89957639` (feat)
3. **Task 2: Create SAML admin endpoints and authentication integration** - `fc5ca454` (feat) — includes the T-64-17 Rule 2 deviation and router_registry.py Rule 3 deviation (see below)

**Plan metadata:** (this commit)

## Files Created/Modified
- `backend/saml_service.py` - SAMLConfig, SAMLAuthenticator, authenticate_saml(), is_saml_sourced_user(), RelayState/replay-cache TTL stores
- `backend/saml_mapping.py` - SAMLUserProvisioner, SAMLGroupMapper
- `backend/sso_service.py` - old SAML demo stub replaced with delegating wrappers into saml_service.py; OIDC/OAuth2 untouched
- `backend/sso_endpoints.py` - new `saml_router` with 7 admin + 4 public SAML endpoints
- `backend/router_registry.py` - registers `sso_endpoints.saml_router` (deviation, see below)
- `backend/user_endpoints.py` - `update_user` password-change guard extended to `source in ("ldap", "saml")` (deviation, see below)
- `backend/auth_password_reset_endpoints.py` - `confirm_password_reset` guard extended to `source in ("ldap", "saml")` (deviation, see below)
- `backend/requirements.txt` - `python3-saml==1.16.0` pinned exactly
- `backend/tests/test_sso_saml.py` - 25 unit tests (config, metadata, login, ACS, SLO, provisioning, group mapping, full auth flow) + 18 endpoint tests (config CRUD/masking/admin-gating, metadata, test-config, attribute-mapping CRUD, login redirect, ACS success/failure paths, SLO) — 43 tests total, all passing

## Decisions Made
See `key-decisions` in frontmatter above — summarized: (1) `python3-saml==1.16.0` chosen and human-approved over `pysaml2`/`authlib`; (2) new module pair (`saml_service.py`/`saml_mapping.py`) per the plan's `<module_budget>`, not an sso_service.py extension; (3) InResponseTo correlation via a server-side RelayState-token store; (4) replay protection as an independent assertion-ID cache on top of python3-saml's own checks; (5) no `SAML_DEFAULT_TENANT_ID` equivalent — first-time SAML provisioning with no resolvable tenant raises rather than guesses; (6) `SAML_IDP_METADATA_URL` auto-configuration deferred (manual IdP config is complete on its own); (7) `/api/admin/sso/saml/test` validates config completeness, not a live IdP round trip.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Wired T-64-17 (block local password changes for SAML-sourced users) into the actual enforcement points**
- **Found during:** Task 2, while implementing the plan's must-have truth "SAML users are provisioned/updated... source='saml' flag" alongside the threat_model's `mitigate` disposition for T-64-17
- **Issue:** The plan's `files_modified` scope (`sso_service.py`, `saml_service.py`, `sso_endpoints.py`, `tests/test_sso_saml.py`) does not include `user_endpoints.py`/`auth_password_reset_endpoints.py` — the files that actually perform local password changes. Without touching them, `source="saml"` would be written to MongoDB but nothing would enforce the plan's own Pitfall-4 requirement ("local password change blocked") against real request traffic.
- **Fix:** Extended the existing 64-03 LDAP guard (`if target_user.get("source") == "ldap"`) in both files to `if target_source in ("ldap", "saml")`, reusing the same 403 pattern.
- **Files modified:** `backend/user_endpoints.py`, `backend/auth_password_reset_endpoints.py`
- **Verification:** Manual code inspection (same accepted gap 64-03 already has for the LDAP half of `auth_password_reset_endpoints.py` — zero pre-existing test coverage in that file); logged to WINDOWS.md.
- **Committed in:** `fc5ca454` (Task 2 commit)
- **Precedent:** Exact repeat of 64-03's own Rule 2 deviation for the LDAP equivalent (T-64-12), in the same two files.

**2. [Rule 3 - Blocking] Registered `saml_router` in `router_registry.py`**
- **Found during:** Task 2, verifying the new endpoints were actually reachable
- **Issue:** New FastAPI routers in this codebase are only mounted via `router_registry.register_all_routers()`. `saml_router` (a second, un-prefixed router object added to `sso_endpoints.py` because the file's existing `router` carries a `/api/sso` prefix that doesn't match `/api/auth/saml/*` or `/api/admin/sso/saml/*`) needed its own `_load(...)` line; without it, all 11 new SAML routes would be dead code.
- **Fix:** Added `_load(app, "sso_endpoints", "saml_router")` alongside the existing `sso_endpoints`/`router` registration, matching the `itam_component_endpoints.py` two-router-per-file precedent (`router` + `asset_components_router`).
- **Files modified:** `backend/router_registry.py`
- **Verification:** `python -c "import sso_endpoints; [r.path for r in sso_endpoints.saml_router.routes]"` confirmed all 11 paths present.
- **Committed in:** `fc5ca454` (Task 2 commit)
- **Precedent:** Same Rule 3 deviation 64-03 made for `ldap_endpoints.router`.

---

**Total deviations:** 2 auto-fixed (1 Rule 2 — security-critical enforcement gap, 1 Rule 3 — blocking/dead-code), both with direct 64-03 precedent in this exact phase.
**Impact on plan:** Both were necessary for the plan's own must-have truths and threat_model mitigations to hold against real request traffic. No architectural changes; no scope creep beyond the specific enforcement points and router registration line.

## Issues Encountered
None beyond the deviations documented above. `python3-saml==1.16.0` installed cleanly via prebuilt manylinux wheels for its `lxml`/`xmlsec` dependencies — no C toolchain issues, unlike the `python-ldap` C-bindings concern that ruled it out in 64-03.

## User Setup Required
**External SAML Identity Provider requires manual configuration for live testing.** This plan's `user_setup` (frontmatter) lists all `SAML_*` env vars: `SAML_ENTITY_ID`, `SAML_ACS_URL`, `SAML_SLO_URL`, `SAML_IDP_METADATA_URL` (documented but not consumed — see Decisions), `SAML_IDP_ENTITY_ID`, `SAML_IDP_SSO_URL`, `SAML_IDP_SLO_URL`, `SAML_IDP_X509_CERT`, `SAML_SP_X509_CERT`, `SAML_SP_PRIVATE_KEY` (all cert/key values accepted either as raw PEM text or base64-wrapped PEM). No SAML IdP (Okta/Azure AD/Keycloak) was available in this sandbox — all verification used a mocked `OneLogin_Saml2_Auth` (`unittest.mock`). The plan's manual verification step ("Configure test SAML IdP, verify SP-initiated and IdP-initiated SSO end-to-end") was **not run** — logged to `.planning/WINDOWS.md` as `unrun-verify` (id 11).

## Next Phase Readiness
- `saml_service.py`/`saml_mapping.py`/`sso_endpoints.saml_router` are live, tested, and registered — ready for a real IdP to be configured via `POST /api/admin/sso/saml/config` or env vars, and for `GET /api/auth/saml/login` to be wired into `LoginPage.tsx` (untouched — no SAML entry point exists in the frontend yet, per this plan's `<frontend_scope>` deferral, same rationale as 64-03's LDAP deferral: the admin config surface needs its own settings-tab design and collides with Phase 70's ownership of `services/apiService.ts`/the ITAM console shell).
- **Follow-up for 64-06 (same wave):** if SAML login must also honor two-phase MFA, that needs to be reconciled with 64-06's rewrite of the local login handler — deliberately not attempted here (plan Task 2, item 11).
- **Follow-up (convenience feature, not a functional gap):** `SAML_IDP_METADATA_URL` auto-configuration (fetch + parse a live IdP metadata document via `OneLogin_Saml2_IdPMetadataParser`) is unimplemented; manual `idp_*` field configuration is a complete, secure alternative. Logged to `.planning/WINDOWS.md` as a deviation.
- **Follow-up (test coverage):** the `source="saml"` password-change/reset guards in `user_endpoints.py`/`auth_password_reset_endpoints.py` have no dedicated automated test (mirrors 64-03's identical LDAP-side gap). Logged to `.planning/WINDOWS.md`.
- **Follow-up (manual verification):** live SAML IdP SP-initiated/IdP-initiated round trip was not exercised in this sandbox; logged to `.planning/WINDOWS.md`.
- Full backend suite: 2039 passed / 35 skipped / 3 pre-existing unrelated failures — unchanged baseline, confirms no regressions.

---
*Phase: 64-user-management*
*Completed: 2026-08-13*

## Self-Check: PASSED

- FOUND: backend/saml_service.py
- FOUND: backend/saml_mapping.py
- FOUND: backend/sso_service.py
- FOUND: backend/sso_endpoints.py (saml_router present, 11 routes)
- FOUND: backend/router_registry.py (saml_router registered)
- FOUND: backend/user_endpoints.py (source in ("ldap","saml") guard present)
- FOUND: backend/auth_password_reset_endpoints.py (source in ("ldap","saml") guard present)
- FOUND: backend/requirements.txt (python3-saml==1.16.0 present)
- FOUND: backend/tests/test_sso_saml.py (43 tests, all passing)
- FOUND: commit 89957639 (Task 1)
- FOUND: commit fc5ca454 (Task 2)
