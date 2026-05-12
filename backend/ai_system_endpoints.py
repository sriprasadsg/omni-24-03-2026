from fastapi import APIRouter, Depends, HTTPException
from typing import List
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from ai_governance_service import get_ai_governance_service

router = APIRouter(prefix="/api/ai-systems", tags=["AI Systems"])

@router.get("")
async def list_ai_systems(current_user: TokenData = Depends(get_current_user)):
    """List all AI systems (models)"""
    try:
        db = get_database()
        service = get_ai_governance_service(db)
        tenant_id = current_user.tenant_id if current_user.tenant_id else "default"
        return await service.list_models(tenant_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{system_id}/risks")
async def get_system_risks(system_id: str, current_user: TokenData = Depends(get_current_user)):
    """Get risks associated with a specific AI system"""
    try:
        db = get_database()
        system = await db.ai_systems.find_one({"id": system_id}, {"_id": 0})
        if not system:
            return []
        risks = system.get("risks", [])
        # Also check standalone risk_assessments collection
        standalone = await db.ai_risk_assessments.find(
            {"system_id": system_id}, {"_id": 0}
        ).to_list(length=200)
        # Merge, deduplicate by id
        seen = {r["id"] for r in risks if "id" in r}
        for r in standalone:
            if r.get("id") not in seen:
                risks.append(r)
                seen.add(r.get("id"))
        return risks
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
