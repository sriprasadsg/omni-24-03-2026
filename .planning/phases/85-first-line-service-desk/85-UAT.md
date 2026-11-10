---
status: complete
phase: 85-first-line-service-desk
source: [85-VERIFICATION.md]
started: 2026-11-09T23:35:31Z
updated: 2026-11-10T08:46:44.976Z
---

## Current Test

[testing complete]

## Tests

### 1. Install Ollama and pull llama3.2:3b, then run the 85-22 measurement/calibration script on the CPU-only server
expected: Real generation times recorded; call timeouts and the retrieval cut-off hold; DESK-05 real response time is reported
result: pass
note: "Run on Omniai-copy 2026-11-10 at the user's request. Ollama 0.40.16 (release archive, sha256 checked) as ollama.service on 127.0.0.1:11434, NUM_PARALLEL=1, MAX_LOADED_MODELS=1; llama3.2:3b pulled. --measure stored system_settings type service_desk_runtime: prefillTps 71.4, genTps 14.4, median total 9.36 s, p95 16.48 s, first load 5.1 s; 4,000-char prompt timeout 45 s. --sets exit 0: escalation 150/0 failed, injection 33 (25 reached the model, 8 handed off before it), 0 failed, retrieval 100/0 unexpected, margin 0.2268 (CUT 0.24). --calibrate: no tenant had Help desk articles (fresh DB), nothing to calibrate. Finding (minor): running --measure right after --measure --dry-run, as the documented order says, stores prefill ~7,000 tok/s from Ollama's prompt cache; re-measured after an Ollama restart. The script should unload the model (keep_alive 0) before measuring."

### 2. Restart the backend (migration 032 and the new manage:tickets role defaults) with Ollama absent and open a new first-line portal ticket
expected: Ticket handed to a person (service_desk_offline); no placeholder answer is posted; a user-role account sees only its own tickets, an analyst sees all
result: pass
note: "Run by Claude against the live API on Omniai-copy 2026-11-10 at the user's request (the user's browser never reached this VM). Backend restarted 08:10:16 (migrations 031 + 032 applied, clean start); UI index-fZpr5iK1.js published by the user. ABC got the 4 starter articles (uat-setup) and switches manage:settings, screen:internalTickets, screen:knowledgeBase, view:autonomous_ops (left on for test 3). Temporary ABC accounts uat85-requester (User) and uat85-analyst (Analyst) signed in via /api/auth/login. With ollama.service stopped, the requester's Incident 'I forgot my password' (TKT-0001, raised via portal) -> desk job done, reason service_desk_offline; comments = staff_note 'Service desk: service desk offline.' (staff) + handoff_notice 'A person from IT will look at this.' (requester); no answer or placeholder. Requester sees 1 comment, analyst 2. With a 2nd ticket raised by the analyst: requester lists 1 (own), analyst lists 2, requester opening the analyst's ticket -> 404. Ollama restarted. Test accounts, tickets, desk jobs, autonomy_actions, notifications and login_events archived to ~/omni-archives/uat85-test2/ and removed; 8 hash-chained audit_logs entries left in place."

### 3. Portal round trip and Windows tray round trip (agent 2.1.18 published): requester sees the AI-assisted answer, confirms or says it did not help
expected: Confirm closes the ticket; did-not-help hands off to a person; the reporter never sees staff-only comments or drafts in the browser
result: issue
reported: "Found by Claude in the portal run (user asked for it to be run via the API): a printer ticket ('My printer will not print') is always handed to a person with output_check_failed. Reproduced 3/3 offline: llama3.2:3b replies cited [1,2,3,4,5,6] for the one given article, reading the printer starter's numbered steps 1-6 as article numbers, so check() fails unknown_citation. The pipeline also drops the failing check name and the model reply, so staff only see 'Output check failed.'"
severity: major
note: "Portal half otherwise PASSED on the live API + published UI (index-fZpr5iK1.js) with temporary ABC accounts, desk mode drafts: password ticket drafted citing 'How to reset your own password'; requester saw nothing before the analyst sent it; after send the requester saw the ai_answer (status pending_customer, confirm offered); 'this fixed it' -> resolved; a second password ticket, sent then 'I still need help' -> status open, phase helped, staff_note for staff only. No staff_note or unsent draft was ever returned to the requester; in headless Chromium the requester's ticket view and Comments tab show only the sent answer (screenshots in ~/omni-archives/uat85-test3/). First run was invalid (agent build saturating the CPU -> 45 s model timeouts -> service_desk_busy hand-offs, nothing posted). Tray half NOT run: agent 2.1.18 built from cde304879 (sha256 4db385d7..., ~/omni-archives/agent-2.1.18/) but not published, and no Windows endpoint is enrolled on this VM. Copy nit: the requester's Comments tab shows the staff hint 'Comments are visible to staff only unless marked Sent to requester'."

### 4. Sign in as a requester (role user) on the published Tickets screen
expected: Only own tickets listed; staff actions that now answer 403 (assign, merge, bulk, watchers) are either hidden or fail with a clear message (IN-604: no frontend code reads manage:tickets)
result: issue
reported: "Found by Claude in headless Chromium on the published UI as a temporary ABC User-role requester: own-tickets listing is correct (3 own listed; the analyst's TKT-0004 not listed and 404 when opened), but the ticket panel shows staff controls (-> in progress / -> resolved / -> closed, Escalate with reason box, Add watcher, Work Log tab, row checkboxes for bulk) and they fail silently: PATCH /api/tickets/{id} 403, POST /escalate 403, POST /watchers 403, each only a console 'Failed to load resource: 403' with nothing shown to the user. Merge is disabled."
severity: major

### 5. Decide on WR-603 (requester-set staff fields at ticket creation) and WR-602 (WebSocket push of audience-tagged notices) before deployment
expected: Either the fix (drop staff-only keys for non-staff in create_ticket; skip the tenant broadcast when metadata.audience is set) or a written acceptance
result: issue
reported: "Fix both (Recommended) — fix WR-603 and WR-602 in this round together with G-85-3 and G-85-4b"
severity: major

## Summary

total: 5
passed: 2
issues: 3
pending: 0
skipped: 0
blocked: 0

## Gaps

# G-85-4 is taken by the second gap round (85-30..85-36); this round's test-4 gap is G-85-4b.
- gap_id: G-85-3
  truth: "A new first-line ticket that matches one Help desk article gets a usable AI-assisted answer or draft; a citation the model gets wrong does not throw away an otherwise grounded answer, and a refused answer records which check failed"
  status: failed
  reason: "Found in UAT: printer starter answers are always refused (unknown_citation: model cites the article's step numbers 1-6 as article numbers); pipeline drops the check name and reply"
  severity: major
  test: 3
  artifacts: []  # Filled by diagnosis
  missing: []    # Filled by diagnosis
- gap_id: G-85-4b
  truth: "A requester (no manage:tickets) on the Tickets screen does not see staff-only controls (status transitions, escalate, watchers, work log, bulk, assign, merge), or any such action they can reach fails with a clear message instead of a silent 403"
  status: failed
  reason: "Found in UAT: staff controls shown to a User-role requester; PATCH, escalate and watchers answer 403 with nothing shown"
  severity: major
  test: 4
  artifacts: []  # Filled by diagnosis
  missing: []    # Filled by diagnosis
- gap_id: G-85-5
  truth: "A requester creating a ticket cannot set staff-only fields (assignee, assignee_group, watchers, approval_required, sla_hours, due_date, also via template defaults), and a notice tagged with an audience (tenant_admins, ticket_staff) is never pushed over the tenant-wide WebSocket broadcast, including pending_agents._post_in_app"
  status: failed
  reason: "User reported: Fix both (Recommended) — fix WR-603 and WR-602 in this round together with G-85-3 and G-85-4b"
  severity: major
  test: 5
  artifacts: []  # Filled by diagnosis
  missing: []    # Filled by diagnosis
