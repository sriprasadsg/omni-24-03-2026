---
phase: 61
slug: frontend-itam-console
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-06
---

# Phase 61 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Vitest 3.2.4 (frontend); pytest (backend — not touched by this phase) |
| **Config file** | `vite.config.ts` (embedded `test` block, `setupFiles: ['./src/__tests__/setup.ts']`) |
| **Quick run command** | `npx vitest run <path-to-new-test-file>` |
| **Full suite command** | `npm run test` (= `vitest run`) |
| **Estimated runtime** | unmeasured — Wave 0 creates the first ITAM frontend test files |

---

## Sampling Rate

- **After every task commit:** `npx tsc --noEmit && npm run build` (tsc catches the `Record<AppView,Permission>` completeness bug that `build`/esbuild misses — this is the same gap class Phase 47-06 hit)
- **After every plan wave:** `npm run test` (full vitest suite) + `npx tsc --noEmit && npm run build`
- **Before `/gsd-verify-work`:** Full suite must be green; manual UAT round-trip walkthrough is the authoritative check for ROADMAP success criterion 3
- **Max feedback latency:** unmeasured (small suite; no watch-mode flags)

---

## Per-Task Verification Map

*Task IDs not yet assigned — the planner has not run for this phase (blocked on UI-SPEC gate). The rows below are the requirement-level map from research; explode into per-task rows once PLAN.md files exist.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | ITAM-UI-01 | — | `manage:itam` permission gates Sidebar/App view | unit | `npx tsc --noEmit` (Record<AppView,Permission> completeness) + `grep -c "itam" App.tsx components/Sidebar.tsx` | ❌ Wave 0 | ⬜ pending |
| TBD | TBD | TBD | ITAM-UI-01 | — | Console renders 4 tabs and switches between them | component | `npx vitest run components/itam/__tests__/ITAMConsole.test.tsx` | ❌ Wave 0 | ⬜ pending |
| TBD | TBD | TBD | ITAM-UI-01 | — | apiService client functions target the correct exact paths | unit | `npx vitest run services/__tests__/itamApiService.test.ts` | ❌ Wave 0 | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `components/itam/__tests__/ITAMConsole.test.tsx` — stubs covering tab-switching + permission-gated render
- [ ] `services/__tests__/itamApiService.test.ts` — stubs covering every new apiService function's URL/method/body shape (mocked fetch, no live backend)

*No shared fixture/mocking gap identified — existing `src/__tests__/setup.ts` already provides the vitest environment used by other component tests in this repo.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full round trip without leaving the console (create catalog asset → check it out → view its warranty/finance tab → assign a license) | ITAM-UI-01 (ROADMAP success criterion 3) | No existing automated harness drives real browser UI in this repo; every prior console-wiring phase (47-06, 48-05, 29-04) logged this as manual-only | Log in as admin, open ITAM console, complete one full create → check-out → finance-view → license-assign round trip per cluster without navigating away from the console |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < N/A (unmeasured — small suite)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
