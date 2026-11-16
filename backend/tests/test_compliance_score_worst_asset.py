"""Compliance score: a control takes its worst asset's status, and the payload says how much was assessed.

Value: protects=a failing computer counting against a control even when another computer passes it, in the live
score, the threat score and the daily snapshot; the counts behind "X of Y controls assessed" on the Compliance
screen; fails_when=the last asset_compliance row read decides a control's status, or the coverage counts are
missing or wrong; no_claim=which controls the agents reach (test_agent_check_names_mapped.py).
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app_background_tasks  # noqa: E402
import compliance_score_endpoints as score_mod  # noqa: E402
from authentication_service import get_current_user  # noqa: E402

ONE_CONTROL = [{"id": "fw1", "name": "FW1", "shortName": "FW1", "controls": [{"id": "C1", "category": "Audit"}]}]


def _rows(*statuses):
    return [{"controlId": "C1", "assetId": f"asset-{n}", "status": s, "tenantId": "t1"} for n, s in enumerate(statuses)]


def _cursor(items):
    async def gen(*a, **k):
        for item in items:
            yield item
    return MagicMock(side_effect=lambda *a, **k: gen())


def _db(frameworks, ac_rows):
    db = MagicMock()
    db.compliance_frameworks.find = _cursor(frameworks)
    db._db.compliance_frameworks.find = _cursor(frameworks)
    db.asset_compliance.find = _cursor(ac_rows)
    db.vulnerabilities.find = _cursor([])
    db.assets.find = _cursor([])
    return db


def _user():
    u = MagicMock()
    u.role, u.tenant_id, u.username = "admin", "t1", "admin@t1"
    return u


def _get(path, db):
    app = FastAPI()
    app.include_router(score_mod.router)
    app.dependency_overrides[get_current_user] = _user
    with patch.object(score_mod, "get_database", return_value=db), \
            patch.object(score_mod.cache, "get", return_value=None), \
            patch.object(score_mod.cache, "set", return_value=True):
        resp = TestClient(app).get(path)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_a_failing_asset_is_not_hidden_by_a_passing_one_read_after_it():
    fw = _get("/api/compliance/score", _db(ONE_CONTROL, _rows("Non-Compliant", "Compliant")))["frameworks"][0]
    assert (fw["passing"], fw["failing"], fw["score"]) == (0, 1, 0.0), fw


def test_a_failing_asset_read_last_still_fails_the_control():
    fw = _get("/api/compliance/score", _db(ONE_CONTROL, _rows("Compliant", "Non-Compliant")))["frameworks"][0]
    assert (fw["passing"], fw["failing"]) == (0, 1), fw


def test_a_warning_on_one_asset_makes_the_control_partial():
    fw = _get("/api/compliance/score", _db(ONE_CONTROL, _rows("Warning", "Compliant", "Pass")))["frameworks"][0]
    assert (fw["passing"], fw["partial"], fw["failing"]) == (0, 1, 0), fw


def test_the_payload_says_how_many_controls_were_assessed():
    frameworks = [
        {"id": "soc2", "name": "SOC 2", "shortName": "SOC 2",
         "controls": [{"id": "CC6.1", "category": "Access Control"}, {"id": "CC6.2", "category": "Cryptography"}]},
        {"id": "iso", "name": "ISO", "shortName": "ISO",
         "controls": [{"id": "A.1", "category": "Audit"}, {"id": "A.2", "category": "Audit"}, {"id": "A.3"}]},
    ]
    body = _get("/api/compliance/score", _db(frameworks, [{"controlId": "CC6.1", "status": "Compliant"}]))
    by_id = {f["framework_id"]: f for f in body["frameworks"]}
    assert (by_id["soc2"]["total_controls"], by_id["soc2"]["framework_controls"]) == (1, 2)
    assert (by_id["iso"]["total_controls"], by_id["iso"]["framework_controls"]) == (0, 3)
    assert (body["assessed_controls"], body["catalogue_controls"]) == (1, 5)


def test_the_threat_score_uses_the_worst_asset_too():
    body = _get("/api/compliance/threat-score", _db(ONE_CONTROL, _rows("Non-Compliant", "Compliant")))
    assert body["domains"]["compliance"]["pct"] == 0.0, body["domains"]["compliance"]


def test_the_daily_snapshot_uses_the_worst_asset_too():
    db = _db(ONE_CONTROL, _rows("Non-Compliant", "Compliant"))
    db._db.tenants.find.return_value.to_list = AsyncMock(return_value=[{"id": "t1"}])
    db._db.compliance_score_history.update_one = AsyncMock()
    sleep = AsyncMock(side_effect=[None, asyncio.CancelledError()])      # one pass, then stop
    with patch("database.get_database", return_value=db), patch.object(app_background_tasks.asyncio, "sleep", sleep):
        try:
            asyncio.run(app_background_tasks.snapshot_compliance_scores_loop())
        except asyncio.CancelledError:
            pass
    written = db._db.compliance_score_history.update_one.call_args.args[1]["$set"]
    assert written["compliance_pct"] == 0.0, written
