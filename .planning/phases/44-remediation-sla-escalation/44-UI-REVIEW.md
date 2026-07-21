# Phase 44 — UI Review

**Audited:** 2026-07-22
**Baseline:** 44-UI-SPEC.md (approved design contract)
**Screenshots:** not captured (no dev server detected on :3000/:5173/:8080 — code-only audit)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Spec-exact strings render correctly, but the retry-error copy is hardcoded in JSX while a separate, differently-worded `error` state string is set and never displayed — dead/misleading state. |
| 2. Visuals | 4/4 | SLA badge and escalation panel are structurally identical clones of pre-existing, reviewed patterns (STATUS_COLORS badge, ChainOfCustodyPanel); toggle affordance has aria-label + keyboard handler. |
| 3. Color | 4/4 | Accent (indigo) confirmed absent from both new elements; SLA_COLORS map matches spec's four-state mapping byte-for-byte, including the `none` neutral fallback. |
| 4. Typography | 4/4 | New elements use exactly the 2 contracted weights (font-semibold, font-normal) and 2 sizes (text-xs, text-sm) — no font-medium/font-bold introduced into the new panel or badge. |
| 5. Spacing | 3/4 | Badge padding (`px-2 py-0.5`) and panel spacing (`px-4 py-2/py-3`, `mt-4`, `gap-1.5`) match the declared scale/exception, but no automated verification was possible for computed pixel rendering (code-only audit, not visually confirmed by this pass). |
| 6. Experience Design | 3/4 | Loading/error/empty/populated states all present and match spec copy; but the escalation panel silently swallows fetch errors into a UI string that's never rendered, meaning any real backend error currently displays generic hardcoded text with no diagnostic path back to the actual failure. |

**Overall: 21/24**

---

## Top 3 Priority Fixes

1. **Dead `error` state string in `EscalationHistoryPanel.tsx`** — User impact: if the escalation-history fetch fails for a reason other than the generic case, the user sees identical boilerplate copy regardless of cause, and the app has no way to ever surface a more specific message since the caught value is discarded. Fix: either render `{error}` in the JSX (line ~94-96) instead of the hardcoded literal, or remove the `setError('Failed to load escalation history')` call and keep the hardcoded spec copy consistently, so there is a single source of truth for the message (`components/EscalationHistoryPanel.tsx:54,95`).
2. **No automated visual confirmation of computed spacing/color rendering** — User impact: pillar 3/5 findings are class-name-level, not rendered-pixel-level, since no dev server was running for this audit; a class name conflict (e.g. dark-mode contrast) would not be caught by this pass. Fix: re-run this audit with a dev server up (`npm run dev` on :3000/:5173) and capture desktop/tablet/mobile screenshots of the dashboard table and an expanded escalation panel before shipping to production.
3. **Discretionary Settings surface (At-Risk Window field) was not built** — User impact: none currently, since the spec explicitly marked it discretionary and pending planner confirmation, and no plan/summary claims it as delivered — but if a compliance admin now expects to configure the at-risk threshold via UI (the backend `GET/PATCH /api/settings/remediation-sla` endpoint from 44-03 exists and is fully wired server-side with no UI consumer), this is an orphaned API surface. Fix: confirm with product whether this was intentionally deferred to a later phase, and if so, note it in ROADMAP/backlog rather than leaving it silently unaddressed.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- `components/EscalationHistoryPanel.tsx:99-101` — empty state `No escalations recorded for this task.` matches spec exactly, single line, italic, `text-xs text-gray-400 italic` — pass.
- `components/EscalationHistoryPanel.tsx:95` — rendered error copy `Failed to load escalation history. Retry by collapsing and expanding this panel.` matches spec's exact contracted phrasing — pass.
- `components/EscalationHistoryPanel.tsx:54` — however, the `catch` block sets `error` to the shorter, different string `'Failed to load escalation history'` (no second sentence), and this state value is **never read or rendered anywhere** in the component (the JSX at line 95 uses a hardcoded literal, not `{error}`). This is dead code that also means the component cannot ever differentiate error causes in copy — a genuine (if currently invisible) contract-adjacent defect.
- `components/EscalationHistoryPanel.tsx:74` panel header `Escalation History` with live `({entries.length} events)` suffix — matches spec's CoC-derived pattern exactly.
- `components/EscalationHistoryPanel.tsx:114` meta line `{formatted timestamp} UTC · Notified: {recipient summary}` — matches spec shape; `summarizeNotified()` joins the resolved recipient list, degrading gracefully to `'none'` when the list is empty (spec did not explicitly define this fallback string, but it is a reasonable, non-blank default consistent with the neutral-fallback pattern used elsewhere in this phase).
- No generic `Submit`/`Click Here`/`OK` labels found in either new file.

### Pillar 2: Visuals (4/4)
- Toggle header (`EscalationHistoryPanel.tsx:64-81`) has `role="button"`, `tabIndex={0}`, `onKeyDown` Enter/Space handling, and a state-dependent `aria-label` — full keyboard/screen-reader parity with the icon-only chevron affordance.
- SLA badge column sits between Status and Actions exactly as specified (`RemediationDashboard.tsx:171`), giving clear visual grouping of the two status signals without introducing a new column pattern.
- Visual hierarchy in the panel: header (`text-sm font-semibold`) > entry actor line (`text-xs font-semibold`) > meta line (`text-xs font-normal text-gray-400`) — three-tier size/weight/color hierarchy matches the spec's Body/Label/Heading role table precisely.
- `AlertTriangleIcon` entry marker consistently colored `text-yellow-600 dark:text-yellow-400`, distinct from the SLA badge's red/yellow/green semantics — no confusing color overlap between the two signal systems.

### Pillar 3: Color (4/4)
- `grep -n "indigo\|text-primary\|bg-primary" components/EscalationHistoryPanel.tsx` — zero matches; accent color correctly absent from the read-only panel, matching the spec's explicit "reserved for CTAs only" rule.
- `SLA_COLORS` map (`RemediationDashboard.tsx:16-21`) matches all four spec-declared states (`ok`/`at_risk`/`breached`/`none`) with identical light/dark class pairs to their `STATUS_COLORS` equivalents (`resolved`/`in_progress`/`open`/`dismissed` respectively) — exact clone as contracted.
- No hardcoded hex/rgb colors introduced in either new file (`RemediationDashboard.tsx`, `EscalationHistoryPanel.tsx`) — all color via Tailwind utility classes.
- Neutral fallback (`SLA_COLORS.none`, gray) is applied via `task.sla_status ?? 'none'` double-guarded with `?? SLA_COLORS.none` (`RemediationDashboard.tsx:205`) — never renders undefined/blank per the spec's explicit anti-crash requirement.

### Pillar 4: Typography (4/4)
- New-file font-weight audit: `EscalationHistoryPanel.tsx` uses only `font-semibold` (lines 72, 110) and `font-normal` (line 75) — exactly the 2 weights the spec contracts for these new elements, no `font-medium`/`font-bold` introduced.
- Size audit: `text-sm` (header, line 72) and `text-xs` (all other new text, lines 75/94/99/110/113) — matches the spec's Heading=14px/Body+Label=12px role table exactly.
- Pre-existing `font-bold`/`font-medium` usages in `RemediationDashboard.tsx` (lines 102, 105, 115, 129, 141, 158, 160, 185, 213, 220) are all outside this phase's scope (page title, existing buttons) — consistent with the spec's explicit "these are out of scope and unchanged" carve-out.

### Pillar 5: Spacing (3/4)
- Badge padding `px-2 py-0.5` (`RemediationDashboard.tsx:205`) matches the spec's declared accepted exception verbatim.
- Panel spacing: `px-4 py-2` (toggle bar), `px-4 py-3` (entries), `mt-4` (panel top margin), `gap-1.5`/`gap-2` (icon-to-text) — all match the declared xs/sm/md/lg scale.
- No arbitrary bracket values (`grep "\[.*px\]\|\[.*rem\]"`) found in either new file.
- Deduction: this audit is code-only (no dev server available), so computed/rendered spacing — e.g. whether dark-mode border colors create visible misalignment, or whether the badge wraps awkwardly at narrow viewport widths — could not be visually confirmed. Class-name compliance is verified; rendered-pixel compliance is not.

### Pillar 6: Experience Design (3/4)
- Loading state: spinner SVG present (`EscalationHistoryPanel.tsx:86-91`), gated on `loading` boolean — matches CoC's identical pattern.
- Error state: renders correctly (see Pillar 1 finding on the dead `error` variable) — the user-facing text is currently correct only because of a hardcoded literal, not because the caught error is read; this is fragile and will silently regress if a future edit "fixes" the error string in one place but not the other.
- Empty state: present, single line, matches spec.
- Populated state: entries render with icon, tier label, timestamp, and notified-recipients summary — full coverage of the spec's required meta line, with a safe `'none'` fallback when `notified` is empty.
- No destructive controls of any kind in the panel (`grep -ni "delete|remove|confirm"` — confirmed clean per plan's own verification and independently re-confirmed here) — correctly honors the SLA-02 immutability contract.
- Fetch is properly lazy (fires only on first expand via `!fetched` guard), avoiding an unnecessary network call for tasks whose panel is never opened.
- Render guard `task?.id &&` (`RemediationTaskModal.tsx:363`) correctly suppresses the panel in create mode, matching spec.

---

## Registry Safety

Registry audit skipped — `components.json` not present in repo root (project confirmed hand-rolled Tailwind, no shadcn, per UI-SPEC.md's own Design System section). No third-party registry blocks to check.

---

## Files Audited
- `components/RemediationDashboard.tsx`
- `components/RemediationTaskModal.tsx`
- `components/EscalationHistoryPanel.tsx` (new)
- `components/ChainOfCustodyPanel.tsx` (reference clone source)
- `components/icons.tsx` (icon export verification)
- `.planning/phases/44-remediation-sla-escalation/44-UI-SPEC.md`
- `.planning/phases/44-remediation-sla-escalation/44-01-SUMMARY.md` through `44-04-SUMMARY.md`
