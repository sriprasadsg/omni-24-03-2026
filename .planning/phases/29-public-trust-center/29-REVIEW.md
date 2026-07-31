---
phase: 29-public-trust-center
reviewed: 2026-07-27T00:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - backend/trust_service.py
  - backend/trust_endpoints.py
  - backend/static/trust-page.html
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 29: Code Review Report

**Reviewed:** 2026-07-27T00:00:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Phase 29 exposes a genuinely public, rate-limited Trust Center: `GET/POST /api/public/trust/{slug}`, Host-header/slug tenant resolution, a private-document-stripping view, and a standalone vanilla-JS page. The core threat handling is solid — private-doc URLs are stripped server-side in `_public_view`, the 404 path is identical for slug and domain no-match (no existence leak), public writes derive `ip_address`/`user_agent`/`requested_at` server-side, and consent is enforced before any DB write. The page renders all dynamic text via `textContent` (no HTML injection). Warnings concern an unvalidated `href` scheme on public document links (stored XSS reachable by a tenant admin against external visitors), an ungated admin `GET /profile` that returns private-document URLs, and reliance on the isolation wrapper with an empty filter.

## Warnings

### WR-01: Public document URL rendered into href without scheme validation (stored XSS)

**File:** `backend/static/trust-page.html:309-314`
**Issue:** `link.href = doc.url || '#'` sets the anchor href directly from an admin-controlled `public_documents[].url` that passes through to unauthenticated external visitors. A tenant admin (or anyone who can write the trust profile) can set `url` to `javascript:...`; clicking "Download" on the public page executes script in the visitor's browser. `rel="noopener noreferrer"` and `target="_blank"` do not neutralize a `javascript:` scheme. Neither `update_profile` (`trust_endpoints.py:58-77`) nor the service validates document URL schemes.
**Fix:** Validate the scheme on write (reject anything but `http`/`https`) in `update_profile`, and defensively on render: `link.href = /^https?:\/\//i.test(doc.url) ? doc.url : '#'`.

### WR-02: Admin GET /profile is ungated and returns private-document URLs

**File:** `backend/trust_endpoints.py:45-55`
**Issue:** `PUT /profile`, `GET/PUT /requests` all enforce `_TRUST_ADMIN_ROLES`, but `GET /profile` has no role gate — any authenticated user in the tenant receives the full profile including `private_documents` with their real `url` values (the exact data the public route is careful to strip). A low-privilege tenant member can read the confidential SOC2/audit-report URLs.
**Fix:** Add the same `_TRUST_ADMIN_ROLES` gate to `GET /profile`, or return a role-appropriate view (strip private URLs for non-admins).

### WR-03: get_profile / update_profile rely entirely on the isolation wrapper with empty `{}` filter

**File:** `backend/trust_service.py:59-73`
**Issue:** `find_one({})` and `update_one({}, ..., upsert=True)` carry no explicit `tenantId`, delegating all scoping to the `TenantIsolatedCollection` wrapper injected by the caller. On the public path the wrapper is armed only by the preceding `set_tenant_id(tenant["id"])`; if that contextvar is ever unset (exception between resolve and query, or a caller that forgets it), `update_one({}, upsert=True)` writes/overwrites an unscoped or wrong-tenant profile. Defense-in-depth is absent because there is no explicit tenant predicate to fall back on.
**Fix:** Pass an explicit `{"tenantId": tenant_id}` filter (the service already receives `tenant_id`) so scoping holds even if the wrapper or context is misconfigured.

## Info

### IN-01: Public access request `reason` accepted but not required

**File:** `backend/trust_endpoints.py:152-159`
**Issue:** `AccessRequestCreate.reason` is required with `max_length=2000`, but the HTML form's `reason` textarea has no `required` attribute (`trust-page.html:242`), so an empty string is submitted. Minor UX/validation mismatch; server still accepts empty string.
**Fix:** Either make `reason` optional server-side or `required` client-side, for a consistent contract.

### IN-02: Slug parsing assumes fixed `/trust/{slug}` path position

**File:** `backend/static/trust-page.html:265-268`
**Issue:** `getSlug()` takes `pathname.split('/').filter(Boolean)[1]`. If the page is ever served under a different mount path, the slug index breaks silently (renders not-found).
**Fix:** Acceptable given the fixed route; note the coupling if the mount path changes.

### IN-03: `_ensure_trust_slug` update_one not upsert — no-op if tenant doc absent

**File:** `backend/trust_service.py:122-132`
**Issue:** `db.tenants.update_one({"id": tenant_id}, {"$set": {"trust_slug": slug}})` without `upsert=True`; if the tenant document does not yet exist, the slug is generated and returned but never persisted, so the next call regenerates a different slug and public links silently rotate.
**Fix:** Guard for `matched_count == 0` (or persist during tenant creation); a tenant should always have a row, but fail loudly if not.

---

_Reviewed: 2026-07-27T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
