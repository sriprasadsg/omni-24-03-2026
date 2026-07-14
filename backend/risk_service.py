import numpy as np
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
    # New residual fields per RISK-01
    inherent_likelihood: Optional[int] = None
    inherent_impact: Optional[int] = None
    inherent_risk_score: Optional[int] = None
    residual_likelihood: Optional[int] = None
    residual_impact: Optional[int] = None
    residual_risk_score: Optional[int] = None
    fair_inputs: Optional[Dict[str, Any]] = None
    fair_results: Optional[Dict[str, Any]] = None

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
        # Handle inherent values (risk_data fields)
        inherent_likelihood = int(risk_data.get("inherent_likelihood", risk_data.get("likelihood", 1)))
        inherent_impact = int(risk_data.get("inherent_impact", risk_data.get("impact", 1)))
        inherent_risk_score = inherent_likelihood * inherent_impact

        # Handle residual values (risk_data fields) - additive only, default to inherent
        residual_likelihood = int(risk_data.get("residual_likelihood", inherent_likelihood))
        residual_impact = int(risk_data.get("residual_impact", inherent_impact))
        residual_risk_score = residual_likelihood * residual_impact

        likelihood = int(risk_data.get("likelihood", 1))
        impact = int(risk_data.get("impact", 1))
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": str(uuid.uuid4()),
            "created_at": now,
            "updated_at": now,
            "risk_score": likelihood * impact,
            "inherent_likelihood": inherent_likelihood,
            "inherent_impact": inherent_impact,
            "inherent_risk_score": inherent_risk_score,
            "residual_likelihood": residual_likelihood,
            "residual_impact": residual_impact,
            "residual_risk_score": residual_risk_score,
            **risk_data,
        }
        # Preserve existing fields
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

        # Determine if residual values are being changed
        has_residual_update = "residual_likelihood" in updates or "residual_impact" in updates

        # Preserve existing inherent values if not being updated
        inherent_likelihood = updates.get("inherent_likelihood", existing.get("inherent_likelihood", 1))
        inherent_impact = updates.get("inherent_impact", existing.get("inherent_impact", 1))
        inherent_risk_score = inherent_likelihood * inherent_impact

        # Preserve existing residual values if not being updated
        residual_likelihood = updates.get("residual_likelihood", existing.get("residual_likelihood", inherent_likelihood))
        residual_impact = updates.get("residual_impact", existing.get("residual_impact", inherent_impact))
        residual_risk_score = residual_likelihood * residual_impact

        merged = {**existing, **updates, "updated_at": datetime.now(timezone.utc).isoformat()}
        # Recompute risk_score if likelihood/impact changed
        if "likelihood" in updates or "impact" in updates:
            merged["risk_score"] = merged.get("likelihood", existing["likelihood"]) * merged.get("impact", existing["impact"])

        # Update inherent/residual fields
        merged["inherent_likelihood"] = inherent_likelihood
        merged["inherent_impact"] = inherent_impact
        merged["inherent_risk_score"] = inherent_risk_score
        merged["residual_likelihood"] = residual_likelihood
        merged["residual_impact"] = residual_impact
        merged["residual_risk_score"] = residual_risk_score

        await db.risks.replace_one(filt, merged)
        return merged

    async def attach_fair_results(
        self,
        risk_id: str,
        fair_inputs: Dict[str, Any],
        fair_results: Dict[str, Any],
        tenant_id: Optional[str] = None,
        role: str = "",
    ) -> Optional[Dict]:
        """Persist a FAIR simulation's inputs and results onto a risk.

        Tenant-scoped identically to update_risk: non-super roles can only touch
        risks in their own tenant. Returns the updated risk, or None if not found.
        """
        db = self._db()
        filt: Dict[str, Any] = {"id": risk_id}
        if role not in _RISK_SUPER_ROLES:
            filt["tenantId"] = tenant_id
        existing = await db.risks.find_one(filt, {"_id": 0})
        if not existing:
            return None
        merged = {
            **existing,
            "fair_inputs": fair_inputs,
            "fair_results": fair_results,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.risks.replace_one(filt, merged)
        return merged

    async def delete_risk(self, risk_id: str, tenant_id: Optional[str] = None, role: str = "") -> bool:
        db = self._db()
        filt: Dict[str, Any] = {"id": risk_id}
        if role not in _RISK_SUPER_ROLES:
            filt["tenantId"] = tenant_id
        result = await db.risks.delete_one(filt)
        return result.deleted_count > 0


risk_service = RiskService()