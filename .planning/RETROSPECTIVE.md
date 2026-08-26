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

## Milestone: v4.1 — ITAM-Backlog

**Shipped:** 2026-08-26
**Phases:** 5 (69–73) | **Plans:** 26

### What Was Built
- Full user management & auth: CRUD, RBAC, LDAP/AD bind auth, SAML/SSO (full signature/replay validation), scope-aware API tokens, TTL-backed MFA (Phase 69)
- Custom fields authoring UI, audit trail backfilled into 20 write routes across 7 endpoint files, bidirectional CSV import/export with dry-run (Phase 70)
- Purchase order/supplier/warranty/depreciation tracking plus a full asset request + approval workflow with notifications (Phase 71)
- Custom report builder, 6 pre-built reports, PDF/Excel/CSV export, 4-tile KPI dashboard with drill-down (Phase 72)
- Dual session/API-key auth with scope narrowing, 8 webhook event types, Jira/ServiceNow ticketing bridge with dedup guards (Phase 73)

### What Worked
- Every report/KPI/CSV-import validation path reused its owning surface's existing computation/validation function verbatim (Phase 70's CSV importer calls the exact same `collect_field_defs`/`validate_custom_field_values`/`build_asset_document` the manual-create route uses; Phase 72's reports/KPIs all call into Finance/Licence/Lifecycle logic directly) — no report ever risked showing a different number than the live panel it summarizes.
- New external dependencies for auth protocols (`ldap3`, `python3-saml`) were gated behind an explicit human-approved blocking checkpoint in the plan itself, rather than silently added — caught before becoming a supply-chain surprise.
- Webhook dispatch was fire-and-forget (`asyncio.create_task`, never awaited inline) from the first tracer plan onward, so a slow/down receiver could never add latency to the asset mutation that triggered it.

### What Was Inefficient
- When phases were folded into root `ROADMAP.md` from the superseded `v4.1-ROADMAP.md` (2026-08-13), no corresponding `## v4.1 — Name` milestone heading was ever added — the phases just landed as bare `### Phase N` entries under the leftover `## v3.4` heading. Combined with `STATE.md`'s `milestone:` frontmatter having drifted to `v1.1` (a milestone shipped 2026-06-22), `gsd_run`'s "current milestone" queries silently resolved to the wrong, long-shipped milestone for an unknown period — only caught when this close session cross-checked `init.milestone-op`'s phase count against `init.manager`'s and found them disagreeing.
- Phase 71 was left mid-session at some point (`wip: pause phase 71 procurement workflow` commit) with a FastAPI entrypoint file accidentally deleted and an orphaned dead-code scaffold left behind; the resuming session had to find and fix both before finishing the phase.
- 4 of 5 phases (69/70/72/73) closed `human_needed` rather than `passed` — all genuinely live-environment-only checks (LDAP/SAML real-directory auth, MFA click-through, concurrent-tenant load isolation, 2 UI viewport visual checks), not missing implementation, but it meant the milestone couldn't reach a clean `verified_closeout` and needed an explicit override decision.
- The pre-close audit's `deferred_items` category refused to acknowledge 6 items via its CLI writer (`unsupported_heading_shape`) because those `deferred-items.md` files use a heading-delimited entry format the writer doesn't support yet — required manually editing each file's `status:` field, and the writer's exact-string-equality check (`status === 'acknowledged'`, not a prefix match) meant a first attempt with explanatory text appended to the status value silently failed to suppress the item.

### Patterns Established
- Human-approved blocking checkpoint for any new external dependency implementing an auth protocol (LDAP, SAML, and by extension OIDC/OAuth2 if added later) — the plan pauses for explicit approval before the dependency is added, not after.
- "Reuse the owning surface's computation function verbatim" is now precedent for any report/dashboard/export surface that summarizes data another panel already computes.

### Key Lessons
1. When a milestone's phases are renumbered or folded into the root `ROADMAP.md` from a separate milestone-specific file, add the corresponding `## vX.Y — Name` heading in the *same* edit that adds the phases — a bare `### Phase N` entry with no owning milestone heading silently falls back to whatever `STATE.md`'s (possibly stale) `milestone:` pointer says, for however long nobody cross-checks it.
2. `human_needed` verification for live-environment-only checks (LDAP/SAML directory auth, MFA click-through, concurrent load, viewport visuals) is a legitimate, recurring terminal state for a sandboxed agent — not a gap needing a fix — and should be accepted as a milestone-close override rather than blocking indefinitely, matching precedent from Phase 34/40's physical-device residuals.
3. A milestone-completion tool's own housekeeping can delete unrelated in-progress work if that work lives in a shared/global file rather than something phase-scoped (`gsd_run query milestone.complete` deleted `.planning/HANDOFF.json` — an unrelated, unresolved Phase 66 root-cause investigation with a pending human decision — as a side effect). Always diff what an automated archival step touched before committing it, not just what you intentionally changed.
4. A CLI acknowledge-writer's `status:` field match can be exact-string, not prefix — appending explanatory context to the same line as `**Status:** acknowledged` silently defeats the suppression; put context in a separate sibling bullet instead.

### Cost Observations
- Sessions: phase work spanned 2026-08-13 through 2026-08-25 (12 days), plus this milestone-close session (2026-08-26) which itself found and fixed the stale milestone pointer, added the missing `ROADMAP.md` heading, and restored an unrelated deleted file.
- Notable: the milestone-close session's data-integrity findings (stale pointer, missing heading) took longer to diagnose than the archival mechanics themselves — worth treating "does `gsd_run` resolve the milestone I think it should" as a standing pre-flight check, not just at close time.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Key Change |
|-----------|--------|------------|
| v3.2 | 7 (40–45, 999.1) | First milestone with the Jira/ServiceNow ticketing bridge + SLA/escalation pattern |
| v3.3 | 4 (46–49) | First milestone with a dedicated privacy/legal review gate front-loaded for a new data-collection surface (location history) |
| v3.4 | 6 (50–55) | First milestone building agent-side detection/response capability (scan/vuln/FIM/remediation) rather than backend/frontend-only features; first milestone where phase-completion bookkeeping (SUMMARY/VERIFICATION artifacts) meaningfully drifted from actual shipped state, requiring an override-and-reconcile milestone close |
| v4.1 | 5 (69–73) | First milestone where the ROADMAP.md/STATE.md milestone-pointer itself went stale (not just phase-completion bookkeeping) — `gsd_run` silently resolved "current milestone" against a long-shipped v1.1 instead of v4.1 until this close session cross-checked two init queries against each other; first milestone with a majority (4/5) of phases closing `human_needed` rather than `passed`, all accepted as override |

### Top Lessons (Verified Across Milestones)

1. Reusing existing tenant-isolation, dispatch-queue, and safety-guard patterns instead of building parallel systems is the consistent highest-leverage move across v3.2, v3.3, v3.4, and v4.1.
2. Background schedulers and cross-tenant aggregation endpoints must use the raw `mongodb.db`/`db._db` handle, never the tenant-context-wrapped one — this bug class has now recurred across multiple milestones (v3.2 SLA scheduler, v3.3 fleet-wide sweeps, v3.4's `validate_citations`-style unwraps) and should be checked by default whenever a new fleet-wide or scheduler-driven read is added.
3. Whenever phases move between roadmap files (superseded-milestone folding, renumbering, archival), the destination file's milestone *heading* must move in the same edit as the phases — a bare phase list with no owning heading silently falls back to whatever the state file's pointer says (v4.1's close session finding), the same class of bug as the earlier phase-number collisions (v3.4-close/v4.0-close era).
