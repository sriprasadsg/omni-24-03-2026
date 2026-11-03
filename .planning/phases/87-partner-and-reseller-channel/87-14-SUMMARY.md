---
phase: 87-partner-and-reseller-channel
plan: 14
subsystem: ui
tags: [react, typescript, vitest, partner-channel, app-shell, sidebar]

requires:
  - phase: 87-07
    provides: isPartnerRoleName, partnerOnly view gate, catalogue entries partners and partnerPortal
  - phase: 87-11
    provides: PartnersDashboard (named export)
  - phase: 87-12
    provides: PartnerPortal (default export)
  - phase: 87-13
    provides: AcceptInvitePage (default export)
provides:
  - Partners and Partner portal views mounted in the shell; the public /accept-invite route
  - A partner shell that starts no customer request (loadAllData, header, sidebar, floating assistants, bundle features)
  - The phase gate record and the live checks left to the user
affects: [87-verification]

actuals:
  tokens: 4560
  tasks: 3
  commits: 4
plan_head_before: e5d3cc7de8d05d1956ac4586501ef4f8014c0da2
plan_head_after: 86e72fea7b25b852af30da9800df6d3417e87fbb

tech-stack:
  added: []
  patterns:
    - "A partner user is recognised once, by isPartnerRoleName, and each shell piece that would call a customer route checks it where it starts the call"
    - "Shell tests render the real App with global fetch stubbed and the four big screens mocked, then assert on the paths the fetch spy saw"

key-files:
  created:
    - src/__tests__/PartnerShell.test.tsx
  modified:
    - App.tsx
    - components/Header.tsx
    - components/Sidebar.tsx
    - contexts/FeaturesContext.tsx

key-decisions:
  - "The accept-invite branch sits after every hook and before the MFA gate, so hook order does not change and an invitee with a held session still sees the page"
  - "A partner user's floating assistants (tour bot, voice bot, chat button, call overlay), the pin star and the Pinned section are not mounted, beyond what the plan named, so the shell has one destination and no other caller"
  - "The test allow-list also admits /api/health (unauthenticated liveness probe) and /api/sso/providers (the sign-in page's own list, shown for a moment before the session is restored and the user is known to be a partner)"

requirements-completed: [PART-01, PART-02, PART-03, PART-04, PART-05, PART-06, PART-07, PART-08]

coverage:
  - id: D1
    description: "/accept-invite renders AcceptInvitePage without a session, outside the shell, ahead of the MFA gate and the sign-in page"
    requirement: PART-02
    verification:
      - kind: unit
        ref: "src/__tests__/PartnerShell.test.tsx#public /accept-invite route (PART-02)"
        status: pass
      - kind: unit
        ref: "src/__tests__/PartnerShell.test.tsx#public /accept-invite route and the MFA gate (PART-02)"
        status: pass
    human_judgment: false
  - id: D2
    description: "partners renders PartnersDashboard for the Super Admin and the Tenants screen receives no type partner organization"
    requirement: PART-01
    verification:
      - kind: unit
        ref: "src/__tests__/PartnerShell.test.tsx#Super Admin views (PART-01)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A partner user lands on the Partner portal, makes no request outside /api/partner, auth, mfa, passkey, GET /api/platform/features (plus the liveness probe and sign-in provider list), and the palette and search keys do nothing"
    requirement: PART-05
    verification:
      - kind: unit
        ref: "src/__tests__/PartnerShell.test.tsx#partner user shell (PART-05, T-87-42)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Header restricted drops palette, search, tour, help, notifications; the partner sidebar holds exactly one entry with no group heading and never polls support; the Super Admin sees Partners right after Tenants and never Partner portal"
    requirement: PART-05
    verification:
      - kind: unit
        ref: "src/__tests__/PartnerShell.test.tsx#Header for a partner user (PART-05, T-87-42)"
        status: pass
      - kind: unit
        ref: "src/__tests__/PartnerShell.test.tsx#Sidebar for partner users and the Super Admin (PART-05, R1)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Phase gates: partner and parity pytest set, full frontend suite, npm run build"
    verification:
      - kind: integration
        ref: "Task 3 gate commands below"
        status: pass
    human_judgment: false
  - id: D6
    description: "Live behaviour: appointing and signing in partners, isolation on real tokens and sockets, suspension, a real retailer trial, and the layout backstop checks at 640, 1024 and 1280 px"
    verification: []
    human_judgment: true
    rationale: "Needs the published UI, the restarted backend (migration 029) and real agents; listed under Live checks for the user"

duration: about 35 min
completed: 2026-11-03
status: complete
---

# Phase 87 Plan 14: Partner Shell Wiring and Phase Gates Summary

**The Partners and Partner portal screens and the public invite page are now mounted in the shell, a partner user's session starts no customer request, and the automated phase gates match the baseline.**

## Performance

- **Duration:** about 35 min (18:40 to 19:15 UTC)
- **Tasks:** 3
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments

- `App.tsx`: lazy `PartnersDashboard`, `PartnerPortal` and `AcceptInvitePage`; cases `partners` and `partnerPortal` under ErrorBoundary and Suspense; `/accept-invite` returns the page inside ThemeProvider before the MFA gate; the Tenants case filters `type === 'partner'`; `loadAllData` returns early for a partner JWT; the Ctrl/Cmd+K and Ctrl/Cmd+/ handler returns for a partner user; Header gets `restricted` and no search opener.
- `components/Header.tsx`: optional `restricted` prop drops the command palette buttons, search, guided tour, feature help and its modal, the notification centre and the pin star. The theme toggle, time zone select and account menu stay.
- `components/Sidebar.tsx`: a partner user's items render with no group heading and are never collapsed; the Pinned section is not shown; the support unread poll does not run.
- `contexts/FeaturesContext.tsx`: no `/bundles/tenant/{id}/features` read for a partner user.
- `src/__tests__/PartnerShell.test.tsx` (272 lines, 13 tests) renders the real `App` with `fetch` stubbed.

## Task Commits

1. **Task 1: Partner views and accept-invite route.** RED `2abef1367` (test), GREEN `86e72fea7` (feat)
2. **Task 2: Partner header and sidebar.** RED `70e637f92` (test), GREEN `79fed8aa7` (feat)

Task 3 made no commit of its own (gates only). **Plan metadata:** committed with this SUMMARY (docs).

Commit order differs from the plan: the Task 2 RED and GREEN commits come before the Task 1 GREEN commit. Task 1's request-spy test cannot pass while the header still mounts the notification centre, and `App.tsx` passes `restricted` to a Header that must accept it, so Header and Sidebar went in first and `App.tsx` last. Each task still has its RED commit before its GREEN commit.

## TDD Gate Compliance

`workflow.tdd_mode` is not set, so the machine RED-evidence classifier was not required.

- **Task 1 RED:** `App` was rendered unchanged against stubbed components. All 7 tests failed on assertions (element not found, or `expected 'Acme Customer|Retailer Partner Org' not to contain 'Retailer Partner Org'`). No import failure: the four screens exist and are mocked. A first run failed on a missing `window.matchMedia`; that was fixed in the test setup before the RED commit.
- **Task 2 RED:** 3 of the 6 new tests failed on assertions (a restricted header still showed 3 widgets, the viewer sidebar listed `Management & Settings` as well as the entry, `/api/support/unread-count` was requested). The other 3 already held (Super Admin order, full header for others, single entry visible), and stay as guards.
- Mutation check: removing the partner early return from the key handler makes "ignores the command palette and search keys" fail, so that test does bite.
- Two GREEN-time test edits: the Task 1 GREEN commit added a 10 s wait for the first full-shell render and added `/api/sso/providers` to the allow-list (see decisions).

## Gate results (Task 3)

All gates ran alone on the VM. Database tests used a private mongod on port 27998 with temporary attachment and share directories; it was stopped and removed afterwards. The live mongod on 27017 was not touched.

| Gate | Result |
|------|--------|
| `backend/venv/bin/python -m pytest` on the 23 partner, parity, auth-baseline, switch, licence and role files named in Task 3 (`-q -p no:cacheprovider -rs`) | 451 passed, 2 failed, 0 skipped in 99.6 s. The 2 failures are `test_catalogue_route_parity::test_ledger_ratchets` and `test_catalogue_manifest::test_sidebar_and_app_agree_with_manifest`, both on the baseline list. No `test_partner_*` test was skipped. |
| `npx vitest run src/__tests__` (exit code read directly) | exit 0. 84 files, 1179 tests, no failures (baseline 83 files, 1166 tests, plus this plan's 13). |
| `npm run build` | exit 0, built in 5.95 s into `dist-new` (nothing published). |
| `npx tsc --noEmit` | clean |

The full backend suite (about 33 minutes) was not run here; it is a human check below.

## Live checks for the user

Backend restart (migration 029), the UI publish and the push are the user's. Nothing was restarted, published, migrated against the live database or pushed.

1. **Full backend suite** alone on a private mongod (about 33 minutes): `backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider` with `MONGO_TEST_URL`, `MONGODB_URL` and `MONGO_URI` pointing at it and temporary `TICKET_ATTACHMENT_DIR` and `FILE_SHARE_DIR`. Failures must match the four baseline names in 87-VALIDATION.md.
2. **Partner onboarding after the restart and publish:** the Super Admin appoints two partners (100 and 1,000 seats). Each partner admin signs in through its invite (SMTP and FRONTEND_URL configured, or a password set in User Management), enrols MFA, creates a customer, changes seats and ticks screens. A partner viewer signs in without MFA and sees no controls.
3. **Browser pass** of Partners, Partner portal (admin and viewer) and Accept invite in light and dark at 640, 1024 and 1280 px, including the three backstop layout checks: a 1,000,000-seat tile, the admin table at 1280 px, and a 100-character organization name at 360 px.
4. **Live isolation:** a partner token on any customer page or API is refused; Socket.IO delivers nothing of customers to a partner session (A-87-A5); suspending a partner signs its users out while its customers' agents keep reporting. Also watch the network tab as a partner user for any request outside the allowed routes.
5. **Real retailer trial:** install agents into a partner customer up to its seats and confirm the next one is held Pending; expire a test pool and confirm new agents are held and running ones keep working.

## Deviations from Plan

**1. [Rule 2 - Missing functionality] The partner shell still made customer requests the plan did not name.**
- **Found during:** Task 1 (reading the shell's background effects while writing the request-spy test)
- **Issue:** T-87-42 and the must-have truth say a partner session makes no request outside its own routes, but beyond `loadAllData` and the header, the sidebar polled `/api/support/unread-count` every 30 s, `FeaturesProvider` read `/api/bundles/tenant/{id}/features`, and the floating assistants (tour bot, voice bot, chat button, call overlay) were mounted. The sidebar's Pinned section would also have shown the single entry a second time under a heading.
- **Fix:** the sidebar poll, the bundle read, the pin star and the Pinned section are skipped for a partner user; the four floating assistants are not mounted.
- **Files modified:** `components/Sidebar.tsx`, `components/Header.tsx`, `contexts/FeaturesContext.tsx`, `App.tsx`
- **Commits:** `79fed8aa7`, `86e72fea7`

**2. [Process] Task order.** The Task 2 commits precede the Task 1 GREEN commit; see Task Commits.

Otherwise the plan ran as written.

## Issues Encountered

- `App.tsx` carried two uncommitted hunks that belong to the user (the `handleResetPassword` rewrite with the new `handleSetUserPassword`, and `onSetUserPassword` on the `settings` case). The working tree was edited in place so they stay. The index copy was built from the working file with those two hunks reverted to HEAD text, by exact string replacement rather than `patch -R`, because the `tenantManagement` line I changed sits inside the patch's trailing context. `git diff --cached` before the commit showed only this plan's hunks. After the last commit, `git diff -- App.tsx` matches the orchestrator's saved patch line for line.
- `holdForMfa` is module state in `apiService`, so the accept-invite-with-MFA-gate test runs last in the file; a held session would otherwise block every later test in the same file.
- A startup `GET /api/health` poll and the sign-in page's `GET /api/sso/providers` (shown before the session is restored) still happen for a partner user. Both are unauthenticated and reveal nothing; the server allowlist (87-05) is the wall for anything else. Socket.IO still connects for any signed-in user; its isolation is a live check (A-87-A5).
- The CLAUDE.md `npm run build && npm test` instruction was met: `npm run build` and the full vitest suite both ran this time.

## User Setup Required

None for the code. After the user restarts the backend (migration 029 runs) and publishes the UI, the live checks above apply.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema.

- **T-87-42 (shell background fetches for partner users):** mitigated. `loadAllData` returns early, the widgets that fetch are not rendered, and the request-spy test shows only allowed paths. The server allowlist still refuses the rest.
- **T-87-43 (/accept-invite while another user is signed in):** accepted as planned. The page renders without the shell, so nothing of the previous session is shown on it.
- **T-87-SC:** no package was installed.

## Self-Check: PASSED

- `src/__tests__/PartnerShell.test.tsx` exists; the four commit hashes (`2abef1367`, `70e637f92`, `79fed8aa7`, `86e72fea7`) are ancestors of HEAD.
- Acceptance greps on `App.tsx`: `case 'partnerPortal'` 1, `case 'partners'` 1, `'/accept-invite'` 1, `t.type !== 'partner'` 1. `restricted` appears in `Header.tsx` 8 times and `isPartnerRoleName` in `Sidebar.tsx` 2 times.
- Line counts: `Header.tsx` 155, `Sidebar.tsx` 316, test 272. `App.tsx` is the existing large file.
