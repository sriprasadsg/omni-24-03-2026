"""Questionnaire Engine — create, distribute, and collect structured surveys."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

_Q_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}
_Q_TYPES = {"Vendor", "Internal", "Gap Analysis", "Security Assessment", "Audit"}
_Q_STATUSES = {"Draft", "Active", "Closed"}
_QUESTION_TYPES = {"text", "yes_no", "multiple_choice", "scale", "date", "file"}


class QuestionnaireService:
    def _db(self):
        from database import get_database
        return get_database()

    async def list_questionnaires(self, tenant_id: Optional[str], role: str) -> List[Dict]:
        db = self._db()
        query: Dict[str, Any] = {} if role in _Q_SUPER_ROLES else {"tenantId": tenant_id}
        return await db.questionnaires.find(query, {"_id": 0}).sort("created_at", -1).to_list(length=500)

    async def create_questionnaire(self, data: Dict[str, Any], tenant_id: str, created_by: str) -> Dict:
        db = self._db()
        now = datetime.now(timezone.utc).isoformat()
        questions = data.get("questions") or []
        for q in questions:
            if "id" not in q:
                q["id"] = str(uuid.uuid4())
        doc = {
            "id": f"qn-{uuid.uuid4().hex}",
            "tenantId": tenant_id,
            "title": data["title"],
            "description": data.get("description", ""),
            "type": data.get("type", "Internal"),
            "questions": questions,
            "status": "Draft",
            "createdBy": created_by,
            "created_at": now,
            "updated_at": now,
            "responseCount": 0,
        }
        await db.questionnaires.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def get_questionnaire(self, qid: str, tenant_id: Optional[str], role: str) -> Optional[Dict]:
        db = self._db()
        query: Dict[str, Any] = {"id": qid}
        if role not in _Q_SUPER_ROLES:
            query["tenantId"] = tenant_id
        return await db.questionnaires.find_one(query, {"_id": 0})

    async def update_questionnaire(self, qid: str, data: Dict[str, Any], tenant_id: Optional[str], role: str) -> Optional[Dict]:
        db = self._db()
        query: Dict[str, Any] = {"id": qid}
        if role not in _Q_SUPER_ROLES:
            query["tenantId"] = tenant_id
        allowed = {"title", "description", "type", "questions", "status"}
        patch = {k: v for k, v in data.items() if k in allowed}
        if not patch:
            return await db.questionnaires.find_one(query, {"_id": 0})
        if "questions" in patch:
            for q in patch["questions"]:
                if "id" not in q:
                    q["id"] = str(uuid.uuid4())
        patch["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.questionnaires.update_one(query, {"$set": patch})
        return await db.questionnaires.find_one(query, {"_id": 0})

    async def send_questionnaire(self, qid: str, emails: List[str], tenant_id: str, role: str) -> Dict:
        """Mark questionnaire Active and create pending response slots."""
        db = self._db()
        query: Dict[str, Any] = {"id": qid}
        if role not in _Q_SUPER_ROLES:
            query["tenantId"] = tenant_id
        now = datetime.now(timezone.utc).isoformat()
        await db.questionnaires.update_one(query, {"$set": {"status": "Active", "updated_at": now}})
        tokens = []
        for email in emails:
            token = uuid.uuid4().hex
            await db.questionnaire_responses.insert_one({
                "id": f"qr-{uuid.uuid4().hex}",
                "questionnaireId": qid,
                "tenantId": tenant_id,
                "respondentEmail": email,
                "token": token,
                "answers": {},
                "status": "Pending",
                "created_at": now,
                "updated_at": now,
            })
            tokens.append({"email": email, "token": token})
        return {"sent": len(emails), "tokens": tokens}

    async def get_responses(self, qid: str, tenant_id: Optional[str], role: str) -> List[Dict]:
        db = self._db()
        query: Dict[str, Any] = {"questionnaireId": qid}
        if role not in _Q_SUPER_ROLES:
            query["tenantId"] = tenant_id
        return await db.questionnaire_responses.find(query, {"_id": 0, "token": 0}).to_list(length=1000)

    async def submit_response(self, qid: str, token: str, answers: Dict[str, Any]) -> Optional[Dict]:
        db = self._db()
        now = datetime.now(timezone.utc).isoformat()
        result = await db.questionnaire_responses.find_one_and_update(
            {"questionnaireId": qid, "token": token, "status": "Pending"},
            {"$set": {"answers": answers, "status": "Submitted", "submitted_at": now, "updated_at": now}},
            return_document=True,
        )
        if result:
            await db.questionnaires.update_one(
                {"id": qid}, {"$inc": {"responseCount": 1}}
            )
            result.pop("_id", None)
            result.pop("token", None)
        return result

    async def delete_questionnaire(self, qid: str, tenant_id: Optional[str], role: str) -> bool:
        db = self._db()
        query: Dict[str, Any] = {"id": qid}
        if role not in _Q_SUPER_ROLES:
            query["tenantId"] = tenant_id
        res = await db.questionnaires.delete_one(query)
        if res.deleted_count:
            await db.questionnaire_responses.delete_many({"questionnaireId": qid})
        return res.deleted_count > 0

    async def get_stats(self, qid: str, tenant_id: Optional[str], role: str) -> Dict:
        responses = await self.get_responses(qid, tenant_id, role)
        total = len(responses)
        submitted = sum(1 for r in responses if r.get("status") == "Submitted")
        return {"total": total, "submitted": submitted, "pending": total - submitted, "responseRate": round(submitted / max(total, 1) * 100)}


questionnaire_service = QuestionnaireService()
