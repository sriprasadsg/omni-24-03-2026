# Phase 42: Comment Threads on Compliance Controls - Context

**Gathered:** 2026-07-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Let compliance admins/reviewers discuss a specific control via a comment thread, scoped to their own tenant, with @mention notifications — a feature genuinely absent from the platform today. Storage must be a new tenant-scoped `control_comments` collection, never embedded on `compliance_controls` (which is on the tenant-isolation exemption allowlist as global reference data — embedding there would leak comments cross-tenant).

</domain>

<decisions>
## Implementation Decisions

### Who can comment
- **D-01:** Restrict to `admin`, `super_admin`, `compliance_reviewer` roles — mirrors the existing evidence-review restriction in `evidence_review_service.py`. Consistent with who else gets to weigh in on compliance state in this platform, rather than opening comments to any authenticated tenant user.

### @mention notification delivery
- **D-02:** In-app only, via the existing notification system (bell icon / `NotificationsDashboard`). No new email-delivery surface for v1 — matches how other in-app events already notify users and avoids adding an email path to verify.

### Comment editing/deletion
- **D-03:** Immutable — comments are append-only once posted, no edit or delete. Matches the chain-of-custody-log precedent already established in this codebase (Phase 7, `COC-01`/`COC-02`) for compliance-adjacent records, avoiding ambiguity about audit-trail integrity.

### @mention autocomplete
- **D-04:** Plain-text `@username` parsing after posting — no live autocomplete/user-search dropdown. Matches CMT-01's minimal scope; a live-search UI component would be new UI surface disproportionate to a single-requirement phase.

### Claude's Discretion
- All 4 decisions above were explicitly deferred by the user ("You decide") — the rationale in each is Claude's, applying "match existing platform patterns, minimal viable scope" as the guiding principle throughout.
- Exact @mention regex/parsing implementation.
- Notification payload shape (reusing whatever the existing notification system's schema is).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone research (v3.2)
- `.planning/research/ARCHITECTURE.md` — confirms `control_comments` as a new, non-exempt, tenant-scoped collection; mounts inside `FrameworkDetail.tsx`'s existing `expandedControlId` row, no new Sidebar/App.tsx nav entry needed
- `.planning/research/PITFALLS.md` — the cross-tenant leak risk of embedding comments on `compliance_controls` (tenant-isolation-exempt); clone `tickets_service.add_comment`'s endpoint *shape* only, not its `$push`-to-parent-doc storage mechanism
- `.planning/research/FEATURES.md` — flat comment list is table stakes; nested/threaded replies and reactions are anti-features (no GRC competitor implements this on controls)

### Codebase maps
- `.planning/codebase/CONVENTIONS.md` — naming/error-handling/logging conventions the new `control_comments_service.py`/`control_comments_endpoints.py` should follow

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tickets_endpoints.py:250` (`POST /{ticket_id}/comments`) — endpoint shape to clone (not storage mechanism).
- `evidence_review_service.py` — role-restriction pattern (`admin`/`super_admin`/`compliance_reviewer`) to reuse per D-01.
- Existing in-app notification system (bell icon / `NotificationsDashboard`) — delivery target per D-02.
- Chain-of-custody log pattern (Phase 7, `evidence_audit_log`) — append-only precedent informing D-03.

### Established Patterns
- `compliance_controls` is tenant-isolation-exempt (global reference data) — new comment collection must NOT be added to that exemption list; it goes through the default `TenantIsolatedCollection` path.

### Integration Points
- `FrameworkDetail.tsx` — mount point for the new comment panel (expanded-control row), per ARCHITECTURE.md.

</code_context>

<specifics>
## Specific Ideas

None beyond the decisions captured above.

</specifics>

<deferred>
## Deferred Ideas

- Live @mention autocomplete — deferred per D-04; could be a future enhancement if plain-text parsing proves insufficient in practice.
- Email notification delivery for @mentions — deferred per D-02; revisit if in-app-only proves insufficient.

</deferred>

---

*Phase: 42-comment-threads-on-compliance-controls*
*Context gathered: 2026-07-20*
