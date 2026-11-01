"""Every server sentence of Phase 83 (autonomous security response), in one module.

83-UI-SPEC sections 2a, 3, 4, 5 and 8 and the What happens lines are copied verbatim. The fences,
the sweep stages, the incident cards and the Activity rows all read this module, so no other new
module holds a sentence shown to a person. ACTV-08 scans this file against the rules in
shared/autonomous-ops-banned-terms.json: the feature is called Autonomous Ops, and the terms listed
there are never used (say undo / undone). Dictionary keys are identifiers, not words shown to anyone.

Templates use ``{name}`` tokens. ``fill`` replaces only the tokens it is given, so a token the browser
fills itself (``{until}``, ``{at}``) stays literal in the text the server sends. Plain strings only;
no HTML anywhere (T-83-09): the browser renders every one of these as text.
"""
from datetime import date, datetime
from typing import Any, Iterable, Optional

# ---------------------------------------------------------------- origins (D-01)

# The shown names of the sources that can name an indicator, keyed by the origin id the signals store uses.
ORIGIN_NAMES = {
    "native": "agent verdict",
    "feed:urlhaus": "URLhaus",
    "feed:malwarebazaar": "MalwareBazaar",
    "feed:otx": "OTX",
    "virustotal": "VirusTotal",
    "onhost": "detection on this computer",
}

# What an undo command removes, keyed by the undo command (the claim the undo names on the agent).
CLAIM_LABELS = {"unblock_ip": "block", "unquarantine_file": "quarantine", "restore_host": "isolation"}

# ---------------------------------------------------------------- what happens (before the click)

WHAT_HAPPENS = {
    "kill_process": "Ends this process right away. Unsaved work in it is lost.",
    "isolate_host": ("Cuts this computer off from the network except its connection to the platform. It returns "
                     "to the network automatically after 4 hours unless you confirm it."),
    "reboot_host": "Restarts this computer. Anyone using it loses unsaved work.",
    "restart_over_budget": "Restarts {service} on this computer. If it fails again it stays down until you act.",
    "kill_then_quarantine": "Ends the process, then moves the file to quarantine. Nothing is deleted.",
    "protected_file": ("Moves this system file to quarantine. If it is needed, this computer may stop working "
                       "properly until you undo this. Nothing is deleted."),
}

# Info blocks on a card (plain strings, unlike the title and message pairs in ``messages.NOTICES``).
NOTICES = {
    "kill_then_quarantine": ("The file couldn't be moved because it is running. Approving ends the process, then "
                             "tries the quarantine again. Nothing is deleted."),
    "kill_only": ("The file was moved to quarantine, but its process is still running. Approving ends the "
                  "process."),
}

UNDO_HINTS = {
    "unblock_ip": "Removes the block on {ip}.",
    "unquarantine_file": "Restores {path} to where it was.",
    "restore_host": "Restores the network connection.",
}
# Used when the row holds no address or path to name.
UNDO_HINTS_PLAIN = {"unblock_ip": "Removes the block.", "unquarantine_file": "Restores the file to where it was."}

# ---------------------------------------------------------------- the Result column

RESULT_TEMPLATES = {
    "block_active": "Blocked for {length}, until {until}. Verified: the firewall rule is in place.",
    "block_expired": "Block removed automatically at {at} when its time ran out.",
    "block_check_failed": "The host did not confirm the firewall rule, so this is marked failed.",
    "quarantine_done": "Moved {path} to quarantine. It was not deleted. Verified: the file is in quarantine.",
    "quarantine_still_running": "The process is still running. See Needs your decision.",
    "restart_done": "Restarted {service}. Healthy again after {seconds} s. Restart {attempt} of 3 this hour.",
    "isolation_done": "{host} is isolated. The connection to the platform stays open.",
    "isolation_reverted": "Returned to the network automatically after 4 hours. Nobody confirmed the isolation.",
    "suggestion_vulnerability": "No action was taken. Patching is where you apply fixes.",
    "suggestion_file_change": "No action was taken. Check whether these changes were expected.",
    "suggestion_one_source": ("Nothing was done. If a second source agrees within 24 hours this runs on its own. "
                             "After that it stays a suggestion."),
    "suggestion_correlation": "Nothing was done. Correlation rules only suggest actions.",
    "not_repeated": "Not repeated.",
    "nothing_done": "Nothing was done.",
}

# ---------------------------------------------------------------- the Why column

WHY_TEMPLATES = {
    "two_sources": "Two sources agree: {first} and {second}.",
    "rule_off": "This organization's two-source rule is off, so one source was enough: {origin}.",
    "one_source": "Only one source flagged this: {origin}. A second, different source has to agree.",
    "restart_watched": "{service} stopped and is on your watched list.",
    "restart_over_budget": "Restarted {service} 3 times in the last hour. Further restarts need your approval.",
    "protected_file": "This is a protected system file, so it isn't moved automatically. {reason}",
    "undone_earlier": "You undid this action on {date}. It isn't repeated for 24 hours.",
    "host_cap": ("This computer already had 3 automatic actions in the last hour, so this one needs your "
                 "approval."),
    "agent_cannot": "This computer's agent doesn't support this action yet.",
    "os_cannot": "This action isn't supported on {os}.",
    "correlation": "A correlation rule asked for this: {rule}.",
    "vulnerability": "{n} known {noun} reported by {host}. Highest severity: {severity}.",
    "file_change": "{n} {noun} changed on {host} since the last baseline.",
}

# The label of a suggestion row (replaces the action label), keyed by what is suggested.
SUGGESTION_LABELS = {
    "block_ip": "Suggested: block IP address",
    "quarantine_file": "Suggested: quarantine file",
    "isolate_host": "Suggested: isolate host",
    "vulnerability": "Suggested: patch vulnerabilities",
    "file_change": "Suggested: review file changes",
}
SUGGESTION_CLASS_LINE = "Suggestion only"

# The views a grouped suggestion links to, keyed by suggestion kind.
SUGGESTION_VIEWS = {"vulnerability": "patchManagement", "file_change": "fimMonitoring"}

# ---------------------------------------------------------------- the old containment paths (D-18)

FENCE = {
    "swarm": "Nothing was sent. Antibody propagation no longer sends containment to agents on its own. Containment is handled in Autonomous Ops.",
    "soar": ("Nothing was sent. This playbook step no longer sends containment to agents on its own. "
             "Containment is handled in Autonomous Ops."),
    "worker": ("Nothing was sent. This background task no longer sends containment or remediation scripts to "
               "agents on its own. Containment is handled in Autonomous Ops."),
    "swarm_mission": ("A containment step was removed from this swarm plan because nothing is sent to agents on "
                      "its own. Containment is handled in Autonomous Ops."),
}

# ---------------------------------------------------------------- additions to messages.py tables

REASON_TEXT = {
    "agent_unsupported": WHY_TEMPLATES["agent_cannot"],
    "capability_off": "Remediation is not switched on for this organization, so nothing was done.",
    "agent_offline": "The computer is offline, so nothing was done.",
    "range_block": "The request named a range of addresses. Only a single IP address is blocked automatically.",
    "superseded": "A second source agreed, so this suggestion became an action.",
    "hash_mismatch": "The file does not match what was flagged, so it was not moved.",
    "locked": "The file is in use and could not be moved, so a person has to decide.",
    "protected_path": "This is a protected system file, so it isn't moved automatically.",
    "blocked_by_local_security": "Security software on the computer blocked this action.",
    "suggestion_only": "This was only suggested. Nothing was done.",
    "auto_reverted": RESULT_TEMPLATES["isolation_reverted"],
    "undo_failed": "The host did not confirm the undo, so the action may still be in place.",
}

CONTROL_LABELS = {
    "two_signal_on": "Two-source rule turned on",
    "two_signal_off": "Two-source rule turned off",
    "block_length_changed": "Block length changed",
    "watched_services_changed": "Watched services changed",
}

API_DETAIL = {
    "suggestion_only": "This was only a suggestion, so there is nothing to approve.",
    "already_confirmed": "This isolation was already confirmed.",
    "not_isolated": "This computer is not isolated by Autonomous Ops.",
    "revert_passed": "The isolation was already returned to the network automatically.",
    "invalid_service": ("Use only letters, numbers, dots, hyphens and underscores, starting with a letter or "
                        "number."),
    "invalid_block_length": "Enter a block length between 1 hour and 7 days.",
}


# ---------------------------------------------------------------- functions

def fill(template: str, **values: Any) -> str:
    """Replace only the given ``{name}`` tokens; any other token stays literal for the browser."""
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def origin_name(origin_id: Any) -> str:
    """The shown name of an origin id. An unknown id raises KeyError and is never shown raw."""
    return ORIGIN_NAMES[origin_id]


def _shown_names(origin_ids: Iterable[Any]) -> list:
    """The distinct origins' shown names in sorted order (KeyError on an unknown id)."""
    return sorted({origin_name(i) for i in origin_ids}, key=str.lower)


def why_two_sources(origin_ids: Iterable[Any]) -> str:
    """Two sources agree: {a} and {b}. Refuses (ValueError) unless two different origins are given,
    so the sentence can never claim two sources from one (T-83-11)."""
    names = _shown_names(list(origin_ids))
    if len(names) < 2:
        raise ValueError("two different origins are needed to say two sources agree")
    return fill(WHY_TEMPLATES["two_sources"], first=names[0], second=names[1])


def why_one_source(origin_id: Any) -> str:
    return fill(WHY_TEMPLATES["one_source"], origin=origin_name(origin_id))


def why_rule_off(origin_id: Any) -> str:
    return fill(WHY_TEMPLATES["rule_off"], origin=origin_name(origin_id))


def _count(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def vulnerabilities(n: int) -> str:
    return _count(n, "vulnerability", "vulnerabilities")


def files(n: int) -> str:
    return _count(n, "file", "files")


def why_vulnerabilities(n: int, host: str, severity: str) -> str:
    return fill(WHY_TEMPLATES["vulnerability"], n=n, noun="vulnerability" if n == 1 else "vulnerabilities",
                host=host, severity=severity)


def why_file_changes(n: int, host: str) -> str:
    return fill(WHY_TEMPLATES["file_change"], n=n, noun="file" if n == 1 else "files", host=host)


def short_date(value: Any) -> str:
    """Mon D (UTC date, no year), e.g. Oct 31; an unreadable value gives an empty string."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if isinstance(value, (datetime, date)):
        return f"{value:%b} {value.day}"
    return ""


def length_text(seconds: int) -> str:
    """A block length in words: whole days from 2 days up, else hours (at least 1)."""
    seconds = max(int(seconds), 0)
    if seconds >= 2 * 86400 and seconds % 86400 == 0:
        return _count(seconds // 86400, "day", "days")
    return _count(max(round(seconds / 3600), 1), "hour", "hours")


def undo_hint(undo_command: Optional[str], *, ip: Optional[str] = None, path: Optional[str] = None) -> Optional[str]:
    """The line under the Undo button, or None when the undo has no hint."""
    template = UNDO_HINTS.get(undo_command)
    if template is None:
        return None
    if "{ip}" in template and not ip:
        return UNDO_HINTS_PLAIN.get(undo_command)
    if "{path}" in template and not path:
        return UNDO_HINTS_PLAIN.get(undo_command)
    return fill(template, ip=ip, path=path)


def what_happens(key: str, **values: Any) -> str:
    return fill(WHAT_HAPPENS[key], **values)

