---
phase: 19-compliance-frameworks
plan: 01
subsystem: compliance-frameworks
tags: [regulatory-frameworks, python, schema-validation]

requires: []
provides:
  - 14 new framework modules (ens, mas_trm, irap, iso_27017, iso_27018, bsi_c5, ffiec, owasp_top10, tisax, aws_well_architected, rbi_csf, tic_3_0, kisa_isms, fedramp_high)
  - All 14 registered in compliance_frameworks_endpoints._REGISTRY and reachable via the API
  - evaluate_controls/_run_check implemented for all 14 via shared _common_checks dispatcher
  - Parametrized schema/contract test suite covering all 43 framework modules (test_frameworks_schema.py)
affects: [compliance-score-dashboard]

tech-stack:
  added: []
  patterns:
    - "Shared _common_checks dispatcher for evaluate_controls/_run_check across new framework modules, avoiding 14 near-duplicate implementations"

key-files:
  created:
    - backend/frameworks/ens.py
    - backend/frameworks/mas_trm.py
    - backend/frameworks/irap.py
    - backend/frameworks/iso_27017.py
    - backend/frameworks/iso_27018.py
    - backend/frameworks/bsi_c5.py
    - backend/frameworks/ffiec.py
    - backend/frameworks/owasp_top10.py
    - backend/frameworks/tisax.py
    - backend/frameworks/aws_well_architected.py
    - backend/frameworks/rbi_csf.py
    - backend/frameworks/tic_3_0.py
    - backend/frameworks/kisa_isms.py
    - backend/frameworks/fedramp_high.py
    - backend/tests/test_frameworks_schema.py
  modified: []

key-decisions:
  - "CR-03 (every new framework ships far fewer controls than the plan's stated minimums, e.g. fedramp_high at 131/421) deliberately NOT fixed — authoring hundreds of regulatory control entries from model recall carries real fabrication risk for a compliance-facing product; deferred to a properly-resourced follow-up sourcing controls from actual published framework documents"
  - "fedramp_high.py docstring and seed status corrected to honestly state partial coverage (131 of 421 controls, 'In Progress'/31%) rather than falsely claiming completion, as a direct honest-accounting consequence of deferring CR-03"

requirements-completed: [FW-01]

duration: unknown (retroactively documented)
completed: 2026-07-04
status: partial
---

# Phase 19: Additional Compliance Frameworks Summary

**14 new regulatory framework modules (ENS, MAS TRM, IRAP, ISO 27017/27018, BSI C5, FFIEC, OWASP Top 10, TISAX, AWS Well-Architected, RBI CSF, TIC 3.0, KISA ISMS, FedRAMP High) registered and evaluable via the compliance API — but shipped with honestly-documented partial control coverage, not the plan's full target counts.**

## Performance
- **Duration:** unknown — implementation predates this documentation pass; retroactively summarized after confirming via git history, code review, and fix cycle
- **Files modified:** 15 (14 framework modules + test_frameworks_schema.py)

## Accomplishments
- 14 new framework modules following the existing schema (`FRAMEWORK_ID`, `FRAMEWORK_NAME`, `FRAMEWORK_VERSION`, `CONTROLS`, `evaluate_controls`)
- All 14 registered in `compliance_frameworks_endpoints._REGISTRY` and seeded via `seed_compliance_frameworks_b` (CR-01 fix — originally unreachable via the API)
- `evaluate_controls`/`_run_check` implemented for all 14 via a shared `_common_checks` dispatcher (CR-02 fix — originally unimplemented stubs)
- Parametrized schema/contract test suite (`test_frameworks_schema.py`) covering all 43 framework modules in the codebase (232 passed, 21 legitimately skipped for DB-driven modules), plus 2 phase-19-specific regression guards (non-empty `CONTROLS`, presence in `_REGISTRY`)
- Full code review: 3 critical + 3 warning + 2 info findings (19-REVIEW.md); CR-01, CR-02, WR-01, IN-01 fixed; **CR-03 and WR-03 explicitly and deliberately skipped** (see Deviations)

## Task Commits
Initial implementation bundled into a mislabeled commit from an adjacent phase's session (pre-existing repo-history quirk).

Review fixes:
1. **CR-01** register 14 new frameworks in `_REGISTRY` and seed function — `6c255dc3`
2. **CR-02** implement `evaluate_controls`/`_run_check` via shared dispatcher — `9458f6ef`
3. **WR-01** add parametrized schema/contract tests for all 43 framework modules — `855bd026`
4. **IN-01** correct `fedramp_high.py` docstring's false "421+ controls" claim — bundled with `9458f6ef`

## Files Created/Modified
- `backend/frameworks/{ens,mas_trm,irap,iso_27017,iso_27018,bsi_c5,ffiec,owasp_top10,tisax,aws_well_architected,rbi_csf,tic_3_0,kisa_isms,fedramp_high}.py` — 14 new framework modules
- `backend/tests/test_frameworks_schema.py` — parametrized schema/contract suite (43 modules)

## Decisions & Deviations

**CR-03 — deliberately unfixed, not a code defect:** every new framework ships 20–75% fewer controls than the plan's stated minimums (e.g. `fedramp_high` at 131 of 421; `kisa_isms` well under its 80+ target). This was an explicit scope decision: authoring hundreds of accurate regulatory compliance control entries from model knowledge carries real fabrication risk for a compliance-facing product. No speculative controls were added to pad counts toward the plan's numbers. This is deferred to a separate, properly-resourced follow-up that sources controls from the actual published framework documents rather than model recall.

**WR-03 — deliberately unfixed:** inconsistent code style (single long unspaced lines per control) across the 14 new files — cosmetic, no functional impact, explicitly out of scope for this pass.

Because of the CR-03 gap, this phase is marked `status: partial` rather than `complete` — the API surface, registration, and evaluation logic are fully correct and tested, but the underlying regulatory content is a documented partial subset, not the full framework.

## Issues Encountered
This phase's `SUMMARY.md` was not created at execution time, causing downstream tooling to treat the phase as unimplemented despite the code, review, and fix cycle all being complete and committed. Retroactively authored after independently verifying via git history and the existing `19-REVIEW.md`/`19-REVIEW-FIX.md` artifacts.

## Next Phase Readiness
Phase 19's API/registration/evaluation layer is complete and tested. **Before shipping this as "done" to users or auditors, decide how to handle the CR-03 control-count gap** — either scope the follow-up work to backfill real controls from source documents, or adjust user-facing claims about these frameworks' coverage depth. Not blocking for `/gsd-verify-work 19`, but worth surfacing there.

---
*Phase: 19-compliance-frameworks*
*Completed: 2026-07-04*
