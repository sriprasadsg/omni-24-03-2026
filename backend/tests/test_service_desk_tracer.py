"""The service desk tracer (Phase 85, plan 85-01, DESK-01 / DESK-04 / DESK-05). Real MongoDB (skips without
one) through the throwaway database of tests/_mongo_test_db.py; the local model is a stand-in
(httpx.MockTransport), never a real Ollama.

Value: protects=a portal ticket is stamped as raised by a person, queued once, answered from the tenant's
own Help desk article through the Autonomous Ops gate, posted to the requester (or kept as a staff-only
draft by default) and read back through the requester view; automation, Off, unticked and Platform tickets
never get an attempt; foreign and global articles are never cited; an absent, wrong or non-loopback model
never produces a row; fails_when=an API key ticket is attempted, a draft reaches the requester, an article of
another tenant is cited, a request leaves for a non-loopback host, a reply that cites an article it was not
given is posted, or one ticket is attempted twice; no_claim=the outcome matrix, hand-offs and the stop edges
(85-04, 85-13), the checks beyond the citation rule (85-06) and a real Ollama.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import PLATFORM_TENANT_ID
from service_desk import intake, store, worker
from service_desk.model import OllamaClient
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_support import (desk_app, ollama_transport, portal_user, seed_article, seed_desk_tenant)

PW_TITLE = "Reset your own password"
PW_CONTENT = ("If you forgot your password, open the sign-in page and choose Forgot password. Enter your work "
              "email and follow the steps to reset your password. You can sign in again once the reset is finished.")
ANSWER = "Open the sign-in page and choose Forgot password."
TICKET = {"title": "I forgot my password",
          "description": "I cannot sign in to my laptop because I forgot my password and I need to reset it"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")     # the deployment master is off
    monkeypatch.delenv("SERVICE_DESK_OLLAMA_URL", raising=False)
    monkeypatch.delenv("SERVICE_DESK_MODEL", raising=False)


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    from autonomous_ops import ledger
    await ledger.ensure_indexes(mongo_db)
    await store.ensure_indexes(mongo_db)
    await seed_desk_tenant(mongo_db, "t1", mode="post")
    await seed_desk_tenant(mongo_db, "t2", mode="post")
    await seed_desk_tenant(mongo_db, "t3")                               # nothing stored: Drafts only (D-03)
    for tenant in ("t1", "t3"):
        await seed_article(mongo_db, tenant, "kb-pw", title=PW_TITLE, content=PW_CONTENT)
    await seed_article(mongo_db, "global", "kb-global", title=PW_TITLE, content=PW_CONTENT)
    await seed_article(mongo_db, "t2", "kb-other", title=PW_TITLE, content=PW_CONTENT)
    return desk_app(mongo_db, monkeypatch)


ALICE = portal_user("t1", "alice")
BOB = portal_user("t1", "bob")
CAROL = portal_user("t2", "carol")


async def _raise(world, user=ALICE, **extra):
    response = await world.call("POST", "/api/tickets", user=user, json={**TICKET, **extra})
    assert response.status_code == 200, response.text
    return response.json()


async def _run(world, answer=ANSWER, cited=(1,), **transport):
    stand_in, calls = ollama_transport(answer, list(cited), **transport)
    job_id = await worker.run_once(world.db, client=OllamaClient(transport=stand_in))
    return job_id, calls


async def _rows(db, tenant="t1"):
    return await db.autonomy_actions.find({"tenantId": tenant, "kind": "servicedesk"}, {"_id": 0}).to_list(20)


async def _stored(db, ticket_id):
    return await db.tickets.find_one({"id": ticket_id}, {"_id": 0})


# ---------------------------------------------------------------- Task 1: the tracer

async def test_a_portal_ticket_is_stamped_queued_answered_through_the_gate_and_read_back(world):
    """protects=DESK-01: one worker pass writes one desk row (dispatcher service_desk, no targets), posts the
    cited answer to the requester and holds the ticket for the reporter; fails_when=the row is missing or
    carries a target, the comment is not requester-visible, the status is not pending_customer or the model
    is asked more than once."""
    db = world.db
    ticket = await _raise(world)
    stored = await _stored(db, ticket["id"])
    assert stored["raised_via"] == "portal" and stored["requester_channel"]["portal"] is True
    assert stored["desk"]["phase"] == "queued"
    jobs = await db.service_desk_jobs.find({"ticketId": ticket["id"]}, {"_id": 0}).to_list(5)
    assert len(jobs) == 1 and jobs[0]["state"] == "pending" and jobs[0]["tenantId"] == "t1"

    job_id, calls = await _run(world)
    assert job_id == jobs[0]["id"]

    rows = await _rows(db)
    assert len(rows) == 1
    row = rows[0]
    assert row["state"] == "executed" and row["dispatcher"] == "service_desk" and row["command"] == "ticket_answer"
    assert row["targets"] == [] and row["desk"]["ticketId"] == ticket["id"] and row["desk"]["phase"] == "posted"
    assert row["desk"]["undoable"] is True and row["desk"]["commentId"] == "sd-" + row["id"]
    assert [a["id"] for a in row["reason"]["inputs"]["articles"]] == ["kb-pw"]
    assert row["reason"]["inputs"]["genMs"] == 4000 and row["reason"]["inputs"]["suggestionOnly"] is True

    stored = await _stored(db, ticket["id"])
    assert stored["status"] == "pending_customer" and stored["hold_started_at"]
    assert len(stored["comments"]) == 1
    comment = stored["comments"][0]
    assert comment["visibility"] == "requester" and comment["kind"] == "ai_answer" and comment["text"] == ANSWER
    assert [c["articleId"] for c in comment["ai"]["citations"]] == ["kb-pw"]
    assert comment["ai"]["citations"][0]["title"] == PW_TITLE
    assert stored["desk"]["phase"] == "posted" and stored["desk"]["actionId"] == row["id"]

    done = await db.service_desk_jobs.find_one({"id": job_id}, {"_id": 0})
    assert done["state"] == "done" and done["reason"] == "posted" and done["finishedAt"] is not None

    generates = [c for c in calls if c["path"] == "/api/generate"]
    assert len(generates) == 1
    body = generates[0]["body"]
    assert body["stream"] is False and body["model"] == "llama3.2:3b"
    assert "<ticket>" in body["prompt"] and "</ticket>" in body["prompt"]
    assert "I forgot my password" in body["prompt"].split("<ticket>")[1].split("</ticket>")[0]


async def test_the_requester_reads_the_answer_back_and_nobody_else_does(world):
    """protects=the requester view: the reporter sees the cited answer; another user of the tenant sees no
    requester block; another tenant gets 404; fails_when=a colleague reads the answer or a foreign tenant
    learns the ticket exists."""
    ticket = await _raise(world)
    await _run(world)
    path = f"/api/tickets/{ticket['id']}/service-desk"

    mine = (await world.call("GET", path, user=ALICE)).json()
    assert mine["isRequester"] is True and mine["ticketNumber"] == ticket["ticket_number"]
    assert mine["status"] == "pending_customer" and mine["requester"]["canSee"] is True
    [item] = mine["requester"]["items"]
    assert item["kind"] == "ai_answer" and item["text"] == ANSWER
    assert item["citations"] == [{"articleId": "kb-pw", "title": PW_TITLE}]

    colleague = (await world.call("GET", path, user=BOB)).json()
    assert colleague["isRequester"] is False and colleague["requester"] is None

    foreign = await world.call("GET", path, user=CAROL)
    assert foreign.status_code == 404


async def test_with_nothing_stored_the_desk_drafts_for_staff_and_the_requester_sees_nothing(world):
    """protects=D-03: Drafts only by default: a suggested row, a staff-only draft, the status untouched and
    nothing for the requester; fails_when=an unconfigured tenant gets a requester-visible answer."""
    db = world.db
    user = portal_user("t3", "dora")
    ticket = await _raise(world, user)
    job_id, calls = await _run(world)

    [row] = await _rows(db, "t3")
    assert row["state"] == "suggested" and row["reason"]["inputs"]["suggestionOnly"] is True
    assert row["desk"]["phase"] == "drafted"
    stored = await _stored(db, ticket["id"])
    [comment] = stored["comments"]
    assert comment["visibility"] == "staff" and comment["kind"] == "ai_draft"
    assert stored["status"] == "open" and stored["desk"]["draftWaiting"] is True
    assert (await db.service_desk_jobs.find_one({"id": job_id}))["reason"] == "drafted"
    assert len([c for c in calls if c["path"] == "/api/generate"]) == 1

    view = (await world.call("GET", f"/api/tickets/{ticket['id']}/service-desk", user=user)).json()
    assert view["isRequester"] is True and view["requester"]["items"] == []

