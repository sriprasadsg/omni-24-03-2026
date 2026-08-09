# Phase 54 — Integration & Operator UI — CONTEXT

**Milestone:** v3.4 (Native Security Scanning & Autonomous Remediation) — final phase (50→51→52→53→**54**)
**Requirements:** INT-01, INT-02, INT-03
**Depends on:** Phase 50 (scan verdicts), 51 (vuln findings), 52 (FIM events), 53 (remediation queue + approve/deny + audit + playbooks) — this phase surfaces them all

## Goal

Give operators one per-tenant console over the native-security stack — live scan status, findings feed, remediation queue with approvals, playbook library, and the audit trail — plus the thin API endpoints that complete the agent-security surface. This is v3.4's only major frontend.

## Success criteria (what must be TRUE)

1. A per-tenant operator dashboard shows live scan status, the findings feed, the remediation queue, and the audit trail (INT-01).
2. An operator can trigger on-demand scans, approve/deny pending remediations, and view/create playbooks from the UI (INT-02).
3. Every agent security function is reachable via an API endpoint — scan, vuln-scan, fim-status, remediation-trigger, playbook CRUD (INT-03).

## Locked decisions

- **D-01 — One unified "Native Security Console" (INT-01).** A new tabbed page `NativeSecurityConsole.tsx` with tabs: **Findings** (NSCAN scan verdicts + native VULN findings + FIM events), **Remediation Queue** (pending/in-flight + approve/deny), **Playbooks** (reuse the existing `PlaybookManager`), **Audit** (the `remediation_audit` trail). New `AppView` member `nativeSecurity`. Single INT-01 surface — not scattered across the existing dashboards.
- **D-02 — Gate on `manage:active_response` (existing).** The nav entry, the page, and the destructive actions (trigger scan, approve/deny) are all gated on `manage:active_response` (implies remediation authority; no new permission). Registration clones the 49-05 four-file pattern (types + App.tsx lazy-import/permission-map/switch + Sidebar entry).
- **D-03 — Thin backend ops endpoints complete INT-03; findings are aggregated server-side (review MED).** Add a `security_ops_endpoints.py` with what 50-53 don't already expose: `GET /findings` — a **single normalized, paginated feed that aggregates all three sources server-side** (scan verdicts from `security_scan_results` + native vuln findings from `vulnerabilities` + FIM events from `fim_events`), each item `{source: scan|vuln|fim, severity, hostname, target, verdict_or_detail, ts}` (the UI must NOT federate three shapes/paginations); `GET` remediation-queue (pending/in-flight remediations); `POST` trigger-scan (dispatch a `scan_file`/`vuln-scan`/`fim` command to an agent via the **existing `agent_instructions` queue**); `GET` fim-status + a small summary. Combined with the existing endpoints (scan POST 50-04, vuln GET 51, fim-events 52, approve/deny + audit GET 53-04, remediation-playbook CRUD 53-01), INT-03 is satisfied. **Do not duplicate** those endpoints.
- **D-04 — Reuse where the store matches; the Playbooks tab targets the deterministic store (review MED).** The Playbooks tab manages the **dedicated `remediation_playbooks` CRUD** (53-01) — the deterministic YAML playbooks the engine actually runs — NOT `PlaybookManager`/`enhanced_playbook_endpoints` (that manages a different LLM playbook store and would not edit the engine's playbooks). Build a lightweight deterministic-playbook list/editor (or adapt `PlaybookManager` only if it can be pointed at the new store cleanly). VULN findings feed the aggregated `/findings`. New UI for scan verdicts, remediation queue/approvals, playbooks (new store), and audit.
- **D-05 — Server enforces, UI surfaces.** trigger-scan/approve/deny reuse Phase-53's dispatch + guards — the **approval gate + dry-run stay server-side**; the UI triggers and displays, never bypasses. All reads tenant-scoped.

## Scope fences (MUST NOT)

- MUST NOT duplicate the 50-53 endpoints (scan POST, vuln GET, fim-events, approve/deny, audit GET, playbook CRUD) — consume them + the thin new ones.
- MUST NOT bypass the Phase-53 server-side guards (approval gate / dry-run) from the UI.
- MUST NOT gate the console on anything other than `manage:active_response` (D-02).
- MUST NOT rebuild `PlaybookManager` or the vuln list components — reuse.
- MUST NOT access `db._db` in new endpoints.

## Pitfalls

- **Async verdicts:** trigger-scan dispatches to a (possibly disconnected) agent and the verdict returns later — check agent connectivity, show a "queued" state, and refresh/poll the findings feed rather than blocking.
- **Feed size:** paginate the findings feed + audit trail; don't load unbounded history.
- **Component size:** keep `NativeSecurityConsole.tsx` under 500 lines — extract each tab into its own child component.
- **Permission consistency:** the same `manage:active_response` gate must hold on the nav, the view, and the action endpoints (defense in depth; server is authority).

## Plan breakdown

| Plan | Wave | Scope | Requirements |
|------|------|-------|--------------|
| 54-01 | 1 | Backend `security_ops_endpoints.py` — GET /findings (aggregated scan+vuln+fim, paginated), GET remediation-queue, POST trigger-scan (dispatch), GET fim-status/summary + registry + tests | INT-03 |
| 54-02 | 1 | Frontend contract — `nativeSecurity` AppView + types + apiService clients (aggregated-findings/queue/trigger/audit/approve-deny/fim-status + remediation-playbook CRUD) | INT-01/02/03 |
| 54-03 | 2 | `NativeSecurityConsole.tsx` — tabbed console (Findings [aggregated] / Queue / Playbooks [remediation_playbooks store] / Audit) + trigger-scan + approve/deny controls | INT-01/02 |
| 54-04 | 3 | Nav registration (App.tsx + Sidebar), `manage:active_response`, cloning 49-05 | INT-01 |
