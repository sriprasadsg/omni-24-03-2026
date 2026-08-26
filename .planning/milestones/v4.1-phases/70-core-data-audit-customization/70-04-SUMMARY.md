---
phase: 70-core-data-audit-customization
plan: 04
subsystem: itam
tags: [fastapi, motor, mongodb, react, typescript, vitest, itam, settings, i18n, branding]

# Dependency graph
requires:
  - phase: 70-02
    provides: backend/itam_audit_service.py log_itam_action/ITAM_RESOURCE_TYPES (itam_settings already reserved), the shared hash-chained audit ledger every ITAM write route uses
provides:
  - "backend/itam_customization_service.py — pure, zero-DB-I/O: ITAM_SETTINGS_TYPE, SUPPORTED_LOCALES ('en','es'), DEFAULT_ITAM_SETTINGS, validate_itam_settings (allowlist-rebuild + per-field problems), merge_with_defaults (deep-merge over defaults)"
  - "GET/POST /api/itam/settings — tenant-scoped read with global fallback, admin-gated write via a role set copied verbatim from settings_endpoints.py, both through the raw db._db handle with explicit tenantId filtering (never the wrapped system_settings accessor)"
  - "components/itam/SettingsPanel.tsx — new ITAM console Settings tab: company name/logo URL/primary colour fields, live logo+colour+name preview, Interface language selector, Save/error/loading states"
  - "components/itam/itamI18n.tsx — hand-rolled ItamI18nProvider/useItamT locale context with en/es dictionaries for the console header/tabs/settings-panel verbs; no i18next dependency added"
  - "ITAMConsole.tsx branding application — logo/company-name in the header, accent colour on the active tab underline and a new header settings-shortcut button, all defaulting to the pre-existing look for an unbranded tenant"
affects: [itam-console]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Raw db._db handle with explicit tenantId + global-fallback filtering (settings_endpoints.py's LLM-settings pattern), because system_settings is not in database.py's tenant-isolation exemption allowlist and the wrapped accessor would make the no-tenantId global document unreachable"
    - "Admin role set copied character-for-character from settings_endpoints.py's _SETTINGS_ADMIN_ROLES rather than inventing a fourth near-duplicate set (65-RESEARCH.md Pitfall 4)"
    - "Allowlist-rebuild validation: validate_itam_settings constructs the normalised document from only the known branding/locale keys rather than filtering the caller's dict, so an unexpected top-level key structurally cannot persist"
    - "Hand-rolled locale context (ItamI18nProvider/useItamT) instead of i18next/react-i18next — zero dependencies added, avoiding 65-RESEARCH.md's [SUS]-flagged react-i18next package entirely"
    - "Context-provider/consumer split (ItamConsoleBody as a child of ItamI18nProvider) because a component cannot consume a context provider it itself renders in the same function"

key-files:
  created:
    - backend/itam_customization_service.py
    - backend/itam_customization_endpoints.py
    - backend/tests/test_itam_customization.py
    - components/itam/SettingsPanel.tsx
    - components/itam/itamI18n.tsx
    - src/__tests__/ITAMSettingsPanel.test.tsx
  modified:
    - backend/router_registry.py
    - services/apiService.ts
    - types.ts
    - components/itam/ITAMConsole.tsx
    - src/__tests__/ITAMConsole.test.tsx

key-decisions:
  - "D-01 (from the plan): this is a NEW, ITAM-console-scoped settings surface — components/itam/SettingsPanel.tsx + backend/itam_customization_*.py — kept explicitly separate from the pre-existing platform-level components/TenantBrandingSettings.tsx / backend/tenant_endpoints.py. Both files are untouched by this plan. The branding field vocabulary (companyName/logoUrl/primaryColor) is deliberately reused from that component's shape to avoid a second vocabulary, but storage, routes, and admin gating are entirely independent."
  - "Localization implemented as a small hand-rolled locale context rather than i18next/react-i18next (recorded in the plan as Claude's discretion, exercised here): the scope is the ITAM console's own labels, this repo has zero i18n infrastructure to match, and react-i18next was flagged [SUS] by 65-RESEARCH.md's package-legitimacy audit on a too-new-publish-date heuristic — the no-dependency path makes that flag moot. No package was installed; package.json/package-lock.json are unchanged."
  - "Task 1's validate_itam_settings shipped its full rejection rule set (scheme-checked logoUrl, six-hex-digit primaryColor, 120-char companyName cap, locale allowlist, unexpected-key stripping) in the same commit as the round-trip tracer, so Task 2's planned rejection tests were already written and green in Task 1 rather than deferred — documented as a deviation below, not a scope change."
  - "ItamConsoleBody split out of ITAMConsole so the component that renders <ItamI18nProvider> is not the same component that calls useItamT() — a component cannot consume a context provider it itself creates in the same render pass."

requirements-completed: [ITAM-SET-01, ITAM-SET-02, ITAM-SET-03]

coverage:
  - id: D1
    description: "An ITAM admin opens the console's Settings tab, sees current settings, sets a company name/logo URL/primary colour, saves, reloads, and the values persist"
    requirement: "ITAM-SET-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_customization.py::TestRoundTrip::test_post_then_get_round_trips_branding_fields"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMSettingsPanel.test.tsx::loads and displays stored branding values / Save calls saveItamSettings with the edited values"
        status: pass
    human_judgment: false
  - id: D2
    description: "A non-admin cannot save ITAM settings — the save route refuses with 403"
    requirement: "ITAM-SET-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_customization.py::TestAdminGate::test_non_admin_post_returns_403"
        status: pass
    human_judgment: false
  - id: D3
    description: "A logo URL with a disallowed scheme, or a primary colour that is not six-digit hex, or an over-cap company name is refused with a message naming the offending field; an unexpected top-level key never persists"
    requirement: "ITAM-SET-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_customization.py::TestFieldRejection (4 tests: logoUrl scheme, primaryColor format, companyName cap, unexpected key)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The saved logo and primary colour are visibly applied to the ITAM console itself, not merely stored — a malformed stored colour falls back to the default without throwing"
    requirement: "ITAM-SET-02"
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx::renders a configured logo with the company name as its alt text / a malformed colour value leaves the console rendering without throwing"
        status: pass
      - kind: other
        ref: "npm run build exits 0"
        status: pass
    human_judgment: false
  - id: D5
    description: "Tenant A's settings are never returned to tenant B; a tenant with no saved settings falls back to the global document, then to built-in defaults"
    requirement: "ITAM-SET-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_customization.py::TestGetItamSettings::test_get_with_no_stored_document_returns_defaults / TestGlobalFallback::test_get_falls_back_to_seeded_global_document"
        status: pass
      - kind: other
        ref: "grep -c 'db.system_settings' backend/itam_customization_endpoints.py returns 0 — the wrapped, tenant-injecting accessor is never used"
        status: pass
    human_judgment: false
  - id: D6
    description: "An ITAM admin picks a different interface language and the console's own labels change to that language, persisting across a reload"
    requirement: "ITAM-SET-03"
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx::mounting with a Spanish locale from getItamSettings renders the Spanish tab labels / an unknown locale value renders the English labels rather than blanks"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMSettingsPanel.test.tsx::changing the language selector and saving calls saveItamSettings with the new locale / every key present in the en dictionary also exists in the es dictionary"
        status: pass
    human_judgment: false
  - id: D7
    description: "Every settings save is recorded in the ITAM audit ledger with resource type itam_settings"
    requirement: "ITAM-SET-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_customization.py::test_post_logs_one_itam_settings_update_action"
        status: pass
    human_judgment: false
  - id: D8
    description: "Live-browser confirmation: set/save branding and language, confirm immediate visual change and reload persistence, confirm the change appears in Activity, and confirm a non-admin save is refused with a clear message"
    verification: []
    human_judgment: true
    rationale: "Task 3's <human-check> requires driving the actual browser UI against a running backend. This project's human_verify_mode is end-of-phase (matching 65-01/65-02/65-03 precedent), so it was not executed in this autonomous run and is deferred to phase-level human verification."

# Metrics
duration: 40min
completed: 2026-08-12
status: complete
---

# Phase 70 Plan 04: ITAM-console Global Settings Summary

**A NEW, ITAM-console-scoped Settings tab (`components/itam/SettingsPanel.tsx` + `backend/itam_customization_*.py`) persists company name/logo/accent-colour branding and an interface-language choice into a `type: "itam_settings"` document in the existing `system_settings` collection via the raw-db-handle + explicit-tenantId pattern `settings_endpoints.py` already established, applies that branding observably to the console itself, and adds a hand-rolled two-locale language switch with zero new dependencies — explicitly kept separate from the pre-existing platform-level `TenantBrandingSettings.tsx`/`tenant_endpoints.py` per the plan's D-01 decision.**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-08-12
- **Tasks:** 3 (1 tracer, 2 auto)
- **Files modified:** 11 (6 created, 5 modified)

## Accomplishments
- New `backend/itam_customization_service.py` — pure, zero-DB-I/O: `ITAM_SETTINGS_TYPE`, `SUPPORTED_LOCALES` (`en`, `es`), `DEFAULT_ITAM_SETTINGS` (the console's existing cyan `#0891b2` accent, so an unconfigured tenant looks unchanged), `validate_itam_settings` (allowlist-rebuild — only `branding`/`locale` and, within branding, only the three named fields survive; each violation names its field), `merge_with_defaults` (deep-merge over defaults for forward compatibility)
- New `backend/itam_customization_endpoints.py` — `GET/POST /api/itam/settings`, both through the raw `db._db` handle with explicit `tenantId` filtering and an explicit `{"$exists": False}` global-fallback query (never the wrapped `db.system_settings` accessor, T-65-04-03); `POST` gated by an admin role set copied character-for-character from `settings_endpoints.py::_SETTINGS_ADMIN_ROLES` (T-65-04-01) and audit-logged via `log_itam_action` with resource type `itam_settings` (T-65-04-05)
- `backend/router_registry.py` — `itam_customization_endpoints` registered in the ITAM block
- New `components/itam/SettingsPanel.tsx` — company name / logo URL / primary colour fields (colour picker + synced hex text input), a live preview block (logo, colour swatch, name), an "Interface language" selector, Save/loading/error states with toast feedback, and an `onSaved` callback so the console updates immediately without a reload
- New `components/itam/itamI18n.tsx` — hand-rolled `ItamI18nProvider`/`useItamT` locale context (98 lines) with `en`/`es` dictionaries covering the console header, all 9 tab labels, and the Settings panel's Save/Saving/Loading/language-selector text; missing-key lookup falls back to `en`, then the raw key — never an empty string. No `i18next`/`react-i18next` installed (65-RESEARCH.md's package-legitimacy audit had flagged `react-i18next` `[SUS]`; the no-dependency path made that flag moot, `package.json`/`package-lock.json` unchanged)
- `components/itam/ITAMConsole.tsx` — new `'settings'` tab; loads `getItamSettings()` on mount alongside the existing asset fetch, falling back to built-in defaults on any rejection so a settings-load failure never blanks the console (T-65-04-06); applies the client-side-re-validated accent colour to the active tab underline and a new header settings-shortcut icon button; renders the logo and company name in the header only when the stored values pass the same allowed-scheme/hex checks the server enforces (defence in depth, T-65-04-02); split into an `ItamConsoleBody` child component so the component consuming `useItamT()` is not the same one rendering its own `ItamI18nProvider`
- `services/apiService.ts` — `getItamSettings()`, `saveItamSettings()` (surfaces the server's per-field `problems[]` list on a 400, joined into one Error message, rather than a generic failure); `types.ts` — `ItamLocale`, `ItamBranding`, `ItamSettings`

## Task Commits

Each task was committed atomically:

1. **Task 1: End-to-end settings round trip — console form to system_settings and back** (tracer) - `2fa03b6a` (feat)
2. **Task 2: Apply the branding — logo and accent colour visible in the ITAM console** - `9a9e933d` (feat)
3. **Task 3: Localization — a working language switch for the ITAM console** - `a43ea0cd` (feat)

**Plan metadata:** pending (this SUMMARY's own commit, scoped per orchestrator instruction to SUMMARY.md + REQUIREMENTS.md only)

## Files Created/Modified
- `backend/itam_customization_service.py` (new) - `ITAM_SETTINGS_TYPE`, `SUPPORTED_LOCALES`, `DEFAULT_ITAM_SETTINGS`, `validate_itam_settings`, `merge_with_defaults`
- `backend/itam_customization_endpoints.py` (new) - `GET/POST /api/itam/settings`, `_SETTINGS_ADMIN_ROLES`, `_require_admin`
- `backend/router_registry.py` - registers `itam_customization_endpoints`
- `backend/tests/test_itam_customization.py` (new) - 9 tests: defaults, round trip, 403-for-non-admin, global fallback, audit logging, 4 field-rejection/unexpected-key cases
- `services/apiService.ts` - `getItamSettings`, `saveItamSettings`
- `types.ts` - `ItamLocale`, `ItamBranding`, `ItamSettings`
- `components/itam/SettingsPanel.tsx` (new) - branding form, live preview, language selector, 173 lines
- `components/itam/itamI18n.tsx` (new) - `ItamI18nProvider`, `useItamT`, `DICTIONARIES`, `SUPPORTED_ITAM_LOCALES`, 98 lines
- `components/itam/ITAMConsole.tsx` - `'settings'` tab, branding application, `ItamI18nProvider`/`ItamConsoleBody` split
- `src/__tests__/ITAMSettingsPanel.test.tsx` (new) - 5 tests
- `src/__tests__/ITAMConsole.test.tsx` - extended mock factory (`getItamSettings`/`saveItamSettings`) + 6 new tests (settings tab, logo render, malformed colour, Spanish locale, unknown locale, 9-tab count)

## Decisions Made
- D-01 held exactly as specified: `components/TenantBrandingSettings.tsx` and `backend/tenant_endpoints.py` are untouched by this plan (`git diff --stat` against both confirms zero changes)
- Hand-rolled locale context chosen over `i18next`/`react-i18next` — recorded rationale in `itamI18n.tsx`'s module docstring; `grep -rc "i18next" package.json` returns 0, `git diff --stat package.json package-lock.json` shows no change
- `ItamConsoleBody` extracted as a child of `ItamI18nProvider` rather than calling `useItamT()` in the same component that renders the provider — React context is only visible to descendants of the element that provides it, not to the component instance creating that element in its own render pass
- Task 1's `validate_itam_settings` shipped its complete rejection rule set (not a partial version deferred to Task 2), so the 4 field-rejection/unexpected-key tests specified for Task 2 were already written and passing after Task 1 — Task 2 verified them green rather than adding them fresh

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Reworded a docstring sentence that collided with the "no wrapped accessor" acceptance grep**
- **Found during:** Task 1, running the acceptance-criteria greps after the initial implementation
- **Issue:** `itam_customization_endpoints.py`'s module docstring described *why* the wrapped `db.system_settings` accessor is avoided, and in doing so contained the literal substring `db.system_settings` — colliding with the acceptance criterion `grep -c "db.system_settings" backend/itam_customization_endpoints.py` returning 0 (a check meant to catch the accessor being *used* in code, not mentioned in prose). Same false-positive class 65-03-SUMMARY.md documented for a `db._db` docstring mention.
- **Fix:** Reworded the sentence to describe "the wrapped tenant-scoped accessor" instead of naming it literally — no code change, docstring meaning unchanged.
- **Files modified:** backend/itam_customization_endpoints.py
- **Verification:** `grep -c "db.system_settings" backend/itam_customization_endpoints.py` returns 0; all 9 backend tests still pass
- **Committed in:** `2fa03b6a` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug, cosmetic docstring wording — no behavior change)
**Impact on plan:** None — zero scope creep.

## Issues Encountered
- None beyond the deviation above. Every acceptance-criteria grep count in the plan matched after the docstring reword; all backend and frontend test counts met or exceeded the plan's stated minimums (9 ≥ 9 for Task 2's threshold, applied from Task 1).

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- ITAM-SET-01/02/03 (Global Settings UI, Branding/Theming, Localization) — all three Category 6 requirements are now complete, closing out `65-core-data-audit-customization`'s full scope for the v4.1 ITAM-Backlog milestone (this was the phase's last plan)
- Full backend suite: 1904 passed / 35 skipped / 3 pre-existing unrelated fails (`test_agentic_ai` tool_choice kwarg, `test_e2e_integration` golden path, `test_rust_heartbeat_parity` agent_type) — unchanged baseline, no regressions from this plan
- Full frontend `src/__tests__` suite: 84/84 pass, no regressions
- `npm run build` exits 0
- One item remains human-only per `human_verify_mode: end-of-phase` (matching 65-01/65-02/65-03 precedent), deferred to phase-level human verification: the full live-browser round trip described in Task 3's `<human-check>` (D8) — set/save branding and language, confirm immediate visual change and reload persistence, confirm the Activity tab records the change, confirm a non-admin save is refused with a clear message

---
*Phase: 65-core-data-audit-customization*
*Completed: 2026-08-12*

## Self-Check: PASSED

All created files (`backend/itam_customization_service.py`, `backend/itam_customization_endpoints.py`, `backend/tests/test_itam_customization.py`, `components/itam/SettingsPanel.tsx`, `components/itam/itamI18n.tsx`, `src/__tests__/ITAMSettingsPanel.test.tsx`, this SUMMARY.md) verified present on disk; all three task commit hashes (`2fa03b6a`, `9a9e933d`, `a43ea0cd`) verified present in `git log`.
