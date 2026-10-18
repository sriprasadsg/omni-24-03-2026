# Phase 77: Fail-Closed Sidebar, View Gate & Role Visibility - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-18
**Phase:** 77-fail-closed-sidebar-view-gate-role-visibility
**Areas discussed:** Role editing: real or read-only, Blocked screens & zero access, 'What can this role see' view, manage:X unlocks the menu item

---

## Role editing: real or read-only

| Option | Description | Selected |
|--------|-------------|----------|
| Custom tenant roles | Create/edit/delete own tenant's custom role documents and assign them; built-ins fixed by the code table | ✓ |
| Read-only roles | No role writes; remove fake buttons; reword SC4/SC5 | |
| Also narrow built-in roles | Custom roles plus per-tenant override narrowing built-ins (needs resolver change) | |

**User's choice:** Custom tenant roles

| Option | Description | Selected |
|--------|-------------|----------|
| manage:rbac + ceiling | manage:rbac holders in the tenant plus Super Admin; role ⊆ editor's closure (75 D-20); platform-only permissions never grantable | ✓ |
| Tenant admins only | Only Tenant Admin/admin and Super Admin edit roles | |
| Super Admin only | Platform owner defines custom roles | |

**User's choice:** manage:rbac + ceiling

| Option | Description | Selected |
|--------|-------------|----------|
| Block until reassigned | Delete refused with the users still holding the role | ✓ |
| Reassign to viewer | Delete succeeds, holders drop to viewer, audited | |
| Leave users with no access | Delete succeeds, holders resolve to no permissions | |

**User's choice:** Block until reassigned

| Option | Description | Selected |
|--------|-------------|----------|
| Users screen + SSO/LDAP maps | Assignable wherever a built-in role is, behind the ceiling | ✓ |
| Users screen only | SAML/LDAP keep built-in roles only | |

**User's choice:** Users screen + SSO/LDAP maps

---

## Blocked screens & zero access

| Option | Description | Selected |
|--------|-------------|----------|
| In-place no-access panel | Content area explains the missing access with a Go-to button; sidebar stays | ✓ |
| Redirect + toast | Jump to landing with a toast | |
| Silent redirect | Jump to landing with no message | |

**User's choice:** In-place no-access panel

| Option | Description | Selected |
|--------|-------------|----------|
| Dashboard, else first allowed | Dashboard with view:dashboard, else first allowed menu item | ✓ |
| Per-role home | Fixed home per built-in role | |
| Remember last screen | Last open screen if still allowed | |

**User's choice:** Dashboard, else first allowed

| Option | Description | Selected |
|--------|-------------|----------|
| Full-page no-access screen | No sidebar; email, role, tenant, ask your administrator, Sign out, Retry | ✓ |
| App shell, empty menu | Header and empty sidebar with the message | |

**User's choice:** Full-page no-access screen

| Option | Description | Selected |
|--------|-------------|----------|
| Hide them, skip the fetch | Not rendered and not fetched (extends C6 ifOn) | ✓ |
| Show a locked placeholder | Frame with "Needs <permission>", fetch skipped | |
| Leave as is | Gate whole screens only | |

**User's choice:** Hide them, skip the fetch

---

## 'What can this role see' view

| Option | Description | Selected |
|--------|-------------|----------|
| In Settings > Roles | Per-role "What it can see" panel next to the editor | ✓ |
| Separate 'Role Access' page | Own sidebar item | |

**User's choice:** In Settings > Roles

| Option | Description | Selected |
|--------|-------------|----------|
| Role ∩ tenant switches | Role effective permissions narrowed by tenant feature switches; switched-off listed separately | ✓ |
| Role permissions only | Ignore switches and tier | |

**User's choice:** Role ∩ tenant switches

| Option | Description | Selected |
|--------|-------------|----------|
| manage:rbac/users, own tenant | Whoever can list roles, own tenant; Super Admin any tenant; platform roles to Super Admin only | ✓ |
| Super Admin only | Platform owner only | |

**User's choice:** manage:rbac/users, own tenant

| Option | Description | Selected |
|--------|-------------|----------|
| Per-role, grouped by menu | One role's screens grouped by sidebar group | ✓ |
| Roles × screens matrix | Grid of roles vs ~200 screens | |
| Both | Panel plus matrix toggle | |

**User's choice:** Per-role, grouped by menu

---

## manage:X unlocks the menu item

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, closure in /me | /login and /me deliver manage:X ⇒ view:X; itam_admin gains Assets and Certificates | ✓ |
| Grant view:assets explicitly | Add view:assets to itam_admin in the table only | |
| Keep as is | Menu on view:X only | |

**User's choice:** Yes, closure in /me

| Option | Description | Selected |
|--------|-------------|----------|
| view:X and request:X | One closure rule everywhere (matches 75 D-20) | ✓ |
| view:X only | Matches the backend read guard exactly | |

**User's choice:** view:X and request:X
**Notes:** Scouting found `backend/itam_asset_request_endpoints.py:21` checks `request:assets` strictly; recorded as a constraint so the backend accepts the closure too.

---

## Claude's Discretion

- Role-write API shape, audit entries, implied-permission display in the editor
- Where the closure is computed, as long as delivery and enforcement cannot diverge
- Unifying super-admin name checks (75 D-05)
- 403-refresh debouncing; wording and styling of the no-access screens (subject to UI-SPEC)
- How the role access data is computed (backend endpoint preferred)
- SC5 test structure

## Deferred Ideas

- Narrowing built-in roles per tenant (needs a resolver change)
- Roles × screens comparison matrix
- Phase 76-11 "Needs a human decision" manifest policy items (not discussed)
- Reviewed todo not folded: "Fix stale capability-count assertions in integration.rs"
