# Phase 43 — UI Review

**Audited:** 2026-07-22
**Baseline:** 43-UI-SPEC.md (design contract)
**Screenshots:** not captured (no dev server at :3000/:5173/:8080) — code-only audit

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 4/4 | All CTA/toast/label strings are exact matches to the contract, including the em-dash error toast shape |
| 2. Visuals | 3/4 | Radio tile selection state has no visible keyboard-focus indicator (native input hidden via `sr-only`) |
| 3. Color | 2/4 | Indigo accent used on the "View in Jira/ServiceNow" link inside the ticket-display block, directly contradicting the contract's "never used for the ticket-display block" rule |
| 4. Typography | 3/4 | Provider tile labels render at `text-xs` with no weight class, not the contract's declared `text-sm font-medium` Label role |
| 5. Spacing | 4/4 | `p-2` correctly used for radio tiles (not the off-scale `p-2.5` the contract explicitly warned against); no arbitrary values found |
| 6. Experience Design | 3/4 | Three-state render logic (hidden/button+picker/read-only block) and loading/error/toast states all implemented correctly; docked for the same focus-visibility gap affecting task completion via keyboard |

**Overall: 19/24**

---

## Top 3 Priority Fixes

1. **Indigo accent leaks into the ticket-display block** (`components/RemediationTaskModal.tsx:301`) — The "View in Jira"/"View in ServiceNow" outbound link uses `text-indigo-600 dark:text-indigo-400`, but the UI-SPEC's Color section is explicit: accent is "Reserved exclusively for: the Create Ticket button fill, and the selected-state border/background of the Jira/ServiceNow provider radio tile... Never used for the ticket-display block, provider badges, or icons." This dilutes the 60/30/10 accent discipline the whole modal otherwise follows. **Fix:** change the link to a neutral/underline style, e.g. `text-gray-700 dark:text-gray-300 hover:underline` (or `text-gray-600` to match the block's other text), keeping the `ExternalLinkIcon` un-tinted.

2. **Provider radio tiles have no visible keyboard focus state** (`components/RemediationTaskModal.tsx:329-336`) — The native `<input type="radio">` is `className="sr-only"`, which visually hides it including its default focus ring. A keyboard-only admin tabbing to a tile gets no visible indication of focus before pressing Space/Enter to select Jira vs ServiceNow — a real interaction gap for a required selection step (D-02). **Fix:** add a `peer` class to the input and a `peer-focus-visible:ring-2 peer-focus-visible:ring-indigo-500` (or similar) treatment on the wrapping `<label>`, matching accessible hidden-radio patterns used elsewhere if any exist, or introducing one here since this is a new interactive control.

3. **Provider tile label typography doesn't match the contract's declared Label role** (`components/RemediationTaskModal.tsx:337-339`) — UI-SPEC's Typography table declares "Label (field labels, provider names, button text)" as `text-sm` / `font-medium`. The implemented tile label is `text-xs leading-tight` with no weight class — it faithfully clones `AddCloudAccountModal.tsx`'s existing (also `text-xs`) tile-label pattern, but that means the actual UI doesn't match what the contract itself declares. **Fix:** either (a) bump the tile label to `text-sm font-medium` to match the written contract, or (b) if `text-xs` is intentionally correct (matching the closest structural analog), amend UI-SPEC.md's Typography table to state the tile-label exception explicitly, the same way the Spacing section calls out its own exceptions — leaving the contract and code in silent disagreement is the actual defect here, independent of which one wins.

---

## Detailed Findings

### Pillar 1: Copywriting (4/4)
- `showToast('Ticket created.', 'success')` (line 104) — exact match to spec.
- `showToast('Failed to create ticket — please try again.', 'error')` (line 108) — exact match, correct em-dash usage, matches the file's own existing `'AI suggestion unavailable — please try again'` shape.
- `'Create Ticket'` / `'Creating...'` (line 355) — exact match.
- `'Choose a provider'` (line 318) — exact match.
- `'View in Jira'` / `'View in ServiceNow'` (line 303) — matches spec's copy contract (the `↗` is supplied by the adjacent icon per spec, correctly not duplicated as literal text).
- `'Ticket'` / `'Ticketing'` section labels (lines 284, 313) — exact match.
- No generic "Submit"/"Click Here"/"OK" patterns introduced by this phase's new code.

### Pillar 2: Visuals (3/4)
- Three-state layout is visually consistent with the rest of the modal's field stack (`space-y-4`), no layout-breaking additions.
- Provider badge and tile styling are visually consistent with the rest of the dashboard (cloned pill/tile patterns), giving expected visual hierarchy.
- **Finding:** `sr-only` on the radio `<input>` (line 335) removes the only default focus indicator from the DOM's actually-focusable element, and no replacement focus style was added to the `<label>` wrapper — a keyboard user cannot see which tile is focused. This is the same underlying pattern already present in `AddCloudAccountModal.tsx` (not a regression introduced uniquely here), but it's still a live accessibility/visual gap being reintroduced with the same shape.
- Icon-only elements (`TicketIcon`, `ExternalLinkIcon`) are always paired with adjacent text ("Create Ticket", "View in Jira/ServiceNow"), not bare icon buttons — correctly avoids the icon-only-without-label failure mode.

### Pillar 3: Color (2/4)
- Confirmed accent (`indigo-600`/`indigo-700`) is correctly scoped to: Create Ticket button fill (line 348), selected radio-tile border/background (line 325) — matches the contract.
- **Violation:** line 301, the outbound ticket link uses `text-indigo-600 dark:text-indigo-400` inside the read-only ticket-display block. The contract lists this exact block as a location where accent must never appear. This is not a stylistic nitpick — it's a direct, checkable contradiction of the written Color contract's "reserved exclusively for" clause.
- Provider badge colors (blue Jira / green ServiceNow, lines 288-291) correctly match the contract's third semantic pair, cloned from `RemediationDashboard`'s `STATUS_COLORS` pill shape.
- No hardcoded hex/rgb values introduced (grep confirmed clean).
- Destructive-red convention untouched — no red anywhere in this phase's additions, matching the "no destructive action" contract note.

### Pillar 4: Typography (3/4)
- Section labels ("Ticketing", "Ticket") correctly use `text-sm font-medium` (lines 283, 312) matching the contract's Label role and the rest of the modal's field labels.
- Ticket reference text (`text-xs text-gray-700`, line 295) correctly matches the contract's Body role (12px / 400 regular, no weight class = regular default).
- **Finding:** provider tile labels (line 337) use `text-xs leading-tight` with no font-weight class — the contract's Typography table explicitly lists "provider names" under the Label role (`text-sm` / `font-medium`). The implementation instead cloned `AddCloudAccountModal.tsx`'s own (also under-spec) tile label exactly. Net effect: two files now share an undeclared-in-spec `text-xs` provider-name convention, and this phase's own contract document doesn't match its own code.
- Font-size distribution in the modified file: `text-lg` (1), `text-sm` (13), `text-xs` (6) — 3 distinct sizes, within reasonable bounds and matching the 2-new-weight budget the contract set (`font-medium`, pre-existing `font-semibold` on the reused badge pill).

### Pillar 5: Spacing (4/4)
- Radio tiles use `p-2` (line 324) as the contract explicitly required, correctly avoiding the off-scale `p-2.5` used by `AddCloudAccountModal.tsx`'s tiles that the spec called out by name as a Do Not Propagate exception.
- `gap-2`/`gap-1` used for icon-label pairing, consistent with the declared `sm`/`xs` tokens.
- `mt-6` on the final button row left untouched, per the contract's "carry forward unchanged" instruction.
- No arbitrary bracket-syntax spacing values (`[Npx]`/`[Nrem]`) found in the modified file.

### Pillar 6: Experience Design (3/4)
- Three-state render logic exactly matches the contract's priority order: `ticket_ref` truthy → display block only (line 281); unsaved/unconfigured → hidden (line 310's `task?.id && (hasJira || hasServiceNow)` guard); otherwise → button (+ picker only if both configured, line 315).
- Loading state clones the existing `saving`/`suggesting` spinner pattern exactly (`creatingTicket`, lines 350-351), including the same spinner markup class string.
- Failure path is fully non-blocking per D-04: catch block only shows a toast, no red border/inline error text introduced, task view remains usable (lines 106-108).
- `getTicketingConfig()` uses a safe-default try/catch (never throws), correctly preventing a config-fetch failure from crashing the modal — it silently hides the section instead, per plan.
- **Docked for the same keyboard-focus gap noted under Visuals:** for a required selection step (provider picker), an admin who cannot see which tile has focus cannot confidently complete "Choose a provider" via keyboard alone — this is an experience-design gap on top of being a visual one, since it affects actual task completion for keyboard users, not just aesthetics.

---

## Files Audited
- `components/RemediationTaskModal.tsx` (Ticketing section, `handleCreateTicket`, related state — lines 1-360)
- `services/apiService.ts` (`createTicketForRemediationTask`, `getTicketingConfig` — lines ~4535-4553)
- `types.ts` (RemediationTask `ticket_provider`/`ticket_ref`/`ticket_url` fields — referenced, not independently defective)
- `components/AddCloudAccountModal.tsx` (referenced as structural analog for the radio-tile pattern comparison)
- `components/RemediationDashboard.tsx` (referenced for the `STATUS_COLORS` pill class string comparison)
- `.planning/phases/43-remediation-to-ticketing-bridge/43-UI-SPEC.md`, `43-CONTEXT.md`, `43-04-PLAN.md`, `43-04-SUMMARY.md` (design contract and build record)

Registry audit: `components.json` not present (shadcn not initialized) — registry safety audit skipped per gate.
