# Phase 84: Staged Patch Rollouts - Research

**Researched:** 2026-11-05
**Domain:** Ring-based patch rollout controller over the Autonomous Ops gate, Python/FastAPI/MongoDB backend plus Rust endpoint agent (Windows Update Agent, apt/dnf/yum), React UI
**Confidence:** HIGH on how the existing code behaves (every claim below was read this session, with file and line); MEDIUM on per-OS reversibility in the field (no live host was available); LOW on a few agent-side behaviours flagged `[ASSUMED]`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Carried forward, not re-decided**
- **Platform host (research D12):** the Platform tenant is never eligible (Phase 81 D-04) and the platform server, its IPs and the management network are on the built-in never-touch list (Phase 81 D-19). A rollout never patches them. Live today has one agent, on the Platform tenant, so nothing on live can join a rollout until a non-platform tenant enrolls a host.
- **Wording (research D13):** "halts on failure; reverts where supported", never an unqualified "rollback" (PTCH-04, ACTV-08).
- Phase 81 limits apply unchanged: approvals expire after 24 h and count as denied (D-16), approve-tier permission with MFA (D-05, D-07), API keys never approve (D-10), stop freezes rollouts and pending approvals (GATE-06, D-12), undo works during a stop (D-12), breaker (D-18), 20 automatic actions per hour (D-20), one automatic decision touches one host (D-17).
- Phase 83 conventions apply: one card holds several lines, each with its own Approve and Deny, no approve-all (D-17); Rust agent only (D-19); Windows and Linux only (D-20); reboot rides the `patch_installer` capability tick (D-21); a vulnerability becomes a suggestion that links to patching (D-07).

**Maintenance window (PTCH-05, research D11)**
- **D-01:** The window is a **recurring per-tenant maintenance window**, not a Change Management change per rollout. The existing Settings windows (`maintenance_service.py`, `MaintenanceWindowConfig.tsx`) are fixed and reused: they gain a time zone and windows that run past midnight, and they are **shown in Change Management** so PTCH-05's "recorded in Change Management" holds. Each ring installs in the next open window, which suits rings that soak for days.
- **D-02:** **One time zone per tenant** (an IANA name such as `Asia/Kolkata`); all of that tenant's windows use it, and daylight-saving changes are handled. Today's windows are UTC only.
- **D-03:** A tenant with **no window cannot start a rollout**. Start is disabled with "Add a maintenance window first" and a link to where windows are set. Nothing waits indefinitely and nothing installs outside a window.
- **D-04:** **Patch instructions expire when their window closes** (this is PTCH-07's "patch instructions expire"). Installs already running finish. A host that was offline installs nothing late; the ring picks it up in the next window. — **Reversibility:** costly — if the agent is made to honour the expiry itself (not only the backend at delivery), the contract ships in a published agent binary and changing it needs a new agent release.

**What runs without a click (PTCH-06, research D10)**
- **D-05:** A patch is **reversible**, and so may install automatically in the canary ring, when it is either:
  - a **Linux package** whose currently installed version the package source still offers, checked just before install, so a downgrade is really possible; or
  - a **Windows KB that Windows marks uninstallable on that host** (WUA `IsUninstallable`), checked on the host before install.

  Everything else waits for approval. This is broader than the research default (Linux only); the user accepted that Windows' flag is not always reliable before install. — **Reversibility:** costly — the Windows check runs inside the agent, so it ships in a published agent binary.
- **D-06:** Linux packages that take effect only after a reboot (kernel, glibc, systemd and similar) **count as not reversible** and wait for the ring's approval.
- **D-07:** A ring that needs approval gets **one card with an Install line and a Reboot line, each with its own Approve and Deny** (Phase 83 D-17 shape). The Reboot line appears only after installs finish, and only lists hosts that actually need a reboot.
- **D-08:** An approved reboot runs **at once if a window is open, otherwise when the next window opens**, with the agent's longest warning: **5 minutes** (`delay_seconds` 300, the `host_power.rs` maximum) and a message such as "Restarting in 5 minutes for updates".

**Rings and starting a rollout (PTCH-01, PTCH-03, PTCH-07)**
- **D-09:** **Rings are built from the tenant's existing agent groups** (`agent_group_endpoints.py`): each ring is one or more groups, set once per tenant and reused by every rollout. Hosts in no ring's group join the last ring.
- **D-10:** Defaults, editable per tenant:
  - every ring soaks **24 h** after its last install or reboot;
  - **any canary failure halts**;
  - later rings halt when **more than 10%** of hosts fail, counted once **at least 10 hosts** have reported; below 10 hosts, any failure halts.
- **D-11:** **Only an operator starts a rollout.** They pick patches from the pending-updates list and press Start. The "patch this" link on a Phase 83 vulnerability suggestion opens a draft rollout already filled in. The platform never creates or starts a rollout by itself.
- **D-12:** A rollout whose patches cover an operating system that the canary ring has no host for **cannot start**. The message names the gap, e.g. "The canary ring has no Linux host; add one to the Canary group". Every operating system is tried on a canary first.
- **D-13:** Hosts already in another active rollout are **left out of the new one and listed**, e.g. '3 hosts are in "November security" and were left out'. A host is never in two active rollouts.

**Halt and revert (PTCH-02, PTCH-03, PTCH-04)**
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

### Deferred Ideas (OUT OF SCOPE)
- The platform drafting a weekly rollout from pending updates, or starting reversible-only rollouts itself: offered and declined for this phase (D-11). Could be a later phase.
- Each rollout linked to a CAB-approved Change Management change: offered and declined in favour of recurring windows (D-01).
- Known-bad patch list shared across tenants: AOPS-F4, already deferred.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PTCH-01 | Operator defines rollout rings per tenant (canary then larger stages); next ring only after soak and green health gate | Rings built from `agent_groups`/`agent_group_members` (section "Agent groups and busy hosts"); `patch_rollout_settings` + snapshot-at-start data model; tick state machine |
| PTCH-02 | Health gate = install result, post-install inventory, fresh heartbeat after reboot, key services; missing data halts | "Health-gate signals" table with storage, freshness and the four gaps (inventory self-fulfilling, no positive service state, no boot baseline, `ACCEPTED` instruction status) |
| PTCH-03 | Failure-rate gate with minimum sample | Pure function `ring_verdict` (Code Examples); thresholds from rings settings (D-10) |
| PTCH-04 | Halt, and revert where the OS supports it; wording "halts on failure; reverts where supported" | Per-OS reversibility matrix; revert as a gated undo (`approvals.undo` pattern, kind `undo`, stop-exempt); agent change for per-job pre-patch state; copy-gate pitfalls |
| PTCH-05 | Install/advance only inside the maintenance window shown in Change Management | Window model rework (time zone, overnight, validation), `zoneinfo` algorithm (verified run), controller `window_open` check, read endpoints per catalogue view |
| PTCH-06 | Installs auto only in canary and only for reversible classes; everything else and every reboot waits for one approval per stage | Registry additions (`install_patches`, `rollback_patches`), agent-side `require_reversible` pre-check + new token, window-deferred approvals dispatcher, reconciler/hold-back changes |
| PTCH-07 | Platform host never patched, one active rollout per host, instructions expire | `protected.check` already covers platform agents/IPs; unique partial index host claim; `expiresAt` enforced in `delivery.hold_back_autonomous` |
</phase_requirements>

## Summary

The ring controller should be a new package area **inside `backend/autonomous_ops/`** (so it inherits that package's structural tests: no ambient tenant, no LLM, stamp only written by `gate.py`), driven by a locked background loop in the pattern of `sweep.py` and `reconciler.py`. It never writes `agent_instructions` itself: installs, reboots and reverts all go through `gate.decide` / `gate.execute`, because `test_queue_writers_are_grandfathered` fails the build for any new module that inserts into the agent queues [VERIFIED: backend/tests/test_autonomous_ops_structural.py:320-331]. The existing real patch path (`new_patch_job` + `patch_instruction` -> agent poll -> Rust `install_patches`/`rollback_patches` -> `POST /api/deployments/{job_id}/result` -> `record_agent_patch_result`) is genuinely wired end to end and has tests, so the controller reuses the job documents and the result recorder, not the legacy `deployment_service.py`.

The research found **ten places where CONTEXT.md's assumptions meet different code** (listed in "Corrections to carry into planning"). The three that shape the plan most: (1) the Rust agent has **no pre-install reversibility check on either OS** and its Linux revert target is the *oldest* recorded version, not the version before this job, so D-05 and D-14 both need an agent release (2.1.17) with new tokens; (2) an `install_patches` instruction's own status stays `ACCEPTED` forever because the real result goes to the deployments endpoint, so the Phase 81 reconciler would fail every rollout row after 24 h unless it skips the rollout dispatcher and the controller settles rows from the job result; (3) approvals that must wait for a window (D-04, D-08) cannot ride `approvals.approve` unchanged because the reconciler fails an `approved` row that has no delivered instruction after 30 minutes. Boot identity needs **no agent change**: `meta.response_state.boot_time` is already in every 2.1.16 heartbeat.

Until agent 2.1.17 is published and live, every host lacking the new tokens must fail closed: no automatic canary install (it becomes an approval line) and no revert claim (the row says the agent does not support it yet, which is already the UI-SPEC text).

**Primary recommendation:** Build `autonomous_ops/rollout/` (state machine, health gate, window math, revert, dispatcher) over `gate.decide`/`gate.execute`; register `install_patches` (auto, restricted to the rollout dispatcher) and `rollback_patches` (undo-only) in the registry; one per-host `patch_deployment_jobs` document per dispatch; ship agent 2.1.17 (reversibility pre-check, per-job revert state, positive watched-service state, rollout mode) in the same release; fence `deployment_service.py` instead of deleting it.

## Corrections to carry into planning

| # | CONTEXT/assumption | What the code does | Consequence |
|---|---------------------|--------------------|-------------|
| C1 | "`install_patches` / `rollback_patches` are not registered yet" and could be ordinary registry entries | Registry test pins the locked auto split: `AUTO = ("block_ip", "quarantine_file", "restart_service")` [VERIFIED: backend/tests/test_autonomous_ops_registry.py:24] and `ACTION_LABELS ⊇ registry.commands()` [VERIFIED: backend/tests/test_autonomous_ops_gate.py:216] | A fourth auto action is a deliberate GATE-04 change: update the pinned test, add labels and reason texts, restrict the new spec to the rollout dispatcher (Open Question 1) |
| C2 | Windows `IsUninstallable` "checked on the host before install" | Only read in the **uninstall** script: `} elseif (-not $match.IsUninstallable) {` [VERIFIED: patch_installer.rs:186]; the install script never reads it [VERIFIED: patch_installer.rs:124-170] | New agent code before the update is added to the install collection; ships in a published binary (D-05 already says so) |
| C3 | Linux "downgrade to the version the agent recorded before upgrading" is a per-job revert | `state.entry(pkg.clone()).or_insert(before.clone()); // keep the oldest pre-patch version` [VERIFIED: patch_installer.rs:361]; rollback target is `state.get(pkg)` [VERIFIED: patch_installer.rs:382] | A revert of rollout job N can downgrade past job N to an older version. State must be keyed by job id (agent change). Nothing today checks the source still offers the version |
| C4 | Instruction expiry is a delivery matter | `patch_instruction` carries `tenantId` but no expiry field [VERIFIED: patch_core_endpoints.py:131-150]; neither mounted poll checks one [VERIFIED: agent_tasks_endpoints.py:33-75] | Add `expiresAt` to rollout instruction documents and enforce it in `delivery.hold_back_autonomous`, which all three poll sites already call [VERIFIED: test_autonomous_ops_structural.py:430-436] |
| C5 | Controller can lean on the reconciler to settle rows | Agent answers an install with `"status": "accepted"` and posts the real result to the deployments route; the instruction stays `ACCEPTED` [VERIFIED: instructions.rs:537-548 and agent_tasks_endpoints.py:110]. Reconciler: `_SUCCESS` = completed/success/executed/done, so `accepted` is neither success nor failure and ends `no_result` after 24 h [VERIFIED: reconciler.py:165-179]; undelivered rows end `not_delivered` after 30 min [VERIFIED: reconciler.py:165] | The reconciler must skip rows whose `dispatcher` is the rollout dispatcher; the controller settles them from `patch_deployment_jobs.agentResults` |
| C6 | Boot identity "must be added" | `meta["response_state"] = ...response_state_report(...)` in every heartbeat [VERIFIED: heartbeat.rs:541]; it contains `"boot_time": boot_time` from `sysinfo::System::boot_time()` [VERIFIED: isolation.rs:480-488]. Capability stripping only touches keys that are capability ids or in `_DATA_KEYS`, and `response_state` is neither [VERIFIED: agent_capabilities.py:173-185] | No agent change for boot identity; the work is backend baseline-and-compare. Only 2.1.16+ agents carry it (Cargo.toml `version = "2.1.16"`; server still offers 2.1.14) |
| C7 | Settings windows "are fixed and reused" | `create_window` stores the raw request dict with no model or validation [VERIFIED: maintenance_endpoints.py:11-20]; there is no update route [VERIFIED: maintenance_endpoints.py:11-43]; weekly match uses Python `now.weekday()` (Mon=0) against `days_of_week` [VERIFIED: maintenance_service.py:70] while the UI labels Sun=0 [VERIFIED: components/MaintenanceWindowConfig.tsx:90 `['Sun', 'Mon', ...]`]; daily/weekly compare `start_time <= now_time <= end_time` so an overnight window never matches [VERIFIED: maintenance_service.py:66-74] | A weekly window is off by one day today. Rework the stored shape (new fields, ISO weekday numbers), add an update route and a pydantic model. Routes sit under catalogue view `systemHealth` [VERIFIED: shared/catalogue-access.json systemHealth `"routes": ["/api/system", "/api/cache", "/api/maintenance"]`], so a tenant without that screen ticked cannot read them: the Rollouts tab and Change Management need their own read endpoints under their own views |
| C8 | `deployment_service.py` can be retired by deleting it | It is in `GRANDFATHERED_WRITERS`, and the test asserts the literal does not rot: `assert sorted(set(GRANDFATHERED_WRITERS) - writers) == []` [VERIFIED: test_autonomous_ops_structural.py:329-330] | Removing its `agent_instructions.insert_one` (deployment_service.py:427) requires removing `"deployment_service.py"` from that literal in the same plan |
| C9 | Copy gate only bites on "roll back" | Pattern is `\\broll(?:ed|ing)?[ -]?back\\b` with exemption "where supported" [VERIFIED: shared/autonomous-ops-banned-terms.json rules]. The separator is optional, so the bare word `rollback` in a comment or docstring of any listed file fails. `rollback_patches` as an identifier does not match (`_` is a word character, no boundary) | New rollout modules (added to `files`) must say "revert" in prose and comments; keep `rollback_patches` only as a code identifier |
| C10 | Pitfall 10 says agent status can lag an hour | `AGENT_STATUS_POLL_SEC = 30`, `AGENT_OFFLINE_AFTER = timedelta(minutes=5)` [VERIFIED: app_background_tasks.py:14-16] | Fixed already. Still compare `lastSeen` (an ISO string written by the heartbeat) against the baseline rather than trusting `status` alone |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Reversibility check (Windows `IsUninstallable`, Linux source-offers-version) | Endpoint agent (Rust) | API/backend (token gate) | Only the host knows; must be atomic with the install (no probe-then-install gap). Backend refuses to rely on it for agents lacking the token |
| Per-job pre-patch state for revert | Endpoint agent | — | The state is on the host (`patch_state.json`) |
| Ring state machine, soak, window check, host claim | API/backend (locked loop) | Database | Survives restart by reading stored state each tick |
| Auto vs approval decision, stop, shadow, rate and host caps, ledger | API/backend (`gate.decide`) | Database (`autonomy_actions`) | Single choke point (GATE-03) |
| Instruction expiry and stop hold-back | API/backend (`delivery.hold_back_autonomous` at poll) | — | Delivery is the last point an instruction can be stopped; agent-side expiry would need a published binary (D-04) |
| Health-gate verdict | API/backend (pure function over stored heartbeat/job data) | Endpoint agent (supplies signals) | Judgement stays server-side, testable without hosts |
| Maintenance window storage and math | API/backend + Database | Browser (display, `Intl` zone list) | Server is the authority on "inside the window" |
| Approvals, Resume, Cancel | API/backend (interactive session + MFA) | Browser | API keys never approve (D-10) |
| Rollouts tab, approval card, settings screens | Browser | API (flags `canStart` etc.) | Client never derives permissions (UI-SPEC section 12) |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `zoneinfo` | Python 3.12.3 [VERIFIED: `backend/venv/bin/python --version`] | Window math in the tenant's IANA zone, DST-safe | No new dependency; system `/usr/share/zoneinfo` exists on the VM [VERIFIED: `ls /usr/share/zoneinfo`] and the venv also holds `tzdata 2026.4` [VERIFIED: ran `import tzdata`] |
| FastAPI / Motor / PyMongo | 0.141.1 / 3.7.1 / 4.18.2 [VERIFIED: ran import in backend venv] | Routes, async Mongo | Existing stack |
| `autonomous_ops` package (gate, approvals, ledger, delivery, reconciler, protected, settings, stop, breaker) | in repo | Every decision, approval, undo, stop and ledger rule | Reuse mandated by CONTEXT and GATE-03 |
| `distributed_lock.lock_with_renewal` | in repo | Single runner for the controller loop | Same as sweep/reconciler [VERIFIED: sweep.py:121-127] |
| Rust agent (`agent-install/omni-agent-rs`) | 2.1.16 built, 2.1.17 needed | Reversibility check, per-job state, service state | Only place the host can be asked |
| Vitest | `^5.0.0` [VERIFIED: package.json] | UI tests | Existing |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `shared/agent-response-contract.json` | in repo | Token/limit contract read by backend and Rust tests | Add new tokens (`patch_reversible_check`, `patch_revert_by_job`, `service_state`) here and in `SUPPORTED_TOKENS` in the same plan |
| Browser `Intl.supportedValuesOf('timeZone')` | built in | Time zone picker list | UI-SPEC section 8 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| New auto registry entry | Register `install_patches` as `approve` and make canary installs a controller-side direct write | Violates the stamp rule (only `gate.py` writes the stamp) and the queue-writer test. Rejected |
| Anchor row per line with union patch list | Per-host rows with per-host params | See Open Question 2; the recommended default below is per-host rows for canary auto and one anchor row per approval line |
| Agent-side expiry | Backend delivery expiry | Agent-side needs a published binary (D-04 flags it costly); backend covers the offline-host case completely. Residual gap: a job queued behind the agent's one-job-at-a-time lock (`PATCH_JOBS`) [VERIFIED: instructions.rs:564] can start after the window closes. Accept and document |

**Installation:** none. No new Python, npm or Cargo packages are required.

**Version verification:** no new packages. `tzdata` is already installed and `zoneinfo` is stdlib.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| tzdata | PyPI | latest release published 2026-10-28 (package is long established) | unknown to the seam | github.com/python/tzdata | SUS (`too-new`, `unknown-downloads`: the seam judged the newest release) | **Not added.** Already present in the venv; the plan relies on stdlib `zoneinfo` plus the system zone database. If the planner wants it declared in `requirements.txt`, add a `checkpoint:human-verify` before the install |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** tzdata (see above; not installed by this phase)

## Architecture Patterns

### System Architecture Diagram

```
 Operator (Rollouts tab)                       Settings / Change Mgmt
   | Start (patches, name)                       | windows + time zone
   v                                             v
 POST /api/patch-rollouts  ------ preflight ----> maintenance window model (zoneinfo)
   |  (window? rings? canary has each OS? busy/other-rollout hosts left out? tokens?)
   v
 patch_rollouts + patch_rollout_hosts  (snapshot of ring membership; unique host claim)
   |
   |   every 60 s, one runner (distributed lock), per tenant in tenant_scope
   v
 ROLLOUT TICK  --- stop active? --> skip install/advance/approve (revert + settle still run)
   |
   +-- settle: patch_deployment_jobs.agentResults -> host state, ledger row executed/failed
   +-- window open? --- no --> ring "Waiting for window" (approved rows deferred)
   |
   +-- canary ring:  per host  gate.decide(install_patches, auto)  --\
   |                 (agent pre-checks reversibility; non-reversible -> approval line)
   +-- later rings / non-reversible: approval line rows -----------> Needs your decision card
   |                                       approve (MFA) -> rollout dispatcher
   |                                          window open ? gate.execute : stay approved
   |                                                  |
   |                         gate.execute -> agent_instructions (stamped, expiresAt)
   |                                                  |   delivery.hold_back_autonomous
   v                                                  v   (stop, expiry, ledger binding)
 install done -> reboot needed? -> Reboot line (approve) -> reboot_host(300 s)
   -> baseline boot_time recorded -> wait new boot (30 min from restart time)
   -> soak (24 h after last install/reboot) -> HEALTH GATE (pure function)
         install result | inventory | heartbeat-after-boot | services | failure share
              green  -> next ring          red/no data -> HALT -> revert via undo (stop-exempt)
                                                           -> Resume (reason) | Cancel
```

### Recommended Project Structure
```
backend/autonomous_ops/rollout/         # inherits autonomous_ops structural tests; each file < 500 lines
├── __init__.py                          # constants: statuses, SOAK default, THIRTY_MIN, DISPATCHER_NAME
├── windows.py                           # occurrences / is_open / next_open (zoneinfo), pure
├── rings.py                             # settings load/validate, membership snapshot, host eligibility
├── start.py                             # preflight + start (claims hosts atomically)
├── controller.py                        # tick(): state machine, lock loop, per-tenant scope
├── canary.py / lines.py                 # auto rows (one per host) and approval line rows
├── health.py                            # signals reader + pure ring_verdict
├── revert.py                            # gated revert (undo pattern) + per-host revert job
├── dispatcher.py                        # approvals dispatcher: window-deferred gate.execute
├── messages.py                          # server copy (added to banned-terms files list)
└── views.py                             # rollout list/detail payloads, flags canStart etc.
backend/patch_rollout_endpoints.py       # /api/patch-rollouts routes (catalogue: patchManagement)
backend/migrations/031_patch_rollouts.py # indexes only
```

### Pattern 1: The controller never writes the queue
**What:** all agent work goes `gate.decide` (record intent) then `gate.execute` / the rollout dispatcher; the revert goes through the undo path. **When:** every install, reboot, revert. **Why:** the stamp is written only in `gate.py` [VERIFIED: gate.py:411-430 `execute` builds `"autonomy": {"actionId": ..., "kind": kind}`], and the structural test fails on any other queue writer.

### Pattern 2: Rows and who owns their lifecycle
Ledger states and dispatchability, verbatim: `_DISPATCHABLE = {"action": ("approved", "dispatching"), "probe": ("dispatching", "executed"), "compensate": ("dispatching", "failed"), "undo": ("undone",)}` [VERIFIED: gate.py:58-59]. `STOP_EXEMPT_KINDS = ("undo", "compensate")` [VERIFIED: autonomous_ops/__init__.py:66]. `HOST_CAP = 1`, `RATE_LIMIT_PER_WINDOW = 20`, `APPROVAL_TTL = timedelta(hours=24)`, `BREAKER_THRESHOLD = 3` [VERIFIED: autonomous_ops/__init__.py:36-40].

- **Canary auto install:** one row per host (`HOST_CAP`), `dispatcher="patch_rollout"`, params per host `{patch_ids: <host pending ∩ rollout patches>, job_id: <per-host job>, require_reversible: true, rollout_id, ring}`. A per-host `patch_deployment_jobs` document (`new_patch_job`) is created first, so `record_agent_patch_result` completes it when that one agent reports.
- **Approval line (Install):** recommended default is **one anchor row per (rollout, ring, line)**, `targets` = every host in the line, identical params for all hosts (union patch list + one ring-level job id + `mode: "rollout"` so the agent treats ids that do not apply to it as `skipped`). Reason: `dispatch_check.bind` requires `same_params(step.params, params)` for every dispatch [VERIFIED: dispatch_check.py `bind`], and `approvals.approve` already revalidates every target [VERIFIED: approvals.py `_revalidate` loops `dict.fromkeys(targets)`]. The dispatcher expands the anchor row into one `gate.execute` per host. *Planning settlement: the plans do not use this default; every line is per-host rows with a line-level approve route (Open Questions (RESOLVED) 2, pending the user's review).*
- **Reboot line:** same anchor-row shape; params `{"delay_seconds": 300, "reason": "Restarting in 5 minutes for updates"}` are identical for all hosts. `reboot_host` is approve-class already [VERIFIED: registry.py:49 `ActionSpec("reboot_host", "approve")`].
- **Revert:** the undo path (Pattern 6).
- Row lifecycle for dispatcher `patch_rollout` is owned by the controller. The reconciler must skip these rows (C5).

### Pattern 3: Window-deferred approvals
`approvals.approve` dispatches immediately after the compare-and-set [VERIFIED: approvals.py `approve`: `result = await dispatcher(db, won, approver)`]. For D-04/D-08 the rollout dispatcher checks the window: open -> `gate.execute` per host now; closed -> return a non-refusal answer and leave the row `approved`. The controller dispatches `approved` rows of this dispatcher when the window opens (the `_authorise` path moves `approved` to `dispatching` itself [VERIFIED: gate.py:395-398]). Required companion changes: reconciler skip (C5); `_revalidate` already covers tenant/eligibility/protected/IP checks but only runs the agent-support re-check for `security_response` [VERIFIED: approvals.py:247], so the rollout dispatcher must run its own capability/online/token check (`agent_support.check`) at dispatch time, which can be days after approval. A stop pressed meanwhile cancels `approved`/`dispatching` rows (`_ROW_STATES = ("approved", "dispatching")` [VERIFIED: stop.py]) to `cancelled_by_stop`; the controller must treat that as "paused", not a failure, and re-issue with a new attempt number after the stop clears.

### Pattern 4: Delivery expiry
Add `expiresAt` (BSON datetime) to each rollout instruction through `gate.execute`'s document (extra optional kwarg), and enforce it inside `delivery.hold_back_autonomous` (the one hook all three poll sites call). An expired pending item is marked terminal (`status: "refused"`, `error: "instruction_expired"`) and dropped from the batch; the hook must still return the list unchanged and touch no database when no item carries `expiresAt`, to keep the existing "no stamped item: untouched" contract [VERIFIED: delivery.py module docstring]. Expiry time = the end of the window occurrence in force when the instruction was issued (D-04). Installs already delivered finish.

### Pattern 5: Health gate is a pure function
Read signals into a plain dict per host, then `ring_verdict(hosts, ring_settings, now)` returns `green`, `waiting` (not enough data yet and soak not over) or `halt(reason_code, host)`. After the soak ends any missing signal is `halt(no_data, signal)`. See Code Examples.

### Pattern 6: Revert is an undo of the install row
Model on `approvals.undo`: transition the row to `undone` with a freshly built `undo` block whose params carry what that host actually installed and a **new revert job id**, then `gate.execute(..., kind="undo")` with exactly those params (`bind` checks the undo block [VERIFIED: dispatch_check.py `decided_steps` for kind `undo`]). Undo is stop-exempt in both `gate._authorise` [VERIFIED: gate.py:391] and delivery [VERIFIED: delivery.py:125]. Register `ActionSpec("install_patches", "auto", undo="rollback_patches", ...)` and `ActionSpec("rollback_patches", "undo_only")`; the registry test requires every undo target to be registered as `undo_only` [VERIFIED: test_autonomous_ops_registry.py:47-53]. For a host whose install row ended `failed` after a partial success, transition `failed -> undone` is allowed by `ledger.transition` (any `from_states`). Tag these transitions with `reasonCode="ring_reverted"` and add that code to `BREAKER_IGNORED` [VERIFIED: ledger.py:252 `BREAKER_IGNORED = ("not_delivered", "no_result", ...)`], like the existing `auto_reverted` precedent. Recommendation on the breaker (Claude's discretion): real install failures keep counting (`agent_failed`), reverts and not-delivered are transparent, so one bad patch cannot by itself drop the tenant's block-IP and quarantine automation, but three failed canary installs in a row still can.

### Pattern 7: One active rollout per host is a database guarantee
A `patch_rollout_hosts` collection, one document per host per rollout, with a unique partial index on `(tenantId, agentId)` where `active: true`. Start inserts all claims in one `insert_many(ordered=False)` and treats `DuplicateKeyError` per host as "left out" (D-13, listed with the owning rollout's name). Release (`active: false`) on rollout end (completed, cancelled). Do not use read-then-write.

### Anti-Patterns to Avoid
- **Writing `agent_instructions` from the controller or reusing `patch_instruction()` for autonomous work:** fails the structural test and bypasses stop, expiry and the ledger.
- **Reading inventory from the pending list alone:** `clear_installed_from_pending` removes installed ids from the stored list when the job reports [VERIFIED: deployment_result_endpoints.py:139-175], so absence is self-fulfilling.
- **Using `agent.status` or the pre-reboot `lastSeen` as "back up":** compare to the baseline.
- **Recording a refused row per tick during a stop:** `_step_tenant_stop` refuses with `record=True` by default [VERIFIED: gate.py:170-173], so a controller that calls `decide` while stopped floods the ledger. Skip tenants with an active stop, as `sweep.py` does [VERIFIED: sweep.py:99-101].
- **Reusing a dedupe key after an undo within 24 h:** `suppressed_by_undo` silently drops the new decision [VERIFIED: gate.py:299-302]. Put rollout id, ring, host and an attempt number in the key.
- **Writing the word "rollback" in rollout modules or docs under the copy gate (C9).**

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DST-correct recurring windows | Offset arithmetic in UTC | `zoneinfo.ZoneInfo` + `datetime.combine(..., tzinfo=tz)` (verified run below) | Spring-forward gap and overnight windows |
| Single-use approvals, expiry, audit mirror | New approval store | `approvals.approve/deny/expire_due`, `ledger.transition` | One compare-and-set winner, hash-chained audit |
| Stop, shadow, protected targets, caps, dedupe | Controller-side checks | `gate.decide` | GATE-03 order is tested |
| One host in one rollout | Read-then-write check | Unique partial index claim | Races between two operators |
| Patch id validation | New regex | `patch_core_endpoints.installable_patch_id`, `pending_patch_ids` | Same rule as the Rust agent (`normalize_patch_id`) |
| Single runner for the loop | Own lock | `distributed_lock.lock_with_renewal` | Used by sweep and reconciler |
| Online test | New heuristic | `agent_support.online()` (status Online and `lastSeen` within 5 min) | Already tested; reads ISO strings safely |
| Capability/token checks | New field | `agent_support.check` and the contract file tokens | Version numbers are not support (a 2.1.15 agent has the code but not the token) |
| Route access | New permission model | `shared/catalogue-access.json` + a `catalogue_mounts_*.py` slice entry under `patchManagement`; drift tests enforce it | Fails the build otherwise |

**Key insight:** every decision a person or the platform makes about a host already has one place it must pass. The phase is mostly about adding a sequencer around those places and fixing the three agent-side truths (reversibility, per-job revert state, positive service state).

## Findings by research focus

### 1. Per-OS reversibility matrix, as the code can do it today

| OS / manager | Install | Revert today | Can the agent tell "revertible" before install? | Needs-reboot signal | Auto canary under D-05/D-06 |
|--------------|---------|--------------|-----------------------------------------------|---------------------|------------------------------|
| Windows (WUA via PowerShell) | `WUA_INSTALL`: `Search("IsInstalled=0 and Type='Software' and IsHidden=0")`, match by KB, `Install()` [VERIFIED: patch_installer.rs:124-170] | `WUA_UNINSTALL`: finds the update among `IsInstalled=1`, refuses when not `IsUninstallable` with message `'Windows marks this update as not uninstallable'` [VERIFIED: patch_installer.rs:186-188] | **No.** The flag is only read at uninstall time. Microsoft documents it as "whether a user can uninstall the update from a computer" [CITED: learn.microsoft.com/en-us/windows/win32/api/wuapi/nf-wuapi-iupdate-get_isuninstallable]. Reading it on the offered `IUpdate` before `$coll.Add($u)` is a small script change. The user accepted that it is not always reliable (D-05) | Post-install `RebootRequired` per update is already returned [VERIFIED: patch_installer.rs:162]. Pre-install, `InstallationBehavior.RebootBehavior` is 0 never / 1 always / 2 can request [CITED: learn.microsoft.com/en-us/windows/win32/api/wuapi/ne-wuapi-installationrebootbehavior] | Yes only for updates with `IsUninstallable` true; others need approval |
| Linux apt (`apt-get`) | `apt-get install --only-upgrade ... -- pkg`, only installed packages [VERIFIED: patch_installer.rs:349-351] | `apt-get install --allow-downgrades pkg=<recorded version>` from `patch_state.json`; fails with the apt error if the version is gone [VERIFIED: patch_installer.rs:386-392] | **No.** Records `before` version only; never asks the source whether it is still offered. Needed: parse `apt-cache madison <pkg>` (pure function, unit-testable) for the installed version before upgrading | Global flag only: `/var/run/reboot-required` or `needs-restarting -r` exit 1 [VERIFIED: patch_installer.rs:318-328], which also trips for unrelated earlier updates | Yes only when the installed version is still in an apt source and the name is not on the reboot-needed denylist |
| Linux dnf / yum | `dnf|yum upgrade -y -q pkg` [VERIFIED: patch_installer.rs:353] | `dnf|yum downgrade -y -q pkg-<version>` [VERIFIED: patch_installer.rs:391] | **No.** Needed: list versions the repos offer (`--showduplicates`) | same as apt (`needs-restarting`) | same rule |
| Other managers (zypper, pacman, apk), macOS | none: `manager()` is `["apt-get", "dnf", "yum"].into_iter().find(...)` [VERIFIED: patch_installer.rs:280-282]; non-Linux/Windows returns `"Patching is not supported on this OS"` [VERIFIED: patch_installer.rs:414-416] | none | n/a | n/a | Not eligible (D-20 says Windows and Linux only). Preflight must name them, not silently drop them |

Planning consequences:
- **Agent change A1 (reversibility pre-check):** `install_patches` gains `require_reversible: true`. Per patch, the agent skips a non-reversible patch with a result row `status: "skipped"` and a machine code (for example `not_reversible`) and installs the rest. One instruction, one atomic check (no probe-then-install gap). The backend then raises an approval line for the skipped ones (UI-SPEC "Canary install, not reversible (Pending)").
- **Agent change A2 (revert by job):** record pre-patch state keyed by job id (and, on Windows, the KBs the job installed). `rollback_patches` with `revert_of: <install job id>` reverts exactly what that job changed on this host, reports `skipped` for ids it did not change, and fails clearly when the source no longer offers the version. This also fixes C3.
- **Honest expectation:** on apt, a security update usually replaces the previous version in the same pocket, so "the source still offers the installed version" will often be false and most Linux canary installs will wait for approval. This is correct behaviour under D-05, but tell the operator why in the row text. `[ASSUMED]` (archive layout varies by distribution; not tested on a live host).
- **Reboot-needing Linux packages (D-06)** cannot be known from the host before install, so combine a code-owned name denylist in the backend (kernel images and headers, glibc/libc6, systemd, dbus, firmware, microcode, grub, openssl-class libraries only if the product wants them) with the post-install `reboot_required` result. The denylist is `[ASSUMED]` content and should be confirmed.
- **Revert may itself need a reboot** (D-15): the revert result carries `reboot_required`; the controller adds the "Restart to finish the revert" line.
- Installs and reverts both run one at a time per agent (`PATCH_JOBS` mutex) [VERIFIED: instructions.rs:564-570].

### 2. Boot identity in the heartbeat

- Rust 2.1.16 sends `meta.response_state.boot_time` (epoch seconds, u64) on every heartbeat [VERIFIED: heartbeat.rs:541, isolation.rs:480-488]. `meta.system_patching.last_boot` (ISO) and `uptime_seconds` exist too but only with the `system_patching` capability, which runs hourly by default (`("system_patching", 3600)` [VERIFIED: capabilities/mod.rs:73]) and is dropped for tenants that have not ticked it. Do not use them.
- The backend stores every `meta.<key>` with `$set` per key on each heartbeat and sets `lastSeen` to the server's receive time as an ISO string [VERIFIED: agent_heartbeat_endpoints.py:144-158]. Only the latest value is kept, so there is no history.
- The Python agent has no usable boot identity (Windows-only, localized string `boot_time`, Linux placeholder [VERIFIED: agent-install/dist/python-agent/capabilities/system_patching.py:26-37,104-121]); rollouts are Rust-only (D-19), so a rollout host is eligible only when `meta.response_actions.tokens` contains `reboot_host` and `meta.response_state.boot_time` is an integer.
- **Backend work:** when the reboot instruction is queued, store `{dispatchedAt, scheduledRestartAt = dispatchedAt + 300 s, baselineBootTime = <meta.response_state.boot_time at that moment>, baselineLastSeen}` on the rollout host. "Fresh heartbeat from the new boot" is: `lastSeen > scheduledRestartAt` and `boot_time > baselineBootTime + tolerance` and `boot_time >= dispatchedAt epoch - tolerance`. Use a tolerance of at least 120 s because `sysinfo` derives boot time from the wall clock and it can shift by seconds after a time sync `[ASSUMED]`. The D-17 30-minute clock should start at `scheduledRestartAt`, not at dispatch (Open Question 5 notes the UI wording says "of the restart").
- Windows delay is passed in seconds, Linux is rounded up to whole minutes (`+5`) [VERIFIED: host_power.rs `schedule_reboot`], so 300 s is exact on both.

### 3. Dispatch, expiry and revert gating

- **The existing install/revert path is real.** `patch_instruction()` files the document under the agent's own tenant: `"tenantId": agent.get("tenantId"), "instruction": "rollback_patches" if rollback else "install_patches", "payload": {"patch_ids": patch_ids, "job_id": job_id}, "type": "os_patch_rollback" if rollback else "os_patch_install"` [VERIFIED: patch_core_endpoints.py:131-150]. The mounted poll delivers it as `task_id`, `instruction`, `payload` and `parameters` [VERIFIED: agent_tasks_endpoints.py:68-80], the Rust arm runs it [VERIFIED: instructions.rs:537-548], and the result lands in `record_agent_patch_result` [VERIFIED: deployment_result_endpoints.py:189-244]. Backend tests cover queueing, results, rollback targets and tenant isolation [VERIFIED: backend/tests/test_patch_deployment_flow.py:162-414]. A live revert on a real host has not been seen by this research `[ASSUMED]` (it stays a live-only check).
- **What it lacks:** no expiry, no gate, no ledger, no stop hold-back (it is unstamped), and `rollback_patch_job` only checks `manage:patches` and a finished job status [VERIFIED: patch_core_endpoints.py:253-298]. Do not reuse its route for autonomous reverts; extract the pure part (build the rollback job and per-agent ids from `agentResults`) and call it from `revert.py`.
- **Poll shape matters:** the live poll reads at most 10 pending items per call and marks them `sent` [VERIFIED: agent_tasks_endpoints.py `to_list(length=10)` and `"status": "sent"`]; a status other than `pending` (for example `scheduled`) is never delivered, and only `scheduler.py` releases `scheduled` items belonging to a `Scheduled` job [VERIFIED: scheduler.py:145-149]. Do not use `scheduled` for window waits (the reconciler would fail it after 24 h); keep the approved *ledger row* waiting and write the instruction only when the window is open.
- **Gate-only commands:** an unstamped item naming `GATE_ONLY_COMMANDS` is refused at delivery: `("quarantine_file", "unquarantine_file", "restart_service", "isolate_host", "restore_host", "reboot_host")` [VERIFIED: delivery.py:36-37]. Do **not** add `install_patches` to it: manual `POST /api/patches/deploy` and `/apply-os-patches` use the same command unstamped.
- **Capability and token gates:** `install_patches`, `rollback_patches` and `reboot_host` all map to capability `patch_installer` [VERIFIED: agent_capabilities.py:69-70,87]; the poll refuses them for a tenant that has not ticked it [VERIFIED: agent_capabilities.py `hold_back`]. Tokens come from the heartbeat; `agent_support.check` returns `capability_off`, `agent_offline`, `agent_unsupported` in that order.
- **Stop:** pressing a stop cancels pending stamped `action`/`probe` instructions and `approved`/`dispatching` rows; `undo` and `compensate` are exempt [VERIFIED: stop.py `_CANCEL_KINDS = ("action", "probe")`]. That is exactly D-15: installs, ring advances and reboots are `action` and are held; reverts are `undo` and pass.

### 4. The old `staged_deployments` / `rollback_jobs` service

- Routes live in `deployment_endpoints.py` under `/api/deployments/staged`, `/api/deployments/approvals/*` and `POST /api/deployments/{deployment_id}/rollback`, guarded as catalogue view `softwareDeployment` [VERIFIED: catalogue_mounts_devices.py:42-47]. UI users: `StagedDeploymentVisualizer.tsx` and `ApprovalDashboard.tsx`; sidebar item `stagedDeployments` shares the routes [VERIFIED: shared/catalogue-access.json `stagedDeployments ... "noBackendReason": "shares routes with softwareDeployment"`].
- Its rollback is dead on arrival: the instruction has no `tenantId` (the live poll filters on it [VERIFIED: agent_tasks_endpoints.py poll query]), carries the patch ids at top level and a free-text `instruction: "Rollback patches: ..."` (the poll relays `i.get("instruction") or i.get("type")`, which the agent cannot match) [VERIFIED: deployment_service.py:415-427].
- **Fence, do not delete.** (1) Replace the instruction loop in `trigger_rollback` with a refusal (HTTP 409, text pointing to Rollouts) so no ungated instruction is ever written, and drop `deployment_service.py` from `GRANDFATHERED_WRITERS` in the same plan (C8). (2) Leave read routes and the sidebar item untouched (a nav change touches 206 catalogue entries and per-tenant switches). (3) Add a regression test that `trigger_rollback` writes nothing to `agent_instructions`. 0 rows on live, so no data migration.

### 5. Health-gate signals

| Signal | Where stored | Writer | Freshness | Gap and fix |
|--------|--------------|--------|-----------|-------------|
| Install result | `patch_deployment_jobs.agentResults[<agent key>]` = `{status, successful, failed, total, rebootRequired, error, results[], reportedAt}` [VERIFIED: deployment_result_endpoints.py:198-207] | Agent POST `/api/deployments/{job_id}/result` | Immediate at job end | Per host. `skipped` counts as cleared (`_CLEARED_STATUSES = {"success", "skipped"}` [VERIFIED: deployment_result_endpoints.py:136]); the gate must distinguish `skipped` (not applicable, or `not_reversible`) from `success`. Agent key replaces `.` and `$` with `_` |
| Post-install inventory | `agents.meta.system_patching.pending_updates` + `timestamp` | Heartbeat, collector runs hourly by default, agent caches the scan 5 minutes [VERIFIED: system_patching.rs:40-52 `TTL ... from_secs(300)`], cache never invalidated after a patch job | Up to about 65 min; the backend also strips cleared ids at result time | Self-fulfilling. **Fix:** (a) agent self-verification in the result row (`verified_installed`: Windows re-queries `IsInstalled=1` for the KB; Linux already compares `installed_version` before and after [VERIFIED: patch_installer.rs:359-361]); (b) after a reboot the agent restarts cold and the next heartbeat carries a fresh scan, giving an independent check; (c) at soak end require `system_patching.timestamp` later than the install plus 5 minutes and the id absent. Missing `system_patching` data at soak end is `no data` (the capability must be ticked; surface as a preflight blocker or the host cannot be judged) |
| Heartbeat after reboot | `agents.lastSeen` (ISO string, server time) and `meta.response_state.boot_time` | Heartbeat | Heartbeat period (default config value `interval_seconds`; about 30 s `[ASSUMED]`) | Needs baseline-and-compare (focus 2). Do not compare an ISO string to a BSON date without parsing (`agent_support._parse_time` does it) |
| Agent service | The heartbeat itself | Agent | same | A live heartbeat after the new boot is the proof; no separate check |
| Watched services | `meta.service_failures` (capability `remediation_executor`, dropped when not ticked [VERIFIED: agent_capabilities.py:56 `_DATA_KEYS`]); tenant list `autonomy_settings.response.watchedServices` [VERIFIED: response_settings.py:3] | Heartbeat; reported only after a 60 s grace and cached 60 s [VERIFIED: service_watch.rs `GRACE_SECONDS`, `REPORT_CACHE_SECONDS`] | about 2 min after boot | **Only failures are reported, never a positive "running"** (a cleanly stopped or never-started service is never listed [VERIFIED: service_watch.rs module doc]). UI-SPEC copy says "{services} are running on {k} of {n}". **Fix (agent change A3):** a small `service_state` heartbeat block listing every watched service as running / stopped / failed / unknown using the existing `status_of`, with a token. Evaluate services no earlier than 2 heartbeats and 120 s after the new boot. Empty watched list: only the agent check, not `no data` (per Claude's-discretion lean). Non-empty list with `remediation_executor` not ticked: `no data` (fail closed) |

Failure share: count hosts with a final verdict among installed hosts. Canary: any failure halts. Later rings: halt when `failed / reported > pct` and `reported >= min`; below `min`, any failure halts (D-10). A `not reached` host (offline the whole ring, no instruction ever delivered) is excluded from both counts (D-18). Canary pass additionally needs one installed host per OS in the rollout.

### 6. Maintenance windows

- Storage today: `maintenance_windows` documents `{id, tenantId, name, start_time (ISO), end_time (ISO), recurrence, days_of_week, is_active}` [VERIFIED: maintenance_service.py:8-32 docstring and body]. Time of day is taken from the ISO strings in UTC; there is no zone. 0 rows on live (CONTEXT). The same windows are consulted by the legacy `deployment_service.create_staged_deployment` (`enforce_maintenance_window` default True [VERIFIED: deployment_service.py:69]).
- **Recommended stored shape (new fields, no migration of rows needed):** `{id, tenantId, name, recurrence: "none"|"daily"|"weekly", startTime: "HH:MM", endTime: "HH:MM", daysOfWeek: [1..7] (ISO, Mon=1), startsAt/endsAt (ISO local naive or UTC) for one-time, isActive}` plus one tenant document `maintenance_settings {tenantId, timeZone}` (not on the `tenants` document: those writes are Super Admin paths). Validate the zone with `ZoneInfo(name)` and reject names not in `zoneinfo.available_timezones()`.
- **Algorithm** (see Code Examples; ran against `Asia/Kolkata` overnight and the `America/New_York` 2026-03-08 gap): enumerate occurrences by *local start date* from yesterday to two days ahead, build wall-clock start and end with `datetime.combine(..., tzinfo=tz)`, end on the next date when `end <= start`, convert both to UTC. The 2026-03-08 window 01:00-04:00 is 2 h long that night, as it should be. Reject start == end and durations over 24 h at write time (UI-SPEC validation). Evaluate "open now", "closes at", "next opens" from the same function.
- **Reads need views the viewer has.** The controller reads windows through the service layer (no route). UI reads: a window strip endpoint under `/api/patch-rollouts` (view `patchManagement`) and a read-only list for Change Management; today Change Management's own permission is `manage:settings` [VERIFIED: shared/catalogue-access.json changeManagement `"permission": "manage:settings"`] and a Settings reader would also hit the `systemHealth` view switch. Writes stay in `/api/maintenance` (view `systemHealth`, `manage:settings`).
- **Existing weekday bug:** convert on write; UI day toggles must send ISO weekday numbers; add a test that Saturday maps to 6.

### 7. How Phase 81 and Phase 83 are wired (reuse map)

| Need | Reuse | Note |
|------|-------|------|
| Decide auto vs card, stop, shadow, caps, dedupe, ledger intent | `gate.decide(db, ActionRequest(...))` | Steps in order: platform stop, eligibility, tenant stop, level, class, protected targets, agent support, blast radius, dedupe, shadow [VERIFIED: gate.py:320-322]. Platform tenant and unticked tenants record nothing |
| Send a decided row | `gate.execute(db, tenant, action_id, command=, agent_id=, params=, kind=)` | Template: `response_dispatch.send` (one row, one `gate.execute`, refusal moves the row out of `dispatching`) |
| Card approval, deny, expiry, undo | `approvals.approve/deny/expire_due/undo`; register a dispatcher with `approvals.register_dispatcher("patch_rollout", fn)` | `security_response` did the same on import [VERIFIED: response_dispatch.py last line] |
| Card listing for "Needs your decision" | Incident cards are built from `autonomy_actions` rows by `incident_views.list_cards` using `_waiting_filter` [VERIFIED: incident_views.py:61-76]; rollout cards need their own list function filtering `dispatcher == "patch_rollout"` with `awaiting_approval` | Approve/Deny routes are generic over `action_id` [VERIFIED: autonomous_ops_endpoints.py:416-440]: `control:autonomous_ops` + interactive session (API keys refused) |
| Periodic runner | `sweep.run_once`/`reconciler.run_once` pattern, started from `app_startup.py` next to the other two [VERIFIED: app_startup.py:512-519] | Add a `rollout_loop` task |
| Activity labels | `messages.ACTION_LABELS` must contain every registry command [VERIFIED: test_autonomous_ops_gate.py:216] | Add `install_patches` and `rollback_patches`; reason codes need plain-words entries in `messages.REASON_TEXT` (the code list is tested) |
| Breaker | `breaker.evaluate` and `ledger.BREAKER_IGNORED` | See Pattern 6 |
| Never-touch / platform host | `protected.check(db, tenant, agent=agent)`: id, hostname and recorded address against built-in and stored entries; built-ins include every agent enrolled in the platform tenant and the backend's own interface addresses [VERIFIED: protected.py module docstring and `check`] | Covers PTCH-07 for installs, reboots, reverts (each passes `gate` or `_revalidate`). Preflight should also call it so a protected host is *listed as left out* rather than failing later |
| Vulnerability suggestion -> draft | Suggestion rows hold `items` with `package` and `cve` per computer [VERIFIED: sweep_suggestions.py:93-118] | The draft endpoint intersects those packages with the host's `pending_patch_ids(agent)`; CVE ids alone map to no installable patch (the deploy route says so [VERIFIED: patch_core_endpoints.py:195-197]) |

### 8. Agent groups as rings; busy hosts

- Groups: `agent_groups {id, tenantId, name, ...}`, members in `agent_group_members {group_id, agent_id, tenantId}` [VERIFIED: agent_group_endpoints.py:41-49,123-160]. Delete removes the group and its members [VERIFIED: agent_group_endpoints.py:110-120], so a ring can end up pointing at a deleted group. Store group ids in the ring settings, validate at Start (a missing group is a preflight blocker), and **snapshot membership into `patch_rollout_hosts` at Start** so later group edits do not move hosts mid-rollout (UI-SPEC: "a running rollout keeps the rings it started with"). Tie rule: a host in two rings' groups joins the earlier ring (UI-SPEC R12); hosts in no group join the last ring.
- Eligibility at Start, per host: tenant matches, status not `Uninstalled`, Rust agent with `reboot_host` token and boot time (see focus 2), not on never-touch, not in another active rollout (claim fails), and **not busy**: an `In Progress` `patch_deployment_jobs` entry with the agent in `dispatchedAgents` and no `agentResults` yet is exactly how the OS Patches tab detects "active job" [VERIFIED: patch_software_endpoints.py:312-320]; reuse that query and list such hosts as left out with the reason `busy`. A busy host mid-rollout (manual patch started later) is only detectable per dispatch: the controller checks the same condition before each dispatch and waits.
- Agent identity: rows target `agents.id`. The poll resolves a hostname or id to the agent document within the caller's tenant [VERIFIED: deployment_result_endpoints.py:87-92 comment], so always store and send `agents.id`.

## Common Pitfalls

### Pitfall 1: Rollout rows fail by themselves
**What goes wrong:** a canary row ends `failed` with `not_delivered` after 30 minutes (host offline) or `no_result` after 24 h (install ran, instruction still `ACCEPTED`).
**Why:** C5. **Avoid:** reconciler skips `dispatcher == "patch_rollout"`; controller settles from jobs. **Warning signs:** Activity shows `agent_failed`-free failures with reason codes `not_delivered` or `no_result` for rollout rows.

### Pitfall 2: Approved but waiting rows die or double-send
**What goes wrong:** an install approved outside the window is failed by the reconciler, or sent twice after a restart. **Avoid:** deferral stored as the row state `approved` with the controller as the only dispatcher; dispatch via `gate.execute` which does the single `approved -> dispatching` compare-and-set; a second tick finds `dispatching` and does nothing.

### Pitfall 3: Revert goes past this job
**What goes wrong:** Linux revert installs the oldest recorded version (C3). **Avoid:** agent change A2; until it ships, the backend must not claim a revert for Linux hosts without the `patch_revert_by_job` token (row says "this computer's agent doesn't support it yet").

### Pitfall 4: Time and clock traps
Weekday off by one (C7); `lastSeen` is an ISO **string** while ledger fields are BSON dates (`_normalize` makes them aware); a naive datetime compared with an aware one raises. Store controller timestamps as aware UTC datetimes and parse agent strings through one helper. A window that crosses midnight is keyed by its *start* date; "next opens" must not return an occurrence already open.

### Pitfall 5: Stop and shadow interactions
Calling `decide` during a stop records refused rows every tick; shadow turns every outcome into a `shadow` row and nothing is sent. Store `shadow` on the rollout at Start and keep it for the rollout's life (UI-SPEC: simulation chip); in simulation, record `would install` rows through `gate.decide` and advance on a simulated clock with no health data. Do not flip a running rollout to live when shadow is lifted.

### Pitfall 6: The 20-per-hour rate limit and one-host cap
A canary of more than 20 hosts hits `rate_limit` and the 21st decision becomes an approval card [VERIFIED: gate.py:271-280]. Issue at most `20 - recent` canary decisions per tick (use `ledger.count_auto_since`), leave the rest `Waiting`, and expect large canaries to span windows. Warn at Start when the canary exceeds 20 hosts.

### Pitfall 7: Reboot decisions made on stale or global signals
Linux `reboot_required()` is a global flag; a host that already needed a reboot before the rollout looks like it needs one because of it. Record the flag before install (agent change: include `reboot_required_before` in the result) or accept the over-report and say "may need a restart". Windows `RebootRequired` is per update result.

### Pitfall 8: Copy gate and registry tests
Adding the new files to `shared/autonomous-ops-banned-terms.json` `files` in the same plan as they are created (UI-SPEC does this for `.tsx`; do it for the new server modules too). Adding registry entries without `ACTION_LABELS` or reason texts fails `test_autonomous_ops_gate.py`.

### Pitfall 9: Approving a closed rollout
A card whose rollout was halted or cancelled must not still be approvable. The controller expires open card rows (`ledger.transition(... ("awaiting_approval",), "expired", reasonCode="rollout_closed")`) when it halts or cancels, and the dispatcher refuses with a plain reason as a second guard.

### Pitfall 10: Agent release dependency
Windows pre-check, Linux pre-check, per-job revert and `service_state` all need agent 2.1.17. Live today has one agent on the Platform tenant, so nothing is blocked now, but **no real canary can auto-install until the user publishes the agent** (publishing is the user's action). Design every agent-dependent step to fail closed by token and say so in the row text.

## Code Examples

### Window occurrences (ran successfully; output reproduced)
```python
# Sketch for backend/autonomous_ops/rollout/windows.py (stdlib only)
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

def occurrences(zone, start_t, end_t, days, around_utc, *, span_days=2):
    tz = ZoneInfo(zone)
    local = around_utc.astimezone(tz)
    for offset in range(-1, span_days + 1):
        d = local.date() + timedelta(days=offset)
        if days is not None and d.isoweekday() not in days:   # ISO: Mon=1 .. Sun=7
            continue
        s_local = datetime.combine(d, start_t, tzinfo=tz)
        e_date = d if end_t > start_t else d + timedelta(days=1)   # runs past midnight
        e_local = datetime.combine(e_date, end_t, tzinfo=tz)
        yield s_local.astimezone(timezone.utc), e_local.astimezone(timezone.utc)

def is_open(zone, start_t, end_t, days, now_utc):
    return next(((o, c) for o, c in occurrences(zone, start_t, end_t, days, now_utc) if o <= now_utc < c), None)
```
Run result (`/tmp/.../scratchpad/win.py`): Saturday 22:00 to 02:00 `Asia/Kolkata` is open at 20:29 UTC and closed at 20:30 UTC on 2026-11-07; `America/New_York` 01:00-04:00 on 2026-03-08 spans `2026-03-08T06:00:00+00:00` to `2026-03-08T08:00:00+00:00` (2 h) while neighbouring days span 3 h.

### Registry additions (sketch)
```python
# backend/autonomous_ops/registry.py (Open Question 1: restrict to the rollout dispatcher)
ActionSpec("install_patches", "auto", undo="rollback_patches"),   # + dispatchers=("patch_rollout",)
ActionSpec("rollback_patches", "undo_only"),
```
Existing precedent in the same file: `ActionSpec("reboot_host", "approve")` (line 49). `gate._step_class` would refuse an `install_patches` request from any other dispatcher as `unregistered_action`.

### Host claim (sketch)
```python
# migration 031 (indexes only)
await coll.create_index([("tenantId", 1), ("agentId", 1)], unique=True, name="one_active_rollout_per_host",
                        partialFilterExpression={"active": True})
# start.py
try:
    await coll.insert_many(claims, ordered=False)
except BulkWriteError as exc:          # duplicates = hosts already in another active rollout -> "left out"
    left_out = [e["op"]["agentId"] for e in exc.details["writeErrors"] if e["code"] == 11000]
```

### Boot comparison (sketch)
```python
def is_new_boot(agent, host, tolerance=120):
    boot = ((agent.get("meta") or {}).get("response_state") or {}).get("boot_time")
    seen = parse_time(agent.get("lastSeen"))
    if isinstance(boot, bool) or not isinstance(boot, int) or seen is None:
        return None                                     # no data -> the ring halts
    return (seen > host["scheduledRestartAt"]
            and boot > host["baselineBootTime"] + tolerance
            and boot >= host["dispatchedAt"].timestamp() - tolerance)
```

### Ring verdict (sketch of the pure function the planner should test exhaustively)
```python
def ring_verdict(hosts, ring, now):   # hosts: list of dicts with per-signal values True/False/None(no data)
    judged = [h for h in hosts if h["state"] not in ("not_reached", "left_out")]
    failed = [h for h in judged if h["failed"]]
    if ring["isCanary"] and failed:                     return halt("canary_failed", failed[0])
    reported = [h for h in judged if h["reported"]]
    if not ring["isCanary"]:
        if len(reported) < ring["minSample"] and failed: return halt("host_failed", failed[0])
        if len(reported) >= ring["minSample"] and len(failed) / len(reported) > ring["failPct"] / 100:
            return halt("failure_share", None)
    if now < ring["soakEndsAt"]:                        return waiting("soak")
    for signal in ("install", "inventory", "heartbeat", "services"):
        missing = [h for h in judged if h[signal] is None]
        if missing:                                     return halt("no_data:" + signal, missing[0])
    return green()
```

### Delivery expiry (sketch, inside `delivery.hold_back_autonomous`)
```python
expired = [i for i in instructions if isinstance(i.get("expiresAt"), datetime) and aware(i["expiresAt"]) <= now]
for item in expired:   # terminal, never delivered later
    await coll.update_one({"_id": item["_id"], "status": "pending"},
                          {"$set": {"status": "refused", "error": "instruction_expired", "refused_at": now_iso}})
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| OS patching "fake end to end" | Real WUA / apt / dnf install and revert with job results | 2026-10-12 (memory: committed 2b4e18de9) | Controller can reuse jobs and results |
| Fixed TEST/DEV/STAGING/PRODUCTION percentage stages (`deployment_service.py`) | Tenant rings from agent groups with soak and health gate | This phase | Percent stages give zero hosts for small tenants (Pitfall 12 in `.planning/research/PITFALLS.md`) |
| Pending-list as "installed?" evidence | Agent self-verification plus post-boot fresh scan | This phase | Removes the self-fulfilling signal |

**Deprecated/outdated:**
- `PatchDeploymentService.trigger_rollback`: writes an undeliverable instruction; fence it (focus 4).
- `.planning/research/PITFALLS.md` Pitfall 10's claim that agent status lags an hour: fixed (C10).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `sysinfo` boot time can shift by seconds after a time sync, so a 120 s tolerance is needed | Findings 2 | Too tight a tolerance fails healthy hosts; too loose misses a no-reboot case |
| A2 | On apt, an older installed version is often no longer offered after a security update, so most Linux canary installs will need approval | Findings 1 | If wrong the canary runs more automatically than expected (low risk, still gated) |
| A3 | Windows `IsUninstallable` read before install is accurate enough (user accepted its unreliability in D-05) | Findings 1 | A "reversible" patch that cannot be uninstalled; revert row says not reverted |
| A4 | Servicing-stack and definition updates report not uninstallable | Findings 1 | They would auto-install in the canary |
| A5 | Heartbeat period is about 30 s | Findings 5 | Evaluation delays; thresholds in this research use minutes so low risk |
| A6 | The Rust agent service starts automatically after reboot on Windows and Linux | Findings 2 | Rings halt with "no heartbeat" on every host (visible quickly in the first live test) |
| A7 | A live revert works end to end (only unit tests and code reading were available) | Findings 3 | Live-only verification step catches it |
| A8 | `dnf downgrade pkg-<version>` and `yum downgrade` accept the `name-version-release` string the agent builds | Findings 1 | Revert fails and reports `failed`, never a false success |
| A9 | The reboot-needing Linux package denylist content (kernel, glibc, systemd, dbus, firmware, microcode, grub) | Findings 1 | A reboot-needing package auto-installs; post-install `reboot_required` still raises the Reboot line |
| A10 | Breaker stance: failures count, reverts and not-delivered are transparent | Pattern 6 | A single bad patch could trip or fail to trip the tenant breaker |
| A11 | A not-reached host is tracked for 7 days after the rollout completes, then reported "never reached" (`closesAt = completedAt + 7 days`) | Open Question 4 | Rollout stays open too long or closes before an offline laptop returns |
| A12 | Per-line anchor rows (one approval per line) rather than per-host approval rows | Pattern 2 | Activity shows one approved row per line rather than per computer; UI-SPEC already describes lines. Not used by the plans: see Open Questions (RESOLVED) 2 (per-host rows) |

## Open Questions (RESOLVED)

Each question below keeps its original text and is followed by the planning settlement and the plans that implement it. These are planning decisions; none has been reviewed or accepted by the user yet. UI-SPEC changes they cause are listed in 84-UI-SPEC.md under "Planning Deviations (pending user review)".

1. **A fourth automatic action (GATE-04).**
   - What we know: the registry test pins three auto actions; PTCH-06 requires canary installs to run on their own.
   - Unclear: whether the user wants the spec restricted to the rollout dispatcher (recommended) or a general registry entry.
   - Recommendation: add `install_patches` as `auto` with a dispatcher allow-list enforced in `_step_class`, update the pinned test with a comment citing PTCH-06, and add a negative test that a playbook request for `install_patches` is refused.
   - **RESOLVED** (follows the recommendation): `install_patches` is registered `auto` with undo `rollback_patches`, and `rollback_patches` `undo_only`, both limited by `ActionSpec.dispatchers = ("patch_rollout",)`. The allow-list is enforced in `gate._step_class` and again in `dispatch_check.bind` (refused `unregistered_action`, nothing recorded); the pinned AUTO test becomes four actions with a comment citing PTCH-06; a negative test refuses `install_patches` from any other dispatcher. Implemented by 84-01 (Task 1). It changes the GATE-04 automatic split from three actions to four, so 84-01 rates it costly; pending the user's review.
2. **One approval per line: anchor row or per-host rows, and the approve route.**
   - What we know: UI-SPEC says Approve/Deny use the existing approvals API; `bind` needs identical params for every host of a row.
   - Unclear: anchor row needs an agent `mode: "rollout"` so non-applicable patch ids are `skipped` (agent change) versus per-host rows needing a line-level approve endpoint that loops `approvals.approve`.
   - Recommendation: anchor row for approval lines (keeps the UI-SPEC API), per-host rows for canary auto. If the planner prefers per-host rows, add `POST /api/patch-rollouts/{id}/lines/{line}/approve|deny` and amend UI-SPEC section 6.
   - **RESOLVED, and the plans deviate from the recommendation above:** every install, restart and revert is one ledger row per host; there is no anchor row. A "line" is the set of a ring's rows sharing `reason.inputs {rolloutId, ring, line}` (84-03). Approve and Deny on a line call new routes `POST /api/autonomous-ops/rollout-lines/{rolloutId}/{ring}/{line}/approve` and `/deny` (84-10, used by the card in 84-15), which run `approvals.approve` or `approvals.deny` once per row with the same permission, signed-in session, stop, 24 h expiry and single-use rules. Why: each host keeps its own patch list and job, so 2.1.16 agents (which fail ids of another OS) can take approved installs without a new agent `mode: "rollout"`; each host's revert is the plain undo of its own install row (84-13, Pattern 6); Activity keeps one row per computer as 81 D-17 does. Cost: one line-level route pair and UI-SPEC deviation DEV-1 (UI-SPEC section 6 is not rewritten; the change is listed in its Planning Deviations section). Pattern 2's anchor-row default and assumption A12 do not apply to these plans. Pending the user's review.
3. **UI-SPEC has no preflight rows for "cannot take a rollout" hosts** (agent too old, capability not ticked, unsupported package manager, busy).
   - Recommendation: reuse the `Left out` info row with a reason sentence per host; amend UI-SPEC section 3 in the planning step rather than inventing a new component.
   - **RESOLVED** (follows the recommendation): preflight lists every host that cannot take a rollout in the `Left out` area with one reason sentence (`agent_too_old`, `capability_off`, `unsupported_os`, `busy`, `never_touch`; texts in `rollout/messages.py` CANNOT_TAKE), never silently dropped. Preflight also blocks when Autonomous Ops is off for the organization and when the claim set would exceed 500 computers. Implemented by 84-02 (copy), 84-06 (preflight) and 84-17 (Start dialog). The UI-SPEC section 3 amendment is recorded as DEV-3 in its Planning Deviations section; pending the user's review.
4. **How long a rollout stays active with "not reached" hosts** (Claude's discretion).
   - Recommendation: the rollout is `Completed` as soon as every ring passed; keep a `notReached` list and a `closesAt` of 7 days; a returning host in that period is offered the install in the next open window as an approval line (not automatic), then the list closes. A11 flags the number.
   - **RESOLVED** (follows the recommendation; Claude's discretion): a rollout is `Completed` as soon as every ring passed; not-reached hosts stay in `notReached` with `closesAt = completedAt + 7 days` (`NOT_REACHED_GRACE`, A11) and keep their claims until they install or the rollout closes; a returning host is offered the install as an approval line in the next open window, never automatically; at `closesAt` the rollout closes, releases the remaining claims and reports `{n} computers were never reached.` Implemented by 84-01 (constant), 84-16 (lifecycle) and 84-14 (the card shows the server's `closesAt`, UI-SPEC R8).
5. **D-17 clock start.** The context says 30 minutes after an approved reboot; the UI-SPEC says "of the restart". Recommendation: start at the scheduled restart time (dispatch plus 300 s).
   - **RESOLVED** (follows the recommendation): the 30-minute clock (`NEW_BOOT_WAIT`, D-17) starts at `scheduledRestartAt`, the reboot dispatch time plus 300 s (`REBOOT_DELAY_SECONDS`, D-08); no heartbeat from the new boot by then counts as no data and halts the ring. Implemented by 84-08.
6. **Services signal needs a small agent addition** (positive `service_state`) for "missing data halts" to be meaningful; without it "Services passed" only means "not reported failing". Recommendation: include it in 2.1.17 with a token; until then show the services row as `Not checked` and do not count it as passed (needs a UI-SPEC wording tweak).
   - **RESOLVED** (follows the recommendation): agent 2.1.17 sends a positive `meta.service_state` block with the `service_state` token (84-11; contract keys in 84-02; version in 84-21). The services signal (84-08) requires every watched service running in a block newer than the new boot; a host without the token is `not_checked` (it fails only when `meta.service_failures` names a watched service), which neither passes nor halts and is shown as `Not checked` (84-02 chip and copy, 84-18 ring detail). The UI-SPEC wording tweak is recorded as DEV-2 in its Planning Deviations section; pending the user's review.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python venv | backend | yes | 3.12.3 | — |
| mongod | backend tests (private instance on 27998) | binary yes, port 27998 not listening now | 8.0.34 | start the private instance per the proven recipe before pytest |
| Node / Vitest | UI tests | yes | v20.20.2, vitest present | — |
| cargo | agent tests | yes (`$HOME/.cargo/bin`) | 1.98.1 | `rustc` is not on PATH; cargo works |
| mingw gcc | Windows agent build | yes | x86_64-w64-mingw32-gcc 13-win32 | — |
| Non-platform tenant with an enrolled Rust agent 2.1.16+ | live-only checks | no (live has one agent on the Platform tenant) | — | none; live checks stay the user's |
| Published agent 2.1.17 | automatic canary, revert, service state | no (2.1.16 built, server offers 2.1.14) | — | fail closed by token |

**Missing dependencies with no fallback:** a disposable non-platform host for the live-only steps (user's).
**Missing dependencies with fallback:** agent 2.1.17 (rollouts run with approvals only, no auto canary, until published).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (backend, async fixtures `tests/_mongo_test_db.py`, helpers `tests/autonomy_support.py`), Vitest 5 (UI), cargo test (agent) |
| Config file | `backend/tests/conftest.py`, `package.json` (`"test": "vitest run"`), `agent-install/omni-agent-rs/Cargo.toml` |
| Quick run command | `MONGO_TEST_URL=mongodb://127.0.0.1:27998 MONGODB_URL=mongodb://127.0.0.1:27998 MONGO_URI=mongodb://127.0.0.1:27998 backend/venv/bin/python -m pytest backend/tests/test_patch_rollout_<file>.py -q -p no:cacheprovider` |
| Full suite command | same prefix with `backend/tests/test_autonomous_ops_*.py backend/tests/test_patch_*.py backend/tests/test_catalogue_*.py -q`; UI `npx vitest run src/__tests__/<file>`; agent `PATH=$HOME/.cargo/bin:$PATH CARGO_BUILD_JOBS=1 CARGO_PROFILE_DEV_DEBUG=0 cargo test --offline --manifest-path agent-install/omni-agent-rs/Cargo.toml --lib <filter>` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PTCH-01 | Rings from groups, snapshot at Start, tie rule, last ring takes ungrouped hosts, next ring only after soak and green | unit + mongo | `pytest backend/tests/test_patch_rollout_rings.py -q` | Wave 0 |
| PTCH-01 | Controller tick state machine incl. restart resume | mongo | `pytest backend/tests/test_patch_rollout_controller.py -q` | Wave 0 |
| PTCH-02 | `ring_verdict` and signal readers: each signal missing halts, `skipped` is not `success`, empty watched list is not no-data | unit | `pytest backend/tests/test_patch_rollout_health.py -q` | Wave 0 |
| PTCH-02 | Boot baseline: old boot, jitter inside tolerance, no `response_state`, 2.1.14 agent | unit | `pytest backend/tests/test_patch_rollout_boot.py -q` | Wave 0 |
| PTCH-03 | Failure share edges: 9 hosts one failure halts, 10 hosts 1 of 10 is 10% not above, 2 of 10 halts; canary any failure | unit | same health file | Wave 0 |
| PTCH-04 | Halt reverts through undo during a stop; unsupported OS row says not reverted; reasonCode `ring_reverted` is breaker-transparent | mongo | `pytest backend/tests/test_patch_rollout_revert.py -q` | Wave 0 |
| PTCH-04 | Copy gate covers new modules; no bare "rollback" | existing | `pytest backend/tests/test_autonomous_ops_copy.py -q` and `npx vitest run src/__tests__/autonomousOpsCopy.test.ts` | exists (update files list) |
| PTCH-05 | Window math: overnight, DST gap, weekday mapping, no window blocks Start, outside window nothing dispatches | unit + mongo | `pytest backend/tests/test_patch_rollout_windows.py -q` | Wave 0 |
| PTCH-05 | Maintenance routes: model validation, update route, tenant isolation, read endpoints per catalogue view | api | `pytest backend/tests/test_maintenance_windows.py backend/tests/test_catalogue_route_parity.py -q` | Wave 0 / exists |
| PTCH-06 | Canary auto only when agent token present and reversible; otherwise approval; deferred approval waits for window; reconciler skips rollout rows; 21st canary decision waits | mongo | `pytest backend/tests/test_patch_rollout_gate.py backend/tests/test_autonomous_ops_reconciler.py -q` | Wave 0 / exists (extend) |
| PTCH-06 | Registry/labels/reason texts/locked split test updated | existing | `pytest backend/tests/test_autonomous_ops_registry.py backend/tests/test_autonomous_ops_gate.py -q` | exists (update) |
| PTCH-07 | Platform tenant and protected hosts never claimed; unique claim race; expired instruction never delivered; stop hold-back for installs, not for undo | mongo | `pytest backend/tests/test_patch_rollout_claims.py backend/tests/test_autonomous_ops_stop.py -q` | Wave 0 / exists |
| PTCH-07 | Legacy fence writes nothing; structural test list updated | existing | `pytest backend/tests/test_autonomous_ops_structural.py -q` | exists (update) |
| Agent | reversibility pre-check, per-job revert state, `skipped` semantics, `service_state`, tokens equal contract | cargo | `cargo test --lib patch_installer` and `--lib response_contract` | Wave 0 (pure parsers, no real package manager) |
| UI | Rollouts tab, Start dialog, ring settings, approval card, window dialogs | vitest | `npx vitest run src/__tests__/PatchRollouts*.test.tsx` | Wave 0 |

### Sampling Rate
- **Per task commit:** the single new test file for that task plus the structural and copy tests.
- **Per wave merge:** all `test_autonomous_ops_*.py`, `test_patch_*.py`, catalogue slice tests, and the touched Vitest files.
- **Phase gate:** full backend suite on the final code (known baseline in memory: 5,135 pass plus the known 5 failures; the two nav-count-190 pins already fail from Phase 87), Vitest, and Rust lib tests green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `backend/tests/test_patch_rollout_*.py` (rings, controller, health, boot, revert, windows, gate, claims) covering PTCH-01..07
- [ ] `backend/tests/test_maintenance_windows.py` (new model, update route, weekday mapping)
- [ ] Rust unit tests for the new pure parsers (`apt-cache madison` output, dnf version list, reversibility decision, per-job state) in `patch_installer.rs`; the Linux package-manager calls use `tokio::process::Command` directly (no recorder), so keep the new logic in pure functions
- [ ] Contract additions in `shared/agent-response-contract.json` and the pinned token list in `response_contract_tests.rs` (lines 155 and 157 pin the exact list)
- [ ] Private mongod on port 27998 started before backend tests
- [ ] UI tests under `src/__tests__/` for each new component

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Approvals need an interactive session; API keys refused (`_require_interactive_session`) |
| V3 Session Management | yes | Existing session/MFA for approve-tier; Resume needs the manage permission plus a typed reason |
| V4 Access Control | yes | `control:autonomous_ops` for approve/deny; `manage:patches` for start, rings, Resume, Cancel; catalogue registration under `patchManagement`; tenant id always from the token, never the body |
| V5 Input Validation | yes | Pydantic models for windows, rings and Start (names 1-60/40 chars, hours 1-168, pct 1-50, sample 1-100, IANA zone from `available_timezones`, patch ids through `installable_patch_id`); group ids must belong to the tenant |
| V6 Cryptography | no | none new |
| V7 Logging | yes | Every ledger change is mirrored to the hash-chained audit log; Resume reasons recorded with the actor |
| V11 Business logic | yes | Limits (20/hour, one host per decision), one active rollout per host (unique index), single-use approvals |
| V13 API | yes | Route group in the catalogue; rate limits as other write routes |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Mass assignment on window create (raw dict stored today, C7) | Tampering | Typed model, whitelisted fields, tenant from context |
| Cross-tenant ring group or rollout id (IDOR) | Information disclosure / Tampering | Every read and write filters `tenantId`; group and agent ids resolved inside the tenant; 404 for foreign ids |
| Patch id or reason text reaching a shell | Tampering | Ids validated by `installable_patch_id` and again by the agent; reboot reason cleaned by `clean_reason` and passed as one argv element [VERIFIED: host_power.rs `clean_reason`] |
| Stale approval used after the rollout closed or days later | Elevation / Repudiation | 24 h expiry, rollout-closed expiry, re-validation at dispatch, window and token check at dispatch |
| Replay of an old install instruction after a halt | Tampering | `expiresAt` hold-back, stamped binding to a ledger row in a dispatchable state, controller cancels pending instructions of a halted ring |
| Patching the platform host | Denial of service | Never-touch built-ins plus Platform tenant refusal in `gate.decide`; preflight lists such hosts as left out |
| Operator DoS via a giant ring | Denial of service | Cap hosts per rollout (planner picks, for example 500), chunk dispatch, rate limit |
| Silent unsupported revert claim | Repudiation | Revert result must come from the agent; row text from the server never says reverted without a success result |

## Sources

### Primary (HIGH confidence)
- Repository files read this session (path and line cited inline): `backend/patch_core_endpoints.py`, `deployment_result_endpoints.py`, `agent_tasks_endpoints.py`, `agent_instruction_endpoints.py`, `agent_heartbeat_endpoints.py`, `agent_capabilities.py`, `deployment_service.py`, `deployment_endpoints.py`, `maintenance_service.py`, `maintenance_endpoints.py`, `agent_group_endpoints.py`, `patch_software_endpoints.py`, `app_background_tasks.py`, `scheduler.py`, `autonomous_ops/{gate,registry,approvals,delivery,reconciler,ledger,breaker,stop,protected,dispatch_check,agent_support,decision_row,response_dispatch,sweep,sweep_restart,incident_views,messages,__init__}.py`, `autonomous_ops_endpoints.py`, `backend/tests/test_autonomous_ops_structural.py`, `test_autonomous_ops_registry.py`, `test_patch_deployment_flow.py`, `shared/{agent-response-contract,agent-capabilities,catalogue-access,autonomous-ops-banned-terms}.json`, `agent-install/omni-agent-rs/src/{instructions,heartbeat,instruction_report}.rs`, `src/capabilities/{patch_installer,host_power,system_patching,service_watch,isolation,response_actions,mod}.rs`.
- Microsoft Learn, `IUpdate::get_IsUninstallable` and `InstallationRebootBehavior` (fetched 2026-11-05).
- Runs this session: Python 3.12.3 `zoneinfo`/`tzdata 2026.4` import, the window algorithm script, the package legitimacy seam for `tzdata`.

### Secondary (MEDIUM confidence)
- `.planning/research/{SUMMARY,PITFALLS,ARCHITECTURE}.md` (internal prior research; one claim corrected, C10).
- Auto-memory notes on Phase 81/83 execution and test recipes.

### Tertiary (LOW confidence)
- Linux archive-layout behaviour for older package versions and `sysinfo` boot-time jitter (training knowledge, items A1, A2, A8).

## Project Constraints (from CLAUDE.md)

- Do what was asked; keep files under 500 lines; never save working files or tests to the repo root (use `/src`, `/tests`, `/docs`, `/config`, `/scripts`); read a file before editing it; validate input at system boundaries; never commit secrets or `.env` files.
- Always run tests after code changes and verify the build before committing (`npm run build && npm test`); backend tests use the private mongod recipe above.
- Do not add a `Co-Authored-By` trailer unless `.claude/settings.json` sets `attribution.commit` (the session reminder gives the attribution line to use when committing).
- Auto-memory directives that apply: archive rather than delete; secrets, service restarts, UI publishes and `git push` are the user's actions (give the user the command); never call the feature "ASI", "Autopilot" or "fully autonomous" and never use an unqualified rollback wording (ACTV-08); copy gate files list must include every new rollout module.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH, no new packages; all components are existing and were read.
- Architecture: HIGH for gate, ledger, approvals, delivery, reconciler wiring (read end to end); MEDIUM for the exact controller state machine (design, not yet built).
- Pitfalls: HIGH for C1-C10 (code-verified); MEDIUM for agent-behaviour items marked assumed.
- Reversibility in the field: MEDIUM-LOW until a disposable host is available.

**Research date:** 2026-11-05
**Valid until:** 2026-12-05 (the gate and approvals code is stable; re-check if Phase 87 or later phases touch `agent_support`, `delivery` or the reconciler before planning executes)
