# Phase 75: Permission Resolver & Single Source of Truth - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-12
**Phase:** 75-permission-resolver-single-source-of-truth
**Areas discussed:** Admin role sets, ITAM role reach, Seeded role documents, Role list & fallback, Role assignment & unknown roles

---

## Admin role sets

| Option | Description | Selected |
|--------|-------------|----------|
| Same set | `admin` aliases `Tenant Admin`; the 18-permission gap is drift | ✓ |
| Keep admin narrower | Keep today's gap on purpose | |

| Option | Description | Selected |
|--------|-------------|----------|
| Tenant admin defaults | Move the 26 catalogues granted only by the seeded document into the tenant-admin defaults; no other role gains | ✓ |
| Decide per role | Also grant read-only ones to user/analyst/viewer | |

| Option | Description | Selected |
|--------|-------------|----------|
| Super-admin only | Federated Learning, Goal System, Jobs, Predictive Health, Vector DB, WebGPU stay platform-only | ✓ |
| Tenant admins too | Add them to the tenant-admin defaults | |
| Split them | Jobs + Predictive Health to tenant admins, the 4 AI-infra pages super-admin | |

| Option | Description | Selected |
|--------|-------------|----------|
| Union | Other built-in roles get everything any current source grants; nobody loses access | ✓ |
| Strictest | Only what all sources agree on | |

| Option | Description | Selected |
|--------|-------------|----------|
| Super-admin only | Remove `manage:tenants` from tenant admins and require super-admin on the 3 bundle routes | ✓ |
| Keep, add tenant check | Tenant admins keep it, restricted to their own tenant_id | |

| Option | Description | Selected |
|--------|-------------|----------|
| Stop writing it | Signup stops writing the unused per-user permissions array; existing records ignored | ✓ |
| Make it per-user grants | Fold into effective permissions | |

| Option | Description | Selected |
|--------|-------------|----------|
| Wildcard ["*"] | Matches existing backend super-admin resolution | ✓ |
| Explicit full list | Expand every permission string | |
| You decide | Leave to planner | |

**Notes:** Two "more questions" rounds. The `manage:tenants` question came from a finding made by code reading during discussion: the `tenants` collection is exempt from tenant isolation, and the bundle-assignment routes check only `manage:tenants`. That allows a cross-tenant bundle write by any Tenant Admin.

---

## ITAM role reach

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, all three (view:profile) | Profile/MFA, My Tasks, Notification Prefs | ✓ |
| No | ITAM-only | |

| Option | Description | Selected |
|--------|-------------|----------|
| No, land in ITAM (view:dashboard) | Phase 77 guarantees the landing view | ✓ |
| Yes | Grant the main dashboard | |

| Option | Description | Selected |
|--------|-------------|----------|
| Keep view:assets | Shared asset store; Phase 78 joins agents to assets | ✓ |
| ITAM console only | Drop view:assets | |

---

## Seeded role documents

| Option | Description | Selected |
|--------|-------------|----------|
| Mirror the table | Rewrite shared documents from the table each startup (name + tenantId "all") | ✓ |
| Insert only if missing | Never touch existing documents | |
| No permission lists in docs | Documents hold metadata only | |

| Option | Description | Selected |
|--------|-------------|----------|
| All built-ins | Add admin + the 3 ITAM roles to the seeded seven | ✓ |
| Only the ITAM three | ACC-02 minimum | |

| Option | Description | Selected |
|--------|-------------|----------|
| Archive them | Move role-writing one-off scripts to an archive folder | ✓ |
| Leave as-is | Note as known copies | |
| Point them at the table | Rewrite the scripts | |

---

## Role list & fallback

| Option | Description | Selected |
|--------|-------------|----------|
| Built-ins + tenant's own | Super Admin listed only to super-admins | ✓ |
| Built-ins only | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Effective | Same resolver as /me | ✓ |
| Document as stored | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Remove the fallback | Empty permissions = no access | ✓ |
| Keep, use real list | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Role/user admins | `manage:users` or `manage:rbac` | ✓ |
| Any signed-in user | | |

---

## Role assignment & unknown roles (added via "Explore more gray areas")

| Option | Description | Selected |
|--------|-------------|----------|
| No assigning above yourself | Assign only roles within your own effective permissions; no self role change | ✓ |
| Fixed tier list | Hard-coded admin tier | |
| Leave as-is | Record escalation as a known gap | |

| Option | Description | Selected |
|--------|-------------|----------|
| Log in, no access | Empty list + server warning; Phase 77 shows the no-access screen | ✓ |
| Refuse login | Reject with a contact-admin message | |

**Notes:** This area came from a second code-reading finding. User CRUD is gated by `manage:assets`, and only super-admin assignment is blocked, so `itam_admin` can escalate to tenant admin.

## Claude's Discretion

- Module layout of the single table and resolver; whether `verify_permission` / `RBACService` delegate to the resolver.
- Whether `itam_admin` also gets `manage:itam`.
- Keeping the client-side `enabledFeatures` intersection unchanged.
- Drift-test mechanism and the per-role diff format.

## Deferred Ideas

- Persisted role create/edit/delete (currently client-memory only) — for Phase 77 discussion (ACC-07/08).
- Per-user permission grants.
- Backend enforcement of tenant `enabledFeatures` (v4.2 out of scope).
