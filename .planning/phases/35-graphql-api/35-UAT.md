# UAT Report: Phase 35 — GraphQL API

## Overview
Validation of the GraphQL API layer alongside the existing FastAPI REST surface.

## Test Cases

| ID | Description | Result | Notes |
|----|-------------|--------|-------|
| 1 | Hello World Query | Pending | Basic hello-world test exists |
| 2 | Compliance Controls Query | Pending | Needs integration test |
| 3 | Evidence Items Query | Pending | Needs integration test |
| 4 | Risks Query | Pending | Needs integration test |
| 5 | Users Query | Pending | Needs integration test |
| 6 | Tenants Query | Pending | Needs integration test |
| 7 | Cross-tenant Isolation | Pending | Needs integration test |
| 8 | RBAC Enforcement | Pending | Needs integration test |

## Verification Gaps
- Full integration test suite not implemented.
- Human verification with Altair/GraphiQL not yet performed.

## Remediation Plan
1. Implement comprehensive integration tests (`test_graphql.py`).
2. Perform human verification of queries against REST API outcomes.
