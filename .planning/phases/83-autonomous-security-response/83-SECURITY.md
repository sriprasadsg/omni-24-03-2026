---
phase: "83"
slug: "autonomous-security-response"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-02"
---

# Phase 83 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| agent -> backend result route | Agent-supplied result fields are untrusted | see 83-01 threat model |
| agent -> backend scan and heartbeat routes | The path name is whatever the agent posted, and the agent's token binds it | see 83-01 threat model |
| sweep -> gate -> agent queue | The only way an automatic action reaches a host | see 83-01 threat model |
| backend instruction -> agent running as SYSTEM or root | Parameters reach privileged commands | see 83-02 threat model |
| local disk -> agent | The state file decides what the agent removes | see 83-02 threat model |
| ledger row -> browser | Paths, hostnames and reasons include agent-reported text | see 83-03 threat model |
| viewer role -> row flags | canUndo decides whether a control renders | see 83-03 threat model |
| backend instruction -> agent firewall | The address or network decides what the host can reach | see 83-04 threat model |
| host clock -> expiry | Expiry compares the host's own clock | see 83-04 threat model |
| public feeds -> edr_ioc | Global, third-party, can be wrong | see 83-05 threat model |
| agent telemetry -> sweep | A compromised host chooses what it reports | see 83-05 threat model |
| one tenant -> shared collections | Feed rows are global, tenant rows are not | see 83-05 threat model |
| LLM mission plan -> agent queue | Model output must never choose containment | see 83-06 threat model |
| any backend writer -> agent poll | The poll is the last point where an unstamped command can be stopped | see 83-06 threat model |
| browser -> settings routes | A tenant admin's input reaches agents as service names | see 83-07 threat model |
| tenant role -> another tenant's settings | Tenant id comes from the token | see 83-07 threat model |
| agent heartbeat -> support decision | meta.response_actions is agent-reported | see 83-08 threat model |
| approval time -> dispatch time | Up to 24 hours can pass between them | see 83-08 threat model |
| backend instruction -> file system as SYSTEM or root | A path reaches a privileged move | see 83-09 threat model |
| time between decision and action | A path or PID can change meaning | see 83-09 threat model |
| quarantine directory -> restore | The manifest decides where a file returns | see 83-09 threat model |
| server row -> DOM | Hostnames, paths and reasons include agent-reported strings | see 83-10 threat model |
| browser -> undo route | A click is a recorded decision | see 83-10 threat model |
| agent-reported path and hash -> quarantine decision | A compromised host names what gets moved on itself | see 83-11 threat model |
| tenant playbook YAML -> class | A tenant may raise a class, never lower it | see 83-11 threat model |
| agent firewall -> management connection | The one path that must never close | see 83-12 threat model |
| heartbeat reply -> isolation state | The reply can keep a host isolated | see 83-12 threat model |
| tenant admin -> agent | Service names arrive through the heartbeat reply | see 83-14 threat model |
| heartbeat data -> sweep | Failure reports come from the host | see 83-14 threat model |
| agent reports -> row items | CVE ids, package names and paths are agent-supplied | see 83-15 threat model |
| agent result -> follow-up decision | A host's report can open a card, never act alone | see 83-16 threat model |
| agent report -> restart decision | The host reports its own failures | see 83-17 threat model |
| settings -> every agent of the tenant | The list goes out in the heartbeat reply | see 83-17 threat model |
| browser -> decision routes | Each click is a recorded decision | see 83-18 threat model |
| agent report -> ledger state | meta.response_state is agent-reported | see 83-18 threat model |
| server card -> DOM | Hostnames, process names and paths are agent-reported | see 83-19 threat model |
| repo -> published agent | Publishing is a person's step | see 83-20 threat model |

---

## Threat Register

Built from the `<threat_model>` blocks of all 20 plans (76 unique ids; T-83-SC repeats in 20 plans). Audited 2026-11-02 by gsd-security-auditor against the code on disk at a67453a8e, ASVS level 1 with level 2 checks on the high-severity rows; every cited file was identical to HEAD. Evidence (file:line and test names) is in the audit report summarised under the audit trail; the orchestrator re-checked a sample of the citations.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-83-01 | Tampering | verify.bounded_result | high | mitigate | Whitelisted keys, closed outcome and check lists from the contract, integer ranges, list and string caps; an unknown value becomes None | closed |
| T-83-02 | Spoofing | signals.resolve | high | mitigate | Resolution is per tenant and refuses when two agents share a hostname, so a finding can never reach another host or tenant (R7) | closed |
| T-83-03 | Tampering | undo claim id | medium | mitigate | block_id is read from the row's own instructionIds, never from a request, and dispatch_check.bind compares it with the recorded undo params | closed |
| T-83-04 | Repudiation | sweep decisions | medium | mitigate | gate.decide writes the row before dispatch and ledger._mirror writes the audit chain event | closed |
| T-83-05 | Denial of Service | sweep tick | medium | mitigate | One runner under a renewed lock, query limits, one tenant's exception logged and contained | closed |
| T-83-SC | Tampering | dependency installs | low | accept | This plan installs no package (83-RESEARCH Package Legitimacy Audit) | closed |
| T-83-06 | Elevation of Privilege | privileged seam | high | mitigate | One spawn helper, argv elements only, no shell, every parameter validated by the agent itself (R3) | closed |
| T-83-07 | Tampering | replayed instruction | medium | mitigate | Claim keyed by task id, a repeat returns already_applied and adds nothing (R6) | closed |
| T-83-08 | Tampering | response_state.json | medium | accept | The file sits in the admin-only install directory; a host admin can already change the firewall | closed |
| T-83-09 | Tampering | row text from agent data | medium | mitigate | Plain strings only, length caps at ingest, React text rendering; no HTML in any template (R11) | closed |
| T-83-10 | Elevation of Privilege | canUndo flag | medium | mitigate | The flag is display only; approvals.undo and _require_control remain the guard, and Platform Support gets false | closed |
| T-83-11 | Repudiation | one origin shown as two | high | mitigate | why_two_sources refuses fewer than two different origin ids, so the sentence cannot be built from one | closed |
| T-83-12 | Denial of Service | block of platform, gateway or DNS | high | mitigate | Agent-side refusal independent of the backend never-touch list, non-global refusal, range containment check (R4) | closed |
| T-83-13 | Elevation of Privilege | address and CIDR text | high | mitigate | Parsed to typed values before use, passed as one argv element (R3) | closed |
| T-83-14 | Tampering | host clock moved to keep a block | low | accept | Only a host admin can do it, and that admin can already change the firewall (R13) | closed |
| T-83-15 | Denial of Service | local AV blocks netsh | medium | mitigate | Distinct outcome, no automatic retry, documented exclusions in UAT (R12) | open — below high threshold (non-blocking): the code half exists (`blocked_by_local_security`, no retry); the written exclusion guidance does not, pending live item 14 of the 83-20 list |
| T-83-16 | Tampering | feed false positive blocks a good address | high | mitigate | Two different origins by default, is_global filter, 48-hour freshness, host binding, TTL, rate limit, breaker (R1) | closed |
| T-83-17 | Spoofing | one host reporting both origins | medium | mitigate | Mirrored alerts collapse to their source, per-host cap of 3 an hour, actions bound to the reporting host; residual: a compromised host can spend its own 3 actions (R2) | closed |
| T-83-18 | Information Disclosure | global versus tenant IOC rows | high | mitigate | Raw handle, tenantId absent filter, two-tenant tests (R7) | closed |
| T-83-19 | Spoofing | unauthenticated honeytoken webhook | high | mitigate | No deception reader exists, and a test keeps it that way (R9) | closed |
| T-83-20 | Information Disclosure | ABUSE_CH_AUTH_KEY | high | mitigate | Read from the environment, sent only as a header to abuse.ch, never logged, never committed | closed |
| T-83-25 | Elevation of Privilege | unstamped gate-only command | high | mitigate | delivery refuses it at every poll, whatever wrote it, and a test covers both stamped and unstamped rows | closed |
| T-83-26 | Tampering | swarm mission plan from an LLM | high | mitigate | isolate_host filtered from every plan just before dispatch | closed |
| T-83-27 | Repudiation | a success answer for nothing sent | medium | mitigate | not_sent status everywhere, agents.isolated no longer set, UI cannot show the green style | open — below high threshold (non-blocking): `remediation_service.py` `approve_and_execute` still marks the vulnerability Patched and the request Executed after a worker task that now answers `not_sent` (A-83-PATCHED, a known defect left for the user) |
| T-83-28 | Elevation of Privilege | XDR skipping the two-source rule | high | mitigate | Automatic executors only reach gate.suggest (D-25) | closed |
| T-83-21 | Tampering | twoSignal off | high | mitigate | Manage permission plus interactive session; control row and audit event per change; bulk needs the platform permission (R8) | closed |
| T-83-22 | Elevation of Privilege | watched service names | high | mitigate | Server regex, 50 limit, critical service refusal; the agent validates again (R3) | closed |
| T-83-23 | Spoofing | API key changing a safeguard | high | mitigate | _require_interactive_session refuses every key (D-10 of Phase 81) | closed |
| T-83-24 | Information Disclosure | cross-tenant read | medium | mitigate | views.resolve_tenant refuses a tenant naming another; two-tenant test | closed |
| T-83-29 | Spoofing | a host reports tokens it lacks | low | accept | A host can only misreport for itself; an unknown instruction fails on that host and the row ends failed | closed |
| T-83-30 | Denial of Service | breaker burned by plumbing | high | mitigate | Dormancy before decide, transparent reason codes, refused hold-back named capability_off (R2 residual) | closed |
| T-83-31 | Tampering | stale card fires later | high | mitigate | _revalidate re-runs the support check; expected_exe and sha256 guard the agent side (R5) | closed |
| T-83-32 | Denial of Service | range overlaps protected network | high | mitigate | check_network overlap test at decide, approve and dispatch; agent refuses too (R4) | closed |
| T-83-33 | Elevation of Privilege | approving a suggestion through the API | medium | mitigate | suggestion_only refusal before the compare-and-set | closed |
| T-83-34 | Elevation of Privilege | path parameter | high | mitigate | Absolute only, no .. segment, symlink refused, own files refused, protected prefixes, hash binding (R3) | closed |
| T-83-35 | Tampering | path reused after the decision | high | mitigate | sha256 must match at move time, else hash_mismatch and nothing moves (R5) | closed |
| T-83-36 | Tampering | PID reused before an approved kill | high | mitigate | plan_kill needs the listed pid and start_time, or the stored image; a reused PID with an unrelated image is never signalled, and one that reports the original path goes in unconfirmed (R5) | closed |
| T-83-37 | Tampering | restore to a chosen path or over a file | high | mitigate | Destination from the manifest only, refuses an existing target and a linked directory, re-checks the hash (R10) | closed |
| T-83-38 | Elevation of Privilege | quarantined file executed | medium | mitigate | Stored mode 000 and no executable extension; restore never starts anything (V10) | closed |
| T-83-74 | Repudiation | kill result while the process is alive | high | mitigate | plan_kill puts any named process it cannot bind in unconfirmed, kill_body answers verify ok true only with no survivor and no unconfirmed entry, and survivors are matched by pid and start_time after a bounded wait | closed |
| T-83-75 | Spoofing | Windows exe read from the target's own memory | medium | accept | A process can rewrite its module path. Hiding before the listing means no card; hiding after it lands in unconfirmed. Either way the failure direction is no kill and no false Done. The live test records the real behaviour | closed |
| T-83-39 | Tampering | agent strings in the DOM | medium | mitigate | React text only, no HTML rendering, targets never linkified; only the two fixed links navigate (R11) | closed |
| T-83-40 | Elevation of Privilege | Undo shown to a viewer | low | mitigate | Rendered from canUndo; the route still enforces control and an interactive session | closed |
| T-83-41 | Tampering | double click | low | mitigate | Ref guard plus disabled state; approvals.undo is compare-and-set | closed |
| T-83-46 | Denial of Service | quarantine of a system file | high | mitigate | Protected paths need a card on both sides, and the agent refuses without allow_protected | closed |
| T-83-47 | Spoofing | incident split or merged by forged evidence | low | accept | Host-bound and per tenant; the worst case is one more or one fewer card on the reporting host | closed |
| T-83-48 | Elevation of Privilege | a class lowered by a playbook | high | mitigate | registry.playbook_raises can only raise, and isolate_host stays approve in the registry | closed |
| T-83-49 | Tampering | path traversal in a protected check | medium | mitigate | Normalised before matching; the agent re-checks on its own | closed |
| T-83-42 | Denial of Service | isolation cuts the agent | high | mitigate | Write-ahead state, allow rules verified before any block, self-test, immediate revert, agent-held timer, startup revert (R4) | closed |
| T-83-43 | Denial of Service | lost or corrupt state while isolated | high | mitigate | Start-up removes isolation rules when state is unreadable: fails open for the network | closed |
| T-83-44 | Tampering | forged isolationConfirmed | medium | mitigate | Only the pinned TLS platform reply reaches it; the id must equal the active isolation id | closed |
| T-83-45 | Tampering | Group Policy overrides local rules | medium | mitigate | not_effective outcome and revert, so the card never reads done when the host is not isolated | closed |
| T-83-54 | Tampering | loosening by accident | medium | mitigate | Dialog before writing; a required checkbox in bulk; the server records the change (R8) | closed |
| T-83-55 | Elevation of Privilege | panel shown to a non-holder | low | mitigate | Hidden in the UI, refused by the server | closed |
| T-83-50 | Elevation of Privilege | service name in argv | high | mitigate | Character rule, leading hyphen refused, critical list, one argv element; validated at server and agent (R3) | closed |
| T-83-51 | Denial of Service | a restart loop on a host | medium | mitigate | Backend budget plus a 60-second grace and a 60-second report cache on the agent | closed |
| T-83-52 | Spoofing | a false failure report | low | accept | A host can only ask to restart its own listed service, within budget | closed |
| T-83-53 | Elevation of Privilege | reboot reason text | low | mitigate | Length cap, control characters removed, one argv element | closed |
| T-83-56 | Denial of Service | row growth from noisy hosts | medium | mitigate | One row per host and kind, 10 items, read limit, no write on no change | closed |
| T-83-57 | Tampering | agent strings in items | low | mitigate | Length caps on items, rendered as text (R11) | closed |
| T-83-58 | Spoofing | FIM event as an origin | high | mitigate | FIM events never write autonomy_signals; a test asserts it (D-08) | closed |
| T-83-59 | Elevation of Privilege | forged locked result leads to a kill | medium | mitigate | A kill needs a person's approval, and the params bind it to the listed pid and start_time, the quarantined path and the stored image; bounded_result caps the list | closed |
| T-83-60 | Denial of Service | endless retry loop | medium | mitigate | parentActionId stops after one retry; the rate limit and breaker apply | closed |
| T-83-61 | Repudiation | Undone shown for a failed undo | medium | mitigate | The row returns to its real state with undoFailed recorded | closed |
| T-83-62 | Denial of Service | restart storm from a false report | medium | mitigate | Budget from the ledger, wait ladder, tenant rate limit; only listed services | closed |
| T-83-63 | Information Disclosure | service list to another tenant | medium | mitigate | Read by the agent's own verified tenant id | closed |
| T-83-64 | Denial of Service | a slow settings read delays heartbeats | low | mitigate | One indexed find_one that never raises | closed |
| T-83-65 | Elevation of Privilege | confirm without approval rights | high | mitigate | control:autonomous_ops, interactive session, Platform Support refused, tenant from the token | closed |
| T-83-66 | Information Disclosure | another tenant's incident | high | mitigate | Every query filters tenantId; incident ids never reach a read alone | closed |
| T-83-67 | Spoofing | agent claims it reverted | low | accept | Only that host's own row changes, and the worst case is a Done row reading Undone for its own host | closed |
| T-83-68 | Repudiation | who kept a host isolated | medium | mitigate | confirmedBy on the row and an audit chain event | closed |
| T-83-69 | Tampering | agent strings in a card | medium | mitigate | React text only, targets never linkified; aria labels built from the same plain strings (R11) | closed |
| T-83-70 | Tampering | one click sent twice | low | mitigate | Disabled while pending, ref guard, single-use server decision | closed |
| T-83-71 | Elevation of Privilege | a button shown to a viewer | low | mitigate | Rendered from the server's flags; the routes still enforce | closed |
| T-83-72 | Tampering | unpublished code assumed live | medium | mitigate | The live list states each step; tenants stay in shadow until a Super Admin lifts them | closed |
| T-83-73 | Denial of Service | test run starves live services | medium | mitigate | One job, nothing beside it, no full suite in a task | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

### Observations for the code review (not counted)

1. The agent compares protected paths as text (`quarantine_paths.rs` `normalize` trims only a trailing separator): with `allow_protected` false it accepts `//etc/passwd`, `/./etc/passwd`, a symlinked parent and Windows forms such as `System32.`. The backend collapses these first and raises a card, and hash binding limits the impact. Counted closed for T-83-34, 46 and 49; the fix is to canonicalise the parent directory on the agent.
2. The gate does not itself refuse `allow_protected: true` on an automatic request; safety rests on its two producers (`sweep_security.py:160`, `followups.py:146`). A one-line gate rule would harden it.
3. The legacy kill path (`response_actions.rs` without `expected_exe`) kills by PID or name with no start-time or image binding; it is approval-gated and used by the Phase 53 UEBA card. T-83-36 covers only the `expected_exe` form.
4. T-83-25: the unstamped gate-only refusal covers the `agent_instructions` polls. The legacy Python agent still reads `response_tasks` and runs isolate, quarantine and kill from human-started SOAR and playbooks (D-25). Reclassify to open if the Python agent is still deployed and the fence was meant to cover it.
5. A restart card stays approvable for 24 hours after the service recovers (83-20 live list item 16).
6. `agent_failed` counts toward the breaker, so a host misreporting its tokens can lower its own tenant to Suggest (the fail-safe direction). T-83-63 has no two-tenant test; it holds by construction.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-83-01 | T-83-08 | The state file sits in the admin-only install directory; a host admin can already change the firewall | plan threat model (83-02) | 2026-10-31 |
| AR-83-02 | T-83-14 | Only a host admin can move the clock, and that admin can already change the firewall (R13) | plan threat model (83-04) | 2026-10-31 |
| AR-83-03 | T-83-29 | A host can only misreport for itself; an unknown instruction fails on that host and the row ends failed | plan threat model (83-08) | 2026-10-31 |
| AR-83-04 | T-83-47 | Host-bound and per tenant; the worst case is one more or one fewer card on the reporting host | plan threat model (83-11) | 2026-10-31 |
| AR-83-05 | T-83-52 | A host can only ask to restart its own listed service, within budget | plan threat model (83-14) | 2026-10-31 |
| AR-83-06 | T-83-67 | Only that host's own row changes; the worst case is a Done row reading Undone for its own host | plan threat model (83-18) | 2026-10-31 |
| AR-83-07 | T-83-75 | A process can rewrite its module path; either way the result is no kill and no false Done; the live Windows test records the real behaviour | plan threat model (83-09) | 2026-10-31 |
| AR-83-08 | T-83-SC | No plan in this phase installs a package; the only manifest change is the agent version 2.1.14 to 2.1.16 | plan threat model (83-01, 83-02…) | 2026-10-31 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-02 | 76 | 74 | 2 (medium, below threshold) | gsd-security-auditor (sonnet), execute-phase orchestrator |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed (T-83-15 and T-83-27 stay open below the high threshold)
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-02 at code level only. Nothing here was observed on a real host; the 83-20 live list still stands.

## Security Audit 2026-11-02

| Metric | Count |
|---|---|
| Threats found | 76 |
| Closed | 74 |
| Open | 2 |
