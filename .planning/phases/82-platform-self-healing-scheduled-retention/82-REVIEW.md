---
phase: 82-platform-self-healing-scheduled-retention
reviewed: 2026-10-30T22:00:00Z
depth: standard
files_reviewed: 54
files_reviewed_list:
  - App.tsx
  - backend/app_background_tasks.py
  - backend/app_startup.py
  - backend/autonomous_ops/health_messages.py
  - backend/autonomous_ops/ledger.py
  - backend/autonomous_ops/notify.py
  - backend/autonomous_ops/oncall.py
  - backend/autonomous_ops/selfheal.py
  - backend/autonomous_ops/views.py
  - backend/autonomous_ops_platform_endpoints.py
  - backend/autonomous_ops_retention_endpoints.py
  - backend/migrations/025_platform_health.py
  - backend/migrations/026_oncall_outbox.py
  - backend/migrations/027_retention_gate.py
  - backend/retention_endpoints.py
  - backend/retention_gate.py
  - backend/retention_job.py
  - backend/retention_service.py
  - backend/router_registry.py
  - backend/watchdog_ingest_endpoints.py
  - components/AutonomousOpsActivity.tsx
  - components/AutonomousOpsActivityList.tsx
  - components/AutonomousOpsHealthBanners.tsx
  - components/AutonomousOpsHealthCards.tsx
  - components/AutonomousOpsHealthChips.tsx
  - components/AutonomousOpsPlatformHealth.tsx
  - components/AutonomousOpsRetentionConfirmDialog.tsx
  - components/AutonomousOpsRetentionReview.tsx
  - components/AutonomousOpsStopBanner.tsx
  - components/RetentionPolicyDashboard.tsx
  - contexts/AutonomousOpsStatusContext.tsx
  - deploy/omni-watchdog/INSTALL.md
  - deploy/omni-watchdog/etc/oncall.env.example
  - deploy/omni-watchdog/etc/watchdog.conf.example
  - deploy/omni-watchdog/omni-watchdog.py
  - deploy/omni-watchdog/omni_watchdog/__init__.py
  - deploy/omni-watchdog/omni_watchdog/checks.py
  - deploy/omni-watchdog/omni_watchdog/config.py
  - deploy/omni-watchdog/omni_watchdog/incidents.py
  - deploy/omni-watchdog/omni_watchdog/paging.py
  - deploy/omni-watchdog/omni_watchdog/restart.py
  - deploy/omni-watchdog/omni_watchdog/run.py
  - deploy/omni-watchdog/omni_watchdog/services.py
  - deploy/omni-watchdog/omni_watchdog/state.py
  - deploy/omni-watchdog/omni_watchdog/sync.py
  - deploy/omni-watchdog/omni_watchdog/warnings.py
  - deploy/omni-watchdog/polkit/49-omni-watchdog.rules
  - deploy/omni-watchdog/systemd/mongod.service.d/50-omni-restart.conf
  - deploy/omni-watchdog/systemd/nginx.service.d/50-omni-restart.conf
  - deploy/omni-watchdog/systemd/omni-backend.service.d/10-omni-watchdog.conf
  - deploy/omni-watchdog/systemd/omni-watchdog.service
  - deploy/omni-watchdog/systemd/omni-watchdog.timer
  - services/autonomousOpsApi.ts
  - shared/autonomous-ops-banned-terms.json
findings:
  critical: 1
  warning: 5
  info: 5
  total: 11
status: issues_found
---

# Phase 82: Code Review Report

**Reviewed:** 2026-10-30
**Depth:** standard
**Files Reviewed:** production files above (test files in the scope list were read for context only and are not enumerated)

## Summary

Production code was read before tests, concentrating on the retention job and gate, the review token and confirm flow, the watchdog ingest route, the restart allowlist and polkit rule, tenant isolation and secrecy.

What holds up:
- Retention: the job iterates only the eight registry types. `NEVER_DELETED` is asserted at import and re-checked in `delete_type`. Every filter carries the stored tenant field on the raw handle. Deletion is by exact `_id` list plus the tenant field. A shortened period returns to counting. A malformed policy value falls back to the default.
- Confirm: it requires `control:platform_autonomous_ops` and an interactive session. The token is a hash over all waiting rows, including counts and `countedAt`, so a recount gives 409.
- Ingest route: the bearer comparison is constant-time and the credential is read on every call. It rejects non-loopback clients and any proxy header, and the body is capped at 256 KB. The credential is never logged.
- Restart path: units come from the constant `UNITS`. The polkit rule is exact-match on subject, action, unit and verb, and falls through to NO for every other `systemd1` action. Watchdog error strings are built from fixed templates plus exception class names, so the routing key, webhook URL and heartbeat URL do not reach events, errors or the sync body.
- Platform-health rows are filtered out of every tenant Activity query.

One data-loss finding against the "never delete before confirmation" rule remains (CR-01). The warnings cover a confirm that covers rows the reviewer never saw, a mislabelled certificate rule id, a poison-event wedge in the ingest, leftover un-gated delete code, and a misleading failure display on the manual cleanup button.

## Critical Issues

### CR-01: "adopt" auto-deletes a tenant or type that the first count pass never reached

**File:** `backend/retention_gate.py:92-104` (also `backend/retention_job.py:126-135`, `166-178`; `backend/retention_gate.py:222-237`)

**Issue:** `gate_state` returns `adopt`, which deletes immediately, for any row with `confirmedDays is None` whose `firstSeenAt` is later than the single global `confirmedAt`. The assumption (A-82-A12) is that such a row is a brand-new tenant or type with nothing old to review. But `firstSeenAt` is only set when the nightly job first reaches that (tenant, type) via `mark_seen`. The first counting pass does not reliably reach every tenant:

- `run_all` stops at `RUN_MAX_MINUTES` or on a lost lock (`stoppedEarly`).
- `run_tenant` does not guard `load_policy_days`, `mark_seen`, or the `update_one` inside `_record_count`. A Mongo error for one tenant aborts `run_all` before any run summary is written, and `retention_loop` retries every 5 minutes from the same tenant.

Failure scenario:
1. The first run counts tenants A..M and then stops or aborts. Rows for N..Z do not exist yet.
2. The Super Admin reviews the visible rows and confirms. `confirm()` sets the global `confirmedAt` to T.
3. At the next 02:00 run, tenants N..Z get `firstSeenAt` greater than T, so `gate_state` returns `adopt`.
4. `delete_type` immediately deletes their metrics, logs, location history and the other types older than the default periods. No count was ever shown and no one confirmed.

The same happens for a tenant created before T but not yet seen. This is irreversible deletion without confirmation, which the phase says must not happen.

**Fix:** Make "adopt" depend on the tenant or type genuinely being new, not on the run order. Two options:

```python
# in confirm(), before writing GATE_GLOBAL: seed every existing (tenant, type) row so none can later read as new
async for t in rdb.tenants.find({}, {"_id": 0, "id": 1}):
    for rtype in RETENTION_TYPES:
        await rdb[GATE].update_one(
            {"tenantId": t["id"], "type": rtype.id},
            {"$setOnInsert": {"tenantId": t["id"], "type": rtype.id, "confirmedDays": None,
                              "firstSeenAt": now}},   # == confirmedAt, so "seen > confirmed_at" is False -> first_run
            upsert=True)
```

Alternatively, adopt only when the tenant document's `createdAt` is after `confirmedAt`. In addition, wrap the per-tenant body of `run_all` in try/except so one bad tenant cannot leave the remaining tenants unseen, and so the run summary is always written.

## Warnings

### WR-01: One confirmation covers every waiting row, but only the first 25 are shown, and the reviewer attests to "every organization listed"

**File:** `components/AutonomousOpsRetentionReview.tsx:313-318` (and `components/AutonomousOpsRetentionConfirmDialog.tsx:38-39`, `104`)

**Issue:** The review endpoint pages at 25 rows. The token and `confirm()` cover all rows (`retention_gate.confirm` confirms every eligible row), and the dialog summary shows totals over all rows. The Confirm deletion button is enabled whenever `countable > 0`, even while `state.nextOffset !== null` (more rows not yet loaded). With 20 tenants and 8 types there are 160 rows. A reviewer who looks at the first page, ticks "I have reviewed the counts for every organization listed", and confirms authorizes deletion for about 135 rows they never saw. The checkbox claim is true only for the loaded rows.

**Fix:** Disable Confirm until all pages are loaded (`state.nextOffset === null`), or have the dialog state the number of rows not yet displayed and require loading them first:

```tsx
const allLoaded = state?.nextOffset === null;
<button ... disabled={running || countable <= 0 || !allLoaded}>
...
{!allLoaded && <p className={MUTED}>Load all {review.total} rows before confirming.</p>}
```

### WR-02: Certificate rule id is off by one rung for 14d, 7d and 1d

**File:** `backend/autonomous_ops/health_messages.py:31, 136-137` (rung source `deploy/omni-watchdog/omni_watchdog/warnings.py:27`)

**Issue:** `CERT_LADDER` has four thresholds but only three rungs: 30d and 14d share rung 1, 7d is rung 2, 1d is rung 3. `_CERT_RULES` has four entries and is indexed by `rung - 1`. Result, verified by running `_rule_id`:

| Real condition | Rule id shown |
|---|---|
| 14-day warning | `cert-expiry-30d` |
| 7-day warning | `cert-expiry-14d` |
| 1-day critical (and expired) | `cert-expiry-7d` |
| unreadable certificate (rung 2) | `cert-expiry-14d` |

`cert-expiry-1d` is unreachable. The rule id is the audit-facing explanation under every certificate row in Platform Activity, and it is stored on the ledger row (`reason.ruleId`). It is wrong for the most urgent rungs. As a related defect, an unreadable certificate renders "`<path> expires —`" (`_reason_and_result`, cert_warning branch), because `daysLeft` is absent.

**Fix:** Derive the rule from the threshold, not the rung. Have the watchdog send the suffix (for example `params["threshold"] = 14`), or map `daysLeft` with `<=1 -> 1d`, `<=7 -> 7d`, `<=14 -> 14d`, otherwise `30d`. Add a distinct "unreadable" rule and wording.

### WR-03: A single un-renderable event wedges the whole watchdog sync permanently

**File:** `backend/autonomous_ops/selfheal.py:152-177` (with `backend/autonomous_ops/health_messages.py:68-71`, `backend/autonomous_ops/ledger.py:176`)

**Issue:** `ingest_events` catches only `ledger.LedgerUnavailable`. `record_platform_health` calls `health_messages.render(...)` before its `try`, and `_num` does `int(round(value))`. `clean_params` only filters NaN, so `inf` passes. `pydantic.model_validate_json` accepts `1e999` and `Infinity`. Verified: an event `{"kind":"disk_forecast","params":{"forecastDays":1e999}}` raises `OverflowError` from `render`. `post_sync` then converts it to 503 for the whole request.

The watchdog only bumps `tries` or removes spool entries on a 200 (`sync.sync_cycle`), so the same event is resent first, in order, every minute. From then on no sync completes. The platform stop is not refreshed. The outbox is never handed out, test alerts are never picked up, and no later event is recorded. The heartbeat still updates, so the dead-man alarm stays quiet.

The watchdog is trusted, but a corrupt `state.json` or spool value, or a future bug, reaches this path.

**Fix:** Treat a render or other per-event failure as a dropped event, not a request failure:

```python
try:
    await ledger.record_platform_health(...)
except ledger.LedgerUnavailable as exc:
    ...; continue
except Exception as exc:               # a malformed event must not wedge the spool
    logger.error("selfheal: event %s dropped: %s", event_id, type(exc).__name__)
    dropped += 1
    continue
```

Also reject non-finite numbers in `clean_params` (`math.isfinite`), and make `_num` return None for non-finite input.

### WR-04: Un-gated platform-wide delete paths remain in `retention_service.py`

**File:** `backend/retention_service.py:30-47` (`purge_agent_telemetry`) and `57-127` (`RetentionService.cleanup_*`, `run_cleanup`)

**Issue:** Phase 82 routes both the nightly job and the manual run through `retention_job`. But `purge_agent_telemetry` and `cleanup_agent_telemetry` (which delete by tenant with no gate), and `RetentionService.cleanup_system_metrics`, `cleanup_notifications`, `cleanup_agent_location_history` and `cleanup_agent_uptime_rollups`, are still importable. The `RetentionService` methods delete across all tenants with no tenant filter. A grep of non-test code shows no callers; only tests, one of which monkeypatches `run_cleanup` to prove it is off the manual path. Any future caller, for example a restored cron or a copy-pasted endpoint, silently bypasses the confirmation gate and the tenant scoping that this phase established. `purge_agent_telemetry` also reads `retention_days` from `retention_policies` without the `valid_days` check, so a malformed value (0 or negative) deletes everything.

**Fix:** Delete the unused functions (`purge_agent_telemetry`, `cleanup_agent_telemetry`, and the `RetentionService` delete methods), and update or remove the legacy tests that exercise them. If the class must stay, make each delete method raise unless called by `retention_job`.

### WR-05: "Run Cleanup Now" reports "Cleanup completed" for 409, 403 and 400 answers

**File:** `components/RetentionPolicyDashboard.tsx:44-53`

**Issue:** `runCleanup` does `const d = await r.json(); setLastResult(d);` without checking `r.ok`. This phase added new failure answers to `POST /api/retention/run`: 409 (a run is in progress), 400 (no tenant), and 403 (not an admin). Each returns `{"detail": ...}`. The component then renders the green "Cleanup completed at Invalid Date" card with no tiles (`lastResult.ran_at` is undefined). A tenant admin who hits the busy lock, or a non-admin, is told the cleanup completed.

**Fix:**
```tsx
const r = await authFetch('/api/retention/run', { method: 'POST' });
const d = await r.json().catch(() => ({}));
if (!r.ok) { showToast(d.detail || "Couldn't run cleanup.", 'error'); return; }
setLastResult(d);
```

## Info

### IN-01: Outbox pages are trigger-only, so each Autonomous Ops notice leaves an open on-call incident

**File:** `backend/autonomous_ops/oncall.py:102` and `deploy/omni-watchdog/omni_watchdog/paging.py:366-368`

**Issue:** `enqueue` always creates `kind: "trigger"` with `dedupKey: None`. The watchdog then uses a unique key `omni:<host>:<id>` per message and never sends the matching resolve. On PagerDuty each stop, breaker or rate-limit notice opens its own incident that nothing auto-resolves. Webhook channels see the same one-way pattern. If this is intended (D-04), document it in INSTALL.md. Otherwise send a resolve when the notice's condition clears.

### IN-02: `testAlert.error` and the Activity `error` params are not URL-scrubbed, unlike the channel status path

**File:** `backend/autonomous_ops/oncall.py:147-152`, `backend/autonomous_ops/selfheal.py:256-259, 288-291`

**Issue:** `channel_status` runs delivery errors through `_safe_error` (URL replaced by `[url]`). But `oncall.test_view`, the `ack_delivered` error stored on the outbox, and the `test_alert` and `page_failed` ledger params keep the watchdog's text with only `clean_text`. Today the watchdog builds these from fixed templates, so no URL reaches them. The backend's own claim ("never a key or URL") then rests on the watchdog alone. Apply `_safe_error` in `_view`, `ack_delivered` and `record_test_result` for defence in depth.

### IN-03: Loopback test compares literal strings

**File:** `backend/watchdog_ingest_endpoints.py:31, 52`

**Issue:** `_LOOPBACK = {"127.0.0.1", "::1"}`. If uvicorn is ever bound dual-stack, a local IPv4 client appears as `::ffff:127.0.0.1` and the watchdog is locked out with 403. Also, uvicorn's proxy-header handling is trusted for 127.0.0.1, so nginx on the same host rewrites `client.host`. The "unreachable through nginx" property depends on nginx always adding `X-Forwarded-For`. The bearer token still protects the route, but consider an explicit `location /api/internal/ { return 404; }` in nginx. Use `ipaddress.ip_address(host).is_loopback` after unmapping IPv4-mapped addresses.

### IN-04: INSTALL.md section 12 names a control that does not exist there

**File:** `deploy/omni-watchdog/INSTALL.md:264-265`

**Issue:** It says "sooner with **Run cleanup now** on the Platform health panel". The manual run is **Run Cleanup Now** on the Data Retention Policies page (tenant admin, own tenant only). The Platform health panel has only the review and Confirm deletion. An operator following the checklist will not find the button, and the manual run cannot count other tenants.

### IN-05: Service state from the snapshot is not validated server-side

**File:** `backend/autonomous_ops/selfheal.py:332-340` and `components/AutonomousOpsPlatformHealth.tsx:131-141`

**Issue:** `_service` passes `state` through as any string up to 32 characters. The UI indexes `SERVICE_LABEL[state]` and `SERVICE_CHIP[state]` with it. An unrecognised value (a newer watchdog, a corrupt snapshot) renders "Last known: undefined" for the stale case, and passes `undefined` to `HealthChip` for the fresh case, which destructures `CHIPS[undefined]` and throws, taking down the Platform health section. Whitelist the vocabulary in `_service` (map unknown to null), or guard in the UI.

---

_Reviewed: 2026-10-30_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
