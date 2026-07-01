"""Cloud Security Checks Engine endpoints — Prowler-style checks for AWS, Azure, GCP."""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from pydantic import BaseModel
from authentication_service import get_current_user
from auth_types import TokenData
from cloud_checks_service import cloud_checks_service

router = APIRouter(prefix="/api/cloud-checks", tags=["Cloud Security Checks"])


def _tenant(user: TokenData) -> str:
    tid = getattr(user, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tid


def _role(user: TokenData) -> str:
    return getattr(user, "role", "")


class RunChecksPayload(BaseModel):
    accountId: str
    provider: str
    credentialsHint: Optional[str] = None


@router.get("")
async def list_checks(
    provider: Optional[str] = Query(None),
    service: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
):
    """List all available security check definitions."""
    return cloud_checks_service.list_checks(provider, service, severity)


@router.get("/summary")
async def get_summary(
    account_id: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
):
    return await cloud_checks_service.get_summary(_tenant(current_user), _role(current_user), account_id)


@router.get("/results")
async def get_results(
    provider: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
):
    return await cloud_checks_service.get_results(
        _tenant(current_user), _role(current_user), provider, account_id
    )


@router.get("/results/{account_id}")
async def get_account_results(
    account_id: str,
    provider: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
):
    return await cloud_checks_service.get_results(
        _tenant(current_user), _role(current_user), provider, account_id
    )


@router.post("/run")
async def run_checks(payload: RunChecksPayload, current_user: TokenData = Depends(get_current_user)):
    """Trigger check evaluation against a connected cloud account."""
    if payload.provider not in ("aws", "azure", "gcp"):
        raise HTTPException(status_code=400, detail="provider must be aws, azure, or gcp")
    return await cloud_checks_service.run_checks(
        payload.accountId, payload.provider, _tenant(current_user), payload.credentialsHint
    )
