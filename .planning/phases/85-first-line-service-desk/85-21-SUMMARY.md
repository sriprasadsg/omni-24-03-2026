---
phase: 85-first-line-service-desk
plan: 21
subsystem: service-desk-ui
tags: [service-desk, knowledge-base, help-desk-mark, starter-articles, knowledge-gaps, article-dialog]
status: complete

requires: [85-02, 85-15]
provides:
  - "services/serviceDesk/knowledgeApi.ts: fetchArticle, patchArticle, createArticle, fetchStarterStatus, addStarters, fetchGaps, dismissGap, restoreGap (each JSDoc-ed with route and permission), DEFAULT_ARTICLE_MAX"
  - "components/serviceDesk/HelpDeskToggle.tsx: HelpDeskToggle (non-optimistic On/Off switch), HelpDeskChips, SharedReferenceLine, EditArticleButton"
  - "components/serviceDesk/ArticleEditDialog.tsx: Edit article and Write article (create mode for a gap)"
  - "components/serviceDesk/StarterArticlesDialog.tsx: Add starter IT articles? with the singular, plural and none toasts"
  - "components/serviceDesk/KnowledgeGapsTab.tsx: the Knowledge gaps tab"
  - "KnowledgeBaseDashboard.tsx (233 to 361 lines): KBDoc fields, flags state, readiness note, amber no-articles block, header button, Help desk pill, row controls, the fourth tab and both dialogs"
  - "backend GET /api/knowledge/docs/{doc_id} (manage:ai_risks): one of the tenant's own articles with its text and the server's character limit (added because the list leaves the text out)"
affects: [85-22]

actuals:
  tokens: 22336
  tasks: 3
  commits: 8
plan_head_before: 0f8fd2ee3d04f2c045b6c24853f76e08e314a17c
plan_head_after: cf9aef6665fe688a6b629bae048bd2c84bde7bb0

tech-stack:
  added: []
  patterns:
    - "Controls render from the server's list flags (canManageArticles, canSeeGaps, starterMissing, deskOff, helpdeskCount); the client never works out who may act"
    - "Non-optimistic writes: the switch keeps the stored value and is disabled while its one request runs; the article dialog sends only the changed keys"
    - "Gap list read once for the tab count on mount (without dismissed), then once per tab open or Try again or closed gap (with dismissed); dismissed groups filtered client-side by status; never polled"
    - "One failure-wording helper (failureLine) turns a server message or its absence into the contract's red line, and a bare 403 into the platform-organization words"

key-files:
  created:
    - services/serviceDesk/knowledgeApi.ts
    - components/serviceDesk/HelpDeskToggle.tsx
    - components/serviceDesk/ArticleEditDialog.tsx
    - components/serviceDesk/StarterArticlesDialog.tsx
    - components/serviceDesk/KnowledgeGapsTab.tsx
    - src/__tests__/ServiceDeskKnowledgeBase.test.tsx
    - src/__tests__/ServiceDeskKnowledgeGaps.test.tsx
    - src/__tests__/_serviceDeskKnowledgeHarness.tsx
  modified:
    - components/KnowledgeBaseDashboard.tsx
    - components/serviceDesk/deskUi.tsx
    - components/serviceDesk/serviceDeskCopy.ts
    - backend/knowledge_helpdesk_endpoints.py
    - backend/tests/test_service_desk_knowledge.py

key-decisions:
  - "Edit article reads the stored text through a new GET /api/knowledge/docs/{id}: the list excludes content and 85-15 built no read route, so the dialog could not have shown or kept the text without it"
  - "Save article is disabled in edit mode until something changed, and sends only the changed keys; create mode always allows Save and validates on press"
  - "The gap list is read with dismissed=true when the tab opens and filtered by status on the client; Show dismissed lists open and dismissed groups together, each dismissed one wearing a Dismissed chip so state is not colour alone"
  - "Ticket numbers on a gap card are mono text, or links when the screen is given an opener; KnowledgeBaseDashboard has no opener (App.tsx carries user changes and is not edited), so they render as text for now"
  - "The character limit comes from the server (max on the new GET) and falls back to 20,000 for a new article"

requirements-completed: []

coverage:
  - id: D1
    description: "Each tenant article row carries a non-optimistic Help desk switch (On/Off words, aria-label naming the title) that sends one PATCH, is disabled while pending, toasts the title and moves the Help desk (k) count; a failure shows the inline red line and keeps the old state; platform articles show the Platform reference chip and the shared-reference line with no switch and no edit"
    requirement: "DESK-06"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskKnowledgeBase.test.tsx#the Help desk switch"
        status: pass
      - kind: unit
        ref: "src/__tests__/ServiceDeskKnowledgeBase.test.tsx#document rows"
        status: pass
    human_judgment: false
  - id: D2
    description: "Readiness note (singular and plural), the amber no-articles block when the desk is on and nothing is marked, the Help desk (k) filter pill, and no desk controls for someone who cannot manage articles"
    requirement: "DESK-06"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskKnowledgeBase.test.tsx#the Help desk filter and the readiness note"
        status: pass
    human_judgment: false
  - id: D3
    description: "Add starter IT articles: header button or Starter IT articles added, a confirmation dialog with Close without adding first, one POST, Adding..., singular, plural and none toasts, a red failure block, list and flags read again"
    requirement: "DESK-07"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskKnowledgeBase.test.tsx#Add starter IT articles"
        status: pass
    human_judgment: false
  - id: D4
    description: "Edit article and Write article: stored text loaded, counter from the server limit, plain-word validation, only changed keys sent, blue starter-copy block, Help desk checkbox with the no-secrets helper, Close without saving discards, write-from-gap pre-fills the title and ticks Help desk and its save closes the gap"
    requirement: "DESK-06"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskKnowledgeBase.test.tsx#Edit article"
        status: pass
      - kind: unit
        ref: "src/__tests__/ServiceDeskKnowledgeBase.test.tsx#Write article (create mode)"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_knowledge.py#test_one_of_the_tenants_own_articles_can_be_read_with_its_text"
        status: pass
    human_judgment: false
  - id: D5
    description: "Knowledge gaps tab only with canSeeGaps, amber while groups are open, grouped cards with ticket numbers, paging, dismiss, restore, write article, other-language line, footnote, skeleton, two empty states and the error block"
    requirement: "DESK-06"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskKnowledgeGaps.test.tsx"
        status: pass
    human_judgment: false
  - id: D6
    description: "How the new controls look and feel in light and dark Spatial Glass on the real screen (chip anatomy, spacing, the amber tab, the dialogs)"
    requirement: "DESK-06"
    human_judgment: true
    rationale: "No test asserts visual adequacy and the UI is not published; a person has to look at it in both themes"

duration: 25 min
completed: 2026-11-09
---

# Phase 85 Plan 21: Knowledge Base desk authoring screen Summary

**The Knowledge Base screen now lets authors switch the Help desk mark per article (tenant articles only), see which articles the desk may quote, add the four starter articles once, edit or write an article in a dialog that says what the mark means, and work through a Knowledge gaps tab that appears only for people with ticket and Knowledge Base access.**

## Performance

- **Duration:** about 25 min
- **Completed:** 2026-11-09
- **Tasks:** 3 (plus one backend prerequisite), 8 commits: RED then GREEN each
- **Files:** 13 (8 created, 5 modified)

## Accomplishments

- Help desk switch and chips (D-16, D-17): a role switch with On and Off words saves once, is disabled while pending, toasts the title and moves the Help desk (k) pill count; platform rows show Platform reference and the shared-reference line with no switch and no edit.
- Add starter IT articles (D-28, DESK-07): a confirmation dialog, one request, toasts for 4, 1 and 0 added, the button replaced by Starter IT articles added once none is missing.
- Article dialog: Edit article and Write article with validation in plain words, a counter from the server limit, the Help desk checkbox and its helper that warns against secrets (T-85-79), the blue starter-copy block.
- Knowledge gaps tab (D-26, D-27): only with `canSeeGaps`, amber count in the tab, group cards with Write article and Dismiss gap, Restore gap in the dismissed view, ten groups then Show more gaps, first three tickets then Show all, other-language line, footnote, three-skeleton loading, both empty states, error with Try again; no polling.
- Verification: the three plan commands, then the whole UI suite (116 files, 1,840 passing, up from 1,793), `tsc --noEmit` clean, eslint clean on the touched files, `npm run build` to dist-new succeeds (nothing published), and 107 backend tests (knowledge, gaps, catalogue parity, route auth baseline) on a private mongod at port 27998.

## Task Commits

0. **Backend prerequisite: read one article with its text** - `bac84f8b8` (test, RED: 405 on the planned route), `0b6a3497a` (feat)
1. **Task 1: Help desk switch, chips, filter and readiness note** - `1e1ebede5` (test, RED: 12 of 15 failed on the planned assertions), `16e02839a` (feat)
2. **Task 2: Article dialog and Add starter IT articles** - `37a9c6a87` (test, RED: 15 of 16 new tests failed), `c2567f45d` (feat)
3. **Task 3: Knowledge gaps tab** - `239b178f9` (test, RED: 15 of 16 failed), `cf9aef666` (feat)

**Plan metadata:** the docs commit that follows this file.

## TDD Gate Compliance

RED and GREEN commits exist for every task (no REFACTOR commit was needed). `workflow.tdd_mode` is false, so the machine RED-evidence classifier was not required. Semantic assessment of each RED: the target tests ran and failed on assertions about the planned behavior (no switch, chips, pill, header button, dialog, tab or route in the screen yet), not on import or syntax faults. To keep RED from failing at import time, the RED commits carried supporting files that are not the behavior under test: the client calls, shared copy and failure helper (Task 1), an empty-props `ArticleEditDialog` skeleton (Task 2), and a few extra gap words with a relative-time helper (Task 3). One slip: in Task 1 the client-call tests (`knowledgeApi`) passed at RED because the client file was written before its tests; they are plain request-shape checks and the behavior tests around them failed as planned.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2/3 - Missing critical, blocking] No route returned an article's text for the Edit dialog**
- **Found during:** Task 2 (reading the screen's list route)
- **Issue:** `GET /api/knowledge/docs` projects out `content`, and 85-15 built PATCH but no read route, so Edit article could neither show the text nor let the author keep it. The plan's files are all front end.
- **Fix:** added `GET /api/knowledge/docs/{doc_id}` to `backend/knowledge_helpdesk_endpoints.py` (manage:ai_risks, the caller's own articles only, 404 for a platform or foreign article like PATCH, with `max` set to the server limit) and two tests, one added to the inherited-guard route list. It adds a route to an existing router and no table or service.
- **Files modified:** backend/knowledge_helpdesk_endpoints.py, backend/tests/test_service_desk_knowledge.py
- **Commits:** bac84f8b8, 0b6a3497a
- **Needs the user:** the backend restart the user schedules; until then Edit article answers its load-failure block.

**2. [Rule 2 - Missing critical] Copy the contract leaves out**
- **Issue:** the UI-SPEC has no words for the singular readiness line, the one-article starter toast, an empty Help desk filter, the article load error, the failed gap action, the Dismissed chip, Restoring..., the one-ticket forms or the platform refusal.
- **Fix:** added to `serviceDeskCopy.ts` in the contract's style (`readinessOne`, `startersAddedOne`, `filterHelpDeskEmpty`, `articleLoadFailed`, `actionFailed`, `chipDismissed`, `restoring`, `countOne`, `otherLanguageOne`, `platformRefused` and fallbacks). The plan's singular wordings ("1 article is marked Help desk." and "Added 1 starter article.") are their openings.
- **Commits:** 1e1ebede5, 239b178f9

**3. [Rule 3 - Blocking, CLAUDE.md 500-line cap] Tests split over two files and a harness**
- **Issue:** one test file for all three tasks would pass 650 lines.
- **Fix:** `ServiceDeskKnowledgeBase.test.tsx` (434), `ServiceDeskKnowledgeGaps.test.tsx` (247) and the shared `_serviceDeskKnowledgeHarness.tsx` (62). The plan's verify command for Task 3 names only the first file; the final run included both.

**4. [Plan wording] Edit article button arrives with Task 2, not Task 1**
- Task 1's behavior text mentions Edit article on each row, but its dialog is Task 2; the button shipped with its dialog so no commit holds a dead button.

**Total deviations:** 4 (1 missing-critical/blocking backend route, 1 missing copy, 1 file split, 1 ordering). **Impact:** the backend route needs the user's restart; nothing else changes the plan's contract.

## Issues Encountered

- A private mongod was already listening on 127.0.0.1:27998 from an earlier run, so the backend tests used it (throwaway test databases only); no new mongod was started.
- Pre-existing deletions and edits in the working tree (dist-test, test_dir, App.tsx, tickets code and others) are the user's and were not touched or staged.

## Known Stubs

None. One deliberate fallback: gap ticket numbers render as mono text, not links, because `KnowledgeBaseDashboard` receives no ticket opener and `App.tsx` (user changes, off limits) is where one would be wired. `KnowledgeGapsTab` already takes an optional `onOpenTicket`; when the screen is given one, the numbers become links with the "Open ticket {number}" name.

## Threat Flags

None beyond the plan's register. T-85-78 (the tab renders only with `canSeeGaps`, covered by a test that also checks no gaps request is made without it) and T-85-79 (the Help desk helper text tells authors not to put secrets in an article) are mitigated. The one new route is behind the same Knowledge Base guard and tenant scoping as the edit route and is in the guard test.

## User Setup Required

None done by me. Nothing was restarted, published, pushed or written to the live database. For this screen to work live the user restarts the backend (the new GET route; the 85-15 routes and the `one_starter_copy` index from 85-17 are also needed) and publishes the UI (`dist-new` builds clean).

## Next Phase Readiness

85-22 can rely on the Knowledge Base screen being complete; the tray and any remaining wiring are its own plan.

## Self-Check: PASSED

- Files exist: the five components and client, the two test files and the harness.
- Commits are ancestors of HEAD: bac84f8b8, 0b6a3497a, 1e1ebede5, 16e02839a, 37a9c6a87, c2567f45d, 239b178f9, cf9aef666 (8 commits measured from the ledger).
- Acceptance greps: HelpDeskToggle 2, `/knowledge/helpdesk` in the client 12, ArticleEditDialog or StarterArticlesDialog 5, KnowledgeGapsTab 2; the dashboard is 361 lines and the gaps tab 213; the toast test asserts the singular and plural.
- Final runs: vitest 116 files and 1,840 tests passing, tsc clean, eslint clean, build ok, backend 107 passed.
- The user's uncommitted work (App.tsx, InternalTicketsDashboard.tsx, tickets_endpoints.py, catalogue-gaps.json and the rest) was not touched or staged.
