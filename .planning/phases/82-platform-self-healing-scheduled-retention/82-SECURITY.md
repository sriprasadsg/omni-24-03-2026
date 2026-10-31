---
phase: "82"
slug: "platform-self-healing-scheduled-retention"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-31"
---

# Phase 82 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (the `<threat_model>` blocks of 82-01..82-17) and verified against the
> implementation at ASVS L1 on 2026-10-31, first after plans 82-01..82-14 and again after the gap round
> 82-15..82-17. The gap-round audit ran the retention and health backend modules on a private mongod with
> 0 skipped, and the three retention UI test files.

**Phase status: THREAT-SECURE.** All 55 threats are closed. Nothing here is deployed: the Phase 82 backend
needs a restart and the watchdog is not installed, so the fixes are not on the live server yet.

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
| T-82-04 | Denial of Service | sync body and event flood | medium | mitigate | 256 KB body cap (413), 50 events per call, 300-character strings, idempotent ids so re-sends never multiply rows; per-event isolation and rejection of unstorable numbers (82-16, completed by the non-string kind fix under T-82-50) | closed |
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
| T-82-33 | Tampering | unconfirmed deletion | high | mitigate | Gate: first_run and shortened only count; confirmation keyed by a review token; uncountable rows stay waiting; adoption only for a readable tenant creation time strictly after the confirmation (82-15) | closed |
| T-82-34 | Tampering | confirming counts that changed | high | mitigate | reviewToken over every waiting row; mismatch 409; mid-run 409; uncountable rows excluded | closed |
| T-82-35 | Elevation of Privilege | review and confirm routes | high | mitigate | control:platform_autonomous_ops (platform-only) plus interactive session; 403 tests for tenant roles and Platform Support | closed |
| T-82-36 | Tampering | bypassing the review with Run cleanup now | high | mitigate | /run calls run_manual which applies the same gate; tests prove waiting types are only counted, an unreached tenant included (PROH-82-10) | closed |
| T-82-37 | Information Disclosure | tenant seeing other tenants' review state | medium | mitigate | /policies flags computed for the caller's own tenant only, no counts; test with two tenants | closed |
| T-82-38 | Information Disclosure | health banners and platform status fetch | medium | mitigate | Fetch and render gated on hasPermission('control:platform_autonomous_ops'); server enforces the same permission (82-08); test that a tenant admin triggers no platform request | closed |
| T-82-39 | Tampering | server error text in banners (XSS) | medium | mitigate | React text only, no dangerouslySetInnerHTML (grep check), server caps at 300 characters | closed |
| T-82-40 | Tampering | rendered server strings and the checklist link | medium | mitigate | React text only; the url renders as a link only when it is https or same-origin, else as text; rel noopener noreferrer | closed |
| T-82-41 | Information Disclosure | on-call secrets in the UI | high | mitigate | The API carries none (82-07/82-08); the card renders only type and booleans; test asserts no URL-like text in the on-call card | closed |
| T-82-42 | Tampering | accidental or stale confirmation | high | mitigate | Required review checkbox, no keyboard submit, one request per click, server reviewToken 409 handled by Reload review (server guard in 82-10), Confirm disabled until every row is loaded (82-17; client-side, see Audit Notes) | closed |
| T-82-43 | Elevation of Privilege | Confirm deletion visibility | medium | mitigate | Rendered only for hasPermission('control:platform_autonomous_ops'); server enforces the same permission; 403 closes with a toast | closed |
| T-82-44 | Information Disclosure | platform-health rows in tenant views | medium | mitigate | Client-side drop outside platform scope as a second guard behind the server filter (82-01); test feeds a platform_health row into tenant scope | closed |
| T-82-45 | Information Disclosure | tenant notices revealing other tenants or counts | low | mitigate | The screen renders only the caller's own gate flags (server-scoped in 82-10) and never counts | closed |
| T-82-46 | Tampering | tenant creation time read for adoption | high | mitigate | created_at_of fails closed: an absent, unparseable or equal time is first_run; every tenant write path checked, no route lets a caller set createdAt or created_at (PROH-82-14) | closed |
| T-82-47 | Tampering | confirming a counted set known to be incomplete | high | mitigate | incomplete_review runs inside confirm() before any write; 409 REVIEW_INCOMPLETE; manual-run rows cover only their own tenant (PROH-82-15) | closed |
| T-82-48 | Repudiation | a failed tenant or tenants cursor leaving no trace | medium | mitigate | Per-tenant and cursor guards on Exception only, failedTenants on an always-written run document, retention_run row ok false (PROH-82-16) | closed |
| T-82-49 | Denial of Service | non-finite or oversized numbers in event params and snapshot values | medium | mitigate | clean_params drops them, _scrub stores None through _storable, health_messages._num returns None | closed |
| T-82-50 | Denial of Service | any other per-event failure in ingest_events | medium | mitigate | Per-event guard on Exception counts the event as dropped and continues; LedgerUnavailable keeps its spool meaning; a non-string kind is dropped before the set lookup (fixed after the audit reproduced a 503, see Audit Notes) (PROH-82-17) | closed |
| T-82-51 | Information Disclosure | the dropped-event log line | low | mitigate | Logs the validated event id and the exception class only | closed |
| T-82-52 | Repudiation | audit rule id naming a threshold that did not fire | medium | mitigate | Rule from the unrounded daysLeft with the watchdog's ladder; own rule id for an unreadable certificate (PROH-82-18) | closed |
| T-82-53 | Tampering | one confirmation attesting to rows never shown | high | mitigate | Confirm deletion disabled until nextOffset is null and while incomplete is set; a recount disables it again (PROH-82-19) | closed |
| T-82-54 | Repudiation | dialog dismissed as if nothing happened while the request is in flight | medium | mitigate | Keep waiting disabled and closeOnEsc false while pending; both work again once the request ends (PROH-82-20) | closed |
| T-82-55 | Spoofing | a refused or failed manual run shown as completed | medium | mitigate | runCleanup checks r.ok and a readable ran_at before setting the result; the server detail is shown only as plain text (PROH-82-21) | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Open Threats

None.

How the four threats open at the first audit were closed:

| Threat | Severity | What was wrong | Closed by |
|--------|----------|----------------|-----------|
| T-82-33 | high | CR-01: `adopt` keyed on when the job first saw a gate row, so a tenant missed by an interrupted first pass was deleted with no count and no confirmation | 82-15: adoption keys on the tenant's creation time; `test_retention_unreached.py` reproduces the old failure (`assert 2 == 5`) and passes now |
| T-82-36 | high | The same hole through `POST /api/retention/run` | 82-15, same gate; the T-82-36 test fails on the code before the fix (`KeyError: 'count'`) and passes now |
| T-82-42 | high | WR-01: Confirm deletion was enabled while pages remained unloaded | 82-17: disabled until `nextOffset === null`; 82-15: the server refuses an incomplete counted set |
| T-82-04 | medium | WR-03: one event with a non-finite number answered 503 and blocked every later event | 82-16 for numbers, plus the non-string `kind` fix below |

---

## Audit Notes (gap round, 2026-10-31)

- **T-82-50 was found open and fixed in the same round.** 82-16's per-event guard did not cover the pre-filter in `ingest_events`: `kind not in WATCHDOG_EVENT_KINDS` raised `TypeError` for a list or dict `kind`, and a request with one good event and one such event answered 503. The auditor reproduced it through the real sync route. It needs a token holder or a corrupted spool. The fix is `not isinstance(kind, str)` before the set lookup. A table test through the route failed first (4 of 6 cases, list and dict) and passes now.
- **T-82-42: "every row loaded" is client-side.** The server does not know how many rows the reviewer loaded, and `confirm()` still confirms every eligible row. A caller using the API directly could confirm rows it never paged through. The server enforces a token over the whole waiting set, no run in progress, a complete counted set, the platform permission and an interactive session. This meets the threat as declared (accidental or stale); it is not proof that a person saw every row.
- **Adoption in the persistent case.** A tenant created after the confirmation is deleted by policy with no count, on the premise that it holds nothing old. If the nightly job stays capped or failing for longer than that tenant's retention period, its own aged telemetry could be deleted unreviewed. Rated unlikely; not counted as a gap.
- **`_EVENT_ID` accepts one trailing newline.** `$` matches before a final `\n`, so a logged id can carry a line break. A log-forging nuisance, not a disclosure, and it needs a token holder or a corrupted spool. Left as it is.
- **`LedgerUnavailable` logs the wrapped driver text** at `selfheal.py:199`. Outside T-82-51's dropped-event line, and unchanged by this round.

---

## Unregistered Findings

Outside the register, recorded so they are not lost. All are also in `82-REVIEW.md` except the last.

- WR-02: certificate rule ids off by one rung. Fixed by 82-16.
- WR-05: Run Cleanup Now showed "Cleanup completed" for 409, 403 and 400 answers. Fixed by 82-17.
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
| 2026-10-31 | 55 | 53 | 2 (0 blocking): T-82-04, T-82-50 | gsd-security-auditor, ASVS L1, block_on high, after 82-15..82-17 |
| 2026-10-31 | 55 | 55 | 0 | Orchestrator, after the non-string `kind` fix; 220 backend tests passed, 0 skipped |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** granted 2026-10-31. T-82-06, T-82-20, T-82-21 and T-82-22 stay verified at artifact and test level until the operator installs the watchdog.

## Security Audit 2026-10-31

| Metric | Count |
|---|---|
| Threats found | 55 |
| Closed | 55 |
| Open | 0 |
