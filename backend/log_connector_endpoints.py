"""Cloud log connector routes (log_connectors, Wave 3) under the SOC console: /api/security/soc/log-sources.

Reading needs the Security Overview screen; connecting, removing and pulling also need manage:automation (the same as
SIEM rules and paging). A tenant user acts on their organization; a Super Admin on the one they are viewing, else the
platform's own.
"""
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException

from auth_types import TokenData
from authentication_service import get_current_user
from catalogue_mounts_secops import SECURITY_GUARD
from database import get_database
from rbac_utils import require_permission
import log_connectors
from soc_endpoints import soc_scope

router = APIRouter(prefix="/api/security/soc/log-sources", tags=["SOC"], dependencies=[Depends(SECURITY_GUARD)])
WRITE = [Depends(require_permission("manage:automation"))]


def _scope(user: TokenData) -> str:
    return soc_scope(user) or "platform-admin"


async def _run(coro):
    try:
        return await coro
    except log_connectors.ConnectorError as e:
        raise HTTPException(status_code=e.status, detail=str(e))


@router.get("")
async def list_log_sources(current_user: TokenData = Depends(get_current_user)):
    """Each cloud log connector: its settings without the secret, and its last run, success and error."""
    return await log_connectors.list_config(get_database(), _scope(current_user))


@router.put("/{provider}", dependencies=WRITE)
async def save_log_source(provider: str, body: Dict[str, Any] = Body(...), current_user: TokenData = Depends(get_current_user)):
    return await _run(log_connectors.save_config(get_database(), _scope(current_user), provider, body, current_user.username))


@router.delete("/{provider}", dependencies=WRITE)
async def remove_log_source(provider: str, current_user: TokenData = Depends(get_current_user)):
    await _run(log_connectors.remove(get_database(), _scope(current_user), provider, current_user.username))
    return {"connected": False}


@router.post("/{provider}/pull", dependencies=WRITE)
async def pull_log_source(provider: str, current_user: TokenData = Depends(get_current_user)):
    """Pull now instead of waiting for the next five-minute run; says how many events were new and how many rules hit."""
    return await _run(log_connectors.pull_now(get_database(), _scope(current_user), provider, current_user.username))
