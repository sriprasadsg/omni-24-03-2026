---
status: complete
phase: 84-staged-patch-rollouts
source: [84-VERIFICATION.md]
started: 2026-11-07T10:20:00Z
updated: 2026-11-07T12:34:52.992Z
---

## Current Test

[testing complete]

## Tests

### 1. Canary install, reboot and post-reboot heartbeat on a real Windows and a real Linux computer (agent 2.1.17, not yet published)
expected: Install result, one restart approval, new-boot heartbeat, fresh inventory and service block are read; the ring goes green only after the soak
result: pass
note: "User tested on another environment with a 2.1.17 build (this VM still runs the 2026-11-05 backend and agent 2.1.14)"

### 2. Force a canary failure on a disposable Linux apt host and a Windows host with a revertible update
expected: Earlier version restored, nothing else removed (--no-remove), unsupported hosts read `halted, not reverted` with a reason; also try an apt host where the package was removed (`rc`) to see WR-25
result: pass
note: "User tested on another environment with a 2.1.17 build"

### 3. Define a Change Management window a few minutes away, start a rollout, watch the wall clock
expected: Nothing installs before the window opens; a late instruction is refused at delivery with instruction_expired
result: pass
note: "User tested on another environment with a 2.1.17 build"

### 4. Approve on an install card and on a Reboot card in the live UI (double-click once); Cancel a running rollout in the live UI
expected: Exactly one instruction per computer; restart warns 'Restarting in 5 minutes for updates'; Cancel keeps patches and the rollout ends cancelled
result: pass
note: "User tested on another environment with a 2.1.17 build and its UI"

### 5. Browser pass over Patching > Rollouts, Start dialog, ring detail, Resume/Cancel, Settings rings, Change Management windows; accept or reject UI-SPEC DEV-1..DEV-4
expected: Matches 84-UI-SPEC; user decision recorded
result: pass
note: "Screens match 84-UI-SPEC; UI-SPEC deviations DEV-1..DEV-4 accepted by the user (pass)"

### 6. Start a rollout with a ring of more than 25 computers
expected: A paged hosts route exists or the limitation is accepted
result: pass
note: "Limitation accepted by the user: no paged hosts route, ring detail reaches the first 25 computers per ring (deferred-items.md)"

### 7. Decide whether to fix WR-25, WR-26, WR-27 and WR-31 before publishing agent 2.1.17 / enabling rollouts for real tenants
expected: Decision recorded
result: pass
note: "Decision: fix all four (WR-25, WR-26, WR-27, WR-31) before agent 2.1.17 is published or rollouts are enabled for real tenants; next step /gsd-code-review 84 --fix"

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
