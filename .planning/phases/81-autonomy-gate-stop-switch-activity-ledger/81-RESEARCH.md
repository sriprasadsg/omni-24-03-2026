# Phase 81: Autonomy Gate, Stop Switch & Activity Ledger - Research

**Researched:** 2026-10-25
**Domain:** Policy-gated autonomous operations core (FastAPI + MongoDB multi-tenant platform; Python backend, React/Vitest frontend, Rust agent only for one folded test todo)
**Confidence:** HIGH for integration points and test-impact (every file below was opened this session; live Mongo read-only queries and two live test runs were done). MEDIUM for UI scope (open question 2). Design recommendations are marked "Recommendation"; facts carry provenance tags.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Locked by milestone requirements (not re-decided here)**
- Eligibility = a Super Admin has ticked the Autonomous Ops screen switch for the tenant (GATE-02); a level that cannot be read is treated as Suggest.
- Action classes per the locked split: block IP, quarantine file, restart service are auto; isolate host, kill process, patch reboot need approval; playbook YAML may raise a class, never lower it (GATE-04). `backend/backend_safety.py`'s opposite classification and `AUTO_APPROVE_CONFIDENCE_THRESHOLD = 0.90` must not apply to autonomous paths (GATE-05).
- The legacy LLM path (`AutonomousRemediationService.run_cycle` -> `generate_plan` -> `execute_plan`, which never checks `requires_approval`) is removed and the scheduled `autonomous_remediation_loop` no longer calls it (GATE-05). Verified 2026-10-25: nothing has ever been dispatched by it on the live server.
- Changing a level, approving/undoing and the platform stop are separate permissions; a Super Admin sets each tenant's highest allowed level (GATE-13).

**Turning it on**
- **D-01:** Migration writes an explicit level for every existing tenant: **Undoable-auto**, the same default as new tenants. The screen tick plus shadow mode are the opt-in. (Satisfies GATE-01's "explicit stored level".)
- **D-02:** Shadow mode has two layers. The existing server setting `AUTONOMOUS_REMEDIATION_DRY_RUN` (default true) stays as a **deployment-wide master** that forces shadow for every tenant. Below it, **every tenant (new and existing) also has its own shadow flag, on by default**, so when the operator turns the server setting off, each tenant still records-only until it is lifted for that tenant. In shadow the gate records "would have done" entries and dispatches nothing.
- **D-03:** Only a **Super Admin** may lift a tenant's shadow flag (going live is a platform decision, like ticking the screen).
- **D-04:** The **Platform tenant is never eligible** in v4.3: the gate always treats it as Off regardless of ticks or level, and the UI does not offer to raise it. The platform server keeps itself healthy through the Phase 82 watchdog. (The local agent on this VM is enrolled to the Platform tenant.)

**Who can do what**
- **D-05:** Three tenant permissions plus one platform-only permission. Exact strings are the planner's call, but follow existing vocabulary: a `view:` permission for the screen, a `manage:` permission for changing the level / never-touch list / clearing a stop, and an approve-tier permission for approve/deny/undo and pressing the stop (`control:` has precedent - `control:remote_access` is already admin-tier). The platform-wide stop uses a platform-only permission added to `rbac_defaults.PLATFORM_ONLY_PERMISSIONS`, served from a platform-only route modelled on HA/DR (`backend/migrations/023_hadr_platform_only.py`). The Phase 77 closure (`manage:X => view:X`, `request:X`) applies; `manage` must **not** imply the approve-tier permission or vice versa unless the role table grants both. - **Reversibility:** costly - once tenant custom roles contain these strings (D-09), renaming or removing them means migrating role documents.
- **D-06:** Built-in defaults:
  - change level / manage: **Tenant Admin only** (plus Super Admin for any tenant)
  - approve / deny / undo / press stop: **Tenant Admin, Security Analyst, Incident Responder** (plus Super Admin)
  - view the Autonomous Ops screen: the approvers **plus Auditor and Analyst**; not Viewer, not the ITAM roles
- **D-07:** The approve-tier permission **joins `rbac_defaults.ADMIN_TIER_PERMISSIONS`**, so every holder must use MFA (Phase 77 D-14 mechanism). - **Reversibility:** costly - Security Analyst and Incident Responder users are prompted to enrol MFA at their next sign-in; reverting later does not un-enrol anyone.
- **D-08:** **Platform Support** can **read** every tenant's Autonomous Ops activity (cross-tenant, read-only, via the existing platform-staff safe-method path in `backend/catalogue_guards.py`) but can never approve, undo, stop, resume or change a level. Only Super Admin acts across tenants.
- **D-09:** Tenant admins **may put the new permissions into custom roles**, under the Phase 77 rules (grant only what you hold; the approve-tier permission drags MFA along via D-07).
- **D-10:** **API keys** may read activity and **press** a stop, but can **never approve, deny, undo or clear a stop**; those require an interactive, MFA-verified session.

**Stop switch behaviour**
- **D-11:** **Press** a tenant stop: anyone holding the approve-tier permission (Tenant Admin, Security Analyst, Incident Responder) and Super Admin for any tenant. **Clear** a tenant stop: only holders of the manage permission (Tenant Admin for their own tenant). The **platform-wide stop**, and any tenant stop a Super Admin pressed, can be cleared **only by a Super Admin**.
- **D-12:** While a stop is on: **undo still works** (it puts things back; a human click counts as its approval), **approving does not** (pending approvals wait until resume), and the gate makes no new decisions. Already-queued autonomous instructions are held back at agent delivery (GATE-06).
- **D-13:** The approval **expiry clock keeps running** during a stop; an approval that expires during a stop is recorded as denied/expired, so nothing stale fires on resume.
- **D-14:** A stop **never clears itself**. Clearing requires a typed reason; pressing may take an optional reason (braking must be fast). Who pressed/cleared and why is recorded in the ledger and the audit chain.
- **D-15:** An active stop shows a **banner across the app** for everyone who can view Autonomous Ops, an Activity entry (who, when, why), and an **on-call alert** (Phase 82 channel; until then the existing in-app notification path).

**Safety limits**
- **D-16:** Pending approvals **expire after 24 hours** and then count as denied (`expired`).
- **D-17:** **One automatic decision may touch exactly one host** (the host its finding came from). Anything wider becomes an approval card.
- **D-18:** **Circuit breaker:** **3 consecutive** automatic actions for a tenant that are undone or fail **within 24 hours** drop that tenant to Suggest (the previous level is recorded) and tell on-call. **A person with the manage permission restores it**; it never re-arms itself.
- **D-19:** **Never-touch list:** built-in entries that nobody can remove - the platform server, its own IP addresses and the management network. **Super Admin** can add platform-wide entries; a **tenant admin** (manage permission) can add entries for their own tenant (e.g. domain controllers, gateways).
- **D-20:** **Per-tenant rate limit:** after **20 automatic actions in an hour**, that tenant's new decisions become approval cards until the window rolls over, and on-call is told.

### Claude's Discretion
- Exact permission strings and route shapes (within D-05), ledger collection and field names, the decision `trace` format, state-machine names (research ARCHITECTURE Pattern 3 is a good starting point).
- Rolling 60-minute window vs clock hour for D-20; what counts as "the management network" for D-19 (derive from the backend's own addresses and the agents' configured backend URL) - document the choice.
- How long decision records are kept, as long as it is longer than generic retention (GATE-07); 365 days, matching `audit_ledger`, is the suggested floor.
- Whether the legacy `run_cycle`/`generate_plan`/`execute_plan` code is deleted outright or left unreachable with a test proving it - GATE-05 says "removed"; prefer deletion, after checking the other references (`backend/skill_handlers.py:192` dispatches type `autonomous_remediation`; `backend/agent_capabilities.py:77` maps it; `backend/app_startup.py:642` starts the loop).
- Layout and copy of the read-only Autonomous Ops screen (sidebar group `automation` per research), subject to the Spatial Glass design system and a `/gsd-ui-phase 81` contract if the planner wants one. Copy must pass ACTV-08.
- Test structure (structural "only the gate writes autonomous instructions" test, LLM-import ban over the new package, two-tenant isolation, approval double-click race, stop hold-back at agent poll).
- Whether `hypothesis` (dev-only) is added for property tests of the gate (research D20, non-blocking).

### Deferred Ideas (OUT OF SCOPE)
None raised during discussion beyond the milestone's own later phases (approve/deny/undo buttons -> Phase 83; on-call channel -> Phase 82; digest/stats/export -> Phase 86).

### Folded Todos
- **Fix stale capability-count assertions in `agent-install/omni-agent-rs/tests/integration.rs`** (`.planning/todos/pending/2026-08-17-fix-stale-capability-count-assertions-in-integration-rs.md`). Fold = make the Rust agent test suite green and close the todo. (See Q9: it is already green.)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GATE-01 | Explicit stored per-tenant level; new tenants Undoable-auto; migration for existing | Q5 (`autonomy_settings`, migration 024, `ensure_tenant` hooks at 2 creation sites) |
| GATE-02 | Eligible only when screen ticked; unreadable level = Suggest | Q2/Q3 (`view:autonomous_ops` permission switch, literal-membership test), decision order |
| GATE-03 | One ordered decision function; only the gate writes autonomous instructions; structural test | Q1 (`gate.decide/execute`), structural AST test design |
| GATE-04 | Code-owned registry; YAML only raises | Q1 registry table, `ACTION_MAP` coverage test |
| GATE-05 | Legacy LLM path removed; 0.90 bypass gone; test proves only registry actions reach queue | Q1 (what to delete, `execute_plan` is shared), XDR finding (open question 1) |
| GATE-06 | Platform + tenant stop, no restart, delivery hold-back, freeze approvals | Q4 (hook beside `hold_back`), stop semantics |
| GATE-07 | Write-ahead intent, audit mirror, retention floor | Q5 (`autonomy_actions`, `audit_ledger.event`, retention exclusion test) |
| GATE-08 | Protected targets + per-decision host cap | Never-touch design (Q6) |
| GATE-09 | Shadow mode default on | Two-layer shadow (D-02), env read per call |
| GATE-10 | Atomic single-use approval; expiry = denied | Q6 CAS (`find_one_and_update`), real-Mongo race test |
| GATE-11 | One runner (lock with renewal), explicit tenant, ctx reset, two-tenant test | Q7 (`renew_lock`, `tenant_scope`, raw+explicit tenantId) |
| GATE-12 | Agent status refresh every 5 min | Q7: premise does not match the code (open question 4) |
| GATE-13 | Separate permissions; Super Admin caps level | Q2 permission matrix |
| GATE-14 | Circuit breaker to Suggest | Q6 breaker algorithm |
| ACTV-01 | Read-only screen with six buckets | Q8, bucket mapping |
| ACTV-03 | Shadow entries labelled simulation | Q8 |
| ACTV-08 | Banned-terms copy check fails the build | Q8 shared rules JSON + two tests |
</phase_requirements>

## Summary

Phase 81 is composition over code that already exists, but five facts from reading the code change the plan and are not in the milestone research. (1) `execute_plan` is not only legacy: `_dispatch_step` and `_check_nscan_resolved` call it, so the legacy removal must replace it with a gate-owned executor, not just delete it. (2) A second, live-seeded automatic path exists that nothing in GATE/RESP covers: five enabled platform-wide XDR playbooks (`trigger_type: correlation`; two isolate an endpoint, one blocks an IP, one isolates and rolls back ransomware) auto-run on a correlation through `PlaybookExecutionEngine` and write the `response_tasks` queue, and `correlation_engine_threat._ai_select_playbook` lets an LLM pick the action. Live data is dormant (0 correlations, 0 playbook executions, 0 response tasks) but "ships inert" is not true until this is fenced. (3) The GATE-12 premise ("sleeps 3600 s after its first pass") does not match `monitor_agent_status`: it sleeps 30 s at the top of every iteration and has no 3600 s sleep (live agent statuses are current). A real defect sits next to it instead (wrong agents notified). (4) The folded Rust todo is already fixed (commit `c5a2e57ee`, 2026-08-23); `cargo test --offline --test integration` passes 21/21 now. (5) D-06 names an "Auditor" role that does not exist in the role table.

The build is: a new package `backend/autonomous_ops/` (settings, registry, protected targets, ledger, gate, reconciler, notify, messages), migration 024 (explicit settings for every tenant plus indexes), a catalogue entry/switch/permissions/slice mount, a delivery hook beside `agent_capabilities.hold_back` in both mounted poll handlers, `remediate()` / `approve_remediation()` / `deny_remediation()` routed through the gate, legacy removal, lock renewal, a two-route router (tenant + platform-only), and a read-only Activity screen plus app-wide stop banner. No new runtime dependencies. All existing tests that mock the database around `remediate()` need a shared fixture because the gate adds ledger and settings reads.

**Primary recommendation:** Build `autonomous_ops` on the raw Mongo handle with an explicit `tenantId` on every query and write (never the ambient ContextVar), make `gate.execute()` the only writer of stamped `agent_instructions`, mirror every ledger transition with `audit_ledger.event`, and drive all state changes through one compare-and-set `transition()` so approval, expiry, stop and undo cannot double-fire.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Decision gate, registry, classification | API / Backend (`autonomous_ops/gate.py`, `registry.py`) | - | Code-owned policy; must not be data or YAML |
| Per-tenant level, shadow, stop, breaker state | Database (`autonomy_settings`, `system_settings` doc for platform stop) | API (5 s cache, fail closed) | Must survive restarts and apply without one |
| Decision ledger + audit mirror | Database (`autonomy_actions`) | API (`ledger.py`, `audit_ledger.event`) | Write-ahead record before dispatch |
| Stop hold-back at delivery | API (agent poll handlers) | Agent (receives only what survives) | Defence in depth for already-queued instructions |
| Approve / deny / undo / stop / level routes | API (`autonomous_ops_endpoints.py`) | Browser (buttons in Phase 83) | Authorization is server-side only |
| Eligibility (screen tick) | Database (`tenants.enabledFeatures`) via `tenant_features` | API | Reuses the purchase model |
| Activity screen + stop banner | Browser (React) | API (`GET /status`, `GET /actions`) | Read-only; banner polls status |
| Expiry of approvals, stuck-dispatch cleanup | API background loop (`reconciler.py`) under distributed lock | Database | Must keep running during a stop (D-13) |
| Copy lint (ACTV-08) | Build/CI (pytest + vitest over files) | - | Static check, no runtime tier |

## Standard Stack

No new runtime or dev dependencies. Everything is already in `backend/venv` or `node_modules`.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12.3 | Backend runtime | `backend/venv/bin/python --version` [VERIFIED: shell] |
| FastAPI | 0.141.1 | Routers, dependencies | Already the API layer [VERIFIED: venv pip list] |
| motor / pymongo | 3.7.1 / 4.18.2 | Mongo access, `find_one_and_update` CAS | Already used by `audit_ledger`, `distributed_lock` [VERIFIED: venv pip list] |
| MongoDB | 8.0.34 | Store; partial unique indexes | `db.version()` via mongosh [VERIFIED: live] |
| PyYAML | 6.0.3 | Playbooks (unchanged) | existing [VERIFIED: venv pip list] |
| psutil | 7.2.2 | Interface addresses for built-in never-touch entries | already in requirements [VERIFIED: venv import, requirements.txt:113] |
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 | Backend tests (`asyncio_mode = auto`) | existing [VERIFIED: venv pip list; backend/pyproject.toml] |
| React / Vitest | ^19.2.0 / 5.0.0 | Screen + tests | existing [VERIFIED: package.json; vitest run output "RUN v5.0.0"] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `hypothesis` property tests (D20) | Exhaustive `itertools.product` over the finite gate input space | `hypothesis` is not installed (`import hypothesis` fails in the venv); the space is small (level x stop x eligible x class x protected x cap x dup x shadow), so full enumeration is stronger and adds nothing. **Recommendation: do not add `hypothesis`.** [VERIFIED: venv import failed for `mongomock_motor, hypothesis` in one probe; `pip list` shows neither] |
| `mongomock_motor` for CAS tests | Existing `tests/_mongo_test_db.py::mongo_db` (throwaway DB on the live mongod, skips if unreachable) | mongomock is not installed and cannot prove atomicity anyway |

**Installation:** none.

**Version verification:** versions above come from `backend/venv/bin/python -m pip list` and `mongosh` run this session. No registry lookups were needed because nothing is installed.

## Package Legitimacy Audit

This phase installs no external packages (backend, frontend or Rust). Audit table intentionally empty.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | - | - | - | - | - | - |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
 CALLERS (automatic origins)                          HUMANS
 UEBA anomaly (ueba_service:121)     Phase 83 sweep    Activity screen / Native Security console
 XDR auto-playbooks (open question 1)       |                    |  approve/deny/undo/stop/level
        |                                   v                    v
        v                      +-----------------------------------------------+
 AutonomousRemediationService.remediate()  | /api/autonomous-ops/*  (guarded)      |
        |  ActionRequest                    | /api/platform/autonomous-ops/* (plat.)|
        v                                   | /api/remediation/{id}/approve|deny    |
 +------------------- autonomous_ops.gate ----------------------------------+
 | decide(): platform stop -> eligibility -> tenant stop -> level -> class   |
 |   -> protected targets -> host cap / rate limit -> cooldown+suppression   |
 |   -> shadow wrapper                                                       |
 | writes INTENT row (autonomy_actions) first; mirrors audit_ledger.event    |
 | approve()/deny()/undo(): CAS transition(); re-check stop+expiry+targets   |
 | execute(): ONLY writer of stamped agent_instructions                      |
 +-----+-----------------------------+------------------------+-------------+
       | ALLOW_AUTO / approved        | NEEDS_APPROVAL/SUGGEST | REFUSE/SHADOW
       v                              v                        v
 agent_instructions (stamped    remediation_requests      ledger row only
 autonomy.actionId, tenantId)   pending_approval          (Refused / simulation)
       |
       v   agent poll (agent_tasks_endpoints = served; deployment_result_endpoints = shadowed)
 agent_capabilities.hold_back  ->  autonomous_ops.delivery.hold_back_autonomous  (stop, row state)
       v
 agent executes -> POST instructions/result -> reconciler / inline verify -> ledger terminal state

 reconciler loop (60 s, distributed lock WITH renewal): expire approvals (also during stop),
 fail stuck "dispatching" rows, evaluate breaker.   Stop/level/shadow live in Mongo, 5 s cache.
```

### Recommended Project Structure
```
backend/
├── autonomous_ops/
│   ├── __init__.py        # LEVELS, PROTECTED_COLLECTIONS (Phase 82 retention reads it)
│   ├── messages.py        # EVERY user-visible string (state labels, reason templates, notices); ACTV-08 scan target
│   ├── settings.py        # level/maxLevel/shadow/stop/breaker; 5 s cache; fail closed; env master read per call
│   ├── registry.py        # ACTIONS table; class resolution; undo pairing
│   ├── protected.py       # built-in + stored never-touch entries; ip/cidr/host matching (stdlib ipaddress)
│   ├── ledger.py          # autonomy_actions: create_intent, transition (CAS), queries, audit mirror
│   ├── gate.py            # decide / execute / approve / deny / undo; breaker + rate-limit hooks
│   ├── delivery.py        # hold_back_autonomous (poll hook)
│   ├── reconciler.py      # expiry + stuck-dispatch + breaker tick; reconciler_loop()
│   ├── notify.py          # single notify() seam (in-app now, Phase 82 channel later)
│   └── scope.py           # tenant_scope() context manager (set + reset in finally)
├── autonomous_ops_endpoints.py     # router (tenant) + platform_router
├── catalogue_mounts_autonomous_ops.py   # MOUNTS slice (new file; slice tests untouched)
├── migrations/024_autonomous_ops.py
└── tests/test_autonomous_ops_*.py, autonomy_support.py (fake ledger/settings fixture)
shared/autonomous-ops-banned-terms.json   # ACTV-08 rules read by both pytest and vitest
components/AutonomousOpsActivity.tsx, AutonomousOpsStopBanner.tsx; services/autonomousOpsApi.ts
```
Each Python file stays under the 500-line rule in CLAUDE.md; split `gate.py` into `gate.py` + `gate_checks.py` if it grows.

### Component Responsibilities (file:function level)

| Location | Change |
|----------|--------|
| `autonomous_remediation_service.py` `remediate()` (548-609) | Build `ActionRequest` from the selected playbook; call `gate.decide`; branch on outcome (see Q1). Remove `AUTONOMOUS_REMEDIATION_DRY_RUN` branch and the `is_destructive` status logic; keep `remediation_requests` row (console queue) and `write_audit` stages |
| `approve_remediation()` (611) / `deny_remediation()` (633) | Delegate to `gate.approve` / `gate.deny`; return `not_found`, `stopped`, `expired`, `already_handled` or the dispatch result |
| `_dispatch_step()` (760) and `_check_nscan_resolved()` (864) | Replace `execute_plan(...)` with `gate.execute(action_id, step)`; probes (`scan_*`) use registry class `probe` |
| `_dispatch_and_verify()` (674) | Keep lease + verify + rollback; rollback steps also go through `gate.execute` (class `compensating`); write ledger `executed` / `verified` / `failed` / `rolled_back` at the existing audit points |
| `run_cycle` (961), `generate_plan` (387), `execute_plan` (469), `verify_remediation` (894), `_log_decision` (937), `_create_failure_ticket` (1029), `_is_tenant_enabled` (123), `RemediationPlan` | Delete. Keep `scan_for_remediable_findings` (trimmed in Phase 83), `SEVERITY_ORDER` (imported by `response_orchestrator.py:56`), `RemediationFinding`, `_render_step_params` |
| `app_background_tasks.py` lines 10-40 | Delete the import and `autonomous_remediation_loop`; fix `monitor_agent_status` (Q7) |
| `app_startup.py:642-643` | Replace legacy loop registration with `reconciler_loop()` via `_safe_bg_task` |
| `agent_tasks_endpoints.py` `get_agent_instructions` (hold_back at line 47) and `deployment_result_endpoints.py` (lines 93-97) | Add the stop hook directly after `agent_capabilities.hold_back` |
| `backend_safety.py` `evaluate_action` | Remove the auto-approve branch and `AUTO_APPROVE_CONFIDENCE_THRESHOLD`; classification tables stop being a second policy (Q1) |
| `response_orchestrator.py` `is_duplicate_task` (231) | Add `tenantId` to both queries; refuse (return True) when `tenant_id` is empty |
| `distributed_lock.py` | Add `renew_lock` and `lock_with_renewal` |
| `rbac_defaults.py`, `shared/*.json`, `types.ts`, `sidebarPresentation.tsx`, `App.tsx` | Q2/Q3/Q8 |

### Q1 - Where the gate lives and how `remediate()` routes through it

**Registry (code, not YAML or DB).** Playbook `ACTION_MAP` today is [VERIFIED: remediation_playbook_service.py:21-31] `"patch_package": "upgrade_software", "kill_process": "kill_process", "restore_file": "restore_file", "block_ip": "block_ip", "unblock_ip": "unblock_ip", "disable_service": "disable_service", "enable_service": "enable_service", "rotate_key": "rotate_key", "rotate_key_rollback": "rotate_key_rollback"`. Recommendation for `registry.ACTIONS` (class, undo, protects):

| Action (instruction) | Class | Undo | Protects | Note |
|---|---|---|---|---|
| `block_ip` | auto | `unblock_ip` | ip param | Rust handler reads `parameters.ip_address` [VERIFIED: instructions.rs:530-538] |
| `quarantine_file` | auto | `unquarantine_file` | host | verb does not exist on agents yet (Phase 83); entry is dormant |
| `restart_service` | auto | none | host | restart budget is Phase 83 |
| `isolate_host` | approve | `restore_host` | host | mapped already to `remediation_executor` in `agent_capabilities` |
| `kill_process` | approve | none | host | |
| `reboot_host` | approve | none | host | Phase 84 verb |
| `upgrade_software` (`patch_package`) | approve | none | host | the vendored playbook says `destructive: false`, `rollback: []` [VERIFIED: playbooks/patch_package.yaml] - the registry fixes this because YAML may only raise |
| `restore_file`, `disable_service`, `rotate_key` | approve | `enable_service` for disable_service | host | conservative (research D6) |
| `unblock_ip`, `enable_service`, `unquarantine_file`, `restore_host`, `rotate_key_rollback` | `undo-only` | - | - | only dispatchable as the inverse of a registered action |
| `scan_file`, `scan_ip`, `scan_url`, `scan_hash` | `probe` | - | - | read-only verify re-scan used by `_check_nscan_resolved` |
Fail closed: an action not in the table is REFUSED `unregistered_action`. A test asserts every `ACTION_MAP` key resolves to a registry entry and every `undo` target is registered.

**Decision function.** `decide(db, req) -> Decision` takes `tenant_id` explicitly and never reads the ContextVar. Hard denies run in the GATE-03 order and short-circuit; soft escalations accumulate and the strongest wins (SUGGEST over NEEDS_APPROVAL over ALLOW), so a protected target is refused even at Suggest (no point proposing it).

| Step | Check | Result |
|---|---|---|
| 1 | platform stop (read uncached on error path; unreadable = stopped) | REFUSE `platform_stop` |
| 2 | eligibility: tenant is `platform-admin` (D-04) -> REFUSE `platform_tenant`; screen not ticked or settings unreadable -> effective level capped at Suggest (`not_enabled` / `settings_unreadable`) | soft |
| 3 | tenant stop | REFUSE `tenant_stop` |
| 4 | level: `off` -> REFUSE `level_off`; `suggest` -> soft SUGGEST | |
| 5 | registry: unknown -> REFUSE; class `approve` or any playbook step `destructive` -> soft NEEDS_APPROVAL | |
| 6 | protected target; cross-tenant target (`agent.tenantId != tenant_id`); no target | REFUSE `protected_target` / `cross_tenant_target` / `no_target` |
| 7 | host cap (exactly 1 host, D-17) and rate limit (D-20): more than one target or 20 automatic actions in the rolling 60 min | soft NEEDS_APPROVAL `blast_radius` / `rate_limit` |
| 8 | dedupe / cooldown / undo suppression | REFUSE `duplicate` / `suppressed_by_undo` |
| 9 | shadow wrapper: if master env shadow or tenant `shadow` flag, any outcome that would dispatch or create a card becomes state `shadow` with `wouldHave=<outcome>`; REFUSEs stay `refused` | |

Rolling-window choice for D-20 (document in code): count ledger rows with `autoDispatched: true` and `createdAt >= now - 60 min`, from the database (not memory); shadow rows are excluded.

**Wiring in `remediate()`** (keep return shapes where tests depend on them):
```python
req = ActionRequest(tenant_id=finding.tenant_id, kind="security", playbook=playbook["name"],
                    actions=[s["action"] for s in playbook["steps"]], targets=[finding.agent_id] if finding.agent_id else [],
                    params=..., playbook_destructive=any(s.get("destructive") for s in playbook["steps"]),
                    reason={"ruleId": f"playbook:{playbook['name']}", "inputs": {"findingId": finding.finding_id,
                            "findingType": finding.finding_type, "severity": finding.severity}},
                    dedupe_key=f"{finding.tenant_id}|{playbook['name']}|{finding.finding_type}|{finding.finding_id}",
                    origin="ueba" if finding.finding_type == "anomaly" else "sweep")
decision = await gate.decide(db, req)          # intent row written here, before anything else
# REFUSE -> {"status": "refused", "reason": code}; SHADOW -> {"status": "shadow", ...};
# NEEDS_APPROVAL/SUGGEST -> insert remediation_requests(status="pending_approval", autonomyActionId=...), return pending_approval
# ALLOW_AUTO -> insert remediation_requests(status="dispatching"), call _dispatch_and_verify(...)
```
The console queue (`native_security_ops_endpoints.get_remediation_queue`, statuses `pending_approval`, `dispatching`, `deferred`) keeps working because `remediation_requests` stays the console's queue; the ledger row is the authority for expiry/stop and is linked by `remediationId` / `autonomyActionId`. `ueba_service._dispatch_anomaly_remediation` (line 121) is unchanged and is gated automatically: `anomaly` + `shadow_ai_detected` maps to `kill_process`, class approve, so at shipped defaults it records a `shadow` row.

**0.90 bypass.** `evaluate_action` auto-approves when `auto_approved and high_confidence and not is_critical_asset` [VERIFIED: backend_safety.py:139-148]; its only importer is `playbook_engine_safety.py:9`. Delete the branch and the constant (keep the keyword parameter, ignored, so `playbook_engine_safety.py:75-81` still imports). Also its tables are the opposite of the lock [VERIFIED: backend_safety.py:29-47 `SAFE_ACTIONS` holds `kill_process`; `APPROVAL_REQUIRED_ACTIONS` holds `restart_service`]; derive the playbook-engine decision from the registry or leave the tables as a legacy human-path advisory but unreachable by any autonomous path. Nothing in `backend/tests` references `evaluate_action`, `auto_approved` or the threshold (grep of tests: no hits).

### Q2 - Permissions and how they flow

Recommended strings (planner may rename before any role document holds them - costly later, D-05):

| String | Meaning | Built-in holders |
|---|---|---|
| `view:autonomous_ops` | see the screen and activity | tenant_admin, analyst, security_analyst, incident_responder; platform_support (see below) |
| `manage:autonomous_ops` | change level, edit never-touch, restore breaker, clear a tenant stop | tenant_admin |
| `control:autonomous_ops` | approve / deny / undo, press stop | tenant_admin, security_analyst, incident_responder |
| `control:platform_autonomous_ops` | platform-wide stop and clear, set tenant max level, lift tenant shadow, platform-wide never-touch | nobody in the table; Super Admin through `"*"` |

Flow, each verified in code:
- **Closure.** `implied_closure` adds `view:X` and `request:X` for every `manage:X` and "never a `control:` string" [VERIFIED: rbac_defaults.py:305-318]. `manage:autonomous_ops` therefore gives `view:autonomous_ops`, and gives nothing in `control:`; `request:autonomous_ops` is dropped unless it is in the vocabulary (`deliverable_closure` filters by `KNOWN_PERMISSIONS`, built from role table + manifest + switches [VERIFIED: permission_vocabulary.py:50-59]).
- **MFA (D-07).** `ADMIN_TIER_PERMISSIONS` is `frozenset({"manage:users","manage:rbac","manage:settings","manage:api_keys","control:remote_access"}) | PLATFORM_ONLY_PERMISSIONS` [VERIFIED: rbac_defaults.py:181-187]. Add `"control:autonomous_ops"` to the literal set; adding `control:platform_autonomous_ops` to `PLATFORM_ONLY_PERMISSIONS` (lines 169-175) makes it admin-tier automatically. Enforcement is at token verification: `_enforce_admin_mfa` refuses every route for an unverified session unless `mfa_verified` or the `mfa_exempt` claim [VERIFIED: authentication_service.py:163-171]. A custom role holding the new string is admin-tier by `effective_permissions` (test pattern in `test_custom_role_mfa.py`).
- **Platform-only.** `effective_permissions` drops every `PLATFORM_ONLY_PERMISSIONS` entry found in a non-platform role document [VERIFIED: rbac_service.py:100-106, `banned = rbac_defaults.SUPER_ADMIN_ONLY_PERMISSIONS | {"*"}`]. Super Admin holds it by `"*"`.
- **Custom-role ceiling (D-09).** `ceiling_allows` uses `implied_closure` of the caller's permissions [VERIFIED: rbac_defaults.py:334-344]; a tenant admin holds all three tenant strings, so it can grant them; nothing to add.
- **Tenant switch.** A switchable `view:X` removes every permission on resource X (`_resource` ignores the verb) [VERIFIED: tenant_features.py `narrow`], so an unticked tenant also loses `manage:`/`control:autonomous_ops`.
- **Platform Support read (D-08).** The role table comment says Platform Support holds "every view: permission in shared/catalogue-access.json except the super-admin-only screens and view:remote_access" [VERIFIED: rbac_defaults.py:117-119]. Add `view:autonomous_ops` to `platform_support`; it then passes the catalogue guard by role and holds no write string. **Do not use `platform_read=("view:tenants",)`**: the only existing use is the `settings` guard [VERIFIED: catalogue_mounts_billing_identity.py:67] and `platform_billing` also holds `view:tenants`, so it would admit Billing, which D-08 does not intend. Cross-tenant reads need an explicit `tenantId` query parameter honoured only when `can_read_all_tenants(user)` (precedent: `audit_endpoints.py:31`, `tenant_endpoints.py:49`); additionally restrict to `platform_tier in ("owner","support")` in the handler.
- **API-key restriction (D-10).** The helper that distinguishes the two is `TokenData.auth_source`, `"session"` (default) or `"api_key"` [VERIFIED: auth_types.py:22 `auth_source: str = "session"`; api_key_auth.py `authenticate` returns `auth_source="api_key"`]. `get_current_user` accepts JWT only; only routes depending on `api_key_auth.get_current_user_or_api_key` can be reached with a key. So: mount the tenant guard with `catalogue_guard(..., auth=get_current_user_or_api_key)` (precedent: `WEBHOOKS_GUARD`), and put a route-level `_require_interactive_session` (403 when `auth_source == "api_key"`) on approve, deny, undo, clear-stop, level, never-touch and restore routes. Name the dependency `_require_*`: `tests/_route_walk.py` treats names matching `_require_` as permission dependencies and `test_route_auth_baseline` fails login-only writes [VERIFIED: _route_walk.py:29 `PERM_DEP`].
- **MFA-verified session vs the exempt Super Admin.** `TokenData` carries `mfa_verified` but not the `mfa_exempt` claim. A strict `require_mfa` (`mfa_verified`) would lock out the deliberately MFA-exempt Super Admin account (project memory 2026-10-21) from clearing the platform stop. **Recommendation:** interpret D-10's "MFA-verified" as "an interactive session that passed the admin-tier MFA gate" (session auth plus admin-tier permission already guarantees it), do not add a second strict check, and record this as a user-confirmable choice (open question 6).
- **Legacy approve/deny routes.** `remediation_control_endpoints.py` routes use `get_current_user` (JWT only: keys already excluded) and permission `manage:active_response`. Recommendation: approve/deny require `control:autonomous_ops` and delegate to the same `gate.approve/deny`; keep `GET /audit` as is. The existing tests patch `remediation_control_endpoints.verify_permission`, so keep calling it from that module.

Test files whose golden values change (executor must update, not skip): `test_rbac_defaults.py` (GOLDEN sets and `GOLDEN_SIZES = {"tenant_admin": 130, "user": 22, "analyst": 19, "security_analyst": 17, "incident_responder": 12, ..., "platform_support": 76, ...}` [VERIFIED: test_rbac_defaults.py:113-115]), `test_custom_role_mfa.py:24,72-75,121` (`BUILTIN_ADMIN_TIER` and the "not admin-tier" role list include `security_analyst`/`incident_responder`), `test_admin_mfa_required.py:60` (parametrized no-MFA roles include `security_analyst`), `test_platform_roles.py` (support holds only `view:`), plus `test_effective_permissions`/`test_login_me_permissions` if they assert counts.

### Q3 - Catalogue and manifest wiring

Manifest entry (group `automation`, not an enforced group, so no `SLICES` change, no mandatory explicit write list; a tagged guard still avoids the `catalogue-gaps.json` ledger):
```json
{"view": "autonomousOps", "label": "Autonomous Ops", "group": "automation", "nav": true,
 "permission": "view:autonomous_ops", "write": ["manage:autonomous_ops", "control:autonomous_ops"],
 "routes": ["/api/autonomous-ops"]}
```
- **Switch.** Add to the "Automation & Intelligence" group of `shared/tenant-feature-switches.json` (per its own rule "its permission's switch when no other item shares that permission"): `{"permission":"view:autonomous_ops","label":"Autonomous Ops"}` and `{"permission":"manage:autonomous_ops","label":"Manage Autonomous Ops","parent":"view:autonomous_ops"}` (same pattern as `view:automation` / `manage:automation`). `test_the_switch_catalogue_is_sound` requires non-screen switches to be in the tenant-admin defaults [VERIFIED: test_tenant_feature_switches.py:100]; both are. New tenants stay Overview-only (`START_FEATURES` at tenant_features.py:97).
- **Eligibility reading.** Use literal membership: `"view:autonomous_ops" in enabledFeatures` via `tenant_features.enabled_features(tenant_id, get_db)` (raw, explicit id, errors propagate). Do not use `switched_off()`, because `"all"` in the list switches nothing off and would make an unticked tenant eligible. `[ASSUMED: no live tenant holds "all"; counts of enabledFeatures were 9/70/59/3]`.
- **Mount.** New file `backend/catalogue_mounts_autonomous_ops.py` exporting `MOUNTS = {("autonomous_ops_endpoints", "router"): AUTONOMOUS_OPS_GUARD}`; `catalogue_mounts._collect` globs `catalogue_mounts_*.py` [VERIFIED: catalogue_mounts.py `_collect`], so no registry code changes. The guard's `read`/`write` must equal the manifest's resolved lists (`test_*_guards_match_manifest` pattern, `_catalogue_parity.resolved_read/resolved_write`). Register in `router_registry.py` next to line 410: `_load(app, "autonomous_ops_endpoints", "router")` and `_load(app, "autonomous_ops_endpoints", "platform_router")`.
- **Platform router.** Prefix `/api/platform/autonomous-ops`. `/api/platform` is already an `unownedPrefixes` entry [VERIFIED: shared/catalogue-access.json unownedPrefixes] and is served today by `platform_endpoints.py` (`/platform/features`), so no manifest entry is needed; no mount guard; every route carries `Depends(_require_platform_autonomy_control)` (`has_platform_permission(user, "control:platform_autonomous_ops")`, which is owner-only because no table role holds it). This is the HA/DR pattern in spirit (HA/DR instead gates a manifest entry with the Super-Admin-only `view:backups`/`manage:backups`).
- **Frontend sources the drift tests read.** `types.ts` `AppView` (+ `'autonomousOps'`) and `Permission` union (+ the three strings; they must be in the union or the exact "backend-only strings" list in `catalogueAccess.test.ts` breaks); `components/sidebarPresentation.tsx` (`SIDEBAR_PRESENTATION.autonomousOps` icon entry, else `findNavDrift` fails); `App.tsx` `case 'autonomousOps'` with a lazy import (App has no per-view permission map any more; `viewAccess` reads the manifest).
- **Hard-coded counts that must move by one** [VERIFIED]: `test_catalogue_manifest.py:147` (`== 203` AppView members) and `:161` (`len(nav) == 189`), `test_closure_delivery.py:214` (`len(tf.NAV_SCREENS) == 189`), `test_role_visibility.py:87` (`... == 189`), `src/__tests__/catalogueAccess.test.ts:49` (`toHaveLength(189)`).
- **Other drift tests to run:** `test_catalogue_route_parity.py` (slow), `test_catalogue_slice_*.py` (unaffected unless a slice file is edited), `test_route_auth_baseline.py`, `test_audit_parity.py` (all `/api/` writes are audited by middleware; new routes need no exemption), `test_tenant_feature_switches.py`, `SidebarTenantSwitches.test.tsx`, `ManageTenantModal.test.tsx`.

### Q4 - Stop hold-back at both poll paths

Route order matters: `agent_tasks_endpoints` `GET /api/agents/{hostname}/instructions` is registered first (route walk index 36) and `deployment_result_endpoints` `GET /api/agents/{agent_id}/instructions` is shadowed (index 488) [VERIFIED: run_real_app_walk this session]. Both still get the hook (existing tests call the `deployment_result_endpoints` function directly). `agent_instruction_endpoints.py` has a third handler that is not mounted (absent from `router_registry`); add the hook there too or delete the dead route, and let the structural test list the three modules explicitly.

Stamp every instruction `gate.execute` writes:
```python
{"id": task_id, "type": command, "agent_id": agent_id, "tenantId": tenant_id,
 "payload": params, "parameters": params, "status": "pending", "triggered_by": "autonomous_ops",
 "autonomy": {"actionId": row_id, "tenantId": tenant_id, "kind": "action" | "undo" | "probe"},
 "created_at": now_iso}
```
Hook, called right after `agent_capabilities.hold_back` and before the `status` update:
```python
instructions = await hold_back_autonomous(db, tenant_id, instructions)
```
`hold_back_autonomous` returns early with no database call when no instruction carries `autonomy` (keeps `test_agent_instruction_poll_*` MagicMock tests green, same shape as `hold_back`'s `if not instructions: return`). For stamped ones it reads the platform stop and the tenant stop uncached, and the ledger row state. It withholds when: platform or tenant stop and `kind != "undo"` (D-12), the ledger row is not in `approved`/`dispatching`/auto state, the row's tenant differs from the instruction's `tenantId`, or any read fails (fail closed: withhold, leave `pending`). A stop-withheld instruction is marked terminal `cancelled_by_stop` (never resurrected on resume, consistent with D-13) and its ledger row transitions to `cancelled_by_stop`; do that write best-effort so a ledger error cannot break the poll. The stop endpoint additionally bulk-marks undelivered stamped `pending` instructions at press time via a partial index on `autonomy.actionId`; the poll hook stays authoritative.

Capability mapping: `agent_capabilities._INSTRUCTIONS` already maps `isolate_host`, `kill_process`, `block_ip`, `unblock_ip`, `disable_service`, `enable_service`, `rotate_key`, `rotate_key_rollback` to `remediation_executor` [VERIFIED: agent_capabilities.py:73-77]; unmapped names bypass per-tenant capability ticks ("Names outside the catalogue are never touched"). Add `restart_service`, `quarantine_file`, `unquarantine_file`, `restore_host` -> `remediation_executor` and `reboot_host` -> `patch_installer` now, with a registry test: every registry command resolves via `instruction_capability`. Keep the existing `"autonomous_remediation": "autonomous_response"` entry: `skill_handlers.handle_rotate_key` (human `/rotate-key`) still writes `type: "autonomous_remediation"` [VERIFIED: skill_handlers.py:177-192, `"type": "autonomous_remediation"`]; that instruction is human-initiated and is not stamped, so do not treat `type` as the autonomy marker.

### Q5 - Ledger, settings, migration 024, audit mirror, retention

**Collections** (raw handle, explicit `tenantId`; BSON `datetime` for new date fields, avoiding the repo's mixed string/ObjectId-time formats):
- `autonomy_settings` (one doc per tenant): `tenantId, level, maxLevel, shadow(bool, default true), stop{active, scope("tenant"|"platform"), pressedBy, pressedByTier, pressedAt, reason}, breaker{trippedAt, previousLevel, actionIds}, updatedAt, updatedBy`.
- Platform stop: doc `{type: "autonomous_ops", stop: {...}}` in `system_settings` via `db._db.system_settings` (raw, like the LLM settings readers [VERIFIED: agent_location_history_service.py:67 `raw.system_settings.find_one`]); Phase 82's watchdog contract in ARCHITECTURE reads this doc.
- `autonomy_actions`: `id, tenantId, kind("security"|"control"|...), action, command, targets[], target(display), origin, state, level, shadow, wouldHave, reason{ruleId, inputs}, reasonText, trace[], dedupeKey, remediationId, instructionIds[], approval{requiredBy, expiresAt, approver, decidedAt}, undo{available, action, params, undoneAt, undoneBy, undoActionId}, autoDispatched, createdAt, updatedAt, finishedAt`. Stop pressed/cleared and breaker events are rows with `kind: "control"` so the Activity view reads one collection; they are excluded from rate-limit and breaker counts.
- `autonomy_never_touch`: `id, scope("platform"|"tenant"), tenantId, kind("ip"|"cidr"|"host"|"agent"), value, note, createdBy, createdAt`.

**State machine** (names are Claude's discretion; this set maps cleanly onto the six UI buckets): `shadow`, `suggested`, `awaiting_approval`, `approved`, `dispatching`, `executed`, `verified`, `failed`, `rolled_back`, `undone`, `denied`, `expired`, `cancelled_by_stop`, `refused`. UI buckets: Pending = `awaiting_approval`, `approved`, `dispatching`; Done = `executed`, `verified`; Undone = `undone`, `rolled_back`; Failed = `failed`; Refused = `refused`, `denied`, `expired`, `cancelled_by_stop`; Suggested = `suggested`; `shadow` rows are shown as Simulation (ACTV-03). One function does every change:
```python
async def transition(db, tenant_id, action_id, from_states, to_state, **fields):
    doc = await db.autonomy_actions.find_one_and_update(
        {"id": action_id, "tenantId": tenant_id, "state": {"$in": list(from_states)}},
        {"$set": {"state": to_state, "updatedAt": now(), **fields}},
        return_document=ReturnDocument.AFTER)
    if doc is not None:
        await audit_ledger.event(f"autonomous_ops.{to_state}", tenant_id, actor=_actor(fields),
                                 catalogue="autonomousOps", resourceId=action_id, ruleId=doc["reason"]["ruleId"])
    return doc          # None = lost the race / wrong state
```
**Write-ahead (GATE-07).** `ledger.create_intent` raises on failure and `decide` converts that to REFUSE `ledger_unavailable`; no instruction is written without a ledger row in `approved`/auto state, and `gate.execute` re-reads the row. `audit_ledger.event` never raises and spools on failure [VERIFIED: audit_ledger.py `record`, `_spool`], so it cannot be the guard; the intent row is. Await the `audit_ledger.event` mirror before dispatch to keep "intent before dispatch" in the chain order. Fault-inject test: make `insert_one` raise and assert zero `agent_instructions` writes.

**Indexes and migration 024.** The runner derives the version from the filename and calls `up(db)` with the raw Motor database at startup seeding [VERIFIED: migrations/runner.py, app_startup.py:240 `await run_migrations(db._db)`], so "apply migration 024" is the backend restart. `up` must be idempotent:
- for every `tenants` doc with an `id`: `update_one({"tenantId": id}, {"$setOnInsert": {level, maxLevel, shadow: True, stop: None, updatedBy: "migration-024", ...}}, upsert=True)`. Recommendation: `undoable_auto` for tenants, **`off`/`off` for `platform-admin`** (D-04 says the gate treats it as Off and the UI must not offer to raise it; storing Off keeps the stored value honest while the gate also hard-codes it). This deviates from D-01's literal "every existing tenant: Undoable-auto" and needs a yes (assumption A2).
- indexes: `autonomy_settings.tenantId` unique; `autonomy_actions.id` unique; `(tenantId, createdAt desc)`; `(tenantId, state, createdAt desc)`; `(state, approval.expiresAt)`; unique partial `(tenantId, dedupeKey)` with `partialFilterExpression {state: {$in: ["suggested","awaiting_approval","approved","dispatching"]}}` (a terminal transition leaves the index automatically; verified live on 8.0.34 that both a `$in` and a boolean-equality partial unique index create and block a duplicate); `autonomy_never_touch (scope, tenantId, kind, value)` unique; `agent_instructions` partial `(autonomy.tenantId, status)` where `autonomy.actionId` exists.
- No backfill of `remediation_requests`: live counts are 0 (`remediation_requests`, `remediation_audit`, `agent_ai_decisions` all 0) [VERIFIED: live mongosh]. `approve_remediation` for a request with no `autonomyActionId` refuses (`legacy_request`) rather than guessing.
- New tenants: call `settings.ensure_tenant(tenant_id)` after the two real creation inserts, `authentication_endpoints.py:355` (sign-up) and `tenant_endpoints.py:123` (Add Tenant) [VERIFIED: git grep `tenants.insert_one`], plus an idempotent `ensure_all_tenants()` at startup as a backstop; a missing doc reads as the default (Undoable-auto, shadow on) but an unreadable one is Suggest.

**Retention.** `retention_service.py` deletes only `audit_logs` (90 d default), `metrics`, `notifications`, `agent_location_history`, `agent_uptime_rollups` and the four `AGENT_TELEMETRY` collections [VERIFIED: retention_service.py read in full]; `retention_endpoints.update_policy` refuses unknown collections. So `autonomy_actions` is already outside generic retention, but the audit-mirror rows in `audit_logs` are removed by `cleanup_audit_logs` after 90 d on a manual run, and by `audit_ledger.purge_expired` after 365 d. The decision record of truth is `autonomy_actions` (no TTL). Add `PROTECTED_COLLECTIONS` in `autonomous_ops/__init__.py`, a 365-day floor constant for a later purge job, and a test asserting no retention module references those names (Phase 82's retention job must import the constant).

### Q6 - Approvals, rate limit, never-touch, breaker

- **Atomic approval.** `gate.approve`: (1) read stop uncached, refuse `stopped` (D-12); (2) `transition(from=("awaiting_approval","suggested"), to="approved", where approval.expiresAt > now)` - if the row is past expiry, `transition` to `expired` and return `expired`; `None` means `already_handled`; (3) CAS the legacy row `remediation_requests.update_one({"id","tenantId","status":"pending_approval"}, {"$set":{"status":"dispatching"}})` and require `matched_count == 1`; (4) re-validate volatile facts (agent still enrolled and same tenant, not protected, tenant level not Off, finding still open for `security` kind); (5) dispatch. Today's code does `find_one` then an unconditional `update_one` [VERIFIED: autonomous_remediation_service.py:619-628], which double-dispatches on a double click. Real-Mongo race test: `asyncio.gather` of two approves; exactly one dispatch.
- **Expiry** is 24 h from creation (`approval.expiresAt`, D-16). The reconciler expires `awaiting_approval`/`suggested` rows whose time has passed on every tick, including during a stop (D-13), and `approve` also checks lazily.
- **Rate limit / host cap.** See decision table step 7. A rate-limit trip notifies once per window (marker field on `autonomy_settings`).
- **Never-touch list.** Built-ins are computed in code by `protected.builtin_entries()` and cached ~60 s: loopback, link-local, unspecified and multicast; every address of the backend's interfaces and each interface's subnet (the management network; `eth0 10.0.0.4/24` on this VM [VERIFIED: `ip -4 -o addr`]); the hosts in `PLATFORM_URL`, `BACKEND_HOST`, `BACKEND_WS_HOST` (env names read from code in `agent_download_endpoints.py`, `agent_chat_endpoints.py`, `remote_endpoints.py`; values unknown, `[ASSUMED]` set on the live VM, never read); and every agent enrolled in `platform-admin` by id, hostname and `ipAddress` [VERIFIED live: `Omniai-copy`, `10.0.0.4`, tenant `platform-admin`]. Stored entries come from `autonomy_never_touch`; built-ins cannot be removed because they are not rows (DELETE on a built-in id returns 404/403). Match with stdlib `ipaddress` (`ip_address`, `ip_network(strict=False)`); an unparsable IP parameter is REFUSE `invalid_target`. Protection applies to the `block_ip` IP parameter and to the target host for every other registry action.
- **Circuit breaker (D-18).** After each automatic action reaches a bad terminal outcome (`failed`, `rolled_back`, `undone`) and on each reconciler tick: take the tenant's 3 most recent finished `autoDispatched` rows (excluding `shadow` and `control`); if all 3 are bad and the oldest `finishedAt` is within 24 h, set `level = "suggest"`, `previousLevel`, write a `control` row, notify. Nothing re-arms it; `POST /settings/restore-level` (manage, interactive) restores `previousLevel` and clears the marker.
- **Level caps.** Ordinal off < suggest < undoable_auto. `PUT /settings/level` rejects above `maxLevel`; only the platform route changes `maxLevel` and `shadow` (D-03).

### Q7 - Lock renewal, tenant context, cadence, `is_duplicate_task`

- **Lock renewal.** `distributed_lock.acquire_lock` upserts `_distributed_locks` with a fixed `expiresAt` and no renewal [VERIFIED: distributed_lock.py]. Add:
```python
async def renew_lock(db, name, token, ttl_seconds=DEFAULT_LOCK_TTL_SECONDS) -> bool:
    now = datetime.now(timezone.utc)
    res = await db._db["_distributed_locks"].update_one(
        {"_id": name, "token": token, "expiresAt": {"$gt": now}},      # still ours and unexpired
        {"$set": {"expiresAt": now + timedelta(seconds=ttl_seconds)}})
    return res.matched_count == 1                                     # False = lost it: stop work
```
plus `lock_with_renewal(db, name, ttl, renew_every)`: an async context manager that acquires, runs a renewer task, exposes `handle.lost`, and releases by token. Sweeps check `handle.lost` between units of work. Existing `scheduler.py` jobs keep their fixed 55 s TTL; only new autonomous loops use renewal. Tests: real Mongo, TTL 1 s, held 3 s with renewal: second acquire fails; without renewal: second acquire succeeds after expiry; a crashed holder's lock expires.
- **Tenant context.** The new package does not use the ambient ContextVar at all: raw handle plus explicit `tenantId` on every filter and document. Reason, verified in `database.py`: under `platform-admin` the wrapper injects no filter and stamps no `tenantId` on insert; with no context it stamps `ORPHANED_DATA_NO_TENANT_CONTEXT` [VERIFIED: database.py `TenantIsolatedCollection.insert_one`]. This is also why `execute_plan` is unsafe today: its instruction has no `tenantId` of its own, so a background caller yields an instruction the poll (filtered on `tenantId`) never delivers. Provide `scope.tenant_scope(tenant_id)` (set, `try/finally` reset) for code that must call tenant-wrapped helpers (e.g. `_verify_finding_resolved`, which already resets correctly). The legacy loop's leak (token overwritten each iteration, only the last reset) disappears with its deletion; `scan_for_remediable_findings` has the related unbound-`_tctx` risk if `set_tenant_id` raises (fix in Phase 83 when trimmed, or wrap now with `tenant_scope`).
- **`monitor_agent_status` (GATE-12).** Observed code: `await asyncio.sleep(30)` is the first statement inside the loop; nothing sleeps 3600 s [VERIFIED: app_background_tasks.py read in full, working tree and `git show HEAD`]; live statuses are current (Online agent `lastSeen` seconds old; seven stale agents Offline) [VERIFIED live]. The "3600" in PITFALLS 10 matches `license_seat_maintenance_loop`, not this function. Recommended plan for GATE-12: (a) pin the documented cadence with a frozen-clock test (patch `asyncio.sleep`, assert `update_many` runs on consecutive iterations and no sleep exceeds 300 s); (b) name the interval constant and move the sleep to the loop bottom; (c) fix the real defect: after `update_many` flips N agents it re-queries `{"status":"Offline","lastSeen":{"$lt":threshold}}` with `to_list(length=modified_count)`, which returns the first N long-offline agents (the live DB has six stale QA agents), so notifications and websocket events go to the wrong agents. Select the Online-and-stale ids first, update by id, notify those. Tell the user GATE-12's premise did not hold.
- **`is_duplicate_task`** [VERIFIED: response_orchestrator.py:231-262]: both queries lack `tenantId` (the cross-agent one takes `tenant_id` but only uses it in the `if`). Add `"tenantId": tenant_id` to both, and return True when `tenant_id` is empty (fail closed). `response_tasks` rows are stamped with `tenantId` only when written under a real tenant context (`_dispatch` builds the task without it), so query the raw collection with the explicit field and note that unstamped rows will not match (acceptable: the gate has its own dedupe). Real-Mongo two-tenant test.

### Q8 - Frontend

- **Files.** `services/autonomousOpsApi.ts` (own module like `roleApi.ts`; `apiService.ts` is 6334 lines), `components/AutonomousOpsActivity.tsx` (name does not collide with the existing `AutonomousOpsLog.tsx`, which belongs to the Agents screen's agentic run), `components/AutonomousOpsStopBanner.tsx`, one `case 'autonomousOps'` plus lazy import in `App.tsx` (2083 lines, already carries unrelated uncommitted edits), icon entry in `sidebarPresentation.tsx`, `types.ts` additions.
- **Banner.** Mount inside the shell column above `<Header>` (App.tsx ~1959, next to the "Backend connection lost" bar), rendered only when `useUser().hasPermission('view:autonomous_ops')`; poll `GET /api/autonomous-ops/status` every 30 s while the tab is visible and on focus, and refetch after any stop action. Shows scope (platform or organization), who, when, reason. Use Spatial Glass tokens and the lit-edge card/`glass` classes from `design-system/omni-agent-2030/MASTER.md`; no hard-coded hex (anti-pattern list there). Run `/gsd-ui-phase 81` if a UI-SPEC contract is wanted (config has `ui_phase: true`).
- **Screen.** Six filter buckets (Pending, Done, Undone, Failed, Refused, Suggested) over `GET /api/autonomous-ops/actions?bucket=&limit=&cursor=`, columns: what ran (label from `messages.py`), why (rule id + reasonText), target, result, time; shadow rows labelled "Simulation: nothing was done". Server returns display-ready labels so React renders text only (React escapes finding-derived strings; no `dangerouslySetInnerHTML`). Loading, empty, error, and `no access` states follow `NoAccessPanel` conventions. Super Admin and Platform Support get a tenant selector that passes `tenantId`.
- **Scope question.** The Phase 81 wording is "read-only". Stop/resume with a typed reason, level, and shadow indicator have no UI home in any later phase (checked ROADMAP/REQUIREMENTS). See open question 2.
- **ACTV-08 enforcement.** Put the rules in `shared/autonomous-ops-banned-terms.json` (precedent: `shared/*.json` read by both sides) and add two thin tests that share them: pytest `test_autonomous_ops_copy.py` scanning `backend/autonomous_ops/messages.py`, `shared/catalogue-access.json` label, and the frontend component/api files; vitest `src/__tests__/autonomousOpsCopy.test.ts` scanning the same frontend files with `fs` (pattern: `catalogueAccess.test.ts` `read()`). Rules: `\bASI\b` (case-sensitive), `\bAutopilot\b` (case-insensitive), `fully[- ]autonomous`, `\bAGI\b` (CONTEXT specifics add it), and `\broll(?:ed|ing)?[- ]?backs?\b` unless the same line contains `where supported`. Scope is an explicit file list, never `.planning/**` (those files quote the banned terms as prohibitions) and never `windowsAutopilot`/`autopilot_service.py`. Include negative controls (a bad string must fail) as the manifest test does. Note `npm run build` is `vite build` and does not run tests; "fails the build" means the test gate (`test_command: npx vitest run src/__tests__` in `.planning/config.json`) plus pytest.

### Q9 - Folded Rust todo
`CapabilityManager::new()` registers 18 collectors (metrics, process_monitor, persistence_detection, pii_scanner, logs, fim, vulnerability_scan, compliance, runtime_security, predictive_health, ueba, sbom, ebpf_tracing, system_patching, software_management, remote_access, network_discovery, agent_update) and `ids()` appends `chat_window` and `ticket_reporter`, giving 20 [VERIFIED: capabilities/mod.rs:89-125]. `tests/integration.rs` already asserts 20 (`test_capability_manager_has_20_capabilities`), 18 collected, and an OS-aware platform check: `assert_eq!(payload["platform"], if cfg!(windows) { "Windows" } else { "Linux" });` [VERIFIED: integration.rs:79-86, 271]. Commit `c5a2e57ee` ("fix 7 stale integration tests against real capability contract", 2026-08-23) did this; the todo (created 2026-08-17) was never closed. Ran `PATH=$HOME/.cargo/bin:$PATH cargo test --offline --test integration` in `agent-install/omni-agent-rs`: **21 passed, 0 failed** (cold compile 4m27s; run against the working tree that has uncommitted `capabilities/mod.rs` interval work, whose ids/count are unchanged). Task for the plan: re-run, move the todo file to `.planning/todos/completed/`, no source change. Note `cargo` is not on the default shell PATH.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tamper-evident audit | A new hash chain | `audit_ledger.event()` (CAS chain head, spool, 365 d checkpoint) | Already tested (`test_audit_ledger.py`); never two truths |
| Approval single-use | Read-then-write status checks | `find_one_and_update` with a state filter (`transition`) | Only an atomic filter closes the double-click race |
| Dedupe under concurrency | In-memory sets, `find_one` then insert | Unique partial index on `(tenantId, dedupeKey)` over non-terminal states | Race-safe across workers; verified on Mongo 8.0.34 |
| Role strings, MFA, ceiling | New permission checks | `rbac_defaults` role table, `ADMIN_TIER_PERMISSIONS`, `ceiling_allows`, `catalogue_guard` | Phase 75-77 machinery; new strings plug in |
| IP / CIDR matching | Regex or string compare | stdlib `ipaddress` | v4/v6, mapped addresses, strict parsing |
| Interface enumeration | Parsing `ip addr` output | `psutil.net_if_addrs()` | Already a dependency |
| Single-runner sweeps | A new scheduler | `distributed_lock` + `renew_lock` | Existing idiom; add one function |
| In-app alerts | A new notification store | `pending_agents.post_to_recipients` behind `notify.py` | One seam Phase 82 swaps for the on-call channel |
| Rule engines / property tests | json-logic/CEL/OPA, `hypothesis` | Pure Python decision function + exhaustive `itertools.product` | Finite space; milestone STACK rejected rule engines |
| Copy lint | Ad-hoc greps in CI | Shared JSON rules + two thin tests with negative controls | Same pattern as manifest drift tests |

**Key insight:** every one of the "safety" mechanisms here already has a tested primitive in the repo; the work is wiring them through one function and one collection so no second path exists.

## Runtime State Inventory

Phase removes a legacy loop and migrates tenant data, so each category is answered.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `remediation_requests`, `remediation_audit`, `agent_ai_decisions`: 0 documents; 0 autonomous `agent_instructions`; 4 tenants (`platform-admin`, QA Tenant, Exafluence, ABC); 5 enabled platform playbooks `trigger_type: correlation`; 0 correlations, 0 `playbook_executions`, 0 `response_tasks` [VERIFIED: live mongosh] | Data migration: 024 writes `autonomy_settings` for all 4 tenants (code edit alone would not). No backfill of remediation rows |
| Live service config | Tenant feature string `autonomousRemediation` on 0 tenants; value of `AUTONOMOUS_REMEDIATION_DRY_RUN` in the live environment not read (`.env` not opened) | Code edit removes the string check; user confirms the env value and that shadow stays on at first deploy |
| OS-registered state | None: no systemd unit or timer references this feature | None |
| Secrets / env vars | `AUTONOMOUS_REMEDIATION_DRY_RUN` stays as the deployment master; `AUTONOMOUS_REMEDIATION_INTERVAL_SEC`, `MAX_AUTO_SEVERITY` only used by the removed loop and scan ceiling | Code edit; add `AUTONOMOUS_OPS_RECONCILE_INTERVAL_SEC` (default 60) |
| Build artifacts | Frontend `dist` must be rebuilt and published by the user; Rust has no build artifact change | UI publish is the user's step (project memory) |

## Common Pitfalls

### Pitfall 1: Deleting `execute_plan` breaks verify and step dispatch
**What goes wrong:** `_dispatch_step` and `_check_nscan_resolved` call it, so a plain delete kills the playbook engine.
**How to avoid:** replace both call sites with `gate.execute` first, then delete; add the structural test in the same plan.
**Warning signs:** `AttributeError: execute_plan` in `test_autonomous_remediation_loop.py`.

### Pitfall 2: Ambient tenant context in background work
**What goes wrong:** under `platform-admin` nothing is scoped or stamped; with no context rows get `ORPHANED_DATA_NO_TENANT_CONTEXT`; instructions without `tenantId` are never delivered because the poll filters on it.
**How to avoid:** raw handle plus explicit `tenantId` everywhere in `autonomous_ops`; a two-tenant real-Mongo test; assert `get_tenant_id() is None` after a reconciler run.

### Pitfall 3: A second automatic dispatch path the research did not list
**What goes wrong:** `correlation_engine_response._trigger_playbooks` auto-runs the five live seeded playbooks (`executed_by="xdr-auto"`), `_ai_select_playbook` runs an LLM-chosen action (`isolate|block|quarantine|notify`), and `_fallback_select_playbook` runs the first enabled playbook by severity; the actions queue `response_tasks` (block_ip and quarantine_file with no gate at all; isolate with `evaluate_action`) [VERIFIED: playbook_engine_actions.py `_action_block_ip`, `_action_isolate_endpoint`, `_action_quarantine_file`; correlation_engine_threat.py:48-120]. `auto_approved` is set in `trigger_data` but `_gate_high_risk_action` reads it from the engine context, so the 0.90 bypass is dead code today, yet still violates GATE-05's text.
**How to avoid:** decide open question 1; at minimum remove the bypass and the LLM selector's execution.

### Pitfall 4: Tests that mock `get_database` around `remediate()` will break
**What goes wrong:** `test_autonomous_remediation_loop.py`, `test_remediation_guards.py`, `test_ueba_remediation_trigger.py` patch `autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN` and use `MagicMock` databases that know nothing about `autonomy_*`.
**How to avoid:** one shared `tests/autonomy_support.py` (in-memory fake ledger, permissive settings object, patch points) used by all three; keep the module constant `AUTONOMOUS_REMEDIATION_DRY_RUN` exported from the service so `patch(...)` targets still resolve and pass it into the gate as the master flag. `test_rotate_key_wiring.py` only imports `_render_step_params` and is unaffected.

### Pitfall 5: API keys cannot reach `get_current_user` routes at all
**What goes wrong:** with the default catalogue guard auth, D-10's "API keys may read and press stop" is impossible; flipping the whole router to API-key-capable auth without per-route session checks lets keys approve.
**How to avoid:** guard auth = `get_current_user_or_api_key`; `_require_interactive_session` on every non-press write; a probe test with `auth: "api_key"` on each route.

### Pitfall 6: Admin-tier change cascades into golden tests and users
**What goes wrong:** the five role-table and MFA tests listed in Q2 fail; at deploy, Security Analysts and Incident Responders are forced to enrol MFA at next sign-in (D-07).
**How to avoid:** update goldens deliberately; put the MFA enrolment notice in the live-only checklist.

### Pitfall 7: Hard-coded counts
Five assertions (Q3) must change from 203/189 to 204/190 in the same commit as the manifest entry.

### Pitfall 8: Shadow rows polluting limits
Rate limit, breaker and "Done" counts must exclude `shadow` and `control` rows or a day of simulation trips the breaker.

### Pitfall 9: Uncommitted work in files this phase edits
`git status` shows unrelated uncommitted hunks in `backend/app_background_tasks.py` (telemetry retention loop), `backend/app_startup.py` (its registration), `backend/agent_capabilities.py` (collection intervals), `backend/deployment_result_endpoints.py` (newest-wins sort), `App.tsx` (reset-password), and `agent-install/omni-agent-rs/src/capabilities/mod.rs` [VERIFIED: git diff]. Executors must stage by path with hunk review, never `git add -A`, and never revert them. (2378 status lines also include mode and CRLF noise.)

### Pitfall 10: Inline dispatch blocks the approve request
`_dispatch_and_verify` polls the agent inline (up to 60 s per step plus 60 s verify). Phase 81 keeps that for approve and `remediate()` (the resumable reconciler states are Phase 83 scope); the reconciler only expires and cleans up. Document so Phase 83 buttons run approval as a background task.

## Code Examples

### Guard mount with API-key-capable auth (one slice file)
```python
# backend/catalogue_mounts_autonomous_ops.py
from api_key_auth import get_current_user_or_api_key
from catalogue_guards import catalogue_guard

AUTONOMOUS_OPS_GUARD = catalogue_guard(
    "autonomousOps",
    read=("view:autonomous_ops",),
    write=("manage:autonomous_ops", "control:autonomous_ops"),
    auth=get_current_user_or_api_key,
)
MOUNTS = {("autonomous_ops_endpoints", "router"): AUTONOMOUS_OPS_GUARD}
```
Source pattern: `catalogue_guard(... auth=...)` signature and the `WEBHOOKS_GUARD` precedent in `catalogue_mounts_settings_ops.py`.

### Session-only dependency (named so the route walker counts it as a permission check)
```python
async def _require_interactive_session(user: TokenData = Depends(get_current_user_or_api_key)) -> TokenData:
    if getattr(user, "auth_source", "session") == "api_key":
        raise HTTPException(403, "An interactive sign-in is required for this action")
    return user
```

### Structural writer test (GATE-03), shape only
```python
def test_only_gate_writes_agent_instructions():
    offenders = {f for f in backend_py_files() if writes_collection(f, {"agent_instructions", "instructions"})}
    assert offenders <= GRANDFATHERED_WRITERS | {"autonomous_ops/gate.py"}   # a new writer fails here
    assert "autonomous_remediation_service.py" not in offenders              # legacy writer is gone
    assert "autonomous_ops/gate.py" in offenders                             # and the gate does write
```
`GRANDFATHERED_WRITERS` is a committed list of today's 27 modules that write `agent_instructions`/`instructions` [VERIFIED: git grep this session found 27 files, e.g. `agent_chat_endpoints.py`, `agentic_service.py`, `patch_core_endpoints.py`, `soar_engine.py`, `swarm_service.py`, `skill_handlers.py`]; a new writer fails the test. A second test AST-scans `autonomous_ops/*.py` for any import of `ai_service`, `ai_orchestration`, `agentic_service`, `ai_remediation_service`, `remediation_service`, `ai_providers`, `langchain*`, `anthropic`, `openai`, and for `agent_instructions` outside `gate.py`/`delivery.py`.

### Migration skeleton
```python
# backend/migrations/024_autonomous_ops.py
DESCRIPTION = "Autonomous Ops: explicit autonomy level for every tenant, ledger indexes"
async def up(db):
    async for t in db.tenants.find({}, {"_id": 0, "id": 1}):
        tid = t.get("id")
        if not tid: continue
        lvl = "off" if tid == "platform-admin" else "undoable_auto"
        await db.autonomy_settings.update_one({"tenantId": tid}, {"$setOnInsert": {
            "tenantId": tid, "level": lvl, "maxLevel": lvl, "shadow": True, "stop": None,
            "updatedBy": "migration-024", "updatedAt": datetime.now(timezone.utc)}}, upsert=True)
    await db.autonomy_settings.create_index("tenantId", unique=True, name="tenant_unique")
    await db.autonomy_actions.create_index([("tenantId", 1), ("dedupeKey", 1)], unique=True, name="open_dedupe",
        partialFilterExpression={"state": {"$in": ["suggested", "awaiting_approval", "approved", "dispatching"]}})
    ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Env constant dry-run read at import | DB level + shadow + stop, read per call with a short cache; env stays the deployment master | this phase | Stop and level apply without a restart |
| Boolean `destructive` in operator-editable YAML | Code registry; YAML may only raise | this phase | A tenant cannot lower a class by editing a playbook |
| `find_one` then `update_one` approvals | CAS `find_one_and_update` | this phase | Single-use approvals |
| LLM-written scripts / tool choice on autonomous paths | Playbook actions only | this phase | GATE-05 |

**Deprecated/outdated:** `AutonomousRemediationService.run_cycle`/`generate_plan`/`execute_plan`/`verify_remediation`, the `autonomousRemediation` tenant feature string, `AUTO_APPROVE_CONFIDENCE_THRESHOLD`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | No live tenant has `"all"` in `enabledFeatures`; eligibility uses literal `view:autonomous_ops` membership | Q3 | An `"all"` tenant would show the screen but gate at Suggest; low |
| A2 | Store `off`/`off` for the Platform tenant in migration 024 (D-01 says every tenant Undoable-auto; D-04 says Off) | Q5 | Needs user yes; otherwise store undoable_auto and rely on the hard-coded gate rule |
| A3 | A tenant that is not ticked is capped at Suggest (roadmap SC1 wording) rather than refused (ARCHITECTURE said deny); rows are still recorded | Q1 | If refusal is intended, change step 2 only; recorded Suggest rows for an unticked tenant are invisible to its users |
| A4 | Permission strings `view:/manage:/control:autonomous_ops` and `control:platform_autonomous_ops` | Q2 | Costly to rename after custom roles hold them (D-05) |
| A5 | D-10 "MFA-verified" = session auth plus the admin-tier gate, not a strict `mfa_verified` re-check | Q2 | Strict check locks out the MFA-exempt Super Admin |
| A6 | Stop-withheld instructions become terminal `cancelled_by_stop`, not delivered on resume | Q4 | If resume should release them, D-13's "nothing stale fires" is weakened |
| A7 | Rolling 60-minute window for D-20; management network = interface subnets plus `PLATFORM_URL`/`BACKEND_HOST`/`BACKEND_WS_HOST` hosts plus platform-tenant agents | Q6 | Too narrow/wide protection; values of those env vars unknown |
| A8 | Platform Support reads via the role-table `view:` string, not `platform_read` | Q2 | If `platform_read` is mandated, Billing gets read access unless handler-restricted |
| A9 | Starlette `BackgroundTasks` (UEBA caller) may run without the request tenant ContextVar | Pitfall 2 | Irrelevant if the raw+explicit design is followed |
| A10 | `PLATFORM_URL`, `BACKEND_HOST`, `BACKEND_WS_HOST` are set on the live VM | Q6 | Management-network list is smaller (interfaces still covered) |

## Open Questions

1. **XDR correlation auto-playbooks and the LLM selector (critical, not in CONTEXT or RESP-11).**
   - Known: five enabled platform playbooks auto-run on a correlation; two isolate, one blocks an IP, one isolates plus VSS rollback; `_ai_select_playbook` lets an LLM choose the action; they write `response_tasks`, a queue the GATE-06 hold-back does not cover. Live is dormant (0 correlations/executions/tasks).
   - Also automatic and not gated: `correlation_engine_threat.py` lines 257 and 308 `insert_many` into `agent_instructions` (a threat hunt fanned out to every matching agent, and kill-chain pre-staging such as `create_vss_snapshot`), both monitoring or snapshot verbs; they stay in the grandfathered list of the structural test but should be named in the verification notes.
   - Unclear: whether Phase 81 must fence it ("nothing acts automatically after this phase" and the roadmap goal say yes; GATE-03's structural test is scoped to `agent_instructions`).
   - Recommendation: in Phase 81 (a) remove the confidence bypass, (b) delete the LLM selector's execution and the rule-based fallback's auto-run (make them record a suggestion through the gate), and (c) for automatic executors (`xdr-auto`, `ai-selector`, `fallback-selector`) pass the four side-effecting playbook actions (`block_ip`, `isolate_endpoint`, `quarantine_file`, `rollback_ransomware`) through `gate.decide`, executing only on ALLOW_AUTO and otherwise recording the decision. The response-task poll path needs the same stop hold-back (third delivery queue). If the user prefers to defer (c), record it as a Phase 83 item next to RESP-11 and state it in the verification notes.
2. **Is a minimal controls strip in scope?** CONTEXT says the screen is read-only, but stop/resume with a typed reason, level display and shadow indicator have no home in later phases. Recommendation: include Stop/Resume (typed reason) and a level/shadow readout in Phase 81; leave level changes, never-touch editing, max-level and shadow lift as API routes with an operator runbook. Confirm.
3. **"Auditor" does not exist** in `ROLE_DEFAULTS` [VERIFIED: rbac_defaults.py:35-145 keys: tenant_admin, user, analyst, security_analyst, incident_responder, viewer, itam_admin, itam_user, itam_viewer, platform_support, platform_billing]. Recommendation: grant view to `analyst` only and let tenant admins create an Auditor custom role (D-09); do not invent a built-in role in this phase.
4. **GATE-12 premise** (3600 s sleep) does not match the code; confirm the plan (cadence test plus wrong-agent notification fix) satisfies the requirement.
5. **Platform tenant stored level and unticked-tenant semantics** (A2, A3).
6. **D-10 strictness vs the MFA-exempt Super Admin** (A5).
7. **Live `AUTONOMOUS_REMEDIATION_DRY_RUN` value** is the user's to confirm (not read here); shadow default must hold at first deploy.
8. **Legacy approve/deny permission:** moving them from `manage:active_response` to `control:autonomous_ops` changes who can approve in the Native Security console (tenant_admin holds both; nobody else held the old one).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| MongoDB (`mongod`) | real-Mongo tests, migration test | yes | 8.0.34, no auth locally | tests skip if unreachable (`mongo_db` fixture) |
| Python venv | backend tests | yes | 3.12.3 | - |
| Node / Vitest | frontend tests | yes | v20.20.2 / 5.0.0 | - |
| cargo / rustc | folded Rust todo | yes, not on default PATH | 1.98.1 | `PATH=$HOME/.cargo/bin:$PATH` |
| `mongomock_motor`, `hypothesis` | none needed | no | - | real throwaway Mongo; exhaustive enumeration |
| Ollama | nothing in this phase may need it | no | - | none needed (LLM-import ban test) |

**Missing dependencies with no fallback:** none. **With fallback:** the two above.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Backend pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode = auto`); Frontend vitest 5.0.0 + @testing-library/react (jsdom); Rust `cargo test` for the folded todo |
| Config file | `pytest.ini` (root), `backend/pyproject.toml`, `backend/tests/conftest.py` (throwaway `omni_test_<pid>` DB), `vite.config.ts` `test:` block |
| Quick run command | `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_<file>.py -q -p no:cacheprovider` and `npx vitest run src/__tests__/<file>` |
| Full suite command | `npx vitest run src/__tests__` ; `npm run build` ; `TICKET_ATTACHMENT_DIR=$(mktemp -d) FILE_SHARE_DIR=$(mktemp -d) backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider` (commands as used in Phase 77 VALIDATION.md; full backend about 11 min; baseline then 4048 passed / 47 skipped) |

Verified this session: `venv/bin/python -m pytest tests/test_distributed_lock.py tests/test_scheduler_lock.py -q` 9 passed in 0.4 s; `npx vitest run src/__tests__/catalogueAccess.test.ts` 44 passed in 2.9 s; `cargo test --offline --test integration` 21 passed.

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GATE-01 | migration writes explicit level for every tenant (idempotent; platform off); new-tenant default | real-Mongo | `pytest backend/tests/test_autonomous_ops_migration.py` | Wave 0 |
| GATE-02 | unticked / unreadable settings cap at Suggest; literal tick; platform tenant refused | unit | `pytest backend/tests/test_autonomous_ops_gate.py` | Wave 0 |
| GATE-03 | exhaustive decision table order; only the gate writes stamped instructions (AST) | unit + structural | `pytest backend/tests/test_autonomous_ops_gate.py backend/tests/test_autonomous_ops_structural.py` | Wave 0 |
| GATE-04 | registry classes pinned; YAML only raises; every ACTION_MAP key registered; undo targets exist; every command capability-mapped | unit | `pytest backend/tests/test_autonomous_ops_registry.py backend/tests/test_agent_capabilities.py` | Wave 0 / exists |
| GATE-05 | legacy symbols absent; no LLM imports; only registry-listed stamped instructions with no `script` for every finding type; bypass removed | unit + structural | `pytest backend/tests/test_autonomous_ops_structural.py backend/tests/test_autonomous_remediation_loop.py` | Wave 0 / modify |
| GATE-06 | platform and tenant stop: decisions refused, queued stamped instruction withheld at BOTH poll handlers, undo delivered, approve refused, clear authority, no restart | unit + real-Mongo | `pytest backend/tests/test_autonomous_ops_stop.py backend/tests/test_agent_instruction_poll_tenant_scoping.py` | Wave 0 / exists |
| GATE-07 | intent before dispatch (fault injection), audit mirror per transition, `audit_ledger.verify` valid, retention modules never touch protected collections | real-Mongo | `pytest backend/tests/test_autonomous_ops_ledger.py` | Wave 0 |
| GATE-08 | built-in protected entries cannot be removed; block_ip of platform IP/mgmt subnet refused; host cap = 1 | unit | `pytest backend/tests/test_autonomous_ops_protected.py` | Wave 0 |
| GATE-09 | env master and tenant flag each force shadow; shadow dispatches nothing; D-03 lift is platform-only | unit | `pytest backend/tests/test_autonomous_ops_gate.py` | Wave 0 |
| GATE-10 | two concurrent approves dispatch once; expired approval refused; expiry continues in stop | real-Mongo | `pytest backend/tests/test_autonomous_ops_ledger.py backend/tests/test_autonomous_ops_stop.py` | Wave 0 |
| GATE-11 | two-tenant isolation of settings, ledger, queue, list; ContextVar `None` after reconciler; lock renewal; `is_duplicate_task` tenant filter | real-Mongo | `pytest backend/tests/test_autonomous_ops_isolation.py backend/tests/test_distributed_lock.py backend/tests/test_response_orchestrator_tenant.py` | Wave 0 / modify |
| GATE-12 | cadence pinned by frozen clock; wrong-agent notification fixed | unit | `pytest backend/tests/test_monitor_agent_status.py` | Wave 0 |
| GATE-13 | permission matrix over the real app (viewer/analyst/security_analyst/tenant_admin/platform_support/billing/super_admin; API key vs session; level above cap 403; platform routes owner-only) | real-app probe | `pytest backend/tests/test_autonomous_ops_endpoints.py backend/tests/test_catalogue_slice_autonomous_ops.py` | Wave 0 |
| GATE-14 | 3 consecutive bad within 24 h trips to Suggest, records previous level, no auto re-arm; rate limit trips at 20; shadow excluded | unit | `pytest backend/tests/test_autonomous_ops_breaker.py` | Wave 0 |
| ACTV-01 | six buckets, display fields, pagination, tenant selector gate | backend + component | `pytest backend/tests/test_autonomous_ops_endpoints.py` ; `npx vitest run AutonomousOpsActivity.test.tsx` | Wave 0 |
| ACTV-03 | shadow rows labelled Simulation | component | `npx vitest run AutonomousOpsActivity.test.tsx` | Wave 0 |
| ACTV-08 | banned terms fail both gates; negative controls | pytest + vitest | `pytest backend/tests/test_autonomous_ops_copy.py` ; `npx vitest run autonomousOpsCopy.test.ts` | Wave 0 |
| D-15 | stop banner shown only to viewers of the screen, shows who/when/why | component | `npx vitest run AutonomousOpsStopBanner.test.tsx` | Wave 0 |
| Folded todo | Rust integration suite green | cargo | `cd agent-install/omni-agent-rs && PATH=$HOME/.cargo/bin:$PATH cargo test --offline --test integration` | exists |

### Sampling Rate
- **Per task commit:** the new or changed test file plus any exact-list test it touches.
- **Per wave merge:** `npx vitest run src/__tests__` and `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_*.py backend/tests/test_rbac_defaults.py backend/tests/test_custom_role_mfa.py backend/tests/test_admin_mfa_required.py backend/tests/test_catalogue_manifest.py backend/tests/test_tenant_feature_switches.py backend/tests/test_remediation_guards.py backend/tests/test_autonomous_remediation_loop.py backend/tests/test_ueba_remediation_trigger.py -q -p no:cacheprovider`.
- **Phase gate:** full suite green including `npm run build` and the slow parity modules (`test_catalogue_route_parity.py`, `test_audit_parity.py`, `test_route_auth_baseline.py`).

### Wave 0 Gaps
- [ ] `backend/tests/autonomy_support.py` - fake ledger and permissive-settings fixtures reused by the three legacy remediation test files
- [ ] `backend/tests/test_autonomous_ops_{registry,gate,ledger,stop,protected,breaker,isolation,structural,endpoints,migration,copy}.py`, `test_catalogue_slice_autonomous_ops.py`, `test_monitor_agent_status.py`, `test_response_orchestrator_tenant.py`
- [ ] `src/__tests__/{AutonomousOpsActivity.test.tsx,AutonomousOpsStopBanner.test.tsx,autonomousOpsCopy.test.ts}`
- [ ] `shared/autonomous-ops-banned-terms.json`
- [ ] Updated existing tests: `test_rbac_defaults.py`, `test_custom_role_mfa.py`, `test_admin_mfa_required.py`, `test_catalogue_manifest.py`, `test_closure_delivery.py`, `test_role_visibility.py`, `catalogueAccess.test.ts`, `test_remediation_guards.py`, `test_autonomous_remediation_loop.py`, `test_ueba_remediation_trigger.py`
- Framework install: none.

**Live-only (cannot be unit-tested, from ROADMAP plus this research):** apply migration 024 by restarting the backend; flip the platform stop on the live server and confirm a real agent poll withholds a queued stamped instruction without a restart; confirm agent status cadence; Security Analyst / Incident Responder MFA enrolment prompt; UI publish; confirm shadow stays on and the env master value.

## Security Domain

`security_enforcement` is enabled (`.planning/config.json`, ASVS level 1, block on high).

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Existing session + MFA admin-tier gate; API keys excluded from approve/deny/undo/clear (`auth_source`) |
| V3 Session Management | yes | Existing JWT sessions and revocation; no new session logic |
| V4 Access Control | yes (central) | `catalogue_guard` + route-level `_require_*` dependencies; tenant id from the token, never the body; platform routes owner-only |
| V5 Input Validation | yes | Pydantic bodies: level enum, reason length bounds, IP/CIDR via `ipaddress`, bounded `limit`, `tenantId` honoured only for platform staff |
| V6 Cryptography | no new use | Hash chain stays in `audit_ledger` (never hand-rolled) |
| V7 Logging | yes | Every transition mirrored to the hash-chained audit ledger; actors recorded |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Tenant admin raises own level above the Super Admin cap | Elevation | Server-side `level <= maxLevel`; `maxLevel` writable only on the platform route |
| API key approves or clears a stop | Elevation | `_require_interactive_session`; probe test per route |
| Cross-tenant read via `tenantId` parameter | Information disclosure | Honoured only when `can_read_all_tenants` and tier is owner/support; raw queries always filter explicit tenant |
| Double-click / replayed approval | Tampering | CAS `transition`, single-use state, expiry check |
| Stop bypass by an already-queued instruction or a race | Tampering / DoS | Delivery hook with uncached reads, `gate.execute` re-check, stamp on every instruction |
| Autonomous action against the platform host or management network | DoS | Built-in never-touch entries, refused at decide and at approve |
| Poisoned finding text rendered in the UI (XSS) | Tampering | Display strings from `messages.py` templates; React text rendering only; backend never returns HTML |
| Ledger tampering | Repudiation | No update/delete API; mirror in chained `audit_logs`; `autonomy_actions` outside every retention path |
| LLM-chosen action reaches an endpoint | Elevation | LLM-import ban test; `generate_plan` removed; XDR selector fenced (open question 1) |
| Unbounded list / never-touch growth | DoS | Cursor pagination with a hard cap; max entries per tenant |

## Project Constraints (from CLAUDE.md)
- Do what was asked; do not create files unless necessary; do not create documentation files unless requested (the operator runbook for stop/level API use is only needed if the user confirms API-only controls, open question 2).
- Never save working files or tests to the repo root; use `/backend`, `/tests`, `/src`, `/scripts`; read a file before editing it.
- Never commit secrets or `.env`; never add `Co-Authored-By` unless `.claude/settings.json` sets `attribution.commit` (the system reminder for this session does supply an attribution line; follow the per-session rule the executor is given).
- Keep files under 500 lines; validate input at system boundaries.
- Always run tests after code changes and verify the build before committing (`npm run build && npm test` is the repo's stated gate; backend pytest per Validation Architecture).
- Naming: the feature is "Autonomous Ops"; never "ASI", "AGI" or "Autopilot" (Windows Autopilot is a separate screen, `backend/autopilot_service.py`).
- Project memory: deploys, restarts and UI publish are the user's step; `git push` needs the user (`! git push origin npx`); archive, do not delete, tenant data; agent installs and secrets are the user's.

## Sources

### Primary (HIGH confidence, opened this session)
- Code: `backend/autonomous_remediation_service.py`, `app_background_tasks.py`, `app_startup.py`, `backend_safety.py`, `playbook_engine_safety.py`, `playbook_engine_actions.py`, `enhanced_playbook_engine.py`, `correlation_engine_threat.py`, `correlation_engine_response.py`, `remediation_playbook_service.py`, `playbooks/*.yaml`, `response_orchestrator.py`, `remediation_control_endpoints.py`, `native_security_ops_endpoints.py`, `ueba_service.py`, `agent_tasks_endpoints.py`, `deployment_result_endpoints.py`, `agent_instruction_endpoints.py`, `agent_capabilities.py`, `audit_ledger.py`, `retention_service.py`, `retention_endpoints.py`, `distributed_lock.py`, `scheduler.py`, `database.py`, `tenant_context.py`, `tenant_features.py`, `rbac_defaults.py`, `rbac_service.py`, `rbac_utils.py`, `permission_vocabulary.py`, `catalogue_guards.py`, `catalogue_mounts*.py`, `router_registry.py`, `authentication_service.py`, `api_key_auth.py`, `auth_types.py`, `pending_agents.py`, `skill_handlers.py`, `migrations/runner.py`, `migrations/022*.py`, `migrations/023*.py`; `shared/catalogue-access.json`, `shared/tenant-feature-switches.json`, `shared/agent-capabilities.json`; frontend `utils/catalogueAccess.ts`, `components/sidebarPresentation.tsx`, `components/Sidebar.tsx`, `components/NoAccessPanel.tsx`, `services/roleApi.ts`, `App.tsx` (shell region), `design-system/omni-agent-2030/MASTER.md`; tests `test_catalogue_manifest.py`, `_catalogue_parity.py`, `_route_walk.py`, `test_rbac_defaults.py`, `test_custom_role_mfa.py`, `test_tenant_feature_switches.py`, `test_distributed_lock.py`, `test_scheduler_lock.py`, `_mongo_test_db.py`, `conftest.py`, the three legacy remediation test files; Rust `capabilities/mod.rs`, `tests/integration.rs`, `instructions.rs`.
- Planning: `81-CONTEXT.md`, `REQUIREMENTS.md`, `ROADMAP.md` (Phase 81 block), `STATE.md`, `research/SUMMARY.md`, `ARCHITECTURE.md`, `PITFALLS.md`, `77-VALIDATION.md`, the folded todo.
- Live read-only checks: mongosh against `omni_platform` (counts, tenant fields, agents, playbooks, partial-index behaviour on a throwaway database that was dropped); `route walk` of the real app; `cargo test` and `pytest`/`vitest` sample runs; `git status`/`git diff` for working-tree overlap.

### Secondary / Tertiary
- None. No web sources were needed; no external library API is introduced.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - nothing new; versions read from the venv and tools.
- Architecture: HIGH for integration points and file/function targets; MEDIUM for the XDR fence and UI scope (user decisions pending).
- Pitfalls: HIGH - each comes from code read this session.

**Research date:** 2026-10-25
**Valid until:** 2026-11-08 (the working tree has many uncommitted edits in touched files; re-check `git diff` before planning edits)
