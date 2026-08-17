"""Periodic Access Review service — schedule, conduct, and close structured access reviews."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import uuid

_AR_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}
_FREQUENCIES = {"Weekly": 7, "Monthly": 30, "Quarterly": 90, "Semi-Annual": 180, "Annual": 365}
_AR_TYPES = {"User Access", "Privileged Access", "Vendor Access", "Application Access", "Service Account"}
_AR_STATUSES = {"Scheduled", "In Progress", "Completed", "Overdue", "Cancelled"}
_DECISIONS = {"Approved", "Revoked", "Modified", "Deferred"}


def _compute_next_date(frequency: str) -> str:
    days = _FREQUENCIES.get(frequency, 90)
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


class AccessReviewService:
    def _db(self):
        from database import get_database
        return get_database()

    async def list_reviews(self, tenant_id: Optional[str], role: str, status: Optional[str] = None) -> List[Dict]:
        db = self._db()
        query: Dict[str, Any] = {} if role in _AR_SUPER_ROLES else {"tenantId": tenant_id}
        if status:
            query["status"] = status
        reviews = await db.access_reviews.find(query, {"_id": 0}).sort("nextReviewDate", 1).to_list(length=1000)
        now = datetime.now(timezone.utc).isoformat()
        updated = []
        for r in reviews:
            if r.get("status") == "Scheduled" and r.get("nextReviewDate", "") < now:
                await db.access_reviews.update_one({"id": r["id"]}, {"$set": {"status": "Overdue"}})
                r["status"] = "Overdue"
            updated.append(r)
        return updated

    async def create_review(self, data: Dict[str, Any], tenant_id: str, created_by: str) -> Dict:
        db = self._db()
        now = datetime.now(timezone.utc).isoformat()
        frequency = data.get("frequency", "Quarterly")
        next_date = data.get("nextReviewDate") or _compute_next_date(frequency)
        scope_users = data.get("scopeUsers", [])
        doc = {
            "id": f"ar-{uuid.uuid4().hex}",
            "tenantId": tenant_id,
            "name": data["name"],
            "description": data.get("description", ""),
            "type": data.get("type", "User Access"),
            "frequency": frequency,
            "status": "Scheduled",
            "reviewer": data.get("reviewer", created_by),
            "nextReviewDate": next_date,
            "scopeUsers": scope_users,
            "decisions": [],
            "createdBy": created_by,
            "created_at": now,
            "updated_at": now,
        }
        await db.access_reviews.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def get_review(self, review_id: str, tenant_id: Optional[str], role: str) -> Optional[Dict]:
        db = self._db()
        query: Dict[str, Any] = {"id": review_id}
        if role not in _AR_SUPER_ROLES:
            query["tenantId"] = tenant_id
        return await db.access_reviews.find_one(query, {"_id": 0})

    async def start_review(self, review_id: str, tenant_id: Optional[str], role: str) -> Optional[Dict]:
        db = self._db()
        query: Dict[str, Any] = {"id": review_id, "status": {"$in": ["Scheduled", "Overdue"]}}
        if role not in _AR_SUPER_ROLES:
            query["tenantId"] = tenant_id
        now = datetime.now(timezone.utc).isoformat()
        await db.access_reviews.update_one(query, {"$set": {"status": "In Progress", "startedAt": now, "updated_at": now}})
        return await db.access_reviews.find_one({"id": review_id}, {"_id": 0})

    async def submit_decisions(self, review_id: str, decisions: List[Dict], tenant_id: Optional[str], role: str) -> Optional[Dict]:
        db = self._db()
        query: Dict[str, Any] = {"id": review_id}
        if role not in _AR_SUPER_ROLES:
            query["tenantId"] = tenant_id
        now = datetime.now(timezone.utc).isoformat()
        validated = []
        for d in decisions:
            if d.get("decision") not in _DECISIONS:
                continue
            validated.append({
                "userId": d.get("userId", ""),
                "userName": d.get("userName", ""),
                "decision": d["decision"],
                "reason": d.get("reason", ""),
                "decidedAt": now,
            })
        if validated:
            await db.access_reviews.update_one(
                query,
                {"$set": {"decisions": validated, "status": "In Progress", "updated_at": now}},
            )
        return await db.access_reviews.find_one({"id": review_id}, {"_id": 0})

    async def complete_review(self, review_id: str, tenant_id: Optional[str], role: str) -> Optional[Dict]:
        db = self._db()
        query: Dict[str, Any] = {"id": review_id}
        if role not in _AR_SUPER_ROLES:
            query["tenantId"] = tenant_id
        review = await db.access_reviews.find_one(query, {"_id": 0})
        if not review:
            return None
        now = datetime.now(timezone.utc).isoformat()
        frequency = review.get("frequency", "Quarterly")
        next_date = _compute_next_date(frequency)
        await db.access_reviews.update_one(
            query,
            {"$set": {"status": "Completed", "completedAt": now, "nextReviewDate": next_date, "updated_at": now}},
        )
        await db.access_review_history.insert_one({
            "id": f"arh-{uuid.uuid4().hex}",
            "reviewId": review_id,
            "tenantId": review.get("tenantId"),
            "completedAt": now,
            "decisions": review.get("decisions", []),
            "revokedCount": sum(1 for d in review.get("decisions", []) if d.get("decision") == "Revoked"),
        })
        return await db.access_reviews.find_one({"id": review_id}, {"_id": 0})

    async def get_upcoming(self, tenant_id: Optional[str], role: str, days: int = 30) -> List[Dict]:
        db = self._db()
        cutoff = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        query: Dict[str, Any] = {"status": "Scheduled", "nextReviewDate": {"$lte": cutoff}}
        if role not in _AR_SUPER_ROLES:
            query["tenantId"] = tenant_id
        return await db.access_reviews.find(query, {"_id": 0}).sort("nextReviewDate", 1).to_list(length=200)

    async def get_summary(self, tenant_id: Optional[str], role: str) -> Dict:
        reviews = await self.list_reviews(tenant_id, role)
        by_status: Dict[str, int] = {}
        for r in reviews:
            s = r.get("status", "Unknown")
            by_status[s] = by_status.get(s, 0) + 1
        overdue = by_status.get("Overdue", 0)
        upcoming_count = len(await self.get_upcoming(tenant_id, role))
        return {
            "total": len(reviews),
            "byStatus": by_status,
            "overdue": overdue,
            "upcomingNext30Days": upcoming_count,
        }

    async def delete_review(self, review_id: str, tenant_id: Optional[str], role: str) -> bool:
        db = self._db()
        query: Dict[str, Any] = {"id": review_id}
        if role not in _AR_SUPER_ROLES:
            query["tenantId"] = tenant_id
        res = await db.access_reviews.delete_one(query)
        return res.deleted_count > 0


access_review_service = AccessReviewService()
