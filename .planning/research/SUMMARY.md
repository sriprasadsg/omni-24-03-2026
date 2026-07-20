# Project Research Summary

**Project:** Enterprise OmniAgent — Security & Compliance Portal
**Domain:** Multi-tenant GRC/CSPM platform (FastAPI + Motor/MongoDB + React/TS backend/frontend) + Rust endpoint agent — v3.2 milestone: agent modernization + remediation-ops feature gaps
**Researched:** 2026-07-20
**Confidence:** HIGH

## Executive Summary

This is a subsequent-milestone integration effort on an already-mature multi-tenant GRC/CSPM platform, not greenfield work. Research confirms two independent workstreams: (1) a Rust endpoint-agent dependency modernization that is **already staged and verified compiling clean** on the current branch — the remaining work is a TLS-backend decision (reqwest 0.13's native-tls→rustls default flip) and shipping the 2.1.0 rebuild; and (2) four remediation-ops features (ticket bridge, SLA/escalation, control comment threads, and real CSPM check catalogs for OCI/Alibaba/Cloudflare) that close named gaps against this codebase's own established patterns. The correct approach throughout is disciplined reuse: existing Jira/ServiceNow connectors, the existing `_compute_sla()` pure function, the existing tenant-isolation wrapper, and the existing `DO_CHECKS`-shaped check-definition pattern all already do 80% of the work — new code should be thin adapters and new data files, not new subsystems.

The dominant risk is not "what to build" but "which of this codebase's existing sharp edges to avoid re-triggering." Architecture and Pitfalls research (both HIGH confidence, grounded directly in source) independently converge on the same five hazards: (1) background schedulers must use the raw unwrapped `mongodb.db`, never `get_database()`, or tenant-isolation fail-closed logic silently returns zero results forever; (2) comment threads must go into a new tenant-scoped collection, never `$push`-ed onto `compliance_controls`, which is a global tenant-isolation-exempt reference collection — embedding there is a cross-tenant data leak by construction; (3) the CSPM provider-allowlist gate that actually blocks checks (`RUNNABLE_PROVIDERS` in `cloud_checks_service.py`) is only 1 of up to 4 historically-duplicated gates — the other two are already correctly widened, so the real fix is a one-line change plus three new check-definition modules; (4) `ticketing_service.py`'s connectors are hardcoded to a security-alert dict shape and need an explicit adapter, not a direct pass-through, or tickets render "Process: N/A"; (5) new routers/frontend components must be explicitly wired into `router_registry.py` and `Sidebar.tsx`/`App.tsx` respectively — this codebase has a documented recurring failure mode of built-but-unreachable features.

Recommended mitigation is process, not new tooling: every new background job copies the `tickets_escalation_service.py`/`app_startup.py` raw-db registration pattern verbatim; every new collection defaults through (never gets added to) the tenant-isolation exemption allowlist; every new provider-check addition greps all provider-allowlist literals before touching any one; every ticket-bridge call goes through an explicit alert-shape adapter function; and every phase's "done" checklist includes a live browser click-through and a two-tenant isolation test, not just passing API/unit tests — this mirrors the codebase's own established verification bar (the CHK-03 precedent).

## Key Findings

### Recommended Stack

Two independent stacks are in play. **Part (a) — Rust agent:** crate bumps (`reqwest` 0.12→0.13, `sysinfo` 0.32→0.39, `tokio-tungstenite` 0.23→0.30, `rusqlite` 0.32→0.40, `hostname` 0.3→0.4, `serde_yaml`→`serde_norway`) are already staged in `Cargo.toml`/`Cargo.lock` on the current branch and verified compiling clean locally (`cargo check --offline`, zero errors). The only open decision is whether to explicitly pin `reqwest`'s `native-tls` feature to preserve pre-0.13 TLS behavior (Windows corporate-CA trust) rather than silently accepting the new rustls default. **Part (b) — CSPM SDKs:** `oci`, `cloudflare`, and `aliyun-python-sdk-core-v3` are already pinned dependencies with existing (fully mocked) ingest stub modules; four new Alibaba V2.0 typed SDK packages (`alibabacloud_config20200907`, `alibabacloud_sas20181203`, `alibabacloud_tea_openapi`, `alibabacloud_credentials`) need adding for Alibaba's actual compliance/config-drift API surface (the existing V1 `AcsClient` package is Security-Center-alerts only, not config-compliance).

**Core technologies:**
- `reqwest 0.13.4` (Rust) — HTTP client for agent↔backend comms; already resolved, verify TLS feature pin before shipping
- `serde_norway 0.9.42` — maintained YAML fork replacing archived `serde_yaml`; already migrated in `src/config.rs`
- `oci` / `cloudflare` (Python, already installed) — official SDKs for OCI Cloud Guard and Cloudflare zone-security-settings CSPM checks
- `alibabacloud_config20200907` / `alibabacloud_sas20181203` (new) — typed V2 SDKs for Alibaba Config-compliance and Security-Center baseline checks, the correct CSPM surface (not the existing V1 alert-polling SDK)

### Expected Features

Four v3.2 feature areas, all P1/table-stakes per competitor research (Vanta, Drata, Cyber Sierra) and this codebase's own established DigitalOcean/AWS reference patterns.

**Must have (table stakes):**
- Remediation task → ticket, manual create + optional auto-create on high/critical priority, reusing existing Jira/ServiceNow connectors via an adapter
- One-way close-loop sync (ticket closed externally → task marked resolved, existing re-scan dispatch triggered) — not full bidirectional sync
- `sla_status` computation (ok/at_risk/breached) + escalation notification + append-only `escalation_history`, scoped to `compliance_remediation_tasks` only
- Threaded comments on `control_id` (author/text/timestamp, @mention detection+notification), cloned from the existing tickets comment *endpoint shape* — but a new tenant-scoped collection, not embedded storage
- Real, minimal-but-correct (~8-10 each) CSPM check catalogs for OCI (CIS OCI Foundations aligned), Alibaba (AWS-equivalent-service mapped), Cloudflare (native Security Center taxonomy), wired into the existing `run_checks()` evaluation engine with `simulated` flagging

**Should have (competitive):** cross-framework check reuse via `frameworks: [...]` field (already the established pattern — just don't stub it empty for new providers).

**Defer (v2+):** bidirectional continuous ticket field sync (needs webhook infra), live SDK-polled CSPM scanning (architecturally inconsistent with every existing provider including AWS/Azure/GCP), severity-tiered SLA policy engine, auditor-visible comment toggle.

### Architecture Approach

All four features attach to the existing FastAPI/Motor/tenant-isolation/router-registry/WebSocket skeleton with no new infrastructure (no message bus — everything is direct in-process `await` with try/except failure isolation, matching every existing cross-service call in this codebase). The ticket bridge is a synchronous adapter call from `compliance_remediation_service.create_task/update_task`; SLA/escalation is a new sibling background-loop module (not an extension of `tickets_escalation_service.py`, which is a genuinely different schema/domain) that reuses only the pure `_compute_sla()` helper; comment threads are a new tenant-scoped `control_comments` collection (never embedded on the tenant-exempt `compliance_controls` doc); CSPM providers are new dedicated `cloud_checks_<provider>.py` data modules plus one line widening `RUNNABLE_PROVIDERS`.

**Major components:**
1. `ticketing_bridge.py` (new) — adapts remediation-task fields into the alert-shape `ticketing_service.py` expects; calls existing (untouched) connectors; writes `ticket_provider`/`ticket_ref`/`ticket_url` back
2. `compliance_remediation_sla_service.py` (new) — raw-db background sweep for due-date breach, reusing `tickets_helpers._compute_sla()`, registered in `app_startup.py` alongside existing schedulers
3. `control_comments_service.py` + `control_comments_endpoints.py` (new) — tenant-scoped comment CRUD, mounted as a sub-panel inside the existing `FrameworkDetail.tsx` expanded-control row (no new nav entry)
4. `cloud_checks_oci.py` / `cloud_checks_alibaba.py` / `cloud_checks_cloudflare.py` (new) — flat check-definition data files, concatenated into `CLOUD_CHECKS`, requiring one `RUNNABLE_PROVIDERS` tuple update in `cloud_checks_service.py`

### Critical Pitfalls

1. **SLA scheduler silently returns zero results forever** — background `asyncio` tasks have no request context, so `get_database()`'s tenant-isolation contextvar fail-closes to a non-existent tenant ID. Register the scheduler with the raw `mongodb.db`, exactly like `tickets_escalation_service.py` already does.
2. **Comment threads leak across tenants if embedded on `compliance_controls`** — that collection is on the tenant-isolation exemption allowlist (global reference data). Use a new, non-exempted, tenant-scoped `control_comments` collection instead; clone only the endpoint *shape* from tickets, not the `$push`-to-parent-doc storage mechanism.
3. **CSPM provider allowlist widening touches only 1 of up to 4 duplicated gates** — `cloud_checks_endpoints.py` and `cloud_account_endpoints.py` already list oci/alibaba/cloudflare; only `cloud_checks_service.py`'s `RUNNABLE_PROVIDERS` (the actual execution gate) is stale. Grep all provider-list literals before assuming which gates need touching.
4. **Ticket-bridge naively passes a remediation task where `ticketing_service.py` expects an alert dict** — `.get()` silently absorbs the field-name mismatch, producing tickets with "Process: N/A"/"MITRE Technique: N/A" instead of erroring. Requires an explicit adapter function.
5. **New routers/frontend components built but never wired in** — `router_registry.py` registration and `Sidebar.tsx`/`App.tsx`/existing-dashboard mounting are both easy to skip and have no automated check; this codebase has documented recurring instances of exactly this failure. Verify via live route hit + live browser click-through, not unit tests alone.

## Implications for Roadmap

Suggested phase structure (5 phases):

### Phase 1: Rust Agent 2.1.0 Dependency Modernization
**Rationale:** Fully independent, already-staged, verified-compiling work in a separate toolchain — zero coupling to the remediation-ops features. Good first/parallel-track phase.
**Delivers:** Committed crate bumps, an explicit TLS-feature decision, and a rebuilt 2.1.0 agent executable.
**Addresses:** Stack research Part (a) findings.
**Avoids:** Shipping a silent TLS-backend behavior change without a deliberate decision.

### Phase 2: CSPM Check Catalogs for OCI/Alibaba/Cloudflare
**Rationale:** Most isolated of the four remediation-ops features — new data-only modules, one allowlist line, zero shared schema with the other three. Low-risk warm-up.
**Delivers:** `cloud_checks_oci.py`, `cloud_checks_alibaba.py`, `cloud_checks_cloudflare.py` (~8-10 checks each), `RUNNABLE_PROVIDERS` widened, `run_checks()` producing correctly-`simulated`-flagged results end to end.
**Addresses:** FEATURES.md's "real CSPM check catalog" table-stakes item.
**Avoids:** Pitfall 3 (only 1 of N gates widened) and Pitfall 4 (unlabeled simulated results).

### Phase 3: Comment Threads on Compliance Controls
**Rationale:** Second most isolated feature; validates the "new collection, default tenant-isolation path" pattern before higher-risk ticketing/SLA phases.
**Delivers:** New `control_comments` collection + service + endpoints + `ControlCommentsPanel.tsx` mounted inside the existing `FrameworkDetail.tsx` expanded-row.
**Addresses:** FEATURES.md's comment-thread table-stakes item.
**Avoids:** Pitfall 2 (cross-tenant leak via embedding on `compliance_controls`).

### Phase 4: Remediation-to-Ticketing Bridge
**Rationale:** Should land before SLA/escalation since both add fields to the same `compliance_remediation_tasks` document — avoids concurrent schema churn.
**Delivers:** `ticketing_bridge.py` adapter, `ticket_provider`/`ticket_ref`/`ticket_url` fields, manual "Create Ticket" action (+ optional auto-create), one-way close-loop poll.
**Addresses:** FEATURES.md's ticket-bridge and close-loop-sync items.
**Avoids:** Pitfall 5 (alert-shape mismatch).

### Phase 5: SLA/Escalation for Remediation Tasks
**Rationale:** Last, after the ticketing bridge, since it also mutates `compliance_remediation_tasks`, and its background-scheduler pattern is the highest-risk item in this milestone.
**Delivers:** `compliance_remediation_sla_service.py`, compound index `(tenantId, due_date, status)`, schema extension (`escalated`, `escalation_level`, `history`), escalation notifications + audit trail.
**Addresses:** FEATURES.md's SLA-breach-detection and escalation items.
**Avoids:** Pitfall 1 (fail-closed silent zero-result scheduler), Pitfall 9 (missing index at scale), Pitfall 10 (assuming `tickets`-shaped schema fields exist that don't).

### Phase Ordering Rationale
- Rust agent work (Phase 1) is fully decoupled by toolchain and can run in parallel with any/all of Phases 2-5.
- Phases 2 and 3 are ordered before 4 and 5 because they are structurally trivial and fully additive, validating risk-bearing patterns cheaply first.
- Phases 4 and 5 share a mutable document (`compliance_remediation_tasks`) — sequencing avoids schema races.
- Every phase's "done" bar requires router registration verification, live browser click-through, and (for comments/SLA) explicit tenant-isolation testing.

### Research Flags

Needs research/discussion during planning:
- **Phase 5 (SLA/escalation):** schema-extension decision (priority-bump-only vs. new status value) is an unresolved product decision.
- **Phase 4 (ticketing bridge):** trigger condition (auto-create on high/critical vs. fully manual) is an unresolved product decision.

Standard patterns (skip research-phase):
- **Phase 1 (Rust):** already verified compiling; only a TLS-feature decision remains.
- **Phase 2 (CSPM checks):** fully resolved by ARCHITECTURE.md/PITFALLS.md with exact file/line references.
- **Phase 3 (comments):** storage/tenant-isolation decision fully resolved with exact precedent cited.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Part (a) verified via direct local `cargo check`/`cargo build`; part (b) verified via live PyPI queries and direct codebase inspection |
| Features | MEDIUM | Cross-checked against multiple GRC vendor sources but no official API-key-gated docs; codebase-pattern claims are HIGH |
| Architecture | HIGH | Every claim grounded directly in this repo's source, file/line cited throughout |
| Pitfalls | HIGH | 100% internal codebase archaeology against actual source and git history |

**Overall confidence:** HIGH

### Gaps to Address
- reqwest TLS-backend default flip acceptability for all deployment targets — needs a decision from endpoint-deployment owner before 2.1.0 exe ships.
- Ticket auto-create trigger condition — flag for `/gsd-discuss-phase` on the ticketing-bridge phase.
- SLA-breach state representation — flag for `/gsd-discuss-phase` on the SLA/escalation phase.
- Whether `mcp_server.py` duplicates a provider enum cosmetically — 30-second grep confirmation during Phase 2 planning.

## Sources

### Primary (HIGH confidence)
- Direct codebase reads across `backend/`, `agent-install/omni-agent-rs/`, and frontend components
- Local `cargo check --offline` / `cargo build --release --offline` execution
- `pip index versions` live PyPI queries
- [RUSTSEC-2025-0068: serde_yml unsound and unmaintained](https://rustsec.org/advisories/RUSTSEC-2025-0068.html)
- Git history: `e55ba34`, `720a76d`, `772e9058`, `7e050f6`
- `.planning/PROJECT.md`, `.planning/HANDOFF.json`

### Secondary (MEDIUM confidence)
- [reqwest v0.13 rustls-default change](https://seanmonstar.com/blog/reqwest-v013-rustls-default/)
- [Vanta Jira integration docs](https://www.vanta.com/integrations/jira)
- [Prowler OCI authentication docs](https://docs.prowler.com/user-guide/providers/oci/authentication), [Alibaba Cloud CSPM docs](https://www.alibabacloud.com/help/en/security-center/user-guide/cspm), [Cloudflare Security Center docs](https://developers.cloudflare.com/security-center/)

---
*Research completed: 2026-07-20*
*Ready for roadmap: yes*
