"""Autonomous Ops action registry (Phase 81, plan 81-01, GATE-04): the locked auto / approve
split, the raise-only playbook rule and the shipped playbook path. No database.

Value: protects=block IP, quarantine file and restart service run on their own and isolate
host, kill process, reboot host and upgrade software never do; a playbook can ask for approval
only with the explicit gate_class step key (never lower a class, and the destructive flag the
vendored YAML sets on block_ip is not a class input); the table cannot change at runtime;
fails_when=a locked class moves, an approve action can become auto, the shipped block_ip
playbook turns into an approval card, or a registry or playbook name falls out of step with
ACTION_MAP; no_claim=the gate's use of the class (test_autonomous_ops_gate.py and 81-11).
"""
import copy
import dataclasses
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import remediation_playbook_service as playbooks
from autonomous_ops import registry as r

# Phase 84 (PTCH-06, OQ1): install_patches is a deliberate fourth automatic action, limited to the
# patch rollout dispatcher and, in the controller, to the canary ring. The original three are unchanged.
AUTO = ("block_ip", "quarantine_file", "restart_service", "install_patches")
APPROVE = ("isolate_host", "kill_process", "reboot_host", "upgrade_software")


def test_locked_split_and_aliases():
    for name in AUTO:
        assert r.resolve(name).cls == "auto", name
    for name in APPROVE:
        assert r.resolve(name).cls == "approve", name
    assert r.resolve("patch_package") is r.resolve("upgrade_software")
    assert r.resolve("isolate_endpoint") is r.resolve("isolate_host")
    assert r.resolve("nonsense") is None and r.resolve(None) is None and r.resolve(["block_ip"]) is None


def test_install_patches_only_for_the_rollout_dispatcher():
    """protects=PTCH-06 / T-84-01: install_patches is automatic, can be undone by rollback_patches, and
    only the rollout dispatcher may ask for it; rollback_patches is only ever the inverse."""
    spec = r.resolve("install_patches")
    assert spec.cls == "auto" and spec.undo == "rollback_patches" and spec.dispatchers == ("patch_rollout",)
    assert r.resolve("rollback_patches").cls == "undo_only"
    for name, other in r.ACTIONS.items():
        if name != "install_patches":
            assert other.dispatchers == (), name


def test_every_playbook_action_resolves_and_every_undo_is_registered():
    for key in playbooks.ACTION_MAP:
        assert r.resolve(key) is not None, key
    for spec in r.ACTIONS.values():
        if spec.undo:
            target = r.ACTIONS.get(spec.undo)
            assert target is not None and target.cls == "undo_only", (spec.name, spec.undo)
    assert r.commands() == frozenset(r.ACTIONS)
    assert {"block_ip", "unblock_ip", "scan_file"} <= r.commands()


def test_registry_is_immutable():
    with pytest.raises(TypeError):
        r.ACTIONS["block_ip"] = r.ACTIONS["kill_process"]
    with pytest.raises(TypeError):
        r.ALIASES["x"] = "block_ip"
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.ACTIONS["block_ip"].cls = "approve"


def test_effective_class_raises_but_never_lowers():
    for spec in r.ACTIONS.values():
        if spec.cls == "approve":
            assert r.effective_class(spec, playbook_raise=False) == "approve", spec.name
            assert r.effective_class(spec, playbook_raise=True) == "approve", spec.name
        elif spec.cls == "auto":
            assert r.effective_class(spec, playbook_raise=False) == "auto", spec.name
            assert r.effective_class(spec, playbook_raise=True) == "approve", spec.name


def test_playbook_raises_only_on_an_explicit_gate_class_step_key():
    assert r.GATE_CLASS_KEY == "gate_class"
    assert r.playbook_raises([]) is False and r.playbook_raises(None) is False
    assert r.playbook_raises(["block_ip", 3, None]) is False
    assert r.playbook_raises([{"action": "block_ip", "destructive": True}]) is False   # not a class input
    assert r.playbook_raises([{"action": "block_ip", "gate_class": "auto"}]) is False   # never lowers
    assert r.playbook_raises([{"action": "block_ip", "gate_class": "approve"}]) is True
    assert r.playbook_raises([{"action": "block_ip", "gate_class": "aproove"}]) is True  # fails closed
    assert r.playbook_raises([{"action": "block_ip", "gate_class": "  APPROVE "}]) is True
    assert r.playbook_raises([{"action": "block_ip", "gate_class": "  AUTO "}]) is False
    assert r.playbook_raises([{"action": "block_ip"}, {"action": "kill_process", "gate_class": "approve"}]) is True
    assert r.playbook_raises([{"action": "block_ip", "gate_class": ""}]) is False
    assert r.playbook_raises([{"action": "block_ip", "gate_class": None}]) is False


def test_shipped_playbooks_keep_their_registry_class():
    shipped = playbooks.load_default_playbooks()
    assert shipped, "no vendored playbooks loaded"
    for pb in shipped:
        assert r.playbook_raises(pb["steps"]) is False, pb["name"]
    block_ip = {p["name"]: p for p in shipped}["block_ip"]
    assert block_ip["steps"][0].get("destructive") is True      # the flag the research mistook for a raise
    raise_flag = r.playbook_raises(block_ip["steps"])
    assert r.effective_class(r.resolve("block_ip"), playbook_raise=raise_flag) == "auto"
    raised = copy.deepcopy(block_ip)
    raised["steps"][0]["gate_class"] = "approve"
    assert r.effective_class(r.resolve("block_ip"), playbook_raise=r.playbook_raises(raised["steps"])) == "approve"
    for pb in shipped:        # every shipped step still resolves to a registered, dispatchable action
        for step in pb["steps"]:
            spec = r.resolve(step["action"])
            assert spec is not None and spec.cls in ("auto", "approve"), (pb["name"], step["action"])
