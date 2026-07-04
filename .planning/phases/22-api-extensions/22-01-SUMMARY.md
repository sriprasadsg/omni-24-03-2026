---
phase: 22-api-extensions
plan: 01
subsystem: api-extensions
tags: [mcp, ocsf, digitalocean, click-cli]

requires: [17-cloud-checks-expansion]
provides:
  - MCP protocol server (GET /api/mcp/tools, POST /api/mcp/execute/{tool_name})
  - 5 MCP tools: list_frameworks, get_control_status, run_cloud_check, list_findings, get_compliance_score
  - OCSF 1.0 export (GET /api/ocsf/findings, GET /api/ocsf/cloud-checks)
  - 10 DigitalOcean cloud checks added to CLOUD_CHECKS
  - omni-cli.py — Click-based CLI (frameworks list, scan cloud, findings list, score)
  - ApiExtensionsDashboard.tsx
affects: [cloud-checks-expansion]

tech-stack:
  added: [click]
  patterns:
    - "MCP tool execute_tool validates/whitelists params before use in DB filters rather than splicing client JSON directly into MongoDB queries"

key-files:
  created:
    - backend/mcp_server_endpoints.py
    - backend/ocsf_endpoints.py
    - backend/scripts/omni-cli.py
  modified:
    - backend/cloud_checks_service.py
    - backend/router_registry.py
    - components/ApiExtensionsDashboard.tsx

key-decisions:
  - "omni-cli.py rewritten as an actual Click CLI (CR-01) — the originally-reviewed version wasn't a Click CLI at all and couldn't parse the plan's own example invocations"
  - "MCP execute_tool params validated/allowlisted before reaching MongoDB filters (CR-02) — the original implementation spliced unvalidated client JSON directly into query filters, a NoSQL injection vector"
  - "MCP run_cloud_check enforces the same provider allowlist as the equivalent REST endpoint (WR-02), closing a bypass where the MCP path skipped that check"

requirements-completed: [API-01, API-02, API-03, API-04]

duration: unknown (retroactively documented); fix cycle completed 2026-07-04
completed: 2026-07-04
status: complete
---

# Phase 22: API Extensions Summary

**MCP protocol server, OCSF 1.0 findings export, 10 new DigitalOcean cloud checks, and a Click-based CLI — after a code review cycle that caught a NoSQL injection vector, an MCP tool that always returned fabricated data, and a CLI that wasn't actually a CLI.**

## Performance
- **Duration:** unknown for initial implementation — retroactively summarized. The code-review/fix cycle (14 findings, all fixed) was completed 2026-07-04.
- **Files modified:** 6 (mcp_server_endpoints.py, ocsf_endpoints.py, cloud_checks_service.py, omni-cli.py, router_registry.py, ApiExtensionsDashboard.tsx)

## Accomplishments
- MCP protocol server: `GET /api/mcp/tools`, `POST /api/mcp/execute/{tool_name}` with 5 tools (`list_frameworks`, `get_control_status`, `run_cloud_check`, `list_findings`, `get_compliance_score`)
- OCSF 1.0 export: `GET /api/ocsf/findings` (class_uid 2004), `GET /api/ocsf/cloud-checks` (class_uid 5001)
- 10 DigitalOcean checks added to `CLOUD_CHECKS` (firewall rules, managed DB encryption, Spaces bucket public access, load balancer SSL, droplet monitoring, VPC isolation, DB backups, K8s auto-upgrade, App Platform HTTPS, snapshot retention)
- `omni-cli.py`: a real Click CLI (`frameworks list`, `scan cloud --provider do`, `findings list --severity high`, `score --framework soc2`)
- `ApiExtensionsDashboard.tsx`: MCP tools list, OCSF export buttons, DO account setup, CLI quickstart
- Full code review: 5 critical + 6 warning + 3 info findings (22-REVIEW.md). All 14 fixed and verified in `22-REVIEW-FIX.md` (status: all_fixed).

## Task Commits
Initial implementation bundled into a mislabeled commit from an adjacent phase's session (pre-existing repo-history quirk). All 14 review fixes landed in a single consolidated commit: `5e9648f8` (`fix(22): resolve all 14 code review findings (CR-01..05, WR-01..06, IN-01..03)`).

Key fixes within that commit:
1. **CR-01** rewrite `omni-cli.py` as an actual Click CLI matching the plan's example invocations
2. **CR-02** validate/allowlist MCP `execute_tool` params before use in MongoDB filters (NoSQL injection)
3. **CR-03** validate `limit` input on `list_findings`/`get_control_status` instead of raising unhandled exceptions
4. **CR-04** fix `list_frameworks` MCP tool returning an empty list for every tenant
5. **CR-05** fix `get_compliance_score` MCP tool ignoring the `framework` filter and fabricating numbers
6. **WR-02** enforce the same provider allowlist on MCP `run_cloud_check` as the REST endpoint
7. **WR-03** restore the DigitalOcean "snapshot retention" check the plan required but the shipped set silently dropped

## Files Created/Modified
- `backend/mcp_server_endpoints.py` — MCP tool registry + execution (115 lines)
- `backend/ocsf_endpoints.py` — OCSF 1.0 export (72 lines)
- `backend/cloud_checks_service.py` — +10 DigitalOcean checks
- `backend/scripts/omni-cli.py` — Click CLI (109 lines)
- `backend/router_registry.py` — registers `mcp_server_endpoints` and `ocsf_endpoints`
- `components/ApiExtensionsDashboard.tsx` — dashboard UI

## Decisions & Deviations
None beyond the review-fix cycle. Plan executed as specified functionally, but — similar to phase 21 — the initial implementation shipped with a genuine security vulnerability (NoSQL injection via unvalidated MCP tool params) and two MCP tools that silently returned wrong/fabricated data rather than erroring, which the review cycle caught before this reached users.

## Issues Encountered
This phase's `SUMMARY.md` was not created at execution time, causing downstream tooling to treat the phase as unimplemented despite the code, review, and fix cycle all being complete and committed. Retroactively authored after independently verifying via git history and the existing `22-REVIEW.md`/`22-REVIEW-FIX.md` artifacts. No dedicated automated test file exists for this phase's endpoints (not specified in the original plan) — worth adding test coverage for the MCP tool dispatcher and OCSF export shape given the injection/fabrication findings above.

## Next Phase Readiness
Phase 22 implemented, reviewed (14/14 findings fixed). Ready for `/gsd-verify-work 22` (human UAT) and `/gsd-secure-phase 22`. Recommend adding automated test coverage for `mcp_server_endpoints.py` and `ocsf_endpoints.py` before further extension.

---
*Phase: 22-api-extensions*
*Completed: 2026-07-04*
