import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth_types import TokenData
from authentication_service import get_current_user
from database import get_database
from itam_asset_endpoints import _require_itam_admin
from itam_models import LicenseCreate, LicenseUpdate, LicenseSeatAssignmentRequest
from itam_license_service import (
    assign_license_seat,
    reclaim_license_seat,
    list_license_assignments,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/itam/licenses", tags=["ITAM Licenses"])


def _enrich_license_seats_and_expiry(doc: Dict[str, Any], seats_assigned: int, now) -> Dict[str, Any]:
    """Computes remaining/expired-seat visibility at read time (ROADMAP Phase 60
    success criterion 1: "see remaining/expired seats") — never stored, per
    60-RESEARCH.md Pattern 4 (read-time-only, no background scheduler)."""
    seat_count = doc.get("seatCount", 0)
    doc["seatsAssigned"] = seats_assigned
    doc["seatsAvailable"] = max(seat_count - seats_assigned, 0)

    expiry_date = doc.get("expiryDate")
    if expiry_date:
        expiry_dt = datetime.fromisoformat(expiry_date.replace("Z", "+00:00"))
        if expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
        doc["daysUntilExpiry"] = (expiry_dt - now).days
        doc["isExpired"] = expiry_dt < now
    else:
        doc["daysUntilExpiry"] = None
        doc["isExpired"] = False
    return doc


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
async def create_license(
    payload: LicenseCreate,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Creates a new software license catalog entity."""
    db = get_database()

    # Validate manufacturer if supplied
    if payload.manufacturerId:
        if not await db.manufacturers.find_one({"id": payload.manufacturerId}):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"manufacturerId '{payload.manufacturerId}' not found."
            )

    import uuid
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
    license_id = f"lic-{uuid.uuid4().hex[:8]}"

    document = payload.model_dump(exclude_none=True)
    document.update({
        "id": license_id,
        "tenantId": current_user.tenant_id,
        "createdAt": now,
        "updatedAt": now,
    })

    await db.licenses.insert_one(document)
    document.pop("_id", None)
    return document


@router.get("", response_model=List[Dict[str, Any]])
async def list_licenses(
    limit: int = Query(200, ge=1, le=500),
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Lists all software licenses."""
    db = get_database()
    licenses = await db.licenses.find({}, {"_id": 0}).limit(limit).to_list(length=limit)
    now = datetime.now(timezone.utc)
    for lic in licenses:
        seats_assigned = await db.license_assignments.count_documents({"licenseId": lic["id"]})
        _enrich_license_seats_and_expiry(lic, seats_assigned, now)
    return licenses


@router.get("/{license_id}", response_model=Dict[str, Any])
async def get_license(
    license_id: str,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Retrieves a specific license by ID."""
    db = get_database()
    license_doc = await db.licenses.find_one({"id": license_id}, {"_id": 0})
    if not license_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    seats_assigned = await db.license_assignments.count_documents({"licenseId": license_id})
    return _enrich_license_seats_and_expiry(license_doc, seats_assigned, datetime.now(timezone.utc))


@router.patch("/{license_id}", response_model=Dict[str, Any])
async def update_license(
    license_id: str,
    payload: LicenseUpdate,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Partially updates a software license."""
    db = get_database()

    update_data = payload.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    from datetime import datetime, timezone
    update_data["updatedAt"] = datetime.now(timezone.utc).isoformat(timespec='milliseconds')

    from pymongo import ReturnDocument
    result = await db.licenses.find_one_and_update(
        {"id": license_id},
        {"$set": update_data},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0}
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    return result


@router.post("/{license_id}/assign", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
async def assign_license(
    license_id: str,
    payload: LicenseSeatAssignmentRequest,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Assigns a license seat to a user or asset."""
    db = get_database()
    tenant_id = current_user.tenant_id

    return await assign_license_seat(
        db, tenant_id, license_id, payload.targetType, payload.targetId, payload.note, current_user.username
    )


@router.get("/{license_id}/assignments", response_model=List[Dict[str, Any]])
async def list_assignments(
    license_id: str,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Lists current assignments for a license."""
    db = get_database()
    tenant_id = current_user.tenant_id

    # Check license existence first
    if not await db.licenses.find_one({"id": license_id}):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")

    return await list_license_assignments(db, tenant_id, license_id)


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def reclaim_license(
    assignment_id: str,
    note: str = Query(None),
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Reclaims a license seat (deletes assignment)."""
    db = get_database()
    tenant_id = current_user.tenant_id

    await reclaim_license_seat(db, tenant_id, assignment_id, note, current_user.username)
