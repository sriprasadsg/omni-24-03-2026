"""TDD suite for the deterministic YAML remediation playbook layer (53-01).

Hermetic: load_playbooks()/select_playbook() read the vendored YAML dir
directly, no database required for these tests.
"""
import pytest

from remediation_playbook_service import (
    ACTION_MAP,
    load_default_playbooks,
    select_playbook,
    validate,
)


class _Finding:
    def __init__(self, finding_type, resource_id=None, details=None, agent_id=None):
        self.finding_type = finding_type
        self.resource_id = resource_id
        self.details = details or {}
        self.agent_id = agent_id


def test_load_default_playbooks_returns_at_least_six():
    playbooks = load_default_playbooks()
    assert len(playbooks) >= 6
    names = {p["name"] for p in playbooks}
    assert {"patch_package", "kill_process", "restore_file", "block_ip", "disable_service", "rotate_key"} <= names
    for p in playbooks:
        assert "name" in p
        assert "finding_class" in p
        assert "steps" in p and len(p["steps"]) >= 1

def test_select_playbook_for_rotate_key_with_fingerprint():
    finding = _Finding("vuln", details={"playbook_ref": "rotate_key", "fingerprint": "SHA256:abc", "affected_path": "/some/path"})
    playbook = select_playbook(finding)
    assert playbook is not None
    assert playbook["name"] == "rotate_key"

def test_select_playbook_for_preexisting_secret_finding_without_fingerprint_is_unchanged():
    # This simulates the existing vulnerability_scan.rs::secret_finding() output
    # which has playbook_ref rotate_key but no fingerprint, and should route to disable_service
    finding = _Finding("vuln", details={"type": "secret", "playbook_ref": "rotate_key", "affected_path": "/etc/environment", "detail": "Private key material"})
    playbook = select_playbook(finding)
    assert playbook is not None
    assert playbook["name"] == "disable_service"

def test_select_playbook_for_rotate_key_with_empty_fingerprint_is_unchanged():
    finding = _Finding("vuln", details={"playbook_ref": "rotate_key", "fingerprint": "", "affected_path": "/some/path"})
    playbook = select_playbook(finding)
    assert playbook is not None
    assert playbook["name"] == "disable_service"

def test_select_playbook_for_vuln_with_cve_and_rotate_key_selects_rotate_key_first():
    finding = _Finding("vuln", details={"cveId": "CVE-2023-1234", "playbook_ref": "rotate_key", "fingerprint": "SHA256:def"})
    playbook = select_playbook(finding)
    assert playbook is not None
    assert playbook["name"] == "rotate_key"

def test_destructive_flag_preserved():
    playbooks = {p["name"]: p for p in load_default_playbooks()}
    assert playbooks["kill_process"]["steps"][0]["destructive"] is True
    assert playbooks["patch_package"]["steps"][0]["destructive"] is False
    assert playbooks["rotate_key"]["steps"][0]["destructive"] is True


def test_select_playbook_for_vuln_finding_with_cve():
    finding = _Finding("vuln", resource_id="asset-1", details={"cveId": "CVE-2023-1234", "package": "openssl"})
    playbook = select_playbook(finding)
    assert playbook is not None
    assert playbook["name"] == "patch_package"


def test_select_playbook_for_malicious_process_nscan_finding():
    finding = _Finding("nscan", resource_id="1234", details={"type": "file", "verdict": "Malicious"})
    playbook = select_playbook(finding)
    assert playbook is not None
    assert playbook["name"] == "kill_process"


def test_select_playbook_for_fim_drift_finding():
    finding = _Finding("fim", resource_id="/etc/passwd", details={"change_type": "modified"})
    playbook = select_playbook(finding)
    assert playbook is not None
    assert playbook["name"] == "restore_file"


def test_select_playbook_for_ip_nscan_finding():
    finding = _Finding("nscan", resource_id="1.2.3.4", details={"type": "ip", "verdict": "Malicious"})
    playbook = select_playbook(finding)
    assert playbook is not None
    assert playbook["name"] == "block_ip"


def test_select_playbook_for_vuln_misconfig_finding():
    finding = _Finding("vuln", resource_id="svc-1", details={"package": "telnet"})
    playbook = select_playbook(finding)
    assert playbook is not None
    assert playbook["name"] == "disable_service"


def test_select_playbook_unknown_finding_type_returns_none():
    finding = _Finding("compliance", resource_id="ctrl-1")
    assert select_playbook(finding) is None


def test_select_playbook_for_shadow_ai_anomaly_with_agent_returns_kill_process():
    finding = _Finding("anomaly", details={"anomaly_rule": "shadow_ai_detected"}, agent_id="agent-1")
    playbook = select_playbook(finding)
    assert playbook is not None
    assert playbook["name"] == "kill_process"


def test_select_playbook_for_shadow_ai_anomaly_without_agent_returns_none():
    finding = _Finding("anomaly", details={"anomaly_rule": "shadow_ai_detected"}, agent_id=None)
    assert select_playbook(finding) is None


def test_select_playbook_for_other_anomaly_rule_returns_none():
    finding = _Finding("anomaly", details={"anomaly_rule": "brute_force"}, agent_id=None)
    assert select_playbook(finding) is None


def test_destructive_flag_preserved():
    playbooks = {p["name"]: p for p in load_default_playbooks()}
    assert playbooks["kill_process"]["steps"][0]["destructive"] is True
    assert playbooks["patch_package"]["steps"][0]["destructive"] is False


def test_action_map_resolves_every_default_action():
    playbooks = load_default_playbooks()
    used_actions = set()
    for p in playbooks:
        for step in p["steps"]:
            used_actions.add(step["action"])
        for step in p.get("rollback", []):
            used_actions.add(step["action"])
    for action in used_actions:
        assert action in ACTION_MAP
        assert isinstance(ACTION_MAP[action], str)


def test_validate_rejects_unknown_action():
    bad = {
        "name": "evil",
        "finding_class": "vuln",
        "steps": [{"action": "format_disk", "params": {}, "destructive": True}],
    }
    with pytest.raises(ValueError):
        validate(bad)


def test_validate_rejects_missing_required_fields():
    with pytest.raises(ValueError):
        validate({"name": "no_class"})


def test_validate_accepts_default_playbooks():
    for p in load_default_playbooks():
        validate(p)  # must not raise
