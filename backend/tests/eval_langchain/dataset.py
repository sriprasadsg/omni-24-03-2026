"""Reference dataset split loaders (AI-SPEC Section 5 / plan 39-10).

Fail-loud typed loaders for the four JSON fixtures under
``backend/tests/eval_langchain/data/``. Every loader raises on a missing or
malformed fixture (missing file, invalid JSON, missing required keys, or an
out-of-vocabulary enum value) rather than returning an empty list -- a
broken dataset must never silently pass the eval gate (T-39-10-A).

Downstream consumers: 39-11 (code-based eval dimensions) and 39-12
(LLM-judged eval dimensions) import these four functions and consume the
stable dict schema documented on each loader below.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

_DATA_DIR = Path(__file__).parent / "data"

_VALID_GOLD_STATUSES = {"pass", "fail", "partial", "insufficient_evidence"}
_VALID_CONFIDENCES = {"high", "medium", "low", "insufficient_evidence"}
_VALID_CHAT_BEHAVIORS = {"answer", "decline_redirect", "refuse"}
_VALID_INPUT_TYPES = {
    "prompt_injection",
    "cross_tenant_probe",
    "tool_arg_bypass",
    "fabricated_control_id",
    "skip_citations",
}
_VALID_TARGET_SURFACES = {"auditor", "chat", "questionnaire"}

_GOLD_CONTROLS_REQUIRED_KEYS = {
    "control_id",
    "framework",
    "evidence",
    "gold_status",
    "gold_citations",
    "gold_rationale",
    "case_type",
}
_QUESTIONNAIRE_REQUIRED_KEYS = {
    "question_id",
    "question_text",
    "gold_answer_text",
    "gold_confidence",
    "gold_source_ids",
    "case_type",
}
_CHAT_REQUIRED_KEYS = {
    "question_id",
    "question_text",
    "gold_behavior",
    "gold_answer_text",
    "gold_source_ids",
    "case_type",
}
_ADVERSARIAL_REQUIRED_KEYS = {
    "id",
    "input_type",
    "target_surface",
    "adversarial_text",
    "canary_strings",
    "gold_expectation",
}

PathLike = Union[str, Path]


def _resolve_path(data_dir: Optional[PathLike], filename: str) -> Path:
    base = Path(data_dir) if data_dir is not None else _DATA_DIR
    return base / filename


def _load_json_array(path: Path) -> List[Any]:
    """Read and parse a fixture file, raising loudly on any structural problem."""
    if not path.exists():
        raise FileNotFoundError(f"Reference dataset fixture missing: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Reference dataset fixture is not valid JSON: {path}") from exc
    if not isinstance(data, list) or not data:
        raise ValueError(f"Reference dataset fixture must be a non-empty JSON array: {path}")
    return data


def _require_keys(entries: List[Any], required_keys: set, filename: str) -> List[Dict[str, Any]]:
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"{filename} entry {i} is not a JSON object")
        missing = required_keys - entry.keys()
        if missing:
            raise ValueError(f"{filename} entry {i} missing required keys: {sorted(missing)}")
    return entries


def load_gold_controls(data_dir: Optional[PathLike] = None) -> List[Dict[str, Any]]:
    """Load the gold-labeled control assessments (auditor-surface oracle).

    Each entry: control_id (str), framework (str), evidence (list of
    {id, source, content, collected_at}), gold_status (pass|fail|partial|
    insufficient_evidence), gold_citations (list of evidence ids, must all
    resolve within this entry's own evidence records), gold_rationale (str),
    case_type (str, e.g. clean_pass/clean_fail/trap_stale/trap_partial/
    trap_zero/trap_context_dependent).
    """
    path = _resolve_path(data_dir, "gold_controls.json")
    entries = _require_keys(_load_json_array(path), _GOLD_CONTROLS_REQUIRED_KEYS, path.name)
    for i, entry in enumerate(entries):
        control_id = entry["control_id"]
        if not isinstance(control_id, str) or not control_id.strip():
            raise ValueError(f"{path.name} entry {i} has an empty control_id")
        if entry["gold_status"] not in _VALID_GOLD_STATUSES:
            raise ValueError(
                f"{path.name} entry {i} ({control_id}) has invalid gold_status: "
                f"{entry['gold_status']!r}"
            )
        evidence = entry.get("evidence", [])
        if not isinstance(evidence, list):
            raise ValueError(f"{path.name} entry {i} ({control_id}) evidence must be a list")
        evidence_ids = {ev.get("id") for ev in evidence if isinstance(ev, dict)}
        for citation_id in entry.get("gold_citations", []):
            if citation_id not in evidence_ids:
                raise ValueError(
                    f"{path.name} entry {i} ({control_id}) cites {citation_id!r}, "
                    f"which is not present in its own evidence records"
                )
    return entries


def load_questionnaire_qa(data_dir: Optional[PathLike] = None) -> List[Dict[str, Any]]:
    """Load the questionnaire Q&A pairs (questionnaire-surface oracle).

    Each entry: question_id, question_text, gold_answer_text,
    gold_confidence (high|medium|low|insufficient_evidence), gold_source_ids
    (list of str), case_type (answerable|hedged|unanswerable).
    """
    path = _resolve_path(data_dir, "questionnaire_qa.json")
    entries = _require_keys(_load_json_array(path), _QUESTIONNAIRE_REQUIRED_KEYS, path.name)
    for i, entry in enumerate(entries):
        if entry["gold_confidence"] not in _VALID_CONFIDENCES:
            raise ValueError(
                f"{path.name} entry {i} ({entry['question_id']}) has invalid gold_confidence: "
                f"{entry['gold_confidence']!r}"
            )
    return entries


def load_chat_questions(data_dir: Optional[PathLike] = None) -> List[Dict[str, Any]]:
    """Load the chat questions (chat-surface oracle).

    Each entry: question_id, question_text, gold_behavior (answer|
    decline_redirect|refuse), gold_answer_text, gold_source_ids (list of
    str), case_type (e.g. posture_lookup/score_explanation/out_of_scope/
    other_customers_probe).
    """
    path = _resolve_path(data_dir, "chat_questions.json")
    entries = _require_keys(_load_json_array(path), _CHAT_REQUIRED_KEYS, path.name)
    for i, entry in enumerate(entries):
        if entry["gold_behavior"] not in _VALID_CHAT_BEHAVIORS:
            raise ValueError(
                f"{path.name} entry {i} ({entry['question_id']}) has invalid gold_behavior: "
                f"{entry['gold_behavior']!r}"
            )
    return entries


def load_adversarial_inputs(data_dir: Optional[PathLike] = None) -> List[Dict[str, Any]]:
    """Load the adversarial inputs (security-engineer-authored red-team set).

    Each entry: id, input_type (prompt_injection|cross_tenant_probe|
    tool_arg_bypass|fabricated_control_id|skip_citations), target_surface
    (auditor|chat|questionnaire), adversarial_text, canary_strings (list of
    str -- the tenant-B canary sentinels this entry embeds, empty for attack
    types that don't probe cross-tenant leakage), gold_expectation.
    """
    path = _resolve_path(data_dir, "adversarial_inputs.json")
    entries = _require_keys(_load_json_array(path), _ADVERSARIAL_REQUIRED_KEYS, path.name)
    for i, entry in enumerate(entries):
        if entry["input_type"] not in _VALID_INPUT_TYPES:
            raise ValueError(
                f"{path.name} entry {i} ({entry['id']}) has invalid input_type: "
                f"{entry['input_type']!r}"
            )
        if entry["target_surface"] not in _VALID_TARGET_SURFACES:
            raise ValueError(
                f"{path.name} entry {i} ({entry['id']}) has invalid target_surface: "
                f"{entry['target_surface']!r}"
            )
        if not isinstance(entry["canary_strings"], list):
            raise ValueError(
                f"{path.name} entry {i} ({entry['id']}) canary_strings must be a list"
            )
    return entries
