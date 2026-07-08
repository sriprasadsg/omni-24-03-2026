"""Vendor Risk Management Service — persists to MongoDB."""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import uuid
from database import get_database

_VENDOR_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin", "admin"}


class VendorAssessment(BaseModel):
    id: str
    vendor_id: str
    assessment_date: str
    reviewer: str
    risk_score: int
    status: str
    questionnaire_responses: Dict[str, Any]
    findings: List[str]


class Vendor(BaseModel):
    id: str
    name: str
    website: str
    criticality: str
    category: str
    contact_name: str
    contact_email: str
    contract_start: str
    contract_end: str
    status: str
    assessments: List[dict] = []
    linked_sboms: List[str] = []


class VendorService:
    def _scope(self, role: str, tenant_id: Optional[str]) -> dict:
        if role in _VENDOR_SUPER_ROLES:
            return {}
        return {"tenantId": tenant_id} if tenant_id else {}

    async def get_all_vendors(self, tenant_id: Optional[str] = None, role: str = "") -> List[Dict]:
        db = get_database()
        return await db.vendors.find(self._scope(role, tenant_id), {"_id": 0}).to_list(length=500)

    async def get_vendor(self, vendor_id: str, tenant_id: Optional[str] = None, role: str = "") -> Optional[Dict]:
        db = get_database()
        return await db.vendors.find_one({"id": vendor_id, **self._scope(role, tenant_id)}, {"_id": 0})

    async def create_vendor(self, vendor_data: Dict[str, Any], tenant_id: Optional[str] = None) -> Dict:
        db = get_database()
        doc = {
            "id": str(uuid.uuid4()),
            "tenantId": tenant_id,
            "assessments": [],
            "linked_sboms": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            **{k: v for k, v in vendor_data.items() if k not in ("id", "tenantId", "_id")},
        }
        await db.vendors.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def update_vendor(self, vendor_id: str, updates: Dict[str, Any], tenant_id: Optional[str] = None, role: str = "") -> Optional[Dict]:
        db = get_database()
        filt = {"id": vendor_id, **self._scope(role, tenant_id)}
        safe_updates = {k: v for k, v in updates.items() if k not in ("id", "tenantId", "_id")}
        result = await db.vendors.update_one(filt, {"$set": safe_updates})
        if result.matched_count == 0:
            return None
        return await db.vendors.find_one(filt, {"_id": 0})

    async def delete_vendor(self, vendor_id: str, tenant_id: Optional[str] = None, role: str = "") -> bool:
        db = get_database()
        result = await db.vendors.delete_one({"id": vendor_id, **self._scope(role, tenant_id)})
        return result.deleted_count > 0

    async def add_assessment(self, vendor_id: str, assessment_data: Dict[str, Any], tenant_id: Optional[str] = None, role: str = "") -> Optional[Dict]:
        db = get_database()
        filt = {"id": vendor_id, **self._scope(role, tenant_id)}
        vendor = await db.vendors.find_one(filt)
        if not vendor:
            return None
        assessment = {
            "id": str(uuid.uuid4()),
            "vendor_id": vendor_id,
            "status": "Completed",
            **assessment_data,
        }
        await db.vendors.update_one(filt, {"$push": {"assessments": assessment}})
        return assessment

    async def calculate_risk_score(self, vendor_id: str, tenant_id: Optional[str] = None, role: str = "") -> int:
        vendor = await self.get_vendor(vendor_id, tenant_id=tenant_id, role=role)
        if not vendor:
            return 0
        criticality_map = {"Low": 20, "Medium": 40, "High": 70, "Critical": 100}
        base_risk = criticality_map.get(vendor.get("criticality", ""), 50)
        assessments = vendor.get("assessments", [])
        if not assessments:
            return base_risk
        return int(assessments[-1].get("risk_score", base_risk))

    async def get_portfolio_summary(self, tenant_id: Optional[str] = None, role: str = "") -> Dict[str, Any]:
        db = get_database()
        all_vendors = await db.vendors.find(
            self._scope(role, tenant_id), {"_id": 0, "id": 1, "criticality": 1, "assessments": 1}
        ).to_list(length=500)
        total = len(all_vendors)
        if total == 0:
            return {"total_vendors": 0, "avg_risk": 0, "critical_vendors": 0}

        criticality_map = {"Low": 20, "Medium": 40, "High": 70, "Critical": 100}
        risk_scores = []
        for v in all_vendors:
            assessments = v.get("assessments", [])
            if assessments:
                risk_scores.append(int(assessments[-1].get("risk_score", 50)))
            else:
                risk_scores.append(criticality_map.get(v.get("criticality", ""), 50))

        avg_risk = sum(risk_scores) / total
        critical_count = sum(1 for s in risk_scores if s >= 80)

        return {
            "total_vendors": total,
            "avg_risk": round(avg_risk, 1),
            "critical_vendors": critical_count,
            "by_criticality": {
                "Critical": sum(1 for v in all_vendors if v.get("criticality") == "Critical"),
                "High": sum(1 for v in all_vendors if v.get("criticality") == "High"),
                "Medium": sum(1 for v in all_vendors if v.get("criticality") == "Medium"),
                "Low": sum(1 for v in all_vendors if v.get("criticality") == "Low"),
            },
        }

    async def add_subprocessor(self, vendor_id: str, subprocessor_data: Dict[str, Any], tenant_id: Optional[str] = None, role: str = "") -> Optional[Dict]:
        db = get_database()
        filt = {"id": vendor_id, **self._scope(role, tenant_id)}
        vendor = await db.vendors.find_one(filt)
        if not vendor:
            return None
        sp = {
            "id": str(uuid.uuid4()),
            **subprocessor_data,
        }
        await db.vendors.update_one(filt, {"$push": {"subprocessors": sp}})
        return sp

    async def remove_subprocessor(self, vendor_id: str, subprocessor_id: str, tenant_id: Optional[str] = None, role: str = "") -> bool:
        db = get_database()
        filt = {"id": vendor_id, **self._scope(role, tenant_id)}
        result = await db.vendors.update_one(filt, {"$pull": {"subprocessors": {"id": subprocessor_id}}})
        return result.matched_count > 0

    async def get_subprocessors(self, vendor_id: str, tenant_id: Optional[str] = None, role: str = "") -> List[Dict]:
        db = get_database()
        vendor = await db.vendors.find_one({"id": vendor_id, **self._scope(role, tenant_id)}, {"_id": 0, "subprocessors": 1})
        if not vendor:
            return []
        return vendor.get("subprocessors", [])

    async def add_document(self, vendor_id: str, doc_data: Dict[str, Any], tenant_id: Optional[str] = None, role: str = "") -> bool:
        db = get_database()
        doc = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **doc_data,
        }
        filt = {"id": vendor_id, **self._scope(role, tenant_id)}
        result = await db.vendors.update_one(filt, {"$push": {"documents": doc}})
        return result.matched_count > 0


vendor_service = VendorService()
