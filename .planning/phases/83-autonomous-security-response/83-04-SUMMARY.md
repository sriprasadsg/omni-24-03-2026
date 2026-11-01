---
phase: 83-autonomous-security-response
plan: 04
subsystem: autonomous-ops
tags: [rust-agent, block-ip, expiry, sweeper, net-safety, cidr, firewall, tdd]
status: complete

requires:
  - phase: 83-02
    provides: privileged seam, response_state.json claims, firewall plans, block_ip/unblock_ip
provides:
  - response_state::expire_due, reapply_live, start_up (PassReport), time passed as a parameter
  - response_sweeper (spawned through response_actions::spawn_sweeper before registration), 15 s loop, start-up pass first
  - capabilities/net_safety.rs: is_global_address, parse_network, parse_target, network_contains, route and DNS parsers, host_addrs, refuse_reason
  - firewall::Target (address or network) accepted by every plan and apply function
  - block_ip / unblock_ip parameter cidr; token block_ip_range reported in every heartbeat
  - RemediationError::BlockedByLocalSecurity and outcome blocked_by_local_security
affects: [83-05, 83-08, 83-09, 83-10, 83-12, 83-16, 83-17]

requirements-completed: []
requirements-partial: [RESP-02]

actuals:
  tokens: 19400
  tasks: 2
  commits: 4
plan_head_before: 502c101344e5c76c8428dfe01bd7c65d7859939c
plan_head_after: 42c068609e40e5e29bc12b97c1a4afe9a42b518d

tech-stack:
  added: []
  patterns:
    - "Expiry is a pure function of (store, os, now); the loop is a thin tokio task around it, with the pass body injected so the loop is tested with a panicking closure"
    - "A claim's key is the normalised target text (an address, or a network with host bits cleared); the same text is parsed back by net_safety::parse_target at expiry"
    - "Host gateway and DNS come through host_addrs(os); under cfg(test) it answers a thread-local, never this machine's files"
    - "Classification of security-product refusals is two pure functions in privileged.rs; the recorder can script a spawn failure with a raw OS code"

key-files:
  created:
    - agent-install/omni-agent-rs/src/capabilities/net_safety.rs
    - agent-install/omni-agent-rs/src/capabilities/net_safety_tests.rs
    - agent-install/omni-agent-rs/src/capabilities/response_sweeper.rs
    - agent-install/omni-agent-rs/src/capabilities/response_state_expiry_tests.rs
    - agent-install/omni-agent-rs/src/capabilities/firewall_range_tests.rs
    - agent-install/omni-agent-rs/src/capabilities/response_actions_tests.rs
  modified:
    - agent-install/omni-agent-rs/src/capabilities/response_state.rs
    - agent-install/omni-agent-rs/src/capabilities/response_actions.rs
    - agent-install/omni-agent-rs/src/capabilities/firewall.rs
    - agent-install/omni-agent-rs/src/capabilities/privileged.rs
    - agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs
    - agent-install/omni-agent-rs/src/capabilities/response_contract_tests.rs
    - agent-install/omni-agent-rs/src/capabilities/mod.rs
    - agent-install/omni-agent-rs/src/lib.rs

key-decisions:
  - "Non-global addresses are now refused by the agent, including RFC 1918. This reverses 83-02's choice that private ranges stay blockable; the plan's truth for 83-04 says refuse anything that is not globally routable. A host on a private network can no longer be blocked by this command."
  - "A failed start-up re-apply (iptables not ready early in boot) is retried on every later pass until it works. The plan only asked for one start-up pass; without the retry a block a reboot lost would stay lost until its claim expired."
  - "The loop treats a panicking pass as 'not done': the start-up pass repeats until it has run once without panicking."
  - "ip_address together with cidr, or neither, is refused rather than guessed."
  - "Gateway and DNS unreadable: the block goes on with a log warning (A-83-GW). The Windows reads use route print -4 and netsh interface ipv4/ipv6 show dnsservers through the privileged seam; Linux reads /proc/net/route, /etc/resolv.conf and /run/systemd/resolve/resolv.conf."

duration: one sequential run (RED, GREEN, mutation checks, committed-tree build)
completed: 2026-11-01
---

# Phase 83 Plan 04: Blocks end on their own, and cannot cut the host off Summary

A block now ends at its time with the platform unreachable, the agent stopped and started, or the host rebooted; the agent refuses by itself any address or network that would cut the host off; an approved range works under the same claim rules; and a security-product refusal has its own name.

## What was built

**Task 1, expiry (commits e240827cb RED, 92fef1d2c GREEN).**
- `response_state.rs`: `expire_due(store, os, now)`, `reapply_live(...)`, `start_up(...)`, each returning a `PassReport {removed, dropped, reapplied, failed, error}`. The whole pass runs inside one `Store::update`, so a `block_ip` cannot interleave with a removal. A claim expires when `expires_at <= now`. An address with another unexpired claim loses only the expired claim and runs no command. A failed removal keeps its claim for the next pass and does not hold back other addresses. A corrupt state file is logged, reported in `error`, and the file is left byte for byte as it was.
- `response_sweeper.rs`: `spawn` starts a tokio task that runs `start_up` once, then `expire_due` every 15 seconds through `spawn_blocking`; a panic inside a pass comes back as a join error, is logged, and the loop continues. It stops when the stop channel turns true. It reads only the state file and the local firewall.
- `lib.rs`: `spawn_sweeper(stop_rx.clone())` sits after config load and identity adoption (line 46) and before the first `ensure_registered` (line 94). `response_actions::spawn_sweeper` is a three-line wrapper.
- Linux start-up re-applies unexpired claims; Windows start-up issues no add command and removes only expired ones.

**Task 2, net safety, ranges, security refusal (commits 80f92f9c8 RED, 42c068609 GREEN).**
- `net_safety.rs` (306 lines): hand-written `is_global_address` for the exact classes in the plan (a v4-mapped address is unwrapped first); `parse_network` with std only (digits-only prefix, no sign, space or leading zero; host bits cleared; mapped /96+ networks become IPv4); `network_contains`; four parsers; `refuse_reason(target, cfg, os, lookup)` which refuses, in order: not global, wider than /8 (IPv6 /32), covers the platform (IP literal in `api_base_url`, or its name through the injected lookup), covers the gateway or a DNS server.
- `firewall.rs`: a `Target` (address, or network with prefix) now flows through every plan and apply function; `-s`/`-d` and `remoteip` take the CIDR text; Windows rule names replace "/" with "_".
- `response_actions.rs`: `cidr` parameter on `block_ip` and `unblock_ip`; `refuse_reason` runs before any state write; `block_ip_range` added to `SUPPORTED_TOKENS`; `failed()` turns `BlockedByLocalSecurity` into `outcome: blocked_by_local_security` and nothing retries it.
- `privileged.rs`: Windows spawn errors 5, 225 and 4551, and stderr naming a virus, "potentially unwanted software", "blocked by group policy" or an "application control policy", become `BlockedByLocalSecurity`. The raw codes count only on Windows.

## Sample outputs the parsers were tested against

`/proc/net/route` (this VM's own file, plus a second default route):
```
Iface	Destination	Gateway 	Flags	RefCnt	Use	Metric	Mask		MTU	Window	IRTT
eth0	00000000	0100000A	0003	0	0	100	00000000	0	0	0
eth0	0000000A	00000000	0001	0	0	100	00FFFFFF	0	0	0
eth0	0100000A	00000000	0005	0	0	100	FFFFFFFF	0	0	0
eth1	00000000	0201A8C0	0003	0	0	200	00000000	0	0	0
```
gives `[10.0.0.1, 192.168.1.2]` (the gateway column is little-endian hex; only rows with destination and mask `00000000` count).

resolv.conf (the first stanza is this VM's own `/run/systemd/resolve/resolv.conf` plus extra lines):
```
# This is /run/systemd/resolve/stub-resolv.conf
nameserver 127.0.0.53
options edns0 trust-ad
search internal.cloudapp.net

nameserver 168.63.129.16
nameserver   2001:4860:4860::8888  
#nameserver 9.9.9.9
nameserver not-an-address
```
gives `[127.0.0.53, 168.63.129.16, 2001:4860:4860::8888]`.

`route print -4` (Windows layout; a hand-written sample, not captured from a real Windows host):
```
IPv4 Route Table
Active Routes:
Network Destination        Netmask          Gateway       Interface  Metric
          0.0.0.0          0.0.0.0       10.1.2.1      10.1.2.55     25
        127.0.0.0        255.0.0.0         On-link         127.0.0.1    331
Persistent Routes:
  Network Address          Netmask  Gateway Address  Metric
          0.0.0.0          0.0.0.0       10.1.2.254  Default
          0.0.0.0          0.0.0.0          On-link  Default
```
gives `[10.1.2.1, 10.1.2.254]`.

`netsh interface ipv4 show dnsservers` (hand-written sample of the same layout):
```
Configuration for interface "Ethernet"
    DNS servers configured through DHCP:  10.1.2.1
                                          10.1.2.2
Configuration for interface "Loopback Pseudo-Interface 1"
    Statically Configured DNS Servers:    127.0.0.1
                                          fec0:0:0:ffff::1%1
```
gives `[10.1.2.1, 10.1.2.2, 127.0.0.1, fec0:0:0:ffff::1]` (every address in the output is taken; over-refusing is the safe side).

Recorded commands for a range, Linux and Windows (tests `linux_blocks_a_network_with_one_source_and_one_destination_rule`, `windows_names_a_network_rule_with_an_underscore_and_gives_the_cidr_to_remoteip`):
```
iptables -w -A OMNI_BLOCK -s 45.33.32.0/24 -j DROP
iptables -w -A OMNI_BLOCK -d 45.33.32.0/24 -j DROP
netsh advfirewall firewall add rule name=OmniAgent_Block_45.33.32.0_24_in dir=in action=block remoteip=45.33.32.0/24
netsh advfirewall firewall add rule name=OmniAgent_Block_45.33.32.0_24_out dir=out action=block remoteip=45.33.32.0/24
```

## Verification

Recipe used for every cargo run: the run notes' recipe (`CARGO_BUILD_JOBS=1`, `CARGO_TARGET_DIR=$PWD/agent-install/omni-agent-rs/target/nodebug`, `CARGO_PROFILE_DEV_DEBUG=0`, `CARGO_PROFILE_TEST_DEBUG=0`, `--offline`), not the plan's bare commands. No link stall.

- Working tree, `--lib -- response_ firewall privileged remediation_actions selection_tests net_safety interval_tests`: 144 passed. `--test remediation_dispatch_test`: 5 passed (this builds the library without cfg(test), so the real `run_output`, `read_host_addrs` and `system_lookup` compile).
- The committed tree alone (`git archive HEAD` into a scratch directory, no uncommitted user hunks): `--lib -- response_ firewall privileged net_safety` 120 passed.
- No test made a real firewall, service or process call. The only reads of this machine are in `read_host_addrs`, which no test calls (tests get a thread-local); its three file paths and two commands are not covered by a unit test. Linux reading was checked by eye against this VM's `/proc/net/route` and resolv.conf, which are the Linux samples above.
- Line counts: net_safety.rs 306, response_actions.rs 247, firewall.rs 495, response_state.rs 468, response_sweeper.rs 173, privileged.rs 202, all under 500. Acceptance greps: `spawn_sweeper` in lib.rs 1, at line 46 before `ensure_registered` at line 94; `expire_due` in response_state.rs more than 2; `refuse_reason` in response_actions.rs 2; `block_ip_range` 2; `BlockedByLocalSecurity` in privileged.rs 5.
- No `gzip`, `post_json`, `collect_due`, `collection_intervals` or `update_intervals` line is in any of the four commits. mod.rs and lib.rs were committed with filtered patches (`git apply --cached`); the remaining mod.rs diff is the user's hunks only.

## TDD: RED and GREEN evidence

| Task | RED commit | RED evidence | GREEN commit |
|------|-----------|--------------|--------------|
| 1 | e240827cb | `--lib -- response_state response_sweeper`: 14 failed, 15 passed. The 14 are assertion failures on the planned behaviour (for example `left: [] right: ["45.33.32.156"]` for the removed list, `assertion failed: store.load().unwrap().claims.is_empty()`, `the loop must keep going after a panic`). It compiled; it was not an ImportError. The 15 that passed are the old tests plus no-op cases (empty list, missing file, Windows re-apply) that a stub satisfies. | 92fef1d2c |
| 2 | 80f92f9c8 | 3 groups failed on assertions: 16 net_safety tests, 3 privileged tests, 10 response_actions tests, 1 contract test (`support_names_the_platform...`), for example `assertion failed: !is_global_address(ip("::ffff:10.0.0.1"))` and `SUPPORTED_TOKENS.contains(&"block_ip_range")`. All compiled. | 42c068609 |

Caveat on RED 2: `Target` and the generic plan functions in firewall.rs, the `BlockedByLocalSecurity` variant and the recorder's `fail_spawn` are real code in the RED commit (the stubs could not compile without them), so `firewall_range_tests.rs` and `a_target_is_an_address...` passed at RED. They were never red. The RED commit's `spawn_failure` stub was a deliberately meaningless body.

Mutation checks (mutate, run, see failure, restore; every file restored and re-tested):

| # | File | Mutation | Failed |
|---|------|----------|--------|
| M1 | net_safety.rs | multicast/reserved edge `a0 >= 224` to `225` | `every_listed_ipv4_class_is_refused_at_both_edges` |
| M2 | response_state.rs | expiry `<= now` to `< now` | 5 tests incl. `a_claim_that_expires_exactly_now_is_removed_with_its_rule` |
| M3 | response_state.rs | forget the claim even when the removal failed | `a_failed_removal_keeps_the_claim_and_the_next_pass_clears_it`, `one_failing_address_does_not_hold_back_another` |
| M4 | net_safety.rs | platform check disabled | `the_platform_host_is_refused_as_a_literal_mapped_or_resolved_name`, `a_network_is_refused_when_it_holds_the_platform...` |
| M5 | privileged.rs | code 225 changed to 226 | `the_windows_codes_for_a_security_block...`, `the_test_seam_can_script_a_spawn_failure` |

One slip worth recording: after M5 was restored with `mv`, cargo kept the old mutated binary because the restored file kept its older timestamp, and one run showed 3 failures that were that stale build. Touching the three files and rerunning gave 144 passed.

TTL boundaries 3600, 604800 (accepted) and 3599, 604801 (refused) are covered by 83-02's tests, which still pass in the moved test file; no new TTL test was written.

## Deviations from Plan

**1. [Rule 3 - Blocking, file not in plan] `RemediationError::BlockedByLocalSecurity` added in `remediation_actions.rs`.** The enum lives there, not in privileged.rs. Three lines. The plan's grep (`BlockedByLocalSecurity` at least 2 times in privileged.rs) is met by the mapping and its tests.

**2. [Rule 3 - 500-line rule, files not in plan] New files.** `response_sweeper.rs` (the loop and pass, so response_actions.rs and response_state.rs stay under 500), `response_actions_tests.rs` (the old inline tests moved out together with the new ones), `response_state_expiry_tests.rs`, `firewall_range_tests.rs`, `net_safety_tests.rs` (each included through `#[path]`, so test names still contain `response_state`, `firewall`, `net_safety`). `response_actions::spawn_sweeper` exists as the plan names it and calls into `response_sweeper`. `mod.rs` got two registration lines (`net_safety`, `response_sweeper`), as the plan lists mod.rs.

**3. [Rule 2 - Missing critical] Start-up re-apply retry.** See key-decisions. The retry state is one `AtomicBool` in the sweeper closure.

**4. [Scope reversal] RFC 1918 and other non-global addresses are now refused.** 83-02 deliberately kept private addresses blockable. This plan's truth overrides it; the old test list in `addresses_that_cannot_be_blocked_are_refused` was left as it was and a new test covers the private classes.

**5. [Plan signature] `refuse_reason` takes `os` as an extra argument** (`refuse_reason(target, cfg, os, lookup)`) so it can read the right gateway and DNS sources.

No Rule 4 stops. No package installed.

## Honesty notes

- The Windows paths (`route print`, `netsh ... show dnsservers`, the raw codes 5/225/4551, `OmniAgent_Block_..._24_in` rules and `remoteip=<cidr>`) are tested only on Linux against hand-written samples and the recorder. Assumption A-83-A1 (Defender does not block netsh from the service) and the netsh CIDR syntax are untested on a real Windows host.
- Error 5 (access denied) mapping to "blocked by local security" can also come from an agent that lacks rights; the plan accepts that mapping.
- `system_lookup` is a blocking DNS call and runs inside the async `handle` (as the firewall commands already do). It only runs when `api_base_url` is a name; a failing lookup logs a warning and the block goes on.
- If the state file is corrupt, the sweeper logs an error every 15 seconds and removes nothing; live rules stay until someone repairs the file. This follows the plan ("a corrupt state file makes the pass log an error and change nothing").
- Expiry compares the host clock (T-83-14 accepted).

## User-visible sentences not in the UI-SPEC

These go in `error` strings the backend or a person may read. None is a UI string, and 83-03's `response_messages.py` words the outcome `blocked_by_local_security` ("Security software on the computer blocked this action."), which is what the operator sees.

- "That address is not on the public internet and is never blocked."
- "That network is wider than the agent will block."
- "That includes the platform's address and is never blocked."
- "That includes this computer's gateway or a DNS server and is never blocked."
- "Give either ip_address or cidr, not both."
- "cidr is not a valid network."
- "Security software on this computer blocked the command: <program> ..." (the error text for `blocked_by_local_security`)

## Known Stubs

None. `isolation` and `quarantine_index` of `response_state.json` stay declared and unused, as in 83-02.

## Requirements

RESP-02 not ticked. The agent half is complete here; the backend half (83-08, 83-10) is not done. 83-01..03 also list it.

## Cross-plan facts for the orchestrator

- The agent now refuses every non-global address, so the backend never-touch list and the agent can disagree for private addresses: the backend may approve a block of a private host and the agent will answer `refused`. 83-08/83-10 should treat `refused` as final, not as a failure for the breaker.
- Range claims are keyed by the normalised network text (`45.33.32.0/24`). An `unblock_ip` for a range must send `cidr` (not `ip_address`) and the same `block_id`.
- `meta.response_actions.tokens` is now `["block_ip_ttl", "block_ip_range"]` on Linux and Windows. The shared contract already lists `block_ip_range`.
- Nothing removes a block on the backend at expiry (D-14); the backend must derive "ended" from `blockedUntil`.
- Not built, published or version-bumped. The agent still needs a release before any of this reaches a host; 83-02's note about the 24-hour default applies to the first published binary.

## Self-Check: PASSED

All six new source files exist; commits e240827cb, 92fef1d2c, 80f92f9c8 and 42c068609 are ancestors of HEAD; `git rev-list --count 502c10134..HEAD` printed 4 before this SUMMARY.
