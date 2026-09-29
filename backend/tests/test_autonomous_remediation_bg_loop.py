"""Regression for the 2026-09-28 startup crash in
`app_background_tasks.autonomous_remediation_loop()`:

    NameError: name 'get_database' is not defined
    (get_database was called but never imported into this module)

...which masked itself behind a second error once the except handler tried
to report it:

    UnboundLocalError: cannot access local variable 'tid' where it is not
    associated with a value
    (the except handler logged `tid`, but `tid` was only ever assigned
    inside the tenant for-loop -- a failure before or during
    `get_database()`/`db._db.tenants.find()` left it unbound)

Fix: import `get_database` at module scope, and seed `tid = None` before
the try block on every iteration so the except handler always has a value
to report, even when the failure happens before any tenant is reached.
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import app_background_tasks

pytestmark = pytest.mark.asyncio


class _StopLoop(Exception):
    """Raised from the patched asyncio.sleep to end the `while True` loop
    after exactly one iteration, so the coroutine under test returns
    control instead of running forever."""


async def _sleep_once_then_stop(*_a, **_kw):
    raise _StopLoop()


class TestAutonomousRemediationLoopCrashRegression:
    def test_get_database_is_imported_at_module_level(self):
        assert hasattr(app_background_tasks, "get_database"), (
            "autonomous_remediation_loop() calls get_database() as a bare "
            "name -- it must be imported at module scope or every call "
            "raises NameError"
        )

    async def test_db_lookup_failure_before_any_tenant_does_not_raise_unbound_local(self):
        # get_database() itself fails (e.g. Mongo not connected yet at
        # startup) -- the for-loop over tenants never runs, so `tid` is
        # never assigned this iteration. Before the fix, logging that
        # failure raised UnboundLocalError instead of the original error.
        with patch.object(app_background_tasks, "get_database", side_effect=RuntimeError("db down")), \
             patch.object(app_background_tasks, "AutonomousRemediationService", return_value=MagicMock()), \
             patch("app_background_tasks.asyncio.sleep", new=_sleep_once_then_stop):
            with pytest.raises(_StopLoop):
                await app_background_tasks.autonomous_remediation_loop()
            # Reaching _StopLoop (not NameError/UnboundLocalError) proves
            # the except handler survived logging the db-down error.

    async def test_tenant_scan_failure_reports_the_failing_tenant_id(self):
        db = MagicMock()
        db._db.tenants.find.return_value.to_list = AsyncMock(
            return_value=[{"id": "tenant-a"}]
        )
        service = MagicMock()
        service.run_cycle = AsyncMock(side_effect=RuntimeError("boom"))

        with patch.object(app_background_tasks, "get_database", return_value=db), \
             patch.object(app_background_tasks, "AutonomousRemediationService", return_value=service), \
             patch("app_background_tasks.asyncio.sleep", new=_sleep_once_then_stop), \
             patch("app_background_tasks.logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            with pytest.raises(_StopLoop):
                await app_background_tasks.autonomous_remediation_loop()

            assert mock_logger.error.called
            logged_args = mock_logger.error.call_args.args
            assert "tenant-a" in logged_args, (
                "the except handler should report the tenant id that was "
                "being processed when run_cycle failed, not crash trying to"
            )
