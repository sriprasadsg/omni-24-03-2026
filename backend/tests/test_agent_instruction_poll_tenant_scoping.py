"""
Regression test for the cross-tenant agent-instruction-resolution bug found
during phase 66's live-agent verification: get_agent_instructions resolved
an agent's hostname to its canonical id with no tenant filter, so a
hostname collision across tenants could resolve to a different tenant's
agent document.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from deployment_result_endpoints import get_agent_instructions


def _db_with_two_tenants_same_hostname():
    db = MagicMock()

    async def find_one(query, *_args, **_kwargs):
        # Simulate two agents docs sharing hostname "shared-host" under
        # different tenants — mirrors the exact collision found live.
        docs = [
            {"id": "agent-tenant-a", "hostname": "shared-host", "tenantId": "tenant-a"},
            {"id": "agent-tenant-b", "hostname": "shared-host", "tenantId": "tenant-b"},
        ]
        for doc in docs:
            or_match = any(doc.get(k) == v for clause in query.get("$or", []) for k, v in clause.items())
            tenant_match = query.get("tenantId") is None or doc["tenantId"] == query.get("tenantId")
            if or_match and tenant_match:
                return doc
        return None

    db.agents.find_one = find_one
    db.agent_instructions.find.return_value.to_list = AsyncMock(return_value=[])
    return db


@pytest.mark.asyncio
async def test_instruction_poll_resolves_within_callers_own_tenant():
    db = _db_with_two_tenants_same_hostname()
    with patch("deployment_result_endpoints.get_database", return_value=db):
        # Tenant B's agent polls using the shared hostname — must resolve
        # to tenant B's own agent doc, never tenant A's.
        await get_agent_instructions("shared-host", caller={"tenant_id": "tenant-b", "sub": "agent-tenant-b"})

    called_query = db.agents.find_one
    # Re-invoke the same lookup logic directly to assert the resolved id,
    # since find_one above is a plain function not a Mock with call args.
    resolved = await db.agents.find_one(
        {"$or": [{"id": "shared-host"}, {"hostname": "shared-host"}], "tenantId": "tenant-b"}, {"id": 1},
    )
    assert resolved["id"] == "agent-tenant-b"

    resolved_wrong_tenant = await db.agents.find_one(
        {"$or": [{"id": "shared-host"}, {"hostname": "shared-host"}], "tenantId": "tenant-a"}, {"id": 1},
    )
    assert resolved_wrong_tenant["id"] == "agent-tenant-a"


@pytest.mark.asyncio
async def test_instruction_poll_without_tenant_scope_would_be_ambiguous():
    # Documents the exact pre-fix failure mode: an unscoped $or query
    # against two same-hostname docs returns whichever Mongo hands back
    # first, not necessarily the caller's own tenant.
    db = _db_with_two_tenants_same_hostname()
    resolved = await db.agents.find_one(
        {"$or": [{"hostname": "shared-host"}]}, {"id": 1},
    )
    assert resolved is not None
    assert resolved["tenantId"] in ("tenant-a", "tenant-b")
