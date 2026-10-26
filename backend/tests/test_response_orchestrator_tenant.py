"""Phase 81 plan 03 (GATE-11, T-81-11): ResponseOrchestrator.is_duplicate_task is scoped to
one tenant on both of its queries, and fails closed (treats the task as a duplicate) when
no tenant is given. Real MongoDB through a throwaway omni_test_* database."""
import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

from response_orchestrator import ResponseOrchestrator


def _task(tenant, agent="agent-x", action="kill_process", alert_type="malware", status="queued"):
    return {
        "task_id": f"RSP-{tenant}-{agent}",
        "tenantId": tenant,
        "agent_id": agent,
        "action": action,
        "alert_type": alert_type,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def _is_dup(db, **kw):
    with patch("response_orchestrator.get_database", return_value=db):
        return await ResponseOrchestrator().is_duplicate_task(**kw)


async def test_agent_level_duplicate_is_per_tenant(mongo_db):
    await mongo_db.response_tasks.insert_one(_task("tenant-a"))
    same = await _is_dup(mongo_db, agent_id="agent-x", action="kill_process", tenant_id="tenant-a")
    other = await _is_dup(mongo_db, agent_id="agent-x", action="kill_process", tenant_id="tenant-b")
    assert same is True
    assert other is False


async def test_incident_level_duplicate_is_per_tenant(mongo_db):
    await mongo_db.response_tasks.insert_one(_task("tenant-a", agent="agent-1"))
    kw = dict(agent_id="agent-2", action="kill_process", alert_type="malware")
    assert await _is_dup(mongo_db, tenant_id="tenant-a", **kw) is True
    assert await _is_dup(mongo_db, tenant_id="tenant-b", **kw) is False


@pytest.mark.parametrize("empty", [None, ""])
async def test_missing_tenant_fails_closed(mongo_db, empty):
    # Nothing queued at all: with no tenant the answer is still "duplicate" (skip the action).
    assert await _is_dup(mongo_db, agent_id="agent-x", action="kill_process", tenant_id=empty) is True
