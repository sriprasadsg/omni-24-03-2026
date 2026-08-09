# Phase 55 — Advanced Threat Detection & Response — CONTEXT

**Milestone:** v3.4 (Native Security Scanning & Autonomous Remediation) — closing phase
**Requirements:** INT-04, AUT-03, COMM-01
**Depends on:** Phase 51 (vuln engine), 53 (autonomous remediation), 54 (UI/API)

## Goal

Real-time threat intelligence correlation, predictive anomaly detection, automated containment/isolation, SOC integration.

## Success criteria (what must be TRUE)

1. Native v3.4 findings (NSCAN/VULN/FIM) and remediation history correlate with existing threat-intel/SIEM data through a real correlation path (INT-04).
2. A predictive/anomaly signal (UEBA-based) can trigger automated containment via the existing Phase 53 remediation engine, gated by the same approval/dry-run/audit guarantees (AUT-03).
3. Findings/remediation events are pushed to an external SIEM/syslog target in OCSF format via the existing webhook infrastructure (COMM-01).

## Locked decisions

- **D-01 — Extend existing correlation infra, don't rebuild (INT-04).** `siem_engine.py` / `threat_intel_endpoints.py` already have correlation logic (134 + 293 lines). Extend them to ingest `security_scan_results`, `vulnerabilities`, `fim_events`, and `remediation_audit` as correlation inputs, rather than building a parallel correlation path. Matches the established pattern from Phase 51/53 of extending real existing infra over building duplicate new systems.
- **D-02 — Predictive containment reuses Phase 53's remediation engine (AUT-03).** `ueba_engine.py`/`ueba_service.py`'s anomaly score becomes a new `finding_type` (e.g. `"anomaly"`) that `autonomous_remediation_service.remediate()` consumes — the SAME playbook selection / dispatch / poll / verify / audit machinery Phase 53 already built and tested. No new containment mechanism, no agent-local engine (consistent with Phase 53's own D-01: backend-orchestrated, agent executes commands).
- **D-03 — SOC integration is outbound OCSF push (COMM-01).** Reuse `webhook_service.py` to push OCSF-formatted (per `ocsf_endpoints.py` conventions) alerts/findings/remediation events to an external SIEM/syslog target. Outbound only — no inbound alert-ingestion endpoint this phase.
- **D-04 — Same approval gate as Phase 53, no autonomy exception (AUT-03).** Containment actions dispatched from a predictive/anomaly trigger go through the IDENTICAL default-on approval gate + dry-run + DB-lease concurrency cap + audit trail Phase 53 built. No faster/autonomous bypass for "real-time" urgency — consistency and safety over speed (explicit user choice over a confidence-threshold auto-dispatch alternative).

## Scope fences (MUST NOT)

- MUST NOT build a second/parallel remediation or dispatch engine — predictive containment routes through the existing `autonomous_remediation_service.remediate()` path (D-02).
- MUST NOT bypass Phase 53's approval gate for containment actions, regardless of anomaly confidence (D-04).
- MUST NOT put an LLM in the containment execution path (inherits Phase 53's D-02 deterministic-only constraint).
- MUST NOT build inbound SOC alert ingestion this phase (D-03, outbound only).
- MUST NOT duplicate existing SIEM/threat-intel/webhook/OCSF endpoints — extend them.
- MUST NOT access `db._db` in new/extended handlers.

## Pitfalls

- **Correlation input volume** — NSCAN/VULN/FIM/remediation_audit could be high-volume; bound/paginate whatever the correlation engine reads, don't load unbounded history (same pitfall as Phase 54's findings feed).
- **Anomaly-to-finding mapping** — UEBA anomaly scores don't have an obvious existing finding_class → playbook mapping; this needs explicit design during planning (which playbook fires for which anomaly type, or a new default containment playbook needed in the Phase 53 store).
- **Webhook delivery failure** — outbound SIEM push must not block the correlation/finding pipeline; fire-and-forget or bounded-retry, matching `webhook_service.py`'s existing failure-handling pattern.
- **False positives on automated containment** — mitigated by design since this reuses Phase 53's human approval gate (D-04), but the anomaly scoring itself should stay conservative given containment actions are destructive.

## Deferred Ideas

(none raised during discussion — scope stayed within the phase boundary)

## Canonical refs

- `.planning/ROADMAP.md` — Phase 55 section (goal, requirements, dependencies)
- `.planning/phases/53-autonomous-remediation/53-CONTEXT.md` — remediation engine contract this phase's containment path reuses
- `.planning/phases/54-integration-operator-ui/54-CONTEXT.md` — operator UI/API pattern precedent
- `backend/siem_engine.py`, `backend/threat_intel_endpoints.py` — existing correlation infra to extend (D-01)
- `backend/ueba_engine.py`, `backend/ueba_service.py` — existing anomaly/UEBA infra (D-02)
- `backend/webhook_service.py`, `backend/ocsf_endpoints.py` — existing webhook + OCSF infra to reuse (D-03)
- `backend/autonomous_remediation_service.py` — remediation engine this phase's containment trigger feeds into (D-02, D-04)

## Plan breakdown

Left to the planner. The 4 existing `55-0N-PLAN.md` files are empty (0-byte) placeholders and will be overwritten:

| Plan | Scope | Requirements |
|------|-------|--------------|
| 55-01 | Threat intelligence correlation | INT-04 |
| 55-02 | Predictive anomaly detection | AUT-03 |
| 55-03 | Automated containment/isolation | AUT-03 |
| 55-04 | SOC integration (syslog/SIEM, OCSF) | COMM-01 |
