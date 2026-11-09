---
phase: "85"
slug: "first-line-service-desk"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-09"
---

# Phase 85 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| portal / API caller -> POST /api/tickets | Ticket text and tags are untrusted; who raised it is decided by the server | per 85-01 threat model |
| service_desk -> Ollama | Ticket text leaves the process only to a loopback model | per 85-01 threat model |
| model reply -> ticket | The reply is untrusted text and never chooses an outcome | per 85-01 threat model |
| server copy -> requester | Notices reach requesters; they must never carry staff-only text or reasons | per 85-02 threat model |
| tray contract | The agent-key boundary between an installed tray and the server | per 85-02 threat model |
| desk code -> autonomy_actions | Desk rows share the decision ledger with security and patch rows | per 85-03 threat model |
| desk request -> gate | A ticket action is decided by the same gate as agent actions but never targets an agent | per 85-03 threat model |
| desk request -> gate | The gate is the single decision function for a post | per 85-04 threat model |
| Activity viewer -> approve, deny, undo routes | People act on desk rows through the Autonomous Ops routes | per 85-04 threat model |
| requester -> ticket text | Fully untrusted, may carry injection, hidden characters and links | per 85-05 threat model |
| tenant admin -> tenant words | Validated at the API (85-11) and matched as literals here | per 85-05 threat model |
| model reply -> requester | The reply is untrusted output (OWASP LLM02) | per 85-06 threat model |
| knowledge base -> retrieval | Only the tenant's own Help desk articles may be cited | per 85-06 threat model |
| backend -> Ollama (loopback) | The only place ticket text leaves the process | per 85-07 threat model |
| desk -> shared VM | One CPU-bound model shares the server with the API and MongoDB | per 85-07 threat model |
| staff -> requester | A comment crosses only when a technician chooses Reply to requester | per 85-08 threat model |
| tenant notification feed | Read by every tenant user unless a notice is tagged | per 85-08 threat model |
| agent token -> /api/agents/{id}/ticket | The tray and the Rust agent share the route and the token | per 85-09 threat model |
| caller identity -> raise-ticket | People, agents and API keys share the route | per 85-09 threat model |
| tray (user session) -> server | Agent key from tray-config.json plus a client-reported Windows user name | per 85-10 threat model |
| server -> tray window | Only the server's projection reaches the window | per 85-10 threat model |
| tenant admin -> settings routes | Writes the switch and the words | per 85-11 threat model |
| settings view -> model probe | A GET triggers a loopback probe | per 85-11 threat model |
| desk -> ticket queue | Hand-offs change the assignee through the tenant's own rules | per 85-12 threat model |
| desk -> requester | The notice is the only hand-off text a requester sees | per 85-12 threat model |
| ticket text -> pipeline | Untrusted input through every stage | per 85-13 threat model |
| model reply -> post | Untrusted output, checked before any requester sees it | per 85-13 threat model |
| portal user -> desk routes | Every caller holds view:dashboard; reporter and staff roles are decided per ticket | per 85-14 threat model |
| article reads | A requester reads knowledge base text without Knowledge Base permission | per 85-14 threat model |
| Knowledge Base editor -> helpdesk routes | Writes articles that requesters will read | per 85-15 threat model |
| gap list -> authors | Shows requesters' questions to people who can edit articles | per 85-15 threat model |
| browser -> settings and undo routes | The UI renders from server flags; the server enforces every permission | per 85-16 threat model |
| background worker -> shared VM | One CPU-bound job at a time on the server that also runs the API and MongoDB | per 85-17 threat model |
| replicas -> lock | Only one runner may generate | per 85-17 threat model |
| control holder -> undo route | Approve-tier permission in a signed-in session | per 85-18 threat model |
| withdrawals -> desk switch | The breaker changes a tenant setting on its own | per 85-18 threat model |
| tray (agent key) -> tray routes | The only enforced requester boundary; the user name is client-reported | per 85-19 threat model |
| browser -> portal desk routes | The UI renders from server flags; the server enforces reporter and staff roles | per 85-20 threat model |
| browser -> Knowledge Base routes | Controls render from server flags; the server enforces manage:ai_risks, view:dashboard and the guard | per 85-21 threat model |
| operator -> live database and model | The script runs on the live server by hand | per 85-22 threat model |
| repository -> released agent | The tray window reaches users only through an agent release the user publishes | per 85-23 threat model |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-85-01 | Spoofing | raised_via | high | mitigate | Stamped by the server from views.is_interactive; create_ticket never reads it from the body (test: api_key and body field ignored) | closed |
| T-85-02 | Elevation of Privilege | registry ticket_answer | high | mitigate | dispatchers ("service_desk",) enforced by gate._step_class (wrong dispatcher refused, no row); ticket ownership checked by desk_gate.ticket_owner_step (cross-tenant and target cases tested); agent_commands() keeps ticket commands out of the agent capability map; the 85-01 pipeline stamps suggestionOnly so approvals.approve can never dispatch a desk row | closed |
| T-85-03 | Information Disclosure | model.py | high | mitigate | Loopback host allow-list; exact tag; a refused client sends nothing (test) | closed |
| T-85-04 | Information Disclosure | retrieval candidates | high | mitigate | Explicit tenantId and helpdesk True filter; global and foreign articles never cited (test) | closed |
| T-85-05 | Tampering | model reply | high | mitigate | Reply parsed by pydantic, cited ids checked against the given set before any row; full checks in 85-06 | closed |
| T-85-06 | Information Disclosure | NOTICE_TITLE, HANDOFF_NOTICE | medium | mitigate | Generic texts with the ticket number only; hand-off reasons exist only in STAFF_REASON_LABELS (staff-only) | closed |
| T-85-07 | Tampering | starter articles | medium | mitigate | No URL, email, phone or vendor name in any starter (test), so D-19 output checks can never allow a foreign link from a starter | closed |
| T-85-08 | Repudiation | tray contract drift | medium | mitigate | Every contract value pinned by a literal test; the script (85-10) and routes (85-19) are tested against the module | closed |
| T-85-09 | Denial of Service | shared rate pool | high | mitigate | Separate servicedesk pool; the default pool excludes desk rows (test with 20 rows each way) | closed |
| T-85-10 | Denial of Service | Phase 81 breaker | high | mitigate | recent_finished_auto excludes kind servicedesk (test: three undone desk rows, level unchanged) | closed |
| T-85-11 | Repudiation | hand-offs and draft actions | medium | mitigate | record_desk_event and set_desk_fields mirror every write to the hash-chained audit ledger with the actor | closed |
| T-85-12 | Elevation of Privilege | approvals.approve on a draft | high | mitigate | Desk rows refused desk_draft (plus suggestionOnly); drafts are sent only by a person on the ticket (test) | closed |
| T-85-13 | Tampering | gate.execute with a ticket command | high | mitigate | dispatch_check.bind refuses target_kind ticket for every row (invariant test) | closed |
| T-85-14 | Denial of Service | desk hourly limit | medium | mitigate | Separate pool escalates to suggest, never to an approval card, never pages (test asserts no notifications or on-call documents) | closed |
| T-85-15 | Elevation of Privilege | undo without a handler | medium | mitigate | Refused not_undoable, nothing written (fail closed) | closed |
| T-85-16 | Tampering | prompt injection via ticket | high | mitigate | HTML, links, hidden characters and forged delimiters removed before the prompt; the prompt states ticket text is data (tests) | closed |
| T-85-17 | Information Disclosure | sensitive tickets reaching the model | high | mitigate | Sensitive, account-access and ask-for-a-person rules run before the model (escalation set) | closed |
| T-85-18 | Denial of Service | regular expressions | medium | mitigate | Patterns built only from escaped literals; ticket text is never compiled as a pattern | closed |
| T-85-19 | Information Disclosure | exfiltration links in answers | high | mitigate | Every link, email, phone and command must occur in a cited article (fixture set) | closed |
| T-85-20 | Tampering | hallucinated answer | high | mitigate | Cut-off plus minimum matched terms gate the model call; cited ids must be among those given | closed |
| T-85-21 | Information Disclosure | cross-tenant or platform articles | high | mitigate | Candidate query filters tenantId and helpdesk True; mongo isolation test | closed |
| T-85-22 | Information Disclosure | ticket text to a cloud model | high | mitigate | Structural import ban plus loopback host allow-list (tests) | closed |
| T-85-23 | Spoofing | mock or scratch provider answering | high | mitigate | The desk never imports a provider module; exact-tag probe only (tests) | closed |
| T-85-24 | Denial of Service | CPU and memory of the VM | medium | mitigate | num_thread = cores - 1, memory check before a cold load, 503 and timeouts mapped to busy | closed |
| T-85-25 | Denial of Service | unbounded generation | medium | mitigate | num_predict cap, read timeout plus asyncio.wait_for, bounded by 300 s | closed |
| T-85-26 | Information Disclosure | comment notice previews | high | mitigate | Staff-only notices carry no preview and exclude the reporter (test) | closed |
| T-85-27 | Information Disclosure | tenant-wide feed | medium | mitigate | metadata.recipient filter in get_notifications (test with two users) | closed |
| T-85-28 | Tampering | visibility field | medium | mitigate | Literal-validated at the API; refused where no requester can see it | closed |
| T-85-29 | Information Disclosure | portal ticket reads | low | accept | D-11: staff with ticket access already see every comment; the portal requester panel is a presentation, the tray routes (85-19) are the enforced boundary | closed |
| T-85-30 | Spoofing | legacy tray claim | medium | mitigate | A spoofed tray claim can only produce a draft (myTickets False); answers still need a matching article | closed |
| T-85-31 | Spoofing | API keys and agents on raise-ticket | medium | mitigate | Only a non-agent interactive caller is portal_agent (tests) | closed |
| T-85-32 | Denial of Service | queue flooding by automation | medium | mitigate | Automation is never enqueued; queue caps in 85-17 | closed |
| T-85-33 | Elevation of Privilege | stopped tenant | high | mitigate | A stop (or an unreadable stop) means no job (test) | closed |
| T-85-34 | Spoofing | Windows user name | low | accept | D-34: the agent key proves the computer and the user name is soft privacy between people on one shared PC; the footnote never claims privacy (R9); stated again in UAT | closed |
| T-85-35 | Tampering | script execution | high | mitigate | No dynamic code execution or downloads in either script (static test); scripts written by the agent running as SYSTEM to ProgramData as today | closed |
| T-85-36 | Denial of Service | polling load | low | mitigate | 30 s only for 3 minutes after raising, then 5 minutes only while an open ticket exists; 10 s request timeout | closed |
| T-85-37 | Information Disclosure | tray-seen.json | low | accept | Holds answer ids only, in the user's own LOCALAPPDATA | closed |
| T-85-38 | Elevation of Privilege | switch to Post answers | high | mitigate | manage:autonomous_ops plus an interactive session; API keys and Platform Support refused; real-app role probe | closed |
| T-85-39 | Tampering | tenant words | medium | mitigate | Count, length and character allow-list at the API; matched as escaped literals (85-05) | closed |
| T-85-40 | Repudiation | settings changes | medium | mitigate | One control row and audit event per change naming the person | closed |
| T-85-41 | Denial of Service | status probe | low | mitigate | 2 s probe timeout and the 15 s availability cache (85-07) | closed |
| T-85-42 | Information Disclosure | hand-off reason | medium | mitigate | Reason only in the staff note and ledger; the requester notice is a fixed sentence (test) | closed |
| T-85-43 | Denial of Service | paging storm | medium | mitigate | No on-call call and no SLA escalation from a hand-off (test) | closed |
| T-85-44 | Information Disclosure | gap text | medium | mitigate | Only the cleaned question (links and emails removed), 300 characters, 90-day TTL; read access needs two permissions (85-15) | closed |
| T-85-45 | Repudiation | hand-offs | low | mitigate | One audited ledger row per hand-off | closed |
| T-85-46 | Elevation of Privilege | injection triggering actions | high | mitigate | No tools, no queue writes, outcomes chosen by rules and the gate; injection set asserts no queue document and no status change beyond open and pending_customer | closed |
| T-85-47 | Tampering | ticket changes from model text | high | mitigate | The pipeline reads only answer and cited; status and assignee are never derived from the reply (extra-keys test) | closed |
| T-85-48 | Information Disclosure | exfiltration through answers | high | mitigate | D-19 checks against cited articles only (injection set compliant stand-in) | closed |
| T-85-49 | Denial of Service | slow or absent model | medium | mitigate | Offline and busy hand-offs, sized timeouts, nothing waits on the model forever | closed |
| T-85-50 | Repudiation | stop pressed during generation | medium | mitigate | The gate's refused row is recorded; the draft is staff-only and its sending is a recorded person's action | closed |
| T-85-51 | Information Disclosure | article route browsing | high | mitigate | Only ids cited on that ticket, tenant-scoped, never global (tests with uncited, global, cross-tenant ids) | closed |
| T-85-52 | Elevation of Privilege | requester sending their own draft | medium | mitigate | The reporter is refused the draft routes; drafts hidden from the reporter's view | closed |
| T-85-53 | Tampering | racing actions | medium | mitigate | Compare-and-set on the comment state and ticket status; concurrent sends give one winner | closed |
| T-85-54 | Repudiation | sent drafts | low | mitigate | sentBy, approval.approver and an audit event per send and discard | closed |
| T-85-55 | Information Disclosure | portal requester panel | low | accept | D-11: on the portal the panel is a presentation; staff with ticket access already see every comment; the tray routes are the enforced boundary | closed |
| T-85-56 | Information Disclosure | gap list | high | mitigate | Both view:dashboard and manage:ai_risks checked in the route (D-27), plus the router guard; cleaned text only (tests) | closed |
| T-85-57 | Tampering | global platform articles | high | mitigate | Every write is filtered on the caller's tenant; global ids answer 404 | closed |
| T-85-58 | Tampering | duplicate starters | low | mitigate | Unique (tenantId, starterKey) index and setOnInsert upserts (race test) | closed |
| T-85-59 | Denial of Service | huge articles | low | mitigate | 20000-character cap on Help desk content and edits | closed |
| T-85-60 | Elevation of Privilege | client-side gating | medium | mitigate | Controls render from canManage, canRestore and canUndo only; the routes enforce manage and control (85-11, 85-04) | closed |
| T-85-61 | Tampering | accidental posting | medium | mitigate | Post answers and Restore need a confirm dialog with the readiness list (UI-SPEC section 2) | closed |
| T-85-64 | Denial of Service | queue starvation by one tenant | medium | mitigate | Per-tenant cap 10, global cap 30, both handed off busy at once (tests) | closed |
| T-85-65 | Denial of Service | crashed or hung generation | medium | mitigate | Stale running recovery, the lock's TTL and renewal, sized timeouts | closed |
| T-85-66 | Tampering | late answers | high | mitigate | Deadline checked before generating and after the reply; a late answer is discarded (test) | closed |
| T-85-67 | Repudiation | returns | low | mitigate | Each return is a ledger hand-off row and a row desk event | closed |
| T-85-68 | Denial of Service | withdrawal abuse disabling the tenant | medium | mitigate | Desk-only breaker; the tenant level and security response are untouched; restore needs manage (test) | closed |
| T-85-69 | Information Disclosure | withdrawn answer still visible | medium | mitigate | Requester projection shows the notice only; staff keep the original (test) | closed |
| T-85-70 | Repudiation | withdrawals and trips | low | mitigate | Ledger transition with the person, control row for the trip, audit mirror | closed |
| T-85-71 | Information Disclosure | staff-only content to the tray | high | mitigate | Explicit tray_view projection from requester-visible comments only; leak test on drafts and staff notes | closed |
| T-85-72 | Spoofing | another computer's tickets | high | mitigate | verify_agent_key binds the path agent to the token; every query filters tenantId and agent_id | closed |
| T-85-73 | Information Disclosure | another Windows user on one PC | low | accept | D-34: soft scoping by the reported user name; a local user who can read tray-config.json could ask for another user's list; stated in the UAT and never claimed as private | closed |
| T-85-74 | Information Disclosure | article browsing | medium | mitigate | Only articles cited on the caller's own visible answer | closed |
| T-85-75 | Denial of Service | tray polling | low | mitigate | Rate limits 30 and 10 per minute per agent; 20-ticket, 60-day list | closed |
| T-85-76 | Information Disclosure | staff text sent to the requester by mistake | medium | mitigate | Staff only is the default and resets after every send; the info line names who will see a reply | closed |
| T-85-77 | Information Disclosure | portal requester panel | low | accept | D-11: a presentation on the portal; staff with ticket access already see every comment; the tray routes are the enforced boundary (85-19) | closed |
| T-85-78 | Information Disclosure | gap tab shown to a Knowledge Base-only user | medium | mitigate | Rendered only with canSeeGaps; the route checks both permissions (85-15) | closed |
| T-85-79 | Tampering | secrets in Help desk articles | low | mitigate | The dialog's helper tells authors not to put secrets, passwords or internal notes in a Help desk article | closed |
| T-85-80 | Information Disclosure | ticket text in --calibrate | medium | mitigate | Loopback model only; prints scores and terms, never ticket text beyond the cleaned first 80 characters | closed |
| T-85-81 | Tampering | live database writes | medium | mitigate | Only --measure writes, one runtime document; --dry-run and the other modes write nothing (tests) | closed |
| T-85-82 | Denial of Service | CPU during measurement | low | accept | Sequential calls only; the operator runs it at a quiet time and watches API latency (docstring) | closed |
| T-85-85 | Tampering | user WIP shipped with the version commit | medium | mitigate | Only the two version lines are staged; the user decides on the uncommitted Rust work before building (live list step 0) | closed |
| T-85-86 | Repudiation | unverified live behaviour | medium | mitigate | Every live-only check is an ordered user step in the SUMMARY; verification marks them human_needed until done | closed |
| T-85-SC | Tampering | dependencies (all 23 plans) | low | accept | No package is installed (85-RESEARCH Package Legitimacy Audit: scikit-learn and httpx are existing dependencies) | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

Evidence for every row (file:line and pinning test) is in the gsd-security-auditor verdict of 2026-11-09, summarised in the audit notes below.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-85-01 | T-85-29 | D-11: staff with ticket access already see every comment; the portal requester panel is a presentation, the tray routes (85-19) are the enforced boundary | planner (85 plan threat model), confirmed by gsd-security-auditor | 2026-11-09 |
| AR-85-02 | T-85-34 | D-34: the agent key proves the computer and the user name is soft privacy between people on one shared PC; the footnote never claims privacy (R9); stated again in UAT | planner (85 plan threat model), confirmed by gsd-security-auditor | 2026-11-09 |
| AR-85-03 | T-85-37 | Holds answer ids only, in the user's own LOCALAPPDATA | planner (85 plan threat model), confirmed by gsd-security-auditor | 2026-11-09 |
| AR-85-04 | T-85-55 | D-11: on the portal the panel is a presentation; staff with ticket access already see every comment; the tray routes are the enforced boundary | planner (85 plan threat model), confirmed by gsd-security-auditor | 2026-11-09 |
| AR-85-05 | T-85-73 | D-34: soft scoping by the reported user name; a local user who can read tray-config.json could ask for another user's list; stated in the UAT and never claimed as private | planner (85 plan threat model), confirmed by gsd-security-auditor | 2026-11-09 |
| AR-85-06 | T-85-77 | D-11: a presentation on the portal; staff with ticket access already see every comment; the tray routes are the enforced boundary (85-19) | planner (85 plan threat model), confirmed by gsd-security-auditor | 2026-11-09 |
| AR-85-07 | T-85-82 | Sequential calls only; the operator runs it at a quiet time and watches API latency (docstring) | planner (85 plan threat model), confirmed by gsd-security-auditor | 2026-11-09 |
| AR-85-08 | T-85-SC | No package is installed (85-RESEARCH Package Legitimacy Audit: scikit-learn and httpx are existing dependencies) | planner (85 plan threat model), confirmed by gsd-security-auditor | 2026-11-09 |

*Accepted risks do not resurface in future audit runs.*

---

## Audit Notes (2026-11-09, gsd-security-auditor, ASVS L1)

- **Result:** SECURED. 83 unique threats (105 register rows, with T-85-SC repeated per plan): 75 mitigations verified in code, 8 accepted with rationale. Nothing is open at any severity.
- **Test evidence:** the auditor ran 353 pure and DB-light desk tests green. 108 DB-backed tests could not run in its sandbox (fixture `PermissionError: /var/lib/omni-platform`, because `TICKET_ATTACHMENT_DIR` was unset). For those, the 85-23 full-gate run on the final code is the pass evidence: backend 1,955 passed, vitest 1,840.
- **Residual (T-85-77, accepted):** no requester-facing route built in this phase returns staff-only or draft text: the requester block of `GET /api/tickets/{id}/service-desk`, the article, confirm and help routes, and the tray routes. The legacy ticket JSON (`GET /api/tickets/{id}`, the list, `PATCH`, and `POST /comments` returning the full ticket) still carries every comment to any tenant user with ticket access, the reporter included. That includes `ai_draft` text, staff-note reason labels and `desk.lastReason`/`draftReason`. This exposure existed before D-11 and is accepted there. Redacting it server-side would be a follow-up.
- **Residual (85-08 notification fix):** `notification_service.send_alert` blanks `message` on the WebSocket push whenever `metadata.recipient` is set, and stored notices carry no message. Titles and metadata still go tenant-wide: comment titles are `[TKT-n] New comment by {author}`, and metadata includes the recipient address and ticket id. The @mention path puts a 120-character comment preview in the mentioned person's own feed, even for a staff-only comment, because mentioning someone is a deliberate act.
- **T-85-02 note:** `registry.agent_commands()` has no production caller; it is pinned by tests only. The enforced controls are `dispatch_check.bind`, which refuses every ticket command, `gate._step_class` and `approvals.approve`.
- **T-85-30 note:** a spoofed legacy tray claim needs that agent's own token. It yields `raised_via=tray` with `myTickets False`, so it can never be posted, listed or acted on through the tray. The cost of a spoof is one queued job, bounded by the queue caps.
- **Hardening suggestion (not a register item, unverified):** `service_desk/model.py` builds `httpx.AsyncClient` without `trust_env=False`. A process-level `HTTP(S)_PROXY` without `NO_PROXY=127.0.0.1` could therefore route the loopback model call through a proxy.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-09 | 83 | 83 | 0 | gsd-security-auditor (sonnet), ASVS L1, block_on high |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-09

## Security Audit 2026-11-09

| Metric | Count |
|---|---|
| Threats found | 83 |
| Closed | 83 |
| Open | 0 |
