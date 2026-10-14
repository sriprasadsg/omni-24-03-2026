"""Mutating routes the audit middleware does not record, each with its reason (spec C5).

The middleware records every /api/ POST, PUT, PATCH and DELETE except the paths below
and agent data-plane calls (agent tokens or the tenant registration key: heartbeats,
telemetry, task results), which the agent cost meter counts instead (spec C9). Agent
enrollment (/api/agents/register) and uninstall reports are recorded. A mutating route
outside /api/ must be listed here, or tests/test_audit_parity.py fails.

Entries are "METHOD path-template" or "* path-template"; templates match FastAPI's
route paths exactly.
"""
EXEMPT = {
    "POST /api/auth/login": "recorded as explicit login.success / login.failure events (email, IP; never the password)",
    "POST /api/auth/logout": "recorded as an explicit logout event",
    "POST /api/auth/refresh": "token refresh on every page load is not a user action; the login it extends is audited",
}

# Agent-plane paths that are recorded even though agents call them.
AGENT_PATHS_RECORDED = ("/api/agents/register", "/uninstall-report")


def exempt_reason(method: str, template: str):
    return EXEMPT.get(f"{method} {template}") or EXEMPT.get(f"* {template}")


def coverage_problems(routes):
    """Problems with audit coverage for [{"methods": [...], "path": template}, ...]:
    mutating routes outside /api/ that are not exempt, and exempt entries that match no
    mounted route or have no reason."""
    problems = []
    mounted = set()
    for route in routes:
        for method in route.get("methods") or []:
            if method not in ("POST", "PUT", "PATCH", "DELETE"):
                continue
            mounted.add((method, route["path"]))
            if not route["path"].startswith("/api/") and not exempt_reason(method, route["path"]):
                problems.append(f"{method} {route['path']}: mutating route outside /api/ is neither audited nor exempt")
    for key, reason in EXEMPT.items():
        method, _, path = key.partition(" ")
        if not reason.strip():
            problems.append(f"{key}: exempt without a reason")
        if not any(p == path and (method == "*" or m == method) for m, p in mounted):
            problems.append(f"{key}: exempt entry matches no mounted mutating route")
    return problems
