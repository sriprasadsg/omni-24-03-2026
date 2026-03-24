from fastapi import APIRouter, Depends
from typing import List
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/cloud-accounts", tags=["Cloud Accounts"])

@router.get("")
async def get_cloud_accounts(current_user: TokenData = Depends(get_current_user)):
    """Get all cloud accounts"""
    db = get_database()
    accounts = await db.cloud_accounts.find({}, {"_id": 0}).to_list(length=100)
    return accounts
