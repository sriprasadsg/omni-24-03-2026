# Phase 54 — REVIEWS (self-review, 2026-07-30)

> Reviewer: claude-self (adversarial; no independent external model available).

## MED — Findings-feed source inconsistency (scan-only endpoint vs scan+vuln+FIM tab)
54-CONTEXT/54-03 say the Findings tab shows scan verdicts + native VULN + FIM, but `54-01`'s `GET /security-ops/findings` only lists `security_scan_results` (scan verdicts), "optionally referencing vuln/fim counts." So the tab must federate three endpoints (findings + `vuln_endpoints` + `fim-events`) with three shapes + three paginations.
**Fix:** decide explicitly — either (a) `GET /findings` aggregates all three server-side into one paginated, normalized feed (cleaner for the UI), or (b) the tab federates three sources with a defined merge/sort/pagination strategy. Pick one in 54-01/54-03; don't leave it split.

## MED — Playbook CRUD store compatibility (cross-ref 53-01 HIGH) — UPDATED 2026-07-30
**Now actionable after the 53 replan:** 53-01 introduced a dedicated `remediation_playbooks` collection + CRUD endpoints (`remediation_playbook_endpoints.py`). So 54-03's Playbooks tab must **target that store**, not the LLM `PlaybookManager`/`enhanced_playbook_endpoints`. When Phase 54 is (re)planned, change 54-03's Playbooks tab to consume the `remediation_playbooks` CRUD (list/create/edit deterministic YAML playbooks) — `PlaybookManager` manages a different (LLM) store and will NOT edit the playbooks the engine runs. Left as a flagged edit for a `/gsd-plan-phase 54 --reviews` pass.

_Original finding:_

INT-03 lists "playbook CRUD" as satisfied by the existing `enhanced_playbook_endpoints`. But those manage the LLM playbook shape; the Phase-53 deterministic YAML playbooks are a different schema. If 53-01 doesn't reconcile them, the console's Playbooks tab (reusing `PlaybookManager`) will not create/edit the deterministic playbooks the engine actually runs.
**Fix:** ensure 53-01's store decision and 54's Playbooks tab target the SAME playbook store/schema. Verify `PlaybookManager` can author deterministic playbooks, or the tab needs a new editor.

## MED — trigger-scan connectivity + async result surfacing
`54-01` trigger-scan dispatches to a possibly-disconnected agent; `54-03` shows a "queued" toast + refresh. But the verdict returns asynchronously (agent → `POST /scan-result`, 50-04) with no push to the UI. Define the refresh/poll cadence and how a queued scan's result appears in the feed, so the operator isn't left staring at "queued."
**Fix:** specify the connectivity check (`websocket_manager.is_agent_connected`?) and a poll/refresh on the findings feed after a trigger.

## LOW — Sidebar icon + placement assumptions
54-04 assumes `ShieldZapIcon`/`ShieldAlertIcon` are already imported in Sidebar; verify at execute (else add the import) — same footgun the 49-05 GlobeIcon import hit.

## Accepted
- Unified console + gate on `manage:active_response`; server enforces the approval gate (UI triggers only) — sound.
- Reuse PlaybookManager + vuln components rather than rebuild — good, PENDING the schema-compat fix above.

## Cross-cutting (v3.4, applies across phases)
1. **Agent Cargo deps are scattered** (yara-x/ed25519-dalek in 50, notify in 52) with implicit ordering — centralize or sequence explicitly.
2. **Windows cross-compile** risk concentrates in the Rust phases (yara-x, notify); gates exist but land late — spike early.
3. **Agent→backend result channel** (needed for 53 verify) is the single biggest unvalidated assumption of the milestone — resolve before executing Phase 53.
