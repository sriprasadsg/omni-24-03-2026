"""Cloud Accounts API — register, scan, summary, org discovery."""
from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Any, Dict
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
import cloud_accounts_service as svc
import logging

router = APIRouter(prefix="/api/cloud-accounts", tags=["Cloud Accounts"])
logger = logging.getLogger(__name__)


def _tid(user: TokenData) -> str:
    return getattr(user, "tenant_id", None) or ""


@router.get("")
async def list_accounts(current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    items = await svc.list_accounts(db, _tid(current_user))
    return {"items": items, "count": len(items)}


@router.post("")
async def register_account(payload: Dict[str, Any] = Body(...), current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    if not payload.get("provider") or not payload.get("account_id"):
        raise HTTPException(status_code=400, detail="provider and account_id required")
    doc = await svc.register_account(db, _tid(current_user), payload)
    return {"account": doc}


@router.post("/{account_id}/scan")
async def scan_account(account_id: str, current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    result = await svc.scan_account(db, account_id, _tid(current_user))
    return result


@router.get("/{account_id}/results")
async def get_account_results(account_id: str, current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    items = await svc.get_results(db, account_id, _tid(current_user))
    return {"items": items, "count": len(items)}


@router.get("/summary")
async def get_summary(current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    summary = await svc.get_summary(db, _tid(current_user))
    return summary


@router.post("/discover-org")
async def discover_org(payload: Dict[str, Any] = Body(...), current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    result = await svc.discover_org_accounts(db, _tid(current_user), payload)
    return result
