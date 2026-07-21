# Phase 42: Comment Threads on Compliance Controls - Research

**Researched:** 2026-07-21
**Domain:** FastAPI + Motor/MongoDB backend, React/TS frontend, multi-tenant GRC platform — new tenant-scoped comment collection integration
**Confidence:** HIGH (every claim below is sourced from files read directly in this repo on branch `feat/rust-agent-2.1.0-and-fixes`, not general domain patterns)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Comment authors restricted to `admin`, `super_admin`, `compliance_reviewer` roles — mirrors the existing evidence-review restriction in `evidence_review_service.py`. Consistent with who else gets to weigh in on compliance state in this platform, rather than opening comments to any authenticated tenant user.
- **D-02:** @mention notifications are in-app only via the existing notification system (bell icon / `NotificationsDashboard`) — no new email-delivery surface for v1.
- **D-03:** Comments are immutable/append-only — no edit or delete, matching the chain-of-custody-log precedent already established in this codebase (Phase 7, `COC-01`/`COC-02`).
- **D-04:** @mention parsing is plain-text `@username` after posting — no live autocomplete/user-search dropdown.

### Claude's Discretion

- All 4 decisions above were explicitly deferred by the user ("You decide") — the rationale in each is Claude's, applying "match existing platform patterns, minimal viable scope" as the guiding principle throughout.
- Exact @mention regex/parsing implementation.
- Notification payload shape (reusing whatever the existing notification system's schema is).

### Deferred Ideas (OUT OF SCOPE)

- Live @mention autocomplete — deferred per D-04; could be a future enhancement if plain-text parsing proves insufficient in practice.
- Email notification delivery for @mentions — deferred per D-02; revisit if in-app-only proves insufficient.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CMT-01 | A compliance admin or auditor can post a comment on a specific control; comments are tenant-scoped (not visible cross-tenant); @mentions trigger a notification | Standard Stack, Architecture Patterns, Code Examples, and Pitfalls sections below give the exact endpoint/service/collection/notification shapes to clone and the exact anti-patterns to avoid for tenant isolation and notification delivery |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Keep new files under 500 lines (`control_comments_service.py` and `control_comments_endpoints.py` will each be well under this given the minimal CRUD surface).
- Never create documentation files unless explicitly requested — this RESEARCH.md is the GSD-required exception.
- Read a file before editing it; prefer editing existing files (`FrameworkDetail.tsx`, `router_registry.py`, `apiService.ts`) over creating new ones where reuse is possible.
- Validate input at system boundaries (Pydantic request models on the new endpoints).
- Do not add a `Co-Authored-By` trailer to commits unless `.claude/settings.json` has `attribution.commit` set.

## Summary

This phase adds one new tenant-scoped MongoDB collection (`control_comments`), one new service module, one new endpoints module, and one new React sub-panel mounted inside an already-reachable view (`FrameworkDetail.tsx`'s `expandedControlId` row, next to the existing `ChainOfCustodyPanel`). Every piece of this phase has a directly-analogous, already-shipped precedent in this codebase — the milestone-level `ARCHITECTURE.md`/`PITFALLS.md`/`FEATURES.md` research already scoped this correctly and this phase-level research confirms and sharpens those findings against the actual source files.

Three concrete, high-confidence findings that materially affect planning:

1. **The endpoint/response shape to clone (`tickets_endpoints.py:250`/`tickets_service.py:346`) uses a `$push`-onto-parent-document storage mechanism that must NOT be copied** — `compliance_controls` is on the tenant-isolation exemption allowlist (global reference data), so embedding comments there leaks cross-tenant. Clone only the request/response JSON shape and the endpoint signature pattern; storage must be a brand-new, non-exempt `control_comments` collection going through the default `TenantIsolatedCollection` path (confirmed absent from `database.py`'s exemption list at lines 122-135/138-151).
2. **The existing tickets `@mention` notification pathway is dead code — do not clone it.** `ticket_notifications.py::_send()` does `from notification_service import notification_service`, but `notification_service.py` exports no such module-level singleton (only the `NotificationService` class and a `get_notification_service(db)` factory). This import raises `ImportError` on every call, silently swallowed by a bare `except Exception: pass` in `tickets_endpoints.py:285-286`. Verified live: `python -c "from notification_service import notification_service"` raises `ImportError`. CMT-01's @mention notification must be wired directly via `get_notification_service(db).send_alert(...)`, not by copying `ticket_notifications.py`'s broken import pattern.
3. **The role-restriction pattern (D-01) has both a backend and a frontend half, and both are simple, already-proven one-liners.** Backend: module-level `_REVIEWER_ROLES = {"admin", "super_admin", "compliance_reviewer"}` + inline `if current_user.role not in _REVIEWER_ROLES: raise HTTPException(403, ...)` in `evidence_review_endpoints.py:45,133-137`. Frontend: `const _REVIEWER_ROLES = ['admin', 'super_admin', 'compliance_reviewer']; const isReviewer = currentUser && _REVIEWER_ROLES.includes(currentUser.role);` in `EvidenceReviewPanel.tsx:15,82`, with an explicit code comment noting the two lists are manually kept in sync (no shared constants module) and that the backend always re-enforces regardless of frontend state.

**Primary recommendation:** Build `control_comments_service.py` (raw CRUD against the new tenant-scoped `control_comments` collection, no `$push`, no embedding), `control_comments_endpoints.py` (clone `tickets_endpoints.py`'s POST/GET comment route *shapes* and `evidence_review_endpoints.py`'s role-gate *pattern*), wire @mention notifications through `get_notification_service(db).send_alert(channels=[])` (in-app only — omit `email`/`sms`/`slack` from `channels` so only the `db.notifications.insert_one` side-effect fires), register the router in `router_registry.py` next to `evidence_review_endpoints` (line 179), and mount a new `ControlCommentsPanel.tsx` in `FrameworkDetail.tsx` immediately after the existing `<ChainOfCustodyPanel controlId={control.id} />` at line 432.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Comment authorship / role gate | API / Backend | Frontend Server (SSR n/a — SPA) | Role check must be server-enforced (`evidence_review_endpoints.py` precedent); frontend mirrors it only for UX (hide the post form for non-reviewers), never as the actual gate |
| Comment storage | Database / Storage | API / Backend | New `control_comments` collection, tenant-scoped via default `TenantIsolatedCollection` — the backend service is the only writer |
| Comment retrieval / rendering | Browser / Client | API / Backend | `ControlCommentsPanel.tsx` fetches on-demand (mirrors `ChainOfCustodyPanel`'s lazy-fetch-on-expand pattern), backend returns tenant-scoped list sorted by `created_at` |
| @mention detection | API / Backend | — | Parsing happens server-side, after the comment is persisted (per D-04, "plain-text `@username` parsing after posting") — never client-side, so it can't be bypassed by a raw API call |
| @mention notification delivery | API / Backend | Browser / Client | Backend writes to `db.notifications` via `NotificationService.send_alert(channels=[])`; the existing `NotificationCenter.tsx` bell-icon component (already wired, already polling) picks it up with zero new frontend polling code |
| Tenant isolation enforcement | Database / Storage | API / Backend | `TenantIsolatedCollection` auto-injects `tenantId` on every read/write to `control_comments` since it is NOT on the exemption allowlist — this is a database-tier guarantee, not something the endpoint code has to re-implement |

## Standard Stack

This phase introduces no new third-party dependencies. It is 100% internal-pattern reuse.

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | (existing, pinned in `backend/requirements.txt`) | New `control_comments_endpoints.py` router | Every other endpoint module in this codebase uses it |
| Motor (AsyncIOMotorClient) | (existing) | Async MongoDB driver for `control_comments` collection | Same driver every other collection in this codebase uses |
| Pydantic | (existing, via FastAPI) | Request body validation (`CreateCommentRequest`) | Matches `evidence_review_endpoints.py`'s `CreateReviewRequest`/`UpdateDecisionRequest` pattern |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `re` (stdlib) | n/a | @mention token extraction from comment text | Server-side, after persist, per D-04 |
| `uuid` (stdlib) | n/a | Comment `id` generation | Matches `tickets_service.add_comment`'s `str(uuid.uuid4())` pattern |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| New `control_comments` collection | Embed comments array on `compliance_controls` (literal reading of "clone tickets_endpoints.py's pattern") | **Rejected — cross-tenant data leak.** `compliance_controls` is exempt from tenant isolation (global reference data); any tenant-specific write there is visible to every tenant. This is Pitfall 2 in the milestone `PITFALLS.md`, confirmed by direct code read of `database.py`'s exemption list. |
| `get_notification_service(db).send_alert(channels=[])` | Clone `ticket_notifications.py::_send()` verbatim | **Rejected — the cloned code is dead/broken.** Verified via live Python import that `from notification_service import notification_service` raises `ImportError`; the existing tickets mention-notification pathway silently no-ops today. |
| Email-shaped `@user@domain.com` mention regex (tickets' existing regex) | Plain-text `@username` regex | Per D-04, this phase intentionally diverges from the tickets pattern here — `@username` is simpler and matches the decision's explicit scope, not the tickets precedent. See Open Questions for the concrete regex/resolution approach, which is genuinely new (see Pitfall 3). |

**Installation:** None — no new packages.

## Package Legitimacy Audit

Not applicable — this phase introduces zero new third-party packages (backend or frontend). All work is composed from libraries already present in `backend/requirements.txt` and `package.json`.

## Architecture Patterns

### System Architecture Diagram

```
FrameworkDetail.tsx (expandedControlId === control.id)
    │
    ├─ <AssetComplianceList .../>            (existing, unchanged)
    ├─ {canViewCoC && <ChainOfCustodyPanel controlId={control.id} />}   (existing, unchanged — line 432)
    └─ <ControlCommentsPanel controlId={control.id} />                 (NEW — mounted immediately after CoC panel)
            │
            │  on expand: GET /api/control-comments?control_id=X
            │  on submit: POST /api/control-comments {control_id, text}
            ▼
    control_comments_endpoints.py  (NEW router, registered in router_registry.py)
            │
            ├─ role gate: current_user.role in {"admin","super_admin","compliance_reviewer"}? (D-01)
            │       └─ 403 if not, on POST only (GET is unrestricted — any authenticated tenant user can read)
            │
            ▼
    control_comments_service.py  (NEW)
            │
            ├─ add_comment(db, control_id, tenant_id, author, text)
            │       → db.control_comments.insert_one({id, control_id, author, text, created_at})
            │         [tenantId auto-injected by TenantIsolatedCollection — collection NOT on exemption list]
            │
            ├─ after insert: extract_mentions(text) → List[str]  (D-04: plain-text @username, server-side)
            │       → for each resolved user: get_notification_service(db).send_alert(
            │             title=..., message=..., severity="info",
            │             recipients=[user_email], tenant_id=tenant_id,
            │             channels=[],              # empty = in-app only, no email/sms/slack side-effects
            │             metadata={"control_id": control_id, "event": "mention"})
            │         → db.notifications.insert_one({..., tenantId: <auto-injected>})
            │
            └─ list_comments(db, control_id, tenant_id) → sorted by created_at
                    → db.control_comments.find({"control_id": control_id})
                      [tenantId auto-injected on read too]

    NotificationCenter.tsx (bell icon, EXISTING, already polling GET /api/notifications)
            │
            └─ renders the new in-app notification with zero new frontend code
```

### Recommended Project Structure

```
backend/
├── control_comments_service.py      # NEW — insert/list against control_comments collection
├── control_comments_endpoints.py    # NEW — POST/GET router, role gate on POST
├── router_registry.py               # MODIFIED — one new _load() line
├── database.py                      # NOT modified — control_comments must NOT be added to the exemption list
components/
├── ControlCommentsPanel.tsx         # NEW — mounted in FrameworkDetail.tsx
├── FrameworkDetail.tsx              # MODIFIED — one new component mount, one new import
services/
├── apiService.ts                    # MODIFIED — 2 new thin wrapper functions (postControlComment, fetchControlComments)
```

### Pattern 1: Endpoint/response shape to clone (NOT the storage mechanism)

**What:** `POST /{ticket_id}/comments` (`tickets_endpoints.py:250-288`) is the shape reference: request body has a single `text` field, response returns the updated resource, and `@mention` detection happens inline in the endpoint handler immediately after the successful write, wrapped in `try/except Exception: pass` so a notification failure never fails the comment POST.

**When to use:** For `control_comments_endpoints.py`'s `POST /api/control-comments` handler.

**Example (existing code, for the shape only — storage differs, see Pitfall 1):**
```python
# Source: backend/tickets_endpoints.py:250-288 (backend/tickets_models.py for AddCommentRequest)
@router.post("/{ticket_id}/comments")
async def add_comment(
    ticket_id:    str,
    body:         AddCommentRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    try:
        updated = await tickets_service.add_comment(
            ticket_id, author=_actor(current_user), text=body.text,
            tenant_id=_effective_tenant(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Detect @mentions in comment text and notify mentioned users
    mentions = re.findall(r'@([\w.+-]+@[\w.+-]+\.[a-z]+)', body.text, re.IGNORECASE)
    if mentions:
        try:
            from ticket_notifications import _send      # DO NOT clone this import — it's broken, see Pitfall 2
            ...
        except Exception:
            pass
    return updated
```

### Pattern 2: Role-restriction gate (D-01) — clone verbatim

**What:** Module-level role set + inline check, enforced server-side, mirrored (not shared) on the frontend for UX only.

**When to use:** `control_comments_endpoints.py`'s `POST /api/control-comments` handler only (GET is open to any authenticated tenant user, matching how `evidence_review_endpoints.py`'s GET routes — `list_evidence_reviews`/`list_pending_review_evidence` — have no role gate while the PATCH decision route does).

**Backend example:**
```python
# Source: backend/evidence_review_endpoints.py:45, 133-137
_REVIEWER_ROLES = {"admin", "super_admin", "compliance_reviewer"}
...
if current_user.role not in _REVIEWER_ROLES:
    raise HTTPException(
        status_code=403,
        detail="Only admins and compliance reviewers can make review decisions",
    )
```

**Frontend example:**
```typescript
// Source: components/EvidenceReviewPanel.tsx:15, 82
// NOTE: manually kept in sync with the backend's role set — no shared constants
// module exists yet. Backend always re-enforces regardless of this frontend gate.
const _REVIEWER_ROLES = ['admin', 'super_admin', 'compliance_reviewer'];
const isReviewer = currentUser && _REVIEWER_ROLES.includes(currentUser.role);
```

### Pattern 3: Tenant-scoped collection, default (non-exempt) path — clone verbatim

**What:** A brand-new collection is automatically tenant-isolated by `TenantIsolatedCollection` as long as it is NOT added to `database.py`'s exemption list. No manual `tenantId` filter code is needed in the service layer for the common case.

**When to use:** All `control_comments` reads/writes in `control_comments_service.py`.

**Example:**
```python
# Source: backend/database.py:13-108 (TenantIsolatedCollection), confirmed control_comments
# absent from the exemption lists at lines 122-135 and 140-151.
# Standard call from a request-scoped endpoint:
db = get_database()                                    # returns TenantIsolatedDatabase
await db.control_comments.insert_one({                 # tenantId auto-injected here
    "id": str(uuid.uuid4()),
    "control_id": control_id,
    "author": author,
    "text": text,
    "created_at": _now_iso(),
})
comments = await db.control_comments.find(              # tenantId auto-injected here too
    {"control_id": control_id}
).sort("created_at", 1).to_list(length=200)
```

### Pattern 4: Lazy-fetch-on-expand panel component (frontend)

**What:** `ChainOfCustodyPanel.tsx` is the closest existing analog to the new `ControlCommentsPanel.tsx` — a `controlId`-scoped panel mounted inside the same `expandedControlId` row, fetching its own data on first expand rather than being pre-fetched by the parent.

**When to use:** `ControlCommentsPanel.tsx`'s data-loading strategy.

**Example (structure to mirror, not the exact content):**
```typescript
// Source: components/ChainOfCustodyPanel.tsx:1-52 (structure only)
interface ControlCommentsPanelProps { controlId: string; }
export const ControlCommentsPanel: React.FC<ControlCommentsPanelProps> = ({ controlId }) => {
    const [comments, setComments] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    // ... fetch api.fetchControlComments(controlId) on mount (comments should always be
    // visible when the row is expanded — unlike CoC, don't gate behind a second click,
    // since "see the discussion" is the primary value of this feature, not an optional drill-down)
};
```

**Note on load timing:** unlike `ChainOfCustodyPanel`'s click-to-expand-then-fetch UX, comments should fetch automatically when `expandedControlId === control.id` becomes true (i.e., on mount of the panel, not on a second nested toggle) — comments are the primary collaboration surface this phase is building, not a secondary audit drill-down. This is a UX judgment call for the planner/UI phase to confirm, not a hard constraint from any research source.

### Anti-Patterns to Avoid

- **Embedding comments in `compliance_controls`:** `$push`-ing onto the exempt, tenant-shared `compliance_controls` document leaks every tenant's comments to every other tenant. See Pitfall 1.
- **Cloning `ticket_notifications.py`'s `_send()` import:** `from notification_service import notification_service` raises `ImportError` every time — this is dead code in the existing tickets feature, not a working pattern. See Pitfall 2.
- **Cloning the email-shaped `@mention` regex:** `r'@([\w.+-]+@[\w.+-]+\.[a-z]+)'` expects a full email address after `@`; D-04 wants plain `@username`. Using the tickets regex verbatim would silently match nothing for `@jsmith`-style mentions. See Pitfall 3 and Open Questions.
- **Building an edit/delete endpoint "just in case":** D-03 requires append-only. Per the chain-of-custody precedent, immutability here is enforced purely by *absence of a PATCH/DELETE route* — do not build one, even a stubbed/disabled one, since its mere existence is a future foot-gun (see Runtime State Inventory analog note in Pitfalls).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| In-app notification storage/delivery | A new notification collection or delivery mechanism | `NotificationService.send_alert(..., channels=[])` writing to the existing `db.notifications` collection, read by the existing `NotificationCenter.tsx` bell icon | Already built, already tenant-scoped (via the same `TenantIsolatedCollection` wrapper when `db` is obtained via `get_database()`), already has read/unread/delete endpoints and a polling frontend component — zero new frontend code needed for delivery |
| Tenant isolation for the new collection | Manual `tenantId` filter checks sprinkled through the service | Simply do NOT add `control_comments` to `database.py`'s exemption list — the wrapper handles it for free | This is the single most consequential "don't hand-roll" in this phase; manual tenant filtering is exactly the kind of code that silently rots when someone adds a new query path later and forgets the filter |
| Role-gate mirroring on the frontend | A shared roles constants module (tempting DRY refactor, out of scope) | Duplicate the literal role array, matching the `EvidenceReviewPanel.tsx`/`evidence_review_endpoints.py` precedent's explicit "manually kept in sync" comment | Introducing a new shared-constants module is a larger refactor than this single-requirement phase warrants; the existing precedent already accepts this tradeoff and documents it inline |

**Key insight:** Every piece of infrastructure this phase needs (notification delivery, tenant isolation, role gating, panel-mount UX) already exists in this codebase in a directly analogous form. The entire implementation is disciplined reuse — the risk in this phase is not "what do we build" but "which existing pattern do we clone correctly vs. which one is a trap" (see Common Pitfalls).

## Common Pitfalls

### Pitfall 1: Embedding comments on `compliance_controls` leaks across tenants

**What goes wrong:** A literal reading of "clone `tickets_endpoints.py`'s comment pattern" leads to `db.compliance_controls.update_one({"id": control_id}, {"$push": {"comments": comment}})` — every tenant then sees every other tenant's comments on that control, since `compliance_controls` is shared global reference data.

**Why it happens:** `compliance_controls` is explicitly listed in `database.py`'s exemption allowlist twice (`__getattr__` line 125, `__getitem__` line 142) as global reference data — the seeded framework control definitions are one document per control, identical for every tenant. Tickets are tenant-owned documents, so `$push` is safe there; controls are not.

**How to avoid:** New, separate `control_comments` collection (confirmed NOT on the exemption list). Never write comment data onto `compliance_controls`.

**Warning signs:** Any code with `db.compliance_controls.update_one(..., {"$push": ...})`; a UAT step where Tenant A sees Tenant B's comment text on the same control ID.

### Pitfall 2: Cloning the broken `ticket_notifications.py` @mention delivery path

**What goes wrong:** `_send()` in `ticket_notifications.py` does `from notification_service import notification_service` and calls `.send_alert(...)` on it. This import fails with `ImportError` (verified live: `notification_service.py` exports no such name, only the `NotificationService` class and `get_notification_service(db)` factory). The failure is swallowed by `except Exception: pass` in `tickets_endpoints.py:285-286`, so the existing tickets @mention notification silently does nothing today.

**Why it happens:** At some point `notification_service.py` was refactored away from a module-level singleton pattern to the `get_notification_service(db)` factory pattern, and `ticket_notifications.py` was never updated to match.

**How to avoid:** In `control_comments_endpoints.py`, instantiate via `from notification_service import get_notification_service; svc = get_notification_service(db)` (where `db = get_database()`, the request-scoped tenant-isolated handle already in use for the comment write), then `await svc.send_alert(title=..., message=..., severity="info", recipients=[...], tenant_id=tenant_id, channels=[], metadata={...})`. Passing `channels=[]` (or omitting all of `email`/`sms`/`slack`/`webhook`) means only the unconditional `db.notifications.insert_one(...)` at the end of `send_alert()` fires — no email/SMS/Slack side effects, matching D-02's "in-app only" requirement precisely.

**Warning signs:** A "You were mentioned" toast/API response that returns 200 but the mentioned user's bell icon never shows a new item; `notifications.log`/console shows nothing (because no channel dispatch happened, not because of a caught exception — check both).

### Pitfall 3: `@username` plain-text parsing is genuinely new — no reusable regex or resolution logic exists

**What goes wrong:** Assuming the tickets `@mention` regex (`r'@([\w.+-]+@[\w.+-]+\.[a-z]+)'`) can be reused as-is for D-04's plain-text `@username` requirement. It cannot — that regex requires a full email address after `@` and will match zero mentions for `@jsmith`-style text.

**Why it happens:** The tickets feature's mentions are resolved directly against `ticket.reporter`/`ticket.assignee`/`ticket.watchers` fields, which are themselves stored as email strings (`_recipients()` filters candidates by `"@" in r`) — the regex was designed to extract an email, not a username, because the whole downstream pipeline expects an email as the "recipient." This codebase's `db.users` documents primarily carry `email`/`name` fields (confirmed in `authentication_endpoints.py:319-331`'s signup `user_doc`); a distinct `username` field is optional/sparse (only referenced as an alternate login identifier at `authentication_endpoints.py:137-141`, not always populated). Also worth noting: `TokenData.username` (the field name suggests a username) is actually populated from the JWT `sub` claim, which is set to the user's **email** at every token-issuance site (`authentication_endpoints.py:180-182,355-359,444-449`) — i.e., "username" in this codebase's auth layer is a misnomer for "email," which is a source of real confusion when designing an `@username` mention feature.

**How to avoid:** Treat this as a genuinely new, small design task, not a clone: (1) extract `@` tokens with a plain-identifier regex (e.g. `r'@([\w.-]+)'`, no email-shape requirement), (2) resolve each token against `db.users` by trying, in order, an exact `username` field match, then an email-local-part match (`email` starting with `token + "@"`), then optionally a case-insensitive `name` match — falling back to "no match, skip" for tokens that resolve to nothing (never error the whole comment POST over an unresolved mention). Document the chosen resolution order in the plan since none of the three is definitively "the" existing convention — this is flagged as Assumption A1 below.

**Warning signs:** A comment containing `@realuser` never triggers a notification even though `realuser` is a valid tenant member; a comment containing `@realuser@company.com` (full email) is required to work but plain `@realuser` silently does nothing (a sign the tickets regex was copied instead of a new one written).

### Pitfall 4: New router never registered in `router_registry.py`

**What goes wrong:** `control_comments_endpoints.py` is written and unit-tested in isolation but 404s through the real running app.

**Why it happens:** Documented as a recurring pattern in this codebase (5 dashboards found orphaned in a v2.0 audit; multiple phases in v3.0 hit the equivalent backend version of this — new router files must be explicitly listed in `router_registry.py`, nothing scans for them automatically).

**How to avoid:** Add `_load(app, "control_comments_endpoints", "router")` in `router_registry.py`, next to `evidence_review_endpoints` at line 179 (same "Governance & Compliance" grouping, lines 169-179). After registering, hit the route through a real `TestClient(app)` (not `TestClient(router)`) at least once — a passing unit test against the bare router object does not prove it's mounted in the real app.

**Warning signs:** `grep control_comments_endpoints backend/router_registry.py` returns nothing; endpoint works in an isolated unit test but 404s when the full app is exercised.

### Pitfall 5: New frontend panel built but never mounted / unreachable

**What goes wrong:** `ControlCommentsPanel.tsx` is fully built and works in isolation but is never actually rendered inside `FrameworkDetail.tsx`, so it's unreachable from the real app despite passing component-level tests.

**Why it happens:** Documented as the dominant "looks done but isn't" failure mode across this project's history (5 stranded dashboards in v2.0, repeated in multiple v3.0 phases). This phase is lower-risk than those cases because there is no new route/nav-entry required (the mount point is an existing, already-reachable expanded-row slot) — but the mount edit to `FrameworkDetail.tsx` itself is still a discrete, skippable step.

**How to avoid:** Explicitly verify (grep + live click-through, not just a passing test) that `<ControlCommentsPanel controlId={control.id} />` appears in `FrameworkDetail.tsx`'s JSX, immediately after the `ChainOfCustodyPanel` at line 432, and that expanding any control row in a live browser session shows the new panel.

**Warning signs:** `grep ControlCommentsPanel components/FrameworkDetail.tsx` returns nothing; API-only testing (curl/Postman) reports success but a live browser click-through can't find the feature.

## Runtime State Inventory

Not applicable — this is a greenfield phase (new collection, new files, new component). No rename/refactor/migration is involved; nothing in this phase changes the meaning or storage location of any existing data.

## Code Examples

### Reading tenant-scoped comments (backend)

```python
# Pattern source: backend/evidence_review_service.py (get_reviews shape) +
# backend/database.py (TenantIsolatedCollection default path)
async def list_comments(db, control_id: str) -> list[dict]:
    cursor = db.control_comments.find({"control_id": control_id}, {"_id": 0})
    return await cursor.sort("created_at", 1).to_list(length=200)
```

### Role-gated POST with append-only write (backend)

```python
# Pattern source: backend/evidence_review_endpoints.py:119-166 (role gate + tenant check shape)
_COMMENT_AUTHOR_ROLES = {"admin", "super_admin", "compliance_reviewer"}   # D-01

@router.post("/api/control-comments")
async def post_control_comment(
    body: CreateCommentRequest,
    current_user: TokenData = Depends(get_current_user),
):
    if current_user.role not in _COMMENT_AUTHOR_ROLES:
        raise HTTPException(status_code=403, detail="Only admins and compliance reviewers can comment")
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    db = get_database()
    comment = await add_comment(db, body.control_id, author=current_user.username, text=body.text)
    # D-03: no PATCH/DELETE route exists for this resource anywhere — that absence IS the enforcement.

    for mention_email in await resolve_mentions(db, body.text):   # Pitfall 3 — new logic, no direct precedent
        svc = get_notification_service(db)
        try:
            await svc.send_alert(
                title="You were mentioned in a control comment",
                message=f"{current_user.username} mentioned you: \"{body.text[:120]}\"",
                severity="info",
                recipients=[mention_email],
                tenant_id=tenant_id,
                channels=[],   # D-02: in-app only — no email/sms/slack dispatch
                metadata={"control_id": body.control_id, "event": "mention"},
            )
        except Exception:
            pass  # non-fatal, matches tickets_endpoints.py's mention-notification error handling
    return comment
```

### Frontend fetch/post wrappers

```typescript
// Pattern source: services/apiService.ts:4564-4572 (fetchControlAuditLog)
export const fetchControlComments = async (controlId: string): Promise<any[]> => {
    try {
        const res = await authFetch(`${API_BASE}/control-comments?control_id=${controlId}`);
        if (!res.ok) return [];
        return await res.json();
    } catch {
        return [];
    }
};

export const postControlComment = async (controlId: string, text: string): Promise<any> => {
    const res = await authFetch(`${API_BASE}/control-comments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ control_id: controlId, text }),
    });
    if (!res.ok) throw new Error('Failed to post comment');
    return await res.json();
};
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| N/A — this is a net-new feature, no prior implementation to compare against | Tenant-scoped dedicated collection + in-app-only notification | This phase (v3.2) | Establishes the pattern for any future "comment on a globally-shared resource" feature in this codebase |

**Deprecated/outdated:** None — nothing in this phase replaces existing functionality.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `@username` mention resolution should try, in order: exact `username` field match → email-local-part match → case-insensitive `name` match, skipping unresolved tokens silently | Pitfall 3, Code Examples | LOW — if the resolution order is wrong, mentions simply don't notify the intended user in some edge cases (e.g. duplicate local-parts across different domains within the same tenant); does not affect tenant isolation or comment posting itself, purely a notification-delivery UX gap. Should be confirmed with the user or the planner before implementation, since it's the one genuinely novel piece of logic in this phase. |
| A2 | GET `/api/control-comments` should be open to any authenticated tenant user (not role-gated), matching how `evidence_review_endpoints.py`'s GET routes are unrestricted while only the decision-making PATCH is role-gated | Architecture Patterns, Pattern 2 | LOW — if comments should actually be read-restricted to the same `_COMMENT_AUTHOR_ROLES` set, this is a one-line change (add the same role check to the GET handler); CMT-01's requirement text says "post... tenant-scoped" without specifying read-visibility restrictions beyond tenant scope, so the permissive-read interpretation is the more conservative (narrower blast radius) default. |
| A3 | Comments should auto-fetch/render when the control row expands, not require a second click like `ChainOfCustodyPanel`'s collapse/expand toggle | Architecture Patterns, Pattern 4 | LOW — purely a UX preference; if wrong, a UI-phase/plan-check pass can flip it to match the CoC panel's click-to-expand pattern with no backend impact. |

## Open Questions

1. **Exact `@username` token-to-user resolution query shape**
   - What we know: `db.users` documents have `email`/`name` reliably, `username` optionally (see Pitfall 3).
   - What's unclear: Whether every tenant's users reliably have a distinct, collision-free identifier suitable for `@mention` matching, or whether email-local-part collisions across users in the same tenant are possible (e.g. two different email domains both having a `jsmith` local part, if a tenant spans multiple orgs).
   - Recommendation: Plan should scope this as: try exact `username` match first (if present), else email-local-part match, and explicitly accept "ambiguous match, notify the first result only" as acceptable v1 behav9or (matches this platform's general risk tolerance for a notification-only feature with no security implication either way).

2. **Whether `compliance_controls` documents are ever actually fetched as MongoDB documents for a "single control" view, or whether `control.id` always originates from an in-memory Python framework module list (e.g. `backend/frameworks/soc2.py`'s `CONTROLS` list)**
   - What we know: `Control.id` on the frontend (e.g. `"CC1.1"`) is the framework-defined control code, consumed identically by `compliance_remediation_tasks.control_id` today with no FK validation (per `ARCHITECTURE.md`'s already-documented precedent).
   - What's unclear: Whether `db.compliance_controls` (the Mongo collection, distinct from the Python framework module lists) is ever queried for a specific control by ID in a code path this phase would touch, or whether it's populated only for import/MCP-tool purposes.
   - Recommendation: Treat `control_id` as a loose, unvalidated foreign key exactly like `compliance_remediation_tasks.control_id` already does — no join/existence check needed at write time. This is the existing, proven precedent and avoids scope creep into validating framework control catalogs.

## Environment Availability

Not applicable — no new external dependencies, services, or CLI tools are introduced by this phase. MongoDB and the existing FastAPI/React toolchain are already running and verified (per `backend-test-environment` memory: full suite green 932/0 as of the last full run).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.0 + pytest-asyncio (auto mode) |
| Config file | `pytest.ini` (repo root) |
| Quick run command | `cd backend && venv/bin/python -m pytest tests/test_control_comments.py -q` (new file, does not exist yet) |
| Full suite command | `cd backend && venv/bin/python -m pytest -q` |

**Must use `backend/venv/bin/python`** — the system Python has no pytest installed and the environment is externally managed (per `backend-test-environment` memory note).

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CMT-01 | Non-reviewer role cannot POST a comment (403) | unit | `venv/bin/python -m pytest tests/test_control_comments.py -k test_non_author_role_forbidden -q` | ❌ Wave 0 |
| CMT-01 | Reviewer/admin can POST a comment, comment persists and is retrievable | unit | `venv/bin/python -m pytest tests/test_control_comments.py -k test_post_and_list_comment -q` | ❌ Wave 0 |
| CMT-01 | Tenant A cannot see Tenant B's comments on the same `control_id` | unit | `venv/bin/python -m pytest tests/test_control_comments.py -k test_tenant_isolation -q` | ❌ Wave 0 |
| CMT-01 | @mention in comment text triggers a `db.notifications` write (in-app) | unit | `venv/bin/python -m pytest tests/test_control_comments.py -k test_mention_triggers_notification -q` | ❌ Wave 0 |
| CMT-01 | @mention notification does NOT trigger email/sms/slack channel dispatch | unit | `venv/bin/python -m pytest tests/test_control_comments.py -k test_mention_is_in_app_only -q` | ❌ Wave 0 |
| CMT-01 | Comment appears in `FrameworkDetail.tsx`'s expanded control row (manual/live) | manual | Live browser click-through: expand a control, post a comment, confirm it renders | n/a (manual gate) |

**Reference test for the role-gate shape to clone:** `backend/tests/test_evidence_review.py::test_non_reviewer_role_forbidden_from_decision` (lines 312-322) — uses `_make_user(role=...)` MagicMock + FastAPI `TestClient` with `dependency_overrides`, asserts `resp.status_code == 403`.

### Sampling Rate

- **Per task commit:** `venv/bin/python -m pytest tests/test_control_comments.py -q`
- **Per wave merge:** `venv/bin/python -m pytest -q` (full backend suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `backend/tests/test_control_comments.py` — new file, covers all 5 automated CMT-01 test rows above. No existing test file covers control comments (confirmed: `test_tickets.py` has zero comment-specific tests, so there is no direct test-shape clone target beyond the role-gate pattern in `test_evidence_review.py`).
- [ ] No new fixtures needed — `_make_user`/`_make_mock_db`-style helpers can be copied inline from `test_evidence_review.py`'s existing pattern (MagicMock db, AsyncMock methods, `asyncio.run()` or native `pytest-asyncio` per the file's existing convention).
- [ ] Framework install: none — pytest/pytest-asyncio already installed in `backend/venv`.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (inherited) | `Depends(get_current_user)` — existing JWT bearer auth, unchanged by this phase |
| V3 Session Management | no | No new session concept introduced |
| V4 Access Control | yes | Role-gate on POST (`_COMMENT_AUTHOR_ROLES` set check, D-01) + tenant isolation on both POST and GET (`TenantIsolatedCollection` default path, D-per-ARCHITECTURE.md) |
| V5 Input Validation | yes | Pydantic `CreateCommentRequest` with `text: str = Field(..., min_length=1, max_length=2000)` — mirror `evidence_review_endpoints.py`'s `CreateReviewRequest` length bound to prevent unbounded comment text |
| V6 Cryptography | no | No new cryptographic material — comments are plaintext, matching the tickets-comment precedent (no encryption-at-rest beyond whatever MongoDB-level encryption already exists for the whole DB) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-tenant data disclosure via a shared/exempt collection | Information Disclosure | New collection NOT added to `database.py`'s exemption list — verified as the single highest-severity pitfall for this phase in `PITFALLS.md`; the plan's verification step must include a live two-tenant isolation test, not just a mocked unit test, per `PITFALLS.md`'s "Looks Done But Isn't" checklist item for comment threads |
| Privilege escalation via role-check bypass (posting as a non-reviewer) | Elevation of Privilege | Server-side role check on every POST, never trust a frontend-only gate — `evidence_review_endpoints.py`'s comment in its own docstring already states this explicitly: "The backend always re-enforces authorization server-side regardless of the frontend list" |
| Stored XSS via unescaped comment text rendered in `ControlCommentsPanel.tsx` | Tampering | React's default JSX text-node escaping handles this automatically as long as comment text is rendered as `{comment.text}`, never via `dangerouslySetInnerHTML` — explicitly flag this as a "don't" for the plan's frontend task |
| Mention-notification spam (posting a comment with many `@mentions` to flood a target's notification feed) | Denial of Service (minor) | Existing `@limiter.limit("30/minute")` pattern already used on `evidence_review_endpoints.py`'s POST routes should be applied to `POST /api/control-comments` too — mirrors the rate-limit precedent already established for this exact class of endpoint, and note the `response: Response` param is required by slowapi (confirmed pitfall pattern across this codebase — every `@limiter.limit(...)`-decorated route must accept a `response: Response` parameter or the rate limiter silently fails to enforce, per this milestone's own documented "Looks Done But Isn't" checklist item) |

## Sources

### Primary (HIGH confidence — direct code reads, this repository, `feat/rust-agent-2.1.0-and-fixes` branch, 2026-07-21)

- `backend/tickets_endpoints.py` (lines 250-309) — comment POST endpoint shape, @mention regex, notification hook
- `backend/tickets_service.py` (lines 330-373) — `add_comment()` storage mechanism (the anti-pattern to avoid)
- `backend/tickets_models.py` — `_actor`/`_effective_tenant` helpers
- `backend/ticket_notifications.py` — confirmed broken `_send()` import (`from notification_service import notification_service` → `ImportError`, verified live)
- `backend/notification_service.py` (lines 1-421) — `NotificationService.send_alert()`, `get_notification_service(db)` factory, `db.notifications.insert_one()` write shape
- `backend/notification_endpoints.py` (lines 1-110) — `GET/PUT/DELETE /api/notifications` read/mark-read/delete routes, confirms `{alert_id, title, message, severity, sent_at, read}` shape
- `backend/evidence_review_endpoints.py` (full file) — `_REVIEWER_ROLES` role-gate pattern (lines 45, 133-137), rate-limiting pattern
- `backend/evidence_coc.py` — chain-of-custody append-only mechanism (confirmed: pure convention, no DB-level enforcement, no update/delete route ever written)
- `backend/database.py` (lines 1-151) — `TenantIsolatedCollection`, `TenantIsolatedDatabase` exemption allowlist (confirmed `control_comments`/`compliance_remediation_tasks` absent, `compliance_controls` present)
- `backend/authentication_endpoints.py` (lines 125-153, 315-360, 440-449) — `db.users` document shape, confirms `TokenData.username` is populated from email, confirms `username` field is optional/sparse
- `backend/auth_types.py` — `TokenData` model fields
- `components/FrameworkDetail.tsx` (lines 1-70, 370-470) — `expandedControlId` state, exact mount point after `ChainOfCustodyPanel` at line 432
- `components/ChainOfCustodyPanel.tsx` (full file) — lazy-fetch-on-expand panel structure to mirror
- `components/EvidenceReviewPanel.tsx` (lines 1-90) — frontend role-gate mirror pattern
- `components/NotificationCenter.tsx` — bell-icon component, confirms `{alert_id, title, message, severity, read}` consumption shape, existing polling mechanism
- `services/apiService.ts` (lines 4564-4572) — `fetchControlAuditLog` wrapper shape to clone
- `types.ts` (lines 440-472) — `ComplianceFramework`/`Control` frontend type shapes, confirms `control.id` is a framework-defined code string
- `backend/router_registry.py` (lines 160-189) — registration point for the new router, next to `evidence_review_endpoints` at line 179
- `backend/tests/test_evidence_review.py` (lines 1-60, 312-322) — role-gate test pattern to clone (`test_non_reviewer_role_forbidden_from_decision`), mock-db test setup convention
- `backend/tests/test_tickets.py` — confirmed no existing comment-specific test coverage exists to clone directly
- Live verification: `backend/venv/bin/python -c "from notification_service import notification_service"` → `ImportError: cannot import name 'notification_service'` (confirms Pitfall 2)
- Live verification: `backend/venv/bin/python -m pytest tests/test_evidence_review.py -k test_non_reviewer_role_forbidden_from_decision -q` → 1 passed

### Secondary (MEDIUM confidence)

- `.planning/research/ARCHITECTURE.md` (v3.2 milestone research, 2026-07-20) — cross-checked and confirmed accurate against direct source reads in this session; no corrections needed, only sharpened with exact line numbers and the newly-discovered broken-notification-import finding
- `.planning/research/PITFALLS.md` (v3.2 milestone research, 2026-07-20) — Pitfall 2 (comment-thread cross-tenant leak) independently re-verified against `database.py` in this session; confirmed accurate
- `.planning/research/FEATURES.md` (v3.2 milestone research, 2026-07-20) — confirms flat-comment-list scope and no-threading/no-reactions anti-feature guidance

### Tertiary (LOW confidence)

- None — this phase's research required no external web search; it is 100% internal codebase archaeology, consistent with the milestone-level research's own method note.

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — zero new dependencies, entirely internal-pattern reuse verified by direct code read
- Architecture: HIGH — every component/pattern is grounded in an actual file/line citation in this repository
- Pitfalls: HIGH — all 5 pitfalls verified against actual source (including a live Python import test proving Pitfall 2)
- @mention resolution logic (Pitfall 3 / Assumption A1): MEDIUM — the problem is well-understood and grounded in real `db.users` schema reads, but the exact resolution algorithm is new design work, not a clone of an existing pattern, hence flagged as an assumption rather than a verified fact

**Research date:** 2026-07-21
**Valid until:** 30 days (stable internal codebase, no fast-moving external dependency)
