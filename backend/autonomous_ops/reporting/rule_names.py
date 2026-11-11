"""Plain names for the decision rules (Phase 86, D-05).

The ids are written by the code that decides (sweeps, follow-ups, the rollout controller, the service
desk); the names are owned here. A rule id this table does not know reads as the id itself, so a new rule
never breaks a report.
"""
from types import MappingProxyType

RULE_NAMES = MappingProxyType({
    "sweep:block_ip": "Block an address two sources agree on",
    "sweep:single_signal": "Suggest a block from one source",
    "sweep:quarantine_file": "Quarantine a file two sources agree on",
    "sweep:isolate_host": "Isolate a host under attack",
    "sweep:kill_process": "Stop a process after a quarantine",
    "sweep:restart_service": "Restart a stopped service",
    "sweep:suggest_vulnerability": "Suggest a patch for a vulnerability",
    "sweep:suggest_file_change": "Suggest a review of a changed file",
    "rollout:install": "Install patches by ring",
    "rollout:canary_install": "Install patches on the canary ring",
    "rollout:reboot": "Restart after patching",
    "rollout:revert_reboot": "Restart after patches were undone",
    "service_desk:answer": "Answer a ticket",
    "service_desk:handoff": "Hand a ticket to a person",
})

_GATE_PREFIX = "gate:"


def rule_name(rule_id: str) -> str:
    """The plain name for a rule id: the table entry, "Automatic decision ({origin})" for a gate:{origin} id,
    else the id itself."""
    name = RULE_NAMES.get(rule_id)
    if name:
        return name
    if isinstance(rule_id, str) and rule_id.startswith(_GATE_PREFIX) and len(rule_id) > len(_GATE_PREFIX):
        return f"Automatic decision ({rule_id[len(_GATE_PREFIX):]})"
    return str(rule_id)
