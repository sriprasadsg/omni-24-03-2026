---
phase: 85-first-line-service-desk
verified: 2026-11-09T20:15:00Z
status: human_needed
score: 7/7 must-haves verified
covered_files:
  - backend/service_desk/checks.py
  - backend/service_desk/pipeline.py
  - backend/service_desk/projection.py
  - backend/service_desk/sanitize.py
  - components/serviceDesk/requesterComments.ts
covered_digest: "v3:sha256:9d3bd2c48234a3f1c5b637d85032d754f779ee95a0d3f4d0d421673bb85c5a65"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 6/7
  gaps_closed:
    - "CR-101: D-19 strict output checks bypassable by zero-width / full-width characters (DESK-03 output side)"
    - "CR-401: reporter sees staff-only comments / AI drafts; UI failed open while deskView was null (DESK-01 draft stays internal)"
  gaps_remaining: []
  regressions: []
advisory:
  - finding: "CR-501: GET /api/notifications/history (backend/reporting_endpoints.py:202-221) has no audience filter; any view:dashboard user of a tenant can read per-person notices (100-character preview of a staff reply written for another requester) and tenant-admin-audience notices. Staff-only comment notices carry no text, and no notice carries AI draft text, so this does not breach a DESK-01..07 truth."
    category: security
    reason: "Real bypass of the D-33 notice audience filter (WR-201/202); adjacent to, not part of, the phase goal. Open in 85-REVIEW-DISPOSITION.md. Small fix (share the reader filter)."
    evidence_status: "confirmed by reading the route and ticket_notifications.notify_comment_added; not executed"
  - finding: "WR-501: reporter projection is a block-list; work_logs text, watchers, custom_fields and some history entries reach the reporter. WR-502: staff-only comments / drafts are readable by every non-reporter tenant user with view:dashboard (platform-wide ticket read model)."
    category: security
    reason: "Residual halves of CR-401 outside the DESK truths; WR-502 needs a product decision on who counts as ticket staff."
    evidence_status: "from 85-REVIEW.md, consistent with projection.py read here"
human_verification:
  - test: "Install Ollama and pull llama3.2:3b, then run the 85-22 measurement/calibration script on the CPU-only server"
    expected: "Real generation times recorded; call timeouts and the retrieval cut-off hold; DESK-05 real response time is reported"
    why_human: "Ollama is not installed on this VM; real CPU timing cannot be produced by tests"
  - test: "Restart the backend (migration 032) with Ollama absent and open a new first-line portal ticket"
    expected: "Ticket handed to a person (service_desk_offline); no placeholder answer is posted"
    why_human: "Live restart effect belongs to the user"
  - test: "Portal round trip and Windows tray round trip (agent 2.1.18 published): requester sees the AI-assisted answer, confirms or says it did not help"
    expected: "Confirm closes the ticket; did-not-help hands off to a person; the reporter never sees staff-only comments or drafts in the browser"
    why_human: "Needs a published UI, a real Windows agent and a real browser"
  - test: "Decide on CR-501 / WR-502 before deployment"
    expected: "Either the notice history route gets the shared audience filter (recommended, small) and the ticket-staff test is made explicit, or the residual exposure is accepted in writing"
    why_human: "Product decision on who may read what; the code review is advisory and these findings are outside the seven DESK truths"
---

# Phase 85: First-Line Service Desk Verification Report

**Phase Goal:** New first-line tickets get a cited answer drafted from the tenant's knowledge base, posted, drafted or escalated by fixed rules, and anything the system is unsure of, anything sensitive, and everything while the language model is unavailable goes to a person.
**Verified:** 2026-11-09T20:15:00Z
**Status:** human_needed
**Re-verification:** Yes, after gap closure (plans 85-24..85-29)

## Previous gaps, re-checked against the code first

| Gap | Result | Evidence |
|-----|--------|----------|
| CR-101 output checks bypass | CLOSED | `checks.py`: `check()` runs `fold_text(reply.answer)` before every rule; `parse_reply()` returns the folded answer; `pipeline.answer()` posts `parsed.answer` (the folded text), so checked text equals shown text. Own probe with cited article "Reset your password at the portal.": `evil.<ZWSP>com`, full-width `evil.com`, `evil<U+3002>com`, `x@evil<ZWSP>.com`, `5551234567` split by ZWSP, `` `r<SHY>m -rf` ``, soft-hyphen domain, bidi-override domain, `h<ZWSP>ttp://evil.com`, U+2024 and U+FE52 dot variants all return foreign_link / foreign_email / foreign_phone / foreign_command; the legitimate answer returns None. Residual look-alike dots (U+2025, U+06D4, U+0589, U+2027) fold to non-link text, not to a domain, so they are not a bypass. Regression suites test_service_desk_output_checks.py and test_service_desk_output_fold.py pass. |
| CR-401 reporter sees staff-only comments / drafts | CLOSED for the reporter | Server: `projection.for_viewer / history_for_viewer / requester_may_read` (ai_draft never, requester-visible only, own comments) applied through `tickets_endpoints._shown/_shown_history` on every route at HEAD (list, get, update, comment, history and the others). UI: `components/serviceDesk/requesterComments.ts` `visibleComments` decides from ticket reporter + signed-in email, not only `deskView`; an unknown viewer with no desk view is treated as reporter (fails closed); wired in `InternalTicketsDashboard.tsx` (HEAD lines 732, 913) and pinned to the server by the shared case table `shared/service-desk-requester-comments.json`. test_service_desk_reporter_ticket.py and test_service_desk_comments.py pass; vitest ServiceDeskRequesterComments 33 passed. Residual exposure to non-reporter users is WR-502 (advisory). |

## Goal Achievement

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | KB-covered ticket gets a cited answer: posted "AI-assisted" at Undoable-auto, internal draft at Suggest, closes only on requester confirmation | VERIFIED | `pipeline.answer`: build_prompt -> client.generate -> parse_reply/check (citation rules) -> fresh re-read -> `gate.decide` with `force_suggest` unless mode is post / can_see -> `outcomes.post` or `keep_draft`; AI path never resolves a ticket (lifecycle/withdraw modules); drafts stripped from the reporter (CR-401 closed). test_service_desk_pipeline (37 incl. lifecycle neighbours), lifecycle, gate suites pass |
| 2 | Escalation (no article, person asked for, security/billing/legal/account access) never answered; model confidence never used; knowledge-gap list | VERIFIED | `rules.evaluate` (fixed phrases) and `retrieval.select/score` run in `prepare()` before any model call; `grep confidence service_desk/*.py` finds only prohibitions; gaps.py + knowledge_helpdesk_endpoints.py (WR-203: gap article must be Help desk, 422); test_service_desk_rules (55) and knowledge_gaps (15) pass |
| 3 | Ticket text cannot trigger an action; links/HTML stripped before the model; injection test set passes; (output side) model-emitted links/addresses cannot reach the requester | VERIFIED | Input: `sanitize.clean_text` (markup, links, emails, bare domains, hidden chars) and `build_prompt`; no tool path, reply read only for `answer`/`cited`. Output: CR-101 closed (above). test_service_desk_injection (4) and output suites pass |
| 4 | Model unavailable (or mock only): ticket escalated, no placeholder answer | VERIFIED | `pipeline.answer`: `not client.available()` -> `service_desk_offline`; `ModelError` -> `service_desk_busy`; `model.py` is a loopback-only Ollama client (`trust_env=False`, WR-101 closed), no mock provider path |
| 5 | Async, one at a time, CPU-sized timeouts, response time measured; starters seedable | VERIFIED in code; live measurement pending | worker `desk_loop` started in `app_startup.py:528-532`; `runtime.call_timeout/load_measurement/recent_gen_ms`; `starters.py` (password reset, VPN, printer, tray); test_service_desk_worker (24) and starters (25) pass; real CPU timing is a human item |

**Score:** 7/7 requirements (5/5 roadmap truths) verified in code; live-only items remain.

### Required Artifacts / Key Links (spot-verified)

| Artifact | Status | Details |
|----------|--------|---------|
| backend/service_desk/checks.py | VERIFIED | substantive, 202 lines; imported by pipeline; fold shared with sanitize |
| backend/service_desk/sanitize.py | VERIFIED | `fold_text` single fold; used by clean_text, normalize_for_match, checks |
| backend/service_desk/pipeline.py | VERIFIED | wired to worker, gate, outcomes, handoff |
| backend/service_desk/projection.py | VERIFIED | wired through tickets_endpoints `_shown` at HEAD |
| components/serviceDesk/requesterComments.ts | VERIFIED | wired in InternalTicketsDashboard.tsx |
| worker -> app_startup | WIRED | `_service_desk_loop` created as background task |
| intake -> agent_tasks_endpoints / tickets_service | WIRED | `desk_intake` imported, RAISED_VIA stamped |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Output check vs hidden/full-width chars | `backend/venv/bin/python` probe of `parse_reply` + `check` (16 cases) | all attack cases rejected, legit answer None | PASS |
| Service desk backend suites (10 files) | pt.sh on private mongod 27998 | 427 passed in 68s | PASS |
| Reporter comment filter (UI) | `npx vitest run src/__tests__/ServiceDeskRequesterComments.test.tsx` | 33 passed | PASS |
| Gate evidence from orchestrator (not re-run by me) | 2,179 backend, 1,873 vitest, build exit 0 | reported | taken as reported |

### Requirements Coverage

All seven IDs appear in PLAN frontmatter (85-01..85-29) and REQUIREMENTS.md; none orphaned.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| DESK-01 | SATISFIED | pipeline/outcomes/lifecycle; drafts hidden from the reporter (CR-401); WR-502 advisory |
| DESK-02 | SATISFIED | rules.py, retrieval.py, gaps.py |
| DESK-03 | SATISFIED | input sanitiser plus CR-101 closed on the output side |
| DESK-04 | SATISFIED | service_desk_offline hand-off, loopback client only |
| DESK-05 | SATISFIED in code | worker, runtime, 85-22 script; real timing human-pending |
| DESK-06 | SATISFIED | gaps.py, knowledge-gap list and tests |
| DESK-07 | SATISFIED | starters.py |

### Anti-Patterns

Debt-marker grep (TBD / FIXME / XXX) over backend/service_desk, components/serviceDesk: none. No stub patterns found in the five covered files. Warning-level findings are below.

### Review Findings Weighed (85-REVIEW.md, gap-round re-review)

- CR-501 (critical in the review): confirmed by reading `reporting_endpoints.get_notification_history` (query is only `{"tenant_id": tenant_id}`). I judge it NOT a failed DESK-01..07 truth: staff-only comment notices contain no comment text, per-person notices carry generic text or a 100-character preview of a requester-visible reply, and no notice carries AI draft text. It is a genuine audience-filter bypass (D-33) and should be fixed before deployment; recorded as an advisory plus a decision item, not a gap.
- WR-501 / WR-502: residual exposure of staff-entered fields to the reporter, and of staff-only comments to non-reporter `view:dashboard` users. Needs a product decision (who is ticket staff). Advisory.
- WR-503 / WR-504: write-order edge cases on exception paths (status left at pending_customer; status reverted after a stored answer). Narrow failure-path defects; not a truth failure. Advisory.
- IN-501..504: informational (username vs email in `is_reporter`, badge count, ideographic-stop rewrite fails closed).

## Human Verification Required

1. **Ollama measurement on the CPU server.** Install Ollama + llama3.2:3b, run the 85-22 script. Expected: real generation times, timeouts and retrieval cut-off hold, DESK-05 time reported. Why human: no Ollama on this VM.
2. **Restart with Ollama absent (migration 032).** Open a first-line portal ticket. Expected: hand-off `service_desk_offline`, no placeholder answer.
3. **Portal and Windows tray round trip** after UI publish and agent 2.1.18 publish. Expected: AI-assisted answer with citations; confirm closes; did-not-help hands off; reporter never sees staff-only comments or drafts.
4. **Decision on CR-501 / WR-502** (advisory, outside the seven DESK truths): fix the notice history route with the shared audience filter (recommended) and make the ticket-staff test explicit, or accept in writing.

## Gaps Summary

Both gaps from the previous verification are closed in the code and confirmed by my own probe and test runs. All five roadmap truths and all seven DESK requirements are supported by substantive, wired code. No FAILED truth, no blocker anti-pattern, no debt markers. The status is human_needed only because the live-only checks (Ollama timing, restart, portal/tray round trips, UI publish) cannot be done on this VM and the CR-501 / WR-502 exposure needs an explicit user decision.

---

_Verified: 2026-11-09T20:15:00Z_
_Verifier: Claude (gsd-verifier)_
