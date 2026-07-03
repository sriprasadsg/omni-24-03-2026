"""Evidence review workflow — submit, approve, reject, request changes.

Stores review records in `evidence_reviews` collection and tracks the current
review state on each evidence object via `asset_compliance.evidence[].status`.

Review lifecycle:
  Uploaded → submit-for-review → pending_review
    → approved              → approved
    → rejected              → rejected
    → changes_requested     → needs_revision → submit-for-review → pending_review
"""
import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_EVIDENCE_REVIEWS_COL = "evidence_reviews"


class EvidenceNotFoundError(ValueError):
    """Raised when the evidence item does not exist for the tenant at all.

    Kept as a ValueError subclass (rather than an unrelated exception type)
    so any pre-existing `except ValueError` handler that hasn't been updated
    yet still catches it — but a distinct type lets `create_review`'s caller
    (evidence_review_endpoints.py) tell "not found" apart from "exists but
    wrong status" and map each to a different HTTP status code (IN-02),
    instead of collapsing both into a single misleading 404.
    """


# ── Helpers ────────────────────────────────────────────────────────────────────


def _generate_id() -> str:
    return f"rev-{uuid.uuid4().hex}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _valid_decisions() -> set[str]:
    return {"approved", "rejected", "changes_requested"}


def requires_comment(decision: str) -> bool:
    """Returns True when a comment is mandatory for this decision."""
    return decision in ("rejected", "changes_requested")


# ── Review lifecycle ───────────────────────────────────────────────────────────


def _submittable_statuses() -> list:
    """Statuses an evidence item may be in before it can be submitted for review.

    None covers evidence that has never had a status set (unset/new).
    """
    return [None, "needs_revision", "rejected"]


async def submit_for_review(
    evidence_id: str,
    db,
    tenant_id: str,
) -> bool:
    """Set evidence status to pending_review (no review record created yet).

    Only allowed from an unset/needs_revision/rejected state — guards against
    re-submitting evidence that is already approved or already pending review.
    Uses positional $ operator — evidence.id must be unique within the array.
    Returns True if a document was actually modified.
    """
    result = await db.asset_compliance.update_one(
        {
            "tenantId": tenant_id,
            "evidence": {
                "$elemMatch": {
                    "id": evidence_id,
                    "status": {"$in": _submittable_statuses()},
                }
            },
        },
        {
            "$set": {
                "evidence.$.status": "pending_review",
                "evidence.$.review_updated_at": _now_iso(),
            }
        },
    )
    return result.modified_count > 0


async def create_review(
    evidence_id: str,
    reviewer: str,
    comment: str,
    db,
    tenant_id: str,
) -> dict:
    """Create a new review record with status 'pending'.

    Validates the evidence item exists for tenant_id and is currently in
    'pending_review' status before inserting; raises ValueError otherwise.
    Without this guard, a review thread could be opened against evidence
    that was never submitted for review, bypassing the documented lifecycle
    (Uploaded → submit-for-review → pending_review → decided).

    KNOWN RESIDUAL RACE (WR-02): the evidence-status validation above is a
    separate read from the atomic upsert below — it is check-then-act, not
    atomic. Another request can change the evidence's status in the window
    between the validation read and the upsert, so this check does not
    *fully* prevent a review record from being created/reused against
    evidence that is no longer actually pending_review by the time the
    write happens. The blast radius is limited: `update_review_decision`'s
    own atomic re-check of evidence status at decision time (see its
    docstring) means such an orphaned review record cannot silently
    overwrite a since-changed evidence status — it only logs a warning.
    Full correctness would require folding this validation into the same
    atomic operation (e.g. a multi-document transaction spanning
    asset_compliance and evidence_reviews), which has not been done here.

    Also reuses an existing 'pending' review record for the same evidence_id
    instead of creating a duplicate. Without this dedup, a retried create call
    (e.g. after a decide-request timed out) can leave multiple independent
    'pending' review threads open against the same evidence item — any one of
    which can later be decided on its own, silently overwriting the evidence's
    current status without the evidence ever being resubmitted for review.

    The dedup is implemented as a single atomic `find_one_and_update` with
    `upsert=True` keyed on (tenantId, evidenceId, status="pending") rather than
    a separate read-then-write (find_one then insert_one) — the latter is a
    check-then-act race where two concurrent create-review calls can both
    observe "no existing pending review" and both insert a duplicate record.
    """
    existing = await db.asset_compliance.find_one(
        {"tenantId": tenant_id, "evidence.id": evidence_id}
    )
    if not existing:
        raise EvidenceNotFoundError(f"Evidence '{evidence_id}' not found for tenant")

    evidence_item = next(
        (e for e in existing.get("evidence", []) if e.get("id") == evidence_id), None
    )
    if not evidence_item or evidence_item.get("status") != "pending_review":
        current_status = (evidence_item.get("status") or "unset") if evidence_item else "unknown"
        raise ValueError(
            f"Evidence '{evidence_id}' is not pending review (current status: {current_status})"
        )

    now = _now_iso()
    review = await db._db[_EVIDENCE_REVIEWS_COL].find_one_and_update(
        {"tenantId": tenant_id, "evidenceId": evidence_id, "status": "pending"},
        {
            "$setOnInsert": {
                "id": _generate_id(),
                "tenantId": tenant_id,
                "evidenceId": evidence_id,
                "reviewer": reviewer,
                "status": "pending",
                "comment": comment,
                "created_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
        return_document=True,
        projection={"_id": 0},
    )
    return review


async def update_review_decision(
    review_id: str,
    evidence_id: str,
    decision: str,
    comment: str,
    db,
    tenant_id: str,
    decided_by: str | None = None,
) -> dict | None:
    """Update a review decision and propagate status to the evidence record.

    decision must be one of: approved, rejected, changes_requested.
    rejected / changes_requested require a non-empty comment.

    Evidence status mapping:
      approved          → approved
      rejected          → rejected
      changes_requested → needs_revision

    Scoped to tenant_id AND evidence_id to prevent cross-tenant access to
    review records *and* to guarantee a URL evidence_id that doesn't match
    the review's real evidenceId naturally yields "not found" with zero side
    effects — the mismatch is part of the same atomic lookup that performs
    the mutation, not a check on the result of a call that already wrote.

    Also scoped to status: "pending" so a review can only be decided once —
    without this, a review already decided 'approved' could be PATCHed again
    to 'rejected', silently flipping the evidence status back and forth with
    no idempotency guard.

    decided_by records the identity of the user who actually made the
    decision. The review's `reviewer` field is fixed at creation time (it can
    belong to whoever first opened the pending thread — see the dedup upsert
    in create_review) and is never overwritten here, so `decided_by` is the
    only reliable record of who approved/rejected/requested changes when
    that differs from the creator (WR-01).

    Returns the updated review dict, or None if not found / already decided.
    """
    now = _now_iso()
    decision = decision.lower()
    if decision not in _valid_decisions():
        raise ValueError(f"Invalid decision '{decision}'. Must be one of {_valid_decisions()}")

    evidence_status = {
        "approved": "approved",
        "rejected": "rejected",
        "changes_requested": "needs_revision",
    }[decision]

    # 1. Update the review record — evidence_id and status: "pending" are
    #    part of the filter itself, so a mismatched evidence_id or an
    #    already-decided review is indistinguishable from "not found" and
    #    never mutates anything.
    review = await db._db[_EVIDENCE_REVIEWS_COL].find_one_and_update(
        {
            "id": review_id,
            "evidenceId": evidence_id,
            "tenantId": tenant_id,
            "status": "pending",
        },
        {
            "$set": {
                "status": decision,
                "comment": comment,
                "updated_at": now,
                "decided_by": decided_by,
            }
        },
        return_document=True,
        projection={"_id": 0},
    )
    if not review:
        return None

    # 2. Propagate status to evidence record in asset_compliance. Also require
    #    the evidence to still be 'pending_review' at this exact moment — without
    #    this, an orphaned/stale 'pending' review record (e.g. left behind by a
    #    request that failed after step 1 but before step 2 on a prior attempt)
    #    could later be decided independently and silently overwrite whatever
    #    status the evidence has since moved to, without the evidence ever being
    #    resubmitted for review. The match result is checked (unlike a
    #    fire-and-forget call) because the review record above has already been
    #    updated at this point — if the evidence item no longer exists at this id,
    #    or is no longer pending_review, the caller still gets a 200 + audit log
    #    for the review-record mutation, but we log a warning so the discrepancy
    #    is at least observable rather than silently swallowed.
    result = await db.asset_compliance.update_one(
        {
            "tenantId": tenant_id,
            "evidence": {
                "$elemMatch": {
                    "id": evidence_id,
                    "status": "pending_review",
                }
            },
        },
        {
            "$set": {
                "evidence.$.status": evidence_status,
                "evidence.$.review_updated_at": now,
            }
        },
    )
    if result.modified_count == 0:
        logger.warning(
            "evidence_review: review %s decided as '%s' but evidence %s was not "
            "'pending_review' at decision time (stale/duplicate review record or "
            "evidence deleted; tenant_id=%s) — evidence status was not changed",
            review_id, decision, evidence_id, tenant_id,
        )

    return review


async def get_reviews(
    evidence_id: str,
    db,
    tenant_id: str,
) -> list[dict]:
    """Return all review records for a given evidence item, newest first.

    Capped at 500 — a single evidence item is not expected to accumulate more
    review rounds than that; the cap bounds worst-case memory/response size
    rather than reflecting a real expected volume.
    """
    cursor = (
        db._db[_EVIDENCE_REVIEWS_COL]
        .find({"evidenceId": evidence_id, "tenantId": tenant_id}, {"_id": 0})
        .sort("created_at", -1)
    )
    return await cursor.to_list(length=500)


async def get_pending_evidence(
    db,
    tenant_id: str,
) -> list[dict]:
    """Return all asset compliance documents with pending_review evidence.

    Uses $unwind + $match aggregation to flatten the evidence array and
    filter to only items with status === 'pending_review'. Capped at 500
    to bound worst-case memory/response size for tenants with a large
    evidence backlog.
    """
    pipeline = [
        {"$match": {"tenantId": tenant_id}},
        {"$unwind": "$evidence"},
        {"$match": {"evidence.status": "pending_review"}},
        {"$sort": {"evidence.review_updated_at": -1}},
        {
            "$project": {
                "_id": 0,
                "assetId": 1,
                "controlId": 1,
                "status": 1,
                "lastUpdated": 1,
                "checkName": 1,
                "evidence_id": "$evidence.id",
                "evidence_name": "$evidence.name",
                "evidence_date": "$evidence.uploadedAt",
                "evidence_agent_type": "$evidence.agent_type",
            }
        },
    ]
    cursor = db.asset_compliance.aggregate(pipeline)
    return await cursor.to_list(length=500)
