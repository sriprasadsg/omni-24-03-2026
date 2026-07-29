---
phase: 47
slug: agent-scoped-geo-security-detectors
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-29
---

# Phase 47 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (backend), tsc/npm build (frontend) |
| **Config file** | `backend/pytest.ini` |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/test_geo_security_detectors.py -q` |
| **Full suite command** | `backend/venv/bin/python -m pytest backend/ -q --continue-on-collection-errors` |
| **Estimated runtime** | ~40 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run the quick command for the touched detector/endpoint test file
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green (modulo documented pre-existing failures)
- **Max feedback latency:** 40 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 47-00-01 | 00 | 0 | (prereq) | — | `persist_security_alert` importable + actually fans out (fixes 5 dormant no-op call sites) | unit | `pytest backend/tests/test_persist_security_alert.py -q` | ❌ W0 | ⬜ pending |
| 47-0x-xx | — | 1 | GSEC-02 | — | Impossible-travel raises exactly one alert on genuine jump; suppressed when either endpoint vpn_heuristic is True | unit | `pytest backend/tests/test_impossible_travel.py -q` | ❌ W0 | ⬜ pending |
| 47-0x-xx | — | 1 | GSEC-03 | — | Check-in country outside tenant allowlist raises alert; alert-only (no block) | unit | `pytest backend/tests/test_geo_fence.py -q` | ❌ W0 | ⬜ pending |
| 47-0x-xx | — | 1 | GSEC-02/03 | — | Dedup: per-(agent,type) transition + 6h cooldown suppresses repeats | unit | `pytest backend/tests/test_detector_dedup.py -q` | ❌ W0 | ⬜ pending |
| 47-0x-xx | — | 2 | GSEC-03 | — | Admin-gated GET/PATCH allowed-regions config; tenant-isolated; non-admin 403 | unit | `pytest backend/tests/test_geo_security_endpoints.py -q` | ❌ W0 | ⬜ pending |
| 47-0x-xx | — | 3 | GSEC-01 | — | `vpn_heuristic` surfaced on agent card, labeled "likely VPN/hosting" (heuristic, never "detected") | manual+build | `npx tsc --noEmit && npm run build` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky. Task IDs finalized by the planner.*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_persist_security_alert.py` — prove the fan-out alias exists and fires (regression for the 5 dormant call sites)
- [ ] `backend/tests/test_geo_security_detectors.py` (or per-detector split) — stubs for GSEC-02/03
- [ ] Shared fixtures: fake agent doc with prior geo + `lastSeen`, mocked `geoip_service`/`agent_asn_service` (GeoLite2-City.mmdb NOT bundled — all geo must be mocked)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Agent-card VPN/hosting badge renders + labeled heuristic | GSEC-01 | Live pixel render not machine-observable | Load an agent card for a VPN-flagged IP; confirm amber "likely VPN/hosting" label, never "detected" |
| Security settings panel: admin edits allowed regions | GSEC-03 | Live admin UI flow | Open Security settings, add/remove a country, confirm persistence + tenant isolation |

*Real GeoLite2-City.mmdb enrichment remains a deploy-time verification (same class as Phase 46's GeoLite2-ASN gate).*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (esp. the `persist_security_alert` fan-out fix)
- [ ] No watch-mode flags
- [ ] Feedback latency < 40s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
