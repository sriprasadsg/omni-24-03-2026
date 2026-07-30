# Phase 52 — REVIEWS (self-review, 2026-07-30)

> Reviewer: claude-self (adversarial; no independent external model available).

## HIGH — FIM-02's "process tree" is only best-effort with `notify` (requirement gap)
`notify` events carry no PID, so `process: {pid, name, tree}` is `unknown` on most events. FIM-02 explicitly requires "process tree." The plans call this out as best-effort, but a strict reading of FIM-02 is only partially met — the raw-fanotify option (declined) is what would truly satisfy it.
**Disposition:** accepted partial by the engine-choice decision — but make it EXPLICIT in the phase VERIFICATION and the milestone audit that FIM-02's process-tree clause is best-effort, not full. Consider a follow-up backlog item for fanotify-based PID attribution on Linux.

## HIGH — Hard cross-phase build dependency on Phase 50's Cargo deps
`52-03` uses `ed25519-dalek`, added by Phase 50. If phases execute out of order (or 52 before 50 completes), 52 won't compile. Same latent issue as the 50 Cargo-ordering finding.
**Fix:** state the hard ordering (50 Cargo deps must land before 52 compiles) in 52's execution notes; ideally centralize the agent Cargo deps.

## MED — `notify` on Windows is ReadDirectoryChangesW, not USN Journal (deviation from FIM-01 wording)
Documented, but the milestone audit should record this as an accepted deviation from the literal "USN Journal," not silently. ReadDirectoryChangesW also does not natively surface permission-only changes as a distinct event — the plan maps permission→modify best-effort, which under-delivers the "permission changes" clause of FIM-01.
**Fix:** verify at execute whether permission-only changes are detectable on each platform; if not, document the gap.

## MED — Watcher is dead code until 52-04; real behavior only validated at UAT
52-02 builds the watcher but 52-04 wires it into `agent_loop`. Unit tests cover event-mapping + enqueue, not the live inotify/RDCW path (timing-dependent). The actual "does it fire on a real file change" is only proven by the 52-04 human-check.
**Disposition:** acceptable, but ensure the 52-04 human-check is treated as REQUIRED verification, not optional.

## LOW — Baseline key rotation on reset needs a defined trigger
D-03 says "rotate on baseline reset" — specify when/how (new keypair on every reset vs keep key, re-sign). Ambiguous.

## Accepted
- Local sqlite queue as the Phase-53 handoff + backend report — clean.
- ed25519-signed baseline, fail-closed on tamper — sound.
