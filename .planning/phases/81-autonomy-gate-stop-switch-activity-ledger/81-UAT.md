---
status: complete
phase: 81-autonomy-gate-stop-switch-activity-ledger
source: [81-VERIFICATION.md]
started: 2026-10-26T22:12:37Z
updated: 2026-11-05T11:50:54Z
---

## Current Test

[testing complete]

## Tests

### 1. Decide whether the operator-click Undo may read 'Undone.' as soon as the undo instruction is queued
expected: Either accept it (D-12 design: the click is the approval; the screen reports the request) or require the row to stay pending until the agent confirms the undo (and become failed if it reports FAILURE or never picks it up)
result: pass

### 2. Decide whether multi-step operator playbooks may run automatically before WR-11 / WR-12 / WR-13 / WR-10 are closed
expected: Either accept (all six vendored playbooks are single step; the one live caller of remediate() is UEBA kill_process, an approval-class action; shadow mode is on) or restrict automatic dispatch to single-step playbooks until the four warnings are fixed
result: pass

### 3. Apply migration 024 and restart the backend (operator step; nothing was applied live)
expected: Every tenant has an autonomy_settings document (Platform tenant Off, others Undoable-auto with shadow on); platform stop and reconciler start without error
result: pass

### 4. Flip the platform stop on the live server while an automatic instruction is queued, then poll as a real agent
expected: The poll withholds the instruction (it becomes cancelled_by_stop), no restart needed; pending approvals stay frozen; undo still works
result: pass
note: "Passed by the user. At 23:42 the live DB (omni_platform on Omniai-copy) held no system_settings autonomous_ops stop record and no uat81-test4 instruction, so the stop was not pressed against this server. The only live agent is in the Platform tenant (never eligible), so no real automatic instruction can be queued here; approvals-frozen and undo-during-stop are covered by automated tests only."

### 5. Watch the live agent status refresh
expected: An agent silent for more than 5 minutes flips to Offline within about 30 s, and the notification names only agents that actually went offline
result: pass
note: "Passed by the user without a live run on this server: at 23:46 omni-agent was active, Omniai-copy Online (last seen 23:43:41), and no offline notification was on record."

### 6. Open the Autonomous Ops screen in a published UI build as a tenant admin (screen ticked) and as Super Admin
expected: Six states and a labelled Simulation chip render; Stop/Resume dialogs and the app-wide stop banner appear; tenant sees 'Platform administrator' for a platform stop
result: pass
note: "2026-11-05: passed in headless Chrome on the release bundle (the published UI plus 2026-11-05 fixes), private copy. Tenant admin (screen ticked): labelled Shadow mode chip On: simulation only, Stop chip, levels; Super Admin platform stop: dialog, app-wide banner on other screens, tenant reads Stopped by Platform administrator and Only a platform administrator can resume this; resume clears it; tenant stop and resume of its own organization; the stop is listed in Activity. No page errors, no refused requests."

### 7. Decide whether the documented XDR-GRANDFATHERED writers are acceptable under the phase goal wording 'every automatic action in the platform'
expected: Either accept (monitoring/hunt/snapshot/auto-update verbs stay outside gate and stop; fenced later) or require them to be gated before switch-on
result: pass

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
