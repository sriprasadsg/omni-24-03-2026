# Phase 73 — API Capability Coverage Matrix

**Generated:** 2026-08-18 (planning)
**Detector:** `api-coverage.cjs --json` against the phase's drafted PLAN.md set → `detected: true` (signals: `integrate/rest`, `wire/webhook`, `surface/api`)

> Full API Coverage by Default — Opt Out, Never Opt In.
> Every capability of every external API surface this phase touches is enumerated below. Each starts at `INTEGRATE`; every `OPT-OUT` carries a one-line reason. A capability is not allowed to be absent from this table.

External surfaces in scope: the **Jira REST API** and the **ServiceNow Table API**, both reached through the pre-existing `backend/ticketing_service.py` connectors that `backend/ticketing_bridge.py` already uses for compliance-remediation tickets (D-09 reuses them unmodified). Plus the phase's own **ITAM webhook event set** (D-05) and the **ITAM REST auth surface** (D-01/D-02), which the checkpoint treats the same way.

---

## Jira REST API

| Capability | Decision | Reason |
|------------|----------|--------|
| Create issue (`POST /rest/api/3/issue`) | INTEGRATE | The phase's core ticketing action; reached via the existing `create_jira_ticket` connector unchanged (73-04, 73-05) |
| Read issue status (`GET /rest/api/3/issue/{key}?fields=status`) | INTEGRATE | Already reused as-is by `run_close_loop_pass`; ITAM tickets created by this phase inherit the same status polling (D-09) |
| Basic-auth with email + API token | INTEGRATE | The only auth mode the existing connector implements; reused unchanged, credential read from the tenant's existing config (D-11) |
| Project key / issue type selection | INTEGRATE | Read from the tenant's existing `jira_project_key` / `jira_issue_type` config; D-11 makes any ITAM-specific variation a field on the payload, not a new config surface |
| Transition issue (workflow move) | OPT-OUT | Close-loop is read-only by design — the platform observes Jira's state, it does not drive it |
| Add comment to issue | OPT-OUT | No ITAM event in D-05 produces follow-up commentary; one ticket per condition is the locked model |
| Attach file to issue | OPT-OUT | No ITAM event carries an artifact; label PDFs and reports have their own delivery paths |
| Delete issue | OPT-OUT | The platform never destroys a customer's ticket; a stale ticket is skipped, never removed |
| Search / JQL query | OPT-OUT | Ticket lookup is by stored `ticket_ref`, so no search surface is needed |
| Assign issue / set assignee | OPT-OUT | Assignment is the customer's Jira workflow concern, not the platform's |
| Set priority / labels / components | OPT-OUT | Severity is carried in the alert shape and rendered into the summary text; no per-field Jira mapping is in scope |
| Link issues to each other | OPT-OUT | ITAM conditions are independent; no parent/child or blocks relationship exists to express |
| Custom field writes | OPT-OUT | Would require per-tenant field discovery; D-11 forbids a new ITAM-specific integration settings surface |
| Issue-type / field metadata discovery (`/createmeta`) | OPT-OUT | Config is operator-supplied and already validated by the existing test-connection route |
| Create an issue per asset on a schedule (CMDB-as-issues) | OPT-OUT | Explicitly deferred by D-12 — this phase builds ticket-per-event only |
| Inbound Jira webhooks into the platform | OPT-OUT | Close-loop uses outbound polling; accepting inbound Jira callbacks would be a new public ingress surface, not in scope |

## ServiceNow Table API

| Capability | Decision | Reason |
|------------|----------|--------|
| Create incident (`POST /api/now/table/incident`) | INTEGRATE | The phase's core ticketing action for ServiceNow tenants; existing `create_servicenow_incident` connector reused unchanged (73-04, 73-05) |
| Read incident state (`GET /api/now/table/incident/{sys_id}`) | INTEGRATE | Already reused as-is by `run_close_loop_pass`, classifying by display-value label rather than numeric state codes |
| Basic auth with instance username + password | INTEGRATE | The only auth mode the existing connector implements; reused unchanged from the tenant's existing config (D-11) |
| Display-value response mode (`sysparm_display_value`) | INTEGRATE | Already used by the status poll; instance-customisable state codes make label comparison the correct read |
| Update incident fields | OPT-OUT | Close-loop is read-only by design — the platform observes ServiceNow's state, it does not drive it |
| Close / resolve incident | OPT-OUT | Same read-only stance; resolution is the customer's process |
| Delete incident | OPT-OUT | The platform never destroys a customer's record |
| Attachment API (`/api/now/attachment`) | OPT-OUT | No ITAM event carries an artifact |
| Query / list incidents (`sysparm_query`) | OPT-OUT | Ticket lookup is by stored `ticket_ref`; no search surface needed |
| CMDB CI table (`cmdb_ci*`) create or sync | OPT-OUT | Explicitly deferred by D-12 — asset-inventory-as-CMDB is a future phase's concern |
| Change request / request item tables | OPT-OUT | D-10 defines ticket triggers only; mapping ITAM approvals onto ServiceNow request items is a different integration model |
| Assignment group / category / priority field mapping | OPT-OUT | Would require per-tenant field discovery; D-11 forbids a new ITAM-specific settings surface |
| Business rules / inbound callbacks | OPT-OUT | Close-loop uses outbound polling; inbound ingress is out of scope |
| Zoho Desk connector (present in the same config module) | OPT-OUT | D-09 and D-10 name Jira and ServiceNow only; the Zoho path exists for other features and is untouched |

## ITAM webhook event set (D-05)

The platform is the *producer* here. Every event type D-05 names is delivered by this phase; none is deferred.

| Capability | Decision | Reason |
|------------|----------|--------|
| `asset.checked_out` | INTEGRATE | Fired inline at the check-out mutation (73-01 tracer) |
| `asset.checked_in` | INTEGRATE | Fired inline at the check-in mutation (73-02) |
| `consumable.low_stock` | INTEGRATE | Fired inline at the consumable-checkout decrement, using the low-stock report's own threshold rule (73-02) |
| `asset.request_approved` | INTEGRATE | Fired inline at request approval (73-02) |
| `asset.request_denied` | INTEGRATE | Fired inline at request rejection (73-02) |
| `asset.warranty_expiring` | INTEGRATE | Fired from the existing periodic warranty job, tenant-bracketed (73-03, D-08) |
| `license.expiring_soon` | INTEGRATE | Fired from a new licence sweep driven by that same existing scheduler, tenant-bracketed (73-03, D-08) |
| `asset.audit_overdue` | INTEGRATE | Required a new periodic sweep that did not previously exist — RESEARCH Pitfall 6 (73-05) |
| Subscription create / list / delete | INTEGRATE | Already shipped in `webhook_endpoints.py`; the picker is extended with the eight new types (73-06, D-14) |
| Delivery history view | INTEGRATE | Already shipped; ITAM deliveries appear in it with no change |
| HMAC-SHA256 payload signing | INTEGRATE | Already implemented in `_send_single_webhook`; inherited unchanged, must not regress |
| SSRF guard on subscriber URLs | INTEGRATE | Already implemented in `_is_safe_webhook_url`; inherited unchanged, must not regress |
| API-key auth on subscription update (`PUT /{id}`) and test (`POST /{id}/test`) | OPT-OUT | Pre-existing inconsistency in `webhook_endpoints.py` flagged by RESEARCH Pitfall 9; outside D-01/D-02's stated scope, which covers the `itam_*_endpoints.py` routers only |
| Per-subscriber retry / back-off policy | OPT-OUT | Lives in the pre-existing dispatcher, which this phase reuses unmodified; changing delivery semantics is not an ITAM concern |
| Event replay / backfill | OPT-OUT | No D-05 decision calls for it; events are live-only, consistent with every existing event type in this codebase |
| Per-event-type payload schema | OPT-OUT | D-06 locks a single flat record shape plus a before/after diff for the lifecycle pair — a bespoke per-type schema was explicitly rejected |

## ITAM REST auth surface (D-01 / D-02)

The platform is the *provider* here. Coverage means: which `_require_itam_admin`-gated routers accept an API key.

| Capability | Decision | Reason |
|------------|----------|--------|
| Asset router | INTEGRATE | Named in D-02 |
| Lifecycle router (check-out/in, audit, overdue report) | INTEGRATE | Named in D-02 |
| Licence router | INTEGRATE | Named in D-02 |
| Consumable router | INTEGRATE | Named in D-02 |
| Component router | INTEGRATE | Named in D-02 |
| Finance router | INTEGRATE | Named in D-02 |
| Reporting router | INTEGRATE | Named in D-02 |
| Catalog router (suppliers, models, custom fields) | INTEGRATE | Unnamed in D-02 but unambiguously ITAM; user-confirmed into the 11-file swap set. Carries its own duplicate guard definition |
| KPI router | INTEGRATE | Unnamed in D-02 but unambiguously ITAM; user-confirmed |
| Data import/export router | INTEGRATE | Unnamed in D-02 but unambiguously ITAM; user-confirmed |
| Label router | INTEGRATE | Unnamed in D-02 but unambiguously ITAM; user-confirmed |
| `manage:assets` as an issuable API-key scope | INTEGRATE | Required for any of the above to be reachable by a scoped key — RESEARCH Pitfall 1, second gap |
| Scope narrowing on the ITAM guard | INTEGRATE | Without it a `read:assets` key passes a `manage:assets` gate — RESEARCH Pitfall 1 |
| LDAP directory-sync router | OPT-OUT | User-confirmed exclusion: letting a key trigger a directory sync or rewrite group-role mappings is a materially different risk from asset access |
| SAML/SSO configuration router | OPT-OUT | Same reasoning; found during planning to import the same guard symbol, excluded on the identical basis |
| User-management CRUD router | OPT-OUT | Same reasoning; found during planning to import the same guard symbol, excluded on the identical basis |
| API-key management router | OPT-OUT | User-confirmed exclusion: a key that can list or create keys is a self-service privilege-escalation surface |
| Asset-request router (`request:assets` / `manage:procurement` gates) | OPT-OUT | Uses its own separate guards, never `_require_itam_admin`; D-02 does not name asset-requests as a category |
| Procurement router (`manage:procurement` gate) | OPT-OUT | Uses its own separate guard, never `_require_itam_admin`; not named in D-02 |
| Version-prefixed external surface (`/api/v1/itam/*`) | OPT-OUT | D-03: API keys unlock the existing unprefixed paths; no new versioned surface is built |
| Dedicated API docs page / OpenAPI export | OPT-OUT | D-13: FastAPI's auto-generated docs page already covers the ITAM routers once API-key auth is added |
| ITAM-specific rate-limit tier | OPT-OUT | D-04: the existing per-key limiter is reused as-is |
