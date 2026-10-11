"""
Every mounted route needs an authentication dependency unless it is on the
reviewed list below (CSO run 1791310678799-7dcecc4e5cd0b8be).

router_registry includes routers without a default auth dependency, so a route
that forgets Depends(get_current_user) is silently public. This test builds the
app exactly as production does and fails on any unauthenticated route that is
not listed here. Entries on the list are public by design or check a
credential inside the handler; the list should only shrink.
Hermetic — no Mongo (routes are registered, never called).
"""
import json
import os
import subprocess
import sys

import pytest

# (method, path). "WS" marks a websocket route.
REVIEWED_UNAUTHENTICATED = frozenset({
    # Sign-in, sign-up, token refresh, password reset, MFA, passkeys, LDAP, SSO
    ("POST", "/api/auth/login"), ("POST", "/api/auth/signup"), ("POST", "/api/auth/refresh"),
    ("POST", "/api/auth/reset-password/request"), ("POST", "/api/auth/reset-password/confirm"),
    ("POST", "/api/mfa/verify"), ("POST", "/api/passkey/login/options"),
    ("POST", "/api/passkey/login/verify"), ("POST", "/api/auth/ldap/login"),
    ("POST", "/api/auth/saml/acs"), ("GET", "/api/auth/saml/login"),
    ("GET", "/api/auth/saml/metadata"), ("GET", "/api/auth/saml/slo"),
    ("POST", "/api/sso/exchange"), ("GET", "/api/sso/google/callback"),
    # Revokes whatever access token / refresh cookie the caller presents and
    # clears the cookie; must work after the access token has expired
    ("POST", "/api/auth/logout"),
    ("GET", "/api/sso/google/login"), ("GET", "/api/sso/providers"), ("GET", "/api/sso/status"),
    # Agent enrollment and self-update (registration key / public binaries)
    ("POST", "/api/agents/register"), ("GET", "/api/agents/version"),
    ("POST", "/api/tenants/lookup-key"),
    ("GET", "/api/agent-updates/latest"), ("GET", "/api/agent-updates/download/{filename}"),
    ("GET", "/api/agent-updates/checksum/{filename}"),
    ("GET", "/api/agent/install-script"), ("GET", "/api/agent/collect-evidence-script"),
    # Credential checked inside the handler (optional user, one-time token,
    # agent key/JWT, share/response/canary token, signature, OAuth state)
    ("GET", "/api/agent/download/{tenant_id}"), ("GET", "/api/agent/download/{tenant_id}/msi"),
    ("GET", "/api/agent/download/{tenant_id}/rust-binary"),
    ("GET", "/api/agent/download/{tenant_id}/rust-exe"), ("GET", "/api/agent/install/{tenant_id}"),
    ("GET", "/api/agents/{agent_id}/instructions"), ("POST", "/api/deployments/{job_id}/result"),
    ("PATCH", "/api/patches/deployment-jobs/{job_id}/progress"),
    ("POST", "/api/edr/events"), ("POST", "/api/powershell-evidence/submit"),
    ("POST", "/api/questionnaires/{qid}/responses"), ("POST", "/api/file-share/access/{token}"),
    ("POST", "/api/deception/webhook/trigger/{token_id}"), ("POST", "/api/payments/webhook/stripe"),
    ("POST", "/api/webhooks/jira/inbound"), ("POST", "/api/webhooks/zoho/inbound"),
    ("GET", "/api/saas/callback/{provider}"),
    ("GET", "/api/graphql"), ("POST", "/api/graphql"), ("WS", "/api/graphql"),
    ("WS", "/api/stream/live"),
    # Public content
    ("POST", "/api/cookie-consent/record"), ("GET", "/api/cookie-consent/session/{tenant_id}/{session_id}"),
    ("GET", "/api/public/trust/{slug}"), ("POST", "/api/public/trust/{slug}/requests"),
    ("GET", "/api/ai"), ("GET", "/api/ai/"), ("GET", "/api/ai/skills"),
    ("GET", "/api/compliance/artifacts/categories"),
    # final_endpoints' copy; system_health_endpoints registers the same path first
    # (authenticated), so this one is never reached
    ("GET", "/api/system/health"),
})


# Runs in a fresh interpreter: other tests reload authentication_service or swap
# its functions, which would break the identity checks below.
_WALK = r"""
import inspect, json, logging, re, sys
logging.disable(logging.CRITICAL)
from fastapi import FastAPI
from fastapi.routing import APIRoute, APIWebSocketRoute, _IncludedRouter
import agent_auth, api_key_auth, authentication_service as auth
from router_registry import register_all_routers

AUTH = {auth.get_current_user, auth.get_current_user_or_agent, auth.get_current_user_mfa_pending,
        agent_auth.verify_agent_key, api_key_auth.get_current_user_or_api_key}

def walk(routes, include_deps=()):
    for route in routes:
        if isinstance(route, _IncludedRouter):
            deps = include_deps + tuple(route.include_context.dependencies or ())
            for c in route.effective_candidates():
                if isinstance(c, _IncludedRouter):
                    yield from walk([c], deps)
                else:
                    path = c.starlette_route.path if c.starlette_route is not None else c.path
                    yield path, c.original_route, deps
        elif isinstance(route, (APIRoute, APIWebSocketRoute)):
            yield route.path, route, include_deps

def has_auth(dep):
    return dep.call in AUTH or any(has_auth(d) for d in dep.dependencies)

USER_AUTH = AUTH - {agent_auth.verify_agent_key}
PERM_DEP = re.compile(r"has_permission|require_permission|require_super_admin|require_role|require_admin|_require_|check_ops_permission")
# Role/permission checks in the handler body. A 403 alone doesn't count: many
# handlers only refuse a missing tenant ("Tenant context required").
PERM_BODY = re.compile(r"verify_permission\(|has_permission\(|is_super_admin\(|_is_super\(|_is_admin\(|_require_\w+\(|_check_auth\(")
# A role comparison is authorisation only if the handler can refuse: many
# handlers compare the role just to decide whether to add a tenant filter, and
# then let any signed-in user through (a viewer could delete agents that way).
ROLE_CMP = re.compile(r"[\"']role[\"'][^\n]*\)\s*(!=|==|(not\s+)?in\s)|\w*role\([^)]*\)\s*(not\s+)?in\s|role\s+(not\s+)?in\s|role\s*[!=]=")
DENIES = re.compile(r"status_code\s*=\s*(403|status\.HTTP_403)|HTTP_403_FORBIDDEN|PermissionError")

def dep_calls(dep, acc):
    acc.append(dep.call)
    for d in dep.dependencies:
        dep_calls(d, acc)
    return acc

def login_only(route, include_deps):
    calls = dep_calls(route.dependant, []) + [getattr(d, "dependency", None) for d in include_deps]
    if not any(c in USER_AUTH for c in calls):
        return False
    names = [getattr(c, "__qualname__", "") for c in calls if c is not None]
    if any(PERM_DEP.search(n) for n in names):
        return False
    try:
        body = inspect.getsource(route.endpoint).split(":", 1)[1]
    except (OSError, TypeError):
        body = ""
    return not (PERM_BODY.search(body) or (ROLE_CMP.search(body) and DENIES.search(body)))

app = FastAPI()
register_all_routers(app)
found, writes, total = set(), set(), 0
for path, route, deps in walk(app.routes):
    if not isinstance(route, (APIRoute, APIWebSocketRoute)):
        continue
    total += 1
    mutating = (getattr(route, "methods", None) or set()) & {"POST", "PUT", "PATCH", "DELETE"}
    if isinstance(route, APIRoute) and mutating and login_only(route, deps):
        writes.update((m, path) for m in mutating)
    if any(getattr(d, "dependency", None) in AUTH for d in deps) or has_auth(route.dependant):
        continue
    for method in sorted(getattr(route, "methods", None) or {"WS"}):
        found.add((method, path))
json.dump({"total": total, "unauthenticated": sorted(found), "login_only_writes": sorted(writes)}, sys.stdout)
"""


@pytest.fixture(scope="module")
def route_walk():
    backend = os.path.join(os.path.dirname(__file__), "..")
    proc = subprocess.run([sys.executable, "-c", _WALK], cwd=backend, capture_output=True,
                          text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    assert result["total"] > 1000  # guards against the walk silently covering nothing
    return result


@pytest.fixture(scope="module")
def unauthenticated_routes(route_walk):
    return {tuple(r) for r in route_walk["unauthenticated"]}


def test_no_unreviewed_unauthenticated_routes(unauthenticated_routes):
    unexpected = sorted(unauthenticated_routes - REVIEWED_UNAUTHENTICATED)
    assert unexpected == [], (
        "Routes without an auth dependency — add Depends(get_current_user) (or a "
        "permission) or, if public by design, review and list them:\n"
        + "\n".join(f"{m} {p}" for m, p in unexpected)
    )


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/stream/publish/{topic}"), ("GET", "/api/stream/metrics"),
    ("GET", "/api/system/fleet"), ("GET", "/api/system/queues"), ("GET", "/api/system/resources"),
    ("POST", "/api/training/modules"), ("POST", "/api/training/assign"),
    ("PUT", "/api/training/progress/{assignment_id}"), ("GET", "/api/training/my-training"),
    ("POST", "/api/predictive/hosts/{host_id}/acknowledge"),
    ("POST", "/api/agent-updates/build"), ("GET", "/api/agent-updates/build/{task_id}"),
    ("POST", "/api/compliance_oracle/analyze"),
    ("GET", "/api/siem/events"), ("POST", "/api/siem/ingest"), ("GET", "/api/ueba/anomalies"),
    ("GET", "/api/sustainability/metrics"), ("GET", "/api/maturity/domains"),
])
def test_previously_public_routes_now_require_auth(unauthenticated_routes, method, path):
    assert (method, path) not in unauthenticated_routes


# Data-changing routes that only need a login: each acts on the caller's own
# account or records (MFA, passkeys, API keys, to-do tasks, support threads,
# training, file shares they created) or is an AI chat open to every user. Everything
# else that changes data needs a permission.
SELF_SERVICE_WRITES = frozenset({
    ("PUT", "/api/users/me/notification-preferences"),
    # API keys act as their owner and can't exceed the owner's role
    ("POST", "/api/api-keys"), ("DELETE", "/api/api-keys/{key_id}"),
    ("POST", "/api/mfa/setup"), ("POST", "/api/mfa/verify-setup"), ("POST", "/api/mfa/disable"),
    ("POST", "/api/mfa/backup-codes/regenerate"), ("POST", "/api/mfa/step-up"),
    ("POST", "/api/passkey/register/options"), ("POST", "/api/passkey/register/verify"),
    ("DELETE", "/api/passkey/credentials/{credential_id}"),
    ("POST", "/api/tasks"), ("PATCH", "/api/tasks/{task_id}"), ("DELETE", "/api/tasks/{task_id}"),
    ("POST", "/api/support/conversations/{convo_id}/messages"),
    ("POST", "/api/support/conversations/{convo_id}/read"),
    ("PUT", "/api/training/progress/{assignment_id}"),
    ("POST", "/api/training/progress/{assignment_id}/quiz"),
    ("POST", "/api/file-share/shares"), ("DELETE", "/api/file-share/shares/{share_id}"),
    ("POST", "/api/trust-center/requests"), ("POST", "/api/experiments/{experiment_id}/track"),
    ("POST", "/api/provenance/verify"), ("POST", "/api/cissp/oracle/chat"),
    ("POST", "/api/jit/requests"),  # asking for just-in-time access; approval is separate
    ("POST", "/api/voice/transcribe"), ("POST", "/api/voice/synthesize"),
    ("POST", "/api/digital_twin/simulate"),  # read-only what-if estimate; writes nothing
})


def test_data_changing_routes_need_a_permission(route_walk):
    login_only = {tuple(r) for r in route_walk["login_only_writes"]}
    unexpected = sorted(login_only - SELF_SERVICE_WRITES)
    assert unexpected == [], (
        "Data-changing routes that only check for a login — use "
        "Depends(require_permission(...)) or, if they act only on the caller's own "
        "records, list them in SELF_SERVICE_WRITES:\n"
        + "\n".join(f"{m} {p}" for m, p in unexpected)
    )
