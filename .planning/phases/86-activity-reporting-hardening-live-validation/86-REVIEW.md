---
phase: 86-activity-reporting-hardening-live-validation
reviewed: 2026-11-14T12:00:00Z
depth: standard
files_reviewed: 69
files_reviewed_list:
  - archive/backend-email-oneoff/send_pending_emails.py
  - backend/app_middleware.py
  - backend/app_startup.py
  - backend/autonomous_ops/__init__.py
  - backend/autonomous_ops/reporting/__init__.py
  - backend/autonomous_ops/reporting/digest.py
  - backend/autonomous_ops/reporting/digest_job.py
  - backend/autonomous_ops/reporting/digest_text.py
  - backend/autonomous_ops/reporting/export.py
  - backend/autonomous_ops/reporting/export_pdf.py
  - backend/autonomous_ops/reporting/golive.py
  - backend/autonomous_ops/reporting/golive_test_org.py
  - backend/autonomous_ops/reporting/rule_names.py
  - backend/autonomous_ops/reporting/stats.py
  - backend/autonomous_ops/views.py
  - backend/autonomous_ops_golive_endpoints.py
  - backend/autonomous_ops_platform_endpoints.py
  - backend/autonomous_ops_reporting_endpoints.py
  - backend/catalogue_mounts_autonomous_ops.py
  - backend/dlp_service.py
  - backend/email_utils.py
  - backend/export_controls.py
  - backend/export_report_endpoint.py
  - backend/export_service.py
  - backend/migrations/035_activity_reporting.py
  - backend/reporting_endpoints.py
  - backend/router_registry.py
  - backend/tests/test_autonomous_ops_copy.py
  - backend/tests/test_autonomous_ops_digest.py
  - backend/tests/test_autonomous_ops_digest_job.py
  - backend/tests/test_autonomous_ops_endpoints_writes.py
  - backend/tests/test_autonomous_ops_export.py
  - backend/tests/test_autonomous_ops_export_registry.py
  - backend/tests/test_autonomous_ops_golive.py
  - backend/tests/test_autonomous_ops_golive_test_org.py
  - backend/tests/test_autonomous_ops_golive_test_org_race.py
  - backend/tests/test_autonomous_ops_ledger.py
  - backend/tests/test_autonomous_ops_stats.py
  - backend/tests/test_autonomous_ops_stop_drill.py
  - backend/tests/test_autonomous_ops_two_tenant.py
  - backend/tests/test_catalogue_slice_autonomous_ops.py
  - backend/tests/test_migration_035_activity_reporting.py
  - backend/tests/test_notification_audience_structure.py
  - components/AutonomousOpsActivity.tsx
  - components/AutonomousOpsActivityList.tsx
  - components/AutonomousOpsEmptyStateCard.tsx
  - components/ReportingDashboard.tsx
  - components/autonomousOpsGoLive/GoLiveCard.tsx
  - components/autonomousOpsGoLive/GoLiveChecklist.tsx
  - components/autonomousOpsGoLive/GoLiveOrganizations.tsx
  - components/autonomousOpsGoLive/ShadowDialogs.tsx
  - components/autonomousOpsGoLive/TestOrgDialogs.tsx
  - components/autonomousOpsGoLive/goLiveCopy.ts
  - components/autonomousOpsStats/ExportDialog.tsx
  - components/autonomousOpsStats/ReportExportCard.tsx
  - components/autonomousOpsStats/StatsCard.tsx
  - components/autonomousOpsStats/StatsRuleTable.tsx
  - components/autonomousOpsStats/TimeSavedBlock.tsx
  - components/autonomousOpsStats/reportingCopy.ts
  - docs/autonomous-ops-go-live.md
  - services/autonomousOpsGoLive.ts
  - services/autonomousOpsReporting.ts
  - shared/autonomous-ops-banned-terms.json
  - src/__tests__/autonomousOpsCopy.test.ts
  - src/__tests__/autonomousOpsExport.test.tsx
  - src/__tests__/autonomousOpsGoLive.test.tsx
  - src/__tests__/autonomousOpsGoLiveTestOrg.test.tsx
  - src/__tests__/autonomousOpsStats.test.tsx
  - src/__tests__/autonomousOpsTableScroll.test.tsx
findings:
  critical: 1
  warning: 7
  info: 7
  total: 15
status: issues_found
---

# Phase 86: Code Review Report

**Reviewed:** 2026-11-14
**Depth:** standard
**Files Reviewed:** 69
**Status:** issues_found

## Summary

Reviewed the phase 86 reporting, digest, export, go-live and test-organization code at HEAD, plus the phase hunks in the large pre-existing files (app_middleware, dlp_service, export_report_endpoint, export_service, reporting_endpoints). The 157 backend tests for golive, test-org (including the race suite), export, digest and stats pass on the current tree. The tenant-scoped queries in stats, digest, export and go-live all carry an explicit tenantId on the raw handle, and the CSV, PDF and email builders escape or sanitise server strings. No cross-tenant leak was found in the reporting read paths.

The main defects are in the hardening work rather than in the reporting logic: the new export DLP scan silently stops scanning on large exports (fail-open), the new export allowance is bypassed by API keys, the new page-size middleware turns a crafted query value into a 500 on every route, and the test-organization exemption is documented as refusing customer organizations when the code does not. One go-live UI dead end (a marked organization that is no longer ticked cannot be cleared) and a digest counting defect are also reported.

No structural (fallow) findings were supplied.

## Critical Issues

### CR-01: Export DLP scan fails open on large exports, non-ASCII content and tenants with many policies

**File:** `backend/dlp_service.py:205-215` (scan_export), `backend/dlp_service.py:209` (truncation and escaping)
**Issue:** `scan_export` builds one string with `"\n".join(json.dumps(r, default=str) for r in rows)[:_EXPORT_SCAN_MAX_CHARS]`. Three separate ways a block policy does not fire:
1. Everything after the first 2,000,000 characters is never scanned. The unbounded report types served by `/api/reports/export` (Asset Inventory, Audit Log, User Activity, ...) routinely exceed that, so a `block` policy stops working exactly on the large exports it exists for. The route then delivers the file with no finding and no incident.
2. `json.dumps` defaults to `ensure_ascii=True`, so every non-ASCII character is rewritten as `\uXXXX` before the admin-written regex runs. A policy for a name, an address or a keyword containing an accented or non-Latin character can never match. Quotes and backslashes are escaped the same way, so `^`/`$`-anchored or quote-containing patterns behave differently from what the admin wrote.
3. Policies are loaded with `.to_list(100)`; the 101st enabled policy of a tenant is silently ignored, including a block policy.

Only `POLICY_UNEVALUATED` (invalid or slow pattern) fails closed. Truncation, escaping and the policy cap do not.
**Fix:**
```python
# scan in chunks instead of truncating; keep the original characters
def _chunks(rows, limit=_EXPORT_SCAN_MAX_CHARS):
    buf, size = [], 0
    for r in rows:
        line = json.dumps(r, default=str, ensure_ascii=False)
        if size + len(line) > limit and buf:
            yield "\n".join(buf); buf, size = [], 0
        buf.append(line); size += len(line) + 1
    if buf:
        yield "\n".join(buf)

def _scan_export_chunks(chunks, policies):
    blocking, alerting = [], []
    for text in chunks:
        b, a = _scan_export_text(text, policies)
        blocking += b; alerting += a
    return blocking, alerting
```
and fetch every enabled policy (`async for` with no 100 cap, or fail closed with a "too many policies" block finding when the count exceeds the cap). Add tests with a block hit placed after 2 MB, a non-ASCII pattern, and 101 policies.

## Warnings

### WR-01: Export allowance and bulk-export detection are bypassed by API keys

**File:** `backend/export_controls.py:41-52` (`_caller`), `backend/export_controls.py:113-115`; route `backend/autonomous_ops_reporting_endpoints.py:60-64`
**Issue:** `_caller` only recognises a bearer JWT in the `Authorization` header. `/api/autonomous-ops/export` (matched by `EXPORT_PATHS`) authenticates with `get_current_user_or_api_key`, which takes API keys from the `X-API-Key` header. For such a request `_caller` returns `None` and the middleware passes the request through untouched: no daily count or size limit, no `export_usage` record, no `data.export` audit event, no bulk-export check. A key holding `export:reports` and `view:autonomous_ops` can export without limit, which contradicts the module docstring ("every route that hands tenant data out"). The route's own `autonomous_ops.export` audit event still exists, but the allowance and the bulk-export incident do not apply.
**Fix:** Identify the caller the same way the route does. Either have `_caller` fall back to resolving `X-API-Key` (key id as the usage identity, tenant from the key), or, simpler, enforce the allowance inside `export.deliver` for non-JWT callers by calling the same `_usage`/`_add_usage` helpers keyed on the key's tenant and key id. Add a test that an `X-API-Key` export beyond `DAILY_EXPORTS` answers 429.

### WR-02: `PageSizeCapMiddleware` raises ValueError (500) on a crafted page-size value, before authentication

**File:** `backend/app_middleware.py:195-196`
**Issue:** The clamp tests `v.strip().isdigit() and int(v) > MAX_PAGE_SIZE`. `str.isdigit()` is true for characters such as superscripts and circled digits that `int()` rejects (`'²'.isdigit()` is True, `int('²')` raises `ValueError`; verified). `?limit=%C2%B2` on any route therefore raises inside this raw ASGI middleware and the client gets a 500 with a logged traceback. It runs outside the auth dependency, so it is reachable unauthenticated on every endpoint.
**Fix:**
```python
def _over_cap(v: str) -> bool:
    v = v.strip()
    return v.isascii() and v.isdigit() and int(v) > MAX_PAGE_SIZE
capped = [(k, str(MAX_PAGE_SIZE) if k in _PAGE_SIZE_PARAMS and _over_cap(v) else v) for k, v in pairs]
```
Add a test with `limit=%C2%B2`. (Also note the rewrite only happens when a value was clamped, so the latin-1/UTF-8 round trip through `urlencode` is limited to those requests.)

### WR-03: `regex` is not a declared dependency, so the admin-pattern timeout silently disappears

**File:** `backend/dlp_service.py:15-18`, `backend/dlp_service.py:164-174`; `backend/requirements.txt` (no entry)
**Issue:** The 0.5 s policy-pattern timeout exists only when `import regex` succeeds. The module is installed in the current venv, but `requirements.txt` does not list it (the comment says the venv "ships it"). On a fresh install the `except ImportError` path falls back to `re.search` with no timeout. That runs in `asyncio.to_thread`, but CPython's `re` holds the GIL for the whole match, so one catastrophic-backtracking policy pattern stalls the entire event loop for every tenant on the next export. `validate_policy_pattern` only checks that the pattern compiles, so it does not prevent this.
**Fix:** Add `regex>=2024.0` to `backend/requirements.txt`, and in the fallback path treat a block policy as unevaluable (fail closed) or refuse to start the scan instead of running an unbounded `re.search`. Also remove the confusing `except (TimeoutError, re.error, Exception)` tuple in favour of `except Exception`.

### WR-04: The test-organization exemption is documented as refusing customer organizations, but any ticked organization can be marked

**File:** `backend/autonomous_ops_golive_endpoints.py:133-147` (post_test_organization); `docs/autonomous-ops-go-live.md:35-37`; `backend/autonomous_ops/reporting/golive.py:130-141`
**Issue:** The doc says "A customer organization, the platform organization and an organization without the Autonomous Ops screen are refused." The route refuses only the platform organization (409) and an unknown or unticked one (404). Nothing in the data model separates a test organization from a customer one, so a Super Admin (or a stolen Super Admin session) who types a real customer's name can exempt it from all five checks and the seven-day observation, and the lift is the only thing that matters for taking a live customer out of shadow. The typed name is a confirmation of intent, not a restriction. Either the doc is wrong or the control is missing.
**Fix:** Decide which. If customers must be refused, require an explicit marker on the tenant (for example a `testOrganization: true` flag that only Add Tenant or a platform route can set) and check it in `post_test_organization`. If not, correct the doc sentence and add a prominent line to the mark dialog and the audit event ("this organization will skip the go-live gate"), and include `tenantName` in the lift audit event so a review can see which organization was exempted.

### WR-05: A marked test organization that is no longer ticked can neither be cleared in the UI nor replaced

**File:** `components/autonomousOpsGoLive/GoLiveOrganizations.tsx:214` and `:96-122`; `backend/autonomous_ops/reporting/golive.py:200-208`
**Issue:** The overview lists only `sweep._ticked_tenants` organizations, while the mark is stored independently and returned as `testOrganization`. Clear (`TestOrgAction`) is rendered only inside an organization's own row. If the marked organization's Autonomous Ops screen is later unticked (or the tenant is removed), its row disappears, `anyMarked` stays true because `testOrganization` is still set, and the UI offers neither "Clear test mark" nor "Use as test organization" for any other organization. The server `DELETE` would work (it needs no tick), so only the UI is stuck; the platform owner has to call the API by hand. The exemption also silently reactivates if the organization is ticked again.
**Fix:** In `GoLiveOrganizations`, when `testOrganization` is set but no row matches `testOrganization.id`, render a separate "Test organization: {name}" line with a Clear button (calling `onClear` with a synthetic `{id, name, shadow: true}`), and let the server clear the mark when the tenant is unticked or deleted (or at least have `overview` return `testOrganization.ticked`).

### WR-06: Digest "ran" and "undone" groups key on `finishedAt`, which is rewritten by later transitions

**File:** `backend/autonomous_ops/reporting/digest.py:72-78`; root cause `backend/autonomous_ops/ledger.py:132-133` and `backend/autonomous_ops/verify.py:173`
**Issue:** `ledger.transition` does `sets.setdefault("finishedAt", now)` on every move into a terminal state. `executed` is terminal, and verification then moves `executed -> verified` through the same call without passing `finishedAt`, so the row's `finishedAt` is overwritten with the verification time. The digest selects `state in (executed, verified)` with `finishedAt` inside the 24-hour window. A row executed at 06:55 and verified at 07:10 is counted in the digest that runs at 07:00 (state `executed`, finishedAt 06:55) and again in the next day's digest (finishedAt 07:10), and a row executed before the window that verifies inside it is counted as ran in a day it did not run. Counts in the digest and the at-most-once claim therefore do not match what ran in the window.
**Fix:** Window on the time the action ran, not the last terminal transition: either record a stable `executedAt` (set once on the first terminal transition) and index/query that, or have `transition` keep the first `finishedAt` for `executed -> verified` (`"$set"` only when the previous state was not already terminal). Add a test of an `executed` row verified after the window end.

## Info

### IN-01: Digest is recorded as "sent" even when both the notice and every email failed

**File:** `backend/autonomous_ops/reporting/digest.py:176-184`
**Issue:** `_post_notice` returns False and `_send_emails` may return `{sent: 0, failed: n}`, yet the claim is updated to `state: "sent"` and the loop never retries that day; only a log line (and the `notice`/`email` fields on the claim) records the loss. The at-most-once trade-off is documented, but a fully failed digest is indistinguishable from a sent one in the state field.
**Fix:** Set `state` to `"failed"` when `noticed` is False and `emailed["sent"] == 0`, and let `run_once` count it in `failed` so the loop log shows it.

### IN-02: Confirm-name comparison trims the typed value but not the stored name

**File:** `backend/autonomous_ops_golive_endpoints.py:146`
**Issue:** `body.confirmName.strip() != name` where `name = str(tenant.get("name") or tenant_id)` is not stripped. An organization whose stored name has leading or trailing whitespace can never be confirmed: the UI compares trimmed to trimmed (`matches`) and sends the trimmed text, so the server answers 422 "Type the organization's name exactly".
**Fix:** `if body.confirmName.strip() != name.strip():` (and use the stripped name in the audit event).

### IN-03: Empty exports (204) are counted as exports by the export middleware

**File:** `backend/export_controls.py:150-155`
**Issue:** The record step runs for any `200 <= status < 300`. `/api/autonomous-ops/export` answers 204 when nothing matches; that response consumes one of the 200 daily exports and writes a `data.export` audit event with 0 bytes and `rows` unset, although nothing left the system.
**Fix:** Record only when `seen["bytes"] > 0` (or `status != 204`).

### IN-04: `email_utils.send_email_async` guard is dead and a bad header raises instead of returning False

**File:** `backend/email_utils.py:22-35`
**Issue:** `SMTP_HOST` defaults to `"localhost"`, so `if not smtp_host` can never be true and a deployment with no mail configured tries a local connection and logs a failure per message. `msg["Subject"] = subject` and `msg["To"] = ...` run before the `try`; a subject or address containing CR/LF raises `ValueError` (verified for `EmailMessage`), which contradicts the function's `-> bool` contract for callers that only wrap it in a broad `except` at the call site. Recipient addresses are logged at INFO.
**Fix:** Default `smtp_host` to `""`, move header assembly inside the `try` (or strip control characters from `subject` first), and log a count or a masked address instead of the full recipient list.

### IN-05: The in-app digest reaches `manage:agents` holders regardless of `view:autonomous_ops`

**File:** `backend/autonomous_ops/reporting/digest.py:103-111`; `backend/notification_audience.py:36-40`
**Issue:** The digest lists hosts, targets and rule names and is addressed to the `tenant_admins` audience, which `reader_filter` grants to anyone holding `*` or `manage:agents`. A user with `manage:agents` but without the Autonomous Ops screen sees the digest in the notification feed, while the email goes to admin-role users only. Not a cross-tenant leak; an intra-tenant audience mismatch.
**Fix:** Either accept and document it, or add a dedicated audience (for example `autonomous_ops_admins`) that `reader_filter` grants only with `view:autonomous_ops`.

## Incremental review: gap plan 86-16 (2026-11-14)

**Scope:** `git diff 07f8bf9ba..HEAD` of `components/autonomousOpsGoLive/GoLiveOrganizations.tsx`, `components/autonomousOpsStats/StatsRuleTable.tsx` and the new `src/__tests__/autonomousOpsTableScroll.test.tsx` (G-86-5, tables clipped at 1024-1280 px). The other 68 files are unchanged by this plan and were not re-reviewed. The new test file passes (8/8 on the current tree).

**Assessment:** The change is small and correct for what it sets out to do. Each wide table now sits in its own `role="region"` / `tabIndex={0}` / `overflow-x-auto` wrapper; the wrapper lives inside the component, so the Show all and glossary controls stay outside it; the `<caption>`, row/column headers and column order are untouched; the card layout and the 1024 px switch are unchanged. The ancestors up to the card (`section.card p-6`, `div.min-w-0`, `section.flex.flex-col`) are block or column-flex containers, so the wrapper can shrink below the table width. The Organizations card `dl` change (`grid-cols-1 sm:grid-cols-2`, `col-span-full`) is valid Tailwind and the test pins it. No bug, security or data-handling defect was found. Three robustness and quality items follow. None of them changes the earlier findings or their IDs.

### WR-07: The off-screen Action / Refused / simulation columns have no visual scroll cue

**File:** `components/autonomousOpsGoLive/GoLiveOrganizations.tsx:137`, `components/autonomousOpsStats/StatsRuleTable.tsx:51`
**Issue:** Between 1024 px and about 1280 px with the sidebar open, the 86-16 fix makes the table scroll sideways, but nothing shows that more content exists to the right. The column that is pushed out of view on the Organizations table is the Action column, which holds the only way to lift or restore shadow mode, and on the Statistics table the Refused and simulation columns. Browsers with overlay scrollbars (macOS default, touch laptops) hide the scrollbar until the user scrolls, so a user can read "Acme, Shadow on, 5 days" and never learn there is a Lift button. The fix removes the clipping, but not the hidden-primary-action problem; the 1024 px switch is still viewport-based while the real constraint is the card width (86-16 itself records about 884 px and 946 px as the needed card widths).
**Fix:** Add a cue. Either a scroll-shadow on the right edge of the region (CSS `background-attachment: local, scroll` gradient, or a small "scroll for more" hint rendered when `scrollWidth > clientWidth`), or switch to the card layout on the card's own width (a `ResizeObserver` on the wrapper, or a container query) instead of `(min-width: 1024px)`, so the table is only drawn when it fits. The second option also removes the need for the scroll region at most widths.

### IN-06: The region wrapper is an unconditional tab stop and a duplicate-named landmark, even when nothing overflows

**File:** `components/autonomousOpsGoLive/GoLiveOrganizations.tsx:137`, `components/autonomousOpsStats/StatsRuleTable.tsx:51`
**Issue:** `tabIndex={0}` plus `role="region"` is applied at every width where the table is drawn, including 1280 px and wider where nothing scrolls. Each table then adds one extra Tab stop and one extra landmark, and the region's `aria-label` repeats the table's `<caption>` text word for word, so a screen reader announces the same name twice ("Shadow mode by organization, region", then "Shadow mode by organization, table"). The test even pins that the card layout adds no extra tab stop (`autonomousOpsTableScroll.test.tsx:81`), which shows the cost was considered for cards but not for a non-overflowing table. The wrapper's `tabIndex` is only needed (axe `scrollable-region-focusable`) when the content has no focusable child; the Organizations table does have buttons, and the Statistics table has none, so the two cases differ.
**Fix:** Keep the focusable region for the Statistics table (no interactive content inside) and drop `tabIndex`/`role` on the Organizations wrapper, whose buttons already satisfy the rule, or set `tabIndex` only while `scrollWidth > clientWidth`. Optionally shorten the region label (for example "Scrollable: ...") so it is not identical to the caption.

### IN-07: Measured pixel widths are written into JSDoc and will go stale

**File:** `components/autonomousOpsGoLive/GoLiveOrganizations.tsx:201-204`, `components/autonomousOpsStats/StatsRuleTable.tsx:140-141`
**Issue:** The doc comments state "about 884 px" and "about 946 px". These are derived from the `min-w-[...]` values on the header cells plus padding, which are right beside the comment; the next column or copy change will silently make the comment wrong (the plan itself had to correct wrong budget claims in 86-UI-SPEC.md). The Organizations comment line is also wrapped unevenly, with a one-line orphan ("table scrolls sideways ... (G-86-5). Whether a").
**Fix:** Drop the numbers and say "when the card is narrower than the sum of the column minimum widths (see the `min-w-[...]` classes)", or derive a shared constant from the columns.

## Known items (cross-reference)

Not counted in the frontmatter totals; recorded elsewhere and still present in the code at HEAD.

- 86-SECURITY.md R1 (third concurrent mark vs the clear's restore): `backend/autonomous_ops_golive_endpoints.py:182-192`, `backend/autonomous_ops/reporting/golive_test_org.py:56-68` (restore returns False and only logs).
- 86-SECURITY.md R2 (stale "already lifted" PUT shadow=false writes `set_shadow(False)` without the gate or the audit): `backend/autonomous_ops_platform_endpoints.py:241-249` and the `lifting`-only audit at `:258-259`.
- 86-SECURITY.md R3 (`golive_test_org.restore()` raising a non-duplicate error gives 503 with the mark gone and the flag off): `backend/autonomous_ops_golive_endpoints.py:190`.
- 86-SECURITY.md R4 (the revert `set_shadow(True)` raising gives 503 with the flag off and the mark gone): `backend/autonomous_ops_platform_endpoints.py:255`.
- 86-UI-REVIEW.md Top fix 1 (org table and StatsRuleTable clipped at 1024-1280 px, `WIDE_QUERY` at lg): `components/autonomousOpsGoLive/GoLiveOrganizations.tsx:13`, `components/autonomousOpsStats/StatsRuleTable.tsx:19`.
- 86-UI-REVIEW.md Top fix 2 ("12 of 7 days" uncapped in `daysLabel`, the "—" ambiguity): `components/autonomousOpsGoLive/goLiveCopy.ts` (`daysLabel`).
- 86-UI-REVIEW.md Top fix 3 (test-org exemption wording, competing "Use as test organization" button): `components/autonomousOpsGoLive/GoLiveOrganizations.tsx:104-122`, `goLiveCopy.ts`.
- 86-UI-REVIEW.md Pillar 6 (Export button hidden when Statistics fails; stale rows after a failed refetch): `components/AutonomousOpsActivity.tsx:50,82`, `components/autonomousOpsGoLive/GoLiveCard.tsx:41-46`.

---

_Reviewed: 2026-11-14_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
