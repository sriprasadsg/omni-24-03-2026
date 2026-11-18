"""SOC report export (soc_report). protects/fails_when/no_claim per test; real MongoDB."""
import csv
import io
import os
import sys
from datetime import datetime, timezone

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import soc_report
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)


def test_cells_that_would_run_as_formulas_are_neutralised():
    """protects=a title like =HYPERLINK(...) is written as text; fails_when=an alert title executes in a spreadsheet"""
    assert soc_report.safe("=cmd|' /C calc'!A0") == "'=cmd|' /C calc'!A0"
    assert soc_report.safe("+1") == "'+1" and soc_report.safe("normal") == "normal" and soc_report.safe(None) == ""
    assert soc_report.safe([{"value": "1.2.3.4"}, "x"]) == "1.2.3.4; x"


@pytest_asyncio.fixture
async def db(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    token = set_tenant_id("platform-admin")
    try:
        yield mongo_db
    finally:
        reset_tenant_id(token)


@pytest.mark.asyncio
async def test_alert_export_is_tenant_scoped_with_risk_and_sla(db):
    """protects=the CSV lists only the tenant's alerts of the period with risk and overdue columns; fails_when=another
    tenant's alert or a merged row appears; no_claim=-"""
    now = datetime.now(timezone.utc).isoformat()
    await db.security_alerts.insert_many([
        {"id": "a1", "tenantId": "t1", "severity": "critical", "title": "=evil()", "status": "open", "created_at": "2026-01-01T00:00:00+00:00", "lastSeenAt": now},
        {"id": "a2", "tenantId": "t2", "severity": "high", "title": "other", "status": "open", "created_at": now},
        {"id": "a3", "tenantId": "t1", "severity": "low", "title": "dup", "status": "merged", "created_at": now},
    ])
    rows = list(csv.DictReader(io.StringIO(await soc_report.export(db, "t1", "alerts", "7d"))))
    assert [r["id"] for r in rows] == ["a1"] and rows[0]["title"] == "'=evil()" and rows[0]["slaOverdue"] == "yes" and int(rows[0]["risk"]) > 0
