"""
Tests for scheduled reports: framework_id field, PDF wiring, delivery logging,
history endpoint, and SMTP validation.

Pattern: asyncio.run() + TestClient + MagicMock/AsyncMock (no pytest-asyncio).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _col():
    """Return a mock collection with standard async methods."""
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="fake-id"))
    col.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    col.count_documents = AsyncMock(return_value=0)

    # find().to_list() chain
    _find_cursor = MagicMock()
    _find_cursor.to_list = AsyncMock(return_value=[])
    _find_cursor.sort = MagicMock(return_value=_find_cursor)
    col.find = MagicMock(return_value=_find_cursor)

    return col


def _db_mock(**overrides):
    """Return a mock database with standard collections."""
    db = MagicMock()
    db.report_schedules = _col()
    db.report_delivery_logs = _col()
    db.smtp_config = _col()
    db.compliance_frameworks = _col()
    db.alerts = _col()
    db.assets = _col()
    db.incidents = _col()
    db.agents = _col()
    db.tenants = _col()
    for k, v in overrides.items():
        setattr(db, k, v)
    return db


_TENANT_USER = {
    "email": "admin@acme.com",
    "tenant_id": "tenant-abc",
    "role": "Tenant Admin",
    "username": "admin",
}

_SUPER_USER = {
    "email": "super@omni.ai",
    "tenant_id": "platform-admin",
    "role": "super_admin",
    "username": "super",
}


def _make_app(db):
    """Create a FastAPI test app with scheduled_reports_endpoints router."""
    import scheduled_reports_endpoints as ep_mod
    app = FastAPI()
    app.include_router(ep_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _TENANT_USER
    return app, ep_mod


# ---------------------------------------------------------------------------
# Task 1 (RED): All tests must FAIL before implementation
# ---------------------------------------------------------------------------

class TestScheduledReportFrameworkId:
    """Tests for framework_id and framework_name persistence (SCHED-01)."""

    def test_create_schedule_with_framework_id(self):
        """create_schedule() must persist framework_id and framework_name."""
        import scheduled_reports_service as svc

        db = _db_mock()
        # Provide SMTP config so the validation passes (this test is about framework_id, not SMTP)
        db.smtp_config.find_one = AsyncMock(return_value={"host": "smtp.example.com"})

        async def run():
            with patch("scheduled_reports_service.get_database", return_value=db):
                schedule = await svc.create_schedule(
                    tenant_id="tenant-abc",
                    created_by="admin@acme.com",
                    data={
                        "name": "SOC2 Weekly",
                        "report_type": "compliance_summary",
                        "frequency": "weekly",
                        "delivery_channel": "email",
                        "recipients": ["a@b.com"],
                        "framework_id": "soc2",
                        "framework_name": "SOC 2",
                    },
                )
            return schedule

        schedule = asyncio.run(run())
        assert schedule.get("framework_id") == "soc2", (
            f"Expected framework_id='soc2', got {schedule.get('framework_id')!r}"
        )
        assert schedule.get("framework_name") == "SOC 2", (
            f"Expected framework_name='SOC 2', got {schedule.get('framework_name')!r}"
        )

    def test_list_schedules_returns_framework_id(self):
        """create_schedule() must persist framework_id so list_schedules() can return it.

        This test calls create_schedule() and verifies the doc passed to insert_one
        contains framework_id and framework_name. It fails before implementation
        because create_schedule() does not yet include those fields.
        """
        import scheduled_reports_service as svc

        db = _db_mock()
        # Provide SMTP config so the validation passes (this test is about framework_id)
        db.smtp_config.find_one = AsyncMock(return_value={"host": "smtp.example.com"})

        async def run():
            with patch("scheduled_reports_service.get_database", return_value=db):
                schedule = await svc.create_schedule(
                    tenant_id="tenant-abc",
                    created_by="admin@acme.com",
                    data={
                        "name": "SOC2 Weekly",
                        "report_type": "compliance_summary",
                        "frequency": "weekly",
                        "delivery_channel": "email",
                        "recipients": ["a@b.com"],
                        "framework_id": "soc2",
                        "framework_name": "SOC 2",
                    },
                )
            return schedule

        schedule = asyncio.run(run())
        # Verify insert_one was called with the framework fields
        inserted_doc = db.report_schedules.insert_one.call_args[0][0]
        assert inserted_doc.get("framework_id") == "soc2", (
            f"insert_one doc missing framework_id='soc2', got {inserted_doc.get('framework_id')!r}"
        )
        assert inserted_doc.get("framework_name") == "SOC 2", (
            f"insert_one doc missing framework_name='SOC 2', got {inserted_doc.get('framework_name')!r}"
        )


class TestGeneratePdfWiring:
    """Tests for _generate_pdf wiring when framework_id is set (SCHED-01)."""

    def test_run_now_calls_generate_pdf_when_framework_set(self):
        """run_report_now() must call _generate_pdf_for_schedule when framework_id set."""
        import scheduled_reports_service as svc

        schedule_doc = {
            "_id": "oid",
            "id": "sched-1",
            "tenant_id": "tenant-abc",
            "name": "SOC2 Weekly",
            "report_type": "compliance_summary",
            "frequency": "weekly",
            "delivery_channel": "email",
            "recipients": ["a@b.com"],
            "framework_id": "soc2",
            "framework_name": "SOC 2",
            "format": "pdf",
            "send_at_hour": 8,
        }

        db = _db_mock()
        db.report_schedules.find_one = AsyncMock(return_value=schedule_doc)

        mock_pdf_gen = AsyncMock(return_value={"filename": "test.pdf", "url": "/static/reports/test.pdf"})

        async def run():
            with patch("scheduled_reports_service.get_database", return_value=db), \
                 patch("scheduled_reports_service._generate_pdf_for_schedule", mock_pdf_gen), \
                 patch("scheduled_reports_service.email_service") as mock_email:
                mock_email.send_report = AsyncMock()
                await svc.run_report_now("sched-1", "tenant-abc", "Tenant Admin")

        asyncio.run(run())
        mock_pdf_gen.assert_called_once()
        call_kwargs = mock_pdf_gen.call_args
        assert call_kwargs[1].get("framework_id") == "soc2" or (
            len(call_kwargs[0]) > 0 and "soc2" in call_kwargs[0]
        ), f"_generate_pdf_for_schedule not called with framework_id='soc2'. Call: {call_kwargs}"


class TestDeliveryLogging:
    """Tests for _write_delivery_log (SCHED-02)."""

    def test_run_now_writes_delivery_log_on_success(self):
        """On successful delivery, insert a log entry with status='success'."""
        import scheduled_reports_service as svc

        schedule_doc = {
            "_id": "oid",
            "id": "sched-1",
            "tenant_id": "tenant-abc",
            "name": "Weekly Report",
            "report_type": "compliance_summary",
            "frequency": "weekly",
            "delivery_channel": "email",
            "recipients": ["a@b.com"],
            "framework_id": None,
            "format": "pdf",
            "send_at_hour": 8,
        }

        db = _db_mock()
        db.report_schedules.find_one = AsyncMock(return_value=schedule_doc)

        async def run():
            with patch("scheduled_reports_service.get_database", return_value=db), \
                 patch("scheduled_reports_service.email_service") as mock_email:
                mock_email.send_report = AsyncMock()
                await svc.run_report_now("sched-1", "tenant-abc", "Tenant Admin")

        asyncio.run(run())

        db.report_delivery_logs.insert_one.assert_called_once()
        call_args = db.report_delivery_logs.insert_one.call_args[0][0]
        assert call_args.get("status") == "success", (
            f"Expected status='success', got {call_args.get('status')!r}"
        )
        assert call_args.get("schedule_id") == "sched-1", (
            f"Expected schedule_id='sched-1', got {call_args.get('schedule_id')!r}"
        )

    def test_run_now_writes_delivery_log_on_failure(self):
        """On delivery failure, insert a log entry with status='failure' and non-empty error."""
        import scheduled_reports_service as svc

        schedule_doc = {
            "_id": "oid",
            "id": "sched-1",
            "tenant_id": "tenant-abc",
            "name": "Weekly Report",
            "report_type": "security_posture",
            "frequency": "weekly",
            "delivery_channel": "email",
            "recipients": ["a@b.com"],
            "framework_id": None,
            "format": "pdf",
            "send_at_hour": 8,
        }

        db = _db_mock()
        db.report_schedules.find_one = AsyncMock(return_value=schedule_doc)

        async def run():
            with patch("scheduled_reports_service.get_database", return_value=db), \
                 patch("scheduled_reports_service.email_service") as mock_email:
                mock_email.send_report = AsyncMock(side_effect=Exception("SMTP connection refused"))
                try:
                    await svc.run_report_now("sched-1", "tenant-abc", "Tenant Admin")
                except Exception:
                    pass  # We expect the exception to propagate

        asyncio.run(run())

        db.report_delivery_logs.insert_one.assert_called_once()
        call_args = db.report_delivery_logs.insert_one.call_args[0][0]
        assert call_args.get("status") == "failure", (
            f"Expected status='failure', got {call_args.get('status')!r}"
        )
        assert call_args.get("error"), (
            f"Expected non-empty 'error' field, got {call_args.get('error')!r}"
        )


class TestDeliveryHistoryEndpoint:
    """Tests for GET /{schedule_id}/history endpoint (SCHED-02)."""

    def test_delivery_history_endpoint_returns_logs(self):
        """GET /api/reports/scheduled/{id}/history must return logs and total."""
        logs = [
            {
                "id": "log-1",
                "schedule_id": "sched-1",
                "tenant_id": "tenant-abc",
                "status": "success",
                "run_at": "2026-06-20T08:00:00Z",
                "recipients": ["a@b.com"],
            },
            {
                "id": "log-2",
                "schedule_id": "sched-1",
                "tenant_id": "tenant-abc",
                "status": "failure",
                "error": "SMTP error",
                "run_at": "2026-06-21T08:00:00Z",
                "recipients": ["a@b.com"],
            },
        ]

        db = _db_mock()
        db.report_delivery_logs.find.return_value.sort.return_value.to_list = AsyncMock(return_value=logs)

        import scheduled_reports_endpoints as ep_mod
        app = FastAPI()
        app.include_router(ep_mod.router)
        app.dependency_overrides[get_current_user] = lambda: _TENANT_USER

        with patch("scheduled_reports_service.get_database", return_value=db):
            with TestClient(app) as client:
                resp = client.get("/api/reports/scheduled/sched-1/history")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert "logs" in body, f"Expected 'logs' key in response, got: {body}"
        assert body.get("total") == 2, f"Expected total=2, got {body.get('total')}"
        assert len(body["logs"]) == 2


class TestSmtpValidation:
    """Test that creating a schedule with email delivery requires SMTP config (SCHED-01)."""

    def test_create_schedule_smtp_not_configured_returns_422(self):
        """POST to create email schedule when SMTP not configured must return 422."""
        db = _db_mock()
        # SMTP not configured — smtp_config.find_one returns None
        db.smtp_config.find_one = AsyncMock(return_value=None)

        import scheduled_reports_endpoints as ep_mod
        app = FastAPI()
        app.include_router(ep_mod.router)
        app.dependency_overrides[get_current_user] = lambda: _TENANT_USER

        with patch("scheduled_reports_service.get_database", return_value=db):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/reports/scheduled",
                    json={
                        "name": "SOC2 Weekly",
                        "report_type": "compliance_summary",
                        "frequency": "weekly",
                        "delivery_channel": "email",
                        "recipients": ["a@b.com"],
                        "framework_id": "soc2",
                    },
                )

        assert resp.status_code == 422, (
            f"Expected 422 when SMTP not configured, got {resp.status_code}: {resp.text}"
        )
        detail = resp.json().get("detail", "")
        assert "smtp" in detail.lower() or "SMTP" in detail, (
            f"Expected 'SMTP' in detail, got: {detail!r}"
        )
