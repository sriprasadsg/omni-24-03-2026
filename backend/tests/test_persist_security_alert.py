"""
Tests for ueba_service.py's public `persist_security_alert` alias —
Phase 47 Plan 01 (Agent-Scoped Geo Security Detectors, prerequisite fix).

Regression test for 47-RESEARCH.md Pitfall 1: `ueba_service.py` only ever
defined a private `_persist_alert(...)` coroutine, but five existing
heartbeat call sites (shadow_ai, ueba_anomaly, fim_violation, pii_detected,
runtime_security — in agent_heartbeat_endpoints.py /
agent_heartbeat_alerts_service.py) do
`from ueba_service import persist_security_alert` inside a
`try/except ImportError: pass` guard. Because the public name never
existed, all five have silently no-op'd since they were written.

This file proves:
  1. The public name is importable (no ImportError).
  2. It IS the same object as `_persist_alert` (alias, not a re-implementation
     — a second/parallel alert-insert path is explicitly prohibited by the
     plan's `<prohibitions>`).
  3. Calling it actually inserts a doc into db.security_alerts carrying the
     given alert_type/severity (proves the fan-out fires end-to-end, not
     just that the name resolves).

Hermetic — no real Mongo, no real streaming broker, no real blockchain
write. Follows the hand-rolled AsyncMock/asyncio.run() convention from
test_agent_location_history.py._mock_db().

RED phase (Task 1): these tests MUST fail with
`ImportError: cannot import name 'persist_security_alert' from 'ueba_service'`
until Task 2 adds the alias.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import asyncio

# Deliberately NOT wrapped in try/except ImportError — this import failing
# IS the RED state we're asserting against for Task 1. Task 2 makes it pass.
import ueba_service
from ueba_service import persist_security_alert


def _run(coro):
    return asyncio.run(coro)


def _mock_db():
    db = MagicMock()

    alerts_col = MagicMock()
    alerts_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-alert-id"))
    db.security_alerts = alerts_col

    blockchain_col = MagicMock()
    blockchain_col.find_one = AsyncMock(return_value=None)
    blockchain_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-block-id"))
    db.blockchain_audit = blockchain_col

    return db


class TestPersistSecurityAlertImportable:
    def test_persist_security_alert_importable(self):
        assert persist_security_alert is not None

    def test_persist_security_alert_is_alias(self):
        # Must be the SAME object as _persist_alert — an alias, never a
        # second/parallel implementation (plan prohibition).
        assert ueba_service.persist_security_alert is ueba_service._persist_alert


class TestPersistSecurityAlertInserts:
    def test_persist_security_alert_inserts(self, monkeypatch):
        db = _mock_db()

        # Patch the streaming broker's publish so the fire-and-forget
        # asyncio.create_task(...) inside _persist_alert has something
        # awaitable/mockable instead of touching the real StreamBroker.
        import streaming_service
        mock_broker_publish = AsyncMock()
        monkeypatch.setattr(streaming_service.broker, "publish", mock_broker_publish)

        _run(
            persist_security_alert(
                db,
                alert_type="impossible_travel",
                severity="high",
                title="Impossible travel detected",
                description="Agent moved implausibly fast between check-ins.",
                metadata={"agent_id": "agent-1"},
            )
        )

        db.security_alerts.insert_one.assert_awaited_once()
        inserted = db.security_alerts.insert_one.await_args[0][0]
        assert inserted["type"] == "impossible_travel"
        assert inserted["severity"] == "high"
