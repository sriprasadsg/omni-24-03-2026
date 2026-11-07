---
phase: "84"
slug: "staged-patch-rollouts"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-07"
---

# Phase 84 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| controller -> gate -> agent queue | The only way a rollout install reaches a host | per 84-01 threat model |
| agent -> result route | Patch results are agent-supplied and untrusted | per 84-01 threat model |
| operator -> start_rollout | Patch ids and the rollout name come from a person | per 84-01 threat model |
| backend -> published agent | The contract is what a released binary will accept | per 84-02 threat model |
| server copy -> operator | Wording that could overstate a revert | per 84-02 threat model |
| approver -> approvals | A person's click dispatches work to many hosts | per 84-03 threat model |
| approved row -> later dispatch | Up to 24 h plus a window wait between approval and send | per 84-03 threat model |
| agent poll -> instruction queue | The last point an instruction can be stopped | per 84-04 threat model |
| legacy route -> queue | An old path that wrote ungated instructions | per 84-04 threat model |
| operator -> /api/maintenance | Window and zone bodies from a person | per 84-05 threat model |
| operator -> rings and start | Group ids, patch ids and names from a person | per 84-06 threat model |
| two operators -> claims | Concurrent starts | per 84-06 threat model |
| backend instruction -> agent | Patch ids and job ids from the server | per 84-07 threat model |
| agent -> package manager | Commands run with privilege on the host | per 84-07 threat model |
| agent heartbeat -> gate | boot_time, lastSeen, scans and service states are agent-supplied | per 84-08 threat model |
| browser -> /api/patch-rollouts | Untrusted bodies, ids and tenant query | per 84-09 threat model |
| approver browser -> line routes | One request dispatches to many hosts | per 84-10 threat model |
| agent -> heartbeat | Service names and states are agent-supplied | per 84-11 threat model |
| server text -> DOM | Window names and schedule texts from the API | per 84-12 threat model |
| controller -> revert instruction | Stop-exempt work reaching hosts | per 84-13 threat model |
| agent -> revert result | Untrusted success claims | per 84-13 threat model |
| API text -> DOM | Rollout, ring, group and host names | per 84-14 threat model |
| approver -> line routes | One click dispatches to many hosts | per 84-15 threat model |
| operator -> resume and cancel | Reason text and the decision to continue | per 84-16 threat model |
| browser -> start and rings routes | Operator input | per 84-17 threat model |
| Autonomous Ops screen -> Patching screen | A suggestion id carried in navigation state | per 84-19 threat model |
| global switches -> controller | Shadow and stop state read every tick | per 84-20 threat model |
| repo -> published agent and live server | Publishing and restarts are a person's steps | per 84-21 threat model |
| backend workers -> rollout controller | Several backend processes start the same loop; only one may act | per 84-22 threat model |
| controller -> patch_rollout_hosts | The one-rollout-per-host rule depends on a database index being present | per 84-22 threat model |

---

## Threat Register

Register authored at plan time (every 84-NN-PLAN.md `<threat_model>`). Verified 2026-11-07 by gsd-security-auditor at ASVS 1 against the implementation, not the summaries; pinning tests re-run on a private mongod (368 passed).

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-84-01 | Elevation of Privilege | registry install_patches auto | high | mitigate | dispatchers allow-list enforced in gate._step_class and dispatch_check.bind; a playbook or other dispatcher is refused unregistered_action (test) — verified: registry.py:52 dispatchers=("patch_rollout",); gate.py:192-195; dispatch_check.py:204-205; tracer + registry tests | closed |
| T-84-02 | Tampering | patch ids | high | mitigate | installable_patch_id at start; ids are intersected with the host's own pending list; the agent re-validates with normalize_patch_id — verified: start.py:328-335 _clean_ids via installable_patch_id; start.py:156 host pending intersect; agent normalize_patch_id | closed |
| T-84-03 | Denial of Service | platform host | high | mitigate | protected.check at start; the platform tenant refused; gate.decide refuses the platform tenant again — verified: start.py:357-358 platform refused; start.py:161 protected.check; gate.py:160-161; controller.py:345 | closed |
| T-84-04 | Tampering | late instruction | medium | mitigate | expiresAt set from the window occurrence end; enforced at delivery by 84-04 — verified: installs.py:203 / dispatcher.py:146 occurrence end; gate.py:428-429 expiresAt; delivery.py:146-176 | closed |
| T-84-05 | Repudiation | revert wording | medium | mitigate | NOT_REVERTED texts and the halt summary come from one module; a test requires "The patch is still installed." on each — verified: messages.py:153-156 single NOT_REVERTED template; test_patch_rollout_messages.py:125 | closed |
| T-84-06 | Tampering | contract drift | medium | mitigate | Existing contract keys snapshotted by a test; new names live under new keys until the agent implements them — verified: test_patch_rollout_contract.py:62-71 token prefix + key digests | closed |
| T-84-07 | Tampering | copy gate blind spot | low | mitigate | Directory entries must exist and be non-empty; negative controls on both sides — verified: test_autonomous_ops_copy.py:230-300 dirs non-empty + negative controls; autonomousOpsCopy.test.ts | closed |
| T-84-08 | Elevation of Privilege | approve_line | high | mitigate | Runs approvals.approve per row (single-use compare-and-set, expiry, _revalidate with protected.check per target); scope fixed to one rollout, ring and line — verified: lines.approve_line per row via approvals.approve, _approval_filter scope; approvals.py:156-158 CAS | closed |
| T-84-09 | Tampering | stale approval | high | mitigate | Dispatch-time re-check of claim, rollout state, capability, online, token and busy; halt expires every open row (rollout_closed) — verified: dispatcher.host_problem send-time re-check; lifecycle.halt _close_open_rows | closed |
| T-84-10 | Tampering | replay after halt | medium | mitigate | Pending install rows of a halted ring move to failed so delivery refuses their instructions as not dispatchable — verified: lifecycle._end_unfetched -> failed rollout_halted; delivery _DISPATCHABLE refuses | closed |
| T-84-11 | Denial of Service | rate limit | low | mitigate | Canary budget computed from count_auto_since, so a large canary spreads over ticks and never floods cards — verified: installs.canary_auto budget = RATE_LIMIT_PER_WINDOW - count_auto_since | closed |
| T-84-12 | Tampering | expired instruction | high | mitigate | Expiry checked in hold_back_autonomous, which every poll path calls (structural test) — verified: delivery.py:168-176 expiry first; test_autonomous_ops_structural.py:430-432 all poll paths | closed |
| T-84-13 | Elevation of Privilege | legacy trigger_rollback | high | mitigate | Fenced with 409; removed from GRANDFATHERED_WRITERS so a regression fails the structural test — verified: deployment_service.py:380-390 LegacyRevertRetired; deployment_endpoints.py:313 409; not in GRANDFATHERED_WRITERS | closed |
| T-84-14 | Denial of Service | reconciler | medium | mitigate | Rollout rows skipped in _reconcile_dispatches; expiry of awaiting rows kept — verified: reconciler.py:131-132 skips patch_rollout; expire sweep unfiltered | closed |
| T-84-15 | Tampering | revert during stop | low | accept | Undo stays stop-exempt by design (81 D-12, 84 D-15) — verified: accepted: STOP_EXEMPT_KINDS = (undo, compensate) autonomous_ops/__init__.py:66; 84-CONTEXT D-15 | closed (accepted) |
| T-84-16 | Tampering | window create (mass assignment, C7) | high | mitigate | Typed WindowBody with whitelisted fields; tenant from context only — verified: maintenance_service.py:41-52 WindowBody; maintenance_endpoints.py:16-21 tenant from context, manage:settings | closed |
| T-84-17 | Information Disclosure | window ids (IDOR) | medium | mitigate | Every read, update and delete filters tenantId; foreign ids answer 404 — verified: maintenance_service.py:238,252,265 tenantId filters; foreign id 404 | closed |
| T-84-18 | Tampering | time zone value | low | mitigate | Only names in zoneinfo.available_timezones() are stored — verified: maintenance_service.py:66-67 available_timezones(), enforced :200, :211 | closed |
| T-84-19 | Information Disclosure | group ids (IDOR) | medium | mitigate | Group ids resolved inside the tenant only; a foreign or deleted id is refused — verified: rings.validate tenant-scoped group lookup; resolve drops deleted; membership filters tenantId | closed |
| T-84-20 | Tampering | concurrent claims | high | mitigate | Unique partial index; a failed claim releases the caller's claims and answers already_in_rollout — verified: store.py:83-87 unique partial index; start.py:369-371 ordered claims, loser discards (AlreadyInRollout 409) | closed |
| T-84-21 | Denial of Service | platform host | high | mitigate | Platform tenant refused; protected.check per host; never-touch hosts listed, never claimed — verified: start.py:357 platform refused; tenant-only agents read; never-touch -> cannot_take | closed |
| T-84-22 | Denial of Service | giant rollout | medium | mitigate | 500-computer cap is a blocker — verified: MAX_HOSTS_PER_ROLLOUT=500; start.py:297 blocking cap row | closed |
| T-84-23 | Tampering | package names and job ids | high | mitigate | normalize_patch_id and the job id shape rule apply to revert_of; every command is an argv list, never a shell string — verified: patch_installer.rs:43,90-92 normalize_patch_id/safe_id; argv-only commands; OMNI_KBS env | closed |
| T-84-24 | Repudiation | revert result | medium | mitigate | Success only after the manager or WUA confirms; coded failures otherwise — verified: Linux success only when installed_version == target; Windows WUA 2/3 only | closed |
| T-84-25 | Tampering | state file | low | mitigate | State kept under the agent's own directory with the existing permissions; unreadable state means no revert_of target and a coded failure — verified: patch_state.rs defaults on unreadable state; plan_revert not_applicable (:98-103) | closed |
| T-84-26 | Spoofing | stale heartbeat as new boot | high | mitigate | Baseline stored at dispatch; new boot needs lastSeen after the scheduled restart and boot_time beyond the tolerance — verified: reboots.py:50-65 is_new_boot three conditions; record_baseline at dispatch | closed |
| T-84-27 | Tampering | self-fulfilling inventory | medium | mitigate | Only a scan timestamped after install + 5 min counts; the result-time pending strip is ignored — verified: signals.py:47-53 scan newer than since + INVENTORY_FRESH_AFTER | closed |
| T-84-28 | Repudiation | services passed without data | medium | mitigate | No token means Not checked, never Passed; a token host with no fresh block is no data and halts — verified: signals._services NOT_CHECKED / no data; ring_verdict halts no_data:services | closed |
| T-84-29 | Information Disclosure | rollout and suggestion ids (IDOR) | high | mitigate | Every query filters the caller's tenant; foreign ids 404 — verified: get_rollout find_one(id, tenantId) 404; views.resolve_tenant 403; picker.draft tenant-scoped; cards.py:100,274 | closed |
| T-84-30 | Elevation of Privilege | start and rings by API key | high | mitigate | _require_interactive_session on writes; manage:patches required — verified: _require_manage_patches + _require_interactive_session on writes; catalogue_mounts_devices.py:36 PATCH_GUARD | closed |
| T-84-31 | Tampering | start body | medium | mitigate | Strict pydantic bodies with length caps; ids through installable_patch_id in start — verified: StartBody/PreflightBody/RingsBody length caps; start.py:328-335 installable_patch_id | closed |
| T-84-32 | Spoofing | client-derived permissions | low | mitigate | Flags computed on the server only — verified: views.py:49-69,341 can_act server-side; cards.py:224 canApprove/canDeny | closed |
| T-84-33 | Elevation of Privilege | line approve | high | mitigate | _require_control plus _require_interactive_session; API keys refused (81 D-10); per-row approvals.approve — verified: autonomous_ops_response_endpoints.py:247-248,264-265 control + session; per-row approvals | closed |
| T-84-34 | Tampering | path parameters | medium | mitigate | rollout id length cap, ring range, line literal; tenant from _tenant_for — verified: path caps (id<=64, ring 0-3, Literal line); _tenant_for + platform 409; foreign 404 | closed |
| T-84-35 | Repudiation | who approved | low | mitigate | Each row's approval records the approver and is mirrored to the audit chain by ledger.transition — verified: approvals.py:171-176 actor; ledger.py:138 _mirror to audit chain | closed |
| T-84-36 | Tampering | service names | low | mitigate | Names capped at 128 characters; the backend matches them against the tenant's own watched list only — verified: service_watch.rs state_report_with drops >128 / malformed; signals._from_block tenant list only | closed |
| T-84-37 | Denial of Service | heartbeat size | low | mitigate | One entry per watched service, duplicates dropped — verified: service_watch.rs case-insensitive dedupe; MAX_WATCHED=50 | closed |
| T-84-38 | Tampering | rendered names (XSS) | medium | mitigate | React text only; no dangerouslySetInnerHTML in any new file — verified: no dangerouslySetInnerHTML/innerHTML in patchRollouts components/services, Decisions, MaintenanceWindowConfig | closed |
| T-84-39 | Spoofing | client-side permission | low | mitigate | Write controls rely on the server's 403 and the existing canManageSettings gate; the Change Management list has no writes — verified: SettingsDashboard.tsx:413 canManageSettings; server manage:settings; CM windows read-only GET | closed |
| T-84-40 | Repudiation | revert claim | high | mitigate | Reverted only from an agent success result; Not reverted texts state the reason — verified: revert.py:216-240 judge: Reverted only on agent success | closed |
| T-84-41 | Tampering | revert scope | high | mitigate | Ids come from the host's own install job results (installed_ids_for), never from a request; bind checks the undo params — verified: revert._targets via installed_ids_for(job, agentId) patch_core_endpoints.py:256-261; dispatch_check.bind :185-190 | closed |
| T-84-42 | Elevation of Privilege | stop bypass | medium | mitigate | Only kind undo is stop-exempt; the revert restart line is an approval and frozen by a stop — verified: only undo/compensate stop-exempt; revert restart is reboot_host action, refused under stop | closed |
| T-84-43 | Denial of Service | breaker | medium | mitigate | ring_reverted and rollout_halted transparent; real install failures counted — verified: ledger.py:268-270 BREAKER_IGNORED excludes rollout_install_failed | closed |
| T-84-44 | Tampering | rendered names (XSS) | medium | mitigate | React text only; a test greps both files for dangerouslySetInnerHTML — verified: clean innerHTML grep; PatchRolloutCard.test.tsx:244 | closed |
| T-84-45 | Spoofing | client-derived controls | low | mitigate | Every control renders from server flags; the server re-checks every write — verified: controls from server flags; server re-checks writes (T-84-30, T-84-33) | closed |
| T-84-46 | Elevation of Privilege | Approve button | medium | mitigate | Rendered only from canApprove; the route re-checks control, session and stop — verified: RolloutApprovalCard.tsx:98,211 canApprove / disabled in stop; route re-checks stop | closed |
| T-84-47 | Repudiation | consequence hidden | low | mitigate | What happens, window timing and restart warning are printed on the line before the click — verified: cards.py:171-178 _what_happens; messages.py:269-277; RolloutApprovalCard.tsx:111,177 | closed |
| T-84-48 | Elevation of Privilege | resume bypassing the gate | high | mitigate | Resume continues only on a green ring_verdict over current data; no skip path exists — verified: lifecycle.resume only on green ring_verdict; _continue (lifecycle.py:263) sole path, no skip | closed |
| T-84-49 | Repudiation | who resumed and why | medium | mitigate | Control row and audit event with actor and reason — verified: resumeLog + record_control mirrored to audit; _undo_flip on record failure | closed |
| T-84-50 | Elevation of Privilege | API key resume | medium | mitigate | _require_interactive_session and manage:patches on both routes — verified: post_resume/post_cancel: _require_manage_patches + _require_interactive_session | closed |
| T-84-51 | Tampering | client-side checks only | medium | mitigate | Every check shown is the server preflight; the server re-runs it at Start — verified: start_rollout re-runs _assess, PreflightBlocked before claims | closed |
| T-84-52 | Tampering | rendered patch titles (XSS) | low | mitigate | React text only — verified: clean innerHTML grep incl. StartPatchPicker/StartPreflight | closed |
| T-84-53 | Tampering | rendered reasons (XSS) | medium | mitigate | React text only — verified: clean innerHTML grep incl. RingDetail/RolloutDialogs | closed |
| T-84-54 | Spoofing | Resume shown to the wrong person | low | mitigate | Rendered only from canResume and canCancel; the routes re-check manage:patches and the session — verified: RolloutDialogs.tsx:232,243,263 server flags; routes re-check (T-84-50) | closed |
| T-84-55 | Elevation of Privilege | draft link | low | mitigate | The link only opens a dialog; the draft route checks the tenant and the Start route checks manage:patches and the session — verified: RolloutsTab.tsx:54-73,210-214 / StartDialog.tsx:91-103 open only; server checks draft + Start | closed |
| T-84-56 | Tampering | suggestion id in state | low | mitigate | The id is sent to the draft route, which resolves it inside the caller's tenant (404 otherwise) — verified: picker.draft ledger.get(db, tenant, id) + tenant agent read; 404 on None | closed |
| T-84-57 | Elevation of Privilege | simulation turning live | high | mitigate | rollout.shadow fixed at Start; master_shadow True on every decide of a simulation rollout — verified: shadow stamped start.py:377; lines.shadow_flag on every decide; dispatcher rollout_simulation refusal | closed |
| T-84-58 | Denial of Service | ledger flooding during a stop | medium | mitigate | No gate.decide while stopped (gate records a refused row per call otherwise) — verified: controller _may_decide guards _ring and _tail; test_patch_rollout_shadow_stop.py | closed |
| T-84-59 | Tampering | double send after a stop | medium | mitigate | Stop-cancelled instructions are terminal; re-issues carry a new attempt and dedupe key — verified: settle._settle_auto/_settle_lines terminal failed + attempt+1; delivery marks cancelled | closed |
| T-84-60 | Tampering | unpublished code assumed live | medium | mitigate | The live list states each step; every agent-dependent path fails closed by token until 2.1.17 is published — verified: process: fail-closed by token (split_canary, host_problem, classify_hosts, revert._start_host, signals._services); live list 84-21-SUMMARY | closed |
| T-84-61 | Denial of Service | live rollout on real tenants | medium | mitigate | Tenants stay in shadow until a Super Admin lifts them; the live checks use a disposable host on a test tenant — verified: process: shadow default True (settings.py:79,100-117), stamped at Start; live list step 6 | closed |
| T-84-62 | Tampering | concurrent controllers | high | mitigate | distributed_lock patch_rollout_controller with renewal around every tick; lost() passed to tick and polled between tenants; test holds the lock and asserts run_once returns None — verified: loop.run_once lock_with_renewal; tick(lost=...); test_patch_rollout_controller.py:102,111 | closed |
| T-84-63 | Elevation of Privilege | missing claim index | high | mitigate | _indexes_ready re-creates one_active_rollout_per_host or stops the pass; migration 031 creates it; test plants duplicate claims and asserts no tick runs — verified: loop._indexes_ready; migration 031 store.ensure_indexes; controller tests :48-136 | closed |
| T-84-64 | Denial of Service | background loop | medium | mitigate | each pass's error is logged and the loop goes on; CancelledError re-raised; started through _safe_bg_task like the sweep — verified: rollout_loop logs + continues, re-raises CancelledError; app_startup.py:524-526 _safe_bg_task | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-84-01 | T-84-15 | A revert (undo) is stop-exempt by design so a halted ring can still be put back during a platform or tenant stop (81 D-12, 84 D-15 in 84-CONTEXT.md); code: `STOP_EXEMPT_KINDS = ("undo", "compensate")`. | Decided in /gsd-discuss-phase 84 (D-15); recorded by /gsd-secure-phase | 2026-11-07 |

*Accepted risks do not resurface in future audit runs.*

### Notes (not threats)

- T-84-60 and T-84-61 are process mitigations: the fail-closed code paths are verified; the live steps in 84-21-SUMMARY.md (publish 2.1.17, lift a test tenant out of shadow) are the user's and have not been performed.
- Known deferred item (84-20): a live rollout whose tenant later enters shadow still sends rows a person approved earlier (inside the window only). Inverse of T-84-57, which is met.
- The person-initiated install/rollback job path in `patch_core_endpoints.py:139` is pre-existing and outside T-84-13 (which covers the retired `trigger_rollback`).

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-07 | 64 | 64 | 0 | gsd-security-auditor (sonnet) via /gsd-secure-phase 84 |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-07

## Security Audit 2026-11-07

| Metric | Count |
|---|---|
| Threats found | 64 |
| Closed | 64 |
| Open | 0 |
