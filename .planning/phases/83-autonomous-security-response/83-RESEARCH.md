# Phase 83: Autonomous Security Response - Research

**Researched:** 2026-10-31
**Domain:** Rule-based security response on a multi-tenant FastAPI/MongoDB platform with a Rust endpoint agent (Windows and Linux)
**Confidence:** HIGH on backend and agent code facts (read this session); MEDIUM on OS behaviour (reasoned, needs live checks); LOW on live feed state (cannot read the live DB)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Carried forward, not re-decided**
- Classes (GATE-04, Phase 81): block IP, quarantine file and restart service are automatic; isolate, kill process and reboot need approval. Playbook YAML may raise a class, never lower it.
- Phase 81 limits apply unchanged: approvals expire after 24 h (D-16), one automatic decision touches one host (D-17), breaker at 3 in 24 h with manual restore (D-18), never-touch list (D-19), 20 automatic actions per hour (D-20), the approve-tier and manage permissions (D-05, D-06), MFA (D-07), undo works during a stop and approve does not (D-12), Platform tenant never eligible (D-04).
- Level, maximum level and the never-touch list stay API-only (Phase 81 D-22). D-21 below adds a panel for this phase's three new settings only.

**Two-signal rule (RESP-08)**
- **D-01:** A second signal means a **different origin**. Origins are: the native agent verdict, each public feed in `edr_ioc` by `source_feed` (URLhaus, MalwareBazaar, OTX), VirusTotal, and an on-host detection on that host that names the same indicator (EDR, deception, UEBA). Two entries from one origin never count. Any two different origins satisfy the rule, so it can fire without paid or keyed feeds. If the agent bundle is ever built from a public feed, those two are one origin.
- **D-02:** The rule applies to **block IP and quarantine file**. Restart service is exempt: a failed service is something the agent observed directly, and the restart budget limits it instead.
- **D-03:** One signal becomes a suggestion. If a second origin arrives **within 24 hours** of the first, the suggestion turns into the automatic action through the gate. After 24 hours it stays a suggestion.
- **D-04:** The rule is **on by default and can be switched off**. A tenant admin (manage permission) may turn it off for their own tenant; a Super Admin may do so for any tenant or for all tenants. With it off, one signal acts. Every change is recorded in the ledger and the audit chain. This loosens RESP-08's "only when two signals agree", and RESP-08 and Phase 83 success criterion 1 now say "by default". Every other limit still applies with the rule off. New tenants start with it on.

**Finding outcomes (RESP-01)**
- **D-05:** A malicious file with two origins is **quarantined**, replacing today's routing of a non-IP scan finding to `kill_process` in `select_playbook`. Moved, never deleted (RESP-03).
- **D-06:** If quarantine fails because the file is running or locked, it becomes **one approval card on the same incident**: approving kills the process and retries the quarantine. Nothing is killed without a person.
- **D-07:** A vulnerability becomes a **suggestion only**, linking to patching. No approval card and no patching here, because rollouts belong to Phase 84 and a host can report hundreds. This covers both vuln routes in `select_playbook` (with a CVE and without).
- **D-08:** A file-integrity change becomes a **suggestion only**. If the file's hash is also flagged malicious it takes the normal two-signal quarantine path, and the change itself is not an origin under D-01 because it shows a change, not malice. The current `fim -> restore_file` route leaves the sweep: the agent refuses to restore without `backup_path`, and nothing in the backend ever sets one, so every card would fail.
- **D-09 (research D6):** `restore_file`, `disable_service` and `rotate_key` **stay approval-only**, as the Phase 81 registry already has them.

**Timers and budgets**
- **D-10:** A tenant names the **services to watch** (manage permission). The list starts empty and nothing restarts until a tenant fills it. Agents do not report service failures today, so this phase adds that reporting for listed services only. A service an admin stopped on purpose must not count as failed.
- **D-11:** Restart budget: **3 per service per host per rolling hour**, with growing waits between tries, then one approval card for further restarts. Same limit as the platform watchdog (Phase 82).
- **D-12 (research D5):** Restart service runs automatically with **no Undo button**; a restart has no inverse. The row shows what restarted and the result.
- **D-13:** Block length: **default 24 h, range 1 hour to 7 days**. A tenant admin sets it for their tenant; a Super Admin for any or all. The length travels with the instruction so the agent can remove the block at expiry while offline (RESP-02). - **Reversibility:** costly - the expiry contract ships inside a published agent binary, and changing it later needs a new agent release and rollout.
- **D-14:** When a block expires and the address is still flagged, it is a **new decision through the gate**, never an automatic extension. It needs two origins again, and evidence older than the expired block's start does not count, so stale evidence cannot keep an address blocked. Expiry is not an undo, so RESP-07's 24-hour no-redo does not apply to it.
- **D-15:** An isolated host reverts after **4 hours** unless an operator confirms. Confirming (approve-tier permission) keeps it isolated until a person restores it. The management connection always stays open (RESP-05).
- **D-16:** **Incident** (RESP-09) = alerts on the same host until **1 hour passes with nothing new**. A long attack stays one card; a quiet host starts a fresh one.
- **D-17:** One card holds several actions, each with **its own Approve and Deny**, so each destructive action gets its own recorded single-use decision through the existing approve route. No approve-all.

**Fences and agent support**
- **D-18 (research D8):** Fence, do not migrate or delete. No automatic trigger can start containment on swarm `propagate-antibody` or the SOAR local block and isolate actions, and a test keeps it that way. These paths stop reporting success: they answer that nothing was sent and point to Autonomous Ops, and SOAR stops setting `agents.isolated` for a host that received nothing. Re-checked 2026-10-31: `db.instructions` has 5 writers (`swarm_service.py`, `soar_engine.py` twice, `tasks.py` twice) and no readers.
- **D-19:** New actions are **Rust agent only**. Installers build only the Rust agent and `agent-install/agent` was last committed in July. Any other agent never reports support, so its rules stay dormant (RESP-10).
- **D-20:** **Windows and Linux.** Other platforms report no support and stay dormant.
- **D-21:** Keep the capability ticks Phase 81 mapped: `remediation_executor` for block, quarantine, restart and isolate, `patch_installer` for reboot. No new per-action ticks, so tenants with those ticked change nothing.

**Settings**
- **D-22:** A small **settings panel on the Autonomous Ops screen** holds the two-signal switch, the block length and the watched services, for holders of the manage permission. Without it restart would stay dormant for most tenants.

### Claude's Discretion
- The exact origin table for D-01, as long as no pair shares an origin, and how an on-host detection is tied to an indicator.
- "For all tenants" in D-04 and D-13 is read as a bulk write to each tenant's own setting, not a separate platform layer, so a tenant admin can change it back and there is only one value to read. Revisit only if research finds a reason.
- Isolation's 4 hours (D-15) is a fixed default with no panel setting.
- Backoff intervals for D-11, the quarantine location and format, and how long quarantined files are kept. Files are never deleted automatically in this phase without a decision being recorded.
- Which capability carries the new service-failure reporting.
- How suggestions are shown so vulnerability volume does not bury cards (D-07); settle in the UI-SPEC.
- Layout and copy of the cards, row actions and panel, subject to the Spatial Glass design system, a `/gsd-ui-phase 83` contract and ACTV-08.

### Deferred Ideas (OUT OF SCOPE)
- **Feed real signatures to agents:** build the agent bundle from the public feeds in `edr_ioc`. Without this, native verdicts rarely fire on real threats, so automatic file and IP actions will be uncommon after this phase. A new capability; a roadmap candidate. Under D-01 the bundle and those feeds would then be one origin.
- **Keep file content for real restores:** the FIM baseline stores hashes only. A real restore needs the agent to keep known-good copies. A new capability.
- **Screens for level, maximum level and never-touch:** stay API-only under Phase 81 D-22.
</user_constraints>

## Summary

Phase 83 is the first caller of the Phase 81 gate. The gate, ledger, approvals, undo, reconciler and delivery hold-back already exist and work; the legacy loop is already gone (nothing calls `scan_for_remediable_findings` any more), so **the sweep is wholly new code**, not a rewire. The code reading found eleven things that change the plan and that CONTEXT.md does not state (listed under "Findings that change the plan"). The three with the largest blast radius: (1) the shipped Rust agent reports `agentId` as its **hostname** in scan and FIM posts, while the gate only accepts `agents.id`, so every finding must be resolved hostname -> agent id first; (2) the gate has **no agent-capability or agent-support step**, so an allowed action sent to a tenant without the `remediation_executor` tick, or to an old agent, is refused at delivery or fails on the agent and **counts toward the circuit breaker**; (3) the existing `block_ip` on the agent has no expiry and the existing verify path would **roll back a successful block** (RESP-06), so both the agent contract and the verify path must be new.

Nothing schedules scans: native verdicts exist only when an operator (`trigger-scan`) or the `/scan` skill sends a `scan_*` instruction, and the agent's bundled feed is seed data. Public-feed origins only exist if abuse.ch still answers anonymous calls (secondary sources say it now needs an Auth-Key; the code sends none) so, on this VM, automatic IP blocks and file quarantines will be rare until a key is set or the two-signal switch is turned off. This is consistent with CONTEXT's Deferred Ideas; the planner must size tests with synthetic origins and say so in the UAT.

**Primary recommendation:** Build the sweep as a new module group inside `backend/autonomous_ops/` (single runner via `lock_with_renewal`, copy `reconciler.py`), own an `autonomy_signals` observation store for origins and dedupe, call `gate.decide` directly (not `remediate()`/`_dispatch_and_verify`), add a new dispatcher and a reconciler verify step driven by an agent-reported `verify` block, and ship the agent work as one release (2.1.16) that adds actions, agent-held expiry, a `meta.response_actions` support report and a `service_failures` report. Gate every new rule on both the tenant tick and the agent's reported support.

## Project Constraints (from CLAUDE.md)

- Do what was asked, nothing more; never create files unless necessary; no documentation files unless requested; never save working files or tests to the repo root (use `/src`, `/tests`, `/docs`, `/config`, `/scripts`; here `backend/`, `backend/tests/`, `agent-install/omni-agent-rs/`).
- Always read a file before editing it; keep files under 500 lines (`autonomous_ops_endpoints.py` is 447 lines, `AutonomousOpsActivityList.tsx` is 439: new routes and components go in new files); validate input at system boundaries.
- Never commit secrets, credentials or `.env`; do not add a `Co-Authored-By` trailer unless `.claude/settings.json` sets `attribution.commit`.
- Run tests after code changes and verify the build before committing (`npm run build && npm test`), subject to the VM limits in the phase constraints (no full backend suite, no full `cargo build`).
- Project memory (treated as binding): secrets and restarts are the user's; archive, do not delete; live deploys, agent publishing and `git push` are the user's step; stage by path and commit only your own hunks (uncommitted hunks sit in `app_startup.py`, `agent_capabilities.py`, `App.tsx`, `capabilities/mod.rs`, `deployment_result_endpoints.py`); the naming rule is "Autonomous Ops", never "ASI", "Autopilot" or "fully autonomous" (ACTV-08, enforced by the copy tests).

## Phase Requirements

<phase_requirements>

| ID | Description | Research Support |
|----|-------------|------------------|
| RESP-01 | Sweep turns native findings into playbook actions through the gate, replacing the legacy loop | Sweep is new (legacy `scan_for_remediable_findings` has no caller); enter via `gate.decide`; `select_playbook` changes per D-05/07/08 (Findings 1, 4; Q3) |
| RESP-02 | Single-IP block, default 24 h, agent removes at expiry offline, undo from Activity, range needs approval | Agent-held claims with persisted expiry, `ttl_seconds` + `block_id` params, support token `block_ip_ttl`; range = CIDR -> approval (Q5) |
| RESP-03 | Quarantine (moved, never deleted), one-click restore | Hash-bound move into a root-only dir with manifest; `unquarantine_file` from manifest only (Q6) |
| RESP-04 | Failed service restarted within a budget, then approval | Watched list via heartbeat reply, `meta.service_failures`, budget counted from ledger, `playbook_raise=True` for the card (Q8) |
| RESP-05 | Kill and isolate as cards; management connection stays open; auto-revert unless confirmed | Carve-out + write-ahead state + self-test + agent timer; confirm via heartbeat reply (Q7) |
| RESP-06 | Per-action verify; a successful block is never rolled back | Agent returns `verify`; new reconciler step; do not use `_dispatch_and_verify` (Q3) |
| RESP-07 | No new action per cycle; no redo for 24 h after undo | Gate already suppresses undone rows 24 h; add sweep-level memory for done/denied/failed/refused (Q3, Pitfall 1) |
| RESP-08 | Two-signal default, switchable per tenant/all | Origin store + per-tenant `response.twoSignal` (Q1, Q13) |
| RESP-09 | One card per incident | `autonomy_incidents` collection, rows carry `incidentId` (Q4) |
| RESP-10 | New Rust actions gated by ticks; dormant until agent reports support | `meta.response_actions` tokens + capability check in sweep, gate and approve revalidate (Q10) |
| RESP-11 | Swarm and SOAR fenced | 5 dead-queue writers, no automatic caller found, all entry points human-started (Q12) |
| ACTV-02 | Approve/deny/undo from the screen | Routes exist; add `canUndo`/`undoHint`/`incidentId`, incident list route, confirm-isolation route (Q13) |

</phase_requirements>

## Findings that change the plan

Each is detailed with evidence below; the planner should treat them as plan inputs.

1. **Sweep is new code.** `scan_for_remediable_findings` has no caller in `backend/` (grep, non-test). `remediate()` is only called by `ueba_service.py:121` and tests. [VERIFIED: grep this session]
2. **Hostname, not agent id.** The Rust agent posts to `/api/agents/{hostname}/security/scan-result` and `/fim-events`; the backend stores the path name as `agentId` / `agent_id`; the gate's `_agent_of` queries `{"id": target}`. Findings must be resolved `{tenantId, $or:[{id},{hostname}]}` -> `agents.id`, refusing when more than one agent matches. [VERIFIED: see Q1 quotes]
3. **No capability or support step in the gate.** `grep capabilit backend/autonomous_ops/*.py` returns nothing. `agent_capabilities.hold_back` later marks an unticked instruction `refused`, the reconciler maps `refused` to `failed`, and `breaker.py` counts `failed` automatic rows. [VERIFIED]
4. **Gate records refusals every call and dedupe only covers open rows.** `_step_dedupe` runs after protected-target and blast-radius refusals, and only checks `OPEN_STATES`, shadow rows and undone rows. A finding that is `verified`, `denied`, `expired`, `failed` or `refused` is decided again on the next 60 s cycle. The sweep needs its own memory. [VERIFIED: gate.py:279-300, `__init__.py:48-50`]
5. **Existing verify rolls back a good block.** `_check_nscan_resolved` re-scans and calls the result `failed` when the verdict is still Malicious; `_dispatch_and_verify` then dispatches the rollback. [VERIFIED: autonomous_remediation_service.py:857-888, 689-713]
6. **Instruction result detail is dropped.** `report_instruction_result` stores only `message`, `error` and `raw_status`. The agent's `verify` block would be lost without a backend change. [VERIFIED: agent_tasks_endpoints.py:98-111]
7. **Old agents ignore new params.** Today's `block_ip` ignores `ttl_seconds` and would block forever; an unknown instruction returns `status: error`. Support must be reported per feature token, not per command name. [VERIFIED: instructions.rs:531-537, 586-593]
8. **Natural block expiry must not change ledger state.** Moving an expired row to `rolled_back` would count as a bad automatic row for the breaker; three expiries would drop the tenant to Suggest. Show expiry from `blockedUntil` instead. [VERIFIED: breaker.py `_BAD_STATES`]
9. **Quarantine of a running file usually succeeds.** On both OSes a same-volume rename of a running image is allowed [ASSUMED, live check], so D-06's "fails because running" is the rarer path; the common case is "moved, process still running". Recommend a kill-only card for it (Open Question 2).
10. **Mostly one origin on this VM.** `edr_ioc` feed rows have no `tenantId`; abuse.ch likely needs a key; VT has none; `threat_intel_scans` is a manual lookup; deception alerts name an external IP but no host. Two real origins will be uncommon (Q1). [VERIFIED code; ASSUMED live]
11. **Old `restart_service`/service-failure data path does not exist.** The agent has no service watcher, and heartbeat meta keys are stored wholesale under `agents.meta.<key>`; a new key must be added to `_DATA_KEYS` to be dropped for untick tenants. [VERIFIED: agent_heartbeat_endpoints.py:150-157, agent_capabilities.py `strip_heartbeat`]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Signal collection, origin matching, suggestion vs action | API / Backend (sweep) | Database | Needs cross-origin, per-tenant joins; agents cannot see feeds |
| Decision, class, caps, stop, shadow | API / Backend (gate) | Database (ledger) | Existing single decision function |
| Block expiry, isolation auto-revert, quarantine, restart | Endpoint agent | Backend (instruction + ttl) | Must work offline; backend only supplies lengths and ids |
| Verification of each action | Endpoint agent (check) | Backend reconciler (state change) | The agent can see the firewall rule or the file; backend cannot |
| Support and failure reporting | Endpoint agent (heartbeat) | Backend (stores `agents.meta.*`) | Agent knows what it can do and what failed |
| Watched service list, block length, two-signal switch | Database (`autonomy_settings`) | API (routes), agent (heartbeat reply for the list) | Per-tenant setting; only the list reaches the agent |
| Approve, deny, undo, confirm isolation | API / Backend | Browser (buttons) | Existing routes + MFA + interactive session |
| Fences (swarm, SOAR) | API / Backend | Browser (message only) | Routes stop writing the dead queue and answer honestly |
| Cards, settings panel | Browser | API | Spatial Glass contract in 83-UI-SPEC.md |

## Standard Stack

### Core (all existing; STACK.md says no new runtime dependencies or crates)

| Library / module | Version | Purpose | Why |
|------------------|---------|---------|-----|
| `autonomous_ops.gate`, `ledger`, `approvals`, `reconciler`, `delivery`, `protected`, `settings`, `breaker` | in repo | decide, record, approve, undo, hold back | Phase 81 core; only the gate writes stamped instructions [VERIFIED: gate.py:1-25] |
| `distributed_lock.lock_with_renewal` | in repo | single-runner sweep | Used by `reconciler.py:157` and `retention_job.py` [VERIFIED] |
| pymongo / motor | in repo | raw handle with explicit `tenantId` | Package rule: never the ambient tenant ContextVar [VERIFIED: scope.py] |
| pytest, `tests/_mongo_test_db.py` | in repo | backend tests with a private mongod | Memory recipe: mongod on port 27998 with `GLIBC_TUNABLES=glibc.pthread.rseq=1` |
| vitest `^5.0.0` | package.json | frontend tests | `"test": "vitest run"` [VERIFIED: package.json:14] |
| Rust std + existing crates (`sysinfo`, `serde_json`, `sha2`, `chrono`, `hex`, `rusqlite`, `winapi`) | agent `Cargo.toml` v2.1.15 | agent actions | No new crates; `run_privileged_command` is the one spawn helper |

### Supporting

| Item | Use |
|------|-----|
| `winapi` feature `winsvc` (existing crate, new feature flag) | Optional native `QueryServiceStatusEx`; the alternative is parsing `sc query`/`sc qc` (already spawned by `disable_service`) |
| `std::net::IpAddr`, Python `ipaddress` | IP validation on both sides (the agent already uses `parse::<IpAddr>`; `protected.parse_ip` is strict) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `netsh`/`sc`/`iptables` CLIs | `windows` crate COM `INetFwPolicy2` / `windows_firewall` crate | Native avoids spawning, but is a new crate and a cross-compile risk (the build already carries wasmtime). STACK.md rejects new crates. Revisit only if Defender blocks the CLIs on EILT0197 (Open Question 6) |
| New `autonomy_signals` collection | Re-derive state from the ledger each cycle | Ledger rows are audit records and expire; the sweep needs first-seen times per origin that survive row expiry |
| Playbook YAML for sweep decisions | Direct `gate.ActionRequest` | YAML cannot express two signals, TTL, verify or chains; keep YAML only for the class-raise key and rollback metadata |

**Installation:** none. **Version verification:** not applicable, no packages are added. `cargo test --offline` uses the prebuilt `target/` (93 GB present).

## Package Legitimacy Audit

No external packages are installed by this phase (no `npm install`, `pip install`, `cargo add`). The only dependency change is the optional `winsvc` feature of the already-locked `winapi` crate. `gsd_run query package-legitimacy check` was not run because there is nothing to check.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
 Agent (Rust 2.1.16)                         Backend (FastAPI + Mongo)                         Operator
 ───────────────────                         ─────────────────────────                         ────────
 heartbeat meta.* ────────────────────────▶ agents.meta.{process_monitor, runtime_security,
  (+ response_actions, response_state,        response_actions, response_state,
     service_failures)                         service_failures}
 POST scan-result (hostname as agentId) ──▶ security_scan_results   ┐
 POST fim-events  (hostname as agent_id) ─▶ fim_events              │ edr_ioc (global feed rows,
 threat_feed_sync (every 6 h, raw handle) ─▶ edr_ioc                │  no tenantId; manual rows
                                                                    │  carry tenantId)
                        ┌───────────────────────────────────────────┘
                        ▼
              SWEEP LOOP (new, 60 s, lock_with_renewal "autonomous_ops_sweep")
              per tenant (sorted, tenant_scope, lost() between tenants):
                skip: ineligible / level off / stopped / agent offline / capability off / agent unsupported
                1 resolve hostname -> agents.id (unique per tenant, else skip)
                2 observe: candidates = host telemetry ∩ indicators; record per-origin first/last seen
                           in autonomy_signals (never trusts feed timestamps)
                3 corroborate: distinct origins >= 2 (or 1 when response.twoSignal is off)
                4 sweep-level memory (done / denied / failed / refused / undone / expiry window)
                5 incident: attach/open autonomy_incidents (1 h quiet gap)
                6 gate.decide(ActionRequest)  ── refuse / suggest / shadow / needs_approval / allow_auto
                        │
        allow_auto ─────┴──▶ gate.execute(kind="action")  ─▶ agent_instructions (stamped)
        needs_approval ─▶ card in autonomy_actions ─▶ approvals.approve ─▶ dispatcher "security_response"
                                                                   └▶ gate.execute
 Agent poll (hold_back + stop hold-back) ◀── instructions
 Agent runs action, holds expiry/revert state in response_state.json,
 returns {status, outcome, verify} ──▶ report_instruction_result (stores verify, outcome)
                        ▼
              RECONCILER (existing 60 s) + verify step (new):
                dispatching -> executed (instruction SUCCESS) -> verified (verify.ok) | failed (verify_failed, NO rollback)
                follow-ups (kill executed -> new gate.decide for quarantine retry)
                        ▼
              Activity screen / Needs-your-decision section (new incident route) ──▶ Approve / Deny / Undo / Confirm isolation
```

### Recommended Project Structure

```
backend/autonomous_ops/
├── sweep.py               # loop, lock, per-tenant tick (copy reconciler.run_once/tick/loop)
├── signals.py             # origin readers, hostname resolution, autonomy_signals store
├── incidents.py           # autonomy_incidents open/attach/close-by-quiet-gap
├── response_settings.py   # twoSignal, blockHours, watchedServices read/write + validation + control rows
├── agent_support.py       # supports(agent, command) and capability check (shared by sweep, gate, approvals)
├── verify.py              # instruction result -> verified / failed (no rollback)
└── followups.py           # kill executed -> quarantine retry decision
backend/autonomous_ops_response_endpoints.py   # new router under /api/autonomous-ops (keeps endpoints file < 500 lines)
backend/migrations/028_security_response.py    # indexes for the new collections (next free number)
agent-install/omni-agent-rs/src/capabilities/
├── response_state.rs      # response_state.json: claims, isolation, quarantine index; atomic write; expiry sweeper
├── firewall.rs            # block/unblock/isolate/restore per OS behind one command seam
├── quarantine.rs          # move, manifest, restore, verify
└── service_watch.rs       # watched list, unexpected-vs-admin-stop classification, restart
```

### Pattern 1: Sweep runner (copy, do not invent)

Same shape as the reconciler. [VERIFIED: reconciler.py:34-37, 153-176]

```python
# Source: backend/autonomous_ops/reconciler.py (verbatim shape)
LOCK_NAME = "autonomous_ops_reconciler"
LOCK_TTL_SECONDS = 120
LOCK_RENEW_EVERY = 30
...
lock_db = SimpleNamespace(_db=raw(db))        # distributed_lock reads db._db
async with distributed_lock.lock_with_renewal(lock_db, LOCK_NAME, ttl_seconds=LOCK_TTL_SECONDS,
                                              renew_every=LOCK_RENEW_EVERY) as handle:
    if not handle.acquired:
        return None
    return await tick(db, now=now, lost=lambda: handle.lost)
```

Use `LOCK_NAME = "autonomous_ops_sweep"`. Start it in `run_startup_services` beside lines 507-515 of `app_startup.py` with `_safe_bg_task(...)`. Wake interval 60 s via `AUTONOMOUS_OPS_SWEEP_INTERVAL_SEC` [ASSUMED: interval is a design choice]. Every write sets `tenantId` explicitly and uses `scope.tenant_scope`.

### Pattern 2: Origins keyed per tenant, host and indicator

`autonomy_signals` (new, raw handle). One doc per `(tenantId, agentId, kind, indicator)`:

```
{ tenantId, agentId, kind: "ip"|"file", indicator: "<ip>" | "<sha256>", path?: "...",
  origins: { "<origin>": { firstSeenAt, lastSeenAt, ref } },     # origin ids below
  decision: { actionId, at, outcome, blockedFrom?, blockedUntil? },
  suggestedAt }
```

Origin ids (no two share an origin): `native` (`security_scan_results`, `source: "native"`), `feed:urlhaus`, `feed:malwarebazaar`, `feed:otx` (from `edr_ioc.source_feed`), `virustotal`, `onhost`. All time comparisons use the sweep's own `firstSeenAt`/`lastSeenAt` (never `edr_ioc.last_seen`, which is a feed-supplied string, and never `updated_at` as "first seen" because the upsert rewrites it every 6 h). D-03 = `second.firstSeenAt - first.firstSeenAt <= 24 h`; D-14 = every counted origin's evidence time is later than the expired block's `blockedFrom` (native and on-host evidence must be newer rows; a feed IOC counts while `edr_ioc.updated_at` is within about 48 h, meaning it is still on the feed's recent list).

### Pattern 3: Suggestion rows and action rows use different dedupe keys

Gate dedupe is per `(tenantId, dedupeKey)` over `OPEN_STATES = ("suggested", "awaiting_approval", "approved", "dispatching")`. [VERIFIED: `__init__.py:48`] If the suggestion and the action shared a key, the open suggestion would refuse the action as `duplicate`. Use `{tenant}|sweep-suggest|{cmd}|{host}|{indicator}` for suggestions (via `gate.suggest`) and `{tenant}|sweep|{cmd}|{host}|{indicator}` for actions. When the second origin arrives in the window: decide the action; on success transition the suggestion row `suggested -> expired` with `reasonCode="superseded"` (new REASON_TEXT and copy-test entry).
Vulnerability and FIM suggestions are one aggregate row per `(tenant, host, kind)` (UI-SPEC R14): `dedupeKey {tenant}|sweep-suggest|{kind}|{host}`, `suggestion: {kind, count, items[<=10], openView}` refreshed each sweep by a new non-state `ledger.refresh_suggestion` update (extends `approval.expiresAt`, no audit mirror each cycle). Otherwise the 24 h approval TTL expires the row while the host still has hundreds of vulnerabilities.

### Pattern 4: Chain follow-up (D-06)

Do not model kill-then-quarantine as one multi-step row: undo returns `no_undo` for `step_count > 1` and the reconciler would mark the row `executed` after the first instruction. Instead: card action K = `kill_process` (approve class, params `{target: "<pid>", expected_exe: "<path>"}`); when the reconciler moves K to `executed`, a `followups` hook calls `gate.decide` for `quarantine_file` again (class auto, key suffix `|retry`, `parentActionId = K`, same `incidentId`). A person's approval of K covers the retry; the retry is still a normal automatic decision under the rate limit and breaker.

### Pattern 5: Dormancy check in three places

`agent_support.check(db, tenant_id, agent, command)` returns a reason or None: capability tick (`agent_capabilities.allowed_for`), agent `status`/`lastSeen` freshness, and `agents.meta.response_actions` token. Call it (a) in the sweep before any decision (dormant means no row), (b) as a recorded-nowhere gate refusal for commands newly added in this phase (`agent_unsupported`, `capability_off`, unrecorded like `not_enabled`), (c) in `approvals._revalidate` so a card approved a day later re-checks. Add the new codes to `gate.REASON_CODES` and `messages.REASON_TEXT` (test `test_autonomous_ops_gate_order.py` enumerates order, so add the step at a fixed position and update it).

### Anti-Patterns to Avoid

- **Calling `remediate()` or `_dispatch_and_verify` for sweep decisions.** It re-reads the finding and rolls back on a still-Malicious verdict (Finding 5), polls inside the approve request for up to ~120 s, and uses a lease keyed by `finding.agent_id or "auto"`.
- **Trusting `security_scan_results.agentId` as an agent id.** It is whatever the agent put in the URL (hostname).
- **Reading `edr_ioc` through the tenant wrapper.** `edr_ioc` is not in `TENANT_ISOLATION_EXEMPT_COLLECTIONS` [VERIFIED: database.py:25-34], so under a tenant context the wrapper adds `tenantId=<tenant>` and the global feed rows (no `tenantId`) never match. Use the raw handle, filter feed rows with `{"tenantId": {"$exists": False}, "source_feed": {"$in": [...]}}`, and never let one tenant's manual IOC rows (which carry `tenantId`, `added_by`, and the fields `sha256`/`ip_address`, a different shape) count for another tenant.
- **Marking expired blocks `rolled_back`.** See Finding 8.
- **Counting free text as an indicator.** Alert `description` and `evidence` fields are attacker-influenced strings; only structured fields (`sha256`, `target`, `source_ip`) are origins.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Single runner | A new lock | `distributed_lock.lock_with_renewal` | Renewal and `handle.lost` already tested |
| Decision, caps, stop, shadow, never-touch | Checks in the sweep | `gate.decide` | GATE-03 order; only the gate writes stamped instructions |
| Approval, expiry, undo | New approve code | `approvals.approve/deny/undo` + `register_dispatcher` | Single-use compare-and-set already there |
| Instruction write | Direct `agent_instructions.insert_one` | `gate.execute` | `test_autonomous_ops_structural.py` fails on a second stamped writer |
| IP validation and never-touch | Regex | `protected.parse_ip`, `protected.check` | Strict parse, mapped IPv6, management network |
| Notifications | Direct inserts | `autonomous_ops.notify` | Existing path |
| Per-tenant bulk write | A platform layer | Loop over tenants calling the same per-tenant writer | CONTEXT discretion: one value to read |
| Firewall expiry | OS scheduled tasks / `at` jobs | Agent-held claims in `response_state.json` plus a tokio sweeper | Survives reboot, no OS scheduler, same on both OSes |

**Key insight:** every hard part is already solved in Phase 81 for decisions; the new difficulty is entirely in the signal store, agent-side time limits, and verify. Keep new backend code outside `gate.py`/`ledger.py` except for the four small hooks named here (undo params carry `block_id`, new reason codes, dormancy step, `refresh_suggestion`).

## Research Answers (evidence)

### Q1. Origins, keys and host binding

| Origin | Collection and fields | Keyed by | Names IP or hash on a host? |
|--------|----------------------|----------|-----------------------------|
| Native verdict | `security_scan_results`: `tenantId`, `agentId` (hostname), `type` (file/url/ip/hash), `target`, `verdict`, `sha256`, `source: "native"`, `created_at` (ISO string) | tenant + host + target | Yes (host-specific) |
| URLhaus | `edr_ioc` `ioc_type: "url"`, `ioc_value` = URL, `source_ip` = URL host, `source_feed: "urlhaus"` | global (no `tenantId`) | Global; usable as an IP entry only when `source_ip` parses as an IP |
| MalwareBazaar | `edr_ioc` `ioc_type: "hash"`, `ioc_value` = sha256, `source_feed: "malwarebazaar"` | global | Global hash |
| OTX | `edr_ioc` `ioc_type: "ip"|"hash"|"url"|"domain"`, `source_ip` = value for ip, `source_feed: "otx"`, key required | global | Global |
| VirusTotal | `fim_events.vt_verdict`, `vt_detection_ratio` plus `security_alerts` `type: "malware_detected"` with `sha256`, `vt_detection_ratio`; manual `threat_intel_scans` (`tenant_id` snake case, `artifact`, `verdict`) | tenant + host (FIM) or tenant only (manual lookup) | Hash on a host via FIM only; the manual lookup names no host. No key on this VM |
| On-host detection | `security_alerts` (`agent_id`, structured `sha256` only on malware alerts), `agent_detections` (free-text `evidence`), `deception_alerts` (`source_ip` of the caller, `tenant_id`, no host), `edr_alerts` (free-form, not posted by the shipped Rust agent) | tenant + host except deception | Only `security_alerts.sha256` is structured; deception names an external IP with no host; EDR/ETW posters are not in the Rust agent |

Evidence:

```python
# backend/threat_feed_sync.py:76 (URLhaus)
                    "source_ip": entry.get("host"),
# backend/threat_feed_sync.py:153 (OTX)
                        "source_ip": ioc_val if ioc_type == "ip" else None,
# backend/threat_feed_sync.py:196 (upsert key)
                {"ioc_type": ioc["ioc_type"], "ioc_value": ioc["ioc_value"]},
# backend/app_startup.py:474 (raw handle, so feed rows carry no tenantId)
        asyncio.create_task(_safe_bg_task(start_threat_feed_loop(db._db), "threat_feed_loop"))
# backend/edr_telemetry_endpoints.py:315 (tenant-added IOCs: a different shape, with tenantId)
    doc = {**ioc.dict(), "added_by": current_user.username,
```

Consequences [VERIFIED unless noted]:
- `edr_ioc` feed rows are **global**; tenant-added rows are tenant-scoped with fields `sha256`/`ip_address` (IOCEntry), not `ioc_value`/`source_ip`. Recommend manual tenant IOCs are **not** an origin (not in D-01); Open Question 3.
- The upsert key is `(ioc_type, ioc_value)` and `$set` replaces `source_feed`: a value listed by two feeds keeps only the last feed's name, so it can never show two feed origins. Fine for D-01, but do not expect it.
- `updated_at` is rewritten on every sync for every row still listed, and rows are never deleted: stale IOCs persist forever and removed false positives never disappear. Use `updated_at` freshness (about 48 h) as "still listed", and the sweep's own first-seen as the time of evidence.
- IP-hosted URLhaus rows are usable: `source_ip` holds the URL's host, which is a domain for most rows, so require `ipaddress.ip_address(source_ip)` to parse. A shared-hosting IP serving one bad URL is a false-positive risk: require `is_global`, never block private, loopback, link-local or multicast addresses automatically, and treat a CIDR as approval.
- Host binding: the candidate must be an observation on the host. Usable passive sources: `fim_events` (`hash_after`/`sha256`, `path`), `agents.meta.process_monitor.processes[].sha256` plus `exe`, `security_scan_results` (target and sha256). Connections from `runtime_security` come from `netstat -ano` capped at 50 and parsed as Windows columns, so treat them as best-effort and Windows-only [VERIFIED: runtime_security.rs:134-186; Linux column layout ASSUMED different].
- The same agent can report both the native verdict and an on-host detection (D-01 allows it). Residual risk is in Security Risks, R2.

### Q2. What produces findings on a schedule

Nothing produces `security_scan_results`. The only senders of a `scan_*` instruction are the operator route `native_security_ops_endpoints.trigger_scan` (`cmd_map = {"file": "scan_file", ...}`), the chat skill `handle_scan` (`"security_scan"`), and the gate's own probe. The Rust agent posts `scan-result` only from the instruction arm. [VERIFIED: native_security_ops_endpoints.py:63; skill_handlers.py:160; instructions.rs:152-190; grep of `scan-result` in the agent shows only instructions.rs:188] The bundled feed is seed data only (CONTEXT, `feed_bundle`). What the sweep can read each cycle with no operator action: `fim_events` (agent `fim` collector, default 600 s), `agents.meta.process_monitor.processes[].sha256` (300 s), `agents.meta.runtime_security.*` (180 s), `vulnerabilities`, `fim_violations`, `security_alerts`, `edr_ioc`. **Recommendation:** do not add scheduled scan dispatch in this phase (scope growth, and the native engine only knows the seed bundle). State the gap in the plan and the UAT script. `[ASSUMED]` that the user accepts this; it matches CONTEXT Deferred Ideas.

### Q3. Entering the gate, verify, reconciler, dedupe, runner

- **Entry:** build `gate.ActionRequest(kind="security", origin="sweep", actions=[cmd], targets=[agents.id], params=..., dedupe_key=..., reason={"ruleId": ..., "inputs": {...}}, dispatcher="security_response", incident id in reason.inputs)`. `decide` records the row before anything is dispatched and returns `Decision(outcome, state, reason, action_id)`. For `allow_auto` the caller must then call `gate.execute(db, tenant, action_id, command=..., agent_id=..., params=..., kind="action")`; `approvals.approve` does that for cards through a registered dispatcher. [VERIFIED: gate.py:374-406, 457-476; approvals.py:56-62, 65-68]
- **Existing verify:** `_verify_finding_resolved` re-reads the finding (vuln, FIM, nscan re-scan) and returns `failed` for a still-Malicious verdict; `_dispatch_and_verify` then marks `failed` and dispatches the rollback. RESP-06 forbids this. [VERIFIED: autonomous_remediation_service.py:857-888, 689-713] Do not route the sweep through it.
- **Reconciler:** maps `dispatching` rows by the latest instruction status, with these constants [VERIFIED: reconciler.py:43-45]:

```python
_SUCCESS = frozenset({"completed", "success", "executed", "done"})
_FAILURE = frozenset({"failed", "failure", "refused", "error", "rejected"})
_UNDELIVERED = frozenset({"pending", "queued"})
```

  `refused` (including a capability hold-back) becomes `failed` with reason `agent_failed`; an instruction nobody picks up in 30 min becomes `failed` (`not_delivered`), so a sweep that targets an offline host trips the breaker. Add a **verify step**: for `executed` rows whose instruction stored `verify`, `verify.ok` true -> `verified`; false -> `failed` with `reasonCode="verify_failed"` and **no compensation**. Needs `report_instruction_result` to persist a bounded, whitelisted `verify` and `outcome` (Finding 6).
- **Dedupe key and fields:** the gate refuses on an open row with the same key, a `shadow` row younger than 24 h, and an `undone` row where `undo.undoneAt`, `finishedAt` or `createdAt` is within 24 h (reason `suppressed_by_undo`). [VERIFIED: gate.py:282-296; `COOLDOWN = timedelta(hours=24)` at `__init__.py:42`] That already satisfies "an undone action is not redone for 24 h" as long as the key is stable across cycles. Everything else (Pitfall 1) needs the sweep's memory.
- **Single runner:** Pattern 1.

### Q4. Incidents and the chain card

`autonomy_incidents` (new): `{id, tenantId, agentId, startedAt, lastAlertAt, alertCount, closed: bool}`. Attach an alert to the host's incident when `lastAlertAt > now - 1 h`, else open a new one; both done with a compare-and-set `find_one_and_update` so a restart or a second runner cannot split an incident. Rows carry `incidentId` (inside `reason.inputs` or a new top-level field; the UI list route groups `awaiting_approval` rows by it). `alertCount` counts distinct evidence items (indicator + origin), not sweeps. All state is in Mongo, so a restart loses nothing; `lastAlertAt` comes from evidence time, not the process clock. A card is the grouping of that incident's rows: pending approvals plus already-ran automatic actions as context (UI-SPEC R4). The D-06 kill card is a row in the same incident (Pattern 4).

### Q5. Block with agent-enforced expiry

Existing agent behaviour [VERIFIED: remediation_actions.rs:191, 195-200]:

```rust
run_privileged_command("iptables", &["-I", "INPUT", "-s", &ip.to_string(), "-j", "DROP"])
let rule_name = format!("OmniAgent_Block_{ip}");
&format!("name={rule_name}"), "dir=in", "action=block",
```

Problems: no expiry; `-I` appends a duplicate on every call while `-D` removes one; IPv6 goes to `iptables` and fails; inbound only; Windows rule name is per IP so duplicates share a name; `validate_ip` accepts loopback, unspecified and the platform address.

Contract to build (D-13, costly once published):
- `block_ip {ip_address, ttl_seconds (3600..604800), block_id, reason?}`; agent validates TTL range itself, refuses non-global addresses and the platform host (`cfg.api_base_url`), the host's default gateway and its DNS servers.
- `response_state.json` beside `config.yaml`, written atomically (temp + rename) **before** touching the firewall: `claims: [{ip, block_id, expires_at_epoch}]`. A second `block_ip` with the same `(ip, block_id)` is idempotent (`outcome: "already_applied"`); a different `block_id` adds a claim.
- `unblock_ip {ip_address, block_id?}` removes that claim; the OS rule is removed only when no unexpired claim remains. Without `block_id` (legacy callers, XDR) remove all claims for the IP. Refcount lives in the state file, not in the OS rule count.
- Expiry sweeper: an independent tokio task (every 15 s) plus a pass at startup, so offline agents and reboots expire blocks. Linux rules are lost on reboot, so startup **re-applies** non-expired claims and drops expired ones; Windows rules persist, so startup only removes expired ones.
- Linux: one idempotent rule per IP in a dedicated chain, `-w` on every call, `-C` before add and after add (verify), IPv6 via `ip6tables`, both INPUT and OUTPUT. Windows: two named rules (`dir=in` and `dir=out`) per IP; verify with `netsh advfirewall firewall show rule name=...`. This VM's `iptables` is `v1.8.10 (nf_tables)` and supports `--check` and `--wait` [VERIFIED: `iptables -h`]. `[ASSUMED]` on Windows that an inbound-only block rule does not stop a connection the host opens to the bad IP (return traffic is stateful), so add `dir=out`.
- Result: `{status:"success", outcome:"applied"|"already_applied", expires_in, verify:{ok, check:"firewall_rule_present"}}`.
- Backend: row stores `params.ttl_seconds`, `blockedFrom`, `blockedUntil` (set at dispatch from the same value); `canUndo` false after `blockedUntil`. `gate._undo_block` currently rewrites undo params to `{"ip_address": ...}` (gate.py:328-337) and `dispatch_check.bind` requires the undo params to equal the decided params, so extend `_undo_block` to keep `block_id`.
- Range blocks (CIDR) are approval-only: the sweep never emits a CIDR as `allow_auto`.
- Defender: **no evidence either way.** A web search found only Elastic rules for netsh disabling the firewall, none about `advfirewall add rule` from a service. The shipped agent already spawns `netsh`/`sc`/`iptables` through `run_privileged_command` for `disable_service` and friends. `[ASSUMED]` that signed Microsoft binaries with fixed arguments are not quarantined the way the encoded-PowerShell capture was; avoid PowerShell and `-EncodedCommand`. **Live check on EILT0197 with Defender on** (PITFALLS Pitfall 17: classify "blocked by local security product" as its own result and do not retry).

### Q6. Quarantine and restore

- Location: Windows `<agent install dir>\quarantine\` (the install dir already holds `config.yaml` and `omni-agent.log`, and is admin-only by default under Program Files `[ASSUMED]`); Linux `/var/lib/omni-agent/quarantine/` mode 0700 root. Each file stored as `<id>` with Linux mode 000 and, on Windows, extension `.q`, plus `<id>.json` manifest `{id, originalPath, sha256, size, mode/owner (Linux), quarantinedAt, actionId}`.
- Params: `quarantine_file {path, sha256, action_id}`; the agent refuses a path that is a directory, uses `symlink_metadata` and moves the link itself (never follows it), refuses its own install and quarantine dirs and its own executable, and refuses OS-critical prefixes for the automatic path (Open Question 4). It hashes the file and **refuses when the hash differs** from `sha256` (outcome `hash_mismatch`, not a failure to count against the breaker), which also closes the path-reuse window.
- Move = rename on the same volume; across volumes copy, fsync, verify hash, then remove the original; if removing the original fails remove only our own copy and report `locked`. Nothing deletes a user file otherwise; there is no delete code path for quarantined files in this phase.
- Locked detection (D-06 signal): Windows `ERROR_SHARING_VIOLATION` (32) or access denied on rename; also report `still_running: [{pid, name}]` for processes whose `exe` equals the path (via `sysinfo`), because a same-volume rename of a running image normally **succeeds** and leaves the process running `[ASSUMED, live check on Windows]`.
- Restore: `unquarantine_file {action_id}` only (the destination comes from the manifest, never from the instruction); refuse when the destination exists, when the destination directory is a reparse point or symlink, or when the stored file's hash no longer matches the manifest; restore original mode on Linux.
- Verify: manifest present, stored hash equals `sha256`, original path absent. Result `{outcome:"applied", verify:{ok, check:"in_quarantine"}}`.
- `restore_file` stays as is (approval-only, D-09).

### Q7. Isolate and restore with a management carve-out

- Never let a failed apply lock the agent out. Order: (1) write `isolation` to `response_state.json` first (`{id, startedAt, revertAt = now + 4 h, confirmed:false, previous policy}`); (2) add the management allow rules and **verify they exist**; (3) only then block everything else; (4) self-test: a TCP connect to `api_base_url` host and port within a few seconds, else revert at once and return `outcome:"self_test_failed"`.
- Carve-out set: the platform host from `cfg.api_base_url` (IP literal in this deployment per project memory: `PLATFORM_URL=https://57.154.210.55` systemd drop-in; if a name, resolve all A/AAAA at apply and re-resolve every 60 s while isolated and open DNS to the host's configured resolvers only), loopback, and DHCP (UDP 67/68) so the lease does not lapse during 4 h. The agent's heartbeat, instruction poll, chat, ticket and tunnel WebSockets all use that one host.
- Linux: dedicated chains hooked at position 1 of INPUT, OUTPUT and FORWARD for iptables and ip6tables; ACCEPT lo, ACCEPT platform both ways, DROP the rest. Revert = unhook, flush, delete.
- Windows: save `netsh advfirewall show allprofiles firewallpolicy` per profile, add `OmniAgent_Isolate_Allow_*` rules (`dir=out remoteip=<platform> action=allow`), then `set allprofiles firewallpolicy blockinbound,blockoutbound`. Revert restores the saved per-profile policy and removes only our rules (do not `import` a whole-policy export: it would drop blocks added meanwhile). Verify with the effective store; a Group Policy firewall can override local policy `[ASSUMED]`, so `verify.ok=false` -> revert and report `not_effective`.
- 4-hour revert on the agent: the same independent sweeper task checks `revertAt` every 15 s and at startup, with no network dependence; a reboot is covered by the startup pass. Unreadable state file while an isolation is recorded: revert (fail open for the network, the safe side).
- Confirm (D-15): backend sets `confirmedAt` on the row via a new route; the heartbeat reply carries `isolationConfirmed: [ids]` computed from rows for that agent; the agent persists `confirmed:true` and cancels `revertAt`. This avoids a new registry command. Agent reports `meta.response_state.isolation` each heartbeat so the backend notices an automatic revert and can mark the row (`rolled_back`; isolate is approve class, never `autoDispatched`, so the breaker ignores it).
- `restore_host {action_id}`: removes the isolation and clears state; idempotent.

### Q8. Restart service and failure reporting

- Watched list: stored at `autonomy_settings.response.watchedServices` per tenant; delivered in the heartbeat **reply** as `watchedServices`, adopted and persisted by the agent exactly like `enabledCapabilities` (`update_enabled_from_heartbeat`, `config::save`). [VERIFIED: capabilities/mod.rs:203-240; lib.rs:208-209] Only send it when the tenant holds `remediation_executor`.
- Server-side validation (the agent's rules are stricter than the UI-SPEC's R12): `is_valid_service_name` accepts only ASCII alphanumerics and `- _ .` and rejects a leading `-`. [VERIFIED: remediation_actions.rs:`is_valid_service_name`] Enforce `^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$`, at most 50 entries, case-insensitive duplicates refused, and the agent's critical list (`sshd`, `ssh`, `systemd`, `dbus`, `networkmanager`, `init`) plus the agent's own service (`OmniAgent` per `service.rs`, and the Linux unit name) refused. The shipped denylist lacks Windows-critical services (`RpcSs`, `winmgmt`, `lsass`-class) so add them agent-side.
- Failure classification: Linux `systemctl show -p ActiveState,SubState,Result,ExecMainStatus <unit>`: `ActiveState=failed` or `Result` other than `success` = failure; `inactive` with `Result=success` = an admin stop. Windows: stopped with a non-zero `dwWin32ExitCode` (including 1066) = failure; stopped with exit code 0, or start type disabled, = treated as an admin stop (conservative, per D-10). Wait a 60 s grace for systemd `Restart=` or SCM recovery before reporting. `[ASSUMED]` Windows exit-code semantics, live check.
- Report: heartbeat `meta.service_failures = [{name, failure_id, since, state, exit_code}]` while failing. Add `"service_failures": "remediation_executor"` to `_DATA_KEYS` so an untick tenant's data is dropped. Capability choice: `remediation_executor` (D-21 forbids new ticks; the reporting is useless without restart).
- Budget (D-11): count ledger rows per `(tenant, host, service)` created in the last hour, states not in `refused`/`shadow`; three allowed with waits 1, 2, 4 min (same ladder as the watchdog's waits; note Phase 82 D-07 is 3 per **30 min**, so "same limit" in D-11 is not numerically identical; follow D-11's hour) `[ASSUMED]`. Over budget: `ActionRequest(playbook_raise=True)` makes the gate answer `needs_approval` with `playbook_raised`. [VERIFIED: gate.py:192-193]
- Handler: validate, refuse own service, `systemctl restart <name>` / `sc stop` then `sc start`; verify state running for N seconds (10 s). Run it off the poll loop (`tokio::spawn`), because `instructions::poll` is awaited by the heartbeat loop and a long wait delays heartbeats (the patch job does the same). Result `{outcome:"restarted", verify:{ok, check:"service_running"}}`. No undo (D-12): registry already has `restart_service` with no `undo`.

### Q9. Reboot host

No reboot code exists in the agent. [VERIFIED: grep of `src/` shows only `reboot_required` flags in `patch_installer.rs` and a comment in `agent_update.rs`; no `reboot_host` arm in `instructions.rs`] Registry has `ActionSpec("reboot_host", "approve")` and the capability map has `"reboot_host": "patch_installer"`. Phase 84 depends on it, so define the contract now: `reboot_host {delay_seconds (30..300), reason, action_id}`; the agent **replies success first**, then schedules `shutdown /r /t <n> /c "<reason>"` (Windows) or `shutdown -r +1` / `systemd-run --on-active=<n>s systemctl reboot` (Linux); return `outcome:"scheduled"`, `verify:{ok, check:"reboot_scheduled"}`; no inverse, but allow cancel via `shutdown /a` / `shutdown -c` only inside the delay (not an undo button). After boot the agent reports `boot_time` in `meta.response_state` so Phase 84 can verify the reboot happened. `[ASSUMED]` `shutdown.exe` is not blocked by Defender (same live check).

### Q10. Support reporting and unknown instructions

- The agent heartbeat already sends `version` (`env!("CARGO_PKG_VERSION")`, `Cargo.toml` `version = "2.1.15"`) and `meta.capabilities` (collector ids). [VERIFIED: heartbeat.rs:553, 538] `meta.<key>` is stored wholesale as `agents.meta.<key>` [VERIFIED: agent_heartbeat_endpoints.py:157]:

```python
                update_data[f"meta.{key}"] = value
```

- Add `meta.response_actions = {"v": 1, "platform": "Windows"|"Linux", "tokens": ["block_ip_ttl", "quarantine_file", "unquarantine_file", "restart_service", "isolate_host", "restore_host", "reboot_host", "kill_process_exe", "service_failures"]}`. Tokens, not versions (Finding 7): `block_ip_ttl` is the token the block rule needs; a 2.1.15 agent has `block_ip` but no `block_ip_ttl`, so the rule stays dormant. Other platforms send no tokens (D-20).
- The gate must read it: `_agent_of` currently projects `id, tenantId, hostname, ipAddress`; extend with `status`, `lastSeen`, `meta.response_actions`. Version number is a secondary guard only (`agent_auto_update_service._parse_ver` exists).
- Old agents receiving an unknown instruction answer `{"status":"error","error":"Agent does not support instruction '<x>'"}` [VERIFIED: instructions.rs:586-593], which becomes `FAILURE` -> ledger `failed` -> breaker. Dormancy must prevent that; do not rely on the error. (The backend substring check `"Unknown instruction"` at agent_tasks_endpoints.py:100 does not match this message; harmless but do not rely on it.)

### Q11. Input safety

| Input | Reaches | Existing check | Needed |
|-------|---------|----------------|--------|
| IP | `iptables`, `netsh` | `parse::<IpAddr>` only | Refuse non-global, platform, gateway, DNS; CIDR rejected on the auto path; backend `protected.check` already refuses loopback, link-local, multicast, backend addresses |
| Service name | `systemctl`, `sc` | alnum `-_.`, no leading `-`, short critical list | Backend regex + limit + own-service denial; agent adds Windows-critical names; pass as one argv element (never a shell string) |
| File path | rename | none (`restore_file` copies to any path) | Absolute, no `..`, `symlink_metadata`, hash-bound, protected prefixes, no own dirs |
| PID | `kill` | refuses 0, 1, own pid, critical names; name match kills **all** processes of that name | Card params `{target: pid, expected_exe}`; agent verifies the pid's exe equals `expected_exe` before killing (a 24 h-old PID may be reused) |
| `ttl_seconds`, `delay_seconds` | timers | none | Range check on the agent, not only the backend |
| `action_id`, `block_id` | state file keys | none | `^AO-[0-9a-f]{32}$` |

Every parameter reaches a privileged command as a separate argv element via `std::process::Command::args` (already the case in `run_privileged_command`); keep it that way and never build a command line string.

### Q12. Fences and settings: `db.instructions`

Re-run (this session) of `grep -rnE "(db|mongodb\.db|_db|raw\(db\))(\.|\[['\"])instructions\b"` over `backend`, `agent*`, `scripts`:

```
backend/swarm_service.py:54:            await db.instructions.insert_many(instructions)
backend/soar_engine.py:193:                await mongodb.db.instructions.insert_one(instruction)
backend/soar_engine.py:272:            await mongodb.db.instructions.insert_one(instruction)
backend/tasks.py:62:    db.instructions.insert_one(instruction)
backend/tasks.py:106:        db.instructions.insert_one({
```

Five writers, no reader (matches D-18). Callers, all human-started [VERIFIED]:
- `swarm_service.propagate_antibody`: HTTP `POST /api/swarm/propagate-antibody`, `require_permission("remediate:agents")`, one UI caller (`SwarmDashboard.tsx:78`). It replies `status: "Propagating"` while writing a queue nobody reads; the UI reads `result.data?.dispatched` which the route never returns.
- `soar_engine` plugins `block_ip_firewall` and `isolate_host`: reached only through `soar_endpoints.execute_playbook` (`manage:playbooks`, background task); `isolate_host` also sets `agents.isolated` even though the instruction never arrives (it writes `network_isolate`, a name no agent knows).
- `soar_connectors_security` (Firewall and EDR connectors, real external calls with `session.post`): reached through `integration_endpoints` and `enhanced_playbook_template_endpoints /integrations/test` (`manage:playbooks`), both human; `playbook_engine_actions._action_create_ticket` uses the integration manager for tickets only.
- `tasks.py`: `execute_remediation_script` (line 106, `run_script`, from `remediation_service.py:106`, a human route) is a scripted-remediation write to the dead queue; line 62 is a non-containment `run_software_scan` from `run_periodic_patch_scan`. Fence line 106; line 62 is not containment but remove or keep behind the same test.
- No automatic trigger reaches `soar_engine`, `soar_connectors_security` or `swarm_service` (the only automatic playbook runner is `PlaybookExecutionEngine`, already gate-routed by Phase 81 D-21 for the four containment actions). Human-started runs keep working (Phase 81 D-21).

Fence design: the routes stop writing and answer honestly (`status: "not_sent"`, a message pointing to Autonomous Ops, `dispatched: 0`); SOAR `isolate_host` must not set `agents.isolated` and returns `{action: "not_sent"}`. Test: extend `test_autonomous_ops_structural.py` so `swarm_service.py`, `soar_engine.py` and `tasks.py` leave `GRANDFATHERED_WRITERS` only if they no longer write any agent queue, and add a scan that no `db.instructions` writer exists outside an explicit empty allow-list. The existing scanner `writes_agent_queue` already covers `instructions`. [VERIFIED: test_autonomous_ops_structural.py `_COLL`]

### Q13. Settings, migration, routes, permissions, bulk write

- Settings live on the existing `autonomy_settings` document under `response: {twoSignal: bool, blockHours: int, watchedServices: [str]}`. Readers default when absent (`twoSignal` true, 24, `[]`); `ensure_tenant` is `$setOnInsert` so new tenants need no write and old tenants no backfill. A malformed stored value reads as the safe default (two-signal on). Add a `settings.load` extension or a `response_settings.load` that never raises.
- Next free migration is **028** (`ls backend/migrations`: `027_retention_gate.py` is last). It only creates indexes for the new collections (`autonomy_signals` unique `(tenantId, agentId, kind, indicator)`; `autonomy_incidents` `(tenantId, agentId, closed)`; ledger index for `incidentId`); follow `027_retention_gate.py` (module `ensure_indexes`, `up(db)`).
- Add `autonomy_signals` and `autonomy_incidents` to `PROTECTED_COLLECTIONS` only if they must outlive generic retention (decision records do; signals do not need to, but never put them in the retention types without review).
- Routes: new router `autonomous_ops_response_endpoints.py` mounted with the same `AUTONOMOUS_OPS_GUARD` under `/api/autonomous-ops`; the manifest entry for `autonomousOps` already covers prefix `/api/autonomous-ops` [VERIFIED: catalogue-access.json:162] so no new catalogue view is needed, but add the entry to `catalogue_mounts_autonomous_ops.MOUNTS` and update `test_catalogue_slice_autonomous_ops.py`. Routes: `GET /incidents`, `POST /actions/{id}/confirm-isolation` (control permission, interactive session, MFA, refused during a stop), `GET/PUT /response-settings` (manage, interactive), platform `GET /api/platform/autonomous-ops/response-settings` and `PUT /response-settings/bulk` on the platform router (pattern `PUT /tenants/{id}/max-level`).
- Permissions: reuse `manage:autonomous_ops` (settings, watched services), `control:autonomous_ops` (approve, deny, undo, confirm), `control:platform_autonomous_ops` (bulk). No new permission strings, so no role migration.
- Bulk write: loop tenants calling the same per-tenant writer; collect per-organization failures; each write creates a `ledger.record_control` row (new `controlEvent` values and `messages.CONTROL_LABELS` entries) and the audit mirror happens inside `record_control`. Loosening (`twoSignal` -> false) in bulk is Super Admin only.
- Frontend copy: every new backend message module and new TSX file must be added to `EXPECTED_FILES` in `test_autonomous_ops_copy.py` and to `shared/autonomous-ops-banned-terms.json` before the first string lands (UI-SPEC item 5). [VERIFIED: test_autonomous_ops_copy.py:21-45]

### Q14. Validation: see the Validation Architecture section.

### Q15. Risks: see the Security Domain section.

## Common Pitfalls

### Pitfall 1: Every sweep cycle creates another row
**What goes wrong:** the next 60 s cycle sees the same finding again. `verified`, `denied`, `expired`, `failed` and recorded refusals are not open, so the gate decides again; a recorded refusal (`protected_target`, `tenant_stop`, `blast_radius`) writes a new `refused` row each minute because refusals return before the dedupe step.
**Why:** gate dedupe is open-state only, and `_UNRECORDED` omits most refusals. [VERIFIED: gate.py:52-54, 314-315]
**How to avoid:** the sweep checks `autonomy_signals.decision` first: skip while `decision.at` is inside a window (done blocks until `blockedUntil`; denied or expired cards 24 h; failed 1 h; refused 24 h unless inputs changed); pre-skip stopped, Off, offline and dormant tenants/hosts instead of letting the gate record them.
**Warning signs:** `autonomy_actions` growth per tenant per hour; Activity filled with identical Refused rows.

### Pitfall 2: Breaker tripped by plumbing, not by bad actions
**What goes wrong:** a capability hold-back, an unsupported agent, an offline host (`not_delivered` after 30 min) or an unknown-instruction error each produce a `failed` automatic row; three drop the tenant to Suggest.
**How to avoid:** dormancy and offline checks before `decide` (Pattern 5); classify `hash_mismatch`, `noop`, `blocked_by_local_security` with their own outcome codes and decide in the plan which count (recommend: only `failed` with `verify_failed` or `agent_failed`).

### Pitfall 3: Block undone after expiry removes someone else's rule
**What goes wrong:** row A (24 h block) expires on the agent; a new decision B blocks the same IP; undoing A removes B's rule.
**How to avoid:** `block_id` in the instruction and in the undo params; agent removes only that claim.

### Pitfall 4: Quarantine succeeds, process keeps running
See Finding 9. The row says "quarantined" while the malware still runs from the quarantine directory. Report `still_running` and raise a kill-only card.

### Pitfall 5: Isolation lockout
Apply management allow first and verify, record state before, self-test after, revert on any failure, revert timer independent of the network. Test the revert path with the carve-out deliberately removed.

### Pitfall 6: Result detail dropped
Without the `report_instruction_result` change the backend sees only `SUCCESS` and cannot verify anything per action. Add it to the same plan as the agent handlers.

### Pitfall 7: `edr_ioc` read through the wrapper or with the wrong shape
See Anti-Patterns. Test with two tenants and a global feed row.

### Pitfall 8: Hostnames are not ids
See Finding 2. Cross-agent hostname collisions inside a tenant must refuse (the test fixture has a unique `(tenantId, hostname)` index; production uniqueness is `[ASSUMED]`).

### Pitfall 9: Approval 24 h later acts on stale facts
`approvals._revalidate` re-checks target and tenant; extend it with dormancy and, for kill, the `expected_exe` check on the agent.

### Pitfall 10: Heavy local builds
2 vCPUs and 8 GB shared with live services. Use `CARGO_BUILD_JOBS=1`, one targeted `cargo test --offline <name>`, never the whole backend suite.

## Code Examples

### Agent result contract (new, to be implemented)

```json
{"status": "success",
 "outcome": "applied",
 "verify": {"ok": true, "check": "firewall_rule_present"},
 "expires_in": 86400}
```

`status` stays `success`/`error` so the existing mapping works (`"SUCCESS" if raw_status == "success"`, agent_tasks_endpoints.py:~94). Persist `outcome` and `verify` (bounded keys and sizes) into `agent_instructions.result`.

### Sweep decision request

```python
# shape only; fields are the ActionRequest dataclass at gate.py:60-77
gate.ActionRequest(
    tenant_id=tenant_id, kind="security", origin="sweep", actions=["block_ip"], targets=[agent_id],
    params={"ip_address": ip, "ttl_seconds": hours * 3600, "block_id": None},   # block_id = action id, set at execute
    dedupe_key=f"{tenant_id}|sweep|block_ip|{agent_id}|{ip}",
    reason={"ruleId": "sweep:block_ip", "inputs": {"origins": sorted(origins), "incidentId": incident_id}},
    reason_text="...", dispatcher="security_response")
```

The claim id problem: `dispatch_check.bind` requires the dispatched params to equal a decided step's params (`same_params`), and the ledger id (`AO-...`) is created by the gate, so it cannot be in the decided params. The poll endpoint relays only `task_id`, `instruction`, `payload` and `parameters` to the agent, not the `autonomy` stamp [VERIFIED: agent_tasks_endpoints.py:64-75]. Therefore **use the instruction's own `task_id` as the agent's claim id** (the agent already reads `task_id`). The row keeps it in `instructionIds` (set by `gate._link`), and the undo reads the original block instruction id from the row and passes it as `block_id` in the decided undo params. That needs only the `_undo_block` change named in Q5, not a change to `bind`. Alternative if the planner prefers: let `gate.execute` accept one extra bound key; rejected here because it widens the single audited writer.

### Rust command seam for hermetic tests

Today `run_privileged_command` is stubbed to `Ok(())` under `#[cfg(test)]`. [VERIFIED: remediation_actions.rs:`#[cfg(test)] fn run_privileged_command`] Replace the stub with a thread-local recorder returning scripted results so tests can assert idempotence, refcount and ordering (management rule before drop), without touching a real firewall.

## State of the Art

| Old approach | Current approach | Impact |
|--------------|------------------|--------|
| Legacy LLM loop; re-read finding to verify | Gate + per-action agent verify | A good block is never reverted |
| `iptables -I INPUT` per call | Chain + `-C` + claims | Idempotent, refcounted undo |
| Backend schedules reverts | Agent-held expiry and dead-man timers | Works offline and across reboot |

**Deprecated/outdated:** `_check_nscan_resolved` for block/quarantine verification; `fim -> restore_file` playbook route; `scan -> kill_process` default for files; `db.instructions` writers.

## Runtime State Inventory

Not a rename/migration phase, but fences and new collections leave state:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `db.instructions` rows already written by the 5 writers (never read) | None (fence, do not delete: D-18) |
| Live service config | none new | None |
| OS-registered state | none; the agent keeps `response_state.json` and a quarantine directory | Document paths in the installer notes; uninstall leaves quarantine in place |
| Secrets/env vars | `OTX_API_KEY`, `VIRUSTOTAL_API_KEY` unset on this VM (project memory) | None; mention in UAT |
| Build artifacts | Agent 2.1.16 needs a published binary and `_LATEST_AGENT_VERSION` bump (user's step) | Plan a manual publish checkpoint |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Defender does not block `netsh`, `sc`, `shutdown.exe` spawned by the agent service with fixed arguments | Q5, Q9 | Windows actions fail with "blocked"; need native APIs or an exclusion |
| A2 | abuse.ch URLhaus and MalwareBazaar require an Auth-Key now (secondary web sources only), so live `edr_ioc` may hold no feed rows | Summary, Q1 | If feeds do work, two-origin pairs are more common than stated |
| A3 | Renaming a running image on the same volume succeeds on Windows and Linux | Q6, Finding 9 | If it fails, D-06 as written is the main path and the kill-only card is unnecessary |
| A4 | A Windows inbound block rule does not stop host-initiated outbound connections | Q5 | If it does, `dir=out` rules are redundant but harmless |
| A5 | Windows explicit allow rules beat a default block policy; a GPO firewall can override local policy | Q7 | Isolation may be ineffective on domain hosts; verify catches it |
| A6 | Windows stopped service exit code 0 means an admin stop; non-zero means failure | Q8 | Crashes with code 0 are missed (safe direction) |
| A7 | Hostnames are unique per tenant in production | Q1, Pitfall 8 | Ambiguous hosts are skipped; no wrong-host action |
| A8 | The sweep interval (60 s), restart waits (1, 2, 4 min), per-host cap (3 automatic per hour) and 48 h feed freshness are acceptable design values | Q3, Q8, Q1 | Tuning only |
| A9 | The user accepts no scheduled scan dispatch in this phase | Q2 | A roadmap follow-up is needed for native origins |
| A10 | Installing under Program Files gives an admin-only quarantine directory | Q6 | Add an explicit ACL step |
| A11 | `netstat -ano` output is Windows-formatted; Linux columns differ so Linux connection telemetry is unreliable | Q1 | Linux IP candidates would come only from scan results |
| A12 | The Linux `iptables-nft` chain hook at position 1 coexists with ufw/firewalld | Q5, Q7 | Rules could be reordered by a firewall manager; verify catches it |

## Open Questions

1. **Do the public feeds populate `edr_ioc` live?**
   - Known: the code sends no `Auth-Key` and treats HTTP 401 as a debug line; secondary sources say a key is now required.
   - Unclear: the live row counts. Recommendation: the user runs one count of `edr_ioc` grouped by `source_feed` (research cannot read the live DB) before UAT; if empty, set a free abuse.ch key (needs a one-line `Auth-Key` header addition in `threat_feed_sync.py`, an in-scope fix) or accept that the UAT uses synthetic origins.
2. **Quarantine succeeds but the file is still running.** D-06 only covers a failed move. Recommend the same card (kill, no retry needed). Needs a user yes because it extends D-06.
3. **Do tenant-added manual IOCs count as an origin?** Recommend no for v1 (not in D-01; a single analyst could otherwise supply an origin).
4. **Auto-quarantine of OS-critical paths.** Recommend the sweep and agent refuse `System32`, `/usr/bin`, `/boot` style prefixes on the automatic path (suggestion or card instead).
5. **Should deception count as an on-host origin?** Its alerts carry an external `source_ip` and no host; it cannot satisfy "on that host". Recommend excluded in v1.
6. **Windows firewall native API.** Only if Defender or EDR blocks the CLIs on EILT0197.
7. **Do `blocked_by_local_security` and `hash_mismatch` outcomes count toward the breaker?** Recommend `hash_mismatch` and noop do not; blocked-by-AV does.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 + pytest | backend tests | yes | project venv | none needed |
| mongod (private instance) | DB-semantics tests | yes (`/usr/bin/mongod`) | 8.0.34 | live 27017 is forbidden for tests; start private on 27998 with `GLIBC_TUNABLES=glibc.pthread.rseq=1` |
| cargo / rustc | agent tests | yes | cargo 1.98.1 | `target/` prebuilt (93 GB) |
| iptables, ip6tables, nft | Linux firewall code and local manual checks | yes | iptables v1.8.10 (nf_tables), nftables v1.0.9 | tests use the command recorder |
| Windows endpoint with Defender (EILT0197) | live verification | user-owned | n/a | none; live-only |
| NSIS | Windows installer | no (project memory) | n/a | mingw cross-build of the exe only |
| Root on this VM | real firewall round trip | no (`id` shows uid 1000) | n/a | user-run live check |

**Missing dependencies with no fallback:** a real Windows endpoint for the live list (user-owned). **Missing with fallback:** root for a Linux firewall round trip (recorder in tests, user runs the live check).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Backend | pytest via `backend/pyproject.toml`; async tests use the `mongo_db` fixture |
| Agent | `cargo test --offline` (unit tests in `src/`, integration in `tests/*.rs`, e.g. `tests/remediation_dispatch_test.rs`) |
| Frontend | vitest `^5.0.0` (`npm test` -> `vitest run`) |
| Quick backend run | `cd backend && MONGO_TEST_URL=mongodb://127.0.0.1:27998 MONGODB_URL=... MONGO_URI=... python -m pytest tests/test_autonomous_ops_sweep.py -x -q` (private mongod, never 27017) |
| Quick agent run | `cd agent-install/omni-agent-rs && PATH=$HOME/.cargo/bin:$PATH CARGO_BUILD_JOBS=1 cargo test --offline <name>` |
| Full suite | not run in this phase's per-task gate; one-off rerun alone before deploy (Phase 82 memory: 24 min, stopped for low memory) |

### Phase Requirements -> Test Map

| Req | Behavior | Test Type | Command / file | Exists |
|-----|----------|-----------|----------------|--------|
| RESP-01 | Sweep turns candidates into gate decisions; vuln/FIM become suggestions; scan route to quarantine | unit + Mongo | `tests/test_autonomous_ops_sweep.py` | Wave 0 |
| RESP-02 | TTL in instruction; claims, expiry offline, idempotent re-block, refcount undo | Rust unit (recorder) + backend params | `cargo test --offline response_state`; `tests/test_autonomous_ops_block_contract.py` | Wave 0 |
| RESP-03 | Move, manifest, hash bound, restore, never delete | Rust integration with tempdirs | `tests/quarantine_dispatch_test.rs` | Wave 0 |
| RESP-04 | Watched list, budget 3/h, ladder, card on exhaustion | backend unit + Rust classifier unit | `tests/test_autonomous_ops_restart_budget.py`, `cargo test --offline service_watch` | Wave 0 |
| RESP-05 | Carve-out ordering, self-test revert, timer revert, confirm via heartbeat reply | Rust unit (recorder), backend route test | `cargo test --offline isolation`, `tests/test_autonomous_ops_confirm_isolation.py` | Wave 0 |
| RESP-06 | verify ok -> `verified`; verify false -> `failed`, no unblock dispatched | Mongo integration | `tests/test_autonomous_ops_verify.py` (extends `test_autonomous_ops_reconciler.py`) | Wave 0 |
| RESP-07 | No row per cycle (10 consecutive ticks create at most one row), 24 h after undo, D-14 evidence | Mongo integration with a frozen clock | `tests/test_autonomous_ops_sweep_dedupe.py` | Wave 0 |
| RESP-08 | Two distinct origins; two entries of one origin never count; 24 h window; setting off | unit | `tests/test_autonomous_ops_origins.py` | Wave 0 |
| RESP-09 | 1 h quiet gap; restart-safe; one card for a burst | Mongo integration | `tests/test_autonomous_ops_incidents.py` | Wave 0 |
| RESP-10 | Dormant without tick, without token, offline, old agent; no breaker effect | Mongo integration | `tests/test_autonomous_ops_dormancy.py` | Wave 0 |
| RESP-11 | No writer to `instructions`; routes answer not-sent; `agents.isolated` unchanged | structural + route | extend `tests/test_autonomous_ops_structural.py`, `tests/test_swarm_soar_fence.py` | Wave 0 |
| ACTV-02 | Approve/deny/undo/confirm buttons and incident list | vitest + route | `src/__tests__/autonomousOpsResponse.test.tsx`, `tests/test_autonomous_ops_response_endpoints.py` | Wave 0 |
| copy | Banned terms over every new file | existing | `tests/test_autonomous_ops_copy.py`, `src/__tests__/autonomousOpsCopy.test.ts` (update file lists first) | exists, extend |
| catalogue | Mount and route parity | existing | `tests/test_catalogue_slice_autonomous_ops.py`, `tests/test_catalogue_route_parity.py` | exists, extend |

**Live-only (user):** publish and roll out agent 2.1.16; firewall round trip on Linux (root) and Windows (EILT0197, Defender on) including both directions and IPv6; a block expiring while offline and across an agent restart and a reboot; quarantine of a running file and restore on Windows; isolation with the management connection open, automatic 4 h revert (and a shortened-value dry run), reboot while isolated; restart of a real service, admin stop versus crash on both OSes; Defender behaviour for `netsh`, `sc`, `shutdown`; abuse.ch row counts.

### Sampling Rate
- **Per task commit:** the touched test file plus `test_autonomous_ops_structural.py` and the copy test
- **Per wave merge:** all `tests/test_autonomous_ops_*.py` and the three catalogue tests on the private mongod
- **Phase gate:** the Autonomous Ops subset green; one full-suite run alone before deploy; Rust unit and integration tests for touched modules

### Wave 0 Gaps
- [ ] Every test file in the table above, written before the code that satisfies it
- [ ] Rust command recorder replacing the `#[cfg(test)]` no-op `run_privileged_command`
- [ ] A hermetic Rust test fixture for `response_state.json` with an injectable clock
- [ ] Seeding helpers in `tests/autonomy_support.py` for `edr_ioc` global rows, `fim_events` and agents with `meta.response_actions` and a hostname different from the id

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Existing interactive-session and MFA requirement for approve, deny, undo, confirm, settings (`_require_interactive_session`, admin-tier `control:autonomous_ops`); API keys never approve |
| V3 Session Management | yes | Inherited |
| V4 Access Control | yes | `manage:` for settings, `control:` for decisions, `control:platform_autonomous_ops` for bulk; tenant id from the token; platform staff read-only |
| V5 Input Validation | yes | pydantic bodies with strict types and limits; server regex for service names; agent-side re-validation of every param |
| V6 Cryptography | no new use | Existing pinned TLS to the platform; hashes via `sha2` on the agent |
| V7 Error handling and logging | yes | Ledger plus audit chain for every change and decision; strings rendered as text only |
| V10 Malicious code | yes | Quarantine never executes the file; restore never auto-runs |
| V12 Files | yes | Path normalisation, symlink handling, hash binding, protected prefixes |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| R1 Feed poisoning or false positive blocks a legitimate IP | Tampering / DoS | Two distinct origins by default, global-address filter, never-touch (platform, backend, loopback), per-host scope (D-17), TTL, rate limit 20/h, breaker, freshness window on feed rows |
| R2 One compromised endpoint reports both the native verdict and an on-host detection, so two origins are not independent (D-01 allows it) | Spoofing | Blast radius is that host only (the gate binds to the host named by the verified agent path; `bind_path_agent` requires the path name to be the caller). Residual risks to document, not reopen: it can make its own host block IPs it chooses (a host it already controls), can burn the tenant's 20/h budget so other hosts fall back to cards, and can trip the breaker with failing actions (denial of the control). Add a per-host automatic cap (3 per hour, A8) and exclude `refused/noop` outcomes from the breaker |
| R3 Command or argument injection into privileged commands (tenant admin service names, agent-reported paths) | Elevation | Backend regex and agent re-validation; argv-only spawn; hash-bound quarantine; `expected_exe` on kill |
| R4 Self-inflicted outage: block of the gateway/DNS/platform, or isolation that cuts the agent | DoS | Backend never-touch plus agent refuses platform, gateway, DNS; carve-out first, self-test, agent-held revert, startup revert |
| R5 PID reuse or path reuse between decision and approval (up to 24 h) | Tampering | `expected_exe` on kill; `sha256` on quarantine; re-validation at approve |
| R6 Replay or double dispatch after agent restart | Tampering | Idempotent claim ids (instruction id), single-use approvals, `already_applied` outcome |
| R7 Cross-tenant leakage: global feed row versus tenant IOC; hostname collisions; `threat_intel_scans` `tenant_id` casing | Information disclosure | Raw handle, explicit `tenantId`, global rows filtered by absence of `tenantId` and by `source_feed`, tenant IOCs never cross tenants, unique-host resolution or skip, two-tenant tests |
| R8 Setting tampering (turning two-signal off, bulk loosening) | Tampering | Manage permission, ledger control row plus audit chain per change, bulk loosening Super Admin only with the UI's required checkbox |
| R9 Unauthenticated honeytoken webhook as an origin feeds a chosen IP | Spoofing | Deception excluded as an automatic origin (no host binding); if later used, require the proxy-trust configuration check |
| R10 Quarantine directory abuse, restore to an attacker-chosen path or over an existing file | Tampering | Destination from manifest only, refuse overwrite and reparse points, hash re-check, restore is an explicit operator action |
| R11 UI and log injection from hostnames, paths, process names | Tampering | React text rendering only (UI-SPEC), length caps server-side, no free-text indicator extraction |
| R12 Local AV or EDR blocks the actions | Availability | Distinct `blocked_by_local_security` outcome, no auto retry, documented exclusions |
| R13 Clock manipulation on the host extends a block or isolation | Tampering | Accepted residual for a host-admin attacker; relative `ttl_seconds` avoids server/agent skew |

## Sources

### Primary (HIGH confidence, read this session)
- `backend/autonomous_ops/` (`gate.py`, `registry.py`, `ledger.py`, `approvals.py`, `reconciler.py`, `dispatch_check.py`, `settings.py`, `breaker.py`, `delivery.py`, `protected.py`, `views.py`, `messages.py`, `__init__.py`, `scope.py`)
- `backend/autonomous_remediation_service.py`, `remediation_playbook_service.py`, `autonomous_ops_endpoints.py`, `autonomous_ops_platform_endpoints.py`, `catalogue_mounts_autonomous_ops.py`, `retention_job.py`, `threat_feed_sync.py`, `agent_security_scan_endpoints.py`, `agent_security_endpoints.py`, `agent_heartbeat_endpoints.py`, `agent_tasks_endpoints.py`, `agent_capabilities.py`, `agent_core_endpoints.py`, `edr_telemetry_endpoints.py`, `agent_telemetry_endpoints.py`, `deception_service.py`, `deception_endpoints.py`, `ueba_service.py`, `swarm_service.py`, `soar_engine.py`, `soar_connectors_security.py`, `tasks.py`, `playbook_engine_actions.py`, `database.py`, `agent_auth.py`
- `agent-install/omni-agent-rs/src/` (`instructions.rs`, `capabilities/remediation_actions.rs`, `capabilities/mod.rs`, `capabilities/security_scan.rs`, `capabilities/runtime_security.rs`, `capabilities/process_monitor.rs`, `capabilities/fim.rs`, `heartbeat.rs`, `config.rs`, `lib.rs`, `service.rs`, `main.rs`), `Cargo.toml`, `tests/remediation_dispatch_test.rs`
- `backend/tests/test_autonomous_ops_structural.py`, `test_autonomous_ops_copy.py`, `_mongo_test_db.py`; `shared/catalogue-access.json:162`; `.planning` context, UI-SPEC, STACK.md, PITFALLS.md; project memory (Defender quarantine, private mongod recipe)
- Local tool probes: `iptables --version`, `iptables -h`, `nft --version`, `cargo --version`

### Secondary (MEDIUM confidence)
- Web search: Elastic detection rule pages for netsh firewall disable (no source on `add rule` from a service); `windows_firewall` and `windows-wfp` crate listings (not adopted)

### Tertiary (LOW confidence, marked for validation)
- Web search results on abuse.ch Auth-Key requirement (Jentic and Archivarix mirrors, not official); treated as `[ASSUMED]` A2
- All Windows behaviour in A1, A3-A6, A10 (training knowledge)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH, no new dependencies, all reused modules read
- Architecture: HIGH for backend integration points and agent seams; MEDIUM for OS-level details
- Pitfalls: HIGH for the code-derived ones (1, 2, 6, 7, 8); MEDIUM for OS ones (3, 4, 5)
- Live feed state: LOW (not readable)

**Research date:** 2026-10-31
**Valid until:** 2026-11-30 for code facts, or until Phase 83 plans are written, whichever is first (the backend files above are active)
