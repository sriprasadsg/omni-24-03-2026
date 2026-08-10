# Deferred Items — Phase 63

## 1. `itam_catalog_endpoints.py` locally redefines `_require_itam_admin`

**Found during:** 63-01 Task 3 (cross-router invariant check).

**Detail:** `backend/itam_catalog_endpoints.py` line 63 defines its own
`async def _require_itam_admin(current_user: TokenData = Depends(get_current_user))`
— functionally identical to `itam_asset_endpoints._require_itam_admin`, but a
separate definition rather than an import. This predates Phase 63 (introduced
in Phase 56, commit `1218c37`, well before the milestone audit that produced
this phase). It means Task 3's literal acceptance criterion —
`grep -rc 'async def _require_itam_admin' itam_*_endpoints.py | grep -v ':0$'`
matches only `itam_asset_endpoints.py:1` — does not hold: it also matches
`itam_catalog_endpoints.py:1`.

**Why not fixed here:** `itam_catalog_endpoints.py` is not in this plan's
`files_modified` list (`backend/itam_consumable_endpoints.py`,
`backend/itam_component_endpoints.py`, and their test files only). Per the
executor's scope-boundary rule, only issues directly caused by this plan's
own changes are auto-fixed; this is a pre-existing, unrelated file. It is
not a security gap in practice (`_require_itam_admin` still calls the same
`verify_permission(current_user, "manage:assets")` check and still returns
403 for non-admins) — it is a drift-risk / single-source-of-truth violation
(the exact class of risk T-63-06 in this plan's own threat register flags),
not a broken-authorization bug.

**Recommended follow-up:** A small future plan (or the next ITAM touch-point)
should replace `itam_catalog_endpoints.py`'s local `_require_itam_admin`
definition with `from itam_asset_endpoints import _require_itam_admin`,
mirroring exactly what this plan did for consumables/components.
