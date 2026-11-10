"""G-85-3: a reply that also cites numbers it was not given keeps its grounded answer (Phase 85, plan 85-37).

Value: protects=G-85-3, D-19, PROH-85-29, T-85-128: the printer starter answer that cites its own step numbers
([1, 2, 3, 4, 5, 6] with one article given) is drafted citing only the printer article; a number that was not
given is dropped; a reply that names no given article is still refused; the grounding rules compare only
against the given articles the reply cites; fails_when=a printer ticket goes to a person with
output_check_failed, a dropped citation is stored or lends its text to the answer, a reply citing nothing it
was given is used, or the parser reads an id the desk never gave as an article; no_claim=what a real model
cites (the live re-check is plan 85-38) and whether an answer is helpful.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import pipeline, retrieval, starters
from service_desk.checks import Reply, check, given_citations, parse_reply
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_support import seed_desk_tenant
from tests.test_service_desk_pipeline import _env, attempt, kinds, make_ticket, stored, world  # noqa: F401  (fixtures and helpers)

PRINTER_TITLE = "My printer will not print"
PRINTER_DESC = "My printer will not print, jobs just sit in the queue."
PRINTER_ANSWER = ("Check that the printer is on, has paper and shows no error.\n"
                  "Open the print queue, cancel the stuck job and print again.\n"
                  "If the printer shows as offline, turn it off, wait 30 seconds, and turn it on again.")
PRINTER_TEXT = next(s["content"] for s in starters.STARTERS if s["key"] == "printer")
TEXT_1 = "Open https://helpdesk.example.com/reset and choose Forgot password. Call 555-0142-77 for help."
TEXT_2 = "The portal is at https://portal.example.org/start."


def test_given_citations_keeps_only_given_numbers_in_first_seen_order():
    assert given_citations(Reply(answer="x", cited=[1, 2, 3, 4, 5, 6]), [1]) == [1]
    assert given_citations(Reply(answer="x", cited=[2, 9, 1, 2]), [1, 2]) == [2, 1]
    assert given_citations(Reply(answer="x", cited=[0, 7]), [1]) == []


def test_a_reply_copied_from_the_printer_steps_that_cites_the_step_numbers_passes():
    reply = Reply(answer=PRINTER_ANSWER, cited=[1, 2, 3, 4, 5, 6])
    assert check(reply, [1], {1: PRINTER_TEXT}) is None


def test_a_reply_that_names_no_given_article_is_refused():
    texts = {1: PRINTER_TEXT}
    assert check(Reply(answer=PRINTER_ANSWER, cited=[7]), [1], texts) == "unknown_citation"
    assert check(Reply(answer=PRINTER_ANSWER, cited=[0]), [1], texts) == "unknown_citation"
    assert check(Reply(answer=PRINTER_ANSWER, cited=[]), [1], texts) == "no_citation"


def test_the_grounding_rules_use_only_the_given_articles_the_reply_cites():
    texts = {1: TEXT_1, 2: TEXT_2}
    link = Reply(answer="Open https://evil.example/reset now.", cited=[1, 9])
    assert check(link, [1], texts) == "foreign_link"
    phone = Reply(answer="Choose Forgot password or call 555-0142-77.", cited=[2, 5])
    assert check(phone, [1, 2], texts) == "foreign_phone"
    # An article that was cited but not given never lends its text, even if the text is supplied.
    assert check(Reply(answer="Open https://portal.example.org/start.", cited=[1, 2]), [1], texts) == "foreign_link"


async def _printer_world_matches(db, ticket):
    question = pipeline._question(ticket)
    return retrieval.select(retrieval.score(question, await retrieval.candidates(db, "t1")))


async def _assert_printer_draft(world, ticket, job, generates):
    assert job["reason"] == "drafted", job
    assert len(generates) == 1
    after = await stored(world, ticket)
    assert kinds(after) == ["ai_draft"], kinds(after)
    [draft] = [c for c in after["comments"] if c["kind"] == "ai_draft"]
    [citation] = draft["ai"]["citations"]
    printer = await world.knowledge_docs.find_one({"tenantId": "t1", "title": "Fixing a printer that will not print"})
    assert citation["articleId"] == printer["id"]
    assert "staff_note" not in kinds(after) and "handoff_notice" not in kinds(after)


async def test_the_printer_ticket_is_drafted_citing_only_the_printer_article(world):
    """protects=G-85-3: UAT round 3 reproduced cited [1..6] for the printer; the ticket must not be handed off."""
    await seed_desk_tenant(world, "t1", mode="drafts", shadow=False)      # the default Drafts only mode
    ticket = await make_ticket(world, title=PRINTER_TITLE, description=PRINTER_DESC)
    matches = await _printer_world_matches(world, ticket)
    assert len(matches) == 1 and matches[0].title == "Fixing a printer that will not print"
    job, generates, _ = await attempt(world, ticket, answer=PRINTER_ANSWER, cited=(1, 2, 3, 4, 5, 6))
    await _assert_printer_draft(world, ticket, job, generates)
