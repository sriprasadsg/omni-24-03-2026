"""
Tests for the ITAM ticketing bridge (Phase 73 Plan 04, D-09/D-10/D-11,
ITAM-API-03) — generalises `ticketing_bridge.py`'s remediation-only
Jira/ServiceNow bridge to ITAM assets and asset requests.

Covers, selectable via `-k <marker>`:
  - alert_shape: `_itam_event_to_alert_shape` field mapping, determinism,
    hostname fallback chain, no-asset-lookup-for-requests rule (Task 1)
  - itam_ticket_create: `create_ticket_for_itam_event`'s dedup guard,
    tenant-context bracketing, per-collection tenant-field write-back, and
    the additive `AssetRequest` ticket fields (Task 2)
  - manual_create: `POST /api/itam/tickets` — 404/409/422/403, credential-
    free response, real-app reachability (Task 3)

Conventions (this repository): backend modules imported by bare name
(never a `backend.` prefix); async functions driven via `asyncio.run()`
(pytest-asyncio not used in this file, mirrors test_ticketing_bridge.py);
FastAPI dependencies swapped via `app.dependency_overrides`.
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import ticketing_bridge
from itam_webhook_events import EVENT_ASSET_AUDIT_OVERDUE


def _run(coro):
    return asyncio.run(coro)


def _mock_db():
    db = MagicMock()
    for name in ("assets", "asset_requests", "ticketing_configs"):
        col = MagicMock()
        col.find_one = AsyncMock(return_value=None)
        col.update_one = AsyncMock()
        setattr(db, name, col)
    return db


def _sample_asset(**overrides):
    doc = {
        "id": "asset-1",
        "tenantId": "tenant-a",
        "assetTag": "IT-0001",
        "hostname": "web-01",
        "updatedAt": "2026-08-01T00:00:00Z",
    }
    doc.update(overrides)
    return doc


def _sample_asset_request(**overrides):
    doc = {
        "id": "ar-1",
        "tenant_id": "tenant-a",
        "item_description": "27-inch Monitor",
        "quantity": 2,
        "requester_id": "user-5",
        "request_date": "2026-08-01T00:00:00Z",
    }
    doc.update(overrides)
    return doc


# ---------------------------------------------------------------------------
# alert_shape (Task 1)
# ---------------------------------------------------------------------------
def test_alert_shape_asset_audit_overdue_key_set_matches_task_shape():
    db = _mock_db()
    task_alert = _run(ticketing_bridge._task_to_alert_shape(db, {"id": "t1"}))
    itam_alert = _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db, EVENT_ASSET_AUDIT_OVERDUE, "asset", _sample_asset()
        )
    )
    assert set(itam_alert.keys()) == set(task_alert.keys())


def test_alert_shape_no_none_values():
    db = _mock_db()
    alert = _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db, EVENT_ASSET_AUDIT_OVERDUE, "asset", _sample_asset()
        )
    )
    assert all(v is not None for v in alert.values())


def test_alert_shape_alert_id_deterministic_same_entity():
    db = _mock_db()
    a1 = _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db, EVENT_ASSET_AUDIT_OVERDUE, "asset", _sample_asset()
        )
    )
    a2 = _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db, EVENT_ASSET_AUDIT_OVERDUE, "asset", _sample_asset()
        )
    )
    assert a1["alert_id"] == a2["alert_id"]


def test_alert_shape_alert_id_differs_across_entities():
    db = _mock_db()
    a1 = _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db, EVENT_ASSET_AUDIT_OVERDUE, "asset", _sample_asset(id="asset-1")
        )
    )
    a2 = _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db, EVENT_ASSET_AUDIT_OVERDUE, "asset", _sample_asset(id="asset-2")
        )
    )
    assert a1["alert_id"] != a2["alert_id"]


def test_alert_shape_type_differs_between_audit_overdue_and_stuck_request():
    db = _mock_db()
    audit_alert = _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db, EVENT_ASSET_AUDIT_OVERDUE, "asset", _sample_asset()
        )
    )
    stuck_alert = _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db,
            "asset_request.stuck_pending_approval",
            "asset_request",
            _sample_asset_request(),
        )
    )
    assert audit_alert["type"] != stuck_alert["type"]


def test_alert_shape_manual_type_is_distinct_from_event_driven_type():
    db = _mock_db()
    manual_alert = _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db, ticketing_bridge.ITAM_TICKET_EVENT_MANUAL, "asset", _sample_asset()
        )
    )
    audit_alert = _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db, EVENT_ASSET_AUDIT_OVERDUE, "asset", _sample_asset()
        )
    )
    assert manual_alert["type"] != audit_alert["type"]


def test_alert_shape_hostname_prefers_hostname_field():
    db = _mock_db()
    alert = _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db,
            EVENT_ASSET_AUDIT_OVERDUE,
            "asset",
            _sample_asset(hostname="srv-42", assetTag="IT-0099"),
        )
    )
    assert alert["hostname"] == "srv-42"


def test_alert_shape_hostname_falls_back_to_asset_tag():
    db = _mock_db()
    alert = _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db,
            EVENT_ASSET_AUDIT_OVERDUE,
            "asset",
            _sample_asset(hostname=None, assetTag="IT-0099"),
        )
    )
    assert alert["hostname"] == "IT-0099"


def test_alert_shape_hostname_placeholder_when_neither_present():
    db = _mock_db()
    entity = {"id": "asset-9"}
    alert = _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db, EVENT_ASSET_AUDIT_OVERDUE, "asset", entity
        )
    )
    assert alert["hostname"]
    assert alert["hostname"] != "None"


def test_alert_shape_asset_request_never_looks_up_asset():
    db = _mock_db()
    _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db,
            "asset_request.stuck_pending_approval",
            "asset_request",
            _sample_asset_request(),
        )
    )
    db.assets.find_one.assert_not_called()


def test_alert_shape_description_contains_reason_and_identifying_text():
    db = _mock_db()
    alert = _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db, EVENT_ASSET_AUDIT_OVERDUE, "asset", _sample_asset(assetTag="IT-0055")
        )
    )
    assert "overdue" in alert["description"].lower()
    assert "IT-0055" in alert["description"]


def test_alert_shape_asset_request_description_contains_item_and_requester():
    db = _mock_db()
    alert = _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db,
            "asset_request.stuck_pending_approval",
            "asset_request",
            _sample_asset_request(item_description="Standing Desk", requester_id="user-9"),
        )
    )
    assert "Standing Desk" in alert["description"]
    assert "user-9" in alert["description"]


def test_alert_shape_no_credential_keys():
    db = _mock_db()
    alert = _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db, EVENT_ASSET_AUDIT_OVERDUE, "asset", _sample_asset()
        )
    )
    forbidden = {"jira_api_token", "snow_password", "api_token", "password", "token"}
    assert not (set(alert.keys()) & forbidden)


def test_alert_shape_performs_no_database_reads():
    """Nothing beyond the passed-in entity's own fields should leak in — no
    db lookups happen for either entity kind in this adapter."""
    db = _mock_db()
    _run(
        ticketing_bridge._itam_event_to_alert_shape(
            db, EVENT_ASSET_AUDIT_OVERDUE, "asset", _sample_asset()
        )
    )
    db.assets.find_one.assert_not_called()
    db.asset_requests.find_one.assert_not_called()


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
