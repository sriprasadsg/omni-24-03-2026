# Feature Research

**Domain:** Autonomous operations (security response, staged patching, platform self-healing, AI first-line service desk, autonomy controls and activity view) added to an existing multi-tenant MSP security/compliance/ITAM platform
**Milestone:** v4.3 Autonomous Ops (phases start at 81)
**Researched:** 2026-10-25
**Confidence:** MEDIUM-HIGH overall. Autonomy-level, approval, undo and audit patterns are well documented (Microsoft Defender, HIGH). Patch-ring health gates, PagerDuty tiers and service-desk deflection rest partly on vendor blogs and secondary sources (MEDIUM). Findings about THIS codebase come from reading the source directly (HIGH).

**Naming rule (locked):** never label any of this "ASI" or "Autopilot" (Windows Autopilot already exists as `autopilot_service.py`). Use "Autonomous Ops". The UI copy should say "automatic" and "needs approval", not "AI-driven".

**Non-negotiable invariants (locked decisions, every category inherits them):**
1. Per-tenant level: Off / Suggest / Undoable-auto (default Undoable-auto). Undoable actions run alone; destructive actions wait for one approval click.
2. Fixed, tested rules pick every action. The local LLM (Ollama llama3.2:3b, CPU only) only summarises and suggests. No LLM output ever becomes a command, a parameter, a target or an approval.
3. Everything audited, undoable where possible, one global stop switch.

---

## How mature products behave (what operators already expect)

| Product | Pattern | What to copy | What not to copy |
|---------|---------|--------------|------------------|
| Microsoft Defender for Endpoint AIR | Levels: Full / Semi (approve all, core folders, non-temp folders) / None, set per device group. Action Center has Pending and History tabs. Pending actions time out after 7 days and the timeout counts as a rejection. Any executed remediation can be undone from History, and a quarantine undo can extend to other instances of the same file. Microsoft notes that AIR stopped running as a separate experience on 2026-09-01 and the capability moved into the default antivirus stack. | Level names that say what happens. Pending/History split. Timeout equals reject. Undo lives in the history list. Bulk undo of the same artefact. | Microsoft's "No automation, not recommended" shaming. Default-Full is fine for us only because the locked default is "Undoable-auto", not Full. |
| SentinelOne | Protect vs Detect policy modes. Protect auto-kills and quarantines, Detect only alerts. Rollback exists as a separate remediation. | Two-axis thinking: what the policy may do automatically versus what is only reported. Rollback as a first-class verb. | Cloud-ML verdicts deciding actions. We use fixed rules. |
| CrowdStrike Falcon Fusion | SOAR workflows with a human-input step. Common "human-in-the-loop containment" pattern gates host containment behind analyst approval. Lifting containment is a distinct console action. Fusion workflows can be scheduled. | Approval as a workflow step, containment and release as a pair, workflow scheduling. | Analyst-authored free-form workflows for tenants (too much surface for v4.3). |
| Windows Update for Business / Intune rings and Autopatch | Ring-based phased rollout. Autopatch watches device telemetry and can pause progression to the next ring when failures spike. Admins keep a manual halt. Third-party sources only on thresholds, so treat thresholds as our own design. | Rings, soak time between rings, automatic hold on failure, manual pause always available. | Letting users defer 35 days (Intune "pause" default). Our device owners are tenants' end users, so deferral policy is a tenant setting. |
| Kubernetes / systemd | Liveness vs readiness. Restart with exponential backoff (10s, 20s, 40s ... capped at 5 min; backoff resets after ~10 min of clean running). `Restart=on-failure` with `StartLimitBurst` inside `StartLimitIntervalSec` stops retrying and leaves the unit failed. The common production failure is an endless restart loop. | Consecutive-failure threshold before acting, backoff, restart budget, give up and page a human when the budget is spent. | Restart policy "Always" without a budget. |
| PagerDuty | Escalation policy with tiers, ack timeout per tier (default 30 min, teams commonly use 5-15), repeat the whole policy a bounded number of times, acknowledging stops escalation, acknowledged-but-unresolved can re-trigger after a timeout, alert grouping so a flood is one incident. Real example: two 10-minute tiers repeated 5 times. | Tiers + timeouts + bounded repeat + ack stops + grouping. | Per-person notification-rule sprawl. Escalation policy overrides personal rules anyway. |
| ServiceNow / Freshservice / Zendesk AI deflection | Confidence bands: high resolves, middle drafts a reply for an agent (internal note), low hands off. Escalate regardless of confidence on explicit "human please", negative sentiment, billing/legal/security-account topics and SLA risk. Handoff carries the conversation and drafted suggestions. Weak knowledge bases make AI worse than a human. Threshold must be adjustable. | Three-band routing, mandatory escalation triggers, context on handoff, show which KB article answered. | Confidence numbers from a 3B model as the only gate (see service desk anti-features). |

---

## Feature Landscape

### Category 1: Autonomy controls (the cross-cutting layer, build first)

#### Table stakes

| Feature | Why expected | Complexity | Notes / dependency on existing code |
|---------|--------------|------------|-------------------------------------|
| Per-tenant autonomy level: Off / Suggest / Undoable-auto, default Undoable-auto | Every mature product has named levels; Defender's Full/Semi/None is the reference. | LOW-MED | Today tenant gating is `tenants.enabledFeatures` containing `autonomousRemediation`, plus a GLOBAL env `AUTONOMOUS_REMEDIATION_DRY_RUN` (default true). The new level must replace both as the single source of truth, and the env dry-run must become "global ceiling", not a second competing switch. Store on the tenant doc; reuse the per-tenant feature-switch (C6) infrastructure for the Activity screen visibility. |
| One shared decision function: `decide(action, tenant_level, asset, context) -> run / ask / suggest / refuse` | Operators expect the same rule everywhere (security, patch, self-heal). Divergent gates are the classic bug class (this repo already has two). | MED | Extends `backend/backend_safety.py::evaluate_action` and the playbook `destructive` flag. See conflicts below. |
| Action reversibility classes: `undoable`, `destructive`, `informational` | The locked split (block IP, quarantine, restart = undoable; isolate, kill, reboot = destructive) needs to be data, not scattered `if`s. | LOW | Today every shipped YAML playbook sets `destructive: true` (including `block_ip` and `disable_service`, which HAVE rollbacks), so today they ALL wait for approval. Needs a second field such as `reversible: true` and a rule: auto-run only if reversible AND rollback steps exist. `kill_process` and `restore_file` have `rollback: []` and stay gated. |
| Global stop switch (platform-wide) plus per-tenant pause | Every vendor has a "halt all automation" button; MSPs expect it for incidents. | LOW-MED | Must be re-checked immediately before EVERY dispatch, not only at cycle start (fail closed if the flag read fails). Stops new actions and new stages; does not silently roll back things in flight (it leaves them and surfaces them in Activity). Also must be flippable without the UI (CLI or flag file) because the incident may be the UI. Should itself be audited and notify operators. |
| Approval inbox with expiry | Defender: Pending tab, 7-day timeout = reject. | LOW | `approve_remediation` / `deny_remediation` and `/api/remediation/{id}/approve|deny` already exist; Agent Approvals and Deployment Approvals screens exist. Add: single unified pending list, expiry (default deny), approver identity, and a "why / what / how many machines" card. |
| Undo button on every undoable action | Defender History undo; operators judge autonomy by how cheap a mistake is to reverse. | MED | Playbook `rollback` blocks already exist and dispatch through `agent_instructions`. Needs: persisted inverse (computed at action time, not at undo time), undo audit entry linked to the original, and "undo failed" handling. |
| Blast-radius limits | Operators fear one bad rule touching the fleet. | MED | Existing: per-agent concurrency lease (`REMEDIATION_MAX_CONCURRENT_PER_AGENT`=2), severity ceiling (`MAX_AUTO_SEVERITY`=medium), 5-minute dedup. Missing: per-decision asset cap, per-tenant actions-per-hour cap, per-rule cap. `evaluate_action` already takes a `blast_radius` argument that no autonomy path enforces. |
| Never-touch list (exclusions) | Auto-blocking your own gateway or DNS is the textbook outage. | LOW-MED | Per-tenant list of protected IPs/ranges, assets, services. Seed with the platform's own backend, MongoDB, Ollama addresses and RFC1918 default gateways. Refuse `/0`, loopback, private-range blocks unless exact entry is approved. |
| Complete audit of every decision, including refusals and "suggest only" | Auditors and MSP clients ask "why did it not act?" as often as "why did it act?". | MED | Reuse `audit_ledger.record` (hash chain, spool-on-failure) and `remediation_audit_service.write_audit` (insert-only). Record the rule id, inputs, level in force, decision, actor, outcome. |
| Activity view (see Category 6 below) | Defender Action Center. | MED | See below. |

#### Differentiators

| Feature | Value | Complexity | Notes |
|---------|-------|------------|-------|
| Circuit breaker: auto-downgrade a tenant to Suggest when N autonomous actions fail or are undone in a window | Self-limiting autonomy builds MSP trust; no mainstream SMB tool does this visibly. | MED | Deterministic counters only. Writes an audit entry and notifies. Operator re-enables explicitly. |
| "Would have done" shadow records in Suggest and Off-with-learning | Lets an MSP trial Undoable-auto per tenant with evidence. | LOW-MED | Same decision function, outcome `suggested`. Free once the decision function exists. |
| Maintenance windows / change freeze honoured by all four domains | MSP clients have freeze periods. | MED | Integrate with existing Change Management (`change_management_service.py`). If a change is in freeze, autonomy downgrades to Suggest for patching and restarts. |
| Per-domain override (security / patching / self-heal / service desk) under the tenant level | Defender allows per-group levels. Patching often needs to be stricter than blocking an IP. | LOW | Keep to one level plus four on/off toggles. Do NOT build per-rule per-tenant matrices in v4.3. |
| Per-rule health stats (fired, undone, failed, approval rate) | Tells the operator which rule to tighten. | LOW | Derived from the activity collection. |

#### Anti-features

| Anti-feature | Why requested | Why problematic | Alternative |
|--------------|---------------|-----------------|-------------|
| Confidence-score auto-approval of destructive actions | "If we are 95% sure, why ask?" | `backend_safety.py` already contains `AUTO_APPROVE_CONFIDENCE_THRESHOLD = 0.90` that lets an approval-required action proceed. It contradicts the locked "destructive waits for one click" decision. A score from any model or heuristic is not an approval. | Remove or hard-disable that bypass for autonomy paths. A regression test proves no score, severity or source bypasses approval (same stance as v3.4 Phase 55 D-04). |
| Two inconsistent action classifications | Historical drift. | `backend_safety.py` lists `kill_process` as SAFE and `restart_service` as APPROVAL_REQUIRED. The locked decision says the opposite for both. Whichever is read first wins, silently. | One classification table, one owner, tests that pin each action to its class. |
| LLM decides action, target, parameters or script | "Smarter responses." | The legacy `AutonomousRemediationService.generate_plan()`/`run_cycle()` path does exactly this: `run_remediation_script` with an AI-generated script, and an "agentic" tool choice for alerts. | Autonomy drives only the playbook path (`remediate()` with YAML playbooks). The legacy `run_cycle` path must be unreachable from autonomy, or removed. |
| Implicit "run as root" free-form script action | Flexibility. | Unbounded blast radius. | Only named, parameter-validated actions the agent already implements. |
| Autonomy that cannot be switched off during an incident | Simplicity. | Operators lose trust the first time they cannot stop it. | Global stop plus per-tenant pause, both outside the normal UI path. |
| Autonomy that acts across tenants | Efficiency ("block this IP everywhere"). | Violates tenant isolation. Recent hardening made the DB wrapper auto-scope tenants. | Cross-tenant suggestions only, shown to the MSP operator, each applied per tenant under that tenant's level. |
| Per-tenant custom rule authoring in v4.3 | MSP asks. | Untested rules are the risk the locked decision removes. | Ship a fixed, tested rule set; tenants choose level and exclusions only. |

---

### Category 2: Security response

#### Table stakes

| Feature | Why expected | Complexity | Notes / dependency |
|---------|--------------|------------|--------------------|
| Alert/finding to playbook mapping with fixed, tested rules | Defender AIR, S1 Protect, Falcon Fusion all do this. | MED | Extends `remediation_playbook_service.select_playbook` and `backend/playbooks/*.yaml` (block_ip, disable_service, kill_process, patch_package, restore_file, rotate_key). A rule table keyed by finding class + severity + corroboration. |
| Undoable actions auto-run under Undoable-auto | Locked decision 1. | MED | Needs the reversibility split above. The playbooks for block_ip and disable_service already carry rollbacks. |
| Destructive actions queue for approval with one click | Locked decision 1. | LOW | Existing `pending_approval` state and approve/deny endpoints. UI: approvals card and push notification. |
| Verify after action, roll back on verify-fail | Existing (v3.4 `_dispatch_and_verify`). | LOW | Keep. Verification currently covers vuln, FIM and nscan finding classes. |
| Auto-expiry of containment (TTL on blocks) | Industry norm: temporary blocks with an expiry and an extend button, so a mistake self-heals. | LOW-MED | New. A sweeper dispatches `unblock_ip` at TTL. Use the same scheduler as retention. Default 24 h, tenant-adjustable. |
| Cooldown and dedup | Existing 5-minute dedup (`ResponseOrchestrator.is_duplicate_task`). | LOW | Keep. Add repeat-offender escalation (same finding again after undo = ask, never retry silently). |
| Notification on every automatic action | Operators want to know. | LOW | `notification_service.send_alert` (email/sms/slack/webhook). Batch into a digest by default; immediate for destructive pending. |
| Missing agent actions for the locked action list | `quarantine_file`, `restart_service` and `isolate_host` are named in the decision but the shipped Rust agent only handles `kill_process`, `restore_file`, `block_ip`, `unblock_ip`, `disable_service`, `enable_service`, `rotate_key` (see `agent-install/omni-agent-rs/src/instructions.rs`). Backend `agent_capabilities.py` lists `isolate_host` but the agent has no handler. | HIGH | New agent release required (agent publish pipeline already exists, version 2.1.x). Each new action needs its inverse: quarantine/restore-from-quarantine, restart (self-inverse, idempotent), isolate/release-isolation. Per-tenant agent capabilities (C6) must gate each new action. |
| Audit entry per step with before/after state | Existing immutable `remediation_audit`. | LOW | Add the autonomy level in force and the rule id. |

#### Differentiators

| Feature | Value | Complexity | Notes |
|---------|-------|------------|-------|
| Corroboration rules (e.g. two independent signals before auto-block) | Cuts false positives without an ML score. | MED | Deterministic: count distinct sources (native scan + UEBA + SIEM correlation, `SiemEngine.correlate_native_findings`). |
| Quarantine-not-delete, always | Safe by construction and matches Defender's quarantine + undo. | MED | Moves a file to a protected folder with hash recorded; restore returns it. Never deletes. |
| Time-boxed isolation after approval, with release reminder | Isolated hosts get forgotten. | MED | Isolation needs approval, then auto-prompts for release at N hours (prompt, not auto-release, unless tenant opts in). |
| Incident grouping on the Activity view | One compromise, ten findings = one story. | MED | Group by asset and time window. |
| LLM-written plain-English summary of the incident, labelled "AI summary" | Saves reading raw JSON. | LOW | Runs after the decision, read-only, optional, skipped if Ollama is down. The decision record does not depend on it. |
| Ticket auto-created per destructive approval or failed verification | Closes the loop with Jira/ServiceNow bridge. | LOW | Reuse `ticketing_bridge`, `_create_failure_ticket`. |

#### Anti-features

| Anti-feature | Why requested | Why problematic | Alternative |
|--------------|---------------|-----------------|-------------|
| Auto-kill process, auto-isolate host, auto-restore file | "Fastest containment." | Destructive per locked decision. `kill_process` and `restore_file` have no rollback. | Queue for approval; make the card one click with the process tree and asset criticality shown. |
| Auto-block by wildcard or CIDR in rules | Block a whole bad subnet. | Self-lockout and customer outage. | Single IPs only automatically; ranges need approval. |
| Auto-block IPs from a threat feed with no corroboration | Feed says "bad". | Stale or poisoned feeds (and the platform's feeds are signed bundles, not live). | Corroboration rule plus TTL. |
| Autonomy on critical or high-criticality assets | "Protect the crown jewels first." | Those are the machines where a wrong action costs most. `backend_safety.HIGH_CRITICALITY_LEVELS` already says they always need a human. | Keep: critical/high assets always ask, whatever the level. |
| Retry-until-success loops on a failed action | Persistence. | Amplifies a bad action. | One attempt, one verify, one rollback, then escalate (ticket + notification). |
| UEBA or SOAR playbooks triggering actions outside the same gate | Existing SOAR/UEBA already act. | A second code path with weaker checks. | Route UEBA, SOAR and Active Response automatic triggers through the one decision function; keep manual operator use unchanged. |

---

### Category 3: Staged patching with health gates

#### Table stakes

| Feature | Why expected | Complexity | Notes / dependency |
|---------|--------------|------------|--------------------|
| Rings/stages (canary, pilot, broad) with a soak time between them | Intune/Autopatch/WSUS/Tanium all do rings. | MED | `deployment_service.py` already creates 4-stage jobs (TEST/DEV/STAGING/PRODUCTION) with percentages and a `staged_deployments` collection. Those are environment-named; MSP fleets need ring-named stages and a canary of 1-5 machines. Rename/extend, do not duplicate. |
| Scheduled start in a maintenance window per tenant timezone | MSPs patch off-hours. | MED | `scheduler.py` (APScheduler) and `report_schedule_timing.py` exist. Add window + timezone. |
| Health check after each stage, auto-halt on failure | The locked requirement; Autopatch behaves this way. | MED-HIGH | `config.health_check_enabled` is set in `deployment_service` but nothing reads it; `update_stage_progress` counts per-asset PATCH success, not post-patch HEALTH. Define health deterministically: agent heartbeat returns within N minutes, critical services running, no new critical alert on the asset, install result OK. |
| Automatic rollback on failed gate | Locked requirement. | HIGH | `trigger_rollback` exists in `deployment_service`; confirm it dispatches real work to agents (memory notes OS patching was once "fake end to end" and later fixed; verify before trusting it). Windows rollback is limited (uninstall KB where possible, otherwise restore point/snapshot); say so honestly in the UI: "rolled back" vs "halted, manual action needed". |
| Pause / resume / cancel by an operator any time | Every rollout tool has it. | LOW | Plus the global stop switch. |
| Reboot handled as a destructive action with ONE approval for the batch | Locked decision (patch reboot = destructive). | MED | One approval per stage ("reboot 14 machines at 02:00"), not per machine. Show deferral to next window if declined or expired. |
| Preflight checks per machine | Prevents patching a sick machine. | MED | Disk free, pending reboot flag, agent online, not on exclusion list, not under change freeze. |
| Result report per stage and per rollout | Auditors and clients ask. | LOW | Reuse `PatchDeploymentJobs.tsx`, `deployment_result_endpoints.py`. |
| Exclusion/hold lists (critical servers manual only) | Common MSP practice. | LOW | Reuse the never-touch list from Category 1. |

#### Differentiators

| Feature | Value | Complexity | Notes |
|---------|-------|------------|-------|
| Failure-rate gate with a minimum sample (e.g. halt if over X% fail AND at least N machines) | Avoids halting on one flaky laptop in a ring of 3, avoids ignoring failure in a ring of 300. | LOW-MED | Deterministic thresholds, tenant-tunable within safe bounds. |
| Auto-skip a patch that failed twice in earlier rings and mark it "known bad" | Stops repeating a bad KB across tenants. | MED | Platform-level known-bad list (operator-curated, not LLM). |
| Canary chosen by rule (lowest-criticality, most-recently-healthy machines) | Better canary than random. | LOW-MED | Derived from asset criticality and heartbeat uptime. |
| Rollout timeline with gate results shown per stage | Makes "why did it halt" obvious. | LOW-MED | Part of the Activity view. |

#### Anti-features

| Anti-feature | Why requested | Why problematic | Alternative |
|--------------|---------------|-----------------|-------------|
| Auto-reboot without approval | "Patches need reboots." | Destructive per the locked decision; data loss for logged-in users. | Per-stage reboot approval; schedule inside the window. |
| Auto-progress past a stage with no health signal | Speed. | A missing signal is not a pass. | Treat "no data" as fail-closed (halt). |
| LLM choosing which patches or which machines | "Smart prioritisation." | No LLM in execution path. | Deterministic priority from severity, CVSS/KEV and asset criticality. |
| Patching the platform host itself automatically | Self-maintenance. | The platform is the thing that would roll back. | Self-healing only warns; the host patch stays the user's step. |
| Auto-uninstall of a patch based on a user complaint | Responsive. | Unverifiable input. | Ticket plus operator-triggered rollback. |

---

### Category 4: Platform self-healing

#### Table stakes

| Feature | Why expected | Complexity | Notes / dependency |
|---------|--------------|------------|--------------------|
| Out-of-process watchdog (systemd unit/timer) probing backend, MongoDB, Ollama | A process cannot reliably watch or restart itself. Kubernetes/systemd both supervise from outside. | MED | The backend can only act on Mongo or Ollama while it itself is up. A separate lightweight unit is required for "backend is down". Installing units on the live VM is the user's step (project memory; never run `run-on-ubuntu.sh`, it touches ufw). Ship units + a script, do not apply them. |
| Liveness vs readiness distinction | Process up is not the same as working. | LOW | e.g. backend `/api/health` answers AND a Mongo ping works; Ollama `/api/tags` answers. `health_service.py` and System Health / API Status screens exist; extend, do not rebuild. |
| N consecutive failures before acting | Avoids restarts on blips. | LOW | Typical 3 probes. |
| Restart with backoff and a restart budget; then stop and page | K8s CrashLoopBackOff (10s to 5 min cap) and systemd StartLimit. Endless loops are the classic failure. | MED | Budget per service per hour; after it is spent mark "needs human" and alert. Memory note: mongod once failed to start after a kernel update and was fixed by a drop-in; a watchdog must not hammer a service that cannot start. |
| Expected-state config per service | Ollama is intentionally inactive on this VM. Alerting on it forever is noise. | LOW | `expected: running | stopped | optional`. |
| Certificate expiry warnings at 30 / 14 / 7 / 1 days | Standard thresholds. | LOW-MED | `certificate_endpoints.py` exists for tenant/agent certs; add the platform's own TLS (probe the live listener, not just files). Warn only; renewal stays human. |
| Disk usage warnings at 80 / 90 / 95 percent | Standard. | LOW | Include MongoDB data dir, logs and backup dir. 7 GB VM makes this real (project notes: heartbeats ~815 MB/day/endpoint raw). |
| Scheduled retention job | Manual today (`retention_service.run_cleanup`, `retention_endpoints.py`). | MED | Cron with per-tenant policy, dry-run preview count, max-delete guard (abort and alert if a run would delete far more than the previous run), run record in Activity. See anti-feature on audit logs. |
| On-call alerting with tiers, ack timeout and bounded repeat | PagerDuty pattern. | MED-HIGH | `notification_service` has email/sms/slack/webhook; nothing models schedules, tiers or acknowledgement. Build the minimum: ordered contact list, per-tier timeout, ack link, repeat N times. Optional webhook to PagerDuty/Opsgenie rather than rebuilding all of it. |
| Alert about alert delivery failure | If SMTP is unset (it is on this VM, see optional-integrations note) the on-call feature silently does nothing. | LOW | Show "no working channel configured" prominently; test-notification button; never claim "on-call covered" without a passing test. |
| Heartbeat/dead-man's switch for the watchdog itself | Silence must be detectable. | LOW-MED | Watchdog writes a heartbeat; the platform raises an alert when it stops. An external ping URL is optional. |

#### Differentiators

| Feature | Value | Complexity | Notes |
|---------|-------|------------|-------|
| Alert grouping and dependency suppression (MongoDB down means do not also page about every API check) | Prevents a page storm. | MED | A small static dependency graph. |
| Self-heal timeline in the Activity view with "restarted X at T, healthy after Y s" | Shows value to the MSP. | LOW | Same activity collection. |
| Capacity forecast (disk fill date) | Warn days ahead rather than at 90 percent. | LOW-MED | Linear fit over recent samples. Deterministic. |
| Degradation modes: Ollama down, service-desk AI falls back to "escalate to human" with a banner | The LLM is optional, the product stays honest. | LOW | Ties Category 5 to Category 4. |

#### Anti-features

| Anti-feature | Why requested | Why problematic | Alternative |
|--------------|---------------|-----------------|-------------|
| Unlimited auto-restart | "Keep it up." | Restart loops mask real faults and can corrupt MongoDB. | Budget, backoff, page. |
| Auto-delete data or backups to free disk | Disk is full. | Destroys evidence and backups; the audit ledger is hash-chained. | Warn; only the scheduled retention policy deletes, and only what policy names. |
| Retention job that touches the audit ledger or Autonomous Ops decision records | "Clean everything." | `RetentionService.cleanup_audit_logs` deletes `audit_logs` older than 90 days by default (it keeps a purge checkpoint so the chain still verifies). If the Activity view reads only `audit_logs`, actions vanish from view after 90 days. | Give autonomy decisions their own collection and longer retention floor; exclude them from the default run; keep ledger checkpointing. |
| Auto-renew certificates or auto-rotate secrets | Convenience. | Wrong renewal breaks every agent (agent TLS pinning is in place). | Warn early; renewal is a human step with a checklist. |
| Restarting MongoDB or the OS from inside the backend process | "Self-contained." | The backend dies with it and cannot verify. | Watchdog outside, user installs. |
| Auto-applying OS patches or kernel updates on the platform VM | "Self-maintenance." | A kernel update already broke mongod once on this VM. | Notify only. |
| Building a full on-call product (calendars, shift swaps, mobile app) | PagerDuty parity. | Months of scope for a side feature. | Contact list with tiers + webhook out to a real on-call tool. |

---

### Category 5: Service desk (AI first-line answers)

#### Table stakes

| Feature | Why expected | Complexity | Notes / dependency |
|---------|--------------|------------|--------------------|
| AI drafts or sends a first answer to a new ticket from the knowledge base only | ServiceNow/Freshservice/Zendesk deflection norm. | MED | `rag_service.py` (query with tenant filter), `knowledge_endpoints.py` `/query`, tickets stack (`tickets_service.py`, `tickets_workflow_endpoints.py`), AI Assistant. Answer is built from retrieved KB passages, quoting and linking them. |
| Cite the KB article(s) used | Trust and verifiability. | LOW | Show title and link in the reply. |
| Escalate when unsure and say so to the user | Locked decision. | MED | Escalation triggers are RULES, not only the model's opinion: no KB hit above a retrieval-score floor, fewer than N supporting passages, user asked for a human, negative sentiment keywords, security/account/billing/legal keywords, ticket category on a never-auto list, reopened ticket, SLA about to breach, VIP user. |
| Three outcomes: answer, draft-for-agent, escalate | Industry confidence bands. | MED | Level mapping: Off = nothing; Suggest = always draft for the agent (internal note); Undoable-auto = send answer only when rules say so, else draft or escalate. A sent answer is reversible only by a follow-up, so it needs the gentlest default. |
| Handoff with context | Agents hate re-asking. | LOW | Attach retrieved passages, the draft, the reason for escalation. |
| "Did this solve it?" confirmation and auto-close only after confirmation or timeout | Prevents false deflection. | LOW-MED | Reopen on negative reply; reopened tickets always escalate. |
| Tenant isolation of the knowledge base | MSP multi-tenant. | LOW (exists) | `rag_service.query(tenant_id=...)`; test that tenant A's KB never answers tenant B (global vs tenant docs distinction already present). |
| Visible "AI-assisted" label | Honesty; avoids a human-impersonation complaint. | LOW | On every AI reply. |
| Ollama-down fallback: skip AI, route normally | The VM's Ollama is inactive today. | LOW | Ticket flow must not depend on the model. |

#### Differentiators

| Feature | Value | Complexity | Notes |
|---------|-------|------------|-------|
| KB gap detection: tickets escalated for no-answer become "suggest an article" items | Makes the KB improve; addresses the weak-KB failure mode. | MED | Group unanswered by question embedding; LLM may only summarise the cluster. |
| Deflection analytics (answered, confirmed, reopened, escalated; top articles) | MSP proof of value. | LOW-MED | Feeds the Activity view. |
| Per-category auto-answer allowlist (password-reset how-to yes, access requests no) | Tenant control without per-rule authoring. | LOW | A list of categories, default conservative. |
| Prompt-injection hardening on ticket text and KB text | Tickets are untrusted input. | MED | Retrieval passages and ticket body are treated as data; model output is displayed as text only; no tool calls from this path. |

#### Anti-features

| Anti-feature | Why requested | Why problematic | Alternative |
|--------------|---------------|-----------------|-------------|
| AI performs actions from ticket text ("reset my MFA", "unlock my account", "install X") | Real self-service. | Ticket text is untrusted; an LLM turning it into an action is exactly the path locked decision 3 forbids. | The AI links the documented how-to or opens a request that goes through existing approval workflows (JIT access, asset requests). |
| Answering without a KB source (model's own knowledge) | Higher deflection rate. | A 3B model hallucinates; wrong answers cost more than escalations. | No retrieval hit means escalate. |
| Using the model's self-reported "confidence" as the gate | Easy to implement. | Small models are poorly calibrated. | Gate on retrieval score, passage count, category and keyword rules; the model only drafts text. |
| Auto-closing tickets without user confirmation | Better metrics. | Hidden failures, angry users. | Close on confirmation or a long timeout with a reopen link. |
| Auto-answering security incidents, billing, legal, account-compromise tickets | Volume. | Regulated and high-risk topics are the standard escalation list. | Always escalate and notify. |
| Training or fine-tuning on tenant tickets | "Gets better over time." | Cross-tenant leakage risk; the project's own-LLM work is a separate effort. | Improve the KB, not the model. |

---

### Category 6: Activity view (what Autonomous Ops did, why, undo)

#### Table stakes

| Feature | Why expected | Complexity | Notes / dependency |
|---------|--------------|------------|--------------------|
| One chronological feed across security, patching, self-healing and service desk | Defender Action Center sets the expectation. | MED | New `autonomy_actions` (decision record) collection written by the single decision function. Do not infer the feed from `audit_logs` (that gets purged by retention). |
| Tabs/filters: Pending approval, Done, Undone, Failed, Refused (blocked by limit, exclusion or level), Suggested | Defender Pending/History. | LOW-MED | Status is an enum on each record. |
| Each row: what, target, when, which rule, level in force, who approved, outcome, undo | The stated purpose. | MED | "Why" comes from the rule id plus the triggering evidence; an optional AI summary is clearly labelled. |
| Undo from the row | Locked requirement. | MED | Undo disabled with the reason when the action is not undoable ("destructive, no rollback") or already undone. |
| Approve/deny from the same list | Fewer places to look. | LOW | Reuses existing endpoints. |
| Link to the immutable ledger entry | Auditors. | LOW | Store the ledger `seq`/`hash` on the record. |
| Tenant-scoped for tenant admins; cross-tenant roll-up for the MSP operator | Multi-tenant. | MED | Follow the tenant wrapper conventions; add a feature switch so the screen appears only where enabled. |
| Global stop switch and the tenant level visible at the top of the page | Operators check state first. | LOW | Banner when stopped or in Suggest. |
| Export (CSV/PDF) | Compliance evidence. | LOW | Existing export patterns. |

#### Differentiators

| Feature | Value | Complexity | Notes |
|---------|-------|------------|-------|
| "While you were away" digest (email/Slack) | Operators do not live in the console. | LOW-MED | Counts are deterministic; an optional AI-written paragraph is labelled. |
| Hours-saved estimate | MSP billing story. | LOW | Fixed minutes per action type; show the assumption. |
| Per-rule undo rate and approval rate | Tune the rules. | LOW | See Category 1. |
| Filter by incident / rollout ID | Follow one story end to end. | MED | Needs correlation ids. |
| Compliance mapping of autonomous actions to controls (change evidence) | The platform's core value is compliance evidence. | MED | Feed autonomous actions into evidence for change-management controls. Defer unless cheap. |

#### Anti-features

| Anti-feature | Why requested | Why problematic | Alternative |
|--------------|---------------|-----------------|-------------|
| Editable or deletable activity records | Tidy up. | Defeats audit; the ledger is append-only. | Undo creates a new linked record. |
| AI-generated "reason" shown as fact | Nicer prose. | A 3B model can misstate why. | Show rule id and evidence first; AI summary second, labelled. |
| Real-time everything (websocket stream of every probe) | Dashboard feel. | Load on a 2 vCPU VM. | Poll or refresh on demand; websocket only for pending approvals. |
| A separate new audit store | Isolation. | Two truths. | The decision record is the view, the ledger is the proof; link them. |

---

## Feature Dependencies

```
Autonomy level + decision function (Cat 1)
    └──requires──> action reversibility classes (playbook "reversible" field)
    └──requires──> single action classification (retire conflicting backend_safety tables)
    └──requires──> global stop switch read at dispatch time

Security response auto-run (Cat 2)
    └──requires──> decision function
    └──requires──> new Rust agent actions: quarantine_file, restart_service, isolate_host (+ inverses)
                       └──requires──> agent release + per-tenant agent capability gates (C6)
    └──requires──> never-touch list, blast-radius caps
    └──enhances──> auto-expiry sweeper (needs scheduler)

Staged patching (Cat 3)
    └──requires──> decision function (reboot = destructive approval)
    └──requires──> real health signal (heartbeat return, service check, new alerts)
    └──requires──> working rollback in deployment_service.trigger_rollback (verify first)
    └──enhances──> maintenance windows (Change Management)

Self-healing (Cat 4)
    └──requires──> out-of-process watchdog (user installs on VM)
    └──requires──> working notification channel (SMTP/Slack currently unconfigured on this VM)
    └──requires──> scheduler for retention + cert/disk probes
    └──enhances──> service desk (Ollama down means fallback)

Service desk (Cat 5)
    └──requires──> decision function (level mapping, sent-answer rules)
    └──requires──> KB with usable content per tenant (RAG store; seed or ingest first)
    └──requires──> escalation rules (reuse tickets_escalation_service + SLA)

Activity view (Cat 6)
    └──requires──> decision-record collection written by everything above
    └──requires──> undo registry (stored inverse per action)
    └──enhances──> every category (shows value, tunes rules)

LLM summaries ──enhances──> Activity view and incident cards (never required by any of them)

Auto-approve by confidence ──conflicts──> locked "destructive waits for a click"
Legacy run_cycle / generate_plan (LLM scripts) ──conflicts──> "no LLM in execution path"
```

### Dependency Notes

- **Everything requires Category 1 and Category 6's record format first.** Without one decision function and one decision record, each domain would invent its own gate and its own log, which is the situation `backend_safety.py` and the legacy remediation cycle already show.
- **Security response is gated on an agent release.** The shipped Rust agent has `block_ip` and `unblock_ip` and `disable_service`/`enable_service`, so "block IP" can be auto-run with only a backend change. `quarantine_file`, `restart_service`, `isolate_host` and a reboot action need agent code and a published build, which the user rolls out. Plan the backend rule and the agent action as a pair and keep the rule dormant until the capability is advertised by the agent.
- **Patching gate quality depends on the health signal, not the UI.** A "health check" that only reads the install exit code is not a health gate.
- **Self-healing cannot be fully delivered by code in the repo.** The watchdog units and any restart permission are applied on the VM by the user; the repo ships the files and a verification checklist.
- **Service desk depends on KB content.** Zero KB articles means everything escalates; that is correct behaviour but means no visible value, so seed content and a "KB coverage" indicator matter.
- **Retention must not eat the evidence.** Scheduling retention (Cat 4) before autonomy records have their own collection and floor (Cat 6) would silently shorten the audit trail.

---

## MVP Definition

### Launch With (v4.3 core)

- [ ] Autonomy level per tenant + global stop + decision function + reversibility classes + never-touch list + blast-radius caps — everything else depends on it.
- [ ] Decision-record collection + Activity view with Pending/Done/Undone/Failed/Refused, approve/deny, undo — the operator's window into autonomy.
- [ ] Security response: block IP auto (existing agent action) with TTL expiry and undo; kill_process / restore_file / patch reboot through approval; remove or fence the confidence bypass and the legacy LLM path.
- [ ] Self-healing: external watchdog for backend, MongoDB, Ollama with budget; disk and cert warnings; scheduled retention with dry-run and delete guard; on-call tiers with ack timeout and alert-channel test.
- [ ] Staged patching: rings, maintenance window, health gate that halts, rollback where supported, per-stage reboot approval.
- [ ] Service desk: KB-only answers with citation, rule-based escalation, draft-for-agent in Suggest mode, "AI-assisted" label.

### Add After Validation (v4.3.x)

- [ ] New agent actions quarantine_file, restart_service, isolate_host with inverses — after the agent release path is proven for block_ip.
- [ ] Circuit breaker auto-downgrade, per-rule stats, incident grouping, known-bad patch list.
- [ ] KB gap detection and deflection analytics.
- [ ] Digest email, hours-saved estimate, disk fill forecast.

### Future Consideration (v5+)

- [ ] Per-tenant custom rules or tenant-authored playbooks (needs a tested rule sandbox).
- [ ] Full on-call product (calendars, swaps) — integrate PagerDuty/Opsgenie instead.
- [ ] Autonomous actions as compliance evidence.
- [ ] Any self-learning or LLM-assisted rule tuning.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Autonomy level + decision function + stop switch | HIGH | MEDIUM | P1 |
| Reversibility classes and single action table | HIGH | LOW | P1 |
| Decision record + Activity view with undo | HIGH | MEDIUM | P1 |
| Never-touch list and blast-radius caps | HIGH | MEDIUM | P1 |
| Auto block IP with TTL and undo | HIGH | LOW-MEDIUM | P1 |
| Destructive approval card (kill, reboot) | HIGH | LOW | P1 |
| Watchdog + restart budget + alert on exhaustion | HIGH | MEDIUM | P1 |
| Disk and certificate warnings | HIGH | LOW | P1 |
| Scheduled retention with guard | MEDIUM | MEDIUM | P1 |
| On-call tiers with ack timeout | HIGH | MEDIUM-HIGH | P1 |
| Staged rollout with health-gate halt | HIGH | HIGH | P1 |
| Auto rollback on failed gate | HIGH | HIGH | P1 |
| KB-only first-line answer + rule-based escalation | HIGH | MEDIUM | P1 |
| New agent actions (quarantine, restart, isolate) | HIGH | HIGH | P2 |
| Corroboration rules | MEDIUM | MEDIUM | P2 |
| Circuit breaker | MEDIUM | MEDIUM | P2 |
| Maintenance windows from Change Management | MEDIUM | MEDIUM | P2 |
| Incident grouping | MEDIUM | MEDIUM | P2 |
| KB gap detection | MEDIUM | MEDIUM | P2 |
| Digest and hours-saved | LOW-MEDIUM | LOW | P3 |
| Disk forecast | LOW-MEDIUM | LOW | P3 |
| Compliance mapping of actions | LOW-MEDIUM | MEDIUM | P3 |

**Priority key:** P1 must have for launch, P2 should have, P3 nice to have.

---

## Competitor Feature Analysis

| Feature | Microsoft Defender AIR | SentinelOne / CrowdStrike | Tanium / Intune / Autopatch | PagerDuty | Service-desk AI (ServiceNow, Freshservice, Zendesk) | Our approach |
|---------|------------------------|---------------------------|-----------------------------|-----------|------------------------------------------------------|--------------|
| Autonomy levels | Full / Semi variants / None per device group | Protect vs Detect policy; Fusion human-input step | Rings plus manual approvals | n/a | Per-intent thresholds | Off / Suggest / Undoable-auto per tenant, plus four domain toggles |
| Approvals | Pending tab, 7-day timeout counts as reject | Analyst approval step in workflow | Approval gates between rings | Ack | Draft for agent | One-click, expires to deny |
| Undo | History tab, bulk "all instances" | Rollback, lift containment | Pause and rollback via reporting | n/a | Follow-up reply | Undo on every undoable row, inverse stored at action time |
| Halt all | Turn level to None | Policy to Detect | Pause rings | Maintenance windows | Disable bot | Global stop checked at dispatch plus per-tenant pause |
| Blast radius | Per device group | Per policy and group | Ring size, canary | n/a | n/a | Per-decision asset cap, per-hour cap, concurrency lease, never-touch list |
| Audit/activity | Action Center | Activity feed | Update reports | Incident log | Conversation log | Decision record + hash-chained ledger link |
| Decision engine | Cloud ML plus rules | ML plus rules | Telemetry-based | Rules | LLM plus retrieval | Fixed tested rules only; LLM summarises |

---

## Sources

- Microsoft Learn, "Automation levels in automated investigation and remediation" (fetched 2026-10-25; page updated 2026-08-14). HIGH: levels, Pending/History, 7-day timeout, undo, 2026-09-01 change. https://learn.microsoft.com/en-us/defender-endpoint/automation-levels
- Microsoft Learn Action Center review and undo guidance (via search results). MEDIUM-HIGH.
- Recast Software, Windows Autopatch article and Intune update rings blog (via search). MEDIUM-LOW: Autopatch pause-on-failure thresholds are not documented in the retrieved Microsoft pages, so thresholds here are our own design.
- CrowdStrike Tech Hub human-in-the-loop containment pattern, Falcon Fusion human-input and scheduling blog (via search). MEDIUM. SentinelOne protect/detect from a third-party runbook. LOW-MEDIUM.
- Kubernetes CrashLoopBackOff references (Komodor, GKE docs, Netdata via search). MEDIUM-HIGH for the 10s-to-5min backoff and 10-minute reset. systemd `Restart`/`StartLimit*` from background knowledge, not re-verified. MEDIUM.
- PagerDuty Escalation Policy Basics and community posts, GitLab handbook (via search). MEDIUM: default 30-minute timeout, repeat up to nine times, ack stops escalation.
- Service-desk deflection guides (eesel.ai, Darwin, Auralis) via search. LOW-MEDIUM, vendor blogs: three confidence bands, escalation triggers. The Zendesk escalation-cause percentages and the "37% more likely" figure could not be verified and are NOT relied on.
- Codebase reading (HIGH), all in this repo: `backend/autonomous_remediation_service.py`, `backend/playbooks/*.yaml`, `backend/remediation_playbook_service.py`, `backend/remediation_control_endpoints.py`, `backend/remediation_audit_service.py`, `backend/backend_safety.py`, `backend/deployment_service.py`, `backend/retention_service.py`, `backend/audit_ledger.py`, `backend/notification_service.py`, `backend/rag_service.py`, `backend/scheduler.py`, `backend/health_service.py`, `agent-install/omni-agent-rs/src/instructions.rs`, `.planning/PROJECT.md`.
- Research method note: the GSD research-plan/research-store seam was not run; searches used the built-in WebSearch/WebFetch and confidence tiers above were assigned manually.

---
*Feature research for: Autonomous Ops (milestone v4.3)*
*Researched: 2026-10-25*
