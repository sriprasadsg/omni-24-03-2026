# Phase 85: First-Line Service Desk - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-11-08
**Phase:** 85-first-line-service-desk
**Areas discussed:** Which tickets get answers, Requester sees and confirms, Model and article matching, Escalation/undo/gap list

---

## Which tickets get answers

| Question | Options presented | Selected |
|----------|-------------------|----------|
| Which tickets should the desk try to answer? | Raised by a person (Recommended) / Only some types / Tenant picks | Raised by a person |
| "Install Software" and "Hardware Request"? | Straight to a person (Recommended) / Answer if an article fits | Straight to a person |
| Own switch apart from the autonomy level? | Own switch, starts at drafts (Recommended) / Own switch, follows level / No switch, level only | Own switch, starts at drafts |
| When does a ticket get an attempt? | Once, new tickets only (Recommended) / New tickets plus backlog / Every requester reply | Once, new tickets only |

**Notes:** Automation-raised tickets (agent instructions, ITAM bridge, compliance, API keys) are never answered. Fulfilment requests are not counted as knowledge gaps.

---

## Requester sees and confirms

| Question | Options presented | Selected |
|----------|-------------------|----------|
| How does a tray requester see an answer? | Tray "My tickets" window (Recommended, costly: agent release) / Tray tickets get drafts only / Tray notification only | Tray "My tickets" window |
| What do the two choices do? | Fixed closes, else a person (Recommended) / One retry, then person | Fixed closes, else a person |
| Requester never responds? | Back to a person after 3 days (Recommended) / Wait indefinitely / Tenant sets the wait | Back to a person after 3 days |
| What can a technician do with a draft? | Send, edit, or discard (Recommended) / Read-only hint | Send, edit, or discard |
| (more) What does the requester see? | Add a "reply to requester" flag (Recommended) / AI answer and status only / Everything | Add a "reply to requester" flag |
| (more) Whose tickets does the tray window list? | This computer + Windows user (Recommended) / Everything from this computer | This computer + Windows user |
| (more) How is the requester told? | Tray pop-up and in-app (Recommended) / Also email when SMTP is set / No push, they look | Tray pop-up and in-app |
| (more) What does the "AI-assisted" mark say? | Mark + articles + way out (Recommended) / Label only | Mark + articles + way out |
| (more) Can the requester open cited articles? | Read inside the answer (Recommended) / Titles only | Read inside the answer |

**Notes:** The user asked for more questions twice in this area. The first follow-up came after I flagged that comments have no internal/public flag, so showing every comment in the tray could expose staff notes.

---

## Model and article matching

| Question | Options presented | Selected |
|----------|-------------------|----------|
| Which model may draft answers? | Local Ollama only (Recommended) / Tenant's configured model / Local default, cloud opt-in | Local Ollama only |
| Which articles may be cited? | Tenant's own only (Recommended) / Own plus shared | Tenant's own only |
| Who sets the match cut-off? | Fixed, tested cut-off (Recommended) / Tenant picks strictness | Fixed, tested cut-off |
| Queue wait limit? | 10 minutes from arrival (Recommended) / 30 minutes / No queue limit | 10 minutes from arrival |
| (more) Which tenant articles are citable? | Only marked help-desk (Recommended) / Every tenant article | Only marked help-desk |
| (more) Output checks before posting? | Strict output checks (Recommended) / Basic checks | Strict output checks |
| (more) Non-English tickets? | English only, rest to a person (Recommended) / Answer in ticket's language | English only |
| (more) Model down? | Status line, no extra paging (Recommended) / Also page on-call | Status line, no extra paging |

---

## Escalation, undo, gap list

| Question | Options presented | Selected |
|----------|-------------------|----------|
| How are sensitive tickets spotted? | Built-in rules + tenant words (Recommended) / Built-in rules only | Built-in rules + tenant words |
| Hand-off routing and requester view? | Normal queue + reason + notice (Recommended) / Normal queue, silent / Dedicated escalation queue | Normal queue + reason + notice |
| What does Undo do, and does it trip a breaker? | Withdraw + desk-only breaker (Recommended) / Withdraw + tenant breaker / Withdraw, no breaker | Withdraw + desk-only breaker |
| Where does the gap list live? | Knowledge Base screen (Recommended) / Autonomous Ops screen | Knowledge Base screen |
| (more) How do starter articles reach a tenant? | Admin adds, editable copies (Recommended) / Auto-seed new tenants / Shared, read-only | Admin adds, editable copies |
| (more) Who may see the gap list? | Ticket + KB permission (Recommended) / Anyone on the KB screen | Ticket + KB permission |
| (more) Who may send, edit or discard drafts? | Anyone who works tickets (Recommended) / Autonomous Ops approvers | Anyone who works tickets |

---

## Claude's Discretion

- How the answer is registered with the gate and the ledger row shape; which gate steps are skipped for a non-agent kind.
- How "raised by a person" is detected (creation path, not tags); portal `feature` tickets treated as fulfilment requests.
- Tickets during a stop or with the switch Off; old agents without the tray window get drafts.
- Retrieval engine, number of citations, length cap, language detector, gap grouping method, phrase lists.
- "Working days" definition; the tray polling interval and route shape; limits on tenant words; the undo window; where the response time is shown.
- Layout and copy, subject to Spatial Glass, a `/gsd-ui-phase 85` contract and ACTV-08.

## Deferred Ideas

- Email notification to portal requesters once SMTP is configured
- Answers in languages other than English
- Opt-in cloud LLM provider for tickets
- Tenant-adjustable match strictness
- AI first-line answers in the tray app's chat sessions
