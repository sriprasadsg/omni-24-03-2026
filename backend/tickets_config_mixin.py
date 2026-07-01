"""
TicketsConfigMixin — stats, templates, queue config, field schema, and watchers.

Intended to be inherited by TicketsService.  All methods use self.COL and
self.TMPL_COL which are defined on the concrete class.
"""
import uuid
from typing import Any, Dict, List, Optional
from database import get_database
from tickets_helpers import _now


class TicketsConfigMixin:

    # ── Stats ─────────────────────────────────────────────────────────────────

    async def get_stats(self, reporter: Optional[str] = None, tenant_id: str = "") -> Dict[str, Any]:
        db          = get_database()
        base_filter: Dict[str, Any] = {"tenantId": tenant_id} if tenant_id else {}
        if reporter:
            base_filter["reporter"] = reporter

        async def _agg(group_key: str) -> Dict[str, int]:
            out: Dict[str, int] = {}
            async for doc in db[self.COL].aggregate([  # type: ignore[attr-defined]
                {"$match": base_filter},
                {"$group": {"_id": f"${group_key}", "count": {"$sum": 1}}},
            ]):
                out[doc["_id"] or "unknown"] = doc["count"]
            return out

        now_iso   = _now()
        overdue   = await db[self.COL].count_documents({  # type: ignore[attr-defined]
            **base_filter,
            "due_date": {"$lt": now_iso, "$ne": None},
            "status":   {"$nin": ["resolved", "closed"]},
        })
        escalated = await db[self.COL].count_documents({**base_filter, "escalated": True})  # type: ignore[attr-defined]

        return {
            "total":       await db[self.COL].count_documents(base_filter),  # type: ignore[attr-defined]
            "by_status":   await _agg("status"),
            "by_priority": await _agg("priority"),
            "by_type":     await _agg("type"),
            "overdue":     overdue,
            "escalated":   escalated,
        }

    # ── Ticket Templates ──────────────────────────────────────────────────────

    async def list_templates(self, tenant_id: str = "") -> List[Dict[str, Any]]:
        db    = get_database()
        query: Dict[str, Any] = {"tenantId": tenant_id} if tenant_id else {}
        items = await db[self.TMPL_COL].find(query, {"_id": 0}).to_list(200)  # type: ignore[attr-defined]
        return items

    async def create_template(self, data: Dict[str, Any], creator: str, tenant_id: str = "") -> Dict[str, Any]:
        db   = get_database()
        tmpl = {
            "id":          str(uuid.uuid4()),
            "tenantId":    tenant_id,
            "name":        data["name"],
            "description": data.get("description", ""),
            "defaults": {
                "type":           data.get("type", "task"),
                "priority":       data.get("priority", "medium"),
                "assignee":       data.get("assignee", ""),
                "assignee_group": data.get("assignee_group", ""),
                "tags":           data.get("tags", []),
                "title_template": data.get("title_template", ""),
                "body_template":  data.get("body_template", ""),
                "custom_fields":  data.get("custom_fields", {}),
                "sla_hours":      data.get("sla_hours"),
            },
            "created_by": creator,
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db[self.TMPL_COL].insert_one(tmpl)  # type: ignore[attr-defined]
        tmpl.pop("_id", None)
        return tmpl

    async def update_template(self, template_id: str, data: Dict[str, Any], tenant_id: str = "") -> Optional[Dict[str, Any]]:
        db    = get_database()
        query: Dict[str, Any] = {"id": template_id}
        if tenant_id:
            query["tenantId"] = tenant_id
        allowed = {"name", "description", "type", "priority", "assignee", "assignee_group",
                   "tags", "title_template", "body_template", "custom_fields", "sla_hours"}
        patch = {k: v for k, v in data.items() if k in allowed}
        patch["updated_at"] = _now()
        result = await db[self.TMPL_COL].update_one(query, {"$set": patch})  # type: ignore[attr-defined]
        if result.matched_count == 0:
            return None
        return await db[self.TMPL_COL].find_one({"id": template_id}, {"_id": 0})  # type: ignore[attr-defined]

    async def delete_template(self, template_id: str, tenant_id: str = "") -> bool:
        db    = get_database()
        query: Dict[str, Any] = {"id": template_id}
        if tenant_id:
            query["tenantId"] = tenant_id
        result = await db[self.TMPL_COL].delete_one(query)  # type: ignore[attr-defined]
        return result.deleted_count > 0

    # ── Queue management / routing rules ─────────────────────────────────────

    async def get_queue_config(self, tenant_id: str) -> Dict[str, Any]:
        db  = get_database()
        doc = await db["ticket_queues"].find_one({"tenantId": tenant_id}, {"_id": 0})
        return doc or {"tenantId": tenant_id, "rules": []}

    async def save_queue_config(self, tenant_id: str, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        db     = get_database()
        config = {"tenantId": tenant_id, "rules": rules, "updated_at": _now()}
        await db["ticket_queues"].update_one(
            {"tenantId": tenant_id}, {"$set": config}, upsert=True
        )
        return config

    async def auto_assign(self, ticket: Dict[str, Any]) -> Optional[str]:
        """Return the assignee determined by queue routing rules, or None."""
        config = await self.get_queue_config(ticket.get("tenantId", ""))
        for rule in config.get("rules", []):
            conds = rule.get("conditions", {})
            match = all(
                ticket.get(k) == v
                for k, v in conds.items()
                if k in ("type", "priority", "tags")
            )
            if match and rule.get("assignee"):
                return rule["assignee"]
        return None

    # ── Custom field schema ───────────────────────────────────────────────────

    async def get_field_schema(self, tenant_id: str) -> Dict[str, Any]:
        db  = get_database()
        doc = await db["ticket_field_schemas"].find_one({"tenantId": tenant_id}, {"_id": 0})
        return doc or {"tenantId": tenant_id, "fields": []}

    async def save_field_schema(self, tenant_id: str, fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        db     = get_database()
        schema = {"tenantId": tenant_id, "fields": fields, "updated_at": _now()}
        await db["ticket_field_schemas"].update_one(
            {"tenantId": tenant_id}, {"$set": schema}, upsert=True
        )
        return schema

    # ── Approval workflow ─────────────────────────────────────────────────────

    async def approve_ticket(
        self,
        ticket_id: str,
        approver: str,
        comment: str = "",
        tenant_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        db    = get_database()
        query = {"id": ticket_id}
        if tenant_id:
            query["tenantId"] = tenant_id
        now     = _now()
        patch   = {"approval_status": "approved", "approved_by": approver, "approved_at": now, "updated_at": now}
        history = self._history_entry(approver, "approved", {"comment": comment})  # type: ignore[attr-defined]
        result  = await db[self.COL].update_one(  # type: ignore[attr-defined]
            query, {"$set": patch, "$push": {"history": history}}
        )
        if result.matched_count == 0:
            return None
        return await self.get_ticket(ticket_id, tenant_id=tenant_id)  # type: ignore[attr-defined]

    async def reject_ticket(
        self,
        ticket_id: str,
        rejector: str,
        reason: str,
        tenant_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        db    = get_database()
        query = {"id": ticket_id}
        if tenant_id:
            query["tenantId"] = tenant_id
        now     = _now()
        patch   = {
            "approval_status":  "rejected",
            "rejected_by":      rejector,
            "rejected_at":      now,
            "rejection_reason": reason,
            "status":           "closed",
            "updated_at":       now,
        }
        history = self._history_entry(rejector, "rejected", {"reason": reason})  # type: ignore[attr-defined]
        result  = await db[self.COL].update_one(  # type: ignore[attr-defined]
            query, {"$set": patch, "$push": {"history": history}}
        )
        if result.matched_count == 0:
            return None
        return await self.get_ticket(ticket_id, tenant_id=tenant_id)  # type: ignore[attr-defined]

    # ── Escalation ────────────────────────────────────────────────────────────

    async def escalate_ticket(
        self,
        ticket_id: str,
        actor: str,
        reason: str = "",
        tenant_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        db    = get_database()
        query = {"id": ticket_id}
        if tenant_id:
            query["tenantId"] = tenant_id
        existing = await db[self.COL].find_one(query)  # type: ignore[attr-defined]
        if not existing:
            return None
        new_level = existing.get("escalation_level", 0) + 1
        now       = _now()
        patch     = {
            "escalated":        True,
            "escalation_level": new_level,
            "escalated_at":     now,
            "updated_at":       now,
        }
        priority_ladder = ["low", "medium", "high", "critical"]
        current_idx = (
            priority_ladder.index(existing.get("priority", "medium"))
            if existing.get("priority", "medium") in priority_ladder
            else 1
        )
        if current_idx < len(priority_ladder) - 1:
            patch["priority"] = priority_ladder[current_idx + 1]

        history = self._history_entry(actor, "escalated", {"level": new_level, "reason": reason})  # type: ignore[attr-defined]
        await db[self.COL].update_one(query, {"$set": patch, "$push": {"history": history}})  # type: ignore[attr-defined]
        updated = await self.get_ticket(ticket_id, tenant_id=tenant_id)  # type: ignore[attr-defined]

        try:
            import asyncio
            from ticket_notifications import notify_escalated
            asyncio.create_task(notify_escalated(updated, actor, reason))
        except Exception:
            pass

        return updated

    # ── Watchers ──────────────────────────────────────────────────────────────

    async def add_watcher(self, ticket_id: str, email: str, tenant_id: str = "") -> bool:
        db    = get_database()
        query = {"id": ticket_id}
        if tenant_id:
            query["tenantId"] = tenant_id
        result = await db[self.COL].update_one(  # type: ignore[attr-defined]
            query, {"$addToSet": {"watchers": email}, "$set": {"updated_at": _now()}}
        )
        return result.matched_count > 0

    async def remove_watcher(self, ticket_id: str, email: str, tenant_id: str = "") -> bool:
        db    = get_database()
        query = {"id": ticket_id}
        if tenant_id:
            query["tenantId"] = tenant_id
        result = await db[self.COL].update_one(  # type: ignore[attr-defined]
            query, {"$pull": {"watchers": email}, "$set": {"updated_at": _now()}}
        )
        return result.matched_count > 0
