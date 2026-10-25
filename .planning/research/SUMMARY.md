# Project Research Summary

**Project:** Enterprise OmniAgent (Omni-Agent AI), milestone v4.3 Autonomous Ops
**Domain:** Policy-gated autonomous operations (security response, staged patching, platform self-healing, AI first-line service desk) added to an existing multi-tenant MSP security/compliance/ITAM platform (FastAPI + MongoDB + Rust/Python endpoint agents, one 2 vCPU / 7 GB / no-GPU systemd VM)
**Researched:** 2026-10-25
**Confidence:** MEDIUM-HIGH (HIGH on codebase facts; MEDIUM on CPU LLM latency, patch reversibility, vendor-pattern thresholds)

**Naming rule (locked):** the feature is "Autonomous Ops". Never "ASI", never "Autopilot" (Windows Autopilot already exists as `autopilot_service.py`). UI copy says "automatic within limits you set" and "needs your approval", not "AI-driven".

**Locked decisions (not reopened):**
1. Per-tenant level Off / Suggest / Undoable-auto, default Undoable-auto. Undoable actions (block IP, quarantine file, restart a service) run on their own. Destructive ones (isolate host, kill process, patch reboot) wait for one approval click.
2. All four scopes ship: security response, staged patching (halt + rollback), platform self-healing, service desk.
3. Fixed, tested rules choose every action. The local LLM only summarises and suggests.
4. v4.3 phases start at 81. v4.2 phases 78-80 stay open and resume later.

## Executive Summary

Autonomous Ops is composition, not greenfield. The platform already has a v3.4 remediation engine (YAML playbooks, approval gate, rollback-on-verify-fail, immutable audit), a staged patch-deployment service, a hash-chained audit ledger, an agent instruction queue, tenant-scoped RAG and a per-tenant feature-switch catalogue. All four researchers agree: zero new backend runtime dependencies, zero new Rust crates. What is new is one code-owned policy gate every autonomous action must pass, one decision ledger feeding an Activity view with undo, a root-owned external watchdog, new agent verbs, and deterministic rules for patch gating and ticket answering. Mature products (Defender AIR, Falcon Fusion, Intune/Autopatch rings, PagerDuty, ServiceNow deflection) converge on named levels, pending/history split, undo on history, restart budgets and confidence bands that escalate. We copy that shape and replace their ML verdicts with fixed rules.

Headline risk: **the engine is not safe to switch on today.** Orchestrator-verified: the scheduled loop (`backend/app_background_tasks.py:33` -> `AutonomousRemediationService.run_cycle`) calls `generate_plan` (LLM fix proposal / agentic tool choice) and `execute_plan`, which never checks `plan.requires_approval`. It is held back only by `AUTONOMOUS_REMEDIATION_DRY_RUN` (default true) AND the tenant feature string `autonomousRemediation`, which 0 tenants have and no switch catalogue offers. Live DB: 0 autonomous `agent_instructions`, 0 `agent_ai_decisions`; nothing has ever run. Flipping the env var and ticking that string would put LLM-authored scripts on endpoints with no approval, breaking locked decision 3. Phase 81 must fence that path and put a single gate in front of every autonomous dispatch. Other structural risks: a boolean `destructive` flag that contradicts the locked split (every vendored playbook including `block_ip` is marked destructive), agent verbs the Rust agent lacks (`restart_service`, `quarantine_file`, `isolate_host`, reboot), and a watchdog that fails if it lives inside the backend it must restart.

Constraints on every phase: Ollama is NOT installed on this VM (no `ollama.service`; configured model `llama3.2:3b`); VM is 2 vCPU / 7 GB / no GPU. Every flow must work with the LLM absent, LLM work is async with concurrency 1, and a Mock-provider answer must never reach a customer. Applying anything on the live VM (units, drop-ins, env flips, backend restarts, agent publishing, installing Ollama) is the user's step; the repo ships artefacts plus a checklist. Recommended approach: ship inert (env dry-run floor on = shadow mode), let the user watch would-have-done decisions in the Activity view, then lift per tenant.

## Key Findings

### Recommended Stack (STACK.md)
Add nothing heavy; everything is in `backend/venv`. APScheduler stays 3.x (3.10.4; 4.x alpha-only). Mongo (not optional Redis) is authoritative for stop switch and autonomy state. Rejected: rule engines (json-logic/CEL/OPA), Prometheus/Monit, `sdnotify`/`systemd-python`, Celery, vendor on-call SDKs, new Rust crates, rerankers, 7B+ models.

**Core technologies:**
- Pure-Python decision function plus code-owned action registry: fixed, exhaustively testable rules.
- MongoDB (motor/pymongo, mongod 8.0.34): new tenant-scoped collections only (ledger, settings, watchdog events, ticket AI attempts).
- systemd 255 timer + oneshot watchdog: external, root-owned, stdlib core; optional backend `sd_notify` drop-in (about 15 in-house lines, `WatchdogSec=90`).
- Existing `autonomous_remediation_service`, `remediation_playbook_service`, `deployment_service`, `audit_ledger`, `distributed_lock`: reused for execution, rollback, audit, single-runner.
- PagerDuty Events v2 via existing connector (stable `dedup_key`) or plain webhook; stdlib `urllib` in the watchdog.
- Chroma + `rag_service` + single-shot `ai_service.generate_text`; no LangChain agent loop; deterministic retrieval threshold + guardrails decide answer vs escalate.
- Rust agent: new `instructions.rs` handlers with std + existing helpers.
- Optional dev-only `hypothesis` for property tests of safety invariants.

Critical version/ops facts: keep the `GLIBC_TUNABLES` mongod drop-in and verify restarts with Mongo `ping` (SERVER-121912, kernel 7.0). Use `cryptography` `not_valid_after_utc`. Ollama env for this box: `NUM_PARALLEL=1`, `MAX_LOADED_MODELS=1`, ctx 2048-4096. `OllamaProvider` timeouts (60 s generate, 15 s configure) fail on a cold CPU model and silently fall back to Mock, so parameterise them.

### Expected Features (FEATURES.md)
**Must have:** per-tenant level as the single source of truth (env dry-run becomes a global ceiling); one `decide()` and one reversibility table; global stop checked at every dispatch (fail closed, flippable without the UI); decision record + Activity view (Pending/Done/Undone/Failed/Refused/Suggested) with approve/deny/undo, approvals expiring to deny, inverse stored at action time; blast caps and never-touch list; security response with fixed rules, auto block-IP with TTL and undo, destructive cards, verify-after-action; staged patching with rings, soak, maintenance window, real health gate (no signal = halt), revert where supported, one reboot approval per stage, preflight; self-healing with out-of-process watchdog, restart budget + backoff + page, expected-state registry (Ollama intentionally off), cert (30/14/7/1) and disk (80/90/95) warnings, scheduled retention with dry-run and delete guard, on-call alerting with channel test, dead-man's switch; service desk with KB-only cited answers, rule-based escalation, three outcomes, "AI-assisted" label, confirm-before-close, Ollama-down fallback.
**Should have:** circuit breaker to Suggest, shadow records, corroboration rules, incident grouping, failure-rate gate with min sample, per-rule stats, KB-gap detection, digest, hours-saved.
**Defer (v4.3.x / v5+):** per-tenant custom rules, full on-call product, compliance-evidence mapping, self-learning, disk forecast, known-bad patch list.
**Refuse outright:** confidence-score auto-approval, LLM-chosen action/target/params, auto-reboot, auto-delete to free disk, cert auto-renewal (agents pin the cert), cross-tenant autonomy, editable activity records, AI acting on ticket text, answers without a KB source.

### Architecture Approach (ARCHITECTURE.md)
New package `backend/autonomous_ops/`. `gate.decide()` is the only door to AUTONOMOUS dispatch, with a second enforcement point at agent delivery (`hold_back_autonomous` beside `agent_capabilities.hold_back` in both poll endpoints) so the stop also catches queued instructions. Human-initiated routes are deliberately not retrofitted. Registry is in code; a YAML `destructive` flag may only raise a class. `autonomy_actions` state machine is mirrored one-way into `audit_ledger`. Undo is a new gated child action plus a suppression. Dispatch/verify become resumable reconciler states. Host watchdog is a second enforcement point with a root-owned allowlist and stop read from Mongo, a cached file, or a STOP file. AST/grep test forbids LLM imports and direct `agent_instructions` writes in the package except named modules.

**Major components:**
1. settings + registry + gate + ledger + reconciler: policy core, stop, decision records, resumable verify.
2. `security_response` sweep: replaces legacy `run_cycle`; native finding types only (nscan malicious, agent vuln, FIM) through deterministic `remediate()`.
3. `patch_rollout` ring controller over existing `new_patch_job`/`patch_instruction`/`trigger_rollback`.
4. Host `omni-watchdog` (stdlib) + `selfheal` ingest + `retention_job` (per-tenant, EXCLUDES `audit_logs`).
5. `service_desk` sweep (single-shot RAG, rule decision) + `summarizer` (sole LLM-importing module, decoration only).
6. Catalogue wiring (screen, switch, permissions, mount, platform-only stop route), migration 024 (indexes only), `agent_capabilities._INSTRUCTIONS` mapping for every new instruction (unmapped names bypass per-tenant capability ticks).

Integration facts: about 25 call sites write `agent_instructions` directly; `soar_engine` and `swarm_service` write `db.instructions`, which ARCHITECTURE found no reader for (so dead ends, not to be reused). Sweeps run as platform-admin and bypass wrapper auto-stamping: set `tenantId` explicitly and reset tenant context in `finally` per iteration.

### Critical Pitfalls (PITFALLS.md, 35 listed)
1. **Legacy LLM path goes live when dry-run flips.** New loop calls `remediate()` only; hard-disable/delete `generate_plan`/`execute_plan` LLM paths; test that only playbook-sourced instructions reach the queue. Do first.
2. **Policy bypass via many enqueue sites.** Autonomous-origin choke point, structural allowlist test, fence `propagate-antibody`/SOAR plugins.
3. **Classification wrong in code.** YAML and `backend_safety.py` contradict the locked split, and `AUTO_APPROVE_CONFIDENCE_THRESHOLD = 0.90` lets approval-required actions proceed. Code registry (class + undo pairing), pin each action in tests, remove the confidence bypass for autonomy paths.
4. **Containment severs the control channel; verification rolls back correct blocks.** Protected-target list at enqueue plus agent-side refusal, agent-side TTL with dead-man revert, per-action `verify:` blocks (a successful `block_ip` today can be rolled back because the IP verdict does not change).
5. **Watchdog blind to its own host, restart loops, privilege creep.** External root-owned timer, restart budget + backoff then page once, expected-state registry, scoped allowlist, app never edits sudoers/units.
6. **Retention and scheduling destroy evidence or double-run.** Exclude the ledger, bounded batches, manual dry-run first, locks with renewal.
7. Also load-bearing: stale health signals (`monitor_agent_status` effectively runs hourly), "rollback" that is not one, approval races/fatigue, stop switch only stopping new decisions, write-ahead audit, prompt injection and hallucinated answers, alert storms, over-claiming, default-on for existing tenants.

## Where the Research Files Disagree (and the ruling)

| Topic | Positions | Recommendation and reason |
|---|---|---|
| Phase order | STACK: agent actions second. ARCHITECTURE: core, watchdog, security, patching, desk, hardening. FEATURES: self-healing third. | Use ARCHITECTURE's order. Watchdog second: needs no agent binary, exercises ledger/stop/alert path on low-risk actions, protects the VM. STACK's "agent actions early" is honoured as a PARALLEL Rust track started in Phase 81 (verbs only matter once the gate exists). FEATURES' "self-healing third" loses because it assumes security response precedes a proven core. |
| block_ip classification | STACK: override YAML `destructive: true` from registry. FEATURES: separate `reversible` field. PITFALLS: `risk_tier` + `undo_action`. ARCHITECTURE: code registry, YAML may only raise. | One mechanism: code registry with `approval: auto|approve`, `undo`, `blast_unit`, `cooldown`. `block_ip` = auto, undo `unblock_ip`. YAML may only raise to approve. Auto-run requires an undo that exists on the agent (agent version gate) or an explicit no-inverse entry. Retire the conflicting tables in `backend_safety.py` (it lists `kill_process` SAFE and `restart_service` APPROVAL_REQUIRED, the opposite of the lock). |
| restart_service "undoable" | Lock says undoable; STACK gives an inverse; ARCHITECTURE says no inverse. | Auto-class with restart budget, no Undo button. Needs user ack (D5). |
| Patch install auto? | ARCHITECTURE: ring `install_patches` auto in window with `rollback_patches`. PITFALLS: re-tier `patch_package` approval-required (`rollback: []`, Windows updates often irreversible). | Auto only for the canary ring, in window, when the patch class is marked reversible; anything broader or non-reversible waits for one per-stage approval. Reboot always one approval per stage. User confirms (D10). |
| Choke-point scope | PITFALLS: migrate all about 46 insert sites. ARCHITECTURE: autonomous origins only. | ARCHITECTURE's scope plus PITFALLS' structural allowlist test. Human actions stay unthrottled but audited. |
| propagate-antibody / SOAR | PITFALLS: dangerous fan-out to cap/migrate. ARCHITECTURE: writes `db.instructions`, no reader. | Dormant dead ends; fence, do not extend. Re-run the grep when planning Phase 83. |
| Watchdog implementation | STACK: venv interpreter + optional pymongo/cryptography. ARCHITECTURE: stdlib only. | Stdlib-only core (works with a broken venv); guarded optional imports. |
| Dry-run precedence | STACK floor; FEATURES ceiling; ARCHITECTURE shadow switch default true; PITFALLS observe-first. | Compatible: env stays a hard extra deny (shadow records only) until the user flips it; DB per-tenant level is the real policy; show "simulation mode" in Activity; ship with floor on. |
| Audit design | ARCHITECTURE: ledger state machine mirrored to `audit_ledger`. PITFALLS: write-ahead intent. | Both: write intent first (enqueue fails if it fails), mirror every transition, no fourth store; decision records get own collection and a retention floor above generic retention. |
| New agent verbs timing | FEATURES: v4.3.x. Others: required now. | Required now (lock names quarantine and restart). Ship `block_ip` (exists) first; new-verb rules dormant until the agent advertises the capability. |
| On-call depth | FEATURES: tiers/ack/repeat. STACK/ARCHITECTURE: webhook/PagerDuty with dedup key. | Webhook/PagerDuty out of band + channel test + "no working channel" banner. No in-house tier product. |

## Implications for Roadmap

### Phase 81: Policy gate, ledger, stop switch, legacy-path fence, read-only Activity
**Rationale:** everything depends on one decision function and record; only phase that closes the live hazard.
**Delivers:** `autonomous_ops` core; per-tenant level + platform stop (platform-only route/permission, STOP file); delivery hook in both agent poll endpoints; write-ahead intent + audit mirror; never-touch list, blast caps, idempotency key, protected targets; shadow mode; read-only Activity list; catalogue/switch/permission/mount wiring; migration 024 (indexes + explicit level for existing tenants); `agent_capabilities._INSTRUCTIONS` mappings; AST/grep test; remove/hard-disable `generate_plan`/`execute_plan` LLM paths and the confidence bypass; scheduler hardening (lock renewal, per-iteration tenant reset); fix `is_duplicate_task` tenant filter; `monitor_agent_status` cadence fix. **Parallel track:** start Rust/Python agent verb work and parity matrix.
**Avoids:** Pitfalls 1, 2, 3, 4, 8, 17, 18, 19, 20, 25, 34.

### Phase 82: Platform self-healing and scheduled retention
**Rationale:** no agent binary needed; validates ledger/stop/alert end to end on low-risk actions; protects the VM.
**Delivers:** `omni-watchdog` timer/oneshot + unit files and drop-ins as templates (user installs); restart budget/backoff/flap guard, expected-state registry, debounce, dead-man's switch; disk and cert warnings (warn only); out-of-band webhook/PagerDuty with `dedup_key` and channel test; watchdog-event ingest (platform scope only); app-level checks; scheduled per-tenant retention in bounded batches excluding audit/decision collections (first live run manual after dry-run); `next_scheduled`; alert-storm grouping.
**Avoids:** Pitfalls 10, 13, 14, 15, 16, 23, 29, 31.

### Phase 83: Security response (autonomous, with undo)
**Rationale:** longest agent lead; establishes undo, dedupe, suppression, blast radius that rings reuse.
**Delivers:** `security_response` sweep replacing `autonomous_remediation_loop`; `remediate()` through the gate; new `ACTION_MAP` entries and playbooks with `verify:` blocks; auto `block_ip` with TTL and agent-side dead-man revert; quarantine-not-delete; restart with budget; destructive cards (kill/isolate) with expiry; undo with pre-state capture and refcounting; corroboration rule, cascade guard, FIM/patch interlock; fence `propagate-antibody`/SOAR; agent publish + capability gating; digest notifications.
**Avoids:** Pitfalls 3, 4, 5, 6, 7, 8, 30, 35.

### Phase 84: Staged patching with halt and revert
**Rationale:** most stateful, hardest to verify; needs gate, undo, blast caps, reboot verb.
**Delivers:** `patch_rollouts`; ring controller (canary covers OS/role, min 1 host, cap); per-tenant window/timezone; preflight; composite health gate (instruction result + post-install inventory + new boot-id heartbeat + services; no data = halt); halt + auto-revert via extracted rollback service function; one reboot approval per stage; instruction `expires_at`; one active rollout per host; platform-host agent excluded; resumable state; wording "halts on failure; reverts where supported"; per-OS revert matrix.
**Avoids:** Pitfalls 9, 10, 11, 12, 23, 30.

### Phase 85: Service desk first line
**Rationale:** independent after 81, low blast radius, but needs KB content and Ollama; may swap with 84 if those land sooner.
**Delivers:** async sweep (concurrency 1), single-shot tenant-scoped RAG, deterministic answer/draft/escalate rules (retrieval floor, citation validation, category allowlist, never security/billing/legal), Suggest = internal-note draft, "AI-assisted" label, confirm-to-close, once-only answer, Jira/ServiceNow echo suppression, link/HTML stripping, Mock-provider guard, per-call timeouts + `keep_alive`, Ollama-down escalation, help-desk KB seeding + coverage indicator, injection and eval sets (100% escalation out-of-KB).
**Avoids:** Pitfalls 21, 22, 31.

### Phase 86: Activity completion, hardening, live validation
**Delivers:** undo buttons from `undoable_now`, filters, grouped approval cards and metrics, digest, export, banned-terms copy lint, kill-switch drills (queued instructions, pending approvals, rollouts, AI replies), observe-first soak and per-tenant lift (user step), two-tenant contract tests per loop, named live-only verification list.
**Avoids:** Pitfalls 8, 20, 24, 33, 35.

### Phase Ordering Rationale
- Core first: divergent gates are already the repo's defect class (two classification tables, two audit stores, two queues).
- Watchdog before security (no agent release needed); security before patching (undo/dedupe/blast radius carry over); patching last of the actors (least verifiable).
- Agent Rust work starts in 81; rules stay dormant until the agent advertises the capability.
- Ship inert (env floor on) so the user observes before enabling.

### Research Flags
Needs `/gsd-plan-phase --research-phase <N>`:
- **Phase 83:** cross-platform agent semantics (idempotent firewall rules, refcounted undo, `netsh` vs Defender heuristics, native APIs, isolate with management carve-out), per-action verify.
- **Phase 84:** per-OS patch reversibility matrix; health-gate signals; confirm `trigger_rollback` dispatches real agent work (OS patching was fake end to end until 2026-10-12).
- **Phase 85:** measure llama3.2:3b CPU tokens/s once Ollama exists; calibrate Chroma threshold; build injection/eval sets.
- **Phase 82:** light only: polkit/sudoers scoping, watchdog Mongo auth path (Mongo auth still an open readiness item).

Standard patterns (skip research): Phase 81 (internal composition over code already read), Phase 86 (UI/tests/copy lint).

## Decisions Needed from the User (deduplicated; B-plan blocks planning, B-live blocks go-live only)

| # | Decision | Source | Blocks |
|---|---|---|---|
| D1 | Confirm "eligible for autonomy = Super Admin ticked the Autonomous Ops screen switch" (new tenants stay Overview-only). | ARCH | 81 B-plan |
| D2 | Existing tenants: explicit stored level at migration + observe-first soak (env floor on, platform-wide Suggest/shadow first days); who lifts it and when. Default unchanged. | PITFALLS, ARCH | 81 B-plan, 86 B-live |
| D3 | Who may change a tenant's level vs approve actions (separate manage/approve permissions; Super Admin cap on max level); who may flip the platform stop. | PITFALLS, ARCH | 81 B-plan |
| D4 | Remove or hard-disable legacy `generate_plan`/`execute_plan` LLM path and the `AUTO_APPROVE_CONFIDENCE_THRESHOLD` bypass (recommend yes to both). | ARCH, PITFALLS, FEATURES | 81 B-plan |
| D5 | `restart_service` auto with restart budget and no Undo button (no inverse); confirm this satisfies "undoable". | ARCH vs STACK | 83 B-plan |
| D6 | Class of `disable_service`, `restore_file`, `rotate_key` (recommend approve; revisit `disable_service`, which has a rollback). | ARCH, FEATURES | 83 B-plan |
| D7 | Defaults: block TTL (24 h proposed), approval expiry (24 h proposed; Defender uses 7 d), blast caps, single-IP-only auto blocks (ranges need approval), corroboration on/off. | FEATURES, PITFALLS | 83 B-plan |
| D8 | `propagate-antibody` and SOAR block/isolate plugins: fence dormant (recommended) or migrate behind the gate. | PITFALLS vs ARCH | 83 B-plan |
| D9 | Publish and roll out the new Rust agent; test quarantine/isolate/block on real Windows with Defender (EILT0197). User steps. | STACK, FEATURES, PITFALLS | 83 B-live |
| D10 | Ring `install_patches`: auto for canary when class is reversible, else per-stage approval (recommended), vs always approval; which patch classes count reversible (default Linux only where previous version confirmed installable; Windows non-reversible). | ARCH vs PITFALLS | 84 B-plan |
| D11 | Maintenance window source: Change Management / `maintenance_service` vs per-tenant setting; default timezone. | FEATURES, STACK | 84 B-plan |
| D12 | Confirm platform host's own agent is excluded from autonomous patching/self-heal (patched manually). | PITFALLS, FEATURES | 84 B-plan |
| D13 | UI wording "halts on failure; reverts where supported" rather than unqualified "rollback". | PITFALLS | 84 B-plan |
| D14 | On-call channel: PagerDuty, Slack/Teams webhook, or email (SMTP unset on this VM; needs a root-only env file the user fills in). | ARCH, STACK, PITFALLS | 82 B-live |
| D15 | User installs watchdog units, mongod/omni-backend drop-ins, any scoped sudoers/polkit rule, and Mongo credentials for the watchdog. Never `run-on-ubuntu.sh` (ufw SSH lockout). | STACK, ARCH, PITFALLS | 82 B-live |
| D16 | First scheduled retention run manual after dry-run count; minimum retention floor for decision records and compliance evidence. | PITFALLS, FEATURES | 82 B-live |
| D17 | Install Ollama + pull `llama3.2:3b` (user step) and accept tens-of-seconds CPU latency with a concurrency-1 queue, or choose Gemini/Anthropic providers for the desk. | STACK, ARCH | 85 B-live |
| D18 | Desk default at Undoable-auto: qualifying answer auto-posts (ARCH) or posts as draft (PITFALLS, safer)? Default category allowlist; who supplies help-desk KB articles (seed content is security-only). | ARCH vs PITFALLS, FEATURES | 85 B-plan |
| D19 | Apply migration 024 and restart the backend (user step; backend runs from checkout); flip the env dry-run floor off per tenant only after observe-first. | ARCH | 86 B-live |
| D20 | Optional dev dependency `hypothesis` for property tests. | STACK | 81 non-blocking |

## Confidence Assessment

| Area | Confidence | Notes |
|---|---|---|
| Stack | HIGH (reuse), MEDIUM (CPU LLM latency) | Versions verified from live venv and repo; systemd/PagerDuty/Ollama from official docs; no measured CPU llama3.2:3b figure exists, so Phase 85 must measure. |
| Features | MEDIUM-HIGH | Defender levels verified on Microsoft Learn; ring thresholds, PagerDuty tiers, deflection bands rest on vendor blogs and are our own design values; codebase claims read directly. |
| Architecture | HIGH (integration points), MEDIUM (watchdog privilege, agent parity) | File/function references with `git grep` confirmation; watchdog privilege model and Python-vs-Rust verb parity need a live check. |
| Pitfalls | HIGH (codebase-sourced), MEDIUM (external) | Engine defects read from source; legal/FTC/OWASP items are secondary coverage. |

**Overall confidence:** MEDIUM-HIGH. The highest-risk behaviours (firewall state, reboots, patch revert, CPU LLM, systemd) are live-only and cannot be proven by unit tests.

### Gaps to Address
- CPU LLM latency and threshold calibration: measure in Phase 85 after Ollama install; design async-only until then.
- `trigger_rollback` real behaviour: verify before Phase 84 promises "revert".
- Agent verb parity: Python agent has quarantine/isolate (`autonomous_response.py`, response-task path); Rust has none of the new verbs; build the parity matrix in Phase 81.
- `db.instructions` dead-end claim: re-run grep in Phase 83 planning before fencing.
- Windows reversibility and Defender behaviour: live test on EILT0197.
- Live-only verification list: name it in the roadmap now (firewall round-trip, reboot gate, watchdog stop/start of mongod and backend, alert delivery).
- Heartbeat volume (about 815 MB/day/endpoint) and four agent collections without TTL: known open items; bounded retention (82) helps but does not fix ingestion.

## Sources
**Primary (HIGH):** repo inspection 2026-10-25 (`backend/autonomous_remediation_service.py`, `app_background_tasks.py`, `remediation_playbook_service.py`, `playbooks/*.yaml`, `backend_safety.py`, `deployment_service.py`, `patch_core_endpoints.py`, `deployment_result_endpoints.py`, `agent_tasks_endpoints.py`, `agent_capabilities.py`, `audit_ledger.py`, `retention_service.py`, `distributed_lock.py`, `scheduler.py`, `rag_service.py`, `ai_providers.py`, catalogue manifests, `agent-install/omni-agent-rs/src/instructions.rs`, `/etc/systemd/system/omni-backend.service`); orchestrator-verified facts (2026-10-25) above; Microsoft Learn Defender AIR automation levels; systemd.service man page; PagerDuty Events v2 docs; Ollama FAQ; PyPI metadata; `.planning/PROJECT.md` and project memory notes.
**Secondary (MEDIUM):** Kubernetes/systemd restart backoff references, PagerDuty escalation guides, Falcon Fusion and Intune/Autopatch ring material, OWASP LLM01, CrowdStrike Channel File 291 RCA coverage, Moffatt v. Air Canada (2024 BCCRT 149), FTC Operation AI Comply coverage.
**Tertiary (LOW):** service-desk deflection vendor blogs; CPU-only llama3.2:3b tokens/s (no authoritative measurement); Autopatch pause thresholds (undocumented, our own design).

*Research completed: 2026-10-25. Ready for roadmap: yes.*
