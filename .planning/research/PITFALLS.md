# Pitfalls Research

**Domain:** Adding Autonomous Ops (autonomous security response, staged patching with halt/rollback, platform self-healing, AI first-line service desk) to an existing multi-tenant MSP security/compliance/ITAM platform (FastAPI + MongoDB + Rust agent, single 2 vCPU / 7 GB VM)
**Milestone:** v4.3 Autonomous Ops (phases start at 81)
**Researched:** 2026-10-25
**Confidence:** HIGH for findings tagged [CODE] (read directly from this repo on 2026-10-25); MEDIUM for [EXT] items (web search snippets and general SRE/LLM-security practice, not re-verified against primary sources)

Phase labels used below (map to roadmap numbers 81+ in whatever order the roadmapper picks):
**P-Core** = autonomy policy, global stop, single enqueue choke point, audit. **P-Sec** = security response. **P-Patch** = staged patching. **P-Heal** = self-healing. **P-Desk** = service desk. **P-UI** = activity view and undo.

The most important single finding: **the engine this milestone builds on is not yet safe to switch on.** The v3.4 engine has a safe `remediate()` path (playbooks, approval gate, lease, audit) that is called from only one place (UEBA). The scheduled loop calls a different, older path (`run_cycle`) that uses LLM-generated plans, ignores `requires_approval`, and is held back only by `AUTONOMOUS_REMEDIATION_DRY_RUN=true`. v4.3 must re-route and harden before anything is turned on (Pitfalls 1, 2, 3).

---

## Critical Pitfalls

### Pitfall 1: Flipping dry-run off activates the legacy LLM-in-the-loop path

**What goes wrong:**
`app_background_tasks.autonomous_remediation_loop` calls `run_cycle()`. `run_cycle` calls `generate_plan()` then `execute_plan()`. `generate_plan` pulls scripts from `RemediationService.generate_fix_proposal` (LLM-written script text) and tool choices from `agentic.run()` (LLM picks `tool_name`). `RemediationPlan.requires_approval` is computed but **never read** by `run_cycle` or `execute_plan`; `execute_plan` only checks the module-level `AUTONOMOUS_REMEDIATION_DRY_RUN` constant. The day someone sets the env var to `false` to "turn on autonomy", LLM-authored scripts run on endpoints with no approval, contradicting locked decision 3 (rules choose, LLM only suggests). The deterministic `remediate()` path is called only from `ueba_service._dispatch_anomaly_remediation`.

**Why it happens:**
Two generations of the engine coexist (pre-Phase-53 loop, Phase-53 playbook engine). The loop was never migrated because dry-run kept it harmless. [CODE]

**How to avoid:**
- In P-Core, make the loop call `remediate()` only; delete or hard-disable `generate_plan`/`execute_plan`/`verify_remediation` for `vulnerability`, `cspm`, `alert`, `compliance` types (move them to "suggest only": write a suggestion record, never an instruction).
- Replace the env-var dry-run with a DB-backed per-tenant autonomy level plus a global stop (Pitfall 19). Keep the env var only as an extra deny.
- Add a test: with autonomy=Undoable-auto and a finding of each type, assert that the only documents that can reach `agent_instructions` carry `source=playbook` and a `playbook` name from `ACTION_MAP`, and that no code path imports `agentic_service` or `ai_remediation_service` from the execution path.

**Warning signs:**
`agent_instructions` rows with `type=run_remediation_script` or `apply_cloud_remediation`; `source_service` of `agentic`/`ai_remediation` in `agent_ai_decisions`; any `script` field non-empty on an autonomous instruction.

**Phase to address:** P-Core (first plan of the milestone; before anything else is enabled).

---

### Pitfall 2: Many dispatch paths bypass the new policy layer

**What goes wrong:**
The autonomy level, blast-radius cap and audit are bolted onto `remediate()` while other code keeps enqueueing agent work directly. There are about 46 `agent_instructions`/`instructions` `insert_one`/`insert_many` sites across 27 backend files (agentic_service, soar_engine, swarm_service, swarm_endpoints, correlation_engine_threat, chaos_engineering_service, playbook_engine_actions, response_endpoints, patch_core_endpoints, ...). `swarm_service.propagate_antibody` is the clearest example: one request inserts `apply_block_rule` into the `instructions` collection (a different queue from `agent_instructions`) for up to 1000 online agents in the tenant, with no cap, no approval, no autonomy check, no audit, an unvalidated `indicator` (can be empty or a gateway IP), and `print()` for logging. [CODE]

**Why it happens:**
Features accreted over 80 phases; each wrote to the queue directly. A policy layer added at one call site feels complete in review.

**How to avoid:**
- P-Core introduces one function, `enqueue_agent_action(tenant_id, agent_id, action, params, actor, decision_id, risk_tier)`, which: checks the tenant's autonomy level and the global stop, enforces the blast cap, validates params (protected targets), writes the intent audit record, then inserts. 
- Migrate the autonomous-relevant callers (remediation engine, propagate-antibody, SOAR/agentic/response_orchestrator `_dispatch`, patch deployment) onto it. For human-initiated manual actions keep behaviour but still route through it with `actor=user` so they are audited and counted against the cap.
- Add a repo test (grep-style, like existing structural tests) that fails on any new direct `agent_instructions.insert_*` / `instructions.insert_*` outside the allowlist file.
- Decide explicitly: propagate-antibody becomes risk-tier "undoable" only with a validated indicator, per-decision cap, and an `unblock` pair; otherwise it is approval-gated.

**Warning signs:**
Audit entries missing for instructions that exist; `source: immune_system` instructions with no `decision_id`; an agent receiving block rules while its tenant is set to Off.

**Phase to address:** P-Core (choke point), P-Sec (migrate propagate-antibody, response_orchestrator, SOAR).

---

### Pitfall 3: "Destructive" vs "undoable" is not what the playbooks currently say

**What goes wrong:**
Locked decision 1 says block IP, quarantine file and restart service run on their own; isolate host, kill process and patch reboot wait for approval. The current playbooks disagree: `block_ip`, `disable_service`, `restore_file`, `rotate_key`, `kill_process` are all `destructive: true` (so they all park for approval, and approval fatigue starts on day one), while `patch_package` is `destructive: false` with `rollback: []`, so it auto-dispatches an upgrade that cannot be reverted. The Rust agent has no `restart_service`, `quarantine_file` or `isolate_host` instruction at all (only `kill_process`, `restore_file`, `block_ip`, `unblock_ip`, `disable_service`, `enable_service`, `rotate_key`, `rotate_key_rollback`, `upgrade_software`), so two of the three "undoable" examples cannot be executed today. A boolean `destructive` flag cannot express "runs alone, but must be undoable". [CODE]

**Why it happens:**
The v3.4 flag meant "needs an operator" not "irreversible". It was set conservatively and one non-reversible action was marked safe.

**How to avoid:**
- Replace the boolean with an explicit `risk_tier` per action (`undoable` | `approval_required`) plus an `undo_action` pairing, defined in `ACTION_MAP`, validated at load. `undoable` requires a registered undo verb that exists on the agent and a round-trip test (apply, verify state changed, undo, verify state restored) on both Linux and Windows.
- Add the missing agent verbs (restart_service, quarantine_file with a reversible restore, isolate_host with a management-channel carve-out) as agent work in P-Sec, and publish a new agent version; until a verb is on the fleet, the engine must treat it as unavailable and downgrade to Suggest (check agent version in the enqueue choke point).
- Re-tier `patch_package` as `approval_required` unless the patch class is proven reversible (Pitfall 9).

**Warning signs:**
A playbook step with `destructive: false` and empty `rollback`; `ACTION_MAP` containing an action with no agent handler; approval queue filled with `block_ip` requests.

**Phase to address:** P-Core (schema), P-Sec (agent verbs and tests).

---

### Pitfall 4: False-positive containment cascades (no idempotency, no real dedup, no brake)

**What goes wrong:**
(a) `scan_for_remediable_findings` re-reads every `Malicious` scan result, every open agent vuln and every `Changed` FIM event on each cycle (up to 100-200 each, no "already handled" marker). `remediation_id` embeds a timestamp, so every cycle creates a new request, a new approval, a new dispatch for the same finding. (b) The dedup that looks like protection is a no-op: `is_duplicate_task` queries `response_tasks`, but `remediate()` writes `remediation_requests`/`agent_instructions`, and the UEBA path calls `is_duplicate_task(action="remediate_anomaly")`, an action nothing ever writes. (c) A bad feed update (signed bundled feeds are updated in bulk) or a bad detection rule flips many hosts at once, and the engine acts on all of them in one cycle. (d) FIM "Changed" fires after every legitimate patch, so `restore_file` proposals revert patched binaries. [CODE]

**Why it happens:**
Dedup was written for the older `response_tasks` collection; the playbook engine was added later with its own collections. No component owns "have we already decided about this finding".

**How to avoid:**
- Idempotency key `(tenant, finding_type, finding_id, playbook)` stored as a unique-indexed `autonomy_decisions` document; a repeat finding updates `last_seen` and does nothing else; a cooldown (for example 24 h) after any non-success outcome before re-attempting.
- Blast-radius cap enforced at the choke point and counted from the DB, not memory: max N hosts per decision, max M autonomous actions per tenant per hour, per action class. Exceeding the cap does not queue silently; it flips that action class for that tenant to Suggest, writes an audit entry and sends one alert (a circuit breaker with explicit manual reset).
- Cascade guard: if more than X% of a tenant's online endpoints produce the same finding within a window, treat it as a detection problem (feed/rule), not an incident: stop acting, alert once.
- Suppress FIM `restore_file` for paths touched by a patch job in the preceding window (consume the patch job's expected-change list), and keep FIM restore approval-gated.
- A protected-target list (the platform's own IP/hostname, the agent's management channel, gateway/DNS, domain controllers, tenant-defined crown-jewel hosts) checked at enqueue.

**Warning signs:**
More than one `remediation_requests` row for the same `findingId`; pending-approval count growing linearly with time; actions per hour proportional to endpoint count; a spike right after a feed update or patch window.

**Phase to address:** P-Core (idempotency, cap, breaker), P-Sec (protected targets, cascade guard, FIM/patch interlock).

---

### Pitfall 5: Verification measures the wrong thing and triggers wrong rollbacks or perpetual escalation

**What goes wrong:**
`_check_nscan_resolved` re-scans the same target and reads its verdict. For a `block_ip` playbook the IP's verdict comes from the feed and does not change because a firewall rule was added, so the verdict stays `Malicious`, verification returns `failed`, and the engine **rolls back the block it just applied** (dispatches `unblock_ip`). For `kill_process` on a file path the file is still on disk and still Malicious, so verification says `failed`, there is no rollback, and an `ESC-` critical alert is inserted every time. Other finding types return `unverified` unconditionally. Rollback is dispatched without polling its result, and only on `failed` (never on `unverified` or `dispatch_incomplete`). [CODE]

**Why it happens:**
Verification was grounded in "is the finding still reported" which fits patches/FIM, not containment actions.

**How to avoid:**
- Verification is per action, defined in the playbook: `block_ip` verifies by an agent-side rule-present check (agent reports firewall state); `kill_process` verifies process absent; `restore_file` verifies hash equals baseline; `restart_service` verifies service active for N seconds. Add `verify:` blocks to the YAML schema and test each against the real agent response.
- Distinguish "action took effect" from "threat gone". Only the first gates rollback.
- Rollback steps must be polled and audited like forward steps; `unverified` after dispatch must hold the item for a human, never silently stay `dispatching`.
- Test: block a documentation IP (192.0.2.x) end to end and assert the audit trail ends in `verified`, not `rollback_dispatched`.

**Warning signs:**
Audit sequences `dispatched -> verified(failed) -> rollback_dispatched` for block_ip; many `ESC-` alerts; requests stuck in `dispatching`.

**Phase to address:** P-Sec.

---

### Pitfall 6: "Undo" that does not undo

**What goes wrong:**
- Linux `block_ip` uses `iptables -I INPUT -s ip -j DROP` (inserts a duplicate on every call) and `unblock_ip` uses `-D` (removes one copy). Block twice, undo once: the IP stays blocked while the UI says undone. Windows uses one rule name per IP, so a second block is a name collision and one delete removes the rule for both reasons.
- Two reasons to block the same IP (auto decision plus operator decision) share one rule; undoing the auto decision removes the operator's block.
- `enable_service` "undoes" `disable_service` by enabling and starting, even if the service was originally disabled or stopped, so undo changes the pre-state.
- `kill_process`, `restore_file`, `patch_package` have `rollback: []` and are irreversible; the Activity view must not show an undo button for them.
- Iptables rules are not persistent and `-I` rules are lost on reboot; the platform thinks a block exists that does not.
- Undo clicked days later, after other state changed. [CODE]

**How to avoid:**
- Capture pre-state before acting (service enabled/active, rule present, file hash) and restore to that state, not to a hard-coded one. Store it on the decision record.
- Make apply idempotent (check-then-add) and reference-counted per `(target, reason)`; a rule is removed only when its last reason is undone. Tag rules with the decision id (rule name or comment).
- Time-to-live on blocks and quarantines, enforced agent-side (agent removes the rule after TTL if no renewal), which also covers the control-channel risk (Pitfall 7).
- Undo is a first-class action through the same choke point, audited, and shows a precondition check ("rule still present; pre-state was X").
- Show irreversible actions as "approval required, cannot be undone".

**Warning signs:**
Undo succeeds but a firewall listing still shows the rule; duplicate iptables rules for one IP.

**Phase to address:** P-Sec (agent semantics), P-UI (undo surface).

---

### Pitfall 7: Containment severs the control channel (block the wrong IP, isolate the management path)

**What goes wrong:**
`block_ip` has no protected-address check (only `validate_ip` syntax). Dropping inbound packets from the backend address, DNS or the gateway also drops the replies to the agent's own outbound calls, so the agent can no longer poll for the `unblock_ip`. `isolate_host` (approval-gated) has the same failure at larger scale. A scan verdict on a shared IP (CDN, the VM's own cloud metadata address, a customer gateway) becomes a self-inflicted outage across a tenant. [CODE]

**How to avoid:**
- Enqueue-time protected list: platform backend host/IP, tenant's configured management ranges, link-local/metadata, loopback, and the tenant's gateway/DNS from agent telemetry. Agent-side hard refusal too (defence in depth), mirroring `kill_process` refusing its own PID.
- Dead-man's-switch: every network-affecting action carries an agent-side expiry; the agent reverts it if it has not heard from the backend within N minutes after applying (this is also the safe answer to "agent offline when undo is queued").
- `isolate_host` must keep an explicit allow rule to the platform and has approval + short TTL.
- Test: attempt to block the backend IP and a /8; assert refusal and an audit record.

**Warning signs:**
Agent goes Offline immediately after a block action; offline agents whose last instruction was a network action.

**Phase to address:** P-Sec.

---

### Pitfall 8: Approval fatigue and approval races

**What goes wrong:**
One approval click is the entire safety model for destructive actions, so its quality matters. Today: no expiry (an approval clicked three days later dispatches against a stale finding and an agent that has since changed); duplicates per cycle (Pitfall 4); `approve_remediation` does `find_one` then `update_one` without a status condition, so a double click or two admins dispatch the playbook twice (the lease only bounds concurrency to 2); the approver is not required to differ from anything; approvals have no context (what, why, which host, what will be undone). Above roughly a dozen pending items per day per operator people start clicking through. [CODE][EXT]

**How to avoid:**
- Approval is an atomic compare-and-set (`update_one({id, status: "pending_approval"}, {$set: {status: "dispatching"}})` and check `matched_count`), then re-validate the finding at approval time (still present, agent online, same agent version, not protected, tenant autonomy not Off).
- Expiry (for example 24 h) moves the item to `expired` (safe default is do nothing), with an audit record and a visible state.
- Group by incident (one approval card for "same finding across hosts"), show blast radius, evidence, exact action and undo availability, and cap pending per tenant (past the cap, new items become digest entries, not new cards).
- No "approve all" for destructive actions. Track approval metrics (time to decision, deny rate); a near-100% approve rate with sub-3-second decisions is a fatigue alarm.
- Approvals are a permission distinct from view (`approve:autonomous_actions`), role-checked per tenant.

**Warning signs:**
Median approval time under a few seconds; items with `status=dispatching` and two `override_approved` audit rows; pending queue older than expiry.

**Phase to address:** P-Core (state machine and atomicity), P-UI (cards, grouping, metrics).

---

### Pitfall 9: Patch "rollback" that is not a rollback

**What goes wrong:**
The agent's `upgrade_software` installs a package with `install_package(pkg, true)`; there is no recorded previous version, no snapshot, and the playbook states `rollback: []`. Windows cumulative updates and servicing-stack updates are generally not removable; Linux downgrades need the old version still available in the repo or cache and can break dependent packages; any action that needs a reboot is one-way once rebooted (and "patch reboot" is itself the approval-gated action). Calling the halt-and-revert behaviour "rollback" in code, UI and marketing sets an expectation the system cannot meet. [CODE][EXT]

**How to avoid:**
- Name two different things: **halt** (stop remaining stages, always possible) and **revert** (restore the previous version, only when proven). Each patch item records `reversible: true|false` and `previous_version` captured pre-install.
- Only mark Linux package patches reversible when the previous version is confirmed installable (agent checks `apt-cache policy`/`dnf history`/`zypper` before install); Windows updates default to non-reversible unless a tested `wusa /uninstall` or equivalent path exists for that KB class.
- Non-reversible patch classes require approval for the stage that includes more than the canary group, and the UI says "halts on failure; cannot be reverted".
- Test on throwaway VMs for each OS family: install, health-fail, revert, confirm version restored; document the matrix of what is and is not reversible. This is a research flag (see summary).

**Warning signs:**
Rollout record says `rolled_back` while agent inventory still shows the new version; `rollback` arrays that are empty or only enable/disable.

**Phase to address:** P-Patch.

---

### Pitfall 10: Health checks read stale signals (agent status, pending list, vuln status)

**What goes wrong:**
- `monitor_agent_status` is documented as "mark Offline if inactive > 5 min" but the loop sleeps 30 s at the top and `3600` s at the bottom: after the first pass it runs hourly, so a host that died after a patch stays `Online` for up to about an hour. A staged rollout that uses "agent still Online" as its health check will never halt on a bricked host. 
- The patch pending list was already observed stale for up to an hour after install (hourly agent scan); fixed for display, but a stage gate that reads inventory repeats the problem. 
- `_verify_vuln_resolved` waits for the next ingest cycle, up to its 60 s timeout, then returns `failed`/`unverified` for a patch that did succeed. [CODE]

**How to avoid:**
- Fix `monitor_agent_status` cadence first (check every 30-60 s; keep the 5 min threshold) and add a test with a frozen clock.
- A stage's health gate is a composite, evaluated after a soak longer than the agent rescan interval: (1) the instruction result from the agent (`SUCCESS`/`FAILURE`), (2) post-install forced rescan or inventory update received after the install timestamp, (3) heartbeat received after reboot with a new boot id, (4) agent version and services expected-running match, (5) optional tenant-defined check. Missing evidence is `unknown`, which halts, never passes.
- Use event time (agent-reported timestamps), not backend receipt time, when comparing before and after.

**Warning signs:**
Rollouts that never halt in testing even with an agent deliberately killed; stage advances within seconds of install.

**Phase to address:** P-Patch (gate), P-Heal (agent status cadence; do this fix early, others depend on it).

---

### Pitfall 11: The patcher patches the platform itself, and the orchestrator is not resumable

**What goes wrong:**
The VM runs a local agent enrolled to this platform. A tenant rollout whose target set includes that agent can reboot the host running backend, MongoDB and the orchestrating loop in the middle of a stage; in-process loops (the engine is `asyncio` tasks inside the backend) die, and nothing resumes a half-finished stage. The same applies to any restart of the backend (self-heal, deploy, OOM): in-flight `remediation_requests` stay `dispatching` forever, and `remediation_inflight` leases hold until their 300 s TTL. [CODE]

**How to avoid:**
- Exclude the platform host's agent from autonomous patching and self-heal actions (explicit `platform_host` flag, enforced at the choke point); patch it manually.
- Persist the rollout state machine (`rollouts`, `rollout_stages`, per-host status, deadlines) in Mongo; make every transition idempotent and the driver loop stateless so it resumes after a restart; on startup, reconcile `dispatching`/`in_progress` records older than their deadline to `unknown -> halted` with an audit entry.
- Chaos test: kill the backend mid-stage in a test environment and assert the rollout halts or resumes with no duplicate dispatch.

**Warning signs:**
Rollout or remediation records stuck in a non-terminal state across a backend restart.

**Phase to address:** P-Patch, P-Core (crash recovery for remediation requests).

---

### Pitfall 12: Staging mechanics that look right and fail on real tenants

**What goes wrong:**
Percentage stages produce zero hosts for small tenants (10% of 3 is 0) or put the only server in the canary; canary hosts are all the same OS/role so a role-specific failure is missed; schedules ignore tenant time zone and maintenance windows; two schedules (patch rollout and the older `software_deployment_jobs` scheduler) target one host simultaneously; an instruction queued for an offline agent is delivered days later (no expiry) and installs a patch outside the window or after a halt; a halted rollout's queued instructions still go out. `simulate_software_deployment` also auto-completes jobs with "[Demo]" status when no agents were dispatched, a false-success pattern to avoid copying. [CODE]

**How to avoid:**
- Stage sizing: at least 1 host, at most a cap, `ceil`, canary chosen to cover each OS family/role present; tenants with fewer than N endpoints use manual stages.
- Per-tenant window and time zone; a rollout starting outside the window waits; a window closing mid-stage pauses.
- Every autonomous instruction carries `expires_at`; the agent drops expired instructions; halt cancels all queued, undelivered instructions for that rollout.
- One active rollout per host (unique index on host-in-active-rollout).
- Never auto-complete a job with no evidence; zero targets is `failed: no_targets`, not success.

**Warning signs:**
`pending` instructions older than the window; hosts patched outside window; rollouts with `targets: 0` marked complete.

**Phase to address:** P-Patch.

---

### Pitfall 13: The watchdog cannot see its own host dying

**What goes wrong:**
The natural implementation is another `asyncio` loop inside the backend ("check Mongo, check Ollama, restart on failure"). If the backend, the VM, or MongoDB dies, the watchdog dies or goes blind with it: it cannot record the incident (audit needs Mongo), cannot restart itself, and cannot notify. Past evidence: after the kernel 7.0 reboot `mongod` failed to start (SERVER-121912) and the platform was down until a human added a drop-in. Alert delivery is also unproven here: SMTP, Gemini and VirusTotal keys are unset on this VM, so "alert the on-call person" may have no working channel. [CODE][memory]

**How to avoid:**
- Two layers. **In-app checks** (Mongo ping latency, Ollama reachable, cert expiry, disk %, job freshness, agent-offline ratio) run in the backend and report. **Out-of-app supervision** runs outside the process: systemd `Restart=on-failure` with `StartLimitBurst/StartLimitIntervalSec`, optionally `WatchdogSec` + `sd_notify`, a small systemd timer unit that curls `/health` and, on failure, writes to the journal and calls an external alert, and an `OnFailure=` unit. Ship these as unit files and an install note in the repo; **installing them on the live VM is the user's step** (locked), so the plan must produce artifacts and a verification checklist, not apply them.
- Dead-man's switch: the backend pings an external heartbeat (webhook/email/another host) every minute; the silence itself is what alerts the on-call person. This is the only way to detect "the whole box is gone".
- Alert channel health is itself a check: the on-call test message is sent on a schedule and failure is shown in the UI. If no channel is configured, the Self-healing screen says so loudly instead of implying coverage.
- Test: stop mongod in a test environment and assert an alert is delivered and the incident is recorded after Mongo returns (spool locally, replay; reuse the `audit_ledger` spool pattern).

**Warning signs:**
Incident timeline with a gap exactly when the platform was down; "all green" while the VM is unreachable; on-call alert test never run.

**Phase to address:** P-Heal.

---

### Pitfall 14: Restart loops and flapping

**What goes wrong:**
Restarting is only a cure for transient faults. Environmental causes (the kernel 7 `mongod` startup failure, OOM on a 7 GB box shared by backend + MongoDB + optional Ollama, a bad config after a deploy, port already in use) turn "restart on failure" into a tight loop that burns CPU, floods logs and alerts, and can corrupt state (repeated unclean `mongod` kills, WiredTiger recovery on every start). Other traps: restarting a service that is **intentionally** off (Ollama is "inactive on this VM") and alerting forever; a restart that kills in-flight remediation and patch state (Pitfall 11); a self-heal check with no hysteresis flapping on a single slow health probe under CPU contention on 2 vCPUs. [CODE][memory]

**How to avoid:**
- Expected-state registry: each watched unit has `expected: running|optional|off`; `optional`/`off` never restarts and never alerts as failure (show "not running (expected)").
- Restart budget with backoff: at most 3 restarts per unit per hour with exponential backoff (for example 10 s, 60 s, 5 min); after the budget is spent, stop restarting, mark `needs_human`, page once, and keep the incident open. Hysteresis: trip after K consecutive failed probes (K >= 3, probe timeout longer than worst-case GC/CPU stall), clear after M consecutive successes.
- Capture evidence before restarting (last 100 journal lines, memory, disk) into the incident record; a restart without evidence destroys the diagnosis.
- Check root-cause guards first: free disk and memory before restarting Mongo; do not restart `mongod` if the previous start failed within the last minute (go straight to human).
- Test: a unit that fails on start must produce exactly budget-many restart attempts then one page, not an unbounded series.

**Warning signs:**
More than a handful of restart events per unit per day; identical incident titles repeating; `mongod` start-time errors in journal.

**Phase to address:** P-Heal.

---

### Pitfall 15: Self-heal needs privilege, and the app grows root

**What goes wrong:**
To restart `omni-backend`, `mongod` or `ollama` the process needs `systemctl` rights. Typical shortcuts: run the backend as root, add broad `NOPASSWD: ALL` sudoers, or let the app write unit files/sudoers. Combined with ticket text and agent-supplied data flowing through the backend, that turns any injection or SSRF into host takeover. Memory also records that secrets and live-service restarts are the operator's job, and that `run-on-ubuntu.sh` once caused an SSH lockout through ufw. [memory]

**How to avoid:**
- The application never edits sudoers, unit files or firewall rules. Provide a fixed, reviewed sudoers drop-in or polkit rule scoped to exactly `systemctl restart|status <unit>` for an allowlist of units, plus a one-line install instruction for the operator.
- The restart helper takes a unit name only from a hard-coded allowlist (never from DB/user input) and uses `subprocess` with an argument list, no shell.
- Self-heal never touches networking/firewall/ssh on the host.
- Tests: allowlist rejects any other unit name; helper refuses shell metacharacters.

**Warning signs:**
Backend unit with `User=root`; sudoers with wildcards; restart commands built via string formatting.

**Phase to address:** P-Heal.

---

### Pitfall 16: Disk "self-healing" and the retention job destroy evidence or stall the box

**What goes wrong:**
- Retention exists as a manual job today; scheduling it daily is easy, but `retention_service.cleanup_audit_logs` deletes `audit_logs` older than 90 days platform-wide with a string timestamp compare, while `audit_ledger` keeps a per-tenant hash chain with 365-day retention and a checkpoint. Deleting ledger rows outside `audit_ledger.purge_expired` breaks chain verification and the "everything audited" promise. The Autonomous Ops decision log and the remediation audit must not fall under shorter retention than the compliance evidence it justifies.
- A first scheduled run against years of un-pruned telemetry (Rust heartbeats are about 290 KB raw per beat; about 815 MB/day/endpoint measured earlier; several agent collections had no TTL) issues enormous `delete_many` calls on a 2 vCPU Mongo, stalling the API and filling the oplog/journal, so the disk warning "fix" causes the outage it was meant to prevent.
- "Disk > 90%" auto-remediation that deletes data under pressure picks the wrong data; and Mongo needs headroom to delete/compact.
- The job's lock (`distributed_lock`, 300 s TTL, no renewal) expires while the sweep is still running, so a second instance starts (Pitfall 17). [CODE]

**How to avoid:**
- Self-heal for disk is **warn early, act only through the same bounded retention job**, never ad-hoc deletes. Thresholds (for example warn 75%, urgent 85%, stop-ingest decision 92%) with hysteresis.
- Retention runs in bounded batches (delete by `_id` range, `limit` per pass, sleep between, stop on CPU/latency budget), reports counts, and supports a dry-run count that is shown to the operator before the first live run (first run is manual, then scheduled).
- Exclude audit/decision/approval collections from the generic retention; they are governed by the ledger's retention, with checkpointing. Retire or fence `cleanup_audit_logs` so it cannot touch the ledger collection.
- Tenant retention policy lower bound validated against compliance frameworks the tenant bought (do not let a 7-day policy delete SOC 2 evidence).
- Test: seed N documents, run retention in batches, assert API latency stays under budget and the hash chain still verifies.

**Warning signs:**
`audit_logs` count dropping with chain verification failures; Mongo slow-query log during the retention window; disk usage jumping up (oplog) during deletion.

**Phase to address:** P-Heal (job), P-Core (audit exclusion).

---

### Pitfall 17: Scheduler double-runs and overlapping cycles

**What goes wrong:**
The loops are `while True: ...; await asyncio.sleep(n)` coroutines started per process: `autonomous_remediation_loop`, escalation scheduler, telemetry retention, the license seat loop. Only some APScheduler jobs use `distributed_lock`. The lock helper has a fixed TTL and no renewal or fencing token on writes: a job that outlives its TTL (retention, rollout drivers, a remediation cycle with 60 s step polls and 30 s sleeps per finding) is run again by another worker while the first continues. A second uvicorn worker (or a manual restart overlap during deploy) doubles every loop. The autonomous loop is also serial across tenants and findings, so one slow tenant delays everyone and the real period drifts far beyond 300 s. The loop also sets the tenant context once per tenant but only resets the last token (leak across iterations). [CODE]

**How to avoid:**
- One scheduling mechanism for all v4.3 jobs with: job-run records (`job_runs`: name, tenant, started, heartbeat, status), a lock with TTL **and heartbeat renewal**, and a fencing token or compare-and-set on the state each run writes. A run that finds a live run for the same `(job, tenant)` skips and records `skipped_overlap`.
- Per-tenant isolation of runs (one tenant's slow cycle must not block others; bounded concurrency of 1-2 total on this VM).
- Reset tenant context in a `finally` per iteration.
- Test: start two instances of each job concurrently and assert one executes; assert a job exceeding its TTL does not get a second concurrent run (renewal works), and that a crashed holder's lock does expire.

**Warning signs:**
Duplicate audit rows with identical decision keys; two `job_runs` active for the same job; log lines from two PIDs for one loop.

**Phase to address:** P-Core (job framework), applied in P-Sec/P-Patch/P-Heal.

---

### Pitfall 18: Cross-tenant leakage in automated actions

**What goes wrong:**
Automation runs with no human request context, which removes the tenant guard that normal routes get. Local risks: `monitor_agent_status` and the escalation scheduler run under `set_tenant_id("platform-admin")` and read/update across tenants; `is_duplicate_task` runs its cross-agent dedup without a `tenantId` filter, so one tenant's recent action can suppress another tenant's response (and the check reads across tenants); `agent_id or "auto"` makes agent-less findings share one lease key across tenants; the loop leaks tenant context tokens; `propagate_antibody` sources its tenant from the caller but nothing stops a shared indicator list; the AI chat's `cross_tenant_output_scan` is substring based and **fails open** when its lookup errors; notifications and Activity views for platform-level self-healing events could show tenant names to the wrong audience. v4.1 and the DB wrapper auto-scope tenants for requests, but platform-admin contexts bypass that. [CODE][memory]

**How to avoid:**
- Every autonomous record carries `tenantId` set from the finding/agent, never from ambient context; the choke point asserts `agent.tenantId == tenant_id` and rejects otherwise.
- Platform-scope actions (self-heal of backend/Mongo/Ollama) are a separate scope: visible only to platform roles, never listed in tenant Activity views, and never mention tenants.
- Fix `is_duplicate_task` to always include tenant; add a lint/test that autonomous queries include `tenantId`.
- Per-tenant autonomy level is looked up **at action time** (not cached for hours, not read from the schedule creation time).
- Contract test with two tenants for every autonomous path: tenant A's findings, approvals, undo, Activity feed, service-desk answers, and on-call alerts never include or affect tenant B (extend the existing `test_e2e_integration` isolation style).
- Service desk: closed-over `tenant_id` retrieval (already the pattern), plus make the cross-tenant output scan fail closed for autonomous replies (escalate instead of sending).

**Warning signs:**
Instructions whose `tenant_id` differs from the target agent's tenant; Activity rows visible to a user from another tenant; the same lease document used by multiple tenants.

**Phase to address:** P-Core (invariants), every other phase (per-feature test).

---

### Pitfall 19: The global stop switch only stops new decisions

**What goes wrong:**
"One switch stops everything" is checked when a decision is made. But there are queued but undelivered instructions in `agent_instructions`, requests parked in `pending_approval` that could be approved after the switch, in-flight `_dispatch_and_verify` loops that continue to rollback steps, staged rollouts with future stages scheduled, and ticket auto-answers already generated and awaiting send. The existing off-switch is an env constant read at import (`AUTONOMOUS_REMEDIATION_DRY_RUN`), which needs a restart (restarts are the user's step), and the switch's own state lives in Mongo, so a Mongo outage leaves behaviour undefined. [CODE]

**How to avoid:**
- Switch is a DB document read per action through a short-TTL cache (seconds, not minutes), plus an in-process override flag set by an endpoint for the Mongo-down case.
- Stop semantics defined and tested: (1) no new autonomous decisions, (2) cancel all undelivered autonomous instructions (mark `cancelled_by_stop`), (3) pause rollouts at the next gate, (4) approvals on existing requests require re-checking the switch, (5) service desk stops sending AI answers and routes to humans, (6) running self-heal restarts finish but no new ones start. Document what does not stop (an action already executing on an agent) and show it.
- **Fail closed**: if the switch or autonomy level cannot be read, do nothing autonomous and say so in the Activity view.
- Resume is a separate, audited step; per-tenant Off applies the same rules for that tenant.

**Warning signs:**
Agent executes an action after the stop timestamp; the switch toggle takes effect only after a restart.

**Phase to address:** P-Core.

---

### Pitfall 20: Audit gaps

**What goes wrong:**
In `_dispatch_and_verify` the audit order is act, then write `dispatched`; a crash between leaves an executed action with no record. `write_audit` failures are not handled (and `asyncio.create_task(push_ocsf_event)` keeps no reference, so it can be garbage-collected). There are two audit stores with different guarantees: `remediation_audit` (append-only by convention, no hash chain, no retention policy, no tenant-scoped sequence) and `audit_ledger` (hash chain, spool, retention checkpoint). Decisions that did **not** result in action (rate-limited, deduped, protected target, tenant Off, Suggest mode) leave no record, so "why did nothing happen" is unanswerable; setting or changing autonomy level, the global switch, a playbook edit, and an approver's denial must themselves be audited. LLM summaries stored as if they were facts blur provenance. [CODE]

**How to avoid:**
- Write-ahead: an `intent` record (decision_id, rule id, inputs, risk tier, autonomy level in force, actor=`system:autonomous_ops`) is written **before** the enqueue; the enqueue fails if the intent write fails. Result and undo records reference `decision_id`. A reconciler marks intents without a result after the deadline as `unknown`.
- Route everything through `audit_ledger.record` (hash chain, spool) and keep `remediation_audit` as a derived view or migrate it; never two truths.
- Record suppressed and no-op decisions with a reason code (cheap, capped by rollup/TTL on the high-volume kind).
- Audit configuration changes: autonomy level, global stop, playbook/risk-tier edits, protected-list edits, approvals and denials, expiries.
- Keep LLM output in a separate field marked `generated_by: llm`, never as the reason of record (the rule id is the reason).
- Test: kill the process between enqueue and result (fault injection) and assert an intent exists and reconciles; verify the chain after a run.

**Warning signs:**
Instructions without a matching intent; a decision with only a `dispatched` row; chain verify failures; Activity view count differing from the instructions count.

**Phase to address:** P-Core (schema, write-ahead), P-UI (reason codes).

---

### Pitfall 21: Prompt injection through ticket text

**What goes wrong:**
Ticket bodies (typed by users, imported from email, or synced from Jira/ServiceNow via the existing bridge) are untrusted third-party text that reaches `llama3.2:3b`. The existing guardrail is seven literal English regexes ("ignore previous instructions", "you are now DAN", "execute code" ...) which any paraphrase, other language, or encoding bypasses, while its PII patterns reject normal tickets (any email address, and the phone pattern `\b\+?1?\d{9,15}\b` matches any 9-15 digit number such as serials and ticket ids), so legitimate tickets are blocked while attacks pass. Indirect injection arrives via the knowledge base if resolved tickets or user comments are fed back into it ("learning from tickets"), and via answers that render links or images (data exfiltration through markdown image URLs). A small 3B model is far easier to steer than a frontier model. [CODE][EXT: OWASP LLM01 guidance recommends least privilege, tiered tool access and marking untrusted content, and notes no filter is reliable]

**How to avoid:**
- Structural, not textual, defences: the service-desk assistant has **no tools with side effects** (retrieval over the tenant's published KB only; keep `search_evidence`-style tenant-closed tools); nothing parses LLM output into actions, status changes, or commands; the model cannot set ticket status, assignee, priority, or call the remediation engine.
- Untrusted text is delimited and labelled as data in the prompt; output is schema-constrained (answer, cited_article_ids, confidence-from-retrieval) and the sender code, not the model, composes the final message.
- Output sanitization: strip links, HTML, markdown images and anything not from the KB allowlist of domains; reject answers containing commands or URLs not present in the cited article.
- KB hygiene: only curated, human-approved articles are retrievable by the assistant; tickets never auto-promote into the KB.
- Replace the regex guard with: length caps, instruction-pattern heuristics as one signal only, and a hard rule that any ticket flagged or low-retrieval goes to a human.
- Red-team test set (paraphrased, multilingual, base64, "system:" role spoofing, hidden text in HTML email) run in CI against the real prompt; success criterion is "no action, no leak, escalates", not "model refuses".

**Warning signs:**
Answers that mention content not in any cited article; answers containing URLs; the assistant "following" instructions found in ticket text in manual tests.

**Phase to address:** P-Desk.

---

### Pitfall 22: An LLM hallucinating first-line answers (and the legal exposure)

**What goes wrong:**
A CPU-only 3B model produces fluent, confident wrong answers: invented admin steps, nonexistent menu items, wrong compliance or policy statements, security-weakening advice ("disable the firewall to test"). The platform is an MSP tool, so an answer is effectively the MSP's statement to its client. Companies are held responsible for what their chatbot says (Moffatt v. Air Canada, BC Civil Resolution Tribunal, 2024: the airline was liable for chatbot misinformation; tribunal-level, limited precedent value). Self-reported model confidence is not calibrated. With Ollama inactive on this VM and 10-60 s CPU latency per answer, naive implementations time out and either hang tickets or send nothing. Two-way ticket bridges can also loop: the AI comment syncs to Jira/ServiceNow, the webhook returns it as a new comment, and the assistant answers itself. [EXT][CODE]

**How to avoid:**
- Extractive-first design: answer only when retrieval returns an article above a similarity threshold, quote or closely paraphrase it, and cite article ids; the sender verifies every cited id exists and belongs to the tenant (reuse `ai_orchestration/validators.py` citation validation). No grounded article means escalate, never "best effort".
- Confidence comes from retrieval and validation outcomes, not from asking the model.
- Scope allowlist of categories the AI may answer (how-to, known issue, status); never security advice that reduces protection, never policy/compliance/pricing/legal statements, never account or access changes.
- The AI never closes a ticket: it posts "proposed answer" and the requester confirms ("did this solve it?"); a negative or no response escalates at the SLA step; the AI answers a ticket at most once (and at most twice including follow-up) to prevent ping-pong.
- Ignore comments authored by the AI (`author=system:ai`) and bridge-originated echoes of them; per-ticket and per-sender rate limits.
- Visibly label AI answers ("Automated answer from article X; reply to reach a person").
- Bound compute: queue with concurrency 1 on this VM, request timeout (for example 30-45 s), circuit breaker, and fallback to templated acknowledgement + escalation when Ollama is down or slow.
- Evaluation set including unanswerable and adversarial questions; release gate such as 100% escalation on out-of-KB questions and a measured wrong-answer rate on in-KB questions before default-on.

**Warning signs:**
Answers with no citations; sources not in the tenant's KB; a growing share of tickets reopened after AI answers; AI comments appearing as inbound webhook events.

**Phase to address:** P-Desk.

---

### Pitfall 23: Alert storms from three new event sources

**What goes wrong:**
Security response, patching and self-healing each emit notifications, and they interact: a patch reboot makes agents go Offline (one `agent.offline` notification **per agent**, as `monitor_agent_status` already does), FIM and anomaly detectors fire on new binaries, self-heal restarts something, and each stage failure notifies. A platform or network blip marks many agents offline at once. The legacy loop adds an `ESC-` alert and a failure ticket every cycle per unverified finding (`_create_failure_ticket`, `ESC-{remediation_id}`), and every audit write also pushes an OCSF event to subscribed SIEMs, so an incident floods external systems too. [CODE]

**How to avoid:**
- One notification pipeline for Autonomous Ops with dedup keys, grouping by incident, per-channel rate limits, severity-based routing, and quiet digest for info-level events; one open incident per `(scope, subject, class)`, updated rather than duplicated.
- Correlation rule: if more than X% of a tenant's agents (or any platform's agents) go offline within a short window, send one "possible platform/network problem" alert and suppress per-agent alerts; if the platform itself is the suspect (Pitfall 13), the dead-man's switch path is used.
- Maintenance windows: a patch rollout registers expected-offline/expected-change for its hosts (reboot window), suppressing offline alerts, FIM-restore proposals and anomaly escalations from the same hosts until the window closes plus grace.
- Cap and rollup what is pushed to SIEM (summary events for high-volume kinds).
- Test: simulate 200 agents offline and a 50-host patch reboot; assert alert count stays within a small bound.

**Warning signs:**
Notification volume correlating with endpoint count; identical titles repeating; on-call acknowledging in batches.

**Phase to address:** P-Heal (pipeline, correlation), P-Patch (maintenance windows), P-Core (rollup).

---

### Pitfall 24: Over-claiming autonomy

**What goes wrong:**
Copy, sidebar labels, release notes, demo scripts and sales material say "fully autonomous", "self-healing", "zero-touch", "AI-driven response", "undo anything", "ASI" or "Autopilot", while the product delivers rule-based automation with approval gates, partial reversibility, and an LLM that only summarises. Verification reports for this project show several `human_needed` live-environment checks; claiming them as done compounds this. Regulators treat exaggerated AI capability claims as deceptive under existing consumer-protection law (FTC "Operation AI Comply", 2024; the "AI washing" theme also appears in SEC actions), and an MSP that repeats the claim to its clients inherits the exposure. [EXT]

**How to avoid:**
- Product vocabulary decided once and enforced: "Autonomous Ops" (never "ASI", never "Autopilot"; the sidebar already has Windows Autopilot), "automatic within limits you set", "undo" only where an undo is registered, "needs your approval" for destructive actions, "AI summaries and suggestions" for LLM output.
- UI states what happened and what could not be undone; the autonomy-level control explains each level in one sentence including limits; every automated item shows the rule that triggered it.
- A claims checklist per phase: each user-visible promise maps to a passing test (for example "halts and rolls back" maps to the P-Patch revert matrix, and the copy says "halts; reverts where supported").
- A copy lint in CI that fails on banned terms in frontend strings and docs.
- Do not promise outcomes (prevents breach, guarantees patched) and do not show compliance-status effects from automated actions without evidence.

**Warning signs:**
Strings like "autopilot", "ASI", "fully automatic", "guaranteed", "zero-touch" in the UI or docs; features described that depend on live-only checks that are still `human_needed`.

**Phase to address:** P-UI (copy), every phase for claims checklist; final milestone gate.

---

### Pitfall 25: Default-on for existing tenants, and who may raise autonomy

**What goes wrong:**
Default is Undoable-auto (locked). On deploy every existing tenant silently starts having actions taken on its endpoints, unannounced to MSP clients whose contracts may not allow it, and before anyone has seen a single would-have-done decision. Related: who may set the level (a client tenant admin raising their own autonomy above what the MSP agreed; a viewer changing it); platform-level vs tenant-level policy; changes by API tokens; and tenants created via sign-up approval and "Overview only" feature gating, where autonomous features must follow the same per-tenant feature-switch rules (every sidebar item is switchable; new screens must be registered, and the new Autonomous Ops screens must be switchable and default correctly for sign-up tenants). [CODE][memory]

**How to avoid:**
- This does not reopen decision 1: new tenants get Undoable-auto, but the migration writes an **explicit** stored value for every existing tenant. Recommend a bounded "observe first" soak at rollout (global switch on Suggest platform-wide for the first days, recording would-have-acted decisions in the Activity view) and a release note; the user decides when to lift it.
- Permission: `manage:autonomy` (change level) and `approve:autonomous_actions` separate from view, super-admin able to cap a tenant's maximum level; every change audited with before/after.
- Register the new screens in the feature-switch catalogue and the tenant-sees-only-selected rules so a sign-up tenant does not receive them by default.
- Test: after migration every tenant document has an explicit level; a tenant admin without the permission gets 403.

**Warning signs:**
Tenants with no stored level; autonomous actions in a tenant whose admins have never opened the screen.

**Phase to address:** P-Core.

---

## Moderate Pitfalls

### Pitfall 26: Existing engine defects to fix before relying on it
**What goes wrong:** `_acquire_agent_lease` counts then inserts (check-then-act race at the cap); `scan_for_remediable_findings` queries policies inside the per-finding loop (N+1 on a 2 vCPU box, up to 200 findings times a policies query) and silently truncates at `to_list(200)`/`100`; severity ceiling is skipped for nscan/vuln/fim sections; `_finding_from_request_doc` approval replay uses stored finding details with no re-check; stale `_tctx` unbound in `finally` if `set_tenant_id` raises. [CODE]
**Prevention:** Atomic lease via unique index on `(agentId, slot)` or `findOneAndUpdate` counter; hoist policy load per cycle; paginate with a backlog counter surfaced in the UI ("N findings not yet processed"); apply the ceiling uniformly; add tests for each.
**Phase:** P-Core / P-Sec.

### Pitfall 27: Polling remediation steps inside the request/loop thread
**What goes wrong:** Step polling (60 s), verify polling (60 s) and a 30 s sleep run serially per finding inside the loop; a handful of findings stalls the cycle for many minutes and delays other tenants. UEBA runs `remediate()` in `BackgroundTasks` (up to about 120 s each) which can pile up with a flood of anomalies.
**Prevention:** Decouple: the engine writes a decision and returns; a bounded worker pool (2) advances decisions; completion is driven by the agent result callback, with a timeout sweeper, not a sleeping coroutine.
**Phase:** P-Core.

### Pitfall 28: Undo/approval over a stale or offline agent
**What goes wrong:** An undo or approved action queued for an agent that is offline executes whenever it returns, long after the context changed. 
**Prevention:** `expires_at` on every instruction; undo against an offline agent is "pending, will run when agent returns, expires in X" with the dead-man's-switch as backstop; show the real state in Activity.
**Phase:** P-Core, P-UI.

### Pitfall 29: Cert-expiry "healing" that breaks pinned agents
**What goes wrong:** The platform pins its TLS identity in agents (tenant-boundary hardening added agent TLS pinning). Any automated certificate renewal or replacement changes the leaf/key and can lock out the whole fleet at once; renewal also needs operator-controlled secrets. [memory]
**Prevention:** v4.3 scope is **warning only** (matches the milestone): warn at 30/14/7/3 days, include which certificates and whether agents pin them, include the operator procedure (pin rollover with overlap). Never auto-replace a cert.
**Phase:** P-Heal.

### Pitfall 30: Antivirus and EDR on the endpoint reacting to the agent's own remediation
**What goes wrong:** Capture PowerShell for remote desktop was quarantined by Microsoft Defender earlier; firewall commands (`netsh`, `iptables`), process termination, and service changes are classic EDR heuristics. Autonomous actions on an endpoint may be blocked, quarantined or flagged, producing false "failed verification" and false rollbacks. [memory]
**Prevention:** Prefer native API calls over shelling out where possible (as done for GDI capture); classify "blocked by local security product" as its own result, not `FAILURE`; do not auto-retry it; document required AV exclusions for operators; test on a real Windows endpoint with Defender on before enabling by default (live-only check, flag it).
**Phase:** P-Sec, P-Patch.

### Pitfall 31: Ollama as a shared-resource hazard
**What goes wrong:** On 2 vCPU / 7 GB with MongoDB and the backend, loading a 3B model (about 2-3 GB resident) for ticket answers or summaries starves Mongo and the API; model unload/reload cycles stall; concurrent answers queue up; self-heal restarts it under memory pressure (Pitfall 14).
**Prevention:** Single-flight queue (concurrency 1), `keep_alive` policy, a memory-headroom check before loading, request timeouts, and a degraded mode that bypasses the LLM entirely (templated summaries, escalation). All Autonomous Ops decisions must work with the LLM absent (they already must by decision 3); add a test that runs every flow with Ollama down.
**Phase:** P-Desk, P-Heal.

### Pitfall 32: SIEM/OCSF and webhook fan-out of autonomous events
**What goes wrong:** Every `write_audit` fires a fire-and-forget push; high-volume suppress/no-op audit records (Pitfall 20) would flood external SIEM endpoints and amplify any loop.
**Prevention:** Only push action-level events (intent, result, undo, approval); roll up suppressed ones; keep task references so pushes are not garbage-collected.
**Phase:** P-Core.

---

## Minor Pitfalls

### Pitfall 33: Activity view that cannot be trusted or loads slowly
**What goes wrong:** Querying large audit collections without compound indexes `(tenantId, ts)`; no pagination; polling instead of push; mixing LLM text with facts; showing an undo button for items whose undo preconditions are false.
**Prevention:** Indexes in the migration, cursor pagination, undo button computed from server-side `undoable_now`, "reason" shows the rule id and inputs.
**Phase:** P-UI.

### Pitfall 34: Clock and timestamp format inconsistency
**What goes wrong:** Mixed ISO strings, BSON dates and ObjectId-time (the repo already mixes them: `remediation_inflight.expiresAt` compared as ISO strings, retention uses ObjectId time); string comparisons across mixed formats silently mis-order or never expire.
**Prevention:** New collections use BSON Date only; add TTL indexes where expiry is the intent; one helper for "now".
**Phase:** P-Core.

### Pitfall 35: Tests that pass because Mongo and the agent are mocked
**What goes wrong:** Previous milestones closed with `human_needed` for live checks, and this milestone's risk is almost entirely in live behaviour (firewall state, reboots, systemd). Unit tests of `remediate()` with mocked `agent_instructions` cannot catch Pitfalls 5, 6, 7, 9.
**Prevention:** For each action class an integration test against a real agent in a disposable environment, recorded as an explicit verification item; keep the live-only list short and named in the roadmap rather than discovered at the end.
**Phase:** every phase; verification plan.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Keep env-var `AUTONOMOUS_REMEDIATION_DRY_RUN` as the master switch | No new code | Needs restart (the user's step), cannot be per tenant, cannot cancel queued work | Never as the only control; fine as an extra deny |
| Add autonomy checks only inside `remediate()` | One file to change | 40+ other enqueue sites bypass it | Never |
| Boolean `destructive` instead of risk tier + undo pairing | Already exists | Cannot express "auto but must be undoable"; wrong approvals | Never for v4.3 |
| In-process asyncio watchdog only | Fast to build | Blind when backend/VM/Mongo die | Only as the in-app layer next to an external supervisor and dead-man's switch |
| Reuse `remediation_audit` as the activity store | No migration | No hash chain, no retention policy, no suppressed-decision records | Only as a derived view over `audit_ledger` |
| Percent-based canary stages | Simple | Zero/one-host stages on small tenants | Only with min 1, cap, and OS/role coverage |
| Call halting "rollback" | Matches the spec wording | False expectations, support and legal exposure | Never; use "halt" and "revert where supported" |
| Let LLM text be the decision "reason" | Readable | Unreproducible, injectable, untestable | Never; store rule id as reason, LLM text as an annotation |
| Shared notification channel for all event kinds | No design work | Alert storms; on-call ignores it | Never past the first demo |
| Retention via one big `delete_many` | Three lines | Stalls Mongo on 2 vCPU | Only against collections known small |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Agent instruction queue (`agent_instructions` vs `instructions`) | Two queues with different consumers; enqueue to the wrong one; no expiry | Single choke point, one queue per semantic, `expires_at`, result callback with decision id |
| Rust agent result callback | Polling the DB for status with sleeps | Event-driven completion + timeout sweeper; treat missing result as `unknown` |
| MongoDB on kernel 7 | Restarting mongod blindly; assuming start succeeds | Check last start result; `GLIBC_TUNABLES` drop-in is a known requirement; verify in the self-heal checklist |
| systemd | App edits units/sudoers; no start limits | Operator-installed units with `StartLimit*`, scoped sudoers allowlist, app only calls an allowlisted helper |
| Ollama | Treat as always present; unbounded concurrency | Optional dependency with expected-state flag, single-flight, timeouts, no-LLM fallback |
| Jira/ServiceNow ticket bridge | AI comment echoes back as an inbound event | Author marker + echo suppression + once-only answer |
| Notification/SMTP | Assume configured (keys unset on this VM) | Channel health check, "no on-call channel configured" state shown in UI |
| `audit_ledger` | Writing to a second audit collection; deleting rows outside `purge_expired` | One writer, chain preserved, retention via ledger API |
| `distributed_lock` | Treating the TTL as the job duration | Renewal + fencing; job-run records |
| Tenant context (contextvars) | Setting per tenant in a loop and resetting once | `try/finally` per iteration; explicit `tenantId` on every record |
| SIEM OCSF push | Pushing every audit row | Push action-level events only; rollups |
| Microsoft Defender/EDR | Shelling out to netsh/powershell | Native calls where possible; classify "blocked by local security" |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Serial per-tenant, per-finding loop with 30-60 s waits | Cycle time exceeds interval; other tenants starved | Decision queue + worker pool(2), callback-driven completion | A handful of findings per tenant, or tens of tenants |
| Policies queried per finding (N+1) | Mongo CPU spikes each cycle | Load once per cycle, cache within the cycle | Hundreds of open findings |
| `to_list(200)` silent truncation | Findings never processed | Pagination + visible backlog counter | More than 200 open findings in a tenant |
| Heartbeats ~290 KB raw each | Disk fill, slow queries, slow retention | TTLs on all agent collections, bounded-batch retention, disk early warning | Already true (about 815 MB/day/endpoint) |
| Unbatched retention delete | API stalls, oplog growth | Batches with sleep and latency budget; dry-run first | First scheduled run after backlog |
| LLM on CPU | 10-60 s answers, Mongo starvation | Concurrency 1, timeouts, no-LLM fallback, extractive-first | Two simultaneous answers on 2 vCPU |
| Activity queries without compound indexes | Slow UI | `(tenantId, ts)` and `(tenantId, decision_id)` indexes in migration | Tens of thousands of entries per tenant |
| Websocket broadcast per audit row | CPU burst during storms | Coalesce events (per second), broadcast summaries | A containment cascade |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Ticket text inside the model's trust boundary | Injection, data exfiltration via links, social engineering of staff | No side-effect tools, schema-constrained output, link stripping, KB curation (Pitfall 21) |
| LLM output parsed into actions | Attacker-controlled actions | Rules only; LLM annotates (locked decision 3) |
| Approval is the only gate and is replayable | Stale/duplicated destructive actions | Atomic CAS, expiry, re-validation (Pitfall 8) |
| Broad sudoers/root for self-heal | Host takeover through any injection | Scoped allowlist drop-in, fixed unit names |
| Autonomous queries without `tenantId` | Cross-tenant effects and reads | Mandatory tenant param, two-tenant contract tests |
| Platform-admin context in loops | Bypasses tenant guard | Platform scope separated; per-record tenant assertion |
| Auto-block of shared/management IPs | Self-inflicted outage or DoS-by-feed | Protected list, TTL, dead-man's switch |
| Autonomy setting editable by too many roles | Client raises own autonomy beyond MSP agreement | Dedicated permission, platform cap, audit of changes |
| Block-rule propagation to all agents | One bad indicator hits a whole tenant | Per-decision cap, validation, approval for fleet-wide |
| Secrets in decision/audit records (script text, params) | Credential leak via Activity view/SIEM | Redact params by key class; never store scripts (there are none after Pitfall 1) |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Approval cards without context | Blind clicking | Show what, why (rule), where, blast radius, undo availability, evidence |
| One card per host for one incident | Fatigue | Group by incident; cap and digest |
| "Autonomous" with no visible limits | Distrust or over-trust | Level descriptions, caps and current counters visible |
| Undo button that sometimes fails | Lost trust | Compute `undoable_now`; show preconditions and result |
| Silent "nothing happened" | Operators assume the system is broken or that it is working | Show suppressed/not-acted reasons and the current switch/level state |
| AI answer indistinguishable from human | Client feels deceived; liability | Label automated answers, easy "talk to a person" |
| Dashboard green when the alert channel is not configured | False assurance | Explicit "alerting not configured" banner |

## "Looks Done But Isn't" Checklist

- [ ] **Autonomy level:** often missing action-time lookup and queue draining on change - verify setting Off cancels undelivered instructions and blocks the next scheduled cycle.
- [ ] **Global stop:** often only blocks new decisions - verify queued instructions, pending approvals, rollout stages and AI replies all respect it, and that unreadable switch state means no action.
- [ ] **Block IP undo:** often leaves duplicate rules - verify block twice, undo once, then confirm firewall state per OS.
- [ ] **Protected targets:** often missing agent-side refusal - verify blocking the backend IP is refused by both backend and agent.
- [ ] **Verification:** often checks the finding verdict - verify a successful block does not roll itself back.
- [ ] **Approval:** often non-atomic - verify two simultaneous approvals dispatch once.
- [ ] **Patch halt:** often never triggers because agent status is stale - verify killing an agent after install halts the rollout within the soak window.
- [ ] **Patch revert:** often untested - verify per OS family and list non-reversible classes in the UI.
- [ ] **Rollout resume:** often in-memory - verify a backend restart mid-stage halts or resumes without duplicates.
- [ ] **Watchdog:** often inside the backend - verify an alert arrives when the backend or mongod is stopped and when the heartbeat stops.
- [ ] **Restart budget:** often unbounded - verify a failing unit gets budget-many restarts then one page.
- [ ] **Retention schedule:** often deletes audit - verify the ledger hash chain verifies after a scheduled run and API latency stays in budget.
- [ ] **Scheduler:** often runs twice on overlap - verify two concurrent starts produce one run, including a run longer than the lock TTL.
- [ ] **Tenant isolation:** often only tested for routes - verify two-tenant tests for each autonomous loop, Activity feed and desk answer.
- [ ] **Service desk:** often answers when it should not - verify out-of-KB and injection test sets escalate with no side effects and no URLs.
- [ ] **Alerting:** often per-event - verify a 200-agent offline simulation produces a bounded alert count.
- [ ] **Audit:** often written after the act - verify intent exists for every instruction, including after fault injection.
- [ ] **Copy:** often drifts - verify the banned-terms lint passes and every claim maps to a test.
- [ ] **Existing tenants:** often default silently - verify each has an explicit stored level and the observe-first decision is recorded.
- [ ] **Everything works with Ollama down:** verify each flow with the LLM absent.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Containment cascade (many hosts blocked/isolated) | HIGH | Global stop; undo by decision group; agent TTL expiry will lift blocks; review audit by `decision_id`; add protected targets and lower caps before re-enabling |
| Agent lost its control channel after a block | MEDIUM-HIGH | Rely on agent-side TTL revert; otherwise manual access on the host; add the protected list entry |
| Restart loop on mongod/ollama | MEDIUM | Stop the restart (budget should have); operator checks journal and the GLIBC drop-in; fix cause; clear `needs_human` |
| Bad patch reached stage 2+ | MEDIUM-HIGH | Halt rollout, cancel undelivered instructions, revert where reversible, otherwise manual remediation and tenant comms; record in incident |
| Duplicate approval dispatch | LOW-MEDIUM | Check audit for double `override_approved`; verify host state; add CAS (Pitfall 8) |
| Wrong AI answer sent | MEDIUM | Post correction through a human, mark the KB article/answer, add to the eval set, consider raising retrieval threshold or pausing AI answers for that tenant |
| Injection suspected | MEDIUM | Disable service desk AI (switch), review conversations and any links sent, rotate anything exposed, extend red-team set |
| Retention deleted audit or evidence | HIGH | Restore from backup (the repo has backups from the production-readiness work), re-run chain verification from checkpoint; fence the deleter |
| Alert storm | LOW | Mute by incident key, enable correlation rule, lower channel rate; review dedup |
| Cross-tenant effect | HIGH | Stop switch, identify records via `tenantId` mismatch query, notify affected tenants per policy, add the contract test that would have caught it |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1 Legacy LLM path goes live | P-Core | Test: only playbook-sourced instructions reach the queue; no agentic/ai_remediation imports in execution path |
| 2 Bypass of policy layer | P-Core, P-Sec | Structural test on direct inserts; propagate-antibody respects Off and cap |
| 3 Destructive vs undoable | P-Core, P-Sec | Schema validation for `risk_tier` + undo; round-trip tests per OS; agent version gate |
| 4 Cascades, no idempotency | P-Core, P-Sec | Unique decision key test; cap/breaker test with simulated 50 findings; patch/FIM interlock test |
| 5 Wrong verification | P-Sec | Block 192.0.2.x ends in `verified` not rollback |
| 6 Undo does not undo | P-Sec, P-UI | Double block/single undo test; pre-state restore test; refcount test |
| 7 Control channel severed | P-Sec | Protected target refusal (backend + agent); dead-man's-switch revert test |
| 8 Approval fatigue/races | P-Core, P-UI | CAS test; expiry test; grouped cards; approval-time metric |
| 9 Rollback not a rollback | P-Patch | Revert matrix per OS; UI wording "halt / revert where supported" |
| 10 Stale health signals | P-Heal (cadence), P-Patch (gate) | Frozen-clock test of agent status cadence; kill-agent test halts rollout |
| 11 Patching the platform/not resumable | P-Patch, P-Core | Platform host excluded; mid-stage restart chaos test |
| 12 Staging mechanics | P-Patch | Small-tenant sizing test; instruction expiry test; no auto-complete with zero targets |
| 13 Watchdog blind to host death | P-Heal | External unit files + checklist; dead-man's-switch alert test; alert channel health check |
| 14 Restart loops/flapping | P-Heal | Restart budget + backoff test; expected-state registry test |
| 15 Privilege creep | P-Heal | Allowlist/argument tests; reviewed sudoers drop-in provided, install is the operator's step |
| 16 Retention/disk | P-Heal, P-Core | Batched retention latency test; chain verify after run; audit collections excluded |
| 17 Scheduler double-runs | P-Core | Two-instance test; TTL-exceeding job test; per-iteration tenant context reset |
| 18 Cross-tenant leakage | P-Core + each phase | Two-tenant contract tests for every loop/feed/answer; `is_duplicate_task` tenant fix |
| 19 Stop switch scope | P-Core | Stop semantics test list (queued, approvals, rollouts, AI replies); fail-closed test |
| 20 Audit gaps | P-Core, P-UI | Write-ahead intent test with fault injection; suppressed decisions recorded; chain verifies |
| 21 Prompt injection | P-Desk | Red-team CI set; no tools; link stripping; KB curation rule |
| 22 Hallucinated answers | P-Desk | Eval set with unanswerable questions (100% escalate); citation validation; once-only answer |
| 23 Alert storms | P-Heal, P-Patch, P-Core | 200-agent offline simulation; maintenance-window suppression test |
| 24 Over-claiming | P-UI + all phases | Banned-terms lint; claims-to-tests table in each phase verification |
| 25 Default-on and permissions | P-Core | Migration test: every tenant has explicit level; permission 403 tests; screens in feature-switch catalogue |
| 26-35 | As listed in each entry | Per-entry tests |

## Sources

- Repo findings read 2026-10-25 (HIGH): `/home/azureuser/enterprise-omni-agent-ai-platform/backend/autonomous_remediation_service.py`, `app_background_tasks.py`, `response_orchestrator.py`, `remediation_playbook_service.py`, `remediation_audit_service.py`, `swarm_service.py`, `distributed_lock.py`, `retention_service.py`, `audit_ledger.py`, `tickets_escalation_service.py`, `guardrail_service.py`, `ai_orchestration/guardrails.py`, `ai_assistant_service.py`, `ueba_service.py`, `playbooks/*.yaml`, and `agent-install/omni-agent-rs/src/instructions.rs` and `capabilities/remediation_actions.rs`; count of agent-queue insert sites from a grep of `backend/*.py`.
- Project memory (user-authored notes, HIGH for local history): MongoDB on kernel 7.0 drop-in, data limits assessment, patch status stale after deploy, remote desktop Defender quarantine, optional integrations unconfigured, tenant boundary hardening, security hardening, feature switches.
- [Moffatt v. Air Canada, 2024 BCCRT 149 coverage (American Bar Association, McMillan, Mondaq)](https://www.americanbar.org/groups/business_law/resources/business-law-today/2024-february/bc-tribunal-confirms-companies-remain-liable-information-provided-ai-chatbot/) - MEDIUM (tribunal decision, secondary coverage).
- [FTC Operation AI Comply coverage (Davis Polk, Duane Morris)](https://www.davispolk.com/insights/client-update/ftc-announces-new-enforcement-initiative-targeting-deceptive-ai-practices) - MEDIUM (2024 coverage; final status of orders not re-verified).
- [CrowdStrike Channel File 291 root cause analysis coverage (TechTarget, 63SATS)](https://www.techtarget.com/searchSecurity/news/366602392/CrowdStrike-details-errors-that-led-to-mass-IT-outage) - MEDIUM (staged rollout and validation lessons; secondary coverage, primary RCA not read).
- OWASP LLM01 prompt injection guidance (search summaries; least privilege, tiered tool approval, untrusted-content marking, no fully reliable defence) - MEDIUM.
- General SRE practice (restart budgets/backoff, hysteresis, dead-man's switch, alert grouping) - MEDIUM, widely established, not re-verified here.

---
*Pitfalls research for: Autonomous Ops on an existing multi-tenant MSP security/compliance/ITAM platform*
*Researched: 2026-10-25*
