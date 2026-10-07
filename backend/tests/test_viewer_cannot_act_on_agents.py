"""
Read-only users must not change agents or send them work. These routes used to
check only for a login and compared the caller's role just to decide whether to
add a tenant filter, so a viewer could delete agents, switch off their
capabilities, push patches or software, run SOAR playbooks, start swarm
missions and queue arbitrary agent instructions (e.g. uninstall software or
kill processes on every endpoint in the tenant).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth_types import TokenData
from authentication_service import get_current_user, get_current_user_or_agent

AGENT = "agent-1"
ROUTES = [
    ("DELETE", f"/api/agents/{AGENT}", None),
    ("PUT", f"/api/agents/{AGENT}", {"capabilities": []}),
    ("PUT", f"/api/agents/{AGENT}/link", {"assetId": "asset-1"}),
    ("POST", "/api/agent/deploy", {"agentIds": [AGENT], "action": "uninstall_software:edr"}),
    ("POST", "/api/patches/apply-os-patches", {"agent_id": AGENT, "patch_ids": ["KB1"]}),
    ("POST", "/api/patches/apply-software-update", {"agent_id": AGENT, "package_name": "x", "pkg_type": "apt"}),
    ("POST", "/api/patches/bulk-apply-software-update", {"updates": [{"agent_id": AGENT, "package_name": "x", "pkg_type": "apt"}]}),
    ("POST", "/api/soar/playbooks/pb-1/execute", {}),
    ("POST", f"/api/agents/{AGENT}/capabilities", {"enable": [], "disable": ["fim"]}),
    ("POST", f"/api/agents/{AGENT}/capabilities/fim/data", {"x": 1}),
    ("POST", "/api/jobs/job-1/cancel", None),
    ("POST", "/api/compliance/collect-all", None),
    ("POST", "/api/swarm/start", {"goal": "patch everything", "priority": "high"}),
    ("POST", "/api/webhooks/wh-1/test", None),
    ("POST", f"/api/agents/{AGENT}/metrics", {"cpu_percent": 1.0, "memory_percent": 1.0}),
    ("POST", "/api/response/tasks/task-1/feedback", {"success": True}),
]


def _app(user):
    import agent_endpoints, agent_download_endpoints, patch_endpoints, soar_endpoints
    import capability_endpoints, jobs_endpoints, compliance_scans_endpoints, swarm_endpoints
    import webhook_endpoints, agent_metrics_endpoints, response_endpoints
    app = FastAPI()
    for mod in (agent_endpoints, agent_download_endpoints, patch_endpoints,
                capability_endpoints, jobs_endpoints, compliance_scans_endpoints, swarm_endpoints,
                webhook_endpoints, agent_metrics_endpoints, response_endpoints):
        app.include_router(mod.router)
    app.include_router(soar_endpoints.router, prefix="/api/soar")  # as router_registry mounts it
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_or_agent] = lambda: user
    return app


@pytest.fixture
def no_custom_roles():
    # Built-in role defaults only: the tenant has no custom role documents.
    roles_db = MagicMock()
    roles_db.roles.find_one = AsyncMock(return_value=None)
    with patch("rbac_utils.get_database", return_value=roles_db), \
         patch("rbac_service.rbac_service.get_user_permissions", AsyncMock(return_value=[])):
        yield


@pytest.mark.parametrize("method,path,body", ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES])
def test_viewer_is_refused(method, path, body, no_custom_roles):
    viewer = TokenData(username="viewer@t1.test", role="viewer", tenant_id="t1")
    with patch("database.get_database", return_value=MagicMock()):
        r = TestClient(_app(viewer)).request(method, path, json=body)
    assert r.status_code == 403, f"{method} {path} -> {r.status_code} {r.text[:200]}"


def test_agent_cannot_report_metrics_for_another_agent(no_custom_roles):
    agent = TokenData(username="agent-other", role="agent", tenant_id="t1")
    r = TestClient(_app(agent)).post(f"/api/agents/{AGENT}/metrics", json={"cpu_percent": 1.0, "memory_percent": 1.0})
    assert r.status_code == 403
