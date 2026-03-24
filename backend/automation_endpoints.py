from fastapi import APIRouter, Depends
from typing import List
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/automation-policies", tags=["Automation"])

@router.get("")
async def get_automation_policies(current_user: TokenData = Depends(get_current_user)):
    """Get automation policies"""
    db = get_database()
    policies = await db.automation_policies.find({}, {"_id": 0}).to_list(length=100)
    return policies
