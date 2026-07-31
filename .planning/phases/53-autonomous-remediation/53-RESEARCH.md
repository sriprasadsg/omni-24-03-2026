# Phase 53 — Autonomous Remediation — RESEARCH

Codebase-grounded. Refs verified 2026-07-30.

## 1. Existing-surface audit

| Surface | State | Use in 53 |
|---------|-------|-----------|
| `backend/autonomous_remediation_service.py` | `RemediationFinding` (vuln/cspm/alert/compliance) + `RemediationPlan` (action, params, script, requires_approval); `scan_for_remediable_findings`; `_severity_within_ceiling` (MAX_AUTO_SEVERITY); `_is_tenant_enabled`; `execute_plan` → DRY_RUN check → build instruction → dedup (ResponseOrchestrator) → `db.agent_instructions.insert_one` → `_log_decision` to `agent_ai_decisions`. Wired via `app_background_tasks.py` + `response_orchestrator.py`. | Extend: add NSCAN/VULN/FIM finding sources; playbook selection; a **verify** step (absent today); completion; audit writes. |
| `execute_plan` dispatch | Inserts `{type: action, agent_id, payload, status: "pending", triggered_by}` into `agent_instructions` (the queue the agent polls). Has DRY_RUN + dedup. | Reuse verbatim for step dispatch. No verify/rollback/concurrency yet. |
| `backend/enhanced_playbook_endpoints.py` + `ai_playbook_service.py` | Playbook CRUD/store; LLM playbook generation (`generate_playbook`, steps/action/trigger shape) | CRUD store for the deterministic YAML playbooks (D-02); LLM stays authoring-only. |
| `agent-install/omni-agent-rs/src/instructions.rs` | Command arms: install_software, upgrade_software, enable/disable_rdp, apply_agent_update, network_scan, create_ticket, remote session… Each executes + returns JSON; some POST results. **No kill_process/restore_file/block_ip/rotate_key/disable_service.** | Add the 5 new destructive-action arms (D-03); patch reuses install/upgrade_software. |
| `remediation_escalations` / agent location-history | append-only immutable write pattern (Phase 44 / 46) | Clone for `remediation_audit` (D-05). |
| `ResponseOrchestrator.is_duplicate_action` | dedup window per agent/action | Keep; add concurrency-cap tracking alongside. |

**Net:** the engine, dispatch queue, playbook store, agent executor, and append-only audit pattern all exist. Phase 53 adds the YAML playbook layer, the 5 agent actions, the verify→complete→audit loop, and the three missing guards (approval gate, rollback, concurrency cap).

## 2. YAML playbooks (AUTO-02) — D-02

`remediation_playbook_service.py`: load/validate deterministic YAML playbooks `{name, finding_class, match: {...}, steps: [{action, params, destructive: bool}], rollback: [{action, params}]}`; `select_playbook(finding)` maps `finding_class` (nscan|vuln|fim|misconfig|secret…) → the best-matching playbook. Vendored defaults (one per action): patch_package, kill_process, restore_file, block_ip, rotate_key, disable_service. Stored/edited via `enhanced_playbook_endpoints` (operator-extensible). No LLM at run time — a fixed `ACTION_MAP: {action_name → agent command}`.

## 3. Agent actions (AUTO-02) — D-03

New `instructions.rs` arms, each bounded + returning `{status, detail}`:
- `kill_process` (by pid/name), `restore_file` (from a baseline/backup path — ties to Phase 52 baseline), `block_ip` (host firewall rule add), `rotate_key` (regenerate/rotate a named credential/key — bounded to safe targets), `disable_service` (stop+disable a named service). `patch_package` → existing install/upgrade_software. Dispatched via the `agent_instructions` queue (payload from the playbook step). Cross-compile: pure Rust / OS commands; re-check windows-gnu.

## 4. Engine loop (AUTO-01) — D-03/53-03

`remediate(finding)`: guard checks (tenant enabled, severity ceiling, concurrency cap, approval if destructive) → `select_playbook` → for each step: `execute_plan(step)` (dispatch), await the agent result (via the instruction result / a bounded poll) → after steps, **verify**: re-run the finding's own check (re-scan file / re-query vuln / re-hash FIM path) → `resolved` | `unverified` | `failed`; on `failed` run rollback steps → emit a completion event → write the immutable audit record at each transition. Human override (cancel/approve) available throughout (D-06).

## 5. Immutable audit (AUTO-04) — D-05

`remediation_audit_service.py`: append-only `remediation_audit` collection, one record per remediation `{remediation_id, tenantId, agentId, finding, playbook, steps_dispatched, verification_result, override?, ts}`; only inserts (never update/delete). Tenant-scoped GET to read the trail (53-04).

## 6. Safety guards (AUTO-03) — D-04/53-04

- **Approval gate:** a destructive playbook (any `destructive: true` step) sets the remediation to `pending_approval`; an operator approve/deny endpoint gates dispatch. Default-on for destructive.
- **Rollback:** on verification `failed`, run the playbook `rollback` steps (dispatched like normal steps); a missing rollback → leave + flag.
- **Concurrency cap:** `MAX_CONCURRENT_PER_AGENT`; count in-flight remediations per agent; over cap → queue/defer, never deadlock (release on complete/timeout).
- Keep DRY_RUN (no-op dispatch), severity ceiling, dedup.

## 7. Risk

- **Biggest phase; destructive actions.** Approval-gate default-on + dry-run + rollback are the guardrails — test them hard.
- **Verify semantics** — bounded, timeout→`unverified` (not `fixed`); rollback only on definite `failed`.
- **Reuse the instruction queue** — no second dispatch path.
- No new pip/crate deps expected (YAML via existing `serde_norway`/PyYAML; commands are OS-level). Re-check windows-gnu after the new agent arms.
