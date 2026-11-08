"""85-06 Task 1: the retrieval cut-off (D-18, DESK-02), tuned on the real starter articles.

Value: protects=a ticket is only answered when a real Help desk article of the tenant matches it well
enough, by one fixed retrieval score that no tenant, setting or model can move; fails_when=a labelled
question is accepted or rejected wrongly, the gap between the worst match and the best non-match shrinks
below the pinned floor, a global, foreign or non-Help-desk article becomes a candidate, or retrieval.py
starts reading a setting or the model; no_claim=the wording of the generated answer (85-13) and the
real-world hit rate on a tenant's own articles.

The questions of retrieval_set.jsonl are invented for this phase and are scored against
service_desk.starters.STARTERS, the same text the Knowledge Base button copies into a tenant.
"""
import ast
import json
from pathlib import Path

import pytest

from service_desk import retrieval
from service_desk.starters import STARTERS
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

FIXTURE = Path(__file__).parent / "fixtures" / "service_desk" / "retrieval_set.jsonl"

PINNED_CUT = 0.24
PINNED_MIN_TERMS = 2
PINNED_MARGIN_FLOOR = 0.22


def _cases():
    rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [row for row in rows if "_comment" not in row]


def _docs():
    return [{"id": s["key"], "title": s["title"], "content": s["content"], "tags": s["tags"]} for s in STARTERS]


def _best(question):
    matches = retrieval.score(question, _docs())
    return matches[0] if matches else None


def test_the_constants_are_pinned():
    assert retrieval.CUT == PINNED_CUT
    assert retrieval.MIN_TERMS == PINNED_MIN_TERMS
    assert retrieval.MARGIN_FLOOR == PINNED_MARGIN_FLOOR


def test_the_set_is_big_enough_and_covers_every_starter():
    cases = _cases()
    matches = [c for c in cases if c["expect"] == "match"]
    nones = [c for c in cases if c["expect"] == "none"]
    assert len(matches) >= 40 and len(nones) >= 40
    for starter in STARTERS:
        assert sum(1 for c in matches if c["article"] == starter["key"]) >= 3, starter["key"]
    assert {c["article"] for c in matches} == {s["key"] for s in STARTERS}


def test_every_labelled_match_is_accepted_and_cites_its_starter():
    wrong = []
    for case in (c for c in _cases() if c["expect"] == "match"):
        chosen = retrieval.select(retrieval.score(case["question"], _docs()))
        if not chosen or chosen[0].id != case["article"]:
            best = _best(case["question"])
            wrong.append((case["id"], case["question"], best and (best.id, round(best.score, 3), best.terms)))
    assert not wrong, wrong


def test_every_labelled_non_match_is_rejected():
    wrong = []
    for case in (c for c in _cases() if c["expect"] == "none"):
        if retrieval.select(retrieval.score(case["question"], _docs())):
            best = _best(case["question"])
            wrong.append((case["id"], case["question"], best and (best.id, round(best.score, 3), best.terms)))
    assert not wrong, wrong


def _gate(question):
    best = _best(question)
    return retrieval.gate_score(best) if best else 0.0


def test_the_margin_between_the_worst_match_and_the_best_non_match_holds():
    lowest = min(_gate(c["question"]) for c in _cases() if c["expect"] == "match")
    highest = max(_gate(c["question"]) for c in _cases() if c["expect"] == "none")
    margin = lowest - highest
    assert margin >= retrieval.MARGIN_FLOOR, (
        f"lowest match {lowest:.4f}, highest non-match {highest:.4f}, margin {margin:.4f} "
        f"< MARGIN_FLOOR {retrieval.MARGIN_FLOOR}")
    assert highest < retrieval.CUT <= lowest, (highest, retrieval.CUT, lowest)


def test_a_question_with_one_shared_word_is_stopped_by_the_term_count_alone():
    best = _best("Where can I find the Wi-Fi guest password for visitors")
    assert best.score >= retrieval.CUT and len(best.terms) < retrieval.MIN_TERMS
    assert retrieval.select([best]) == []


def test_a_question_that_names_the_subject_without_being_answered_passes_by_design():
    overlap = [c for c in _cases() if c["expect"] == "overlap"]
    assert len(overlap) >= 2
    for case in overlap:
        assert retrieval.select(retrieval.score(case["question"], _docs())), case["question"]


def test_a_second_starter_is_not_cited_for_an_unrelated_ticket():
    chosen = retrieval.select(retrieval.score("VPN will not connect from home", _docs()))
    assert [m.id for m in chosen][:1] == ["vpn"]
    assert "printer" not in [m.id for m in chosen]


def test_hyphen_and_dot_variants_meet():
    assert retrieval._terms("Wi-Fi") == retrieval._terms("wifi")
    assert retrieval._terms("e-mail") == retrieval._terms("email")
    assert retrieval._terms("printed printing prints") == ["print", "print", "print"]
    assert retrieval._terms("the and of to") == []
    assert retrieval._terms(None) == []


def test_an_empty_question_or_empty_candidates_return_nothing_without_raising():
    assert retrieval.score("", _docs()) == []
    assert retrieval.score("   ", _docs()) == []
    assert retrieval.score("the and of", _docs()) == []
    assert retrieval.score("printer", []) == []
    assert retrieval.score(None, _docs()) == []
    assert retrieval.select([]) == []


def test_retrieval_reads_no_setting():
    tree = ast.parse((Path(__file__).parent.parent / "service_desk" / "retrieval.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(("." * node.level) + (node.module or ""))
            imported.update(("." * node.level) + (node.module or "") + "." + a.name for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    joined = " ".join(sorted(imported))
    for forbidden in ("settings", "model", "os.environ", "getenv"):
        assert forbidden not in joined, (forbidden, joined)
    source = (Path(__file__).parent.parent / "service_desk" / "retrieval.py").read_text(encoding="utf-8")
    assert "os.environ" not in source and "getenv" not in source


async def test_candidates_are_only_the_tenants_own_help_desk_articles(mongo_db):  # noqa: F811
    docs = mongo_db.knowledge_docs
    await docs.insert_many([
        {"id": "own-a", "tenantId": "t1", "title": "A", "content": "a", "tags": [], "helpdesk": True},
        {"id": "own-b", "tenantId": "t1", "title": "B", "content": "b", "tags": [], "helpdesk": True},
        {"id": "not-marked", "tenantId": "t1", "title": "C", "content": "c", "tags": []},
        {"id": "marked-false", "tenantId": "t1", "title": "D", "content": "d", "tags": [], "helpdesk": False},
        {"id": "global-one", "tenantId": "global", "title": "E", "content": "e", "tags": [], "helpdesk": True},
        {"id": "other-tenant", "tenantId": "t2", "title": "F", "content": "f", "tags": [], "helpdesk": True},
    ])
    assert sorted(d["id"] for d in await retrieval.candidates(mongo_db, "t1")) == ["own-a", "own-b"]
    assert await retrieval.candidates(mongo_db, "global") == []
    assert await retrieval.candidates(mongo_db, "") == []
    assert await retrieval.candidates(mongo_db, None) == []
    assert [d["id"] for d in await retrieval.candidates(mongo_db, "t2")] == ["other-tenant"]


async def test_the_candidates_feed_the_same_score_the_starters_get(mongo_db):  # noqa: F811
    await mongo_db.knowledge_docs.insert_many(
        [{"id": s["key"], "tenantId": "t1", "title": s["title"], "content": s["content"], "tags": s["tags"],
          "helpdesk": True} for s in STARTERS])
    found = await retrieval.candidates(mongo_db, "t1")
    chosen = retrieval.select(retrieval.score("The printer shows offline", found))
    assert chosen and chosen[0].id == "printer"
