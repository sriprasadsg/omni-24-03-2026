"""
Agent endpoints aggregator.
All routes are defined in the sub-modules below; each sub-module carries the
/api/agents prefix so this aggregator uses no prefix of its own.
router_registry.py continues to import a single `router` with no changes.
"""
from fastapi import APIRouter

from agent_registry_endpoints import router as _registry
from agent_core_endpoints import router as _core
from agent_tasks_endpoints import router as _tasks
from agent_approval_endpoints import router as _approvals
from agent_telemetry_endpoints import router as _telemetry
from agent_heartbeat_endpoints import router as _heartbeat
from agent_security_endpoints import router as _security
from agent_uninstall_endpoints import router as _uninstall
from pending_agent_endpoints import router as _pending

router = APIRouter()
router.include_router(_pending)  # static /pending paths first, before any /{agent_id} route
router.include_router(_registry)
router.include_router(_core)
router.include_router(_tasks)
router.include_router(_approvals)
router.include_router(_telemetry)
router.include_router(_heartbeat)
router.include_router(_security)
router.include_router(_uninstall)

# Re-exported for router_registry.py's global /api/tasks/{task_id} alias
from agent_tasks_endpoints import get_task_status  # noqa: F401

__all__ = ["router", "get_task_status"]
