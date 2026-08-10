---
phase: 63
slug: close-gap-itam-lic-02-03-rbac-itam-cat-05-label-ui
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-11
---

# Phase 63 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (backend, via `backend/venv/bin/python -m pytest`) + vitest (frontend, `src/__tests__`) |
| **Config file** | `backend/pytest.ini` (implicit rootdir per existing test files) / Vite/vitest config (existing) |
| **Quick run command** | `cd backend && venv/bin/python -m pytest tests/test_itam_consumable.py tests/test_itam_component.py -q` |
| **Full suite command** | `cd backend && venv/bin/python -m pytest -q` (backend) + `npm test` / `npm run build` (frontend) |
| **Estimated runtime** | ~40s backend full suite; ~10s frontend build |

---

## Sampling Rate

- **After every task commit:** `pytest backend/tests/test_itam_consumable.py backend/tests/test_itam_component.py -q` (RBAC tasks) / `npx tsc --noEmit` (frontend tasks)
- **After every plan wave:** Full backend suite (`pytest -q`) + `npm run build`
- **Before `/gsd-verify-work`:** Full suite must be green; manual browser check of the 3 download buttons recommended (no automated download-verification precedent exists in this codebase for the sibling `exportReport`/`downloadComplianceReport` functions either)
- **Max feedback latency:** ~40 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 63-01-01 | 01 | 1 | ITAM-LIC-02 | T-63-01 | Non-admin gets 403 on all `itam_consumable_endpoints.py` routes | unit | `pytest backend/tests/test_itam_consumable.py -k Rbac -x` | ❌ W0 | ⬜ pending |
| 63-01-02 | 01 | 1 | ITAM-LIC-03 | T-63-01 | Non-admin gets 403 on all `itam_component_endpoints.py` routes (both `router` + `asset_components_router`) | unit | `pytest backend/tests/test_itam_component.py -k Rbac -x` | ❌ W0 | ⬜ pending |
| 63-01-03 | 01 | 1 | ITAM-LIC-02/03 | T-63-01 | Admin-role requests still succeed post-swap (regression) | unit | `pytest backend/tests/test_itam_consumable.py backend/tests/test_itam_component.py -q` | ✅ (existing tests already pre-patch `verify_permission=True`) | ⬜ pending |
| 63-02-01 | 02 | 2 | ITAM-CAT-05 | — | Clicking "Label" → QR/Barcode/Sheet triggers a real download | manual/UAT | N/A — browser-only behavior (`URL.createObjectURL` + synthetic click) | — no automated coverage precedent | ⬜ pending |
| 63-02-02 | 02 | 2 | ITAM-CAT-05 | — | New `apiService.ts` label functions call the correct URL/method | unit (optional) | `npx tsc --noEmit` + code inspection | ❌ (no apiService test precedent for `exportReport`/`downloadComplianceReport` either) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Task IDs above are provisional — the planner assigns final task IDs; this table is a coverage map, not a lock on exact numbering.*

---

## Wave 0 Requirements

- [ ] `TestConsumableRbac` class in `backend/tests/test_itam_consumable.py` — covers ITAM-LIC-02's 403 behavior, cloning `test_itam_finance.py`'s `TestFinanceRbacAndTenantIsolation` shape (the real working RBAC-test pattern in this codebase)
- [ ] `TestComponentRbac` class in `backend/tests/test_itam_component.py` — covers ITAM-LIC-03's 403 behavior (both `router` and `asset_components_router`)
- [ ] No framework install needed — pytest/vitest already installed and in active use

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Label download buttons produce real files in a real browser | ITAM-CAT-05 | Browser-only behavior (`URL.createObjectURL` + synthetic `<a download>` click) — no download-interception harness exists in this codebase, same gap already present for the sibling `exportReport`/`downloadComplianceReport` functions | Log in as admin, open ITAM Console → Lifecycle tab, click "Label" on an asset row, click each of QR Code / Barcode / Label Sheet, confirm 3 files download with sensible names and open correctly |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
