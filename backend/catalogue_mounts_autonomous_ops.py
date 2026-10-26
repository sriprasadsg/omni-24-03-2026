"""Autonomous Ops catalogue mount (Phase 81, plan 81-09): the tenant router /api/autonomous-ops.

Reads need ``view:autonomous_ops`` (or its manage twin); writes need ``manage:autonomous_ops`` or
``control:autonomous_ops``. Each write route then asks for the exact permission it needs through its
own ``_require_*`` dependency (autonomous_ops_endpoints). The guard authenticates through
``get_current_user_or_api_key`` because an API key may read the status and activity and press a stop
(D-10); the routes that must never run on a key refuse it themselves.

The platform router (/api/platform/autonomous-ops) is outside every catalogue prefix and carries its
own ``_require_platform_autonomy_control`` dependency instead.

Read and write strings mirror ``shared/catalogue-access.json``; ``test_catalogue_slice_autonomous_ops``
fails when the two drift.
"""
from api_key_auth import get_current_user_or_api_key
from catalogue_guards import catalogue_guard

__all__ = ["AUTONOMOUS_OPS_GUARD", "MOUNTS"]

AUTONOMOUS_OPS_GUARD = catalogue_guard(
    "autonomousOps",
    read=("view:autonomous_ops",),
    write=("manage:autonomous_ops", "control:autonomous_ops"),
    auth=get_current_user_or_api_key,
)

MOUNTS = {
    ("autonomous_ops_endpoints", "router"): AUTONOMOUS_OPS_GUARD,
}
