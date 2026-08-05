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
  - rule_routed / raw_db_contract: the rule/channel-routed and raw-handle
    delivery contracts Plan 59-04's sweep must satisfy — added in 59-02
    Task 2.
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
