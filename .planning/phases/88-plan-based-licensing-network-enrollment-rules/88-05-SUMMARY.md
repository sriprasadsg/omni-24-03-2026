---
phase: 88-plan-based-licensing-network-enrollment-rules
plan: 05
subsystem: licensing
tags: [networks, enrollment, ipaddress, pending, mongodb]

requires:
  - phase: 88-01
    provides: plan_service.is_exempt, the shared _enrollment_harness (register with a settable client address)
  - phase: 88-02
    provides: licensing seat functions, pending_agents.approve raise path
provides:
  - network_rules (normalize_ip, network_of, contains, entry, validate_widen, learn_first, allow, MAX_NETWORKS)
  - hold_reasons (every hold reason code, REASON_TEXT, REFUSAL_TEXT, reason_text, refusal_text)
  - new_network hold in license_rules.hold_reason (params source_ip, hostname)
  - approve(widen_to) and ApproveBody.widenTo; approve result networkAllowed / network
  - tenant field allowedNetworks, agent field sourceIp on admitted agents
affects: [88-06, 88-07, 88-11, 88-16]

actuals:
  tokens: 36000
  tasks: 3
  commits: 7
plan_head_before: daadc6855612ca2f95395e38c5a37824ffa7cf65
plan_head_after: c3dfc7cdb26f0489ddd093f8840370c1252bb99e

tech-stack:
  added: []
  patterns:
    - "the network decision rests on request.client.host only; uvicorn trusting only 127.0.0.1 and ::1 makes that the address nginx appended, and a test pins it"
    - "learn and allow are single conditional updates ($push guarded by the filter), so a race or a full list is a False, never a second write"

key-files:
  created:
    - backend/network_rules.py
    - backend/hold_reasons.py
    - backend/tests/test_network_rule.py
    - backend/tests/test_proxy_headers.py
  modified:
    - backend/license_rules.py
    - backend/agent_registry_endpoints.py
    - backend/pending_agents.py
    - backend/pending_agent_endpoints.py
    - backend/tests/test_plan_tracer.py
    - backend/tests/test_licensing.py
    - backend/tests/test_partner_expiry.py
    - backend/tests/test_agent_registry_regression_1.py
    - backend/tests/test_agent_location_history_wiring.py

key-decisions:
  - "The new_network tenant text is 'it enrolled from a new network {ip}, waiting for platform approval' (no parentheses around the address) so the notice contains the D-33 wording 'new network <ip>, waiting for platform approval' exactly"
  - "An unparsable or missing observed address on a tenant with no network is held new_network and learns nothing (the rule needs a real address to teach)"
  - "A hold whose approval finds the network already listed or the list full still admits the machine; the result carries networkAllowed false and the warning is logged"
  - "approve validates widenTo (and the observed address) before any write, and adds the network only after the status flip succeeded"

requirements-completed: [LIC-05]

coverage:
  - id: D1
    description: "The network decision uses only the server-observed address: uvicorn's trusted-proxy handling resolves the appended address for 127.0.0.1 and ::1 peers and ignores the header from others; the rule modules hold no header name and never the agent's own address claim"
    requirement: LIC-05
    verification:
      - kind: integration
        ref: "backend/tests/test_proxy_headers.py (4 ProxyHeadersMiddleware cases, test_the_rule_modules_hold_no_header_name_and_never_the_agents_own_report)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The first machine teaches the tenant a /32 (/128) learned network, a new machine from another address is held new_network with its sourceIp and a readable tenant notice, enrolled agents are never re-checked, the platform is exempt, a missing address is held and never learned, IPv4-mapped addresses compare as IPv4, concurrent first enrollments leave one network"
    requirement: LIC-05
    verification:
      - kind: integration
        ref: "backend/tests/test_network_rule.py (test_the_first_machine_teaches_*, test_a_new_machine_from_another_network_waits_*, test_an_enrolled_agent_is_never_checked_*, test_an_old_agent_build_sees_*, test_the_platform_organization_*, test_a_missing_observed_address_*, test_an_ipv4_mapped_*, test_two_concurrent_first_enrollments_*)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A platform decider approving a new_network hold allows the observed address or a validated widenTo (at most /24 or /48, containing the address, same version, no private range for a public address); bad ranges answer 422 and change nothing; a tenant admin gets 403; no free seat adds no network; bulk approve allows the exact address; duplicates and the 100-entry cap add nothing"
    requirement: LIC-05
    verification:
      - kind: integration
        ref: "backend/tests/test_network_rule.py (test_approving_a_new_network_*, test_widening_to_a_24_*, test_a_wide_or_foreign_range_*, test_a_hold_without_an_observed_address_*, test_a_range_is_refused_for_any_other_hold, test_no_free_seat_*, test_a_tenant_admin_cannot_approve_*, test_bulk_approve_*, test_approving_an_already_listed_network_*, test_allow_twice_*)"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-11-11
status: complete
---

# Phase 88 Plan 05: Allowed networks and the new_network hold Summary

**Each tenant now keeps allowed networks decided on the address the server observed: the first machine teaches a /32, a new machine from anywhere else waits Pending `new_network` for the Super Admin, and approving it allows that address or a validated /24 (/48) around it, while enrolled agents and the platform organization are never touched.**

## Accomplishments

- `network_rules.py` (120 lines, stdlib `ipaddress` only): normalizes addresses (IPv4-mapped IPv6 becomes IPv4), compares against stored CIDRs, validates `widenTo` per D-42, and writes through two atomic conditional `$push` updates (`learn_first` only when the list is empty, `allow` only when the cidr is absent and fewer than 100 entries).
- `hold_reasons.py` is the one home for reason codes and their tenant and older-build refusal texts, moved out of `pending_agents.py` (now 493 lines, was 490). Existing imports of `pending_agents.REASON_*` and `reason_text` still work.
- `license_rules.hold_reason` gained `source_ip` and `hostname`; the new_network step sits after the allowlist and before the sub-limits and claims the first address atomically (a lost race re-reads the winner's list).
- `register_agent` passes `request.client.host` and stores it as `sourceIp` on admitted agents.
- `pending_agents.approve(widen_to=...)` validates before any write, allows the network after the machine is admitted, names the cidr in the `agent.approved` audit detail; `ApproveBody.widenTo` exposes it; bulk approve allows the exact address.
- `test_proxy_headers.py` pins uvicorn's trusted-proxy semantics and scans the rule modules for header names and the agent's own address claim.

## Verification

- Task 1 command: 20 passed. Task 2 command: 88 passed and 1 failed (test_plan_tracer's old `allowedNetworks == []` assertion, deviation 1), 19 passed in test_plan_tracer after the fix. Task 3 command: 82 passed. All with 0 skipped on the private mongod at 127.0.0.1:27998.
- Plan-level: test_route_auth_baseline, test_catalogue_route_parity plus every suite that registers agents or calls `hold_reason` (test_licensing, test_partner_expiry, test_agent_registry_regression_1, test_agent_location_history_wiring, test_agent_identity, test_itam_lifecycle*, test_audit_ledger, test_rust_heartbeat_parity, partner/platform role suites): 251 + 242 passed, 0 failed.
- Acceptance greps: `forwarded|x-real` 0 in network_rules.py; 4 definitions (validate_widen, learn_first, allow, contains); `_REASON_TEXT = {` / `_REFUSAL_TEXT = {` 0 in pending_agents.py; `REASON_NEW_NETWORK` 4 in hold_reasons.py; `source_ip=` 1 in agent_registry_endpoints.py; `publicIp` 0 in license_rules.py and network_rules.py; widenTo 3 in pending_agent_endpoints.py; network_rules.allow/validate_widen 2 in pending_agents.py; pending_agents.py 493 and hold_reasons.py 51 lines (under 500).
- Not run: `test_service_desk_notification_audience.py` errors with PermissionError on /var/lib/omni-platform (the known environmental failure, unrelated).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Older suites enrolled new machines with no observed address, which the new rule now holds**
- **Found during:** plan-level verification
- **Issue:** `test_licensing`, `test_agent_registry_regression_1` built a `Request` with no client, `test_partner_expiry` called `hold_reason` with no `source_ip`, `test_agent_location_history_wiring` used TestClient's `testclient` host, and `test_plan_tracer` asserted `allowedNetworks == []` after the first enrollment. Under the plan's own edge rule (a missing or unparsable address is held `new_network`) these all turned into new_network holds.
- **Fix:** their fixtures carry the address 203.0.113.7; the plan-tracer assertion now expects the learned `203.0.113.7/32`. Production behavior is as the plan specifies.
- **Files modified:** backend/tests/test_licensing.py, test_partner_expiry.py, test_agent_registry_regression_1.py, test_agent_location_history_wiring.py, test_plan_tracer.py
- **Commits:** 9da878acd (plan tracer), c3dfc7cdb (the other four)

**2. [Rule 1 - Bug] The plan's tenant text and its own behavior list disagreed**
- **Issue:** the text "it enrolled from a new network ({ip}), waiting for platform approval" puts parentheses around the address, so the notice would not contain "new network <ip>, waiting for platform approval" as the must-have and D-33 state.
- **Fix:** the text is "it enrolled from a new network {ip}, waiting for platform approval".
- **Commit:** 9da878acd

**3. [Process] Task 3 code was written before its tests**
- The approve and endpoint changes were in the working tree when the Task 3 tests were written, so the test commit (bb2d8f8d6) precedes the code commit (4478ccfc8) in history but was not observed failing against HEAD. Tasks 1 and 2 followed RED then GREEN with the failures observed (collection error; 9 failed).

**4. [Rule 3 - Blocking] The harness's limiter patch races under asyncio.gather**
- Two concurrent `harness.register` calls restore the shared `limiter.enabled` flag as the first finishes, breaking the second inside slowapi. The concurrency tests wrap both calls in one outer `harness.register_patches` scope; the harness itself is unchanged.

**Total deviations:** 2 auto-fixed bugs, 1 blocking test-setup fix, 1 process note. **Impact:** none on scope.

## Commit hygiene

`backend/tests/test_agent_location_history_wiring.py` already carried the user's uncommitted asset-mock hunk; only the one-line TestClient change was staged (blob written with `git hash-object`, `git update-index --cacheinfo`), so the user's 5 lines stay uncommitted. All other touched files were clean before this plan. No Co-Authored-By trailer on any commit (checked).

## Known Stubs

None.

## Threat Flags

None. T-88-12 (request.client.host only; proxy trust pinned by test_proxy_headers; source scan forbids header names and the agent's own address claim in the rule modules), T-88-13 (validate_widen: contains the observed address, at most /24 or /48, same version, public address needs a public range, 7 refusal cases tested), T-88-14 (`_require_decider` unchanged; tenant admin gets 403 with the list unchanged), T-88-15 (atomic guarded `$push`, 100-entry cap tested, lost learn race re-reads) are implemented and tested.

## Open item handed to the user (A-88-A1, PROH-88-03)

The rule is only as trustworthy as the uvicorn flags. `start-all-services.sh` (the user's uncommitted work) must run uvicorn with `--proxy-headers --forwarded-allow-ips 127.0.0.1` (or `127.0.0.1,::1`) so `request.client.host` is the address nginx appended; without it every request looks like it comes from 127.0.0.1 and the first machine would teach `127.0.0.1/32`. This plan did not touch that script; 88-16 hands it to the user. Nothing here is deployed: the backend must be restarted by the user.

## Next

Ready for 88-06 and 88-07 (which adds `cross_tenant_duplicate` ahead of `not_allowlisted` in `hold_reason`). The Pending screen and notice text for `new_network` (and the Approve widenTo control) are a later UI plan; the backend API fields are `ApproveBody.widenTo`, result `networkAllowed` / `network`, and refusal codes `widen_only_for_new_network`, `no_observed_address`.

## Self-Check: PASSED

- backend/network_rules.py, hold_reasons.py, tests/test_network_rule.py, tests/test_proxy_headers.py found on disk.
- Commits 06101d69e, 4b563430c, c2e057f14, 9da878acd, bb2d8f8d6, 4478ccfc8, c3dfc7cdb are ancestors of HEAD.
