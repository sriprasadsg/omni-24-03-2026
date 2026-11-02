---
phase: 83-autonomous-security-response
reviewed: 2026-11-02T12:10:00Z
depth: standard
files_reviewed: 81
files_reviewed_list:
  - App.tsx
  - agent-install/omni-agent-rs/Cargo.toml
  - agent-install/omni-agent-rs/src/capabilities/firewall.rs
  - agent-install/omni-agent-rs/src/capabilities/host_power.rs
  - agent-install/omni-agent-rs/src/capabilities/isolation.rs
  - agent-install/omni-agent-rs/src/capabilities/isolation_plan.rs
  - agent-install/omni-agent-rs/src/capabilities/mod.rs
  - agent-install/omni-agent-rs/src/capabilities/net_safety.rs
  - agent-install/omni-agent-rs/src/capabilities/privileged.rs
  - agent-install/omni-agent-rs/src/capabilities/process_kill.rs
  - agent-install/omni-agent-rs/src/capabilities/quarantine.rs
  - agent-install/omni-agent-rs/src/capabilities/quarantine_paths.rs
  - agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs
  - agent-install/omni-agent-rs/src/capabilities/response_actions.rs
  - agent-install/omni-agent-rs/src/capabilities/response_state.rs
  - agent-install/omni-agent-rs/src/capabilities/response_sweeper.rs
  - agent-install/omni-agent-rs/src/capabilities/service_watch.rs
  - agent-install/omni-agent-rs/src/config.rs
  - agent-install/omni-agent-rs/src/heartbeat.rs
  - agent-install/omni-agent-rs/src/instructions.rs
  - agent-install/omni-agent-rs/src/lib.rs
  - backend/agent_capabilities.py
  - backend/agent_heartbeat_endpoints.py
  - backend/agent_tasks_endpoints.py
  - backend/app_startup.py
  - backend/autonomous_ops/agent_support.py
  - backend/autonomous_ops/approvals.py
  - backend/autonomous_ops/breaker.py
  - backend/autonomous_ops/decision_row.py
  - backend/autonomous_ops/delivery.py
  - backend/autonomous_ops/dispatch_check.py
  - backend/autonomous_ops/followups.py
  - backend/autonomous_ops/gate.py
  - backend/autonomous_ops/incident_views.py
  - backend/autonomous_ops/incidents.py
  - backend/autonomous_ops/isolation.py
  - backend/autonomous_ops/ledger.py
  - backend/autonomous_ops/messages.py
  - backend/autonomous_ops/protected.py
  - backend/autonomous_ops/protected_paths.py
  - backend/autonomous_ops/reconciler.py
  - backend/autonomous_ops/registry.py
  - backend/autonomous_ops/response_dispatch.py
  - backend/autonomous_ops/response_messages.py
  - backend/autonomous_ops/response_settings.py
  - backend/autonomous_ops/response_views.py
  - backend/autonomous_ops/signals.py
  - backend/autonomous_ops/sweep.py
  - backend/autonomous_ops/sweep_memory.py
  - backend/autonomous_ops/sweep_restart.py
  - backend/autonomous_ops/sweep_security.py
  - backend/autonomous_ops/sweep_suggestions.py
  - backend/autonomous_ops/verify.py
  - backend/autonomous_ops/views.py
  - backend/autonomous_ops_endpoints.py
  - backend/autonomous_ops_response_endpoints.py
  - backend/autonomous_ops_response_platform_endpoints.py
  - backend/catalogue_mounts_autonomous_ops.py
  - backend/migrations/028_security_response.py
  - backend/playbook_engine_actions.py
  - backend/playbooks/quarantine_file.yaml
  - backend/remediation_playbook_service.py
  - backend/router_registry.py
  - backend/soar_engine.py
  - backend/swarm_endpoints.py
  - backend/swarm_service.py
  - backend/tasks.py
  - backend/threat_feed_sync.py
  - components/AutonomousOpsActivity.tsx
  - components/AutonomousOpsActivityList.tsx
  - components/AutonomousOpsDecisions.tsx
  - components/AutonomousOpsIncidentCard.tsx
  - components/AutonomousOpsResponseSettings.tsx
  - components/AutonomousOpsResponseSettingsDialogs.tsx
  - components/AutonomousOpsResponseSettingsPlatform.tsx
  - components/AutonomousOpsRowActions.tsx
  - components/SwarmDashboard.tsx
  - services/autonomousOpsApi.ts
  - services/autonomousOpsIncidentsApi.ts
  - shared/agent-response-contract.json
  - shared/autonomous-ops-banned-terms.json
findings:
  critical: 2
  warning: 30
  info: 23
  total: 55
status: issues_found
---

# Phase 83: Code Review Report

## Summary

Four gsd-code-reviewer passes ran in parallel at standard depth over the 81 Phase 83 source files (backend core, backend routes and wiring, Rust agent, frontend), scoped from the SUMMARY key-files, the phase commits and the evaluation scope. Tests were reference only. Nothing was run. The orchestrator merged and renumbered the parts (map below), checked both Critical findings and the two findings that changed against the code, and corrected those two in place.

**2 critical, 30 warning, 23 info.** Both criticals are in the Rust agent, which is not yet published (2.1.16); they must be fixed before it is. Nothing in the backend or frontend is critical. Questions carried from earlier stages are answered in the reviewer notes at the end: no path reaches an automatic quarantine of a protected path today, tenant isolation holds, A-83-ONE-PATH does not hold (WR-02), and the over-budget restart card stays approvable after recovery (WR-03).

## Critical Issues

### CR-01: [agent] No child-process timeout while process-wide locks are held: one hung firewall command stops the isolation revert, every block expiry and the agent loop

_Source: Rust agent CR-01_


**File:** `agent-install/omni-agent-rs/src/capabilities/privileged.rs:58-68` (also `response_sweeper.rs:87`, `response_state.rs:127,181-191`, `isolation.rs:35-39,377-380`, `response_actions.rs:301`, `lib.rs:212,229`)
**Issue:** `run_output` calls `Command::output()` with no timeout and no kill. Every Linux firewall call carries `-w`, which waits for the xtables lock with no upper bound. `netsh`, `sc`, `systemctl`, `shutdown` and `route` can hang too (a stalled Windows Firewall service, a stuck unit job).

The callers all hold something while they wait:
- `expire_due`, `reapply_live`, `unblock`, `due_pass`, `apply`, `restore` and the quarantine run their commands inside `Store::update`, so they hold the process-wide `WRITE_LOCK`. The isolation ones also hold `isolation::LOCK`.
- The sweeper loop does `spawn_blocking(...).await` on each pass (`response_sweeper.rs:87`). A pass that never returns means the loop never ticks again, so no later pass runs.

Failure scenario on a real host, with a firewall tool stuck for a long time (a fail2ban or docker bulk restore holding the xtables lock; on Windows a hung `netsh advfirewall`):
1. The 15-second pass or an `isolate_host` is inside `iptables -w ...`. It never returns.
2. The isolation `revertAt` passes. The pass that would lift it is the one that is stuck, so the host stays cut off from everything except the platform. This breaks D-15's promise that the agent holds its own revert.
3. Every `Store::update` after that blocks on `WRITE_LOCK` with no timeout. `block_ip`, `unblock_ip` and the quarantine arms run inline on the agent-loop task (`handle` -> `handle_at`, `response_actions.rs:90,301`). `isolation::apply_body` does the same when a heartbeat reply carries `isolationConfirmed` (`lib.rs:212`). The agent loop stops: no heartbeats, no instruction polls, and the host appears offline.

The same missing timeout is inside the heartbeat build: `service_watch::report` runs up to 50 `systemctl show` or `sc query` calls in sequence on the loop task (`heartbeat.rs:542`, `service_watch.rs:180-196`).

**Fix:** Give `run_output` a deadline (for example 20 s): spawn the child, poll `try_wait` with a short sleep, and on expiry `kill()` it and return `OperationFailed("... timed out")`. Add `-W 2000000` style wait limits to the iptables `-w` calls (`-w 10`). Inside `Store::update`, fail the pass on a timeout rather than wait. Move the inline firewall arms of `handle_at` (`block`, `unblock`, `reboot_host`) into `spawn_blocking` like the quarantine arms. Use `try_lock` with a bounded retry, or `spawn_blocking`, for `isolation::apply_body`.

```rust
let mut child = Command::new(program).args(args).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn()?;
let deadline = Instant::now() + Duration::from_secs(20);
loop {
    if let Some(status) = child.try_wait()? { /* collect output */ break; }
    if Instant::now() >= deadline { let _ = child.kill(); return Err(timeout_error(program)); }
    std::thread::sleep(Duration::from_millis(50));
}
```
(Read the pipes on separate threads, or redirect to temp files, so a chatty child cannot fill the pipe before `try_wait` sees it exit.)

### CR-02: [agent] The agent's "never block a non-public network" guard only tests the CIDR's base address, so `172.0.0.0/8` or `192.0.0.0/8` passes and drops the LAN

_Source: Rust agent CR-02_


**File:** `agent-install/omni-agent-rs/src/capabilities/net_safety.rs:281-302` (check at 287; `parse_network` at 80-97)
**Issue:** `refuse_reason` calls `is_global_address(target.addr)` once, on the masked network address, and then only refuses a prefix shorter than /8. A network is judged by its first address. `172.0.0.0/8` has base `172.0.0.0`, which is global (second octet 0, not in 172.16/12), and /8 is allowed. It covers 172.16.0.0/12, all of RFC1918's middle block. The same holds for `192.0.0.0/8` (covers 192.168/16, 192.0.0/24, 192.0.2/24), `100.0.0.0/8` (CGNAT 100.64/10), `169.0.0.0/8` (169.254/16, including cloud metadata), `198.0.0.0/8` (198.18/15), `203.0.0.0/8`, and any /9-/15 inside those, such as `192.128.0.0/9`. No test covers this (`net_safety_tests.rs:213,229` only list /8 networks that are fully public).

Failure scenario: a card, a playbook bug or an over-wide `block_ip_range` carries `172.0.0.0/8`. The agent writes `-s`/`-d 172.0.0.0/8 DROP` into `OMNI_BLOCK` for up to 7 days, and the host loses file servers, domain controllers and anything else on 172.16/12. The only remaining protections are the platform-address, gateway and DNS checks. Those are best effort (`read_host_addrs` logs and continues when a file or command fails) and say nothing about the rest of the LAN. The doc comment on `refuse_reason` and 83-SECURITY T-83-12 both state the agent refuses these independently of the backend.

**Fix:** Refuse any network that overlaps a non-global class, not just one that starts in one. For each non-global range, test overlap of the two intervals, or test the network's first and last address plus every non-global range's first address.

```rust
const NON_GLOBAL_V4: &[(u32, u8)] = &[ /* (base, prefix) for 0/8, 10/8, 100.64/10, 127/8, 169.254/16, 172.16/12, 192.0.0/24, 192.0.2/24, 192.168/16, 198.18/15, 198.51.100/24, 203.0.113/24, 224/3 */ ];
fn overlaps(net: (IpAddr, u8), other: (IpAddr, u8)) -> bool {
    let p = net.1.min(other.1);
    mask(net.0, p) == mask(other.0, p)
}
```
Add the three networks above, and a /9 that straddles one, to the tests.

## Warnings

### WR-01: [backend core] A persisted origin never goes stale, so one fresh signal can pair with an old one

_Source: backend/autonomous_ops WR-01_


**File:** `backend/autonomous_ops/signals.py:466-491` (`counting_origins`, `corroborated`), used at `backend/autonomous_ops/sweep_security.py:339-344`
**Issue:** `observe` honours `NATIVE_WINDOW` (25 h) and `FEED_WINDOW` (48 h) only when it reads sources. Once an origin is stored on an `autonomy_signals` document it stays forever. `counting_origins` applies no `lastSeenAt` or `evidenceAt` limit unless `evidence_after` is given, and `run()` passes that only after a previous block has expired (`after` is None otherwise). `corroborated` compares `firstSeenAt` values only. The top-level `lastSeenAt` is refreshed by any origin, so the TTL index does not drop the document.

Failure scenario, with every tenant in shadow by default, as D-02 sets up:
- Day 3: a host talks to IP X. URLhaus lists X (origin A) and an operator native scan flags it (origin B), 2 h apart. The pair agrees, and the sweep records a simulation.
- Day 20: a Super Admin lifts shadow. The host talks to X again and URLhaus still lists it. The native verdict is 17 days old and is no longer read, but it is still in the document.
- `observe` touches the candidate through origin A, and `corroborated` sees A and B within 24 h of each other by their first sightings. The sweep blocks X on one fresh signal plus a 17-day-old one.
- The same happens for a quarantine when a dormant tenant becomes active (capability ticked or host back online) after weeks.

This contradicts the module's own windows, D-01 ("different origin") and the point of D-14 ("stale evidence must not count"). D-14 is only enforced after a block, because it needs `began`.
**Fix:** Make an origin count only while its source still vouches for it, by passing `now` into `counting_origins` and `corroborated`:
```python
_ORIGIN_WINDOW = {"native": NATIVE_WINDOW, "onhost": NATIVE_WINDOW, "virustotal": NATIVE_WINDOW}  # feeds: FEED_WINDOW

def counting_origins(doc, evidence_after=None, *, now=None):
    ...
    for name, value in (origins or {}).items():
        ...
        if now is not None:
            window = _ORIGIN_WINDOW.get(name, FEED_WINDOW)
            seen = _aware(value.get("lastSeenAt"))
            if not isinstance(seen, datetime) or now - seen > window:
                continue
```
Call it with `now=now` from `sweep_security.run` (lines 340 and 344). Add a test: a 17-day-old origin plus a fresh one gives `corroborated` False.

**Orchestrator check (2026-11-02):** the example as written does not hold. `signals.corroborated` (signals.py:482-491) requires the two origins' `firstSeenAt` to be at most 24 hours apart, so a 17-day-old verdict plus a fresh feed listing does not corroborate. What survives: once two origins were first seen within 24 hours of each other, neither ever expires (`lastSeenAt` and `evidenceAt` are not consulted outside D-14), so a pair recorded while a tenant sat in shadow still counts weeks later when shadow is lifted.

### WR-02: [backend core] A file signal keeps the alphabetically first path, not the newest (A-83-ONE-PATH)

_Source: backend/autonomous_ops WR-02_


**File:** `backend/autonomous_ops/signals.py:248-249` (`_Acc.origin`), `signals.py:253-254` (`_Acc.has_hash`), `signals.py:412-413` (`_record`)
**Issue:** The path is chosen with `path < self.paths[key]`, so the lexicographically smallest path wins. It is not the most recent evidence. `_record` then overwrites the stored `path` with whatever this pass chose, so the target also changes between ticks when a different set of sources is visible (a FIM event in the 25 h window, a process `exe`, a scan target).

Failure scenario: the same sha256 exists at `C:\Users\a\Downloads\evil.exe` (an old FIM event) and `C:\Windows\Temp\evil.exe` (the newest native scan target). The sweep picks the Downloads copy. If that copy is gone, the agent answers `hash_mismatch` or not found, the row ends `refused`, and the sweep stays quiet for 24 h (`sweep_memory.WINDOWS["refused"]`), while the live copy stays on disk. The dedupe key has no path, so a second copy is never targeted.
**Fix:** Keep `(evidence_time, path)` and take the max by time. `has_hash` needs a time too (use `self.now` for telemetry):
```python
if path:
    cur = self.paths.get(key)
    if cur is None or (evidence, path) > cur:
        self.paths[key] = (evidence, path)
```
Store only `path` in `_record`.

### WR-03: [backend core] An over-budget restart card stays approvable after the service has recovered (question 4)

_Source: backend/autonomous_ops WR-03_


**File:** `backend/autonomous_ops/approvals.py:73-114` (`_revalidate`); `backend/autonomous_ops/sweep_restart.py:231-244` (`run`)
**Issue:** The card comes from `sweep_restart._request(over_budget=True)`, with the `|card` key and `playbook_raise`. For up to 24 h it stays in `awaiting_approval`. `_revalidate` re-checks tenant eligibility, the target agent, the never-touch list, and capability, online and token. It does not check that the service is still failing. `sweep_restart.run` walks only agents that currently report `meta.service_failures`, so nothing ever supersedes or expires a card whose service has come back. Sweep suggestions have `_close_gone` for this, and restart cards have no equivalent.

Failure scenario: 10:00, `Spooler` fails 3 times and a card is raised. 10:05, an admin fixes it by hand. 17:30, someone clicks Approve on the stale card. The consequence is a restart of a healthy service and an unplanned outage on a production host.
**Fix:** In `_revalidate`, for a `restart_service` row with `reason.inputs.overBudget`, re-read `agents.meta.service_failures` for this tenant and agent and refuse with a plain code (for example `service_recovered`, with REASON_TEXT) when `params.service_name` is not listed. Also have `sweep_restart` expire an open `|card` row whose service no longer fails, as `_close_gone` does.

### WR-04: [backend core] Restart budget (3) equals breaker threshold (3), so one dead watched service lowers the whole tenant to Suggest

_Source: backend/autonomous_ops WR-04_


**File:** `backend/autonomous_ops/sweep_restart.py:45` (`RESTART_BUDGET = 3`, `WAITS` 60/120/240 s); `backend/autonomous_ops/__init__.py:40` (`BREAKER_THRESHOLD = 3`); `backend/autonomous_ops/ledger.py:246` and `ledger.py:261-268` (`BREAKER_FAILURES`, `recent_finished_auto`)
**Issue:** An automatic restart is an `autoDispatched` row. `recent_finished_auto` selects the tenant's three most recent finished automatic rows of any command. `verify_failed` and `agent_failed` are on the counted list. A service that cannot be brought back (disabled, missing dependency, bad config) uses its whole budget of 3 restarts within about 3 minutes and ends `verify_failed` or `agent_failed` each time. Those three rows are exactly the three the breaker looks at. `breaker.evaluate` runs from the reconciler and sets the tenant's level to `suggest` with a notice, and a manager must restore it by hand.

Failure scenario: one watched service on one host is broken. Within minutes every automatic block IP and quarantine for that tenant becomes a Suggest-only row, which is a loss of automatic containment during a possible incident. It fails in the safe direction, but it is surprising and costly. Security observation 6 covers a host misreporting; this is the ordinary case.
**Fix:** Keep restarts out of the breaker's window, because their failures are already bounded by the budget and a card. In `ledger.recent_finished_auto` add `"command": {"$ne": "restart_service"}` to the filter. Alternatively count a restart failure only when the same service has failed in two separate hours. Add a test: three failed restarts do not trip the breaker.

### WR-05: [backend core] `_agreeing` includes origins that are not within 24 hours of the agreeing pair, so the recorded "why" can name the wrong sources

_Source: backend/autonomous_ops WR-05_


**File:** `backend/autonomous_ops/sweep_security.py:69-77`
**Issue:** After finding the first adjacent pair within 24 h, the code returns every origin where `firstSeenAt - start <= window`. There is no lower bound, so origins that started before the pair are included (a negative difference passes).

Example: A is first seen at t0, B at t0+30 h, C at t0+31 h. The agreeing pair is (B, C), but the function returns [A, B, C]. The row then stores `origins` = [A, B, C], and `why_two_sources` names the first two by display name, which may be A and B, 30 h apart and not the pair that satisfied the rule. The decision itself is made by `signals.corroborated`, so no unsafe action results. The ledger reason is wrong, which breaks the guarantee in T-83-11 that the sentence is always true. `sweep_memory.skip_reason` also compares against `sorted(live)`.
**Fix:**
```python
return sorted(n for n in order
              if 0 <= (live[n]["firstSeenAt"] - start).total_seconds() <= signals.CORROBORATION_WINDOW.total_seconds())
```

### WR-06: [backend core] Approving a card while the host is briefly offline burns the single-use decision

_Source: backend/autonomous_ops WR-06_


**File:** `backend/autonomous_ops/approvals.py:105-110` and `approvals.py:155-159`
**Issue:** `_revalidate` calls `agent_support.check`, whose `online` test needs `lastSeen` within 5 minutes. On `agent_offline` the approval CAS has already moved the row to `approved`, and it is then moved to terminal `refused`. The card cannot be approved again. A transient gap of more than 5 minutes (a sleeping laptop, a missed heartbeat) therefore consumes the approver's decision.

The isolate line is the worst case: `incidents.claim_isolate` (incidents.py:110) is spent once per incident and is released only when the gate records nothing. `sweep_memory` holds a refused finding for 24 h (`WINDOWS["refused"]`), unless a new origin appears. After one unlucky click the incident has no isolation card and a kill or quarantine card is not re-raised for a day.
**Fix:** For `agent_offline` only, do not consume the card. Either answer `refused` without transitioning (restore the row to `awaiting_approval` with the same expiry), or queue the instruction anyway so the existing `not_delivered` bound (30 min) handles a host that never returns. Keep the hard refusals (`capability_off`, `agent_unsupported`, protected target) as they are.

### WR-07: [backend core] One failing sweep stage skips every later stage for that tenant, including restarts and the isolation revert bookkeeping

_Source: backend/autonomous_ops WR-07_


**File:** `backend/autonomous_ops/sweep.py:79-84`
**Issue:** The `try` wraps the whole `for stage in _STAGES` loop. `sweep_security.run` is first in the tuple and has several unguarded awaits (`signals.observe`, `gate.decide`, `incidents.claim_isolate`). Any exception there, such as a malformed `autonomy_signals` document, aborts the rest of that tenant's tick, so `sweep_suggestions`, `sweep_restart` and `isolation.run` never run. If the cause is persistent (a bad document in `_merge`, a bad value in a feed row) it repeats every 60 s. Restarts stop for that tenant, and `isolation.run` stops moving expired isolation rows to `rolled_back` / `auto_reverted`.
**Fix:** Isolate stages from each other:
```python
for stage in _STAGES:
    try:
        for key, value in (await stage(db, tenant_id, tenant, response, now)).items():
            counts[key] = counts.get(key, 0) + value
    except Exception as exc:
        logger.error("autonomous_ops: sweep stage %s failed for tenant %s: %s", stage.__module__, tenant_id, exc)
```

### WR-08: [backend routes] The shipped `quarantine_file` playbook can never produce a working quarantine from the legacy remediation path

_Source: backend routes and wiring WR-01_


**File:** `backend/playbooks/quarantine_file.yaml:8-9`, `backend/remediation_playbook_service.py:134-140`, `backend/autonomous_remediation_service.py:334`
**Issue:**
- The playbook renders `sha256: "{{finding.details.sha256}}"` and `path: "{{finding.resource_id}}"`.
- `autonomous_remediation_service.scan_for_remediable_findings` builds nscan findings with `details={"type", "verdict", "ts"}` only (line 334). The scan row's `sha256` stays in `raw_doc` and never reaches `details`.
- `_render_step_params` therefore yields `sha256: None`.
- `select_playbook` (line 134-140) sends every non-`ip` nscan type to `quarantine_file`. Native scan types include `url` and `hash` as well as `file`, so for those types `resource_id` is a URL or a hash, not a path.
- The Rust agent answers `refused("path and sha256 are required.")` (`response_actions.rs:144-148`).

**Failure scenario:**
1. A Malicious native verdict for a URL or hash target, or for a file, becomes a `quarantine_file` card with `sha256` null.
2. A person approves it.
3. The agent refuses, and the row ends `failed` or `refused` for a reason the person could not have seen.
4. If the refusal counts toward the breaker (security audit observation 6), repeated attempts lower the tenant's level.
5. The sweep path (`sweep_security._params`) handles the same verdicts with a real indicator and path. The legacy path therefore adds only noise and duplicate cards.

**Fix:**
```python
# autonomous_remediation_service.py, the nscan finding
details={"type": s.get("type"), "verdict": s.get("verdict"), "ts": s.get("created_at"),
         "sha256": s.get("sha256")},
```
```python
# remediation_playbook_service.select_playbook
if scan_type in ("file", "hash"):
    return by_name.get("quarantine_file") if details.get("sha256") else None
return None
```

### WR-09: [backend routes] The feed upsert can match a tenant's own IOC row instead of the global row

_Source: backend routes and wiring WR-03_


**File:** `backend/threat_feed_sync.py:219-222`
**Issue:**
- The filter is `{"ioc_type", "ioc_value"}` with no `tenantId: {"$exists": False}`.
- `edr_telemetry_endpoints.add_ioc` lets any `manage:security_cases` user insert a tenant-stamped row with any type and value.
- `update_one(..., upsert=True)` then matches that tenant row. The feed fields are written onto it and no global row is created.
- The sweep reads global rows only (`signals._read_feeds`, `glob = {"tenantId": {"$exists": False}}`), so the corroborating feed origin disappears for every tenant.
- The same match also overwrites the tenant's own `threat_type` and `confidence`.

**Failure scenario:** One analyst adds the hash of a known-bad file as a manual IOC. The next sync folds URLhaus into that tenant row. The global row never exists, so no tenant gets the second origin for that hash, and the failure is silent. The direction is fail-safe (fewer actions), but D-01/D-26 are defeated for the indicator.

**Fix:** Filter on `{"ioc_type": ..., "ioc_value": ..., "tenantId": {"$exists": False}}`. A global row would then be created beside the tenant's row. If the upsert needs a unique key, add a partial unique index on the global rows.

### WR-10: [backend routes] The result route stores agent free text unbounded and crashes on a non-string status

_Source: backend routes and wiring WR-04_


**File:** `backend/agent_tasks_endpoints.py:94-98, 108-115`
**Issue:**
- `bounded_result` limits only the structured keys. `message_text`, `error_msg` and `raw_status` are stored as posted. Any JSON type is accepted: a dict, a list or a multi-megabyte string, up to the Mongo 16 MB document limit.
- `raw_status.upper()` (line 95) raises `AttributeError` when `status` is a number, list or object. The route answers 500 and the instruction is never updated, so a task whose agent keeps posting a malformed status stays `sent`.
- This is pre-existing code, but this phase made the route the T-83-01 boundary for a security verdict.
- The free text does not reach the ledger (I checked `verify.settle` and `response_views`). It is shown through `get_task_status` only.

**Failure scenario:** A faulty agent build posts `{"status": null}` or a very large `message` for a response task. The result is a 500 or an oversized `agent_instructions` row, and the ledger row waits for the no-result bound.

**Fix:**
```python
raw_status = result.get("status")
raw_status = raw_status if isinstance(raw_status, str) and len(raw_status) <= 32 else "unknown"
def _text(v, n=2000): return v[:n] if isinstance(v, str) else ""
error_msg = _text(result.get("error") or nested.get("error"))
message_text = _text(result.get("message") or result.get("details") or nested.get("output") or nested.get("message"))
```

### WR-11: [backend routes] A SOAR run with a fenced step still reports `status: completed`

_Source: backend routes and wiring WR-05_


**File:** `backend/soar_engine.py:59, 82-83, 122`
**Issue:**
- The per-node status is now `not_sent` (PROH-83-10), but the run-level `status` stays `"completed"`.
- `soar_endpoints.run_and_save` stores that run-level status in `soar_runs`. The Runs list therefore shows a completed run whose only containment step sent nothing.
- Downstream nodes still run after a `not_sent` node: edges are followed regardless, so a notify or ticket node can say the host was contained.

**Failure scenario:** A playbook is `block_ip_firewall`, then `send_email "IP blocked"`. The email goes out and the run reads "completed", but nothing was blocked.

**Fix:** After the loop set `status = "partial"` (or `"not_sent"`) when any logged node has `status == "not_sent"`. Do not follow edges out of a `not_sent` node unless the edge opts in.

### WR-12: [backend routes] A failed migration 028 is swallowed, and the sweep starts without the indexes it relies on

_Source: backend routes and wiring WR-06_


**File:** `backend/app_startup.py:238-242, 513-515`; `backend/migrations/028_security_response.py:22-26`
**Issue:**
- `run_migrations` failures are only logged, and `autonomous_ops_sweep` is started unconditionally.
- Signal upserts and `incidents.attach` both depend on the unique indexes: `attach` handles `DuplicateKeyError`, which only exists with `incident_one_open`.
- If 028 fails once (a transient Mongo error, or an index conflict), the sweep runs unprotected and can create duplicate signals or duplicate open incidents.
- Once such duplicates exist, `create_index(unique=True)` fails permanently with `DuplicateKeyError`. 028 can then never apply, and the failure is again only a log line.
- The runner also has no lock, so two workers can both apply 028. That is harmless here because `create_index` is idempotent.

**Fix:** Have the sweep loop (or `run_startup_services`) check that `signal_unique` and `incident_one_open` exist and skip the sweep with an error log if not. Alternatively, make 028 dedupe before creating the unique indexes.

### WR-13: [agent] Protected-path and own-file checks compare text, confirmed bypasses on Linux and Windows (question 1)

_Source: Rust agent WR-01_


**File:** `agent-install/omni-agent-rs/src/capabilities/quarantine_paths.rs:141-156` (`normalize`), `175-193` (`is_under`, `under_protected`), `quarantine.rs:314-320`
**Issue:** After `normalize` (Linux: trims trailing `/`; Windows: lower-case, `/` to `\`, drop `\\?\`, trim trailing `\`) the path is compared by prefix. `has_dotdot` rejects only `..` parts. These inputs reach `std::fs::symlink_metadata`/`rename` as the protected file but do not match `PROTECTED_LINUX`/`PROTECTED_WINDOWS` or `own_paths`:
- Linux: `//etc/passwd` (`is_under("//etc/passwd","/etc/")` is false), `/./etc/passwd`, `/etc//passwd` is fine but `/usr//bin/ssh`, `/usr/bin/./ssh`; any path whose parent directory is a symlink (`/home/u/d/passwd` with `d -> /etc`): `symlink_metadata` on the full path follows the symlinked parent, `meta.is_file()` is true, and `rename` moves `/etc/passwd`. Only the final component is checked for being a link.
- Windows: `C:\Windows\System32.\x.dll` and `C:\Windows\System32 \x.dll` (Win32 strips trailing dots and spaces), `C:\Windows\\System32\x`, `C:\Windows\.\System32\x`, `C:\PROGRA~1\OMNIAG~1\omni-agent.exe` (8.3 names bypass both the protected list and `own_paths`), `C:\Windows\System32\x::$DATA`, `\\localhost\C$\Windows\System32\x` (`under_protected` returns false for anything without a drive letter), and NTFS junction parents.

Impact is limited as 83-SECURITY says: the hash must equal the one the backend flagged, and a restore exists. The remaining risk is that a symlink or junction planted by a local user in a scanned folder makes a flagged-file card move an OS file or the agent's own binary (`omni-agent.exe` moved aside means the service cannot restart). A file moved from `/etc` or `System32` can stop the host from booting or logging in.

**Fix:** Decide on the canonical path, not the text. After the cheap checks, `std::fs::canonicalize(parent)` (resolves `//`, `.`, symlinks, junctions and, on Windows, 8.3 names and trailing dots), join the file name, normalise that, and run `is_own_file` and `under_protected` on both the requested and the canonical form. Refuse if either is protected. On Windows also refuse a path containing `:` after the drive, a trailing dot or space in any part, and any UNC or `\\.\` form unless it resolves to a local drive. Add the inputs above to `quarantine_tests.rs`.

### WR-14: [agent] Legacy `kill_process` path: PID kills skip the critical-process list, name kills hit every match, and a missing `expected_exe` silently selects it (question 2)

_Source: Rust agent WR-02_


**File:** `agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs:77-143`, `response_actions.rs:181-188`
**Issue:** Confirmed that with no `expected_exe` the kill is by PID or name with no start time or image binding. In more detail:
1. The numeric branch (lines 84-107) returns before the `CRITICAL_PROCESS_NAMES` check at 109-112. Only PID 0/1 and the agent's own PID are refused. A PID whose process is now `lsass.exe`, `csrss.exe`, `wininit.exe`, `winlogon.exe`, `systemd` (when not PID 1 of a container) or `sshd` is killed. Approvals can be a day old (`process_kill.rs` header says so), so PID reuse is a realistic route. Killing `lsass`, `csrss` or `wininit` forces a Windows restart within about a minute.
2. A name target kills every process with that exact, case-sensitive name (lines 121-141). `CRITICAL_PROCESS_NAMES` has no `sshd`, `dbus-daemon`, `NetworkManager`, `systemd-journald`, `svchost.exe` or `explorer.exe`. `kill_process("sshd")` ends the listener and every session, which locks out the administrator. On Linux sysinfo names are the 15-character `comm`, so unrelated programs can share a name.
3. `kill_arm` chooses the legacy path only because `expected_exe` is absent (line 182). An instruction that carries `processes` or `quarantine_id` but lost `expected_exe` is silently treated as "kill `target`", dropping the binding the sender asked for.

**Fix:** Apply the critical-name check to the process found for a PID as well (look up `proc.name()` and refuse on a match). Add `sshd`, `dbus-daemon`, `networkmanager`, `systemd-journald`, `svchost.exe`, `explorer.exe`, `lsm.exe`, `services.exe` to the list. In `kill_arm`, if `processes` or `quarantine_id` is present without `expected_exe`, return `refused_body`. Longer term, give the Phase 53 card a pid plus start time and route it through `plan_kill`.

### WR-15: [agent] The `expected_exe` kill with no quarantine kills every process running the same image, listed or not

_Source: Rust agent WR-03_


**File:** `agent-install/omni-agent-rs/src/capabilities/process_kill.rs:78-80`
**Issue:** `(None, false) => on_original.then_some(true)`: with `moved_exe` absent, a process that is not in `processes` but runs the same image is put in `kill`. The binding to a pid and start time holds only for listed processes. If the card names a shared interpreter or host program (`/usr/bin/python3`, `/usr/bin/java`, `/usr/sbin/sshd`, `C:\Windows\System32\svchost.exe`'s name is critical but `powershell.exe`, `cmd.exe`, `msiexec.exe` are not), every other instance on the host is killed, including the ones the person did not see on the card. `extra_instances` then also counts them as survivors.

**Fix:** Kill only listed pids (with matching start time and image). Treat an unlisted process on the image as `unconfirmed`, as the `moved` case already does, unless the image lies under the quarantine directory.

### WR-16: [agent] A second `isolate_host` while isolated answers `already_applied` / `verify.ok = true` without checking the rules or the id

_Source: Rust agent WR-04_


**File:** `agent-install/omni-agent-rs/src/capabilities/isolation.rs:254-266` (answer at 263, body at 52-54), `408-417`
**Issue:** If any isolation record exists, `apply_with` returns `already_applied_body()` immediately. It does not compare ids, does not extend or reset `revert_at`, and does not check that the rules are present. Failure scenarios:
- The platform records the second task's id as the isolation id, but the agent's record carries the first. `isolationConfirmed: [<second id>]` then matches nothing in `apply_confirmations` (line 411), so the isolation is never confirmed and reverts after 4 hours while the platform believes it is held indefinitely.
- The record is left over from a failed back-out (`revert_at = now`, lines 174-177) or from rules that were cleared by hand or by a Group Policy refresh. The new request is answered "isolated, management connection open" and a few seconds later the sweeper lifts it, or the host was never isolated at all.

**Fix:** On an existing record, check `rules_present(os)`. If the rules are missing or the revert is already due, reapply under the existing record, or replace the record with the new id. If the id differs, return a distinct outcome (or adopt the new id) so the confirmation path matches the id the platform stored.

### WR-17: [agent] `restore_host` with no record answers `not_found` / `network_restored ok` without looking at the firewall

_Source: Rust agent WR-05_


**File:** `agent-install/omni-agent-rs/src/capabilities/isolation.rs:312,335-339`, `349-373`
**Issue:** `restore` returns `Ok(false)` when `s.isolation` is `None`, and then reports `not_found` with `verify.ok = true` and issues no firewall command. `due_pass` also does nothing without a record, and the only "rules but no record" repair is Linux `start_up` in the opposite direction (record but no rules). So if the state file is missing (NotFound loads as an empty state, `response_state.rs:164`), for example after a reinstall or cleanup that removes the install folder's data, a Windows host keeps `blockinbound,blockoutbound` and the `OmniAgent_Isolate_Allow_*` rules forever. The operator's restore is marked Done with a green check.

**Fix:** In `restore`'s `not_found` branch and in a start-up pass, run `rules_present(os)` and, if the rules are there, call `force_revert(os)` and report `restored` with `verify.ok = !rules_present(os)`. Report `not_found` only when both the record and the rules are absent.

### WR-18: [agent] A damaged or newer-version state file is a dead end: blocks never expire, cannot be unblocked, and nothing quarantines or restores

_Source: Rust agent WR-06_


**File:** `agent-install/omni-agent-rs/src/capabilities/response_state.rs:161-176,181-191,243-250`; `quarantine.rs:344,403`
**Issue:** `load` returns an error for unparseable JSON or `v > STATE_VERSION`, and `update` then does not run `change`. This is deliberate (an empty state would forget live blocks). But there is no way out. `run_pass` logs "pass skipped" every 15 seconds forever. A block's firewall rule stays with its claim unreadable, `unblock_ip` fails, `quarantine_file` and `unquarantine_file` fail (both go through `Store::update`, although restore needs only the manifest), and the heartbeat only sets `state_unreadable`. A version downgrade (agent 2.1.16 back to an older Rust build, or a newer agent writing `v: 2` and then being rolled back) produces this state.

The one thing that does react, `isolation::due_pass`, treats every `Err` as "state lost" and lifts the isolation (lines 368-371). That includes a confirmed isolation and a transient read error (EIO, a sharing violation on Windows), so a person's confirmed isolation can end on a momentary read failure.

**Fix:** On a parse failure, rename the file to `response_state.json.corrupt-<ts>`, log, and start from an empty state. First sweep the firewall for the agent's own `OMNI_BLOCK` chain and `OmniAgent_Block_*` rules (the agent owns them) so nothing is forgotten. Retry a read error a few times before treating the file as lost. Do not let `restore_at` depend on the state file.

### WR-19: [agent] `Cmd::passes` turns every failure into "not present": a failed check can drop a live claim, or add a duplicate rule

_Source: Rust agent WR-07_


**File:** `agent-install/omni-agent-rs/src/capabilities/firewall.rs:78-84`, `265-289`; `response_state.rs:283-287`
**Issue:** `passes` is `false` for a spawn failure, a lock timeout, a permission error and a missing binary, as well as for "rule absent" (iptables `-C` exit 1; netsh "No rules match"). `remove_block` skips a step whose check fails and returns `Ok(false)`. `expire_due` takes `Ok(_)` as success and drops the claims. If `iptables -C` fails for a reason other than absence while the rule is in place (iptables not yet usable early in boot, agent restart during a firewall reload), the rule stays in the kernel with its claim forgotten: a block that never ends. The mirror case in `apply_block` appends a second copy of the rule, and `remove_block` deletes only one copy per pass.

**Fix:** Have the check return a tri-state (Present, Absent, Error), mapping only iptables exit code 1 (and netsh's no-match) to Absent. In `remove_block`, return an error on `Error` so the claim stays and the next pass retries. In `apply_block`, fail the step rather than add.

### WR-20: [agent] Isolation "verify" is not an isolation test; on Windows only the default policy changes

_Source: Rust agent WR-08_


**File:** `agent-install/omni-agent-rs/src/capabilities/isolation_plan.rs:194-213`, `isolation.rs:219-224,294-301`
**Issue:** The Windows block step is only `netsh advfirewall set allprofiles firewallpolicy blockinbound,blockoutbound`, and "effective" is a read-back of that policy. A default-block policy still lets through every enabled allow rule: the built-in Core Networking group (outbound DNS to any address, among others), any rule an installer added for a browser or a sync client, and the inbound Remote Desktop rule when the platform's own `enable_rdp` has switched it on. The answer is still `isolated` with `management_connection_open ok`. The self-test (`tcp_self_test`) proves only that the platform is reachable, which is true whether or not the host is isolated. On Linux, "effective" is `-C <hook> -j <chain>`, which was just inserted, so `not_effective` can never fire there either. None of this has run on a Windows host, and a security card that says "isolated" while an attacker's RDP session or DNS tunnel still works is the worst kind of wrong answer.

**Fix:** Add a negative probe to step 5: after the block, try to connect to a public address that is not the platform (a fixed address on a fixed port, with a short timeout, or the platform address on a closed port, or the host's own default gateway). If it connects, undo and answer `not_effective`. For Windows, also disable the enabled inbound allow rules for the isolation period (saving which ones to re-enable), or document and report the limit in the outcome.

### WR-21: [agent] `restart_service` checks the characters and the critical list only: unit type and the tenant's watched list are not enforced on the agent

_Source: Rust agent WR-09_


**File:** `agent-install/omni-agent-rs/src/capabilities/service_watch.rs:209-216,249-272`; `remediation_actions.rs:68-73,213-227`
**Issue:** `validate_service_name` accepts any name of letters, digits, `-`, `_`, `.` that is not in a short list. On Linux, `systemctl restart <name>` accepts any unit type, so `reboot.target`, `poweroff.target`, `halt.target`, `rescue.target`, `emergency.target`, `sshd.socket`, `ssh.socket`, `dbus.socket`, `systemd-networkd`, `systemd-logind` and `network.target` all pass (the `.service` suffix is stripped only for the critical-list comparison, line 222). Restarting a power target reboots or halts the host. The agent never checks that the name is in `cfg.watched_services` (`restart_arm` has `cfg` in hand), although the module's design is that only listed services are touched. The agent therefore trusts the backend for the whole question; 83-SECURITY calls this "within budget" on the platform, but the other controls in this phase (`CRITICAL_SERVICE_NAMES`, "the agent refuses them again") exist so that the agent does not rely on that.

**Fix:** In `restart_arm`, require `name` (case-insensitively) to be in `cfg.watched_services`. On Linux accept only a bare name or a `.service` suffix; reject `.target`, `.socket`, `.mount` and the like. Add `systemd-logind`, `systemd-networkd`, `network`, `networking` to the critical list.

### WR-22: [agent] Large quarantines hold the state lock and the agent loop; isolate/restart final result is ordered by a 2-second sleep and is never retried

_Source: Rust agent WR-10_


**File:** `agent-install/omni-agent-rs/src/capabilities/quarantine.rs:344-390`, `response_actions.rs:119-136`, `instructions.rs:104-116`
**Issue:**
1. The quarantine hashes the file before the lock and then, under `WRITE_LOCK`, copies, re-hashes and (`verify_in_quarantine`) hashes the stored file again. A multi-gigabyte file on a slow disk holds the lock for minutes. The sweeper's expiry and the isolation revert block on the same lock for that long, and the agent loop awaits the whole instruction, so heartbeats stop (question 4). Lock order is consistent (`isolation::LOCK` then `WRITE_LOCK`, never the reverse) so there is no deadlock, only long waits.
2. `background_arm` returns `accepted` and relies on `ACCEPTED_HEAD_START` (2 s) so the final body is posted after it. The `accepted` post goes out after `compute_instruction_result` returns, with a 30-second client timeout. If that post is slow, the final `isolated`/`restored` body can arrive first and then be overwritten by `accepted`.
3. `report_result` discards the send result (`let _ =`, line 104). A final body lost to a transient network error leaves the card at `accepted` although the host is isolated, and nothing resends it. For a non-idempotent action (`reboot_host`), a platform that re-offers an instruction whose result never arrived would schedule a second reboot.

**Fix:** Cap the file size accepted for quarantine, or hash and copy outside the state lock and hold the lock only for the index update. Run the quarantine/kill arms off the loop (`tokio::spawn` plus the same result route as isolation). Order the two posts with a oneshot channel from `execute_instruction` instead of a sleep, and retry `report_result` a few times with backoff, logging the final failure.

### WR-23: [frontend] Activity list silently ignores Refresh, a decision and the stale-row reload once "Load more" was used

_Source: frontend WR-01_


**File:** `components/AutonomousOpsActivityList.tsx:303` (also 340, 363, 376); callers `components/AutonomousOpsActivity.tsx:136` and `components/AutonomousOpsRowActions.tsx:112`
**Issue:** `loadFirst(true)` returns immediately when `pages.current > 1`, and `loadMore` raises `pages.current` after each page. Four things are all routed through `loadFirst(true)`:
- the page Refresh button, through `refreshSignal`
- a decision, through `decidedCount`
- the 30-second poll and the focus handler
- `onStale`, which RowActions calls after an Undo answers 409

All four become no-ops once the person has pressed "Load more" once.

Failure scenario: the person pages to row 26 or beyond and approves a request in "Needs your decision".
- The Activity list is not reloaded, so the Pending row stays Pending and keeps its "Review in Needs your decision" link to a card that is gone.
- The page Refresh button does nothing for the list.
- A row whose Undo got a 409 keeps showing the Undo button. The `onStale` reload meant to remove it is skipped, so every further click gives the same 409.
- A row changed by another administrator is never updated. Only a filter change reloads.

**Fix:** keep the "don't throw away loaded pages" rule for the timer and focus poll only. For the user-initiated paths (Refresh, a decision, `onStale`) reload the first page and keep the rest, or reset to page one:
```ts
const loadFirst = useCallback((silent: boolean, force = false) => {
    if (silent && (busy.current || (pages.current > 1 && !force))) return;
    ...
    // on a forced silent reload: pages.current = 1 once the first page has landed
}, [request]);
const onStale = useCallback(() => loadFirst(true, true), [loadFirst]);
// refreshSignal effect: loadFirst(true, true)
```

### WR-24: [frontend] A failing background read leaves stale cards with live Approve buttons and says nothing

_Source: frontend WR-02_


**File:** `components/AutonomousOpsDecisions.tsx:80-82, 158-159, 167-179`
**Issue:** `failed` is shown only when `state === null`. Once any page has loaded, every later failure (network loss, 401/403, 500) is swallowed. The cards stay, their countdowns keep ticking from the old `deadlineAt`, and Approve and Deny stay enabled. The header comment says "a failed one keeps the last cards", but nothing tells the person the data is old.

Failure scenario: another administrator denies a request, or a stop is pressed, while the browser is offline or the session is mid-refresh. The first card still shows Approve with no warning. For an isolation or reboot request the person decides on a view that may be hours old. The server's 409 does protect the data, but the screen should not present a stale view as current.

**Fix:** when `failed && state !== null`, render a small non-blocking notice such as "Couldn't refresh approvals. Showing the last result." with a Try again button, and clear it on the next success (`setFailed(false)` already runs there).

### WR-25: [frontend] A decided line keeps its "what happens" sentence, which can contradict the result

_Source: frontend WR-03_


**File:** `components/AutonomousOpsIncidentCard.tsx:130-132, 214-219`
**Issue:** `consequence` is built from `action.consequenceText` with no check of `settled`. The `notice` block is hidden once the line is not waiting (`waiting && action.notice`, line 209), but the consequence sentence is not. A line is rendered from the held card snapshot (Decisions.tsx:127-131, 138-140) when its card has left the server list, which happens after the last waiting line is decided. In that case the old sentence stays next to the new result until the next poll.

Failure scenario: after "Confirm isolation", the line shows "Confirmed by X at 14:03. The computer stays isolated until a person restores it." and directly below it, "Without it, the computer returns to the network automatically at 18:03." On a Denied kill line the "Ends this process right away. Unsaved work in it is lost." sentence stays under "Denied by X. Nothing was sent". A person could read this as the action still going to happen.

**Fix:**
```ts
const consequence = action.consequenceText && !settled
    ? (fillBlockTimes(action.consequenceText, action.revertsAt) ?? action.consequenceText)
    : null;
```
(`describedBy` already tolerates a null `consequence`.)

### WR-26: [frontend] A decision that fails for any reason other than "expired" or "already made" does not re-read the card

_Source: frontend WR-04_


**File:** `components/AutonomousOpsIncidentCard.tsx:165-173`
**Issue:** Only the two special 409 texts call `onDecided`, which triggers `load('decision')`. Every other failure just sets a local error and leaves the line as it was, with the buttons enabled. Server answers that fall here:
- 409 "Automatic actions are stopped, so this cannot be done right now."
- 409 for a `refused` reason. The server may have already moved the row to refused.
- 404 "Action not found."
- 503 and similar.

The error text always ends in "Try again.", even for conditions that cannot be retried.

Failure scenario: someone presses Stop; the shared status poll has not updated yet. The person clicks Approve, gets "Couldn't approve this action: automatic actions are stopped... Try again.", and the Approve button stays enabled. Nothing refreshes the stop state or the card until the next 30-second poll.

**Fix:** after any 409 or 404, call `callbacks.onDecided` or a plain reload and also trigger the status `refresh()`. Drop "Try again." from the 409 and 404 wording (the existing `plain()` helper and the server text already say why), or leave the line to be re-rendered from the fresh read.

### WR-27: [frontend] Approve, Deny and Confirm are disabled or hidden using the browser's clock

_Source: frontend WR-05_


**File:** `components/AutonomousOpsIncidentCard.tsx:57, 119-120, 126, 183, 315`
**Issue:** `isPast(action.expiresAt, now)` and `isPast(card.deadlineAt, now)` compare a server timestamp with `Date.now()`.
- A line the browser thinks is expired is rendered with all controls removed (`showControls` false) and the sentence "This request has expired and counts as denied." (line 126).
- `cardExpired` disables Approve, Deny and Confirm for every line of the card.
- `isPast` treats an unparsable date as expired.
- The server never gives the client a time reference (`incidents` returns no server `now`).

Failure scenario: a managed-less laptop whose clock is a few hours ahead shows a live request as expired and removes Deny, the safe action. The request stays approvable by other administrators for up to 24 hours, and this person cannot deny it. A clock that is behind shows live buttons on requests that have expired, which the server then answers with 409, handled. A card with mixed deadlines also disables the later-deadline lines for up to 30 seconds after the nearest deadline passes.

**Fix:** have `/incidents` return `serverNow` (ISO) and compute a skew once per read (`skew = Date.parse(serverNow) - Date.now()`), then use `Date.now() + skew` as `now`. Never remove Deny on a client-side guess; at most disable Approve and Confirm. Let the server's 409 decide.

### WR-28: [frontend] The settings form discards edits made while saving, and a full-list save can overwrite another administrator's services

_Source: frontend WR-06_


**File:** `components/AutonomousOpsResponseSettings.tsx:193, 218-222, 301-366, 137-138`
**Issue:**
- Every field stays editable while `pending` (the switch, block length, service input, Add and Remove have no `disabled`). On success `setData(saved)` runs, then `void load()` calls `setData(next)` again. The effect at line 193 resets the whole draft each time, so anything typed during the save, or in the second after it, disappears without notice.
- `watchedServices` is sent as the complete list (`changes.watchedServices = draft.services`), compared against data loaded when the panel mounted. `data` is never refreshed. Two administrators editing the services list overwrite each other (last writer wins). The same holds for the two-source switch if it was changed elsewhere in the meantime, since the diff is computed against stale `data`.

**Fix:** disable all inputs while `pending`, and skip the second `load()` after a successful save (the PUT already returns the saved settings). For the lost update, have the server accept `add` and `remove` for services, or compare against a freshly fetched value before sending.

### WR-29: [frontend] Undo reports "Couldn't undo" after the undo was sent, when the answer carries no row

_Source: frontend WR-07_


**File:** `components/AutonomousOpsRowActions.tsx:99, 109-112`
**Issue:** `if (!out?.action?.id) throw new Error('empty answer')` runs after the server returned 200. The server's `present_one` can return `None` (autonomous_ops/views.py:380-381), and `_decide` puts that straight into `"action"`. The catch block then shows "Couldn't undo this action. Check your connection and try again." and does not call `onStale`, because the error is not an `AutonomousOpsApiError`. The undo was already sent to the host. The Undo button stays enabled, the second click gets a 409, and the person has been told the first one failed.

**Fix:** treat a 200 as success. If the row is missing, still show the "Undo sent" toast and call `onStale?.()` to reload the list:
```ts
const out = await undoAutonomousOpsAction(row.id, tenantId);
if (out?.action?.id) onRowChanged(out.action); else onStale?.();
```

### WR-30: [frontend] A held card is a snapshot from the first decision, so lines resolved elsewhere still show Approve and Deny

_Source: frontend WR-08_


**File:** `components/AutonomousOpsDecisions.tsx:127-131, 136-142`
**Issue:** `onDecided` stores the card at the first decision and never replaces it (`prev.some(h => h.card.id === card.id) ? prev : ...`). When the card later leaves the server list, the held copy is shown with only the lines this person decided marked as settled. Any other line of that card that was waiting at the snapshot time is shown as waiting with live buttons, even though the server only drops a card when no line needs a person. Those lines were resolved elsewhere or expired. The state lasts up to 30 seconds (until the next poll clears `held`). A click on such a line returns 409, which is handled, but the card is misleading in the meantime.

**Fix:** refresh the snapshot from the latest server version whenever the card is present in `state.items`, for example by replacing the `held` entry inside `load` with the card found in `next.items`. Alternatively render lines that have no patch and are not in the latest read as settled-unknown.

## Info

### IN-01: [backend core] Question 1 holds today, but the gate does not stop a future caller (`remediate()` and automatic `quarantine_file`)

_Source: backend/autonomous_ops IN-01_


**File:** `backend/autonomous_remediation_service.py:425-471` (`_remediate`); `backend/remediation_playbook_service.py:140`; `backend/playbooks/quarantine_file.yaml`
**Issue:** `select_playbook` now returns `quarantine_file` for any non-IP `nscan` finding (D-05). The playbook has no `gate_class`, so `_remediate` builds a request with `playbook_raise=False` and dispatcher `remediation`. The gate classes it `class_auto` and dispatches it at once, with no two-origin rule and no protected-path escalation. Those two checks exist only in `sweep_security`. The agent still refuses protected paths without `allow_protected`.

Reachability today: `remediate()` has one caller, `ueba_service.py:121`, and it only builds `anomaly` findings, which map to `kill_process` (an approval card). `scan_for_remediable_findings` has no caller, and `remediation_control_endpoints.py` only approves and denies. So question 1 holds: no automatic path reaches `quarantine_file` or `block_ip` through `remediate()`. The protection is the absence of callers, not a rule.
**Fix:** Defence in depth. In `_remediate`, force `playbook_raise=True` for any playbook whose first action is `quarantine_file` or `block_ip`, or in `gate._step_class` escalate those two commands to `needs_approval` unless `req.dispatcher == "security_response"`. Add a test that builds an `nscan` file finding and asserts an approval card.

### IN-02: [backend core] Question 3 holds; the safety of `allow_protected` rests on three call sites

_Source: backend/autonomous_ops IN-02_


**File:** `backend/autonomous_ops/sweep_security.py:158-162`; `backend/autonomous_ops/followups.py:145-146`; `backend/autonomous_ops/gate.py:187-201`
**Issue:** No code in `gate.py` or `dispatch_check.py` mentions `allow_protected`.
- `sweep_security._act_request` sets it only together with `raises=True`, which gives `playbook_raised` and a card. This holds, including the host-cap and undo-hold replacements.
- `followups._retry` sets it when the original, person-approved quarantine row had it. That request has no `playbook_raise`, so the gate decides `class_auto` and the retry is sent automatically, counted as an automatic row (rate limit, breaker). The UI wording ("Ends the process, then moves the file to quarantine") covers it, and a person approved both the quarantine card and the kill card. It still means a protected system file is moved by an `autoDispatched` row, which D-28 words as "never automatically".
- No other producer sets the key. The grep over `backend/` found only these two files.
**Fix:** The one-line gate rule suggested in the security observations needs an exception for the retry: escalate to `needs_approval` when any step has `params.allow_protected` and `req.reason.inputs.parentActionId` is not set. That keeps the retry working and makes a future producer safe by default.

### IN-03: [backend core] Question 5 holds; tenant isolation of the Phase 83 queries

_Source: backend/autonomous_ops IN-03_


**File:** all 29 files
**Issue:** I checked every `find`, `find_one`, `update_one`, `count_documents` and aggregate.
- All carry `tenantId` (or an `id` that has been checked against the tenant just before).
- Global feed rows are read only with `{"tenantId": {"$exists": False}}` (`signals.py:351`). Tenant IOC rows are ignored. A tenant `add_ioc` row uses `sha256` and `ip_address`, not `ioc_type`, `ioc_value` or `source_ip`, so it cannot match the readers. A caller with no tenant can create a global row through `add_ioc`, but it cannot carry feed names.
- `threat_feed_sync._upsert_iocs` filters on type and value only, so a tenant-owned row with the same value can receive a feed's names. That fails toward fewer origins.
- Two helpers read `agents` by id with no tenant argument: `gate._agent_of` (`gate.py:206`) and `agent_support.agent_of` (`agent_support.py:111`). Every caller verifies `tenantId` first (`gate.py:226`, `approvals.py:97`, and `approvals.py:108` after the loop). `delivery._row` reads by id only on purpose and compares the tenant.

**Fix:** None needed. Hardening: give `agent_support.agent_of` a `tenant_id` parameter and filter on it, so a later caller cannot forget the check.

### IN-04: [backend core] `delivery.py` docstring claims the unstamped-command refusal covers response tasks; it does not

_Source: backend/autonomous_ops IN-04_


**File:** `backend/autonomous_ops/delivery.py:3-9` versus `delivery.py:162-167`
**Issue:** The docstring says both hold-back functions look at an unstamped item's command and refuse the gate-only ones. Only `hold_back_autonomous` (`delivery.py:144-157`) does. `hold_back_response_tasks` goes straight to `_screen`, which handles stamped items only. This matches security observation 4 (the legacy Python agent still reads `response_tasks`), but the docstring and the module claim "whatever wrote it (T-83-25, RESP-11)" say otherwise. Automatic writers into that queue such as `response_orchestrator.py` "auto-policy" `quarantine_file` (lines 29 and 337) are not stopped by this module.
**Fix:** Correct the docstring, or add the unstamped filter to `hold_back_response_tasks` if the fence is meant to cover it. This is a decision for the owner of D-25.

### IN-05: [backend core] `protected_paths.kind_of` treats "Darwin" as Windows

_Source: backend/autonomous_ops IN-05_


**File:** `backend/autonomous_ops/protected_paths.py:63`
**Issue:** `"win" in text` is true for `darwin`. A macOS platform string is then checked against the Windows list only, so `/usr/bin/x` counts as unprotected. macOS agents report no response tokens, so the sweep is dormant for them and nothing is sent. The code would be wrong if a macOS agent ever reported the tokens.
**Fix:** Test `text.startswith("win")` or `"windows" in text`, and add `darwin` and `mac` to the unknown-platform branch (both lists).

### IN-06: [backend core] Small correctness and clarity notes

_Source: backend/autonomous_ops IN-06_


**File:** several
**Issue:**
- `response_views.py:75` and `:96` use a local variable named `raw`, which shadows the imported `raw` from `.scope` (line 24). It is harmless today, but a later edit that calls `raw(db)` in those functions would fail.
- `signals.py:435-439` cuts candidates to 500 after sorting by agent id, so a tenant with more than 500 candidates always serves the same hosts first and starves later ones.
- `sweep_suggestions.py:98-121` and `:245-257`: when more than 5000 agent vulnerabilities exist, agents whose rows fall past the cut-off are absent from `groups`. `_close_gone` then ends their open suggestion with the text "Nothing is reported on this computer any more", which is not true.
- `sweep_security.py:197-204` counts a recorded *refused* suggest decision as `suggested` in the pass counts.
- `response_settings.save` (`:184-192`) restores the old values if a control row fails, but control rows already written for earlier keys in the same save stay in the ledger with no matching restore.
**Fix:** Rename the local to `suggestion`. Rotate or randomise the candidate cut-off, or process all candidates in chunks. Skip `_close_gone` when the read hit the limit. Count refusals separately. Record a compensating control row on restore.

### IN-07: [backend core] Critical services are excluded only when the watched list is saved

_Source: backend/autonomous_ops IN-07_


**File:** `backend/autonomous_ops/sweep_restart.py:71-77`; `backend/autonomous_ops/response_settings.py:96-108`
**Issue:** `_watched` checks the name pattern but not `criticalServices`. That list is enforced only in `validate_service_name` when the setting is saved. A stored list written some other way (a direct DB change, or a future bulk route that skips `validate_changes`) could restart `sshd` or `mpssvc`. I did not verify whether the agent applies the same list, and the backend should not rely on it.
**Fix:** In `_watched`, also drop names whose case-folded form is in `agent_support.CONTRACT["criticalServices"]`.

---

### IN-08: [backend routes] The swarm containment fence is a one-value denylist on `type`, while the agent acts on `instruction`

_Source: backend routes and wiring WR-02_


**File:** `backend/swarm_endpoints.py:34, 37-40, 126-153`
**Issue:**
- `CONTAINMENT_MISSION_TYPES = {"isolate_host"}` strips only steps whose `type` is `isolate_host`.
- The plan comes from LLM output (`ai_instructions`). The prompt's list of types is not enforced, and the goal text is user-written.
- The agent poll relays `instruction` first (`agent_tasks_endpoints.py:60`), and the Rust agent dispatches on `action`, then `instruction`, then `type` (`instructions.rs:22-27`).
- `agent_capabilities.instruction_capability` also reads `instruction` before `type`.
- A step such as `{"type": "general_task", "instruction": "isolate_host"}` or `{"type": "block_ip", ...}` passes the fence and is written to `agent_instructions` without the gate (no stop, limits, protected targets or ledger row).
- Caveat: I could not confirm that these inserts carry a `tenantId`. The poll query filters on it (`agent_tasks_endpoints.py:40-44`), so delivery depends on the DB wrapper adding it. If it does not, the rows are never delivered and this is latent.

**Failure scenario:** A `manage:agents` user starts a mission with a goal that steers the model to emit `instruction: "isolate_host"`. Each online agent in the tenant receives an isolation that skipped Autonomous Ops, which is what D-18/RESP-11 forbids.

**Fix:** Use an allowlist on both fields, and make the existing `type` the only thing the agent can see:
```python
ALLOWED_MISSION_TYPES = {"vulnerability_scan", "os_patch_install", "threat_hunt", "log_collection", "general_task"}

def _without_containment(instructions):
    kept = [i for i in instructions
            if isinstance(i, dict)
            and str(i.get("type", "")).strip().lower() in ALLOWED_MISSION_TYPES
            and isinstance(i.get("instruction"), str)
            and agent_capabilities.instruction_capability({"instruction": i["instruction"]}) is None]
    return kept, len(instructions) - len(kept)
```
At the same time, stop writing the model's free text into `instruction`. Store it under `description`, and let `instruction` be the allowlisted `type`.

**Orchestrator check (2026-11-02), moved from Warning to Info:** the second layer catches it. `delivery._gate_only_unstamped` (delivery.py:54-56) checks `type`, `instruction` and `action` for the gate-only commands, and `hold_back_autonomous` marks an unstamped one `refused` at the agent poll, so `{"type": "general_task", "instruction": "isolate_host"}` never reaches an agent. The swarm-level filter is still narrower than it claims; commands outside `GATE_ONLY_COMMANDS` (block_ip, kill_process) are not covered by either layer.

### IN-09: [backend routes] The "accepted never overwrites a final status" guard uses upper-case names, but the capability hold-back writes lower-case `refused`

_Source: backend routes and wiring IN-01_


**File:** `backend/agent_tasks_endpoints.py:104`, `backend/agent_capabilities.py:34`
**Issue:**
- The `$nin` list is `["SUCCESS", "FAILURE", "REFUSED"]`. `hold_back` writes `"refused"`, and `verify.failure_outcome` lower-cases for that reason.
- This does not matter today: a held-back task is never delivered, so no `accepted` post arrives. An agent status other than `success` or `error` (for example `failed`) maps to `FAILED`, which is also not in the list.
- Only the Rust agent's three values are covered.

**Fix:** Add `"FAILED"` and `"refused"` to the list, or compare case-insensitively.

### IN-10: [backend routes] `validate_intervals` has no caller (uncommitted hunk)

_Source: backend routes and wiring IN-02_


**File:** `backend/agent_capabilities.py:131-146`
**Issue:**
- This sits in the user's uncommitted `agent_capabilities.py` hunk.
- Nothing in the backend writes `tenants.agentCollectionIntervals` or `agents.collectionIntervals`, so `validate_intervals` is dead.
- `capability_endpoints.py` stores a different field, `capabilityConfig.collectionIntervals`.
- The heartbeat sends `collectionIntervals` (`agent_heartbeat_endpoints.py:534`, also uncommitted) that can only be the catalogue defaults.

**Fix:** Wire the Super Admin setter, or drop the dead function. Reconcile the two field names.

### IN-11: [backend routes] Smaller robustness points in the new response routes and the swarm plan

_Source: backend routes and wiring IN-03_


**Files:** `backend/autonomous_ops_response_platform_endpoints.py:100-112`, `backend/autonomous_ops_response_endpoints.py:49`, `backend/swarm_endpoints.py:132, 153`, `backend/swarm_service.py:8`
**Issue:**
- `onlyTenants: []` is accepted and returns `{"changed": [], "failures": []}` with 200. An empty retry silently does nothing. Add `min_length=1` or treat an empty list as 422.
- `ResponseSettingsBody.watchedServices` has no list-length limit at the Pydantic layer. The 50-name cap applies only after the whole body is parsed.
- In `run_swarm_lifecycle`, `i['type']` and `instr['instruction']` raise `KeyError` for a model item without those keys. `_without_containment` keeps non-dict items, which then fail on `.get`. The background task dies and the mission stays "Running".
- `swarm_service.py` still imports `get_current_user` and does not use it.

**Fix:** Apply the allowlist from WR-02, which also removes the malformed items. Add `max_length=50` to the list type and delete the unused import.

### IN-12: [backend routes] `playbook_engine_actions` fence reads `executed_by` as a free string

_Source: backend routes and wiring IN-04_


**File:** `backend/playbook_engine_actions.py:7, 96-98`
**Issue:**
- A run counts as automatic only when `executed_by` is one of three literals. Any other automatic caller that sets a different `executed_by` takes the unchanged manual path.
- The current callers are fine: `correlation_engine_response` uses `xdr-auto`, and the user routes pass a username.
- A future scheduler that passes `"system"` would bypass the fence without any test failing.

**Fix:** Invert the check so that only an `executed_by` equal to the authenticated user's name or `manual` is a human run. Anything else is treated as automatic.

---

_Reviewed: 2026-11-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

### IN-13: [agent] Isolation revert uses the wall clock only; a backward step lengthens the isolation (question 3)

_Source: Rust agent IN-01_


**File:** `agent-install/omni-agent-rs/src/capabilities/isolation.rs:254,352`, `response_actions.rs:204-209`
**Issue:** `revert_at = now + 14_400` is an epoch value compared with `now_epoch()` each pass. A forward clock step ends the isolation early, which is the safe direction. A backward step (a VM resume with a stale clock, an RTC reset to 1970 at boot before time sync) keeps an unconfirmed isolation up for as long as the step, with no bound, and `now_epoch()` returns 0 if the clock is before the epoch. AR-83-02 accepts a host admin moving the clock; this is the non-malicious case. A second isolate while isolated is WR-04.
**Fix:** Persist `started_at` as epoch plus a monotonic anchor (boot time and uptime), and revert when either the epoch deadline or `4 h` of elapsed uptime has passed.

### IN-14: [agent] A cross-volume quarantine can delete a file that changed after the copy was verified

_Source: Rust agent IN-02_


**File:** `agent-install/omni-agent-rs/src/capabilities/quarantine.rs:233-257`
**Issue:** `copy_across` hashes the copy, then removes `src`. If the source is rewritten between the copy and `remove_original` (a running dropper rewriting itself), the new content is deleted although only the old bytes were saved. Rename (same volume) has the same shape: the hash was taken before the lock and the file is not re-hashed before the rename. The window is small and the saved copy matches the flagged hash.
**Fix:** Before removing the original, compare its size and modified time with the values taken before the copy; if they changed, discard the copy and return `Locked`.

### IN-15: [agent] Process listing failure reports a kill as done

_Source: Rust agent IN-03_


**File:** `agent-install/omni-agent-rs/src/capabilities/process_kill.rs:181-183`
**Issue:** `spawn_blocking(running_now).await.unwrap_or_default()` returns an empty list if the listing task panics. `plan_kill` then sees nothing and `kill_body` answers `process_gone` with `verify.ok = true`, and the later read (also empty) makes a real kill look complete. Unlikely, but the answer asserts something that was never observed.
**Fix:** Return a `refused_body("The process list could not be read.")` when the join fails, and treat an empty later list after a failed read as unverified.

### IN-16: [agent] gzip fallback sends every heartbeat twice when the platform rejects the payload for another reason (uncommitted hunk)

_Source: Rust agent IN-04_


**File:** `agent-install/omni-agent-rs/src/heartbeat.rs:599-625`
**Issue:** A gzip post answered 400/415/422 is resent plain. If the platform rejects the content itself (a 422 on a field), both posts fail every beat, `GZIP_REFUSED` is never set, and traffic doubles until fixed. When the plain post succeeds, compression stays off until the agent restarts even if the platform is upgraded. The retry also fires for each buffered heartbeat in `flush_buffer`.
**Fix:** Retry plain only on 415 (or on 400 with a body that names the encoding), and log the status of the plain attempt.

### IN-17: [agent] Collection intervals: skipped collectors send nothing and last-run state is per process (uncommitted hunks)

_Source: Rust agent IN-05_


**File:** `agent-install/omni-agent-rs/src/capabilities/mod.rs:163-188`, `heartbeat.rs:436`
**Issue:** `collect_due_at` keeps the `last_run` lock while it runs every due collector, and a collector skipped on a beat is omitted from `meta`; the platform keeps its last data. After an agent restart all collectors run once on the first beat. With a short heartbeat interval a collector can run up to one interval later than its period (for example 25 s beats and a 60 s period run at 0 and 75 s). These are consistent with the stated design; the point is only that detection latency for `fim` (600 s), `persistence_detection` (3600 s) and `runtime_security` (180 s) is now the interval, not the beat, so any backend rule that treats a missing section as "clean" would be wrong.
**Fix:** Confirm on the backend that an absent capability section is treated as "no new data".

### IN-18: [agent] Other notes

_Source: Rust agent IN-06_


**File:** several
**Issue:**
- `isolation::carve_out` opens the platform addresses resolved once at apply time (`isolation.rs:83-108`). A platform behind rotating or anycast addresses, or an agent that reaches it through the system proxy (`reqwest` is built with `system-proxy`, `Cargo.toml`), can be cut off while `tcp_self_test` succeeds directly. The 4-hour revert bounds it.
- `response_state_report` is built at send time and stored in the offline buffer (`heartbeat.rs:541`); a flushed old beat can later tell the platform an isolation is still active.
- `valid_id` allows Windows device names (`con`, `nul`, `aux`) that become `con.q`/`con.json` in the quarantine folder (`quarantine_paths.rs:112-123`). Task ids are normally UUIDs, so this needs a hostile backend; reject reserved names for completeness.
- `service_watch::failure_id` uses the first time this process saw the failure, so an agent restart gives the same failure a new id and a second card.
**Fix:** As described in each bullet; none is urgent.

---

### IN-19: [frontend] Swarm antibody form: Enter bypasses the in-flight guard, and the error text can be wrong or crash the page

_Source: frontend IN-01_


**File:** `components/SwarmDashboard.tsx:86-105, 243`
**Issue:**
- `onKeyDown` on Enter calls `handlePropagateAntibody()` without checking `propagating`, so holding Enter sends several requests (the button is disabled, the key is not).
- Line 95 puts `result.data?.detail` into state as the message. If the server answers with a validation `detail` array or object, React throws "Objects are not valid as a React child" at line 217 and the dashboard goes to the error boundary. Use `typeof detail === 'string' ? detail : 'Propagation failed.'`. The same applies to `result.data?.message` at line 100.
- `apiService.propagateAntibody` returns a bare `{status: 403}` for every 403 (apiService.ts:1667). `require_permission("remediate:agents")` also answers 403 when the permission is missing, so the person is told "Tenant context required. Please re-authenticate." and re-authenticating does not help.
- The indicator is cleared (line 104) on a "not sent" answer, so the person loses what they typed although nothing happened.

**Fix:** guard with `if (propagating) return`, check the types of `detail` and `message`, only clear the field for `kind: 'ok'`, and pass the 403 body through so the real reason shows.

### IN-20: [frontend] The decision result text is rebuilt in the browser, and the server's refreshed row is thrown away

_Source: frontend IN-02_


**File:** `components/AutonomousOpsIncidentCard.tsx:149-156`; `services/autonomousOpsIncidentsApi.ts:94-104`
**Issue:** `postDecision` returns `{status, action}` and no caller reads it. The line instead shows hard-coded copies of the server templates ("Approved. Sent to {host}.", "Denied by {name}.", "Confirmed by {name} at {at}..."), the name from `currentUser.name` and a time from `new Date().toISOString()` (the browser clock). Two sources of truth can drift: the server uses the approver's `display`, the text stays "Sent to" for an action that may only be queued, and the confirmed time may differ from the one the server stored.
**Fix:** after a 200, build the patch from `out.action` (`resultText`, `bucket`, `blockedUntil`) and use the server's `confirmedAt`.

### IN-21: [frontend] `actionCount` is typed but never read, so a card with more than 50 lines hides the rest without saying so

_Source: frontend IN-03_


**File:** `services/autonomousOpsIncidentsApi.ts:66`; `components/AutonomousOpsIncidentCard.tsx:312-313`
**Issue:** the server caps a card at 50 lines (`LINE_CAP`, incident_views.py:32) and sends the true count in `actionCount`. The card computes "Show N more actions" from `lines.length`, so lines 51 and beyond never appear and nothing says they exist.
**Fix:** use `Math.max(lines.length, card.actionCount)` for the hidden count, and add "N more are not shown" text when `actionCount > lines.length`.

### IN-22: [frontend] Bulk apply does not check the shape of its answer, and the distribution summary leaves out unreadable organizations

_Source: frontend IN-04_


**File:** `components/AutonomousOpsResponseSettingsPlatform.tsx:109-127, 21-28, 150`
**Issue:**
- `result.changed.length` and `result.failures.length` are read without checking that the arrays exist. A 200 with a different body throws a TypeError inside the `try`, which is reported as "Couldn't save response settings. Check your connection and try again." even though the server may have written every organization. No reload of the distribution follows.
- The `unreadable` count from the distribution is never shown, and the dialog's "N organizations will be changed" uses `dist.organizations`, which includes them.
**Fix:** validate with an `isApplyResult` guard like the one used for `isDistribution`; on a malformed 200 reload the distribution and say the outcome is unknown. Show the unreadable count in the summary.

### IN-23: [frontend] Smaller race and robustness points

_Source: frontend IN-05_


**File:** `components/AutonomousOpsDecisions.tsx:85-106`; `components/AutonomousOpsIncidentCard.tsx:313, 339`
**Issue:**
- `loadMore` has no sequence guard. A slow "Show more" reply that lands after a newer poll overwrites `total` with an older value and appends rows from the older ordering. The id de-duplication prevents duplicates, not a wrong total.
- Lines beyond the first five unmount when the person presses "Show fewer actions" while a decision is in flight. The remounted line has a fresh `sent` ref, so a second click can send a second request. The server answers 409 "already made", which is handled, so this is only noise.
- `StateChip` does `CHIPS[chip]` with no fallback (ActivityList.tsx:58). A new server bucket not in `CHIPS` throws during render and takes down the whole Autonomous Ops view through its error boundary.
**Fix:** check `mine === seq.current`-style ordering in `loadMore`; keep the `sent` ref in the card or key the lines by id outside the collapse; give `StateChip` a neutral fallback entry.

---

## Finding map

| Merged | Part finding |
|--------|--------------|
| CR-01 | Rust agent CR-01 |
| CR-02 | Rust agent CR-02 |
| WR-01 | backend/autonomous_ops WR-01 |
| WR-02 | backend/autonomous_ops WR-02 |
| WR-03 | backend/autonomous_ops WR-03 |
| WR-04 | backend/autonomous_ops WR-04 |
| WR-05 | backend/autonomous_ops WR-05 |
| WR-06 | backend/autonomous_ops WR-06 |
| WR-07 | backend/autonomous_ops WR-07 |
| WR-08 | backend routes and wiring WR-01 |
| WR-09 | backend routes and wiring WR-03 |
| WR-10 | backend routes and wiring WR-04 |
| WR-11 | backend routes and wiring WR-05 |
| WR-12 | backend routes and wiring WR-06 |
| WR-13 | Rust agent WR-01 |
| WR-14 | Rust agent WR-02 |
| WR-15 | Rust agent WR-03 |
| WR-16 | Rust agent WR-04 |
| WR-17 | Rust agent WR-05 |
| WR-18 | Rust agent WR-06 |
| WR-19 | Rust agent WR-07 |
| WR-20 | Rust agent WR-08 |
| WR-21 | Rust agent WR-09 |
| WR-22 | Rust agent WR-10 |
| WR-23 | frontend WR-01 |
| WR-24 | frontend WR-02 |
| WR-25 | frontend WR-03 |
| WR-26 | frontend WR-04 |
| WR-27 | frontend WR-05 |
| WR-28 | frontend WR-06 |
| WR-29 | frontend WR-07 |
| WR-30 | frontend WR-08 |
| IN-01 | backend/autonomous_ops IN-01 |
| IN-02 | backend/autonomous_ops IN-02 |
| IN-03 | backend/autonomous_ops IN-03 |
| IN-04 | backend/autonomous_ops IN-04 |
| IN-05 | backend/autonomous_ops IN-05 |
| IN-06 | backend/autonomous_ops IN-06 |
| IN-07 | backend/autonomous_ops IN-07 |
| IN-08 | backend routes and wiring WR-02 |
| IN-09 | backend routes and wiring IN-01 |
| IN-10 | backend routes and wiring IN-02 |
| IN-11 | backend routes and wiring IN-03 |
| IN-12 | backend routes and wiring IN-04 |
| IN-13 | Rust agent IN-01 |
| IN-14 | Rust agent IN-02 |
| IN-15 | Rust agent IN-03 |
| IN-16 | Rust agent IN-04 |
| IN-17 | Rust agent IN-05 |
| IN-18 | Rust agent IN-06 |
| IN-19 | frontend IN-01 |
| IN-20 | frontend IN-02 |
| IN-21 | frontend IN-03 |
| IN-22 | frontend IN-04 |
| IN-23 | frontend IN-05 |

## Reviewer notes

### backend/autonomous_ops: Answers to the review questions

1. **`remediate()` reaching automatic `quarantine_file`:** holds today (see IN-01). The only caller is UEBA anomalies, which map to `kill_process` and an approval card. The protection is the absence of callers; the gate has no rule of its own.
2. **A-83-ONE-PATH:** does not hold. `signals._Acc.origin` and `has_hash` keep the alphabetically first path (WR-02).
3. **Gate and `allow_protected`:** the gate does not refuse it. The two producers behave as described, and the `followups._retry` path sends it automatically after two person approvals (IN-02).
4. **Over-budget restart card:** stays approvable after recovery, and `_revalidate` re-checks host support only (WR-03).
5. **Tenant isolation:** holds (IN-03).

### backend/autonomous_ops: Not read or only partly checked

- Everything under `backend/autonomous_ops/` that is not in the 29-file list: `__init__.py` (I read the constants), `settings.py`, `scope.py`, `notify.py`, `stop.py`, `selfheal.py`, `health_messages.py`. I relied on their behaviour as called.
- I read only part of the code the findings depended on. For `autonomous_remediation_service.py` I read `remediate`, `_remediate` and the grep results, not `_dispatch_and_verify`. For `agent_tasks_endpoints.py` I read `report_instruction_result` only.
- The Rust agent, the routes and the frontend belong to the other three reviewers. Security observation 1 (agent path canonicalisation) and 3 (legacy kill path) are outside these files.
- No test, build or service was run, and the live mongod was not touched.

---

_Reviewed: 2026-11-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

### backend routes and wiring: Not read

- `backend/autonomous_ops/*` was read only where a route called into it: `views.resolve_tenant`, `response_settings`, `isolation.confirm` and `confirmed_ids`, `verify.bounded_result`, `settle` and `failure_outcome`, the `signals` index and feed functions, `incidents.ensure_indexes` and `attach`, `agent_support` loading. The rest belongs to the backend-core reviewer.
- `autonomous_ops_endpoints.py` (449 lines): only the Phase 83 hunks, the permission dependencies and `_decide` were read. The never-touch, stop and level routes were not.
- The large pre-phase bodies of `agent_heartbeat_endpoints.py`, `agent_tasks_endpoints.py`, `soar_engine.py`, `swarm_endpoints.py` and `threat_feed_sync.py` were read only around the Phase 83 diffs and what they call. The feed fetchers were not read except the changed header lines.
- `playbook_engine_actions.py` lines 330-420 (`rollback_ransomware` and the tail) were not read.
- `router_registry.py` was read only at the two new lines and `_load`.
- Other `agent_instructions` writers outside my list (`correlation_engine_threat.py:264, 315` and the `KILL_CHAIN_NEXT_STAGE` instructions, `agentic_service.py`, `chaos_engineering_service.py` and others) were not checked for containment. Those two correlation writers set no `tenantId`, so the poll probably never delivers them, but I did not confirm it.
- `shared/agent-response-contract.json` was checked against the backend consumers. It was spot-checked against the Rust agent only for outcome and check names, token names and `status` values, not exhaustively. The Rust agent is another reviewer's.
- I did not verify whether migration 028 has already been applied on the live database. I did not touch mongod on 27017.

### Rust agent: Answers to the review questions

1. **Textual protected-path compare:** confirmed, see WR-01 (`//etc/passwd`, `/./etc/passwd`, symlinked parent, `System32.`, 8.3 names, UNC, `::$DATA`). Fix is to canonicalise the parent directory and compare the canonical form.
2. **Legacy kill:** confirmed and wider than the observation, see WR-02 (PID path skips the critical list, name path kills all matches, missing `expected_exe` degrades silently) and WR-03 (the new path also kills unlisted instances when nothing was quarantined).
3. **Isolation revert / clock / second isolate:** unreadable state leads to `force_revert` (kept, but it also drops a confirmed isolation on a transient error and leaves a corrupt file permanent, WR-06); a missing state file leaves rules with no record and `restore_host` answers `not_found` (WR-05); clock steps are IN-01; a second isolate is WR-04.
4. **Lock ordering / blocking:** order is consistent (`isolation::LOCK` before `WRITE_LOCK`, no re-entrant call from inside a `Store::update` closure that I found), so no deadlock. The problems are unbounded waits while holding those locks and inline blocking on the agent loop (CR-01, WR-10).

### Rust agent: Not read

- `*_tests.rs` files and `agent-install/omni-agent-rs/tests/` (reference only, as instructed), except grep checks in `net_safety_tests.rs`.
- `agent-install/omni-agent-rs/src/log_file.rs` and `main.rs` log-rotation hunk (the user's uncommitted log rotation; not in the file list), so the `.expect("log file")` start-up path is unreviewed.
- `firewall.rs` lines 330-495 (inline unit tests only).
- `instructions.rs` lines 260-500 and 600-689 (pre-existing arms and the patch job; only the Phase 83 hunks and the dispatch were read).
- `heartbeat.rs` outside `build_payload` and the gzip hunk; `config.rs` beyond the diff.
- `shared/agent-response-contract.json` was not opened; contract-equality is asserted by tests I did not run.
- The sysinfo crate was spot-checked (`exe` strips ` (deleted)`; `start_time` is set when a process is first read) in the local cargo registry; nothing else outside the listed files.

---

_Reviewed: 2026-11-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

### frontend: Not read

- `components/AutonomousOpsHealthBanners.tsx`, `AutonomousOpsHealthCards.tsx`, `AutonomousOpsHealthChips.tsx` (read only the `HealthNotice` and `safeHref` parts), `AutonomousOpsLog.tsx`, `AutonomousOpsPlatformHealth.tsx`, `AutonomousOpsRetentionConfirmDialog.tsx`, `AutonomousOpsRetentionReview.tsx`, `AutonomousOpsStatusCard.tsx`, `AutonomousOpsStopBanner.tsx`, `AutonomousOpsStopDialog.tsx`: not in the file list.
- `services/autonomousOpsApi.ts` lines 130-260 (health and retention types): types only, outside Phase 83.
- `contexts/AutonomousOpsStatusContext.tsx`: read only the exports and the scope resolver.
- `components/Modal.tsx`: checked only that the `closeOnEsc`, `closeOnBackdrop` and `showClose` props exist.
- `services/apiService.ts`: read `authFetch` up to the first 401 retry and `propagateAntibody`.
- Backend: read only `incident_views.py` (lines 150-309), the approve, deny and undo handlers in `autonomous_ops_endpoints.py`, the incidents and confirm-isolation handlers in `autonomous_ops_response_endpoints.py`, and `swarm_service.py`, to confirm what the client depends on. The `approvals` and `isolation` services were not read.
- The rest of `App.tsx` and `SwarmDashboard.tsx` outside the Phase 83 diff, and App.tsx's two uncommitted password hunks.
- Nothing was run (no vitest, tsc or browser).

---

_Reviewed: 2026-11-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
