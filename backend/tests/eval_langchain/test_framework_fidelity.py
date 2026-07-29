"""Eval dimension: Framework fidelity (AI-SPEC Section 5, Rubric 3).

Code check: regex-extract every control-ID-shaped token from free output
text (rationale/narrative prose, not just the structured `control_id`
field) via `extract_control_id_tokens` and validate each against the
seeded framework registry with `validate_framework_fidelity` — invented
IDs (the adversarial set's "SOC 2 CC9.9" bait) must be flagged, real IDs
must pass. Deterministic, zero token spend (`not llm`); the registry is a
mocked db seeded from the gold-control fixtures, and the auditor-agent
wiring of the same validator is exercised in test_traceability.py.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from ai_orchestration.validators import (
    extract_control_id_tokens,
    validate_framework_fidelity,
)

from tests.eval_langchain.conftest import EVAL_TENANT_A_ID
from tests.eval_langchain.dataset import load_adversarial_inputs, load_gold_controls

pytestmark = pytest.mark.eval

GOLD_CONTROLS = load_gold_controls()
FABRICATED_ID_BAITS = [
    e for e in load_adversarial_inputs() if e["input_type"] == "fabricated_control_id"
]
KNOWN_CONTROL_IDS = sorted({e["control_id"] for e in GOLD_CONTROLS})


def _cursor(docs):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=docs)
    return cursor


def make_registry_db():
    """Mocked db whose `compliance_frameworks` registry holds exactly the
    gold set's control ids — the oracle invented tokens must fail against."""
    by_framework: dict = {}
    for entry in GOLD_CONTROLS:
        by_framework.setdefault(entry["framework"], []).append({"id": entry["control_id"]})
    fw_docs = [
        {"id": name, "tenantId": "global", "controls": controls}
        for name, controls in by_framework.items()
    ]
    db = MagicMock(spec=["compliance_frameworks"])
    db.compliance_frameworks = MagicMock()
    db.compliance_frameworks.find = MagicMock(return_value=_cursor(fw_docs))
    return db


class TestTokenExtraction:
    def test_extracts_hyphenated_and_dotted_ids(self):
        text = "CIS-4.1 and AC-2 are covered; CC6.1 partially."
        tokens = extract_control_id_tokens(text)
        assert "CIS-4.1" in tokens
        assert "AC-2" in tokens
        assert "CC6.1" in tokens

    def test_framework_names_do_not_false_positive(self):
        """Merely naming a framework ("SOC 2", "ISO 27001") is not a
        control-ID claim — the sweep must not flag it."""
        tokens = extract_control_id_tokens("We are SOC 2 and ISO 27001 aligned.")
        assert "SOC" not in tokens
        # "ISO 27001" (with space) must not match; "ISO27001" (fused) does.
        assert not any(t.startswith("ISO ") for t in tokens)

    def test_no_tokens_in_plain_prose(self):
        assert extract_control_id_tokens("The overall posture is strong.") == []


class TestRealIdsPass:
    @pytest.mark.parametrize("control_id", KNOWN_CONTROL_IDS)
    async def test_registry_control_id_in_prose_passes(self, control_id):
        result = await validate_framework_fidelity(
            f"Control {control_id} is satisfied by the collected evidence.",
            EVAL_TENANT_A_ID,
            make_registry_db(),
        )
        assert result.ok, f"real registry id {control_id} was wrongly flagged"

    async def test_gold_rationales_pass_fidelity_sweep(self):
        """Every gold rationale (real analyst-authored prose) must survive
        the sweep against the seeded registry — no false positives."""
        db = make_registry_db()
        for entry in GOLD_CONTROLS:
            result = await validate_framework_fidelity(
                entry["gold_rationale"], EVAL_TENANT_A_ID, db
            )
            assert result.ok, (
                f"{entry['control_id']} gold rationale falsely flagged: {result.detail}"
            )

    async def test_tokenless_text_passes(self):
        result = await validate_framework_fidelity(
            "No specific controls referenced here.", EVAL_TENANT_A_ID, make_registry_db()
        )
        assert result.ok


class TestFabricatedIdsFlagged:
    async def test_soc2_cc99_bait_is_flagged(self):
        """The canonical AI-SPEC bait: "SOC 2 CC9.9" does not exist in the
        registry and must be flagged (adv-07)."""
        result = await validate_framework_fidelity(
            "Assessed against SOC 2 CC9.9 and found compliant.",
            EVAL_TENANT_A_ID,
            make_registry_db(),
        )
        assert not result.ok
        assert "CC9.9" in (result.detail or "")

    @pytest.mark.parametrize(
        "bait", FABRICATED_ID_BAITS, ids=[e["id"] for e in FABRICATED_ID_BAITS]
    )
    async def test_adversarial_fabricated_control_id_baits_flagged(self, bait):
        """Both fabricated-control-ID adversarial entries carry an invented
        ID-shaped token the sweep must catch."""
        result = await validate_framework_fidelity(
            bait["adversarial_text"], EVAL_TENANT_A_ID, make_registry_db()
        )
        assert not result.ok, f"{bait['id']}: invented control id not flagged"

    async def test_mixed_real_and_invented_ids_still_flagged(self):
        result = await validate_framework_fidelity(
            "CIS-4.1 passes, and so does CC9.9.", EVAL_TENANT_A_ID, make_registry_db()
        )
        assert not result.ok
        assert "CC9.9" in (result.detail or "")
        assert "CIS-4.1" not in (result.detail or "")
