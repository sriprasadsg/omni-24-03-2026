---
phase: 13
slug: ai-compliance-narratives
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-23
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | backend/tests/ |
| **Quick run command** | `python -m pytest backend/tests/test_compliance_narrative_service.py -x -q` |
| **Full suite command** | `python -m pytest backend/tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest backend/tests/test_compliance_narrative_service.py -x -q`
- **After every plan wave:** Run `python -m pytest backend/tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | AI-05 | — | Narrative output sanitised before PDF embed | unit | `python -m pytest backend/tests/test_compliance_narrative_service.py::test_sanitise -x -q` | ✅ | ⬜ pending |
| 13-01-02 | 01 | 1 | AI-05 | — | Long text trimmed to word boundary | unit | `python -m pytest backend/tests/test_compliance_narrative_service.py::test_trim_to_words -x -q` | ✅ | ⬜ pending |
| 13-01-03 | 01 | 1 | AI-05 | — | Executive summary generated via generate_text | unit | `python -m pytest backend/tests/test_compliance_narrative_service.py::test_executive_summary -x -q` | ✅ | ⬜ pending |
| 13-01-04 | 01 | 1 | AI-06 | — | Framework narrative generated per-framework | unit | `python -m pytest backend/tests/test_compliance_narrative_service.py::test_framework_narrative -x -q` | ✅ | ⬜ pending |
| 13-01-05 | 01 | 1 | AI-06 | — | enrich_report_data injects narrative into report dict | unit | `python -m pytest backend/tests/test_compliance_narrative_service.py::test_enrich_report_data -x -q` | ✅ | ⬜ pending |
| 13-01-06 | 01 | 2 | AI-05,AI-06 | — | _generate_report calls enrich_report_data when AI enabled | integration | `python -m pytest backend/tests/test_compliance_narrative_service.py::test_generate_report_integration -x -q` | ✅ | ⬜ pending |
| 13-01-07 | 01 | 2 | AI-05,AI-06 | — | Graceful fallback when generate_text raises | unit | `python -m pytest backend/tests/test_compliance_narrative_service.py::test_fallback_on_error -x -q` | ✅ | ⬜ pending |
| 13-01-08 | 01 | 2 | AI-05,AI-06 | — | _build_pdf receives enriched data with narratives | integration | `python -m pytest backend/tests/test_compliance_narrative_service.py::test_build_pdf_receives_narratives -x -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `backend/tests/test_compliance_narrative_service.py` — 8-test suite for AI-05/AI-06

*Existing infrastructure covers all phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| PDF contains AI-generated narrative sections in generated report | AI-05, AI-06 | Requires full scheduler + email delivery pipeline | Trigger a scheduled report run, download PDF, verify narrative sections present |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
