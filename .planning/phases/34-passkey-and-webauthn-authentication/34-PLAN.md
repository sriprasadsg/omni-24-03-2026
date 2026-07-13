# Phase 34: Passkey and WebAuthn Authentication - Plan

**Goal:** Add WebAuthn/FIDO2 passkey registration and login as an alternative to password/SSO/TOTP.

**Requirements:** AUTH-01

**Waves:** 3
- **Wave 1:** Backend service, endpoints, and tests (TDD).
- **Wave 2:** Frontend UI components.
- **Wave 3:** Integration and human verification.

---
## Plan 34-01: Backend Service, Endpoints, and Tests

**Goal:** Implement the backend logic for passkey registration and authentication.

**Tasks:**

1.  **Checkpoint:** Human-verify the `webauthn` and `soft-webauthn` PyPI packages before installation. The package legitimacy audit in `34-RESEARCH.md` flagged them as `[SUS]`. This checkpoint must pass before proceeding.

2.  **Dependencies:**
    -   Add `webauthn>=3.0.0,<4.0.0` to `backend/requirements.txt` under a new `# WebAuthn / Passkeys` section.
    -   Add `soft-webauthn>=0.1.4,<0.2.0` to a new `backend/requirements-dev.txt` for test-only use.

3.  **Service (`passkey_service.py`):**
    -   Create `backend/passkey_service.py`.
    -   Implement the in-memory challenge store (`_webauthn_challenges`, `store_challenge`, `consume_challenge`) following the pattern from `mfa_service.py`.
    -   Derive `RP_ID` and `ORIGIN` from `PLATFORM_URL` at module load.
    -   Implement `build_registration_options` to wrap `webauthn.generate_registration_options`.
    -   Implement `verify_and_store_registration` to wrap `webauthn.verify_registration_response` and persist the credential to `users.webauthn_credentials`.
    -   Implement `build_authentication_options`.
    -   Implement `verify_authentication` to wrap `webauthn.verify_authentication_response`, handle sign-count logic, and return the user on success.

4.  **Endpoints (`passkey_endpoints.py`):**
    -   Create `backend/passkey_endpoints.py`.
    -   Implement registration endpoints:
        -   `POST /api/passkey/register/options` (authenticated)
        -   `POST /api/passkey/register/verify` (authenticated)
    -   Implement login endpoints (unauthenticated, rate-limited):
        -   `POST /api/passkey/login/options`
        -   `POST /api/passkey/login/verify` (mints JWTs using `authentication_service` helpers)
    -   Implement credential management endpoints (authenticated):
        -   `GET /api/passkey/credentials`
        -   `DELETE /api/passkey/credentials/{credential_id}`

5.  **Registration:**
    -   Add `_load(app, "passkey_endpoints", "router")` to `backend/router_registry.py`.

6.  **Tests (`test_passkey_auth.py`):**
    -   Create `backend/tests/test_passkey_auth.py`.
    -   Use `soft-webauthn`'s `SoftWebauthnDevice` to drive end-to-end ceremony tests without a browser.
    -   Cover: successful registration, successful login, challenge replay, challenge expiry, sign-count check, and tenant isolation.
    -   Ensure all existing auth tests in `test_authentication.py` and `test_auth_mfa.py` still pass.

**Verification:**
- All new and existing tests must pass.
- `wc -l backend/authentication_endpoints.py` must remain <= 500 lines.

---
## Plan 34-02: Frontend UI

**Goal:** Build the user interface for registering, managing, and logging in with passkeys.

**Tasks:**

1.  **Dependency:**
    -   Run `npm install @simplewebauthn/browser@^13.3.0`.

2.  **API Service (`apiService.ts`):**
    -   Add functions for all new passkey endpoints:
        -   `passkeyRegisterOptions`
        -   `passkeyRegisterVerify`
        -   `passkeyLoginOptions`
        -   `passkeyLoginVerify`
        -   `listPasskeys`
        -   `deletePasskey`

3.  **Login Page (`LoginPage.tsx`):**
    -   Add a "Sign in with a passkey" button.
    -   Wire the button to the `passkeyLoginOptions` and `passkeyLoginVerify` flow using `@simplewebauthn/browser`.

4.  **Profile Page (`UserProfilePage.tsx`):**
    -   Add a "Passkeys" section to the "Security" card.
    -   Display a list of registered passkeys with a "Remove" button.
    -   Add a "Register a new passkey" button that opens `PasskeySetupModal.tsx`.

5.  **New Component (`PasskeySetupModal.tsx`):**
    -   Create `components/PasskeySetupModal.tsx`.
    -   Provide a UI for naming a new passkey and triggering the registration flow (`passkeyRegisterOptions`, `passkeyRegisterVerify`).

**Verification:**
- All frontend components render correctly and handle loading/error states.
- All new UI flows are usable.

---
## Plan 34-03: Integration and Human Verification

**Goal:** Verify the end-to-end passkey flow in a running application and confirm no regressions.

**Tasks:**

1.  **Run Application:** Start the backend and frontend development servers.

2.  **Human Verification:**
    -   **Registration:**
        -   Log in with a password.
        -   Navigate to the user profile page.
        -   Register a new passkey (e.g., Touch ID, Windows Hello).
        -   Verify the passkey appears in the list.
    -   **Login:**
        -   Log out.
        -   Use the "Sign in with a passkey" button to log in.
        -   Verify login succeeds.
    -   **Management:**
        -   Navigate back to the profile page.
        -   Remove the registered passkey.
        -   Verify it is removed from the list.
    -   **Regression:**
        -   Log out and log back in with the original password and MFA (if enabled) to confirm existing flows are unaffected.

**Verification:**
- All human verification steps complete successfully.
- AUTH-01 requirement is met.
