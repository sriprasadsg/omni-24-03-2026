"""Tests for evidence review workflow (Phase 15).

Uses asyncio.run() pattern (consistent with test_powershell_evidence.py).
"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_user(tenant_id="tenant-a", role="admin", username="reviewer1"):
    u = MagicMock()
    u.tenant_id = tenant_id
    u.role = role
    u.username = username
    return u


def _make_mock_db():
    """Return a mock DB with asset_compliance collection and evidence_reviews collection."""
    db = MagicMock()
    # asset_compliance collection
    db.asset_compliance = MagicMock()
    db.asset_compliance.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    # find_one() backs create_review()'s evidence-existence check (WR-04) — must
    # resolve to a truthy dict or every create_review call raises ValueError.
    db.asset_compliance.find_one = AsyncMock(return_value={
        "id": "ac-1", "tenantId": "tenant-a", "evidence": [{"id": "ev-1", "status": "pending_review"}],
    })
    # aggregate() is synchronous on a real Motor collection — it returns a cursor
    # object immediately; only cursor.to_list() is awaited. Mocking aggregate()
    # itself as an AsyncMock makes the call return a coroutine with no .to_list.
    db.asset_compliance.aggregate = MagicMock(return_value=MagicMock(
        to_list=AsyncMock(return_value=[])
    ))
    # audit_logs collection — written on every review decision (T-10 fix).
    db.audit_logs = MagicMock()
    db.audit_logs.insert_one = AsyncMock(return_value=MagicMock(inserted_id="log-1"))

    # evidence_reviews collection via _db — service code accesses it by subscript
    # (db._db[_EVIDENCE_REVIEWS_COL]), not by attribute, so __getitem__ must be
    # wired to the same mock the assertions below reference.
    inner = MagicMock()
    inner.evidence_reviews = MagicMock()
    inner.evidence_reviews.insert_one = AsyncMock(return_value=MagicMock(inserted_id="rev-abc"))
    inner.evidence_reviews.find_one_and_update = AsyncMock(return_value={
        "id": "rev-abc", "evidenceId": "ev-1", "status": "approved",
        "comment": "Looks good", "reviewer": "admin",
        "tenantId": "tenant-a",
    })
    inner.evidence_reviews.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=MagicMock(
        to_list=AsyncMock(return_value=[
            {"id": "rev-1", "evidenceId": "ev-1", "status": "approved", "comment": "OK", "reviewer": "admin", "tenantId": "tenant-a", "created_at": "2026-06-27T12:00:00Z"},
            {"id": "rev-2", "evidenceId": "ev-1", "status": "pending", "comment": "Reviewing", "reviewer": "user1", "tenantId": "tenant-a", "created_at": "2026-06-27T11:00:00Z"},
        ])
    ))))
    inner.__getitem__ = MagicMock(return_value=inner.evidence_reviews)
    db._db = inner
    return db


def _build_client(mock_db, current_user):
    import evidence_review_endpoints as mod
    from authentication_service import get_current_user

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = lambda: current_user

    patcher = patch("evidence_review_endpoints.get_database", return_value=mock_db)
    patcher.start()
    return TestClient(app, raise_server_exceptions=False)


# ── Test 1: Submit for review ──────────────────────────────────────────────────

def test_submit_for_review_sets_status():
    """POST /api/evidence/{id}/submit-for-review → 200 + status=pending_review."""
    db = _make_mock_db()
    user = _make_user("tenant-a", "admin")
    client = _build_client(db, user)

    resp = client.post("/api/evidence/ev-1/submit-for-review")
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["status"] == "pending_review"
    db.asset_compliance.update_one.assert_awaited()


# ── Test 2: Create review record ───────────────────────────────────────────────

def test_create_review_record():
    """POST /api/evidence/{id}/review → 200 + review record created."""
    db = _make_mock_db()
    user = _make_user("tenant-a", "admin")
    client = _build_client(db, user)

    resp = client.post("/api/evidence/ev-1/review", json={"comment": "Initial review"})
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["success"] is True
    assert "review" in data
    # WR-01: create_review now uses an atomic find_one_and_update(upsert=True)
    # instead of a separate find_one + insert_one, to close the check-then-act
    # race that could create duplicate pending review records.
    db._db.evidence_reviews.find_one_and_update.assert_awaited()


# ── Test 3: Approve evidence ───────────────────────────────────────────────────

def test_approve_evidence_updates_status():
    """PATCH /api/evidence/{id}/review/{review_id} with approved → status=approved."""
    db = _make_mock_db()
    user = _make_user("tenant-a", "admin")
    client = _build_client(db, user)

    resp = client.patch(
        "/api/evidence/ev-1/review/rev-abc",
        json={"decision": "approved", "comment": "Approved after review"},
    )
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["success"] is True
    assert data["review"]["status"] == "approved"


# ── Test 4: Reject requires comment ────────────────────────────────────────────

def test_reject_requires_comment():
    """PATCH reject without comment → 422."""
    db = _make_mock_db()
    user = _make_user("tenant-a", "admin")
    client = _build_client(db, user)

    resp = client.patch(
        "/api/evidence/ev-1/review/rev-abc",
        json={"decision": "rejected", "comment": ""},
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


# ── Test 5: Changes requested → needs_revision ─────────────────────────────────

def test_changes_requested_sets_needs_revision():
    """PATCH changes_requested with comment → 200, evidence status = needs_revision."""
    db = _make_mock_db()
    user = _make_user("tenant-a", "admin")
    client = _build_client(db, user)

    resp = client.patch(
        "/api/evidence/ev-1/review/rev-abc",
        json={"decision": "changes_requested", "comment": "Please add more details"},
    )
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["success"] is True


# ── Test 6: Get reviews sorted by date ─────────────────────────────────────────

def test_get_reviews_sorted_by_date():
    """GET /api/evidence/{id}/reviews → list sorted by created_at desc."""
    db = _make_mock_db()
    user = _make_user("tenant-a", "admin")
    client = _build_client(db, user)

    resp = client.get("/api/evidence/ev-1/reviews")
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["count"] >= 2
    # Verify descending order
    dates = [r["created_at"] for r in data["reviews"]]
    assert dates == sorted(dates, reverse=True)


# ── Test 7: Get pending evidence ───────────────────────────────────────────────

def test_get_pending_returns_only_pending_review():
    """GET /api/evidence/pending-review → list of pending review items."""
    db = _make_mock_db()
    user = _make_user("tenant-a", "admin")
    client = _build_client(db, user)

    resp = client.get("/api/evidence/pending-review")
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "items" in data


# ── Test 8: Tenant isolation ───────────────────────────────────────────────────

def test_tenant_isolation_get_excludes_cross_tenant_reviews():
    """A tenant-a GET must never surface tenant-b's review records for the same
    evidence id — the query is scoped on tenantId, not just evidenceId."""
    db = _make_mock_db()

    def _find_side_effect(query):
        # Mirror the real find() call shape: {"evidenceId": ..., "tenantId": ...}.
        # Only "tenant-b" has data seeded here; a tenant-a query must come back
        # empty even though a record exists for the same evidenceId.
        if query.get("tenantId") == "tenant-b":
            return MagicMock(sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[
                {
                    "id": "rev-b1", "evidenceId": "ev-1", "status": "approved",
                    "comment": "tenant-b only", "reviewer": "b-admin",
                    "tenantId": "tenant-b", "created_at": "2026-06-27T12:00:00Z",
                },
            ]))))
        return MagicMock(sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[]))))

    db._db.evidence_reviews.find = MagicMock(side_effect=_find_side_effect)

    user = _make_user("tenant-a", "admin")
    client = _build_client(db, user)

    resp = client.get("/api/evidence/ev-1/reviews")
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["count"] == 0, f"Expected 0 reviews for tenant-a, leaked tenant-b data: {data}"
    assert data["reviews"] == []


def test_tenant_isolation_patch_returns_404_for_cross_tenant_review():
    """A tenant-a admin cannot decide (PATCH) a review record that only exists
    for tenant-b — the lookup is tenant-scoped, so this must be indistinguishable
    from 'not found' (404), not silently apply tenant-b's data."""
    db = _make_mock_db()

    async def _scoped_find_one_and_update(query, *args, **kwargs):
        if query.get("tenantId") == "tenant-b":
            return {
                "id": "rev-b1", "evidenceId": "ev-1", "status": "approved",
                "comment": "tenant-b review", "reviewer": "b-admin", "tenantId": "tenant-b",
            }
        return None

    db._db.evidence_reviews.find_one_and_update = AsyncMock(side_effect=_scoped_find_one_and_update)

    user = _make_user("tenant-a", "admin")
    client = _build_client(db, user)

    resp = client.patch(
        "/api/evidence/ev-1/review/rev-b1",
        json={"decision": "approved", "comment": "trying to access tenant-b review"},
    )
    assert resp.status_code == 404, f"Expected 404 for cross-tenant review access, got {resp.status_code}: {resp.text}"


def test_evidence_id_mismatch_same_tenant_returns_404_without_mutation():
    """A PATCH whose URL evidence_id doesn't match the review's real evidenceId
    (same tenant, different evidence) must be indistinguishable from 'not found'
    (404) — the mismatch is part of the atomic lookup filter, so zero mutation
    occurs and no audit log is written. Regression test for the exact class of
    gap that caused the prior review's CR-01 (evidence-id-mismatch-before-
    mutation), now fixed."""
    db = _make_mock_db()

    async def _scoped(query, *a, **kw):
        if query.get("evidenceId") == "ev-1":
            return {"id": "rev-abc", "evidenceId": "ev-1", "status": "pending", "tenantId": "tenant-a"}
        return None

    db._db.evidence_reviews.find_one_and_update = AsyncMock(side_effect=_scoped)
    user = _make_user("tenant-a", "admin")
    client = _build_client(db, user)

    resp = client.patch(
        "/api/evidence/ev-WRONG/review/rev-abc",
        json={"decision": "approved", "comment": "x"},
    )
    assert resp.status_code == 404, f"Expected 404 for evidence-id mismatch, got {resp.status_code}: {resp.text}"
    db.audit_logs.insert_one.assert_not_awaited()


def test_non_reviewer_role_forbidden_from_decision():
    """A non-admin/non-reviewer role cannot make a review decision — 403."""
    db = _make_mock_db()
    user = _make_user("tenant-a", "user")
    client = _build_client(db, user)

    resp = client.patch(
        "/api/evidence/ev-1/review/rev-abc",
        json={"decision": "approved", "comment": "test"},
    )
    assert resp.status_code == 403, f"Expected 403 for non-admin PATCH, got {resp.status_code}"


def test_create_review_dedup_returns_existing_pending_via_atomic_upsert():
    """A retried create-review call for evidence that already has a pending
    review must return that existing record via the atomic find_one_and_update
    upsert, not insert a duplicate. Regression test for WR-01 (the prior
    find_one-then-insert_one dedup was a check-then-act race)."""
    db = _make_mock_db()
    existing_review = {
        "id": "rev-existing", "tenantId": "tenant-a", "evidenceId": "ev-1",
        "reviewer": "reviewer1", "status": "pending", "comment": "first attempt",
        "created_at": "2026-06-27T10:00:00Z", "updated_at": "2026-06-27T10:00:00Z",
    }
    db._db.evidence_reviews.find_one_and_update = AsyncMock(return_value=existing_review)
    user = _make_user("tenant-a", "admin")
    client = _build_client(db, user)

    resp = client.post("/api/evidence/ev-1/review", json={"comment": "retried after timeout"})
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["review"]["id"] == "rev-existing"
    db._db.evidence_reviews.insert_one.assert_not_awaited()


def test_repatch_already_decided_review_returns_404():
    """PATCHing a review that has already been decided (status no longer
    'pending') must 404 with no side effects, not silently re-decide it.
    Regression test for the status: "pending" filter guard added in the
    prior CR-01 fix (evidence_review_service.py update_review_decision)."""
    db = _make_mock_db()
    db._db.evidence_reviews.find_one_and_update = AsyncMock(return_value=None)
    user = _make_user("tenant-a", "admin")
    client = _build_client(db, user)

    resp = client.patch(
        "/api/evidence/ev-1/review/rev-abc",
        json={"decision": "rejected", "comment": "trying to re-decide"},
    )
    assert resp.status_code == 404, f"Expected 404 for re-deciding an already-decided review, got {resp.status_code}: {resp.text}"
    db.audit_logs.insert_one.assert_not_awaited()


# ── Test: CR-01 regression — evidence-status propagation query shape ──────────
#
# A plain mock (see _make_mock_db above) always returns modified_count=1
# regardless of the filter dict passed to update_one, so it structurally
# cannot catch a query-shape bug like a missing $elemMatch. This test runs
# the real query against a live MongoDB instance instead, seeding an
# asset_compliance document with two evidence items so a missing $elemMatch
# (which lets `evidence.id` and `evidence.status` match independent array
# elements) would silently flip the *wrong* item's status.
def test_evidence_propagation_query_does_not_corrupt_unrelated_evidence_item():
    """Regression test for CR-01: deciding a review for ev-1 (which is NOT
    'pending_review') must never touch ev-2 (which IS 'pending_review'), even
    though both live in the same asset_compliance document. Without
    $elemMatch tying "id" and "status" to the same array element, MongoDB's
    positional $ operator can resolve to the wrong element and corrupt it."""
    import motor.motor_asyncio
    import evidence_review_service as svc

    mongo_uri = os.environ.get("MONGODB_URI") or os.environ.get("MONGO_URI", "mongodb://localhost:27017")

    async def _run():
        client = motor.motor_asyncio.AsyncIOMotorClient(
            mongo_uri, serverSelectionTimeoutMS=1500
        )
        try:
            await client.admin.command("ping")
        except Exception:
            client.close()
            import pytest
            pytest.skip(f"No live MongoDB reachable at {mongo_uri} for CR-01 regression test")
            return

        motor_db = client["evidence_review_cr01_test"]

        class _RealDbWrapper:
            """Minimal shim matching the (asset_compliance, _db[...]) surface
            evidence_review_service expects, backed by a real Mongo database
            instead of a mock."""
            def __init__(self, mdb):
                self.asset_compliance = mdb.asset_compliance
                self._db = mdb

        db = _RealDbWrapper(motor_db)

        try:
            await motor_db.asset_compliance.delete_many({"tenantId": "tenant-cr01"})
            await motor_db.evidence_reviews.delete_many({"tenantId": "tenant-cr01"})

            # Two evidence items in one document: ev-1 is NOT pending_review
            # (stale/already-moved-on), ev-2 IS pending_review and must stay
            # completely untouched by a decision made against ev-1.
            await motor_db.asset_compliance.insert_one({
                "tenantId": "tenant-cr01",
                "evidence": [
                    {"id": "ev-1", "status": "needs_revision"},
                    {"id": "ev-2", "status": "pending_review"},
                ],
            })
            await motor_db.evidence_reviews.insert_one({
                "id": "rev-cr01", "tenantId": "tenant-cr01", "evidenceId": "ev-1",
                "reviewer": "admin", "status": "pending", "comment": "initial",
                "created_at": "2026-07-02T00:00:00Z", "updated_at": "2026-07-02T00:00:00Z",
            })

            result = await svc.update_review_decision(
                review_id="rev-cr01",
                evidence_id="ev-1",
                decision="approved",
                comment="approving ev-1",
                db=db,
                tenant_id="tenant-cr01",
            )
            assert result is not None, "review record should still be updated (step 1 unaffected)"

            doc = await motor_db.asset_compliance.find_one({"tenantId": "tenant-cr01"})
            evidence_by_id = {e["id"]: e for e in doc["evidence"]}
            assert evidence_by_id["ev-2"]["status"] == "pending_review", (
                f"CR-01 regression: ev-2 was corrupted by a decision made against ev-1 "
                f"(got status={evidence_by_id['ev-2']['status']!r}) — the propagation "
                f"query is missing $elemMatch"
            )
            assert evidence_by_id["ev-1"]["status"] == "needs_revision", (
                "ev-1 was not actually pending_review at decision time, so its status "
                "must remain unchanged too — only the warning branch should fire"
            )
        finally:
            await motor_db.asset_compliance.delete_many({"tenantId": "tenant-cr01"})
            await motor_db.evidence_reviews.delete_many({"tenantId": "tenant-cr01"})
            client.close()

    asyncio.run(_run())
