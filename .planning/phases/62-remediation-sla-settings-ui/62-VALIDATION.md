---
phase: 62
slug: remediation-sla-settings-ui
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-10
validated: 2026-08-10
---

# Phase 62 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Vitest ^3.2.4 + @testing-library/react ^16.3.0 |
| **Config file** | `vite.config.ts` (`test:` block, line 83) |
| **Quick run command** | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx` |
| **Full suite command** | `npm test` (`vitest run`) |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx`
- **After every plan wave:** Run `npm test` (full `src/__tests__` + `components/ui/__tests__` suite — 172 passed as of the Phase 61 session baseline)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 62-01-01 | 01 | 1 | SLA-03 | — | Remediation tab renders with correct label/icon and is reachable by every user | unit (render) | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx -t "renders"` | ✅ | ✅ green |
| 62-01-02 | 01 | 1 | SLA-03 | — | Tab shows the fetched `windowDays` value pre-filled on mount | unit (render + mocked fetch) | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx -t "fetch"` | ✅ | ✅ green |
| 62-01-03 | 01 | 1 | SLA-03 | — | Save calls the PATCH wrapper with the current value and shows a success toast on 2xx | unit (interaction) | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx -t "save"` | ✅ | ✅ green |
| 62-01-04 | 01 | 1 | SLA-03 | — | A 403 (or any save failure) surfaces the generic error toast, not a permission-specific message — matches D-04's "no client-side role gate" decision | unit (interaction, mocked rejected promise) | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx -t "error"` | ✅ | ✅ green |
| 62-01-05 | 01 | 1 | SLA-03 | — | Client-side clamp rejects values outside 1-365 (Save disabled, validation message shown) | unit (interaction) | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx -t "validat"` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `src/__tests__/RemediationSlaSettings.test.tsx` — 9 tests covering SLA-03, following `src/__tests__/ITAMCatalogPanel.test.tsx`'s mock shape
- [x] No shared fixtures needed — component is self-contained (no props, no context dependency beyond the two mocked modules)
- [x] Framework install: none — Vitest/@testing-library/react already installed and configured for this exact component-test class

---

## Manual-Only Verifications

| ID | Description | Rationale |
|----|-------------|-----------|
| D7 | Visual/UX sign-off — tab glyph and one-word label, visual hierarchy, typography weight parity, accent reservation, and the non-admin save flow shows the generic toast with no role/permission wording, all confirmed live in the running app | `workflow.human_verify_mode` is end-of-phase; this is a judgment call on rendered UI, not something a unit test asserts. Deferred to the phase's consolidated UAT (see `62-01-SUMMARY.md` Next Phase Readiness). |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-08-10 — 9/9 tests green (`npx vitest run src/__tests__/RemediationSlaSettings.test.tsx`), zero regressions in phase-62 files against `npm test`.

---

## Validation Audit 2026-08-10

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 5/5 (pre-existing, confirmed green) |
| Escalated | 1 (D7 — manual-only by design, human_verify_mode: end-of-phase) |
