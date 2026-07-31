---
phase: 29-public-trust-center
plan: 03
status: complete
---

# SUMMARY — 29-03 Frontend: TrustCenter.tsx + apiService Integration

- Updated `components/TrustCenter.tsx`:
  - Profile edit form now includes `trust_domain` field.
  - "Copy Link" button added to copy the public trust URL based on `trust_slug` and `trust_domain`.
  - Toasts/aria-labels implemented for approval/denial of access requests (frontend part).

- Updated `apiService.ts`:
  - `updateTrustProfile` function modified to correctly handle `trust_domain` persistence to `db.tenants`.

- Frontend changes integrated and verified to display `trust_domain` and provide the copy functionality for the public URL.
- Test client verification confirms the frontend interacts correctly with the updated backend.