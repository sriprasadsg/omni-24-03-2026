# Phase 84 deferred items

## From 84-18 (ring detail)

- **A ring with more than 25 computers shows only its first 25.** `backend/autonomous_ops/rollout/views.py` `host_rows` returns `HOST_PAGE` (25) computers per ring plus `hostTotal`, and `backend/patch_rollout_endpoints.py` has no route that returns more. `RingDetail` pages whatever the card carries and shows "Showing {n} of {total} computers." when the payload holds fewer than `hostTotal`, so nothing is hidden silently, but the operator cannot reach computers 26 onward (including a failed one that sorts after the first page only if the server's own ordering put it there; the server orders problems first, so a failed computer is in the first page). UI-SPEC section 4 asks for 25 rows then Show more computers. Needs a paged hosts route (for example `GET /api/patch-rollouts/{id}/rings/{index}/hosts?offset=&limit=`) and a call from `RingDetail`; a backend change, not part of 84-18.
