# Phase 23 — UI Review

**Audited:** 2026-07-06
**Baseline:** abstract 6-pillar standards (no UI-SPEC.md exists for this phase)
**Screenshots:** not captured (no dev server detected on :3000, :5173, :8080 — code-only audit)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Emoji-prefixed status strings mixed inconsistently into plain-text labels (`🔄`, `⏳`, `✅`, `❌`) |
| 2. Visuals | 3/4 | Three install steps share identical h4 styling with no visual distinction of recommended/primary path |
| 3. Color | 3/4 | 5 distinct semantic accent colors (blue/red/amber/green/purple) across two files with no documented system |
| 4. Typography | 4/4 | Only 2 sizes (text-sm/text-xs) and 2 weights (font-medium/font-semibold) in new component |
| 5. Spacing | 4/4 | All spacing values on Tailwind's standard scale; no arbitrary `[px]`/`[rem]` values found |
| 6. Experience Design | 3/4 | Build flow has loading/error/success states, but no retry affordance beyond re-clicking, and poll loop has no visible progress indicator |

**Overall: 20/24**

---

## Top 3 Priority Fixes

1. **Emoji used as sole status indicator inside translated/localizable strings** (`components/WindowsInstallTab.tsx:147,151,163`) — Screen readers announce raw emoji glyphs, and the emoji-in-string pattern breaks if the app is ever localized or themed. Fix: move icons to actual `<svg>`/icon components adjacent to text (as already done for the copy-button check/copy icons), and keep string content emoji-free.

2. **No indeterminate progress/step feedback during the 30s build poll** (`components/WindowsInstallTab.tsx:79-134`) — user sees only a static "Building installer… this may take 15–30s" text with no spinner or progress bar for up to 30 seconds; on slower networks this reads as a frozen UI. Fix: add a `Spinner`/animated indicator tied to `buildState === 'building'`, and disable/gray the whole card (not just the button) to signal a blocking operation.

3. **Three install steps are visually undifferentiated** (`components/WindowsInstallTab.tsx:176-198`) — Step 1 (primary/recommended), Step 2 (dependent on Step 1), and Step 3 (standalone alternative) all render as identical `h4` + `CodeBlock` blocks with no visual cue signaling that Step 3 is an alternative path to Steps 1+2, risking users running both flows redundantly. Fix: add a "or" divider/visual break before Step 3, or badge it "Alternative" to distinguish it from the sequential Steps 1-2.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- `WindowsInstallTab.tsx:147` — `🔄 Building installer with Spyglass evidence collection… this may take 15–30s` — emoji glued to sentence start, inconsistent with the rest of the app's text-only labeling (checked against `AssetComplianceList.tsx` badges which use plain text "Automated"/"Manual"/"PS").
- `WindowsInstallTab.tsx:151` — `❌ {buildError}` — raw server error text (`err.detail || HTTP ${status}`) surfaced directly to user with no rewritten user-facing copy; a raw HTTP status code like "HTTP 500" is not actionable copy.
- `WindowsInstallTab.tsx:163` — button label toggles between `⏳ Building…`, `✅ Download .exe`, and plain `Download .exe` — three different visual treatments for one CTA is inconsistent; standard pattern is one stable label + a separate status region.
- Step headings ("Step 1 — Install Agent Service", "Step 2 — Collect Evidence Now (runs immediately after service install)", "Step 3 — Standalone Evidence Collection (no service install needed)") are clear and specific — a genuine strength, no generic "Submit"/"Click Here" patterns found via grep.
- No empty-state copy needed here (static instructional content), so no empty-state check applies.

### Pillar 2: Visuals (3/4)
- Icon-only copy button (`CodeBlock`, line 21-31) has `aria-label="Copy command"` — correctly accessible.
- EXE download card provides a clear focal point at the top of the tab (blue banner, `DownloadIcon`).
- No visual hierarchy differentiates the 3 sequential steps from each other beyond numbering text — same font size/weight for all three `h4` headers (line 178, 186, 194), same `CodeBlock` treatment. A user skimming has no way to tell Step 3 is a standalone alternative rather than a required Step 4.
- Non-Windows fallback card (line 167-173) correctly greys out to signal unavailability — good state differentiation.

### Pillar 3: Color (3/4)
- `WindowsInstallTab.tsx` alone uses gray (13 shades), blue (10 instances — decorative border/bg/text), red (2), amber/yellow (2), green (1) — reasonable semantic mapping (blue=info/primary, amber=warning, red=error, green=success) but no single documented accent; combined with `AssetComplianceList.tsx`'s purple "PS" badge, blue "Automated" badge, and green "Manual" badge, the evidence-related UI now spans blue, green, purple, amber, and red as "semantic" colors — exceeds a clean 60/30/10 split and risks users not learning a consistent color-to-meaning mapping across the two components.
- No hardcoded hex/rgb() values found in `WindowsInstallTab.tsx` or `AssetComplianceList.tsx` — all colors are Tailwind semantic classes, which is good practice.

### Pillar 4: Typography (4/4)
- `WindowsInstallTab.tsx` uses only `text-sm`/`text-xs` (7/6 occurrences) and `font-medium`/`font-semibold` (5/3 occurrences) — within the "≤4 sizes, ≤2 weights" abstract-standard threshold with room to spare.

### Pillar 5: Spacing (4/4)
- Spacing values found (`gap-2`, `gap-3`, `mt-1/3/4`, `p-1/2/3/4`, `px-3`, `py-1`, `space-y-3/5`) are all on Tailwind's default 4px-multiple scale — no arbitrary `[Npx]`/`[Nrem]` values detected via grep.

### Pillar 6: Experience Design (3/4)
- Build/download flow (`handleBuildAndDownload`, lines 79-134) covers idle/building/done/failed states explicitly, with the trigger button disabled during `building` — solid baseline coverage.
- Failure path surfaces error text but offers no explicit "Retry" button — user must intuit that clicking the same button again retries; not disqualifying but a missed clarity opportunity.
- No visible incremental progress during the up-to-30s poll loop (line 98-114) — only a static caption, no spinner/progress bar, which risks users perceiving the UI as unresponsive on a real 15-30s wait.
- Threat-flag-documented intentional lack of auth on `/api/agent-updates/build` and `/download/...` is out of scope for this frontend audit (backend concern, already flagged in code comments as a tracked follow-up) — not scored here.

---

## Files Audited
- components/WindowsInstallTab.tsx (new, Phase 23-03)
- components/AgentInstallation.tsx (modified, Phase 23-03)
- components/AssetComplianceList.tsx (modified, Phase 23-03)
- .planning/phases/23-windows-powershell-evidence/23-01-SUMMARY.md (backend-only, no UI surface)
- .planning/phases/23-windows-powershell-evidence/23-02-SUMMARY.md (PowerShell scripts, no UI surface)
- .planning/phases/23-windows-powershell-evidence/23-03-SUMMARY.md
- .planning/phases/23-windows-powershell-evidence/23-01-PLAN.md
- .planning/phases/23-windows-powershell-evidence/23-02-PLAN.md
- .planning/phases/23-windows-powershell-evidence/23-03-PLAN.md

Registry audit: no `components.json` (shadcn) present in this project — registry safety audit skipped.
