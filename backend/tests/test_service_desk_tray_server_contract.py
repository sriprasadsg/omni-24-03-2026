"""The tray routes against the frozen tray contract and the tray script (Phase 85, plan 85-19, D-05). 85-10 tested
the script against service_desk/tray_contract.py as text; this file tests the server against the same module and
against the script, so a field renamed on either side fails here. Real MongoDB (skips without one) for the
response shapes; the script is read as text (there is no PowerShell on the development VM).

Value: protects=the five route paths and methods, every response field the script reads and every request field
it sends are the ones the server serves and accepts, and the AI-assisted line shows once; fails_when=a path or
method differs from the contract, the script reads a field the projection does not have (the failure lists each
one), the script sends a field or a template the create route refuses, or the mark appears twice above an
answer; no_claim=how the window renders and what a real Windows tray does with the responses.
"""
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import service_desk_tray_endpoints as tray
from service_desk import messages, projection
from service_desk import tray_contract as c
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_portal_support import ANSWER
from tests.service_desk_tray_support import build_tray_world, raised_and_answered, say, seed_ticket
from tests.test_service_desk_tray_static import MAIN_PATH, SECOND_PATH, block_after, code, function_body, read, top_level_keys


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    return await build_tray_world(mongo_db, monkeypatch)


def fields_read(script: str, var: str) -> set:
    """The members the script reads off ``$var`` (``$var.name``), comments and strings left alone."""
    return set(re.findall(r"\$" + var + r"\.(\w+)", code(script)))


def missing_fields(script: str, var: str, produced) -> list:
    """Every field ``$var`` reads in the script that the server does not produce (empty when all are served)."""
    return sorted(fields_read(script, var) - set(produced))


async def _rich_ticket(world):
    """A ticket with one entry of every kind the tray can show, so the response has every field in play."""
    ticket = await seed_ticket(world)
    at = datetime.now(timezone.utc)
    ai = {"actionId": "act-1", "state": "posted", "citations": [{"articleId": "kb-pw", "title": "Reset your own password"}]}
    await say(world, ticket, "sd-act-1", "ai_answer", ANSWER, ai=ai, at=at)
    await say(world, ticket, "c-1", None, "A person here", author="bob@x.co", at=at + timedelta(seconds=1))
    await say(world, ticket, "sd-help-1", "requester_reply", "still broken", author="tray:a1", at=at + timedelta(seconds=2))
    await say(world, ticket, "sd-notice-1", "handoff_notice", messages.HANDOFF_NOTICE, at=at + timedelta(seconds=3))
    await say(world, ticket, "sd-old", "ai_answer", "old", ai={"state": "withdrawn", "citations": []}, at=at - timedelta(minutes=1))
    return ticket


# ---------------------------------------------------------------- routes and methods

def test_the_routers_paths_and_methods_are_the_contracts():
    """protects=D-05 the frozen routes; fails_when=a path or a method of the router differs from tray_contract."""
    served = {(method, route.path) for route in tray.router.routes for method in route.methods}
    wanted = {(c.METHODS[name], path) for name, path in c.ROUTES.items()}
    assert served == wanted


def test_the_agent_aggregator_serves_each_contract_route():
    """protects=D-05 the routes are mounted where the agent aggregator puts them; fails_when=a contract route is
    missing from the aggregator or one that is not in the contract is served under the tray prefix."""
    from fastapi import FastAPI
    import agent_endpoints
    app = FastAPI()
    app.include_router(agent_endpoints.router)
    served = {(method.upper(), path) for path, item in app.openapi()["paths"].items() if "/tray/" in path for method in item}
    assert served == {(c.METHODS[name], path) for name, path in c.ROUTES.items()}


def test_the_user_parameter_and_body_fields_are_the_contracts():
    """protects=D-06 the Windows user travels as ``user`` on every route; fails_when=a route names it otherwise."""
    for route in tray.router.routes:
        if route.methods == {"GET"}:
            assert c.USER_PARAM in {p.name for p in route.dependant.query_params}, route.path
    assert c.USER_PARAM in tray.ConfirmRequest.model_fields and set(tray.HelpRequest.model_fields) == set(c.HELP_FIELDS)
    assert set(tray.ConfirmRequest.model_fields) == set(c.CONFIRM_FIELDS)
    assert set(tray.TrayTicketRequest.model_fields) == set(c.CREATE_FIELDS)
    assert set(tray.TrayClient.model_fields) == set(c.CLIENT_FIELDS)


# ---------------------------------------------------------------- response fields the script reads

async def test_every_field_the_script_reads_is_in_the_response(world):
    """protects=D-05 / D-11 the projection serves what the window reads; fails_when=the script reads a ticket,
    entry, citation, display, article, list or create-response field the server does not produce (named in the failure)."""
    ticket = await _rich_ticket(world)
    listed = (await world.list()).json()
    [shown] = listed["tickets"]
    assert shown["id"] == ticket["id"] and {e["kind"] for e in shown["entries"]} == set(c.ENTRY_KINDS)
    answer = next(e for e in shown["entries"] if e["kind"] == "answer")
    article = (await world.article("a1", ticket, "kb-pw")).json()
    created = (await world.create("a1")).json()
    second, main = read(SECOND_PATH), read(MAIN_PATH)
    dialog = function_body(main, "Show-TicketDialog")
    produced = {"tk": set(shown), "lr": set(listed), "dp": set(listed["display"]), "ar": set(article)}
    problems = {var: missing_fields(second, var, keys) for var, keys in produced.items()}
    problems["en"] = sorted(set().union(*(missing_fields(second, "en", e) for e in shown["entries"])))
    problems["ci"] = missing_fields(second, "ci", answer["citations"][0])
    problems["r (create)"] = missing_fields(dialog, "r", created)
    assert {var: found for var, found in problems.items() if found} == {}


def test_a_field_the_script_reads_but_the_server_lacks_is_reported():
    """protects=the contract test above cannot pass vacuously; fails_when=a made-up read is not named."""
    script = "function F { $tk.number; $tk.invented; $tk.alsoInvented }"
    assert missing_fields(script, "tk", {"number"}) == ["alsoInvented", "invented"]


async def test_every_ticket_and_entry_has_exactly_the_contract_fields(world):
    """protects=T-85-71 the projection is explicit and closed; fails_when=a ticket or an entry has a field the
    contract does not name, or lacks one."""
    await _rich_ticket(world)
    [shown] = (await world.list()).json()["tickets"]
    assert set(shown) == set(c.TICKET_FIELDS)
    assert {e["kind"] for e in shown["entries"]} <= set(c.ENTRY_KINDS)
    assert all(set(e) == set(c.ENTRY_FIELDS) for e in shown["entries"])
    assert all(set(ci) == set(c.CITATION_FIELDS) for e in shown["entries"] for ci in e["citations"])
    assert set(projection.tray_display("x")) == set(c.DISPLAY_FIELDS)
    assert set((await world.list()).json()) == set(c.LIST_RESPONSE_FIELDS)


# ---------------------------------------------------------------- request fields the script sends

def test_every_field_the_script_sends_is_one_the_request_models_accept():
    """protects=D-05 the script's bodies fit the models; fails_when=the create body, its client, its endpoint
    info or a confirm or help payload carries a key the server model does not declare."""
    main, second = read(MAIN_PATH), read(SECOND_PATH)
    dialog = function_body(main, "Show-TicketDialog")
    body = block_after(dialog, r"\$newBody\s*=\s*@\{")
    assert set(top_level_keys(body)) <= set(tray.TrayTicketRequest.model_fields)
    assert set(top_level_keys(block_after(body, r"client\s*=\s*@\{"))) <= set(tray.TrayClient.model_fields)
    info = block_after(function_body(main, "Get-EndpointInfo"), r"@\{")
    assert {"username"} <= set(top_level_keys(info)) <= set(tray.EndpointInfo.model_fields)
    payloads = [block_after(second[m.start():], r"@\{") for m in re.finditer(r"\$payload\s*=\s*@\{", second)]
    assert [set(top_level_keys(p)) for p in payloads] == [set(tray.ConfirmRequest.model_fields), set(tray.HelpRequest.model_fields)]


async def test_every_template_the_script_offers_is_accepted(world):
    """protects=D-02 the Raise a Ticket templates (id, type, priority) all create a ticket; fails_when=one of
    the script's templates is refused by the server, so a user could not raise it."""
    main = read(MAIN_PATH)
    templates = re.findall(r"Id='(\w+)'.*?Type='(\w+)'.*?Priority='(\w+)'", block_after(main, r"\$Templates\s*=\s*@\("))
    assert [t[0] for t in templates] == list(c.TEMPLATE_IDS)
    for template, ticket_type, priority in templates:
        response = await world.create("a1", template=template, type=ticket_type, priority=priority)
        assert response.status_code == 200, (template, response.text)
        stored = await world.stored(response.json()["ticket_id"])
        assert stored["requester_channel"]["template"] == template and stored["type"] == ticket_type


# ---------------------------------------------------------------- the AI-assisted line

async def test_the_ai_assisted_line_appears_once_above_an_answer(world):
    """protects=the script adds the line unless the text already starts with it, and the server never adds it, so
    it shows exactly once; fails_when=the server's answer text carries the mark (it would then be shown by both) or
    the script's guard is gone."""
    ticket = await raised_and_answered(world)
    [shown] = (await world.list()).json()["tickets"]
    [answer] = shown["entries"]
    assert answer["text"] == ANSWER and not answer["text"].startswith(messages.MARK)
    second = read(SECOND_PATH)
    assert f"'{messages.MARK}'" in second and "-not $text.StartsWith($mark)" in second

    def as_the_script_shows(text):
        return ([] if text.startswith(messages.MARK) else [messages.MARK]) + [text]

    for text in (answer["text"], messages.MARK + "\n" + ANSWER):
        assert "\n".join(as_the_script_shows(text)).count(messages.MARK) == 1
    assert ticket["desk"]["phase"] == "posted"
