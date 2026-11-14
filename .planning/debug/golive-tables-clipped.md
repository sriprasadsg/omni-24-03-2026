---
status: diagnosed
trigger: "86-UAT test 5 / gap G-86-5: Going live organizations table and Autonomous Ops per-rule statistics table clipped at ~1024-1280 px with the sidebar open; no horizontal page scroll at 320 px"
created: 2026-11-14T11:00:00Z
updated: 2026-11-14T11:30:00Z
goal: find_root_cause_only
---

## Current Focus

hypothesis: CONFIRMED (UI review root cause holds, with corrected numbers). The two tables switch to the wide layout on the VIEWPORT (matchMedia min-width 1024) but need 884 / 946 px of COLUMN width; the content column is viewport - 358 - scrollbar with the sidebar open. Neither table has an overflow-x-auto wrapper, so the overflow spills out of the card and is cut off by main's overflow-x-hidden (App.tsx:2023).
test: static layout probe, live CSS index-BRVoEUxD.css (the build served now), chrome-headless-shell, same shell/card/table classes as the source, light + dark, sidebar open (256) and collapsed (76), 320..1440 px
expecting: n/a (done)
next_action: hand ROOT CAUSE FOUND to the caller; gap plan applies the fix (no source edited here)
bug_class: Bohrbug (deterministic, pure layout; reproduces at every run)
reasoning: candidate_causes below; and_gate = yes (two conditions are both required)

candidate_causes:
- "code: wide/narrow switch is viewport based (WIDE_QUERY 1024) while the table width is fixed by column minimums, so it is wrong whenever the content column is narrower than the table"
- "code: no overflow-x-auto wrapper around either table (the wrapper is only min-w-0)"
- "spec/config: UI-SPEC '900 px budget' is compared to a constant, never to the real content column (viewport - 358 - scrollbar); also per-rule minimum is 946 not 888"
- "environment: shell main has overflow-x-hidden, turning any overflow into unreachable content; sidebar 256/76 and 6-10 px scrollbar change the column width"
- "data: long organization / rule names -> eliminated, table width is the sum of fixed min-w values"
and_gate: "yes. Both (a) the viewport-based switch being too early AND (b) no scroll container are needed for the user to lose columns. With (b) fixed alone the columns become reachable by scrolling (the RingDetail / Partner precedent). With (a) fixed alone (container based switch) nothing overflows. The shell's overflow-x-hidden is the amplifier, not a thing to change."

## Symptoms

expected: Visual checks at 320 px (light and dark) and at 1024-1280 px with the sidebar open for the Going live organizations table and the Autonomous Ops per-rule statistics table: no clipped Action column and no horizontal page scroll at 320 px.
actual: Recorded as an issue on code evidence (user typed "pass" but nothing reached the server). GoLiveOrganizations.tsx and StatsRuleTable.tsx have no overflow-x-auto wrapper and switch to the wide (table) layout at WIDE_QUERY = '(min-width: 1024px)'. UI review: at ~1024-1175 px with the sidebar open the Organizations Action column is clipped by main's overflow-x-hidden; the per-rule table loses Refused and Would have done (simulation) up to ~1240 px.
errors: none
reproduction: Test 5 in .planning/phases/86-activity-reporting-hardening-live-validation/86-UAT.md
started: UAT 2026-11-14; files last changed in 86-15 (c28996228) and 86-12 (e3a3f14b3); 86-04 (3efaa474e) for the per-rule table

## Eliminated

- hypothesis: long organization or rule names make the tables wider than the column
  evidence: table width is the sum of min-w cells (240+160+120+144+220 = 884; 240+7x72+144 = 888 + padding growth = 945.9 measured) and is the same with short names; the name cells wrap (break-words / break-all)
  timestamp: 2026-11-14
- hypothesis: moving the layout switch from lg (1024) to xl (1280), as the UI review suggests, is enough
  evidence: probe at 1280 with the sidebar open: per-rule table 945.9 px in a 912 px column (34 px past the card padding, right edge 1259 vs main clip 1258). It needs vw >= 1314. xl also needlessly forces cards at 1072-1279 px with the sidebar collapsed, where the tables fit
  timestamp: 2026-11-14
- hypothesis: horizontal page scroll at 320 px
  evidence: probe at 320 (light and dark): documentElement.scrollWidth = 320, main.scrollWidth = main.clientWidth = 206. Below 1024 both components render the card layout, so neither table exists at 320. main has overflow-x-hidden so a page scroll cannot appear in any case (the check has to look for clipping, not scrolling)
  timestamp: 2026-11-14
- hypothesis: dark mode changes the geometry
  evidence: 320 px probe in dark has identical numbers (only colour classes differ)
  timestamp: 2026-11-14

## Evidence

- timestamp: 2026-11-14
  checked: GoLiveOrganizations.tsx (full)
  found: line 15 WIDE_QUERY = '(min-width: 1024px)'; lines 24-35 useWideLayout (matchMedia, wide when matchMedia is missing); line 136-162 table `w-full border-collapse`, th min-w 240/160/120/144/220 (= 884); line 231-233 `<div className="min-w-0">{wide ? <OrganizationTable/> : <OrganizationCards/>}</div>` with no overflow class
  implication: the wrapper is only min-w-0; a table wider than the card overflows visibly out of it

- timestamp: 2026-11-14
  checked: StatsRuleTable.tsx (full)
  found: line 16 WIDE_QUERY 1024; line 19-30 identical hook; line 50-86 table `w-full min-w-0`, th min-w 240 + 7 x 72 + 144; line 149-152 `<div className="flex flex-col gap-4"><div className="min-w-0">{wide ? <RuleTable/> : <RuleCards/>}</div>` no overflow class
  implication: same defect; the table measured 945.9 px (min-w-[72px] on a border-box th includes the 32 px px-4, so 'Approved' needs ~82 px)

- timestamp: 2026-11-14
  checked: App.tsx 1989-2023, Sidebar.tsx:204, index.css:239 (.card), GoLiveCard.tsx:97 / StatsCard.tsx:97 (`card p-6`)
  found: shell `p-2 md:p-3` (24 px at md+), sidebar `w-64` open / `w-[76px]` closed (open by default at >= 768, closed below), `gap-3` (12), main `flex-1 overflow-x-hidden overflow-y-auto px-1 md:px-2`, card `p-6` + 1 px border, `.card` has no overflow rule. index.css:424-431 thin scrollbar
  implication: content column = vw - 24 - 256 - 12 - 16 - (scrollbar 6-10) - 2 - 48 = vw - 358 - scrollbar (open); + 180 when the sidebar is collapsed. The UI review's "vw - 356" omitted the card border and the scrollbar

- timestamp: 2026-11-14
  checked: probe, sidebar OPEN, scrollbar 10 px (headless thin)
  found: column / Orgs table / per-rule table. 1024: 656 / 884 (Action col starts at x=977, main clip at x=1002, Lift button 993-1166 -> ~9 px visible) / 946 (Refused and Would-have-done gone). 1100: 732 / same / 946. 1180: 812 / Lift button r=1166 (clip 1158), Use as test organization r=1181 / sim column r=1259 (clip 1158). 1240: 872 / fits main but 12 px past card padding / 946 (sim column r=1259, clip 1218). 1280: 912 / fits exactly / 946 (34 px over, 1 px past clip). 1320: 952 / 946 both fit
  implication: Orgs table needs vw >= 1252 (1242 with an overlay scrollbar); per-rule needs vw >= 1314 (1304). Content is cut off (unreachable) below roughly 1190 (Orgs) and 1281 (per-rule); between that and the fit width it overhangs the card padding/border but is visible

- timestamp: 2026-11-14
  checked: probe, sidebar COLLAPSED (76 px)
  found: 1024: column 836, Orgs 884 (buttons end at 986-1001, within main clip 1002 but 15 px over the card edge), per-rule 946 (sim column r=1079 vs clip 1002, clipped). 1072: Orgs fits; per-rule still clipped. 1100: per-rule 34 px over. 1140: both fit
  implication: collapsing the sidebar is a workaround for the Orgs table only from 1024; per-rule still needs >= 1134

- timestamp: 2026-11-14
  checked: probe at 320 / 360 / 375 / 414 / 640 (sidebar closed, default below 768), light and dark; also 768 / 900 / 1023 sidebar open
  found: no horizontal page scroll anywhere (pageScrollW = vw; main.scrollWidth = clientWidth). Card layout used below 1024. At 320 the content column is only 148 px (320 - 16 shell - 76 collapsed sidebar still in flow - 12 gap - 8 main - 10 scrollbar - 2 - 48; ~158 on a phone with overlay scrollbars). Inside the 116 px li: (a) the `Shadow mode on` chip has min-content 87 px in a 54 px grid cell, so it spans x=141-228 and overlaps the Days observed cell (starts x=203) by 25 px (5 px at 360, none from 375); (b) `Use as test organization` has min-content 132 px in a 116 px li, overhangs the li padding by 16 px but stays inside the card; (c) per-rule cards: `Approved` dt 57 px in a 54 px cell, inside the 8 px gap, invisible
  implication: the 320 px half of the truth (no horizontal page scroll) holds. A smaller, separate cosmetic defect exists in the Organizations card layout at <= ~366 px (chip overlapping the neighbouring cell). Not reported by the UI review

- timestamp: 2026-11-14
  checked: precedents for wide tables in this shell
  found: components/patchRollouts/RingDetail.tsx:64 `<div className="hidden overflow-x-auto lg:block">` (min widths 800, scrolls inside the card, CSS only switch); PartnersDashboard.tsx:188 and :327, PartnerPortal.tsx:240, PartnerTeamPanel.tsx:281 use the SAME matchMedia useWideLayout hook (1024) AND wrap the table in `<div className="overflow-x-auto">`; ~40 other dashboards use overflow-x-auto. No reusable ResizeObserver / element-width hook in components/ (only react-grid-layout's useContainerWidth in dashboards/DashboardGrid.tsx and test stubs); Tailwind 3.4.17 without the container-queries plugin (live CSS has 0 @container)
  implication: the established fix is the overflow-x-auto wrapper; the two Phase 86 components are the only matchMedia-table components without it. A container-width switch would need a new hook

- timestamp: 2026-11-14
  checked: 86-UI-SPEC.md lines 72, 258, 333-341, 387; 86-VERIFICATION.md line 159
  found: the spec's "900 px table budget" (inherited from Phase 81) is a constant compared with the table width (888 / 884), and the switch is tied to `lg`. It never subtracts the shell (sidebar 256, paddings, card). Verification rated the same finding W2 (warning) and gave "collapse the sidebar" as the workaround
  implication: the defect was designed in, not a regression; the E2 / E10 "overflow resolved" rows in the spec only covered the card layout

- timestamp: 2026-11-14
  checked: vitest baseline
  found: `npx vitest run` on autonomousOpsGoLive.test.tsx, autonomousOpsGoLiveTestOrg.test.tsx, autonomousOpsStats.test.tsx: 93 passed. They stub matchMedia matches:false for the card layout (autonomousOpsStats.test.tsx:400-427, autonomousOpsGoLive.test.tsx:524-545) and use jsdom's no-matchMedia default for the table; nothing asserts a scroll container
  implication: the defect is invisible to the unit tests; jsdom has no layout, so a regression test can only assert structure

## Resolution

root_cause: "GoLiveOrganizations.tsx:231-233 and StatsRuleTable.tsx:149-152 put a 884 px (Organizations) and a 946 px (per-rule) table, whose width is fixed by column minimums, in a plain `min-w-0` div with no overflow-x-auto, and choose the table layout from the VIEWPORT (WIDE_QUERY (min-width: 1024px), GoLiveOrganizations.tsx:15, StatsRuleTable.tsx:16) instead of the card width. With the sidebar open the card's content column is only vw - 358 - scrollbar (656 px at 1024), so the tables are used 230-290 px before they fit (Organizations from 1252 px, per-rule from 1314 px). The overflow is not scrollable and is cut off by main's overflow-x-hidden (App.tsx:2023), so the Action column and the Refused / Would have done (simulation) columns cannot be reached. Both conditions are required (AND-gate)."
fix: "(not applied, diagnose only)"
verification: ""
files_changed: []
