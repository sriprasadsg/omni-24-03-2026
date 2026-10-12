# Phase 76: Catalogue Manifest & Backend Route Enforcement - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.

**Date:** 2026-10-12
**Phase:** 76-catalogue-manifest-backend-route-enforcement
**Areas discussed:** Guard scope, View vs manage, Cost fields, New routers (presented as four direct questions in one round to conserve orchestrator context)

| Area | Options | Selected |
|------|---------|----------|
| Guard scope | Assets, Settings, SecOps / Assets + Settings only / All 8 groups | Assets, Settings, SecOps |
| View vs manage | manage implies view for reads / exact strings only | manage implies view |
| Cost fields | Strip finance fields without view:itam / block asset reads | Strip cost fields |
| New routers | Fail the test (deny-by-default) / warn only | Fail the test |

## Claude's Discretion
Manifest and ledger format/location, guard placement and tagging, re-measuring baselines, exact stripped field names.

## Deferred Ideas
Non-priority group guards (ACC-F2); ITAM tab-level gating (ACC-F1).
