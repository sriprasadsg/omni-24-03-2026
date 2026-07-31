"""
Tests for agent_location_history_service.py — Phase 46 Plan 02
(Public-IP ASN/VPN Enrichment + Location-History Audit, GAUD-01).

This is the Wave-0 test scaffold for the change-detection + NAT-flip de-noise
state machine + per-tenant track_agent_location toggle + append-only write.
All tests below exercise not-yet-existing symbols on purpose and stay RED
until Task 2 implements backend/agent_location_history_service.py.

Covers (46-RESEARCH.md "Validation Architecture" Test Map -k selectors):
  - change_detection: first-ever write, no-op on unchanged candidate, and a
    city/country-only change (same IP) still eventually writing a row (D-05).
  - denoise: A(confirmed)->B(pending, within window)->A again collapses to
    zero rows for B; B promoted after the debounce window elapses; two
    genuine changes spaced beyond the window each write exactly one row.
  - toggle: get_track_agent_location's tenant->global->default(True)
    resolution order, and record_location_change becoming a full no-op when
    the toggle resolves False.
  - bson_date: the inserted row's timestamp is a real datetime instance
    (BSON Date), never a string (regression guard against Pitfall 6).

Hermetic — no real Mongo, no network. A tiny hand-rolled AsyncMock-backed
fake db (mirrors test_compliance_remediation_sla.py's _mock_db() shape) is
used instead of mongomock, since these scenarios need multi-call state
threading (the shadow locationConfirmed/locationPending fields simulated by
hand between successive record_location_change() calls, exactly like a real
heartbeat handler re-fetching existing_agent on every request).
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# agent_location_history_service.py is created in Task 2 — guard so
# collection succeeds even before that task lands (Task 1 runs first).
try:
    import agent_location_history_service as loc_svc
except ImportError:
    loc_svc = None

import asyncio

# Debounce window used by this test file's scenarios — must match the
# service's own DEBOUNCE_WINDOW (~10 minutes per D-06/CONTEXT.md Claude's
# Discretion). Read from the module once available so the test and
# implementation never drift; falls back to the locked-in 10-minute value
# during the RED phase before the service exists.
_DEBOUNCE_WINDOW = getattr(loc_svc, "DEBOUNCE_WINDOW", timedelta(minutes=10))


def _run(coro):
    return asyncio.run(coro)


def _mock_db():
    db = MagicMock()

    history_col = MagicMock()
    history_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-hist-id"))
    db.agent_location_history = history_col

    agents_col = MagicMock()
    agents_col.update_one = AsyncMock()
    db.agents = agents_col

    settings_col = MagicMock()
    settings_col.find_one = AsyncMock(return_value=None)
    db.system_settings = settings_col

    # get_track_agent_location()'s `db._db if hasattr(db, "_db") else db`
    # unwrap guard must resolve back to this same configured mock.
    db._db = db

    return db


def _apply_agent_update(agent: dict, update_one_mock: AsyncMock) -> dict:
    """Simulate applying the most recent agents.update_one($set/$unset) call
    onto a local dict — mirrors what a real heartbeat's next existing_agent
    fetch would see, without needing a real/mongomock-backed agents
    collection."""
    assert update_one_mock.await_count >= 1, "expected agents.update_one to have been called"
    args, kwargs = update_one_mock.await_args
    update_spec = args[1] if len(args) > 1 else kwargs.get("update", {})
    agent = dict(agent)
    for k, v in (update_spec.get("$set") or {}).items():
        agent[k] = v
    for k in (update_spec.get("$unset") or {}):
        agent.pop(k, None)
    return agent


_GEO_NYC = {"city": "New York", "country": "United States", "country_code": "US"}
_GEO_LA = {"city": "Los Angeles", "country": "United States", "country_code": "US"}

_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# ===========================================================================
# change_detection
# ===========================================================================
class TestChangeDetection:
    def test_change_detection_first_ever_write(self):
        assert loc_svc is not None, "agent_location_history_service not yet created (Task 2)"
        db = _mock_db()
        wrote = _run(
            loc_svc.record_location_change(
                db, existing_agent={}, agent_id="agent-1", tenant_id="tenant-a",
                public_ip="1.2.3.4", geo=_GEO_NYC, asn_enrichment=None, now=_T0,
            )
        )
        assert wrote is True
        db.agent_location_history.insert_one.assert_awaited_once()
        db.agents.update_one.assert_awaited()

    def test_change_detection_no_row_when_unchanged(self):
        assert loc_svc is not None, "agent_location_history_service not yet created (Task 2)"
        db = _mock_db()
        existing_agent = {
            "locationConfirmed": {"publicIp": "1.2.3.4", "geo": _GEO_NYC, "confirmedAt": _T0}
        }
        wrote = _run(
            loc_svc.record_location_change(
                db, existing_agent=existing_agent, agent_id="agent-1", tenant_id="tenant-a",
                public_ip="1.2.3.4", geo=_GEO_NYC, asn_enrichment=None,
                now=_T0 + timedelta(minutes=1),
            )
        )
        assert wrote is False
        db.agent_location_history.insert_one.assert_not_awaited()

    def test_change_detection_city_country_change_same_ip_eventually_writes(self):
        assert loc_svc is not None, "agent_location_history_service not yet created (Task 2)"
        db = _mock_db()
        existing_agent = {
            "locationConfirmed": {"publicIp": "1.2.3.4", "geo": _GEO_NYC, "confirmedAt": _T0}
        }
        # Same public IP, but city/country resolved differently (D-05: "publicIp
        # OR resolved city/country changes") — first observation starts pending.
        t1 = _T0 + timedelta(minutes=5)
        wrote1 = _run(
            loc_svc.record_location_change(
                db, existing_agent=existing_agent, agent_id="agent-1", tenant_id="tenant-a",
                public_ip="1.2.3.4", geo=_GEO_LA, asn_enrichment=None, now=t1,
            )
        )
        assert wrote1 is False
        db.agent_location_history.insert_one.assert_not_awaited()
        existing_agent = _apply_agent_update(existing_agent, db.agents.update_one)

        # Same candidate seen again after the debounce window elapses -> promoted.
        t2 = t1 + _DEBOUNCE_WINDOW + timedelta(seconds=1)
        wrote2 = _run(
            loc_svc.record_location_change(
                db, existing_agent=existing_agent, agent_id="agent-1", tenant_id="tenant-a",
                public_ip="1.2.3.4", geo=_GEO_LA, asn_enrichment=None, now=t2,
            )
        )
        assert wrote2 is True
        db.agent_location_history.insert_one.assert_awaited_once()
        inserted = db.agent_location_history.insert_one.await_args[0][0]
        assert inserted["geo"] == _GEO_LA


# ===========================================================================
# denoise
# ===========================================================================
class TestDenoise:
    def test_denoise_flip_flop_a_b_a_never_writes(self):
        assert loc_svc is not None, "agent_location_history_service not yet created (Task 2)"
        db = _mock_db()
        existing_agent = {
            "locationConfirmed": {"publicIp": "1.1.1.1", "geo": _GEO_NYC, "confirmedAt": _T0}
        }

        # A -> B: candidate differs from confirmed, starts a pending candidate.
        t1 = _T0 + timedelta(minutes=1)
        wrote1 = _run(
            loc_svc.record_location_change(
                db, existing_agent=existing_agent, agent_id="agent-1", tenant_id="tenant-a",
                public_ip="2.2.2.2", geo=_GEO_LA, asn_enrichment=None, now=t1,
            )
        )
        assert wrote1 is False
        db.agent_location_history.insert_one.assert_not_awaited()
        existing_agent = _apply_agent_update(existing_agent, db.agents.update_one)
        assert existing_agent.get("locationPending", {}).get("publicIp") == "2.2.2.2"

        # B -> A again, still well within the debounce window: matches the
        # confirmed baseline (A) -> no-op, and B's stale pending is discarded.
        db.agents.update_one.reset_mock()
        t2 = t1 + timedelta(minutes=3)
        wrote2 = _run(
            loc_svc.record_location_change(
                db, existing_agent=existing_agent, agent_id="agent-1", tenant_id="tenant-a",
                public_ip="1.1.1.1", geo=_GEO_NYC, asn_enrichment=None, now=t2,
            )
        )
        assert wrote2 is False
        db.agent_location_history.insert_one.assert_not_awaited()
        if db.agents.update_one.await_count:
            existing_agent = _apply_agent_update(existing_agent, db.agents.update_one)
        assert not existing_agent.get("locationPending")

        # A real third heartbeat back at B, shortly after — since the pending
        # state was discarded, this starts a brand new pending window rather
        # than inheriting B's original (now-stale) firstSeenAt.
        db.agents.update_one.reset_mock()
        t3 = t2 + timedelta(minutes=1)
        wrote3 = _run(
            loc_svc.record_location_change(
                db, existing_agent=existing_agent, agent_id="agent-1", tenant_id="tenant-a",
                public_ip="2.2.2.2", geo=_GEO_LA, asn_enrichment=None, now=t3,
            )
        )
        assert wrote3 is False
        db.agent_location_history.insert_one.assert_not_awaited()

    def test_denoise_promotes_after_window_elapses(self):
        assert loc_svc is not None, "agent_location_history_service not yet created (Task 2)"
        db = _mock_db()
        existing_agent = {
            "locationConfirmed": {"publicIp": "1.1.1.1", "geo": _GEO_NYC, "confirmedAt": _T0}
        }

        t1 = _T0 + timedelta(minutes=1)
        _run(
            loc_svc.record_location_change(
                db, existing_agent=existing_agent, agent_id="agent-1", tenant_id="tenant-a",
                public_ip="2.2.2.2", geo=_GEO_LA, asn_enrichment=None, now=t1,
            )
        )
        existing_agent = _apply_agent_update(existing_agent, db.agents.update_one)
        db.agents.update_one.reset_mock()

        t2 = t1 + _DEBOUNCE_WINDOW + timedelta(seconds=1)
        wrote = _run(
            loc_svc.record_location_change(
                db, existing_agent=existing_agent, agent_id="agent-1", tenant_id="tenant-a",
                public_ip="2.2.2.2", geo=_GEO_LA, asn_enrichment=None, now=t2,
            )
        )
        assert wrote is True
        db.agent_location_history.insert_one.assert_awaited_once()
        existing_agent = _apply_agent_update(existing_agent, db.agents.update_one)
        assert existing_agent["locationConfirmed"]["publicIp"] == "2.2.2.2"
        assert not existing_agent.get("locationPending")

    def test_denoise_two_genuine_changes_each_write_one_row(self):
        assert loc_svc is not None, "agent_location_history_service not yet created (Task 2)"
        db = _mock_db()
        existing_agent = {
            "locationConfirmed": {"publicIp": "1.1.1.1", "geo": _GEO_NYC, "confirmedAt": _T0}
        }

        # A -> B, spaced beyond the debounce window -> promotes (row 1).
        t1 = _T0 + timedelta(minutes=1)
        _run(
            loc_svc.record_location_change(
                db, existing_agent=existing_agent, agent_id="agent-1", tenant_id="tenant-a",
                public_ip="2.2.2.2", geo=_GEO_LA, asn_enrichment=None, now=t1,
            )
        )
        existing_agent = _apply_agent_update(existing_agent, db.agents.update_one)
        db.agents.update_one.reset_mock()

        t2 = t1 + _DEBOUNCE_WINDOW + timedelta(seconds=1)
        wrote_b = _run(
            loc_svc.record_location_change(
                db, existing_agent=existing_agent, agent_id="agent-1", tenant_id="tenant-a",
                public_ip="2.2.2.2", geo=_GEO_LA, asn_enrichment=None, now=t2,
            )
        )
        assert wrote_b is True
        assert db.agent_location_history.insert_one.await_count == 1
        existing_agent = _apply_agent_update(existing_agent, db.agents.update_one)
        db.agents.update_one.reset_mock()

        # B -> C, spaced well beyond the window again -> promotes (row 2).
        geo_chicago = {"city": "Chicago", "country": "United States", "country_code": "US"}
        t3 = t2 + timedelta(minutes=1)
        _run(
            loc_svc.record_location_change(
                db, existing_agent=existing_agent, agent_id="agent-1", tenant_id="tenant-a",
                public_ip="3.3.3.3", geo=geo_chicago, asn_enrichment=None, now=t3,
            )
        )
        existing_agent = _apply_agent_update(existing_agent, db.agents.update_one)
        db.agents.update_one.reset_mock()

        t4 = t3 + _DEBOUNCE_WINDOW + timedelta(seconds=1)
        wrote_c = _run(
            loc_svc.record_location_change(
                db, existing_agent=existing_agent, agent_id="agent-1", tenant_id="tenant-a",
                public_ip="3.3.3.3", geo=geo_chicago, asn_enrichment=None, now=t4,
            )
        )
        assert wrote_c is True
        assert db.agent_location_history.insert_one.await_count == 2


# ===========================================================================
# toggle
# ===========================================================================
class TestToggle:
    def test_toggle_defaults_to_true(self):
        assert loc_svc is not None, "agent_location_history_service not yet created (Task 2)"
        db = _mock_db()
        db.system_settings.find_one = AsyncMock(return_value=None)
        result = _run(loc_svc.get_track_agent_location(db, "tenant-a"))
        assert result is True

    def test_toggle_honors_per_tenant_false_doc(self):
        assert loc_svc is not None, "agent_location_history_service not yet created (Task 2)"
        db = _mock_db()
        db.system_settings.find_one = AsyncMock(
            return_value={"type": "track_agent_location", "tenantId": "tenant-a", "enabled": False}
        )
        result = _run(loc_svc.get_track_agent_location(db, "tenant-a"))
        assert result is False

    def test_toggle_honors_global_false_doc_fallback(self):
        assert loc_svc is not None, "agent_location_history_service not yet created (Task 2)"
        db = _mock_db()

        async def _find_one(query):
            if query.get("tenantId") == "tenant-a":
                return None
            return {"type": "track_agent_location", "enabled": False}

        db.system_settings.find_one = AsyncMock(side_effect=_find_one)
        result = _run(loc_svc.get_track_agent_location(db, "tenant-a"))
        assert result is False

    def test_toggle_off_makes_record_location_change_a_full_noop(self):
        assert loc_svc is not None, "agent_location_history_service not yet created (Task 2)"
        db = _mock_db()
        db.system_settings.find_one = AsyncMock(
            return_value={"type": "track_agent_location", "tenantId": "tenant-a", "enabled": False}
        )
        wrote = _run(
            loc_svc.record_location_change(
                db, existing_agent={}, agent_id="agent-1", tenant_id="tenant-a",
                public_ip="1.2.3.4", geo=_GEO_NYC, asn_enrichment=None, now=_T0,
            )
        )
        assert wrote is False
        db.agent_location_history.insert_one.assert_not_awaited()
        db.agents.update_one.assert_not_awaited()


# ===========================================================================
# bson_date
# ===========================================================================
class TestBsonDate:
    def test_bson_date_inserted_timestamp_is_datetime_not_string(self):
        assert loc_svc is not None, "agent_location_history_service not yet created (Task 2)"
        db = _mock_db()
        _run(
            loc_svc.record_location_change(
                db, existing_agent={}, agent_id="agent-1", tenant_id="tenant-a",
                public_ip="1.2.3.4", geo=_GEO_NYC, asn_enrichment=None, now=_T0,
            )
        )
        db.agent_location_history.insert_one.assert_awaited_once()
        inserted = db.agent_location_history.insert_one.await_args[0][0]
        assert isinstance(inserted["timestamp"], datetime)
        assert not isinstance(inserted["timestamp"], str)
