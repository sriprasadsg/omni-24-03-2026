# Stack Research

**Domain:** Autonomous Ops (policy-driven security response, staged patching with health gates, platform self-healing, AI first-line service desk) added to an existing multi-tenant FastAPI/MongoDB/Rust-agent platform
**Milestone:** v4.3 (phases start at 81)
**Researched:** 2026-10-25
**Overall confidence:** HIGH for "reuse what exists / add nothing heavy" (verified by inspecting the repo and the live venv); MEDIUM for CPU-only LLM latency (no measured benchmark found; must be measured on the VM in Phase 1 of the AI work)

> Source-tier note: the `classify-confidence` seam returns LOW for plain WebSearch/WebFetch (no Context7 library in play, no legitimacy verdicts). Claims below tagged HIGH are verified directly against the repo/venv or an official primary document fetched in full; claims tagged MEDIUM/LOW are called out as such.

## Headline Recommendation

**Add zero new runtime dependencies to the backend. Add zero new crates to the agent. Add one new systemd unit pair (external watchdog) and a handful of agent instruction handlers.**

Everything Autonomous Ops needs is already installed in `backend/venv` (verified via `importlib.metadata`): APScheduler 3.10.4, psutil 7.2.2, cryptography 50.0.2, httpx 0.28.1, PyYAML 6.0.3, tenacity 9.1.4, pydantic 2.13.5, jsonschema 4.26.0, pymongo 4.18.2 / motor 3.7.1, chromadb 1.5.9, ollama 0.6.2, langchain-ollama 1.1.0, aiosmtplib 5.1.3. The work in this milestone is **composition and safety logic**, not libraries. The biggest stack-level decision is architectural: **the watchdog must run outside the backend process** (a process cannot reliably restart or page about itself), as a root-owned systemd timer unit using only stdlib plus the already-installed venv.

## Recommended Stack

### Core Technologies (all already present — pinned to what is installed)

| Technology | Version (installed) | Purpose in v4.3 | Why Recommended |
|------------|--------------------|-----------------|-----------------|
| Python / FastAPI / Pydantic | 3.12.3 / 0.141.1 / 2.13.5 | Autonomy policy API, activity view API, rule models | Already the platform spine. Pydantic v2 models double as the validated schema for per-tenant autonomy config and rule definitions. |
| MongoDB (motor 3.7.1 / pymongo 4.18.2) | mongod 8.0.34 | Source of truth for autonomy level, global stop switch, action ledger, undo records, watchdog events | Mongo is already authoritative for tenant settings, `remediation_audit`, `staged_deployments`, `agent_instructions`. Redis is *optional* on this platform, so the kill switch and autonomy state must NOT depend on it. |
| APScheduler | 3.10.4 (keep; 3.11.3 is latest stable) | Wall-clock jobs: scheduled retention (daily cron), patch maintenance windows | Already used (`scheduler.py` uses `AsyncIOScheduler` + `CronTrigger`/`IntervalTrigger` with `distributed_lock`). 4.0 is alpha-only (4.0.0a6, April 2025) with no 3.x job-store migration path, so stay on 3.x. Bumping 3.10.4 to 3.11.3 is optional and unnecessary here; do not take the risk this milestone. |
| `distributed_lock.py` (in-repo) | n/a | Single-runner guarantee for every new periodic job (autonomy evaluator, rollout driver, retention, ticket-answer worker) | Mongo upsert-collision lock with TTL. Reuse exactly the pattern `scheduler.py` and `app_background_tasks.py` use; keep TTL just under the job interval. |
| `autonomous_remediation_service.py` + `remediation_playbook_service.py` (in-repo) | v3.4 | The execution engine for security response. v4.3 adds a *policy layer in front of it*, it does not replace it | Already has dry-run default, approval gate, rollback-on-verify-fail, concurrency cap, immutable audit. YAML playbook `rollback:` blocks are the undo mechanism. |
| systemd | 255 (Ubuntu 24.04) | External watchdog, `Restart=` hardening, service watchdog | `Restart=`, `RestartSteps=`/`RestartMaxDelaySec=` (exponential backoff), `StartLimitBurst`, `WatchdogSec=` all exist in v255 (verified against systemd.service man page). |

### New Components to Build (no new third-party libraries)

| Component | Implementation | Purpose | Why this and not a library |
|-----------|---------------|---------|----------------------------|
| **Autonomy policy engine** | Pure-Python module (`autonomy_policy.py`): frozen dataclasses/pydantic models + a pure function `decide(event, tenant_policy, ledger_state) -> Decision(action, mode, reason_code)` | Maps (action class x tenant level x blast radius x kill switch) to `run` / `needs_approval` / `suggest_only` / `deny` | The decision space is tiny and must be exhaustively unit-testable and auditable ("fixed, tested rules choose every action"). A rules library (json-logic, durable_rules, CEL, OPA) adds an interpreter, a second language, and a larger attack/audit surface for ~6 rules. Table-driven rules in code with a closed enum of action classes (`undoable`/`destructive`) is the safest and most reviewable design. |
| **Action classification registry** | Extend `ACTION_MAP` in `remediation_playbook_service.py` with `class: undoable|destructive` + `inverse:` per action; add new actions (below) | Locks decision 1: block IP / quarantine file / restart service = undoable; isolate host / kill process / patch reboot = destructive | Keeps the existing "every action must resolve in ACTION_MAP or validate() rejects" invariant. Classification lives next to the allowlist so a new action cannot exist without a class. |
| **Global stop switch + autonomy level** | Mongo doc (`platform_settings`/`tenant` field), read with a short in-process TTL cache (<=5 s); plus optional file flag `/var/lib/omni/autonomy.stop` honored by the external watchdog | One switch halts all autonomous execution; per-tenant Off/Suggest/Undoable-auto | Must work when Redis is absent and must fail closed: if the flag read errors, behave as Suggest. File flag lets an operator stop the watchdog's restarts even when the backend/Mongo are down. |
| **Rollout driver + health gate** | New async loop (repo's `asyncio.sleep` + `acquire_lock` pattern) over existing `staged_deployments` (stages test -> dev -> staging -> production); gate evaluator is a pure function over existing agent data | After each stage: wait soak time, check cohort health (agent heartbeat age, post-patch error rate from `deployment_result_endpoints`, key service up, no reboot-pending beyond window); pass -> advance, fail -> halt + call existing `trigger_rollback` | `PatchDeploymentService` already has stages, approvals, `progress_to_next_stage`, `trigger_rollback` (queues `rollback_patches` instructions), and the Rust agent already handles `install_patches`/`rollback_patches`. Missing piece is the *automatic* driver + gate, which is plain code over existing collections. Maintenance windows reuse `maintenance_service.py`. |
| **External watchdog** (`omni-watchdog.service` oneshot + `omni-watchdog.timer`, 60 s) | One Python script using the backend venv interpreter; stdlib for core checks (`socket`, `urllib.request`, `shutil.disk_usage`, `ssl`, `subprocess` -> `systemctl`); `pymongo` ping and `cryptography.x509` only if importable | Checks backend (`/health/ready`), MongoDB (TCP + `ping`), Ollama (`/api/tags`), cert expiry, disk %, restarts allowlisted units, pages on-call | See "Watchdog design" below. Runs as root (or a dedicated user + polkit rule) with `ProtectSystem=strict`, `ReadWritePaths=/var/lib/omni-watchdog`. Writes `state.json` + `events.jsonl`; backend ingests those into Mongo when it is up (so the Activity view shows platform self-healing). |
| **Backend sd_notify heartbeat** | ~15-line in-house helper (AF_UNIX datagram to `$NOTIFY_SOCKET`, send `READY=1` once, `WATCHDOG=1` every `WATCHDOG_USEC/2` from an asyncio task); unit drop-in `Type=notify`, `NotifyAccess=main`, `WatchdogSec=90` | Detects a *hung* event loop (alive PID, dead service) which `Restart=always` cannot | Do not add the `sdnotify` PyPI package: last release 0.3.2 in **2017**, unmaintained, and the protocol is a single `sendto`. Because the ping runs on the loop, a blocked loop stops pings and systemd restarts it (`Restart=always` already set). Ship as a drop-in the user applies (the user owns restarts/units). |
| **On-call alert fan-out** | Reuse `PagerDutyConnector` (`soar_connectors_messaging.py`, Events API v2 `https://events.pagerduty.com/v2/enqueue`), Slack/Teams connectors, `notification_service.send_notification`, `aiosmtplib`; watchdog uses raw `urllib.request` POST | Page when self-healing fails or a restart-flap guard trips; resolve on recovery | PagerDuty Events v2 is already integrated. Rules to follow (official doc): trigger requires `routing_key`, `event_action`, `payload.summary/source/severity`; **always send a stable `dedup_key`** (<=255 chars, e.g. `omni:<host>:<check>`) so repeats collapse and a later `resolve` closes the right alert; resolve with no matching open alert is silently dropped; 429/5xx retry with backoff, 400 do not retry. The watchdog cannot rely on the backend DB or SMTP (unset on this VM), so its channel config is a root-only env file the user fills in. |
| **Scheduled retention** | New loop calling the existing `RetentionService` per tenant (same code path as `POST /api/retention/run`), via `app_background_tasks.py` pattern or an APScheduler `CronTrigger` at a quiet hour (e.g. 03:30 UTC, after the 02:30 backup timer) | Retention on a schedule instead of manual | `audit_maintenance_loop` and `agent_telemetry_retention_loop` already exist as the template. Take a `distributed_lock`, write a ledger entry per run, skip if the backup unit is active. |
| **Cert/disk checks** | Cert: `cryptography.x509.load_pem_x509_certificate(...).not_valid_after_utc` on `/etc/nginx/ssl/omni.crt` (watchdog) plus a sweep over the existing `certificate_endpoints` collection (backend); Disk: `shutil.disk_usage` / `psutil.disk_usage` | Warn at 30/14/7 days; disk warn at 80%, critical at 90% | psutil and cryptography are already pinned; no `pyOpenSSL` calls needed (note: `ssl.get_server_certificate` + `x509` covers remote certs). Disk at 68% used on `/` today (80 GB free), so thresholds will not fire immediately. |
| **First-line ticket answerer** | Background worker (one job at a time, concurrency 1) -> `rag_service.query(..., tenant_id=...)` (Chroma, tenant + global chunks) -> deterministic gate -> **single-shot** `ai_service.generate_text` (Ollama) -> `ai_guardrails.scan_text` on output -> post reply or escalate | Answer routine tickets from the Knowledge Base; escalate when unsure | See "AI on 2 vCPU CPU-only" below. The escalate/answer decision is made by a deterministic retrieval-distance threshold plus guardrails, **not** by asking the LLM how confident it is. |
| **Agent instruction handlers (Rust, `omni-agent-rs`)** | New match arms in `src/instructions.rs` + functions in `src/capabilities/remediation_actions.rs`, **std-only, no new crates**: `restart_service`, `quarantine_file` + `unquarantine_file`, `isolate_host` + `unisolate_host`, `reboot` (patch) | The agent currently supports `kill_process`, `restore_file`, `block_ip`/`unblock_ip`, `disable_service`/`enable_service`, `rotate_key(_rollback)`, `install_patches`/`rollback_patches`. Quarantine, restart, isolate and reboot do **not** exist yet and are required by decision 1 | Reuse `run_privileged_command` (already stubbed under `#[cfg(test)]`), `validate_service_name`, `validate_ip`, and the critical-target denylists. Quarantine = move to a root-owned quarantine dir with mode 000 + JSON manifest (original path, sha256, time); undo = move back. |

### Database

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| MongoDB (existing) | 8.0.34 | New collections only: `autonomy_ledger` (append-only, mirror `remediation_audit_service.py` insert-only pattern), `autonomy_settings`, `watchdog_events`, `ticket_ai_attempts` | No new datastore. Tenant-scoping is enforced by the DB wrapper, so every new collection must carry `tenantId` and go through the wrapper; the watchdog/platform collections are the deliberate exception (use `db._db` raw handle like `distributed_lock.py` does, and document it). Add TTL indexes where retention applies (4 agent collections already lack TTL per the 2026-10-21 data-limits assessment; do not add more untimed collections). |
| Chroma (existing) | 1.5.9 | KB retrieval for first-line answers | Already holds `omni-agent-knowledge` with `tenantId` metadata filter incl. `"global"`. Default embedding function is local ONNX MiniLM (no network at query time after first model download); cheap on CPU. |

### Infrastructure

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| systemd units (new) | systemd 255 | `omni-watchdog.service` (oneshot) + `.timer` (every 60 s, `AccuracySec=10s`, `Persistent=false`); `OnFailure=` on the watchdog unit to ping a "watchdog itself failed" path | Same pattern the platform already uses for `omni-backup.service`/`.timer` (generated by `start-all-services.sh`). A timer-driven oneshot is stateless between runs and cannot hang the way a long-lived daemon can. |
| systemd drop-ins (user applies) | n/a | `mongod.service.d/restart.conf` (`Restart=on-failure`, `RestartSec=5`, `StartLimitBurst`); same for `ollama.service` if/when installed; `omni-backend.service.d/watchdog.conf` (`Type=notify`, `NotifyAccess=main`, `WatchdogSec=90`, `RestartSteps=4`, `RestartMaxDelaySec=60`) | `omni-backend.service` already has `Restart=always`. The stock mongod unit has **no** `Restart=` set (the existing `kernel-rseq-check.conf` drop-in only sets `GLIBC_TUNABLES`), so a crash after the next kernel quirk stays down until someone notices. `Restart=` is the cheapest self-healing and covers crashes; the watchdog covers hangs/unresponsive-but-running. |
| Ollama | 0.40.11 (latest release, 2026-10-24) | Local LLM for summaries/suggestions/first-line drafts | **Not installed on this VM** (`ollama.service` does not exist; `OllamaProvider` falls back to Mock when unreachable). Installing it is the user's step. Server env for this box: `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_KEEP_ALIVE=10m` (or `-1` if RAM allows), `OLLAMA_CONTEXT_LENGTH=4096` (documented default 4096; RAM scales with parallel x context). |

### Supporting Libraries (already installed; use these, do not add alternatives)

| Library | Installed | Purpose | When to Use |
|---------|-----------|---------|-------------|
| psutil | 7.2.2 | Disk/memory/load in watchdog and self-health summary | Disk %, free memory before loading the LLM, load average before launching heavy jobs |
| cryptography | 50.0.2 | Parse PEM certs, `not_valid_after_utc` | Cert-expiry checks (local nginx cert + stored tenant certs) |
| httpx | 0.28.1 | Backend-side HTTP health probes and outbound webhooks | Backend loops; **timeouts must be explicit** (see pitfalls) |
| tenacity | 9.1.4 | Retry/backoff around PagerDuty/webhook sends and agent-instruction polling | Wrap outbound sends: retry on 429/5xx/network, never on 400 |
| PyYAML | 6.0.3 | Playbook loading (already via `remediation_playbook_service`) | Add `class:`/`inverse:` fields to playbooks; always `yaml.safe_load` |
| jsonschema | 4.26.0 | Optional validation of playbook/policy files at load | Playbook files are a trust boundary |
| ollama (python) / langchain-ollama | 0.6.2 / 1.1.0 | Already installed; **do not use for ticket answering** | Existing chat agent uses LangChain `create_agent`; keep it for interactive assistant only |
| Existing PagerDuty/Slack/Teams connectors, `notification_service`, `ticketing_bridge.py`, `tickets_escalation_service.py` | in-repo | On-call + ticket escalation | Escalation of an unsure AI answer = existing priority bump / assignment path, plus Jira/ServiceNow bridge if configured |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| pytest 9.1.1 + pytest-asyncio 1.4.0 (installed; `asyncio_mode = auto` in pytest.ini) | Tests for policy engine, health gate, watchdog | Note: the PROJECT.md key decision says tests use `asyncio.run()`; follow whichever the neighbouring test file uses. |
| **hypothesis 6.170.9** (dev-only, optional new dep, `requirements-dev.txt`) | Property tests for the invariants that matter: "no destructive action ever executes without approval at any level", "kill switch on => zero executions", "blast-radius cap never exceeded", "every executed undoable action has an inverse" | Only dev addition worth considering. Rule engine is small; this is the cheapest way to *prove* the safety invariants rather than sample them. Skip if the dependency-legitimacy gate is a burden; table-driven tests cover most value. |
| freezegun 1.5.5 / respx 0.23.1 (dev-only, optional) | Time-travel for soak timers/cert expiry; mock httpx for PagerDuty | **Not required**: inject a `now()` callable into the pure functions and use `unittest.mock`/a fake transport instead; avoids two more dev deps. |

## Watchdog design (the one real infrastructure decision)

**Placement:** external, root-owned, timer-driven; never inside `omni-backend`. Reason: Autonomous Ops claims "restarts what fails". A backend that watches itself cannot act when it is hung or down, and `omni-backend` runs as `azureuser` and cannot `systemctl restart mongod`.

**Checks (all with hard timeouts <=5 s, whole run <=30 s so the 60 s timer never overlaps; use `flock` or systemd's one-instance-per-unit oneshot semantics):**
1. Backend: `GET http://127.0.0.1:5000/health/ready` (the real readiness probe: pings Mongo, returns 503 on demo/mock-DB fallback). Do **not** use `/health` or `/api/health`, they are static literals.
2. MongoDB: `systemctl is-active mongod` + TCP 27017 + `pymongo` `ping` with `serverSelectionTimeoutMS=3000` (credentials from the root-only env file; Mongo auth is still an open production-readiness item). After any mongod restart verify with ping, not just `is-active`, because of the kernel-7.0 `GLIBC_TUNABLES` history (SERVER-121912).
3. Ollama: `GET http://127.0.0.1:11434/api/tags` if the unit exists, **skip (not alert) if the unit is not installed** so "inactive on this VM" is not reported as an outage.
4. Cert expiry: parse `/etc/nginx/ssl/omni.crt`; warn 30/14/7 days.
5. Disk: `shutil.disk_usage` on `/`, the Mongo dbPath, and the backup dir; warn 80%, page 90%.

**Remediation rules (fixed, no LLM):** restart only an allowlist `{omni-backend, mongod, ollama}`; order-aware (Mongo before backend); **flap guard**: max 3 restarts per 30 min per unit, then stop restarting and page; consecutive-failure debounce (2 failed runs before acting); honor the `/var/lib/omni/autonomy.stop` flag and the per-platform "self-healing off" setting; never restart during the nightly backup unit's active window (`omni-backup.service` active -> skip mongod restart).

**Reporting without the backend:** append JSONL to `/var/lib/omni-watchdog/events.jsonl`; the backend tails it into `watchdog_events` and shows it in the Activity view. Page via PagerDuty Events v2 (stable `dedup_key`, resolve on recovery) or a Slack/Teams webhook using stdlib `urllib`. Dead-man's switch: the backend raises its own alert if `state.json` is older than 3 minutes.

## Autonomy policy and rules evaluation: why plain code

- Action classes: `undoable` (block_ip, quarantine_file, restart_service) vs `destructive` (isolate_host, kill_process, reboot for patching). Playbook YAML for `block_ip` currently says `destructive: true`; **the v4.3 policy layer must override that flag from the registry** (block IP is undoable per locked decision 1) rather than reading the legacy per-step flag. This is a correctness trap, flag it in the plan.
- Decision function inputs: tenant autonomy level, action class, `AUTONOMOUS_REMEDIATION_DRY_RUN`, global stop, blast-radius counter (machines touched per decision/hour, from the ledger), per-agent concurrency (existing `MAX_CONCURRENT_PER_AGENT`), severity ceiling (existing `MAX_AUTO_SEVERITY`).
- Default level is "Undoable-auto" per decision 1, but `AUTONOMOUS_REMEDIATION_DRY_RUN` defaults true in the engine. The policy layer must define precedence explicitly (dry-run env stays the hard floor until the operator flips it; recommend surfacing it in the Activity view as "simulation mode").
- Undo: each ledger entry stores the resolved inverse action + params; "Undo" enqueues the inverse through the same engine path and the same audit trail. Idempotent inverses only.

## AI first-line answering on 2 vCPU / 7 GB / no GPU

- **Latency is the constraint, not accuracy.** 3B Q4 on 2 vCPU is expected in the low single-digit tokens/second range (my estimate; **no measured CPU-only figure was found, treat as LOW confidence and measure on the VM**: `OLLAMA_NUM_GPU=0 ollama run llama3.2:3b --verbose`). A 150-token answer is therefore ~30-60+ s. Consequences:
  - Ticket answering must be **asynchronous**: ticket created -> job row -> single worker -> reply posted. Never in the request path.
  - Hard concurrency of **1**. Interactive assistant chat and ticket answers compete for the same two cores; give the interactive path priority (worker yields if a chat request is in flight).
  - Use **single-shot RAG, not an agent loop**. `ai_assistant_service.chat` uses a LangChain `create_agent` with tools; a 3B model's tool-calling is unreliable and each tool round-trip multiplies CPU time. For tickets: `rag_service.query(top 3-4)` -> prompt -> one `generate` call.
  - **Existing code needs adjusting for CPU:** `OllamaProvider.generate` has `timeout=60.0` and `configure()` runs a "hi" test generation with `timeout=15.0`. On a CPU box with a cold model load, both can time out; `configure()` failing makes the provider selection fall back to Mock, silently producing mock answers. Plan a per-call timeout parameter (180-300 s for ticket jobs) and a warmed model (`keep_alive`) or a lazy "model loading" state; add an explicit "AI unavailable -> escalate to human" path so a Mock answer can never be posted to a customer as a real one (gate on provider name != Mock).
- **Escalation is deterministic.** Answer only if best Chroma distance <= calibrated threshold AND >=1 source chunk AND `ai_guardrails.scan_text` passes on the output (PII/injection) AND ticket category is on a tenant-configurable allowlist AND priority is not critical/security. Otherwise escalate via the existing `tickets_escalation_service` path. Calibrate the threshold against real KB/ticket pairs; Chroma's default collection metric is L2 on MiniLM embeddings, so thresholds are corpus-specific.
- Every AI reply carries citations (KB source ids), is marked as AI-authored, and is retractable. Record `ticket_ai_attempts` (query, chunks, distance, model, latency, decision) for audit.
- Memory: 7.9 GB total, ~3.2 GB available at time of research with mongod + backend + chroma loaded. A 3B Q4 model is ~2 GB plus KV cache; feasible but tight. Keep `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1`, `num_ctx` 2048-4096. The watchdog should check `psutil.virtual_memory().available` and the worker should refuse to start a generation below a floor (e.g. 1.5 GB).

## Installation

```bash
# Backend runtime: NOTHING to install. Verify the lockfile is unchanged:
git diff --stat backend/requirements.txt   # expect no changes

# Optional dev-only (requirements-dev.txt), only if the legitimacy gate approves:
# hypothesis==6.170.9

# Agent (Rust): no Cargo.toml changes. New handlers use std + existing helpers.

# Ops (the USER applies; this repo only ships the unit files + drop-ins as templates):
#   install -m 0644 omni-watchdog.service omni-watchdog.timer /etc/systemd/system/
#   systemctl daemon-reload && systemctl enable --now omni-watchdog.timer
#   drop-ins for mongod.service.d/restart.conf and omni-backend.service.d/watchdog.conf
#   root-only /etc/omni-watchdog.env (PagerDuty routing key / webhook URL, Mongo URI)
#   (install Ollama + `ollama pull llama3.2:3b` when the service desk AI is switched on)
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Pure-Python decision function | json-logic / CEL / OPA / durable_rules | If tenants must author arbitrary rules in the UI. Locked decision says fixed, tested rules: not needed. |
| External systemd-timer watchdog (stdlib + venv) | Prometheus + Alertmanager + node_exporter; Monit; Uptime Kuma | If the fleet grows beyond one VM or an ops team already runs Prometheus. On a single 7 GB VM they add 200-500 MB RAM and a second config plane for 5 checks. |
| In-house 15-line sd_notify | `sdnotify` (PyPI) or `systemd-python` | `systemd-python` needs libsystemd headers and a compile; `sdnotify` is unmaintained since 2017. Neither is worth a dependency. |
| APScheduler 3.x `CronTrigger` + existing asyncio loops | Celery beat; APScheduler 4 alpha | Celery is installed but **no worker runs** on this VM and Redis is optional; APScheduler 4 is alpha-only without a migration path. |
| Asyncio loop + `distributed_lock` for intervals | APScheduler jobs everywhere | Use APScheduler only where wall-clock cron semantics are needed (retention at 03:30, maintenance windows). |
| PagerDuty Events v2 via existing connector (+ Slack/Teams/email) | Opsgenie / VictorOps SDKs | Only if the customer standardises on them; Opsgenie support can be a second connector later. Do not add vendor SDKs; a plain HTTPS POST suffices. |
| Single-shot RAG with deterministic gate | LangChain agent / LangGraph for tickets | When a GPU or a hosted LLM (Gemini/Anthropic providers exist) is available and tool-calling is reliable. |
| Chroma (existing) distance threshold | Cross-encoder reranker (`sentence-transformers`, `rank-bm25`) | Not installed; torch CPU is present but loading a reranker costs RAM/CPU on the same 2 vCPU. Revisit only if answer quality is poor after threshold calibration. |

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| New rule-engine / policy-language library (json-logic, CEL, OPA, durable_rules, `python-rule-engine`) | An interpreter + second language to audit for ~6 rules; makes "fixed, tested rules" harder to prove | Pure functions + enum action classes + property/table tests |
| Prometheus / Alertmanager / Grafana Agent / node_exporter / Monit / Nagios | RAM and a second operational surface on a 7 GB, 2 vCPU box already using ~4.6 GB | systemd timer watchdog + existing `/health/ready`, psutil |
| Docker/Kubernetes health probes or a container supervisor | Platform runs as bare systemd units here | systemd `Restart=`, `WatchdogSec=` |
| Celery workers / beat for new jobs | Installed but not running; Redis is optional so it cannot be a hard dependency | `asyncio` loops with `distributed_lock`; APScheduler cron where needed |
| APScheduler 4.x (alpha) | Pre-release, API changed, no job-store migration | Stay on 3.x (3.10.4 installed; 3.11.3 is latest stable) |
| `sdnotify`, `systemd-python`, `python-systemd` | Unmaintained / needs C headers | In-house `sd_notify` helper using `NOTIFY_SOCKET` |
| PagerDuty / Opsgenie / Slack vendor SDKs | Connectors already exist; SDKs add transitive deps | Existing `PagerDutyConnector`, `notification_service`, plain HTTPS |
| LLM in the execution path, LLM self-reported "confidence", or LangChain agent loops for tickets | Locked decision 3; a 3B CPU model is slow and unreliable at tool calls | LLM only summarises/drafts; deterministic retrieval threshold + guardrails decide |
| A bigger local model (7B+), a GPU requirement, or a reranker model | 2 vCPU / no GPU / ~3 GB RAM headroom | `llama3.2:3b` Q4, single request at a time; Gemini/Anthropic providers remain optional |
| Redis as the home of the kill switch/autonomy state | Redis is optional here; a stale/absent cache could ignore a stop | Mongo authoritative + short in-process cache + file flag for the watchdog |
| Terraform/Ansible/Salt/`fabric`/SSH from the backend to "fix" the VM | Backend running as `azureuser` pushing root changes is a privilege-escalation path | The root-owned watchdog with a hard allowlist of units |
| `os.system`/shell strings for restarts | Injection and quoting risk | `subprocess.run([...], shell=False)` with allowlisted unit names |
| New Rust crates for quarantine/firewall/service control (`nftables`, `iptables`, `windows-service` etc.) | Agent binary already carries wasmtime/cranelift (yara-x); cross-compile risk; existing helpers already shell out | std `fs` + `run_privileged_command` + OS firewall CLIs behind existing validators |
| Running `run-on-ubuntu.sh` or any `ufw` rule rewrite as part of host isolation or watchdog | Known SSH lockout on this VM (memory: vm-host-migration) | Agent-side isolate must be allowlist-first (platform backend IP/port, DNS, loopback) with a TTL auto-revert |

## Stack Patterns by Variant

**If Redis is configured on the target deployment:**
- Use it only as an optional cache for the autonomy-level read; Mongo stays authoritative.
- Because the platform treats Redis as optional everywhere else.

**If Ollama is not installed / not reachable (the current VM):**
- Service-desk AI is disabled by capability check; tickets proceed to humans with no error; the Activity view shows "AI unavailable".
- Because Mock fallback must never impersonate a real answer.

**If the tenant sets autonomy = Suggest:**
- Engine runs the same evaluation, writes the ledger entry as `suggested`, and renders an approve button; the action never reaches `agent_instructions` until approved.

**If a Windows endpoint is targeted:**
- Quarantine/isolate/restart use `netsh advfirewall`, `sc`, and file moves via the same handlers behind `#[cfg(windows)]`; the Defender-quarantine history on EILT0197 (capture PowerShell was quarantined) says prefer native APIs over spawning PowerShell, as the 2.1.12 GDI-capture fix did.

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| APScheduler 3.10.4 | Python 3.12, pytz/tzlocal as already resolved | Do not upgrade to 4.x; 3.11.3 optional later |
| cryptography 50.0.2 | `x509.not_valid_after_utc` (UTC-aware property) | Use the `_utc` variant; the naive `not_valid_after` is deprecated |
| langchain 1.3.14 / langchain-core 1.4.9 / langgraph 1.2.9 / langchain-ollama 1.1.0 | pinned exactly in requirements.txt | Do not touch pins in this milestone; ticket path bypasses LangChain entirely |
| webauthn 2.5.x, scipy <1.14, numpy <2 | pinned for stated reasons | Unrelated to v4.3; any new dependency would have to resolve against these |
| systemd 255 | `RestartSteps=`/`RestartMaxDelaySec=`, `WatchdogSec=`, `NotifyAccess=` | All available (verified in the man page) |
| MongoDB 8.0.34 on kernel 7.0.0-1017 | Needs `GLIBC_TUNABLES=glibc.pthread.rseq=1` drop-in | Watchdog's mongod restart must not remove/overwrite this drop-in; verify with `ping` after restart |

## Sources

- Repo inspection (HIGH, direct): `backend/requirements.txt`, `backend/venv` package metadata (versions above), `backend/scheduler.py`, `backend/distributed_lock.py`, `backend/app.py` (`/health/ready`), `backend/app_background_tasks.py`, `backend/autonomous_remediation_service.py`, `backend/remediation_playbook_service.py` + `backend/playbooks/*.yaml`, `backend/deployment_service.py` (`trigger_rollback`), `backend/soar_connectors_messaging.py` (`PagerDutyConnector`), `backend/integrations_v2.py`, `backend/ai_providers.py` (`OllamaProvider` timeouts), `backend/rag_service.py`, `backend/ai_assistant_service.py`, `agent-install/omni-agent-rs/src/instructions.rs` + `capabilities/remediation_actions.rs` + `Cargo.toml`, `/etc/systemd/system/omni-backend.service`, `omni-backup.service/.timer`, `mongod.service.d/kernel-rseq-check.conf` (ollama.service absent).
- PyPI JSON for APScheduler (3.11.3 latest stable; 4.0.0a1-a6 alpha only), hypothesis 6.170.9 (2026-10-23), freezegun 1.5.5, respx 0.23.1, croniter 6.2.4, sdnotify 0.3.2 (2017-08-02) (MEDIUM, official registry, fetched 2026-10-25).
- https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html (WatchdogSec, Restart=, RestartSteps, NotifyAccess) (MEDIUM, official man page).
- https://docs.pagerduty.com/developer/send-alert-event and https://docs.pagerduty.com/developer/events-api-v2-overview (Events API v2 fields, dedup_key rules, 202/400/429/5xx handling) (MEDIUM, official).
- https://docs.ollama.com/faq (OLLAMA_KEEP_ALIVE=5m default, NUM_PARALLEL=1, MAX_LOADED_MODELS=3 on CPU, context default 4096, preload/unload via empty request / keep_alive) (MEDIUM, official).
- https://apscheduler.readthedocs.io/en/master/migration.html (no automatic 3.x job-store import) (MEDIUM).
- https://api.github.com/repos/ollama/ollama/releases/latest (v0.40.11, 2026-10-24) (MEDIUM).
- CPU-only llama3.2:3b tokens/second: **no authoritative measurement found** (LOW); community pages were SEO/affiliate or GPU-based. Must be measured on the VM.

---
*Stack research for: Autonomous Ops (v4.3) on the Omni-Agent AI platform*
*Researched: 2026-10-25*
