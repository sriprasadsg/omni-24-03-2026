"""Cloud Accounts API — register, scan, summary, org discovery."""
from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Any, Dict
from database import get_database
from auth_types import TokenData
from rbac_service import rbac_service
import cloud_accounts_service as svc
import logging

router = APIRouter(prefix="/api/cloud-accounts", tags=["Cloud Accounts"])
logger = logging.getLogger(__name__)

_VALID_PROVIDERS = {"aws", "azure", "gcp", "kubernetes", "digitalocean", "microsoft365", "mongodb_atlas", "oci", "alibaba", "cloudflare"}
_VALID_ENVS = {"prod", "staging", "dev"}


def _tid(user: TokenData) -> str:
    return getattr(user, "tenant_id", None) or ""


@router.get("")
async def list_accounts(
    skip: int = 0,
    limit: int = 100,
    current_user: TokenData = Depends(rbac_service.has_permission("view:cloud_security")),
):
    db = get_database()
    skip = max(0, skip)
    limit = max(1, min(limit, 500))
    items = await svc.list_accounts(db, _tid(current_user), skip=skip, limit=limit)
    total_count = await svc.count_accounts(db, _tid(current_user))
    return {"items": items, "count": len(items), "total_count": total_count}


@router.post("")
async def register_account(payload: Dict[str, Any] = Body(...), current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    db = get_database()
    if not payload.get("provider") or not payload.get("account_id"):
        raise HTTPException(status_code=400, detail="provider and account_id required")
    if not isinstance(payload.get("account_id"), str):
        raise HTTPException(status_code=400, detail="account_id must be a non-empty string")
    if payload.get("provider") not in _VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"provider must be one of {sorted(_VALID_PROVIDERS)}")
    if payload.get("environment", "dev") not in _VALID_ENVS:
        raise HTTPException(status_code=400, detail=f"environment must be one of {sorted(_VALID_ENVS)}")
    if payload.get("credentials_ref") is not None and not isinstance(payload["credentials_ref"], str):
        raise HTTPException(status_code=400, detail="credentials_ref must be a string")
    doc = await svc.register_account(db, _tid(current_user), payload)
    return {"account": doc}


@router.post("/{account_id}/scan")
async def scan_account(account_id: str, current_user: TokenData = Depends(rbac_service.has_permission("view:cloud_security"))):
    db = get_database()
    result = await svc.scan_account(db, account_id, _tid(current_user))
    if result.get("error"):
        status_code = 404 if result["error"] == "Cloud account not found" else 502
        raise HTTPException(status_code=status_code, detail=result["error"])
    return result


@router.get("/{account_id}/results")
async def get_account_results(account_id: str, current_user: TokenData = Depends(rbac_service.has_permission("view:cloud_security"))):
    db = get_database()
    items = await svc.get_results(db, account_id, _tid(current_user))
    return {"items": items, "count": len(items)}


@router.get("/summary")
async def get_summary(current_user: TokenData = Depends(rbac_service.has_permission("view:cloud_security"))):
    db = get_database()
    summary = await svc.get_summary(db, _tid(current_user))
    return summary


@router.post("/discover-org")
async def discover_org(payload: Dict[str, Any] = Body(...), current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    # discover_org_accounts() is currently a stub simulation (real impl calls AWS
    # Organizations ListAccounts) that ignores this payload's contents entirely —
    # this check only pins the contract shape so validation doesn't need to be
    # retrofitted later when the real integration replaces the stub.
    if not payload.get("management_account_id"):
        raise HTTPException(status_code=400, detail="management_account_id required")
    db = get_database()
    result = await svc.discover_org_accounts(db, _tid(current_user), payload)
    return result
