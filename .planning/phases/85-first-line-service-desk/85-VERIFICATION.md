---
phase: 85-first-line-service-desk
verified: 2026-11-09T00:00:00Z
status: gaps_found
score: 6/7 must-haves verified
covered_files:
  - .planning/phases/85-first-line-service-desk/85-01-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-01-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-02-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-02-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-03-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-03-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-04-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-04-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-05-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-05-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-06-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-06-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-07-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-07-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-08-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-08-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-09-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-09-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-10-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-10-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-11-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-11-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-12-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-12-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-13-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-13-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-14-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-14-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-15-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-15-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-16-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-16-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-17-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-17-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-18-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-18-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-19-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-19-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-20-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-20-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-21-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-21-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-22-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-22-SUMMARY.md
  - .planning/phases/85-first-line-service-desk/85-23-PLAN.md
  - .planning/phases/85-first-line-service-desk/85-23-SUMMARY.md
  - backend/service_desk/checks.py
  - backend/service_desk/model.py
  - backend/service_desk/pipeline.py
covered_digest: "v3:sha256:f9915bd0e1c584a9834b89b414352c753fe8d7db7abb83892139dea5fc36639e"
behavior_unverified: 0
gaps:
  - truth: "D-19 strict output checks: a posted/drafted answer may contain only links, emails, phones, commands and numbers that occur in a cited article (DESK-01 cited answer, DESK-03 ticket text cannot cause exfiltration; SECURITY T-85-19 / T-85-48)"
    status: failed
    reason: "checks.check() runs its URL/email/domain/command regexes on the raw answer; only the article text is NFKC-normalised. Reproduced: answer 'Visit evil.<ZWSP>com now', the full-width 'evil.com', and 'x@evil<ZWSP>.com' all return None (pass) with cited article 'Reset your password at the portal.'; plain 'evil.com' correctly returns foreign_link. pipeline.answer() then posts parsed.answer unchanged. No test in test_service_desk_output_checks.py covers hidden or full-width characters, so the 785 green tests do not see it (CR-101, open in disposition)."
    artifacts:
      - path: "backend/service_desk/checks.py"
        issue: "check() does not normalise/strip hidden (Cf) and compatibility characters from reply.answer before the _URL/_EMAIL/_BARE_DOMAIN/_COMMAND rules"
      - path: "backend/service_desk/pipeline.py"
        issue: "posts parsed.answer as returned by the model (line ~121-136), after check() only"
    missing:
      - "Normalise the answer (NFKC + remove format/control chars, the same fold sanitize.py already has) before the output rules, and post the normalised text"
      - "Regression tests: ZWSP, soft hyphen, full-width dot/letters, and bidi-control variants of link, email, phone, command"
  - truth: "Staff-only comments and AI drafts are not shown to the requester (DESK-01: AI draft stays an internal draft at Suggest)"
    status: partial
    reason: "components/InternalTicketsDashboard.tsx:1385 filters only kind==='ai_draft' and only when deskView?.isRequester is truthy, so it fails open while deskView is null and does not hide staff-only comments (CR-401). Server-side legacy ticket JSON still carries all comments (accepted risk T-85-77). Not independently run in a browser."
    artifacts:
      - path: "components/InternalTicketsDashboard.tsx"
        issue: "comment filter is reporter-hostile only for ai_draft and fails open"
    missing:
      - "Hide ai_draft and staff-only comments from non-staff until deskView resolves, or strip them server-side"
behavior_unverified_items: []
human_verification:
  - test: "Install Ollama and a model, then run the 85-22 measurement/calibration script on the CPU-only server"
    expected: "Real generation times recorded; call timeouts and the retrieval cut-off hold; DESK-05 real response time is reported"
    why_human: "Ollama is not installed on this VM; real CPU timing cannot be produced by tests"
  - test: "Windows tray round trip: requester sees the AI-assisted answer and confirms or says it did not help"
    expected: "Confirm closes the ticket; 'did not help' hands off to a person"
    why_human: "Needs a real Windows agent"
  - test: "Publish the UI and check the desk views visually; portal round trip after a backend restart"
    expected: "AI-assisted label, citations, draft panel and knowledge-gap list render; portal confirm/reject works"
    why_human: "UI publish and a visual check are the user's steps (85-UI-REVIEW scored 19/24 code-only)"
  - test: "Restart the backend with Ollama absent and open a new first-line ticket"
    expected: "Ticket is handed to a person (service_desk_offline); no placeholder answer is ever posted"
    why_human: "Live restart effect belongs to the user"
---

# Phase 85: First-Line Service Desk Verification Report

**Phase Goal:** New first-line tickets get a cited answer drafted from the tenant's knowledge base, posted, drafted or escalated by fixed rules, and anything the system is unsure of, anything sensitive, and everything while the language model is unavailable goes to a person.
**Verified:** 2026-11-09
**Status:** gaps_found
**Re-verification:** No, initial verification

## Goal Achievement

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | KB-covered ticket gets a cited answer: posted "AI-assisted" at Undoable-auto, internal draft at Suggest, closes only on requester confirmation | VERIFIED (with gap on output checks) | pipeline.answer() builds a request, runs gate.decide, then outcomes.post / keep_draft; force_suggest when mode != post; lifecycle/withdraw/returns modules; test_service_desk_pipeline/lifecycle/gate pass |
| 2 | Escalation (no article, asks for a person, security/billing/legal/account access) never answered; model confidence never used; knowledge-gap list | VERIFIED | rules.evaluate (fixed phrases, PROH-85-03 doc), retrieval gate_score (a retrieval score, not model confidence; grep finds no use of confidence); gaps.py; test_service_desk_rules / retrieval / knowledge_gaps pass |
| 3 | Ticket text cannot trigger an action; links/HTML stripped before model; injection test set passes | FAILED (output side) / VERIFIED (input side) | Input: sanitize.build_prompt (NFKC, hidden-char removal), no tool call path, test_service_desk_injection/sanitize/structural pass. Output: D-19 checks bypassable (CR-101, reproduced), so a link/address the model was induced to emit can reach the requester |
| 4 | Model unavailable (or mock only): ticket escalated, no placeholder answer | VERIFIED | pipeline.answer: not client.available() -> _handoff service_desk_offline; ModelError -> service_desk_busy; desk talks only to loopback Ollama client, no mock provider path; test_a_model_that_is_not_running_hands_off_service_desk_offline passes |
| 5 | Async, one at a time, CPU-sized timeouts, response time measured; starter articles seedable | VERIFIED in code, live measurement pending | worker.py/runtime.call_timeout/load_measurement; starters.py (password reset, VPN, printer, tray); test_service_desk_worker/starters/eval_script pass; real CPU timing is a human item (no Ollama) |

**Score:** 6/7 requirements satisfied (DESK-03 blocked on its output side); 4 human items.

### Key Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Whole service desk backend suite | pytest tests/test_service_desk_*.py on private mongod 27998 | 785 passed in 266s | PASS |
| Output check vs hidden chars | checks.check on "evil.<ZWSP>com", full-width evil.com, "x@evil<ZWSP>.com" | all None (accepted); plain evil.com -> foreign_link | FAIL |
| Proxy env | grep model.py:129 httpx.AsyncClient(...) | no trust_env=False, so HTTP_PROXY is honoured (WR-101) | WARNING |
| Reporter comment filter | InternalTicketsDashboard.tsx:1385 | only ai_draft, only when deskView?.isRequester | FAIL (CR-401) |

### Requirements Coverage

All 7 IDs appear in plan frontmatter (85-01..85-23, 85-23 claims all) and in REQUIREMENTS.md; none orphaned.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| DESK-01 | SATISFIED, with CR-101/CR-401 caveats | pipeline/outcomes/lifecycle tests |
| DESK-02 | SATISFIED | rules.py, retrieval.py, gaps.py |
| DESK-03 | BLOCKED (output side) | CR-101 reproduced; input sanitising satisfied |
| DESK-04 | SATISFIED | service_desk_offline hand-off |
| DESK-05 | SATISFIED in code; real timing human-pending | worker, runtime, 85-22 script |
| DESK-06 | SATISFIED | gaps.py, knowledge-gap tests |
| DESK-07 | SATISFIED | starters.py, test_service_desk_starters |

### Review Findings Weighed

- CR-101 (critical): confirmed by reproduction; defeats the D-19 must-have. Gap (blocker).
- CR-401 (critical): confirmed in the UI source; gap (partial), server-side exposure is an accepted risk T-85-77.
- WR-101 confirmed (trust_env default); WR-102/103, WR-201/202, WR-301: not re-run, warnings carried from 85-REVIEW.md, all still open in 85-REVIEW-DISPOSITION.md.
- Anti-pattern scan not repeated on the whole 4,241-line module; debt-marker gate not re-run (limited context). Marked as unchecked, not as passed.

### Gaps Summary

The pipeline, escalation rules, offline hand-off, knowledge-gap list, starters and worker are real and tested (785 passed). The phase goal is not fully met because the strict output check that stops a model-emitted link or address from reaching a requester can be bypassed with a zero-width or full-width character, and the shipped tests do not cover it. A small fix plus tests closes it (normalise the answer with the fold already in sanitize.py before the rules, and post the normalised text). CR-401 should be fixed in the same round. Live items (Ollama, timing, Windows tray, UI publish, restart effect) are the user's steps and are listed under human verification, not as gaps.

---

_Verified: 2026-11-09_
_Verifier: Claude (gsd-verifier)_
