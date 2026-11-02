---
phase: 87-partner-and-reseller-channel
plan: 07
subsystem: ui
tags: [react, typescript, rbac, vitest, partner-channel, session]

requires:
  - phase: 87-01
    provides: partner_admin and partner_viewer roles, partners and partnerPortal catalogues, the partner route contract
  - phase: 87-04
    provides: X-Partner-Suspended 403 header and the stable suspended message
  - phase: 87-06
    provides: public POST /api/auth/invite/status and the reuse of reset-password/confirm
  - phase: 87-15
    provides: AppView partners and partnerPortal, partner Permission members
provides:
  - services/partnerApi.ts typed client for the Partners page, the Partner portal and the accept-invite page, with PartnerApiError
  - isPartnerRoleName, isPartnerAdminRoleName, partnerRoleLabel, PARTNER_ROLE_KEYS
  - PARTNER_ONLY_VIEWS role gate that hides the Partner portal from the Super Admin and every non-partner role
  - suspended-partner session exit to /login?error=partner_suspended and the sign-in message
  - PartnerStatusChip, PoolExpiryChip, StaffStatusChip, daysUntil, formatDay
  - PartnerScreenPicker (ceiling and customer modes)
affects: [87-11, 87-12, 87-13, 87-14]

actuals:
  tokens: 14800
  tasks: 3
  commits: 5
plan_head_before: 1f75188749d1e3a3123405dbf0341b33e50fd30a
plan_head_after: 9c231e692bcea9bb7de332dc48927182cc50d497

tech-stack:
  added: []
  patterns:
    - "Partner-only views are denied by role before the owner short-circuit in evaluateViewAccess and canReadView"
    - "Refusals from partner routes throw PartnerApiError (server error text, then detail; code; status; the whole body as data)"
    - "Tests that exercise apiService session state use vi.resetModules plus a dynamic import, because _sessionEnding is module state"

key-files:
  created:
    - services/partnerApi.ts
    - components/PartnerStatusChip.tsx
    - components/PartnerScreenPicker.tsx
    - src/__tests__/partnerAccess.test.ts
    - src/__tests__/PartnerScreenPicker.test.tsx
  modified:
    - utils/permissions.ts
    - utils/viewAccess.ts
    - services/apiService.ts
    - components/LoginPage.tsx
    - src/__tests__/viewAccess.test.ts
    - src/__tests__/SidebarFailClosed.test.tsx

key-decisions:
  - "The suspended-session exit navigates synchronously and does not set the generic session-ended notice, so the sign-in page shows only the one suspended message"
  - "The picker hides switches outside the ceiling instead of showing them disabled; only kept screens (held, outside the ceiling) appear locked"
  - "A held screen outside the ceiling is treated as kept even when the caller's kept list omits it"
  - "The Overview row (screen:dashboard) keeps its JSON label Overview, shown checked and disabled with Always included"
  - "A parent of a kept screen is locked on ('Needed by a screen kept from before.') so unticking it can never drop a kept child"

patterns-established:
  - "PartnerScreenPicker is controlled and passes through any entry it does not show (start screens, unknown names)"
  - "Chips copy the Phase 81/82 tone classes instead of importing across feature folders"

requirements-completed: [PART-01, PART-05, PART-06]

coverage:
  - id: D1
    description: "Typed partner client: every route goes through authFetch and API_BASE, refusals throw PartnerApiError with the server text, code, status and numbers; the two invite-page calls use plain fetch with no Authorization header"
    requirement: PART-01
    verification:
      - kind: unit
        ref: "src/__tests__/partnerAccess.test.ts#partner API client"
        status: pass
    human_judgment: false
  - id: D2
    description: "The Partner portal is visible to partner users only: denied to the Super Admin, star holders and every non-partner role, allowed to partner_admin and partner_viewer holding view:partner_portal; partner landing view is partnerPortal and the Super Admin landing is unchanged"
    requirement: PART-05
    verification:
      - kind: unit
        ref: "src/__tests__/partnerAccess.test.ts#the Partner portal belongs to partner users only (PART-05, R1)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A 403 carrying X-Partner-Suspended clears the session and goes to /login?error=partner_suspended; login surfaces body.error; LoginPage shows the suspended message"
    requirement: PART-01
    verification:
      - kind: unit
        ref: "src/__tests__/partnerAccess.test.ts#a suspended partner session ends on the sign-in page (PART-01, T-87-21)"
        status: pass
      - kind: unit
        ref: "src/__tests__/partnerAccess.test.ts#LoginPage explains a suspended partner"
        status: pass
    human_judgment: false
  - id: D4
    description: "PartnerScreenPicker offers only ceiling switches as tickable, locks Overview and kept screens with the specified sentences, follows the parent rule, and shows the empty-ceiling message; chips render the specified labels and tones"
    requirement: PART-06
    verification:
      - kind: unit
        ref: "src/__tests__/PartnerScreenPicker.test.tsx (26 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Visual fit of the chips and the checklist (spacing, dark theme, wrapping at 320px) against 87-UI-SPEC"
    verification: []
    human_judgment: true
    rationale: "Components are not yet mounted in any screen; layout and theme can only be judged once 87-11 to 87-14 place them"

duration: 21min
completed: 2026-11-02
status: complete
---

# Phase 87 Plan 07: Shared Partner Frontend Ground Summary

**A typed partner API client with server-worded errors, a role gate that hides the Partner portal from everyone but partner users (the Super Admin included), a suspended-session exit to the sign-in page, and the shared status chips and ceiling-limited screen picker the three partner screens build on.**

## Performance

- **Duration:** 21 min
- **Started:** 2026-11-02T22:03:00Z
- **Completed:** 2026-11-02T22:24:00Z
- **Tasks:** 3
- **Files modified:** 11 (5 created, 6 modified)

## Accomplishments

- `services/partnerApi.ts` (255 lines): 18 functions, one per route in the plan's context block, plus the types the screens need. Signed-in calls use `authFetch`; `fetchInviteStatus` and `acceptInvite` use plain `fetch` with no Authorization header and are the only functions that handle an invite token.
- `evaluateViewAccess` and `canReadView` deny `partnerPortal` to anyone who is not a partner role before the owner short-circuit, so the Super Admin no longer sees the portal; `landingView` for a partner user holding only `view:partner_portal` is `partnerPortal`.
- A 403 with `X-Partner-Suspended` ends the session (tokens and caches cleared, refresh cycle stopped) and sends the tab to `/login?error=partner_suspended`; sign-in shows the exact suspended sentence, and `login()` now prefers `body.error` over `body.detail` on a 403.
- `PartnerScreenPicker` (200 lines) in `ceiling` and `customer` modes, with the Manage Tenant grouping and parent rule, locked Overview and kept screens, Select all / Clear all that touch tickable rows only, and the empty-ceiling message.
- Frontend suite: 1000 tests pass (938 baseline + 62 new), `npm run build` passes (writes dist-new only; nothing published).

## Task Commits

1. **Task 1 (tracer): typed partner client and role gate** - `79baf0636` (feat)
2. **Task 2: suspended-partner exit** - RED `1447323c5` (test), GREEN `ee5f5db6d` (feat)
3. **Task 3: chips and screen picker** - RED `bab109407` (test), GREEN `9c231e692` (feat)

**Plan metadata:** committed with this SUMMARY (docs).

## TDD Gate Compliance

Tasks 2 and 3 followed RED then GREEN with `test(87-07)` before `feat(87-07)`; no refactor commit was needed. `workflow.tdd_mode` is false, so the machine RED-evidence classifier was not required; the semantic assessment of each RED run follows.

- **Task 2 RED:** 4 of 9 new tests failed on the planned assertions: the suspended 403 resolved instead of rejecting, `login()` returned the disabled-account fallback instead of `body.error`, and the LoginPage did not render the suspended text. The "403 without the header behaves as before" case passed at RED by design (a regression guard on existing behavior). One failure ("refuses every later call") failed because the mocked fetch had no second answer when the session was not ended; it fails for the same missing behavior.
- **Task 3 RED:** the components were empty stubs so all 26 tests failed on assertions (elements and text not found), not on import or syntax errors.

## Files Created/Modified

- `services/partnerApi.ts` - typed client, `PartnerApiError`, 18 route functions
- `utils/permissions.ts` - `PARTNER_ROLE_KEYS`, `isPartnerRoleName`, `isPartnerAdminRoleName`, `partnerRoleLabel`
- `utils/viewAccess.ts` - `PARTNER_ONLY_VIEWS` and the role check in `evaluateViewAccess` / `canReadView`
- `services/apiService.ts` - `_endPartnerSession`, the 403 branch in `authFetch`, `body.error` in `login` (20 added lines)
- `components/LoginPage.tsx` - `partner_suspended` URL error mapping
- `components/PartnerStatusChip.tsx` - status, pool expiry and staff chips, `daysUntil`, `formatDay`
- `components/PartnerScreenPicker.tsx` - the screen checklist
- `src/__tests__/partnerAccess.test.ts`, `src/__tests__/PartnerScreenPicker.test.tsx` - new tests
- `src/__tests__/viewAccess.test.ts`, `src/__tests__/SidebarFailClosed.test.tsx` - the two "Super Admin sees every manifest view" cases now skip the partner-only view

## Decisions Made

See `key-decisions` above. The two worth repeating for the screen plans: the picker never offers a screen outside the ceiling (it hides it), and its `onChange` output keeps every entry it does not show, so a caller can pass the customer's full list without losing start screens or kept screens.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Two existing tests asserted the behavior the plan removes**
- **Found during:** Task 1 (full-suite run after the role gate)
- **Issue:** `viewAccess.test.ts` ("allows every manifest view for the super-admin spelling") and `SidebarFailClosed.test.tsx` ("recognises the platform-admin spelling as a super admin") expected the Super Admin to see every manifest view, including `partnerPortal`. PART-05 (R1) requires the opposite, so they failed for the intended reason.
- **Fix:** Both loops skip `PARTNER_ONLY_VIEWS`; the denial itself is asserted in `partnerAccess.test.ts`. No other test changed outcome.
- **Files modified:** `src/__tests__/viewAccess.test.ts`, `src/__tests__/SidebarFailClosed.test.tsx`
- **Verification:** full suite 1000 passed
- **Committed in:** `79baf0636`

**2. [Rule 1 - Bug] RED test isolation: a partial `vi.mock` of apiService shared session state**
- **Found during:** Task 2 GREEN
- **Issue:** The RED commit mocked apiService with `importOriginal` to silence the SSO fetch; `vi.resetModules` did not give each case a fresh `_sessionEnding`, so a later case saw "Session ended".
- **Fix:** Removed that mock; the LoginPage cases stub global `fetch` for the SSO providers call instead, and the session cases import a fresh apiService per test.
- **Files modified:** `src/__tests__/partnerAccess.test.ts`
- **Verification:** 54 tests pass across the three Task 2 files
- **Committed in:** `ee5f5db6d` (the RED commit was not rewritten)

---

**Total deviations:** 2 auto-fixed (2 bugs, both in tests)
**Impact on plan:** None on shipped behavior. The first is the plan's own change colliding with two older assertions.

## Issues Encountered

- `services/apiService.ts` carries a user-side hunk (`setUserPassword`) and a file-mode flip; `utils/permissions.ts` also carries a mode flip. Commits were staged by writing the exact blob (HEAD content plus only this plan's lines, mode 100644) into the index, so neither the user hunk nor any mode change was committed. They remain as working-tree modifications.
- Not-yet-built server shapes (87-08, 87-09 run in the same wave): the types for `CustomerFeatures`, `PartnerTeamMember`, `{customer, emailSent}` and the `PartnerSummary` mutation responses (`{partner}`) follow the plan text and the 87-08/87-09 plans, not shipped code. `changeCustomerSeats` reads `customer` from the PUT response; `resendColleagueInvite` and `inviteColleague` accept `member` and `emailSent`. If 87-09 ships different keys, adjust `services/partnerApi.ts` only.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None. `components/PartnerStatusChip.tsx` and `components/PartnerScreenPicker.tsx` are complete; they are simply not mounted in any screen until 87-11 to 87-14.

## Threat Flags

None. No new endpoint, auth path or file access; T-87-20 and T-87-21 are mitigated as planned (role gate before the owner short-circuit; suspended header ends the session on the next call).

## Next Phase Readiness

- 87-11, 87-12 and 87-13 can import the client, chips and picker; 87-14 mounts the views. `PARTNER_ONLY_VIEWS` already keeps the portal out of the Super Admin's sidebar.
- The UI is built to `dist-new` only; nothing was published and no backend was restarted.

## Self-Check: PASSED

- Created files exist: `services/partnerApi.ts`, `components/PartnerStatusChip.tsx`, `components/PartnerScreenPicker.tsx`, `src/__tests__/partnerAccess.test.ts`, `src/__tests__/PartnerScreenPicker.test.tsx`.
- Commits `79baf0636`, `1447323c5`, `ee5f5db6d`, `bab109407`, `9c231e692` are ancestors of HEAD (5 measured from the ledger).
- Acceptance criteria re-run: PartnerApiError 1; PARTNER_ONLY_VIEWS 3; token reads in partnerApi 0; partnerApi 255 lines (< 500); X-Partner-Suspended in apiService 1; partner_suspended in LoginPage 1; apiService added lines 20 (<= 20); lucide-react 0 and dangerouslySetInnerHTML 0 in both components; kept sentence 1.
- Plan verification: three task commands green; `npx vitest run src/__tests__` 78 files, 1000 tests pass; `npm run build` passes.

---
*Phase: 87-partner-and-reseller-channel*
*Completed: 2026-11-02*
