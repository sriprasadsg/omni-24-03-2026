"""ITIL Change Management service — controlled modifications to IT services."""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_database

import logging

logger = logging.getLogger(__name__)

_REQUIRED_APPROVALS = {"standard": 1, "normal": 2, "emergency": 3}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _history_entry(actor: str, action: str, changes: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id":         str(uuid.uuid4()),
        "actor":      actor,
        "action":     action,
        "changes":    changes,
        "created_at": _now(),
    }


class ChangeService:
    COL = "change_requests"

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_change(
        self,
        data: Dict[str, Any],
        reporter: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        db = get_database()
        change_type = data.get("change_type", "normal")
        now = _now()
        change: Dict[str, Any] = {
            "id":                  str(uuid.uuid4()),
            "tenantId":            tenant_id,
            "title":               data["title"],
            "description":         data.get("description", ""),
            "change_type":         change_type,
            "status":              "draft",
            "risk_level":          data.get("risk_level", "medium"),
            "impact_level":        data.get("impact_level", "medium"),
            "risk_assessment":     data.get("risk_assessment", ""),
            "rollback_plan":       data.get("rollback_plan", ""),
            "implementation_plan": data.get("implementation_plan", ""),
            "cab_votes":           [],
            "required_approvals":  _REQUIRED_APPROVALS.get(change_type, 2),
            "scheduled_start":     data.get("scheduled_start"),
            "scheduled_end":       data.get("scheduled_end"),
            "assignee":            data.get("assignee", ""),
            "reporter":            reporter,
            "created_at":          now,
            "updated_at":          now,
            "history":             [],
        }
        change["history"].append(
            _history_entry(reporter, "created", {"change_type": change_type, "status": "draft"})
        )
        await db[self.COL].insert_one(change)
        change.pop("_id", None)
        return change

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_changes(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        change_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        db = get_database()
        query: Dict[str, Any] = {"tenantId": tenant_id} if tenant_id else {}
        if status:
            query["status"] = status
        if change_type:
            query["change_type"] = change_type

        total = await db[self.COL].count_documents(query)
        skip = (page - 1) * page_size
        cursor = (
            db[self.COL]
            .find(query, {"_id": 0, "history": 0})
            .sort("created_at", -1)
            .skip(skip)
            .limit(page_size)
        )
        items = [doc async for doc in cursor]
        return {"changes": items, "total": total, "page": page, "page_size": page_size}

    # ── Get ───────────────────────────────────────────────────────────────────

    async def get_change(
        self,
        change_id: str,
        tenant_id: str,
    ) -> Optional[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        db = get_database()
        return await db[self.COL].find_one(
            {"id": change_id, "tenantId": tenant_id}, {"_id": 0}
        )

    # ── Update ────────────────────────────────────────────────────────────────

    async def update_change(
        self,
        change_id: str,
        data: Dict[str, Any],
        actor: str,
        tenant_id: str,
    ) -> Optional[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        db = get_database()
        query = {"id": change_id, "tenantId": tenant_id}

        existing = await db[self.COL].find_one(query, {"_id": 0})
        if not existing:
            return None
        if existing.get("status") == "completed":
            raise ValueError("Cannot update a completed change request")

        allowed = {
            "title", "description", "change_type", "risk_level", "impact_level",
            "risk_assessment", "rollback_plan", "implementation_plan",
            "scheduled_start", "scheduled_end", "assignee",
        }
        patch = {k: v for k, v in data.items() if k in allowed}
        if not patch:
            return existing

        change_record: Dict[str, Any] = {}
        for key, new_val in patch.items():
            old_val = existing.get(key)
            if old_val != new_val:
                change_record[key] = {"from": old_val, "to": new_val}

        patch["updated_at"] = _now()
        update_op: Dict[str, Any] = {"$set": patch}
        if change_record:
            update_op["$push"] = {"history": _history_entry(actor, "updated", change_record)}

        result = await db[self.COL].update_one(query, update_op)
        if result.matched_count == 0:
            return None
        return await self.get_change(change_id, tenant_id)

    # ── Submit for CAB ────────────────────────────────────────────────────────

    async def submit_for_cab(
        self,
        change_id: str,
        tenant_id: str,
        actor: str,
    ) -> Optional[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        db = get_database()
        query = {"id": change_id, "tenantId": tenant_id}
        existing = await db[self.COL].find_one(query, {"_id": 0, "id": 1, "status": 1})
        if not existing:
            return None

        entry = _history_entry(actor, "submitted_for_cab", {"status": {"from": existing.get("status"), "to": "cab_review"}})
        await db[self.COL].update_one(
            query,
            {"$set": {"status": "cab_review", "updated_at": _now()}, "$push": {"history": entry}},
        )
        return await self.get_change(change_id, tenant_id)

    # ── CAB vote ──────────────────────────────────────────────────────────────

    async def cast_cab_vote(
        self,
        change_id: str,
        voter: str,
        vote: str,
        reason: str,
        tenant_id: str,
    ) -> Optional[Dict[str, Any]]:
        if vote not in {"approve", "reject"}:
            raise ValueError("vote must be 'approve' or 'reject'")
        if not tenant_id:
            raise ValueError("tenant_id is required")
        db = get_database()
        query = {"id": change_id, "tenantId": tenant_id}

        existing = await db[self.COL].find_one(query, {"_id": 0})
        if not existing:
            return None

        cab_vote = {"voter": voter, "vote": vote, "reason": reason, "voted_at": _now()}
        entry = _history_entry(voter, "cab_vote_cast", {"vote": vote, "reason": reason})

        # Tally after adding new vote
        existing_votes: List[Dict[str, Any]] = existing.get("cab_votes", [])
        all_votes = existing_votes + [cab_vote]
        approve_count = sum(1 for v in all_votes if v["vote"] == "approve")
        has_reject    = any(v["vote"] == "reject" for v in all_votes)
        required      = existing.get("required_approvals", 2)

        new_status = existing.get("status", "cab_review")
        if has_reject:
            new_status = "rejected"
        elif approve_count >= required:
            new_status = "approved"

        await db[self.COL].update_one(
            query,
            {
                "$push": {"cab_votes": cab_vote, "history": entry},
                "$set":  {"status": new_status, "updated_at": _now()},
            },
        )
        return await self.get_change(change_id, tenant_id)

    # ── Schedule ──────────────────────────────────────────────────────────────

    async def schedule_change(
        self,
        change_id: str,
        start: str,
        end: str,
        tenant_id: str,
        actor: str,
    ) -> Optional[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        db = get_database()
        query = {"id": change_id, "tenantId": tenant_id}
        existing = await db[self.COL].find_one(query, {"_id": 0, "id": 1})
        if not existing:
            return None

        entry = _history_entry(actor, "scheduled", {"scheduled_start": start, "scheduled_end": end})
        await db[self.COL].update_one(
            query,
            {
                "$set": {
                    "scheduled_start": start,
                    "scheduled_end":   end,
                    "status":          "scheduled",
                    "updated_at":      _now(),
                },
                "$push": {"history": entry},
            },
        )
        return await self.get_change(change_id, tenant_id)


change_service = ChangeService()
