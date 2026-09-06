---
status: superseded
superseded_at: 2026-08-25T05:35:00Z
superseded_by: .planning/phases/65-fim-process-attribution-via-fanotify/
---

# Superseded: early, ungrounded "Phase 65" research + plan draft

This directory lived at
`.planning/milestones/v3.4-phases/65-fim-process-attribution-via-fanotify/`
— same name as the canonical, live phase directory. Moved out as part of
a general cleanup that restored every resolvable archived phase (50-61)
back to `.planning/phases/` so `gsd_run` phase-number queries work again;
this one and phase 64's `_superseded-64-key-rotation-draft/` were the two
exceptions, kept out because their content genuinely diverges from and
predates the canonical work.

## What this track actually is

Just two files: `65-01-PLAN.md` and `RESEARCH.md` (titled
"Phase 65: FIM Process Attribution via Fanotify Research (Skipped)").
No SUMMARY.md, no VERIFICATION.md — never executed.

- The research doc is ungrounded relative to this project's actual
  stack: it recommends PostgreSQL and Redis Pub/Sub for storage/event
  correlation, neither of which this project uses anywhere (it's
  MongoDB throughout, with a local SQLite queue on the agent side). It
  reads as generic/templated rather than researched against this
  codebase — no package-legitimacy audit, no real crates.io data, no
  correct file paths.
- `65-01-PLAN.md` targets bare `src/capabilities/fim_fanotify_watcher.rs`
  / `src/capabilities/fim_process_mapper.rs` / `tests/fim_fanotify_test.rs`
  — the wrong tree structure entirely, not
  `agent-install/omni-agent-rs/src/capabilities/...` (the canonical,
  shipped agent tree since 2026-07-16 per project memory).

## Why the canonical track wins

`65-fim-process-attribution-via-fanotify/` (live) has a properly
grounded `65-RESEARCH.md` (real package-legitimacy audit flagging
`fanotify-rs`/`naughtyfy` as SUS, correct canonical tree paths), a real
executed `65-01-PLAN.md` with a matching `65-01-SUMMARY.md`, and a full
`65-VERIFICATION.md`/`65-VALIDATION.md`/checkpoint trail proving actual
completion. This draft never got past an ungrounded research pass.
