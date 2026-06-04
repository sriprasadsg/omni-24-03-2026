"""ITIL Problem Management service — root cause tracking for incidents."""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_database

import logging

logger = logging.getLogger(__name__)


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


class ProblemService:
    COL = "problems"

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_problem(
        self,
        data: Dict[str, Any],
        reporter: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        db = get_database()
        now = _now()
        problem: Dict[str, Any] = {
            "id":                  str(uuid.uuid4()),
            "tenantId":            tenant_id,
            "title":               data["title"],
            "description":         data.get("description", ""),
            "status":              data.get("status", "open"),
            "priority":            data.get("priority", "medium"),
            "root_cause":          data.get("root_cause", ""),
            "workaround":          data.get("workaround", ""),
            "permanent_fix":       data.get("permanent_fix", ""),
            "linked_incident_ids": data.get("linked_incident_ids", []),
            "known_error":         data.get("known_error", False),
            "assignee":            data.get("assignee", ""),
            "reporter":            reporter,
            "created_at":          now,
            "updated_at":          now,
            "resolved_at":         None,
            "history":             [],
        }
        problem["history"].append(
            _history_entry(reporter, "created", {"status": problem["status"], "priority": problem["priority"]})
        )
        await db[self.COL].insert_one(problem)
        problem.pop("_id", None)
        return problem

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_problems(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        db = get_database()
        query: Dict[str, Any] = {"tenantId": tenant_id} if tenant_id else {}
        if status:
            query["status"] = status
        if priority:
            query["priority"] = priority

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
        return {"problems": items, "total": total, "page": page, "page_size": page_size}

    # ── Get ───────────────────────────────────────────────────────────────────

    async def get_problem(
        self,
        problem_id: str,
        tenant_id: str,
    ) -> Optional[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        db = get_database()
        return await db[self.COL].find_one(
            {"id": problem_id, "tenantId": tenant_id}, {"_id": 0}
        )

    # ── Update ────────────────────────────────────────────────────────────────

    async def update_problem(
        self,
        problem_id: str,
        data: Dict[str, Any],
        actor: str,
        tenant_id: str,
    ) -> Optional[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        db = get_database()
        query = {"id": problem_id, "tenantId": tenant_id}

        allowed = {
            "title", "description", "status", "priority",
            "root_cause", "workaround", "permanent_fix",
            "assignee", "known_error",
        }
        patch = {k: v for k, v in data.items() if k in allowed}
        if not patch:
            return await self.get_problem(problem_id, tenant_id)

        existing = await db[self.COL].find_one(query, {"_id": 0})
        if not existing:
            return None

        change_record: Dict[str, Any] = {}
        for key, new_val in patch.items():
            old_val = existing.get(key)
            if old_val != new_val:
                change_record[key] = {"from": old_val, "to": new_val}

        patch["updated_at"] = _now()
        if patch.get("status") in {"resolved", "closed"} and not existing.get("resolved_at"):
            patch["resolved_at"] = patch["updated_at"]

        update_op: Dict[str, Any] = {"$set": patch}
        if change_record:
            update_op["$push"] = {"history": _history_entry(actor, "updated", change_record)}

        result = await db[self.COL].update_one(query, update_op)
        if result.matched_count == 0:
            return None
        return await self.get_problem(problem_id, tenant_id)

    # ── Link incident ─────────────────────────────────────────────────────────

    async def link_incident(
        self,
        problem_id: str,
        incident_id: str,
        tenant_id: str,
    ) -> Optional[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        db = get_database()
        query = {"id": problem_id, "tenantId": tenant_id}
        existing = await db[self.COL].find_one(query, {"_id": 0, "linked_incident_ids": 1})
        if not existing:
            return None
        if incident_id in existing.get("linked_incident_ids", []):
            return await self.get_problem(problem_id, tenant_id)

        entry = _history_entry("system", "incident_linked", {"incident_id": incident_id})
        await db[self.COL].update_one(
            query,
            {
                "$addToSet": {"linked_incident_ids": incident_id},
                "$push":     {"history": entry},
                "$set":      {"updated_at": _now()},
            },
        )
        return await self.get_problem(problem_id, tenant_id)

    # ── Promote to Known Error ────────────────────────────────────────────────

    async def promote_to_known_error(
        self,
        problem_id: str,
        workaround: str,
        tenant_id: str,
        actor: str,
    ) -> Optional[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        db = get_database()
        query = {"id": problem_id, "tenantId": tenant_id}
        existing = await db[self.COL].find_one(query, {"_id": 0, "id": 1})
        if not existing:
            return None

        entry = _history_entry(actor, "promoted_to_known_error", {"workaround": workaround})
        await db[self.COL].update_one(
            query,
            {
                "$set": {
                    "known_error": True,
                    "workaround":  workaround,
                    "status":      "known_error",
                    "updated_at":  _now(),
                },
                "$push": {"history": entry},
            },
        )
        return await self.get_problem(problem_id, tenant_id)


problem_service = ProblemService()
