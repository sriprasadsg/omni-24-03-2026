"""Shared world for the worker and return tests (Phase 85, plan 85-17): a tenant with the desk in Post mode and
the four starter articles, a stand-in Ollama that records the read timeout of every call, tickets queued at a
chosen arrival time, and a clock a test can move. Every time in these tests is seeded by the test itself."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import ledger
from service_desk import intake, model, starters
from tests.service_desk_support import desk_indexes_without_ttl, seed_desk_tenant

ANSWER = "Open your company's sign-in page and choose Forgot password."
TITLE = "I forgot my password"
DESC = "I cannot sign in to my laptop because I forgot my password and I need to reset it"
TIMINGS = {"eval_count": 40, "eval_duration": 4_000_000_000, "prompt_eval_count": 300,
           "prompt_eval_duration": 6_000_000_000, "load_duration": 1_000_000_000, "total_duration": 11_000_000_000}
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


class Clock:
    """The injected clock: calling it gives the time, ``advance`` moves it."""

    def __init__(self, at=NOW):
        self.at = at

    def __call__(self):
        return self.at

    def advance(self, seconds):
        self.at += timedelta(seconds=seconds)


@pytest.fixture(autouse=True)
def _desk_env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    monkeypatch.delenv("SERVICE_DESK_OLLAMA_URL", raising=False)
    monkeypatch.delenv("SERVICE_DESK_MODEL", raising=False)
    model.clear_probe_cache()


async def add_tenant(db, tenant, *, mode="post"):
    await seed_desk_tenant(db, tenant, mode=mode, shadow=False)
    await db.knowledge_docs.insert_many(starters.copy_docs(tenant, {"name": "test"}, "2026-11-09T09:00:00"))


@pytest.fixture
async def world(mongo_db, monkeypatch):
    from unittest.mock import AsyncMock
    import ticket_notifications
    import tickets_config_mixin
    import tickets_service
    for module in (tickets_service, tickets_config_mixin):
        monkeypatch.setattr(module, "get_database", lambda: mongo_db)
    monkeypatch.setattr(ticket_notifications, "notify_assigned", AsyncMock())
    monkeypatch.setattr(ticket_notifications, "notify_status_changed", AsyncMock())
    await ledger.ensure_indexes(mongo_db)
    await desk_indexes_without_ttl(mongo_db)
    await add_tenant(mongo_db, "t1")
    return mongo_db


def stand_in(answer=ANSWER, cited=(1,), *, fail_tags=False, on_generate=None):
    """A stand-in Ollama. Every request is appended to ``calls`` with the read timeout it was sent with."""
    calls = []

    async def handler(request):
        body = json.loads(request.content) if request.content else None
        timeout = request.extensions.get("timeout") or {}
        calls.append({"path": request.url.path, "body": body, "read": timeout.get("read")})
        if request.url.path == "/api/tags":
            if fail_tags:
                raise httpx.ConnectError("no model is running", request=request)
            return httpx.Response(200, json={"models": [{"name": "llama3.2:3b", "model": "llama3.2:3b"}]})
        if request.url.path == "/api/generate":
            if on_generate:
                await on_generate()
            return httpx.Response(200, json={"response": json.dumps({"answer": answer, "cited": list(cited)}),
                                             **TIMINGS})
        return httpx.Response(404)

    return httpx.MockTransport(handler), calls


def generates(calls):
    return [c for c in calls if c["path"] == "/api/generate"]


async def queue(db, n, *, arrived=NOW, tenant="t1", title=TITLE, description=DESC, type="task", priority="medium"):
    """Insert ticket ``k<n>`` and queue its job as if the ticket arrived at ``arrived``. Returns (ticket, job id)."""
    ticket = {"id": f"k{n}", "tenantId": tenant, "ticket_number": f"TKT-{n:04d}", "title": title,
              "description": description, "type": type, "priority": priority, "status": "open",
              "reporter": "alice", "assignee": None, "raised_via": "portal", "comments": [], "history": [],
              "requester_channel": {"portal": True, "tray": False, "myTickets": False}, "escalated": False}
    await db.tickets.insert_one(dict(ticket))
    job_id = await intake.on_ticket_created(db, ticket, via="portal", now=arrived)
    assert job_id, "the ticket was not queued"
    return ticket, job_id


async def job(db, job_id):
    return await db.service_desk_jobs.find_one({"id": job_id}, {"_id": 0})


async def stored(db, ticket):
    return await db.tickets.find_one({"id": ticket["id"]}, {"_id": 0})


async def rows(db, tenant="t1"):
    return await db.autonomy_actions.find({"tenantId": tenant, "kind": "servicedesk"}, {"_id": 0}).to_list(200)


def kinds(ticket):
    return [c["kind"] for c in ticket["comments"]]
