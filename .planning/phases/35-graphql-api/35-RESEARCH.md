# Phase 35: GraphQL API - Research

**Researched:** 2026-07-10
**Domain:** GraphQL API implementation for Compliance/Evidence/Risk data model
**Confidence:** HIGH

## Summary

This phase stands up a GraphQL API alongside existing FastAPI REST endpoints. The primary challenge is maintaining strict tenant isolation and RBAC parity.

The existing REST stack uses `TenantMiddleware` to set tenant context via a `ContextVar` (`set_tenant_id`) and `rbac_service` (FastAPI dependency injection) for authorization. GraphQL resolvers must explicitly check these contexts, as the REST dependencies will not automatically apply to GQL resolvers unless specifically integrated.

**Primary recommendation:** Use `Strawberry` for type-safe GraphQL implementation in FastAPI, ensuring custom execution context that wraps REST auth dependencies (RBAC + Tenant).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| GQL Schema | API / Backend | — | Defined in backend. |
| Tenant Scoping | API / Backend | — | Resolved via ContextVar at request start. |
| RBAC Enforcement | API / Backend | — | Must be checked at resolver level. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `strawberry-graphql` | [ASSUMED] | GraphQL API | Type-safe, FastAPI-friendly. |

## Package Legitimacy Audit

> **Required** whenever this phase installs external packages. Run the Package Legitimacy Gate protocol before completing this section.

*Pending `npm/pip` package legitimacy check.*

## Architecture Patterns

### Recommended Project Structure
```
src/
└── graphql/         # GraphQL schema, types, resolvers
```

### Pattern 1: Tenant-Aware Resolvers
**What:** Resolvers MUST access `tenant_context` to filter DB queries.
**When to use:** Every read/write query.
**Example:**
```python
# Conceptual
@strawberry.field
async def evidence(info: Info) -> List[Evidence]:
    tenant_id = get_tenant_id() # From tenant_context
    return await db.evidence.find({"tenantId": tenant_id}).to_list(None)
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| GQL Schema | Custom string parsing | `strawberry` | Type safety, IDE support. |

## Common Pitfalls

### Pitfall 1: Bypassing RBAC
**What goes wrong:** GQL resolvers fail to check `rbac_service`.
**Why it happens:** GQL is a new surface; existing FastAPI dependencies aren't automatically used.
**How to avoid:** Explicitly call `rbac_service.has_permission()` inside every GQL resolver.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Strawberry is best choice | Standard Stack | High-effort refactor if wrong. |

## Sources

### Primary (HIGH confidence)
- `backend/rbac_service.py` - RBAC pattern analysis
- `backend/tenant_middleware.py` - Tenant isolation pattern analysis

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM - Need to confirm if Strawberry works with current FastAPI/Motor setup.
- Architecture: HIGH - REST auth patterns are clear.
- Pitfalls: HIGH - Common GQL risk.

**Research date:** 2026-07-10
**Valid until:** 2026-08-09
