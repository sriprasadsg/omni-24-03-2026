---
phase: 48
slug: fleet-observability-uptime-rollups
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-29
---

# Phase 48 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (backend), tsc/npm build (frontend) |
| **Config file** | `backend/pytest.ini` |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/ -k fleet_observability -q` |
| **Full suite command** | `backend/venv/bin/python -m pytest backend/ -q --continue-on-collection-errors` |
| **Estimated runtime** | ~40 seconds (full) |

---

## Sampling Rate

- **After every task commit:** quick command for the touched uptime/fleet test file
- **After every plan wave:** full suite command
- **Before `/gsd-verify-work`:** full suite green (modulo documented pre-existing failures)
- **Max feedback latency:** 40 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------------|-----------|-------------------|-------------|--------|
| 48-0x | — | 1 | FOBS-02 | Uptime endpoint: gap-detection over `agent_metrics` (30s cadence), received/expected ratio; tenant-isolated; empty/never-heartbeat agent → 0% not crash | unit | `pytest backend/tests/ -k agent_uptime -q` | ❌ W0 | ⬜ pending |
| 48-0x | — | 1 | FOBS-02 | Daily uptime-rollup sweep writes per-agent daily % to `agent_uptime_rollups`; retention routed through retention_service; no backfill | unit | `pytest backend/tests/ -k uptime_rollup -q` | ❌ W0 | ⬜ pending |
| 48-0x | — | 1 | FOBS-03 | Fleet aggregate endpoint: offline set (status Offline) + version-drift (reported vs _LATEST_AGENT_VERSION); admin-gated; tenant-isolated | unit | `pytest backend/tests/ -k fleet_observability -q` | ❌ W0 | ⬜ pending |
| 48-0x | — | 2 | FOBS-01 | Agent metrics charts render CPU/mem/disk from `/agents/{id}/metrics/history`; ≤48h presets; mounted in agent detail (new file, not bloating AgentDetailModal) | build | `npx tsc --noEmit && npm run build` | ❌ W0 | ⬜ pending |
| 48-0x | — | 2 | FOBS-02 | Uptime timeline UI + selectable ≤48h range in agent detail | build | `npx tsc --noEmit && npm run build` | ❌ W0 | ⬜ pending |
| 48-0x | — | 3 | FOBS-03 | Fleet Observability admin-gated nav page (offline + drift lists), registered App.tsx/Sidebar.tsx | build+manual | `npx tsc --noEmit && npm run build` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red. Task IDs finalized by the planner.*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_agent_uptime.py` — gap-detection + rollup sweep stubs (mock `agent_metrics` timestamps)
- [ ] `backend/tests/test_fleet_observability.py` — aggregate endpoint (offline + drift) stubs
- [ ] Shared fixtures: fake `agent_metrics` rows at 30s cadence with injected gaps; agents with mixed reported versions/status

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Metrics charts + uptime timeline render in agent detail | FOBS-01/02 | Live pixel render | Open an agent detail view; confirm CPU/mem/disk charts + uptime timeline + range selector |
| Fleet Observability page lists offline + drifted agents | FOBS-03 | Live admin UI + real fleet state | As admin, open the Fleet Observability page; confirm offline agents + version-drift list; non-admin gated |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers uptime + fleet-aggregate test stubs
- [ ] No watch-mode flags
- [ ] Feedback latency < 40s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
