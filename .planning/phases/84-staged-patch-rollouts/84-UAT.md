---
status: testing
phase: 84-staged-patch-rollouts
source: [84-VERIFICATION.md]
started: 2026-11-07T10:20:00Z
updated: 2026-11-07T10:20:00Z
---

## Current Test

number: 1
name: Canary install, reboot and post-reboot heartbeat on a real Windows and a real Linux computer (agent 2.1.17, not yet published)
expected: |
  Install result, one restart approval, new-boot heartbeat, fresh inventory and service block are read; the ring goes green only after the soak
awaiting: user response

## Tests

### 1. Canary install, reboot and post-reboot heartbeat on a real Windows and a real Linux computer (agent 2.1.17, not yet published)
expected: Install result, one restart approval, new-boot heartbeat, fresh inventory and service block are read; the ring goes green only after the soak
result: [pending]

### 2. Force a canary failure on a disposable Linux apt host and a Windows host with a revertible update
expected: Earlier version restored, nothing else removed (--no-remove), unsupported hosts read `halted, not reverted` with a reason; also try an apt host where the package was removed (`rc`) to see WR-25
result: [pending]

### 3. Define a Change Management window a few minutes away, start a rollout, watch the wall clock
expected: Nothing installs before the window opens; a late instruction is refused at delivery with instruction_expired
result: [pending]

### 4. Approve on an install card and on a Reboot card in the live UI (double-click once); Cancel a running rollout in the live UI
expected: Exactly one instruction per computer; restart warns 'Restarting in 5 minutes for updates'; Cancel keeps patches and the rollout ends cancelled
result: [pending]

### 5. Browser pass over Patching > Rollouts, Start dialog, ring detail, Resume/Cancel, Settings rings, Change Management windows; accept or reject UI-SPEC DEV-1..DEV-4
expected: Matches 84-UI-SPEC; user decision recorded
result: [pending]

### 6. Start a rollout with a ring of more than 25 computers
expected: A paged hosts route exists or the limitation is accepted
result: [pending]

### 7. Decide whether to fix WR-25, WR-26, WR-27 and WR-31 before publishing agent 2.1.17 / enabling rollouts for real tenants
expected: Decision recorded
result: [pending]

## Summary

total: 7
passed: 0
issues: 0
pending: 7
skipped: 0
blocked: 0

## Gaps
