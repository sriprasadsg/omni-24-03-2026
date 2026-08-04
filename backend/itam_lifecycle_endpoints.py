"""ITAM Lifecycle endpoints (Phase 57) — check-out, check-in, physical audit, and the
assignment-history read route for IT assets. Mounted at /api/assets alongside
itam_asset_endpoints.py's router (Phase 56); every route here is multi-segment
(`/{asset_id}/checkout`, `/{asset_id}/history`, ...) so none can be shadowed by
asset_endpoints.py's single-segment `GET /{asset_id}` under any registration order.

This module reuses `_require_itam_admin` from itam_asset_endpoints.py rather than
redefining the manage:assets RBAC gate.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo import ReturnDocument

from auth_types import TokenData
from database import get_database
from cache_service import invalidate_cache
from itam_asset_endpoints import _require_itam_admin
from itam_models import AuditMarkRequest, CheckinRequest, CheckoutRequest, LifecycleStatus
from itam_lifecycle_service import list_history, write_history

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assets", tags=["ITAM Lifecycle"])

# Action constants (57-01 consumes ACTION_CHECKOUT; 57-02/57-03 consume the rest).
ACTION_CHECKOUT = "checkout"
ACTION_CHECKIN = "checkin"
ACTION_AUDIT = "audit"
AUDIT_INTERVAL_DAYS = 365  # D-03: fixed 12-month physical-audit interval (57-03).


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _audit_cutoff_iso() -> str:
    """AUDIT_INTERVAL_DAYS ago, formatted like every other timestamp this phase
    writes (`+00:00` offset, millisecond precision) so lexicographic string
    comparison against `lastAuditedAt`/`createdAt` is chronologically valid."""
    delta = timedelta(days=AUDIT_INTERVAL_DAYS)
    return (datetime.now(timezone.utc) - delta).isoformat(timespec="milliseconds")


def _deployable_guard() -> Dict[str, Any]:
    """Filter fragment matching an asset whose lifecycleStatus is deployable, or whose
    lifecycleStatus key is absent entirely. The absent case is not optional: every
    pre-existing agent-discovered asset lacks the key, and asset_endpoints.py already
    treats its absence as deployable at read time — this guard must match that.
    """
    return {
        "$or": [
            {"lifecycleStatus": LifecycleStatus.DEPLOYABLE.value},
            {"lifecycleStatus": {"$exists": False}},
        ]
    }


def _deployed_guard() -> Dict[str, Any]:
    """Filter fragment matching an asset whose lifecycleStatus is exactly deployed.

    Unlike `_deployable_guard()`, this does NOT admit a missing `lifecycleStatus`
    key: an asset with no key has never been checked out through this API, so
    checking it in would be a no-op that nevertheless flipped a possibly-`retired`
    (or otherwise non-deployed) record into stock and wrote a misleading history
    entry (T-57-12).
    """
    return {"lifecycleStatus": LifecycleStatus.DEPLOYED.value}


async def _resolve_target(db, target_type: str, target_id: str) -> None:
    """Resolve a checkout target against the caller's tenant. Raises 400 when the id
    does not resolve to a user or a location in the caller's tenant. Called strictly
    before the guarded update so an unresolvable target never mutates the asset.
    """
    if target_type == "user":
        target = await db.users.find_one({"id": target_id})
    elif target_type == "location":
        target = await db.locations.find_one({"id": target_id})
    else:  # pragma: no cover — CheckoutRequest's Literal already excludes this
        target = None
    if not target:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{target_type} '{target_id}' not found.",
        )


@router.post("/{asset_id}/checkout", response_model=Dict[str, Any])
async def checkout_asset(
    asset_id: str,
    payload: CheckoutRequest,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Check a deployable asset out to a platform user or a location (ITAM-LIFE-02).

    Refused with 409 for an asset not in a deployable-typed status, 404 for an
    unknown or cross-tenant asset id, and 400 for an unresolvable target. Every
    successful check-out writes exactly one immutable assignment_history entry.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant ID not found for the current user.",
        )

    db = get_database()

    # Target resolution happens strictly before the guarded update so an
    # unresolvable target never mutates the asset.
    await _resolve_target(db, payload.targetType, payload.targetId)

    now = _now_iso()
    set_doc: Dict[str, Any] = {
        "lifecycleStatus": LifecycleStatus.DEPLOYED.value,
        "assignedToType": payload.targetType,
        "assignedToId": payload.targetId,
        "checkedOutAt": now,
        "checkedOutBy": current_user.username,
        "updatedAt": now,
    }
    if payload.targetType == "location":
        # D-02: locationId means where the asset currently is, not where it was
        # catalogued — a location check-out overwrites it. The prior value survives
        # only in assignment_history. Left untouched for a user target.
        set_doc["locationId"] = payload.targetId

    update: Dict[str, Any] = {"$set": set_doc}
    if payload.expectedReturnDate:
        set_doc["expectedReturnDate"] = payload.expectedReturnDate
    else:
        # A value from an earlier check-out can never survive into a new one.
        update["$unset"] = {"expectedReturnDate": ""}

    # The deployable guard belongs inside the find_one_and_update filter itself,
    # never in a preceding conditional read — two concurrent requests would
    # otherwise both observe a deployable asset and both write. tenantId is never
    # added by hand; the TenantIsolatedCollection wrapper injects it.
    filt: Dict[str, Any] = {"id": asset_id, **_deployable_guard()}

    updated = await db.assets.find_one_and_update(
        filt, update, return_document=ReturnDocument.AFTER
    )

    if not updated:
        # The atomic operation above has already decided the outcome; this
        # follow-up read is purely to disambiguate the failure reason and does
        # not reintroduce a race. Never write a history entry on a refused checkout.
        existing = await db.assets.find_one({"id": asset_id})
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset is not in a deployable status.",
        )

    history_record: Dict[str, Any] = {
        "assetId": asset_id,
        "action": ACTION_CHECKOUT,
        "targetType": payload.targetType,
        "targetId": payload.targetId,
        "note": payload.note,
        "expectedReturnDate": payload.expectedReturnDate,
        "actorUsername": current_user.username,
        "ts": now,
    }
    try:
        history_id = await write_history(db, tenant_id, history_record)
    except Exception as exc:
        # A check-out that returns success while its trail write failed is exactly
        # the invisible hole this plan's second authored prohibition forbids.
        logger.error(
            "Failed to write assignment_history entry for asset %s: %s", asset_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Check-out succeeded but its history entry failed to write.",
        )

    # Synchronous helper — never awaited (cache_service.invalidate_cache is a
    # plain `def` returning None).
    invalidate_cache("assets:*")

    updated.pop("_id", None)
    response_history = {**history_record, "id": history_id}
    return {**updated, "history": response_history}


@router.post("/{asset_id}/checkin", response_model=Dict[str, Any])
async def checkin_asset(
    asset_id: str,
    payload: CheckinRequest,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Check a deployed asset back in, returning it to stock and clearing its
    assignment (ITAM-LIFE-03).

    Refused with 409 for an asset that is not currently checked out (deployed),
    404 for an unknown or cross-tenant asset id. Every successful check-in writes
    exactly one immutable assignment_history entry.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant ID not found for the current user.",
        )

    db = get_database()

    now = _now_iso()
    set_doc: Dict[str, Any] = {
        "lifecycleStatus": LifecycleStatus.DEPLOYABLE.value,
        "checkedInAt": now,
        "checkedInBy": current_user.username,
        "updatedAt": now,
    }
    # locationId is deliberately absent from both $set and $unset below: D-02
    # defines it as the asset's current physical location, not its assignment, so
    # returning it to stock must never erase where the asset actually is. Do not
    # "fix" this by adding it to $unset.
    unset_doc: Dict[str, Any] = {
        "assignedToType": "",
        "assignedToId": "",
        "checkedOutAt": "",
        "checkedOutBy": "",
        "expectedReturnDate": "",
    }
    update: Dict[str, Any] = {"$set": set_doc, "$unset": unset_doc}

    # The deployed guard lives inside the find_one_and_update filter itself,
    # never in a preceding conditional read — same atomicity reasoning as
    # checkout's guard. tenantId is never added by hand; the TenantIsolatedDatabase
    # wrapper injects it.
    filt: Dict[str, Any] = {"id": asset_id, **_deployed_guard()}

    updated = await db.assets.find_one_and_update(
        filt, update, return_document=ReturnDocument.AFTER
    )

    if not updated:
        # The atomic operation above has already decided the outcome; this
        # follow-up read is purely to disambiguate the failure reason and does
        # not reintroduce a race. Never write a history entry on a refused checkin.
        existing = await db.assets.find_one({"id": asset_id})
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset is not currently checked out.",
        )

    # A check-in has no target — the target fields are simply absent.
    history_record: Dict[str, Any] = {
        "assetId": asset_id,
        "action": ACTION_CHECKIN,
        "note": payload.note,
        "actorUsername": current_user.username,
        "ts": now,
    }
    try:
        history_id = await write_history(db, tenant_id, history_record)
    except Exception as exc:
        # A check-in that reports success without a trail entry is the same
        # invisible hole as an untracked check-out.
        logger.error(
            "Failed to write assignment_history entry for asset %s: %s", asset_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Check-in succeeded but its history entry failed to write.",
        )

    # Synchronous helper — never awaited (cache_service.invalidate_cache is a
    # plain `def` returning None).
    invalidate_cache("assets:*")

    updated.pop("_id", None)
    response_history = {**history_record, "id": history_id}
    return {**updated, "history": response_history}


@router.get("/{asset_id}/history", response_model=Dict[str, Any])
async def list_assignment_history(
    asset_id: str,
    limit: int = Query(100, ge=1, le=500),
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Read one asset's full assignment-history trail, newest first (ITAM-LIFE-04).

    The asset lookup below is this route's tenant-isolation boundary: because the
    `assets` collection is auto-tenant-scoped, an asset id belonging to another
    tenant resolves to nothing here and produces exactly the same 404 as a
    genuinely unknown id, so the response never discloses that the id exists
    elsewhere. History is only read once the asset resolves, so a cross-tenant
    lookup reads zero assignment_history rows.

    An asset that resolves but has no entries returns 200 with an empty list —
    never 404, never a null body — because "this asset has never been handed
    off" is a real and useful answer, distinct from "this asset does not exist".

    No route on this router alters or removes a history entry, under any method
    or name — a correction is always a new appended entry, never a rewrite.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant ID not found for the current user.",
        )

    db = get_database()

    asset = await db.assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    # Delegates the read to list_history rather than querying the collection
    # inline — list_history owns the ts-descending/_id-descending sort and the
    # {"_id": 0} projection.
    entries = await list_history(db, tenant_id, asset_id, limit)
    return {"assetId": asset_id, "entries": entries}


@router.post("/{asset_id}/audit", response_model=Dict[str, Any])
async def mark_asset_audited(
    asset_id: str,
    payload: AuditMarkRequest,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Mark an asset as physically audited on a given date (ITAM-LIFE-05).

    No lifecycle guard on this filter: an audit is meaningful in every status
    including `deployed`/`broken`/`retired`, so `None` means only that the
    asset does not resolve in the caller's tenant — 404 directly, no
    404-vs-409 disambiguation needed.

    The `$set` document carries exactly four keys and no `$unset`: an audit
    changes what is known, never availability or assignment. `lastAuditRecordedAt`
    is always the server clock, even with a caller-supplied `auditedAt` — a
    backdated assertion stays visible as an assertion (the attribution
    prohibition).
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant ID not found for the current user.",
        )

    db = get_database()

    now = _now_iso()
    audited_at = payload.auditedAt if payload.auditedAt else now
    set_doc: Dict[str, Any] = {
        "lastAuditedAt": audited_at,
        "lastAuditedBy": current_user.username,
        "lastAuditRecordedAt": now,
        "updatedAt": now,
    }

    updated = await db.assets.find_one_and_update(
        {"id": asset_id}, {"$set": set_doc}, return_document=ReturnDocument.AFTER
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    history_record: Dict[str, Any] = {
        "assetId": asset_id,
        "action": ACTION_AUDIT,
        "auditedAt": audited_at,
        "note": payload.note,
        "actorUsername": current_user.username,
        "ts": now,
    }
    try:
        history_id = await write_history(db, tenant_id, history_record)
    except Exception as exc:
        # Success without a trail entry would be the same invisible hole as
        # an untracked check-out.
        logger.error("Failed to write assignment_history entry for asset %s: %s", asset_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Audit mark succeeded but its history entry failed to write.",
        )

    # Synchronous helper — never awaited (cache_service.invalidate_cache is a
    # plain `def` returning None).
    invalidate_cache("assets:*")

    updated.pop("_id", None)
    response_history = {**history_record, "id": history_id}
    return {**updated, "history": response_history}


def _overdue_query(cutoff: str) -> Dict[str, Any]:
    """The three-branch `$or` population, stated explicitly. Branch three is not
    optional: every agent-discovered asset lands there, since the registration
    upsert writes `lastScanned` (refreshed each heartbeat — recency, not age)
    and never `createdAt`. Omitting it would quietly report a fleet as audited
    when most has never been physically verified."""
    return {
        "$or": [
            {"lastAuditedAt": {"$lt": cutoff}},
            {"lastAuditedAt": {"$exists": False}, "createdAt": {"$lt": cutoff}},
            {"lastAuditedAt": {"$exists": False}, "createdAt": {"$exists": False}},
        ]
    }


def _overdue_row(doc: Dict[str, Any], cutoff: str, now: datetime) -> Dict[str, Any]:
    """Shape one report row: `ageBasis` names the date the age was computed
    from, `neverAudited` is true whenever no audited date is present, and
    `daysOverdue` is null — never zero, never a guess — when the basis is
    unknown."""
    row = dict(doc)
    last_audited = row.get("lastAuditedAt")
    created_at = row.get("createdAt")

    if last_audited:
        age_basis = "lastAuditedAt"
        basis_date = last_audited
    elif created_at:
        age_basis = "createdAt"
        basis_date = created_at
    else:
        age_basis = "unknown"
        basis_date = None

    days_overdue = None
    if basis_date:
        try:
            basis_dt = datetime.fromisoformat(basis_date.replace("Z", "+00:00"))
            if basis_dt.tzinfo is None:
                basis_dt = basis_dt.replace(tzinfo=timezone.utc)
            days_overdue = (now - basis_dt).days - AUDIT_INTERVAL_DAYS
        except ValueError:
            days_overdue = None

    row["ageBasis"] = age_basis
    row["neverAudited"] = not bool(last_audited)
    row["daysOverdue"] = days_overdue
    return row


@router.get("/reports/overdue-audit", response_model=Dict[str, Any])
async def overdue_audit_report(
    limit: int = Query(200, ge=1, le=1000),
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Report every asset overdue for physical audit (ITAM-LIFE-05), computed at
    request time against the fixed `AUDIT_INTERVAL_DAYS` interval — deliberately
    not a background sweep (D-03; top recorded milestone risk). The literal
    `/reports/overdue-audit` path is not cosmetic: `asset_endpoints.py` declares
    `GET /{asset_id}` on a router sharing this prefix, so a single-segment path
    would resolve only by registration luck (PD-02).
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant ID not found for the current user.",
        )

    db = get_database()

    cutoff = _audit_cutoff_iso()
    now = datetime.now(timezone.utc)
    query = _overdue_query(cutoff)
    projection = {
        "_id": 0,
        "id": 1,
        "name": 1,
        "assetTag": 1,
        "lifecycleStatus": 1,
        "locationId": 1,
        "assignedToType": 1,
        "assignedToId": 1,
        "lastAuditedAt": 1,
        "lastAuditedBy": 1,
        "createdAt": 1,
    }

    cursor = db.assets.find(query, projection).limit(limit)
    docs = await cursor.to_list(length=limit)

    rows = [_overdue_row(doc, cutoff, now) for doc in docs]
    # Oldest-basis-first where a basis exists; unknown-basis rows last.
    rows.sort(key=lambda r: (r["ageBasis"] == "unknown", r.get("lastAuditedAt") or r.get("createdAt") or ""))

    return {
        "intervalDays": AUDIT_INTERVAL_DAYS,
        "cutoff": cutoff,
        "count": len(rows),
        "rows": rows,
    }
