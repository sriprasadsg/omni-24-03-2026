"""The shared register harness for every Phase 88 enrollment test (real MongoDB).

It calls the real ``register_agent`` route function with a settable client address, so network rules
can be tested without an HTTP layer. Limiters, the cost recalculation and the cache are patched out;
nothing here reaches the live database (the caller passes the private ``mongo_db`` fixture).
"""
import contextlib
import importlib
import sys
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

import agent_registry_endpoints as reg
from plan_service import PLATFORM_TENANT_ID  # noqa: F401  (re-exported for tests)

REG_KEY = "reg_0123456789abcdef0123"


def request(client_ip: str = "203.0.113.7") -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/agents/register", "headers": [],
                    "client": (client_ip, 5555)})


@contextlib.contextmanager
def register_patches(db):
    stub = MagicMock()
    stub.finops_service.recalculate_tenant_costs = AsyncMock()
    with patch.object(reg, "get_database", return_value=db), patch.object(reg.limiter, "enabled", False), \
            patch.object(reg, "invalidate_cache"), patch.dict(sys.modules, {"finops_service": stub}):
        yield


def hw(serial: str, uuid: Optional[str] = None, os_family: str = "windows") -> Dict[str, Any]:
    out = {"serialNumber": serial, "osFamily": os_family, "osName": "Windows 11 Pro", "deviceType": "laptop",
           "macAddresses": []}
    if uuid:
        out["smbiosUuid"] = uuid
    return out


async def register(db, hostname: str, key: str = REG_KEY, hardware: Optional[Dict[str, Any]] = None,
                   client_ip: str = "203.0.113.7", **body):
    """(status, body) of POST /api/agents/register; (status, detail) when refused."""
    payload = {"registrationKey": key, "hostname": hostname, "platform": "Windows", "version": "2.1.13",
               "supportsPending": True, **body}
    if hardware is not None:
        payload["hardware"] = hardware
    response = Response()
    with register_patches(db):
        try:
            out = await reg.register_agent(request(client_ip), response, payload, background_tasks=MagicMock())
        except HTTPException as exc:
            return exc.status_code, exc.detail
    return response.status_code, out


async def tenant(db, tenant_id: str, *, key: str = REG_KEY, plan: Optional[str] = "Free",
                 trial: Optional[Dict[str, Any]] = None, max_agents: int = 50, **extra) -> Dict[str, Any]:
    """Insert a tenant with a licence sub-document and give its registration key a Legacy install key
    (migration 013 is idempotent, so it runs after every insert). ``plan`` None leaves subscriptionTier
    off; ``trial`` None leaves the trial record off."""
    doc: Dict[str, Any] = {"id": tenant_id, "name": f"Org {tenant_id}", "registrationKey": key,
                           "license": {"maxAgents": max_agents, "seatsUsed": 0, "inactiveReclaimDays": 30}}
    if plan is not None:
        doc["subscriptionTier"] = plan
    if trial is not None:
        doc["trial"] = trial
    doc.update(extra)
    await db.tenants.insert_one(dict(doc))
    await importlib.import_module("migrations.013_enrollment_controls").up(db)
    return doc
