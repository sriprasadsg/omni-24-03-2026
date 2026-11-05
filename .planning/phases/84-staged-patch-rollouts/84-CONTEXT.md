# Phase 84: Staged Patch Rollouts - Context

**Gathered:** 2026-11-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 84 lets an operator roll patches out in rings instead of to every host at once:

- rings built from the tenant's agent groups, a canary ring first, then larger rings
- a soak period and a real health gate between rings (install result, post-install inventory, a fresh heartbeat from the new boot, key services); missing data halts
- a failure-rate gate with a minimum sample size
- a halt on failure that reverts the failed ring where the operating system supports it, worded "halts on failure; reverts where supported"
- installs and reboots only inside the tenant's maintenance window
- automatic installs only in the canary ring and only for reversible patches; every other install and every reboot waits for one approval per ring
- the platform's own host never patched, one active rollout per host, patch instructions that expire

Requirements: PTCH-01..07 (7). Depends on Phase 81 (gate, ledger, stop freezes rollouts) and Phase 83 (undo, dedupe, card conventions, `reboot_host`). Independent of Phases 82 and 85. Tenants stay in shadow until a Super Admin lifts them (Phase 81 D-02, D-03), so rollouts record "would have done" entries until then.

Not in this phase: a known-bad patch list shared across tenants (AOPS-F4, deferred), digest/statistics/export (Phase 86), the platform proposing or starting rollouts itself (D-11). Naming rule: "Autonomous Ops", never "ASI", "Autopilot", "fully autonomous" or an unqualified "rollback" (ACTV-08).

</domain>

<decisions>
## Implementation Decisions

### Carried forward, not re-decided
- **Platform host (research D12):** the Platform tenant is never eligible (Phase 81 D-04) and the platform server, its IPs and the management network are on the built-in never-touch list (Phase 81 D-19). A rollout never patches them. Live today has one agent, on the Platform tenant, so nothing on live can join a rollout until a non-platform tenant enrolls a host.
- **Wording (research D13):** "halts on failure; reverts where supported", never an unqualified "rollback" (PTCH-04, ACTV-08).
- Phase 81 limits apply unchanged: approvals expire after 24 h and count as denied (D-16), approve-tier permission with MFA (D-05, D-07), API keys never approve (D-10), stop freezes rollouts and pending approvals (GATE-06, D-12), undo works during a stop (D-12), breaker (D-18), 20 automatic actions per hour (D-20), one automatic decision touches one host (D-17).
- Phase 83 conventions apply: one card holds several lines, each with its own Approve and Deny, no approve-all (D-17); Rust agent only (D-19); Windows and Linux only (D-20); reboot rides the `patch_installer` capability tick (D-21); a vulnerability becomes a suggestion that links to patching (D-07).

### Maintenance window (PTCH-05, research D11)
- **D-01:** The window is a **recurring per-tenant maintenance window**, not a Change Management change per rollout. The existing Settings windows (`maintenance_service.py`, `MaintenanceWindowConfig.tsx`) are fixed and reused: they gain a time zone and windows that run past midnight, and they are **shown in Change Management** so PTCH-05's "recorded in Change Management" holds. Each ring installs in the next open window, which suits rings that soak for days.
- **D-02:** **One time zone per tenant** (an IANA name such as `Asia/Kolkata`); all of that tenant's windows use it, and daylight-saving changes are handled. Today's windows are UTC only.
- **D-03:** A tenant with **no window cannot start a rollout**. Start is disabled with "Add a maintenance window first" and a link to where windows are set. Nothing waits indefinitely and nothing installs outside a window.
- **D-04:** **Patch instructions expire when their window closes** (this is PTCH-07's "patch instructions expire"). Installs already running finish. A host that was offline installs nothing late; the ring picks it up in the next window. — **Reversibility:** costly — if the agent is made to honour the expiry itself (not only the backend at delivery), the contract ships in a published agent binary and changing it needs a new agent release.

### What runs without a click (PTCH-06, research D10)
- **D-05:** A patch is **reversible**, and so may install automatically in the canary ring, when it is either:
  - a **Linux package** whose currently installed version the package source still offers, checked just before install, so a downgrade is really possible; or
  - a **Windows KB that Windows marks uninstallable on that host** (WUA `IsUninstallable`), checked on the host before install.

  Everything else waits for approval. This is broader than the research default (Linux only); the user accepted that Windows' flag is not always reliable before install. — **Reversibility:** costly — the Windows check runs inside the agent, so it ships in a published agent binary.
- **D-06:** Linux packages that take effect only after a reboot (kernel, glibc, systemd and similar) **count as not reversible** and wait for the ring's approval.
- **D-07:** A ring that needs approval gets **one card with an Install line and a Reboot line, each with its own Approve and Deny** (Phase 83 D-17 shape). The Reboot line appears only after installs finish, and only lists hosts that actually need a reboot.
- **D-08:** An approved reboot runs **at once if a window is open, otherwise when the next window opens**, with the agent's longest warning: **5 minutes** (`delay_seconds` 300, the `host_power.rs` maximum) and a message such as "Restarting in 5 minutes for updates".

### Rings and starting a rollout (PTCH-01, PTCH-03, PTCH-07)
- **D-09:** **Rings are built from the tenant's existing agent groups** (`agent_group_endpoints.py`): each ring is one or more groups, set once per tenant and reused by every rollout. Hosts in no ring's group join the last ring.
- **D-10:** Defaults, editable per tenant:
  - every ring soaks **24 h** after its last install or reboot;
  - **any canary failure halts**;
  - later rings halt when **more than 10%** of hosts fail, counted once **at least 10 hosts** have reported; below 10 hosts, any failure halts.
- **D-11:** **Only an operator starts a rollout.** They pick patches from the pending-updates list and press Start. The "patch this" link on a Phase 83 vulnerability suggestion opens a draft rollout already filled in. The platform never creates or starts a rollout by itself.
- **D-12:** A rollout whose patches cover an operating system that the canary ring has no host for **cannot start**. The message names the gap, e.g. "The canary ring has no Linux host; add one to the Canary group". Every operating system is tried on a canary first.
- **D-13:** Hosts already in another active rollout are **left out of the new one and listed**, e.g. '3 hosts are in "November security" and were left out'. A host is never in two active rollouts.

### Halt and revert (PTCH-02, PTCH-03, PTCH-04)
- **D-14:** When a ring fails, **every host in that ring that installed the patch is reverted where supported**, healthy-looking ones included. Earlier rings keep the patch because they passed their soak. Nothing further installs.
- **D-15:** **The revert runs on its own**, at once, as an undo: even outside the window and during a stop, matching Phase 81 D-12's "undo works during a stop". If uninstalling needs a restart, a Reboot line is added to that ring's card for approval (D-07). Where the operating system can't revert, the row says so instead of claiming a revert.
- **D-16:** After a halt the operator can **Resume or Cancel**, nothing else:
  - **Resume** needs the manage permission and a typed reason. It re-runs the failed ring's health gate and continues only if it is green.
  - **Cancel** ends the rollout; hosts already patched keep their patches.
  - There is no "skip failed hosts".
- **D-17:** After an approved reboot, a host with **no fresh heartbeat from the new boot within 30 minutes** counts as missing data and halts the ring.
- **D-18:** A host that stays **offline for the whole ring and never installs** is not a failure. It is shown as **"not reached"**, the ring is judged on the hosts that did install, and the host gets the patch when it comes back online in a later window. In the canary ring, at least one host per operating system in the rollout must actually install before the canary can pass.

### Claude's Discretion
- **Which services the health gate checks.** Lean: the tenant's Phase 83 watched-services list (D-10 there) for that host plus the agent's own service. An empty watched list means only the agent's service is checked, and that does not count as missing data. Research confirms.
- **How long a rollout stays active** while "not reached" hosts are outstanding (D-18), and how it reports them when it completes.
- **How the revert-during-stop of D-15 meets the delivery hold-back** (`autonomous_ops/delivery.py` `hold_back_autonomous`). Revert instructions must pass the hold-back; installs, ring advances and reboots must not.
- **How canary auto-installs fit Phase 81 limits:** one decision per host (D-17), the 20-per-hour rate limit (D-20, a canary larger than 20 hosts would hit it), and whether a reverted canary counts toward the 3-in-24-h breaker (D-18 there).
- **How the old `staged_deployments` / `rollback_jobs` service** (`deployment_service.py`, fixed TEST/DEV/STAGING/PRODUCTION stages, 0 rows on live, a rollback that queues instructions without tenant, expiry or gate) is retired or fenced. Research suggests building the ring controller over `new_patch_job` / `patch_instruction` and extracting the revert into a gated service function.
- **Monthly window recurrence** stays unsupported unless it is cheap. Daily, weekly and one-off windows are required.
- **Where the rollout screen lives** and its layout and copy: settle in a `/gsd-ui-phase 84` contract under the Spatial Glass design system and ACTV-08.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope and requirements
- `.planning/ROADMAP.md` § "Phase 84: Staged Patch Rollouts": goal, 5 success criteria, research flags, live-only verification list.
- `.planning/REQUIREMENTS.md` §3 "Staged Patching": PTCH-01..07; ACTV-08 (banned wording); AOPS-F4 (deferred known-bad patch list).

### Research
- `.planning/research/SUMMARY.md`: decision table rows D10–D13; "Phase 84: Staged patching with halt and revert" delivers list; "Patch install auto?" conflict row.
- `.planning/research/PITFALLS.md`: Pitfall 9 (patch "rollback" that is not a rollback), 10 (stale health signals), 11 (patcher patches the platform; orchestrator not resumable), 12 (staging mechanics on real tenants), 19 (stop only stops new decisions).
- `.planning/research/ARCHITECTURE.md`: `patch_rollout` ring controller over `new_patch_job` / `patch_instruction` / `trigger_rollback`.

### Earlier decisions this phase builds on
- `.planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-CONTEXT.md`: gate, stop, limits, permissions, never-touch list, shadow (D-01..D-25).
- `.planning/phases/83-autonomous-security-response/83-CONTEXT.md`: card shape (D-17), Rust-only and OS scope (D-19, D-20), capability ticks (D-21), vulnerability suggestion → patching (D-07), watched services (D-10).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/patch_core_endpoints.py`: `installable_patch_id`, `new_patch_job`, `patch_instruction`, `POST /api/patches/deploy`, `POST /api/patches/deployment-jobs/{id}/rollback`. This is the real patch path (fixed 2026-10-12; before that, OS patching was fake end to end).
- `backend/deployment_result_endpoints.py`: per-agent results and `clear_installed_from_pending`, a source for the gate's install-result and inventory signals.
- `agent-install/omni-agent-rs/src/capabilities/patch_installer.rs`: `install_patches` / `rollback_patches`. Windows installs and uninstalls through WUA, and refuses an uninstall Windows marks not uninstallable. Linux upgrades only installed packages and downgrades to the version the agent recorded before upgrading (refuses otherwise).
- `agent-install/omni-agent-rs/src/capabilities/host_power.rs`: `reboot_host` with a 30–300 s delay and a reason text; ships in agent 2.1.16 (built, **not yet published**; the server still offers 2.1.14).
- `backend/autonomous_ops/`: `gate.py`, `registry.py` (`reboot_host` and `upgrade_software` are approve-class; `install_patches` / `rollback_patches` are not registered yet), `approvals.py`, `delivery.py` (`hold_back_autonomous`), `ledger.py`, `reconciler.py`, `stop.py`, `protected.py`.
- `backend/agent_capabilities.py`: `install_patches`, `rollback_patches` and `reboot_host` already map to the `patch_installer` tick.
- `backend/maintenance_service.py` + `maintenance_endpoints.py` + `components/MaintenanceWindowConfig.tsx` (in Settings): recurring windows (none, daily or weekly), UTC only, no zone. A window crossing midnight never matches. 0 rows on live.
- `backend/change_management_service.py` + `components/ChangeManagementDashboard.tsx`: changes with CAB vote and scheduled start and end. 0 rows on live; D-01 only shows the windows there.
- `backend/agent_group_endpoints.py`: tenant agent groups and members, the ring source (D-09).

### Established Patterns
- Every route is registered in `shared/catalogue-access.json` and mounted through a `catalogue_mounts_*.py` slice; drift tests fail otherwise.
- Background loops set `tenantId` explicitly, reset tenant context per iteration and take a renewable distributed lock (Phase 82 retention pattern).
- Fail closed: an unknown action, missing capability, missing health data or missing window means deny or halt.
- A patch result's agent message can say "not supported"; that fails the job (2026-10-12 rule).

### Integration Points
- The heartbeat needs a boot identity (boot id or boot time) for "fresh heartbeat from the new boot" (D-17); research checks what agents send today.
- A rollout state machine that survives a backend restart, resuming from stored state.
- The gate and approvals registry, for the canary auto-install decisions, Install and Reboot lines and revert children.
- The patch screen's pending-updates list, for starting a rollout (D-11); the Phase 83 vulnerability suggestion link, for the pre-filled draft.

</code_context>

<specifics>
## Specific Ideas

- Messages the user accepted (exact copy is the UI-SPEC's call):
  - "Add a maintenance window first"
  - "The canary ring has no Linux host; add one to the Canary group"
  - '3 hosts are in "November security" and were left out'
  - "Restarting in 5 minutes for updates"
  - "not reached"
- Live-only checks from the roadmap stay the user's:
  - a canary install plus reboot on a disposable host;
  - a revert on a supported OS;
  - the post-reboot heartbeat feeding the gate;
  - window enforcement;
  - the per-ring reboot approval click.

  All of them need a non-platform tenant with an enrolled Rust agent on 2.1.16 or later.

</specifics>

<deferred>
## Deferred Ideas

- The platform drafting a weekly rollout from pending updates, or starting reversible-only rollouts itself: offered and declined for this phase (D-11). Could be a later phase.
- Each rollout linked to a CAB-approved Change Management change: offered and declined in favour of recurring windows (D-01).
- Known-bad patch list shared across tenants: AOPS-F4, already deferred.

</deferred>

---

*Phase: 84-staged-patch-rollouts*
