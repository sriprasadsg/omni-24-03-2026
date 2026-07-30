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
- **D-02 — Deterministic YAML playbooks (AUTO-02).** Playbooks are `{finding_class, steps: [{action, params, destructive?}], rollback: [...]}` YAML, stored + CRUD'd via the existing `enhanced_playbook_endpoints`/playbook store, executed through a **deterministic run-time action map — no LLM in the execution path**. `ai_playbook_service` (LLM) stays for authoring assistance only. Vendored default playbooks cover: patch_package (→ existing install/upgrade_software), kill_process, restore_file, block_ip, rotate_key, disable_service.
- **D-03 — Agent executes actions via new `instructions.rs` command arms (AUTO-02).** Add `kill_process`, `restore_file`, `block_ip`, `rotate_key`, `disable_service` arms (patch reuses existing install/upgrade_software), each bounded/safe and returning a result the engine verifies. Dispatched through the existing `agent_instructions` queue the agent already polls — no parallel dispatch path.
- **D-04 — Safety guards (AUTO-03).** Keep the existing `DRY_RUN` + severity ceiling + dedup. Add: (a) an **approval gate** — destructive steps enter a pending-approval state and only dispatch after operator approval (default-on for destructive); (b) **rollback** — on verification failure, run the playbook's rollback steps; (c) a **max-concurrent-remediations-per-agent** cap (in-flight tracking).
- **D-05 — Immutable audit trail (AUTO-04).** A new append-only `remediation_audit` collection (via `remediation_audit_service.py`), one immutable record per remediation capturing finding, playbook, actions taken, verification result, and any operator override — cloning the append-only pattern of `remediation_escalations` / agent location-history. Never mutated after write; corrections are new records. Read via a tenant-scoped GET.
- **D-06 — Human override always available (AUTO-01).** The approval gate + a cancel/override path let an operator intervene at any step; every override is recorded in the audit.

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
| 53-02 | 1 | Agent: new `instructions.rs` action arms (kill_process/restore_file/block_ip/rotate_key/disable_service) + tests | AUTO-02 |
| 53-03 | 2 | Backend engine: ingest NSCAN/VULN/FIM findings + playbook selection + execute steps + verify loop + completion + immutable audit writes (`remediation_audit_service.py`) | AUTO-01, AUTO-04 |
| 53-04 | 3 | Backend: safety guards (approval gate + rollback + concurrency cap) + audit read endpoint + tests | AUTO-03, AUTO-04 |
