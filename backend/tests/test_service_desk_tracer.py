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


def _first_job(counts):
    """The id of the job a pass closed first (the pass reports counts since 85-17), or None."""
    return counts["jobs"][0] if counts and counts["jobs"] else None


async def _run(world, answer=ANSWER, cited=(1,), **transport):
    stand_in, calls = ollama_transport(answer, list(cited), **transport)
    job_id = _first_job(await worker.run_once(world.db, client=OllamaClient(transport=stand_in)))
    return job_id, calls


async def _rows(db, tenant="t1"):
    return await db.autonomy_actions.find({"tenantId": tenant, "kind": "servicedesk"}, {"_id": 0}).to_list(20)


async def _answers(db, tenant="t1"):
    """The rows that carry an answer (a hand-off to a person is a servicedesk row of its own, 85-12/85-13)."""
    return [r for r in await _rows(db, tenant) if r["command"] == "ticket_answer"]


def _model_comments(ticket):
    """The comments a model answer would have left on the ticket (the hand-off's own notes are not those)."""
    return [c for c in ticket["comments"] if c["kind"] in ("ai_answer", "ai_draft")]


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


# ---------------------------------------------------------------- Task 2: who raised it, Off, unticked, Platform

async def test_an_api_key_ticket_is_automation_and_gets_no_attempt(world):
    """protects=D-01 / T-85-01: a ticket created with an API key is stored as automation, queued nowhere and
    the body cannot claim otherwise; fails_when=automation raises a job or a row."""
    key = portal_user("t1", "integration", auth_source="api_key")
    ticket = await _raise(world, key, raised_via="portal", requester_channel={"portal": True})
    stored = await _stored(world.db, ticket["id"])
    assert stored["raised_via"] == "automation" and stored["requester_channel"]["portal"] is False
    assert await world.db.service_desk_jobs.count_documents({}) == 0
    job_id, calls = await _run(world)
    assert job_id is None and calls == [] and await _rows(world.db) == []


async def test_a_body_cannot_make_a_session_ticket_anything_but_what_the_server_decides(world):
    """protects=T-85-01: a client body field raised_via never reaches the stored ticket; fails_when=it does."""
    ticket = await _raise(world, ALICE, raised_via="automation")
    assert (await _stored(world.db, ticket["id"]))["raised_via"] == "portal"


async def test_mode_off_gives_no_job_and_the_ticket_flows_as_before(world):
    """protects=D-04: a stored mode off queues nothing; fails_when=an Off tenant gets an attempt."""
    await seed_desk_tenant(world.db, "t4", mode="off")
    ticket = await _raise(world, portal_user("t4", "erin"))
    assert (await _stored(world.db, ticket["id"]))["status"] == "open"
    assert await world.db.service_desk_jobs.count_documents({}) == 0
    assert await _rows(world.db, "t4") == []


async def test_an_unticked_tenant_gets_no_job(world):
    """protects=Phase 81 D-23: without the Autonomous Ops screen the desk never starts; fails_when=it does."""
    await seed_desk_tenant(world.db, "t5", mode="post", ticked=False)
    await _raise(world, portal_user("t5", "finn"))
    assert await world.db.service_desk_jobs.count_documents({}) == 0


async def test_the_platform_tenant_never_gets_a_job(world):
    """protects=D-04: the Platform tenant is never queued; fails_when=intake accepts it."""
    await seed_desk_tenant(world.db, PLATFORM_TENANT_ID, mode="post")
    ticket = {"id": "tp1", "tenantId": PLATFORM_TENANT_ID, "ticket_number": "TKT-9999"}
    assert await intake.on_ticket_created(world.db, ticket, via="portal") is None
    assert await world.db.service_desk_jobs.count_documents({}) == 0


async def test_a_ticket_is_queued_once(world):
    """protects=one attempt per ticket: a second enqueue of the same ticket returns None and leaves one job."""
    ticket = await _raise(world)
    stored = await _stored(world.db, ticket["id"])
    assert await intake.on_ticket_created(world.db, stored, via="portal") is None
    assert await world.db.service_desk_jobs.count_documents({"ticketId": ticket["id"]}) == 1


# ---------------------------------------------------------------- Task 2: articles

async def test_only_the_tenants_own_help_desk_articles_are_candidates(world):
    """protects=T-85-04: with only global, foreign and non-Help-desk articles the ticket gets no row and its
    job ends no_article; fails_when=any of them is cited or the model is asked."""
    await seed_desk_tenant(world.db, "t6", mode="post")
    await seed_article(world.db, "t6", "kb-notes", title=PW_TITLE, content=PW_CONTENT, helpdesk=False)
    await seed_article(world.db, "global", "kb-global2", title=PW_TITLE, content=PW_CONTENT)
    await seed_article(world.db, "t1", "kb-pw-t1-only", title=PW_TITLE, content=PW_CONTENT)
    ticket = await _raise(world, portal_user("t6", "gus"))
    job_id, calls = await _run(world)
    assert calls == [] and await _answers(world.db, "t6") == []
    done = await world.db.service_desk_jobs.find_one({"id": job_id})
    assert done["state"] == "done" and done["reason"] == "no_article"
    assert _model_comments(await _stored(world.db, ticket["id"])) == []


# ---------------------------------------------------------------- Task 2: the model

async def test_a_model_that_cannot_be_reached_writes_nothing(world):
    """protects=DESK-04: a failing tags probe sends no generate request, writes no row, ends offline."""
    ticket = await _raise(world)
    job_id, calls = await _run(world, fail_tags=True)
    assert not [c for c in calls if c["path"] == "/api/generate"]
    assert await _answers(world.db) == []
    assert (await world.db.service_desk_jobs.find_one({"id": job_id}))["reason"] == "service_desk_offline"
    assert _model_comments(await _stored(world.db, ticket["id"])) == []


async def test_a_different_model_tag_is_not_good_enough(world):
    """protects=DESK-04: only llama3.2:1b installed means offline; there is no first-available fallback."""
    await _raise(world)
    job_id, calls = await _run(world, tags=("llama3.2:1b",))
    assert [c["path"] for c in calls] == ["/api/tags"]
    assert await _answers(world.db) == []
    assert (await world.db.service_desk_jobs.find_one({"id": job_id}))["reason"] == "service_desk_offline"


async def test_a_client_for_a_non_loopback_host_sends_nothing(world):
    """protects=D-15 / T-85-03: ticket text never leaves the loopback host; fails_when=a request is sent."""
    stand_in, calls = ollama_transport(ANSWER, [1])
    client = OllamaClient(base_url="http://10.0.0.4:11434", transport=stand_in)
    assert client.refused is True and await client.available() is False
    assert calls == []
    await _raise(world)
    job_id = _first_job(await worker.run_once(world.db, client=client))
    assert calls == [] and await _answers(world.db) == []
    assert (await world.db.service_desk_jobs.find_one({"id": job_id}))["reason"] == "service_desk_offline"


async def test_a_loopback_host_with_a_look_alike_name_is_refused():
    """protects=T-85-03: the allow-list matches the host, not a prefix of it."""
    for url in ("http://127.0.0.1.example.com:11434", "http://localhost.example.com", "ftp://127.0.0.1"):
        assert OllamaClient(base_url=url).refused is True
    for url in ("http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434"):
        assert OllamaClient(base_url=url).refused is False


async def test_a_reply_that_cites_an_article_it_was_not_given_is_not_used(world):
    """protects=T-85-05: cited [7] when one article was given: no row, no comment, job output_check_failed."""
    ticket = await _raise(world)
    job_id, calls = await _run(world, cited=[7])
    assert len([c for c in calls if c["path"] == "/api/generate"]) == 1
    assert await _answers(world.db) == []
    assert (await world.db.service_desk_jobs.find_one({"id": job_id}))["reason"] == "output_check_failed"
    assert _model_comments(await _stored(world.db, ticket["id"])) == []


async def test_a_reply_that_is_not_the_agreed_shape_is_not_used(world):
    """protects=T-85-05: free text, a missing citation and an empty citation list all fail the check."""
    replies = ("Just reset it, here is a link: http://evil.example", '{"answer": "x"}', '{"answer": "x", "cited": []}')
    for number, reply in enumerate(replies):
        await _raise(world, portal_user("t1", f"user{number}"))
        job_id, _ = await _run(world, reply_text=reply)
        assert (await world.db.service_desk_jobs.find_one({"id": job_id}))["reason"] == "output_check_failed"
    assert await _answers(world.db) == []
