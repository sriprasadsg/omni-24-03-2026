---
phase: 58
slug: asset-tags-offline-labels
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-05
---

# Phase 58 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`@pytest.mark.asyncio`), matching `test_itam_foundation.py`/`test_itam_lifecycle.py` |
| **Config file** | none — no `pytest.ini`/`pyproject.toml [tool.pytest]` section in this repo |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/test_itam_labels.py -q` |
| **Full suite command** | `backend/venv/bin/python -m pytest backend/tests -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `backend/venv/bin/python -m pytest backend/tests/test_itam_labels.py -q`
- **After every plan wave:** Run `backend/venv/bin/python -m pytest backend/tests -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 58-01-01 | 01 | 0 | ITAM-CAT-05 | — | `generate_qr_png(assetTag)` returns valid, decodable PNG bytes | unit | `pytest backend/tests/test_itam_labels.py -k qr_generation -x` | ❌ W0 | ⬜ pending |
| 58-01-02 | 01 | 0 | ITAM-CAT-05 | — | `generate_barcode_png(assetTag)` returns valid Code128 PNG bytes | unit | `pytest backend/tests/test_itam_labels.py -k barcode_generation -x` | ❌ W0 | ⬜ pending |
| 58-01-03 | 01 | 0 | ITAM-CAT-05 | T-58-01 | Invalid/empty tag on barcode generation returns 400, not 500 | unit | `pytest backend/tests/test_itam_labels.py -k barcode_invalid_tag -x` | ❌ W0 | ⬜ pending |
| 58-02-01 | 02 | 1 | ITAM-CAT-05 | — | `POST /api/assets/labels/sheet` with 1/29/30/31/60 ids produces correct page count, no drop/overlap | unit | `pytest backend/tests/test_itam_labels.py -k sheet_pagination -x` | ❌ W0 | ⬜ pending |
| 58-02-02 | 02 | 1 | ITAM-CAT-05 (SC-3) | — | QR/barcode/sheet generation succeeds with `socket.socket` patched to raise — proves zero network calls | unit | `pytest backend/tests/test_itam_labels.py -k offline_network_blocked -x` | ❌ W0 | ⬜ pending |
| 58-02-03 | 02 | 1 | ITAM-CAT-05 | T-58-04 | Label endpoints reject callers without `manage:assets` (403) | unit | `pytest backend/tests/test_itam_labels.py -k rbac -x` | ❌ W0 | ⬜ pending |
| 58-02-04 | 02 | 1 | ITAM-CAT-05 | T-58-01 | Cross-tenant asset id on label/sheet request returns 404, never another tenant's data | unit | `pytest backend/tests/test_itam_labels.py -k tenant_isolation -x` | ❌ W0 | ⬜ pending |
| 58-02-05 | 02 | 1 | ITAM-CAT-05 (D-01) | — | Generated PDF's extracted text stream contains tag, name, and model | unit | `pytest backend/tests/test_itam_labels.py -k label_content -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_itam_labels.py` — new file, covers all rows above; reuse `MockTenantIsolatedDatabase`/`MockTenantIsolatedCollection` fixtures from `backend/tests/test_itam_foundation.py` (check `conftest.py` for a promoted shared fixture before duplicating)
- [ ] Offline-network-blocked test (`socket.socket` patched to raise) — new pattern, no existing fixture to reuse; write directly in `test_itam_labels.py`
- [ ] `python-barcode==0.16.1` install — gated by `checkpoint:human-verify` (automated legitimacy check flagged SUS; manual PyPI/wheel inspection this session found it clean — MIT license, real GitHub repo, no postinstall scripts) — must resolve before any barcode test can import the module

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Avery 5160 physical print alignment | ITAM-CAT-05 | Outer-margin figure (0.3125") was arithmetically reconciled, not sourced as one stated number — needs a physical label-stock print to confirm no drift | Print the generated PDF onto real Avery 5160 stock (or equivalent) and visually confirm QR/barcode/text land inside each label cell with no overlap |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
