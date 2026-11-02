"""ACTV-08: Autonomous Ops copy never uses the banned terms (backend side).

The rules and the explicit list of scanned files live in ``shared/autonomous-ops-banned-terms.json``;
``src/__tests__/autonomousOpsCopy.test.ts`` reads the same file and scans the frontend files. This
side scans the backend files and the ``autonomousOps`` label in ``shared/catalogue-access.json``.
Every listed file must exist (a rename must not turn the check into a silent pass), and each rule
has negative controls proving it fires, so a rule that stops matching fails the suite.
"""
import json
import os
import re
import sys
from typing import Any, Dict, List, Tuple

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RULES_PATH = os.path.join(REPO_ROOT, "shared", "autonomous-ops-banned-terms.json")

# The same list is hard-coded in the vitest side. If either side drifts from the JSON, it fails.
EXPECTED_FILES = [
    "backend/autonomous_ops/messages.py",
    "backend/autonomous_ops/views.py",
    "backend/autonomous_ops/response_messages.py",
    "backend/autonomous_ops/response_views.py",
    "backend/autonomous_ops/incident_views.py",
    "backend/autonomous_ops/health_messages.py",
    "backend/autonomous_ops/selfheal.py",
    "backend/autonomous_ops_endpoints.py",
    "backend/autonomous_ops_platform_endpoints.py",
    "backend/watchdog_ingest_endpoints.py",
    "backend/autonomous_ops_retention_endpoints.py",
    "backend/autonomous_ops_response_endpoints.py",
    "backend/autonomous_ops_response_platform_endpoints.py",
    "services/autonomousOpsApi.ts",
    "contexts/AutonomousOpsStatusContext.tsx",
    "components/AutonomousOpsActivity.tsx",
    "components/AutonomousOpsActivityList.tsx",
    "components/AutonomousOpsRowActions.tsx",
    "components/AutonomousOpsStatusCard.tsx",
    "components/AutonomousOpsStopDialog.tsx",
    "components/AutonomousOpsStopBanner.tsx",
    "components/AutonomousOpsHealthBanners.tsx",
    "components/AutonomousOpsHealthChips.tsx",
    "components/AutonomousOpsPlatformHealth.tsx",
    "components/AutonomousOpsHealthCards.tsx",
    "components/AutonomousOpsRetentionReview.tsx",
    "components/AutonomousOpsRetentionConfirmDialog.tsx",
    "components/AutonomousOpsResponseSettings.tsx",
    "components/AutonomousOpsResponseSettingsDialogs.tsx",
    "components/AutonomousOpsResponseSettingsPlatform.tsx",
    "components/SwarmDashboard.tsx",
]


def load_rules() -> Dict[str, Any]:
    with open(RULES_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def compile_rules(rules: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], "re.Pattern[str]"]]:
    compiled = []
    for rule in rules:
        flags = re.IGNORECASE if "i" in rule.get("flags", "") else 0
        compiled.append((rule, re.compile(rule["pattern"], flags)))
    return compiled


def violations(text: str, rules: List[Dict[str, Any]]) -> List[Tuple[int, str, str]]:
    """(line number, rule id, line) for every line that breaks a rule; the exception is per line."""
    found = []
    compiled = compile_rules(rules)
    for number, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in compiled:
            exempt = rule.get("unlessLineContains")
            if exempt and exempt.lower() in line.lower():
                continue
            if pattern.search(line):
                found.append((number, rule["id"], line.strip()))
    return found


def scan_files(files: List[str], rules: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    """(missing files, problems). A listed file that does not exist is its own failure."""
    missing, problems = [], []
    for rel in files:
        path = os.path.join(REPO_ROOT, rel)
        if not os.path.isfile(path):
            missing.append(rel)
            continue
        with open(path, encoding="utf-8") as handle:
            for number, rule_id, line in violations(handle.read(), rules):
                problems.append(f"{rel}:{number} [{rule_id}] {line}")
    return missing, problems


def catalogue_labels(views: List[str]) -> List[str]:
    with open(os.path.join(REPO_ROOT, "shared", "catalogue-access.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
    return [entry["label"] for entry in manifest["catalogues"] if entry.get("view") in views]


# ---------------------------------------------------------------- the rules file

def test_rules_file_shape():
    data = load_rules()
    ids = [rule["id"] for rule in data["rules"]]
    assert len(ids) >= 5 and len(ids) == len(set(ids))
    for rule in data["rules"]:
        assert rule["pattern"] and set(rule.get("flags", "")) <= {"i"}
        re.compile(rule["pattern"])
    assert data["catalogueViews"] == ["autonomousOps"]


def test_file_list_is_the_agreed_list_and_the_scope_excludes_other_screens():
    files = load_rules()["files"]
    assert files == EXPECTED_FILES
    for rel in files:
        assert not rel.startswith(".planning"), rel
        assert "autopilot" not in rel.lower(), rel
        assert not rel.endswith("AutonomousOpsLog.tsx"), rel


def test_every_listed_file_exists():
    missing, _ = scan_files(load_rules()["files"], load_rules()["rules"])
    assert missing == []


def test_a_missing_listed_file_is_reported_not_skipped():
    missing, problems = scan_files(["backend/autonomous_ops/no_such_file.py"], load_rules()["rules"])
    assert missing == ["backend/autonomous_ops/no_such_file.py"] and problems == []


# ---------------------------------------------------------------- the real copy

def test_backend_files_pass_every_rule():
    data = load_rules()
    backend = [rel for rel in data["files"] if rel.startswith("backend/")]
    missing, problems = scan_files(backend, data["rules"])
    assert missing == []
    assert problems == []


def test_the_autonomous_ops_catalogue_label_passes_every_rule():
    data = load_rules()
    labels = catalogue_labels(data["catalogueViews"])
    assert labels == ["Autonomous Ops"]
    for label in labels:
        assert violations(label, data["rules"]) == [], label


# ---------------------------------------------------------------- negative controls

FLAGGED = {
    "asi": ["Our ASI engine", "ASI.", "(ASI)"],
    "agi": ["AGI inside", "an AGI feature"],
    "autopilot": ["autopilot mode", "Autopilot", "AUTOPILOT"],
    "fully-autonomous": ["fully autonomous", "fully-autonomous", "Fully Autonomous operations"],
    "rollback": ["we roll back", "rollback", "rolled back", "rolling-back", "Roll-back", "rolling back the change"],
}
PASSING = {
    "asi": ["basic", "magic", "classify", "Asia", "asi"],
    "agi": ["magic", "imagine", "again"],
    "autopilot": ["autonomous", "automatic actions"],
    "fully-autonomous": ["autonomous within limits", "fully supported"],
    "rollback": ["rollback where supported", "Rollback Where Supported", "rolled_back", "rollback_ransomware",
                 "rotate_key_rollback", "undo", "roller"],
}


@pytest.mark.parametrize("rule_id", sorted(FLAGGED))
def test_negative_controls_every_rule_fires_on_its_examples(rule_id):
    rules = [rule for rule in load_rules()["rules"] if rule["id"] == rule_id]
    assert len(rules) == 1, f"rule {rule_id} is missing from the rules file"
    for text in FLAGGED[rule_id]:
        assert [v[1] for v in violations(text, rules)] == [rule_id], text


@pytest.mark.parametrize("rule_id", sorted(PASSING))
def test_negative_controls_every_rule_leaves_its_look_alikes_alone(rule_id):
    rules = [rule for rule in load_rules()["rules"] if rule["id"] == rule_id]
    for text in PASSING[rule_id]:
        assert violations(text, rules) == [], text


def test_every_rule_in_the_file_has_a_control():
    ids = {rule["id"] for rule in load_rules()["rules"]}
    assert ids == set(FLAGGED) == set(PASSING)


def test_where_supported_exempts_only_its_own_line():
    rules = load_rules()["rules"]
    text = "Undo works.\nRollback where supported.\nThen we roll back everything."
    assert [(n, r) for n, r, _ in violations(text, rules)] == [(3, "rollback")]


def test_the_scan_catches_a_banned_term_in_a_real_looking_file(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", str(tmp_path))
    sample = tmp_path / "components"
    sample.mkdir()
    (sample / "Copy.tsx").write_text("const a = 'Autonomous Ops';\nconst b = 'Autopilot for your fleet';\n")
    missing, problems = scan_files(["components/Copy.tsx"], load_rules()["rules"])
    assert missing == []
    assert problems == ["components/Copy.tsx:2 [autopilot] const b = 'Autopilot for your fleet';"]


# ---------------------------------------------------------------- response_messages (Phase 83, plan 83-03)

ORIGIN_IDS = ["native", "feed:urlhaus", "feed:malwarebazaar", "feed:otx", "virustotal", "onhost"]


def _strings(value):
    """Every string inside a nested constant."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def test_origin_names_are_the_six_shown_names_and_an_unknown_id_is_never_shown():
    from autonomous_ops import response_messages as rm
    shown = [rm.origin_name(i) for i in ORIGIN_IDS]
    assert shown == ["agent verdict", "URLhaus", "MalwareBazaar", "OTX", "VirusTotal", "detection on this computer"]
    with pytest.raises(KeyError):
        rm.origin_name("feed:unknown")
    with pytest.raises(KeyError):
        rm.origin_name(None)


def test_two_sources_sentence_needs_two_different_origins_and_sorts_the_names():
    from autonomous_ops import response_messages as rm
    assert rm.why_two_sources(["native", "feed:urlhaus"]) == rm.why_two_sources(["feed:urlhaus", "native"])
    assert rm.why_two_sources(["native", "feed:urlhaus"]) == "Two sources agree: agent verdict and URLhaus."
    for bad in ([], ["native"], ["native", "native"], ("onhost", "onhost")):
        with pytest.raises(ValueError):
            rm.why_two_sources(bad)
    with pytest.raises(KeyError):
        rm.why_two_sources(["native", "feed:nope"])


def test_one_source_and_rule_off_sentences_name_the_origin():
    from autonomous_ops import response_messages as rm
    assert rm.why_rule_off("native") == ("This organization's two-source rule is off, so one source was enough: "
                                         "agent verdict.")
    assert rm.why_one_source("feed:otx") == ("Only one source flagged this: OTX. A second, different source has "
                                             "to agree.")


def test_ui_spec_strings_are_verbatim():
    from autonomous_ops import response_messages as rm
    assert rm.FENCE["swarm"] == ("Nothing was sent. Antibody propagation no longer sends containment to agents on "
                                 "its own. Containment is handled in Autonomous Ops.")
    assert rm.WHAT_HAPPENS["kill_process"] == "Ends this process right away. Unsaved work in it is lost."
    assert rm.WHAT_HAPPENS["reboot_host"] == "Restarts this computer. Anyone using it loses unsaved work."
    assert rm.WHAT_HAPPENS["kill_then_quarantine"] == "Ends the process, then moves the file to quarantine. Nothing is deleted."
    assert rm.WHAT_HAPPENS["isolate_host"].endswith("returns to the network automatically after 4 hours unless you confirm it.")
    assert rm.NOTICES["kill_only"] == ("The file was moved to quarantine, but its process is still running. "
                                       "Approving ends the process.")
    assert rm.UNDO_HINTS == {"unblock_ip": "Removes the block on {ip}.",
                             "unquarantine_file": "Restores {path} to where it was.",
                             "restore_host": "Restores the network connection."}
    assert rm.RESULT_TEMPLATES["block_active"] == ("Blocked for {length}, until {until}. Verified: the firewall "
                                                   "rule is in place.")
    assert rm.RESULT_TEMPLATES["block_expired"] == "Block removed automatically at {at} when its time ran out."
    assert rm.RESULT_TEMPLATES["quarantine_done"] == ("Moved {path} to quarantine. It was not deleted. Verified: "
                                                      "the file is in quarantine.")
    assert rm.RESULT_TEMPLATES["not_repeated"] == "Not repeated."


def test_every_fence_names_autonomous_ops_in_its_last_sentence():
    from autonomous_ops import response_messages as rm
    assert {"swarm", "soar", "worker"} <= set(rm.FENCE)
    for key, text in rm.FENCE.items():
        assert text.rstrip().endswith("Autonomous Ops."), key


def test_added_keys_resolve_through_messages():
    from autonomous_ops import messages, response_messages as rm
    for key in ("agent_unsupported", "capability_off", "agent_offline", "range_block", "superseded", "hash_mismatch",
                "locked", "protected_path", "blocked_by_local_security", "suggestion_only", "auto_reverted",
                "undo_failed"):
        assert messages.REASON_TEXT[key] == rm.REASON_TEXT[key] and rm.REASON_TEXT[key].endswith("."), key
    for key in ("two_signal_on", "two_signal_off", "block_length_changed", "watched_services_changed"):
        assert messages.CONTROL_LABELS[key] == rm.CONTROL_LABELS[key], key
    for key in ("suggestion_only", "already_confirmed", "not_isolated", "revert_passed", "invalid_service",
                "invalid_block_length"):
        assert messages.API_DETAIL[key] == rm.API_DETAIL[key], key
    assert (messages.ACTION_LABELS["kill_process"], messages.ACTION_LABELS["isolate_host"],
            messages.ACTION_LABELS["reboot_host"]) == ("Kill process", "Isolate host", "Reboot host")
    # Phase 81 entries are untouched.
    assert messages.REASON_TEXT["level_off"] == "Autonomous Ops is set to Off for this organization."


def test_counts_are_pluralised():
    from autonomous_ops import response_messages as rm
    assert rm.vulnerabilities(1) == "1 vulnerability" and rm.vulnerabilities(2) == "2 vulnerabilities"
    assert rm.files(1) == "1 file" and rm.files(0) == "0 files" and rm.files(11) == "11 files"


def test_every_string_in_the_module_passes_the_rules_and_holds_no_html():
    from autonomous_ops import response_messages as rm
    rules = load_rules()["rules"]
    for name in ("ORIGIN_NAMES", "WHAT_HAPPENS", "NOTICES", "UNDO_HINTS", "RESULT_TEMPLATES", "WHY_TEMPLATES",
                 "FENCE", "REASON_TEXT", "CONTROL_LABELS", "API_DETAIL", "SUGGESTION_LABELS"):
        for text in _strings(getattr(rm, name)):
            assert violations(text, rules) == [], (name, text)
            assert "<" not in text and ">" not in text, (name, text)
