"""
Tests for geo_security_service.py — Phase 47 Plan 02
(Agent-Scoped Geo Security Detectors, GSEC-02/GSEC-03).

Hermetic — no real GeoLite2 .mmdb, no real Mongo. All geo dicts are
hand-constructed fixtures; the db is a hand-rolled AsyncMock-backed fake
(mirrors test_agent_location_history.py's _mock_db() shape). geoip_service
and agent_asn_service are never imported here (47-RESEARCH.md Pitfall 6).

Covers (47-RESEARCH.md Validation Architecture Test Map -k selectors):
  - impossible_travel_positive / impossible_travel_below_speed: D-01 haversine
    speed threshold (reuses ueba_service._haversine_km, never re-copied).
  - vpn_suppression / vpn_none_handling: D-02 `is True`-only suppression,
    3-valued vpn_heuristic (Pitfall 5).
  - first_checkin: no prior geo (or no lat/long) -> never fires (Pitfall 3).
  - elapsed_floor / clock_skew: D-08 15-minute floor + negative/zero elapsed
    guard.
  - geo_fence_violation / geo_fence_clean: D-03 country-code allowlist,
    case-insensitive normalization.
  - config_resolution: tenant -> global -> default resolution (clone of
    get_sla_at_risk_window/get_track_agent_location's 3-step contract).
  - dedup_cooldown: D-05/D-07 state-transition + 6h cooldown re-fire.

These tests MUST fail at collection/import (module does not exist yet) until
Task 2/3 land backend/geo_security_service.py — RED first.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# geo_security_service.py is created in Task 2/3 — guard so collection
# succeeds even before those tasks land (Task 1 runs first, RED).
try:
    import geo_security_service as geo_svc
except ImportError:
    geo_svc = None


def _run(coro):
    return asyncio.run(coro)


def _mock_db():
    db = MagicMock()

    agents_col = MagicMock()
    agents_col.update_one = AsyncMock()
    db.agents = agents_col

    settings_col = MagicMock()
    settings_col.find_one = AsyncMock(return_value=None)
    db.system_settings = settings_col

    # get_geo_security_settings()'s `db._db if hasattr(db, "_db") else db`
    # unwrap guard must resolve back to this same configured mock.
    db._db = db

    return db


# Real-world-shaped geo fixtures (geoip_service.lookup()'s return shape):
# {country, country_code, city, region, latitude, longitude}. NYC<->London
# is ~5570 km apart — comfortably over the 1000 km/h ceiling within an hour.
_NYC = {"latitude": 40.7128, "longitude": -74.0060, "country_code": "US"}
_LON = {"latitude": 51.5074, "longitude": -0.1278, "country_code": "GB"}

_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


# ===========================================================================
# impossible_travel_positive / impossible_travel_below_speed
# ===========================================================================
class TestImpossibleTravel:
    def test_impossible_travel_positive(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        result = geo_svc.evaluate_impossible_travel(
            prev_geo=_NYC, prev_last_seen_iso=_iso(_T0), curr_geo=_LON,
            now=_T0 + timedelta(hours=1), prev_vpn=None, curr_vpn=None,
        )
        assert result is True

    def test_impossible_travel_below_speed(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        result = geo_svc.evaluate_impossible_travel(
            prev_geo=_NYC, prev_last_seen_iso=_iso(_T0), curr_geo=_LON,
            now=_T0 + timedelta(hours=24), prev_vpn=None, curr_vpn=None,
        )
        assert result is False


# ===========================================================================
# vpn_suppression / vpn_none_handling
# ===========================================================================
class TestVpnSuppression:
    def test_vpn_suppression_prev_vpn_true(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        result = geo_svc.evaluate_impossible_travel(
            prev_geo=_NYC, prev_last_seen_iso=_iso(_T0), curr_geo=_LON,
            now=_T0 + timedelta(hours=1), prev_vpn=True, curr_vpn=None,
        )
        assert result is False

    def test_vpn_suppression_curr_vpn_true(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        result = geo_svc.evaluate_impossible_travel(
            prev_geo=_NYC, prev_last_seen_iso=_iso(_T0), curr_geo=_LON,
            now=_T0 + timedelta(hours=1), prev_vpn=None, curr_vpn=True,
        )
        assert result is False

    def test_vpn_none_handling_does_not_suppress(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        # vpn_heuristic absent (None) on both sides -- a real over-speed jump
        # must still fire (D-02 uses `is True` only, never falsy coercion).
        result = geo_svc.evaluate_impossible_travel(
            prev_geo=_NYC, prev_last_seen_iso=_iso(_T0), curr_geo=_LON,
            now=_T0 + timedelta(hours=1), prev_vpn=None, curr_vpn=None,
        )
        assert result is True

    def test_vpn_none_handling_explicit_false_does_not_suppress(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        # vpn_heuristic explicitly False (ranges loaded, not flagged) on both
        # sides -- still fires, same as the None/absent case.
        result = geo_svc.evaluate_impossible_travel(
            prev_geo=_NYC, prev_last_seen_iso=_iso(_T0), curr_geo=_LON,
            now=_T0 + timedelta(hours=1), prev_vpn=False, curr_vpn=False,
        )
        assert result is True


# ===========================================================================
# first_checkin
# ===========================================================================
class TestFirstCheckin:
    def test_first_checkin_no_prior_geo(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        result = geo_svc.evaluate_impossible_travel(
            prev_geo=None, prev_last_seen_iso=None, curr_geo=_LON,
            now=_T0, prev_vpn=None, curr_vpn=None,
        )
        assert result is False

    def test_first_checkin_missing_latitude(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        result = geo_svc.evaluate_impossible_travel(
            prev_geo={"country_code": "US"}, prev_last_seen_iso=_iso(_T0),
            curr_geo=_LON, now=_T0 + timedelta(hours=1), prev_vpn=None, curr_vpn=None,
        )
        assert result is False


# ===========================================================================
# elapsed_floor / clock_skew
# ===========================================================================
class TestElapsedFloor:
    def test_elapsed_floor_below_15_minutes_suppresses(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        result = geo_svc.evaluate_impossible_travel(
            prev_geo=_NYC, prev_last_seen_iso=_iso(_T0), curr_geo=_LON,
            now=_T0 + timedelta(minutes=10), prev_vpn=None, curr_vpn=None,
        )
        assert result is False

    def test_elapsed_floor_at_20_minutes_still_fires(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        result = geo_svc.evaluate_impossible_travel(
            prev_geo=_NYC, prev_last_seen_iso=_iso(_T0), curr_geo=_LON,
            now=_T0 + timedelta(minutes=20), prev_vpn=None, curr_vpn=None,
        )
        assert result is True

    def test_clock_skew_negative_elapsed_suppresses(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        result = geo_svc.evaluate_impossible_travel(
            prev_geo=_NYC, prev_last_seen_iso=_iso(_T0), curr_geo=_LON,
            now=_T0 - timedelta(minutes=5), prev_vpn=None, curr_vpn=None,
        )
        assert result is False

    def test_clock_skew_zero_elapsed_suppresses(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        result = geo_svc.evaluate_impossible_travel(
            prev_geo=_NYC, prev_last_seen_iso=_iso(_T0), curr_geo=_LON,
            now=_T0, prev_vpn=None, curr_vpn=None,
        )
        assert result is False


# ===========================================================================
# geo_fence_violation / geo_fence_clean
# ===========================================================================
class TestGeoFence:
    def test_geo_fence_violation_country_not_in_allowlist(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        result = geo_svc.evaluate_geo_fence("RU", ["US", "GB"])
        assert result is True

    def test_geo_fence_violation_case_insensitive_normalization(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        # "us" normalizes to "US" and matches the allowlist -> not a violation.
        result = geo_svc.evaluate_geo_fence("us", ["US", "GB"])
        assert result is False

    def test_geo_fence_clean_country_in_allowlist(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        result = geo_svc.evaluate_geo_fence("GB", ["US", "GB"])
        assert result is False

    def test_geo_fence_clean_empty_country_code(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        result = geo_svc.evaluate_geo_fence("", ["US", "GB"])
        assert result is False

    def test_geo_fence_clean_none_country_code(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        result = geo_svc.evaluate_geo_fence(None, ["US", "GB"])
        assert result is False

    def test_geo_fence_clean_empty_allowlist(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        result = geo_svc.evaluate_geo_fence("RU", [])
        assert result is False


# ===========================================================================
# config_resolution
# ===========================================================================
class TestConfigResolution:
    def test_config_resolution_default(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        db = _mock_db()
        db.system_settings.find_one = AsyncMock(return_value=None)
        result = _run(geo_svc.get_geo_security_settings(db, "tenant-a"))
        assert result == {
            "impossible_travel_enabled": True,
            "geo_fence_enabled": False,
            "allowed_country_codes": [],
        }

    def test_config_resolution_global_fallback(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        db = _mock_db()

        async def _find_one(query):
            if query.get("tenantId") == "tenant-a":
                return None
            return {
                "type": "geo_security_detectors",
                "geo_fence_enabled": True,
                "allowed_country_codes": ["US"],
            }

        db.system_settings.find_one = AsyncMock(side_effect=_find_one)
        result = _run(geo_svc.get_geo_security_settings(db, "tenant-a"))
        assert result["geo_fence_enabled"] is True
        assert result["allowed_country_codes"] == ["US"]
        assert result["impossible_travel_enabled"] is True  # untouched default

    def test_config_resolution_tenant_overrides_global(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        db = _mock_db()

        async def _find_one(query):
            if query.get("tenantId") == "tenant-a":
                return {
                    "type": "geo_security_detectors",
                    "tenantId": "tenant-a",
                    "geo_fence_enabled": True,
                    "allowed_country_codes": ["FR"],
                }
            return {
                "type": "geo_security_detectors",
                "geo_fence_enabled": True,
                "allowed_country_codes": ["US"],
            }

        db.system_settings.find_one = AsyncMock(side_effect=_find_one)
        result = _run(geo_svc.get_geo_security_settings(db, "tenant-a"))
        assert result["allowed_country_codes"] == ["FR"]

    def test_config_resolution_default_geo_fence_disabled(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 2)"
        db = _mock_db()
        db.system_settings.find_one = AsyncMock(return_value=None)
        result = _run(geo_svc.get_geo_security_settings(db, None))
        assert result["geo_fence_enabled"] is False
        assert result["allowed_country_codes"] == []


# ===========================================================================
# dedup_cooldown
# ===========================================================================
class TestDedupCooldown:
    def test_dedup_cooldown_transition_then_suppress_then_refire_then_clear(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 3)"
        db = _mock_db()

        # First violating call: clean -> violating transition -- fires.
        fired1 = _run(
            geo_svc.dedup_and_maybe_alert(
                db, "agent-1", {}, "impossible_travel", True,
            )
        )
        assert fired1 is True
        db.agents.update_one.assert_awaited()
        args, kwargs = db.agents.update_one.await_args
        update_spec = args[1] if len(args) > 1 else kwargs.get("update", {})
        set_fields = update_spec.get("$set", {})
        assert set_fields["geoSecurityState.impossible_travel.violating"] is True
        last_alerted = set_fields["geoSecurityState.impossible_travel.lastAlertedAt"]
        assert isinstance(last_alerted, datetime)
        existing_agent = {
            "geoSecurityState": {
                "impossible_travel": {"violating": True, "lastAlertedAt": last_alerted}
            }
        }
        db.agents.update_one.reset_mock()

        # Immediate repeat within the 6h cooldown -- suppressed, no write.
        fired2 = _run(
            geo_svc.dedup_and_maybe_alert(
                db, "agent-1", existing_agent, "impossible_travel", True,
            )
        )
        assert fired2 is False
        db.agents.update_one.assert_not_awaited()

        # lastAlertedAt older than the 6h cooldown, still violating -> re-fires (D-07).
        stale_agent = {
            "geoSecurityState": {
                "impossible_travel": {
                    "violating": True,
                    "lastAlertedAt": last_alerted - timedelta(hours=7),
                }
            }
        }
        fired3 = _run(
            geo_svc.dedup_and_maybe_alert(
                db, "agent-1", stale_agent, "impossible_travel", True,
            )
        )
        assert fired3 is True
        db.agents.update_one.assert_awaited()
        db.agents.update_one.reset_mock()

        # A clean (non-violating) call after violating -- clears state, no fire.
        fired4 = _run(
            geo_svc.dedup_and_maybe_alert(
                db, "agent-1", existing_agent, "impossible_travel", False,
            )
        )
        assert fired4 is False
        db.agents.update_one.assert_awaited()
        args, kwargs = db.agents.update_one.await_args
        update_spec = args[1] if len(args) > 1 else kwargs.get("update", {})
        assert update_spec["$set"]["geoSecurityState.impossible_travel.violating"] is False

    def test_dedup_cooldown_clean_call_with_no_prior_state_never_writes(self):
        assert geo_svc is not None, "geo_security_service not yet created (Task 3)"
        db = _mock_db()
        fired = _run(
            geo_svc.dedup_and_maybe_alert(
                db, "agent-1", {}, "geo_fence_violation", False,
            )
        )
        assert fired is False
        db.agents.update_one.assert_not_awaited()
