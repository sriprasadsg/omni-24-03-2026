# Phase 13 — UI Review

**Audited:** 2026-07-06
**Baseline:** abstract 6-pillar standards (no UI-SPEC.md exists for this phase)
**Screenshots:** not captured — no dev server running (localhost:3000/5173 both unreachable); phase has no React/frontend surface, and no separately runnable PDF-preview tool. Audit performed via direct code review of the generated-PDF rendering path.

---

## Scope Note

Phase 13 ("AI Compliance Narratives") is a backend-only phase: it adds `backend/compliance_narrative_service.py` and wires it into `backend/scheduled_reports_service.py`. There is **no `.tsx`/`.jsx` frontend code** in this phase (confirmed via `grep -rln "narrative" src --include="*.tsx" --include="*.jsx"` → zero hits). The only user-facing surface this phase produces is the **PDF document** delivered by the scheduler (`_build_pdf` in `scheduled_reports_service.py`), which embeds AI-generated `Paragraph` text via `reportlab`.

Because the PDF is the actual artifact a human reads, this audit treats the PDF's narrative rendering (`_render_narratives`, `backend/compliance_narrative_service.py:259-273`) as the "UI" and scores it against the 6 pillars. This is a legitimate, if unusual, audit target — do not read the scores below as "N/A across the board."

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Prompts and fallback templates are clear and professional; one edge-case fallback string reads oddly ("scored 0.0%") when no framework data exists |
| 2. Visuals | 3/4 | Title → Heading2 → Normal hierarchy is consistent; no visual separator between AI narrative blocks and the structured metrics table |
| 3. Color | 2/4 | Metrics table uses an on-brand accent (`#667eea`) for its header row; narrative section headings get zero color treatment, so AI content looks visually disconnected from the rest of the report |
| 4. Typography | 3/4 | Only 3 style buckets used (`Title`, `Heading2`, `Normal`), reused consistently, in line with abstract standard (≤4 sizes) |
| 5. Spacing | 2/4 | `Spacer` values are ad hoc: 12, 24, 8 used with no declared scale or consistent multiplier logic |
| 6. Experience Design | 3/4 | Strong fallback/error coverage (BLOCKED:/Error: → static fallback, ValidationError caught, whole enrichment wrapped so PDF delivery is never blocked); no equivalent "empty state" polish beyond silently omitting the heading |

**Overall: 16/24**

---

## Top 3 Priority Fixes

1. **Narrative headings have no color treatment while the metrics table does** (`compliance_narrative_service.py:264,271` vs `scheduled_reports_service.py:347` `colors.HexColor("#667eea")`) — user impact: the AI-generated executive summary and per-framework findings (arguably the most important content in the report) read as plain black text sandwiched between a colorfully-styled table, making them look like an afterthought rather than the headline content. Fix: apply the same `#667eea` accent (or a `Heading2` style variant with `textColor=colors.HexColor("#667eea")`) to the "Executive Summary" and "{fw} — Findings" `Paragraph` headings.

2. **Spacing values are inconsistent and undocumented** (`Spacer(1, 12)` at scheduled_reports_service.py:323, `Spacer(1, 24)` at line 333, `Spacer(1, 8)` at compliance_narrative_service.py:270, `Spacer(1, 12)` at line 266) — user impact: uneven vertical rhythm in the PDF, especially between consecutive framework narrative blocks (8px) vs. the gap before the table (24px) vs. after the title block (12px). Fix: define a single spacing scale (e.g., `SPACER_SM=8, SPACER_MD=16, SPACER_LG=24`) as module constants and apply consistently to all `Spacer` calls in both files.

3. **No visual boundary between narrative prose and the structured metrics table** (`_render_narratives` called at `scheduled_reports_service.py:335` and `:357`, sandwiching the `Table` with zero rule/border/background differentiation) — user impact: a reader skimming the PDF cannot visually tell "this paragraph is AI-generated commentary" apart from "this is the raw data table" at a glance; both are set in identical `Normal` black text with no divider. Fix: add a thin horizontal rule (`reportlab.platypus.flowables.HRFlowable`) or a light background box around narrative paragraphs to create a distinct visual zone for AI content.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- Prompts (`compliance_narrative_service.py:99-104`, `134-138`) are well-scoped system instructions that explicitly forbid hallucinated control names/scores — good LLM-copy discipline.
- Fallback strings (`_fallback_executive_summary`, lines 80-86; inline fallback lines 130-133) are clear, C-level-appropriate prose.
- Minor issue: when `enrich_report_data`'s outer try fails (line 233), the exception-path fallback calls `_fallback_executive_summary(fw_name, 0.0)` (line 238) — this will render "The overall compliance score is 0.0%" even when the real score is simply unknown due to a query failure, which misrepresents an error state as a real (zero) compliance score. This is a copy-accuracy defect, not just a style nit.

### Pillar 2: Visuals (3/4)
- Consistent 3-tier hierarchy: `styles["Title"]` for report title (scheduled_reports_service.py:322), `styles["Heading2"]` for narrative section headers (compliance_narrative_service.py:264, 271), `styles["Normal"]` for body text — matches expected visual hierarchy heuristic.
- No focal-point competition: title anchors the page, narrative sections are subordinate headings, table is clearly the densest visual block.
- Gap: no rule/border/shading distinguishes the two narrative zones from the table between them (see Fix #3 above) — a reader scanning the page has no visual anchor beyond text position to know where "commentary" ends and "data" begins.

### Pillar 3: Color (2/4)
- `_build_pdf`'s metrics table (scheduled_reports_service.py:346-354) deliberately uses brand color `#667eea` for header background/text and `#f3f4f6`/`#e5e7eb` for zebra rows and grid lines — a real, intentional accent application.
- `_render_narratives` (compliance_narrative_service.py:259-273) uses zero color — `Paragraph(..., styles["Heading2"])` and `styles["Normal"]` are reportlab's stock black-on-white styles, with no `textColor` override.
- This is an inconsistent application of the report's established accent: the one part of the document with a defined color language (the table) is disconnected from the two narrative blocks that bookend it. A 60/30/10-style audit finds 100% of the accent concentrated in the table and 0% elsewhere, rather than a deliberate, book-ended distribution.

### Pillar 4: Typography (3/4)
- Reuses `getSampleStyleSheet()` defaults uniformly across both files: `Title` (1), `Heading2` (2), `Normal` (2 — used for both report metadata and narrative body) — 3 distinct type roles, well under the ≤4-size guidance for abstract standards.
- No arbitrary/inline font-size or font-weight overrides found in either file.
- Not scored higher only because `Heading2` is reused for both top-level report subsections (implicit, in other flows) and narrative subheadings without any secondary distinguishing style (e.g., different weight/size for "Executive Summary" vs. per-framework "{fw} — Findings"), which flattens what could be a deeper hierarchy (report section vs. sub-finding).

### Pillar 5: Spacing (2/4)
- Grep of both files for `Spacer(` calls: `Spacer(1, 12)` (scheduled_reports_service.py:323), `Spacer(1, 24)` (scheduled_reports_service.py:333), `Spacer(1, 12)` (compliance_narrative_service.py:266), `Spacer(1, 8)` (compliance_narrative_service.py:270).
- Four different spacing values (8, 12, 24) used across two files with no shared constant or documented scale — classic arbitrary-spacing violation per the abstract standard.
- Values don't follow a clear multiplier (8, 12, 24 is not a consistent ratio like 8/16/24/32) — looks like values were chosen ad hoc per call site rather than from a system.

### Pillar 6: Experience Design (3/4)
- Excellent failure-mode coverage: `BLOCKED:`/`Error:` prefix detection (compliance_narrative_service.py:113, 147) triggers static fallback before any Pydantic validation runs; `NarrativeOutput` model_validator (`within_budget`, lines 53-63) is a second independent gate against word-budget bypass; `_validated_narrative` (lines 71-77) catches `ValidationError` and never propagates.
- `enrich_report_data` triple-wraps its three logical steps (failing-controls query, executive summary, per-framework narratives) in independent try/except blocks (lines 166-221, 223-238, 240-256) so a failure in any one step degrades gracefully without blocking PDF delivery — this is a genuinely strong resilience pattern, confirmed by the 8-test suite (`13-01-SUMMARY.md`) and the async test-ordering fix (`13-02-SUMMARY.md`).
- Not scored 4/4: the "empty state" for a framework with no narrative is a silent omission (`if narrative:` at compliance_narrative_service.py:269 skips rendering) rather than an intentional placeholder ("Findings narrative unavailable for this framework") — a reader would see a framework simply missing its findings section with no indication whether that's by design or a failure.

---

## Files Audited
- `backend/compliance_narrative_service.py` (273 lines)
- `backend/scheduled_reports_service.py` (`_build_pdf` function, lines 307-363, plus import/wiring points)
- `.planning/phases/13-ai-compliance-narratives/13-01-SUMMARY.md`
- `.planning/phases/13-ai-compliance-narratives/13-02-SUMMARY.md`
- `.planning/phases/13-ai-compliance-narratives/13-01-PLAN.md`
- `.planning/phases/13-ai-compliance-narratives/13-02-PLAN.md`

No frontend (`.tsx`/`.jsx`) files exist for this phase; registry safety audit skipped (no `components.json` third-party registry entries apply to this backend-only phase).
