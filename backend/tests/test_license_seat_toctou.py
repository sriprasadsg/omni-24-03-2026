"""Regression tests for DB-F06 (2026-08-25 audit): license seat allocation TOCTOU race.

assign_license_seat used to count existing assignments, THEN insert — two
concurrent requests could both pass the count check before either had
inserted, allocating more seats than seatCount allows. It also had a
separate race on the "target already has a seat" check (find_one then
insert, no uniqueness enforced anywhere).

The fix: insert first and recount afterwards, rolling back if the total
exceeds seatCount (insert-then-compensate, matching the history-write
rollback already used elsewhere in this file); and a unique index on
(licenseId, targetType, targetId) — asserted here via a simulated
DuplicateKeyError, since a MagicMock db can't enforce a real Mongo index —
backstops the same-target race and is caught and converted to 409.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

import itam_license_service as svc


def _mock_db(seat_count=1, post_insert_count=1):
    db = MagicMock()
    db.licenses.find_one = AsyncMock(return_value={"id": "lic-1", "seatCount": seat_count, "tenantId": "t-a"})
    db.users.find_one = AsyncMock(return_value={"id": "user-1"})
    db.license_assignments.find_one = AsyncMock(return_value=None)
    db.license_assignments.insert_one = AsyncMock()
    db.license_assignments.delete_one = AsyncMock()
    db.license_assignments.count_documents = AsyncMock(return_value=post_insert_count)
    db.assignment_history.insert_one = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_seat_granted_when_recount_within_limit():
    db = _mock_db(seat_count=2, post_insert_count=1)
    result = await svc.assign_license_seat(db, "t-a", "lic-1", "user", "user-1")
    assert result["targetId"] == "user-1"
    db.license_assignments.insert_one.assert_awaited_once()
    db.license_assignments.delete_one.assert_not_called()


@pytest.mark.asyncio
async def test_seat_rolled_back_when_recount_exceeds_seat_count():
    """Simulates losing the race: this request's insert landed, but the
    recount shows another concurrent request already filled the last seat."""
    db = _mock_db(seat_count=1, post_insert_count=2)
    with pytest.raises(HTTPException) as exc_info:
        await svc.assign_license_seat(db, "t-a", "lic-1", "user", "user-1")
    assert exc_info.value.status_code == 400
    assert "No seats available" in exc_info.value.detail
    db.license_assignments.insert_one.assert_awaited_once()
    db.license_assignments.delete_one.assert_awaited_once()
    db.assignment_history.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_target_assignment_becomes_409_not_500():
    """Simulates the unique-index backstop firing: two concurrent requests
    both passed the find_one existing-assignment check, but only one insert
    can win against the unique (licenseId, targetType, targetId) index."""
    db = _mock_db(seat_count=5, post_insert_count=1)
    db.license_assignments.insert_one = AsyncMock(side_effect=DuplicateKeyError("dup"))

    with pytest.raises(HTTPException) as exc_info:
        await svc.assign_license_seat(db, "t-a", "lic-1", "user", "user-1")
    assert exc_info.value.status_code == 409
    assert "already has a seat" in exc_info.value.detail
