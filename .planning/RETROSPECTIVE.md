# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v3.4 — Native Security Scanning & Autonomous Remediation Agent

**Shipped:** 2026-08-04
**Phases:** 6 (50–55) | **Plans:** 25

### What Was Built
- Native offline scan engine: file/URL/IP/hash verdicts against signed bundled feeds, no live lookup at scan time (Phase 50)
- Agent-side vulnerability detection: signed CVE feed matching, misconfig + exposed-secret checks (Phase 51)
- File Integrity Monitoring: event-driven native-OS watcher, signed baseline + restart drift detection (Phase 52)
- Autonomous remediation engine: deterministic YAML playbooks, approval gate, rollback, immutable audit trail (Phase 53)
- Operator console + full agent-security API surface (Phase 54)
- Threat-intel correlation, UEBA-triggered predictive containment, outbound OCSF/SIEM webhook (Phase 55)

### What Worked
- Dependency-ordered phasing (shared signed-bundle mechanism first, then the three detection sources that reuse it, then the remediation engine that consumes all of them, then the UI) meant no phase blocked on rework of an earlier one.
- Reusing existing infrastructure aggressively — `autonomous_remediation_service.py`, `webhook_service`, `agent_instructions` dispatch queue, the SSRF+HMAC webhook pipeline — instead of building parallel systems kept the new surface small and avoided duplicating safety logic (approval gates, dry-run, dedup).
- The Phase 50 spike on yara-x (rejected for JIT/cross-compile bloat, documented fallback taken) is an example of a deviation caught early and cheaply rather than discovered mid-build.

### What Was Inefficient
- Formal per-plan `SUMMARY.md`/`VERIFICATION.md` artifacts were inconsistently produced across phases 50–54 (Phase 50: one consolidated summary instead of 5 per-plan; Phase 52: missing 52-02; Phase 54: zero artifacts despite the work being real, tested, and committed). This didn't affect the shipped code, but it meant `gsd-tools init.manager` couldn't recognize 4 of 6 phases as complete at milestone-close time, requiring a manual override decision and after-the-fact reconciliation.
- `.planning/REQUIREMENTS.md` was overwritten on 2026-07-31 (mid-milestone) with an unrelated draft "v4.0" requirement set, which then propagated into the milestone-close tooling: `gsd-tools milestone.complete`'s archival step snapshot-copies whatever is currently in `REQUIREMENTS.md`, so the auto-generated `v3.4-REQUIREMENTS.md` archive initially captured the wrong content and had to be manually reconstructed from the per-phase ROADMAP.md requirement lines.
- 55-VERIFICATION.md's gap #1 (INT-04 route not mounting due to a `virustotal_client.py` import bug) was actually fixed by plan 55-05, but the verification doc's `status: gaps_found` was never updated to reflect the fix — discovered and corrected only at this milestone-close session.

### Patterns Established
- Signed-bundle update mechanism (ed25519 detached signature + versioned `GET` endpoint + local SQLite cache) is now the standard pattern for any agent-side feed distribution (scan signatures, CVE feed, and reusable for future feed types).
- Safety-guard shape for autonomous/automated actions (dry-run, approval gate for destructive ops, rollback on verify-fail, concurrency cap, immutable append-only audit) is now precedent for any future auto-remediation surface — and was proven to extend cleanly to a second trigger source (UEBA anomalies in Phase 55) without weakening the gate.

### Key Lessons
1. When a milestone-close tool auto-archives "whatever's currently in REQUIREMENTS.md," a requirements draft for the *next* milestone must never be written into that file before the *current* milestone actually ships — write next-milestone drafts to `MILESTONE-CONTEXT.md` or a scratch file instead, not `REQUIREMENTS.md`.
2. A `**Status:** Complete — verified ...` line in ROADMAP.md prose is not sufficient signal for phase-completion tooling if the corresponding `SUMMARY.md`/`VERIFICATION.md` artifact files were never written — prose and structured artifacts can drift apart, so treat both as required, not either/or.
3. When a post-verification fix resolves a documented gap, update the `VERIFICATION.md` frontmatter `status` field (not just fix the code) — otherwise the gap re-surfaces as a false blocker at the next milestone-close audit.

### Cost Observations
- Sessions: spanned 2026-07-30 through 2026-08-04 (6 days), plus this milestone-close session.
- Notable: the milestone-close session itself did non-trivial work beyond bookkeeping — resolved a genuine open verification gap (INT-04 route-mounting) that had been sitting unresolved in the phase's own docs.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Key Change |
|-----------|--------|------------|
| v3.2 | 7 (40–45, 999.1) | First milestone with the Jira/ServiceNow ticketing bridge + SLA/escalation pattern |
| v3.3 | 4 (46–49) | First milestone with a dedicated privacy/legal review gate front-loaded for a new data-collection surface (location history) |
| v3.4 | 6 (50–55) | First milestone building agent-side detection/response capability (scan/vuln/FIM/remediation) rather than backend/frontend-only features; first milestone where phase-completion bookkeeping (SUMMARY/VERIFICATION artifacts) meaningfully drifted from actual shipped state, requiring an override-and-reconcile milestone close |

### Top Lessons (Verified Across Milestones)

1. Reusing existing tenant-isolation, dispatch-queue, and safety-guard patterns instead of building parallel systems is the consistent highest-leverage move across v3.2, v3.3, and v3.4.
2. Background schedulers and cross-tenant aggregation endpoints must use the raw `mongodb.db`/`db._db` handle, never the tenant-context-wrapped one — this bug class has now recurred across multiple milestones (v3.2 SLA scheduler, v3.3 fleet-wide sweeps, v3.4's `validate_citations`-style unwraps) and should be checked by default whenever a new fleet-wide or scheduler-driven read is added.
