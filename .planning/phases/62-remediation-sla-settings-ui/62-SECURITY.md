---
phase: 62
slug: remediation-sla-settings-ui
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-08-10
---

# Phase 62 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| browser → `/api/settings/remediation-sla` | Only boundary this phase crosses. Authenticated user's `windowDays` value crosses on write; tenant's stored value crosses back on read. Authorization (admin-only write) and range validation both live server-side, unchanged by this phase. | `{windowDays: number}` |
| `RemediationSlaSettings` → `services/apiService.authFetch` | In-process. Bearer token + refresh handling attached here; a bare `fetch` would bypass them. | Bearer token |
| `SettingsDashboard` tab row → panel mount | In-process. Determines which authenticated users can *see* the panel. Deliberately ungated (D-01), mirroring the route's own ungated read. | n/a |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-62-01 | Elevation of Privilege | `RemediationSlaSettings.handleSave` / new tab button | high | mitigate | No client-side permission conditional (grep for `canManageSettings\|canManageRBAC\|isSuperAdmin\|hasPermission\|useUser(` returns 0 hits); server admin gate on PATCH is the sole boundary; rejected write surfaces the generic error toast (test-verified). | closed |
| T-62-02 | Tampering | `saveRemediationSlaWindow` request body `windowDays` | medium | mitigate | Client clamps input to `[1,365]` on change, disables Save when out of range; server `Field(ge=1, le=365)` is the authoritative bound (422 on violation). | closed |
| T-62-03 | Information Disclosure | error toast copy on write failure | low | mitigate | Bare `catch {}` (no error argument bound); single hardcoded toast string for every failure mode; no status/role/endpoint interpolation possible. | closed |
| T-62-04 | Information Disclosure | cross-tenant read via `fetchRemediationSlaWindow` | medium | accept | Tenant scoping enforced server-side, unchanged by this phase; new client wrapper sends no tenant parameter. Accepted as an inherited, unmodified control — this phase adds no new surface. | open — below high threshold (non-blocking) |
| T-62-05 | Spoofing | auth-token attachment on the two new client calls | low | mitigate | Both new wrappers route through the shared `authFetch` helper (bearer + refresh), never a bare `fetch` (2/2 call sites confirmed). | closed |
| T-62-SC | Tampering | npm/pip/cargo installs | high | mitigate | Zero package installs this phase — `package.json`/`package-lock.json` diff empty across both phase commits; no `backend/` file touched. | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-62-01 | T-62-04 | Cross-tenant read isolation for `GET /api/settings/remediation-sla` is enforced entirely server-side and is unchanged by this phase — the new `fetchRemediationSlaWindow` client wrapper sends no tenant parameter and cannot influence scoping. Re-verification of the underlying isolation control belongs to a dedicated `/gsd-secure-phase` pass over the unchanged server module (Phase 44), not this UI-only phase. | gsd-security-auditor (Phase 62 audit) | 2026-08-10 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-08-10 | 6 | 5 | 1 (non-blocking) | gsd-security-auditor |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-08-10
