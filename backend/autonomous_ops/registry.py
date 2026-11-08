"""The code-owned action registry (GATE-04).

Which actions run on their own, which need a person, and what undoes each. The table is a
read-only mapping built at import: nothing at runtime (a playbook, a database document, a
request) can add, change or lower an entry, so concurrent decisions always read the same
classes. An action name that is not here is refused by the gate (fail closed).

The class of an action comes only from this table plus one explicit playbook step key,
``gate_class``: a step that sets it to anything other than "auto" raises the playbook to
approval, and nothing lowers an approve action. The step key ``destructive`` is NOT an
input: every vendored playbook step except patch_package sets it, block_ip included, so
reading it would turn the locked automatic block-IP into an approval card (GATE-04).

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
    ("ip", "host" or "none"; "ticket" acts on a service desk ticket and is never sent to an agent). ip_params: parameter names that carry an IP address. cidr_params: parameter
    names that carry a whole network (Phase 83): a request holding one always needs a person.
    dispatchers: the only dispatchers allowed to ask for the action; empty means any dispatcher.
    install_patches is the one automatic action limited to a single dispatcher (PTCH-06)."""
    name: str
    cls: str
    undo: Optional[str] = None
    target_kind: str = "host"
    ip_params: Tuple[str, ...] = ()
    cidr_params: Tuple[str, ...] = ()
    dispatchers: Tuple[str, ...] = ()


def _specs(*specs: ActionSpec):
    return MappingProxyType({s.name: s for s in specs})


ACTIONS = _specs(
    # Locked split (GATE-04): these three run on their own.
    ActionSpec("block_ip", "auto", undo="unblock_ip", target_kind="ip", ip_params=("ip_address", "ip"),
               cidr_params=("cidr",)),
    ActionSpec("quarantine_file", "auto", undo="unquarantine_file"),
    ActionSpec("restart_service", "auto"),
    # PTCH-06 / OQ1: a fourth automatic action, only ever asked for by the patch rollout controller and
    # only for the canary ring. Any other dispatcher is refused unregistered_action, at decide time
    # (gate._step_class) and again at delivery (dispatch_check.bind).
    ActionSpec("install_patches", "auto", undo="rollback_patches", dispatchers=("patch_rollout",)),
    # DESK-01 / D-03: a fifth automatic action, only ever asked for by the service desk and only on a ticket
    # of the caller's own tenant (desk_gate.ticket_owner_step). It writes a comment on a ticket, so it
    # is never delivered to an agent (see agent_commands). ticket_withdraw is only its inverse.
    ActionSpec("ticket_answer", "auto", undo="ticket_withdraw", target_kind="ticket", dispatchers=("service_desk",)),
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
    ActionSpec("unblock_ip", "undo_only", target_kind="ip", ip_params=("ip_address", "ip"), cidr_params=("cidr",)),
    ActionSpec("enable_service", "undo_only"),
    ActionSpec("unquarantine_file", "undo_only"),
    ActionSpec("restore_host", "undo_only"),
    ActionSpec("rotate_key_rollback", "undo_only"),
    ActionSpec("rollback_patches", "undo_only"),
    ActionSpec("ticket_withdraw", "undo_only", target_kind="ticket", dispatchers=("service_desk",)),
    # Read-only verify re-scans.
    ActionSpec("scan_file", "probe", target_kind="none"),
    ActionSpec("scan_ip", "probe", target_kind="none"),
    ActionSpec("scan_url", "probe", target_kind="none"),
    ActionSpec("scan_hash", "probe", target_kind="none"),
)

# Playbook action names that differ from the instruction command.
ALIASES = MappingProxyType({"patch_package": "upgrade_software", "isolate_endpoint": "isolate_host"})


# The only playbook step key that can raise a class (GATE-04).
GATE_CLASS_KEY = "gate_class"


def resolve(name) -> Optional[ActionSpec]:
    """The spec for an action name (aliases followed), or None when it is not registered."""
    if not isinstance(name, str):
        return None
    return ACTIONS.get(ALIASES.get(name, name))


def commands() -> frozenset:
    """Every registered command name."""
    return frozenset(ACTIONS)


def agent_commands() -> frozenset:
    """Every registered command that can be sent to an agent: the ticket actions of the service desk
    (target_kind "ticket") are decided by the gate but never delivered to an agent (DESK-01)."""
    return frozenset(name for name, spec in ACTIONS.items() if spec.target_kind != "ticket")


def playbook_raises(steps) -> bool:
    """True only when some step sets ``gate_class`` to a non-empty value other than "auto"
    (case and surrounding spaces ignored). A misspelt value therefore fails closed, toward
    approval; "auto" is accepted and changes nothing; ``destructive`` is ignored."""
    if not isinstance(steps, (list, tuple)):
        return False
    for step in steps:
        if not isinstance(step, dict):
            continue
        value = step.get(GATE_CLASS_KEY)
        if value is None:
            continue
        value = str(value).strip().lower()
        if value and value != "auto":
            return True
    return False


def effective_class(spec: ActionSpec, *, playbook_raise: bool = False) -> str:
    """"approve" when the spec is an approve action or the playbook raised the class, else
    "auto". A playbook may raise a class, never lower it (GATE-04)."""
    return "approve" if spec.cls == "approve" or playbook_raise else "auto"
