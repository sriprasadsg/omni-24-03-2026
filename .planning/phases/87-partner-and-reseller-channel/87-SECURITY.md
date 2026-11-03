---
phase: "87"
slug: "partner-and-reseller-channel"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-03"
---

# Phase 87 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| partner bearer token -> any /api route | The whole route table, including routes guarded only by authentication | Customer and platform data (high) |
| partner user -> /api/partner, /api/partner/customers/{id} | The partner comes from the token's tenant. The customer id comes from the client. `tenants` is exempt from the tenant wrapper | The D-01 facts of the partner's own customers |
| bearer token -> every user route | Tokens outlive a suspension unless each request checks it | Session authority |
| concurrent requests -> tenants documents | Partner, platform and enrollment writers touch the same seat counters | Seat counts (integrity) |
| Super Admin -> /api/platform/partners and partner/customer documents | Creates partner organizations and pools. Changes pool, ceiling, status and ownership | Pools, ceilings, ownership |
| platform staff -> customer seats | Licence PATCH and approve-and-raise | `license.maxAgents` |
| role documents and user administration -> permission resolver | Tenant admins and the Super Admin write role documents and role assignments | Permissions |
| role table -> drift tests | The pinned GOLDEN table and counts stop a partner role from quietly gaining a tenant or platform permission | Permission sets |
| inviter (partner or Super Admin) -> invite store | The inviter chooses the address and must never hold the token | Invite tokens (secret) |
| anonymous caller -> /api/auth/invite/status, /api/auth/login, confirm route | Public routes: token in the body; refusals must not reveal partner membership | Invite tokens, passwords |
| emailed link -> browser -> /accept-invite | The token sits in the URL on arrival; the page is reached without a session | Invite token |
| new agent -> enrollment | `hold_reason` decides whether an agent is Pending | Enrollment decisions |
| partner session -> application shell | The shell starts many background fetches meant for other roles | Customer data in background requests |
| server data -> DOM and CSV | Partner- and customer-chosen names are rendered and opened in spreadsheets | User-chosen text |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-87-01 | Information disclosure | partner_store.customer_rows | high | mitigate | Raw handle with explicit {"partnerId": partner id from the token}; rows rebuilt from CUSTOMER_FIELDS, never a stored document | closed |
| T-87-02 | Tampering | partner_pool.claim | high | mitigate | Single conditional $expr update, no read-then-write; insert failure releases the claim | closed |
| T-87-03 | Elevation of privilege | partner_endpoints.current_partner | high | mitigate | Partner role required, partner taken only from the verified token tenant and confirmed type partner and active; Super Admin gets 403 | closed |
| T-87-04 | Elevation of privilege | rbac_service.effective_permissions | high | mitigate | Partner roles return their table row only; partner permissions banned from every other role's documents | closed |
| T-87-05 | Elevation of privilege | user_endpoints create/update | high | mitigate | assert_role_fits_tenant_type on both paths; Super-Admin-only assignment of partner roles | closed |
| T-87-06 | Elevation of privilege | LDAP/SAML mapping | medium | mitigate | refuse_directory_platform_role refuses partner roles too | closed |
| T-87-07 | Tampering | change_allotment, move_customer | high | mitigate | Pool claim before customer write, compare-and-set on the customer, compensating release on a lost race | closed |
| T-87-08 | Tampering | crash between the two writes | medium | mitigate | Ordering keeps allocated at or above the true sum; daily reconcile_pools with compare-and-set repairs leaks and audits them | closed |
| T-87-09 | Denial of service | lowering a customer's seats | medium | mitigate | $expr floor against license.seatsUsed in the same update (D-06); running agents keep their seats | closed |
| T-87-10 | Elevation of privilege | verify_token_async | high | mitigate | Per-request partner status check for partner roles, before revocation, fail closed with 503 on lookup error | closed |
| T-87-11 | Information disclosure | login refusal | medium | mitigate | Suspension checked only after the password verified; wrong password keeps the generic 401 | closed |
| T-87-12 | Denial of service | partner status lookup | low | accept | A database outage stops partner sessions only (503); other roles are not looked up | closed |
| T-87-13 | Information disclosure | routes authenticated with get_current_user only | high | mitigate | PartnerScopeMiddleware allowlist; route-walk test over every mounted route; shared `bearer_token()` parser (FastAPI's own `get_authorization_scheme_param`) in every edge parser, fixed 2ae92b5d2 | closed |
| T-87-14 | Tampering | partner_viewer writes | medium | mitigate | Catalogue guard write string manage:partner_customers plus the middleware viewer refusal | closed |
| T-87-15 | Information disclosure | websocket and Socket.IO | medium | accept | Per-tenant delivery and no partner emitters (A-87-A5); flagged for a live check | closed |
| T-87-16 | Elevation of privilege | invite() return value | high | mitigate | Token and link never returned or logged; only emailed; resend refused after the first password is set | closed |
| T-87-17 | Spoofing | token guessing | medium | mitigate | 256-bit secrets.token_urlsafe tokens, SHA-256 at rest in invites, 10/minute limit on status, single use through confirm | closed |
| T-87-18 | Information disclosure | email clash refusal | medium | mitigate | One generic message for every clash, case-insensitive, no organization named | closed |
| T-87-19 | Information disclosure | token in URLs and logs | medium | mitigate | Status route takes the token in the body; no logger call carries the token or link | closed |
| T-87-20 | Elevation of privilege | viewAccess partner-only views | low | mitigate | Role gate before the owner short-circuit; the server (87-05) is the real wall | closed |
| T-87-21 | Information disclosure | suspended session left open in a tab | medium | mitigate | X-Partner-Suspended header ends the session and clears tokens on the next call | closed |
| T-87-22 | Repudiation | appoint, change, suspend, reinstate, move | medium | mitigate | audit_ledger.event under platform-admin and each partner chain with before/after values | closed |
| T-87-23 | Tampering | pool resize | high | mitigate | partner_pool.set_pool_size conditional update (D-07) | closed |
| T-87-24 | Elevation of privilege | screen ceiling | medium | mitigate | validate_ceiling accepts only tenant_features.SWITCHABLE strings or the single all | closed |
| T-87-25 | Denial of service | suspension | high | mitigate | suspend writes only the partner document and sessions; customers and agents untouched (D-15), proven by a byte-for-byte test | closed |
| T-87-26 | Information disclosure | customer id in path | high | mitigate | Every lookup filters {"id", "partnerId": token partner}; foreign and unknown ids both 404 | closed |
| T-87-27 | Elevation of privilege | customer features | high | mitigate | Server-side ceiling check against tenant_features vocabulary; "all" refused; kept screens only retained (D-10, D-19) | closed |
| T-87-28 | Information disclosure | overview and create responses | high | mitigate | Rows built from CUSTOMER_FIELDS only; tests walk responses for forbidden keys | closed |
| T-87-29 | Elevation of privilege | resend | high | mitigate | Resend only within the caller's partner and only before a password is set; never for customer admins | closed |
| T-87-30 | Information disclosure | name clash refusal | low | mitigate | One generic message, no organization named | closed |
| T-87-31 | Tampering | licence PATCH, approve raise | high | mitigate | Both route through partner_pool.change_allotment for partner customers; drift test forbids new writers | closed |
| T-87-32 | Tampering | deleting a partner with customers | medium | mitigate | 409 refusal; customer deletion releases its seats | closed |
| T-87-33 | Elevation of privilege | enrollment after pool expiry | medium | mitigate | hold_reason returns license_expired from the partner's expiry (D-08) | closed |
| T-87-34 | Information disclosure | MSSP lists | low | mitigate | type partner excluded from the three listings | closed |
| T-87-35 | Tampering | client-side floors and fit checks | low | accept | Advisory only; the server enforces D-07 and D-18 (87-03, 87-08) | closed |
| T-87-36 | Information disclosure | XSS through names | medium | mitigate | React text rendering only; no dangerouslySetInnerHTML (acceptance grep) | closed |
| T-87-37 | Tampering | CSV export | medium | mitigate | toCsv/csvCell quote per RFC 4180 and prefix formula characters (tested) | closed |
| T-87-38 | Information disclosure | portal rendering | high | mitigate | Only the D-01 fields are rendered or exported (DOM and CSV tests) | closed |
| T-87-39 | Elevation of privilege | viewer controls | medium | mitigate | Controls removed for viewers; the server refuses writes regardless (87-05) | closed |
| T-87-40 | Information disclosure | token in address bar, history, referrer | medium | mitigate | replaceState before any request; token kept in component memory only; status call uses a POST body | closed |
| T-87-41 | Information disclosure | password handling | medium | mitigate | Password never logged, never in a URL, never stored beyond the existing session token | closed |
| T-87-42 | Information disclosure | shell background fetches for partner users | medium | mitigate | loadAllData returns early; header widgets that fetch are not rendered; the server allowlist (87-05) refuses the rest | closed |
| T-87-43 | Spoofing | /accept-invite while another user is signed in | low | accept | Signing in with the invite replaces the tab's session; nothing of the previous session is shown on the page | closed |
| T-87-44 | Tampering | test_rbac_defaults GOLDEN and the pinned manifest counts | medium | mitigate | Counts move by exactly the two views, two nav entries, two sliced views, two roles and one super-admin-only permission 87-01 adds; GOLDEN names the exact partner permissions, so a widened partner role fails the suite | closed |
| T-87-45 | Elevation of privilege | test_sidebar_screen_switches TENANT_PERMS | low | mitigate | Exclusion is by rbac_defaults.PARTNER_ROLE_KEYS only, never by permission string, so a tenant role that gained view:partner_portal would make the Partner portal tenant-reachable and fail the switch test | closed |
| T-87-SC | Tampering | npm/pip installs | low | accept | No package is installed by this plan | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low. Only open threats at or above workflow.security_block_on (high) count toward threats_open.*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

### Closed threat T-87-13: partner wall bypassed by the Authorization scheme spelling

**Fixed 2026-11-03.**
- **Tests:** 92aa01b57 adds the tests, fixed in 2ae92b5d2.
- **Change:** `bearer_token()` in `backend/tenant_middleware.py` parses the header with FastAPI's own `get_authorization_scheme_param` and the same case-insensitive scheme test `OAuth2PasswordBearer` applies. Three readers use it: `_bearer_role` (the partner, platform read-only and screen-switch walls), `TenantMiddleware`, and the audit actor (`audit_middleware.actor_of`).
- **Evidence:**
  - Four new tests in `backend/tests/test_partner_route_walk.py` pass. One compares the walls' role reader with the real `OAuth2PasswordBearer` dependency across 12 header spellings.
  - The auditor's probe now gets 403 for all five spellings, where four previously reached the app.
  - A suite of 613 tests on a private mongod, covering partners, parity, middleware and audit, gave 610 passed. The 3 failures are the 2 baseline names plus `test_platform_roles::test_user_endpoints_apply_the_last_owner_guard`. That last one already failed before this fix: its fake database lacks `tenants`, which the Phase 87 tenant-type check reads.
- **`backend/export_controls.py`:** it had the same exact-prefix parser, so a `bearer` request skipped the daily export allowance. Its `_caller` now uses `bearer_token()` too. The file is uncommitted user work, so the change stays in the working tree and is not committed.

The original finding follows.

- **What the auditor found (2026-11-03):** `PartnerScopeMiddleware` (`backend/partner_middleware.py:62`) reads the role through `_bearer_role` (`backend/tenant_middleware.py:101-111`). That function only recognizes the exact prefix `"Bearer "` and decodes `auth[7:]`.
- **Why that is a bypass:** FastAPI 0.141.1 `OAuth2PasswordBearer`, which `get_current_user` uses, matches the scheme case-insensitively (`scheme.lower() != "bearer"`) and strips the parameter.
  - So a valid partner token sent as `bearer <t>`, `BEARER <t>`, `Bearer  <t>` (two spaces) or `Bearer <t> ` (trailing space) skips the allowlist.
  - `get_current_user` still accepts it.
  - The orchestrator confirmed both parsers by reading the code. The auditor's probe is in the session scratchpad (`audit87/probe_bearer.py`).
- **Reach:**
  - The catalogue guards (the first wall) still refuse partners on every guarded surface: `/api/tenants`, `/api/mssp`, `/api/assets`, `/api/agents`, `/api/users` and `/api/platform/partners`.
  - What is exposed is the set of routes protected only by `get_current_user`, which the edge allowlist was meant to cover. That set was not enumerated.
- **Why the tests miss it:** they call `partner_request_refusal` directly, and the mounted-middleware test only sends `Bearer <token>`.
- **Same parser elsewhere:** `PlatformReadOnlyMiddleware` and `ScreenSwitchMiddleware` (`backend/tenant_middleware.py:53,78`) also use `_bearer_role`. Similar hand-written parsers exist at `backend/audit_middleware.py:69`, `backend/export_controls.py:46` and `backend/tenant_middleware.py:177-182`. The weakness may predate Phase 87 for those walls.
- **Suggested fix:**
  - Parse the header the way FastAPI does: `partition(" ")`, a case-insensitive scheme, and `strip()` on the parameter. Do it in one shared helper.
  - Add scheme-spelling variants to the mounted-middleware test.
  - Check whether nginx passes the header unchanged.
  - Then re-run `/gsd-secure-phase 87`.

### Note on T-87-15 (accepted, medium): `/api/stream/live` fixed 2026-11-03

**Fixed.**
- **Tests:** cab219d81 adds them, fixed in e693da59e.
- **Partners:** the live feed now refuses partner roles at the handshake (close code 4403).
- **Everyone else:** they receive the platform-wide `system_stats` window counts. `logs` and `security_events` reach them only when the event is tagged with their own tenant.
- **Untagged events:** UEBA's platform-wide IP bans and super-admin broadcasts go to platform staff only (`can_read_all_tenants`), who still receive everything.
- **Evidence:** four live-feed tests in `backend/tests/test_tenant_boundary_hardening.py`.
- **Still to do:** the live check A-87-A5 remains for Socket.IO.

The original note follows.

`backend/stream_processing_endpoints.py:66-110` accepts any active JWT, an active partner's included. It subscribes every client to the global `system_stats`, `logs` and `security_events` topics with no tenant filter or role check. Two services publish tenant-tagged data to those topics:
- `backend/log_endpoints.py:69` publishes logs.
- `backend/ueba_alert_persistence_service.py:42` publishes UEBA alerts.

`PartnerScopeMiddleware` handles HTTP scopes only. The "per-tenant delivery" rationale for accepting T-87-15 therefore does not hold for this route, although Socket.IO (`backend/websocket_manager.py`) does deliver per sid and per tenant.

The leak exists for every tenant today, so it is not new in Phase 87. T-87-15 is below the block threshold and stays accepted. Before shipping partners:
- add a partner-role refusal or tenant filtering to the `/live` handshake;
- otherwise the live check A-87-A5 will fail on this route.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-87-01 | T-87-12 | If the partner-status lookup fails, only partner sessions stop (503), and non-partner tokens cause no lookup. Planned in 87-04-PLAN.md | Phase 87 plan (user-approved plan set) | 2026-11-02 |
| AR-87-02 | T-87-15 | Socket.IO reach for partner sessions is accepted pending the live check A-87-A5. `/api/stream/live` was fixed on 2026-11-03 (e693da59e): it refuses partners and filters by tenant | Phase 87 plan (user-approved plan set) | 2026-11-02 |
| AR-87-03 | T-87-35 | The Partners screen's UI rules are advisory. The server enforces D-07 (`backend/partner_pool.py:157`) and D-18 (`:188`) | Phase 87 plan (user-approved plan set) | 2026-11-02 |
| AR-87-04 | T-87-43 | Opening /accept-invite while signed in replaces the tab's session, and the page shows nothing of the previous session | Phase 87 plan (user-approved plan set) | 2026-11-02 |
| AR-87-05 | T-87-SC | No package was installed. No Phase 87 commit changes package.json, package-lock.json, backend/requirements*.txt or Cargo.toml | Phase 87 plan (user-approved plan set) | 2026-11-02 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-03 | 46 | 45 | 1 (T-87-13, high, blocking) | gsd-security-auditor (sonnet), orchestrator confirmed T-87-13 in code |
| 2026-11-03 | 46 | 46 | 0 | orchestrator, after the T-87-13 fix 2ae92b5d2 (tests and the auditor's probe) |
| 2026-11-03 | 46 | 46 | 0 | gsd-security-auditor (sonnet), independent re-check of T-87-13/14/15 after fixes 2ae92b5d2 and e693da59e. A differential test of 23 header shapes found 0 bypasses. A backend-wide parser search found no parser looser than FastAPI. The other 43 closures stand |

The auditor checked every closed threat at L1 depth: the code is present and a test is cited. It ran 236 partner and catalogue tests on a private mongod (all passed), and modified no implementation files.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed (T-87-13 fixed in 2ae92b5d2)
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-03. The orchestrator closed T-87-13 after the fix, and `/gsd-secure-phase 87` re-checked it independently (SECURED, threats_open 0).

## Security Audit 2026-11-03

| Metric | Count |
|---|---|
| Threats found | 46 |
| Closed | 45 |
| Open | 1 |

## Security Audit 2026-11-03

| Metric | Count |
|---|---|
| Threats found | 46 |
| Closed | 46 |
| Open | 0 |
