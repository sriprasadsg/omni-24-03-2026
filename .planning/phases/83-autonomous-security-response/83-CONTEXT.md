# Phase 83: Autonomous Security Response - Context

**Gathered:** 2026-10-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 83 builds the first code that acts on its own. A security sweep replaces the legacy remediation loop and turns findings into gated actions:

- undoable containment that runs by itself at Undoable-auto: block a single IP address for a set time, quarantine a malicious file, restart a failed watched service within a budget
- approval cards for destructive actions (kill process, isolate host), one card per incident
- a check for every action against its own evidence, deduplication, and a 24-hour no-redo after an operator undoes something
- approve, deny and undo on the Autonomous Ops screen (ACTV-02), plus a small settings panel
- the Rust agent actions all of this needs, including the new reporting of failed services
- fences around the swarm and SOAR containment paths

Requirements: RESP-01..11, ACTV-02 (12). Depends on Phase 81. Independent of Phases 82 and 85. Tenants stay in shadow until a Super Admin lifts them (Phase 81 D-02, D-03), so this phase records "would have done" entries until then.

Staged patch rollouts are Phase 84. Digest, statistics and export are Phase 86. Naming rule: "Autonomous Ops", never "ASI", "Autopilot" or "fully autonomous" (ACTV-08).

</domain>

<decisions>
## Implementation Decisions

### Carried forward, not re-decided
- Classes (GATE-04, Phase 81): block IP, quarantine file and restart service are automatic; isolate, kill process and reboot need approval. Playbook YAML may raise a class, never lower it.
- Phase 81 limits apply unchanged: approvals expire after 24 h (D-16), one automatic decision touches one host (D-17), breaker at 3 in 24 h with manual restore (D-18), never-touch list (D-19), 20 automatic actions per hour (D-20), the approve-tier and manage permissions (D-05, D-06), MFA (D-07), undo works during a stop and approve does not (D-12), Platform tenant never eligible (D-04).
- Level, maximum level and the never-touch list stay API-only (Phase 81 D-22). D-21 below adds a panel for this phase's three new settings only.

### Two-signal rule (RESP-08)
- **D-01:** A second signal means a **different origin**. Origins are: the native agent verdict, each public feed in `edr_ioc` by `source_feed` (URLhaus, MalwareBazaar, OTX), VirusTotal, and an on-host detection on that host that names the same indicator (EDR, deception, UEBA). Two entries from one origin never count. Any two different origins satisfy the rule, so it can fire without paid or keyed feeds. If the agent bundle is ever built from a public feed, those two are one origin.
- **D-02:** The rule applies to **block IP and quarantine file**. Restart service is exempt: a failed service is something the agent observed directly, and the restart budget limits it instead.
- **D-03:** One signal becomes a suggestion. If a second origin arrives **within 24 hours** of the first, the suggestion turns into the automatic action through the gate. After 24 hours it stays a suggestion.
- **D-04:** The rule is **on by default and can be switched off**. A tenant admin (manage permission) may turn it off for their own tenant; a Super Admin may do so for any tenant or for all tenants. With it off, one signal acts. Every change is recorded in the ledger and the audit chain. This loosens RESP-08's "only when two signals agree", and RESP-08 and Phase 83 success criterion 1 now say "by default". Every other limit still applies with the rule off. New tenants start with it on.

### Finding outcomes (RESP-01)
- **D-05:** A malicious file with two origins is **quarantined**, replacing today's routing of a non-IP scan finding to `kill_process` in `select_playbook`. Moved, never deleted (RESP-03).
- **D-06:** If quarantine fails because the file is running or locked, it becomes **one approval card on the same incident**: approving kills the process and retries the quarantine. Nothing is killed without a person.
- **D-07:** A vulnerability becomes a **suggestion only**, linking to patching. No approval card and no patching here, because rollouts belong to Phase 84 and a host can report hundreds. This covers both vuln routes in `select_playbook` (with a CVE and without).
- **D-08:** A file-integrity change becomes a **suggestion only**. If the file's hash is also flagged malicious it takes the normal two-signal quarantine path, and the change itself is not an origin under D-01 because it shows a change, not malice. The current `fim → restore_file` route leaves the sweep: the agent refuses to restore without `backup_path`, and nothing in the backend ever sets one, so every card would fail.
- **D-09 (research D6):** `restore_file`, `disable_service` and `rotate_key` **stay approval-only**, as the Phase 81 registry already has them.

### Timers and budgets
- **D-10:** A tenant names the **services to watch** (manage permission). The list starts empty and nothing restarts until a tenant fills it. Agents do not report service failures today, so this phase adds that reporting for listed services only. A service an admin stopped on purpose must not count as failed.
- **D-11:** Restart budget: **3 per service per host per rolling hour**, with growing waits between tries, then one approval card for further restarts. Same limit as the platform watchdog (Phase 82).
- **D-12 (research D5):** Restart service runs automatically with **no Undo button**; a restart has no inverse. The row shows what restarted and the result.
- **D-13:** Block length: **default 24 h, range 1 hour to 7 days**. A tenant admin sets it for their tenant; a Super Admin for any or all. The length travels with the instruction so the agent can remove the block at expiry while offline (RESP-02). — **Reversibility:** costly — the expiry contract ships inside a published agent binary, and changing it later needs a new agent release and rollout.
- **D-14:** When a block expires and the address is still flagged, it is a **new decision through the gate**, never an automatic extension. It needs two origins again, and evidence older than the expired block's start does not count, so stale evidence cannot keep an address blocked. Expiry is not an undo, so RESP-07's 24-hour no-redo does not apply to it.
- **D-15:** An isolated host reverts after **4 hours** unless an operator confirms. Confirming (approve-tier permission) keeps it isolated until a person restores it. The management connection always stays open (RESP-05).
- **D-16:** **Incident** (RESP-09) = alerts on the same host until **1 hour passes with nothing new**. A long attack stays one card; a quiet host starts a fresh one.
- **D-17:** One card holds several actions, each with **its own Approve and Deny**, so each destructive action gets its own recorded single-use decision through the existing approve route. No approve-all.

### Fences and agent support
- **D-18 (research D8):** Fence, do not migrate or delete. No automatic trigger can start containment on swarm `propagate-antibody` or the SOAR local block and isolate actions, and a test keeps it that way. These paths stop reporting success: they answer that nothing was sent and point to Autonomous Ops, and SOAR stops setting `agents.isolated` for a host that received nothing. Re-checked 2026-10-31: `db.instructions` has 5 writers (`swarm_service.py`, `soar_engine.py` twice, `tasks.py` twice) and no readers.
- **D-19:** New actions are **Rust agent only**. Installers build only the Rust agent and `agent-install/agent` was last committed in July. Any other agent never reports support, so its rules stay dormant (RESP-10).
- **D-20:** **Windows and Linux.** Other platforms report no support and stay dormant.
- **D-21:** Keep the capability ticks Phase 81 mapped: `remediation_executor` for block, quarantine, restart and isolate, `patch_installer` for reboot. No new per-action ticks, so tenants with those ticked change nothing.

### Settings
- **D-22:** A small **settings panel on the Autonomous Ops screen** holds the two-signal switch, the block length and the watched services, for holders of the manage permission. Without it restart would stay dormant for most tenants.

### Claude's Discretion
- The exact origin table for D-01, as long as no pair shares an origin, and how an on-host detection is tied to an indicator.
- "For all tenants" in D-04 and D-13 is read as a bulk write to each tenant's own setting, not a separate platform layer, so a tenant admin can change it back and there is only one value to read. Revisit only if research finds a reason.
- Isolation's 4 hours (D-15) is a fixed default with no panel setting.
- Backoff intervals for D-11, the quarantine location and format, and how long quarantined files are kept. Files are never deleted automatically in this phase without a decision being recorded.
- Which capability carries the new service-failure reporting.
- How suggestions are shown so vulnerability volume does not bury cards (D-07); settle in the UI-SPEC.
- Layout and copy of the cards, row actions and panel, subject to the Spatial Glass design system, a `/gsd-ui-phase 83` contract and ACTV-08.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope and research
- `.planning/REQUIREMENTS.md` — RESP-01..11, ACTV-02 (RESP-08 amended by D-04) and the v4.3 Out of Scope table
- `.planning/ROADMAP.md` — "Phase 83" block: goal, success criteria, research note, live-only verification list
- `.planning/research/SUMMARY.md` — rulings on `restart_service` and on propagate-antibody/SOAR, decisions D5-D9, Phase 83 delivery list
- `.planning/research/PITFALLS.md` — Pitfall 7 and the blast-radius sections: agent-side time limits, dead-man revert, keeping the platform allow rule during isolation
- `.planning/research/FEATURES.md` — containment expiry, corroboration, incident grouping, restart budget
- `.planning/research/ARCHITECTURE.md` — gate, registry and ledger patterns, integration points
- `.planning/research/STACK.md` — no new runtime dependencies

### Prior phase decisions that constrain this phase
- `.planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-CONTEXT.md` — D-01..D-25, the gate this phase is the first caller of
- `.planning/phases/82-platform-self-healing-scheduled-retention/82-CONTEXT.md` — restart budget precedent, on-call channel
- `.planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-04-SUMMARY.md` and `81-10-SUMMARY.md` — dispatcher registration and what 83 adds to the screen

### Code the phase changes or must respect
- `backend/autonomous_ops/registry.py` — action table; `restart_service` has no undo, and `quarantine_file`, `isolate_host` and `reboot_host` are registered but the Rust agent lacks them
- `backend/autonomous_ops/gate.py`, `approvals.py`, `ledger.py`, `reconciler.py`, `dispatch_check.py`, `delivery.py`, `protected.py` — decision, approval, undo and delivery paths
- `backend/autonomous_ops_endpoints.py` — approve, deny and undo routes already exist
- `backend/autonomous_remediation_service.py` — `remediate()`, the deterministic path; `backend/remediation_playbook_service.py` — `select_playbook` routing to change (D-05, D-07, D-08)
- `backend/playbooks/*.yaml` — no `quarantine_file` or `restart_service` playbook exists; `kill_process.yaml` is today's route for malicious files
- `backend/agent_capabilities.py` — instruction-to-capability map (D-21); `shared/agent-capabilities.json`
- `backend/agent_security_scan_endpoints.py` — writes `security_scan_results` and `security_alerts` with `source: native`
- `backend/threat_feed_sync.py` — fills `edr_ioc` every 6 h; `backend/agent_security_feed_service.py` — the agent's signed bundle, seed data only
- `backend/swarm_service.py`, `backend/soar_engine.py`, `backend/soar_connectors_security.py`, `backend/tasks.py` — fence targets (D-18)
- `agent-install/omni-agent-rs/src/instructions.rs`, `src/capabilities/remediation_actions.rs` — existing block, unblock, kill and restore handlers; the shipped Rust tree (not `agent-rust/`)
- `components/AutonomousOpsActivity.tsx`, `services/autonomousOpsApi.ts` — the screen this phase extends
- `shared/catalogue-access.json` — route registration and drift tests

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 81 gate, ledger, approvals and undo: the approve, deny and undo routes exist, only the buttons do not.
- `approvals.register_dispatcher`: where the sweep's dispatchers plug in.
- `autonomous_ops/delivery.py` and the agent poll hold-back: stop enforcement already applies to new instructions.
- `edr_ioc`: a live second origin for hashes and URLs with no key.
- The Phase 82 retention job's distributed-lock pattern with renewal, for the sweep's single runner and any expiry sweeper.

### Established Patterns
- Every route is registered in `shared/catalogue-access.json` and mounted through a `catalogue_mounts_*.py` slice; drift tests fail otherwise.
- Background sweeps set `tenantId` explicitly and reset tenant context per iteration.
- Fail closed: an unknown action, setting or missing capability means deny or dormant.
- The real app adds a permission guard the tests' bare router lacks, so route tests alone do not prove the guard.

### Integration Points
- `run_startup_services` in `backend/app_startup.py` — start the sweep.
- Agent config pull — carries the watched-service list to agents.
- Heartbeat or a new endpoint — carries service failures and action support back.

</code_context>

<specifics>
## Specific Ideas

- Facts found while scouting that research must plan around, not rediscover:
  - The bundled agent feed is seed data only: the EICAR test hash and sample IP ranges. Real signatures do not reach agents.
  - IP entries in `edr_ioc` come only from OTX, which needs a key, and VirusTotal has no key on this VM. An IP's second origin here will usually be an on-host detection, or an IP-hosted URL in URLhaus if research finds that usable.
  - Agent scans run only when an instruction asks for them; research must find what produces findings on a schedule.
  - The Rust `block_ip` has no time limit. `quarantine_file`, `unquarantine_file`, `restart_service`, `isolate_host`, `restore_host` and `reboot_host` do not exist in the agent. SOAR's `network_isolate` is a name no agent knows.
  - `soar_connectors_security.py` can call real external firewalls. Research must confirm no automatic trigger reaches them; human-started runs keep working (Phase 81 D-21).
  - `backend/tasks.py` also writes the dead `db.instructions` queue and is not named in RESP-11; check it during fencing.
- Live checks stay the user's (research D9): publish and roll out the new agent, firewall round-trip on real Linux and Windows (EILT0197 with Defender), a block expiring while offline, quarantine and restore, isolate with the management connection open and the automatic revert, service restart.

</specifics>

<deferred>
## Deferred Ideas

- **Feed real signatures to agents:** build the agent bundle from the public feeds in `edr_ioc`. Without this, native verdicts rarely fire on real threats, so automatic file and IP actions will be uncommon after this phase. A new capability; a roadmap candidate. Under D-01 the bundle and those feeds would then be one origin.
- **Keep file content for real restores:** the FIM baseline stores hashes only. A real restore needs the agent to keep known-good copies. A new capability.
- **Screens for level, maximum level and never-touch:** stay API-only under Phase 81 D-22.

</deferred>

---

*Phase: 83-autonomous-security-response*
*Context gathered: 2026-10-31*
