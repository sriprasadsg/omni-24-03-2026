"""85-24: the output checks fold the answer before every rule (CR-101, D-19, DESK-03, T-85-19, T-85-48, T-85-87).

Value: protects=a model reply can no longer carry a foreign link, address, phone number or command past the
output checks behind a zero-width, bidi, soft-hyphen, default-ignorable, full-width, ideographic-dot or look-alike
character, and the text that is posted or kept as a staff draft is exactly the folded text the checks accepted;
fails_when=a hidden, compatibility or look-alike character lets a foreign fragment through, the stored text
differs from the checked text, or the fold is not idempotent; no_claim=whether an answer is helpful, and the
input-side cleaning (test_service_desk_sanitize.py).

Every invisible or look-alike character is written as an escape or built with chr(), never pasted.
"""
import json
import os
import sys
import unicodedata

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import checks, sanitize, worker
from service_desk.model import OllamaClient
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_worker_support import (Clock, _desk_env, add_tenant, job, kinds, queue,  # noqa: F401
                                               rows, stand_in, stored, world)

ARTICLE = "Open the Settings page. Contact IT support from the tray for help."
ZWSP = "​"
ACCEPTED = "Open your company's sign-in page and choose Forgot password."
FULLWIDTH_FORGOT = "".join(chr(0xFF00 + ord(c) - 0x20) for c in "Forgot")


def verdict(answer, article=ARTICLE):
    return checks.check(checks.Reply(answer=answer, cited=[1]), [1], {1: article})


# ---------------------------------------------------------------- the reviewer's strings (CR-101)

@pytest.mark.parametrize("answer,expected", [
    ("Visit evil." + ZWSP + "com now for Settings page help", "foreign_link"),
    ("Visit evil" + ZWSP + ".com for Settings help", "foreign_link"),
    ("Visit ｅｖｉｌ．ｃｏｍ Settings", "foreign_link"),
    ("Visit EVIL。com Settings", "foreign_link"),
    ("Mail a" + ZWSP + "@evil.com about Settings", "foreign_email"),
    ("Mail x@evil" + ZWSP + ".com about Settings", "foreign_email"),
    ("Visit evil.com now", "foreign_link"),
], ids=["zwsp-after-dot", "zwsp-before-dot", "fullwidth-domain", "ideographic-stop", "email-local-zwsp",
        "email-domain-zwsp", "plain-control"])
def test_the_reviewers_strings_are_refused(answer, expected):
    assert verdict(answer) == expected


def test_verdict_of_raw_json_folds_too():
    raw = json.dumps({"answer": "Visit evil." + ZWSP + "com now", "cited": [1]})
    assert checks.verdict(raw, [1], {1: ARTICLE}) == "foreign_link"


# ---------------------------------------------------------------- the dots: pinned, not assumed

def test_what_nfkc_does_to_the_three_dots_is_pinned():
    nfkc = unicodedata.normalize
    assert nfkc("NFKC", "．") == "."
    assert nfkc("NFKC", "｡") == "。"
    assert nfkc("NFKC", "。") == "。"


@pytest.mark.parametrize("raw", ["EVIL。com", "evil．com", "evil｡com"])
def test_fold_text_maps_every_idna_dot_to_a_full_stop(raw):
    assert sanitize.fold_text(raw) == raw[:4] + "." + "com"


def test_fold_text_is_idempotent_and_total():
    for sample in ("Visit evil." + ZWSP + "com", "ｅｖｉｌ．ｃｏｍ", "a­b", ""):
        once = sanitize.fold_text(sample)
        assert sanitize.fold_text(once) == once
    assert sanitize.fold_text(None) == ""
    assert sanitize.fold_text(5) == ""


# ---------------------------------------------------------------- parse_reply returns the folded answer

def test_parse_reply_returns_the_folded_answer():
    assert checks.parse_reply(json.dumps({"answer": "a" + ZWSP + "b", "cited": [1]})).answer == "ab"
    reply = checks.parse_reply(json.dumps({"answer": "ＡＢＣ １", "cited": [1]}))
    assert reply.answer == "ABC 1" and reply.cited == [1]


# ---------------------------------------------------------------- the pipeline: handed off, and stored folded

async def test_a_hidden_character_link_is_handed_off_not_posted(world):
    ticket, job_id = await queue(world, 1)
    transport, calls = stand_in(answer="Visit evil." + ZWSP + "com now")
    await worker.run_once(world, client=OllamaClient(transport=transport), clock=Clock())
    assert (await job(world, job_id))["reason"] == "output_check_failed"
    ledger_rows = await rows(world)
    assert [r["reasonCode"] for r in ledger_rows] == ["output_check_failed"]
    assert not {"ai_answer", "ai_draft"} & set(kinds(await stored(world, ticket)))


async def test_a_hidden_character_link_is_handed_off_in_drafts_mode_too(world):
    await add_tenant(world, "t2", mode="drafts")
    ticket, job_id = await queue(world, 2, tenant="t2")
    transport, calls = stand_in(answer="Visit evil." + ZWSP + "com now")
    await worker.run_once(world, client=OllamaClient(transport=transport), clock=Clock())
    assert (await job(world, job_id))["reason"] == "output_check_failed"
    assert not {"ai_answer", "ai_draft"} & set(kinds(await stored(world, ticket)))


def _folded_reply():
    return "Open your company's sign-in page and choose " + FULLWIDTH_FORGOT + " pass­word."


async def test_an_accepted_reply_is_posted_in_the_folded_form(world):
    ticket, _ = await queue(world, 3)
    transport, _calls = stand_in(answer=_folded_reply())
    await worker.run_once(world, client=OllamaClient(transport=transport), clock=Clock())
    comments = [c for c in (await stored(world, ticket))["comments"] if c["kind"] == "ai_answer"]
    assert len(comments) == 1
    text = comments[0]["text"]
    assert text == sanitize.fold_text(_folded_reply()) == ACCEPTED
    assert not any(unicodedata.category(ch) == "Cf" for ch in text)


async def test_an_accepted_reply_is_kept_as_a_folded_staff_draft_in_drafts_mode(world):
    await add_tenant(world, "t2", mode="drafts")
    ticket, _ = await queue(world, 4, tenant="t2")
    transport, _calls = stand_in(answer=_folded_reply())
    await worker.run_once(world, client=OllamaClient(transport=transport), clock=Clock())
    comments = [c for c in (await stored(world, ticket))["comments"] if c["kind"] == "ai_draft"]
    assert len(comments) == 1
    assert comments[0]["visibility"] == "staff"
    assert comments[0]["text"] == ACCEPTED
