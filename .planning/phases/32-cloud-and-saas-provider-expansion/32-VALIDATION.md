---
phase: 32
slug: cloud-and-saas-provider-expansion
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-08
---

# Phase 32 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`pytest.ini` at repo root, `asyncio_mode = auto`) |
| **Config file** | `pytest.ini` |
| **Quick run command** | `cd backend && python -m pytest tests/test_cloud_integrations.py tests/test_cloud_checks_expansion.py tests/test_saas_posture_checks.py tests/test_attack_path.py -x` |
| **Full suite command** | `cd backend && python -m pytest tests/ -q` |

---

## Sampling Rate

- **After every task commit:** `cd backend && python -m pytest tests/test_cloud_integrations.py tests/test_cloud_checks_expansion.py tests/test_saas_posture_checks.py tests/test_attack_path.py -x`
- **After every plan wave:** `cd backend && python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Task IDs are assigned by the planner; requirement-level rows below are the contract the planner must map tasks onto (per `32-RESEARCH.md` § Validation Architecture, updated for the resolved real-findings-ingestion scope).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | PROV-01 | T-32-CRED | `test_integration()`/poll for `oci_cloud_guard`/`alibaba_sas`/`cloudflare_zero_trust` calls a real (mocked-in-test) SDK/HTTP client and ingests findings; every new secret field is in `_SECRET_FIELDS` (Fernet-encrypted) and masked by `_mask_secrets()` | unit | `pytest backend/tests/test_cloud_integrations.py -k "oci or alibaba or cloudflare" -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PROV-01 | — | `cloud_account_endpoints.py` `_VALID_PROVIDERS` lockstep-widened — OCI/Alibaba/Cloudflare no longer 400 on submit (Phase 25 lockstep precedent) | unit | `pytest backend/tests/test_cloud_accounts.py -k provider -x` | ✅ (extend) | ⬜ pending |
| TBD | TBD | TBD | PROV-02 | — | `run_checks()` evaluates M365/MongoDB Atlas checks; all provider gates accept the two new values | unit | `pytest backend/tests/test_cloud_checks_expansion.py -k "microsoft365 or mongodb_atlas" -x` | ✅ (extend) | ⬜ pending |
| TBD | TBD | TBD | PROV-02 | T-32-MALFORMED | M365 (Graph secureScores) and MongoDB Atlas (Admin API, HTTPDigestAuth) ingest paths write real findings to `cloud_findings`; malformed API responses are swallowed (`return 0`), never propagate | unit | `pytest backend/tests/test_cloud_integrations.py -k "m365_ingest or atlas_ingest" -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PROV-02 | — | Checks evaluated against real ingested findings are distinguishable from catalog-only/empty-findings evaluations (Phase 25 `simulated`-flag labeling convention extended); existing catalog-only providers' behavior unchanged (no regression) | unit | `pytest backend/tests/test_cloud_checks_expansion.py -k "findings_provenance or no_regression" -x` | ✅ (extend) | ⬜ pending |
| TBD | TBD | TBD | PROV-03 | T-32-DIVERGE | `run_posture_checks()` for GitHub/Okta/Google Workspace/Slack/Jira reshapes `pull_*_evidence()`'s already-computed status — `evidence.status == "fail"` always yields `check.result == "FAIL"` (pure reshaping, no independent re-derivation); results tenant-scoped in `saas_check_results` | unit | `pytest backend/tests/test_saas_posture_checks.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PROV-03 | — | New posture-check logic lives in a NEW file (`saas_integration_service.py` is at the 500-line CLAUDE.md cap) | grep | `wc -l backend/saas_integration_service.py` (≤500) | ✅ | ⬜ pending |
| TBD | TBD | TBD | PROV-04 | T-32-SPOOF | `GET /api/security/attack-paths` returns real correlated paths when `db.assets`/`db.vulnerabilities` have data; returns `simulated: true` demo paths only when empty, with the flag present on every demo dict | integration | `pytest backend/tests/test_attack_path.py -k prefers_real -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PROV-04 | — | Edge dicts match the (fixed) `AttackPathEdge` frontend contract; final grep confirms `AttackPathDashboard.tsx` is the only consumer | unit + grep | `pytest backend/tests/test_attack_path.py -k edge_field_contract -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_cloud_integrations.py` — new file (also closes a pre-existing coverage gap: `cloud_integrations_endpoints.py` has zero dedicated tests despite encryption/RBAC/11 providers)
- [ ] `backend/tests/test_attack_path.py` — new file (same pre-existing gap for `attack_path_service.py`/`attack_path_endpoints.py`)
- [ ] `backend/tests/test_saas_posture_checks.py` — new file for PROV-03
- [ ] Extend `backend/tests/test_cloud_checks_expansion.py` (exists from Phase 25) with PROV-02 cases
- [ ] Framework install: `pip install oci aliyun-python-sdk-core-v3 cloudflare` + explicit `msal` line in requirements.txt (already resolvable transitively) — SUS-flagged packages cross-checked and approved in research's Package Legitimacy Audit; surface a `checkpoint:human-verify` before install per that audit's disposition

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| Attack-path dashboard visibly labels demo/simulated paths and renders edge labels (broken today due to the field-name mismatch) | PROV-04 | Visual check | Open Attack Path dashboard with empty assets/vulns → confirm demo badge; seed an asset+vuln → confirm a real path renders with edge labels |
| New provider config forms accept OCI/Alibaba/Cloudflare/M365/MongoDB Atlas credentials end-to-end | PROV-01/02 | UI flow check | Add each new provider via the integrations UI, confirm no 400, confirm secrets are masked in the list view |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (3 new test files + 1 extension created before assertions run)
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (planner, 2026-07-08)
