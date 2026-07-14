---
phase: 29-public-trust-center
plan: 03
subsystem: web
tags: [trust-center, admin-ui, react, toast, accessibility, custom-domain]

# Dependency graph
requires:
  - phase: 29-public-trust-center (plan 01)
    provides: "DB-backed PUT /api/trust-center/profile returning trust_slug/trust_domain"
provides:
  - "services/apiService.ts updateTrustProfile() client function (PUT /api/trust-center/profile)"
  - "components/TrustCenter.tsx profile edit form, Sharing section (Public Trust Page URL + Copy Link, Custom Domain), approve/deny toasts, aria-labels"
  - "components/TrustProfileEditForm.tsx extracted edit-form component"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Extracted a large form (TrustProfileEditForm.tsx) out of an existing dashboard component to stay under the CLAUDE.md 500-line file limit, following the 08-02 BulkEvidenceUploadModal precedent — parent owns state, child receives editForm + an onChange(updater) callback"

key-files:
  created:
    - components/TrustProfileEditForm.tsx
  modified:
    - services/apiService.ts
    - components/TrustCenter.tsx

key-decisions:
  - "Extracted the profile edit form (company name, description, contact email, logo URL, compliance-framework add/remove, public/private document add/remove, sharing/custom-domain fields) into a new components/TrustProfileEditForm.tsx rather than inlining it in TrustCenter.tsx, because the full inline form would have pushed TrustCenter.tsx past the 500-line CLAUDE.md limit. TrustCenter.tsx ended at 349 lines, TrustProfileEditForm.tsx at 243 — both well under budget."
  - "The global TrustProfile type in types.ts (imported by apiService.ts) already carried optional trust_slug/trust_domain fields — no interface change was needed there; only the local TrustProfile interface inside TrustCenter.tsx (and the new TrustProfileFormData in the extracted form) needed the two optional fields added."
  - "Kept the read-only Sharing section (Public Trust Page URL + Copy Link, Custom Domain display) visible on the profile preview even when not editing, in addition to the editable Custom Domain field inside the edit form — so an admin can copy the public link without entering edit mode."

requirements-completed: [TRUST-01, TRUST-03]

# Metrics
duration: 22min
completed: 2026-07-14
status: complete
---

# Phase 29 Plan 03: Trust Center Admin UI — Profile Edit, Custom Domain, Toasts Summary

**Closed the two real frontend gaps blocking TRUST-01/TRUST-03: added `updateTrustProfile()` to apiService.ts and built the missing profile edit form, Public Trust Page URL/Copy Link, Custom Domain field, and approve/deny toast+aria-label additions in TrustCenter.tsx (extracting the edit form into a new component to respect the 500-line file limit).**

## Performance

- **Duration:** 22 min
- **Completed:** 2026-07-14
- **Tasks:** 3
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- `services/apiService.ts` now exposes `updateTrustProfile(updates)` — `PUT ${API_BASE}/trust-center/profile` via `authFetch`, mirroring `updateTrustRequest`'s shape exactly, using the already-imported global `TrustProfile` type (which already had `trust_slug?`/`trust_domain?` from 29-01's backend work).
- `components/TrustCenter.tsx` gained an "Edit Profile" toggle on the Profile tab that swaps the read-only preview for `TrustProfileEditForm`, wired to `handleSaveProfile` (calls `api.updateTrustProfile`, toasts success/error, exits edit mode on success).
- A "Sharing" section renders on the read-only profile view: a read-only "Public Trust Page URL" (`{window.location.origin}/trust/{trust_slug}`) with a working "Copy Link" button (`navigator.clipboard.writeText` + `showToast('Public link copied to clipboard', 'success')`), and the current "Custom Domain" value (or "Not set"). The same Custom Domain field is editable inside the edit form and submitted as `trust_domain` on save.
- New `components/TrustProfileEditForm.tsx` (243 lines) holds the full edit form: company name, description, contact email, logo URL, add/remove-row editors for `compliance_frameworks[]`, `public_documents[]`, and `private_documents[]` (with an explicit note that the private-doc URL is an admin-only reference), plus its own Sharing sub-section (Copy Link + editable Custom Domain with the exact UI-SPEC helper text).
- `handleRequestAction` now calls `showToast('Request approved.', 'success')` / `showToast('Request denied.', 'success')` on success and `showToast('Could not update request status. Please try again.', 'error')` in the catch block; the icon-only `UserCheck`/`XCircle` buttons carry `aria-label="Approve request"` / `aria-label="Deny request"` (existing `title` attributes and the reversible-status interaction model were left unchanged — no confirmation modal was added).
- `npm run build` (Vite production build) and `npx tsc --noEmit` both pass clean with no new errors referencing any of the three files.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add updateTrustProfile() to apiService.ts** - `cda3692c` (feat)
2. **Task 2: Profile edit form + Custom Domain field + Public Trust Page URL / Copy Link** - `d43c89cd` (feat)
3. **Task 3: Approve/Deny success+error toasts and aria-labels** - `e3a045bc` (feat)

## Files Created/Modified
- `services/apiService.ts` - Added `updateTrustProfile(updates: Partial<TrustProfile>): Promise<TrustProfile>` directly below `updateTrustRequest`.
- `components/TrustCenter.tsx` - Local `TrustProfile` interface extended with `trust_slug?`/`trust_domain?`; added `isEditing`/`editForm`/`saving` state; added `startEditing`/`cancelEditing`/`handleSaveProfile`/`handleCopyLink` handlers; profile preview now shows an "Edit Profile" button and a read-only Sharing section; `handleRequestAction` now toasts; Approve/Deny buttons carry aria-labels. Ended at 349 lines.
- `components/TrustProfileEditForm.tsx` (new) - Extracted edit-form component: receives `editForm`/`saving`/`onChange`/`onSave`/`onCancel` props; owns its own framework/document add-remove-row handlers and the editable Sharing sub-section (Copy Link + Custom Domain input with helper text). 243 lines.

## Decisions Made
- Extracted the edit form into a new file per the plan's explicit fallback instruction (500-line CLAUDE.md limit, precedent: 08-02 BulkEvidenceUploadModal split) rather than inlining everything into `TrustCenter.tsx` — inlining the full form (frameworks + two document lists + sharing section, each with add/remove-row controls) would have pushed the file well past 500 lines.
- Kept a read-only Sharing display on the non-editing profile view (in addition to the editable one inside the form) so Copy Link works without entering edit mode — this is an additive UX choice consistent with the plan's "Public Trust Page URL is shown with a working Copy Link" success criterion, which doesn't gate the link behind edit mode.
- No changes were needed to the global `TrustProfile` type in `types.ts` — it already had the optional `trust_slug`/`trust_domain` fields from a prior session; only the component-local interfaces needed the addition.

## Deviations from Plan

### Auto-fixed Issues

None requiring the Rule 1-4 process — plan executed as written. The one implementation choice not spelled out verbatim in the plan (extracting `TrustProfileEditForm.tsx` as a separate component vs. some other split strategy) was explicitly pre-authorized by the plan's own text ("If these additions push the file over 500 lines... extract the edit form into a new `components/TrustProfileEditForm.tsx`").

## Issues Encountered

None. `npm run build` and `npx tsc --noEmit` passed clean on the first attempt after each task's edits.

## User Setup Required

None - no external service configuration required. No new npm packages introduced (confirmed by the plan's threat register T-29-SC: `lucide-react`, Tailwind, and `utils/toast.ts` are all pre-existing dependencies).

## Next Phase Readiness
- TRUST-01 (admin profile management) and TRUST-03 (custom domain + public link admin surface) are both functionally complete on the frontend, backed by the already-shipped 29-01/29-02 routes.
- Manual verification (per 29-VALIDATION.md Manual-Only gate, listed in this plan's `<verification>` block) is still outstanding: log in as an admin, edit + save the profile, copy the public link, set a custom domain, approve/deny a request and confirm the toast appears. This was not exercised in a live browser session as part of this automated execution.
- No blockers.

## Known Stubs

None. No hardcoded empty values, placeholder text, or unwired data sources were introduced. The "Trust Analytics" quick-stats panel (Profile Views, Document Downloads) retains its pre-existing hardcoded `1,245`/`342` values — these were not touched by this plan and are out of scope (not part of TRUST-01/TRUST-03's must_haves; no backend analytics endpoint exists to wire them to).

## Threat Flags

None. This plan's surface (admin-only, authenticated `TrustCenter.tsx`/`TrustProfileEditForm.tsx`) is fully covered by the plan's own `<threat_model>` (T-29-01, T-29-03, T-29-07, T-29-SC — all closed). No new network endpoints, auth paths, or trust-boundary-crossing surface was introduced beyond what the plan's threat register already accounts for; all admin actions continue to route exclusively through `authFetch` (JWT bearer) to the existing `_TRUST_ADMIN_ROLES`-gated routes.

---
*Phase: 29-public-trust-center*
*Completed: 2026-07-14*

## Self-Check: PASSED

- FOUND: services/apiService.ts
- FOUND: components/TrustCenter.tsx
- FOUND: components/TrustProfileEditForm.tsx
- FOUND: .planning/phases/29-public-trust-center/29-03-SUMMARY.md
- FOUND commit: cda3692c (Task 1: updateTrustProfile)
- FOUND commit: d43c89cd (Task 2: edit form + custom domain + sharing)
- FOUND commit: e3a045bc (Task 3: toasts + aria-labels)
