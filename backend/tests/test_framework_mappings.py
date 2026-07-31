"""Unit tests for the cross-framework mapping data layer
(framework_mappings_service.py) — gap #3.

Pure data + pure functions, so these assert structural integrity and that the
crosswalk only references CSF categories / D3FEND techniques that actually
exist (no dangling ids), plus the ATT&CK-id join behavior.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import framework_mappings_service as fm


class TestNistCsf:
    def test_has_all_six_functions(self):
        ids = [f["id"] for f in fm.get_nist_csf()["functions"]]
        assert ids == ["GV", "ID", "PR", "DE", "RS", "RC"]

    def test_version_is_2_0(self):
        assert fm.get_nist_csf()["version"] == "2.0"

    def test_category_name_lookup(self):
        assert fm.csf_category_name("PR.AA").startswith("Identity Management")
        assert fm.csf_category_name("NOPE") is None


class TestD3fend:
    def test_six_defensive_tactics(self):
        names = [t["name"] for t in fm.get_d3fend()]
        assert names == ["Model", "Harden", "Detect", "Isolate", "Deceive", "Evict"]

    def test_tactic_lookup_for_technique(self):
        assert fm.d3fend_tactic_for("Multi-factor Authentication") == "Harden"
        assert fm.d3fend_tactic_for("Network Traffic Analysis") == "Detect"
        assert fm.d3fend_tactic_for("Nonexistent") is None


class TestCrosswalkIntegrity:
    def test_every_crosswalk_csf_id_is_real(self):
        valid = set(fm._CSF_CATEGORY_NAMES)
        for tid, entry in fm.ATTACK_CROSSWALK.items():
            for cat in entry["csf"]:
                assert cat in valid, f"{tid} maps to unknown CSF category {cat}"

    def test_every_crosswalk_d3fend_technique_is_real(self):
        valid = set(fm._D3FEND_TECHNIQUE_TACTIC)
        for tid, entry in fm.ATTACK_CROSSWALK.items():
            for tech in entry["d3fend"]:
                assert tech in valid, f"{tid} maps to unknown D3FEND technique {tech}"


class TestMapTechnique:
    def test_known_technique_resolves_to_names(self):
        m = fm.map_technique("T1110")
        assert m["mapped"] is True
        assert any(d["technique"] == "Multi-factor Authentication" for d in m["d3fend"])
        assert all("name" in c and "id" in c for c in m["csf"])
        # each d3fend entry carries its resolved tactic
        assert all(d["tactic"] in ("Harden", "Detect", "Evict", "Isolate", "Model", "Deceive")
                   for d in m["d3fend"])

    def test_case_insensitive_id(self):
        assert fm.map_technique("t1078")["mapped"] is True
        assert fm.map_technique("t1078")["attack_id"] == "T1078"

    def test_unknown_technique_is_unmapped_not_error(self):
        m = fm.map_technique("T9999")
        assert m["mapped"] is False and m["d3fend"] == [] and m["csf"] == []

    def test_get_crosswalk_covers_all_entries(self):
        cw = fm.get_crosswalk()
        assert len(cw) == len(fm.ATTACK_CROSSWALK)
        assert all(v["mapped"] for v in cw.values())
