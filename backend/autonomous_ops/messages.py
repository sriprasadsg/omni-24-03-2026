"""Every user-visible backend string for Autonomous Ops, in one module.

Labels, reasons and notices are plain strings (no HTML). ACTV-08 scans this file: the feature
is called Autonomous Ops, copy never uses the abbreviations ASI or AGI, the word Autopilot,
the phrase fully autonomous, or an unqualified rollback (use undo / undone). The dictionary
keys below are agent instruction identifiers, not words shown to anyone.
"""

# What an action is called on screen, keyed by the registry command name.
ACTION_LABELS = {
    "block_ip": "Block IP address",
    "quarantine_file": "Quarantine file",
    "restart_service": "Restart service",
    "isolate_host": "Isolate host from the network",
    "kill_process": "Stop process",
    "reboot_host": "Restart host",
    "upgrade_software": "Update software",
    "restore_file": "Restore file",
    "disable_service": "Disable service",
    "rotate_key": "Rotate key",
    "rollback_ransomware": "Restore files from a snapshot",
    "unblock_ip": "Unblock IP address",
    "enable_service": "Enable service",
    "unquarantine_file": "Release file from quarantine",
    "restore_host": "Reconnect host to the network",
    "rotate_key_rollback": "Put the previous key back",
    "scan_file": "Re-scan file",
    "scan_ip": "Re-scan IP address",
    "scan_url": "Re-scan web address",
    "scan_hash": "Re-check file hash",
}

# The action class lines shown under the label.
CLASS_LINES = {"auto": "Automatic", "approve": "Needs approval"}

# Control rows (kind "control"), keyed by controlEvent.
CONTROL_LABELS = {
    "stop_pressed": "Stop pressed",
    "stop_cleared": "Stop cleared",
    "platform_stop_pressed": "Platform-wide stop pressed",
    "platform_stop_cleared": "Platform-wide stop cleared",
    "breaker_tripped": "Level lowered by the circuit breaker",
    "level_restored": "Level restored",
    "rate_limit_reached": "Rate limit reached",
}

# D-25: a tenant never sees which platform person acted.
PLATFORM_ADMIN_DISPLAY = "Platform administrator"

# Why a request was refused or held for a person, keyed by gate reason code.
REASON_TEXT = {
    "no_tenant": "The request did not name an organization.",
    "platform_tenant": "Autonomous Ops is not available for the platform organization.",
    "not_enabled": "Autonomous Ops is not switched on for this organization.",
    "platform_stop": "Automatic actions are stopped for the whole platform.",
    "tenant_stop": "Automatic actions are stopped for this organization.",
    "level_off": "Autonomous Ops is set to Off for this organization.",
    "settings_unreadable": "This organization's setting could not be read, so it is treated as Suggest only.",
    "level_suggest": "This organization is set to Suggest only, so a person must approve every action.",
    "suggest_requested": "This action was only suggested.",
    "unregistered_action": "This action is not one Autonomous Ops is allowed to run.",
    "class_approve": "This action is riskier and needs a person's approval.",
    "playbook_raised": "The playbook asks for a person's approval before this step.",
    "class_auto": "This action is allowed to run on its own within the limits you set.",
    "no_target": "The request did not name a host to act on.",
    "cross_tenant_target": "The host is not enrolled in this organization.",
    "protected_target": "The target is on the never-touch list, so it is never changed automatically.",
    "invalid_target": "The address in the request is not a valid IP address.",
    "blast_radius": "The request touches more than one host, so a person must approve it.",
    "rate_limit": "Too many automatic actions ran in the last hour, so a person must approve this one.",
    "duplicate": "The same action is already open or was simulated within the last 24 hours.",
    "suppressed_by_undo": "A person undid this same action within the last 24 hours, so it is not repeated.",
    "ledger_unavailable": "The decision could not be recorded, so nothing was done.",
}


def simulation_result(text: str) -> str:
    """What a shadow-mode row says it would have done."""
    return f"Nothing was done. This is what would have happened: {str(text).rstrip('. ')}."


# In-app notices (title, message). Callers format the message with the named fields.
NOTICES = {
    "rate_limit_reached": (
        "Autonomous Ops rate limit reached",
        "{tenant} reached the limit of {limit} automatic actions in one hour. Further actions wait for "
        "approval until the hour passes."),
    "stop_pressed": (
        "Automatic actions stopped",
        "Automatic actions were stopped for {tenant} by {actor}. {reason}"),
    "platform_stop_pressed": (
        "Automatic actions stopped for the whole platform",
        "Automatic actions were stopped for every organization by {actor}. {reason}"),
    "breaker_tripped": (
        "Autonomous Ops level lowered",
        "{tenant} was lowered to Suggest only after several automatic actions in a row were undone or "
        "failed. A person with manage access can restore it."),
}
