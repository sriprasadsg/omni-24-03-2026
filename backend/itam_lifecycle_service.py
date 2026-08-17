"""Append-only assignment-history module (Phase 57, ITAM-LIFE-04).

Only `write_history` (insert) and `list_history` (read) are exposed — this is the
entire public surface of this module. There is no update/delete/edit/purge/correction
function anywhere in it, so a written assignment-history record can never be altered
or removed by anything that imports this module. A correction is always a new
appended entry, never a rewrite of an existing one — that absence is the append-only
guarantee behind this plan's first authored prohibition (assignment history must
never gain an alter/remove path, including a TTL index).

Modelled 1:1 on remediation_audit_service.py, minus its OCSF push side-effect.

`_revert_on_history_failure` below is unrelated to that guarantee — it compensates
`assets` (not `assignment_history`) when a write_history call fails after the asset
mutation already committed (WR-01). It is private (leading underscore) and imported
by name from itam_lifecycle_endpoints.py, kept here only to keep that file under the
CLAUDE.md 500-line cap.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


async def write_history(db, tenant_id: str, record: Dict[str, Any]) -> str:
    """Inserts one immutable assignment-history record.

    Copies `record`, sets a freshly generated `id`, `setdefault`s `tenantId` to the
    passed tenant and `ts` to the current UTC ISO timestamp (a caller-supplied `ts`
    is preserved, never overwritten), inserts into `db.assignment_history`, and
    returns the generated `id`.
    """
    doc = dict(record)
    doc["id"] = f"ah-{uuid.uuid4().hex[:8]}"
    doc.setdefault("tenantId", tenant_id)
    doc.setdefault("ts", _now_iso())
    await db.assignment_history.insert_one(doc)
    return doc["id"]


async def list_history(
    db, tenant_id: str, asset_id: str, limit: int = 100
) -> List[Dict[str, Any]]:
    """Returns one asset's assignment-history entries, newest first.

    Sort is `ts` descending with `_id` descending as the tiebreak, so entries
    sharing an identical `ts` still come back in a stable, repeatable order. This
    function is deliberately per-asset by construction — no arbitrary-filter
    variant exists here.
    """
    cursor = (
        db.assignment_history.find({"tenantId": tenant_id, "assetId": asset_id}, {"_id": 0})
        .sort([("ts", -1), ("_id", -1)])
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


def _apply_known_delta(pre_image: Dict[str, Any], set_doc: Dict[str, Any], unset_keys) -> Dict[str, Any]:
    """Reconstructs an after-mutation document from a pre-image plus the exact
    $set/$unset a caller just issued (WR-01's BEFORE-not-AFTER pattern) — used
    by every checkout/checkin/audit route so find_one_and_update need only be
    called once per request, preserving the no-extra-read-on-success invariant."""
    doc = {**pre_image, **set_doc}
    for key in unset_keys:
        doc.pop(key, None)
    return doc


async def _revert_on_history_failure(
    db,
    asset_id: str,
    pre_image: Dict[str, Any],
    touched_keys: list,
    action: str,
    exc: Exception,
) -> None:
    """Compensate for an `assets` mutation that already committed when the
    follow-up `write_history` call then fails (WR-01). Without this, a caller
    sees a 500 while the asset is left in the new (mutated) state with no
    corresponding history entry, and a retry would then hit a stale 409
    instead of succeeding.

    `pre_image` is the asset document as it was immediately before the
    guarded mutation ran (used only to reconstruct prior field values for
    this compensating write, never to make the original accept/reject
    decision). `touched_keys` lists every key the mutation may have set or
    unset; each key reverts to its pre-image value, or is unset if it was
    absent from pre_image.
    """
    revert_set: Dict[str, Any] = {}
    revert_unset: Dict[str, Any] = {}
    for key in touched_keys:
        if pre_image is not None and key in pre_image:
            revert_set[key] = pre_image[key]
        else:
            revert_unset[key] = ""

    revert_update: Dict[str, Any] = {}
    if revert_set:
        revert_update["$set"] = revert_set
    if revert_unset:
        revert_update["$unset"] = revert_unset

    if not revert_update:
        return

    try:
        await db.assets.find_one_and_update({"id": asset_id}, revert_update)
    except Exception as revert_exc:
        # Best-effort: the original error is already surfaced as a 500 to the
        # caller. If the compensating write also fails, log loudly — this is
        # the one case where the asset and its history trail can genuinely
        # drift, and it needs a human to reconcile.
        logger.error(
            "Failed to revert asset %s after %s history write failure "
            "(original error: %s); asset state may now be inconsistent with "
            "its history trail: %s",
            asset_id, action, exc, revert_exc,
        )
