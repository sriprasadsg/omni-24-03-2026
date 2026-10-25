# Phase 81: Autonomy Gate, Stop Switch & Activity Ledger - Context

**Gathered:** 2026-10-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 81 builds the safety core of milestone v4.3 Autonomous Ops and ships it **inert**:

- a stored autonomy level per tenant (Off / Suggest / Undoable-auto)
- one code-owned decision function ("the gate") that every autonomous action must pass, and a code-owned action registry (which actions are automatic, which need approval, and each action's undo)
- a platform-wide stop and a per-tenant stop, enforced again when an agent polls for instructions
- an intent record written before any dispatch, mirrored into the hash-chained audit ledger
- shadow mode, single-use expiring approvals, the never-touch list, the per-decision host cap, the per-tenant rate limit and the circuit breaker
- removal of the legacy LLM remediation loop (`run_cycle` / `generate_plan` / `execute_plan`) and the 0.90 confidence auto-approve for autonomous paths
- scheduler hardening (one runner at a time with lock renewal, per-tenant context reset) and the agent online/offline cadence fix
- a **read-only** Autonomous Ops screen (Pending / Done / Undone / Failed / Refused / Suggested, shadow entries labelled as simulation) and the banned-terms copy check

Requirements: GATE-01..14, ACTV-01, ACTV-03, ACTV-08 (17). Nothing acts automatically after this phase: the first autonomous actor is the Phase 83 security sweep. Approve/deny/undo **buttons** on the screen are Phase 83 (ACTV-02); Phase 81 builds their backend semantics. The on-call channel is Phase 82; Phase 81 calls a notify hook that uses the existing in-app notification path until then.

Naming rule: the feature is "Autonomous Ops" — never "ASI", never "Autopilot" (Windows Autopilot is a separate existing screen, `backend/autopilot_service.py`).

</domain>

<decisions>
## Implementation Decisions

### Locked by milestone requirements (not re-decided here)
- Eligibility = a Super Admin has ticked the Autonomous Ops screen switch for the tenant (GATE-02); a level that cannot be read is treated as Suggest.
- Action classes per the locked split: block IP, quarantine file, restart service are auto; isolate host, kill process, patch reboot need approval; playbook YAML may raise a class, never lower it (GATE-04). `backend/backend_safety.py`'s opposite classification and `AUTO_APPROVE_CONFIDENCE_THRESHOLD = 0.90` must not apply to autonomous paths (GATE-05).
- The legacy LLM path (`AutonomousRemediationService.run_cycle` → `generate_plan` → `execute_plan`, which never checks `requires_approval`) is removed and the scheduled `autonomous_remediation_loop` no longer calls it (GATE-05). Verified 2026-10-25: nothing has ever been dispatched by it on the live server.
- Changing a level, approving/undoing and the platform stop are separate permissions; a Super Admin sets each tenant's highest allowed level (GATE-13).

### Turning it on
- **D-01:** Migration writes an explicit level for every existing tenant: **Undoable-auto**, the same default as new tenants. The screen tick plus shadow mode are the opt-in. (Satisfies GATE-01's "explicit stored level".)
- **D-02:** Shadow mode has two layers. The existing server setting `AUTONOMOUS_REMEDIATION_DRY_RUN` (default true) stays as a **deployment-wide master** that forces shadow for every tenant. Below it, **every tenant (new and existing) also has its own shadow flag, on by default**, so when the operator turns the server setting off, each tenant still records-only until it is lifted for that tenant. In shadow the gate records "would have done" entries and dispatches nothing.
- **D-03:** Only a **Super Admin** may lift a tenant's shadow flag (going live is a platform decision, like ticking the screen).
- **D-04:** The **Platform tenant is never eligible** in v4.3: the gate always treats it as Off regardless of ticks or level, and the UI does not offer to raise it. The platform server keeps itself healthy through the Phase 82 watchdog. (The local agent on this VM is enrolled to the Platform tenant.)

### Who can do what
- **D-05:** Three tenant permissions plus one platform-only permission. Exact strings are the planner's call, but follow existing vocabulary: a `view:` permission for the screen, a `manage:` permission for changing the level / never-touch list / clearing a stop, and an approve-tier permission for approve/deny/undo and pressing the stop (`control:` has precedent — `control:remote_access` is already admin-tier). The platform-wide stop uses a platform-only permission added to `rbac_defaults.PLATFORM_ONLY_PERMISSIONS`, served from a platform-only route modelled on HA/DR (`backend/migrations/023_hadr_platform_only.py`). The Phase 77 closure (`manage:X ⇒ view:X`, `request:X`) applies; `manage` must **not** imply the approve-tier permission or vice versa unless the role table grants both. — **Reversibility:** costly — once tenant custom roles contain these strings (D-09), renaming or removing them means migrating role documents.
- **D-06:** Built-in defaults:
  - change level / manage: **Tenant Admin only** (plus Super Admin for any tenant)
  - approve / deny / undo / press stop: **Tenant Admin, Security Analyst, Incident Responder** (plus Super Admin)
  - view the Autonomous Ops screen: the approvers **plus Auditor and Analyst**; not Viewer, not the ITAM roles
- **D-07:** The approve-tier permission **joins `rbac_defaults.ADMIN_TIER_PERMISSIONS`**, so every holder must use MFA (Phase 77 D-14 mechanism). — **Reversibility:** costly — Security Analyst and Incident Responder users are prompted to enrol MFA at their next sign-in; reverting later does not un-enrol anyone.
- **D-08:** **Platform Support** can **read** every tenant's Autonomous Ops activity (cross-tenant, read-only, via the existing platform-staff safe-method path in `backend/catalogue_guards.py`) but can never approve, undo, stop, resume or change a level. Only Super Admin acts across tenants.
- **D-09:** Tenant admins **may put the new permissions into custom roles**, under the Phase 77 rules (grant only what you hold; the approve-tier permission drags MFA along via D-07).
- **D-10:** **API keys** may read activity and **press** a stop, but can **never approve, deny, undo or clear a stop**; those require an interactive, MFA-verified session.

### Stop switch behaviour
- **D-11:** **Press** a tenant stop: anyone holding the approve-tier permission (Tenant Admin, Security Analyst, Incident Responder) and Super Admin for any tenant. **Clear** a tenant stop: only holders of the manage permission (Tenant Admin for their own tenant). The **platform-wide stop**, and any tenant stop a Super Admin pressed, can be cleared **only by a Super Admin**.
- **D-12:** While a stop is on: **undo still works** (it puts things back; a human click counts as its approval), **approving does not** (pending approvals wait until resume), and the gate makes no new decisions. Already-queued autonomous instructions are held back at agent delivery (GATE-06).
- **D-13:** The approval **expiry clock keeps running** during a stop; an approval that expires during a stop is recorded as denied/expired, so nothing stale fires on resume.
- **D-14:** A stop **never clears itself**. Clearing requires a typed reason; pressing may take an optional reason (braking must be fast). Who pressed/cleared and why is recorded in the ledger and the audit chain.
- **D-15:** An active stop shows a **banner across the app** for everyone who can view Autonomous Ops, an Activity entry (who, when, why), and an **on-call alert** (Phase 82 channel; until then the existing in-app notification path).

### Safety limits
- **D-16:** Pending approvals **expire after 24 hours** and then count as denied (`expired`).
- **D-17:** **One automatic decision may touch exactly one host** (the host its finding came from). Anything wider becomes an approval card.
- **D-18:** **Circuit breaker:** **3 consecutive** automatic actions for a tenant that are undone or fail **within 24 hours** drop that tenant to Suggest (the previous level is recorded) and tell on-call. **A person with the manage permission restores it**; it never re-arms itself.
- **D-19:** **Never-touch list:** built-in entries that nobody can remove — the platform server, its own IP addresses and the management network. **Super Admin** can add platform-wide entries; a **tenant admin** (manage permission) can add entries for their own tenant (e.g. domain controllers, gateways).
- **D-20:** **Per-tenant rate limit:** after **20 automatic actions in an hour**, that tenant's new decisions become approval cards until the window rolls over, and on-call is told.

### Claude's Discretion
- Exact permission strings and route shapes (within D-05), ledger collection and field names, the decision `trace` format, state-machine names (research ARCHITECTURE Pattern 3 is a good starting point).
- Rolling 60-minute window vs clock hour for D-20; what counts as "the management network" for D-19 (derive from the backend's own addresses and the agents' configured backend URL) — document the choice.
- How long decision records are kept, as long as it is longer than generic retention (GATE-07); 365 days, matching `audit_ledger`, is the suggested floor.
- Whether the legacy `run_cycle`/`generate_plan`/`execute_plan` code is deleted outright or left unreachable with a test proving it — GATE-05 says "removed"; prefer deletion, after checking the other references (`backend/skill_handlers.py:192` dispatches type `autonomous_remediation`; `backend/agent_capabilities.py:77` maps it; `backend/app_startup.py:642` starts the loop).
- Layout and copy of the read-only Autonomous Ops screen (sidebar group `automation` per research), subject to the Spatial Glass design system and a `/gsd-ui-phase 81` contract if the planner wants one. Copy must pass ACTV-08.
- Test structure (structural "only the gate writes autonomous instructions" test, LLM-import ban over the new package, two-tenant isolation, approval double-click race, stop hold-back at agent poll).
- Whether `hypothesis` (dev-only) is added for property tests of the gate (research D20, non-blocking).

### Folded Todos
- **Fix stale capability-count assertions in `agent-install/omni-agent-rs/tests/integration.rs`** (`.planning/todos/pending/2026-08-17-fix-stale-capability-count-assertions-in-integration-rs.md`). `test_capability_manager_has_15_capabilities` and 6 dependent tests assert an old count of 15; `CapabilityManager::new()` now registers 18–20. `test_heartbeat_payload_top_level_fields` also asserts `platform == "Windows"` and fails on Linux. Fix: derive the expected values from the current registration list in `agent-install/omni-agent-rs/src/capabilities/mod.rs` by running `cargo test --test integration`, and make the platform check OS-aware. Folded so the Rust agent test suite is green before Phase 83 adds new agent actions. Close the todo when done.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope and research
- `.planning/REQUIREMENTS.md` — GATE-01..14, ACTV-01, ACTV-03, ACTV-08 (v4.3 section) and the v4.3 Out of Scope table
- `.planning/ROADMAP.md` — "Phase 81" detail block: goal, success criteria, live-only verification list
- `.planning/research/SUMMARY.md` — synthesis, disagreements and rulings, decisions list D1–D20
- `.planning/research/ARCHITECTURE.md` — gate/registry/ledger patterns (Patterns 1–5, 7), integration points table, multi-tenant and catalogue rules, anti-patterns
- `.planning/research/PITFALLS.md` — pitfalls mapped to "P-Core" (legacy LLM path, enqueue bypass, classification, approval race, stop that only stops new decisions, write-ahead audit, scheduler double-run, tenant-context leak)
- `.planning/research/STACK.md` — no new runtime dependencies; Mongo (not Redis) holds stop/level state with fail-closed cache
- `.planning/PROJECT.md` — "Current Milestone: v4.3 Autonomous Ops" (locked decisions, naming rule)

### Prior phase decisions that constrain this phase
- `.planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-CONTEXT.md` — D-02 custom-role ceiling, D-11 `manage:X ⇒ view:X` closure, D-14 permission-based MFA (`ADMIN_TIER_PERMISSIONS`)
- `.planning/phases/75-permission-resolver-single-source-of-truth/75-CONTEXT.md` — single permission resolver, role table, D-20 assignment ceiling
- `backend/migrations/023_hadr_platform_only.py` — precedent for a platform-only screen/route/permission

### Code the phase changes or must respect
- `backend/autonomous_remediation_service.py` — `run_cycle` (~961), `generate_plan` (~387), `execute_plan` (~468), `remediate` (~548), `approve_remediation` (~611), `AUTONOMOUS_REMEDIATION_DRY_RUN` (line 20)
- `backend/app_background_tasks.py` — `autonomous_remediation_loop` (tenant-token leak: only the last token is reset), `monitor_agent_status` (sleeps 3600 s after the first pass)
- `backend/app_startup.py:642` — starts the legacy loop
- `backend/backend_safety.py` — conflicting action classification and the 0.90 confidence threshold
- `backend/remediation_playbook_service.py` + `backend/playbooks/*.yaml` — `ACTION_MAP`, per-step `destructive` flags (all `destructive: true` incl. `block_ip`)
- `backend/response_orchestrator.py` — `is_duplicate_task` (reads `response_tasks`, cross-agent query lacks a `tenantId` filter)
- `backend/deployment_result_endpoints.py:get_agent_instructions` and `backend/agent_tasks_endpoints.py:get_agent_instructions` — the two agent poll paths where the stop hold-back goes, next to `agent_capabilities.hold_back`
- `backend/agent_capabilities.py` — `_INSTRUCTIONS` mapping, `hold_back`, fail-closed `allowed_for`
- `backend/audit_ledger.py` — hash-chained `event()`; `backend/retention_service.py` deletes `audit_logs` after 90 days (decision records must not live there)
- `backend/distributed_lock.py`, `backend/scheduler.py` — lock idiom (no renewal today)
- `backend/tenant_context.py`, `backend/database.py` — tenant ContextVar and the wrapper that does not stamp `tenantId` under `platform-admin`
- `backend/rbac_defaults.py` — role table, `PLATFORM_ONLY_PERMISSIONS`, `ADMIN_TIER_PERMISSIONS`; `backend/permission_vocabulary.py`; `backend/catalogue_guards.py`; `backend/catalogue_mounts*.py`
- `shared/catalogue-access.json`, `shared/tenant-feature-switches.json` — new screen entry and tenant switch (drift tests: `test_catalogue_manifest`, `test_catalogue_route_parity`, slice tests)
- `backend/tenant_features.py` — `START_FEATURES` (new tenants Overview-only)
- `backend/ueba_service.py:121` — the one existing caller of `remediate()`; becomes gated automatically
- `backend/remediation_control_endpoints.py` — existing approve/deny routes used by the Native Security console (keep working)
- `backend/notification_service.py` — in-app notifications for the D-15/D-18/D-20 alerts until Phase 82
- `agent-install/omni-agent-rs/tests/integration.rs`, `agent-install/omni-agent-rs/src/capabilities/mod.rs` — folded todo

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `AutonomousRemediationService.remediate()`: the deterministic playbook path (no LLM) to route through the gate; its approve/deny, lease (`remediation_inflight`, max 2 per agent) and rollback-on-verify-fail logic stay.
- `audit_ledger.event()`: hash-chained, never raises, spools on failure — the immutable mirror for every ledger transition.
- `agent_capabilities.hold_back` in both agent poll endpoints: the existing pattern for refusing instructions at delivery; the stop hold-back sits beside it.
- `distributed_lock.acquire_lock` + `scheduler.py` idiom: single-runner sweeps (needs renewal added).
- Phase 77 role editor, closure and MFA machinery (`rbac_defaults.ADMIN_TIER_PERMISSIONS`, `requires_mfa`): new permissions plug in without new auth code.
- HA/DR platform-only screen (migration 023): template for the platform-wide stop route and permission.
- Spec C6 tenant feature switches and catalogue manifest: eligibility (screen tick) and route registration come for free once the entries exist.

### Established Patterns
- Every route is registered in `shared/catalogue-access.json` and mounted through a `catalogue_mounts_*.py` slice; drift tests fail otherwise.
- Background sweeps run as `platform-admin` and must set `tenantId` explicitly on every write and reset tenant context per iteration (Phase 59 warranty-sweep bug; SEC-03 leak class).
- Fail closed: unknown permission, unknown action, unreadable setting → deny/Suggest.
- Migrations are numbered scripts in `backend/migrations/`; next free number is 024.
- Live deploys are the user's step: the backend runs from the git checkout and needs a restart; the UI is published separately (see project memory on deploy steps).

### Integration Points
- New package (research suggestion): `backend/autonomous_ops/` (`settings.py`, `registry.py`, `gate.py`, `ledger.py`, `reconciler.py`), router `backend/autonomous_ops_endpoints.py`, `backend/migrations/024_autonomous_ops.py`, frontend `components/AutonomousOpsActivity.tsx` plus the app-wide stop banner in the shell.
- `app_startup.run_startup_services`: replace the legacy loop registration; the new security sweep itself arrives in Phase 83.
- `monitor_agent_status` cadence fix lives in `backend/app_background_tasks.py`.

</code_context>

<specifics>
## Specific Ideas

- The user asked for "artificial super intelligence" and an unattended mode; the agreed scope is rule-based Autonomous Ops with human approval for destructive actions. Nothing in code, UI copy, docs or the client deck may describe it as ASI, AGI, "Autopilot" or "fully autonomous" (ACTV-08 enforces this for Autonomous Ops screens/docs).
- Model the levels and the Pending/History split on Microsoft Defender's automation levels (research FEATURES.md), with fixed rules instead of ML verdicts.
- Braking is easy, resuming is deliberate (D-11, D-14).

</specifics>

<deferred>
## Deferred Ideas

None raised during discussion beyond the milestone's own later phases (approve/deny/undo buttons → Phase 83; on-call channel → Phase 82; digest/stats/export → Phase 86).

</deferred>

---

*Phase: 81-autonomy-gate-stop-switch-activity-ledger*
*Context gathered: 2026-10-25*
