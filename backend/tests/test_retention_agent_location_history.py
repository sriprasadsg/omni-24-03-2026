"""
RetentionService.cleanup_agent_location_history() — Phase 46 plan 46-03 (GAUD-01, D-01) —
is retired (Phase 82 WR-04).

agent_location_history retention (365 days by default) runs through retention_job: the
nightly job and POST /api/retention/run, tenant-scoped and behind the confirmation gate
(registry in retention_gate, behaviour in test_retention_job). The legacy RetentionService
deleted across every tenant with no gate, so it refuses to run; these tests pin that.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import retention_service as retention_service_mod


def test_the_legacy_service_refuses_to_run():
    db = MagicMock()
    db.agent_location_history.delete_many = AsyncMock()
    with pytest.raises(RuntimeError, match="retention_job"):
        retention_service_mod.RetentionService(db)
    db.agent_location_history.delete_many.assert_not_awaited()


def test_location_history_is_in_the_gated_registry():
    import retention_gate
    assert "agent_location_history" in retention_gate.BY_ID
