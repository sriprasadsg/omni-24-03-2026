import uuid
from typing import Any, Dict, List, Optional
from database import get_database
import logging

from tickets_helpers import _now, _sla_due, _compute_sla, _SLA_HOURS, LINK_TYPES  # noqa: F401
from tickets_config_mixin import TicketsConfigMixin

logger = logging.getLogger(__name__)


async def get_sla_hours(
    priority: str,
    ticket_type: str,
    tags: List[str],
    db: Any = None,
) -> int:
    """Return SLA hours for a ticket, consulting sla_policies collection first."""
    if db is None:
        db = get_database()
    try:
        query: Dict[str, Any] = {
            "$or": [
                {"type": ticket_type},
                {"tags": {"$in": tags}} if tags else {"tags": {"$in": []}},
            ]
        }
        policy = await db["sla_policies"].find_one(query, {"_id": 0})
        if policy and policy.get("sla_hours"):
            return int(policy["sla_hours"])
    except Exception:
        pass
    return _SLA_HOURS.get(priority, 24)


class TicketsService(TicketsConfigMixin):
    COL      = "tickets"
    TMPL_COL = "ticket_templates"

    @staticmethod
    def _require_tenant(tenant_id: str) -> None:
        """Raise ValueError when tenant_id is falsy — prevents cross-tenant IDOR."""
        if not tenant_id:
            raise ValueError("tenant_id is required for all ticket operations")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _history_entry(self, actor: str, action: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id":         str(uuid.uuid4()),
            "actor":      actor,
            "action":     action,
            "changes":    changes,
            "created_at": _now(),
        }

    # ── List / fetch ──────────────────────────────────────────────────────────

    async def list_tickets(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        ticket_type: Optional[str] = None,
        assignee: Optional[str] = None,
        assignee_group: Optional[str] = None,
        reporter: Optional[str] = None,
        search: Optional[str] = None,
        sla_status: Optional[str] = None,
        overdue_only: bool = False,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "created_at",
        sort_dir: int = -1,
    ) -> Dict[str, Any]:
        db = get_database()
        # list_tickets intentionally accepts tenant_id="" for Super Admin
        # (cross-tenant listing). _require_tenant is enforced on single-record
        # operations (get, update, delete) where an empty tenant_id would be IDOR.
        query: Dict[str, Any] = {"tenantId": tenant_id} if tenant_id else {}
        if status:         query["status"]         = status
        if priority:       query["priority"]        = priority
        if ticket_type:    query["type"]            = ticket_type
        if assignee:       query["assignee"]        = assignee
        if assignee_group: query["assignee_group"]  = assignee_group
        if reporter:       query["reporter"]        = reporter
        if overdue_only:
            query["due_date"] = {"$lt": _now(), "$ne": None}
            query["status"]   = {"$nin": ["resolved", "closed"]}
        if search:
            query["$or"] = [
                {"title":         {"$regex": search, "$options": "i"}},
                {"description":   {"$regex": search, "$options": "i"}},
                {"ticket_number": {"$regex": search, "$options": "i"}},
                {"tags":          {"$regex": search, "$options": "i"}},
            ]

        valid_sort = {"created_at", "updated_at", "priority", "status", "due_date", "ticket_number"}
        sort_field = sort_by if sort_by in valid_sort else "created_at"

        total  = await db[self.COL].count_documents(query)
        skip   = (page - 1) * page_size
        cursor = (
            db[self.COL]
            .find(query, {"_id": 0, "history": 0})
            .sort(sort_field, sort_dir)
            .skip(skip)
            .limit(page_size)
        )
        items = [_compute_sla(doc) async for doc in cursor]

        if sla_status:
            items = [t for t in items if t.get("sla_status") == sla_status]

        return {"tickets": items, "total": total, "page": page, "page_size": page_size}

    async def get_ticket(self, ticket_id: str, tenant_id: str = "") -> Optional[Dict[str, Any]]:
        db    = get_database()
        self._require_tenant(tenant_id)
        query = {"id": ticket_id, "tenantId": tenant_id}
        doc = await db[self.COL].find_one(query, {"_id": 0})
        if doc:
            _compute_sla(doc)
        return doc

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_ticket(
        self,
        data: Dict[str, Any],
        reporter: str,
        tenant_id: str = "",
    ) -> Dict[str, Any]:
        db         = get_database()
        count      = await db[self.COL].count_documents({})
        priority   = data.get("priority", "medium")
        sla_hours  = data.get("sla_hours")
        created_at = _now()
        # due_date resolved after get_sla_hours below; placeholder until then
        due_date   = data.get("due_date")

        resolved_sla_hours = await get_sla_hours(
            priority, data.get("type", "task"), data.get("tags", []), db
        )
        if sla_hours is None:
            sla_hours = resolved_sla_hours
        if not due_date:
            due_date = _sla_due(priority, sla_hours, created_at)

        ticket: Dict[str, Any] = {
            "id":             str(uuid.uuid4()),
            "ticket_number":  f"TKT-{count + 1:04d}",
            "tenantId":       tenant_id,
            "title":          data["title"],
            "description":    data.get("description", ""),
            "type":           data.get("type", "task"),
            "priority":       priority,
            "status":         "open",
            "assignee":       data.get("assignee", ""),
            "assignee_group": data.get("assignee_group", ""),
            "watchers":       data.get("watchers", []),
            "reporter":       reporter,
            "tags":           data.get("tags", []),
            "custom_fields":  data.get("custom_fields", {}),
            "sla_hours":      sla_hours,
            "due_date":       due_date,
            "hold_started_at":    None,
            "total_hold_duration": 0,
            "escalated":      False,
            "escalation_level": 0,
            "escalated_at":   None,
            "endpoint_info":  data.get("endpoint_info") or {},
            "agent_id":       data.get("agent_id", ""),
            "agent_hostname": data.get("agent_hostname", ""),
            "tenant_name":    data.get("tenant_name", ""),
            "linked_assets":  data.get("linked_assets", []),
            "linked_vulnerabilities": data.get("linked_vulnerabilities", []),
            "links":          [],
            "attachments":    [],
            "work_logs":      [],
            "approval_required": data.get("approval_required", False),
            "approval_status":   "pending" if data.get("approval_required") else "none",
            "approved_by":    None,
            "approved_at":    None,
            "rejected_by":    None,
            "rejected_at":    None,
            "rejection_reason": None,
            "comments":       [],
            "history":        [],
            "total_hours_logged": 0.0,
            "created_at":     created_at,
            "updated_at":     created_at,
        }
        ticket["history"].append(
            self._history_entry(reporter, "created", {"status": "open", "priority": priority})
        )
        await db[self.COL].insert_one(ticket)
        ticket.pop("_id", None)
        _compute_sla(ticket)

        try:
            from ticket_notifications import notify_ticket_created
            import asyncio
            asyncio.create_task(notify_ticket_created(ticket))
        except Exception:
            pass

        return ticket

    # ── Update ────────────────────────────────────────────────────────────────

    async def update_ticket(
        self,
        ticket_id: str,
        updates: Dict[str, Any],
        actor: str = "system",
        tenant_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        db    = get_database()
        self._require_tenant(tenant_id)
        query = {"id": ticket_id, "tenantId": tenant_id}

        allowed = {
            "title", "description", "type", "priority", "status",
            "assignee", "assignee_group", "watchers", "tags", "due_date",
            "sla_hours", "linked_assets", "linked_vulnerabilities",
            "custom_fields", "approval_required",
        }
        patch = {k: v for k, v in updates.items() if k in allowed}
        if not patch:
            return await self.get_ticket(ticket_id, tenant_id=tenant_id)

        existing = await db[self.COL].find_one(query, {"_id": 0})
        if not existing:
            return None

        change_record: Dict[str, Any] = {}
        for key, new_val in patch.items():
            old_val = existing.get(key)
            if old_val != new_val:
                change_record[key] = {"from": old_val, "to": new_val}

        patch["updated_at"] = _now()
        if "priority" in patch and "due_date" not in patch:
            patch["due_date"] = _sla_due(
                patch["priority"],
                patch.get("sla_hours", existing.get("sla_hours")),
                existing["created_at"],
            )

        # ── Hold / pause SLA tracking ─────────────────────────────────────────
        _hold_statuses = {"on_hold", "pending_customer"}
        new_status = patch.get("status")
        old_status = existing.get("status", "")
        if new_status and new_status != old_status:
            now_str = patch["updated_at"]
            if new_status in _hold_statuses and old_status not in _hold_statuses:
                # Entering hold — record when the hold started
                patch["hold_started_at"] = now_str
            elif new_status not in _hold_statuses and old_status in _hold_statuses:
                # Leaving hold — accumulate elapsed hold time
                hold_started_raw = existing.get("hold_started_at")
                if hold_started_raw:
                    from datetime import datetime, timezone
                    try:
                        hs = datetime.fromisoformat(
                            str(hold_started_raw).replace("Z", "+00:00")
                        )
                        if hs.tzinfo is None:
                            hs = hs.replace(tzinfo=timezone.utc)
                        now_dt = datetime.fromisoformat(now_str.replace("Z", "+00:00"))
                        if now_dt.tzinfo is None:
                            now_dt = now_dt.replace(tzinfo=timezone.utc)
                        elapsed = (now_dt - hs).total_seconds()
                        patch["total_hold_duration"] = (
                            (existing.get("total_hold_duration") or 0) + elapsed
                        )
                    except (ValueError, TypeError):
                        pass
                patch["hold_started_at"] = None

        update_op: Dict[str, Any] = {"$set": patch}
        if change_record:
            update_op["$push"] = {
                "history": self._history_entry(actor, "updated", change_record)
            }

        result = await db[self.COL].update_one(query, update_op)
        if result.matched_count == 0:
            return None
        updated = await self.get_ticket(ticket_id, tenant_id=tenant_id)

        try:
            import asyncio
            if updated and "status" in change_record:
                from ticket_notifications import notify_status_changed
                asyncio.create_task(
                    notify_status_changed(updated, change_record["status"]["from"], actor)
                )
            if updated and "assignee" in change_record:
                from ticket_notifications import notify_assigned
                asyncio.create_task(
                    notify_assigned(updated, change_record["assignee"]["to"] or "", actor)
                )
        except Exception:
            pass

        return updated

    # ── Bulk update ───────────────────────────────────────────────────────────

    async def bulk_update(
        self,
        ticket_ids: List[str],
        updates: Dict[str, Any],
        actor: str = "system",
        tenant_id: str = "",
    ) -> Dict[str, Any]:
        db      = get_database()
        allowed = {"status", "priority", "assignee", "assignee_group", "tags", "due_date"}
        patch   = {k: v for k, v in updates.items() if k in allowed}
        if not patch:
            return {"updated": 0}

        self._require_tenant(tenant_id)
        base_query: Dict[str, Any] = {"id": {"$in": ticket_ids}, "tenantId": tenant_id}

        patch["updated_at"] = _now()
        history_entry = self._history_entry(actor, "bulk_updated", patch)
        result = await db[self.COL].update_many(
            base_query,
            {"$set": patch, "$push": {"history": history_entry}},
        )
        return {"updated": result.modified_count}

    # ── History ───────────────────────────────────────────────────────────────

    async def get_history(self, ticket_id: str, tenant_id: str = "") -> Optional[List[Dict[str, Any]]]:
        doc = await self.get_ticket(ticket_id, tenant_id=tenant_id)
        if not doc:
            return None
        return sorted(doc.get("history", []), key=lambda h: h["created_at"], reverse=True)

    # ── Comments ──────────────────────────────────────────────────────────────

    async def add_comment(
        self,
        ticket_id: str,
        author: str,
        text: str,
        tenant_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        db    = get_database()
        self._require_tenant(tenant_id)
        query = {"id": ticket_id, "tenantId": tenant_id}
        comment = {
            "id":         str(uuid.uuid4()),
            "author":     author,
            "text":       text,
            "created_at": _now(),
            "edited":     False,
        }
        history = self._history_entry(author, "commented", {"preview": text[:80]})
        result = await db[self.COL].update_one(
            query,
            {
                "$push": {"comments": comment, "history": history},
                "$set":  {"updated_at": _now()},
            },
        )
        if result.matched_count == 0:
            return None
        updated = await self.get_ticket(ticket_id, tenant_id=tenant_id)

        try:
            import asyncio
            from ticket_notifications import notify_comment_added
            asyncio.create_task(notify_comment_added(updated, author, text))
        except Exception:
            pass

        return updated

    # ── Ticket links / dependencies ───────────────────────────────────────────

    async def add_link(
        self,
        ticket_id: str,
        linked_id: str,
        link_type: str,
        actor: str,
        tenant_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        if link_type not in LINK_TYPES:
            raise ValueError(f"Invalid link type. Allowed: {LINK_TYPES}")
        db    = get_database()
        self._require_tenant(tenant_id)
        query = {"id": ticket_id, "tenantId": tenant_id}
        link    = {"linked_id": linked_id, "type": link_type, "created_at": _now()}
        history = self._history_entry(actor, "linked", {"linked_id": linked_id, "type": link_type})
        result  = await db[self.COL].update_one(
            query,
            {"$push": {"links": link, "history": history}, "$set": {"updated_at": _now()}},
        )
        if result.matched_count == 0:
            return None
        return await self.get_ticket(ticket_id, tenant_id=tenant_id)

    async def remove_link(
        self,
        ticket_id: str,
        linked_id: str,
        actor: str,
        tenant_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        db    = get_database()
        self._require_tenant(tenant_id)
        query = {"id": ticket_id, "tenantId": tenant_id}
        history = self._history_entry(actor, "unlinked", {"linked_id": linked_id})
        result  = await db[self.COL].update_one(
            query,
            {
                "$pull": {"links": {"linked_id": linked_id}},
                "$push": {"history": history},
                "$set":  {"updated_at": _now()},
            },
        )
        if result.matched_count == 0:
            return None
        return await self.get_ticket(ticket_id, tenant_id=tenant_id)

    # ── Work log / time tracking ──────────────────────────────────────────────

    async def log_work(
        self,
        ticket_id: str,
        author: str,
        hours: float,
        description: str,
        tenant_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        if hours <= 0:
            raise ValueError("Hours must be positive")
        db    = get_database()
        self._require_tenant(tenant_id)
        query = {"id": ticket_id, "tenantId": tenant_id}
        entry = {
            "id":          str(uuid.uuid4()),
            "author":      author,
            "hours":       round(hours, 2),
            "description": description,
            "created_at":  _now(),
        }
        history = self._history_entry(author, "work_logged", {"hours": hours})
        result  = await db[self.COL].update_one(
            query,
            {
                "$push":  {"work_logs": entry, "history": history},
                "$inc":   {"total_hours_logged": hours},
                "$set":   {"updated_at": _now()},
            },
        )
        if result.matched_count == 0:
            return None
        return await self.get_ticket(ticket_id, tenant_id=tenant_id)

    # ── Attachments ───────────────────────────────────────────────────────────

    async def add_attachment(
        self,
        ticket_id: str,
        filename: str,
        size: int,
        mimetype: str,
        stored_as: str,
        uploaded_by: str,
        tenant_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        db    = get_database()
        self._require_tenant(tenant_id)
        query = {"id": ticket_id, "tenantId": tenant_id}
        att = {
            "id":          str(uuid.uuid4()),
            "filename":    filename,
            "size":        size,
            "mimetype":    mimetype,
            "stored_as":   stored_as,
            "uploaded_by": uploaded_by,
            "created_at":  _now(),
        }
        history = self._history_entry(uploaded_by, "attachment_added", {"filename": filename})
        result  = await db[self.COL].update_one(
            query,
            {"$push": {"attachments": att, "history": history}, "$set": {"updated_at": _now()}},
        )
        if result.matched_count == 0:
            return None
        return att

    async def remove_attachment(
        self,
        ticket_id: str,
        attachment_id: str,
        actor: str,
        tenant_id: str = "",
    ) -> bool:
        db    = get_database()
        self._require_tenant(tenant_id)
        query = {"id": ticket_id, "tenantId": tenant_id}
        history = self._history_entry(actor, "attachment_removed", {"attachment_id": attachment_id})
        result  = await db[self.COL].update_one(
            query,
            {
                "$pull": {"attachments": {"id": attachment_id}},
                "$push": {"history": history},
                "$set":  {"updated_at": _now()},
            },
        )
        return result.matched_count > 0

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_ticket(self, ticket_id: str, tenant_id: str = "") -> bool:
        db    = get_database()
        self._require_tenant(tenant_id)
        query = {"id": ticket_id, "tenantId": tenant_id}
        result = await db[self.COL].delete_one(query)
        return result.deleted_count > 0


tickets_service = TicketsService()
