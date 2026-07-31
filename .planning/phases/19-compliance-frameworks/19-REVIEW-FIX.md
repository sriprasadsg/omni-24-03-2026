---
phase: 19-compliance-frameworks
fixed_at: 2026-07-03T22:37:57Z
review_path: .planning/phases/19-compliance-frameworks/19-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 3
status: partial
---

# Phase 19: Code Review Fix Report

**Fixed at:** 2026-07-03T22:37:57Z
**Source review:** .planning/phases/19-compliance-frameworks/19-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope (per custom scope instructions): CR-01, CR-02, WR-01, WR-02, IN-01
- Fixed: 5 (CR-01, CR-02, WR-01, WR-02, IN-01)
- Explicitly out of scope / skipped-with-reason: 3 (CR-03, WR-03, IN-02) — deliberate scope decision per task instructions, not a failure

Note on scope: this fix pass used a **custom** scope specified by the invoking workflow, not the default `critical_warning` bucket. CR-03 (control-count expansion) was explicitly excluded due to fabrication risk for a compliance-facing product; WR-03 (style reformatting) and IN-02 (single-line-dict formatting) were explicitly excluded as out-of-scope style nits with no functional impact.

## Fixed Issues

### CR-02: All 14 new framework modules were missing `evaluate_controls()` — calling any of them (once wired) would crash

**Files modified:** `backend/frameworks/_common_checks.py` (new), `backend/frameworks/ens.py`, `backend/frameworks/mas_trm.py`, `backend/frameworks/irap.py`, `backend/frameworks/iso_27017.py`, `backend/frameworks/iso_27018.py`, `backend/frameworks/bsi_c5.py`, `backend/frameworks/ffiec.py`, `backend/frameworks/owasp_top10.py`, `backend/frameworks/tisax.py`, `backend/frameworks/aws_well_architected.py`, `backend/frameworks/rbi_csf.py`, `backend/frameworks/tic_3_0.py`, `backend/frameworks/kisa_isms.py`, `backend/frameworks/fedramp_high.py`
**Commit:** `9458f6e`
**Applied fix:** Extracted a shared `_run_check(db, ctrl)`-equivalent dispatcher into a new `backend/frameworks/_common_checks.py` module (`run_check(db, ctrl)` + `now()`), rather than duplicating percentage-threshold logic 14 times. The dispatcher:
- Reuses the exact multi-signal check logic and MongoDB collection names already established in `nist_800_53.py` / `soc2.py` / `pci_dss.py` / `hipaa.py` for every `check_type` that already has precedent elsewhere in the file family (`count_gt_zero`, `policies_present`, `training_present`, `mfa_coverage`/`mfa_configured`, `rbac_configured`/`access_control_system`/`least_privilege`, `audit_log_volume`, `security_events_monitored`/`continuous_monitoring`, `change_monitoring`/`change_control`, `playbooks_present`/`incident_handling`, `vuln_scan_recent`/`vuln_scanner`, `pentest_or_vuln_scan`/`pen_testing`, `backup_recent`/`backup_completed`, `tls_enforced`/`tls_enabled`, and several more), plus a small number of new multi-signal checks for check_types shared across several of the 14 new frameworks but with no prior precedent (`separation_of_duties`, `disk_encrypted`, `fw_blocked`, `ids_ips_enabled`, `malware_protection`, `patch_management`, `supplier_assessment`, `supplier_contracts`, `baseline_config`, `log_retention`, `input_validation`, `integrity_monitoring`, `device_compliance`, `access_keys_rotated`, `iam_no_wildcards`, `backup_dr`, `background_checks`, `risk_assessment_completed`, `incident_reporting`).
- Falls back to a generic "does at least one matching document exist" presence check (`_PRESENCE_CHECKS` table, ~85 entries) for the remaining check_types that are unique to a single framework (mostly FedRAMP High's NIST 800-53 High-baseline-specific controls, e.g. `audit_generation`, `media_labeling`, `session_lock`, `password_policy`) — same shape as the pre-existing `count_gt_zero` check_type, real MongoDB queries, no fabricated pass results.
- Falls through to `"not_applicable"` for anything genuinely unmapped, matching every pre-existing `_run_check`'s final fallback behavior.

Each of the 14 modules now has `from ._common_checks import run_check as _run_check, now as _now` plus its own local `async def evaluate_controls(db)` that iterates `CONTROLS` and calls `_run_check` per control — matching the interface shape of `nist_800_53.py`'s pattern while avoiding 14x duplication of the dispatch logic. Pre-existing framework modules (`nist_800_53.py`, `soc2.py`, etc.) were **not** touched or migrated to the shared helper, to eliminate any risk of regressing working code during this fix pass.

**Verification performed (beyond standard 3-tier):**
- `ast.parse` on all 14 modified module files: pass.
- `from frameworks import ens, mas_trm, irap, iso_27017, iso_27018, bsi_c5, ffiec, owasp_top10, tisax, aws_well_architected, rbi_csf, tic_3_0, kisa_isms, fedramp_high` via `backend/venv/bin/python`: imports cleanly.
- Called `evaluate_controls(db)` against a lightweight mocked db for all 14 modules: returned exactly `len(CONTROLS)` results per module, zero exceptions, zero unmapped (`"Unknown check type"`) results across all 611 total controls in these 14 modules — confirming the crash CR-02 identified (`AttributeError: module 'ens' has no attribute 'evaluate_controls'`) is resolved and that `_run_check`'s dispatch table is exhaustive for every `check_type` actually used by these 14 frameworks.

### WR-02: 4 `check_type` values did not semantically match their control's title/description

**Files modified:** `backend/frameworks/kisa_isms.py`, `backend/frameworks/iso_27018.py`
**Commit:** `9458f6e` (bundled with CR-02 — see note below)
**Applied fix:**
- `kisa_isms.py` `ISMS-2.1` ("CEO commitment"): `check_type` changed from `separation_of_duties` → `policies_present` (governance sign-off is a policy/commitment check, not a duty-separation check).
- `kisa_isms.py` `ISMS-3.2` ("Risk treatment"): `check_type` changed from `pen_testing` → `policies_present` (a documented risk treatment plan, not a penetration test).
- `kisa_isms.py` `ISMS-14.2` ("Internal audit"): `check_type` changed from `pen_testing` → new `internal_audit_evidence` check_type, implemented in `_common_checks.py`'s presence table (queries `cissp_assessments` with `status: "completed"`) — distinct from both `pen_testing` (external assessment) and `ISMS-14.1`'s `assessments_performed` (general compliance review).
- `iso_27018.py` `ISO27018-7.1.1` ("Disclosure of PII"): `check_type` changed from `incident_reporting` → new `pii_disclosure_controlled` check_type, implemented in `_common_checks.py`'s presence table (queries `data_classifications` for `category: "PII", access_restricted: True`) — reflects access-restriction to authorized parties rather than breach notification.

**Note on commit bundling:** WR-02's edits are single-line `check_type` value changes inside the same `CONTROLS` list entries that CR-02's `evaluate_controls` implementation needed to dispatch against and test end-to-end. Fixing the check_type values before implementing/testing the dispatcher (rather than as a separate follow-up commit touching the same lines again) let the CR-02 spot-check (calling `evaluate_controls` and asserting zero unmapped check_types) validate the corrected values directly. Both fixes are recorded here for traceability even though they landed in one commit.

### CR-01: 14 new frameworks were not registered in any code path a user can reach

**Files modified:** `backend/compliance_frameworks_endpoints.py`, `backend/seed_compliance_frameworks_b.py`
**Commit:** `6c255dc`
**Applied fix:**
- Added all 14 modules to the `frameworks` import and to `_REGISTRY` in `compliance_frameworks_endpoints.py`, using each module's own `FRAMEWORK_ID` value as the registry key (all 14 module `FRAMEWORK_ID`s already matched their filenames, so no key-naming judgment calls were needed).
- Added a `seed_compliance_frameworks_b.py` import of the 14 modules plus a `_controls_from_module(mod)` helper that derives each seed document's `controls` list directly from the module's own `CONTROLS` (via `id`/`title`/`description`/`theme`), keeping the framework module as the single source of truth rather than duplicating ~611 control entries by hand into the seed file. Appended 14 new entries to `FRAMEWORKS_PART2` — `name`/`shortName`/`description` per entry use each module's `FRAMEWORK_NAME` and one-line module docstring (also avoiding fabricated/duplicated descriptive text). 13 of the 14 are seeded `"status": "Implemented", "progress": 100` (matching the existing convention for other check-based, non-DB-driven frameworks like `nist_800_53`); `fedramp_high` is seeded `"status": "In Progress"` with `progress` computed as `round(131/421*100) = 31` rather than falsely claiming 100%, since CR-03 (control-count shortfall) was deliberately left unfixed in this pass — seeding it as "fully implemented" would have been dishonest.

**Verification performed (beyond standard 3-tier):**
- `import compliance_frameworks_endpoints`: succeeds; all 14 new IDs confirmed present in `_REGISTRY` (registry grew from 30 to 44 entries).
- `from seed_compliance_frameworks_a import FRAMEWORKS_PART1; from seed_compliance_frameworks_b import FRAMEWORKS_PART2`: succeeds; all 14 new IDs present with non-empty `controls` lists; combined canonical id set is 44 with zero duplicate ids (confirming `seed_compliance.py`'s stale-doc deletion logic, which is keyed off this canonical set, will not delete anything unexpectedly and will not collide with any existing framework id).

### WR-01: No test coverage for any of the 14 new framework modules

**Files modified:** `backend/tests/test_frameworks_schema.py` (new)
**Commit:** `855bd02`
**Applied fix:** Added a parametrized pytest module that iterates every module in `frameworks.__all__` (43 modules, including the 14 phase-19 additions) and asserts: `FRAMEWORK_ID`/`FRAMEWORK_NAME`/`FRAMEWORK_VERSION` are non-empty strings; `CONTROLS` is a list (non-empty entries validated for dict shape, required `id`/`title`/`description` keys, and unique `id`s — pre-existing modules that legitimately use the DB-driven `CONTROLS=[]` pattern, e.g. `gdpr`/`dora`/`cobit`, are skipped for the non-empty-specific shape check via `pytest.skip`, not silently passed); `evaluate_controls` is defined and is an `async` function; and `evaluate_controls(db)` returns exactly one result per `CONTROLS` entry when run against a lightweight mocked db (DB-driven modules detected structurally via bytecode inspection of `evaluate_controls`, since a couple of them, e.g. `eu_ai_act`, have a non-empty-but-vestigial static `CONTROLS` list their `evaluate_controls` never actually consults — this is a pre-existing, out-of-scope quirk unrelated to phase 19, handled rather than papered over). Added two additional focused parametrized checks specific to the 14 phase-19 frameworks: each must ship a non-empty static `CONTROLS` list, and each must be present in `compliance_frameworks_endpoints._REGISTRY` (a CR-01 regression guard).

**Verification performed:** `pytest tests/test_frameworks_schema.py -q` → 232 passed, 21 skipped (the legitimate DB-driven modules), 0 failed. Also ran alongside `test_compliance_score.py` to confirm no interaction/regression: 242 passed, 21 skipped.

### IN-01: `fedramp_high.py` docstring falsely claimed "421+ controls"

**Files modified:** `backend/frameworks/fedramp_high.py`
**Commit:** `9458f6e` (bundled with CR-02, same file)
**Applied fix:** Docstring changed from `"""FedRAMP High — NIST 800-53 High baseline (421+ controls)."""` to `"""FedRAMP High — NIST 800-53 High baseline (131 of 421 controls implemented; full baseline pending)."""`, as a direct consequence of CR-03 (the actual control-count fix) being deliberately left unfixed in this pass. This is a one-line honest-accounting correction, not the WR-03 reformat.

## Skipped Issues

### CR-03: Every new framework's control count falls far short of the plan's must-have minimums

**File:** `backend/frameworks/ens.py`, `mas_trm.py`, `irap.py`, `iso_27017.py`, `iso_27018.py`, `bsi_c5.py`, `ffiec.py`, `tisax.py`, `aws_well_architected.py`, `rbi_csf.py`, `tic_3_0.py`, `kisa_isms.py`, `fedramp_high.py`
**Reason:** Explicitly deferred by the user/task instructions. Authoring hundreds of accurate regulatory compliance control entries from model knowledge (e.g. expanding `fedramp_high` from 131 to 421 controls, `kisa_isms` from 34 to 80+) carries real fabrication risk for a compliance-facing product. This was intentionally scoped out of this fix pass for a separate, properly-resourced follow-up (e.g. sourcing controls from the actual published framework documents rather than model recall). No speculative controls were added to pad counts. `IN-01` was fixed as an honest-accounting side effect (correcting `fedramp_high.py`'s docstring so it doesn't misstate its own control count while this shortfall remains unaddressed), and `fedramp_high`'s seed entry was given an honest `"In Progress"` / `31%` status rather than falsely claiming completion.
**Original issue:** See `19-REVIEW.md` CR-03 — every framework except `owasp_top10` (which matches the fixed 10-item OWASP Top 10 list) ships 20-75% fewer controls than the plan's stated minimums.

### WR-03: Inconsistent coding style across the 14 new files

**File:** `backend/frameworks/ens.py`, `mas_trm.py`, `irap.py`, `iso_27018.py`, `bsi_c5.py`, `ffiec.py`, `owasp_top10.py`, `tisax.py`, `aws_well_architected.py`, `rbi_csf.py`, `tic_3_0.py`, `kisa_isms.py`
**Reason:** Explicitly out of scope per task instructions. Pure style/formatting concern (dense semicolon-chained single-line style vs. `iso_27017.py`/`fedramp_high.py`'s typed multi-line style) with no functional impact. Reformatting all 12 files would add significant diff noise without addressing any of the functional gaps (CR-01/CR-02/CR-03) that actually matter, and was explicitly excluded by the invoking workflow's custom scope.
**Original issue:** See `19-REVIEW.md` WR-03 — 12 of 14 files use a dense, unspaced, non-typed style that's harder to diff/review than the codebase's established convention.

### IN-02: Dense single-line control definitions reduce readability

**File:** `backend/frameworks/ens.py`, `mas_trm.py`, `irap.py`, `iso_27018.py`, `bsi_c5.py`, `ffiec.py`, `owasp_top10.py`, `tisax.py`, `aws_well_architected.py`, `rbi_csf.py`, `tic_3_0.py`, `kisa_isms.py`
**Reason:** Explicitly out of scope per task instructions — info-tier formatting nit, no functional impact, subsumed by (and explicitly separated from) the WR-03 skip above.
**Original issue:** See `19-REVIEW.md` IN-02 — single long unspaced lines per control obscure per-field diffs.

---

_Fixed: 2026-07-03T22:37:57Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
