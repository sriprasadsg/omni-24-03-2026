"""Autonomous Ops: the safety core (Phase 81 of milestone v4.3).

Every autonomous action passes one decision function (``gate.decide``, GATE-03) and is
written to the decision ledger (``autonomy_actions``) before anything is dispatched
(GATE-07). This package never uses the ambient tenant ContextVar: every read and write
goes through the raw Mongo handle with an explicit tenantId. Constants here are stdlib only
so any module (including tests and the retention checks) can import them.

Limits cite the locked decisions: D-16 (approvals expire after 24 hours), D-17 (one
automatic decision touches exactly one host), D-18 (circuit breaker: 3 bad automatic
actions in 24 hours), D-20 (20 automatic actions per rolling hour).
"""
from datetime import timedelta

# Levels (GATE-01). Ordinal: off < suggest < undoable_auto.
LEVELS = ("off", "suggest", "undoable_auto")
LEVEL_RANK = {"off": 0, "suggest": 1, "undoable_auto": 2}
DEFAULT_LEVEL = "undoable_auto"

# The Platform tenant is never eligible in v4.3 (D-04).
PLATFORM_TENANT_ID = "platform-admin"

# Permissions (D-05, D-07).
SCREEN_PERMISSION = "view:autonomous_ops"
MANAGE_PERMISSION = "manage:autonomous_ops"
CONTROL_PERMISSION = "control:autonomous_ops"
PLATFORM_CONTROL_PERMISSION = "control:platform_autonomous_ops"

# Decision records sit outside every generic retention path (GATE-07). Anything that
# deletes documents must leave these collections alone and keep decisions at least
# DECISION_RETENTION_FLOOR_DAYS (matching audit_ledger's 365).
PROTECTED_COLLECTIONS = frozenset({
    "autonomy_actions", "autonomy_settings", "autonomy_never_touch",
    "autonomy_golive_checks",     # the recorded go-live evidence (Phase 86, D-14): never deleted, only added to
})
DECISION_RETENTION_FLOOR_DAYS = 365

# Safety limits.
APPROVAL_TTL = timedelta(hours=24)          # D-16
HOST_CAP = 1                                # D-17
RATE_LIMIT_PER_WINDOW = 20                  # D-20
RATE_LIMIT_WINDOW = timedelta(minutes=60)   # D-20 (rolling window)
BREAKER_THRESHOLD = 3                       # D-18
BREAKER_WINDOW = timedelta(hours=24)        # D-18
COOLDOWN = timedelta(hours=24)

# The marker on every instruction and response task the gate writes. Only gate.py uses it.
STAMP_SOURCE = "autonomous_ops"

# Ledger states.
OPEN_STATES = ("suggested", "awaiting_approval", "approved", "dispatching")
TERMINAL_STATES = ("shadow", "executed", "verified", "failed", "rolled_back", "undone",
                   "denied", "expired", "cancelled_by_stop", "refused")

# The Activity buckets. Control rows (kind "control", state "recorded") belong to "all" only.
BUCKET_STATES = {
    "pending": ("awaiting_approval", "approved", "dispatching"),
    "done": ("executed", "verified"),
    "undone": ("undone", "rolled_back"),
    "failed": ("failed",),
    "refused": ("refused", "denied", "expired", "cancelled_by_stop"),
    "suggested": ("suggested",),
    "simulation": ("shadow",),
}

# What an instruction row written for an action can be (the stamp's `kind`).
INSTRUCTION_KINDS = ("action", "probe", "compensate", "undo")
# D-12: putting things back still works during a stop.
STOP_EXEMPT_KINDS = ("undo", "compensate")
