"""First direct test coverage for siem_engine.py (Phase 55-01, INT-04).

Covers SiemEngine.correlate_native_findings(): native v3.4 finding sources
(security_scan_results, vulnerabilities, fim_events, remediation_audit) are
read bounded/tenant-scoped, normalized into the same event shape
_normalize_log() emits, and evaluated via the EXISTING _evaluate_rules() —
a matching siem_rules doc creates exactly one security_cases document.

Fixture/mocking style cloned from test_remediation_guards.py.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from siem_engine import SiemEngine, NATIVE_FINDING_READ_LIMIT

pytestmark = pytest.mark.asyncio


def _mock_db(scans=None, vulns=None, fim=None, remediations=None, rules=None):
    db = MagicMock()

    db.security_scan_results.find.return_value.to_list = AsyncMock(return_value=scans or [])
    db.vulnerabilities.find.return_value.to_list = AsyncMock(return_value=vulns or [])
    db.fim_events.find.return_value.to_list = AsyncMock(return_value=fim or [])
    db.remediation_audit.find.return_value.to_list = AsyncMock(return_value=remediations or [])
    db.siem_rules.find.return_value.to_list = AsyncMock(return_value=rules or [])

    db.security_cases.insert_one = AsyncMock(return_value=MagicMock(inserted_id="case-1"))
    db.smtp_config.find_one = AsyncMock(return_value=None)
    db.users.find.return_value.to_list = AsyncMock(return_value=[])

    return db


def _scan_doc(**overrides):
    base = dict(
        id="scan-1", tenantId="t1", agentId="agent-1",
        severity="critical", verdict="Malicious", created_at="2026-08-01T00:00:00Z",
    )
    base.update(overrides)
    return base


def _matching_rule(**overrides):
    base = dict(
        id="rule-1", tenantId="t1", enabled=True, name="Native scan malicious",
        severity="Critical",
        conditions={"source": "native_scan", "category": "critical"},
    )
    base.update(overrides)
    return base


class TestCorrelateNativeFindings:
    async def test_matching_rule_creates_exactly_one_security_case(self):
        db = _mock_db(scans=[_scan_doc()], rules=[_matching_rule()])
        engine = SiemEngine(db)

        result = await engine.correlate_native_findings("t1")

        assert result["evaluated_count"] == 1
        assert result["sources"] == ["native_scan"]
        db.security_cases.insert_one.assert_called_once()
        inserted = db.security_cases.insert_one.call_args.args[0]
        assert inserted["tenantId"] == "t1"
        assert inserted["relatedEvents"] == ["scan-1"]

    async def test_no_matching_rule_creates_no_case(self):
        non_matching_rule = _matching_rule(conditions={"source": "native_scan", "category": "low"})
        db = _mock_db(scans=[_scan_doc()], rules=[non_matching_rule])
        engine = SiemEngine(db)

        result = await engine.correlate_native_findings("t1")

        assert result["evaluated_count"] == 1
        db.security_cases.insert_one.assert_not_called()

    async def test_no_native_findings_short_circuits_rule_evaluation(self):
        db = _mock_db(rules=[_matching_rule()])
        engine = SiemEngine(db)

        result = await engine.correlate_native_findings("t1")

        assert result == {"evaluated_count": 0, "sources": []}
        # _evaluate_rules never reached siem_rules.find when there are no events
        db.siem_rules.find.assert_not_called()

    async def test_reuses_evaluate_rules_not_a_parallel_loop(self):
        """Guards D-01: correlation must call the EXISTING _evaluate_rules,
        not reimplement rule matching."""
        db = _mock_db(scans=[_scan_doc()], rules=[_matching_rule()])
        engine = SiemEngine(db)
        engine._evaluate_rules = AsyncMock(wraps=engine._evaluate_rules)

        await engine.correlate_native_findings("t1")

        engine._evaluate_rules.assert_awaited_once()

    async def test_native_scan_bounded_read(self):
        db = _mock_db(scans=[_scan_doc()])
        engine = SiemEngine(db)

        await engine.correlate_native_findings("t1")

        for collection in (db.security_scan_results, db.vulnerabilities, db.fim_events, db.remediation_audit):
            collection.find.assert_called_once_with({"tenantId": "t1"})
            _, to_list_kwargs = collection.find.return_value.to_list.call_args
            assert to_list_kwargs.get("length") == NATIVE_FINDING_READ_LIMIT
