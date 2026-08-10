---
phase: 62
slug: remediation-sla-settings-ui
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-10
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
| 62-01-01 | 01 | 1 | SLA-03 | — | Remediation tab renders with correct label/icon and is reachable by every user | unit (render) | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx -t "renders"` | ❌ W0 | ⬜ pending |
| 62-01-02 | 01 | 1 | SLA-03 | — | Tab shows the fetched `windowDays` value pre-filled on mount | unit (render + mocked fetch) | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx -t "fetch"` | ❌ W0 | ⬜ pending |
| 62-01-03 | 01 | 1 | SLA-03 | — | Save calls the PATCH wrapper with the current value and shows a success toast on 2xx | unit (interaction) | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx -t "save"` | ❌ W0 | ⬜ pending |
| 62-01-04 | 01 | 1 | SLA-03 | — | A 403 (or any save failure) surfaces the generic error toast, not a permission-specific message — matches D-04's "no client-side role gate" decision | unit (interaction, mocked rejected promise) | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx -t "error"` | ❌ W0 | ⬜ pending |
| 62-01-05 | 01 | 1 | SLA-03 | — | Client-side clamp rejects values outside 1-365 (Save disabled, validation message shown) | unit (interaction) | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx -t "validat"` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `src/__tests__/RemediationSlaSettings.test.tsx` — stubs for SLA-03, following `src/__tests__/ITAMCatalogPanel.test.tsx`'s mock shape: `vi.mock('../../services/apiService', ...)` + `vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }))`
- [ ] No shared fixtures needed — component is self-contained (no props, no context dependency beyond the two mocked modules)
- [ ] Framework install: none — Vitest/@testing-library/react already installed and configured for this exact component-test class (`ITAMCatalogPanel.test.tsx`, `ITAMConsole.test.tsx` precedents)

---

## Manual-Only Verifications

*None — all phase behaviors have automated verification via the unit test file above.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
