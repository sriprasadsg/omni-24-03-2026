# Feature Research

**Domain:** GRC/compliance platform — remediation operations (ticketing bridge, SLA/escalation, control comment threads, CSPM checks)
**Researched:** 2026-07-20
**Confidence:** MEDIUM (cross-checked web sources: Vanta help center, Cloudflare developer docs, Alibaba Cloud official docs, Prowler docs, ServiceNow community, GRC vendor blogs — no official API-key-gated docs available for direct verification; codebase patterns read directly from source, HIGH confidence)

**Scope note:** This is a subsequent-milestone research pass. Existing capabilities (Jira/ServiceNow connectors for security alerts, generic support-ticket SLA escalation, DigitalOcean CSPM checks, remediation task CRUD/AI-suggest/re-scan/WebSocket, single-field evidence comments) are NOT re-researched — see `.planning/PROJECT.md` v3.2 milestone section. This file covers only the 4 new v3.2 feature areas.

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Remediation task → ticket, one-click or auto-create | Vanta/Drata/Cyber Sierra all let a failing control/task generate a Jira issue or ServiceNow incident pre-populated with failure reason, control ID, and remediation steps — this is the single most-cited integration pattern across every GRC vendor surveyed | MEDIUM | `ticketing_service.py` already has `create_jira_ticket`/`create_servicenow_incident` accepting an `alert`-shaped dict; reuse by mapping a `compliance_remediation_tasks` doc into that same shape rather than adding a parallel code path |
| Dedup guard on auto-create | Every vendor source describes checking for an existing open linked ticket before creating a new one on repeat trigger (e.g. re-scan still failing) | LOW | Store `ticket_ref`/`ticket_provider`/`ticket_url` fields directly on the remediation task doc; auto-create logic checks these are unset before calling the connector |
| One-way close-loop sync (external ticket resolved → task marked resolved) | Vanta: "once an issue is resolved in Jira, Vanta automatically reflects that so engineers never need to log into Vanta" — this is described as baseline, not premium, across sources | MEDIUM | Requires either a webhook receiver (Jira/ServiceNow webhook → `PATCH` task status) or a polling job; polling is simpler and matches this codebase's existing `start_escalation_scheduler` background-loop pattern in `tickets_escalation_service.py` |
| Manual link (attach existing ticket to a task) | Fallback when auto-create is off or ticketing isn't configured for the tenant; needed because `ticketing_service.get_ticketing_config` can return `None` | LOW | Simple `ticket_ref`/`ticket_url` field set via PATCH, no connector call |
| Severity/priority mapping from task priority to ticket priority | Existing `JIRA_PRIORITY_MAP`/`SNOW_URGENCY_MAP` already encode this pattern for alerts; remediation tasks have their own `priority` field that needs the same mapping | LOW | Reuse the existing maps — remediation task priority values (`low/medium/high/critical` per `compliance_remediation_service.py`) already match the map keys |
| Due-date breach detection on remediation tasks | Every SLA-escalation source frames "detect overdue, don't silently miss" as the baseline expectation; auditors specifically look for this | LOW-MEDIUM | `compliance_remediation_tasks` already has `due_date`; add a `sla_status` compute (ok/at_risk/breached) mirroring `tickets_helpers._compute_sla`, scoped to this collection only per PROJECT.md's explicit note that `tickets_escalation_service.py` is a different domain |
| Escalation notification to assignee (+ optionally assignee's manager or a configured escalation target) | Universally cited: "overdue tasks trigger automatic escalation notifications to task owners" | MEDIUM | Needs an escalation-target concept per tenant/task since `assignee_type` is already `user`\|presumably `team`; simplest v1 is notify the assignee + a per-tenant configured escalation contact/channel, not full org-chart manager lookup |
| Escalation audit trail (immutable log of what was escalated, when, why) | Auditors explicitly expect a documented trail of SLA misses, not silent breach — cited by multiple sources as differentiating a defensible program from an informal one | LOW | Mirrors the existing `status_history` pattern already used for compliance status overrides (`PATCH /api/assets/{id}/compliance/status`) — append an `escalation_history` array entry, don't overwrite |
| Threaded comments on a control, visible to the compliance team | GRC platforms use comment threads on controls/evidence to replace email chains for questions and gap-flagging; described as a core collaboration primitive, not a premium add-on | LOW-MEDIUM | Codebase already has this exact pattern in `tickets_service.add_comment`/`tickets_endpoints.py` (`POST /{id}/comments`, `$push` to an array, `@mentions` regex, notification dispatch) — clone directly per PROJECT.md's own note |
| @mention detection + notification in comments | Existing tickets comment pattern already does this (`re.findall(r'@([\w.+-]+@[\w.+-]+\.[a-z]+)', ...)`) and it's a reasonable baseline for any comment feature in this codebase | LOW | Copy the existing regex + notification dispatch verbatim |
| Comment author + timestamp displayed, chronological order | Baseline expectation for any audit-relevant comment thread — sources note "comment history is part of the audit trail" | LOW | Same shape as tickets: `{id, author, text, created_at, edited}` |
| Real CSPM check catalog entries for OCI/Alibaba/Cloudflare (not just allowlisted provider names) | DigitalOcean already sets the bar in this codebase: 10 real, correctly-scoped checks covering firewall, storage encryption, network isolation, monitoring. OCI/Alibaba/Cloudflare currently have zero — that's the literal gap named in the milestone | MEDIUM (×3 providers) | Follow the exact `DO_CHECKS` list shape (`id`, `name`, `description`, `provider`, `service`, `severity`, `frameworks`, `remediation`) in a new `cloud_checks_oci.py` / `cloud_checks_alibaba.py` / `cloud_checks_cloudflare.py` file each, imported into `CLOUD_CHECKS` in `cloud_checks_service.py`, exactly like `AWS_CHECKS`/`AZURE_CHECKS`/etc. are combined today |
| OCI checks aligned to CIS OCI Foundations Benchmark | Prowler (this project's own competitive benchmark target) implements OCI checks against this exact standard; it's the de facto baseline for any OCI CSPM tool | — | Minimal-but-real set (~8-10 checks): IAM (MFA enforced, no tenancy-admin day-to-day use, API keys rotated, storage-admin scoped without delete), Object Storage (bucket not public, encryption via Vault), Networking (security lists not open to 0.0.0.0/0 on admin ports, VCN flow logs on), Logging (Cloud Guard enabled, Audit log retention), Compute (boot volume encryption) |
| Alibaba checks mirroring AWS-equivalent services | Alibaba Cloud Security Center's own configuration-assessment checks and Trend Micro Conformity map almost 1:1 to AWS checks (RAM~IAM, OSS~S3, ActionTrail~CloudTrail, Security Group~SG) | — | Minimal-but-real set (~8-10 checks): OSS bucket not public-read/public-read-write, OSS SSE enabled, OSS access logging, RAM least-privilege (no individual-user AdministratorAccess, MFA enforced, unused creds removed), ECS security group not open to 0.0.0.0/0 on 22/3389, RDS/ApsaraDB not publicly accessible + encrypted at rest, ActionTrail enabled account-wide |
| Cloudflare checks aligned to its own Security Center/Security Insights categories | Cloudflare's own dashboard groups exactly these checks under "Security" — using their own taxonomy avoids inventing non-standard categories | — | Minimal-but-real set (~8-10 checks): SSL/TLS mode is Full (strict) not Flexible, DNSSEC enabled, min TLS version ≥1.2, Always Use HTTPS enabled, WAF Managed Rules enabled (not log-only), API tokens scoped (not Global API Key), rate limiting on auth/API paths, Bot Fight Mode/Bot Management enabled, origin IP not exposed (proxy/orange-cloud on) |
| `simulated` flag when a check runs without real imported findings | Existing precedent in `cloud_checks_service.run_checks()` (`"simulated": not has_real_findings`) and the CloudFormation container-scan decision in PROJECT.md's Key Decisions table — labeled simulated data beats silent fake-pass/fail | LOW | New OCI/Alibaba/Cloudflare checks plug into the exact same `run_checks()` evaluation loop already in `cloud_checks_service.py` — no new evaluation logic needed, only new check *definitions* |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Bidirectional field sync (status, assignee, comments flow both ways between GRC task and Jira/ServiceNow ticket) | Sources explicitly frame full two-way sync as beyond baseline — most competitors do one-way close-loop only (ticket closed → task resolved), not continuous field mirroring | HIGH | Explicitly defer past v1 — requires webhook infra + conflict resolution; PROJECT.md's downstream-consumer question already flags this as a v1-scope decision, answer: NOT needed for v1, fire-and-forget create + poll-based close-loop is sufficient |
| Severity-tiered SLA policy engine (critical 15-30d / high 30-60d / medium 60-90d / low next-cycle) configurable per tenant/framework | Cited as GRC-leader behavior (documented policy-driven SLA windows, not just a single global due-date field) — this project already has `compliance_remediation_tasks.due_date` set per-task by the creator, so a policy *engine* that auto-derives due dates from severity would be a step up | MEDIUM | Good v1.1+ candidate once basic breach detection ships; v1 can rely on user-set `due_date` per task |
| Auditor-facing comment visibility toggle (internal-only vs auditor-visible comments) | Sources note auditor collaboration tools distinguish internal notes from shared/auditor-visible ones | MEDIUM | Not requested in the v3.2 scope language ("new comment model... genuinely absent") — worth flagging as a natural v1.1 follow-on given this platform already has MSP/tenant/auditor role distinctions elsewhere, but do not build proactively |
| Live API-polled CSPM checks (real-time SDK calls to OCI/Alibaba/Cloudflare rather than evaluation against imported findings) | Would move this codebase from "findings importer + check evaluator" (current architecture for all providers, including DO) to true live CSPM | HIGH | Explicitly NOT what "real check logic" means in this milestone — DigitalOcean, the reference implementation named in PROJECT.md, also evaluates against `cloud_findings` import data, not live polling. Building live SDK integration for 3 new providers in this milestone would be scope creep against the established architecture |
| Cross-framework check reuse (single OCI/Alibaba/Cloudflare check mapped to multiple frameworks: SOC2, ISO27001, PCI, NIST) | Every existing provider check list (AWS/Azure/GCP/DO) already does this via the `frameworks: [...]` array field | LOW (already the pattern) | Not really a "differentiator" so much as consistency — just make sure new checks populate this field like all others do, not a stub `[]` |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Rebuilding a parallel ticketing system instead of reusing `ticketing_service.py` connectors | "Remediation tickets are different from alert tickets" feels intuitively true | PROJECT.md is explicit: "reuse, don't rebuild" — `ticketing_service.py`'s Jira/ServiceNow functions are generic (`create_jira_ticket(alert, config)` takes any dict-shaped payload, not an alert-specific schema); duplicating auth/config/connector code for remediation tasks doubles maintenance surface for zero functional gain | Map a `compliance_remediation_tasks` doc into the same shape `create_jira_ticket`/`create_servicenow_incident` already expect (rename `alert.get('type')`→task title, `alert.get('hostname')`→asset name, etc.) and call the existing functions |
| Reusing `tickets_escalation_service.py` as-is for remediation task SLA | It already implements SLA-breach escalation logic, seems like free reuse | PROJECT.md explicitly calls this out: it operates on the generic `db.tickets` collection with `status`/`priority` semantics specific to the internal ticketing system (open/in_progress/on_hold/etc.), not `compliance_remediation_tasks`' status vocabulary (open/resolved) or its `due_date`-driven (not created_at+SLA-policy-driven) breach model | Write a small, scoped `compliance_remediation_escalation_service.py` that borrows the *pattern* (background loop, `_history_entry`, priority bump) but queries `compliance_remediation_tasks` and respects its own status/priority vocabulary |
| Rich/nested comment threading (replies-to-replies, reactions, edit history diffing) | Feels like "modern collaboration tool" parity (Slack/Linear-style threads) | No GRC competitor source surveyed does this on compliance controls — flat chronological comment lists are the norm; nested threading adds real UI/data-model complexity (parent_id chains, thread collapsing) for a feature whose job is "leave an auditable note," not real-time chat | Flat array of `{id, author, text, created_at, edited}` per control, exactly like the existing `tickets_service.add_comment` pattern already proven in this codebase |
| Building a fully generic "comments on anything" polymorphic system (tickets + controls + evidence + assets all sharing one comments collection/endpoint) | DRY instinct — "we already have a comment pattern, make it universal" | Increases blast radius of a schema change and RBAC complexity (different resources have different visibility/tenant-isolation rules); PROJECT.md scopes this narrowly to `control_id`-linked comments only | Clone the tickets comment *pattern* into a control-scoped implementation; do not attempt a shared polymorphic comments service in this milestone |
| Full live-scanning CSPM agents/connectors for OCI/Alibaba/Cloudflare (OAuth flows, SDK polling schedulers, credential vaulting) | "Real check logic" sounds like it implies live scanning | Every existing provider in this codebase (including the reference-quality DigitalOcean implementation) evaluates checks against previously-imported `cloud_findings`, not live API calls — building live scanning for 3 providers when even AWS/Azure/GCP don't have it here would be wildly inconsistent scope and effort for a milestone framed as "close real gaps," not "add new architecture" | Real, correctly-researched check *definitions* (name/description/severity/frameworks/remediation) evaluated against the existing import-and-match `run_checks()` engine, marked `simulated` when no findings are imported yet — same as every other provider |
| Auto-escalating remediation tasks all the way to a hard priority bump on the underlying compliance control itself | Seems like it "closes the loop" fully | Compliance control pass/fail state is derived from evidence/scan results (`compliance_evidence_processor`), not from remediation-task SLA state; conflating the two would let an unrelated process (a missed SLA notification) silently mutate compliance status, undermining the existing `manual_override`/`status_history` integrity model from Phase 6 | Escalation only ever touches the remediation task's own fields (`priority`, `escalation_level`, `escalated_at`) and notifications — it never writes to asset/control compliance status |

## Feature Dependencies

```
Remediation-to-ticketing bridge
    └──requires──> existing ticketing_service.py Jira/ServiceNow connectors (already built)
    └──requires──> compliance_remediation_tasks collection (already built)
    └──enhances──> SLA/escalation (an escalated task can auto-comment/update the linked ticket, optional)

SLA/escalation for remediation tasks
    └──requires──> compliance_remediation_tasks.due_date field (already present)
    └──pattern-borrows-from──> tickets_escalation_service.py (background-loop shape only, not the collection/query)

Comment threads on compliance controls
    └──pattern-clones──> tickets_endpoints.py / tickets_service.py comment implementation (already built, proven)
    └──independent-of──> ticketing bridge and SLA/escalation (no shared data model)

CSPM checks for OCI/Alibaba/Cloudflare
    └──pattern-clones──> cloud_checks_service.py DO_CHECKS shape + RUNNABLE_PROVIDERS inclusion (already built, proven)
    └──independent-of──> the other 3 features entirely (different subsystem: cloud posture, not remediation ops)
```

### Dependency Notes

- **Ticketing bridge requires existing `ticketing_service.py` connectors:** No new Jira/ServiceNow auth or API-call code needed — only a translation layer from `compliance_remediation_tasks` doc shape to the `alert`-dict shape those functions already consume, plus new fields on the task doc (`ticket_provider`, `ticket_ref`, `ticket_url`) to record the link.
- **SLA/escalation borrows the *pattern*, not the collection, from `tickets_escalation_service.py`:** PROJECT.md is explicit that the existing service is "a different domain, not reusable as-is" because it queries `db.tickets` with that system's status vocabulary. A new, scoped service should reuse the background-loop-every-N-minutes shape and the append-only history-entry idiom, but query `compliance_remediation_tasks` directly.
- **Comment threads clone the tickets comment pattern directly:** Same array-push-per-comment shape, same `@mention` regex, same notification dispatch call — the only real design decision is where the array lives: embedded on the (already tenant-scoped) `compliance_controls` doc, matching how tickets embed comments on the ticket doc, versus a separate `control_comments` collection keyed by `{tenantId, control_id}`. Embedding matches the existing proven pattern most closely and needs no new tenant-isolation logic (the parent `compliance_controls` doc is already tenant-filtered everywhere it's read). A separate collection would need its own tenant-isolation test coverage identical to what already exists for `compliance_remediation_tasks` (5 boundaries verified per PROJECT.md) — pick whichever is cheaper to implement correctly, but embedding is the lower-risk default given how closely it mirrors the proven ticket pattern.
- **CSPM checks are fully independent of the other 3 features:** Different subsystem (`cloud_checks_*` files), no shared data model with remediation tasks, tickets, or comments. Can be built/planned as a separate phase with zero ordering constraint relative to the other three.

## MVP Definition

### Launch With (v1 — this milestone)

- [ ] Remediation task → ticket link, manual "Create Ticket" action + optional per-tenant auto-create-on-create-task toggle, reusing existing Jira/ServiceNow connectors — table stakes, matches every competitor surveyed
- [ ] One-way close-loop sync (poll linked ticket status; when Jira/ServiceNow ticket closes, mark remediation task resolved and trigger existing re-scan dispatch) — table stakes per Vanta's described baseline behavior; NOT full bidirectional field sync
- [ ] `sla_status` computation (ok/at_risk/breached) on `compliance_remediation_tasks` scoped to that collection's own `due_date` and status vocabulary — table stakes
- [ ] Escalation notification (to assignee, plus a per-tenant configured escalation contact) + `escalation_history` audit trail entries — table stakes, matches auditor-defensibility expectations
- [ ] Comment thread on `control_id`, cloned from the existing ticket-comment pattern (author/text/timestamp, `@mention` detection, notification) — table stakes, explicitly named as "genuinely absent" in PROJECT.md
- [ ] Real check-definition catalogs for OCI (~8-10 checks), Alibaba (~8-10 checks), Cloudflare (~8-10 checks), each following the `DO_CHECKS` shape, wired into `CLOUD_CHECKS` and evaluated by the existing `run_checks()` engine with `simulated` flagging — table stakes, matches the DigitalOcean reference bar already set in this codebase

### Add After Validation (v1.x)

- [ ] Severity-tiered SLA *policy* engine that auto-derives `due_date` from control severity + framework, rather than relying purely on user-set due dates — trigger: once teams start asking for consistent SLA windows across tenants instead of per-task manual dates
- [ ] Auditor-visible vs internal-only comment visibility toggle — trigger: once external auditor portal access (if/when built) needs to reuse this same comment thread
- [ ] Deeper OCI/Alibaba/Cloudflare check catalogs (beyond the minimal-but-real 8-10 each) expanding toward Prowler-parity coverage counts — trigger: once the minimal set proves the CSPM pattern generalizes correctly and there's demand for broader coverage parity with AWS's 147 checks

### Future Consideration (v2+)

- [ ] Bidirectional continuous field sync between remediation tasks and external tickets (status/assignee/comments mirrored both ways in near-real-time) — defer: requires webhook infrastructure and conflict-resolution logic disproportionate to a "close real gaps" milestone; no competitor source treats this as baseline
- [ ] Live SDK-based CSPM scanning for OCI/Alibaba/Cloudflare (real-time API polling instead of imported-findings evaluation) — defer: architecturally inconsistent with every other provider in this codebase including the AWS/Azure/GCP reference implementations; would require rearchitecting the whole `cloud_checks_service.py` evaluation model, not just adding 3 providers

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Remediation-to-ticketing bridge (create + one-way close-loop) | HIGH | MEDIUM | P1 |
| SLA/escalation on remediation tasks | HIGH | LOW-MEDIUM | P1 |
| Comment threads on compliance controls | MEDIUM-HIGH | LOW-MEDIUM | P1 |
| OCI/Alibaba/Cloudflare CSPM check catalogs (minimal-but-real) | MEDIUM | MEDIUM (×3) | P1 |
| Bidirectional ticket field sync | MEDIUM | HIGH | P3 |
| SLA policy engine (severity-tiered auto due-dates) | MEDIUM | MEDIUM | P2 |
| Auditor-visible comment toggle | LOW-MEDIUM | MEDIUM | P3 |
| Live CSPM scanning (real SDK calls) | LOW (for this milestone's stated goal) | HIGH | P3 (architectural mismatch — not just deferred, actively avoid this milestone) |

**Priority key:**
- P1: Must have for launch (v3.2 milestone scope)
- P2: Should have, add when possible (v1.x)
- P3: Nice to have, future consideration (v2+) — or actively out of scope per architecture fit

## Competitor Feature Analysis

| Feature | Vanta | Drata / Cyber Sierra | This Project's Approach |
|---------|-------|----------------------|--------------------------|
| Ticket creation from failed control | One-click, pre-populated with test/control/remediation context, dedup against open issues | Auto-create Jira issue or ServiceNow incident, assign to asset owner, link to control | Reuse existing `create_jira_ticket`/`create_servicenow_incident`; map remediation task fields into the same payload shape; add dedup via stored `ticket_ref` |
| Close-loop sync | Ticket closed in Jira → Vanta reflects automatically, no manual re-check needed | Platform "verifies the fix, closing the loop" | Poll linked ticket status (reuses `start_escalation_scheduler`-style background loop shape) → mark task resolved → trigger existing `dispatch_rescan` |
| SLA/escalation | Not deeply detailed in sources, but severity-tiered windows are the general GRC pattern | ServiceNow GRC/IRM module has native SLA definitions per module | Scoped `sla_status` + escalation service on `compliance_remediation_tasks` only, borrowing the existing internal-ticketing pattern's shape, not its collection |
| Control/evidence comments | Auditor collaboration surfaces described as "share evidence, respond to requests, preserve audit trails" in-platform | Not deeply detailed, general "collaborative workflow" language across sources | Clone the existing internal-tickets comment pattern (flat array, `@mention`, notification) onto `control_id` |
| CSPM coverage breadth | N/A (Vanta/Drata are compliance-evidence platforms, not CSPM scanners in the Prowler sense) | Prowler (this project's own named competitive benchmark) has broad multi-cloud check coverage including OCI | Minimal-but-real 8-10 checks per new provider, following the CIS-benchmark-aligned pattern Prowler itself uses for OCI, and the AWS-equivalent-service pattern for Alibaba (RAM~IAM, OSS~S3, ActionTrail~CloudTrail) |

## Sources

- [Jira + Vanta Integration](https://www.vanta.com/integrations/jira)
- [Jira: Integration Guide | Vanta Help Center](https://help.vanta.com/en/articles/14441707-jira-integration-guide)
- [How to Integrate Compliance Monitoring with Jira or ServiceNow Workflows](https://cybersierra.co/blog/sstreamline-compliance-jira-servicenow/)
- [SOC 2 Ticketing & SLAs: Vulnerability Patching & Incident Response](https://truvocyber.com/blog/soc2-ticketing-sla-vulnerability-incident-response)
- [Controls remediation: best practices and real-world examples for 2025](https://community.trustcloud.ai/docs/grc-launchpad/grc-101/risk-management/navigating-controls-remediation-best-practices-and-case-studies/)
- [Automating SLAs in Risk-Based Vulnerability Management](https://nucleussec.com/blog/automating-slas-rbvm/)
- [A Practical Guide for GRC Leaders (Three Lines of Defense) — ServiceNow Community](https://www.servicenow.com/community/grc-articles/a-practical-guide-for-grc-leaders-three-lines-of-defense-in/ta-p/3396208)
- [Solved: SLAs for any module in GRC/IRM — ServiceNow Community](https://www.servicenow.com/community/grc-forum/slas-for-any-module-in-grc-irm/m-p/2446100)
- [SOC 2 Compliance Software (2026): 14 Platforms Ranked by an Auditor Network](https://soc2auditors.org/insights/soc-2-software/)
- [Best 12 Compliance Audit Software Platforms for SOC Readiness](https://securityboulevard.com/2026/07/best-12-compliance-audit-software-platforms-for-soc-readiness/)
- [Overview of Security Best Practices in OCI Tenancy | ateam](https://www.ateam-oracle.com/oci-tenancy-security-best-practices-guide-overview)
- [Well-architected framework for Oracle Cloud Infrastructure](https://docs.oracle.com/en/solutions/oci-best-practices/optimize-security-posture-your-environment1.html)
- [Oracle Cloud Infrastructure (OCI) Authentication in Prowler — Prowler Documentation](https://docs.prowler.com/user-guide/providers/oci/authentication)
- [prowler-cloud/prowler releases (GitHub)](https://github.com/prowler-cloud/prowler/releases)
- [Overview of Cloud Security Posture Management (CSPM) — Alibaba Cloud](https://www.alibabacloud.com/help/en/security-center/user-guide/cspm)
- [Manage cloud configuration risks with security checks — Security Center — Alibaba Cloud](https://www.alibabacloud.com/help/en/security-center/user-guide/cloud-service-configuration-assessment/)
- [OSS Bucket Public Access | Trend Micro Cloud One Conformity](https://www.trendmicro.com/cloudoneconformity/knowledge-base/alibaba-cloud/AlibabaCloud-OSS/publicly-accessible-oss-bucket.html)
- [Best practice rules for Alibaba Cloud | TrendAI](https://www.trendmicro.com/trendaivisiononecloudriskmanagement/knowledge-base/alibaba-cloud/)
- [Overview · Cloudflare Security Center docs](https://developers.cloudflare.com/security-center/)
- [API token permissions · Cloudflare Fundamentals docs](https://developers.cloudflare.com/fundamentals/api/reference/permissions/)
- [Cloudflare WAF Best Practices](https://www.appsecure.security/blog/cloudflare-waf-best-practices)
- [Recommended Cloudflare Performance & Security Settings (Guide)](https://linuxblog.io/recommended-cloudflare-performance-security-settings-guide/)
- Codebase read directly (HIGH confidence, not web-sourced): `backend/ticketing_service.py`, `backend/tickets_escalation_service.py`, `backend/tickets_endpoints.py`, `backend/tickets_service.py`, `backend/compliance_remediation_service.py`, `backend/cloud_checks_service.py`, `backend/cloud_checks_endpoints.py`, `backend/cloud_account_endpoints.py`, `backend/mcp_server.py`

---
*Feature research for: GRC/compliance platform — remediation operations (v3.2 milestone)*
*Researched: 2026-07-20*
