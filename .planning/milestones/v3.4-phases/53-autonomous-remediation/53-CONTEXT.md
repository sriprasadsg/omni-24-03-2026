# Phase 53 — Autonomous Remediation — CONTEXT

**Milestone:** v3.4 (Native Security Scanning & Autonomous Remediation) — phase 4 of 5 (50→51→52→**53**→54)
**Requirements:** AUTO-01, AUTO-02, AUTO-03, AUTO-04
**Depends on:** Phase 50 (NSCAN findings/alerts), 51 (VULN findings), 52 (FIM events/queue) — the finding sources this engine consumes

## Goal

Turn the existing backend remediation engine into a closed-loop autonomous remediator for the native security findings: finding → select a deterministic YAML playbook → execute action(s) on the agent → verify the fix → emit completion, with safety guards (dry-run, approval gate, rollback, concurrency cap) and an immutable audit trail. Human override always available.

## Success criteria (what must be TRUE)

1. A finding from VULN/FIM/NSCAN is matched to a playbook, executed, verified, and completed — with a human override available at every step (AUTO-01).
2. Remediation actions (patch package, kill process, restore file, block IP, rotate key, disable service) are YAML-defined per finding class and operator-extensible (AUTO-02).
3. Destructive actions honor dry-run + approval gate, verification failure triggers rollback, and per-agent concurrent remediations are capped (AUTO-03).
4. Every remediation writes an immutable record — finding, playbook, actions, verification result, any operator override (AUTO-04).

## Locked decisions

- **D-01 — Backend-orchestrated engine, extend `autonomous_remediation_service` (AUTO-01).** The engine already dispatches actions to agents via the `agent_instructions` queue (`execute_plan`), unifies findings (`RemediationFinding`: vuln/cspm/alert/compliance), and has a severity ceiling + per-tenant toggle + dedup. Extend it to also consume **NSCAN/VULN/FIM** findings, select a YAML playbook, execute its steps (dispatch), **verify** the fix (re-scan/re-check the finding cleared), and emit completion. **No agent-local engine** — the agent executes commands; the backend orchestrates + verifies + audits.
- **D-02 — Deterministic YAML playbooks in a dedicated store (AUTO-02).** Playbooks are `{name, finding_class, steps: [{action, params, destructive?}], rollback: [...]}` YAML, materialized into a **dedicated `remediation_playbooks` collection** with its own CRUD (NOT the existing LLM `enhanced_playbook_endpoints` store — review HIGH: the schemas differ and would not round-trip). Phase 54's Playbooks tab targets this dedicated store. Executed through a **deterministic run-time action map — no LLM in the execution path**. `ai_playbook_service` (LLM) stays for authoring assistance only. Vendored default playbooks cover: patch_package (→ existing install/upgrade_software), kill_process, restore_file, block_ip, disable_service (rotate_key deferred, D-03).
- **D-03 — Agent executes actions via new `instructions.rs` command arms (AUTO-02).** Add `kill_process`, `restore_file`, `block_ip`, `disable_service` arms (patch reuses existing install/upgrade_software), each bounded/safe and returning a result the engine verifies. Dispatched through the existing `agent_instructions` queue the agent already polls — no parallel dispatch path. **`rotate_key` is DEFERRED** to a backlog follow-up (review MED: under-specified + dangerous + hard to make reversible) — ship the four safe/reversible actions this phase; the `rotate_key` playbook/action is a later addition.
- **D-04 — Safety guards (AUTO-03).** Keep the existing `DRY_RUN` + severity ceiling + dedup. Add: (a) an **approval gate** — destructive steps enter a pending-approval state and only dispatch after operator approval (default-on for destructive); (b) **rollback** — on a verification `failed` for a REVERSIBLE action, run the playbook's rollback steps; for an IRREVERSIBLE action (kill_process, patch_package) a `failed` verify **escalates to a human alert + audit flag, never an automated undo** (review MED); (c) a **max-concurrent-remediations-per-agent** cap tracked via a **DB lease** (a `remediation_inflight` record with a TTL), NOT an in-process map — the backend runs multiple uvicorn workers, so the cap must hold across processes and self-release on completion/timeout (review HIGH).
- **D-05 — Immutable audit trail (AUTO-04).** A new append-only `remediation_audit` collection (via `remediation_audit_service.py`), one immutable record per remediation capturing finding, playbook, actions taken, verification result, and any operator override — cloning the append-only pattern of `remediation_escalations` / agent location-history. Never mutated after write; corrections are new records. Read via a tenant-scoped GET.
- **D-06 — Human override always available (AUTO-01).** The approval gate + a cancel/override path let an operator intervene at any step; every override is recorded in the audit.
- **D-07 — Verify via a grounded two-step (AUTO-01; resolves the review BLOCKER).** The agent→backend result channel EXISTS: the agent reports each instruction's outcome via `POST /api/agents/{hostname}/instructions/result` (`agent_tasks_endpoints.report_instruction_result`), which sets `status` (SUCCESS/FAILURE) + `result` on the `agent_instructions` doc keyed by `task_id`. So verify is: (1) after `execute_plan` dispatch, **poll the dispatched instruction's `status`** (by its task_id) within a bounded timeout for step completion; then (2) **re-run the finding's own check** (re-scan the file / re-query the vuln / re-hash the FIM path) to confirm resolution. Result: `resolved` (check clears) | `failed` (still present) | `unverified` (timeout — NEVER reported as resolved). This does NOT rest on an unconfirmed channel — the polled field is written by an existing endpoint.

## Review resolutions (2026-07-30, from 53-REVIEWS.md)

- **BLOCKER (verify loop):** resolved by D-07 — grounded in the existing `POST /instructions/result` → `agent_instructions.status` write. Verify = poll instruction status + re-run the finding check.
- **HIGH (concurrency across workers):** resolved by D-04(c) — DB-lease concurrency, not an in-process map.
- **HIGH (playbook schema unreconciled):** resolved by D-02 — dedicated `remediation_playbooks` collection + its own CRUD; Phase 54 targets it.
- **MED (rotate_key dangerous):** resolved by D-03 — deferred to backlog; ship four reversible actions.
- **MED (irreversible rollback):** resolved by D-04(b) — irreversible-action verify=failed escalates to a human alert, no automated undo.

## Scope fences (MUST NOT)

- MUST NOT put an LLM in the destructive-action execution path (deterministic YAML action map only).
- MUST NOT execute a destructive action without passing the approval gate when required.
- MUST NOT build an agent-local remediation engine — backend orchestrates, agent executes commands.
- MUST NOT bypass the existing dry-run / severity-ceiling / tenant-enable / dedup guards.
- MUST NOT mutate `remediation_audit` records after write (append-only).
- MUST NOT access `db._db` in new handlers/services.

## Pitfalls

- **Destructive actions on live endpoints** — bound every new agent command; approval-gate default-on for destructive; dry-run must actually no-op the dispatch.
- **Verification semantics** — re-scan/re-check may lag; define a bounded verify (re-run the finding's own check; timeout → `unverified`, never silently `fixed`); rollback only on a definite failure, not on `unverified`.
- **Concurrency** — track in-flight remediations per agent; the cap must not deadlock (release on completion/timeout).
- **Rollback correctness** — rollback steps must be defined per destructive playbook; a missing rollback → leave alone + flag, don't guess.
- **Reuse the `agent_instructions` queue** — the agent already polls it; don't build a second dispatch channel.

## Plan breakdown

| Plan | Wave | Scope | Requirements |
|------|------|-------|--------------|
| 53-01 | 1 | Backend: deterministic YAML playbook system (`remediation_playbook_service.py` + vendored defaults + finding_class→playbook selection) + CRUD via `enhanced_playbook_endpoints` + tests | AUTO-02 |
| 53-02 | 1 | Agent: new `instructions.rs` action arms (kill_process/restore_file/block_ip/disable_service; rotate_key deferred) + tests | AUTO-02 |
| 53-03 | 2 | Backend engine: ingest NSCAN/VULN/FIM findings + dedicated-store playbook selection + execute steps + grounded verify (poll instruction status + re-run finding check) + completion + immutable audit writes | AUTO-01, AUTO-04 |
| 53-04 | 3 | Backend: safety guards (approval gate + reversible rollback / irreversible escalation + DB-lease concurrency cap) + audit read endpoint + tests | AUTO-03, AUTO-04 |
