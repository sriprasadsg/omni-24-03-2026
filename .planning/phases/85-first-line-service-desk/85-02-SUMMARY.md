---
phase: 85-first-line-service-desk
plan: 02
subsystem: service-desk
tags: [copy, starters, tray-contract, copy-gate, vitest, pytest]
status: complete

requires: []
provides:
  - "backend/service_desk/messages.py: every server sentence of the desk (5 shared strings, 19 staff reason labels, 8 draft reason texts, Activity, tray and API detail texts, sentence/plural/activity_why)"
  - "backend/service_desk/starters.py: the four generic starter IT articles and copy_docs"
  - "backend/service_desk/tray_contract.py: the frozen tray-to-server contract (routes, template ids, limits, timings, field names)"
  - "components/serviceDesk/serviceDeskCopy.ts: every fixed UI label and the fill helper"
  - "services/serviceDesk/types.ts: request and response types for every desk route"
  - "ACTV-08 copy gate over backend/service_desk, components/serviceDesk and services/serviceDesk"
affects: [85-01, 85-03, 85-04, 85-05, 85-06, 85-10, 85-12, 85-19, 85-23]

actuals:
  tokens: 16600
  tasks: 3
  commits: 3
plan_head_before: cfeee0e8c290feb1edaab5bd4e6fd616ba8132a4
plan_head_after: ef3c0785a08cbb40d961bc0a5d59ab3eda0173ac

tech-stack:
  added: []
  patterns:
    - "One module per language holds every user-visible sentence; a vitest test reads the Python file as text to keep the shared strings in step"
    - "Starter text lives only in service_desk/starters.py (no JSON copy); tests and the Knowledge Base button load the same module"
    - "Contract constants pinned by literal tests so a change is a visible diff"

key-files:
  created:
    - backend/service_desk/messages.py
    - backend/service_desk/starters.py
    - backend/service_desk/tray_contract.py
    - backend/tests/test_service_desk_starters.py
    - backend/tests/test_service_desk_tray_contract.py
    - components/serviceDesk/serviceDeskCopy.ts
    - services/serviceDesk/types.ts
    - src/__tests__/serviceDeskCopy.test.ts
  modified:
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "starters.py is the single source of the starter text; no starter_articles.json fixture is made (assumption A-85-STARTER-SRC); 85-23 records this in the validation map"
  - "Hand-off reasons exist only in STAFF_REASON_LABELS; every requester-facing text is generic (T-85-06), and a test checks no requester text contains a staff label"
  - "serviceDeskCopy.ts stays one file (401 lines, under the 480-line split threshold)"
  - "messages.py gained ACTION_LABELS, UNDO_HINT, UNDO_TOAST and UNDO_TOAST_BREAKER beyond the plan's list so the Activity rows have all their text in one module"

requirements-completed: [DESK-01, DESK-02, DESK-06, DESK-07]

coverage:
  - id: D1
    description: "Server copy module with the five shared strings, 19 staff reason labels and 8 draft reason texts"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_starters.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Four generic starter IT articles and the tenant-scoped copy builder"
    requirement: "DESK-07"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_starters.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Frozen tray-to-server contract pinned by literal tests"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tray_contract.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "UI copy module and API types, with the shared strings checked against the server file"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "src/__tests__/serviceDeskCopy.test.ts"
        status: pass
    human_judgment: false
  - id: D5
    description: "ACTV-08 copy gate walks the three new desk directories on both sides"
    requirement: "DESK-06"
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_copy.py; src/__tests__/autonomousOpsCopy.test.ts"
        status: pass
    human_judgment: false
---

# Phase 85 Plan 02: Contracts, copy, starters and the copy gate Summary

Every contract the rest of Phase 85 builds against now exists once: all server copy, four generic editable starter IT articles, the frozen tray-to-server contract, all fixed UI copy plus API types, and the ACTV-08 copy gate extended over the three new desk directories.

Duration: about 15 min. Tasks: 3. Files: 11 (8 created, 3 modified). Completed 2026-11-08.

## Accomplishments

- **Server copy (Task 1, 841eb98a7).** `messages.py` holds MARK, FOOTER, HANDOFF_NOTICE, WITHDRAWN_NOTICE and OFFLINE_STATUS exactly as agreed, `STAFF_REASON_LABELS` (19 codes), `DRAFT_REASON_TEXT` (8), the Activity result templates, the tray window texts, the in-app notice title, `API_DETAIL` and the helpers `sentence`, `plural`, `activity_why`. `starters.py` holds the password reset, VPN, printer and agent tray starters (each opens with "Edit this article to match your organization before you rely on it.", uses "your company's" placeholders, and carries no URL, email, phone number, vendor or operating system name) and `copy_docs`, which builds tenant-scoped `knowledge_docs` documents with `helpdesk` True and `starterKey` set and refuses an empty or "global" tenant. The password article covers the self-service how-to and sends unlocks, MFA resets and access changes to a person through "I still need help" (D-32).
- **UI copy and types (Task 2, 27ee48325).** `serviceDeskCopy.ts` (401 lines) has one group per UI-SPEC surface and a `fill` helper. `types.ts` (168 lines) has every type the plan listed. `serviceDeskCopy.test.ts` reads `messages.py` as text and asserts the five shared strings, the eight draft reason lines and the notice title appear verbatim, and that every exported string is non-empty.
- **Tray contract (Task 3, ef3c0785a).** `tray_contract.py` pins the five route paths and methods, the `my_tickets` claim, the six template ids with their classes, the five legacy title prefixes, the limits (20 tickets, 60 days, 500-character note, 200-character title), the poll timings (30 s for 180 s, then 300 s, 10 s request timeout) and every field name. Its test pins each value literally and asserts the module imports nothing.

## Copy gate: directories now scanned

The ACTV-08 gate (JSON `directories`, pytest `EXPECTED_DIRECTORIES`, vitest `EXPECTED_DIRECTORIES`) now lists, in this order:

1. `backend/autonomous_ops/rollout`
2. `components/patchRollouts`
3. `services/patchRollouts`
4. `backend/service_desk`
5. `components/serviceDesk`
6. `services/serviceDesk`

Both copy tests pass on HEAD (pytest 33 passed; vitest 40 passed across the two files). 85-03's verify step, which runs `test_autonomous_ops_copy.py`, will find the three new directories present and non-empty. Every `.py` file added under `backend/service_desk` later (85-01's `__init__.py` and the rest) is scanned automatically and must stay free of the banned terms.

## Task Commits

| Task | Commit | Type | Description |
|------|--------|------|-------------|
| 1 | 841eb98a7 | feat | Service desk server copy and four starter IT articles |
| 2 | 27ee48325 | feat | UI copy, API types and the copy gate over the new directories |
| 3 | ef3c0785a | feat | Frozen tray-to-server contract |

Each task is one commit: the plan type is `execute` (tasks marked `tdd="true"`, not `type: tdd`), so the three-commit RED/GREEN gate does not apply. Tests and implementation were written together per task and committed together.

## Verification

- `backend/venv/bin/python -m pytest backend/tests/test_service_desk_starters.py` : 25 passed
- `backend/venv/bin/python -m pytest backend/tests/test_service_desk_tray_contract.py` : 8 passed
- `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_copy.py` : 33 passed
- `npx vitest run src/__tests__/serviceDeskCopy.test.ts src/__tests__/autonomousOpsCopy.test.ts` : exit 0, 40 passed
- `tsc --noEmit --strict` on `serviceDeskCopy.ts` and `types.ts`: clean
- Acceptance criteria: all PASS (the string appears once in `messages.py`; 19 and 8 label counts; starter keys in order; gate JSON has 3 matching lines; `types.ts` has 3 matching lines; every new file is under 500 lines; `tray_contract.py` has 1 `my_tickets` line and 5 `/tray/tickets` lines)
- No database was touched; no private mongod was needed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Directory-subset assertions in the existing copy tests**
- **Found during:** Task 2
- **Issue:** The plan says "nothing else in those files changes", but two existing assertions hard-code the old subsets and would fail once the three directories are listed: `backend == ["backend/autonomous_ops/rollout"]` in `test_autonomous_ops_copy.py` and `FRONTEND_DIRECTORIES` equal to the two patchRollouts folders in `autonomousOpsCopy.test.ts`.
- **Fix:** Updated both assertions to the new subsets (`["backend/autonomous_ops/rollout", "backend/service_desk"]` and the four frontend folders). The scan logic is unchanged.
- **Files modified:** backend/tests/test_autonomous_ops_copy.py, src/__tests__/autonomousOpsCopy.test.ts
- **Commit:** 27ee48325

**2. [Rule 2 - Missing critical] Extra message constants for Activity rows**
- **Found during:** Task 1
- **Issue:** The Activity row action labels ("Post ticket answer" and so on), the Undo hint and the two Undo toasts are server sentences but were not in the plan's list; leaving them out would force a second copy source.
- **Fix:** Added `ACTION_LABELS`, `UNDO_HINT`, `UNDO_TOAST`, `UNDO_TOAST_BREAKER` to `messages.py`.
- **Commit:** 841eb98a7

**3. [Rule 1 - Bug] Acceptance grep needed literal route lines**
- **Found during:** Task 3
- **Issue:** Building the routes from a shared `_BASE` made `grep -c "/tray/tickets"` print 1, below the acceptance criterion's 2.
- **Fix:** Wrote the five route paths out literally, which also suits a frozen contract.
- **Commit:** ef3c0785a

**Total deviations:** 3 auto-fixed (1 test assertion, 1 missing constants, 1 acceptance fit). **Impact:** none on scope; no architectural change.

## Authentication Gates

None.

## Known Stubs

None. No placeholder data flows to any UI; the "your company's" wording in the starters is the intentional editable placeholder required by D-36.

## Threat Flags

None. The plan added no endpoint, auth path or file access; the threat register items T-85-06 (generic requester texts), T-85-07 (no URL, email, phone or vendor in starters) and T-85-08 (contract pinned by literal tests) are covered by tests.

## User steps

None for this plan. The tray contract becomes costly to change only once the agent carrying the tray window is published, and that publish stays the user's step (later plans).

## Notes for later plans

- 85-01 creates `backend/service_desk/__init__.py` with its own copies of the 19 hand-off codes and 8 draft reasons; 85-12 tests they equal the keys of `STAFF_REASON_LABELS` and `DRAFT_REASON_TEXT`.
- The three backend modules import nothing from `service_desk/__init__.py`, so they work before and after 85-01.
- The user's uncommitted work was not touched: `backend/tickets_endpoints.py`, `components/InternalTicketsDashboard.tsx`, `shared/catalogue-gaps.json` and `agent-install/omni-agent-rs/Cargo.toml` still show their own unstaged diffs.

## Self-Check: PASSED

Created files all present on disk; commits 841eb98a7, 27ee48325 and ef3c0785a are ancestors of HEAD; all task acceptance criteria and plan-level verification commands re-run green.
