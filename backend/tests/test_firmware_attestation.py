"""Unit tests for firmware/hardware attestation posture
(firmware_attestation_service.py) — gap #5. Pure functions.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import firmware_attestation_service as fa


class TestChecks:
    def test_catalog_keys_unique_and_well_formed(self):
        keys = [c["key"] for c in fa.get_checks()]
        assert len(keys) == len(set(keys))
        for c in fa.get_checks():
            assert {"key", "name", "desired", "severity", "csf", "remediation"} <= set(c)

    def test_every_check_csf_is_real(self):
        import framework_mappings_service as fm
        for c in fa.get_checks():
            assert fm.csf_category_name(c["csf"]) is not None


class TestAssess:
    def test_all_secure_scores_100(self):
        desc = {c["key"]: c["desired"] for c in fa.get_checks()}
        res = fa.assess_posture(desc)
        assert res["posture_score"] == 100 and res["failed"] == [] and res["max_severity"] == "none"

    def test_failed_check_reported_with_csf(self):
        desc = {c["key"]: c["desired"] for c in fa.get_checks()}
        desc["secure_boot"] = False
        res = fa.assess_posture(desc)
        assert any(f["key"] == "secure_boot" for f in res["failed"])
        assert "PR.PS" in res["csf_categories"]
        assert res["max_severity"] == "high"

    def test_missing_key_is_unknown_not_assumed_secure(self):
        # only supply one key; the rest are unknown, not passed
        res = fa.assess_posture({"secure_boot": True})
        assert len(res["unknown"]) == len(fa.get_checks()) - 1
        assert res["passed"] == ["secure_boot"]
        # score denominator excludes unknowns -> 1/1 = 100
        assert res["posture_score"] == 100

    def test_score_excludes_unknowns(self):
        res = fa.assess_posture({"secure_boot": True, "tpm_present": False})
        # 1 pass, 1 fail, rest unknown -> 50
        assert res["posture_score"] == 50

    def test_empty_descriptor_scores_zero(self):
        res = fa.assess_posture({})
        assert res["posture_score"] == 0 and len(res["unknown"]) == len(fa.get_checks())

    def test_max_severity_rolls_up_highest(self):
        desc = {"tpm_2_0": False, "tpm_present": False}  # medium + high
        res = fa.assess_posture(desc)
        assert res["max_severity"] == "high"
