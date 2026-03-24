from fastapi import APIRouter, Depends
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
        # Reusing list_models as it likely serves the same purpose
        tenant_id = current_user.tenant_id if current_user.tenant_id else "default"
        return await service.list_models(tenant_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
