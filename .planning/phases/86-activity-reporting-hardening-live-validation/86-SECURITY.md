---
phase: "86"
slug: "activity-reporting-hardening-live-validation"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
threats_total: 41
threats_closed: 41
threats_open_nonblocking: 0
# residual notes R1-R4 under T-86-14-03: each low (below block_on high), open, NOT accepted; see Audit Notes
residual_notes_open: 4
asvs_level: 1
block_on: high
register_authored_at_plan_time: true
audit_verdict: SECURED
created: "2026-11-14"
---

# Phase 86 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

The register is the union of the `<threat_model>` blocks in 86-01..86-15-PLAN.md. T-86-SC (no package installed) appears in 86-01..86-13 with the same text and is counted once. The 86-14 and 86-15 registers carry no Severity column. Their severities below are the auditor's assessment, marked "assessed". An OPEN threat with no plan severity counts as critical for the gate (fail-closed rule).

Line anchors are at HEAD 324340252 (third audit, 2026-11-14). Only seven files changed after the first audit (`git diff --name-only 2b14815b0 HEAD`): `autonomous_ops/reporting/golive.py`, `autonomous_ops/reporting/golive_test_org.py`, `autonomous_ops_golive_endpoints.py`, `autonomous_ops_platform_endpoints.py`, `tests/test_autonomous_ops_golive.py`, `tests/test_autonomous_ops_golive_test_org.py` and the new `tests/test_autonomous_ops_golive_test_org_race.py`. Every other row's evidence is unchanged from the first audit.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| browser -> GET /api/autonomous-ops/statistics, /export | days, bucket, format, tenantId from the query string; caller may be a tenant role, platform staff or an API key | per-tenant ledger counts and rows (tenant-confidential) |
| browser -> GET /api/reports/export (registry) | the registry elevates Super Admins to every tenant for other report types | a tenant's ledger rows (tenant-confidential) |
| route / automatic loop -> autonomy_actions and other per-tenant data | the sweep, rollouts, desk, retention, statistics, export and digest each read tenant data | tenant-confidential rows |
| stop switch -> every automatic actor | the stop must reach the sweep, delivery, approvals, rollouts, desk and watchdog | control state (safety-critical) |
| ledger rows -> notice, email, CSV, PDF | targets, hostnames and ticket titles come from agents and requesters | untrusted strings |
| digest -> notifications; backend -> SMTP | the audience tag decides who reads the notice; the external SMTP server may hang | tenant-admin-only notice; outbound mail |
| Super Admin -> PUT /tenants/{id}/shadow, POST /golive/checks, POST/DELETE /golive/test-organization | lifting shadow mode, recording go-live evidence, marking the go-live test organization (D-23) | safety gate state; free-text evidence notes |
| API key -> platform routes | a key may hold the platform scope but must never lift shadow, record evidence or mark/clear the test organization | credentials |
| platform API / server headers -> browser | organization names, notes, recorder names, gate sentences, file names, X-Export-* counts | server strings rendered on screen |
| working tree -> HEAD (D-18, 86-13) | the user's uncommitted files become history; HEAD must work alone | source code (secrets risk) |
| executor -> live server (86-13) | read-only log, health and file checks only | none written |
| repository document -> operators | runbook text readable by anyone with repository access | operational text |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-86-01 | Information disclosure | statistics route tenant resolution | high | mitigate | `autonomous_ops_reporting_endpoints.py:41` -> `_tenant_for` (`autonomous_ops_endpoints.py:41-46`) -> `views.resolve_tenant` (`views.py:107-128`: Billing 403 at 112-113, staff must name one at 120-121, tenant role only its own at 123-127); `stats.py:32` `$match` names tenantId; tests `test_autonomous_ops_stats.py:270,280,285`, `test_autonomous_ops_two_tenant.py:339` | closed |
| T-86-02 | Tampering | days / tenantId query parameters | low | mitigate | `autonomous_ops_reporting_endpoints.py:31` (max_length TENANT_ID_MAX=128), `:37-38` (422 outside WINDOWS); `views.py:114-116`; test `test_autonomous_ops_stats.py:101` | closed |
| T-86-03 | Information disclosure | rule names and targets in the statistics payload | low | accept | Plan-time accept, logged as AR-86-01 (user, 2026-11-14). Rationale verified: `stats.py:111-120` returns counts, rule ids and code-owned names (`rule_names.py`), no targets or people; React text (`StatsRuleTable.tsx`) | closed (accepted, AR-86-01) |
| T-86-SC | Tampering | npm/pip installs | low | accept | Plan-time accept, logged as AR-86-02 (user, 2026-11-14). Rationale verified: `git diff fd337f721~1 HEAD` over every package.json, lock file, requirements*.txt, pyproject and Cargo file is empty (reportlab was already in `backend/requirements.txt:99`); the ae0b01058..324340252 fix commits touch no package file | closed (accepted, AR-86-02) |
| T-86-04 | Elevation of privilege | any automatic actor that ignores the stop | high | mitigate | `tests/test_autonomous_ops_stop_drill.py:156-157` presses the real `stop.press`; platform and tenant stops over sweep, delivery, approvals, rollout, desk and watchdog (295-449), control test at 295, unreadable stop counts as stopped at 449 | closed |
| T-86-05 | Information disclosure | sweep, rollout loop, desk worker, retention | high | mitigate | `tests/test_autonomous_ops_two_tenant.py:103` (sweep), `:147` (rollout), `:206` (desk), `:259` (retention) | closed |
| T-86-06 | Tampering | StatsCard, StatsRuleTable, TimeSavedBlock | low | mitigate | No `dangerouslySetInnerHTML`/`innerHTML` in any Phase 86 frontend file (18 files); `StatsRuleTable.tsx:45-46` renders name/id as text | closed |
| T-86-07 | Information disclosure | digest delivery path | high | mitigate | `reporting/digest.py:96-98` `_post_in_app` with `audience: tenant_admins`; platform org skipped at :166; `notification_audience.py:34-39` hides it without `*`/`manage:agents`; `pending_agents.py:261-263` never pushes audience-tagged notices; email to `TENANT_ADMIN_ROLE_NAMES` only (`digest.py:105-114`); tests `test_autonomous_ops_digest.py:280,310,405`. The unscoped notice reader `send_pending_emails.py` is out of backend/ (49e659791) | closed |
| T-86-08 | Tampering | email subject and html body | medium | mitigate | `digest_text.py:31` control-char regex, `:50-52` `_one_line`, `:160-162` subject; `:186-206` `html.escape` on every string; target cap 80 (`reporting/__init__.py:46`, `digest_text.py:89`); tests `test_autonomous_ops_digest.py:151,175,449` | closed |
| T-86-09 | Denial of service | SMTP send | medium | mitigate | `digest.py:32,145-147` `asyncio.wait_for` 30 s; per-recipient try/except `:143-154`; `digest_job.py:64-65` `lock_with_renewal` | closed |
| T-86-10 | Repudiation | duplicate or missing digests | low | mitigate | `digest.py:47` unique `digest_once_per_day`; `_claim` `:83-89`; states quiet/sent with counts `:178,183`; tests `test_autonomous_ops_digest.py:347,388` | closed |
| T-86-11 | Tampering | CSV cells | high | mitigate | `reporting/export.py:93` `sanitize_csv_cell` on every cell; `itam_data_service.py:60` covers `= + - @ \t \r`; test `test_autonomous_ops_export.py:197` | closed |
| T-86-12 | Tampering | PDF cells | medium | mitigate | `export_pdf.py:37-38` is the only `Paragraph(` builder and escapes; test `test_autonomous_ops_export.py:282` | closed |
| T-86-13 | Information disclosure | approver names in a tenant's file | medium | mitigate | `export.py:71-77` -> `views.display_actor` (`views.py:146-152`); test `test_autonomous_ops_export.py:215` | closed |
| T-86-14 | Information disclosure | D-18 commit db8b8cd4c | high | mitigate | Scan recorded in 86-06-SUMMARY:134; re-scan of the commit's added lines on 2026-11-14: no key headers, AKIA ids, quoted secret literals, bearer tokens or credentialed URIs. The commit is now pushed (by the user, 86-13) | closed |
| T-86-15 | Elevation of privilege | put_shadow lift | critical | mitigate | `autonomous_ops_platform_endpoints.py:241-247` (`lifting` :241, `golive.lift_decision` :244, 409 :245-247) before the `set_shadow` write at :249; `golive.py:105-119` (`_reasons`: 5 checks, 7 days, `unreadable` reason), `:147-153` (`lift_decision`), `:156-159` (`lift_blockers`); `put_shadow` is the only production caller of `set_shadow` (:249, and :255 the T-86-14-03 revert, which writes True only); `settings.py:214` is the only writer of `shadow` besides the True default at `settings.py:138`; tests `test_autonomous_ops_golive.py:81-140,290`, `test_autonomous_ops_endpoints_writes.py:167-190`. The gate runs before the write for every lift whose flag read says on. Residual R2 (Audit Notes) is a TOCTOU on put_shadow's already-lifted branch: noted, low, not blocking | closed |
| T-86-16 | Repudiation | go-live evidence | high | mitigate | `golive.py:32-34` sole accessor, insert-only `:48-63`; `autonomous_ops/__init__.py:32-35` PROTECTED_COLLECTIONS; audit event `autonomous_ops_golive_endpoints.py:80-86`; structural tests `test_autonomous_ops_golive.py:448-482`, `test_autonomous_ops_ledger.py:327` | closed |
| T-86-17 | Spoofing | API key on platform routes | high | mitigate | `_require_platform_autonomy_control` + `_require_interactive_session` on all four go-live routes (`autonomous_ops_golive_endpoints.py:51-52,69-70,129-130,166-167`) and put_shadow (`autonomous_ops_platform_endpoints.py:224-225`); tests `test_autonomous_ops_golive.py:335`, `test_autonomous_ops_endpoints_writes.py:188` | closed |
| T-86-18 | Tampering | check id and note input | medium | mitigate | `autonomous_ops_golive_endpoints.py:37` Literal, `:41` 10-500 trimmed; `golive.py:51-55`; `GoLiveChecklist.tsx:144` text; test `test_autonomous_ops_golive.py:322` | closed |
| T-86-19 | Information disclosure | registry Super Admin elevation | critical | mitigate | `export_report_endpoint.py:59-60` branches before `set_tenant_id("platform-admin")` at :66; `:96-99` refuses platform roles, super roles and org-less callers; test `test_autonomous_ops_export_registry.py:103` | closed |
| T-86-20 | Elevation of privilege | export permissions | high | mitigate | `autonomous_ops_reporting_endpoints.py:68-69` both rights via `views.holds`; registry `export_report_endpoint.py:41,49,56-57` | closed |
| T-86-21 | Repudiation | exports | medium | mitigate | `export.py:157-161` `autonomous_ops.export` event (not in a try: an audit failure withholds the file); ExportControlMiddleware `app_middleware.py:300-302` | closed |
| T-86-22 | Denial of service | large exports | medium | mitigate | `export.py:114` `.limit(EXPORT_ROW_CAP)` (5000); `export_controls.py:33` in EXPORT_PATHS; tests `test_autonomous_ops_export.py:162,177` | closed |
| T-86-23 | Information disclosure | sensitive content in rows | medium | mitigate | `export.py:150-156` `dlp_service.scan_export`, incident, 403 before any byte is sent; both entry points use `deliver`; tests `test_autonomous_ops_export.py:458`, `test_autonomous_ops_export_registry.py:121` | closed |
| T-86-24 | Denial of service | index builds at restart | low | accept | Plan-time accept, logged as AR-86-03 (user, 2026-11-14). Rationale verified with a count correction: 4 index definitions, not 3 (`digest.py:47-48`, `golive.py:44-45`), all idempotent; migration 035 only calls the two `ensure_indexes` | closed (accepted, AR-86-03) |
| T-86-25 | Information disclosure | statistics, export, digest | high | mitigate | `tests/test_autonomous_ops_two_tenant.py:339` (statistics), `:355` (export), `:372` (digest) | closed |
| T-86-26 | Information disclosure | docs/autonomous-ops-go-live.md | low | mitigate | Scan: no IP literal, host name, URL, token or key; on-call file named by path only; no `autonomy_settings`/"Open decision" text | closed |
| T-86-27 | Tampering | export dialog file name and counts | low | mitigate | `services/autonomousOpsReporting.ts:64-77` (`fileNameFrom`, `wholeNumber` parseInt with fallback); no HTML sink | closed |
| T-86-28 | Elevation of privilege | hidden or disabled export controls | low | accept | Plan-time accept, logged as AR-86-04 (user, 2026-11-14). Rationale verified: server checks both rights and the organization (T-86-19, T-86-20) | closed (accepted, AR-86-04) |
| T-86-29 | Tampering | go-live notes and organization names on screen | medium | mitigate | `GoLiveChecklist.tsx:144` `whitespace-pre-wrap break-words`; no HTML sink in `components/autonomousOpsGoLive` | closed |
| T-86-30 | Elevation of privilege | a UI-only lift gate | low | accept | Plan-time accept, logged as AR-86-05 (user, 2026-11-14). Rationale verified: server gate `autonomous_ops_platform_endpoints.py:243-247`, write at :249 (T-86-15) | closed (accepted, AR-86-05) |
| T-86-31 | Tampering | drift between working tree and HEAD | high | mitigate | 86-13-SUMMARY:90-99 (working tree 2819 passed; git archive snapshot of HEAD). Only Phase 86 path dirty now: `components/ReportingDashboard.tsx`, the user's own 3-line KPI edit that 86-11 deliberately left unstaged, unrelated to Phase 86. Third audit: a git archive snapshot of HEAD 324340252 (backend, shared, components, services, contexts, docs and the tracked root `pytest.ini`) passes the test-organization, race, go-live, writes, copy and structural suites (129 passed) | closed |
| T-86-32 | Tampering | live database during checks | high | mitigate | Process control: 86-13-SUMMARY Task 3 lists log greps, a health curl and a published-file grep only; no Phase 86 test names 27017; all three audits used only 127.0.0.1:27998 | closed |
| T-86-14-01 | Elevation of privilege | test-organization mark/clear routes | high (assessed) | mitigate | `autonomous_ops_golive_endpoints.py:129-130,166-167`; role matrix `test_autonomous_ops_golive_test_org.py:416-428` (Platform Support, Billing, tenant admin, analyst, all-scope API key -> 403) | closed |
| T-86-14-02 | Tampering | several organizations exempted, or a customer organization exempted quietly | medium (assessed) | mitigate | One mark by construction: `golive_test_org.py:47-49` (fixed `_id` insert at :47, DuplicateKeyError -> AlreadyMarked at :48-49); typed name `autonomous_ops_golive_endpoints.py:146-147`; platform org 409 at :140-141, unticked/unknown 404 at :143-144; platform-chain events :101-108,155,192; label `GoLiveOrganizations.tsx:44`; race test `test_autonomous_ops_golive_test_org.py:130-138`. Detective, not preventive: see Audit Notes. "One at a time" now holds for any two concurrent requests (the gate-to-mark-read window is closed by 324340252); residuals R1 and R2 (three concurrent Super Admin requests) can still leave a second organization out of shadow mode | closed |
| T-86-14-03 | Tampering | mark cleared while the organization stays out of shadow mode | unranked in plan (counted critical while open; assessed medium before the fix) | mitigate | Declared mitigation "Clear refused while its own shadow flag is off" verified, fail closed on both sides. **Clear:** `_clear_refusal` `autonomous_ops_golive_endpoints.py:111-118` (settings missing, unreadable or shadow not True -> refuse) on a fresh load at :179-181, before the delete at :182; re-read after the delete at :183-188 (a raise counts as unconfirmed); `golive_test_org.restore` (`golive_test_org.py:59-68`) and 409 at :189-191, with no `cleared` event; `cleared` audited at :192 only. **Lift:** `golive.lift_decision` (`golive.py:147-153`) returns `(reasons, exempt)` from the gate's one fail-closed mark read (`_read` :134-144, `_test_org_mark` :122-127); `put_shadow` decides the post-write re-check from that `exempt` (`autonomous_ops_platform_endpoints.py:244`, :252-257) and reverts to True with a 409 when the mark is gone or unreadable (:255). Tests: `test_autonomous_ops_golive_test_org.py:153,181,197,209,230,251,334,357`; race file `test_autonomous_ops_golive_test_org_race.py:52,68,89,109,125,144,171` (4 of its 7 fail on the 6cd12cb2d code). One clear racing one lift never ends lifted and unmarked: 0 of 381 model interleavings, 0 of 750 randomised real-route schedules at HEAD (34 of 750 on the pre-fix code). Residuals R1-R4 (three concurrent requests or a mid-request write failure) are open, low, non-blocking and not accepted: see Audit Notes | closed |
| T-86-14-04 | Denial of safety | a read failure exempts an organization | high (assessed) | mitigate | `golive.py:122-127` mark read in try -> None; `:130-131` no exemption; read once in `_read` (:134-144, mark read at :144) and handed on by `lift_decision` (:147-153); test `test_autonomous_ops_golive_test_org.py:312-322`, race file `:89`, `:144` | closed |
| T-86-14-05 | Repudiation | early lift indistinguishable from a normal lift | low (assessed) | mitigate | `golive.py:162-167` `testOrganization` in lift evidence (:167); spread into `shadow_lifted` by `_audit_shadow_change` (`autonomous_ops_platform_endpoints.py:267-280`, `lift_evidence` at :271, event at :274-278); tests `test_autonomous_ops_golive_test_org.py:272-287` (assert :287), `:290-301`; race file `:109` (exemption lift audited once with `testOrganization: true`), `:125` (customer lift audited with `false`) | closed |
| T-86-15-01 | Spoofing/Tampering | the UI marks or lifts what the server would refuse | low (assessed) | mitigate | `GoLiveOrganizations.tsx:71-90` disables Lift on the server's `canLift` and shows its reasons; refetch after any refusal; no 5-check/7-day constants in the UI | closed |
| T-86-15-02 | Repudiation | an operator marks the wrong organization | low (assessed) | mitigate | `TestOrgDialogs.tsx:58,66` confirm only on the typed exact name; warning `goLiveCopy.ts:176` (MARK_BODY), label `goLiveCopy.ts:166` shown at `GoLiveOrganizations.tsx:44`; server audit `autonomous_ops_golive_endpoints.py:155` | closed |
| T-86-15-03 | Information disclosure | server sentence rendered as HTML | low (assessed) | mitigate | `TestOrgDialogs.tsx:40-45` sentence as React text; no HTML sink in `components/autonomousOpsGoLive` | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-86-01 | T-86-03 | 86-01 plan: the statistics payload carries counts and code-owned rule names only, no targets or people, and the UI renders it as React text. Verified: `stats.py:111-120`, `rule_names.py`, `StatsRuleTable.tsx` | the user ("Yes, log them", via the /gsd-execute-phase 86 orchestrator); planner (86-01 threat model); rationale confirmed by gsd-security-auditor | 2026-11-14 |
| AR-86-02 | T-86-SC | 86-01..86-13 plans: no package is installed by this phase. Verified: `git diff fd337f721~1 HEAD` over every package.json, lock file, requirements*.txt, pyproject and Cargo file is empty; reportlab was already in `backend/requirements.txt:99` | the user ("Yes, log them", via the /gsd-execute-phase 86 orchestrator); planner (86-01..86-13 threat models); rationale confirmed by gsd-security-auditor | 2026-11-14 |
| AR-86-03 | T-86-24 | 86-09 plan: small index builds at restart; autonomy_actions holds at most 365 days of decisions; create_index is idempotent. Count corrected by the audit: 4 index definitions, not the plan's 3 (`digest.py:47-48`: `digest_once_per_day`, `tenant_finished`; `golive.py:44-45`: `check_recorded`, `id_unique`); migration 035 only calls the two `ensure_indexes` | the user ("Yes, log them", via the /gsd-execute-phase 86 orchestrator); planner (86-09 threat model); rationale confirmed by gsd-security-auditor | 2026-11-14 |
| AR-86-04 | T-86-28 | 86-11 plan: hiding or disabling the export controls is a convenience; the server checks both permissions and the organization (86-08; T-86-19, T-86-20) | the user ("Yes, log them", via the /gsd-execute-phase 86 orchestrator); planner (86-11 threat model); rationale confirmed by gsd-security-auditor | 2026-11-14 |
| AR-86-05 | T-86-30 | 86-12 plan: the server enforces the lift gate (86-07, T-86-15, `autonomous_ops_platform_endpoints.py:243-247`); the UI shows the server's reasons and refetches after any refusal. The test-organization exemption's server-side window is closed (T-86-14-03, 324340252); residuals R1-R4 are notes, not accepted here | the user ("Yes, log them", via the /gsd-execute-phase 86 orchestrator); planner (86-12 threat model); rationale confirmed by gsd-security-auditor | 2026-11-14 |

*Accepted risks do not resurface in future audit runs.*

T-86-14-03 was never accepted. The user chose to fix it (6b58bd655, then 324340252), and it is closed by verification. Residuals R1-R4 are not accepted either. They are open notes below the high threshold, and whether to fix or accept them is the user's decision.

---

## Audit Notes

### T-86-14-03 third audit after 324340252 (2026-11-14): closed

**What 324340252 changes:**
- `golive.lift_decision` (`golive.py:147-153`) returns `(reasons, exempt)` from the single mark read the gate decided on. `lift_blockers` (:156-159) delegates to it.
- `put_shadow` takes `test_org_lift` from that `exempt` (`autonomous_ops_platform_endpoints.py:244`). It re-runs `lift_decision` after the write only then (:252-253) and reverts to True with the same 409 when the mark is gone or unreadable (:254-257).
- The second mark read (`_may_be_test_organization`) is removed, which closes the gate-to-mark-read window of the second audit.

**Declared mitigation verified:**
- The clear is refused while the organization's own flag is off or cannot be confirmed on. This holds before the delete (:179-181) and after it (:183-191, mark restored, 409, no `cleared` event).
- `settings.load` (`settings.py:54-87`) marks a tenants-read raise, a settings-read raise and a non-bool `shadow` or invalid level as `readable=False`. Each refuses the clear.
- No other entry point exists:
  - `golive_test_org.mark`, `clear` and `restore` are called only at `autonomous_ops_golive_endpoints.py:150,182,190`.
  - `settings.set_shadow` is called only at `autonomous_ops_platform_endpoints.py:249,255`.

**Tests (private mongod 127.0.0.1:27998, all three URLs set):**

| Run | Result |
|---|---|
| Working tree: test-org, race, go-live, endpoints_writes, copy, structural | 129 passed, 0 skipped (23, 7, 22, 18, 33, 26) |
| git-archive snapshot of HEAD 324340252, same six suites | 129 passed |
| 6cd12cb2d snapshot (production code identical to 6b58bd655), its own race file | 2 failed (200 == 409 at `:52`, `:68`), 3 passed |
| 6cd12cb2d snapshot, HEAD's race file | 4 failed of 7 (`:52`, `:68`; `:144`, `:171` on the missing `lift_decision`) |
| gsd-security-auditor, test-org + race | 30 passed |
| gsd-security-auditor, go-live + writes | 40 passed |

**Real-route stress (gsd-security-auditor, scratch file `test_scratch_audit_t86_14_03.py` in the session scratchpad, run in snapshots only):** one clear against one lift with a random 0-3 ms delay before every Motor call.
- HEAD: 0 bad endings in 750 schedules.
- 6cd12cb2d: 34 bad in 750, so the harness can find the window.

**Interleaving models (session scratchpad, pure Python, no repo imports):**
- The earlier model `model_t86_14_03.py` (`lift_fixed` variant) gives 0 bad of 696 for one clear against one lift.
- The memoised HEAD model `model_t86_14_03_head.py` uses one step per database round trip. `set_shadow` is `ensure_tenant` (`$setOnInsert`) plus an unconditional `$set`, and `restore` is an insert that loses to any existing mark. The auditor checked it line by line and found it faithful.
- It assumes single-document operations are atomic and linearizable. That holds: mongod is standalone and has no read-preference override.
- Results, where bad means A out of shadow mode and unmarked, A never meeting the full gate:
  - one clear against one lift: 0 of 381 (366 from in-shadow, 15 from lifted);
  - every pair of concurrent actions that includes a clear (second clear, lift, restore, mark of another organization, re-mark): 0;
  - every single fail-closed read fault (clear read1, clear read2, gate mark read, post-check mark read): 0;
  - bad endings only with three concurrent actions or a write failure (R1-R4 below).

**Judgement:**
- **Declared mitigation:** verified for the threat as registered.
- **PROH-86-14:** holds for every pair of concurrent Super Admin requests and every single read fault. It is broken only by R1 (three concurrent requests) and R3 (a write failure on top of the race). In both, the clear's delete stands while the organization is out of shadow mode.
- **R2 and R4:** reach the threat's end state through the lift side, so they fall under PROH-86-04 / T-86-15.
- **Severity:** each residual is low, below `block_on: high`, so T-86-14-03 is closed and nothing is accepted.

### Residual notes R1-R4 (open, below the high threshold, non-blocking, NOT accepted)

gsd-security-auditor reproduced each shape on the real routes at HEAD with barriers. The barriers show the mechanism, not the likelihood. The counts come from the HEAD model.

| ID | Shape | Mechanism at HEAD | Evidence | Severity | Scope |
|---|---|---|---|---|---|
| R1 | Third concurrent mark of another organization (clear A, lift A, mark B) | The clear's read1 (:179) sees shadow on. The lift writes and its post-check still sees the mark (:249, :252-253), so the lift stands. The clear's delete (:182) and read2 (:184) see off. B's insert takes the empty slot, and `restore` loses (`golive_test_org.py:62-67`, returns False with an ERROR). The route ignores that (:190) and answers 409. End: A lifted and unmarked, B marked, and B can then be lifted by exemption | model 30 of 4492 (from in-shadow); real routes: lift 200, mark 201, clear 409, both flags off, ERROR "could not be put back" | low | T-86-14-03 / PROH-86-14, three-actor variant |
| R2 | Stale already-lifted lift: (restore A, clear A, lift A whose flag read saw "already lifted") or (clear A plus two lifts, the second reading the first lift's transient False before its revert) | When `lifting` is False (:241), `put_shadow` skips the gate (:243-247) and the post-check (:252), yet still writes `set_shadow(False)` at :249, and it audits nothing (:258). The flag read and the write are about 3 round trips apart. Two actors are enough to lose a concurrent restore this way: the organization stays out of shadow mode with `shadow_restored` as its last event | model 710 of 5283 (from lifted and marked) and 2876 of 11,412,916 (from in-shadow); real routes: end flag off and unmarked, no `shadow_lifted` for the final write | low | Not the clear's mitigation (the clear sees shadow on twice). PROH-86-04 / T-86-15, put_shadow's already-lifted branch (D-21) |
| R3 | `restore()` raising a non-duplicate error | After a lift lands between the clear's reads, the restore insert raises, giving 503 (:196-197). End: mark gone, flag off; only `shadow_lifted` is audited, with no `cleared` | model 15 of 366; real routes reproduced | low | T-86-14-03 / PROH-86-14, double fault (race plus a database failure) |
| R4 | Revert `set_shadow(True)` raising | The clear completes while shadow is on. The exemption lift writes False, its post-check finds no mark, and the revert (:255) raises, giving 503. End: flag off, mark gone, no `shadow_lifted` for that lift. Request cancellation or a process kill between the lift's write and its revert (or between the clear's delete and restore) is the same class | model 53 of 366; real routes reproduced | low | Lift side (PROH-86-04), double fault |

**Why each is low:**
- **Actor:** only the platform owner with an interactive session reaches these routes (T-86-14-01, T-86-17).
- **Window:**
  - R1 and R2 need three near-simultaneous privileged requests inside one to three database round trips.
  - The Lift dialog blocks double submission (`ShadowDialogs.tsx:44,81`), so R2's two-lift shape needs a second tab, a second Super Admin or a script.
  - R3 and R4 need a database failure on top of the race, which an attacker does not control.
- **Capability:** nothing the actor lacks already. The platform owner can mark any ticked organization and lift it by exemption (detective control, T-86-14-02). The residuals bypass only "one at a time" and "clear only while in shadow mode", and each attempt leaves audit traces.
- **Effect is latent:** a stored `shadow=False` acts only while `AUTONOMOUS_REMEDIATION_DRY_RUN` is off. `settings.master_shadow()` (`settings.py:100-117`) keeps shadow on when the variable is unset or unrecognised. The live value was not checked.
- **Would rise to medium if:** the Super Admin population included untrusted operators while the deployment switch is off.

**Detection:** after the fact only.
- R1: the ERROR line at `golive_test_org.py:65-66`, plus `shadow_lifted` for A (`testOrganization: true`), `golive_test_org_marked` for B, and no `cleared` for A.
- R2 and R4: an organization whose flag is off with no `shadow_lifted` after its latest `shadow_restored` or `golive_test_org_cleared`. The Going live card shows it off and not marked.
- R3 and R4: the `_unavailable` ERROR log.
- An informational point carried from the second audit: a successful revert (:255) is not written as `shadow_restored`. Its net effect is no change, and it shows in the settings document's `updatedAt`/`updatedBy` and in the 409.

**Code that would close them (for the user to decide; no code was changed).** Each was checked separately in the HEAD model:
- **R1 + R3:** in `delete_test_organization`, replace :189-191:
  - wrap `restore` in `try/except Exception` and treat a raise like a return of False;
  - when the mark was not put back, call `ao_settings.set_shadow(db, tenantId, True, actor=await views.actor_for(db, await views.build_caller(user)))` before raising the 409.
  - Model: the R1 shapes go to 0 and R3 to 0 of 550; R2 is unchanged.
- **R2:** in `put_shadow`, between the `if lifting:` block (:243-247) and `actor = ...` (:248), add `if body.shadow is False and not lifting: return await views.status_payload(db, caller, tenant)`.
  - An already-lifted request then writes and audits nothing. That matches the docstring's "changes nothing" and D-21's ungated no-op.
  - Model: the R2 shapes go to 0; R1 is unchanged.
- **Both together:** 0 bad in every three-actor combination.
- **R4:** not closable inside the request; it stays at 53 of 366 with both changes.
  - A bounded retry of the revert plus a CRITICAL log would narrow it.
  - Airtight options are design changes:
    - keep the mark on the organization's own `autonomy_settings` document, with a partial unique index for one at a time, so the exemption lift and the clear are each one conditional `update_one` and need no post-check, restore or revert;
    - or enforce at the consumer: treat a stored `shadow=False` as on unless `lift_decision` still passes, in `settings.shadow_state` (7 production call sites, central one `gate.py:320`).
  - The auditor's scratch file can seed regression tests.

### T-86-14-03 re-audit after 6b58bd655 (2026-11-14): superseded by 324340252

Kept for the record.

**Closed by 6b58bd655 and verified:**
- Read failures on the clear.
- The clear-side race (re-read after the delete; the mark is restored with a 409).
- The lift post-check.
- The 6b58bd655 tests failed 6 of 23 on ae0b01058 and passed at 6b58bd655.

**Second-audit finding, now closed by 324340252:** the gate-to-mark-read window.
- The gate passed the organization by exemption on one mark read.
- A clear landing before the second read (`_may_be_test_organization`) left `test_org_lift` False, so the lift was written with no post-check.
- Reproduced then as 200, flag off, no mark; the model gave 72 bad of 1144.

The residuals listed at the time (restore losing to a third mark, the two double faults, the unaudited revert) are carried forward as R1, R3, R4 and the informational point above. R2 is new in the third audit.

### T-86-14-03 first audit (2026-11-14, before 6b58bd655): superseded

Kept for the record. The read-failure paths and the clear-side race below were fixed by 6b58bd655. The lift-side window was fixed by 324340252.

- **Where:** `backend/autonomous_ops_golive_endpoints.py:166` (pre-fix) refused the clear only when `(await ao_settings.load(db, tenantId)).shadow is not True`. It never checked `.readable`.
- **Why it failed open:** `backend/autonomous_ops/settings.py` `load()` returns the dataclass default `shadow=True` (line 31) with `readable=False` in three cases: the tenant read raises (62-65), the `autonomy_settings` read raises (71-74), or the stored `shadow` is not a bool (82-86).
- **Reproduced:** a scratchpad probe on the private mongod at 127.0.0.1:27998 made the `autonomy_settings` read raise with the stored shadow False. `DELETE /test-organization` answered 200 and the mark was removed. The auditor confirmed the same result with a fake handle and through the non-bool path.
- **Race:** the check and the delete were not atomic.
- **Effect:** this contradicted D-23 ("the mark is cleared only while that organization's own shadow flag is back on") and PROH-86-14.

### D-23 exemption narrowness (requested check)

- **One mark by construction:** verified (fixed `_id`, `insert_one`, race test `:130-138`). "One at a time" holds for any two concurrent requests. R1 and R2 (three concurrent requests) can break it.
- **Platform owner and interactive session only:** verified on POST and DELETE, with the role matrix and an all-scope API key refused.
- **Typed name:** verified on the server (`confirmName.strip() == name`, :146-147) and in the dialog.
- **Audited:** mark and clear write to the platform chain, and the lift carries `testOrganization: true`. Audit writes are best-effort: a failure is logged and the stored mark stands, as the plan intends.
- **Fail-closed mark read:** verified (`golive.py:122-127`, test `:312-322`). Since 324340252 the gate's single read also decides the post-write check.
- **Clear refused while lifted:** verified before and after the delete. The lift side re-checks from the gate's own read.
- **Other paths:** no other code path writes the `shadow` field. The exemption skips the check-count and observation reads only for the marked organization, and every other organization keeps the full gate.
- **Detective, not preventive:** the server cannot tell a test organization from a customer one. Any ticked organization other than the platform one can be marked. The declared safeguards are the typed name, the audit event and the label. "Never a customer organization" appears only in the runbook and the dialog warning; nothing enforces it.

### Informational (not in the register, not blocking)

- **Archived notice reader:** `archive/backend-email-oneoff/send_pending_emails.py` (49e659791, user-approved) reads every organization's unsent notices with no tenant filter. It sits outside `backend/` with a do-not-run header. Nothing imports, schedules or allow-lists it. It contains no secrets.
- **Test fallback to port 27017:** `backend/tests/conftest.py:37` falls back to `mongodb://localhost:27017` when no URL environment variable is set. This predates Phase 86. The Phase 86 verify commands set all three variables to 27998.
- **Uncommitted pytest config:** `backend/pyproject.toml` carries an uncommitted `[tool.pytest.ini_options]` block. It is not a Phase 86 path. HEAD snapshots run through the tracked root `pytest.ini` (same `asyncio_mode = auto`), so Phase 86 tests do not depend on it.
- **Tests run:**
  - First audit: 201 backend tests on the private mongod and 117 vitest tests in 4 Phase 86 UI suites, all passed.
  - Re-audit: 245 backend tests in 13 Phase 86 security suites on the private mongod (0 skipped), plus pre-fix and HEAD snapshot runs.
  - Third audit: 129 backend tests in 6 suites in the working tree and in a HEAD snapshot, the two pre-fix snapshot runs, and the auditor's 70 tests plus the 1500-schedule stress runs.
- **Summary threat flags:** all 15 `## Threat Flags` sections say none beyond the register. There are no unregistered flags.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-14 | 41 | 35 | 6 (1 blocking: T-86-14-03; 5 non-blocking plan-time accepts) | gsd-security-auditor (sonnet) + secure-phase orchestrator probe |
| 2026-11-14 (re-audit after 6b58bd655) | 41 | 40 | 1 (blocking: T-86-14-03, gate-to-mark-read window; AR-86-01..05 accepted by the user) | gsd-security-auditor (sonnet) + secure-phase orchestrator reproduction, ASVS L1, block_on high |
| 2026-11-14 (third audit after 324340252) | 41 | 41 | 0 (residual notes R1-R4: low, non-blocking, open, not accepted) | gsd-security-auditor (sonnet, SECURED, L3 trace for T-86-14-03) + secure-phase orchestrator tests, snapshots and HEAD model, ASVS L1, block_on high |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log (AR-86-01..05, accepted by the user 2026-11-14)
- [x] `threats_open: 0` confirmed (third audit, HEAD 324340252)
- [x] `status: verified` set in frontmatter

**Approval:** verified by /gsd-secure-phase 86 on 2026-11-14 (threats_open: 0). Residual notes R1-R4 await the user's fix-or-accept decision; none is accepted.

## Security Audit 2026-11-14

| Metric | Count |
|---|---|
| Threats found | 41 |
| Closed | 40 |
| Open | 1 |

## Security Audit 2026-11-14

| Metric | Count |
|---|---|
| Threats found | 41 |
| Closed | 41 |
| Open | 0 |
