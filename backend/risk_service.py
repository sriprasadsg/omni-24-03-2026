from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import uuid

class Risk(BaseModel):
    id: str
    title: str
    description: str
    category: str  # Enterprise, AI, Compliance, Third-Party, Cyber
    status: str  # Open, Mitigated, Accepted, Transferred, Avoided
    likelihood: int  # 1-5
    impact: int  # 1-5
    risk_score: int  # likelihood * impact
    owner: str
    mitigation_plan: Optional[str] = None
    created_at: str
    updated_at: str

    # AI Specific
    ai_system_id: Optional[str] = None

    # Vendor Specific
    vendor_id: Optional[str] = None

_RISK_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}


class RiskService:
    def _db(self):
        from database import get_database
        return get_database()

    async def get_all_risks(self, tenant_id: Optional[str] = None, role: str = "") -> List[Dict]:
        db = self._db()
        query: Dict[str, Any] = {} if role in _RISK_SUPER_ROLES else {"tenantId": tenant_id}
        return await db.risks.find(query, {"_id": 0}).sort("created_at", -1).to_list(length=1000)

    async def create_risk(self, risk_data: Dict[str, Any], tenant_id: Optional[str] = None) -> Dict:
        db = self._db()
        likelihood = int(risk_data.get("likelihood", 1))
        impact = int(risk_data.get("impact", 1))
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": str(uuid.uuid4()),
            "created_at": now,
            "updated_at": now,
            "risk_score": likelihood * impact,
            **risk_data,
        }
        doc["likelihood"] = likelihood
        doc["impact"] = impact
        doc["tenantId"] = tenant_id
        await db.risks.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def update_risk(self, risk_id: str, updates: Dict[str, Any], tenant_id: Optional[str] = None, role: str = "") -> Optional[Dict]:
        db = self._db()
        filt: Dict[str, Any] = {"id": risk_id}
        if role not in _RISK_SUPER_ROLES:
            filt["tenantId"] = tenant_id
        existing = await db.risks.find_one(filt, {"_id": 0})
        if not existing:
            return None
        merged = {**existing, **updates, "updated_at": datetime.now(timezone.utc).isoformat()}
        if "likelihood" in updates or "impact" in updates:
            merged["risk_score"] = merged.get("likelihood", existing["likelihood"]) * merged.get("impact", existing["impact"])
        await db.risks.replace_one(filt, merged)
        return merged

    async def delete_risk(self, risk_id: str, tenant_id: Optional[str] = None, role: str = "") -> bool:
        db = self._db()
        filt: Dict[str, Any] = {"id": risk_id}
        if role not in _RISK_SUPER_ROLES:
            filt["tenantId"] = tenant_id
        result = await db.risks.delete_one(filt)
        return result.deleted_count > 0

# Singleton instance
risk_service = RiskService()
