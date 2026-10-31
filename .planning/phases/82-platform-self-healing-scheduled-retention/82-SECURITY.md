---
phase: "82"
slug: "platform-self-healing-scheduled-retention"
status: draft
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 3
asvs_level: 1
created: "2026-10-31"
---

# Phase 82 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (the `<threat_model>` blocks of 82-01..82-14) and verified against the
> implementation at ASVS L1 on 2026-10-31, after all 14 plans executed. Phase 82 backend modules and the
> frontend suite (792 tests) were green at audit time; none of those tests cover the open threats below.

**Phase status: SECURITY BLOCKED.** Three high-severity threats are open. Advancement stays blocked until
`threats_open: 0`. Nothing here is deployed: the Phase 82 backend needs a restart and the watchdog is not
installed, so no open threat is reachable on the live server yet.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| watchdog process (omni-watchdog user) -> backend :5000 | Heartbeat, snapshot and events cross a loopback HTTP call; port 5000 listens on 0.0.0.0, so the token is the control | untrusted / safety-critical |
| nginx -> backend /api | Every proxied request carries X-Forwarded-For / X-Real-IP | untrusted / safety-critical |
| ledger rows -> tenant and Platform Support views | Platform-scope rows must stay out of tenant queries | untrusted / safety-critical |
| /etc/omni-watchdog (root-owned) -> watchdog process | Config, token and on-call secrets are read-only to the watchdog | untrusted / safety-critical |
| backend HTTP responses -> watchdog decisions | Stop state and later outbox/test requests arrive from a process the watchdog does not trust for commands | untrusted / safety-critical |
| /var/lib/omni-watchdog (watchdog-owned) | State and spool; the backend user must not be able to edit them | untrusted / safety-critical |
| watchdog -> systemd (D-Bus, polkit) | Restart requests cross into PID 1 under the 82-06 polkit rule | untrusted / safety-critical |
| stop sources -> restart decisions | A STOP file, the database stop and the cache gate restarts | untrusted / safety-critical |
| watchdog.conf extra_certs -> openssl | Operator-supplied paths are read, never written | untrusted / safety-critical |
| filesystem metrics -> pages | Disk numbers drive on-call messages | untrusted / safety-critical |
| watchdog -> PagerDuty / webhook / heartbeat URL (internet) | Pages leave the VM over HTTPS with the routing key or webhook URL | untrusted / safety-critical |
| backend outbox -> watchdog sender | Message text from the backend is forwarded but never treated as a command | untrusted / safety-critical |
| omni-watchdog user -> systemd via polkit | The only privilege the watchdog has | untrusted / safety-critical |
| backend user (azureuser) -> watchdog files | The backend must not be able to change what runs with restart rights | untrusted / safety-critical |
| repo -> live server | Files cross only by the operator's hand | untrusted / safety-critical |
| Super Admin browser -> test-alert route | A privileged action that makes the watchdog send a message | untrusted / safety-critical |
| backend -> watchdog (outbox, testRequest) | Message content crosses to the process that holds the key | untrusted / safety-critical |
| backend -> Super Admin browser | Platform internals cross only to the platform permission holder | untrusted / safety-critical |
| watchdog snapshot -> health document | Values reported by the watchdog are displayed, never executed | untrusted / safety-critical |
| retention_policies (tenant-editable) -> deletion | A tenant admin's period decides what the job deletes for that tenant | untrusted / safety-critical |
| retention job -> MongoDB | Irreversible deletes on a 2-vCPU server shared with the API | untrusted / safety-critical |
| Super Admin browser -> confirm route | One click permits irreversible deletion for every listed row | untrusted / safety-critical |
| tenant admin -> /api/retention/* | Tenant-editable periods and manual runs | untrusted / safety-critical |
| platform status API -> browser | Platform internals reach only platform-permission holders | untrusted / safety-critical |
| server strings -> DOM | Error text from the watchdog is displayed | untrusted / safety-critical |
| health API -> browser | Watchdog-reported strings (paths, errors, host) are displayed | untrusted / safety-critical |
| install checklist url -> link | A URL from the server becomes an anchor | untrusted / safety-critical |
| Super Admin click -> irreversible deletion permit | The one destructive UI action of the phase | untrusted / safety-critical |
| actions API -> Activity list | Rows from the server are rendered; platform rows must stay in platform scope | untrusted / safety-critical |
| /api/retention/policies -> tenant screen | Gate state of the viewer's own tenant only | untrusted / safety-critical |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-82-01 | Spoofing | POST /api/internal/watchdog/sync | high | mitigate | Bearer token from the systemd credential compared with hmac.compare_digest; loopback client only; proxy headers refused (unreachable via nginx); 503 while no credential exists | closed |
| T-82-02 | Tampering | event text in the Activity UI, forged retention confirmation | high | mitigate | Closed WATCHDOG_EVENT_KINDS enum, closed params keys, backend-only kinds refused from the watchdog, all user-visible text rendered from health_messages.py | closed |
| T-82-03 | Information Disclosure | views.list_page for tenants and Platform Support | high | mitigate | include_platform_health defaults False and ANDs kind != platform_health for every tenant id including platform-admin; separate PlatformBucket on the platform route only; tests for tenant admin, viewer and Platform Support (PROH-82-06) | closed |
| T-82-04 | Denial of Service | sync body and event flood | medium | mitigate | 256 KB body cap (413), 50 events per call, 300-character strings, idempotent ids so re-sends never multiply rows | open — below high threshold (non-blocking) |
| T-82-05 | Repudiation | watchdog events | low | mitigate | Each accepted event is mirrored to the platform-admin hash-chained audit ledger through ledger._mirror | closed |
| T-82-06 | Elevation of Privilege | watchdog code path | high | mitigate | Stdlib-only package installed root-owned outside the checkout (82-06 INSTALL.md); entry script adds only its own real directory to sys.path under python3 -I | closed |
| T-82-07 | Tampering | state.json / concurrent runs | medium | mitigate | Atomic temp+fsync+os.replace writes, corrupt-file quarantine with a state_reset event, fcntl.flock run lock | closed |
| T-82-08 | Tampering | values from HTTP responses or config reaching subprocess | high | mitigate | Argument lists only, no shell; unit names come from the UNITS constant, never from config or responses | closed |
| T-82-09 | Information Disclosure | token and on-call secrets in logs | medium | mitigate | Oncall object repr shows only type/booleans; no logging of headers or URLs; test asserts repr carries no secret | closed |
| T-82-10 | Denial of Service | restart loop on a broken service | high | mitigate | Budget 3 per 30 min, waits 60/120/240 s, gave_up until 1 h healthy, test proves no restart after gave_up (PROH-82-09) | closed |
| T-82-11 | Elevation of Privilege | restarting arbitrary units | high | mitigate | Unit names only from UNITS; Ollama only when expected; polkit rule (82-06) allows only these units and verbs restart/start/reset-failed (PROH-82-01) | closed |
| T-82-12 | Tampering | restarts during a platform stop | medium | mitigate | Stop from file > database > cache checked before every restart; counters untouched; test per source (PROH-82-02) | closed |
| T-82-13 | Tampering | openssl invocation with configured paths | medium | mitigate | Argument list with the path as a single argv element after -in, no shell, fixed openssl verb set (structural test) | closed |
| T-82-14 | Denial of Service | alert flapping around a threshold | medium | mitigate | One open incident per check, 2-point disk hysteresis, 20 percent forecast hysteresis, events only on crossings | closed |
| T-82-15 | Tampering | destructive self-help (deleting files, renewing pinned certificate) | high | mitigate | Read-only module; AST scan forbids delete calls outside state.py and any openssl verb other than x509 -enddate (PROH-82-03) | closed |
| T-82-16 | Information Disclosure | routing key, webhook URL, heartbeat URL | high | mitigate | Read only from oncall.env; never in logs, events, the sync body or results; test asserts no secret string in any posted body | closed |
| T-82-17 | Spoofing | PagerDuty and webhook endpoints | medium | mitigate | Default verified SSL context for every https call; structural check that paging.py never builds an unverified context | closed |
| T-82-18 | Denial of Service | alert storm / duplicate pages | high | mitigate | Grouped trigger per run, stable dedup_key, sent flag persisted before and after sending, 500-id delivered memory, at most 10 sends per run (PROH-82-08) | closed |
| T-82-19 | Tampering | stale outbox messages paging much later | low | mitigate | Outbox TTL 24 h on the backend (82-07); delivered ids remembered so a lost acknowledgement never re-pages | closed |
| T-82-20 | Elevation of Privilege | polkit rule | high | mitigate | Matches subject.user, action id, unit and verb; NO for every other systemd1 action of that user; harness proves each case; ES5 lint so Duktape never silently denies by syntax error | closed |
| T-82-21 | Elevation of Privilege | script and config ownership | high | mitigate | INSTALL installs the script root-owned outside the checkout, /etc/omni-watchdog root:omni-watchdog 0750, secrets 0640; unit hardening (NoNewPrivileges, ProtectSystem=strict, empty CapabilityBoundingSet, UMask 0077) | closed |
| T-82-22 | Tampering | existing mongod drop-in (GLIBC_TUNABLES) | high | mitigate | New file names only, no Environment= in shipped drop-ins, before/after systemctl cat diff in INSTALL (PROH-82-07) | closed |
| T-82-23 | Elevation of Privilege | the app installing privilege rules | high | mitigate | start-all-services.sh never references the watchdog; structural test that Phase 82 backend modules never call systemctl or subprocess or write /etc | closed |
| T-82-24 | Information Disclosure | on-call key and URLs | high | mitigate | Backend never reads oncall.env; outbox and responses carry type and booleans only; scan and JSON tests (PROH-82-04) | closed |
| T-82-25 | Elevation of Privilege | POST /health/test-alert | high | mitigate | control:platform_autonomous_ops (platform-only permission) plus interactive session; 403 tests for tenant roles and Platform Support | closed |
| T-82-26 | Denial of Service | test-alert spam, outbox flood | medium | mitigate | One pending test request reused; 20 outbox items per sync; 24 h TTL; watchdog sends at most 10 per run (82-05) | closed |
| T-82-27 | Information Disclosure | GET /health and status.health | high | mitigate | control:platform_autonomous_ops (platform-only) plus interactive session; 403 tests for tenant roles and Platform Support | closed |
| T-82-28 | Spoofing | false or missed dead-man alarm | medium | mitigate | Arms only after first heartbeat; 180 s startup grace; compare-and-set alarmedAt; single sweep runner under renewed lock | closed |
| T-82-29 | Information Disclosure | secrets in health payloads | high | mitigate | Payloads built from type and booleans only; JSON key/value scan test (PROH-82-13 keeps the key out of the backend entirely) | closed |
| T-82-30 | Tampering | deleting audit evidence or decision records | high | mitigate | Registry of eight types only, NEVER_DELETED asserted disjoint at import and in tests, protected collections untouched after a confirmed run (PROH-82-05) | closed |
| T-82-31 | Denial of Service | MongoDB load during deletes | medium | mitigate | 500-id batches, 0.5 s pauses, 60-minute cap, count maxTimeMS 30000, 02:00 UTC before the 02:30 backup | closed |
| T-82-32 | Tampering | cross-tenant deletion through the wrong tenant field | high | mitigate | Raw handle with the type's stored tenant field (tenant_id for uptime rollups and agent/asset metrics); two-tenant isolation tests | closed |
| T-82-33 | Tampering | unconfirmed deletion | high | mitigate | Gate: first_run and shortened only count; confirmation keyed by a review token; uncountable rows stay waiting | open |
| T-82-34 | Tampering | confirming counts that changed | high | mitigate | reviewToken over every waiting row; mismatch 409; mid-run 409; uncountable rows excluded | closed |
| T-82-35 | Elevation of Privilege | review and confirm routes | high | mitigate | control:platform_autonomous_ops (platform-only) plus interactive session; 403 tests for tenant roles and Platform Support | closed |
| T-82-36 | Tampering | bypassing the review with Run cleanup now | high | mitigate | /run calls run_manual which applies the same gate; tests prove waiting types are only counted (PROH-82-10) | open |
| T-82-37 | Information Disclosure | tenant seeing other tenants' review state | medium | mitigate | /policies flags computed for the caller's own tenant only, no counts; test with two tenants | closed |
| T-82-38 | Information Disclosure | health banners and platform status fetch | medium | mitigate | Fetch and render gated on hasPermission('control:platform_autonomous_ops'); server enforces the same permission (82-08); test that a tenant admin triggers no platform request | closed |
| T-82-39 | Tampering | server error text in banners (XSS) | medium | mitigate | React text only, no dangerouslySetInnerHTML (grep check), server caps at 300 characters | closed |
| T-82-40 | Tampering | rendered server strings and the checklist link | medium | mitigate | React text only; the url renders as a link only when it is https or same-origin, else as text; rel noopener noreferrer | closed |
| T-82-41 | Information Disclosure | on-call secrets in the UI | high | mitigate | The API carries none (82-07/82-08); the card renders only type and booleans; test asserts no URL-like text in the on-call card | closed |
| T-82-42 | Tampering | accidental or stale confirmation | high | mitigate | Required review checkbox, no keyboard submit, one request per click, server reviewToken 409 handled by Reload review (server guard in 82-10) | open |
| T-82-43 | Elevation of Privilege | Confirm deletion visibility | medium | mitigate | Rendered only for hasPermission('control:platform_autonomous_ops'); server enforces the same permission; 403 closes with a toast | closed |
| T-82-44 | Information Disclosure | platform-health rows in tenant views | medium | mitigate | Client-side drop outside platform scope as a second guard behind the server filter (82-01); test feeds a platform_health row into tenant scope | closed |
| T-82-45 | Information Disclosure | tenant notices revealing other tenants or counts | low | mitigate | The screen renders only the caller's own gate flags (server-scoped in 82-10) and never counts | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Open Threats

| Threat | Severity | How the mitigation is bypassed | Fix |
|--------|----------|--------------------------------|-----|
| T-82-33 | high | CR-01. `gate_state` returns `adopt` when `confirmedDays` is None and `firstSeenAt` is after the global `confirmedAt` (`retention_gate.py:99-102`). `firstSeenAt` is set only when `run_tenant` reaches the tenant (`retention_job.py:131`), and `confirm()` seeds nothing. A tenant that existed before the confirmation but was missed by an interrupted first pass (time cap, lost lock, or an unguarded Mongo error in another tenant) is deleted with no count and no confirmation. Reproduced by the auditor: `t-z` went from 5 documents to 2 in the next nightly run. The same applies to a data type added later whose collection already holds old data | Seed gate rows for every existing tenant and type at confirm time, or adopt only when the tenant's `createdAt` is after `confirmedAt`. Refuse confirm when the last run stopped early or a tenant lacks gate rows. Guard each tenant in `run_all`. Add a test for the unreached tenant |
| T-82-36 | high | The same hole through `POST /api/retention/run` into `run_tenant` (`retention_endpoints.py:108`). Reproduced through `run_manual`. The legacy delete functions in `retention_service.py` (WR-04) have no non-test callers and are not the route | Same fix as T-82-33 |
| T-82-42 | high | WR-01. Confirm deletion is enabled while pages remain unloaded (`AutonomousOpsRetentionReview.tsx:315`), and the server confirms every eligible row (`retention_gate.py:228`). At 25 rows per page and 8 rows per tenant, 4 or more tenants are paged, so one checkbox attests to rows never displayed. The dialog's whole-set totals reduce this but do not prevent it | Disable Confirm until `nextOffset === null`, with a test for the paged case |
| T-82-04 | medium | WR-03. Size, count and string caps hold, but failure is not isolated per event. An event with `forecastDays: 1e999` passes validation and raises OverflowError in `health_messages._num`; `ingest_events` catches only `LedgerUnavailable`, so `post_sync` answers 503 and the watchdog resends the same event every minute. Needs a token holder or a corrupted spool; the watchdog cannot produce it alone | Catch per-event failures, reject non-finite numbers |

---

## Unregistered Findings

Outside the register, recorded so they are not lost. All are also in `82-REVIEW.md` except the last.

- WR-02: certificate rule ids are off by one rung (14d shows as 30d, 7d as 14d, 1d as 7d) on the audit-facing `reason.ruleId`.
- WR-05: Run Cleanup Now shows "Cleanup completed" for 409, 403 and 400 answers.
- IN-02: `testAlert.error` and the stored `page_failed` and `test_alert` params are not URL-scrubbed. The watchdog never formats exception text into them today.
- IN-03: the loopback check is a literal string match, and "unreachable through nginx" depends on nginx always adding `X-Forwarded-For`, which the live config does.
- T-82-06, T-82-20, T-82-21 and T-82-22 are verified at artifact and test level only. The watchdog is not installed on this host, so deployed ownership and modes must be checked after the operator install.

---

## Accepted Risks Log

No accepted risks.

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-31 | 45 | 41 | 4 (3 blocking) | gsd-security-auditor, ASVS L1, block_on high |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [ ] `threats_open: 0` confirmed
- [ ] `status: verified` set in frontmatter

**Approval:** pending, blocked by T-82-33, T-82-36 and T-82-42
