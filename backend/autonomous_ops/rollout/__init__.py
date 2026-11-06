"""Staged patch rollouts (Phase 84 of milestone v4.3): constants shared by every rollout module.

A rollout installs chosen patches on a tenant's computers ring by ring, inside the tenant's maintenance
windows. The first (canary) ring installs on its own, one reversible patch at a time, through
``gate.decide`` / ``gate.execute``; every later step waits for a person or a clean health check. Nothing
in this package writes an agent queue: all agent work goes through the gate, which owns the stop, the
limits and the decision ledger.

This module is stdlib only so any module (tests included) can import it. Prose says "revert" or "put
back" (copy gate rule, ACTV-08); the identifier ``rollback_patches`` is only ever a registry command.
"""
from datetime import timedelta

DISPATCHER_NAME = "patch_rollout"
COMMAND_INSTALL = "install_patches"
COMMAND_UNDO = "rollback_patches"
LOCK_NAME = "patch_rollout_controller"
CAPABILITY = "patch_installer"
SYSTEM_ACTOR = {"id": "autonomous_ops", "name": "Rollout"}

# Rollout and ring and host states.
ROLLOUT_STATUSES = ("running", "halted", "completed", "cancelled")
ACTIVE_STATUSES = ("running", "halted")
RING_STATES = ("not_started", "waiting_for_window", "waiting_for_approval", "installing", "restarting",
               "soaking", "checking_health", "passed", "halted", "reverted", "cancelled")
HOST_STATES = ("waiting", "installing", "installed", "restarting", "healthy", "failed", "reverting",
               "reverted", "not_reverted", "not_reached", "would_install", "would_restart")
LINES = ("install", "reboot", "revert_reboot")

# Ring defaults (D-10) and limits.
DEFAULT_SOAK_HOURS = 24
DEFAULT_FAIL_PCT = 10
DEFAULT_MIN_SAMPLE = 10
MIN_RINGS = 2
MAX_RINGS = 4
MAX_HOSTS_PER_ROLLOUT = 500
MAX_ATTEMPTS = 3                  # an install that was not delivered is tried again this many times in all

# Restart and health timing (D-08, D-17).
REBOOT_DELAY_SECONDS = 300
REBOOT_REASON = "Restarting in 5 minutes for updates"
NEW_BOOT_WAIT = timedelta(minutes=30)
BOOT_TOLERANCE_SECONDS = 120
INVENTORY_FRESH_AFTER = timedelta(minutes=5)
SERVICE_SETTLE = timedelta(seconds=120)
NOT_REACHED_GRACE = timedelta(days=7)

# The agent tokens a rollout step needs (heartbeat ``meta.response_actions.tokens``).
TOKEN_REVERSIBLE = "patch_reversible_check"
TOKEN_REVERT_BY_JOB = "patch_revert_by_job"
TOKEN_SERVICE_STATE = "service_state"
TOKEN_REBOOT = "reboot_host"

# D-06: a package whose name starts with one of these usually needs a restart, so it never installs on
# its own (research A9: assumed content, reviewed with the user).
REBOOT_NEEDING_PACKAGES = (
    "linux-image", "linux-headers", "linux-modules", "kernel", "glibc", "libc6", "systemd", "dbus",
    "linux-firmware", "microcode", "intel-microcode", "amd64-microcode", "grub",
)


def needs_restart_by_name(patch_id: str) -> bool:
    """True when a Linux package name is one of the usually-restart-needing families (D-06)."""
    name = str(patch_id or "").strip().lower()
    return any(name.startswith(prefix) for prefix in REBOOT_NEEDING_PACKAGES)
