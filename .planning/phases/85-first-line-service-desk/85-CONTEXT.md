# Phase 85: First-Line Service Desk - Context

**Gathered:** 2026-11-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 85 adds a first-line service desk to Autonomous Ops. A ticket that a person raises gets one attempt at an answer drafted from the tenant's own help-desk articles, with the articles cited. Fixed rules decide whether the answer is posted, kept as a staff draft, or skipped so the ticket goes to a person. The model only writes the reply text; it never chooses an outcome and never triggers an action.

The phase delivers:
- the service desk sweep: one ticket at a time, local model only, with a queue limit and per-call timeouts sized from the measured CPU speed
- the escalation rules (no matching article, sensitive topic, the requester asks for a person, the model is unavailable or only the mock provider is active, non-English, output checks fail, queue limit reached)
- the requester loop: "This fixed it" / "I still need help" in the portal and in a new tray "My tickets" window, a three-working-day return to a person, and no automatic close
- staff drafts (send, edit, discard), a "reply to requester" comment flag, and Undo on a posted answer
- a per-tenant service desk switch, tenant-added sensitive words and a status line in the Autonomous Ops settings panel
- a "Help desk" mark on knowledge base articles, the knowledge-gap list and the starter IT articles on the Knowledge Base screen
- prompt-injection, escalation and retrieval test sets

Requirements: DESK-01..07 (7). Depends on Phase 81 (level, gate, ledger, stop). Independent of Phases 82-84. Tenants stay in shadow until a Super Admin lifts them (Phase 81 D-02, D-03), so posting needs that lift as well as this phase's switch.

Live validation is the user's step: install Ollama, pull `llama3.2:3b`, measure real response time, calibrate on a real knowledge base, publish the agent release that carries the tray window, and walk a real ticket round trip. Digest, statistics, export and the stop drill that pauses AI ticket replies are Phase 86. Naming rule: "Autonomous Ops", never "ASI", "Autopilot" or "fully autonomous" (ACTV-08).

</domain>

<decisions>
## Implementation Decisions

### Carried forward, not re-decided
- The model only writes text. Fixed rules choose every outcome, and ticket text can never trigger an action (PROJECT key context, DESK-03).
- Phase 81 rules apply unchanged:
  - levels Off, Suggest and Undoable-auto;
  - an unticked Autonomous Ops screen means Off, and nothing is recorded (D-23);
  - unreadable settings mean Suggest;
  - per-tenant shadow is on by default, and only a Super Admin lifts it (D-02, D-03);
  - the Platform tenant is never eligible (D-04);
  - stops halt new decisions, and undo still works during a stop (D-12);
  - the ledger records each decision;
  - the 20-automatic-actions-per-hour limit (D-20);
  - the permission strings `view:` / `manage:` / `control:autonomous_ops`.
- New tenant settings go in the Autonomous Ops settings panel (Phase 83 D-22) and need the manage permission. Every change is recorded in the ledger and the audit chain.
- Research decision D18 (`.planning/research/SUMMARY.md`) is settled by D-29 below.

### Which tickets get an answer
- **D-01:** Only tickets **a person raised** get an attempt:
  - portal tickets created in an interactive session;
  - tray "Raise a Ticket" tickets.

  Tickets that automation creates are never answered: agent `create_ticket` instructions, the ITAM ticketing bridge, Jira/ServiceNow echoes, compliance tasks and API-key integrations. The sensitive-topic rules in D-23 still apply to person-raised tickets.
- **D-02:** **Fulfilment requests go straight to a person**: the tray's "Install Software" and "Hardware Request" templates. An article cannot install software or ship hardware. They are not counted in the knowledge-gap list.
- **D-03:** The service desk has **its own per-tenant switch** with three settings:
  - **Off:** no attempt and nothing recorded; tickets flow as today.
  - **Drafts only:** answers become staff drafts.
  - **Post answers:** the answer is posted.

  Every tenant, new and existing, starts at **Drafts only**. "Post answers" posts only when every one of these holds:
  - the tenant level is Undoable-auto;
  - the tenant is out of shadow;
  - no stop is on;
  - the rate limit is not reached;
  - the service desk breaker (D-25) has not tripped.

  Otherwise the answer becomes a draft. In shadow the ledger records "would have posted". Suggest gives drafts, and Off gives nothing. Moving a tenant to Undoable-auto for security response therefore never starts posting ticket answers by itself.
- **D-04:** **One attempt per ticket, new tickets only.** The attempt runs when the ticket is created, and only for tickets created while the switch is above Off. Open tickets that existed before are left alone. A later comment never starts a new attempt: once the requester replies, a person takes over.

### The requester side
- **D-05:** Tray tickets get a **"My tickets" window in the tray app**. It shows the status, posted or sent AI answers with their cited articles, replies sent to the requester, and two buttons: "This fixed it" and "I still need help" (with an optional text box). — **Reversibility:** costly — the tray script `agent-install/omni-agent-rs/scripts/tray_icon.ps1` ships inside the agent, so the window and its backend contract reach users only through an agent release. Publishing it and bumping `_LATEST_AGENT_VERSION` are the user's steps. Older agents never show answers, so their tickets should get drafts, not posts (Claude's discretion below).
- **D-06:** The window lists only tickets raised **from this computer while the same Windows user was signed in**. The agent key proves the computer, and the tray reports the Windows user name. On a shared PC, one user does not see another's tickets.
- **D-07:** **"This fixed it"** resolves the ticket and records the requester's confirmation. **"I still need help"**, or any typed reply, sends the ticket to a person with the answer marked "did not help". There is no second AI attempt. The AI path never closes a ticket. Staff can still resolve or close tickets by hand, as today.
- **D-08:** If the requester never responds to a posted answer, after **3 working days** the ticket goes back to the queue for a person, marked "no reply to AI answer". It is never closed without the requester's confirmation.
- **D-09:** A **draft** sits on the ticket where only staff see it, with **Send as is**, **Edit and send** and **Discard**. A sent draft keeps the "AI-assisted" mark and its citations, records which staff member sent it, and gives the requester the same two buttons.
- **D-10:** Anyone who can **reply on the tenant's tickets** today may send, edit or discard a draft. Sending is a person's choice and needs no MFA-tier approval.
- **D-11:** Comments get a **visibility flag**. Existing comments, and new comments by default, are **staff-only**. A technician chooses **"Reply to requester"** to send one to the requester. The requester view (the tray window and the requester's confirm panel on a portal ticket) shows only:
  - the status;
  - posted or sent AI answers;
  - replies to the requester.

  AI drafts are always staff-only. What staff with ticket access already see does not change. — **Reversibility:** costly — the flag is stored on every new comment, and the tray window's contract reads it, so removing it later needs a data migration and an agent release.
- **D-12:** Requesters are told when an answer arrives:
  - The tray checks for updates while it runs and shows a Windows pop-up ("Your ticket has an answer") that opens "My tickets".
  - Portal requesters get the existing in-app notification.
  - Email is not used in this phase.
- **D-13:** The "AI-assisted" mark reads "AI-assisted answer from your IT knowledge base". The cited article titles appear under it, followed by: "Not right? Choose 'I still need help' and a person will take over."
- **D-14:** Each cited title **expands to that article's text, read-only**, inside the ticket or the tray window. Only articles cited on that requester's own ticket can be opened. This needs no Knowledge Base permission and gives no browsing.

### Model and article matching
- **D-15:** **Local Ollama only.** Ticket text never leaves the server.
  - Cloud providers a tenant configured for other features (Anthropic, Gemini, a 9router/OpenAI-compatible router) are never used for tickets.
  - The experimental from-scratch model (`with_own_model` / `OmniScratchProvider`) is never used for answers.
  - With no local model running, or only the mock provider active, every ticket goes to a person (DESK-04).
- **D-16:** Only the **tenant's own articles** may be cited, starter articles included once copied in (D-29). The shared platform articles (`tenantId: "global"`, the security reference seed: MITRE ATT&CK, OWASP Top 10, ransomware playbook and others) are never cited to a requester.
- **D-17:** Only articles **marked "Help desk"** may be cited. The Knowledge Base screen gets the toggle, and starter articles arrive marked. Compliance text pulled in from framework pages or LLMOps, and analysts' notes, stay out unless someone marks them.
- **D-18:** "No article matches well enough" uses **one fixed, tested cut-off on the search-match score**. It is tuned on the starter articles plus a test set of matching and non-matching tickets, and pinned by tests. Tenants cannot change it. It is tuned later only from measured results. This is a retrieval score, never the model's own confidence (DESK-02).
- **D-19:** **Strict output checks.** Failing any one sends the ticket to a person. The draft must:
  - cite at least one of the articles it was given;
  - stay under a length cap;
  - contain no HTML;
  - contain no links, email addresses, phone numbers or command lines that are not in those cited articles.

  These are fixed rules with no model judgement.
- **D-20:** **English only.** Tickets not detected as English go to a person and are counted separately in the gap list.
- **D-21:** **Queue limit of 10 minutes** from the ticket's arrival, covering queue wait plus generation. If no answer is ready by then, the attempt is dropped and the ticket goes to a person as "service desk busy". A late answer is never posted. Each single generation also has its own timeout, sized from the measured CPU speed (DESK-05).
- **D-22:** When the model is down or only the mock provider is active:
  - the settings panel shows a status line, "Offline: the local model isn't running";
  - each escalated ticket is marked "service desk offline".

  The service desk pages no one itself. On-call paging stays with the Phase 82 watchdog, which already watches Ollama where it is installed.

### Escalation, undo and the gap list
- **D-23:** **Sensitive tickets are spotted by rules, never by the model.** The built-in rules cannot be removed:
  - ticket type `security`;
  - the tray's "Security Concern" and "Access Request" templates;
  - phrase lists for security, billing, legal and account access, and for asking for a person ("talk to a human" and similar).

  A tenant admin (manage permission) can **add their own words** in the settings panel, for example "payroll". Any hit sends the ticket to a person **before the model sees it**.
- **D-24:** A hand-off goes through the **tenant's existing assignment rules**, with a **staff-only note naming the reason**: "no article matched", "billing topic", "requester asked for a person", "service desk offline", "service desk busy", "not English", "output check failed" and so on. The requester gets a reply-to-requester notice: "A person from IT will look at this." The reason itself is not shown to them.
- **D-25:** **Undo on a posted answer** (Autonomous Ops, approve-tier permission, works during a stop per Phase 81 D-12):
  - hides the answer from the requester and replaces it with "This answer was withdrawn; a person will follow up";
  - sends the ticket to a person.

  **Service desk breaker:** 3 withdrawn answers within 24 hours drop that tenant's service desk switch to **Drafts only** until a manage-permission holder restores it. Phase 81's tenant-wide breaker and security response are not affected. A requester's "I still need help" never counts toward it.
- **D-26:** The **knowledge-gap list** is a "Knowledge gaps" section on the **Knowledge Base screen**, where articles are written.
  - Entries: each ticket escalated because no article matched, shown as the stripped question with a link to the ticket.
  - Grouping: nearly identical wording is grouped by plain text similarity, with no model.
  - Actions: **Write article** (title pre-filled) and **Dismiss**.
  - Non-English tickets are counted separately.
  - Fulfilment requests (D-02) and sensitive tickets (D-23) are not gaps.
- **D-27:** Only people who can **both see the tenant's tickets and edit Knowledge Base articles** may see the gap list. Someone with Knowledge Base access alone cannot read requesters' questions.
- **D-28:** **Starter IT articles** (password reset, VPN, printer, agent tray app) are added when an admin presses **"Add starter IT articles"** on the Knowledge Base screen.
  - The button copies them into that tenant's knowledge base as **editable copies marked Help desk**, so a tenant can adapt them to its own VPN client and printers.
  - Pressing it again adds nothing twice.
  - Nothing is seeded automatically.
- **D-29:** Settles D18: the starter articles come from the platform (this phase writes them) and the tenant edits its copies. Answers default to drafts (D-03). The request templates and sensitive categories are fixed rules (D-02, D-23).

### Post-research amendments (2026-11-08, user-approved after 85-RESEARCH.md)
- **D-30 (amends D-03; research Open Question 1):** Posted ticket answers have their **own budget of 20 per hour per tenant**, separate from Phase 81's automatic-action pool. Answers beyond the desk's 20 become drafts. Desk rows never count toward the security rate limit or Phase 81's tenant-wide breaker (D-25 keeps its desk-only breaker).
- **D-31 (Open Question 2):** A posted answer moves the ticket to the existing hold status **`pending_customer`**, which pauses the SLA. "I still need help", a requester reply, an Undo or the three-working-day return (D-08) moves it back to `open` for a person.
- **D-32 (Open Question 3; narrows D-23):** A **self-service password how-to** ("forgot my password, how do I reset it") is answerable from the starter article. Unlocks, MFA resets, access grants, permission changes and suspected account compromise always go to a person. Test cases pin both sides.
- **D-33 (Open Question 4; amends D-12):** The in-app notifications reader (`GET /api/notifications`) gets a **recipient filter**: a notice tagged with a recipient is shown only to that user, and untagged notices behave as today. The existing comment notice must also stop previewing staff-only text to the requester.
- **D-34 (Open Question 5; qualifies D-06):** The Windows user name is **reported by the tray**. The computer's agent key is the boundary, and the user name is soft privacy between people on a shared PC. This is accepted, and the threat model and UAT must say so.
- **D-35 (Open Question 6; settles D-20):** English is detected by a **built-in standard-library heuristic** (script check plus common English words), pinned by test cases. No new dependency.
- **D-36 (Open Question 7; refines D-28):** Starter articles are **generic**: no product or vendor names, no URLs, no phone numbers. Placeholders such as "your company's VPN app" show the tenant what to edit.
- **D-37 (research assumption A5; extends D-23):** A ticket with **`critical` priority always goes to a person**. `high`, `medium` and `low` stay eligible, since the tray's "Report an Issue" defaults to `high`.
- **Research defaults adopted (85-RESEARCH.md; no further user input needed):**
  - **Gate:** `gate.decide` with a `service_desk` dispatcher, registry rows `ticket_answer` (undo `ticket_withdraw`) and `ticket_withdraw`. A ticket-ownership check replaces the protected-targets step for this kind. The decision runs after generation, so a stop pressed during the slow call still blocks the post.
  - **Draft rows** never expire as approvals.
  - **Hand-offs are not gated.** They are the fail-safe direction and are written as direct `servicedesk` ledger rows.
  - **Model client:** a desk-only loopback client in a new `backend/service_desk/` package (LLM imports stay out of `autonomous_ops/`). It sends an exact model tag, an explicit token cap, and a timeout sized from an operator-run measurement, with conservative defaults until that measurement exists.
  - **DESK-04:** the model is unavailable when `/api/tags` fails or the tag is missing.
  - **Retrieval:** TF-IDF cosine similarity over the tenant's Help desk articles (scikit-learn, already a dependency), plus a minimum of matched content terms. The cut-off is re-pinned on the real starter articles by fixture tests.
  - **"Raised by a person"** is recorded by the server at creation (`raised_via`). The new tray uses a new route and announces its `my_tickets` support. Old trays keep the legacy route, and their answers become drafts.
  - **Migration 032** only creates indexes. A missing desk setting reads as Drafts only, and a missing comment visibility reads as staff-only.

### UAT amendments (2026-11-09, gap G-85-4, user-approved in 85-UAT.md)
- **D-38 (UD-1; amends D-10 and D-11: who counts as staff):** Ticket staff is a new permission, **`manage:tickets`**. Built-in holders are tenant_admin, analyst, security_analyst and incident_responder; the Super Admin has it through `*`. The built-in roles `user` and `viewer` are requesters only, and `platform_support` gets no ticket-staff access.
- **D-39 (UD-2; amends D-10 and D-11):** Staff is required to send, edit or discard an AI draft and to open the cited-article reader, and also for bulk update, merge, approve, reject, escalate, work-log and watchers. Requesters keep comment, attach and confirm on their own tickets. Anyone who is neither staff nor the reporter gets 404 on a ticket and on the desk routes, and ticket lists, stats and reports show them only their own tickets.
- **D-40 (UD-3):** Custom tenant roles from Phase 77 start as non-staff (fail closed). No migration grants `manage:tickets`; tenant admins tick it on technician roles in the role editor.
- **D-41 (UD-4; amends D-33):** The Super Admin keeps the cross-tenant view of notice history, but the history route applies the same audience filter as everyone else (recipient, excludeRecipients, tenant_admins, ticket_staff). Without a tenant a non-Super-Admin gets 403, and a notice that carries only a tenantId is handled by the shared filter.

### UAT amendments (2026-11-10, gap G-85-5, user-approved in 85-UAT.md)
- **D-42 (UAT test 5, WR-603; amends D-39):** Someone who is not ticket staff cannot set the assignee, group, watchers, approval, SLA hours or due date when creating a ticket, also not through a template. The server drops them and the queue rules route the ticket.
- **D-43 (UAT test 5, WR-602; amends D-33 and D-41):** A notice addressed to an audience is read from the feed only and never pushed on the tenant-wide socket. The pending-agent notices are included.

### Claude's Discretion
- How the answer is registered with the gate (a non-agent action kind such as `ticket_comment` in `autonomous_ops/registry.py`), and the ledger `kind: servicedesk` row shape, as long as every attempt, draft, post, hand-off and undo is a ledger row and the gate's stop, level, shadow and rate-limit steps apply. Steps that only make sense for agent targets (protected targets, blast radius) may be skipped for this kind, with a test.
- How "raised by a person" is detected: by creation path, not by client-supplied tags alone. The tray sends `user-raised` and `tray` itself, and `RaiseTicketRequest` accepts any tags.
- Portal ticket types other than `security`: `task`, `bug` and `incident` are eligible. Treat `feature` like a fulfilment request (straight to a person, not a gap) unless research finds a reason not to.
- What happens to tickets created during a stop or with the switch Off: no attempt. They follow the normal assignment flow, and the D-24 notice may be skipped when the desk was simply off.
- When a tray ticket comes from an agent too old to have the "My tickets" window: its answer becomes a staff draft rather than a post, because the requester cannot see it.
- The retrieval engine (`knowledge_docs` text search versus the ChromaDB `rag_service`), how many articles to cite (up to 3 suggested), the length cap, the language detector (no heavy new dependency), the similarity method for gap grouping, and the phrase lists themselves. The test sets pin all of these.
- What "working days" means for D-08: Monday to Friday in the tenant's time zone if one is stored, otherwise UTC, with no holiday calendar.
- The tray's polling interval and the agent-key route shape for "My tickets", scoped to agent id plus the Windows user name.
- Limits on tenant-added words (count, length, characters), with validation at the API boundary.
- Undo stays available until the requester confirms or a person replies.
- Where the measured response time is shown (DESK-05). The suggestion is the status line in the settings panel, as the median of recent attempts with generation time stored on each ledger row.
- Layout and copy of the drafts, the requester panel, the tray window, the settings rows and the gap list, subject to the Spatial Glass design system, a `/gsd-ui-phase 85` contract and ACTV-08.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope and research
- `.planning/REQUIREMENTS.md` — DESK-01..07 and the v4.3 Out of Scope table
- `.planning/ROADMAP.md` — the "Phase 85" block: goal, success criteria, research flag (measure `llama3.2:3b` CPU tokens per second, calibrate the retrieval threshold, build injection and escalation eval sets), and the live-only verification list
- `.planning/research/SUMMARY.md` — the Phase 85 delivery list and decision D18 (settled here by D-03, D-29)
- `.planning/research/ARCHITECTURE.md` — the "Service desk" sweep sketch, the `ticket_comment` / `ticket_resolve` registry rows, `kind: servicedesk` ledger rows, the Ollama concurrency-1 note
- `.planning/research/PITFALLS.md` — Pitfall 21 (prompt injection through ticket text), Pitfall 22 (hallucinated first-line answers), Pitfall 31 (Ollama as a shared-resource hazard)
- `.planning/research/FEATURES.md` — Category 5 (service desk) table-stakes and anti-features, the Ollama-down degradation mode

### Prior phase decisions that constrain this phase
- `.planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-CONTEXT.md` — D-01..D-25: levels, shadow, stops, breaker, rate limit, permissions, Platform tenant never eligible
- `.planning/phases/83-autonomous-security-response/83-CONTEXT.md` — D-22 settings panel, the ledger/audit recording of setting changes
- `.planning/phases/82-platform-self-healing-scheduled-retention/82-CONTEXT.md` — watchdog and on-call channel; it already probes Ollama (D-22 relies on it)

### Code the phase changes or must respect
- `backend/tickets_service.py`, `backend/tickets_endpoints.py`, `backend/tickets_models.py` — ticket create, `add_comment` (no visibility flag today), `auto_assign`, statuses (`pending_customer` is a hold status)
- `backend/tickets_escalation_service.py`, `backend/tickets_config_mixin.py` — escalation and queue rules the hand-off reuses
- `backend/agent_tasks_endpoints.py` — `POST /api/agents/{agent_id}/ticket` (tray path, `verify_agent_key`, reporter = agent id, `ticket_reporter` capability) and the interactive agent-ticket route
- `agent-install/omni-agent-rs/scripts/tray_icon.ps1` — tray menu, ticket templates (lines ~91-96), `Get-EndpointInfo` (Windows user name), error-text helper; the "My tickets" window goes here
- `backend/knowledge_endpoints.py` — `knowledge_docs` (text index, `tenantId` or `"global"`), `_SEED_DOCS` (security-only), ingest/query/list/delete routes
- `backend/rag_service.py` — ChromaDB store with tenant metadata (an alternative retrieval engine)
- `backend/ai_service.py`, `backend/ai_providers.py` — provider selection per tenant, `MockProvider`, `OllamaProvider` (`llama3.2:3b` default, httpx timeouts); `backend/ai_services/omni_scratch_provider.py` — `with_own_model` wrapping, which must be bypassed (D-15)
- `backend/autonomous_ops/` — `gate.py` (`decide`, `suggest`, steps), `registry.py` (action table), `ledger.py`, `breaker.py`, `stop.py`, `settings.py`, `response_settings.py` (Phase 83 panel settings)
- `backend/autonomous_ops_endpoints.py`, `components/AutonomousOpsResponseSettings.tsx`, `services/autonomousOpsApi.ts` — the screen and panel this phase extends
- `components/InternalTicketsDashboard.tsx` — ticket view (drafts, reply-to-requester, requester confirm panel)
- `components/KnowledgeBaseDashboard.tsx` — Help desk toggle, gap list, starter-articles button
- `backend/feature_catalog.py` (`tickets` → `view:tickets`, `knowledge_base` → `view:knowledge_base`), `backend/rbac_defaults.py`, `shared/catalogue-access.json` — permissions and route registration

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 81 gate, ledger, stop, breaker and rate limit: the desk is a new caller, with its own kind.
- Phase 83 settings panel (`response_settings.py`, `AutonomousOpsResponseSettings.tsx`): where the switch, the tenant words and the status line go.
- `tickets_service.auto_assign` and the queue rules: the hand-off path (D-24).
- `knowledge_docs` with a text index and tenant scoping already in place; the ingest route for starter copies.
- The existing in-app notification path (`ticket_notifications`): the portal requester notice (D-12).
- `OllamaProvider` plus the `MockProvider` type check, for the DESK-04 guard.

### Established Patterns
- Every route is registered in `shared/catalogue-access.json` and mounted through a `catalogue_mounts_*.py` slice; drift tests fail otherwise.
- Background sweeps set `tenantId` explicitly, reset tenant context per iteration, and run under `lock_with_renewal`.
- Fail closed: an unknown setting, a missing capability, or an unreadable level means no post.
- The real app adds a permission guard that the tests' bare router lacks, so route tests alone do not prove the guard.
- Executors stage only their own hunks: the tree has many unrelated dirty files and user WIP (see the Phase 84 memory notes).

### Integration Points
- Ticket creation (`tickets_endpoints.create_ticket`, `agent_tasks_endpoints.create_ticket_from_agent`) marks a ticket eligible. The desk sweep picks it up asynchronously, one at a time.
- `run_startup_services` in `backend/app_startup.py` starts the desk sweep and the three-working-day return.
- New agent-key routes for the tray window ("My tickets" list, confirm or still-need-help, read a cited article).
- The Knowledge Base screen gets the Help desk mark, the gap list and the starter button.
- What the VM looks like today: Ollama is not installed, and the server is 4 vCPU / 15 GB (the research text says 2 vCPU / 7 GB). Every flow must work with the model absent, which means everything goes to a person.

</code_context>

<specifics>
## Specific Ideas

- Requester copy:
  - "AI-assisted answer from your IT knowledge base"
  - "Not right? Choose 'I still need help' and a person will take over."
  - "A person from IT will look at this."
  - "This answer was withdrawn; a person will follow up."
- Tray pop-up: "Your ticket has an answer", which opens "My tickets".
- Status line: "Offline: the local model isn't running".
- Staff reason labels: "no article matched", "billing topic", "requester asked for a person", "service desk offline", "service desk busy", "not English", "output check failed", "no reply to AI answer", "did not help".

</specifics>

<deferred>
## Deferred Ideas

- Email notification to portal requesters once SMTP is configured
- Answers in languages other than English
- Opt-in use of a tenant's cloud LLM provider for tickets (rejected for this phase in favour of local only)
- Tenant-adjustable match strictness (rejected for this phase in favour of one fixed cut-off)
- AI first-line answers in the tray app's "Chat with IT Support" sessions (not discussed; chat is outside this phase)

</deferred>

---

*Phase: 85-first-line-service-desk*
*Context gathered: 2026-11-08*
