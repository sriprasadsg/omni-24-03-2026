---
phase: 41
slug: cspm-provider-expansion-oci-alibaba-cloudflare
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-20
---

# Phase 41 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`backend/venv/bin/python -m pytest`) |
| **Config file** | none found — see Wave 0 |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/test_cloud_checks_expansion.py backend/tests/test_cloud_findings_ingest.py -q` |
| **Full suite command** | `cd backend && venv/bin/python -m pytest -q` |
| **Estimated runtime** | ~30-60s (quick), ~30-60s (full backend suite per Phase 40 baseline) |

---

## Sampling Rate

- **After every task commit:** `backend/venv/bin/python -m pytest backend/tests/test_cloud_checks_expansion.py backend/tests/test_cloud_findings_ingest.py backend/tests/test_cloud_accounts.py -q`
- **After every plan wave:** `cd backend && venv/bin/python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite green; live browser click-through for the SIMULATED badge and credential-form fix (no automated frontend test framework detected for these components)
- **Max feedback latency:** ~60s

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Automated Command | File Exists | Status |
|---------|------|------|-------------|-------------------|-------------|--------|
| TBD (planner) | TBD | TBD | CSPM-01 | `pytest backend/tests/test_cloud_checks_expansion.py -k oci -x` | ❌ Wave 0 (extend existing file) | ⬜ pending |
| TBD (planner) | TBD | TBD | CSPM-01 | `pytest backend/tests/test_cloud_findings_ingest.py -k oci -x` | ❌ Wave 0 (extend existing file) | ⬜ pending |
| TBD (planner) | TBD | TBD | CSPM-02 | `pytest backend/tests/test_cloud_checks_expansion.py -k alibaba -x` | ❌ Wave 0 | ⬜ pending |
| TBD (planner) | TBD | TBD | CSPM-02 | `pytest backend/tests/test_cloud_findings_ingest.py -k alibaba -x` | ❌ Wave 0 | ⬜ pending |
| TBD (planner) | TBD | TBD | CSPM-03 | `pytest backend/tests/test_cloud_checks_expansion.py -k cloudflare -x` | ❌ Wave 0 | ⬜ pending |
| TBD (planner) | TBD | TBD | CSPM-03 | `pytest backend/tests/test_cloud_findings_ingest.py -k cloudflare -x` | ❌ Wave 0 | ⬜ pending |
| TBD (planner) | TBD | TBD | CSPM-01/02/03 | `pytest backend/tests/test_cloud_accounts.py -k scan -x` (extend existing file) | ⚠️ file exists, new cases needed | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky — Task ID/Plan/Wave columns filled once the planner assigns tasks; requirement→command mapping carried verbatim from 41-RESEARCH.md's Validation Architecture section.*

**Not in table (manual/UAT only):** SIMULATED badge rendering on a fresh account with no imported findings — no automated frontend test framework detected for `CloudChecksScanner.tsx`/`CloudAccountsDashboard.tsx`.

---

## Wave 0 Requirements

- [ ] Extend `backend/tests/test_cloud_checks_expansion.py` with `oci`/`alibaba`/`cloudflare` cases (clone the existing `kubernetes`/`digitalocean` test shape)
- [ ] Extend `backend/tests/test_cloud_findings_ingest.py` with `oci`/`alibaba`/`cloudflare` poll-function unit tests (clone the M365/Atlas fixture shape)
- [ ] No frontend test framework detected for `CloudChecksScanner.tsx`/`CloudAccountsDashboard.tsx`/`AddCloudAccountModal.tsx` — SIMULATED badge and credential-field verification rely on the manual/UAT gate only

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SIMULATED badge renders on fresh account with no imported findings | All (D-02) | No automated frontend test framework detected for this component in this repo | Connect a fresh OCI/Alibaba/Cloudflare account with zero imported findings, load the cloud checks dashboard, confirm a SIMULATED badge is visible wherever `result.simulated` is true |
| Credential-form fix actually stores usable credentials | CSPM-01/02/03 (D-04) | Requires a live browser click-through against the account-creation modal, not just code inspection — this codebase's established CHK-03 verification bar | Add a new OCI/Alibaba/Cloudflare account via the UI form, confirm the stored `credentials_ref` round-trips through `scan_account()` and produces a real (non-simulated) poll, not a silently-discarded payload |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
