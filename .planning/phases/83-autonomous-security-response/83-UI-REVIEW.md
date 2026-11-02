# Phase 83 — UI Review

**Audited:** 2026-11-02
**Baseline:** 83-UI-SPEC.md (approved)
**Screenshots:** not captured (code-only audit; no dev server permitted, UI unpublished)
**Interaction captures:** off (workflow.ui_interaction_capture is false); every interaction finding is derived from code

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Spec strings match nearly word for word; one unspecified sentence on SwarmDashboard, and a deny shows the `Refused` chip |
| 2. Visuals | 3/4 | Anatomy follows the contract; `role="status"` on a `<li>` breaks list semantics; repeated amber chips per card |
| 3. Color | 3/4 | Accent used only where declared; SwarmDashboard not-sent style has no dark variant; two 12px grays are low-contrast |
| 4. Typography | 4/4 | No off-scale sizes or weights, no `truncate`, no hex values in any audited file |
| 5. Spacing | 3/4 | Spec scale respected; 16px checkboxes are below any sensible touch target |
| 6. Experience Design | 3/4 | States are thorough; bulk retry reuses edited values, no blur validation, 409 "already made" leaves a stale chip |

**Overall: 19/24**

No BLOCKER found. Nothing breaks task completion in the code as read. All findings are WARNING.

---

## Top 3 Priority Fixes

1. **Bulk-apply retry can send different values than the first attempt** (WARNING) — after a partial failure the Super Admin can still tick, untick or edit the two groups behind the open dialog's state, and the retry sends `onlyTenants` with whatever is now staged (`AutonomousOpsResponseSettingsPlatform.tsx:99-107`, `lines` built at 88-90). Some organizations then end up with different values than others, under a dialog that says "retry the rest". Fix: freeze `body` (without `onlyTenants`) in a ref when the first attempt starts and reuse it for the retry; disable the two groups while `failedIds.length > 0`.
2. **`role="status"` set on the `<li>` of a settled action line** (WARNING) — `AutonomousOpsIncidentCard.tsx:191`. It overrides the listitem role inside a `<ul>`, so the list loses an item for screen readers exactly when a decision lands. Fix: keep `<li>` plain and put the `role="status"` on an inner `<div>` wrapping the result text, keep `tabIndex={-1}`/focus on the li.
3. **SwarmDashboard not-sent message has no dark-mode style and uses an unspecified sentence** (WARNING) — `SwarmDashboard.tsx:25-29` (`bg-amber-50 border-amber-200 text-amber-800`, no `dark:` classes) and a new static sentence at line 213 that the UI-SPEC does not word. The rest of the dashboard carries `dark:` classes (line 209). Fix: add `dark:bg-amber-400/10 dark:border-amber-400/25 dark:text-amber-200`; confirm the line 213 sentence with the spec owner or add it to section 8.

Further fixes below (items 4 to 9) are worth doing in the same pass.

4. Checkboxes are 16px (`h-4 w-4`) in `AutonomousOpsResponseSettingsPlatform.tsx:32` and `AutonomousOpsResponseSettingsDialogs.tsx:119`. Wrap in a label with `min-h-10` padding or enlarge the hit area.
5. Block-length validation fires on every keystroke, not on blur and Save as specified (`AutonomousOpsResponseSettings.tsx:245`, `Platform.tsx:84`). Clearing the field to retype shows a red `role="alert"` immediately and announces it.
6. 12px gray text on `text-gray-500`: undo hint (`AutonomousOpsRowActions.tsx:148`), decision count (`AutonomousOpsDecisions.tsx:186`), `HELPER` (`ResponseSettings.tsx:24`). Spec says "muted"; use `text-gray-600` as the rest of the file does.
7. A 409 "already made" patches only `message`, so the chip stays `Pending` until the poll (`AutonomousOpsIncidentCard.tsx:169-170`). Patch `bucket` too, or trigger the refetch result immediately.
8. `Deny` is patched to bucket `refused` (`IncidentCard.tsx:151`), so a person's own denial shows the OUTLINE `Refused` chip, which the spec reserves for "not done by design". Spec table lists no chip for denied; confirm intent.
9. After a 409 expired, focus is not moved (`IncidentCard.tsx:167-168`), while the buttons vanish; focus falls to body.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- Verified word for word against the Copywriting Contract: section line (`Decisions.tsx:188-190`), stop notices (23-25), load error (22), `Approving...`/`Denying...`/`Confirming...`/`Undoing...` labels (`IncidentCard.tsx:251,264,276`; `RowActions.tsx:146`), failure frames (`IncidentCard.tsx:172`, `RowActions.tsx:111`), expired/blocked/waiting lines (24-27), dialogs (`Dialogs.tsx:44,60,63,100,125,133`), settings helpers (`Settings.tsx:19-24,298,329-330`), validation strings (`Settings.tsx:16,54-57`), toasts.
- Fallbacks for approve, deny, confirm and undo exist. No emojis, no ASI/AGI/Autopilot/rollback terms in the files grepped.
- WARNING: `SwarmDashboard.tsx:213` adds `Propagating an antibody no longer sends anything to agents. Containment is handled in Autonomous Ops.` which is not in the contract (the plan summaries list it as an extra sentence; not verified against the banned-terms test, which I did not run).
- WARNING: `IncidentCard.tsx:151` deny result chip is `Refused` (see fix 8).
- Minor: dismiss button on SwarmDashboard is a bare `✕` glyph with `aria-label="Dismiss"` (line 224), fine for AT, inconsistent with the icon set.
- Not verified: the `Started {relative}` wording depends on `formatWhen` in `AutonomousOpsActivityList.tsx`, which I did not read.

### Pillar 2: Visuals (3/4)
- Anatomy matches section 2a: article with `aria-labelledby`, header with `ShieldAlertIcon`, host `h3`, meta, deadline chip, action lines, `Show {n} more actions` with `aria-expanded`/`aria-controls` (`IncidentCard.tsx:322-361`).
- Focal point: the section returns `null` on first load and when empty (`Decisions.tsx:158-159`), as specified.
- WARNING: `IncidentCard.tsx:191` `role="status"` on `<li>` (fix 2).
- WARNING: each waiting line repeats an identical amber chip (`IncidentCard.tsx:198-203`) next to the header chip (331-336). Spec asks for both, but on a 5-line card the focal chip is drowned. Consider showing the line chip only when it differs from the header.
- Icon-only controls: remove-service button has `aria-label` (`Settings.tsx:357`); all other icons are `aria-hidden` and paired with text.
- Switch thumb math is correct (`Settings.tsx:74-76`: 44px track, 16px thumb, `translate-x-6`).
- Not verified visually: no screenshots, so wrapping, overflow at 1280px (S3 backstop) and focus ring appearance are unconfirmed.

### Pillar 3: Color (3/4)
- Accent (`bg-primary-600`) appears in `ACCENT_BUTTON` (`Dialogs.tsx:8`) and the switch track (`Settings.tsx:74`) only; Deny, Undo, Confirm isolation, Review, Show more use SECONDARY_BUTTON or text buttons, as declared. No new tone; deadline chip reuses amber (`IncidentCard.tsx:28-30`). No hex or rgba in any of the six component files.
- WARNING: `SwarmDashboard.tsx:25-29` no `dark:` variants for the three status styles.
- WARNING: low-contrast 12px grays (fix 6).
- Count: `primary-600` and `bg-gray-50` combined hits across the six files: 4 lines; accent is not overused.
- Note: a disabled Approve uses `disabled:opacity-60`; the explanatory line is present, so meaning does not rely on opacity.

### Pillar 4: Typography (4/4)
- grep over the six component files for `font-medium|font-bold|text-base|text-xl|text-[|truncate|dangerouslySetInnerHTML` returned nothing. Only `text-xs`, `text-sm`, `text-lg` and `font-semibold`/`font-normal` appear. `tabular-nums` used on countdowns, counts, hours. `font-mono` limited to targets, ids, service names, paths.
- Caveat: SwarmDashboard is out of the type scale by design (R13).

### Pillar 5: Spacing (3/4)
- `px-6 py-4`, `gap-4`, `space-y-6`, `p-6`, `min-h-10`, `h-8 w-8`, `h-6 w-11`, `w-24` all match the declared exceptions. No arbitrary `[..px]` values.
- WARNING: checkbox hit area 16px (fix 4). Remove-chip 32px is a declared, accepted exception.
- Not verified: the 1016px column-minimum claim for the Activity table (backstop S3) needs a browser.

### Pillar 6: Experience Design (3/4)
- Strong: single in-flight guard via `sent` ref on every decision, undo, save and apply (`IncidentCard.tsx:111,140-141`; `RowActions.tsx:89,93-94`; `Settings.tsx:172`; `Platform.tsx:63`); first load silent; background failure keeps cards (`Decisions.tsx:80-82`); stop disables Approve and Confirm, not Deny (`IncidentCard.tsx:246,259,271`); shadow hides buttons (120); past deadline disables the card (183); poll replaces patches only on `poll` (`Decisions.tsx:79`); dialogs block Esc and Cancel while pending; 403 closes the form with a toast; unreadable settings show the blue defaults notice.
- WARNING: bulk retry reuses live form state (fix 1).
- WARNING: validation timing differs from spec (fix 5); an invalid field also leaves `dirty` true while Save is disabled with no hint other than the inline error.
- WARNING: 409 already-made leaves stale chip (fix 7); 409 expired loses focus (fix 9).
- Minor: `loadMore` failure in Decisions shows `LOAD_ERROR` ("Couldn't load approvals...") without a retry other than clicking Show more again (`Decisions.tsx:214`); acceptable.
- Minor: platform scope hides decisions entirely (`Activity.tsx:61`), matching the spec.

---

## Files Audited
Read in full: `components/AutonomousOpsIncidentCard.tsx`, `AutonomousOpsDecisions.tsx`, `AutonomousOpsRowActions.tsx`, `AutonomousOpsResponseSettings.tsx`, `AutonomousOpsResponseSettingsDialogs.tsx`, `AutonomousOpsResponseSettingsPlatform.tsx`, 83-UI-SPEC.md (all 529 lines).
Read in part: `AutonomousOpsActivity.tsx` (lines 56-143), `SwarmDashboard.tsx` (17-30, 90-105, 205-235), `backend/autonomous_ops/response_messages.py` (75-100 plus greps).
Grepped only: `AutonomousOpsActivityList.tsx`, `AutonomousOpsHealthCards.tsx` (SECONDARY_BUTTON), `shared/autonomous-ops-banned-terms.json`.

## Not read
83-CONTEXT.md, all seven PLAN.md and SUMMARY.md files, `services/autonomousOpsApi.ts`, `services/autonomousOpsIncidentsApi.ts`, `AutonomousOpsActivityList.tsx` body (StateChip, formatWhen, resultFor), `AutonomousOpsHealthChips.tsx` (HealthNotice, role handling), `Modal.tsx`, the rest of `response_messages.py`, and App.tsx wiring of `onOpenView`. No tests, builds or live site were run or fetched. Registry audit skipped: no `components.json`.
