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

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import ticketing_bridge
import itam_asset_endpoints
import itam_ticketing_endpoints
from auth_types import TokenData
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


# ---------------------------------------------------------------------------
# itam_ticket_create (Task 2)
# ---------------------------------------------------------------------------
def test_itam_ticket_create_asset_creates_jira_and_persists():
    db = _mock_db()
    asset = _sample_asset()
    with patch(
        "ticketing_bridge.get_ticketing_config", AsyncMock(return_value={"provider": "jira"})
    ), patch(
        "ticketing_bridge.create_jira_ticket",
        AsyncMock(return_value={"success": True, "ticket_key": "ITAM-1", "url": "https://x/ITAM-1"}),
    ) as mock_create:
        result = _run(
            ticketing_bridge.create_ticket_for_itam_event(
                db, "asset", asset, "tenant-a", EVENT_ASSET_AUDIT_OVERDUE
            )
        )

    assert result == {
        "ticket_provider": "jira",
        "ticket_ref": "ITAM-1",
        "ticket_url": "https://x/ITAM-1",
    }
    mock_create.assert_awaited_once()
    db.assets.update_one.assert_awaited_once()
    args, kwargs = db.assets.update_one.call_args
    assert args[0] == {"id": "asset-1", "tenantId": "tenant-a"}
    assert args[1]["$set"] == {
        "ticket_provider": "jira",
        "ticket_ref": "ITAM-1",
        "ticket_url": "https://x/ITAM-1",
    }


def test_itam_ticket_create_dedup_second_call_creates_nothing():
    db = _mock_db()
    asset = _sample_asset(ticket_ref="ITAM-1")
    with patch("ticketing_bridge.get_ticketing_config", AsyncMock()) as mock_config, patch(
        "ticketing_bridge.create_jira_ticket", AsyncMock()
    ) as mock_create:
        result = _run(
            ticketing_bridge.create_ticket_for_itam_event(
                db, "asset", asset, "tenant-a", EVENT_ASSET_AUDIT_OVERDUE
            )
        )

    assert result is None
    mock_config.assert_not_called()
    mock_create.assert_not_called()


def test_itam_ticket_create_asset_request_uses_snake_case_tenant_field():
    db = _mock_db()
    request = _sample_asset_request()
    with patch(
        "ticketing_bridge.get_ticketing_config", AsyncMock(return_value={"provider": "servicenow"})
    ), patch(
        "ticketing_bridge.create_servicenow_incident",
        AsyncMock(return_value={"success": True, "ticket_number": "INC01", "url": "https://x/INC01"}),
    ):
        _run(
            ticketing_bridge.create_ticket_for_itam_event(
                db, "asset_request", request, "tenant-a", "asset_request.stuck_pending_approval"
            )
        )

    db.asset_requests.update_one.assert_awaited_once()
    args, kwargs = db.asset_requests.update_one.call_args
    filter_used = args[0]
    assert filter_used == {"id": "ar-1", "tenant_id": "tenant-a"}
    # Proves a camelCase filter would match zero asset-request documents —
    # the two ITAM collections genuinely disagree on this field name.
    assert "tenantId" not in filter_used


def test_itam_ticket_create_no_config_returns_none_and_no_write():
    db = _mock_db()
    asset = _sample_asset()
    with patch("ticketing_bridge.get_ticketing_config", AsyncMock(return_value=None)):
        result = _run(
            ticketing_bridge.create_ticket_for_itam_event(
                db, "asset", asset, "tenant-a", EVENT_ASSET_AUDIT_OVERDUE
            )
        )
    assert result is None
    db.assets.update_one.assert_not_called()


def test_itam_ticket_create_provider_override_wins_over_config_default():
    db = _mock_db()
    asset = _sample_asset()
    with patch(
        "ticketing_bridge.get_ticketing_config", AsyncMock(return_value={"provider": "servicenow"})
    ), patch(
        "ticketing_bridge.create_jira_ticket",
        AsyncMock(return_value={"success": True, "ticket_key": "ITAM-2", "url": "u"}),
    ) as mock_jira, patch(
        "ticketing_bridge.create_servicenow_incident", AsyncMock()
    ) as mock_snow:
        result = _run(
            ticketing_bridge.create_ticket_for_itam_event(
                db, "asset", asset, "tenant-a", EVENT_ASSET_AUDIT_OVERDUE, provider_override="jira"
            )
        )

    assert result["ticket_provider"] == "jira"
    mock_jira.assert_awaited_once()
    mock_snow.assert_not_called()


def test_itam_ticket_create_unsuccessful_connector_writes_nothing():
    db = _mock_db()
    asset = _sample_asset()
    with patch(
        "ticketing_bridge.get_ticketing_config", AsyncMock(return_value={"provider": "jira"})
    ), patch(
        "ticketing_bridge.create_jira_ticket", AsyncMock(return_value={"success": False, "error": "boom"})
    ):
        result = _run(
            ticketing_bridge.create_ticket_for_itam_event(
                db, "asset", asset, "tenant-a", EVENT_ASSET_AUDIT_OVERDUE
            )
        )

    assert result is None
    db.assets.update_one.assert_not_called()


def test_itam_ticket_create_resolves_config_with_no_ambient_tenant_context():
    """Fails if the set_tenant_id/reset_tenant_id bracketing around the
    get_ticketing_config call is removed — clears ambient tenant context
    before calling the orchestrator and asserts the tenant was resolvable
    *during* the config lookup itself, plus that ticket creation proceeded
    (the background-sweep case, plan 73-05)."""
    import tenant_context
    from tenant_context import reset_tenant_id, set_tenant_id

    token = set_tenant_id(None)
    reset_tenant_id(token)
    assert tenant_context.get_tenant_id() is None

    db = _mock_db()
    asset = _sample_asset()
    seen_tenant_during_lookup = {}

    async def _fake_get_config(tenant_id):
        seen_tenant_during_lookup["tenant_id"] = tenant_context.get_tenant_id()
        return {"provider": "jira"}

    with patch("ticketing_bridge.get_ticketing_config", _fake_get_config), patch(
        "ticketing_bridge.create_jira_ticket",
        AsyncMock(return_value={"success": True, "ticket_key": "ITAM-3", "url": "u"}),
    ):
        result = _run(
            ticketing_bridge.create_ticket_for_itam_event(
                db, "asset", asset, "tenant-a", EVENT_ASSET_AUDIT_OVERDUE
            )
        )

    assert result is not None
    assert seen_tenant_during_lookup["tenant_id"] == "tenant-a"
    # Bracketing must reset — ambient context must not leak past the call.
    assert tenant_context.get_tenant_id() is None


def test_itam_ticket_create_asset_request_model_roundtrips_ticket_fields():
    from itam_models import AssetRequest

    ar = AssetRequest(
        item_description="Monitor",
        quantity=1,
        reason="need it",
        tenant_id="tenant-a",
        requester_id="user-1",
        ticket_provider="jira",
        ticket_ref="ITAM-9",
        ticket_url="https://x/ITAM-9",
    )
    dumped = ar.model_dump()
    assert dumped["ticket_provider"] == "jira"
    assert dumped["ticket_ref"] == "ITAM-9"
    assert dumped["ticket_url"] == "https://x/ITAM-9"


def test_itam_ticket_create_asset_request_create_and_update_reject_ticket_fields():
    from itam_models import AssetRequestCreate, AssetRequestUpdate

    assert "ticket_ref" not in AssetRequestCreate.model_fields
    assert "ticket_provider" not in AssetRequestCreate.model_fields
    assert "ticket_ref" not in AssetRequestUpdate.model_fields
    assert "ticket_provider" not in AssetRequestUpdate.model_fields


# ---------------------------------------------------------------------------
# manual_create (Task 3) — POST /api/itam/tickets
# ---------------------------------------------------------------------------
_ADMIN_TOKEN = TokenData(username="admin@tenant-a", role="admin", tenant_id="tenant-a")


def _entity_db(**collections):
    """collections: e.g. assets={...doc...} or assets=None."""
    db = MagicMock()
    for name, doc in collections.items():
        col = MagicMock()
        col.find_one = AsyncMock(return_value=doc)
        col.update_one = AsyncMock()
        setattr(db, name, col)
    return db


def _ticket_endpoint_app(admin_ok=True):
    app = FastAPI()
    app.include_router(itam_ticketing_endpoints.router)
    if admin_ok:
        app.dependency_overrides[itam_asset_endpoints._require_itam_admin] = lambda: _ADMIN_TOKEN
    else:
        async def _refuse():
            raise HTTPException(status_code=403, detail="User does not have permission to manage ITAM assets.")

        app.dependency_overrides[itam_asset_endpoints._require_itam_admin] = _refuse
    return app


def test_manual_create_valid_asset_returns_ticket_fields():
    db = _entity_db(assets=_sample_asset())
    app = _ticket_endpoint_app()
    with patch.object(itam_ticketing_endpoints, "get_database", return_value=db), patch.object(
        itam_ticketing_endpoints,
        "create_ticket_for_itam_event",
        AsyncMock(
            return_value={
                "ticket_provider": "jira",
                "ticket_ref": "ITAM-1",
                "ticket_url": "https://x/ITAM-1",
            }
        ),
    ):
        with TestClient(app) as client:
            r = client.post(
                "/api/itam/tickets",
                json={"entityKind": "asset", "entityId": "asset-1", "provider": "jira"},
            )

    assert r.status_code == 200
    assert r.json() == {
        "ticket_provider": "jira",
        "ticket_ref": "ITAM-1",
        "ticket_url": "https://x/ITAM-1",
    }


def test_manual_create_entity_not_found_returns_404():
    db = _entity_db(assets=None)
    app = _ticket_endpoint_app()
    with patch.object(itam_ticketing_endpoints, "get_database", return_value=db):
        with TestClient(app) as client:
            r = client.post(
                "/api/itam/tickets",
                json={"entityKind": "asset", "entityId": "asset-missing", "provider": "jira"},
            )

    assert r.status_code == 404


def test_manual_create_already_ticketed_returns_409_not_a_second_ticket():
    db = _entity_db(assets=_sample_asset(ticket_ref="ITAM-EXISTING"))
    app = _ticket_endpoint_app()
    with patch.object(itam_ticketing_endpoints, "get_database", return_value=db), patch.object(
        itam_ticketing_endpoints, "create_ticket_for_itam_event", AsyncMock()
    ) as mock_bridge:
        with TestClient(app) as client:
            r = client.post(
                "/api/itam/tickets",
                json={"entityKind": "asset", "entityId": "asset-1", "provider": "jira"},
            )

    assert r.status_code == 409
    mock_bridge.assert_not_called()


def test_manual_create_invalid_provider_rejected_before_handler():
    db = _entity_db(assets=_sample_asset())
    app = _ticket_endpoint_app()
    with patch.object(itam_ticketing_endpoints, "get_database", return_value=db):
        with TestClient(app) as client:
            r = client.post(
                "/api/itam/tickets",
                json={"entityKind": "asset", "entityId": "asset-1", "provider": "trello"},
            )

    assert r.status_code == 422


def test_manual_create_refused_without_itam_admin_permission():
    db = _entity_db(assets=_sample_asset())
    app = _ticket_endpoint_app(admin_ok=False)
    with patch.object(itam_ticketing_endpoints, "get_database", return_value=db):
        with TestClient(app) as client:
            r = client.post(
                "/api/itam/tickets",
                json={"entityKind": "asset", "entityId": "asset-1", "provider": "jira"},
            )

    assert r.status_code == 403


def test_manual_create_response_body_key_set_is_exactly_three_ticket_keys():
    db = _entity_db(assets=_sample_asset())
    app = _ticket_endpoint_app()
    with patch.object(itam_ticketing_endpoints, "get_database", return_value=db), patch.object(
        itam_ticketing_endpoints,
        "create_ticket_for_itam_event",
        AsyncMock(
            return_value={
                "ticket_provider": "jira",
                "ticket_ref": "ITAM-1",
                "ticket_url": "https://x/ITAM-1",
            }
        ),
    ):
        with TestClient(app) as client:
            r = client.post(
                "/api/itam/tickets",
                json={"entityKind": "asset", "entityId": "asset-1", "provider": "jira"},
            )

    assert set(r.json().keys()) == {"ticket_provider", "ticket_ref", "ticket_url"}


def test_manual_create_asset_request_entity_kind_uses_snake_case_tenant_field():
    db = _entity_db(asset_requests=_sample_asset_request())
    app = _ticket_endpoint_app()
    with patch.object(itam_ticketing_endpoints, "get_database", return_value=db), patch.object(
        itam_ticketing_endpoints,
        "create_ticket_for_itam_event",
        AsyncMock(
            return_value={
                "ticket_provider": "servicenow",
                "ticket_ref": "INC01",
                "ticket_url": "https://x/INC01",
            }
        ),
    ):
        with TestClient(app) as client:
            r = client.post(
                "/api/itam/tickets",
                json={"entityKind": "asset_request", "entityId": "ar-1", "provider": "servicenow"},
            )

    assert r.status_code == 200
    args, kwargs = db.asset_requests.find_one.call_args
    filter_used = args[0]
    assert filter_used["tenant_id"] == "tenant-a"
    assert "tenantId" not in filter_used


def test_manual_create_bridge_failure_returns_502():
    db = _entity_db(assets=_sample_asset())
    app = _ticket_endpoint_app()
    with patch.object(itam_ticketing_endpoints, "get_database", return_value=db), patch.object(
        itam_ticketing_endpoints, "create_ticket_for_itam_event", AsyncMock(return_value=None)
    ):
        with TestClient(app) as client:
            r = client.post(
                "/api/itam/tickets",
                json={"entityKind": "asset", "entityId": "asset-1", "provider": "jira"},
            )

    assert r.status_code == 502


def test_manual_create_route_reachable_in_assembled_app_not_a_404():
    """Drives a real request through TestClient (not a route-table
    inspection) to prove the route resolves in the real app — an
    unregistered router 404s every route it declares (router_registry.py's
    own documented failure class)."""
    db = _entity_db(assets=_sample_asset())
    app = _ticket_endpoint_app()
    with patch.object(itam_ticketing_endpoints, "get_database", return_value=db), patch.object(
        itam_ticketing_endpoints,
        "create_ticket_for_itam_event",
        AsyncMock(
            return_value={"ticket_provider": "jira", "ticket_ref": "ITAM-1", "ticket_url": "u"}
        ),
    ):
        with TestClient(app) as client:
            r = client.post(
                "/api/itam/tickets",
                json={"entityKind": "asset", "entityId": "asset-1", "provider": "jira"},
            )

    assert r.status_code != 404


def test_manual_create_registered_in_real_app():
    """Regression guard for the documented 'route module never registered'
    defect class — imports the real assembled app and drives a request
    through it end to end. Uses the `_fastapi_app` escape hatch (app.py
    reassigns the module-level `app` name to a socketio.ASGIApp wrapper
    with no usable route table, per test_threat_intel_correlate_native_route.py's
    documented precedent) and instantiates TestClient WITHOUT the `with`
    context manager so the real lifespan (live Mongo connect) never runs —
    hermetic. Auth will 401/403 without real credentials, but that proves
    the route exists — a 404 here would mean it isn't wired into
    router_registry.py at all."""
    import app as real_app_module

    client = TestClient(real_app_module._fastapi_app)
    r = client.post(
        "/api/itam/tickets",
        json={"entityKind": "asset", "entityId": "asset-1", "provider": "jira"},
    )

    assert r.status_code != 404


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
