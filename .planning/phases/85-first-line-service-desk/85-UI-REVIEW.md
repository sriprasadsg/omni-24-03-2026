# Phase 85 — UI Review

**Audited:** 2026-11-09
**Baseline:** 85-UI-SPEC.md (approved, R1..R14)
**Screenshots:** not captured (no dev server on 3000, 5173 or 8080; UI unpublished). Code-only audit.
**Interaction captures:** off (workflow.ui_interaction_capture is false)

Not scored, per orchestrator: the user's uncommitted work in InternalTicketsDashboard.tsx and App.tsx. Light/dark, 320 px wrapping and 150% tray scaling are not verified here (need a browser/Windows).

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Single-source copy module, no banned terms or generic labels; copy not verified in a rendered view |
| 2. Visuals | 3/4 | Anatomy matches spec; mode radios have no visible keyboard focus |
| 3. Color | 3/4 | Tokens only, no hex; HelpDeskToggle has no dark: classes of its own; status colour is yellow, spec says amber |
| 4. Typography | 4/4 | Only text-xs/sm/lg and font-semibold; no font-medium/bold |
| 5. Spacing | 3/4 | No arbitrary values; two gap-3 (12px) off the 4/8/16/24 scale |
| 6. Experience Design | 3/4 | State coverage present; unverified live; one keyboard-focus gap |

**Overall: 19/24** (code-only; visual scores are capped at 3 because nothing was rendered)

## Top 3 Priority Fixes

1. **Mode radios have no visible focus** — `components/serviceDesk/DeskModeGroup.tsx:49` hides the native radio with `sr-only`, and the wrapping label (line 38) has no `focus-within`/`has-[:focus-visible]` ring. The global `:focus-visible` rule (`index.css:131`) lands on a 1px clipped input, so a keyboard user cannot see which of Off / Drafts only / Post answers is focused, on the control that can turn on posting to requesters. Fix: add `has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-primary-600` (or `focus-within:`) to the label. (WARNING; a WCAG 2.4.7 failure on a consequential control.)
2. **Off-scale spacing** — `RequesterAnswerPanel.tsx:132` and `:149` use `gap-3` (12px); the contract allows 4/8/16/24/32/48 and says "no half-steps". Change to `gap-2` or `gap-4`. (WARNING)
3. **Waiting-on-customer status colour** — `InternalTicketsDashboard.tsx:74` uses `yellow-*` for `pending_customer`; the spec asks for amber-style classes consistent with `in_progress`. Align the classes so the new status does not add a fourth yellow/amber tone. (WARNING, minor)

Minor: `KnowledgeGapsTab.tsx:124` builds loading skeletons from `card h-24 animate-pulse` where the card and tab elsewhere use `HEALTH_SKELETON` (`DeskSettingsCard.tsx:255`, `:272`); use the shared skeleton for consistent reduced-motion behaviour. `HelpDeskToggle.tsx` has 0 `dark:` classes of its own (it relies on `OnOffSwitch` and `ERROR_LINE`, which carry them), so confirm in a dark render.

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- All fixed labels live in `components/serviceDesk/serviceDeskCopy.ts` (420 lines), shared by portal, tests and copy gate, as the spec asks.
- Grep of `components/serviceDesk` and `services/serviceDesk` for ASI/AGI/Autopilot/"fully autonomous"/"rolled back": 0 hits.
- Generic labels (Submit, OK, Click here): none; CTA labels are specific (`Send as is`, `Edit and send`, `Discard draft`, `This fixed it`, `I still need help`).
- Gap: error, empty and 409 strings were checked by pattern only, not exercised.
- Tray: labels in `agent-install/omni-agent-rs/scripts/tray_my_tickets.ps1` use the spec strings (`My tickets`, `My tickets ({0} new)`, `This fixed it`, `I still need help`, `Refresh tickets`, `Close`).

### Pillar 2: Visuals (3/4)
- Focal point follows the contract: `TicketDraftPanel` / `RequesterAnswerPanel` mounted above the tabs in `InternalTicketsDashboard.tsx:1064-1066`; the `Draft waiting` chip appears in the detail header (`:1051`) and the list row (`:916`, suppressed for the reporter).
- Icon-only controls carry labels (word-remove button `DeskWords.tsx:85` is `h-8 w-8`, as specified; `EditArticleButton` has an aria-label).
- Chips follow the 81 anatomy: 12px `aria-hidden` icon plus text (`deskUi.tsx:15-26`).
- Defect: radio focus (Fix 1).
- Tray window: every control position and size in `tray_my_tickets.ps1:273-354` matches section 8 exactly (800x560, list 292x400, buttons at 320/440/580/688,464, feedback 12,500 764x40). 4 px grid holds. Real-scaling check pending.

### Pillar 3: Color (3/4)
- Hex/rgb literals in `components/serviceDesk`: 0. Accent buttons all route through `ACCENT_BUTTON` (`bg-primary-600`); red only in `RED_BUTTON` (`deskUi.tsx:39`) used for `Discard draft`, matching the one-red-confirm rule.
- Accent use stays within the five declared items: ACCENT_BUTTON appears at `TicketDraftPanel.tsx:229,236`, `RequesterAnswerPanel.tsx:152`, `DeskSettingsCard.tsx:326` (only when dirty), `DeskDialogs.tsx:44,82`, `StarterArticlesDialog.tsx:56`. `ArticleEditDialog` uses the secondary button as specified.
- `dark:` classes are present on every file except `HelpDeskToggle.tsx` (see minor note above).
- Yellow vs amber: Fix 3.

### Pillar 4: Typography (4/4)
- Sizes in use: `text-xs`, `text-sm`, `text-lg` only (18px at `DeskSettingsCard.tsx:245`, `KnowledgeGapsTab.tsx:105`). Weights: `font-semibold` only. No `font-medium`/`font-bold`/`text-base`/`text-xl`.

### Pillar 5: Spacing (3/4)
- No arbitrary `[..px]` values. Half-step classes: none. Off-scale: `gap-3` at `RequesterAnswerPanel.tsx:132,149`. `px-3` at `DeskWords.tsx:8` is the specified word-chip/input padding and is acceptable.
- Consequential controls are `min-h-10` through the shared button constants; the mode cards, reply rows, cited-article buttons and checkbox row carry `min-h-10`.
- `TEXT_BUTTON` is `min-h-8` (32px) for Try again / Back to answer; the spec names no 40px rule for these, so this is noted, not scored.

### Pillar 6: Experience Design (3/4)
- State coverage exists for loading (`aria-busy`, skeletons), error (`role="alert"`, `failureLine` with fallback), pending labels, one-request-per-click and non-optimistic toggle (`HelpDeskToggle.tsx:38-52`). `pending_customer` is added to the status map and the Kanban and filter lists (`InternalTicketsDashboard.tsx:74,728,809`), closing R2.
- Focus management: result and notice targets receive focus (`TicketDraftPanel.tsx:73-74`, `RequesterAnswerPanel.tsx:68-71`).
- Defect: the radio focus issue (Fix 1). Nothing was driven in a browser, so mode-change dialog flow, breaker state and Undo focus return are code-read only.
- No shadcn registry; registry audit not applicable.

## Files Audited
components/serviceDesk/* (all 14 files), services/serviceDesk/*, components/AutonomousOpsActivity.tsx, components/AutonomousOpsRowActions.tsx, components/KnowledgeBaseDashboard.tsx, components/InternalTicketsDashboard.tsx (mount points only), agent-install/omni-agent-rs/scripts/tray_my_tickets.ps1 (layout; tray_icon.ps1 not read), index.css (focus rule). UI-SPEC read to line 372 of 609 (sections 1-7 and the start of 8); the Copywriting Contract and later sections were not re-read, so copy was checked against banned terms and spec strings seen above, not exhaustively.
