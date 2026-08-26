---
phase: 73
slug: api-integrations
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-18
planned: 2026-08-18
---

# Phase 73 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (backend), existing `backend/tests/` convention |
| **Config file** | none dedicated — project-wide pytest config already in place |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/test_itam_api_integrations.py -q` |
| **Full suite command** | `backend/venv/bin/python -m pytest backend/ -q` |
| **Estimated runtime** | ~30s (quick), full suite per project baseline |

---

## Sampling Rate

- **After every task commit:** Run the targeted `-k` filter for the file(s) touched
- **After every plan wave:** Run `pytest backend/tests/test_itam_api_integrations.py backend/tests/test_itam_webhook_events.py backend/tests/test_itam_ticketing_bridge.py -q`
- **Before `/gsd-verify-work`:** Full `backend/` suite must be green
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| Task 3 | 73-01 | 1 | ITAM-API-01 | Pitfall 1 | Session auth still works on `_require_itam_admin`-gated routes (regression) | unit | `pytest backend/tests/test_itam_api_integrations.py -k session_auth -x` | ❌ W0 | ⬜ pending |
| Task 3 | 73-01 | 1 | ITAM-API-01 | Pitfall 1 | A `manage:assets`-scoped API key can perform a gated operation | unit | `pytest backend/tests/test_itam_api_integrations.py -k scoped_key_allowed -x` | ❌ W0 | ⬜ pending |
| Task 3 | 73-01 | 1 | ITAM-API-01 | Pitfall 1 (critical) | A `read:assets`-only (narrow-scope) API key is REJECTED on a `manage:assets` operation | unit | `pytest backend/tests/test_itam_api_integrations.py -k scope_narrowing_enforced -x` | ❌ W0 | ⬜ pending |
| Task 3 | 73-01 | 1 | ITAM-API-01 | — | Rate limiter still triggers 429 on a key over its per-minute cap when hit via an ITAM route | unit | `pytest backend/tests/test_itam_api_integrations.py -k rate_limit -x` | ❌ W0 | ⬜ pending |
| Task 1 | 73-02 | 2 | ITAM-API-02 | Pitfall 4 | `checkout_asset`/`checkin_asset` fire `asset.checked_out`/`asset.checked_in` with correct before/after payload | unit | `pytest backend/tests/test_itam_webhook_events.py -k lifecycle -x` | ❌ W0 | ⬜ pending |
| Task 2 | 73-02 | 2 | ITAM-API-02 | — | `checkout_consumable` fires `consumable.low_stock` only when the post-decrement quantity crosses threshold | unit | `pytest backend/tests/test_itam_webhook_events.py -k low_stock -x` | ❌ W0 | ⬜ pending |
| Task 3 | 73-02 | 2 | ITAM-API-02 | — | `approve_asset_request`/`reject_asset_request` fire the matching request event | unit | `pytest backend/tests/test_itam_webhook_events.py -k asset_request -x` | ❌ W0 | ⬜ pending |
| Task 3 | 73-03 | 3 | ITAM-API-02 | Pitfall 3 (critical) | Warranty/licence background sweeps set tenant context correctly before dispatching (assert `trigger_webhook` called with ambient context matching the asset's actual tenantId, 2+ tenants) | unit | `pytest backend/tests/test_itam_webhook_events.py -k tenant_context_background -x` | ❌ W0 | ⬜ pending |
| Task 1 | 73-04 | 2 | ITAM-API-03 | — | New ITAM alert-shape adapter produces the exact shape `create_jira_ticket`/`create_servicenow_incident` expect | unit | `pytest backend/tests/test_itam_ticketing_bridge.py -k alert_shape -x` | ❌ W0 | ⬜ pending |
| Task 2 | 73-05 | 4 | ITAM-API-03 | Pitfall 6 | Audit-overdue and stuck-approval automatic triggers create exactly one ticket per condition (dedup guard works) | unit | `pytest backend/tests/test_itam_ticketing_bridge.py -k automatic_trigger -x` | ❌ W0 | ⬜ pending |
| Task 3 | 73-04 | 2 | ITAM-API-03 | — | Manual "Create Ticket" button's endpoint works ad-hoc regardless of automatic-trigger state | unit | `pytest backend/tests/test_itam_ticketing_bridge.py -k manual_create -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky. Task/Plan/Wave IDs filled in now that all 6 PLAN.md files exist (plan-checker VERIFICATION PASSED 2026-08-18); execution ("File Exists"/Status columns) has not started.*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_itam_api_integrations.py` — covers ITAM-API-01 (auth swap + scope-narrowing fix + rate limit)
- [ ] `backend/tests/test_itam_webhook_events.py` — covers ITAM-API-02 (all 8 event triggers + tenant-context regression for the 2 background-sweep events)
- [ ] `backend/tests/test_itam_ticketing_bridge.py` — covers ITAM-API-03 (adapter shape + 2 automatic triggers + manual button)
- Framework install: none — pytest already installed and used project-wide.

---

## Manual-Only Verifications

*None — all phase behaviors have automated verification per the Phase Requirements → Test Map above.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-08-18 (gsd-plan-checker Dimension 8 — Nyquist/Validation Architecture: PASS)
