---
status: testing
phase: 69-user-management
source: [64-VERIFICATION.md]
started: 2026-08-13T08:47:11Z
updated: 2026-08-13T08:47:11Z
---

## Current Test

number: 1
name: LDAP/AD end-to-end authentication against a real directory
expected: |
  Configure a real LDAP/AD server per 64-03's user_setup env vars (LDAP_URI, LDAP_BIND_DN,
  LDAP_BIND_PASSWORD, LDAP_USER_BASE_DN, LDAP_GROUP_BASE_DN, etc.), then run
  POST /api/admin/ldap/test-connection, POST /api/admin/ldap/sync, and log in via
  POST /api/auth/ldap/login. Bind succeeds, users/groups sync into MongoDB with
  source="ldap" and correct role mapping, and a directory user receives a valid JWT.
awaiting: user response

## Tests

### 1. LDAP/AD end-to-end authentication against a real directory
expected: Configure a real LDAP/AD server per 64-03's user_setup env vars, then run POST /api/admin/ldap/test-connection, POST /api/admin/ldap/sync, and log in via POST /api/auth/ldap/login. Bind succeeds, users/groups sync into MongoDB with source="ldap" and correct role mapping, and a directory user receives a valid JWT.
result: [pending]

### 2. SAML SSO end-to-end against a real Identity Provider
expected: Configure a real SAML IdP (Okta/Azure AD/Keycloak) per 64-04's user_setup env vars, then exercise both SP-initiated (GET /api/auth/saml/login) and IdP-initiated SSO through to a minted JWT, plus GET /api/auth/saml/slo. AuthnRequest/redirect, ACS assertion validation (signature/audience/timestamp/InResponseTo/replay-cache), source="saml" provisioning, and SLO all work against the live IdP.
result: [pending]

### 3. Live-browser click-through of the tightened MFA disable form
expected: In a running browser session, enable 2FA on a test account, then use UserProfilePage.tsx's inline disable-2FA form to disable it with the account password. The form renders a password input (not the prior 6-digit TOTP field) and correctly labeled; submitting the correct password successfully disables 2FA via POST /api/mfa/disable; submitting a wrong password shows an inline error and is rate-limited after 5 attempts/minute.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
