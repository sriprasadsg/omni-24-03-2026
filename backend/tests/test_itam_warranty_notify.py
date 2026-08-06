"""
Tests for the Phase 59 (ITAM Procurement & Finance — Warranty & Depreciation)
warranty-alert delivery contract across notification_service.py and
notification_endpoints.py.

Covers:
  - event_vocabulary: the `itam.warranty_expiring` event type is accepted by
    both hardcoded vocabulary guards (notification_service.VALID_EVENTS,
    notification_endpoints.RuleCreate.event_type's Literal) without disturbing
    the five pre-existing GRC event types or the closed-vocabulary rejection
    of an unknown event type (59-02 Task 1).
  - rule_routed: notification_service.send_notification, given a handle
    exposing `_db`, resolves a tenant's itam.warranty_expiring rule to its
    channel and dispatches — the rule-routed delivery path Plan 59-04's sweep
    will call for tenants who have configured a notification rule (59-02
    Task 2).
  - raw_db_contract: the calling contract RESEARCH Pitfall 1 found waiting for
    a naive raw-db background sweep — send_notification requires a `_db`-
    exposing handle and raises AttributeError without one, while
    get_notification_service(...).send_alert(...) never unwraps `db` and
    works against a raw handle directly (59-02 Task 2).
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pydantic
import pytest

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import notification_service
import notification_endpoints
from notification_endpoints import RuleCreate

_LEGACY_EVENT_TYPES = (
    "finding_created",
    "control_failed",
    "evidence_expired",
    "review_overdue",
    "cert_expiring",
)
_NEW_EVENT_TYPE = "itam.warranty_expiring"


def _mock_db():
    """MagicMock-based db with db._db explicitly wired back to itself, so
    create_rule's `db._db.notification_rules...` calls resolve to the same
    configured mock rather than an auto-created child MagicMock (mirrors
    test_compliance_remediation_sla.py's _mock_db() convention)."""
    db = MagicMock()
    db._db = db
    db.notification_rules = MagicMock()
    db.notification_rules.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-rule-id"))
    return db


# ===========================================================================
# TestWarrantyEventVocabulary — 59-02 Task 1
# ===========================================================================
class TestWarrantyEventVocabulary:
    def test_event_vocabulary_service_set_contains_new_and_legacy_members(self):
        assert _NEW_EVENT_TYPE in notification_service.VALID_EVENTS
        for legacy in _LEGACY_EVENT_TYPES:
            assert legacy in notification_service.VALID_EVENTS

    def test_event_vocabulary_literal_contains_new_and_legacy_members(self):
        import typing

        args = typing.get_args(RuleCreate.model_fields["event_type"].annotation)
        assert _NEW_EVENT_TYPE in args
        for legacy in _LEGACY_EVENT_TYPES:
            assert legacy in args

    def test_event_vocabulary_create_rule_accepts_new_event_type(self):
        db = _mock_db()
        rule = asyncio.run(notification_service.create_rule(
            db, "tenant-a", {"event_type": _NEW_EVENT_TYPE, "channel_ids": ["chan-1"]}
        ))
        assert rule["event_type"] == _NEW_EVENT_TYPE
        assert rule["tenantId"] == "tenant-a"
        assert rule["id"]

    def test_event_vocabulary_create_rule_accepts_every_legacy_event_type(self):
        for legacy in _LEGACY_EVENT_TYPES:
            db = _mock_db()
            rule = asyncio.run(notification_service.create_rule(
                db, "tenant-a", {"event_type": legacy, "channel_ids": []}
            ))
            assert rule["event_type"] == legacy
            assert rule["id"]

    def test_event_vocabulary_create_rule_rejects_unknown_event_type(self):
        db = _mock_db()
        with pytest.raises(ValueError):
            asyncio.run(notification_service.create_rule(
                db, "tenant-a", {"event_type": "not_a_real_event", "channel_ids": []}
            ))

    def test_event_vocabulary_rule_create_pydantic_validates_new_event_type(self):
        rc = RuleCreate(event_type=_NEW_EVENT_TYPE, channel_ids=[])
        assert rc.event_type == _NEW_EVENT_TYPE

    def test_event_vocabulary_rule_create_pydantic_rejects_unknown_event_type(self):
        with pytest.raises(pydantic.ValidationError):
            RuleCreate(event_type="something.else")


# ===========================================================================
# TestRuleRoutedDelivery — 59-02 Task 2 (rule/channel-routed delivery path)
# ===========================================================================
class _RulesRoutedStubDb:
    """Plain-class db stub (not a bare MagicMock) whose collection attributes
    expose `find(...)` returning an object with an AsyncMock `to_list`. Used
    behind `_Handle` below — the same `_db`-exposing shape Plan 59-04 will
    hand `send_notification`."""

    def __init__(self, rules=None, channels=None):
        self.notification_rules = MagicMock()
        rules_result = MagicMock()
        rules_result.to_list = AsyncMock(return_value=list(rules or []))
        self.notification_rules.find = MagicMock(return_value=rules_result)

        self.notification_channels = MagicMock()
        channels_result = MagicMock()
        channels_result.to_list = AsyncMock(return_value=list(channels or []))
        self.notification_channels.find = MagicMock(return_value=channels_result)

        self.notifications = MagicMock()
        self.notifications.insert_one = AsyncMock()


class _Handle:
    """Minimal adapter exposing the stub db as `_db`."""

    def __init__(self, db):
        self._db = db


def _rule(event_type=_NEW_EVENT_TYPE, tenant_id="tenant-a", severity_filter=None, channel_ids=("chan-1",)):
    return {
        "id": "rule-1",
        "tenantId": tenant_id,
        "event_type": event_type,
        "channel_ids": list(channel_ids),
        "severity_filter": list(severity_filter) if severity_filter else [],
    }


def _email_channel(channel_id="chan-1", tenant_id="tenant-a"):
    return {"id": channel_id, "tenantId": tenant_id, "type": "email", "config": {"email": "admin@acme.com"}}


class TestRuleRoutedDelivery:
    def test_rule_routed_matches_and_dispatches_single_email_channel(self):
        stub = _RulesRoutedStubDb(rules=[_rule()], channels=[_email_channel()])
        handle = _Handle(stub)
        result = asyncio.run(notification_service.send_notification(
            handle, "tenant-a", _NEW_EVENT_TYPE, {"severity": "warning", "message": "Asset ABC warranty expiring"}
        ))
        assert result["matched_rules"] == 1
        assert result["sent"] == 1
        assert result["results"][0]["status"] == "sent"

    def test_rule_routed_filter_scoped_by_tenant_and_event_type(self):
        stub = _RulesRoutedStubDb(rules=[_rule()], channels=[_email_channel()])
        handle = _Handle(stub)
        asyncio.run(notification_service.send_notification(
            handle, "tenant-a", _NEW_EVENT_TYPE, {"severity": "warning"}
        ))
        used_filter = stub.notification_rules.find.call_args[0][0]
        assert used_filter.get("tenantId") == "tenant-a"
        assert used_filter.get("event_type") == _NEW_EVENT_TYPE

    def test_rule_routed_severity_filter_excludes_non_matching_severity(self):
        stub = _RulesRoutedStubDb(rules=[_rule(severity_filter=["critical"])], channels=[_email_channel()])
        handle = _Handle(stub)
        result = asyncio.run(notification_service.send_notification(
            handle, "tenant-a", _NEW_EVENT_TYPE, {"severity": "info"}
        ))
        assert result["matched_rules"] == 0
        assert result["sent"] == 0

    def test_rule_routed_severity_filter_includes_matching_severity(self):
        stub = _RulesRoutedStubDb(rules=[_rule(severity_filter=["warning"])], channels=[_email_channel()])
        handle = _Handle(stub)
        result = asyncio.run(notification_service.send_notification(
            handle, "tenant-a", _NEW_EVENT_TYPE, {"severity": "warning"}
        ))
        assert result["matched_rules"] == 1
        assert result["sent"] == 1

    def test_rule_routed_no_severity_filter_matches_any_severity(self):
        stub = _RulesRoutedStubDb(rules=[_rule(severity_filter=[])], channels=[_email_channel()])
        handle = _Handle(stub)
        result = asyncio.run(notification_service.send_notification(
            handle, "tenant-a", _NEW_EVENT_TYPE, {"severity": "critical"}
        ))
        assert result["matched_rules"] == 1
        assert result["sent"] == 1


# ===========================================================================
# TestRawDbCallingContract — 59-02 Task 2 (regression guard for RESEARCH
# Pitfall 1 — the most load-bearing class in this plan)
# ===========================================================================
class _RawDbNoAdapter:
    """Raw-database-shaped stub: explicitly declared collection attributes,
    NO `_db` attribute and NO `__getattr__` fallback, so `hasattr(stub, "_db")`
    is genuinely False. A MagicMock/AsyncMock fixture would auto-create `_db`
    on attribute access and make this whole class pass vacuously while the
    real bug (RESEARCH Pitfall 1 — a raw-db warranty sweep crashing on
    `db._db.notification_rules...`) remained hidden."""

    def __init__(self):
        self.notifications = MagicMock()
        self.notifications.insert_one = AsyncMock()
        self.notification_rules = MagicMock()
        self.notification_channels = MagicMock()


class TestRawDbCallingContract:
    def test_raw_db_contract_send_notification_raises_attributeerror(self):
        raw = _RawDbNoAdapter()
        assert not hasattr(raw, "_db")
        with pytest.raises(AttributeError):
            asyncio.run(notification_service.send_notification(
                raw, "tenant-a", _NEW_EVENT_TYPE, {"severity": "warning"}
            ))

    def test_raw_db_contract_send_alert_works_without_db_unwrap(self):
        raw = _RawDbNoAdapter()
        svc = notification_service.get_notification_service(raw)
        result = asyncio.run(svc.send_alert(
            title="Asset warranty expiring",
            message="Asset ABC warranty expiring on 2026-09-01.",
            severity="warning",
            recipients=["admin@acme.com"],
            tenant_id="tenant-a",
            channels=[],
            metadata={"event": _NEW_EVENT_TYPE},
        ))
        raw.notifications.insert_one.assert_awaited_once()
        assert result["channels"] == {}, f"channels=[] must dispatch on no external channel, got {result['channels']}"
        inserted_doc = raw.notifications.insert_one.call_args.args[0]
        assert inserted_doc["tenantId"] == "tenant-a", (
            "send_alert must set tenantId explicitly — a raw/unwrapped db has no "
            "TenantIsolatedCollection.insert_one to auto-inject it, so a document "
            "missing this field is invisible to every tenantId-filtered reader in "
            "notification_endpoints.py (list/mark-read/delete)"
        )
