"""Seeded frameworks: a control's status comes from its recent asset evidence, never from the seeded status.

Value: protects=the Framework Evaluator not showing the 22 seeded frameworks (SOC 1, SOC 3, CMMC, HITRUST, GDPR,
DORA, NIS2, FedRAMP Moderate, CCPA ...) as passing when nothing proves it; a failing computer failing the control;
fails_when=a seeded "Implemented" control passes without evidence, evidence older than 30 days still counts, a
Compliant asset hides a Non-Compliant one, or "not assessed" controls count in the framework score;
no_claim=the platform-record overrides some seeded modules apply afterwards (MFA rate, roles, scans).
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compliance_frameworks_endpoints import _score  # noqa: E402
from frameworks import soc1  # noqa: E402
from frameworks._db_eval import evaluate_from_db  # noqa: E402

NOW = datetime.now(timezone.utc)
RECENT = (NOW - timedelta(days=2)).isoformat()
STALE = (NOW - timedelta(days=35)).isoformat()


def _db(framework_id, control_ids, rows):
    """compliance_frameworks holds one seeded doc (every control "Implemented"); asset_compliance applies the
    query's $in on controlId and $gte on lastUpdated, as Mongo would."""
    async def find_one(query, *a, **k):
        if query.get("id") != framework_id:
            return None
        return {"id": framework_id, "controls": [
            {"id": cid, "name": f"Control {cid}", "category": "Access Control", "status": "Implemented"}
            for cid in control_ids]}

    def find(query, *a, **k):
        ids = set(query["controlId"]["$in"])
        since = query["lastUpdated"]["$gte"]

        async def gen():
            for row in rows:
                if row["controlId"] in ids and row["lastUpdated"] >= since:
                    yield row
        return gen()

    async def count_documents(query, *a, **k):      # the per-control count the evaluator used before
        return sum(1 for row in rows if row["controlId"] == query.get("controlId")
                   and row["status"] == query.get("status", row["status"])
                   and row["lastUpdated"] >= query.get("lastUpdated", {}).get("$gte", ""))

    db = MagicMock()
    db.compliance_frameworks.find_one = find_one
    db.asset_compliance.find = MagicMock(side_effect=find)
    db.asset_compliance.count_documents = count_documents
    return db


def _row(cid, status, when=RECENT, asset="a1"):
    return {"controlId": cid, "status": status, "lastUpdated": when, "assetId": asset}


def _statuses(results):
    return {r["id"]: r["status"] for r in results}


def test_a_seeded_control_without_evidence_is_not_assessed():
    results = asyncio.run(evaluate_from_db(_db("fw", ["C1"], []), "fw"))
    assert _statuses(results) == {"C1": "not_assessed"}


def test_recent_evidence_decides_and_the_worst_asset_wins():
    rows = [_row("PASS", "Compliant"),
            _row("FAIL", "Compliant", asset="a1"), _row("FAIL", "Non-Compliant", asset="a2"),
            _row("WARN", "Warning"), _row("WARN", "Compliant", asset="a2"),
            _row("OLD", "Compliant", when=STALE)]
    results = asyncio.run(evaluate_from_db(_db("fw", ["PASS", "FAIL", "WARN", "OLD", "NONE"], rows), "fw"))
    assert _statuses(results) == {"PASS": "pass", "FAIL": "fail", "WARN": "partial",
                                  "OLD": "not_assessed", "NONE": "not_assessed"}
    assert {r["id"]: r["evidence_count"] for r in results} == {"PASS": 1, "FAIL": 2, "WARN": 2, "OLD": 0, "NONE": 0}


def test_not_assessed_controls_stay_out_of_the_framework_score():
    s = _score([{"status": "pass"}, {"status": "fail"}, {"status": "not_assessed"}, {"status": "not_assessed"}])
    assert (s["score"], s["assessed"], s["not_assessed"], s["total"]) == (50.0, 2, 2, 4)


def test_a_framework_with_nothing_assessed_scores_nothing():
    s = _score([{"status": "not_assessed"}, {"status": "not_assessed"}])
    assert (s["score"], s["assessed"], s["passed"]) == (0, 0, 0)


def test_soc1_no_longer_passes_on_its_seeded_status():
    results = asyncio.run(soc1.evaluate_controls(_db("soc1_type2", ["CC1.1", "CC1.2"], [_row("CC1.2", "Compliant")])))
    assert _statuses(results) == {"CC1.1": "not_assessed", "CC1.2": "pass"}
