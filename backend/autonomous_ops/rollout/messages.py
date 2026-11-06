"""Every server sentence of the staged patch rollouts (Phase 84), in one module.

84-UI-SPEC sections 2 to 7 and the Copywriting Contract are copied from here; the rollout screens, cards,
preflight, halt block and Activity rows read this module, so no other rollout module holds a sentence shown
to a person (PTCH-04). ACTV-08 scans this whole directory against shared/autonomous-ops-banned-terms.json.

Copy rules: plain English, short sentences, no emoji, no HTML (the browser renders every string as text).
Say "revert" or "put back", never an unqualified word for rolling a change back; the identifier
``rollback_patches`` is only a registry command name and is never shown. No sentence may claim a revert
the agent did not report as done: a computer that could not be reverted reads "Not reverted: <reason>. The
patch is still installed." (PROH-84-02).

Templates use ``{name}`` tokens. ``fill`` replaces only the tokens it is given. Count tokens named
``{computers}``, ``{patches}``, ``{hours}`` expect a phrase from ``plural`` ("1 computer", "3 computers"), so
no sentence ever reads "1 computers". Where a sentence changes shape at one (verbs, pronouns) the entry is a
``{"one": ..., "many": ...}`` pair and ``forms`` picks it.
"""
from typing import Any, Dict

# ---------------------------------------------------------------- helpers


def fill(template: str, **values: Any) -> str:
    """Replace only the given ``{name}`` tokens; any other token stays literal for the browser."""
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def plural(n: int, one: str, many: str) -> str:
    """The number and the noun that agrees with it: plural(1, "computer", "computers") is "1 computer"."""
    return f"{n} {one if n == 1 else many}"


def count(n: int, noun_one: str, noun_many: str) -> str:
    """Only the noun that agrees with ``n``: count(3, "host", "hosts") is "hosts"."""
    return noun_one if n == 1 else noun_many


def forms(n: int, pair: Dict[str, str], **values: Any) -> str:
    """The ``one`` or ``many`` form of a pair, filled; ``n`` is also available as ``{n}``."""
    return fill(pair["one" if n == 1 else "many"], n=n, **values)


# ---------------------------------------------------------------- fixed lines (UI-SPEC sections 2 and 4)

ASSURANCE = ("A rollout halts on failure; reverts where supported. "
             "Nothing is installed outside your maintenance window.")
HALT_SECOND_LINE = ("A rollout halts on failure; reverts where supported. "
                    "Rings that already passed keep the patches. Nothing further installs.")
HALT_FIRST_LINE = "Halted at {ring}: {reason}"

STOPPED = ("Rollouts are paused while automatic actions are stopped. Nothing new installs or restarts. "
           "A revert that is already under way still runs.")
STOPPED_PLATFORM = ("Rollouts are paused because automatic actions are stopped for the whole platform. "
                    "Nothing new installs or restarts. A revert that is already under way still runs.")
SHADOW = ("Shadow mode is on for this organization. A rollout runs as a simulation: it records what it would "
          "have done and installs and restarts nothing.")

# ---------------------------------------------------------------- ring and computer states (section 4)

RING_DETAIL = {
    "not_started": "Starts after {previous} passes.",
    "waiting_for_approval": "Waiting for your approval in Needs your decision.",
    "waiting_for_approval_no_access": "Waiting for someone with access to Autonomous Ops.",
    "waiting_for_window": "Opens {opens} ({zone}).",
    "installing": "{k} of {n} installed.",
    "restarting": "{k} of {n} back up.",
    "soaking": "Soak: {h} h left. Ends {ends}.",
    "checking_health": "Waiting for {signal}.",
    "passed": "{computers} healthy.",
    "passed_not_reached": "{computers} healthy. {k} not reached.",
    "reverted": "Reverted on {computers}.",
    "reverted_some_not": "Reverted on {computers}. {k} could not be reverted.",
    "cancelled_before": "Ended before this ring started.",
    "cancelled_running": "Ended while this ring was running.",
    # Simulation (shadow mode): the same states in the conditional.
    "sim_installing": "Would install on {computers}.",
    "sim_restarting": "Would restart {computers}.",
}

HOST_RESULT = {
    "waiting_window": "Waiting for the next window.",
    "waiting_approval": "Waiting for approval.",
    "installing": "Installing {patches}.",
    "installed": "Installed {patches}. Verified: no longer pending.",
    "restarting": "Restarting. Waiting for a heartbeat from the new start.",
    "healthy": "Passed every check at {at}.",
    "failed_install": "{patch} failed to install: {message}.",
    "failed_no_heartbeat": "No heartbeat from this computer within 30 minutes of the restart, so the ring halts.",
    "failed_service": "{service} is not running after the update.",
    "reverted": "Reverted {patches} at {at}.",
    "not_reached": ("Offline for the whole ring, so nothing was installed. It gets the patches in a later "
                    "window if it comes back online."),
    "left_out": 'In "{other}" at the time this rollout started.',
    "reverting": "Reverting {patches}.",
    "would_install": "Would install {patches}. Nothing was carried out.",
    "would_restart": "Would restart. Nothing was carried out.",
}

# ---------------------------------------------------------------- health check, failure rate, soak

NOT_CHECKED = "{services} can't be checked on {k} of {n} computers until their agent is updated."

HEALTH = {
    "titles": {"install": "Install result", "inventory": "Inventory after install",
               "heartbeat": "Heartbeat after restart", "services": "Services"},
    "install": "{k} of {computers} installed without an error.",
    "inventory": "{k} of {computers} no longer list these patches.",
    "heartbeat": "{k} of {computers} sent a heartbeat after restarting.",
    "services": "{services} are running on {k} of {computers}.",
    "services_agent_only": "Only the agent service is checked.",
    "not_checked": NOT_CHECKED,
    "no_data": "No data for {signal} counts as a failure, so the ring halts.",
    "waiting": "Waiting for {signal}.",
    # The shown names of the four signals in sentences such as "Waiting for {signal}."
    "signals": {"install": "the install result", "inventory": "the inventory after the install",
                "heartbeat": "the heartbeat after the restart", "services": "the services check"},
}

FAILURE_RATE = {
    "canary": "Any failure halts the rollout.",
    "at_or_above_minimum": ("{f} of {computers} failed ({p}%). The ring halts above {limit}% once {min} computers "
                            "have reported. Below {min} computers, any failure halts."),
    "below_minimum": ("{f} of {computers} failed. Fewer than {min} computers have reported, so any failure "
                      "halts."),
}

SOAK = "Soaks {hours} after the last install or restart."

# ---------------------------------------------------------------- the halt (section 4, R11)

HALT_REASON = {
    "failure_share": "{f} of {computers} failed, more than the {limit}% limit.",
    "canary_failed": "a computer failed its health check.",
    "host_failed": "{host} failed its health check.",
    "no_data:install": "no data for the install result.",
    "no_data:inventory": "no data for the inventory after the install.",
    "no_data:heartbeat": "no data for the heartbeat after the restart.",
    "no_data:services": "no data for the services check.",
    "no_new_boot": "no heartbeat from {host} within 30 minutes of the restart.",
    "install_denied": "the install was denied.",
    "restart_denied": "the restart was denied.",
    "approval_expired": "the approval expired.",
}

# Why a computer could not be put back: the reason alone, and the full Not reverted sentence built from it.
NOT_REVERTED_REASON = {
    "not_uninstallable": "Windows doesn't allow this update to be uninstalled",
    "version_not_offered": "the earlier version is no longer offered by the package source",
    "agent_unsupported": "this computer's agent doesn't support it yet",
}
NOT_REVERTED = {code: f"Not reverted: {reason}. The patch is still installed."
                for code, reason in NOT_REVERTED_REASON.items()}
# A computer whose recorded reason is not one of the three above: still honest, never reads as reverted.
NOT_REVERTED_OTHER = "Not reverted. The patch is still installed."

REVERT_SUMMARY = {
    "running": "Reverting {computers} now.",
    "done": "Reverted on {computers}.",
    "could_not": {"one": "{computers} could not be reverted: {reason}. The patch is still installed on it.",
                  "many": "{computers} could not be reverted: {reason}. The patch is still installed on them."},
    "could_not_other": {"one": "{computers} could not be reverted. The patch is still installed on it.",
                        "many": "{computers} could not be reverted. The patch is still installed on them."},
    "needs_restart": "A restart is needed on {computers} to finish the revert. See Needs your decision.",
}

# ---------------------------------------------------------------- the window strip and the rings card (sections 2 and 5)

WINDOW_STRIP = {"open": "Closes at {closes} ({zone}).", "closed": "Next window opens {opens} ({zone}).",
                "none": "Add a maintenance window first."}
RINGS_SUMMARY = {
    "unset": "No rings set up yet \u00b7 Canary needs a group before a rollout can start",
    "last": "Everyone else",
    "soak_same": "{h}-hour soak",
    "soak_range": "{lo} to {hi}-hour soaks",
}
DRAFT_NAME = {"cve": "Patches for {cve} on {host}", "many": "Patches for vulnerabilities on {host}"}

# ---------------------------------------------------------------- the check before starting (section 3, DEV-3)

CANARY_OS_GAP = {
    "one_group": "The canary ring has no {os} host; add one to the {group} group.",
    "several_groups": "The canary ring has no {os} host; add one to a group in the canary ring.",
}
LEFT_OUT = {
    "one": '1 host is in "{name}" and was left out.',
    "many": '{n} hosts are in "{name}" and were left out.',
}
LEFT_OUT_MORE = "and {k} more"
LEFT_OUT_SHOWING = "Showing {shown} of {n}."
OFFLINE_NOW = {
    "one": "1 computer is offline now. It gets the patches in a later window if it comes back online.",
    "many": "{n} computers are offline now. They get the patches in a later window if they come back online.",
}

PREFLIGHT = {
    "titles": {"window": "Window", "rings": "Rings", "canary": "Canary ring", "left_out": "Left out",
               "offline": "Offline now", "autonomous_ops": "Autonomous Ops", "cap": "Size of the rollout",
               "patches": "Patches"},
    "window_ok": "Next window: {opens} ({zone}).",
    "window_blocker": "Add a maintenance window first.",
    "rings_ok": "{computers} in {rings}: {breakdown}.",
    "rings_not_set": "Your rollout rings are not set up yet. Pick a group for the canary ring in Rollout rings.",
    "canary_empty": "The canary ring has no computers. Pick a group for it in Rollout rings.",
    "canary_ok": "The canary ring has a {os} computer.",
    "autonomy_off": "Autonomous Ops is off for this organization, so a rollout can't run.",
    "stopped": "Paused while automatic actions are stopped.",
    "cap": "A rollout can reach at most 500 computers. Pick fewer patches or split your rings.",
    "nothing_pending": "Nothing is waiting to be installed.",
}

# One sentence each for a computer that cannot take a rollout; it is listed in the Left out area, never dropped.
CANNOT_TAKE = {
    "agent_too_old": "The agent on this computer is too old to take a rollout.",
    "capability_off": "Patch installs are not switched on for this computer.",
    "unsupported_os": "Only Windows and Linux computers can take a rollout.",
    "busy": "This computer is busy with another patch job.",
    "never_touch": "This computer is on the never-touch list.",
}

VALIDATION = {
    "name": "Enter a name for this rollout.",
    "patches": "Pick at least one patch to install.",
    "canary_group": "Pick at least one group for the Canary ring.",
    "ring_name": "Enter a ring name.",
    "ring_names_unique": "Ring names must be different.",
    "soak_hours": "Enter hours between 1 and 168.",
    "fail_pct": "Enter a percentage between 1 and 50.",
    "min_sample": "Enter a number between 1 and 100.",
    # Rings the screen cannot get wrong by itself but the server still checks (plan 84-06)
    "ring_count": "A rollout needs 2 to 4 rings.",
    "ring_name_long": "A ring name can be up to 40 characters.",
    "canary_name": "The first ring is always named Canary.",
    "ring_group": "Pick at least one group for every ring except the last.",
    "group_twice": "A group can be in only one ring.",
    "group_unknown": "One of those groups was not found. Pick groups from your own Agent Groups.",
    # Maintenance windows (UI-SPEC section 8, plan 84-05)
    "window_name": "Enter a window name.",
    "window_name_long": "A window name can be up to 60 characters.",
    "window_repeats": "Choose One-time, Daily or Weekly.",
    "window_times": "Enter a start and end time.",
    "window_dates": "Enter a start and end date and time.",
    "window_days": "Choose at least one day.",
    "window_days_range": "Choose days from Monday (1) to Sunday (7).",
    "window_same_time": "The window can't start and end at the same time.",
    "window_too_long": "A window can be up to 24 hours long.",
    "window_end_before_start": "The end must be after the start.",
    "window_limit": "You can keep up to 50 maintenance windows. Delete one first.",
    "time_zone": "Choose a time zone from the list, for example Asia/Kolkata.",
}

# The control row written when a person saves the rings; shown in Activity and mirrored to the audit chain.
RINGS_SAVED = "Rollout rings saved: {rings} ({names})."

# ---------------------------------------------------------------- the approval card (section 6)

CARD = {
    "ring_subtitle": "Ring {i} of {r}: {ring} · {computers}",
    "meta": "{patches} · {computers} · Started {when} by {name}",
    "labels": {"install": "Install {patches} on {computers}", "reboot": "Restart {computers}",
               "revert_reboot": "Restart {computers} to finish the revert"},
    "why": {
        "install": "{previous} passed its health check at {at}. {ring} is next.",
        "install_not_reversible": "{patch} can't be reversed on every computer in this ring, so it needs your approval.",
        "reboot": "A restart is needed on {computers} to finish installing.",
        "revert_reboot": "Removing the update needs a restart on {computers}.",
    },
    "what_happens": {
        "install": ("Installs these patches inside your maintenance window{window_clause}. The ring halts if "
                    "more than {limit}% of its computers fail or a check has no data."),
        "restart": ('Restarts these computers with a 5-minute warning ("Restarting in 5 minutes for updates"). '
                    "Anyone using them loses unsaved work. Runs now if your window is open, otherwise when it "
                    "next opens at {opens}."),
    },
    "window_clause": {"open": " (open now, closes {closes})", "next": " (next opens {opens})"},
    "settled": {
        "approved_install": "Approved. Installing {when}.",
        "approved_restart": "Approved. Restarting {when}.",
        "denied": "Denied by {name}. The rollout halts at {ring}.",
        "expired": "Expired after 24 hours, counted as denied. The rollout halts at {ring}.",
        "when_now": "now",
        "when_window": "when your window opens at {opens}",
    },
    "not_reached": {
        "one": ("1 computer was offline for the whole ring. It gets the patches in a later window if it comes "
                "back online. This rollout closes {date}."),
        "many": ("{n} computers were offline for the whole ring. They get the patches in a later window if they "
                 "come back online. This rollout closes {date}."),
    },
    "never_reached": {"one": "1 computer was never reached.", "many": "{n} computers were never reached."},
}

# What an approve or deny click on a whole line answers when nothing was decided (84-03).
LINE_RESULT = {
    "not_running": "This rollout is not running, so nothing was decided.",
    "not_found": "This step was not found.",
    "stopped": "Automatic actions are stopped, so nothing was approved.",
    "already_handled": "This step was already decided.",
    "nothing_open": "Nothing is waiting for a decision here.",
    "waiting_computer": "Approved. Each computer gets it as soon as it can take it, inside your maintenance window.",
}

# ---------------------------------------------------------------- Activity rows (section 7)

ACTIVITY = {
    "canary_why": "{rollout}: canary ring, reversible patch ({patch}).",
    "canary_done": "Installed {patch}. Verified: it is no longer pending.",
    "canary_failed": "The computer did not confirm the install, so this is marked failed.",
    "not_reversible_why": "{patch} can't be reversed on {host}, so it needs your approval.",
    "not_reversible_result": "Waiting for your approval.",
    "outside_window_why": "{rollout}: canary ring.",
    "outside_window_result": ("Not sent. Your maintenance window is closed. It is tried again when the window "
                              "opens at {opens}."),
    "revert_why": "{ring} halted: {reason}.",
    "revert_done_package": "Reverted {patch} on {host}. Verified: the earlier version is installed.",
    "revert_done_update": "Uninstalled {patch}. Verified: it is no longer listed.",
    "restart_why": "{rollout}: {ring} needs a restart.",
    "restart_done": "Restarted. Warned 5 minutes before. Back online at {at}.",
    "never_touch_why": "{host} is on the never-touch list.",
    "never_touch_result": "Nothing was done.",
    "simulation": "Would have {did}. Nothing was carried out.",
}

# ---------------------------------------------------------------- short explanations the routes return

API_DETAIL = {
    "already_in_rollout": "One or more of these computers are already in another rollout.",
    "platform_tenant": "Patches are never rolled out to the platform's own server.",
    "not_halted": "This rollout is not halted.",
    "revert_running": "Wait for the revert to finish.",
    "reason_required": "A reason is required, up to 500 characters.",
    "rollout_not_found": "Rollout not found.",
    "suggestion_not_found": "Suggestion not found.",
    "rings_unreadable": "Your rollout rings couldn't be read, so no rollout can start until they load.",
}


# ---------------------------------------------------------------- builders for the shapes that vary

def canary_os_gap(os_name: str, canary_groups: list) -> str:
    """The canary-ring gap sentence: names the group when the ring has exactly one."""
    if len(canary_groups) == 1:
        return fill(CANARY_OS_GAP["one_group"], os=os_name, group=canary_groups[0])
    return fill(CANARY_OS_GAP["several_groups"], os=os_name)


def left_out(n: int, name: str) -> str:
    return forms(n, LEFT_OUT, name=name)


def offline_now(n: int) -> str:
    return forms(n, OFFLINE_NOW)


def halt_first_line(ring: str, reason: str) -> str:
    return fill(HALT_FIRST_LINE, ring=ring, reason=reason)


def not_reverted(code: str) -> str:
    """The Not reverted sentence for a reason code. An unknown code raises KeyError: a reason is never guessed."""
    return NOT_REVERTED[code]
