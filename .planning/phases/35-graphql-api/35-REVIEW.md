---
phase: 35-graphql-api
reviewed: 2026-07-27T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - backend/graphql_api/schema.py
  - backend/graphql_api/types.py
  - backend/graphql_api/resolvers.py
  - backend/graphql_endpoints.py
  - backend/tests/test_graphql.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 35: Code Review Report

**Reviewed:** 2026-07-27
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

GraphQL layer (strawberry) mounted at `/api/graphql`. Tenant isolation and RBAC
enforced in every resolver via `_authorized_tenant` (`verify_permission` +
tenant scoping) and `is_super_admin` for tenants. Auth model is sound: bearer
token resolved once in `_graphql_context`, resolvers read `current_user` from
context and return `[]` on any auth/RBAC failure — no cross-tenant leak. Test
coverage is good (isolation, unauth, RBAC-denied, cross-tenant, partial-perms).

No Critical issues. Two Warnings (data-completeness cap, no GraphQL query
hardening) and three Info items.

## Warnings

### WR-01: Silent result truncation at 1000 docs

**File:** `backend/graphql_api/resolvers.py:44,68,90,113,134`
**Issue:** Every resolver caps `.to_list(length=1000)`. A tenant with >1000
compliance controls / risks / users / evidence items silently loses rows — no
pagination, no error, no indicator. Callers cannot tell a truncated list from a
complete one, which is a correctness/data-completeness bug for larger tenants.
**Fix:** Add pagination (cursor/offset args) to the schema fields and page
through, or at minimum surface a `hasMore`/`totalCount` field. Interim:
```python
LIST_CAP = 1000
docs = await mongodb.db.compliance_controls.find(
    {"tenantId": tenant_id}, {"_id": 0}
).to_list(length=LIST_CAP + 1)
truncated = len(docs) > LIST_CAP
docs = docs[:LIST_CAP]
# expose `truncated` on the response type
```

### WR-02: No query-depth/complexity limit; introspection publicly reachable

**File:** `backend/graphql_api/schema.py:41`, `backend/graphql_endpoints.py:34`
**Issue:** `strawberry.Schema(query=Query)` is built with no
`extensions=[QueryDepthLimiter(...)]` / complexity limiter, and the endpoint
serves unauthenticated introspection by design (documented). Impact is limited
today because the schema types are flat (no nested object relations), but as
ReBAC relation fields (`owner_id`, `viewer_user_ids`) grow into resolved
sub-objects, unbounded depth/alias queries become a DoS vector, and open
introspection discloses the full schema to unauthenticated callers.
**Fix:**
```python
from strawberry.extensions import QueryDepthLimiter, AddValidationRules
from graphql.validation import NoSchemaIntrospectionCustomRule
schema = strawberry.Schema(
    query=Query,
    extensions=[QueryDepthLimiter(max_depth=10)],
)
```
Gate introspection behind auth (or disable in production) via
`AddValidationRules([NoSchemaIntrospectionCustomRule])`.

## Info

### IN-01: SUMMARY file paths do not match actual source paths

**File:** `35-01-SUMMARY.md:9-12`, `35-02-SUMMARY.md:9`
**Issue:** SUMMARYs reference `backend/graphql/schema.py`, `types.py`,
`resolvers.py` and describe `CustomGraphQLRouter.get_context`. Actual code lives
in `backend/graphql_api/` and uses a `context_getter` function
(`_graphql_context`), not a `CustomGraphQLRouter` subclass. `graphql_endpoints.py`
even notes subclass `get_context` is NOT called — so the SUMMARY describes a
discarded design. Stale docs mislead future maintainers.
**Fix:** Update SUMMARYs to the `graphql_api/` paths and `context_getter` model.

### IN-02: Magic number 1000 duplicated across five resolvers

**File:** `backend/graphql_api/resolvers.py:44,68,90,113,134`
**Issue:** The list cap is hardcoded in each resolver.
**Fix:** Hoist to a module constant `LIST_CAP = 1000` (pairs with WR-01 fix).

### IN-03: Empty `graphql_api/__init__.py`

**File:** `backend/graphql_api/__init__.py`
**Issue:** Empty file; imports use absolute `graphql_api.*` paths and rely on
`backend/` being on `sys.path`. Works in practice but the package boundary is
implicit. Non-blocking.
**Fix:** None required; optionally re-export the schema for a stable import.

### IN-04: Auth failure and empty-result are indistinguishable

**File:** `backend/graphql_api/resolvers.py:39-40,63-64,86-87,108-109,131`
**Issue:** All auth/RBAC failures return `[]` — a client cannot tell "not
permitted" from "no data." Documented as intentional (avoids leaking existence),
which is defensible, but worth noting for API consumers.
**Fix:** None required; if clients need to distinguish, add a typed error union.

---

_Reviewed: 2026-07-27_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
