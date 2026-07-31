# Phase 43: Remediation-to-Ticketing Bridge - Context

**Gathered:** 2026-07-20 (updated 2026-07-21)
**Status:** Ready for planning — replan required, see "Replanning required" note below

<domain>
## Phase Boundary

Wire `compliance_remediation_service` task create/update to the existing Jira/ServiceNow connectors in `ticketing_service.py` through an explicit field adapter (reuse, don't rebuild — connectors currently only serve security-alert tickets, hardcoded to fields like `process.sha256`/`mitre_technique` that remediation tasks don't have), and close the loop when the external ticket resolves.

</domain>

<decisions>
## Implementation Decisions

### Ticket-creation trigger (captured during batch plan-phase attempt, 2026-07-20; revised 2026-07-21)
- **D-01:** Auto-create a ticket when a remediation task is created at critical/high/**medium** priority, in addition to a manual "Create Ticket" action available for all priorities (including low). **Revised 2026-07-21** — originally high/critical only; user explicitly broadened to include medium. Manual button remains available at every priority level, including low, per the original wording.

### Provider selection (Jira vs ServiceNow)
- **D-02:** Admin picks per-ticket. The "Create Ticket" action shows both provider options if the tenant has both Jira and ServiceNow configured — simple, explicit, no hidden tenant-level default-provider setting to build or maintain.

### Close-loop mechanism
- **D-03:** Polling, not a webhook receiver. Reuse the existing scheduler pattern from `tickets_escalation_service.py`/`scheduled_reports_service.py` — periodic background check **every 5 minutes** (revised 2026-07-21; originally "15-30 min, tune if needed"), registered via `app_startup.py` like the existing schedulers. No new incoming-webhook endpoint or provider-side webhook configuration needed for v1.

### Close-loop: linked ticket deleted, not just closed (added 2026-07-21)
- **D-06:** If the Jira/ServiceNow status-check call returns "not found" (ticket deleted) rather than a closed/open status, the close-loop scheduler treats it as unresolvable for that pass — log and skip, do NOT auto-resolve the task. Deletion is ambiguous (could mean "wrong ticket, ignore" rather than "issue is fixed"), unlike an explicit closed status which unambiguously means resolved. Matches D-04's existing best-effort/non-fatal pattern — a 404 never crashes the scheduler pass, and never silently resolves a task on ambiguous evidence.

### Ticket-creation failure handling
- **D-04:** Best-effort, non-blocking. If the Jira/ServiceNow API call fails, the remediation task action (create/update) still succeeds; the ticket-creation failure is logged and surfaced as an error toast to the admin. Matches the try/except non-fatal pattern already used throughout this codebase for external API calls.

### Claude's Discretion
- D-02, D-04 were explicitly deferred by the user ("You decide") — rationale above is Claude's, following "reuse existing patterns, minimal new infra" as the guiding principle.
- D-06's specific "log and skip, never auto-resolve on ambiguous evidence" resolution is Claude's reasoning for a scenario the user flagged (linked ticket deleted) without specifying the exact handling.
- Where the field-adapter function lives (new module vs added to `ticketing_service.py` — verify during planning which keeps files under the 500-line CLAUDE.md limit).

### Replanning required (2026-07-21)
- D-01 (auto-create priority threshold) and D-03 (poll interval) were revised after this phase was already planned and plan-checker-verified (4 plans: 43-01..43-04, commit `62dbfdc`). Plans 43-01 (scheduler interval) and 43-02 (auto-create trigger) now reflect stale values and MUST be regenerated before execution. D-06 (deleted-ticket handling) is new and unplanned. Run `/gsd-plan-phase 43` to replan before `/gsd-execute-phase 43`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone research (v3.2)
- `.planning/research/ARCHITECTURE.md` — ticket bridge must be synchronous in-process (`await`, try/except non-fatal) — no message bus exists anywhere in this codebase; ticket ref/url gets `$set` back onto the task doc, same pattern as the existing `ai_suggestion` persist-back
- `.planning/research/PITFALLS.md` — `ticketing_service.py`'s connectors are hardcoded to alert-shaped fields (`process.sha256`, `mitre_technique`); passing a remediation task straight through would silently produce "N/A"-filled tickets via `.get()` defaults — requires an explicit adapter, not a pass-through
- `.planning/research/FEATURES.md` — one-way close-loop sync (ticket closed → task resolved, re-scan dispatch triggered) is table stakes; full bidirectional continuous field sync is a v2+ anti-feature requiring webhook infra this phase deliberately avoids (consistent with D-03)

### Codebase maps
- `.planning/codebase/INTEGRATIONS.md` — confirms Jira SDK (`atlassian-python-api`) is present but currently commented out in requirements.txt; verify it's actually installed/enabled before assuming the connector works end-to-end

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/ticketing_service.py::create_jira_ticket`/`create_servicenow_incident` — connectors to call via adapter, not directly.
- `backend/integration_service_ticketing.py` — a second existing Jira/ServiceNow connector pair; confirm during research which one this phase should build the adapter against (may be duplicated capability worth consolidating, or may serve different purposes — verify before choosing).
- `backend/tickets_escalation_service.py`/`backend/scheduled_reports_service.py` — scheduler registration pattern for D-03's polling loop.
- `backend/compliance_remediation_service.py`/`compliance_remediation_endpoints.py` — task create/update call sites where the adapter hooks in.

### Established Patterns
- Fire-and-forget external API calls wrapped in try/except, logged not re-raised — matches D-04.
- Raw unwrapped `mongodb.db` for background scheduler tasks (no request/tenant context available) — required for D-03's polling loop, same as `tickets_escalation_service.py`.

### Integration Points
- Remediation task view (frontend) — needs a "Create Ticket" action/button, provider picker if both configured (D-02), and display of `ticket_provider`/`ticket_ref`/`ticket_url` once created.

</code_context>

<specifics>
## Specific Ideas

None beyond the decisions captured above.

</specifics>

<deferred>
## Deferred Ideas

- Bidirectional continuous ticket field sync — explicitly out of scope per REQUIREMENTS.md's v3.2 Out of Scope table; only one-way close-loop (ticket closed → task resolved) ships this phase.
- Webhook-based real-time close-loop — deferred per D-03; revisit only if polling latency proves genuinely problematic in practice.

</deferred>

---

*Phase: 43-remediation-to-ticketing-bridge*
*Context gathered: 2026-07-20, updated 2026-07-21*
