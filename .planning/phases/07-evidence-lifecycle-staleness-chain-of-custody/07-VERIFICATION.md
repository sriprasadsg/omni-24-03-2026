---
phase: 07-evidence-lifecycle-staleness-chain-of-custody
verified: 2026-06-21T20:38:12Z
status: passed
score: 14/14
behavior_unverified: 0
overrides_applied: 0
re_verification: null
---

# Phase 07: Evidence Lifecycle (Staleness + Chain-of-Custody) Verification Report

**Phase Goal:** Automated evidence older than the tenant-configured threshold is flagged stale; every evidence create/update/delete is appended to an immutable chain-of-custody log visible in the control detail view.

**Verified:** 2026-06-21T20:38:12Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

All truths derived from ROADMAP.md requirements (STALE-01, STALE-02, COC-01, COC-02) and the three PLAN frontmatter `must_haves.truths` blocks.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `compute_stale` on automated evidence older than threshold returns `stale=True` with correct `stale_days` | VERIFIED | `evidence_staleness.py` lines 18-24: computes `age_days = (now - dt).days`; returns `{"stale": age_days >= threshold_days, "stale_days": age_days}`. Test `test_staleness_computation` passes. |
| 2 | `compute_stale` on manual evidence never returns `stale=True` (caller contract) | VERIFIED | Caller in `get_control_evidence` gates on `is_auto` flag (line 445-455); manual docs always get `stale=False, stale_days=0`. Test `test_staleness_manual_excluded` passes. |
| 3 | `get_staleness_threshold` returns per-tenant value, falls back to global, then defaults to 7 | VERIFIED | `evidence_staleness.py` lines 45-57: queries `system_settings` with tenant-first/global-fallback pattern; returns `7` when no doc. Tests `test_staleness_threshold_default` and `test_get_staleness_threshold_default` pass. |
| 4 | `_append_coc_entry` inserts one immutable record into `evidence_audit_log` and never raises | VERIFIED | `evidence_coc.py` lines 33-45: single `insert_one` with all 7 required fields; `except Exception as e: logging.error(...)` — never re-raises. Tests `test_coc_create_entry` and `test_coc_never_raises` pass. |
| 5 | `evidence_audit_log` has indexes on `(evidenceId, tenantId)` and `(tenantId, timestamp)` | VERIFIED | `database.py` lines 267-268: two `create_index` calls with exact required compound keys. No TTL index present. |
| 6 | `GET /api/settings/evidence-staleness` returns `{thresholdDays: 7}` for a new tenant | VERIFIED | `compliance_evidence_lifecycle_endpoints.py` line 41-56: endpoint calls `get_staleness_threshold(db, tenant_id)` — default 7 when no settings doc. Test `test_get_staleness_threshold_default` passes (200, `thresholdDays: 7`). |
| 7 | `PATCH /api/settings/evidence-staleness` with `thresholdDays: 14` persists and is returned; admin-only | VERIFIED | Lines 63-98: `_require_admin` called before upsert; upsert writes to `system_settings`; returns `{"thresholdDays": 14}`. Tests `test_patch_staleness_threshold` and `test_patch_staleness_requires_admin` both pass. |
| 8 | `PATCH /api/settings/evidence-staleness` with `thresholdDays: 0` or `400` returns 422 | VERIFIED | `StalenessThresholdUpdate(BaseModel)` at line 33-34: `thresholdDays: int = Field(ge=1, le=365)` — Pydantic auto-422 on out-of-range. Test `test_staleness_threshold_validation` passes. |
| 9 | `GET /api/compliance/controls/{control_id}/audit-log` returns CoC entries tenant-scoped | VERIFIED | `compliance_evidence_lifecycle_endpoints.py` lines 139-197: aggregates evidence IDs from both `control_evidence` and `asset_compliance`; applies `query["tenantId"] = tenant_id` for non-super users; 403 without tenant. Tests `test_get_coc_log` and `test_coc_tenant_isolation` pass. |
| 10 | Uploading evidence appends a CoC entry with `action_type=create`; deleting appends `action_type=delete` | VERIFIED | `compliance_evidence_endpoints.py` lines 115-123 (upload asset evidence), 296-304 (delete asset evidence), 388-396 (upload control evidence), 483-487 (delete control evidence): 4 distinct `await _append_coc_entry(...)` calls each after the successful DB write `await`. Grep confirms 4 non-import call sites. |
| 11 | GET control evidence injects `stale/stale_days` on automated records; manual records always `stale=False` | VERIFIED | `compliance_evidence_endpoints.py` lines 443-455: `threshold = await get_staleness_threshold(db, tenant_id)` fetched once; `is_auto` gate; `compute_stale` applied to automated docs; manual docs get `stale=False, stale_days=0`. |
| 12 | Automated evidence row with `stale=true` shows amber "Stale" badge and days-old parenthetical | VERIFIED | `AssetComplianceList.tsx` lines 133, 146, 156-159: stale parenthetical in evidence name; `bg-amber-100 text-amber-700` badge with `AlertCircleIcon` shown only when `isAutomated && ev.stale`. Manual evidence has no badge path. |
| 13 | Settings page has an Evidence tab where admin can set staleness threshold (1-365) and save | VERIFIED | `SettingsDashboard.tsx` line 65: `'evidence'` in `SettingsView` type union; line 288-290: Evidence tab button with `ClockIcon`; lines 354-356: `{activeView === 'evidence' && <EvidenceSettings />}` render guard. `EvidenceSettings.tsx`: number input with `min={1} max={365}`, onChange clamp, "Save Threshold" button, `saveStalenessThreshold` call, `showToast` feedback. |
| 14 | Control detail view shows a collapsible Chain-of-Custody panel only to users with `view:audit_log` permission | VERIFIED | `FrameworkDetail.tsx` line 409: `const canViewCoC = hasPermission('view:audit_log')`; line 821: `{canViewCoC && <ChainOfCustodyPanel controlId={control.id} />}`. `ChainOfCustodyPanel.tsx` lazily fetches on first expand via `fetchControlAuditLog`; displays actor + action label + UTC timestamp per entry. |

**Score:** 14/14 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/evidence_staleness.py` | `compute_stale` + `get_staleness_threshold` | VERIFIED | 57 lines, both functions implemented with real logic, proper fallback chain |
| `backend/evidence_coc.py` | `_append_coc_entry` immutable insert helper | VERIFIED | 45 lines, fire-and-forget, raw Motor access, all 7 fields |
| `backend/database.py` | `evidence_audit_log` indexes | VERIFIED | 2 compound indexes, no TTL |
| `backend/tests/test_evidence_lifecycle.py` | Staleness + CoC tests | VERIFIED | 14 tests, all pass under `backend/venv/bin/python3 -m pytest` |
| `backend/compliance_evidence_lifecycle_endpoints.py` | 4 endpoints (GET/PATCH staleness, 2 audit-log GETs) | VERIFIED | 197 lines, all 4 endpoints present with correct auth |
| `backend/router_registry.py` | Lifecycle router registered + in `_REQUIRED_ROUTERS` | VERIFIED | Line 21: in frozenset; line 130: `_load(...)` call |
| `backend/compliance_evidence_endpoints.py` | 4 CoC call sites + staleness injection in `get_control_evidence` | VERIFIED | 495 lines (under 500); 4 non-import `await _append_coc_entry(...)` at lines 115, 296, 388, 483; staleness injection at lines 443-455 |
| `services/apiService.ts` | 4 new API functions | VERIFIED | `fetchStalenessThreshold`, `saveStalenessThreshold`, `fetchEvidenceAuditLog`, `fetchControlAuditLog` at lines 4323-4360 |
| `components/EvidenceSettings.tsx` | Staleness threshold settings UI | VERIFIED | 70 lines, controlled input, validation, toast, save call |
| `components/ChainOfCustodyPanel.tsx` | Collapsible CoC panel with lazy fetch | VERIFIED | 143 lines, lazy-fetch sentinel, expand/collapse, per-entry rendering |
| `components/AssetComplianceList.tsx` | Amber stale badge | VERIFIED | `bg-amber-100 text-amber-700`, conditional on `isAutomated && ev.stale` |
| `components/SettingsDashboard.tsx` | Evidence tab wiring | VERIFIED | Import + type union + nav button + render guard |
| `components/FrameworkDetail.tsx` | `ChainOfCustodyPanel` behind `view:audit_log` | VERIFIED | Import at line 5, `canViewCoC` at line 409, mount at line 821 |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `evidence_staleness.py` | `system_settings` collection | `get_staleness_threshold` queries `system_settings` for `type=evidence_staleness` | WIRED | Lines 47-56: tenant-first then global fallback queries |
| `evidence_coc.py` | `evidence_audit_log` collection | `insert_one` on raw Motor `db._db` | WIRED | Line 35-43: `raw.evidence_audit_log.insert_one(...)` |
| `compliance_evidence_lifecycle_endpoints.py` | `router_registry.py` | `_load(app, 'compliance_evidence_lifecycle_endpoints', 'router')` | WIRED | registry.py line 130 + line 21 in `_REQUIRED_ROUTERS` |
| `compliance_evidence_endpoints.py` | `evidence_coc.py` | `await _append_coc_entry(...)` after each successful mutation | WIRED | 4 call sites: lines 115, 296, 388, 483; all placed after the DB write `await` |
| `compliance_evidence_endpoints.py` `get_control_evidence` | `evidence_staleness.py` | `get_staleness_threshold` + `compute_stale` | WIRED | Lines 443, 447: both functions imported and called |
| `EvidenceSettings.tsx` | `services/apiService.ts` | `fetchStalenessThreshold` on mount + `saveStalenessThreshold` on save | WIRED | `EvidenceSettings.tsx` lines 10, 19 |
| `ChainOfCustodyPanel.tsx` | `services/apiService.ts` | `fetchControlAuditLog` on first expand | WIRED | `ChainOfCustodyPanel.tsx` line 42 |
| `FrameworkDetail.tsx` | `ChainOfCustodyPanel.tsx` | Mounted when `hasPermission('view:audit_log')` | WIRED | Lines 409, 821 |
| `AssetComplianceList.tsx` | Backend `stale` field | Renders `ev.stale === true` | WIRED | Line 156: `{isAutomated && ev.stale && ...}` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `ChainOfCustodyPanel.tsx` | `entries` | `fetchControlAuditLog(controlId)` → `GET /api/compliance/controls/{id}/audit-log` → `evidence_audit_log` collection query | Yes — real MongoDB query on `evidence_audit_log` | FLOWING |
| `EvidenceSettings.tsx` | `threshold` | `fetchStalenessThreshold()` → `GET /api/settings/evidence-staleness` → `get_staleness_threshold(db, tenant_id)` → `system_settings` query | Yes — real MongoDB query with fallback default | FLOWING |
| `AssetComplianceList.tsx` | `ev.stale` / `ev.stale_days` | Backend `get_control_evidence` → `compute_stale(uploadedAt, threshold)` injected per automated record | Yes — computed from real record timestamps and real threshold | FLOWING |

---

### Behavioral Spot-Checks

All 14 tests enumerated and run via `backend/venv/bin/python3 -m pytest tests/test_evidence_lifecycle.py -x -q`:

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 14 evidence lifecycle tests (staleness + CoC helpers + endpoint integration) | `backend/venv/bin/python3 -m pytest tests/test_evidence_lifecycle.py -x -q` | 14 passed, 1 warning in 1.11s | PASS |
| All 9 commits from SUMMARYs exist | `git log --oneline \| grep {hashes}` | All 9 commit hashes confirmed: `6de432d`, `0bd73c9`, `7a3e139`, `a4cc7bf`, `39a4aee`, `1857500`, `11e7cbe`, `54a24db`, `694eafd` | PASS |

---

### Probe Execution

No probe scripts declared in plans or discovered at `scripts/*/tests/probe-*.sh`.

---

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|---------------|-------------|--------|---------|
| STALE-01 | 07-01, 07-02, 07-03 | `compute_stale` helper + staleness injection in `get_control_evidence` + stale badge in UI | SATISFIED | `evidence_staleness.py`, `compliance_evidence_endpoints.py` lines 443-455, `AssetComplianceList.tsx` lines 156-159 |
| STALE-02 | 07-02, 07-03 | GET/PATCH `/api/settings/evidence-staleness` with `Field(ge=1, le=365)` admin gate; `EvidenceSettings` component + Evidence tab | SATISFIED | `compliance_evidence_lifecycle_endpoints.py` lines 41-98, `EvidenceSettings.tsx`, `SettingsDashboard.tsx` lines 65/288-290/354-356 |
| COC-01 | 07-01, 07-02 | `_append_coc_entry` helper; 4 call sites in `compliance_evidence_endpoints.py` after successful mutations | SATISFIED | `evidence_coc.py`, 4 `await _append_coc_entry(...)` calls at lines 115, 296, 388, 483 |
| COC-02 | 07-02, 07-03 | GET audit-log endpoints (evidence + control level); tenant-scoped; `ChainOfCustodyPanel` gated on `view:audit_log` | SATISFIED | `compliance_evidence_lifecycle_endpoints.py` lines 105-197, `FrameworkDetail.tsx` lines 409, 821 |

---

### Anti-Patterns Found

No TBD, FIXME, or XXX markers found in any phase-modified file. No stub implementations detected.

Two `return []` patterns in `compliance_evidence_endpoints.py` lines 146, 149 are early-exit guards for empty tenant/asset queries — they are not stubs (they guard the query, not replace it).

`return null` in `SettingsDashboard.tsx` line 150 is a conditional render guard (`if (!currentUser) return null`) — pre-existing, not introduced by this phase.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | No blockers found |

---

### Human Verification Required

No items require human verification. All truths are fully verifiable through code inspection and automated tests.

---

### Gaps Summary

No gaps. All 14 must-have truths are verified by real code and passing tests. All 9 claimed commits exist in git history. The phase goal — automated evidence flagged stale at read-time and an immutable CoC log visible in the control view — is fully achieved in the codebase.

---

_Verified: 2026-06-21T20:38:12Z_
_Verifier: Claude (gsd-verifier)_
