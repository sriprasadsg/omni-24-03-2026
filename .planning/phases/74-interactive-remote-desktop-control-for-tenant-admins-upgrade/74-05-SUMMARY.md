---
phase: 74-interactive-remote-desktop-control-for-tenant-admins-upgrade
plan: 05
type: execute
wave: 3
depends_on: ["74-01", "74-02"]
files_modified:
  - types.ts
  - services/apiService.ts
  - components/RemoteDesktop.tsx
  - components/RemoteAccessDashboard.tsx
  - src/__tests__/remoteControl.test.ts
autonomous: true
requirements: []

estimate:
  tokens: 75000
  raw_tokens: 75000
  tasks: 3
  confidence: low

must_haves:
  truths:
    - "The canvas has four visually and behaviourally distinct states — view-only, awaiting consent, control active, and control ended — matching the UI-SPEC Interaction Contract state table."
    - "The awaiting-consent state renders as a dimmed canvas with a centred spinner, a wait cursor, and a pulsing amber badge — visually distinct from the plain connection spinner the component already shows, so waiting on a person is never mistaken for waiting on the network."
    - "The control-active state renders an emerald ring, a crosshair cursor, and a solid emerald badge with a pulsing dot, so an elevated-privilege session is unmissable at a glance."
    - "Mouse and keyboard handlers are attached to the canvas only while control is active; in every other state the canvas has zero input handlers, so no input frame can leak during the awaiting-consent window."
    - "The View and Control toggle is omitted entirely, not rendered disabled, for a user without control:remote_access — a disabled-but-visible option would advertise a permission tier the user does not hold."
    - "No-interactive-desktop, wrong-platform, and agent-offline render as three distinguishable messages rather than one generic string, and the existing 45-second generic message remains only as the fallback when no reason discriminant is present."
    - "Consent declined, consent timed out, and session-ended-by-tunnel-drop each render their own copy, and the tunnel-drop copy states that reconnecting requires fresh approval rather than reading like a transient blip."
    - "The admin Disconnect button uses a two-step inline confirm that reverts after 4 seconds, while the platform-admin Force End Session uses a full confirmation modal — three confirmation weights matched to blast radius, with the endpoint-side stop having none at all."
    - "Every new UI element uses Tailwind utility classes with the UI-SPEC token values, adds no new inline style object, and uses no indigo or violet accent."
    - "A control session that is accepted but whose input relay then fails renders the session-ended copy rather than a fifth distinct error string."
    - statement: "The agent hostname in the RemoteDesktop and RemoteAccessDashboard header rows does not overflow its row when unusually long."
      verification: backstop
  artifacts:
    - types.ts with the completed DOM_CODE_TO_VK map covering the full extended and printable key sets
    - services/apiService.ts with disconnectRemoteSession and getRemoteCapabilities
    - components/RemoteDesktop.tsx implementing the four-state control canvas
    - components/RemoteAccessDashboard.tsx with the permission-gated View and Control toggle and the force-end modal
    - src/__tests__/remoteControl.test.ts
  key_links:
    - "the View and Control toggle is gated on GET /api/remote/capabilities, not on the client-side hasPermission mirror, because App.tsx intersects user permissions with tenant enabledFeatures before hasPermission sees them"
    - "input handlers are bound conditionally on control state so the awaiting-consent window cannot emit frames"
---

# Phase 74-05: Frontend — Four-State Control Canvas, Permission-Gated Toggle, Force-End

Implemented the interactive-control experience specified in the UI-SPEC: a canvas that makes the elevated-privilege state unmissable, full mouse and keyboard capture that only exists while consent holds, and three destructive affordances whose confirmation weight matches their blast radius.

## Performance

- **Duration:** ~120 min
- **Started:** 2026-08-29
- **Completed:** 2026-08-30
- **Tasks:** 3
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments

### Task 1: Complete the key map and the control API surface
- **types.ts** — Completed `DOM_CODE_TO_VK` map covering the full extended and printable key sets (arrows, Insert, Delete, Home, End, PageUp, PageDown, right Alt/Control, numpad Enter, function-key row, Tab, Enter, Backspace, Escape, Space, modifiers, punctuation row). Added `resolveKeyEventToFrame` helper that returns a virtual-key code or, when unmapped and `key` is a single character, that character's UTF-16 code unit with vk=0. Added `normalizeCanvasPoint` helper that clamps coordinates to 0..1 inclusive.
- **services/apiService.ts** — Added `disconnectRemoteSession(sessionId)` and `getRemoteCapabilities()` following the file's `authFetch` + try/catch/`return { error: e }` convention. Verified no client-side consent-route wrapper exists (`grep -c 'session/.*\/consent' services/apiService.ts` returns 0).
- **src/__tests__/remoteControl.test.ts** — Created 12 tests covering: unmapped code returns undefined, out-of-bounds pointer clamps, DOM_CODE_TO_VK coverage for extended and printable sets, key resolver handles Unicode fallback, normalizeCanvasPoint clamps correctly, API functions follow error convention.

### Task 2: Four-state control canvas in RemoteDesktop.tsx
- Rendered four canvas states from the UI-SPEC Interaction Contract, driven by `controlState` from `control_state` frames:
  - **View-only**: default border, default cursor, neutral badge
  - **Awaiting consent**: dimmed frame with semi-transparent overlay, centred spinner, wait cursor, pulsing amber badge
  - **Control active**: emerald 2px ring, crosshair cursor, solid emerald badge with pulsing dot
  - **Control ended**: view-only visual with transient inline red-text banner
- Attached mouse/keyboard handlers to `<canvas>` ONLY while `controlState === 'active'`. In all other states the canvas has zero input handlers — this is a security property per D-01. Bindings are conditional, not early-return inside handlers.
- Covered every INTEGRATE input row from COVERAGE.md: pointer move, pointer down/up (primary, secondary, middle, X1, X2), wheel (both axes), key down/up resolved through Task 1 helper.
- Rendered error/lifecycle copy from UI-SPEC Copywriting Contract, switching on `reason` discriminant: no-interactive-desktop, wrong-platform, already-controlled (names holding admin), consent declined, consent timed-out. Generic 45-second message only as fallback when no `reason` present. Tunnel-drop message states reconnecting requires fresh approval.
- Treated accepted session whose relay fails as session end (tunnel-drop copy), per planner assumption.
- Added admin Disconnect affordance in header row next to FPS counter. Two-step inline confirm: first click swaps label to red confirm wording for 4 seconds, second click calls `disconnectRemoteSession`, no second click reverts. Timer cleared on unmount. No modal — low blast radius.
- All new elements use Tailwind utilities with UI-SPEC token values: accent for armed/requesting, destructive red for disconnect/live badge, emerald for connected/accepted, amber for pending. Only font weights 400 and 700, four declared sizes. No new inline style objects. No indigo/violet accent. Added truncation class to header row hostname.

### Task 3: Permission-gated mode toggle and platform-admin force-end
- **RemoteAccessDashboard.tsx** — Added nested View and Control toggle appearing only when Desktop mode is active AND `getRemoteCapabilities` returns `can_control: true`. Fetch once on mount with existing `AbortController` pattern. Gate on server probe, NOT on `useUser().hasPermission` — `App.tsx` intersects permissions with tenant `enabledFeatures` before `hasPermission` sees them, so a backend-granted permission can silently vanish client-side. The probe is the only client-reachable source of truth; enforcement stays on `start_remote_session` and disconnect route.
- When `can_control` is false, the toggle is omitted entirely (not rendered disabled) — a disabled-but-visible option would advertise a permission tier the user lacks.
- Pass selected sub-mode into `<RemoteDesktop>` as `mode` prop. Reuse segmented pill shape with Tailwind/tokens (active segment = design-system blue, not legacy indigo). Legacy Terminal/Desktop toggle styling untouched.
- Added platform-admin Force End Session action, visible only to super-role set, using full confirmation modal. Heading/body copy from UI-SPEC Copywriting Contract, interpolating admin name, mode, hostname, tenant name. On confirm, calls `disconnectRemoteSession`. Heavier confirmation matches cross-tenant blast radius.
- Added truncation class to header row hostname. Only font weights 400/700, four declared sizes, spacing in multiples of 4. No indigo/violet accent on new elements.

## Files Created/Modified
- `types.ts` — Completed `DOM_CODE_TO_VK`, added `resolveKeyEventToFrame`, `normalizeCanvasPoint`
- `services/apiService.ts` — Added `disconnectRemoteSession`, `getRemoteCapabilities`
- `components/RemoteDesktop.tsx` — Four-state canvas, conditional input handlers, error/lifecycle copy, two-step Disconnect, hostname truncation
- `components/RemoteAccessDashboard.tsx` — Nested View/Control toggle gated on server capability probe, Force End Session modal, hostname truncation
- `src/__tests__/remoteControl.test.ts` — 12 tests for key map, point normalization, API surface

## Threat Mitigations (from plan)
- T-74-03: View/Control toggle is affordance gate only; real enforcement on `verify_permission` (start_remote_session) and `require_permission` (disconnect route)
- T-74-25: Handlers bound conditionally on control-active state, not bound always with early return — no code path emits input frame during awaiting-consent window
- T-74-26: Toggle omitted rather than disabled for users without permission — UI does not enumerate permission tier
- T-74-27: No client wrapper for consent route; only tunnel-authenticated agent can assert consent decision
- T-74-09b: Force End Session rendered only for super-role set, behind full modal; backend re-checks role independently and audits every force-kill
- T-74-28: `preventDefault` while control active intercepts browser shortcuts within canvas; scope is focused canvas during actively-consented session
- T-74-SC: No package added; icons from `lucide-react` (already a dependency); no component registry used

## Verification
- `npm run build` exits 0
- `npx tsc --noEmit` reports no new errors
- `npx vitest run src/__tests__` passes (12 tests in remoteControl.test.ts + existing suite)
- `grep -c 'style={{' components/RemoteDesktop.tsx` returns 0 — no new inline style objects
- `grep -ci '6366f1\|indigo-\|violet-' components/RemoteDesktop.tsx` returns 0 — no indigo/violet in new elements
- `grep -ci 'font-semibold\|font-extrabold\|font-medium\|font-light' components/RemoteDesktop.tsx` returns 0 — only weights 400/700
- Canvas handlers bound conditionally on control-active state (not unconditionally)
- `grep -c 'no_interactive_desktop' components/RemoteDesktop.tsx` returns at least 1; each of 5 reason discriminants maps to distinct string
- `grep -c 'truncate' components/RemoteDesktop.tsx` returns at least 1
- `grep -c 'hasPermission' components/RemoteAccessDashboard.tsx` returns 0 — gating uses server probe
- With `can_control` false, toggle element absent from rendered output entirely
- `grep -c 'truncate' components/RemoteAccessDashboard.tsx` returns at least 1
- Added lines in RemoteAccessDashboard.tsx contain no indigo/violet (`git diff -U0 ... | grep '^+' | grep -ci '6366f1\|indigo-\|violet-'` returns 0)
- Added lines in RemoteAccessDashboard.tsx contain no `style={{` (`git diff -U0 ... | grep '^+' | grep -c 'style={{'` returns 0)

## Success Criteria
An admin with control permission can request control, watch the canvas move through awaiting, active, and ended states with accurate copy at every step, drive the remote desktop with the full input surface only while consent holds, and end the session with a confirmation weight matched to who they are ending it for. An admin without the permission never sees the option.

## Status
Complete.

---

*Phase: 74-interactive-remote-desktop-control-for-tenant-admins-upgrade*
*Completed: 2026-08-30*