---
phase: 46
slug: public-ip-asn-vpn-enrichment-location-history-audit
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-29
---

# Phase 46 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Scaffold created at plan time; Wave 0 fills the verification map. See 46-RESEARCH.md § "Validation Architecture" for the tested invariants (append-only integrity, one-row-per-change / NAT de-noise, retention decision, timeline visibility).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (backend/venv/bin/python) |
| **Config file** | backend/pytest.ini (or repo default) |
| **Quick run command** | `cd backend && venv/bin/python -m pytest tests/test_agent_location_history.py -q` |
| **Full suite command** | `cd backend && venv/bin/python -m pytest -q` |
| **Estimated runtime** | ~quick <10s / full ~40s |

---

## Sampling Rate

- **After every task commit:** Run the quick command
- **After every plan wave:** Run the full suite
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~10 seconds (quick)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 46-01-01 | 01 | 0 | GAUD-01 | — | append-only: no PATCH/DELETE route for location history | unit | `venv/bin/python -m pytest tests/test_agent_location_history.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky. Wave 0 expands this map from 46-RESEARCH.md's Validation Architecture section.*

---

## Wave 0 Requirements

- [ ] `tests/test_agent_location_history.py` — stubs for GAUD-01 (append-only integrity, one-row-per-change, NAT flip-flop de-noise) and GAUD-02 (timeline read + dwell computed at read time)
- [ ] `tests/conftest.py` — reuse existing shared fixtures (real Mongo)

*Existing pytest infrastructure covers the phase; only new test files are added at Wave 0.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Location-history timeline renders in agent detail view | GAUD-02 | UI render/visual | Open an agent detail view after a public-IP change; confirm the AgentLocationHistory panel shows the chronological rows with flag/city/IP/VPN-badge/timestamp/dwell |
| Heuristic VPN/ASN enrichment against a real GeoLite2-ASN .mmdb | GAUD-01 | Needs a licensed .mmdb supplied out-of-band | With GEOIP_ASN_DB_PATH set, confirm geo.asn/geo.vpn_heuristic populate |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
