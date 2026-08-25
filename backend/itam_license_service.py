"""ITAM License service (Phase 60, ITAM-LIC-01).

Handles seat tracking, assignment, and reclamation for software licenses.
Mirroring the history and compensation patterns from itam_lifecycle_service.py.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from itam_lifecycle_service import write_history

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


async def assign_license_seat(
    db, tenant_id: str, license_id: str, target_type: str, target_id: str, note: str = None, username: str = "system"
) -> Dict[str, Any]:
    """Assigns one license seat to a user or asset.

    Validates:
    - License existence.
    - Target existence (user or asset).
    - Seat availability (current assignment count < seatCount).
    - Target not already assigned this license.
    """
    now = _now_iso()

    # 1. Resolve license and check seatCount
    license_doc = await db.licenses.find_one({"id": license_id})
    if not license_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")

    seat_count = license_doc.get("seatCount", 0)

    # 2. Resolve target
    if target_type == "user":
        target = await db.users.find_one({"id": target_id})
    elif target_type == "asset":
        target = await db.assets.find_one({"id": target_id})
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid target type: {target_type}")

    if not target:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{target_type} '{target_id}' not found.")

    # 3. Check for existing assignment for this target+license
    existing = await db.license_assignments.find_one({
        "licenseId": license_id,
        "targetType": target_type,
        "targetId": target_id
    })
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"This {target_type} already has a seat for this license.")

    assignment_id = f"la-{uuid.uuid4().hex[:8]}"
    assignment_doc = {
        "id": assignment_id,
        "tenantId": tenant_id,
        "licenseId": license_id,
        "targetType": target_type,
        "targetId": target_id,
        "assignedAt": now,
        "assignedBy": username,
        "note": note,
    }

    # 4/5. Reserve the seat optimistically, then verify (DB-F06, 2026-08-25
    # audit): the old code counted assignments *before* inserting, so two
    # concurrent requests could both pass the count check before either had
    # inserted, over-allocating seats beyond seatCount. Mongo has no
    # multi-document transaction available here (no replica set assumed),
    # but a single insert_one is atomic, so inserting first and recounting
    # afterwards means any request that pushes the total past seatCount sees
    # its own recount reflect that and can compensate by deleting what it
    # just wrote — the same insert-then-compensate idiom used below for the
    # history write. Under heavy contention this can reject more requests
    # than strictly necessary (multiple concurrent winners may all roll
    # back), but it can never allow more than seatCount seats to remain
    # assigned.
    # A unique index on (licenseId, targetType, targetId) — see database.py —
    # is the authoritative guard against the same race on step 3's existence
    # check above: two concurrent requests for the same target could both
    # see no existing assignment before either inserts. The find_one above
    # is just a fast, friendly-error fast path; this catches the case it
    # misses.
    try:
        await db.license_assignments.insert_one(assignment_doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This {target_type} already has a seat for this license."
        )
    current_seats = await db.license_assignments.count_documents({"licenseId": license_id})
    if current_seats > seat_count:
        await db.license_assignments.delete_one({"id": assignment_id})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No seats available. All {seat_count} seats are assigned."
        )

    # 6. Write history (reuse assignment_history collection but different action)
    history_record = {
        "assetId": license_id, # License acts as the "asset" for history purposes
        "action": "license_assign",
        "targetType": target_type,
        "targetId": target_id,
        "note": note,
        "actorUsername": username,
        "ts": now,
    }
    try:
        await write_history(db, tenant_id, history_record)
    except Exception as exc:
        logger.error("Failed to write history for license assignment %s: %s", license_id, exc)
        # Revert assignment
        await db.license_assignments.delete_one({"id": assignment_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Assignment failed: history could not be written, and the change has been reverted."
        )

    return assignment_doc


async def reclaim_license_seat(
    db, tenant_id: str, assignment_id: str, note: str = None, username: str = "system"
) -> None:
    """Reclaims a license seat by assignment ID."""
    assignment = await db.license_assignments.find_one({"id": assignment_id})
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    license_id = assignment["licenseId"]
    now = _now_iso()

    # 1. Delete assignment
    await db.license_assignments.delete_one({"id": assignment_id})

    # 2. Write history
    history_record = {
        "assetId": license_id,
        "action": "license_reclaim",
        "targetType": assignment["targetType"],
        "targetId": assignment["targetId"],
        "note": note,
        "actorUsername": username,
        "ts": now,
    }
    try:
        await write_history(db, tenant_id, history_record)
    except Exception as exc:
        logger.error("Failed to write history for license reclaim %s: %s", license_id, exc)
        # Compensation: restore assignment
        await db.license_assignments.insert_one(assignment)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Reclamation failed: history could not be written, and the change has been reverted."
        )


async def list_license_assignments(db, tenant_id: str, license_id: str) -> List[Dict[str, Any]]:
    """Lists all current assignments for a license."""
    cursor = db.license_assignments.find({"licenseId": license_id}, {"_id": 0})
    return await cursor.to_list(length=1000)
