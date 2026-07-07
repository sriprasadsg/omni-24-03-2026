# Phase 29: Public Trust Center - Research

**Researched:** 2026-07-07
**Domain:** Retrofitting an internal-only, in-memory, fully-authenticated dashboard module into a DB-backed, genuinely public-facing customer trust page with an external NDA-gated access-request flow and per-tenant custom-domain support (Python/FastAPI/Motor backend, React/TypeScript SPA frontend)
**Confidence:** HIGH (backend architecture, tenant-isolation mechanics, RBAC/rate-limiting precedents — all confirmed by direct in-session reads of this codebase) / MEDIUM (custom-domain scope and NDA-approval-mode — genuinely open product decisions, see Open Questions)

<user_constraints>
## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase. This project runs in yolo/auto mode this milestone — no `/gsd-discuss-phase` was run for Phase 29 (or any other v3.0 phase). This research and the resulting plan must proceed from `.planning/REQUIREMENTS.md` + `.planning/ROADMAP.md` + direct codebase inspection only. There are no locked decisions, discretion notes, or deferred ideas to copy verbatim — everything below is this agent's own research-derived recommendation, and items needing a human product decision are called out explicitly in **Open Questions**.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRUST-01 | Trust Center data is persisted in the database (replacing the in-memory `TrustService` singleton in `trust_service.py`) and survives restarts | See Architecture Patterns → Pattern 1 (Mongo-backed `trust_profiles`/`trust_access_requests` collections, cloned from `privacy_service.py`'s tenant-scoped CRUD shape — not the embedded-versions shape, since a trust profile has no version history requirement) |
| TRUST-02 | A real unauthenticated public route serves the trust page; NDA-gated documents require a real external access-request/approval flow | See Architecture Patterns → Pattern 2 (public-route + manual `set_tenant_id` resolution, cloned from `agent_registry_endpoints.register_agent` — an **existing**, already-shipped no-auth precedent) and Pattern 3 (NDA consent capture, cloned from Phase 28's e-signature pattern + `cookie_consent_endpoints.py`'s public self-reported-identity capture) |
| TRUST-03 | Tenants can serve their trust page from a custom domain | See Architecture Patterns → Pattern 4 (Host-header tenant resolution against a `trust_domain` field on the `tenants` document — lightest-weight option; see Open Questions for scope boundary vs. a full custom-domain-hosting product) |
</phase_requirements>

## Summary

This phase retrofits three internal-only, in-memory, fully-authenticated files (`trust_service.py`, `trust_endpoints.py`, `components/TrustCenter.tsx`) into a real customer-facing surface. The good news: this codebase already contains every architectural building block TRUST-01/02/03 need, proven and shipped elsewhere — this is composition, not invention, exactly like Phase 28.

**TRUST-01** is the easy part: `trust_service.py`'s `TrustService` singleton (in-process `self.profile`/`self.requests` state, reset on every restart) moves to two Mongo collections (`trust_profiles`, `trust_access_requests`), following the tenant-scoped CRUD shape already used by `privacy_service.py`/`baa_endpoints.py` (no version history needed here — a trust profile is a single current document, not a versioned one like Phase 28's governance documents).

**TRUST-02 is the load-bearing finding of this research, and it is more subtle than the phase brief assumes.** The brief states this will be "the FIRST route in this entire codebase that will genuinely bypass `get_current_user`" — **that premise is not quite accurate, and the correction matters for how the plan should be written.** Two genuinely public (no `get_current_user`), rate-limited routes already exist and ship in production: `file_share_endpoints.access_share` (token-is-the-credential single-resource access) and, more importantly, `agent_registry_endpoints.register_agent` — a route that resolves a **tenant** from a public credential (`registrationKey`, looked up in the globally-exempt `db.tenants` collection) and then calls `set_tenant_id(tenant["id"])` **manually inside the route handler**, before any tenant-scoped query runs. This is the *exact* shape TRUST-02 needs (resolve tenant from a public identifier → set tenant context → query normally) and it is the pattern the plan should clone, not invent.

The reason this matters architecturally: `backend/database.py`'s `TenantIsolatedCollection` wrapper **fail-closes** — every query through `get_database()` on any collection not in its small global-exemption allowlist (`tenants`, `roles`, `compliance_frameworks`, etc.) has `tenantId` silently injected from a contextvar (`tenant_context.get_tenant_id()`), and if that contextvar is unset it injects `"NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"` — a filter that can never match. `TenantMiddleware` only populates that contextvar when it decodes a valid `Authorization: Bearer` JWT; a genuinely public request has no JWT, so the contextvar is empty by default. **This means a naively-written public trust route (`GET /api/public/trust/{slug}`, no auth, straight into `db.trust_profiles.find_one({"slug": slug})`) will silently return nothing — not a security bug, but a correctness bug that looks like "the route doesn't work" during execution, and is easy to "fix" by disabling tenant isolation on the whole `trust_profiles` collection (which WOULD be a real cross-tenant leak).** The correct fix, already proven by `register_agent`: look up the tenant by its public identifier directly against the tenant-isolation-exempt `db.tenants` collection, then explicitly call `set_tenant_id(tenant["id"])` before any further query in that request. The plan must include this as an explicit, testable step — Common Pitfalls has the full writeup.

**The public trust page itself has no obvious home in the current frontend.** This SPA has no client-side router (`grep` for `react-router`/`BrowserRouter` returns nothing) and gates its entire render tree behind `if (!token) return <LoginPage .../>` in `App.tsx`. There is no existing precedent for serving an unauthenticated page from this frontend. Building the public trust page as a new view inside the existing gated SPA is architecturally wrong (it would require punching a hole through the login gate for one specific view, which the codebase's `App.tsx` structure does not support cleanly). The lightest-weight correct answer, and the one this research recommends, is a small standalone static HTML page (vanilla JS `fetch()` against the new public JSON endpoint, no React, no build step, no new npm dependency) served directly by FastAPI at a top-level (non-`/api`) route — mirroring the existing `GET /.well-known/security.txt` `FileResponse` precedent in `app.py`, which is the only existing example of the backend serving a non-API, non-SPA file today. `components/TrustCenter.tsx` (the current internal dashboard) becomes the **admin-management view only** (rename its purpose in the plan explicitly — it manages the DB-backed profile/requests, it does not render the public page).

**TRUST-03 ("custom domain")** has zero existing precedent in this codebase (no `custom_domain`/`subdomain`/CNAME concept anywhere in `tenant_endpoints.py` or the `tenants` schema). Per CLAUDE.md's "do what's asked, nothing more" and this codebase's existing static, environment-variable-driven CORS allowlist (`app_middleware.py` — no wildcard regex, explicit list only, `allow_credentials=True`), building a full self-service custom-domain hosting product (automatic TLS provisioning, DNS verification UI, dangling-CNAME cleanup) is out of scope for a Tier-2/medium phase. The recommended lightest-weight design: add an optional `trust_domain` field to the `tenants` document; add Host-header-based tenant resolution to the new public route handler (fall back to path-based `/trust/{slug}` when the Host header doesn't match a configured custom domain); document that DNS (CNAME) pointing and TLS termination are the operator's/reverse-proxy's responsibility, not something this phase's application code provisions. This is flagged as an Open Question because "custom domain" is a phrase that could reasonably mean much more (see below) and no CONTEXT.md exists to confirm scope.

**Reused precedents to be explicit about (not hand-rolled):** Phase 28's e-signature/consent-capture pattern (typed name + explicit consent checkbox + server-derived IP/UA/timestamp) is the right shape for "NDA-gated access request," but it must be **adapted, not reused verbatim** — Phase 28's `sign_document` derives signer identity from a JWT-authenticated `current_user`; Phase 29's external visitor has no JWT, so identity is self-reported (`requester_email`, `company`) exactly as `AccessRequest` already models, following `cookie_consent_endpoints.record_consent`'s "public endpoint, self-reported identity + server-derived IP/UA" shape instead.

**Zero_trust_service.py is unrelated** — it implements Zero Trust Architecture concepts (per-device trust scoring, per-session risk scoring, post-quantum cryptographic inventory) under `/api/zero-trust`-style routes, sharing no code, models, or collections with the Trust Center. The only connection is naming similarity; the planner must not conflate them or attempt to "reuse" anything from it.

**Primary recommendation:** Move `trust_service.py` to two tenant-scoped Mongo collections; build a genuinely public `GET`+`POST` pair under a new top-level (non-`/api`, or `/api/public`) prefix that resolves tenant via public slug/custom-domain lookup against the exempt `tenants` collection and manually sets tenant context before any further query (cloning `agent_registry_endpoints.register_agent`'s pattern); rate-limit both new public routes with `slowapi` (remembering the `response: Response` parameter this codebase has already been bitten by once, per Phase 25/CHK-03); serve the actual public page as a small static HTML+vanilla-JS file via a new `FileResponse` route (cloning the `/.well-known/security.txt` precedent), leaving `TrustCenter.tsx` as the admin-only management view; and treat "custom domain" as Host-header resolution against a `tenants.trust_domain` field, explicitly scoped away from automated TLS/DNS provisioning.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Trust profile / access-request persistence | Database / Storage | API / Backend | Replaces the in-memory singleton; tenant-scoped Mongo collections mutated only via backend endpoints, matching every other GRC module in this codebase |
| Public trust page rendering | Browser / Client (new, standalone) | API / Backend (public JSON) | The existing SPA has no unauthenticated render path (no client router, hard login gate in `App.tsx`) — the public page must be a new, decoupled static artifact, not a view inside the gated SPA |
| Admin management of trust profile/requests | Browser / Client (existing gated SPA) | API / Backend | `TrustCenter.tsx` remains inside the authenticated app, now backed by real persistence instead of the in-memory singleton |
| NDA-gated document access-request flow | API / Backend | Database / Storage | Server validates consent + persists the request; approval decision is an authenticated admin action inside the existing gated SPA (`TrustCenter.tsx`'s "Access Requests" tab) |
| Tenant resolution for public requests (slug or custom domain) | API / Backend | — | Must happen inside the route handler via explicit `set_tenant_id(...)` after an exempt-collection lookup — cannot rely on `TenantMiddleware`, which only resolves tenant from a JWT |
| Custom-domain Host-header routing | API / Backend | CDN / Static (reverse proxy, out of app scope) | DNS/CNAME pointing and TLS termination are infrastructure-layer; the application only needs to resolve `Host` → tenant once traffic arrives |
| Rate limiting / anti-enumeration on public routes | API / Backend | — | `slowapi` `Limiter`, already wired app-wide via `app_middleware.py`; needs an explicit per-route `@limiter.limit(...)` + `response: Response` parameter |

## Standard Stack

### Core
No new libraries are required. Every capability TRUST-01/02/03 need is already an installed, in-use dependency:

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI + Motor (async pymongo) | `fastapi>=0.110.0,<1.0.0`, `motor>=3.3.0,<4.0.0` [VERIFIED: `backend/requirements.txt`, this session] | Async REST endpoints + MongoDB access | Matches every sibling endpoints/service file pair in this codebase |
| `slowapi` | `>=0.1.9` [VERIFIED: `backend/requirements.txt`, this session] | Public-route rate limiting | Already the platform's only rate-limiter; `rate_limiter.py`'s shared `limiter` (IP-keyed, Redis-backed with in-memory fallback) is reused verbatim, not reinvented |
| stdlib `uuid`/`datetime` | n/a | ID + timestamp generation | Matches the `f"{prefix}-{uuid.uuid4().hex[:N]}"` / `datetime.now(timezone.utc).isoformat()` convention used throughout |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `jinja2` | `>=3.1.0` [VERIFIED: `backend/requirements.txt`, this session — already a dependency, but **not currently used** for HTML page serving anywhere in this codebase (only for PDF/invoice/report string templating)] | Optional: server-side templating for the public HTML page if more than trivial string substitution is needed | Only pull this in if the static-HTML-plus-`FileResponse` approach (recommended) proves insufficient; do not add `Jinja2Templates` wiring speculatively |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Standalone static HTML + vanilla JS public page, served via `FileResponse` (recommended) | A second Vite multi-entry bundle with a slim standalone React component | Consistent visual/component parity with the rest of the app, but requires `vite.config.ts` multi-entry changes and a new build artifact path — meaningfully more machinery for a page whose entire job is "render some fetched JSON," and this codebase has zero existing multi-entry-Vite precedent to clone |
| Host-header + `trust_domain` field custom-domain resolution (recommended) | A full custom-domain hosting product (per-tenant automated ACME/TLS cert issuance, DNS verification UI, dangling-CNAME detection/cleanup) | Massive infrastructure lift (cert management, DNS API integration) with no existing precedent anywhere in this codebase or its dependency list; explicitly over-engineering per CLAUDE.md's "do what's asked, nothing more" unless a human confirms this is truly required (see Open Questions) |
| Manual `set_tenant_id()` resolution inside the route (recommended, cloned from `agent_registry_endpoints.register_agent`) | Add the trust-page path(s) to `TenantMiddleware._PUBLIC_PATHS` and/or bypass `TenantIsolatedCollection` entirely for these collections | Bypassing tenant isolation for the collection entirely (rather than resolving-then-scoping per request) reintroduces exactly the cross-tenant leak risk `TenantIsolatedCollection` exists to prevent — the middleware's `_PUBLIC_PATHS` list only controls whether the middleware attempts a JWT decode, it does not set tenant context, so adding to it alone does not solve the query-scoping problem |

**Installation:**
```bash
# No new packages required — fastapi, motor, slowapi, jinja2, uuid, datetime are all already installed and in use.
```

**Version verification:** `backend/requirements.txt` confirmed `fastapi>=0.110.0,<1.0.0`, `motor>=3.3.0,<4.0.0`, `pymongo>=4.6.0,<5.0.0`, `jinja2>=3.1.0`, `slowapi>=0.1.9` — all read directly this session [VERIFIED: `backend/requirements.txt`].

## Package Legitimacy Audit

No external packages are being introduced by this phase — every capability (persistence, public routing, rate limiting, tenant resolution, HTML serving) reuses existing in-tree dependencies already verified above. **No Package Legitimacy Gate run was needed; no packages to check.**

**Packages removed due to [SLOP] verdict:** none (none proposed).
**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
                    EXTERNAL VISITOR (no auth)                    TENANT ADMIN (authenticated, existing SPA)
                            │                                                  │
                            ▼                                                  ▼
              ┌────────────────────────────┐                    ┌─────────────────────────────┐
              │  GET /trust/{slug}          │                    │  TrustCenter.tsx (existing,   │
              │   or Host: trust.acme.com   │                    │  now admin-only) — reads/     │
              │  → FileResponse: static     │                    │  writes profile + approves/   │
              │    trust-page.html          │                    │  denies access requests via   │
              │  (vanilla JS, no React)     │                    │  authFetch (JWT bearer)       │
              └──────────────┬──────────────┘                    └───────────────┬───────────────┘
                             │ fetch()                                            │ authFetch
                             ▼                                                    ▼
              ┌─────────────────────────────────────────────────────────────────────────────┐
              │  trust_endpoints.py  (retrofitted FastAPI router)                            │
              │                                                                               │
              │  GET  /api/public/trust/{slug}       — NO get_current_user, rate-limited      │
              │        └─► resolve tenant: db.tenants.find_one({"trust_slug"/"trust_domain"}) │
              │             (tenants is tenant-isolation-EXEMPT — safe to query with no       │
              │             context set yet)                                                  │
              │        └─► set_tenant_id(tenant["id"])  ◄── MUST happen before the next line  │
              │        └─► db.trust_profiles.find_one({})  — now correctly tenant-scoped      │
              │        └─► response strips `private_documents` (NDA-gated) down to name-only  │
              │             stubs; never returns URLs for unapproved requesters               │
              │                                                                               │
              │  POST /api/public/trust/{slug}/requests  — NO get_current_user, rate-limited  │
              │        └─► same slug→tenant→set_tenant_id resolution                          │
              │        └─► validates typed_name + explicit consent checkbox (NDA acceptance)  │
              │        └─► captures ip_address/user_agent/submitted_at server-side            │
              │        └─► db.trust_access_requests.insert_one({...status: "Pending"...})     │
              │                                                                               │
              │  GET/PUT /api/trust-center/profile, /api/trust-center/requests(/{id})         │
              │        (existing, authenticated — admin management, unchanged auth model)     │
              └──────────────────────────┬────────────────────────────────────────────────────┘
                                         │
                                         ▼
                        db.tenants (exempt)   db.trust_profiles   db.trust_access_requests
                        {id, trust_slug,      {tenantId, company_ {tenantId, id, requester_
                         trust_domain}         name, ..., public_  email, company, reason,
                                               documents[],        typed_name, consented,
                                               private_documents[]} ip_address, status, ...}
```

### Recommended Project Structure
```
backend/
├── trust_service.py                    # MODIFIED — Mongo-backed CRUD replacing in-memory singleton
├── trust_endpoints.py                  # MODIFIED — add public GET/POST pair; existing admin routes unchanged
├── static/
│   └── trust-page.html                 # NEW — standalone vanilla-JS public trust page (no build step)
├── tests/
│   └── test_trust_center.py            # NEW — pytest suite (persistence, public route, tenant isolation, rate limit)

components/
└── TrustCenter.tsx                     # MODIFIED — becomes admin-only management view (no public rendering claim)

app.py                                  # MODIFIED — one new top-level route: GET /trust/{slug} -> FileResponse(static/trust-page.html)
```

### Pattern 1: DB-backed trust profile + access requests (tenant-scoped CRUD, no versioning needed)
**What:** Replace `TrustService.__init__`'s hardcoded `self.profile`/`self.requests` with two Mongo collections, following the flat tenant-scoped shape of `privacy_service.py`'s simpler CRUD helpers (not its embedded-`versions[]` shape — a trust profile is a single current document per tenant, there is no versioning requirement in TRUST-01).
**When to use:** TRUST-01.
**Example:**
```python
# Source: adapted from backend/privacy_service.py's tenant-scoped find_one/update_one shape (existing pattern, read this session)
async def get_profile(db, tenant_id: str) -> dict:
    profile = await db.trust_profiles.find_one({}, {"_id": 0})  # TenantIsolatedCollection injects tenantId
    return profile or _default_profile(tenant_id)

async def update_profile(db, tenant_id: str, updates: dict) -> dict:
    await db.trust_profiles.update_one({}, {"$set": {**updates, "updated_at": _now_iso()}}, upsert=True)
    return await get_profile(db, tenant_id)
```

### Pattern 2: Public route tenant resolution — clone `agent_registry_endpoints.register_agent`, do NOT invent a new mechanism
**What:** The ONLY existing precedent in this codebase for "resolve tenant from a public, non-JWT identifier, then correctly scope subsequent tenant-isolated queries" is `agent_registry_endpoints.py`'s `register_agent`. Clone this exact shape for the public trust route.
**When to use:** TRUST-02's public `GET`/`POST` routes.
**Example:**
```python
# Source: backend/agent_registry_endpoints.py lines 15-33 (existing, read in full this session) — the pattern to clone
from database import get_database
from tenant_context import set_tenant_id
from rate_limiter import limiter

@router.get("/public/trust/{slug}")
@limiter.limit("30/minute")
async def get_public_trust_profile(request: Request, response: Response, slug: str):
    db = get_database()
    # db.tenants is on the TenantIsolatedDatabase global-exemption allowlist (database.py) —
    # safe to query directly with no tenant context set yet.
    tenant = await db.tenants.find_one({"trust_slug": slug}, {"id": 1, "_id": 0})
    if not tenant:
        raise HTTPException(status_code=404, detail="Not found")
    set_tenant_id(tenant["id"])  # MUST run before any further tenant-scoped query — see Pitfall 1
    profile = await get_profile(db, tenant["id"])
    return _public_view(profile)  # strips private_documents down to name-only stubs (Pitfall 3)
```
**Note the `response: Response` parameter** — omitting it is a documented, previously-shipped-and-caught bug in this exact codebase (Phase 25/CHK-03: `container_scanner_endpoints.py` 500'd on every real request because `@limiter.limit(...)` requires it; unit tests never caught it because they bypass the route/middleware stack). Any new `@limiter.limit(...)`-decorated route in this phase must include it, and the plan's verification step must include an actual HTTP call through the route (not just an import/unit check) to catch this class of bug the way unit tests provably cannot.

### Pattern 3: NDA-gated access request — adapt Phase 28's consent capture, do not reuse verbatim
**What:** Phase 28's `sign_document` derives signer identity from an authenticated `current_user` (JWT) because its signer is an internal, logged-in employee. Phase 29's requester is an **external, unauthenticated visitor** with no JWT — identity must be self-reported in the request body (`requester_email`, `company`), exactly as `AccessRequest` already models it, following `cookie_consent_endpoints.record_consent`'s "public endpoint; self-reported identity fields; server-derives only IP/UA/timestamp" shape instead of Phase 28's "everything server-derived from JWT" shape.
**When to use:** TRUST-02's NDA-gated access-request flow.
**Example:**
```python
# Source: adapted from backend/cookie_consent_endpoints.py lines 51-59 (public, self-reported identity + server IP/UA)
# combined with the typed-name + explicit-consent shape from 28-02-PLAN.md's sign_document
@router.post("/public/trust/{slug}/requests")
@limiter.limit("5/minute")
async def create_public_access_request(request: Request, response: Response, slug: str, payload: AccessRequestCreate):
    if not payload.consent:
        raise HTTPException(400, "Explicit NDA-acceptance consent checkbox is required")
    tenant = await db.tenants.find_one({"trust_slug": slug}, {"id": 1, "_id": 0})
    if not tenant:
        raise HTTPException(404, "Not found")
    set_tenant_id(tenant["id"])
    record = {
        "requester_email": payload.requester_email,   # self-reported — this is the whole point of an access *request*
        "company": payload.company,                    # self-reported
        "reason": payload.reason,                       # self-reported
        "consented": True,
        "ip_address": request.client.host if request.client else "unknown",   # server-derived
        "user_agent": request.headers.get("user-agent", "")[:512],            # server-derived
        "status": "Pending",
        "requested_at": _now_iso(),                     # server-derived
    }
    await db.trust_access_requests.insert_one(record)
    return {"success": True}
```
Self-reported `requester_email`/`company`/`reason` are, by definition of this feature, unverified claims from an anonymous party — that is inherent to an access-*request* flow (the admin approval step, unchanged from today's `update_request_status`, is exactly where a human validates the claim before granting access). This is different from Phase 28's signature record, where trust in the signer's identity comes from JWT auth, not from the request body.

### Pattern 4: Custom-domain resolution — Host header against `tenants.trust_domain`, not a hosting product
**What:** Add an optional `trust_domain` (e.g., `"trust.acmecorp.com"`) field to the `tenants` document (`tenant_endpoints.py`'s existing `BrandingConfig`-style update pattern is the model to clone for a settable field). The public route handler checks `request.headers.get("host")` first; if it matches a tenant's `trust_domain`, resolve that tenant; otherwise fall back to the `/trust/{slug}` path-based lookup.
**When to use:** TRUST-03.
**Example:**
```python
# Source: adapted from backend/agent_download_endpoints.py's existing Host-header read
# (request.headers.get("host", ""), line 50) + tenant_endpoints.py's branding update pattern
async def _resolve_tenant_from_request(db, request: Request, slug: Optional[str]) -> dict:
    host = (request.headers.get("host") or "").split(":")[0]
    tenant = await db.tenants.find_one({"trust_domain": host}, {"id": 1, "_id": 0}) if host else None
    if not tenant and slug:
        tenant = await db.tenants.find_one({"trust_slug": slug}, {"id": 1, "_id": 0})
    if not tenant:
        raise HTTPException(status_code=404, detail="Not found")
    return tenant
```
DNS (CNAME pointing the custom domain at this platform) and TLS termination are explicitly out of this phase's application-code scope — document this boundary in the plan and in any admin-facing UI copy, so "custom domain" doesn't silently balloon into a certificate-management project.

### Anti-Patterns to Avoid
- **Bypassing `TenantIsolatedCollection` for `trust_profiles`/`trust_access_requests` (e.g. adding them to the global-exemption allowlist in `database.py`) to "make the public route work":** This defeats the entire purpose of the fail-closed wrapper and turns a correctness bug (empty result) into an actual cross-tenant data leak (every tenant's profile visible to every query). Resolve tenant, then `set_tenant_id`, per Pattern 2 — never weaken the wrapper.
- **Adding the trust-page route(s) to `TenantMiddleware._PUBLIC_PATHS` and assuming that's sufficient:** That list only controls whether the middleware attempts a JWT decode; it does not set tenant context. The route handler itself must still call `set_tenant_id(...)` explicitly (Pattern 2).
- **Rendering the public page inside the existing gated SPA:** `App.tsx` has no client router and hard-gates on `if (!token)`; punching a hole through that for one view is a structural mismatch. Build the public page as a decoupled static artifact instead (see Pattern 2's diagram and the Frontend section below).
- **Reusing Phase 28's `sign_document` JWT-derived-identity pattern verbatim for the NDA access request:** The requester here has no JWT; identity must be self-reported (Pattern 3). Copying Phase 28's code wholesale would either break (no `current_user`) or silently require authentication, defeating TRUST-02's "external, unauthenticated visitor" requirement.
- **Confusing `zero_trust_service.py` with the Trust Center:** They share no code, models, routes, or collections. Do not "reuse" anything from `zero_trust_service.py` for this phase, and do not let a `/api/zero-trust/...` route accidentally get touched.
- **Returning `private_documents` (with real URLs) from the public route to any unauthenticated caller, approved or not:** Approval only unlocks access via the existing authenticated admin flow granting a real login/download link out-of-band (email, existing file-share mechanism, etc.) — TRUST-02 does not ask for (and this research does not recommend building) a second authentication mechanism for "approved external visitors." Flag this scope boundary explicitly — see Open Questions.
- **Building automated per-tenant TLS certificate issuance for TRUST-03:** No existing precedent, no ACME/cert-manager dependency in this codebase, and CLAUDE.md's "nothing more than asked" — Host-header resolution against an operator-configured domain is the correct scope unless a human confirms otherwise (Open Questions).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Public-route tenant resolution without a JWT | A new "public auth" concept or a bespoke token system | `db.tenants` exempt-collection lookup + `set_tenant_id()`, cloned from `agent_registry_endpoints.register_agent` | Already a proven, shipped pattern in this exact codebase for exactly this problem shape |
| Rate limiting / abuse prevention on the new public routes | A custom IP-tracking/throttling middleware | `slowapi`'s shared `limiter` from `rate_limiter.py` (IP-keyed, Redis-backed with in-memory fallback) | Already the platform's rate-limit engine, already wired into `app_middleware.py`; a second implementation would fragment rate-limit state and headers |
| NDA/consent capture legal-sufficiency plumbing | A cryptographic signing subsystem or third-party e-sign API | Typed-name + consent-checkbox + server-derived IP/UA/timestamp, adapted from Phase 28's Pattern 3 + `cookie_consent_endpoints.py` | Same ESIGN Act/UETA-baseline reasoning as Phase 28 (see its Assumptions Log A1) applies here; over-engineering to add a paid e-sign provider for an access-request acknowledgment |
| Custom-domain hosting infrastructure | Automated ACME/TLS provisioning, DNS verification UI, dangling-CNAME detection | Host-header resolution against a `tenants.trust_domain` field; document DNS/TLS as an operator/reverse-proxy responsibility | No existing precedent or dependency in this codebase for automated certificate management; a full custom-domain product is an infrastructure-tier initiative, not a Tier-2/medium application phase |

**Key insight:** As with Phase 28, every piece TRUST-01/02/03 needs already has a working precedent somewhere in this codebase (`agent_registry_endpoints.py`'s public-tenant-resolution pattern, `cookie_consent_endpoints.py`'s public self-reported-identity capture, `rate_limiter.py`'s shared limiter, `/.well-known/security.txt`'s static-file-serving precedent). The one genuinely new architectural piece — a public page outside the gated SPA — has no in-codebase precedent to clone, which is exactly why it should be built as simply as possible (static HTML, no new framework machinery) rather than retrofitted into the SPA.

## Runtime State Inventory

> This phase moves `trust_service.py` off an in-memory singleton onto the database — a migration, triggering this inventory.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — the current `TrustService` is purely in-memory (`self.profile`, `self.requests` set in `__init__`); nothing is persisted today, so there is no existing data to migrate. The one seeded `AccessRequest(id="req-1", ...)` in `__init__` is demo/placeholder data that resets on every restart — it does not need to be carried into the new collections. | Code edit only — no data migration. Confirmed by full-file read of `trust_service.py` this session. |
| Live service config | None found — no n8n/external-service configuration references trust-center data. | None. |
| OS-registered state | None found — no OS-level task/service registration references trust-center data. | None. |
| Secrets/env vars | None found — `trust_service.py`/`trust_endpoints.py` reference no environment variables or secret keys today. A new `PLATFORM_TRUST_BASE_URL`-style env var (analogous to `agent_download_endpoints.py`'s existing `PLATFORM_URL`) may be worth adding if the plan needs an absolute base URL for the public page's links, but this is new surface, not a rename. | None required; optional new env var is additive. |
| Build artifacts | None found — no compiled/installed artifact currently references `trust_service`/`trust_endpoints`/`TrustCenter`. | None. |

**Nothing found requiring data migration** — this is a pure code-and-schema-additive change (new collections created on first write), not a rename/data-migration of existing records, because the current implementation never persisted anything to begin with.

## Common Pitfalls

### Pitfall 1: Public route silently returns nothing because tenant context was never set (looks like a bug, not a leak — but the wrong fix creates a real leak)
**What goes wrong:** A public route queries `db.trust_profiles.find_one({"slug": slug})` directly. `TenantIsolatedCollection._inject_tenant_id` adds `tenantId: "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"` to that filter because no JWT was ever decoded (no `Authorization` header on a public request → `TenantMiddleware` never calls `set_tenant_id`). The query never matches anything, for any tenant, ever.
**Why it happens:** Every other file in this codebase relies on `TenantMiddleware` to populate tenant context from a JWT before the route runs — this is the first *domain-data* route where that assumption doesn't hold (the visitor has no JWT by design).
**How to avoid:** Resolve the tenant first via the exempt `db.tenants` collection (safe to query with no context set — it's on `TenantIsolatedDatabase`'s allowlist), then explicitly call `set_tenant_id(tenant["id"])` before any further tenant-scoped query, exactly as `agent_registry_endpoints.register_agent` already does. Do NOT "fix" the symptom by adding `trust_profiles`/`trust_access_requests` to the global-exemption allowlist in `database.py` — that removes tenant isolation entirely and turns this into a real cross-tenant leak.
**Warning signs:** The public route's tests pass with a mocked/patched `get_tenant_id`, but a real end-to-end HTTP call against a live-ish setup returns 404/empty for every tenant.

### Pitfall 2: `@limiter.limit(...)` without the `response: Response` parameter (documented, previously-shipped bug in this exact codebase)
**What goes wrong:** `slowapi`'s `@limiter.limit(...)` decorator requires a FastAPI-injected `response: Response` parameter on the decorated endpoint or the route 500s on every real request — unit tests that call the underlying function directly (bypassing the ASGI middleware stack) never catch this.
**Why it happens:** It is easy to add `@limiter.limit(...)` to a route signature that only has `request: Request` and forget the sibling `response: Response` parameter.
**How to avoid:** Every new `@limiter.limit(...)`-decorated route in this phase (both the public `GET` and the public `POST`) must include `response: Response` in its signature, exactly like `file_share_endpoints.access_share` and `agent_registry_endpoints.register_agent` already do. The plan's verification step must include an actual HTTP call through `TestClient` (not just importing the module) — this exact bug (`container_scanner_endpoints.py`, Phase 25/CHK-03) was invisible to unit tests and only caught by an end-to-end run.
**Warning signs:** `grep -c "response: Response"` on the new route file returns fewer matches than `grep -c "@limiter.limit"`.

### Pitfall 3: Public payload accidentally includes NDA-gated document URLs or other internal-only fields
**What goes wrong:** The existing `TrustProfile.private_documents` field carries real, working URLs (`"/docs/soc2-2025.pdf"`) today, gated only by which UI tab renders it — there is no server-side filtering, because every existing route already required `get_current_user`. A naive "just return `trust_service.get_profile()`" public route would leak those URLs to anyone.
**Why it happens:** The in-memory model conflated "data shown to admins" and "data shown publicly" into one `TrustProfile` shape, because until now every consumer was an authenticated admin.
**How to avoid:** The public route handler must build a distinct, explicitly-filtered public view — `public_documents` pass through with URLs; `private_documents` pass through as name-only stubs (no `url` field) with an "NDA required" marker, mirroring what `TrustCenter.tsx` already renders visually today but now enforced server-side, not just hidden by UI tab choice.
**Warning signs:** The public route's response model is the same Pydantic model (`TrustProfile`) used by the authenticated admin routes, with no field-level filtering applied.

### Pitfall 4: Any simulated/demo compliance data on the public page is presented as authoritative to an external, unauthenticated visitor
**What goes wrong:** If the trust page surfaces compliance scores, scan results, or framework-adherence claims that are simulated/demo data anywhere in this codebase (per the Phase 25 "SIMULATED badge" precedent — container scan results, for example), an external visitor with zero context has no way to know the data isn't real, unlike an internal user who has been told this is a demo environment.
**Why it happens:** The existing `TrustProfile.compliance_frameworks` is a flat list of framework names with no live/simulated distinction today; if a future iteration wires in live compliance scores, the SIMULATED-badge discipline needs to travel with the data all the way to this public, external-facing surface.
**How to avoid:** If this phase's plan surfaces anything beyond the existing static `compliance_frameworks` name-list (e.g., an actual compliance score number), it must carry the same SIMULATED-badge labeling this codebase established in Phase 25 — and apply it *more* prominently here, since the audience is an unauthenticated external party who may make a business decision (whether to trust this vendor) based on what they see.
**Warning signs:** A numeric score, a "passed" badge, or any specific scan-result claim appears on the public page with no visible data-provenance/simulated marker.

### Pitfall 5: Reusing `zero_trust_service.py` concepts or code
**What goes wrong:** Because both files have "trust" in the name, it's an easy mistake to import from, extend, or draw architectural analogy from `zero_trust_service.py` (device trust scores, session risk scores, quantum-crypto inventory) when building the Trust Center.
**Why it happens:** Naming collision, not conceptual overlap — confirmed by full-file read this session that `zero_trust_service.py` shares zero models, collections, or routes with the Trust Center domain.
**How to avoid:** Treat them as completely unrelated files. If the plan or its diff touches `zero_trust_service.py`, that's a signal something has gone wrong.
**Warning signs:** Any import of `zero_trust_service` inside `trust_service.py`/`trust_endpoints.py`, or vice versa.

## Code Examples

Verified patterns from this codebase (read in full this session):

### Existing public, no-auth, rate-limited route (the pattern to clone)
```python
# Source: backend/agent_registry_endpoints.py lines 15-40
@router.post("/register")
@limiter.limit("10/minute")
async def register_agent(request: Request, response: Response, data: Dict[str, Any] = Body(...), background_tasks: BackgroundTasks = None):
    """Public endpoint, requires registrationKey."""
    db = get_database()
    registration_key = data.get("registrationKey")
    if not registration_key:
        raise HTTPException(status_code=400, detail="Registration key required")
    tenant = await db.tenants.find_one({"registrationKey": registration_key})
    if not tenant:
        raise HTTPException(status_code=404, detail="Invalid registration key")
    from tenant_context import set_tenant_id
    set_tenant_id(tenant["id"])
    # ...subsequent queries are now correctly tenant-scoped
```

### Existing public, self-reported-identity consent capture (the pattern to adapt for the NDA request)
```python
# Source: backend/cookie_consent_endpoints.py lines 51-59
@router.post("/record")
async def record_consent(payload: ConsentRecord, request: Request):
    """Public endpoint — records visitor cookie consent. No auth required."""
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    meta = {"userId": payload.userId, "ipAddress": ip, "userAgent": ua}
    return await cookie_consent_service.record_consent(payload.tenantId, payload.sessionId, payload.consentedCategories, meta)
```

### The fail-closed tenant isolation wrapper (why Pattern 2 is mandatory, not optional)
```python
# Source: backend/database.py lines 13-39 (TenantIsolatedCollection._inject_tenant_id)
def _inject_tenant_id(self, filter_query):
    tenant_id = get_tenant_id()
    if tenant_id == "platform-admin":
        return filter_query if filter_query is not None else {}
    effective_tenant_id = tenant_id if tenant_id else "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"
    new_filter = filter_query.copy() if filter_query else {}
    new_filter["tenantId"] = effective_tenant_id
    if not tenant_id:
        logging.error(f"[SECURITY ALERT] DB Access without tenant context on collection: {self._collection.name}")
    return new_filter
```

### Existing non-API static-file route (the pattern to clone for the public HTML page)
```python
# Source: backend/app.py lines 85-90
@app.get("/.well-known/security.txt", include_in_schema=False)
async def security_txt():
    from fastapi.responses import FileResponse
    _path = os.path.join(os.path.dirname(__file__), "static", ".well-known", "security.txt")
    return FileResponse(_path, media_type="text/plain")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `TrustService` in-memory singleton; every route (including "public profile") behind `get_current_user`; `TrustCenter.tsx` doubles as (unreachable-by-outsiders) "public" preview | Mongo-backed `trust_profiles`/`trust_access_requests`; a genuinely public, rate-limited `GET`/`POST` pair resolving tenant via `set_tenant_id` (cloned from `agent_registry_endpoints`); a standalone static public page; `TrustCenter.tsx` becomes admin-only | This phase (29) | First time this platform serves tenant-owned domain data (not just a single-token file share) to a genuinely unauthenticated party — establishes the "resolve public identifier → `set_tenant_id` → query normally" pattern other future public-surface phases can clone |

**Deprecated/outdated:** The in-memory `TrustService` singleton and its hardcoded demo data (`Omni-Agent Corp`, the seeded `req-1` access request) are removed entirely, not preserved as a fallback — TRUST-01 explicitly requires persistence across restarts, which the old singleton architecturally cannot provide.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A standalone static HTML + vanilla-JS page (no React, no new Vite entry) is the correct scope for "serves the trust page," rather than a fully-styled React page matching the rest of the app's design system | Architecture Patterns → Summary, Pattern 2 diagram | If the actual product intent is a polished, on-brand public marketing-style page, this recommendation under-delivers visually; the fix (a second Vite entry point) is a moderate, not large, follow-up if this assumption is wrong — flagged as Open Question 1 |
| A2 | "Custom domain" (TRUST-03) means Host-header tenant resolution against an operator-configured domain, with DNS/TLS explicitly out of application scope — not a full self-service custom-domain hosting product with automated certificate issuance | Architecture Patterns → Pattern 4, Don't Hand-Roll | If the actual requirement is full self-service (a tenant enters their own domain in a UI and traffic Just Works with a valid cert), this phase under-delivers substantially — flagged as Open Question 2 |
| A3 | Approval of an NDA-gated access request remains a manual, authenticated-admin action (unchanged from today's `update_request_status`) rather than an automated/rules-based approval | Architecture Patterns → Anti-Patterns, Don't Hand-Roll | If automatic approval (e.g., any `.edu`/`.gov` domain, or any request at all) is actually wanted, the plan needs an explicit auto-approval rule engine instead of assuming a human always reviews — flagged as Open Question 3 |
| A4 | Reusing the existing `manage:compliance`/`view:compliance` RBAC permissions for the admin-side trust-center routes (unchanged from today) is sufficient, consistent with Phase 28's resolved RBAC decision | Architectural Responsibility Map | Low risk — this is a continuation of the existing route's current RBAC gate (`_TRUST_ADMIN_ROLES` in `trust_endpoints.py` today), not a new decision |
| A5 | Approved external visitors receive access to NDA-gated documents through an out-of-band mechanism (e.g., an admin manually emailing a link, or granting access via the existing authenticated flow) rather than a new second authentication system built specifically for external approved visitors | Architecture Patterns → Anti-Patterns | If the actual requirement is "an approved external visitor can then log into a lightweight portal and download the NDA'd document directly," that is meaningfully more scope (a second, lower-privilege auth system) than TRUST-02's literal wording implies — flagged as Open Question 4 |

## Open Questions

1. **Does the public trust page need visual/brand parity with the rest of the app (full React/Tailwind styling), or is a simple, clean static HTML page sufficient for v1?**
   - What we know: The existing SPA has no unauthenticated render path; a static HTML page is the lightest-weight correct architecture (Assumption A1).
   - What's unclear: Product/brand expectations for a page external prospects/auditors will see and judge the company by.
   - Recommendation: Build the static HTML page first (matches "lightest-weight approach that satisfies the requirement"); if visual parity is later confirmed as a hard requirement, a follow-up phase can add a second Vite entry point reusing the existing Tailwind config without touching the backend contract.

2. **What does "custom domain" (TRUST-03) need to cover: Host-header resolution against an operator-configured domain (this research's recommendation), or full self-service domain management with automated TLS?**
   - What we know: Zero existing precedent for either in this codebase; Host-header resolution is a small, well-understood addition; automated TLS/DNS management is a substantial infrastructure project with no existing dependency to build on.
   - What's unclear: Whether tenants configure their custom domain themselves via a UI, or whether this is an operator/support-assisted setup (e.g., a support engineer sets `trust_domain` via an internal API call after manually verifying DNS).
   - Recommendation: Default to the lightweight Host-header approach with `trust_domain` set via an authenticated admin API call (cloning the existing `tenant_endpoints.py` branding-update pattern), and explicitly document that DNS/CNAME pointing and TLS termination are the tenant's/operator's reverse-proxy responsibility — not something this phase provisions.

3. **Is NDA-gated access-request approval a manual admin decision (today's model, unchanged) or does this phase need any auto-approval logic?**
   - What we know: `update_request_status` already exists and is authenticated-admin-only; nothing in TRUST-02's wording implies automation.
   - What's unclear: Whether product wants zero-touch approval for some cases (e.g., pre-vetted domains).
   - Recommendation: Keep it fully manual for v1 (matches today's existing admin flow, adds the least scope) — flag any auto-approval rule engine as a deferred idea unless a human confirms otherwise.

4. **After an access request is approved, how does the external visitor actually receive the NDA-gated document — a new lightweight external-viewer auth system, or an out-of-band mechanism (email link, existing file-share token) outside this phase's scope?**
   - What we know: TRUST-02's literal wording is "NDA-gated documents require a real external access-request/approval flow" — it describes the *request* and *approval*, not necessarily the delivery mechanism.
   - What's unclear: Whether "gated access" implies the visitor then gets some kind of ongoing authenticated access, or a one-time delivery.
   - Recommendation: Scope this phase to request + approval only, with delivery handled out-of-band (e.g., an admin manually shares the document via the existing `file_share_endpoints.access_share` token mechanism after approving) — this reuses an existing capability instead of building a second external-facing auth system. Confirm with a human if ongoing self-service access for approved visitors is actually required.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| MongoDB (via Motor) | Trust profile/access-request persistence (TRUST-01) | ✓ (assumed running — used by every other phase in this milestone) [ASSUMED — not independently re-probed this session; no prior phase in this milestone flagged it unavailable] | — | — |
| `slowapi` + Redis (optional) | Public-route rate limiting | ✓ package installed; Redis optional (falls back to in-memory single-instance limiting per `rate_limiter.py`'s `_make_storage_uri`) [VERIFIED: `backend/requirements.txt`, `rate_limiter.py` read this session] | slowapi `>=0.1.9` | In-memory rate limiting if `REDIS_URL` unset — acceptable for a single-instance deployment, documented limitation for horizontally-scaled deployments |
| DNS/CNAME + TLS termination (custom domain, TRUST-03) | TRUST-03 | ✗ — not an application-code concern; depends on the tenant's/operator's DNS and reverse-proxy/TLS setup, entirely outside this codebase | — | Host-header resolution still works once traffic correctly arrives at this backend; DNS pointing and cert provisioning are explicitly out of scope (see Open Question 2) |

**Missing dependencies with no fallback:** none identified for TRUST-01/TRUST-02 application code.
**Missing dependencies with fallback:** Redis for distributed rate-limit state (falls back to in-memory, fine for single-instance); DNS/TLS for custom domains (out of scope, documented).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (project-standard; `pytest.ini` at repo root) [VERIFIED: `pytest.ini` read this session — `testpaths = . backend`, `asyncio_mode = auto`] |
| Config file | `pytest.ini` (repo root) |
| Quick run command | `cd backend && python -m pytest tests/test_trust_center.py -x` |
| Full suite command | `cd backend && python -m pytest tests/ -q` |
| Frontend framework | Vitest (`"test": "vitest run"` in `package.json`) [VERIFIED: `package.json` read this session] |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRUST-01 | Trust profile persists across a simulated restart (data survives a fresh `get_database()` call, not held in a Python-process singleton) | unit | `pytest tests/test_trust_center.py -k persistence -x` | ❌ Wave 0 |
| TRUST-01 | Tenant isolation — a trust profile/request in tenant A is invisible to tenant B via the admin routes | unit | `pytest tests/test_trust_center.py -k tenant -x` | ❌ Wave 0 |
| TRUST-02 | Public `GET` route requires no `Authorization` header, resolves tenant via slug, and returns a 404-not-500 for an unknown slug | integration | `pytest tests/test_trust_center.py -k public_get -x` | ❌ Wave 0 |
| TRUST-02 | Public `GET` route never includes `private_documents[].url` in its response — only name + "NDA required" marker | unit | `pytest tests/test_trust_center.py -k private_doc_filter -x` | ❌ Wave 0 |
| TRUST-02 | Public `POST` (access request) rejects missing consent, captures server-derived IP/UA, and is reachable via `TestClient` end-to-end (not just an import check) to catch the `response: Response` slowapi pitfall | integration | `pytest tests/test_trust_center.py -k public_post -x` | ❌ Wave 0 |
| TRUST-02 | Rate limiting is actually enforced on both public routes (Nth request in a window returns 429) | integration | `pytest tests/test_trust_center.py -k rate_limit -x` | ❌ Wave 0 |
| TRUST-03 | Host-header resolution correctly maps a configured `trust_domain` to its tenant; unrecognized Host falls back to slug-based lookup | unit | `pytest tests/test_trust_center.py -k custom_domain -x` | ❌ Wave 0 |
| TRUST-01/02 | Admin routes (`/api/trust-center/...`) still require `get_current_user` and `manage:compliance` for writes — no accidental broadening of the existing auth model | unit | `pytest tests/test_trust_center.py -k admin_auth -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_trust_center.py -x`
- **Per wave merge:** `cd backend && python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`; additionally, an actual `TestClient` HTTP call (not just a module import) through both new public routes, per Pitfall 2's documented `response: Response` failure mode.

### Wave 0 Gaps
- [ ] `backend/tests/test_trust_center.py` — new file; clone the `_col`/`_db`/`_user`/`_app` helper block from `backend/tests/test_automation_and_baa.py` per this repo's per-file test-helper convention
- [ ] Framework install: none — pytest and Vitest already present and configured

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | yes (for admin routes only) | Existing admin routes keep `get_current_user` + `_TRUST_ADMIN_ROLES`/`manage:compliance` gating, unchanged |
| V3 Session Management | no | No new session-management surface; public routes are stateless per-request |
| V4 Access Control | yes — the central risk of this phase | Public routes MUST resolve tenant via the exempt `tenants` collection and call `set_tenant_id()` before any tenant-scoped query (Pattern 2/Pitfall 1); `private_documents` URLs MUST be stripped server-side from the public response, never gated only by which UI tab renders them (Pitfall 3) |
| V5 Input Validation | yes | Access-request body fields (`requester_email`, `company`, `reason`) length-capped and validated; explicit consent-boolean check; slug/Host-header values used only as lookup keys, never interpolated into a query in a way that changes its shape |
| V6 Cryptography | no | No cryptographic signing introduced — NDA consent capture uses the same non-cryptographic ESIGN/UETA-baseline shape as Phase 28, deliberately |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Cross-tenant trust-profile leak via the fail-closed tenant-isolation wrapper being silently bypassed or weakened to "fix" the public route | Information Disclosure | Resolve tenant via the exempt `tenants` collection + explicit `set_tenant_id()` per request (Pattern 2/Pitfall 1); never add `trust_profiles`/`trust_access_requests` to the global-exemption allowlist |
| Enumeration/scraping of tenant `trust_slug` values via the public `GET` route (sequential or brute-force guessing to discover which companies have a trust page, or to scrape all tenants' profiles) | Information Disclosure | Rate-limit the public `GET`/`POST` routes via `slowapi` (IP-keyed); identical 404 for both "slug well-formed but no such tenant" and "tenant exists but has no public profile configured" (do not leak existence via differing error messages); consider a non-sequential, sufficiently-random `trust_slug` (the existing `tenant_id` format — `tenant_{uuid4().hex[:12]}` — is already reasonably opaque, but a dedicated, independently-rotatable `trust_slug` is preferable so exposure isn't tied to the internal tenant ID) |
| Client-forged access-request metadata (fake IP/timestamp to obscure the true source of a request) | Tampering / Spoofing | `ip_address`/`user_agent`/`requested_at` are server-derived from `request.client.host`/`request.headers`/`datetime.now(utc)`, never accepted from the request body — only `requester_email`/`company`/`reason`/`consent` (which are inherently self-reported and validated by the human admin at approval time, not by the server) come from the body |
| Private document URL disclosure via an unfiltered public response model | Information Disclosure | Public route builds a dedicated, explicitly-filtered response shape — `private_documents` returns name-only stubs, never `url` (Pitfall 3) |
| Public NDA-request endpoint used as a spam/abuse vector (mass-submitting fake access requests) | Denial of Service (resource exhaustion of the admin review queue) | Tighter per-route rate limit on the `POST` (e.g., 5/minute per IP) than the `GET`, per the WebSearch-cited practice of applying endpoint-specific tighter limits to routes that trigger persistent writes or downstream human review work |
| Dangling-CNAME / subdomain takeover if a tenant's custom domain is later removed but its DNS record is left pointing at this platform | Spoofing | Out of this phase's direct application-code scope (DNS is the tenant's/operator's responsibility per Pattern 4), but the plan should at minimum log/flag when a `trust_domain` is unset so an operator can advise the tenant to remove the now-dangling DNS record — flagged as a documentation/ops note, not a code requirement |

## Sources

### Primary (HIGH confidence)
- `backend/trust_service.py` (full file read, this session) — confirmed in-memory singleton, exact fields/methods needing DB backing
- `backend/trust_endpoints.py` (full file read, this session) — confirmed all 5 routes require `get_current_user`; RBAC via `_TRUST_ADMIN_ROLES`
- `components/TrustCenter.tsx` (full file read, this session) — confirmed internal-only dashboard shape, tabs, and data model
- `backend/zero_trust_service.py` (partial read, this session) — confirmed unrelated domain (device trust scores, session risk, PQC crypto inventory)
- `backend/agent_registry_endpoints.py` (full file read, this session) — the exact public-tenant-resolution pattern to clone (`register_agent`)
- `backend/file_share_endpoints.py` (full file read, this session) — second existing public-route precedent (token-is-credential)
- `backend/cookie_consent_endpoints.py` (full file read, this session) — public self-reported-identity + server-derived IP/UA capture pattern
- `backend/database.py` (full `TenantIsolatedCollection`/`TenantIsolatedDatabase` read, this session) — the fail-closed tenant-isolation mechanism and its global-exemption allowlist (including `tenants`)
- `backend/tenant_context.py`, `backend/tenant_middleware.py` (full file reads, this session) — confirmed `TenantMiddleware` only sets tenant context from a decoded JWT, never blocks unauthenticated requests itself
- `backend/rate_limiter.py`, `backend/app_middleware.py` (read, this session) — shared `slowapi` limiter configuration, CORS allowlist mechanics
- `backend/router_registry.py` (read, this session) — confirmed `trust_endpoints` is an optional (non-`_REQUIRED_ROUTERS`) router
- `backend/tenant_endpoints.py` (read, this session) — confirmed no existing custom-domain/subdomain concept; branding-update pattern to clone for `trust_domain`
- `backend/app.py` (read, this session) — confirmed no CORS/Jinja2Templates HTML-serving precedent except `/.well-known/security.txt`'s `FileResponse`
- `App.tsx`, `vite.config.ts`, `index.html` (read, this session) — confirmed no client-side router, hard login gate, single Vite entry point
- `.planning/phases/28-governance-document-management/28-RESEARCH.md`, `28-01/02/03-PLAN.md` (read in full, this session) — Phase 28's e-signature/consent-capture pattern and its resolved RBAC decision, used as the direct analog and contrast for Pattern 3
- `.planning/STATE.md` (read, this session) — confirmed the Phase 25/CHK-03 `response: Response` slowapi bug history
- `backend/requirements.txt` (read, this session) — confirmed no new packages needed (fastapi, motor, slowapi, jinja2 all already present)

### Secondary (MEDIUM confidence)
- [Domain Name Considerations in Multitenant Solutions — Azure Architecture Center](https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/considerations/domain-names) (WebSearch, this session) — CNAME + Host-header tenant-resolution pattern, dangling-CNAME/subdomain-takeover risk
- General web synthesis on rate-limiting/anti-scraping best practice (WebSearch, this session, aggregated across multiple blog sources — not all individually authoritative) — IP-based + endpoint-specific tighter limits, sliding-window preference, `Retry-After` header practice

### Tertiary (LOW confidence)
- None used as authoritative for any Standard Stack or Architecture recommendation — all architectural claims in this research are grounded in direct, in-session reads of this codebase.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; every reused pattern verified by direct full-file reads this session
- Architecture: HIGH for the backend tenant-isolation/public-route mechanics (directly read and verified this session, including finding the two existing public-route precedents the phase brief didn't account for); MEDIUM for TRUST-03's exact scope and the frontend public-page delivery mechanism, both flagged as Open Questions needing a human product decision
- Pitfalls: HIGH — Pitfall 1 (fail-closed tenant isolation) and Pitfall 2 (`response: Response` slowapi requirement) are both drawn directly from this codebase's own architecture and documented history (STATE.md's Phase 25/CHK-03 incident)

**Research date:** 2026-07-07
**Valid until:** 30 days (stable internal codebase patterns; the two open product-scope questions — custom-domain depth and NDA-delivery mechanism — should be confirmed before or during planning, not left to expire silently)
