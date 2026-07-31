"""Unit tests for the OT/ICS assessment module (ot_ics_service.py) — gap #4.
Pure data + pure functions; assert reference integrity and assessment logic.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ot_ics_service as ot


class TestReference:
    def test_iec_62443_has_five_levels(self):
        assert [s["sl"] for s in ot.IEC_62443_SECURITY_LEVELS] == [0, 1, 2, 3, 4]

    def test_purdue_includes_idmz(self):
        levels = {p["level"] for p in ot.PURDUE_LEVELS}
        assert "3.5" in levels  # the industrial DMZ

    def test_protocols_have_required_fields(self):
        for key, p in ot.ICS_PROTOCOLS.items():
            assert {"name", "port", "native_auth", "native_encryption", "risks"} <= set(p)
            assert isinstance(p["risks"], list) and p["risks"]


class TestAssess:
    def test_unauthenticated_protocol_flagged(self):
        res = ot.assess_asset(protocols=["modbus"], purdue_level="1")
        assert res["finding_count"] == 1
        f = res["findings"][0]
        assert f["protocol"] == "Modbus TCP" and f["severity"] == "high"
        assert "PR.AA" in {c["id"] for c in f["csf"]}

    def test_internet_exposure_escalates_to_critical(self):
        res = ot.assess_asset(protocols=["modbus"], purdue_level="3", internet_exposed=True)
        assert res["max_severity"] == "critical"
        assert "PR.IR" in res["csf_categories"]

    def test_lower_purdue_level_is_higher_severity(self):
        low = ot.assess_asset(protocols=["dnp3"], purdue_level="1")["max_severity"]
        high = ot.assess_asset(protocols=["dnp3"], purdue_level="4")["max_severity"]
        assert low == "high" and high == "medium"

    def test_opcua_with_native_auth_not_flagged_when_internal(self):
        res = ot.assess_asset(protocols=["opcua"], purdue_level="3", internet_exposed=False)
        assert res["finding_count"] == 0 and res["max_severity"] == "none"

    def test_unknown_protocol_reported_not_dropped(self):
        res = ot.assess_asset(protocols=["frobnicate"], purdue_level="2")
        assert res["finding_count"] == 1 and res["findings"][0]["severity"] == "info"

    def test_invalid_purdue_level_defaults_to_2(self):
        assert ot.assess_asset(protocols=[], purdue_level="99")["purdue_level"] == "2"

    def test_csf_categories_resolve_to_real_names(self):
        import framework_mappings_service as fm
        res = ot.assess_asset(protocols=["modbus"], purdue_level="1")
        for c in res["findings"][0]["csf"]:
            assert fm.csf_category_name(c["id"]) == c["name"]
