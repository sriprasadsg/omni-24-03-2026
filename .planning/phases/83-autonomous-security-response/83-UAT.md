---
status: complete
phase: 83-autonomous-security-response
source: [83-VERIFICATION.md]
started: 2026-11-02T12:55:00Z
updated: 2026-11-07T14:08:09.637Z
---

## Current Test

[testing complete]

## Tests

### 1. DECISION BEFORE PUBLISHING 2.1.16: fix Rust CR-01 (no child-process timeout while WRITE_LOCK / isolation LOCK are held, privileged.rs:58-68) and CR-02 (net_safety.rs:281-302 tests only a CIDR's base address, so 172.0.0.0/8 and 192.0.0.0/8 pass), or consciously accept them
expected: A gap-closure plan (or a quick fix) lands both, with tests: a hung child is killed after a deadline and the pass returns an error; a network that overlaps any non-global range is refused by the agent (and by backend signals.global_range, which has the same flaw)
result: pass

### 2. Read the sentences the UI-SPEC does not word (83-20 Live list item 1) and confirm A-83-LEVEL-SUGGEST (item 2: which Suggest-level rows appear as approvable lines)
expected: Wording accepted, or edited, before the UI is published
result: pass
note: "2026-11-05: the user accepted the plan-written wording and A-83-LEVEL-SUGGEST as built."

### 3. Accept the two agent behaviour changes before publishing 2.1.16 (item 3): a block_ip with no ttl_seconds lasts 24 hours; the agent refuses every non-global address (RFC 1918 included), the platform host, gateway, DNS servers and networks wider than /8
expected: Accepted
result: pass
note: "2026-11-05: the user accepted both behaviour changes (24-hour default block; refusal of non-global, platform, gateway, DNS and wider-than-/8 targets) before 2.1.16 is published."

### 4. Publish the UI (dist-new index-VUPN-kZs.js) and then agent 2.1.16 with _LATEST_AGENT_VERSION bumped from 2.1.14; confirm meta.response_actions tokens arrive from a test host (items 4-5)
expected: Cards, Undo and settings render; heartbeat carries tokens block_ip_ttl, block_ip_range, quarantine_file, unquarantine_file, kill_process_exe, restart_service, service_failures, isolate_host, restore_host, reboot_host; RESP-10 can then be ticked
result: pass
note: "Passed by the user 2026-11-07. On this VM the live UI is index-uy_SL0y8.js (2026-11-05) and the committed _LATEST_AGENT_VERSION is still 2.1.14, so the agent publish and token check were not done from this server."

### 5. Lift one tenant out of shadow and watch what the sweep does; set ABUSE_CH_AUTH_KEY, restart the backend and count edr_ioc by source_feeds (items 6-7)
expected: Simulation rows only while in shadow; automatic block/quarantine stay uncommon until two real origins exist (A-83-SCAN, A-83-ONHOST); with the key set the public-feed origin gets rows
result: pass
note: "Passed by the user 2026-11-07."

### 6. Firewall round trip on real Linux (beside ufw or firewalld) and on EILT0197 with Defender on, IPv4 and IPv6, both directions, using a routable address such as 45.33.32.156 (item 8)
expected: Rule exists after block (verify check firewall_rule_present), traffic is dropped, Undo removes it; no Defender interference
result: pass
note: "Passed by the user 2026-11-07."

### 7. A 1-hour block expiring while the host is offline, across an agent restart and a reboot (item 9)
expected: Rule gone at expiry without any platform contact; backend row unchanged
result: pass
note: "Passed by the user 2026-11-07."

### 8. Quarantine and restore of a running harmless test binary on Windows, including the kill-only card (item 10)
expected: Correct one of 'still running' or 'locked'; kill card ends the process before the row reads Done; restore returns the file; quarantine directory ACL checked
result: pass
note: "Passed by the user 2026-11-07."

### 9. Isolation on a throwaway host with a shortened revert first (item 11), including a reboot while isolated and a Group Policy firewall
expected: Management connection stays open; host really is cut off from everything else (review WR-20: the agent's own verify does not test this); automatic revert and Confirm isolation work; a host with a missing state file does not stay isolated (WR-17)
result: pass
note: "Passed by the user 2026-11-07."

### 10. Capture real Windows output (sc, netsh, route print, error codes 5, 225, 4551) on EILT0197 and compare with the parser fixtures; check Defender history for netsh/sc/shutdown spawned by the agent (items 12, 14)
expected: Parsers match; no blocked_by_local_security; written exclusion guidance produced (open threat T-83-15)
result: pass
note: "Passed by the user 2026-11-07."

### 11. Crash and stop a test service on both operating systems (item 13)
expected: Only the crash restarts it; an administrator stop does not
result: pass
note: "Passed by the user 2026-11-07."

### 12. Browser pass of cards, Undo and settings, light and dark, 640/1024/1280 px, no sideways scroll at 1280 (item 15)
expected: Matches 83-UI-SPEC; 83-UI-REVIEW warnings (role=status on li, SwarmDashboard dark style, 16px checkboxes) decided
result: pass
note: "Passed by the user 2026-11-07."

### 13. Decide the open known defects (items 16-17): the over-budget restart card stays approvable after the service recovers (WR-03); remediation_service.py still marks a vulnerability Patched after a worker task answering not_sent (A-83-PATCHED, T-83-27)
expected: Fixed, deferred to a later phase, or accepted
result: pass

## Summary

total: 13
passed: 13
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
