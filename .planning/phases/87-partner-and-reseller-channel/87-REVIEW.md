---
phase: 87-partner-and-reseller-channel
reviewed: 2026-11-03T20:01:49Z
depth: standard
files_reviewed: 84
files_reviewed_list:
  - App.tsx
  - backend/app_background_tasks.py
  - backend/app_middleware.py
  - backend/authentication_endpoints.py
  - backend/authentication_service.py
  - backend/catalogue_mounts_partners.py
  - backend/invite_endpoints.py
  - backend/license_rules.py
  - backend/licensing.py
  - backend/migrations/029_partner_channel.py
  - backend/mssp_endpoints.py
  - backend/partner_endpoints.py
  - backend/partner_invites.py
  - backend/partner_middleware.py
  - backend/partner_platform_endpoints.py
  - backend/partner_platform_service.py
  - backend/partner_pool.py
  - backend/partner_portal_service.py
  - backend/partner_status.py
  - backend/partner_store.py
  - backend/pending_agents.py
  - backend/rbac_defaults.py
  - backend/rbac_service.py
  - backend/role_assignment.py
  - backend/router_registry.py
  - backend/tenant_docs.py
  - backend/tenant_endpoints.py
  - backend/tenant_features.py
  - backend/tests/_catalogue_parity.py
  - backend/tests/test_catalogue_manifest.py
  - backend/tests/test_catalogue_route_parity.py
  - backend/tests/test_catalogue_slice_partners.py
  - backend/tests/test_custom_role_mfa.py
  - backend/tests/test_partner_ceiling.py
  - backend/tests/test_partner_customers.py
  - backend/tests/test_partner_expiry.py
  - backend/tests/test_partner_invites.py
  - backend/tests/test_partner_isolation.py
  - backend/tests/test_partner_license_writers.py
  - backend/tests/test_partner_move.py
  - backend/tests/test_partner_platform.py
  - backend/tests/test_partner_pool.py
  - backend/tests/test_partner_roles.py
  - backend/tests/test_partner_route_walk.py
  - backend/tests/test_partner_suspension.py
  - backend/tests/test_partner_tracer.py
  - backend/tests/test_partner_usage.py
  - backend/tests/test_rbac_defaults.py
  - backend/tests/test_route_auth_baseline.py
  - backend/tests/test_session_revocation.py
  - backend/tests/test_sidebar_screen_switches.py
  - backend/user_endpoints.py
  - components/AcceptInvitePage.tsx
  - components/Header.tsx
  - components/LoginPage.tsx
  - components/PartnerCustomerModals.tsx
  - components/PartnerFormModal.tsx
  - components/PartnerMoveCustomerModal.tsx
  - components/PartnerPortal.tsx
  - components/PartnerScreenPicker.tsx
  - components/PartnerStatusChip.tsx
  - components/PartnerStatusDialogs.tsx
  - components/PartnerTeamPanel.tsx
  - components/PartnersDashboard.tsx
  - components/Sidebar.tsx
  - components/sidebarPresentation.tsx
  - contexts/FeaturesContext.tsx
  - services/apiService.ts
  - services/partnerApi.ts
  - shared/catalogue-access.json
  - src/__tests__/AcceptInvitePage.test.tsx
  - src/__tests__/PartnerAdminModals.test.tsx
  - src/__tests__/PartnerPortal.test.tsx
  - src/__tests__/PartnerPortalModals.test.tsx
  - src/__tests__/PartnerScreenPicker.test.tsx
  - src/__tests__/PartnerShell.test.tsx
  - src/__tests__/PartnersDashboard.test.tsx
  - src/__tests__/SidebarFailClosed.test.tsx
  - src/__tests__/catalogueAccess.test.ts
  - src/__tests__/partnerAccess.test.ts
  - src/__tests__/viewAccess.test.ts
  - types.ts
  - utils/permissions.ts
  - utils/viewAccess.ts
findings:
  critical: 0
  warning: 11
  info: 10
  total: 21
status: issues_found
---

# Phase 87: Code Review Report

**Depth:** standard. **Files reviewed:** 84. **Status:** issues_found (0 critical, 11 warning, 10 info).

The 84-file scope was split into two lanes reviewed in parallel. Each finding title carries its lane.
- **[backend]** 51 files: backend source and tests. WR-01..07 and IN-01..06.
- **[frontend]** 33 files: frontend source and tests. The lane's WR-01..04 became WR-08..11 and its IN-01..04 became IN-07..10.

The orchestrator corrected the backend lane's `backend/partner_pool.py` line citations, which pointed past the end of the 254-line file. The substance was confirmed against the code: `claim` returns True for `n == 0` at lines 49-50, and login matches the email exactly in `authentication_endpoints.py:173-178`.

Already recorded elsewhere and not repeated as findings:
- T-87-13, the Authorization-scheme bypass of the partner wall, in 87-SECURITY.md. The backend lane confirmed it and noted that the same exact-prefix check in `TenantMiddleware` also lets lower-case `bearer` past `PlatformReadOnlyMiddleware` and `ScreenSwitchMiddleware`.
- The `/api/stream/live` reach of partner sessions, also in 87-SECURITY.md.
- The visual and accessibility items in 87-UI-REVIEW.md.

## Summary

### [backend]

Reviewed all new partner_*.py, invite_endpoints.py, catalogue_mounts_partners.py, license_rules.py, migration 029 and
role_assignment.py in full, and the Phase 87 diffs (b1578773..HEAD) of the large pre-existing files together with the
code they call into. The 13 backend partner test modules (218 tests) pass against a private mongod on port 27998
(since stopped and removed).

The seat-pool design (claim first on increase, write customer first on decrease, compare-and-set on the customer, reconcile
with a settle pause) holds up under adversarial reading. I found no over-sell path and no cross-partner read or write: every
partner query is pinned to the token's tenant, and customer rows are rebuilt key by key from `CUSTOMER_FIELDS`. No
blocker-grade defect is in the backend lane beyond the two already recorded in 87-SECURITY.md. The findings are
robustness, completeness and consistency defects, the most notable being partner roles leaking into tenant admins' role lists,
an unhandled unique-index race that turns into a 500, orphaned invited users, and the mixed-case email login mismatch.

Already-recorded items, confirmed rather than rediscovered:
- T-87-13 is confirmed. `_bearer_role` (backend/tenant_middleware.py:104) requires the exact `"Bearer "` prefix, while FastAPI's
  OAuth2 scheme accepts any case, so `PartnerScopeMiddleware` (backend/partner_middleware.py:265) sees `role=None` and lets
  `authorization: bearer <partner token>` through to every `get_current_user` route. `TenantMiddleware` has the same exact-prefix
  check at tenant_middleware.py:176. This also bypasses `PlatformReadOnlyMiddleware` and `ScreenSwitchMiddleware`.
- `/api/stream/live` delivery of global topics to a partner JWT (87-SECURITY.md) was not re-investigated.
- The route-walk test (`backend/tests/test_partner_route_walk.py:54`) tolerates any non-`/api/` path as allowed. I ran the real
  route table and found no HTTP route outside `/api/`, so this is not exploitable today. A future non-`/api` router would bypass
  the allowlist unnoticed.

### [frontend]

The Partner*.tsx files, AcceptInvitePage.tsx and partnerApi.ts were read in full. The Phase 87 hunks of the large pre-existing files were read through `git diff b1578773..HEAD` and `git show HEAD:App.tsx`. The 11 test files were run (318 tests, all pass).

The things the lane notes asked about hold up:

- **D-01 facts only.** The Partner portal renders and exports only the six D-01 facts. The CSV maps exactly those columns through `toCsv`, which already neutralises formula cells. Customer names are never links or tooltips.
- **Partner shell requests.** The partner shell makes no customer-route requests I could find:
  - `loadAllData` returns early on the JWT role.
  - The Sidebar unread poll, the FeaturesContext bundles read, the Header command palette, search, notification centre and the floating assistants are all gated.
  - The `App.tsx` ⌘K and ⌘/ handler is guarded, and `ShellServices` and `CommandPalette` add no key listener of their own that opens the palette.
- **Accept-invite token and password handling.**
  - The token is stripped from the URL before the first request and sent only in POST bodies.
  - The password never enters a URL or a log, and it is cleared on every exit.
  - A 400 re-asks the invite status, and in-flight double submit is guarded by a ref.
  - The client password rules match `auth_utils.validate_password_complexity`.
- **Role-name risk.** A tenant cannot create a custom role that the frontend would mistake for a partner role: `role_contents.validate_role_name` refuses built-in keys in any spelling.

No security or data-exposure defects were found in this lane. What remains is stale-data and state-handling defects, plus one date-display inconsistency.

## Warnings

### WR-01: [backend] Partner roles are listed and readable to every tenant admin

**File:** `backend/role_endpoints.py:130-131` (caused by `backend/rbac_defaults.py:262-266`, `backend/role_assignment.py:24-26`)
**Issue:** Phase 87 appended `partner_admin` and `partner_viewer` to `BUILTIN_ROLES`, but the role list hides only
`PLATFORM_ROLE_KEYS` from non-super callers. A tenant admin calling `GET /api/roles` therefore sees "Partner Admin" and
"Partner Viewer", with their permissions (`manage:partner_customers`, `view:partner_portal`), and so does the role dropdown built
from it. `GET /api/roles/{role_id}` (line 326-328) also serves `role-partner-admin` to a non-super caller because its fence is
also `PLATFORM_ROLE_KEYS`. Picking one fails later, at `assert_can_assign_role` with a 403 (backend/role_assignment.py:171). This
leaks the existence and permission set of the reseller channel to every tenant, and it is a UX trap. D-04 says these roles stay
out of every platform and tenant surface.
**Fix:**
```python
# role_endpoints.py list_roles and role detail
hidden = rbac_defaults.PLATFORM_ROLE_KEYS | rbac_defaults.PARTNER_ROLE_KEYS
if builtin.key in hidden and not caller_is_super:
    continue
...
if builtin is not None and builtin.key in hidden:   # detail route
```
Add a test that a tenant admin's `GET /api/roles` contains neither partner key.

### WR-02: [backend] Unique-index races on tenant name surface as HTTP 500 and (for appoint) are not cleaned up consistently

**File:** `backend/partner_platform_service.py:90`, `backend/partner_portal_service.py:111`, `backend/partner_platform_service.py:149`
**Issue:** `name_taken` is a check-then-write. `tenants.name` carries a unique index (backend/database.py:327), so two concurrent
creates, or a create racing a rename, pass the check and the loser raises `DuplicateKeyError` from `insert_one` or `update_one`.
No caller maps it to the `name_unavailable` 409 contract. In `create_customer` the seats are correctly released by the bare
`except Exception` and then the error is re-raised, so the partner sees a raw 500 instead of "That name isn't available."
In `appoint` nothing was written yet so the 500 is clean but unmapped. In `update_partner` the pool resize has already been
applied (`set_pool_size`, line 145) when the later `$set` of `name` raises, leaving a half-applied update with no audit.
**Fix:** catch `pymongo.errors.DuplicateKeyError` around those three writes and raise
`PartnerError(409, "name_unavailable", ...)`. In `update_partner`, put the `name` set (the only write that can collide) before
`set_pool_size`, or fold both into one `update_one`.

### WR-03: [backend] `invite()` leaves an unreachable, un-resendable user when issuing the link fails

**File:** `backend/partner_invites.py:139-150`, `backend/partner_invites.py:190-195`
**Issue:** `invite()` inserts the user (Active, random password) and then calls `issue_invite`. If `issue_invite` raises (a
Mongo error on `password_reset_tokens` or `invites`), the user stays. `create_customer` and `appoint` clean up, but
`invite_colleague` (backend/partner_portal_service.py:229-241) does not. The address is then "in use" for every later invite
(`email_in_use`), and `resend` refuses it with `already_active` because `member_status` reports `"active"` when no invite row
exists (line 184-186). The colleague can never be invited again without database surgery.
**Fix:** wrap `issue_invite` in `invite()`: on failure `await _raw(db).users.delete_one({"id": user_id})` and re-raise. (The
callers' own cleanup then remains a harmless superset.)

### WR-04: [backend] Invited users are stored lower-cased but login matches the email exactly

**File:** `backend/partner_invites.py:53-57`, `backend/partner_invites.py:139-141`, `backend/authentication_endpoints.py:170-175`
**Issue:** `normalize_email` lower-cases the address, which is what is stored on the user and what the link is bound to. Login
looks the user up with `{"$or": [{"username": identifier}, {"email": identifier}]}`, an exact case-sensitive match on the string
the user types. An invitee whose address was typed `Jane.Doe@Corp.com` by the partner and who later signs in with the
capitalization of their own mailbox gets the generic "Invalid credentials" (and counts toward the lock-out). Pre-existing users
are stored as typed, so the platform has relied on typed-case equality until now; the invite flow breaks that for any mixed-case
address.
**Fix:** make the login lookup case-insensitive for email (lower-case the identifier and match `email` against the lower-cased
value, with a fallback for legacy mixed-case documents), or store the address as typed and compare case-insensitively
everywhere. Do not change only one side.

### WR-05: [backend] A 0-seat customer can be moved into a suspended partner (claim returns True for n == 0 without any check)

**File:** `backend/partner_pool.py:49-50`, `backend/partner_pool.py:188`
**Issue:** `claim()` returns `True` for `n == 0` before it looks at the partner, so `move_customer(..., require_active=True)` skips
the suspension check for a customer with 0 seats. Verified on a private mongod: a customer with `maxAgents: 0` was moved into a
partner whose `partner.status` is `suspended`, and `partnerId` was written. Moves into a suspended partner are refused for any
customer with seats, so this is inconsistent. The same early return also skips partner existence, although `move_customer` checks
that separately.
**Fix:** in `claim`, only short-circuit when `n == 0` and the partner passes the same `type`/`status` filter, for example
`if n == 0: return await _raw(db).tenants.count_documents({...query without $expr}, limit=1) == 1`. Alternatively check
`target["partner"]["status"]` explicitly in `move_customer`.

### WR-06: [backend] A losing compare-and-set transiently over-claims the pool and can refuse an unrelated, valid request

**File:** `backend/partner_pool.py:132-135`
**Issue:** For a raise, `change_allotment` claims the pool first and only then runs the customer compare-and-set. When the CAS
loses (a concurrent change of the same customer) the claim is released, but between claim and release `partner.allocated` is
too high by `delta`. A different customer's valid raise in that window sees `pool_full` and the partner gets "Only N seats are
free" although the seats were free. The test `test_twenty_concurrent_raises_of_one_customer_succeed_once` only covers one
customer, where this is invisible. The over-sell invariant is intact; the defect is a spurious refusal. The same shape exists for
`move_customer` at lines 196-201 (orchestrator-corrected citation).
**Fix:** acceptable as documented behavior, but then say so in the module docstring and make `_claim_refusal` retry once (re-run the
claim after a short pause) before it reports `pool_full` when `free < n` could have been caused by an in-flight claim. Otherwise
read the customer first and use a single-document compare-and-set before claiming (claim only after a successful pre-check).

### WR-07: [backend] Pool reconcile is placed ahead of the other seat upkeep in the same try and sleeps inside request paths

**File:** `backend/app_background_tasks.py:337-342`, `backend/partner_pool.py:70-73`, `backend/partner_pool.py:231`
**Issue:** `partner_pool.reconcile_pools(db)` runs inside the same `try` as `licensing.reclaim_inactive_agents` and
`license_rules.send_expiry_reminders`. If it raises (a malformed partner document, or a failing audit write that is not caught),
the 24-hourly iteration skips agent-seat reclamation and expiry reminders for that hour. Separately, `release()` calls
`reconcile_partner` whenever its conditional decrement does not match, and that function does `asyncio.sleep(RECONCILE_SETTLE_SECONDS)`
(1 s) before it repairs. `release` is awaited inside `PUT /api/partner/customers/{id}/seats`, `delete_tenant`, and the
failure-cleanup paths, so a request that hits a drifted counter stalls for a second and runs two aggregates.
**Fix:** wrap each reconcile call in its own `try/except` with logging (or put it in a separate loop iteration), and have `release`
schedule the repair as a background task (`asyncio.create_task`) instead of awaiting it.

### WR-08: [frontend] Partners screen keeps a stale customer list for any partner that is collapsed during a refresh

**File:** `components/PartnersDashboard.tsx:265-278`
**Issue:** `toggle` fetches a partner's customers only when `customers[partner.id]` is empty (line 277). `refreshAll` (lines 265-268) refetches customers only for partners in `expandedRef.current`.
- After a move, the Super Admin may have moved a customer from partner A to partner B while B was collapsed. B's cached `ready` rows are never invalidated.
- Expanding B later shows the old list, without the customer just moved in. The same happens for seat counts after any change.
- The stale row exposes a "Move customer" button for a customer that is no longer there, which then fails.
**Fix:** Invalidate the cache for partners that are not open, and refetch on every expand:
```tsx
const refreshAll = useCallback(() => {
  void load(false);
  const open = expandedRef.current;
  setCustomers(prev => Object.fromEntries(Object.entries(prev).filter(([id]) => open.has(id))));
  open.forEach(id => { void loadCustomers(id); });
}, [load, loadCustomers]);
```
Alternatively, drop the `!customers[partner.id]` condition in `toggle` so each expand reloads.

### WR-09: [frontend] Expiry dates display in the browser's time zone but are saved and edited as UTC days

**File:** `components/PartnerStatusChip.tsx:56-62` (used by `PartnerPortal.tsx:98,311,318,333` and `PartnersDashboard.tsx:99`); written at `components/PartnerFormModal.tsx:103,134`
**Issue:**
- The form stores the chosen day as `${expiresOn}T23:59:59Z`.
- The edit form and the CSV read the day back from the string (`dayOf`), so they show the day that was chosen.
- Every on-screen date goes through `formatDay`, which calls `toLocaleDateString` in the viewer's zone.
- For anyone east of UTC (the operators here are on IST), 23:59:59Z falls on the next calendar day. A pool set to expire "Dec 31" shows as "Jan 1, 2027" in the table, the portal tile and the "Your seat pool expired on ..." banner.
- Edit then pre-fills "Dec 31", and the exported CSV says "Dec 31" for the licence date, so the same facts disagree between views.
- The same drift applies to customer licence expiry.
- Both files' own comments say they avoid timezone shifts, which holds for `dayOf` but not for `formatDay`.
**Fix:** Format the day from the string for date-only display, with a UTC fallback:
```ts
export function formatDay(iso: string | null | undefined): string {
  if (!iso) return '';
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return '';
  return when.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}
```
Pass `timeZone: 'UTC'` so the display matches the form and the CSV. `daysUntil` and the expired comparison already use the instant, so they need no change.

### WR-10: [frontend] Seat, screen and move modals work from a row snapshot that a refusal-triggered refetch does not update

**File:** `components/PartnerPortal.tsx:123,193-198,399-404`; `components/PartnerCustomerModals.tsx:268-310`; `components/PartnersDashboard.tsx:71-77,301-309`; `components/PartnerMoveCustomerModal.tsx:79-99`
**Issue:**
- `modal` state stores the whole `customer` or `partner` object captured at click time.
- On a refusal (409 or 422), `ChangeSeatsModal` and `CreateCustomerModal` call `onRefetch()` precisely so the numbers refresh. But `ChangeSeatsModal` keeps validating against the stale `customer.seatsUsed` and `customer.seatsAssigned`, and the move modal against the stale `partner.free` and `customer.seatsAssigned`.
- Only the pool-level `free` prop updates. The modal therefore mixes new `free` with old `used` and `assigned`. It can keep offering a value the server just refused, or show "Takes N more seats" computed from the old assigned figure. The consequence text in the move modal ("They are taken from X's pool (N free)") can also be wrong after a lost race.
**Fix:** Store only the id in `modal` and derive the row on each render:
```tsx
type Modal = { kind: 'seats'; customerId: string } | ...;
const live = (id: string) => data?.customers.find(c => c.id === id);
// render the modal only when live(modal.customerId) exists; pass that row
```
Do the same for the partner in `PartnersDashboard` (look the partner up in `partners` by id). Close the modal if the row has gone.

### WR-11: [frontend] A failed quiet reload empties the whole screen, and overlapping reloads can land out of order

**File:** `components/PartnerPortal.tsx:142-151`; `components/PartnersDashboard.tsx:241-250`; `components/PartnerTeamPanel.tsx:206-215`
**Issue:**
- The three `load` functions set data back to `null` on any failure, including the quiet (`showSkeleton=false`) reloads that run after every successful write or refusal.
- A transient error on that reload replaces a good list with the "Couldn't load" banner. Meanwhile `PartnerPortal` still has its modal open, now fed `free=0`, `ceiling=[]` and `unrestricted=false`. In the Create modal the seats error then reads "between 1 and 0" and the picker shows the empty-ceiling message.
- None of the loaders discards a response that a newer request has superseded. A slow earlier reload (the post-write refetch) that finishes after the user's manual "Refresh customers" overwrites the newer data.
**Fix:** Keep the last good data on a quiet failure and show the error beside it, and tag requests so only the latest applies:
```tsx
const seq = useRef(0);
const load = useCallback(async (showSkeleton: boolean) => {
  const mine = ++seq.current;
  if (showSkeleton) setData(null);
  setLoadError(false);
  try {
    const next = await fetchPartnerOverview();
    if (alive.current && mine === seq.current) setData(next);
  } catch {
    if (!alive.current || mine !== seq.current) return;
    setLoadError(true);
    if (showSkeleton) setData(null);   // quiet reloads keep what is on screen
  }
}, []);
```
The render guards that check `data` before showing the error banner then need to show the banner without hiding existing rows. Apply the same change to the other two loaders.

## Info

### IN-01: [backend] Customer first admin cannot be re-invited by the partner (no resend path)

**File:** `backend/partner_portal_service.py:244-254`
**Issue:** `resend_colleague` accepts only partner staff roles (`_staff_role`). A customer's first admin created by
`create_customer` has no resend route for the partner. With no SMTP configured or `FRONTEND_URL` unset (the live VM state,
per project notes) `emailSent` is `false` and the link is never shown, so the 7-day expiry strands the customer admin. If this
is deliberate under D-01 ("a partner never sees a customer's users"), a Super Admin resend must exist; the platform side has no
resend route either.
**Fix:** add a partner-scoped `POST /customers/{id}/resend-admin` that resolves the customer's invited admin by `tenantId` and
`invite: True`, or document that Super Admin set-password is the recovery path.

### IN-02: [backend] Name and email clash responses are enumeration oracles for platform-wide data

**File:** `backend/partner_portal_service.py:101-104`, `backend/partner_store.py:128-133`
**Issue:** A partner admin learns whether any organization anywhere carries a given name (`name_unavailable`, 409) and whether
any user anywhere holds an address (`email_unavailable`, 409, versus 422 for a malformed address), across tenant boundaries,
at the rate of the endpoint. The messages are deliberately generic but the status and code are distinct. Accepted trade-off for
uniqueness, but not rate limited on `POST /api/partner/customers` or `POST /api/partner/team`.
**Fix:** rate limit those two routes per partner and consider returning the same body for the email clash and a successful send.

### IN-03: [backend] `claim` tolerates a malformed pool document and can over-allocate

**File:** `backend/partner_pool.py:51-59`
**Issue:** `{"$add": ["$partner.allocated", n]} <= "$partner.poolSize"` evaluates `null <= null` as true when `partner.allocated`
or `poolSize` is missing. Verified: a partner document with `poolSize: 5` and no `allocated` accepted a claim of 99. Documents
written by `appoint` always set both fields, so this only matters for hand-edited or restored documents.
**Fix:** add `"partner.allocated": {"$type": "number"}, "partner.poolSize": {"$type": "number"}` to the claim query.

### IN-04: [backend] Duplicated constants and helpers

**File:** `backend/partner_endpoints.py:280`, `backend/partner_status.py:177`; `backend/partner_portal_service.py:28-29`,
`backend/partner_platform_service.py:43-46`, `backend/partner_store.py:144-147`; literal `"partner"` in `partner_pool.py`,
`partner_status.py`, `role_assignment.py`, `license_rules.py`, `tenant_endpoints.py`, `licensing.py`, `mssp_endpoints.py`
**Issue:** `SUSPENDED_MESSAGE` is defined twice with the same text. There are three near-identical actor helpers
(`_actor_email` twice, `_actor`). The organization type string `"partner"` is spelled as a literal in eight modules while
`partner_store.PARTNER_TYPE` exists. A change in one place silently diverges.
**Fix:** import `partner_status.SUSPENDED_MESSAGE`; move the actor helper and `PARTNER_TYPE` to a small shared module that
`partner_pool` can import without a cycle.

### IN-05: [backend] Invite and password-reset rows are not cleaned up on tenant delete

**File:** `backend/tenant_endpoints.py:287-312`
**Issue:** `delete_tenant` removes users and agents but leaves `invites` and `password_reset_tokens` rows for the tenant. A still
open invite link then reports `valid` on `/api/auth/invite/status` and `reset-password/confirm` answers success for a user that no
longer exists. `invites` also has no TTL, so rows accumulate with invitee emails.
**Fix:** delete `invites` by `tenantId` and `password_reset_tokens` by the removed users' emails with `invite: True`; add a TTL
index on a real datetime field of `invites`.

### IN-06: [backend] `current_partner` reports a stale or mis-typed token as "suspended"

**File:** `backend/partner_endpoints.py:325-327`
**Issue:** When the token's tenant is no longer a partner organization (deleted, or the user was moved to a customer tenant),
`find_partner` returns None and the 403 text says the account is suspended. That misleads the user and the Super Admin reading
support tickets, and `partner_status.refuse_if_suspended` already treats the same case with the same text.
**Fix:** split the cases: missing partner gives 403 "This account is not linked to a partner organization"; keep the suspended text
for `status != "active"`.

---

_Reviewed: 2026-11-03_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

### IN-07: [frontend] Accept-invite page maps every status-check failure to "Couldn't reach the platform"

**File:** `components/AcceptInvitePage.tsx:114-123`; `services/partnerApi.ts:248-250`
**Issue:** The status endpoint is rate limited at 10 per minute and its body is validated (`token` 1 to 512 characters, `backend/invite_endpoints.py:20-28`). Both a 429 and a 422 (an over-long or mangled token) reject `fetchInviteStatus`, which the page turns into the `network` view. The user then sees a connectivity message and a "Try again" button that cannot succeed (422), or one that makes the rate limit worse (429). A 422 is really an invalid link.
**Fix:** In the rejection handler, branch on `PartnerApiError.status`. A 4xx other than 429 goes to `invalid`. A 429 gets its own wait-and-try-again wording. Reserve `network` for thrown non-API errors and 5xx.

### IN-08: [frontend] `PartnerPortal` and `PartnersDashboard` render a second `<main>` inside the shell's `<main id="main-content">`

**File:** `components/PartnerPortal.tsx:278`; `components/PartnersDashboard.tsx:391`
**Issue:** The shell wraps every view in `<main id="main-content" tabIndex={-1}>` (`App.tsx` around line 2000), and these two screens add another `<main>`. Screen readers then announce two main landmarks, and the skip link lands on the outer one. No other dashboard does this.
**Fix:** Change both to `<div className="container mx-auto space-y-6 p-6">`.

### IN-09: [frontend] Partner viewer briefly sees admin-only controls while the overview loads or fails

**File:** `components/PartnerPortal.tsx:169-170,220,286-291`
**Issue:** `isAdmin = !isViewer` is true while `data` is null (loading or load error). A viewer therefore sees a disabled "Create customer" button and the Actions column header until the overview resolves, and keeps the button if the load fails. Writes are still refused by the server, so this is cosmetic, but it contradicts D-04 ("removed rather than disabled") and fails open on the role.
**Fix:** Derive the role from `data` and treat the unknown case as viewer: `const isAdmin = data?.role === 'admin'; const isViewer = !isAdmin;`. Adjust the `loading` skeleton column spans, which already use `isAdmin ? 6 : 5`.

### IN-10: [frontend] Appoint, Move and Suspend/Reinstate submit guards are state-only, unlike the portal modals

**File:** `components/PartnerFormModal.tsx:117-120`; `components/PartnerMoveCustomerModal.tsx:108-110`; `components/PartnerStatusDialogs.tsx:51-54`
**Issue:** The portal modals guard double submit with a `useRef` (`busy.current`). These three rely on the `saving` or `pending` state alone. In React 18 a discrete click normally re-renders before the next event, so the window is small, but appointing a partner sends an invite email and is not idempotent. Two events dispatched in one task would send two requests. The portal modals show the intended pattern.
**Fix:** Add a `busy` ref checked and set at the top of each handler and cleared in `finally` or the catch, as in `CreateCustomerModal.submit`.

---

_Reviewed: 2026-11-03T19:50:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
