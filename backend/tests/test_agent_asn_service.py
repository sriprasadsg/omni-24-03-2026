"""
Tests for agent_asn_service.py — Phase 46 Plan 01 (GAUD-01 foundation).

Hermetic pytest suite (no live .mmdb, no network). Mirrors the geoip_service.py
lazy-singleton pattern's never-raises contract, plus the bundled X4BNet VPN
CIDR-range heuristic (D-11/D-12).

Each test reloads the module fresh (importlib.reload) so the single-attempt-
then-cache-None-forever lazy-load globals (_reader/_load_attempted,
_vpn_ranges/_vpn_load_attempted) never leak state across test cases.

Covers:
  - none_or_empty: lookup(None) / lookup("") return None
  - private_ip: private/loopback/link-local IPs return None, never touching
    the ASN reader or VPN-range loader
  - asn_absent_vpn_present: GEOIP_ASN_DB_PATH pointing nowhere + a present
    X4BNet snapshot -> dict with "vpn_heuristic" present, no "asn" key
  - vpn_range_membership: an IP inside a bundled CIDR -> vpn_heuristic=True;
    an IP outside every range -> vpn_heuristic=False
  - both_absent: no .mmdb and no snapshot file -> lookup returns None,
    logs a warning, never raises
"""
import importlib
import logging
import os
import sys
from unittest.mock import MagicMock

import pytest

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# agent_asn_service.py is created in Plan 01 Task 2 — this import is expected
# to fail (ModuleNotFoundError -> pytest collection error) until Task 2 lands.
# That collection failure IS the RED state for this Wave-0 test scaffold.
import agent_asn_service  # noqa: E402


# Fixture-usable "known VPN" CIDRs for tests. NOT the RFC 5737 documentation
# ranges (203.0.113.0/24, 198.51.100.0/24) suggested in the plan — Python's
# stdlib `ipaddress.IPv4Address.is_private` classifies those TEST-NET blocks
# as private (they're in CPython's _private_networks table), so
# geoip_service._is_public() filters them out before any reader/range access
# ever runs, silently defeating every assertion below. Using two genuinely
# public, non-special-purpose ranges instead (arbitrary — not real VPN IPs).
_FIXTURE_CIDRS = ["93.184.216.0/24", "185.199.108.0/24"]


@pytest.fixture(autouse=True)
def _fresh_module():
    """Reset all lazy-load globals before every test."""
    importlib.reload(agent_asn_service)
    yield


@pytest.fixture
def vpn_snapshot(tmp_path):
    """Write a tmp X4BNet-shaped snapshot file with comments + blank lines."""
    snapshot = tmp_path / "x4bnet_vpn_ipv4.txt"
    lines = [
        "# vendored snapshot fixture — test only",
        "",
        *_FIXTURE_CIDRS,
        "",
    ]
    snapshot.write_text("\n".join(lines) + "\n")
    return snapshot


class TestNoneOrEmpty:
    def test_lookup_none_returns_none(self):
        assert agent_asn_service.lookup(None) is None

    def test_lookup_empty_string_returns_none(self):
        assert agent_asn_service.lookup("") is None


class TestPrivateIp:
    @pytest.mark.parametrize("ip", ["10.0.0.1", "127.0.0.1", "192.168.1.5"])
    def test_private_ip_returns_none(self, ip, monkeypatch):
        # Spy on the lazy loaders to prove private IPs never trigger a
        # reader/range access at all.
        reader_spy = MagicMock(wraps=agent_asn_service._get_reader)
        vpn_spy = MagicMock(wraps=agent_asn_service._load_vpn_ranges)
        monkeypatch.setattr(agent_asn_service, "_get_reader", reader_spy)
        monkeypatch.setattr(agent_asn_service, "_load_vpn_ranges", vpn_spy)

        assert agent_asn_service.lookup(ip) is None
        reader_spy.assert_not_called()
        vpn_spy.assert_not_called()


class TestAsnAbsentVpnPresent:
    def test_missing_mmdb_still_evaluates_vpn_heuristic(
        self, monkeypatch, tmp_path, vpn_snapshot
    ):
        nonexistent_db = tmp_path / "does-not-exist.mmdb"
        monkeypatch.setenv("GEOIP_ASN_DB_PATH", str(nonexistent_db))
        monkeypatch.setattr(agent_asn_service, "_VPN_RANGES_PATH", str(vpn_snapshot))

        result = agent_asn_service.lookup("93.184.216.42")

        assert result is not None
        assert "vpn_heuristic" in result
        assert "asn" not in result
        assert result["vpn_heuristic"] is True


class TestVpnRangeMembership:
    def test_ip_inside_bundled_range_flags_true(
        self, monkeypatch, tmp_path, vpn_snapshot
    ):
        monkeypatch.setenv("GEOIP_ASN_DB_PATH", str(tmp_path / "absent.mmdb"))
        monkeypatch.setattr(agent_asn_service, "_VPN_RANGES_PATH", str(vpn_snapshot))

        result = agent_asn_service.lookup("185.199.108.7")

        assert result is not None
        assert result["vpn_heuristic"] is True

    def test_ip_outside_every_range_flags_false(
        self, monkeypatch, tmp_path, vpn_snapshot
    ):
        monkeypatch.setenv("GEOIP_ASN_DB_PATH", str(tmp_path / "absent.mmdb"))
        monkeypatch.setattr(agent_asn_service, "_VPN_RANGES_PATH", str(vpn_snapshot))

        result = agent_asn_service.lookup("8.8.8.8")

        # vpn_heuristic must be explicitly False, not merely absent/None.
        assert result is not None
        assert result["vpn_heuristic"] is False


class TestBothAbsent:
    def test_both_mmdb_and_snapshot_absent_returns_none_and_warns(
        self, monkeypatch, tmp_path, caplog
    ):
        monkeypatch.setenv("GEOIP_ASN_DB_PATH", str(tmp_path / "no-db-here.mmdb"))
        monkeypatch.setattr(
            agent_asn_service, "_VPN_RANGES_PATH", str(tmp_path / "no-snapshot-here.txt")
        )

        with caplog.at_level(logging.WARNING):
            result = agent_asn_service.lookup("93.184.216.42")

        assert result is None
        assert any(
            record.levelno >= logging.WARNING for record in caplog.records
        ), "expected at least one warning-level log on both-absent degrade"

    def test_both_absent_never_raises_for_various_ips(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GEOIP_ASN_DB_PATH", str(tmp_path / "no-db-here.mmdb"))
        monkeypatch.setattr(
            agent_asn_service, "_VPN_RANGES_PATH", str(tmp_path / "no-snapshot-here.txt")
        )

        for ip in ["93.184.216.42", "8.8.8.8", "1.1.1.1", None, "", "10.0.0.1"]:
            # Must never raise, regardless of input shape.
            agent_asn_service.lookup(ip)
