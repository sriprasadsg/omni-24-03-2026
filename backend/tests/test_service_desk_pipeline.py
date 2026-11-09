"""Every stage of one service desk attempt, wired end to end (Phase 85, plan 85-13, DESK-01 to DESK-05). Real
MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py; the local model is a
stand-in (httpx.MockTransport), never a real Ollama.

Value: protects=a ticket reaches the model only when every fixed rule, the stop, the English check and the
article cut-off let it; every failure ends as exactly one hand-off to a person; a reply is posted only after the
output checks, the re-read of the ticket and the gate; fails_when=a sensitive, critical, fulfilment or
non-English ticket is sent to the model, a stop pressed during generation still posts, a ticket a person moved
or answered still gets an automatic post, a reply with a link or command its article lacks is kept, a model that
is offline or slow leaves the ticket with no hand-off, the timeout is not the measured one, or a key the model
adds to its reply changes an outcome; no_claim=a real Ollama, the live knowledge base and the injection set
(test_service_desk_injection.py).
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import ledger
from service_desk import DRAFT_REASONS, messages, model, runtime, starters, store, worker
from service_desk import intake
from service_desk.model import OllamaClient
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_support import seed_desk_tenant

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "service_desk")
ANSWER = "Open your company's sign-in page and choose Forgot password."
TITLE = "I forgot my password"
DESC = "I cannot sign in to my laptop because I forgot my password and I need to reset it"
TIMINGS = {"eval_count": 40, "eval_duration": 4_000_000_000, "prompt_eval_count": 300,
           "prompt_eval_duration": 6_000_000_000, "load_duration": 1_000_000_000, "total_duration": 11_000_000_000}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    monkeypatch.delenv("SERVICE_DESK_OLLAMA_URL", raising=False)
    monkeypatch.delenv("SERVICE_DESK_MODEL", raising=False)
    model.clear_probe_cache()


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    from unittest.mock import AsyncMock
    import ticket_notifications
    import tickets_config_mixin
    import tickets_service
    for module in (tickets_service, tickets_config_mixin):
        monkeypatch.setattr(module, "get_database", lambda: mongo_db)
    monkeypatch.setattr(ticket_notifications, "notify_assigned", AsyncMock())
    monkeypatch.setattr(ticket_notifications, "notify_status_changed", AsyncMock())
    await ledger.ensure_indexes(mongo_db)
    await store.ensure_indexes(mongo_db)
    await seed_desk_tenant(mongo_db, "t1", mode="post", shadow=False)
    await mongo_db.knowledge_docs.insert_many(starters.copy_docs("t1", {"name": "test"}, "2026-11-09T09:00:00"))
    return mongo_db


def stand_in(answer=ANSWER, cited=(1,), *, tags=("llama3.2:3b",), status=200, reply_text=None, fail_tags=False,
             raises=None, on_generate=None):
    """A stand-in Ollama. Every request is appended to ``calls`` with the read timeout it was sent with."""
    calls = []

    async def handler(request):
        body = json.loads(request.content) if request.content else None
        timeout = request.extensions.get("timeout") or {}
        calls.append({"path": request.url.path, "body": body, "read": timeout.get("read")})
        if request.url.path == "/api/tags":
            if fail_tags:
                raise httpx.ConnectError("no model is running", request=request)
            return httpx.Response(200, json={"models": [{"name": t, "model": t} for t in tags]})
        if request.url.path == "/api/generate":
            if on_generate:
                await on_generate()
            if raises:
                raise raises(request)
            text = reply_text if reply_text is not None else json.dumps({"answer": answer, "cited": list(cited)})
            return httpx.Response(status, json={"response": text, **TIMINGS})
        return httpx.Response(404)

    return httpx.MockTransport(handler), calls


async def make_ticket(db, n=1, *, tenant="t1", title=TITLE, description=DESC, type="task", priority="medium",
                      channel=None, template=None, reporter="alice"):
    channel = dict({"portal": True, "tray": False, "myTickets": False} if channel is None else channel)
    if template:
        channel["template"] = template
    ticket = {"id": f"k{n}", "tenantId": tenant, "ticket_number": f"TKT-{n:04d}", "title": title,
              "description": description, "type": type, "priority": priority, "status": "open",
              "reporter": reporter, "assignee": None, "raised_via": "portal", "comments": [], "history": [],
              "requester_channel": channel, "escalated": False}
    await db.tickets.insert_one(dict(ticket))
    return ticket


async def attempt(db, ticket, *, after_queue=None, **transport):
    """Queue the ticket and run one worker pass. Returns (job, generate calls, all calls)."""
    job_id = await intake.on_ticket_created(db, ticket, via="portal")
    assert job_id, "the ticket was not queued"
    if after_queue:
        await after_queue()
    stand, calls = stand_in(**transport)
    await worker.run_once(db, client=OllamaClient(transport=stand))
    return await db.service_desk_jobs.find_one({"id": job_id}, {"_id": 0}), [c for c in calls if c["path"] == "/api/generate"], calls


async def stored(db, ticket):
    return await db.tickets.find_one({"id": ticket["id"]}, {"_id": 0})


async def rows(db, command=None):
    found = await db.autonomy_actions.find({"tenantId": "t1", "kind": "servicedesk"}, {"_id": 0}).to_list(100)
    return [r for r in found if not r["id"].startswith("AO-old") and (command is None or r["action"] == command)]


def kinds(ticket):
    return [c["kind"] for c in ticket["comments"]]


async def expect_handoff(world, reason, after_queue=None, **ticket_fields):
    """A pre-model hand-off: the job ends with the reason, one ledger row, no generate request, no answer."""
    ticket = await make_ticket(world, **ticket_fields)
    job, generates, _ = await attempt(world, ticket, after_queue=after_queue)
    assert (job["state"], job["reason"]) == ("done", reason)
    assert generates == []
    [row] = await rows(world)
    assert row["command"] == "ticket_handoff" and row["reasonCode"] == reason
    after = await stored(world, ticket)
    assert not {"ai_answer", "ai_draft"} & set(kinds(after))
    assert after["desk"]["phase"] == "handed_off" and after["desk"]["lastReason"] == reason
    return ticket, after


async def gap_reasons(db):
    return [g["reason"] async for g in db.service_desk_gaps.find({"tenantId": "t1"}, {"_id": 0})]


# ---------------------------------------------------------------- the fixed rules, before the model

async def test_an_empty_ticket_goes_to_a_person(world):
    await expect_handoff(world, "empty_ticket", title="", description="")
    assert await gap_reasons(world) == []


async def test_a_critical_ticket_goes_to_a_person_with_the_requester_notice(world):
    _, after = await expect_handoff(world, "critical_priority", priority="critical")
    assert "handoff_notice" in kinds(after)


async def test_a_fulfilment_request_goes_to_a_person(world):
    await expect_handoff(world, "fulfilment_request", type="feature")


async def test_a_ticket_type_the_desk_does_not_answer_goes_to_a_person(world):
    await expect_handoff(world, "type_not_answered", type="problem")


async def test_a_security_topic_goes_to_a_person(world):
    await expect_handoff(world, "security_topic", title="I think I clicked a phishing link")


async def test_a_billing_topic_goes_to_a_person(world):
    await expect_handoff(world, "billing_topic", title="Wrong invoice for March")


async def test_a_legal_topic_goes_to_a_person(world):
    await expect_handoff(world, "legal_topic", title="Our lawyer needs a copy of the email thread")


async def test_an_account_access_ticket_goes_to_a_person(world):
    await expect_handoff(world, "account_access", title="Please unlock my account")


async def test_a_ticket_that_asks_for_a_person_goes_to_a_person(world):
    await expect_handoff(world, "asked_for_person", title="Can a real person call me about this?")


async def test_a_word_the_tenant_added_goes_to_a_person(world):
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"serviceDesk": {
        "mode": "post", "words": ["payroll"]}}})
    await expect_handoff(world, "tenant_word", title="Payroll portal will not load")


async def test_a_ticket_not_in_english_goes_to_a_person_and_leaves_a_gap_row(world):
    await expect_handoff(world, "not_english", title="No puedo entrar a mi cuenta", description="Necesito ayuda con el correo")
    assert await gap_reasons(world) == ["not_english"]


async def test_a_ticket_no_article_covers_goes_to_a_person_and_leaves_a_gap_row(world):
    await expect_handoff(world, "no_article", title="How do I book a meeting room", description="For next week")
    assert await gap_reasons(world) == ["no_article"]


async def test_a_desk_that_is_off_when_the_job_is_picked_up_writes_nothing(world):
    ticket = await make_ticket(world)
    job_id = await intake.on_ticket_created(world, ticket, via="portal")
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"serviceDesk": {"mode": "off"}}})
    stand, calls = stand_in()
    await worker.run_once(world, client=OllamaClient(transport=stand))
    assert (await world.service_desk_jobs.find_one({"id": job_id}))["reason"] == "desk_off"
    assert calls == [] and await rows(world) == [] and (await stored(world, ticket))["comments"] == []


async def test_a_stop_already_on_hands_the_ticket_over_quietly_and_sends_no_request(world):
    async def press_stop():
        await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop": {"active": True}}})
    ticket, after = await expect_handoff(world, "desk_stopped", after_queue=press_stop)
    assert "handoff_notice" not in kinds(after)


# ---------------------------------------------------------------- the model

async def test_a_model_that_is_not_running_hands_off_service_desk_offline(world):
    ticket = await make_ticket(world)
    job, generates, calls = await attempt(world, ticket, fail_tags=True)
    assert job["reason"] == "service_desk_offline" and generates == []
    assert [r["reasonCode"] for r in await rows(world)] == ["service_desk_offline"]
    assert await gap_reasons(world) == [] and "ai_draft" not in kinds(await stored(world, ticket))


async def test_a_busy_model_hands_off_service_desk_busy(world):
    ticket = await make_ticket(world)
    job, generates, _ = await attempt(world, ticket, status=503)
    assert job["reason"] == "service_desk_busy" and len(generates) == 1
    assert [r["reasonCode"] for r in await rows(world)] == ["service_desk_busy"]
    assert not {"ai_answer", "ai_draft"} & set(kinds(await stored(world, ticket)))


async def test_a_model_that_times_out_hands_off_service_desk_busy(world):
    ticket = await make_ticket(world)
    job, _, _ = await attempt(world, ticket, raises=lambda request: httpx.ReadTimeout("too slow", request=request))
    assert job["reason"] == "service_desk_busy" and [r["reasonCode"] for r in await rows(world)] == ["service_desk_busy"]


async def test_a_reply_that_fails_the_output_check_hands_off_and_posts_nothing(world):
    ticket = await make_ticket(world)
    job, _, _ = await attempt(world, ticket, answer="Go to https://evil.example/reset now.")
    assert job["reason"] == "output_check_failed"
    assert [r["reasonCode"] for r in await rows(world)] == ["output_check_failed"]
    assert not {"ai_answer", "ai_draft"} & set(kinds(await stored(world, ticket)))


async def test_the_generate_timeout_is_the_one_sized_from_the_measurement(world):
    await runtime.save_measurement(world, {"model": "llama3.2:3b", "prefillTps": 20, "genTps": 6, "loadSeconds": 5,
                                           "samples": 3})
    ticket = await make_ticket(world)
    _, generates, _ = await attempt(world, ticket)
    prompt = generates[0]["body"]
    expected = runtime.call_timeout(len(prompt["system"]) + len(prompt["prompt"]), 220,
                                    await runtime.load_measurement(world), await runtime.recent_gen_ms(world))
    assert generates[0]["read"] == expected and expected != runtime.call_timeout(0, 0, runtime.Measurement())


# ---------------------------------------------------------------- post or draft

async def test_a_post_notifies_the_reporter_and_words_the_activity_row(world):
    ticket = await make_ticket(world)
    job, generates, _ = await attempt(world, ticket)
    assert job["reason"] == "posted" and len(generates) == 1
    [row] = await rows(world)
    assert row["state"] == "executed" and row["command"] == "ticket_answer"
    assert row["reasonText"] == f'Ticket TKT-0001: "{TITLE}" matched 1 Help desk article.'
    assert row["activityResult"] == messages.ACTIVITY["posted_result"].format(n=1, articles="article")
    assert row["reason"]["inputs"]["genMs"] == 4000 and row["reason"]["inputs"]["model"] == "llama3.2:3b"
    after = await stored(world, ticket)
    assert after["status"] == "pending_customer" and kinds(after) == ["ai_answer"]
    [note] = await world.notifications.find({"tenantId": "t1"}, {"_id": 0}).to_list(5)
    assert note["metadata"]["recipient"] == "alice" and note["title"] == "Your ticket TKT-0001 has an answer"
    assert TITLE not in repr(note)


async def _draft_case(world, ticket, reason, **transport):
    job, _, _ = await attempt(world, ticket, **transport)
    after = await stored(world, ticket)
    [row] = await rows(world, "ticket_answer")
    assert job["reason"] == "drafted" and kinds(after) == ["ai_draft"] and after["comments"][0]["visibility"] == "staff"
    assert after["status"] == "open" and after["desk"]["draftReason"] == reason == row["desk"]["draftReason"]
    assert reason in DRAFT_REASONS and messages.DRAFT_REASON_TEXT[reason] in row["reasonText"]
    return row


async def test_a_ticket_from_an_old_tray_is_a_draft_with_no_tray_window(world):
    ticket = await make_ticket(world, channel={"portal": False, "tray": True, "myTickets": False})
    await _draft_case(world, ticket, "no_tray_window")


async def test_at_suggest_level_the_answer_is_a_draft(world):
    await seed_desk_tenant(world, "t1", level="suggest", mode="post", shadow=False)
    await _draft_case(world, await make_ticket(world), "level_suggest")


async def test_drafts_only_mode_keeps_a_draft(world):
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"serviceDesk": {"mode": "drafts"}}})
    row = await _draft_case(world, await make_ticket(world), "mode_drafts")
    assert row["state"] == "suggested" and row["activityResult"] == messages.ACTIVITY["draft_result"]


async def test_a_stored_breaker_keeps_a_draft_with_the_breaker_reason(world):
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"serviceDesk": {
        "mode": "drafts", "breaker": {"trippedAt": datetime.now(timezone.utc), "actionIds": []}}}})
    await _draft_case(world, await make_ticket(world), "desk_breaker")


async def test_settings_that_cannot_be_understood_keep_a_draft(world):
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"serviceDesk": "garbage"}})
    await _draft_case(world, await make_ticket(world), "settings_unreadable")


async def test_in_shadow_the_row_is_a_simulation_and_the_answer_a_staff_draft(world):
    await seed_desk_tenant(world, "t1", mode="post", shadow=True)
    job, _, _ = await attempt(world, await make_ticket(world))
    [row] = await rows(world, "ticket_answer")
    assert job["reason"] == "drafted" and row["state"] == "shadow" and row["desk"]["draftReason"] == "shadow"
    assert row["activityResult"].startswith("Nothing was done.")
    assert "Would have posted the answer to ticket TKT-0001. Nothing was posted" in row["activityResult"]


async def test_the_21st_answer_in_the_hour_is_a_draft(world):
    now = datetime.now(timezone.utc) - timedelta(minutes=10)
    await world.autonomy_actions.insert_many([
        {"id": f"AO-old-{i}", "tenantId": "t1", "kind": "servicedesk", "state": "executed", "autoDispatched": True,
         "createdAt": now, "updatedAt": now, "finishedAt": now, "command": "ticket_answer", "targets": [],
         "reason": {"ruleId": "t", "inputs": {}}} for i in range(20)])
    await _draft_case(world, await make_ticket(world), "desk_rate_limit")


BADGE_LINK = "https://badges.corp.example/replace"
BADGE = {"title": "Request a replacement badge", "tags": ["badge"], "content": (
    "If you lost your badge or it stopped working, request a replacement badge at " + BADGE_LINK + " and "
    "collect it from the front desk.")}


async def _badge_ticket(world):
    await world.knowledge_docs.insert_one({"id": "kb-badge", "tenantId": "t1", "helpdesk": True, "source": "manual", **BADGE})
    return await make_ticket(world, title="Lost badge, how do I request a replacement badge",
                             description="I lost my badge and need to request a replacement badge from the front desk")


async def test_a_link_the_cited_article_holds_is_kept_in_the_answer(world):
    """protects=D-19: the checks run against the text of the cited articles, so a link the article itself holds
    can be posted; fails_when=the cited texts are not passed to the checks and every such reply is refused."""
    ticket = await _badge_ticket(world)
    job, _, _ = await attempt(world, ticket, answer="Request a replacement badge at " + BADGE_LINK + ".")
    assert job["reason"] == "posted" and BADGE_LINK in (await stored(world, ticket))["comments"][0]["text"]


async def test_a_link_the_cited_article_does_not_hold_is_refused(world):
    ticket = await _badge_ticket(world)
    job, _, _ = await attempt(world, ticket, answer="Request a replacement badge at https://badges.evil.example/replace.")
    assert job["reason"] == "output_check_failed" and not {"ai_answer", "ai_draft"} & set(kinds(await stored(world, ticket)))


# ---------------------------------------------------------------- stops, and a ticket that changed meanwhile

async def test_a_stop_pressed_during_generation_posts_nothing_and_keeps_a_draft(world):
    async def press_stop():
        await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop": {"active": True}}})
    ticket = await make_ticket(world)
    job, generates, _ = await attempt(world, ticket, on_generate=press_stop)
    after = await stored(world, ticket)
    [row] = await rows(world, "ticket_answer")
    assert job["reason"] == "drafted" and len(generates) == 1
    assert row["state"] == "refused" and row["reasonCode"] == "tenant_stop"
    assert kinds(after) == ["ai_draft"] and after["status"] == "open" and after["desk"]["draftReason"] == "stopped"
    assert row["desk"]["draftReason"] == "stopped" and row["desk"]["ticketId"] == ticket["id"]


async def test_a_platform_stop_pressed_during_generation_keeps_a_draft_too(world):
    async def press_stop():
        await world.system_settings.update_one({"type": "autonomous_ops"}, {"$set": {
            "type": "autonomous_ops", "stop": {"active": True}}}, upsert=True)
    ticket = await make_ticket(world)
    job, _, _ = await attempt(world, ticket, on_generate=press_stop)
    assert job["reason"] == "drafted" and kinds(await stored(world, ticket)) == ["ai_draft"]
    assert (await rows(world, "ticket_answer"))[0]["reasonCode"] == "platform_stop"


async def test_a_ticket_a_person_moved_during_generation_gets_no_post(world):
    ticket = await make_ticket(world)

    async def person_moves_it():
        await world.tickets.update_one({"id": ticket["id"]}, {"$set": {"status": "in_progress", "assignee": "bob"}})
    job, _, _ = await attempt(world, ticket, on_generate=person_moves_it)
    after = await stored(world, ticket)
    assert job["reason"] == "ticket_changed" and kinds(after) == ["ai_draft"]
    assert after["status"] == "in_progress" and after["assignee"] == "bob"
    assert (await rows(world, "ticket_answer"))[0]["state"] == "suggested"


async def test_a_reply_to_the_requester_by_a_person_during_generation_gets_no_post(world):
    ticket = await make_ticket(world)

    async def person_replies():
        await world.tickets.update_one({"id": ticket["id"]}, {"$push": {"comments": {
            "id": "c1", "author": "bob", "text": "On it", "visibility": "requester", "kind": "requester_reply"}}})
    job, _, _ = await attempt(world, ticket, on_generate=person_replies)
    after = await stored(world, ticket)
    assert job["reason"] == "ticket_changed" and kinds(after) == ["requester_reply", "ai_draft"]
    assert after["status"] == "open"


async def test_a_ticket_moved_after_the_gate_but_before_the_post_is_kept_as_a_draft(world, monkeypatch):
    from autonomous_ops import gate
    real = gate.decide
    ticket = await make_ticket(world)

    async def decide_then_a_person_moves_it(db, request, **kw):
        decision = await real(db, request, **kw)
        await world.tickets.update_one({"id": ticket["id"]}, {"$set": {"status": "in_progress"}})
        return decision
    monkeypatch.setattr(gate, "decide", decide_then_a_person_moves_it)
    job, _, _ = await attempt(world, ticket)
    after = await stored(world, ticket)
    [row] = await rows(world, "ticket_answer")
    assert job["reason"] == "ticket_changed" and kinds(after) == ["ai_draft"] and after["status"] == "in_progress"
    assert row["state"] == "suggested" and row["desk"]["draftReason"] and "ai_answer" not in kinds(after)


# ---------------------------------------------------------------- escalation set, and the model's own keys

def _fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip() and "_comment" not in line[:12]]


async def _run_case(world, number, case):
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"serviceDesk": {
        "mode": "post", "words": case["words"]}}})
    ticket = await make_ticket(world, number, title=case["title"], description=case["description"],
                               type=case["type"], priority=case["priority"], template=case["template"])
    return await attempt(world, ticket)


async def test_every_escalation_case_goes_to_a_person_without_the_model_seeing_it(world):
    failures = []
    for number, case in enumerate([c for c in _fixture("escalation_set.jsonl") if c["expect"]], start=1):
        job, generates, _ = await _run_case(world, number, case)
        if job["reason"] != case["expect"] or generates:
            failures.append((case["id"], job["reason"], len(generates)))
    assert failures == []


async def test_answerable_escalation_cases_reach_the_model_unless_retrieval_or_language_stops_them(world):
    reached, stopped, wrong = 0, 0, []
    for number, case in enumerate([c for c in _fixture("escalation_set.jsonl") if not c["expect"]], start=1):
        job, generates, _ = await _run_case(world, number, case)
        if generates:
            reached += 1
            assert len(generates) == 1
        elif job["reason"] in ("no_article", "not_english"):
            stopped += 1
        else:
            wrong.append((case["id"], job["reason"]))
    assert wrong == [] and reached >= 5 and reached + stopped == len([c for c in _fixture("escalation_set.jsonl") if not c["expect"]])


async def test_keys_the_model_adds_to_its_reply_change_nothing(world):
    plain = json.dumps({"answer": ANSWER, "cited": [1]})
    padded = json.dumps({"answer": ANSWER, "cited": [1], "confidence": 0.01, "close_ticket": True,
                         "assignee": "mallory", "status": "closed", "priority": "low"})
    seen = []
    for number, text in enumerate((plain, padded), start=1):
        ticket = await make_ticket(world, number)
        job, _, _ = await attempt(world, ticket, reply_text=text)
        after = await stored(world, ticket)
        row = (await rows(world, "ticket_answer"))[-1]
        seen.append((job["reason"], [(c["kind"], c["visibility"], c["text"]) for c in after["comments"]],
                     after["status"], after["assignee"], after["priority"], row["state"], row["reasonText"]))
    assert seen[0][0] == "posted" and seen[0][2:5] == ("pending_customer", None, "medium")
    assert seen[0][1:6] == seen[1][1:6]         # the comments, status, assignee, priority and row state are the same
