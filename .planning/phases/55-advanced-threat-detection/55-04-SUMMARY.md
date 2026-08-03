---
phase: 55-advanced-threat-detection
plan: 04
subsystem: api
tags: [ocsf, siem, webhook, fastapi, asyncio, fire-and-forget]

requires:
  - phase: 55-advanced-threat-detection (55-01)
    provides: SiemEngine._trigger_alert / correlate_native_findings correlation case creation
  - phase: 55-advanced-threat-detection (55-03)
    provides: UEBAService._persist_alert anomaly persistence + autonomous remediation trigger
  - phase: 53-autonomous-remediation
    provides: remediation_audit_service.write_audit as the single funnel for all remediation stage transitions
provides:
  - soc_integration_service.push_ocsf_event(event_type, source_doc) — OCSF Detection Finding (class_uid=2004) builder + fire-and-forget webhook dispatch
  - three outbound push call sites: siem_engine._trigger_alert (threat.correlation), ueba_service._persist_alert (ueba.anomaly), remediation_audit_service.write_audit (remediation.event)
affects: [siem-integration, soc-webhooks, future SOC/SIEM ingestion work]

tech-stack:
  added: []
  patterns:
    - "Module-level singleton service instance (_webhook_service = WebhookService()) reused across calls, mirrors notification_manager's pattern"
    - "Fire-and-forget dispatch: asyncio.create_task(...) wrapped in swallow-and-log try/except so a delivery failure never propagates into the emitting pipeline"

key-files:
  created:
    - backend/soc_integration_service.py
    - backend/tests/test_soc_integration.py
  modified:
    - backend/ocsf_endpoints.py (hoisted severity_map to module level so it's importable)
    - backend/siem_engine.py (push after security_cases insert in _trigger_alert)
    - backend/ueba_service.py (push after security_alerts insert in _persist_alert)
    - backend/remediation_audit_service.py (push after remediation_audit insert in write_audit)

key-decisions:
  - "Reused a module-level WebhookService() singleton instead of instantiating per-call, for consistency with notification_manager's existing pattern (functionally equivalent to the plan's literal suggestion, cheaper)."
  - "siem_engine.py awaits push_ocsf_event(...) directly (no outer create_task) since push_ocsf_event's own body never blocks — it only builds the payload and schedules trigger_webhook via create_task internally. ueba_service.py and remediation_audit_service.py additionally wrap the call in asyncio.create_task(...) (belt-and-suspenders). Both are fire-and-forget with respect to the actual webhook HTTP call; the inconsistency is cosmetic, not a defect."

patterns-established:
  - "OCSF outbound push: import push_ocsf_event locally inside the function that needs it (matches existing deferred-import convention for cross-module calls in this backend), call/schedule it immediately after the write it reports on, wrapped in its own try/except."

requirements-completed: [COMM-01]

coverage:
  - id: D1
    description: "push_ocsf_event builds an OCSF Detection Finding (class_uid=2004, category_uid=2, type_uid=200401) and dispatches it fire-and-forget via the existing SSRF-safe, HMAC-signed webhook_service.trigger_webhook — never awaited inline."
    requirement: "COMM-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_soc_integration.py#test_soc_integration_basic_structure"
        status: pass
    human_judgment: false
  - id: D2
    description: "Correlation (siem_engine), anomaly (ueba_service), and remediation (remediation_audit_service) each call push_ocsf_event at their respective insert points."
    requirement: "COMM-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_soc_integration.py#test_siem_engine_trigger_alert_calls_push_ocsf"
        status: pass
      - kind: other
        ref: "backend/tests/test_soc_integration.py#test_multiple_call_sites_exist (static source check, all 3 call sites)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A push/delivery failure at any of the three call sites does not propagate into or break the emitting pipeline (correlation/anomaly/remediation insert still completes)."
    requirement: "COMM-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_soc_integration.py#test_delivery_failure_is_non_fatal_for_ueba_and_remediation"
        status: pass
    human_judgment: false

duration: "~21:05-23:34 IST 2026-08-03, across executor run + a separate post-merge fix pass (see Deviations)"
completed: 2026-08-03
status: complete
---

# Phase 55 Plan 04: SOC Integration Summary

**Outbound OCSF (class_uid=2004) push from correlation/anomaly/remediation pipelines to subscribed SIEM webhooks, fire-and-forget, via the existing SSRF-safe HMAC-signed webhook_service — reusing `notification_manager`'s dispatch pattern and `ocsf_endpoints.py`'s payload shape.**

## Performance

- **Tasks:** 2 (both complete)
- **Files created:** 2 (`soc_integration_service.py`, `tests/test_soc_integration.py`)
- **Files modified:** 4 (`ocsf_endpoints.py`, `siem_engine.py`, `ueba_service.py`, `remediation_audit_service.py`)

## Accomplishments
- `soc_integration_service.push_ocsf_event(event_type, source_doc)` builds an OCSF Detection Finding payload (class_uid=2004, category_uid=2, type_uid=200401), reusing `_to_epoch`/`severity_map` from `ocsf_endpoints.py`, and dispatches it fire-and-forget via a module-level `WebhookService()` singleton's `trigger_webhook()` — unchanged SSRF blocklist and HMAC signing.
- Wired all three D-03 pipeline points: `siem_engine._trigger_alert` (`threat.correlation`), `ueba_service._persist_alert` (`ueba.anomaly`), `remediation_audit_service.write_audit` (`remediation.event`, covering every remediation stage transition through this single funnel).
- Added `tests/test_soc_integration.py` covering OCSF payload shape, all three call sites firing, and delivery-failure non-fatality.

## Task Commits

1. **Task 1: soc_integration_service + first end-to-end OCSF push (correlation case)** — `7e41f73` (feat), `b58c68b` (test), `cb21f96` (feat: wire SIEM engine)
2. **Task 2: wire remaining two push points + delivery-failure-non-fatal proof** — `a9bfe77` (feat: UEBA), `0dd7198` (feat: remediation audit), `e112301` (test)

**Plan metadata:** `6050076`, `2fcbaee` (docs: summary — superseded by this revision)

**Post-merge fix (this revision):** `b9077b1` (fix: import identity + module-scope bug), `89de3f9` (test: missing delivery-failure test) — see Deviations.

## Files Created/Modified
- `backend/soc_integration_service.py` - OCSF builder + fire-and-forget dispatch wrapper (48 lines)
- `backend/ocsf_endpoints.py` - `severity_map` hoisted to module level (was function-local, not importable)
- `backend/siem_engine.py` - push after `security_cases` insert in `_trigger_alert`
- `backend/ueba_service.py` - push after `security_alerts` insert in `_persist_alert`
- `backend/remediation_audit_service.py` - push after `remediation_audit` insert in `write_audit`
- `backend/tests/test_soc_integration.py` - OCSF shape, all 3 call sites, delivery-failure-non-fatal

## Decisions Made
- Module-level `WebhookService()` singleton instead of per-call instantiation (matches `notification_manager`'s existing pattern; cheaper, same behavior).
- `siem_engine.py`'s call site awaits `push_ocsf_event(...)` directly rather than wrapping it in an additional `asyncio.create_task(...)` like the other two sites — harmless inconsistency, not a defect (see `key-decisions` in frontmatter).

## Deviations from Plan

### Auto-fixed Issues

**1. [Post-merge test gate] Broken imports prevented the module from loading under its actual runtime call convention**
- **Found during:** Post-merge test gate, this session — `pytest tests/test_soc_integration.py` was green at merge time only because the test file's own broken imports (see #2) meant the real `push_ocsf_event`/`SiemEngine` were never actually exercised end-to-end the way production does.
- **Issue:** `soc_integration_service.py` used package-relative imports (`from .ocsf_endpoints import ...`, `from .webhook_service import ...`). All three production call sites import it as `from soc_integration_service import push_ocsf_event` (bare name, no package) — a relative import raises `ImportError: attempted relative import with no known parent package` under that convention. Separately, `severity_map` was a function-local variable inside `ocsf_endpoints.ocsf_findings()`, not a module-level name, so `from ocsf_endpoints import severity_map` would also fail.
- **Fix:** Changed both imports in `soc_integration_service.py` to bare (`from ocsf_endpoints import ...`, `from webhook_service import ...`), matching the convention already used by every other sibling module in `backend/`. Hoisted `severity_map` to module level in `ocsf_endpoints.py` (used unchanged by the existing `/findings` endpoint, now also importable).
- **Files modified:** `backend/soc_integration_service.py`, `backend/ocsf_endpoints.py`
- **Verification:** `python -c "import app"` succeeds; all three production call sites' deferred `from soc_integration_service import push_ocsf_event` now resolve.
- **Committed in:** `b9077b1`

**2. [Post-merge test gate] Test patched the wrong module identity (dual-import trap)**
- **Found during:** Post-merge test gate, this session.
- **Issue:** `test_soc_integration_basic_structure` imported `push_ocsf_event` via `from backend.soc_integration_service import push_ocsf_event` (package-qualified) but patched `soc_integration_service._webhook_service` (bare name). Python's import system treats `backend.soc_integration_service` and `soc_integration_service` as two distinct module objects (both importable given this project's sys.path setup), each with its own `_webhook_service` singleton. The patch silently missed its target; the real `WebhookService.trigger_webhook` ran and hit the test environment's disconnected DB, and the test failed on `assert_awaited_once()` never having been awaited.
- **Fix:** Patch target corrected to `backend.soc_integration_service._webhook_service`, matching the import actually under test.
- **Files modified:** `backend/tests/test_soc_integration.py`
- **Verification:** `pytest tests/test_soc_integration.py -v` — was 2/3 passing, now 3/3 (then 4/4 after #3).
- **Committed in:** `b9077b1`

**3. [Plan acceptance gap] Task 2's delivery-failure-non-fatal test was never actually written**
- **Found during:** Reviewing the committed test file against Plan 55-04's Task 2 acceptance criteria while investigating #2.
- **Issue:** Task 2 explicitly required "a test patches trigger_webhook (or httpx post) to raise and asserts `_persist_alert` and `write_audit` both still complete their insert without propagating the exception." The committed suite only had `test_multiple_call_sites_exist`, a static `inspect.getsource()` string check for `'push_ocsf_event'` — it proves the call sites exist textually, not that failures are actually non-fatal at runtime.
- **Fix:** Added `test_delivery_failure_is_non_fatal_for_ueba_and_remediation`, patching `soc_integration_service.push_ocsf_event` to raise and asserting both `_persist_alert` and `write_audit` still complete their own DB insert.
- **Files modified:** `backend/tests/test_soc_integration.py`
- **Verification:** New test passes; full file now 4/4.
- **Committed in:** `89de3f9`

---

**Total deviations:** 3 auto-fixed (2 blocking import/patch bugs, 1 missing acceptance-criteria test).
**Impact on plan:** All three were necessary for the plan's own stated must-haves to actually hold (the module didn't import under its real call convention; the one existing OCSF-shape test wasn't actually testing the code path it claimed to; the non-fatal-delivery guarantee had no runtime proof). No scope creep — no file outside this plan's `files_modified` list was touched, and `backend/virustotal_client.py`'s unrelated pre-existing `BaseCapability` import bug (encountered only as background noise in `import app` output, tracked in `deferred-items.md` since 55-01) was left alone.

## Issues Encountered
The wave-3 worktree merge (`e0874d0`) landed with the two bugs above already present; `python -m pytest tests/test_soc_integration.py` reported green at merge time despite this, because the broken patch target (#2) meant the failing assertion path was never reached — the test exercised the real `WebhookService` hitting a disconnected DB inside an unawaited background task, whose exception was swallowed by asyncio (`Task exception was never retrieved`) rather than failing the test. Caught by re-running the suite in this session rather than trusting the prior green result at face value.

## User Setup Required
None - no external service configuration required. Operators subscribe to the new `threat.correlation` / `ueba.anomaly` / `remediation.event` webhook event types via the existing `POST /api/webhooks` `events[]` array; no new endpoint or env var.

## Next Phase Readiness
- COMM-01 closes the outbound loop for phase 55: correlation (55-01), anomaly detection (55-02), and containment (55-03) events are now all externally visible to a subscribed SOC/SIEM.
- `.planning/REQUIREMENTS.md` does not currently track `COMM-01` (same pre-existing v4.0 requirements-set drift documented in `deferred-items.md` item 3 for `AUT-03`) — `requirements.mark-complete COMM-01` is expected to return `not_found`; traceability for this plan lives in this SUMMARY's frontmatter (`requirements-completed: [COMM-01]`) and `coverage` block instead.
- This is Phase 55's final plan (Wave 3, last remaining). No further plans in this phase.

---
*Phase: 55-advanced-threat-detection*
*Completed: 2026-08-03*
