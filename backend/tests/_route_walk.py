"""Shared route walker for the auth baseline and the catalogue parity tests (Phase 76, D-05).

Walks the mounted FastAPI app and reports, per route, its catalogue tags, exemption
marker, auth class (public, agent, agent_capable, user) and whether a known guard is
present. The real app is walked in a fresh interpreter: other tests reload
``authentication_service`` or swap its functions, which would break the identity
checks below. Synthetic apps are walked in-process with :func:`walk_app`.

Nothing here imports backend modules at import time, so the child interpreter can load
this file before the app exists. Hermetic: no Mongo is reached (routes are registered,
never called) and the child points the database at an unroutable port and a
throwaway name.
"""
from __future__ import annotations

import functools
import inspect
import json
import logging
import os
import re
import subprocess
import sys
from typing import Any, Dict, Iterable, List

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

PERM_DEP = re.compile(r"has_permission|require_permission|require_super_admin|require_role|require_admin|_require_|check_ops_permission")
# Role/permission checks in the handler body. A 403 alone doesn't count: many
# handlers only refuse a missing tenant ("Tenant context required").
PERM_BODY = re.compile(r"verify_permission\(|has_permission\(|is_super_admin\(|_is_super\(|_is_admin\(|_require_\w+\(|_check_auth\(")
# A role comparison is authorisation only if the handler can refuse: many
# handlers compare the role just to decide whether to add a tenant filter, and
# then let any signed-in user through (a viewer could delete agents that way).
ROLE_CMP = re.compile(r"[\"']role[\"'][^\n]*\)\s*(!=|==|(not\s+)?in\s)|\w*role\([^)]*\)\s*(not\s+)?in\s|role\s+(not\s+)?in\s|role\s*[!=]=")
DENIES = re.compile(r"status_code\s*=\s*(403|status\.HTTP_403)|HTTP_403_FORBIDDEN|PermissionError")


def throwaway_env() -> Dict[str, str]:
    """Environment for a child interpreter that must never reach the live database."""
    env = dict(os.environ)
    env.update({
        "MONGODB_URL": "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=300",
        "MONGO_URI": "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=300",
        "MONGODB_DB_NAME": "catalogue_probe_throwaway",
        "ENVIRONMENT": "test",
    })
    return env


def _walk_routes(routes, include_deps=()):
    from fastapi.routing import APIRoute, APIWebSocketRoute, _IncludedRouter
    for route in routes:
        if isinstance(route, _IncludedRouter):
            deps = include_deps + tuple(route.include_context.dependencies or ())
            for c in route.effective_candidates():
                if isinstance(c, _IncludedRouter):
                    yield from _walk_routes([c], deps)
                else:
                    path = c.starlette_route.path if c.starlette_route is not None else c.path
                    yield path, c.original_route, deps
        elif isinstance(route, (APIRoute, APIWebSocketRoute)):
            yield route.path, route, include_deps


def walk_app(app) -> Dict[str, Any]:
    """Walk *app*; returns total, unauthenticated, login_only_writes and per-route ``routes``."""
    from fastapi.dependencies.utils import get_dependant
    from fastapi.routing import APIRoute, APIWebSocketRoute
    import agent_auth
    import api_key_auth
    import authentication_service as auth

    AUTH = {auth.get_current_user, auth.get_current_user_or_agent, auth.get_current_user_mfa_pending,
            agent_auth.verify_agent_key, api_key_auth.get_current_user_or_api_key}
    USER_AUTH = AUTH - {agent_auth.verify_agent_key}

    def dep_calls(dep, acc):
        acc.append(dep.call)
        for d in dep.dependencies:
            dep_calls(d, acc)
        return acc

    include_cache: Dict[Any, List[Any]] = {}

    def include_calls(call) -> List[Any]:
        """Every callable reachable from an include-level dependency (itself included)."""
        if call not in include_cache:
            try:
                include_cache[call] = dep_calls(get_dependant(path="/", call=call), [])
            except Exception:
                include_cache[call] = [call]
        return include_cache[call]

    def all_calls(route, include_deps) -> List[Any]:
        calls = dep_calls(route.dependant, [])
        for d in include_deps:
            call = getattr(d, "dependency", None)
            if call is not None:
                calls.extend(include_calls(call))
        return [c for c in calls if c is not None]

    def login_only(route, include_deps) -> bool:
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

    found, writes, records, total = set(), set(), [], 0
    for path, route, deps in _walk_routes(app.routes):
        if not isinstance(route, (APIRoute, APIWebSocketRoute)):
            continue
        total += 1
        calls = all_calls(route, deps)
        mutating = (getattr(route, "methods", None) or set()) & {"POST", "PUT", "PATCH", "DELETE"}
        if isinstance(route, APIRoute) and mutating and login_only(route, deps):
            writes.update((m, path) for m in mutating)
        methods = sorted(getattr(route, "methods", None) or {"WS"})
        has_auth = any(c in AUTH for c in calls)
        if not has_auth:
            found.update((m, path) for m in methods)
        if not has_auth:
            klass = "public"
        elif auth.get_current_user_or_agent in calls:
            klass = "agent_capable"
        elif not any(c in USER_AUTH for c in calls):
            klass = "agent"
        else:
            klass = "user"
        tags = [dict(c.__catalogue_guard__) for c in calls if hasattr(c, "__catalogue_guard__")]
        reasons = [c.__catalogue_exempt__ for c in calls if hasattr(c, "__catalogue_exempt__")]
        records.append({
            "methods": methods,
            "path": path,
            "module": getattr(getattr(route, "endpoint", None), "__module__", None),
            "auth": klass,
            "tags": tags,
            "exempt": reasons[0] if reasons else None,
            "known_guard": any(PERM_DEP.search(getattr(c, "__qualname__", "")) for c in calls),
        })
    return {
        "total": total,
        "unauthenticated": sorted(found),
        "login_only_writes": sorted(writes),
        "routes": records,
    }


def main() -> None:
    """Build the real app exactly as production does and print the walk as JSON."""
    logging.disable(logging.CRITICAL)
    from fastapi import FastAPI
    from router_registry import register_all_routers
    app = FastAPI()
    register_all_routers(app)
    json.dump(walk_app(app), sys.stdout)


def _run_child(code: str, args: Iterable[str] = ()) -> str:
    proc = subprocess.run([sys.executable, "-c", code, *args], cwd=BACKEND_DIR, env=throwaway_env(),
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return proc.stdout.strip().splitlines()[-1]


@functools.lru_cache(maxsize=None)
def run_real_app_walk() -> Dict[str, Any]:
    """Walk of the real mounted app, shared by every test module in one pytest session."""
    code = "import sys; sys.path.insert(0, sys.argv[1]); from tests._route_walk import main; main()"
    result = json.loads(_run_child(code, [BACKEND_DIR]))
    assert result["total"] > 1000  # guards against the walk silently covering nothing
    return result


_PROBE = r"""
import json, logging, sys
logging.disable(logging.CRITICAL)
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api_key_auth
import authentication_service as auth
from auth_types import TokenData
from router_registry import register_all_routers
import tenant_features

# Spec C6: the child has no database, so the tenant's feature switches come from the
# case ("tenant_features", default every feature on).
_switches = {"list": [tenant_features.ALL_FEATURES]}

async def _case_switches(tenant_id, get_db):
    return list(_switches["list"])

tenant_features.enabled_features = _case_switches

app = FastAPI()
register_all_routers(app)
out = []
for case in json.loads(sys.argv[1]):
    _switches["list"] = case.get("tenant_features", [tenant_features.ALL_FEATURES])
    api_key = case.get("auth", "session") == "api_key"
    td = TokenData(username="probe@example.com", role=case["role"], tenant_id=case["tenant_id"],
                   scopes=case.get("scopes"), auth_source="api_key" if api_key else "session")
    app.dependency_overrides.clear()
    target = api_key_auth.get_current_user_or_api_key if api_key else auth.get_current_user
    app.dependency_overrides[target] = lambda td=td: td
    client = TestClient(app, raise_server_exceptions=False)
    out.append(client.request(case["method"], case["path"]).status_code)
json.dump(out, sys.stdout)
"""


def probe_real_app(cases: List[Dict[str, Any]]) -> List[int]:
    """Status code per case on the real app (fresh interpreter, throwaway Mongo env).

    Case keys: method, path, role, tenant_id, scopes (optional), auth ("session" or "api_key"),
    tenant_features (optional: the tenant's feature-switch list, spec C6; default every feature on).
    """
    raw = subprocess.run([sys.executable, "-c", _PROBE, json.dumps(cases)], cwd=BACKEND_DIR,
                         env=throwaway_env(), capture_output=True, text=True, timeout=300)
    assert raw.returncode == 0, raw.stderr[-2000:]
    return json.loads(raw.stdout.strip().splitlines()[-1])
