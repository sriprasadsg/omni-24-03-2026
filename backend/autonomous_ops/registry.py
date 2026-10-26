"""The code-owned action registry (GATE-04).

Which actions run on their own, which need a person, and what undoes each. The table is a
read-only mapping built at import: nothing at runtime (a playbook, a database document, a
request) can add, change or lower an entry, so concurrent decisions always read the same
classes. An action name that is not here is refused by the gate (fail closed).

Never uses the ambient tenant ContextVar; it holds no tenant data at all.
"""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Optional, Tuple


@dataclass(frozen=True)
class ActionSpec:
    """name: the agent instruction command. cls: "auto" (runs on its own), "approve" (needs a
    person), "undo_only" (only the inverse of another action) or "probe" (read-only re-scan).
    undo: the command that puts it back, or None. target_kind: what the action protects
    ("ip", "host" or "none"). ip_params: parameter names that carry an IP address."""
    name: str
    cls: str
    undo: Optional[str] = None
    target_kind: str = "host"
    ip_params: Tuple[str, ...] = ()


def _specs(*specs: ActionSpec):
    return MappingProxyType({s.name: s for s in specs})


ACTIONS = _specs(
    # Locked split (GATE-04): these three run on their own.
    ActionSpec("block_ip", "auto", undo="unblock_ip", target_kind="ip", ip_params=("ip_address", "ip")),
    ActionSpec("quarantine_file", "auto", undo="unquarantine_file"),
    ActionSpec("restart_service", "auto"),
    # These need a person.
    ActionSpec("isolate_host", "approve", undo="restore_host"),
    ActionSpec("kill_process", "approve"),
    ActionSpec("reboot_host", "approve"),
    ActionSpec("upgrade_software", "approve"),
    ActionSpec("restore_file", "approve"),
    ActionSpec("disable_service", "approve", undo="enable_service"),
    ActionSpec("rotate_key", "approve", undo="rotate_key_rollback"),
    ActionSpec("rollback_ransomware", "approve"),
    # Only ever the inverse of a registered action.
    ActionSpec("unblock_ip", "undo_only", target_kind="ip", ip_params=("ip_address", "ip")),
    ActionSpec("enable_service", "undo_only"),
    ActionSpec("unquarantine_file", "undo_only"),
    ActionSpec("restore_host", "undo_only"),
    ActionSpec("rotate_key_rollback", "undo_only"),
    # Read-only verify re-scans.
    ActionSpec("scan_file", "probe", target_kind="none"),
    ActionSpec("scan_ip", "probe", target_kind="none"),
    ActionSpec("scan_url", "probe", target_kind="none"),
    ActionSpec("scan_hash", "probe", target_kind="none"),
)

# Playbook action names that differ from the instruction command.
ALIASES = MappingProxyType({"patch_package": "upgrade_software", "isolate_endpoint": "isolate_host"})


def resolve(name) -> Optional[ActionSpec]:
    """The spec for an action name (aliases followed), or None when it is not registered."""
    if not isinstance(name, str):
        return None
    return ACTIONS.get(ALIASES.get(name, name))


def commands() -> frozenset:
    """Every registered command name."""
    return frozenset(ACTIONS)


def effective_class(spec: ActionSpec, *, playbook_raise: bool = False) -> str:
    """"approve" when the spec is an approve action or the playbook raised the class, else
    "auto". A playbook may raise a class, never lower it (GATE-04)."""
    return "approve" if spec.cls == "approve" or playbook_raise else "auto"
