import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from database import get_database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TicketsService:
    COL = "tickets"

    async def list_tickets(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        ticket_type: Optional[str] = None,
        assignee: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        db = get_database()
        query: Dict[str, Any] = {}
        if status:
            query["status"] = status
        if priority:
            query["priority"] = priority
        if ticket_type:
            query["type"] = ticket_type
        if assignee:
            query["assignee"] = assignee
        if search:
            query["$or"] = [
                {"title": {"$regex": search, "$options": "i"}},
                {"description": {"$regex": search, "$options": "i"}},
                {"ticket_number": {"$regex": search, "$options": "i"}},
            ]

        total = await db[self.COL].count_documents(query)
        skip = (page - 1) * page_size
        cursor = db[self.COL].find(query).sort("created_at", -1).skip(skip).limit(page_size)
        items = []
        async for doc in cursor:
            doc.pop("_id", None)
            items.append(doc)

        return {"tickets": items, "total": total, "page": page, "page_size": page_size}

    async def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        db = get_database()
        doc = await db[self.COL].find_one({"id": ticket_id})
        if doc:
            doc.pop("_id", None)
        return doc

    async def create_ticket(self, data: Dict[str, Any], reporter: str) -> Dict[str, Any]:
        db = get_database()
        # Generate sequential-style ticket number
        count = await db[self.COL].count_documents({})
        ticket = {
            "id": str(uuid.uuid4()),
            "ticket_number": f"TKT-{count + 1:04d}",
            "title": data["title"],
            "description": data.get("description", ""),
            "type": data.get("type", "task"),
            "priority": data.get("priority", "medium"),
            "status": "open",
            "assignee": data.get("assignee", ""),
            "reporter": reporter,
            "tags": data.get("tags", []),
            "linked_assets": data.get("linked_assets", []),
            "linked_vulnerabilities": data.get("linked_vulnerabilities", []),
            "comments": [],
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db[self.COL].insert_one(ticket)
        ticket.pop("_id", None)
        return ticket

    async def update_ticket(self, ticket_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        db = get_database()
        allowed = {"title", "description", "type", "priority", "status", "assignee", "tags",
                   "linked_assets", "linked_vulnerabilities"}
        patch = {k: v for k, v in updates.items() if k in allowed}
        if not patch:
            return await self.get_ticket(ticket_id)
        patch["updated_at"] = _now()
        await db[self.COL].update_one({"id": ticket_id}, {"$set": patch})
        return await self.get_ticket(ticket_id)

    async def add_comment(self, ticket_id: str, author: str, text: str) -> Optional[Dict[str, Any]]:
        db = get_database()
        comment = {
            "id": str(uuid.uuid4()),
            "author": author,
            "text": text,
            "created_at": _now(),
        }
        await db[self.COL].update_one(
            {"id": ticket_id},
            {"$push": {"comments": comment}, "$set": {"updated_at": _now()}},
        )
        return await self.get_ticket(ticket_id)

    async def delete_ticket(self, ticket_id: str) -> bool:
        db = get_database()
        result = await db[self.COL].delete_one({"id": ticket_id})
        return result.deleted_count > 0

    async def get_stats(self) -> Dict[str, Any]:
        db = get_database()
        pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        by_status: Dict[str, int] = {}
        async for doc in db[self.COL].aggregate(pipeline):
            by_status[doc["_id"]] = doc["count"]

        pipeline2 = [
            {"$group": {"_id": "$priority", "count": {"$sum": 1}}},
        ]
        by_priority: Dict[str, int] = {}
        async for doc in db[self.COL].aggregate(pipeline2):
            by_priority[doc["_id"]] = doc["count"]

        total = await db[self.COL].count_documents({})
        return {
            "total": total,
            "by_status": by_status,
            "by_priority": by_priority,
        }


tickets_service = TicketsService()
