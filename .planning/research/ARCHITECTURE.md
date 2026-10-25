# Architecture Research: v4.3 Autonomous Ops

**Domain:** Policy-gated autonomous security response, staged patching, platform self-healing and first-line service desk, added to an existing multi-tenant security/compliance/ITAM platform (single systemd VM, FastAPI + MongoDB, Python + Rust endpoint agents)
**Researched:** 2026-10-25
**Confidence:** HIGH for integration points and gaps (every claim below was read from this repo, file paths given; "no caller" and "no reader" claims were confirmed with `git grep`). MEDIUM for the watchdog privilege model and the agent action parity (needs a live check, flagged). Items marked DECISION need a user or discuss-phase call.

## Scope note

This is a subsequent-milestone integration study. Tenant isolation (`database.py` wrapper plus `tenant_context`), RBAC, the catalogue manifest and guards, the audit ledger, the v3.4 remediation engine and the agent instruction queue already exist and are not re-researched. This file answers only how Autonomous Ops attaches to them. Never call the feature "ASI" or "Autopilot" (`backend/autopilot_service.py` is Windows Autopilot). Package and routes are named `autonomous_ops`.

Five findings from reading the code change the shape of the work. They are stated up front because the build order depends on them.

1. **There is no dispatch choke point today.** About 25 call sites insert straight into `agent_instructions` (`agent_chat_endpoints.py`, `agentic_service.py`, `patch_core_endpoints.py`, `autonomous_remediation_service.py:execute_plan`, `compliance_*`, `remote_endpoints.py`, ...). Two more writers (`soar_engine.py`, `swarm_service.py`) insert into `db.instructions`, a collection **no agent and no backend reader ever polls** (`git grep` finds no `instructions.find`). So `propagate-antibody` and the SOAR `block_ip`/`network_isolate` plugins are dead ends and must not be reused. The choke point has to be a new module that Autonomous Ops actors are forced through, plus a delivery-time hook for defence in depth. It cannot be retrofitted onto human-initiated routes, and must not try to be.
2. **The v3.4 engine's `destructive` flag is data, not policy.** `remediate()` parks a request as `pending_approval` when any playbook step carries `destructive: true`. That flag lives in YAML that operators can edit through the `remediation_playbooks` collection, and every vendored playbook marks `block_ip` and `disable_service` destructive. The locked decision (block IP auto, kill process approved) needs a code-owned action registry where a YAML flag may only raise a class, never lower it.
3. **The existing periodic loop is inert and violates the no-LLM rule.** `autonomous_remediation_loop` calls `run_cycle`, which returns "disabled" unless `tenants.enabledFeatures` holds `autonomousRemediation`. That string appears in no switch catalogue (`shared/tenant-feature-switches.json`) and no UI sets it. When enabled, `generate_plan` sends `alert` findings to `agentic_service.run` (LLM tool choice) and `vulnerability`/`cspm`/`compliance` findings to LLM-generated scripts. The deterministic `remediate()` is called from exactly one place, `ueba_service.py:121`. The new security loop replaces `run_cycle`; it does not extend it.
4. **Three agent actions the milestone needs do not exist in the Rust agent.** `agent-install/omni-agent-rs/src/instructions.rs` handles `kill_process`, `restore_file`, `block_ip`, `unblock_ip`, `disable_service`, `enable_service`, `rotate_key(_rollback)`, `install_patches`, `rollback_patches`. There is no `restart_service`, `quarantine_file`/`unquarantine_file`, `isolate_host`/`restore_host`, `reboot_host` or health probe. The Python agent has quarantine/isolate/restore in `agent/capabilities/autonomous_response.py`, reached through a different (response-task) path, and not `restart_service` on the instruction path. These are long-lead items and a capability-gating trap (finding 5).
5. **Unmapped instruction names bypass per-tenant agent capabilities.** `agent_capabilities._INSTRUCTIONS` maps instruction names to capabilities; "names outside the catalogue are never touched". Any new instruction (`restart_service`, `quarantine_file`, `reboot_host`, `health_probe`) that is not added there is delivered to every tenant regardless of what the Super Admin ticked.

## Standard Architecture

### System Overview

```
 HUMANS                         BACKEND PROCESS (omni-backend.service, 1 uvicorn worker)
 ┌──────────────────┐   ┌──────────────────────────────────────────────────────────────┐
 │ Activity view    │   │  /api/autonomous-ops/*  (catalogue-guarded router, NEW)      │
 │ approve / deny / │──▶│   settings, actions, approve, deny, undo, stop (tenant)      │
 │ undo / stop      │   │  /api/platform/autonomous-ops/* (platform-only stop, NEW)    │
 └──────────────────┘   └───────────────┬──────────────────────────────────────────────┘
                                         │
 DECIDERS (deterministic rules, no LLM)  ▼
 ┌─────────────┐ ┌──────────────┐ ┌─────────────┐ ┌──────────────┐ ┌─────────────────┐
 │ security    │ │ patch ring   │ │ app health  │ │ service desk │ │ watchdog ingest │
 │ response    │ │ controller   │ │ + retention │ │ first line   │ │ (host reports)  │
 │ sweep       │ │ sweep        │ │ sweep       │ │ sweep        │ │ sweep           │
 └──────┬──────┘ └──────┬───────┘ └──────┬──────┘ └──────┬───────┘ └────────┬────────┘
        │  ActionRequest(tenant, kind, action, targets, reason, dedupeKey)    │
        ▼               ▼                ▼               ▼                   ▼
 ╔══════════════════════════════════════════════════════════════════════════════════╗
 ║  autonomous_ops.gate.decide()  ── THE choke point ──  ALLOW_AUTO | NEEDS_APPROVAL ║
 ║  platform stop → tenant eligibility → tenant stop → level → registry → class →   ║
 ║  blast radius → cooldown/window → dedupe/suppression          | PROPOSE | DENY    ║
 ╚════════════╤═════════════════════════════════════════════════════════════════════╝
              │ every decision writes a ledger row + audit_ledger event
              ▼
 ┌────────────────────┐   ALLOW_AUTO or approved   ┌──────────────────────────────────┐
 │ autonomy_actions   │──────────────────────────▶│ gate.execute()  (only writer of   │
 │ (state machine,    │                            │ autonomous agent_instructions)    │
 │ undo, reason)      │◀── reconciler (resumable) ─│ stamps autonomy:{actionId,...}    │
 └─────────┬──────────┘                            └──────────────┬───────────────────┘
           │ audit_ledger.event (hash chain)                       ▼
           ▼                                          agent poll: deployment_result_endpoints /
   audit_logs (canonical)                              agent_tasks_endpoints → hold_back (capability)
                                                        + hold_back_autonomous (stop switch) NEW
                                                                   ▼
                                                    Rust / Python agent executes, POSTs result

 HOST (outside the backend process)
 ┌─────────────────────────────────────────────────────────────────────────────────┐
 │ omni-watchdog.timer (30-60 s) → omni-watchdog.service (oneshot, stdlib Python)  │
 │ checks backend /api/health + /api/health/ready, mongod, ollama, disk, TLS cert  │
 │ restarts allowlisted units under a budget, alerts on-call out of band           │
 │ writes events → Mongo (if up) + logs/watchdog-events.ndjson; backend ingests    │
 └─────────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | New / Modified |
|-----------|----------------|----------------|
| `backend/autonomous_ops/settings.py` | Read per-tenant level/cap/stop and the platform stop; 5 s in-process cache; fail-closed on lookup error | NEW |
| `backend/autonomous_ops/registry.py` | Code-owned action registry: approval class, inverse (undo) action, blast unit, cooldown | NEW |
| `backend/autonomous_ops/gate.py` | `decide()`, `execute()`, `approve()`, `deny()`, `undo()`; the only door to autonomous dispatch | NEW |
| `backend/autonomous_ops/ledger.py` | `autonomy_actions` state machine, dedupe keys, suppressions, `audit_ledger.event` mirror | NEW |
| `backend/autonomous_ops/reconciler.py` | Resumable verify/timeout/expiry tick (survives backend restart) | NEW |
| `backend/autonomous_ops/security_response.py` | Per-tenant sweep: findings → `remediate()` through the gate | NEW |
| `backend/autonomous_ops/patch_rollout.py` | Ring controller: ring jobs, soak, health gate, halt + auto-rollback | NEW |
| `backend/autonomous_ops/selfheal.py` | App-level checks (retention, audit spool backlog, stuck approvals, watchdog dead-man) and watchdog-event ingest | NEW |
| `backend/autonomous_ops/retention_job.py` | Scheduled retention wrapper (excludes `audit_logs`) | NEW |
| `backend/autonomous_ops/service_desk.py` | First-line ticket answer with rule-based escalate-or-answer | NEW |
| `backend/autonomous_ops/summarizer.py` | The only module allowed to import an LLM; adds an "in plain words" field after the fact | NEW |
| `backend/autonomous_ops_endpoints.py` | Tenant router `/api/autonomous-ops` plus platform router | NEW |
| `scripts/omni-watchdog.py` + unit/timer generated by `start-all-services.sh` | Host watchdog | NEW |
| `backend/autonomous_remediation_service.py` | `remediate()` asks the gate instead of computing `is_destructive`; `approve/deny` call the gate; dispatch/verify split into resumable states | MODIFIED |
| `backend/remediation_playbook_service.py` | `ACTION_MAP` gains `restart_service`, `quarantine_file`, `unquarantine_file`, `isolate_host`, `restore_host`; `select_playbook` routes CVE findings to the ring engine in autonomy mode | MODIFIED |
| `backend/playbooks/*.yaml` | New playbooks for the new actions; `destructive` flag becomes advisory | MODIFIED/NEW |
| `backend/agent_capabilities.py` | `_INSTRUCTIONS` maps every new instruction name to a capability | MODIFIED |
| `backend/deployment_result_endpoints.py`, `backend/agent_tasks_endpoints.py` | Call `hold_back_autonomous` beside `agent_capabilities.hold_back`; `record_agent_patch_result` nudges the ring controller | MODIFIED |
| `backend/patch_core_endpoints.py` | Extract rollback job creation (lines 253-298) into a callable service function; accept `rolloutId`/`ringIndex` on jobs | MODIFIED |
| `backend/app_background_tasks.py`, `backend/app_startup.py` | Replace `autonomous_remediation_loop`; register the new sweeps under distributed locks | MODIFIED |
| `backend/retention_endpoints.py` | `/stats` fills `next_scheduled`; manual run reuses the job body | MODIFIED |
| `shared/catalogue-access.json`, `shared/tenant-feature-switches.json`, `backend/catalogue_mounts_*.py`, `backend/rbac_defaults.py` | New screen, switch, guard mount, permissions | MODIFIED |
| `agent-install/omni-agent-rs/src/instructions.rs`, `src/capabilities/remediation_actions.rs`, Python agent | New instruction handlers | MODIFIED |
| `components/AutonomousOpsActivity.tsx`, `services/apiService.ts` | Activity view, settings panel, approvals | NEW/MODIFIED |

## Recommended Project Structure

```
backend/
├── autonomous_ops/                 # package; AST test forbids LLM/db-direct imports except where noted
│   ├── __init__.py
│   ├── settings.py                 # level, cap, stop; cache; fail-closed
│   ├── registry.py                 # ACTIONS table (code, not YAML, not DB)
│   ├── gate.py                     # decide / execute / approve / deny / undo
│   ├── ledger.py                   # autonomy_actions + suppressions + audit mirror
│   ├── reconciler.py               # resume in-flight actions after restart
│   ├── security_response.py
│   ├── patch_rollout.py
│   ├── selfheal.py                 # app checks + watchdog-event ingest
│   ├── retention_job.py
│   ├── service_desk.py
│   └── summarizer.py               # sole LLM import; summaries are decoration
├── autonomous_ops_endpoints.py     # router(s); mounted via catalogue_mounts_*.py
├── migrations/024_autonomous_ops.py   # indexes only (unique partial dedupe, state/time)
└── tests/test_autonomous_ops_*.py
scripts/omni-watchdog.py            # stdlib only; root-owned config in /etc/omni-watchdog/
components/AutonomousOpsActivity.tsx
```

Rationale: the backend is a flat module directory, but `ai_orchestration/` and `migrations/` show packages are accepted, and a package gives the import-lint test a directory to scan. The watchdog is stdlib-only so it still runs when the backend venv is broken, which is one of the failure modes it exists for.

## Architectural Patterns

### Pattern 1: One gate, two enforcement points

**What:** `gate.decide()` is the single decision function for every autonomous action; `gate.execute()` is the only code that writes autonomous instructions to `agent_instructions`. A second hook at agent delivery (`hold_back_autonomous`, next to `agent_capabilities.hold_back` in both poll endpoints) refuses any instruction stamped `autonomy.actionId` when the stop switch is on or its ledger row is no longer `approved`/`auto`.
**When:** always; the delivery hook is what makes "one switch stops everything" true for instructions already queued but not yet delivered.
**Trade-offs:** adds a ledger lookup per delivered autonomous instruction (cheap, indexed, and only for stamped instructions). Human-initiated instructions are untouched.

Decision order (first match wins, each step recorded in the row's `trace`):

```python
async def decide(req: ActionRequest) -> Decision:
    if await settings.platform_stopped():            return deny("kill_switch_platform")
    cfg = await settings.for_tenant(req.tenant_id)   # error -> level "suggest"
    if not cfg.eligible:                             return deny("not_enabled")   # screen ticked
    if cfg.stopped:                                  return deny("kill_switch_tenant")
    if cfg.level == "off":                           return deny("level_off")
    spec = registry.ACTIONS.get(req.action)
    if spec is None:                                 return deny("unregistered_action")  # fail closed
    if cfg.level == "suggest":                       return propose("level_suggest")
    if spec.approval == "approve" or req.playbook_destructive:   # YAML can only raise
        return needs_approval("destructive")
    if await blast.exceeds(cfg, req):                return needs_approval("blast_radius")
    if await cooldown.active(req, spec):             return needs_approval("restart_budget")  # or defer
    if await ledger.suppressed(req.dedupe_key):      return deny("undone_by_operator")
    return allow_auto()
```

### Pattern 2: Action registry owned by code, class and undo are independent

**What:** `registry.ACTIONS` maps each `ACTION_MAP` action to `{approval: auto|approve, undo: <inverse action or None>, blast_unit: host|tenant, cooldown}`. The classification follows the locked decision, with reversibility recorded separately (isolate host is reversible but still needs approval).

| Action | Approval | Undo | Notes |
|--------|----------|------|-------|
| `block_ip` | auto | `unblock_ip` | per-host firewall rule via agent |
| `quarantine_file` | auto | `unquarantine_file` | new agent instruction |
| `restart_service` | auto | none | nothing to revert; Activity shows no undo button; restart budget (e.g. 3 per service per hour, then escalate) |
| `enable_service` | auto | `disable_service` | inverse of the undo |
| `install_patches` (ring) | auto | `rollback_patches` | inside the tenant maintenance window only |
| `rollback_patches` (system-initiated on failed health) | auto | none | compensating action |
| `isolate_host` | approve | `restore_host` | reversible, still destructive |
| `kill_process` | approve | none | irreversible |
| `reboot_host` (patch reboot) | approve | none | new agent instruction |
| `disable_service`, `restore_file`, `rotate_key` | approve | inverse where one exists | conservative; DECISION: revisit `disable_service` |
| `ticket_comment`, `ticket_escalate` | auto | none | service desk |
| `ticket_resolve` | approve (or requester confirm) | reopen | never auto-closes on the model's say-so |

**Why code:** `remediation_playbooks` is operator-editable (`remediation_playbook_endpoints.py`); a tenant must never be able to lower a class by editing a playbook.

### Pattern 3: Ledger state machine plus hash-chained audit, not a fourth audit store

**What:** `autonomy_actions` is operational state (mutable `state`), `audit_ledger.event()` is the immutable record, `remediation_audit` stays as the engine already writes it. Each ledger transition calls `audit_ledger.event(action="autonomous_ops.<state>", tenant_id, actor=..., catalogue="autonomousOps", resourceId=actionId, ...)`. The Activity view reads `autonomy_actions`.

States: `proposed → awaiting_approval | approved → dispatching → executed → verified | failed | rolled_back | undone`, plus `shadow` (would-have-run), `denied`, `expired`, `cancelled_by_stop`.

Row shape (illustrative):

```json
{"id": "...", "tenantId": "t1", "kind": "security|patch|selfheal|servicedesk",
 "action": "block_ip", "targets": ["agent-123"], "origin": "autonomy|operator|watchdog",
 "state": "executed", "level": "undoable_auto",
 "reason": {"ruleId": "block_ip_on_malicious_ip_verdict", "inputs": {"findingId": "...", "verdict": "Malicious"}},
 "reasonText": "Rule block_ip_on_malicious_ip_verdict matched ...",      // deterministic template
 "summary": {"text": "...", "generatedBy": "llm"},                         // optional, decoration only
 "trace": [{"check": "kill_switch", "result": "pass"}, "..."],
 "dedupeKey": "t1|block_ip|203.0.113.7",
 "instructionIds": ["AUTO-..."], "remediationId": "REM-...", "rolloutId": null,
 "undo": {"available": true, "action": "unblock_ip", "params": {"ip_address": "203.0.113.7"},
          "undoneAt": null, "undoneBy": null, "undoActionId": null},
 "approval": {"requiredBy": "destructive", "approver": null, "expiresAt": "..."},
 "createdAt": "...", "updatedAt": "..."}
```

Unique partial index on `(tenantId, dedupeKey)` for non-terminal states stops the 5-minute sweep from re-proposing the same open finding forever (`remediate()` has no finding-level dedupe of its own, and `scan_for_remediable_findings` returns the same open findings every cycle).

### Pattern 4: Undo is a new gated action, never a mutation

**What:** `undo(actionId, user)` creates a child action (`undoOf=actionId`) from the registry inverse and sends it through `decide()`; a human click counts as the approval, so it works while the tenant is stopped or at level Off. On success the parent gets `state=undone` and a **suppression** `(tenantId, dedupeKey)` for 24 h (configurable) so the next sweep does not re-apply the action the operator just reverted.
**When:** every action whose registry `undo` is set. The existing playbook `rollback:` lists (`block_ip.yaml`, `disable_service.yaml`, `rotate_key.yaml`) are the proven inverses and are reused as the source for registry inverses. Failed verification still triggers the engine's own rollback (`_dispatch_and_verify`), recorded as `rolled_back`.

### Pattern 5: Dispatch and verify as resumable states, not inline polling

**What:** today `_dispatch_and_verify` polls the agent for up to 60 s per step, then up to 60 s to verify, inline in the sweep coroutine; state lives in the coroutine. Self-healing restarts the backend, so an in-flight action would be orphaned in `dispatching`. The reconciler tick (15-30 s, under a distributed lock like `scheduler.py`) advances rows by reading `agent_instructions.status` (`SUCCESS`/`FAILURE`, set by `agent_tasks_endpoints.report_instruction_result`) and the existing `_verify_*` functions, and expires stuck rows. `remediate()` returns after queuing; the sweep never blocks on one tenant's agent.

### Pattern 6: Host watchdog is a separate, tiny, second enforcement point

**What:** the in-process gate cannot govern a process that restarts the process. `omni-watchdog` is a systemd **timer plus oneshot** (cannot hang silently the way a daemon can), stdlib Python, running as root with a **root-owned allowlist** (`/etc/omni-watchdog/watchdog.conf`: `omni-backend`, `mongod`, `ollama`, restart budget, thresholds, webhook URL). A compromised backend (running as `azureuser`) cannot widen what the watchdog will restart. The gate and the watchdog share one rule: the platform stop. The watchdog reads the stop from Mongo when reachable (`system_settings` doc `type: "autonomous_ops"`), caches the last value in `/var/lib/omni-watchdog/state.json`, and also honours a manual `/etc/omni-watchdog/STOP` file. Stopped means observe-and-alert only.

Watchdog behaviours:
- Backend: `GET /api/health` (static liveness, `app.py:105`) and `/api/health/ready` (pings Mongo, 503 on failure). Three consecutive failures or timeouts restarts `omni-backend`. When systemd has given up (`StartLimitBurst=10` in `omni-backend.service`), `reset-failed` then start.
- MongoDB: unit state plus TCP 27017; restart `mongod`, then backend if needed (the 2026-10-14 kernel-7.0 `mongod` failure and its `GLIBC_TUNABLES` drop-in is the motivating case).
- Ollama: probe `127.0.0.1:11434/api/tags`; the unit is **not installed** on this VM (`ollama.service not-found`), so "unit missing" is reported once as informational, never as a failure loop.
- Disk and TLS certificate (`/etc/nginx/ssl/omni.crt`): **warn only**. Agents pin that cert (agent TLS pin, commit 3b1abad01), so never auto-rotate.
- Restart storm guard: at most N restarts per unit per window, then stop trying and page.
- Out-of-band alerting: webhook POST from the watchdog itself (the backend and Mongo may be the thing that is down), journald as the floor.
- Dead-man switch: the watchdog touches `/var/lib/omni-watchdog/heartbeat` and writes a Mongo doc each run; the backend selfheal sweep alerts if the heartbeat is older than ~5 minutes.
- Reporting: events to `logs/watchdog-events.ndjson` (and Mongo when up); the backend ingest sweep mirrors them into `autonomy_actions` (`origin: watchdog`, `kind: selfheal`) and `audit_ledger.event`, reusing the NDJSON-spool-and-replay idiom from `audit_ledger.replay_spool`.

### Pattern 7: Rules decide, the LLM decorates

**What:** `reasonText` and the registry-driven `trace` are deterministic and written at decision time. `summarizer.py` may add `summary.text` asynchronously (queue, concurrency 1, short timeout, skipped when Ollama is down or backlog is deep; 2 vCPU/7 GB/no GPU). An AST test fails the build if any module in `autonomous_ops/` other than `summarizer.py` (and the service-desk answer function) imports `ai_service`, `ai_orchestration`, `agentic_service`, `langchain*`, or touches `agent_instructions` directly outside `gate.py`. Service desk answers are text for a human requester: no tools are given to the model, retrieval is tenant-scoped (`rag_service.query(query_text, n_results, tenant_id)`), and the escalate-or-answer choice is a rule (retrieval score threshold, at least one citation, category allowlist, not security-tagged, not critical priority, requester-confirm to close). Ticket text is untrusted input.

## Data Flow

### Security response (the headline path)

```
security_response sweep (per tenant, distributed lock, tenant scope set AND reset per tenant)
  → AutonomousRemediationService.scan_for_remediable_findings(tenant)   # keep native types only:
      nscan (malicious verdict), vuln (source=agent), fim (Changed)    # skip vulnerability/cspm/alert/compliance
  → select_playbook(finding)                                           # deterministic, remediation_playbook_service.py
  → ActionRequest(targets=[finding.agent_id], reason={ruleId, inputs}, dedupeKey)
  → gate.decide()
        ALLOW_AUTO      → ledger.executed path → _dispatch_step → execute_plan → agent_instructions (stamped)
        NEEDS_APPROVAL  → state awaiting_approval, notify (notification_service + in-app feed + websocket)
        PROPOSE         → same, labelled suggestion (level Suggest)
        DENY            → counted, not logged per finding (one rolled-up "suppressed" counter per sweep)
  → agent executes → report_instruction_result → reconciler verifies (_verify_vuln/_fim/_nscan) → verified | failed(rollback|escalate)
Approve click → POST /api/autonomous-ops/actions/{id}/approve → gate.approve() re-runs the volatile checks
                (stop switch, finding still open, agent still enrolled) → AutonomousRemediationService.approve_remediation()
```

`AUTONOMOUS_REMEDIATION_DRY_RUN` keeps its meaning as the **deployment-level shadow switch** and stays default `true`: the gate records `shadow` rows (what it would have done) and dispatches nothing. That makes shipping inert, lets the user watch proposals in the Activity view first, and reconciles the per-tenant default "Undoable-auto" with "applying on the live VM is the user's step" (flip the env var, restart the backend). The old severity ceiling `MAX_AUTO_SEVERITY` must not be applied to the deterministic types (it never was); a malicious IP is `critical` and should be blocked, not parked.

### Staged patching

```
Rollout created (human, or from the CVE→patch route):  patch_rollouts{id, tenantId, patchIds, rings[], policy}
  rings[i] = {name, selector (asset group / tag / percentage), agentIds[], jobId, state, soakMinutes, healthResult}
patch_rollout sweep (60 s, locked):
  ring i queued → gate.decide(install_patches, targets=ring agents, window=tenant maintenance window)
       → new_patch_job(...) + patch_instruction(...)  [reused unchanged from patch_core_endpoints] + rolloutId/ringIndex
       → job reaches Completed / Partially / Failed via record_agent_patch_result  (nudge hook; sweep is authoritative)
  ring installed → [reboot_required? → reboot_host action awaiting approval, ONE click for the ring, size capped]
  soak → health gate (rules): every ring agent heartbeating after install (agents.lastSeen),
         failed-patch ratio under threshold, no new service-down alert on those hosts
  pass → release ring i+1        fail → halt rollout, create rollback job from the extracted
                                   rollback service function, mark ring rolled_back, page the tenant
Stop switch → rollout halted_by_stop (no automatic rollback; a human decides)
```

Two integration facts: patches are already installed per job through `patch_core_endpoints.create_deployment_job`/`new_patch_job`/`patch_instruction`, and scheduled release already exists in `scheduler.process_scheduled_deployments` (flips `scheduled` instructions to `pending`). Rings reuse both; they do not add a second patch dispatcher. The `playbooks/patch_package.yaml` path (`upgrade_software` via software management, no rollback) must be re-pointed so a CVE finding opens a ring proposal rather than a direct `upgrade_software`.

### Platform self-healing and retention

```
omni-watchdog (host) ──events──▶ ndjson + Mongo ──ingest sweep──▶ autonomy_actions + audit_ledger
selfheal sweep (backend, 60-300 s): watchdog heartbeat age, audit spool backlog (audit_ledger.spool_path),
   stuck awaiting_approval rows (expire + re-notify), reconciler lag, retention last-run age
retention_job (daily, distributed lock): RetentionService methods EXCEPT cleanup_audit_logs,
   per-tenant policies, records retention_runs (existing collection) so /api/retention/stats can show next run
```

Retention fact that shapes the job: `agent_telemetry_retention_loop` already purges four telemetry collections daily. What is manual is `POST /api/retention/run` → `RetentionService.run_cleanup`, which also deletes `audit_logs` older than 90 days by timestamp. Scheduling that as-is would bypass `audit_ledger.purge_expired` (365-day per-tenant retention with chain checkpoints), leave gaps that `audit_ledger.verify` reports as broken links, and, run from a platform-admin sweep, delete across tenants. The scheduled job must skip audit logs and run as per-tenant scoped calls.

### Service desk

```
service_desk sweep (60 s): tickets with no aiFirstLine marker, status open, tenant eligible
  → rag_service.query(ticket text, tenant_id)   # tenant-scoped retrieval, no tools to the model
  → rules: score ≥ T, ≥1 citation, category in allowlist, not security/critical  → ANSWER else ESCALATE
  → ANSWER: gate (ticket_comment, auto at Undoable-auto; draft-as-internal-note at Suggest)
            tickets_service.add_comment(ticket_id, author="AI Assistant", text, tenant_id)
            asks requester to confirm; auto-resolve only on confirm (rule), reopen on reply
  → ESCALATE: tickets_service.update_ticket(assignee/priority via existing auto_assign + tickets_escalation_service)
  → LLM unavailable (Ollama inactive today): escalate immediately; never queue forever
```

The seeded knowledge base (`knowledge_endpoints.py:_SEED_DOCS`) is security content only. First-line help-desk answers need tenant or platform help-desk articles; without them the rule escalates almost everything, which is the correct failure mode.

### Key Data Flows

1. **Approval request:** gate → `autonomy_actions(awaiting_approval)` → `notification_service.send_notification` + `pending_agents._post_in_app` feed + `websocket_manager.broadcast_notification` → human click → `gate.approve`.
2. **Stop switch:** platform doc/tenant field flips → `settings` cache (≤5 s) → `decide()` denies; stop endpoint also marks pending/approved autonomous `agent_instructions` as `cancelled_by_stop`; delivery hook refuses stragglers; rollouts halt; watchdog goes observe-only on its next tick.
3. **Undo:** Activity button → child action → gate (human = approval) → inverse instruction → parent `undone` + suppression.

## Multi-tenant isolation and catalogue rules

- **Sweeps run as platform-admin and bypass the wrapper's auto-stamping**: `TenantIsolatedCollection.insert_one` only stamps `tenantId` when the context is a real tenant; under `platform-admin` it stamps nothing. Every sweep write must set `tenantId` explicitly (the Phase 59 warranty sweep shipped notifications without it, invisible to their tenant, and had to be fixed). Use one helper that sets the context per tenant **and resets it in `finally` per iteration**; the existing `autonomous_remediation_loop` overwrites its token each iteration and resets only the last one, which is the SEC-03 leak class that `tenant_context.py` warns about. `gate.decide()` takes `tenant_id` as an argument and never reads the ContextVar.
- **New collections stay wrapper-scoped.** Do not add any to `TENANT_ISOLATION_EXEMPT_COLLECTIONS`. Platform/host events use `tenantId: "platform-admin"`.
- **Eligibility is the existing purchase model.** The engine acts for a tenant only when the Super Admin has ticked the Autonomous Ops screen switch (new tenants start Overview-only, `tenant_features.START_FEATURES`). Within an eligible tenant the level defaults to Undoable-auto. A missing level means the default; a lookup **error** means Suggest (never auto on error), mirroring `agent_capabilities.allowed_for` fail-closed behaviour. DECISION: confirm "eligible = screen ticked".
- **Routes are registered in the catalogue manifest.** Add a `catalogues` entry to `shared/catalogue-access.json` (`view: autonomousOps`, group `automation`, `permission: view:autonomous_ops`, `write: [manage:autonomous_ops]`, `routes: ["/api/autonomous-ops"]`), a `screen:autonomousOps` entry to `shared/tenant-feature-switches.json`, a `MOUNTS` key `("autonomous_ops_endpoints", "router")` in the right `catalogue_mounts_*.py` slice (`catalogue_mounts_settings_ops.py` or `catalogue_mounts_secops.py`), and permissions in `rbac_defaults` (the vocabulary is derived from the manifest by `permission_vocabulary.py`). `test_catalogue_manifest`, `test_catalogue_route_parity` and the slice tests fail on drift. The platform-wide stop is a **platform-only** screen and route (`/api/platform/autonomous-ops`, platform-only permission added to `PLATFORM_ONLY_PERMISSIONS`), modelled on the HA/DR change (migration 023), because `platform_read` in `catalogue_guards.py` only lets platform staff through on safe methods and a stop is a POST.
- **Any agent-facing route must use `agent_tolerant`/`catalogue_exempt` deliberately**, not by accident; Autonomous Ops adds no new agent-facing routes, only the delivery hook inside existing ones.
- **Agent capability gating:** map every new instruction in `agent_capabilities._INSTRUCTIONS` (`restart_service`, `quarantine_file`, `unquarantine_file`, `restore_host` to `remediation_executor`/`autonomous_response`; `reboot_host` to `patch_installer`; `health_probe` to a catalogue capability), otherwise they bypass the per-tenant ticks.
- **Migration 024** only creates indexes (unique partial dedupe, `(tenantId, state, createdAt)`, `patch_rollouts`, `service_desk` marker). No default tenant data is written, so no per-tenant surprise at deploy (compare 022/023 which rewrote tenant lists).

## Scaling Considerations

Target is one 2 vCPU / 7 GB VM and tens of tenants, not scale-out.

| Concern | At current size | If it grows |
|---------|-----------------|-------------|
| Sweep cadence | security 60-300 s per tenant, ring controller 60 s, reconciler 15-30 s, service desk 60 s; cap actions per cycle (e.g. 10) | add per-tenant jitter; already lock-per-sweep via `distributed_lock.acquire_lock` so replicas are safe |
| Event loop blocking | no inline 60 s polls; Mongo-only work between awaits | none needed |
| Ollama | summaries queued, concurrency 1, optional | switch summarizer off by config |
| Ledger growth | one row per decision, no TTL (audit); purge by tenant retention in `audit_maintenance_loop` style, not a TTL index | archive after 365 d |
| Watchdog cost | one oneshot per 30-60 s, a few HTTP/TCP probes | n/a |

First bottleneck: per-agent concurrency leases (`MAX_CONCURRENT_PER_AGENT=2`, `remediation_inflight`) and the blast-radius cap, both of which intentionally defer rather than queue unboundedly.

## Anti-Patterns

### Anti-Pattern 1: Retrofitting the gate onto every `agent_instructions` writer

**What people do:** wrap or patch the 25 insert sites so "everything goes through policy".
**Why it's wrong:** human-initiated actions (a tech clicking Kill Process) are not autonomous and must not be throttled by the autonomy level; touching 25 files risks regressions in unrelated features.
**Do this instead:** make the gate the only door for **autonomous** origins, enforce it with an AST test over `autonomous_ops/`, and stamp instructions so the delivery hook can tell them apart.

### Anti-Pattern 2: Letting playbook YAML or tenant data set the approval class

**What people do:** keep `destructive: true/false` in YAML as the policy.
**Why it's wrong:** operators can edit it; the vendored files are also wrong for the locked decision (block IP flagged destructive).
**Do this instead:** registry in code; YAML flag may only escalate.

### Anti-Pattern 3: Reusing `propagate-antibody` or SOAR plugins for fan-out and isolate

**What people do:** reuse `swarm_service.propagate_antibody` (fans out to every online agent) or `soar_engine` `block_ip`/`network_isolate`.
**Why it's wrong:** they write `db.instructions`, which nothing reads (no agent and no endpoint polls it), through the raw handle, with no gate or blast radius.
**Do this instead:** dispatch to `agent_instructions` via `ACTION_MAP`, and copy only the *idea* of fan-out, bounded by the blast-radius cap.

### Anti-Pattern 4: A watchdog inside the backend, or one that can be reconfigured by the backend

**What people do:** an asyncio task that "restarts the backend" via `systemctl`, or a watchdog whose allowlist lives in Mongo.
**Why it's wrong:** it dies with the thing it heals and a compromised backend could widen its authority.
**Do this instead:** root-owned timer/oneshot, root-owned config, one-way event flow to the backend.

### Anti-Pattern 5: Running `RetentionService.run_cleanup` on a timer

See the retention fact above: audit chain breakage plus cross-tenant deletion.

### Anti-Pattern 6: LLM-generated scripts or tool choices anywhere reachable

`generate_plan` (`vulnerability`/`cspm`/`alert`/`compliance`) and `agentic_service` write instructions from model output. They stay unreachable from the new loop; consider deleting `run_cycle` once the new sweep ships.

## Integration Points

### Internal boundaries (file:function)

| Boundary | Change | Notes |
|----------|--------|-------|
| `autonomous_remediation_service.py:remediate()` (line ~548) | replace `is_destructive` branch with `gate.decide`; write ledger row; keep `write_audit` stages | `ueba_service.py:121` caller gets gated automatically |
| `autonomous_remediation_service.py:approve_remediation/deny_remediation` | called by `gate.approve/deny`; keep `remediation_control_endpoints.py` routes working | the Native Security console keeps its queue |
| `autonomous_remediation_service.py:_dispatch_and_verify` | split into queue step + reconciler verify; keep lease and rollback logic | resumable after restart |
| `autonomous_remediation_service.py:execute_plan` | only called by `gate.execute` for autonomous origins; adds `autonomy` stamp to the instruction | dedupe via `ResponseOrchestrator.is_duplicate_task` kept |
| `remediation_playbook_service.py:ACTION_MAP`, `select_playbook` | add actions; CVE route to ring proposal | `validate()` allowlist unchanged in spirit |
| `app_background_tasks.py:autonomous_remediation_loop` | replaced by `security_response` sweep; fix per-iteration tenant token reset | |
| `app_startup.py:run_startup_services` (~line 642) | register sweeps via `_safe_bg_task` | follow the `scheduler.py` lock idiom |
| `deployment_result_endpoints.py:get_agent_instructions` (line 66) and `agent_tasks_endpoints.py:get_agent_instructions` (line 31) | add `hold_back_autonomous` beside `agent_capabilities.hold_back` | the two agent poll paths |
| `deployment_result_endpoints.py:record_agent_patch_result` (line 186) | nudge ring controller when a ring job finalises | optional; sweep is authoritative |
| `patch_core_endpoints.py:rollback_patch_job` (line 253), `new_patch_job`, `patch_instruction` | extract rollback creation into a function the controller can call; add `rolloutId`, `ringIndex` | tenant scoping stays explicit |
| `scheduler.py:process_scheduled_deployments` | unchanged; rings may reuse scheduled release | |
| `agent_capabilities.py:_INSTRUCTIONS` | map all new instruction names | prevents capability bypass |
| `audit_ledger.py:event` | one call per ledger transition | never raises; spools on failure |
| `retention_service.py`, `retention_endpoints.py:get_stats` | job wrapper excluding audit logs; fill `next_scheduled` | `retention_runs` already exists |
| `tickets_service.add_comment/update_ticket`, `rag_service.query`, `tickets_escalation_service.py` | service desk reads/writes | `tickets_endpoints.create_ticket` is untouched; use a sweep, not an inline hook, so a crash loses nothing |
| `pending_agents.post_to_recipients`, `notification_service.send_notification` | in-app and rule-based notifications for approvals | email unset on this VM |
| `shared/*.json`, `catalogue_mounts_*.py`, `rbac_defaults.py` | see Multi-tenant section | drift tests enforce |
| `start-all-services.sh` | generates `omni-watchdog.service/.timer` like the existing units | installing is the user's step |
| Agents (`instructions.rs`, `remediation_actions.rs`, Python `autonomous_response.py` path) | new instruction handlers and tests | parity matrix first |

### External services

| Service | Integration | Notes |
|---------|-------------|-------|
| On-call channel | webhook from the watchdog (Slack/Teams/PagerDuty-style URL in root-owned config) | SMTP/Gemini/VirusTotal keys are unset on this VM; DECISION: which channel |
| Ollama | optional, summarizer and service-desk drafts only | unit not installed here; features degrade to templates/escalation |
| systemd | `systemctl restart/reset-failed` by root watchdog on an allowlist | applying units on the live VM is the user's step |

## Suggested Build Order

Dependencies drive the order: the gate, ledger and stop switch are prerequisites for every actor; the watchdog needs only the settings doc and ledger ingest; security response needs agent actions (long lead); rings need the gate, undo, blast radius and a reboot action; service desk needs only the gate.

| Phase | Name | Delivers | Depends on |
|-------|------|----------|------------|
| 81 | Policy, gate, ledger, stop switch, read-only Activity | `autonomous_ops` core, registry, settings (tenant + platform), `autonomy_actions`, audit mirror, reconciler skeleton, delivery hook, router + manifest/switch/permissions/mount, migration 024, AST import test, Activity list (read-only), shadow mode | none |
| 82 | Self-healing watchdog and scheduled retention | host watchdog + unit/timer generation, stop mirror, dead-man, disk/cert warnings, webhook on-call, watchdog-event ingest, app-level checks, retention job (audit excluded) | 81 (settings, ledger) |
| 83 | Security response | new sweep replaces the old loop, `remediate()` through the gate, new ACTION_MAP entries and playbooks, capability mapping, Rust + Python agent actions (restart, quarantine, isolate), approve/deny/undo, suppression, blast-radius cap, dedupe | 81; agent work can start during 81-82 |
| 84 | Staged patching | `patch_rollouts`, ring controller, health gate, halt + auto-rollback, extracted rollback function, `reboot_host` + `health_probe` agent actions, maintenance window, CVE→ring routing | 81, 83 (undo, blast radius, agent action pattern) |
| 85 | Service desk first line | sweep, retrieval, rules, comment/escalate/confirm-to-close, help-desk KB seeding, injection tests | 81 (can run parallel to 83-84) |
| 86 | Activity completion, hardening and live validation | undo buttons everywhere, filters, daily digest (LLM optional), approvals UX, E2E, kill-switch drills, flip shadow to live per tenant (user step) | 82-85 |

Why this order: self-healing second because it touches no agent binary, validates the ledger, stop switch and alert path end to end on low-risk actions, and protects the VM the rest runs on. Security response third because its agent actions are the longest lead and it establishes undo, dedupe and blast radius that rings reuse. Rings fourth because they are the most stateful and hardest to verify. Service desk is independent after 81.

## Sources

- `/home/azureuser/enterprise-omni-agent-ai-platform/.planning/PROJECT.md`, `.planning/codebase/ARCHITECTURE.md` (frontend-only; useless for backend), `CONVENTIONS.md` (frontend-only)
- `backend/autonomous_remediation_service.py`, `remediation_playbook_service.py`, `playbooks/*.yaml`, `remediation_audit_service.py`, `remediation_control_endpoints.py`, `native_security_ops_endpoints.py`, `ueba_service.py`
- `backend/app_background_tasks.py`, `app_startup.py`, `scheduler.py`, `distributed_lock.py`, `retention_service.py`, `retention_endpoints.py`, `audit_ledger.py`
- `backend/deployment_result_endpoints.py`, `agent_tasks_endpoints.py`, `agent_instruction_endpoints.py`, `patch_core_endpoints.py`, `agent_capabilities.py`, `swarm_service.py`, `soar_engine.py`
- `backend/catalogue_guards.py`, `catalogue_mounts*.py`, `permission_vocabulary.py`, `rbac_defaults.py`, `shared/catalogue-access.json`, `shared/tenant-feature-switches.json`, `shared/agent-capabilities.json`
- `backend/database.py`, `tenant_context.py`, `tickets_service.py`, `tickets_endpoints.py`, `knowledge_endpoints.py`, `ai_assistant_service.py`, `ai_orchestration/agents/chat.py`, `pending_agents.py`
- `agent-install/omni-agent-rs/src/instructions.rs`, `src/capabilities/patch_installer.rs`, `src/capabilities/remediation_actions.rs`; `agent/agent.py`, `agent/capabilities/autonomous_response.py`
- `/etc/systemd/system/omni-backend.service`, `omni-agent.service`, `omni-backup.timer`; `systemctl list-units` (Ollama not installed, mongod active)
- Project memory notes: kernel-7.0 mongod drop-in, agent TLS pin, tenant-sees-only-selected, optional integrations unconfigured

---
*Architecture research for: Autonomous Ops (v4.3)*
*Researched: 2026-10-25*
