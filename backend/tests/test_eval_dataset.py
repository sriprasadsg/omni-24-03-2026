"""Reference dataset consistency + loader tests (AI-SPEC Section 5 / plan 39-10).

Deterministic, no live model, no token spend -- marked `eval` only (never
`llm`). Covers: each split loads its expected example count, gold-control
citation/control-ID internal consistency, trap-subset gold labels,
adversarial canaries matching the conftest canary constants, and fail-loud
behavior on a missing/malformed fixture.

Naming: `-k splits` selects the split-loading tests (matches Task 1/plan
39-10's per-task `<verify>` for gold/questionnaire/chat), `-k loader`
selects the loader-robustness tests (matches Task 2's `<verify>`). Running
with `-m eval -q` (no `-k` filter) runs everything in this file, per Task 3.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.eval_langchain.conftest import CANARY_STRINGS
from tests.eval_langchain.dataset import (
    load_adversarial_inputs,
    load_chat_questions,
    load_gold_controls,
    load_questionnaire_qa,
)

pytestmark = pytest.mark.eval


# ---------------------------------------------------------------------------
# Split-loading tests (-k splits)
# ---------------------------------------------------------------------------

class TestDatasetSplits:
    def test_gold_controls_splits_count(self):
        entries = load_gold_controls()
        assert len(entries) == 20

    def test_questionnaire_qa_splits_count(self):
        entries = load_questionnaire_qa()
        assert len(entries) == 10

    def test_chat_questions_splits_count(self):
        entries = load_chat_questions()
        assert len(entries) == 8

    def test_adversarial_inputs_splits_count(self):
        entries = load_adversarial_inputs()
        assert len(entries) == 10

    def test_gold_controls_splits_trap_subset_labels(self):
        """>= 8 gold controls carry the trap-set gold labels (insufficient_evidence
        or partial) -- stale/partial/zero-evidence/context-dependent cases."""
        entries = load_gold_controls()
        trap_labeled = [e for e in entries if e["gold_status"] in ("insufficient_evidence", "partial")]
        assert len(trap_labeled) >= 8

        trap_case_types = {e["case_type"] for e in entries if e["gold_status"] in ("insufficient_evidence", "partial")}
        assert "trap_stale" in trap_case_types
        assert "trap_partial" in trap_case_types
        assert "trap_zero" in trap_case_types
        assert "trap_context_dependent" in trap_case_types

    def test_gold_controls_splits_clean_pass_and_fail_present(self):
        entries = load_gold_controls()
        assert sum(1 for e in entries if e["gold_status"] == "pass") >= 8
        assert sum(1 for e in entries if e["gold_status"] == "fail") >= 4

    def test_questionnaire_qa_splits_case_type_composition(self):
        entries = load_questionnaire_qa()
        case_types = [e["case_type"] for e in entries]
        assert case_types.count("answerable") == 5
        assert case_types.count("hedged") == 3
        assert case_types.count("unanswerable") == 2
        unanswerable = [e for e in entries if e["case_type"] == "unanswerable"]
        assert len(unanswerable) == 2
        assert all(e["gold_confidence"] == "insufficient_evidence" for e in unanswerable)

    def test_chat_questions_splits_includes_out_of_scope_and_refusal(self):
        entries = load_chat_questions()
        case_types = {e["case_type"] for e in entries}
        assert "out_of_scope" in case_types
        assert "other_customers_probe" in case_types

        out_of_scope = [e for e in entries if e["case_type"] == "out_of_scope"]
        assert all(e["gold_behavior"] == "decline_redirect" for e in out_of_scope)

        other_customers = [e for e in entries if e["case_type"] == "other_customers_probe"]
        assert all(e["gold_behavior"] == "refuse" for e in other_customers)

    def test_adversarial_inputs_splits_type_composition(self):
        entries = load_adversarial_inputs()
        input_types = [e["input_type"] for e in entries]
        for expected_type in (
            "prompt_injection",
            "cross_tenant_probe",
            "tool_arg_bypass",
            "fabricated_control_id",
            "skip_citations",
        ):
            assert input_types.count(expected_type) >= 2, f"missing/short type: {expected_type}"


# ---------------------------------------------------------------------------
# Internal-consistency tests (-k splits, gold citation/control-ID coherence)
# ---------------------------------------------------------------------------

class TestGoldControlConsistency:
    def test_splits_citation_ids_resolve_within_own_evidence(self):
        entries = load_gold_controls()
        for entry in entries:
            evidence_ids = {ev["id"] for ev in entry["evidence"]}
            for citation_id in entry["gold_citations"]:
                assert citation_id in evidence_ids, (
                    f"{entry['control_id']} cites {citation_id!r} not present in its own evidence"
                )

    def test_splits_control_ids_non_empty(self):
        entries = load_gold_controls()
        for entry in entries:
            assert entry["control_id"].strip(), "control_id must not be empty"

    def test_splits_zero_evidence_traps_have_no_citations(self):
        entries = load_gold_controls()
        zero_evidence = [e for e in entries if e["case_type"] == "trap_zero"]
        assert len(zero_evidence) == 2
        for entry in zero_evidence:
            assert entry["evidence"] == []
            assert entry["gold_citations"] == []
            assert entry["gold_status"] == "insufficient_evidence"


# ---------------------------------------------------------------------------
# Adversarial canary tests (-k splits, tenant-B canary alignment)
# ---------------------------------------------------------------------------

class TestAdversarialCanaries:
    def test_splits_canaries_match_conftest_constants(self):
        entries = load_adversarial_inputs()
        canary_bearing = [e for e in entries if e["canary_strings"]]
        assert canary_bearing, "expected at least one adversarial entry to embed a canary string"
        for entry in canary_bearing:
            for canary in entry["canary_strings"]:
                assert canary in CANARY_STRINGS, (
                    f"{entry['id']} references {canary!r}, not a known conftest canary constant"
                )

    def test_splits_leakage_probe_types_reference_a_canary(self):
        """The three attack types that actually probe cross-tenant leakage
        (prompt_injection, cross_tenant_probe, tool_arg_bypass) must each
        embed a real canary string so a leak is machine-detectable."""
        entries = load_adversarial_inputs()
        leakage_probe_types = {"prompt_injection", "cross_tenant_probe", "tool_arg_bypass"}
        for entry in entries:
            if entry["input_type"] in leakage_probe_types:
                assert entry["canary_strings"], (
                    f"{entry['id']} ({entry['input_type']}) has no canary_strings to detect leakage"
                )


# ---------------------------------------------------------------------------
# Loader robustness tests (-k loader)
# ---------------------------------------------------------------------------

class TestDatasetLoader:
    def test_loader_exports_all_four_split_functions(self):
        assert callable(load_gold_controls)
        assert callable(load_questionnaire_qa)
        assert callable(load_chat_questions)
        assert callable(load_adversarial_inputs)

    def test_loader_raises_on_missing_fixture(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_gold_controls(data_dir=tmp_path)

    def test_loader_raises_on_malformed_json(self, tmp_path):
        (tmp_path / "gold_controls.json").write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError):
            load_gold_controls(data_dir=tmp_path)

    def test_loader_raises_on_empty_array(self, tmp_path):
        (tmp_path / "gold_controls.json").write_text("[]", encoding="utf-8")
        with pytest.raises(ValueError):
            load_gold_controls(data_dir=tmp_path)

    def test_loader_raises_on_missing_required_keys(self, tmp_path):
        (tmp_path / "questionnaire_qa.json").write_text(
            json.dumps([{"question_id": "q1"}]), encoding="utf-8"
        )
        with pytest.raises(ValueError):
            load_questionnaire_qa(data_dir=tmp_path)

    def test_loader_raises_on_invalid_gold_status(self, tmp_path):
        bad_entry = {
            "control_id": "CIS-1.1",
            "framework": "CIS Controls v8",
            "evidence": [],
            "gold_status": "definitely-maybe",
            "gold_citations": [],
            "gold_rationale": "bad status value",
            "case_type": "clean_pass",
        }
        (tmp_path / "gold_controls.json").write_text(json.dumps([bad_entry]), encoding="utf-8")
        with pytest.raises(ValueError):
            load_gold_controls(data_dir=tmp_path)

    def test_loader_raises_on_citation_not_in_own_evidence(self, tmp_path):
        bad_entry = {
            "control_id": "CIS-1.1",
            "framework": "CIS Controls v8",
            "evidence": [{"id": "ev-1", "source": "x", "content": "x", "collected_at": "2026-01-01T00:00:00Z"}],
            "gold_status": "pass",
            "gold_citations": ["ev-does-not-exist"],
            "gold_rationale": "dangling citation",
            "case_type": "clean_pass",
        }
        (tmp_path / "gold_controls.json").write_text(json.dumps([bad_entry]), encoding="utf-8")
        with pytest.raises(ValueError):
            load_gold_controls(data_dir=tmp_path)

    def test_loader_raises_on_invalid_input_type(self, tmp_path):
        bad_entry = {
            "id": "adv-bad",
            "input_type": "not-a-real-type",
            "target_surface": "chat",
            "adversarial_text": "x",
            "canary_strings": [],
            "gold_expectation": "x",
        }
        (tmp_path / "adversarial_inputs.json").write_text(json.dumps([bad_entry]), encoding="utf-8")
        with pytest.raises(ValueError):
            load_adversarial_inputs(data_dir=tmp_path)

    def test_loader_succeeds_on_real_fixtures(self):
        """Sanity check: the loader functions used above resolve against the
        real fixture files under data/ without needing data_dir overrides."""
        assert len(load_gold_controls()) == 20
        assert len(load_questionnaire_qa()) == 10
        assert len(load_chat_questions()) == 8
        assert len(load_adversarial_inputs()) == 10
