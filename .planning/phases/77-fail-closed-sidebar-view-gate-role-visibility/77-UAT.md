---
status: testing
phase: 77-fail-closed-sidebar-view-gate-role-visibility
source: [77-VERIFICATION.md]
started: 2026-10-19T16:43:12Z
updated: 2026-10-19T17:57:14Z
---

## Current Test

number: 1
name: Two-session role edit refresh
expected: |
  Deploy (backend restart + UI publish). In two browser sessions, sign in as a user holding a custom role; have an admin add a catalogue permission (e.g. a view:X) to that role; focus the first window (or trigger a 403). The new catalogue appears in the first user's sidebar without logging out. The newly unlocked screen loads its data straight away, and if the edit removed the screen that is open, it swaps to the no-access panel.
awaiting: user response

## Tests

### 1. Two-session role edit refresh
expected: After deploy, an admin adds a catalogue permission to a custom role; on the holder's next window focus (or 403) the new catalogue appears in their sidebar without re-login. The newly unlocked screen shows its data at once; a removed, open screen swaps to the no-access panel.
result: [pending]

### 2. Restricted roles on the live system
expected: Signed in as itam_viewer and as a custom role with no screens, walking the sidebar, URL hashes (#users, #settings) and chat/socket-driven navigation: forbidden catalogues are absent from the sidebar, hash and deep links show the in-place no-access panel, the zero-screen role gets the full-page zero-access screen with working Retry and Sign out, and no raw 403 toasts or offline banners appear.
result: [pending]

### 3. Layout at 320, 375 and 768 px, light and dark
expected: The no-access panel, zero-access screen and Settings > Roles "What it can see" panel have no horizontal scroll; the action row stacks under 400 px; truncation and wrapping follow UI-SPEC C11-C16.
result: [pending]

### 4. Super Admin visibility panel vs. actual sidebar
expected: As Super Admin, in Settings > Roles, pick a tenant and open "What it can see" for built-in and custom roles; each list matches the sidebar that role's holders actually see.
result: [pending]

### 5. A role edit puts its holders behind MFA at once
expected: Give a custom role held by a user with an open session and no MFA enrolled the manage:users permission. That user's next API call hits the MFA gate straight away (not after 60 s), and a fresh socket connect is refused until they pass MFA; removing the permission lifts both. An already-open socket is not re-checked until it reconnects.
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
