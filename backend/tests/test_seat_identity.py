"""Spec C2: hardware identity normalization and seat-key precedence (pure, no I/O).

Value: protects=placeholder serials/UUIDs and virtual MACs never become a seat identity,
and serial > UUID > MAC > legacy precedence holds; fails_when=a junk value or a
locally administered MAC is accepted, or precedence changes; no_claim=what real
firmware reports (inputs are literal strings).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import seat_identity as si


@pytest.mark.parametrize("junk", ["", "0", "None", "Not Available", "To Be Filled By O.E.M.", "Default string",
                                  "System Serial Number", "123456789", "0000000000", "   ", None, 42])
def test_placeholder_serials_are_rejected(junk):
    assert si.normalize_serial(junk) is None


def test_real_serial_is_kept_upper_case():
    assert si.normalize_serial(" pf3abc12 ") == "PF3ABC12"


@pytest.mark.parametrize("junk", ["00000000-0000-0000-0000-000000000000", "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF",
                                  "short", None])
def test_placeholder_uuids_are_rejected(junk):
    assert si.normalize_uuid(junk) is None


@pytest.mark.parametrize("mac,expected", [
    ("3C-52-82-AA-BB-CC", "3c:52:82:aa:bb:cc"),
    ("00:00:00:00:00:00", None),      # all zero
    ("02:42:ac:11:00:02", None),      # locally administered (docker)
    ("01:00:5e:00:00:01", None),      # multicast
    ("not-a-mac", None),
])
def test_mac_normalization(mac, expected):
    assert si.normalize_mac(mac) == expected


def test_precedence_serial_then_uuid_then_mac_then_legacy():
    full = si.normalize_hardware({"serialNumber": "PF3ABC12", "smbiosUuid": "4c4c4544-0042-3010-8051-b4c04f4d3132",
                                  "macAddresses": ["3c:52:82:aa:bb:cc"]})
    assert si.seat_key(full) == "serial:PF3ABC12"
    no_serial = si.normalize_hardware({"serialNumber": "To Be Filled By O.E.M.",
                                       "smbiosUuid": "4C4C4544-0042-3010-8051-B4C04F4D3132"})
    assert si.seat_key(no_serial) == "uuid:4c4c4544-0042-3010-8051-b4c04f4d3132"
    mac_only = si.normalize_hardware({"macAddresses": ["02:42:ac:11:00:02", "3c:52:82:aa:bb:cc"]})
    assert si.seat_key(mac_only) == "mac:3c:52:82:aa:bb:cc"
    assert si.seat_key(si.normalize_hardware(None), "abc123") == "legacy:abc123"


def test_identity_strength():
    assert si.identity_strength("serial:X") == "strong"
    assert si.identity_strength("uuid:x") == "strong"
    assert si.identity_strength("mac:x") == "medium"
    assert si.identity_strength("legacy:x") == "weak"


def test_hardware_match_needs_serial_or_uuid():
    assert si.hardware_match_filter("t1", si.normalize_hardware({"macAddresses": ["3c:52:82:aa:bb:cc"]})) is None
    flt = si.hardware_match_filter("t1", si.normalize_hardware({"serialNumber": "PF3ABC12"}))
    assert flt == {"tenantId": "t1", "$or": [{"hardware.serialNumber": "PF3ABC12"}]}
