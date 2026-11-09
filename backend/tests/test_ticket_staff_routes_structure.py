"""Structure test of the /api/tickets API (Phase 85 gap G-85-4, plan 85-35, WR-502): every route of the five ticket
routers is classified, so a future route cannot skip the staff rules. No database; it reads the route modules'
source with ``ast`` and the routers' dependencies at runtime.

Value: protects=WR-502 / UD-2 / T-85-125: every route is viewer-guarded ({ticket_id} in the path and the router
carries ``ticket_access.ticket_viewer``), staff-only (``manage:tickets`` in its signature or a ``_staff_only`` call,
also through the helper it delegates to), own-scoped (``tickets_scope`` or the reports' ``_scope``) or on the
reasoned open list below (or manage:settings administration); the fifteen named staff routes keep their staff
check; the five modules are the only ones that declare the /api/tickets prefix; fails_when=a route is none of
these, a named staff route loses its check or is renamed away, a router with a {ticket_id} route loses the viewer
guard, or a sixth backend module declares the prefix; no_claim=what each route does once it is let through (the
behavior tests of test_ticket_staff_actions.py, test_service_desk_staff_routes.py and test_service_desk_reporter_ticket.py).

When a route that is neither of these is added on purpose, classify it here: a staff route joins STAFF_ROUTES, a
route open to every requester joins OPEN_ROUTES with the reason it is safe.
"""
import ast
import importlib
import os
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKEND = Path(__file__).resolve().parent.parent
PREFIX = "/api/tickets"
ROUTER_MODULES = ("tickets_endpoints", "tickets_workflow_endpoints", "tickets_config_endpoints",
                  "ticket_reports_endpoints", "service_desk_endpoints")

# The routes only ticket staff (manage:tickets) may use. Each must show the check in its own signature or reach a
# _staff_only call; the three draft routes keep view:dashboard in the signature and refuse inside _staff_only so the
# reporter reads the desk's staff_only sentence (A-85-G31).
STAFF_ROUTES = ("bulk_update", "update_ticket", "add_link", "remove_link", "log_work", "delete_attachment",
                "approve_ticket", "reject_ticket", "escalate_ticket", "merge_ticket", "add_watcher", "remove_watcher",
                "send_draft", "edit_and_send_draft", "discard_draft")

# Routes with no {ticket_id} that are open to every signed-in requester (view:dashboard), each with why that is safe.
OPEN_ROUTES = {
    "create_ticket": "every requester raises tickets; the reporter is set from the caller and the response is the requester projection",
    "list_templates": "the ticket templates are the same for everybody who raises a ticket and hold no ticket data",
    "get_field_schema": "the custom field definitions the new-ticket form needs; no ticket data",
}

_HTTP = {"get", "post", "put", "patch", "delete"}
_PERMISSION_CALLS = {"has_permission", "require_permission"}
_SCOPE_CALLS = {"tickets_scope", "_scope"}


class Route(NamedTuple):
    name: str
    method: str
    path: str
    permissions: Set[str]      # permission strings of has_permission / require_permission in decorator and signature
    called: Set[str]           # names called by the route and, transitively, by the module-level helpers it calls


def _call_name(node: ast.AST) -> Optional[str]:
    func = node.func if isinstance(node, ast.Call) else None
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _permission_of(arg: ast.AST) -> Optional[str]:
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if (isinstance(arg, ast.Attribute) and arg.attr == "TICKET_STAFF") or (isinstance(arg, ast.Name) and arg.id == "TICKET_STAFF"):
        return "manage:tickets"
    return None


def _permissions(nodes: List[ast.AST]) -> Set[str]:
    found: Set[str] = set()
    for root in nodes:
        for node in ast.walk(root):
            if _call_name(node) in _PERMISSION_CALLS and node.args:
                permission = _permission_of(node.args[0])
                if permission:
                    found.add(permission)
    return found


def _called(func: ast.AST, helpers: Dict[str, ast.AST], seen: Optional[Set[str]] = None) -> Set[str]:
    seen = set() if seen is None else seen
    names: Set[str] = set()
    for node in ast.walk(func):
        name = _call_name(node)
        if name:
            names.add(name)
            if name in helpers and name not in seen:
                seen.add(name)
                names |= _called(helpers[name], helpers, seen)
    return names


def routes_of(source: str) -> List[Route]:
    """The ``@router.<method>(path)`` routes of a module's source."""
    tree = ast.parse(source)
    helpers = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    found: List[Route] = []
    for func in helpers.values():
        for dec in func.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in _HTTP
                    and isinstance(dec.func.value, ast.Name) and dec.func.value.id == "router"):
                continue
            path = dec.args[0].value if dec.args and isinstance(dec.args[0], ast.Constant) else "<dynamic>"
            signature = [func.args] if func.args else []
            found.append(Route(func.name, dec.func.attr.upper(), path, _permissions([dec] + signature),
                               _called(func, helpers)))
    return found


def is_staff_only(route: Route) -> bool:
    return "manage:tickets" in route.permissions or "_staff_only" in route.called


def classify(route: Route, router_guarded: bool, open_routes=OPEN_ROUTES) -> Optional[str]:
    """How the route is closed to people who are not allowed, or None when nothing closes it."""
    if "{ticket_id}" in route.path and router_guarded:
        return "viewer-guarded"
    if is_staff_only(route):
        return "staff-only"
    if route.called & _SCOPE_CALLS:
        return "own-scoped"
    if route.name in open_routes or "manage:settings" in route.permissions:
        return "open"
    return None


def has_viewer_guard(router) -> bool:
    return any(getattr(dep.dependency, "__qualname__", "").startswith("ticket_viewer.") for dep in router.dependencies)


def declaring_modules(root: Path) -> Set[str]:
    """Paths (relative to ``root``) of the .py files with a call whose ``prefix`` keyword is the constant /api/tickets
    (APIRouter or include_router). Skips tests, the virtual environments and vendored directories."""
    found: Set[str] = set()
    for folder, dirs, files in os.walk(root):
        top = Path(folder) == root
        dirs[:] = [d for d in dirs if d not in {"site-packages", "node_modules", "__pycache__"}
                   and not (top and (d == "tests" or d.startswith("venv")))]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = Path(folder) / name
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                continue
            if PREFIX not in text:
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and any(
                        kw.arg == "prefix" and isinstance(kw.value, ast.Constant) and kw.value.value == PREFIX
                        for kw in node.keywords):
                    found.add(path.relative_to(root).as_posix())
                    break
    return found


def _load():
    """{module name: (router, routes)} of the five ticket routers."""
    loaded = {}
    for name in ROUTER_MODULES:
        module = importlib.import_module(name)
        loaded[name] = (module.router, routes_of(Path(module.__file__).read_text(encoding="utf-8-sig")))
    return loaded


def test_the_five_modules_are_the_only_ones_declaring_the_tickets_prefix():
    """protects=T-85-125 a sixth router under /api/tickets would skip the viewer guard; fails_when=the set of
    modules differs from the five."""
    assert declaring_modules(BACKEND) == {f"{name}.py" for name in ROUTER_MODULES}
    for name, (router, routes) in _load().items():
        assert router.prefix == PREFIX, name
        assert routes, f"{name}: no route was read, the test would pass without checking anything"


def test_every_router_with_a_ticket_id_route_carries_the_viewer_guard():
    """protects=WR-502 / PROH-85-23; fails_when=a router with a {ticket_id} route has no ticket_viewer
    dependency (ticket_reports_endpoints has no such route and needs none)."""
    for name, (router, routes) in _load().items():
        if any("{ticket_id}" in route.path for route in routes):
            assert has_viewer_guard(router), f"{name} has a {{ticket_id}} route but no ticket_viewer dependency"


def test_every_ticket_route_is_classified():
    """protects=WR-502 / UD-2 / T-85-125; fails_when=a route is not viewer-guarded, staff-only, own-scoped, on
    the open list or manage:settings administration; the message names the module and the route."""
    unclassified = []
    for name, (router, routes) in _load().items():
        guarded = has_viewer_guard(router)
        unclassified += [f"{name}.{r.name} ({r.method} {r.path})" for r in routes if classify(r, guarded) is None]
    assert not unclassified, f"unclassified ticket routes, add the staff or scope rule or list them with a reason: {unclassified}"


def test_the_named_staff_routes_keep_their_staff_check():
    """protects=WR-502 / UD-2; fails_when=one of the fifteen staff routes is missing, appears twice, or lost
    manage:tickets in its signature (and its _staff_only call)."""
    seen: Dict[str, List[str]] = {}
    for name, (_, routes) in _load().items():
        for route in routes:
            if route.name in STAFF_ROUTES:
                seen.setdefault(route.name, []).append(f"{name}:{is_staff_only(route)}")
    assert sorted(seen) == sorted(STAFF_ROUTES), f"missing or renamed staff routes: {set(STAFF_ROUTES) ^ set(seen)}"
    assert all(len(places) == 1 for places in seen.values()), seen
    lost = [places[0] for places in seen.values() if places[0].endswith(":False")]
    assert not lost, f"staff routes without a staff check: {lost}"


def test_the_open_list_names_real_routes_without_a_ticket_id():
    """protects=T-85-125 a stale or too broad open list; fails_when=an entry names no route or a {ticket_id} route."""
    everything = {r.name: r for _, routes in _load().values() for r in routes}
    for name in OPEN_ROUTES:
        assert name in everything, f"{name} is on the open list but is not a route"
        assert "{ticket_id}" not in everything[name].path, f"{name} has a ticket id and belongs under the viewer guard"
        assert OPEN_ROUTES[name].strip()


# ---------------------------------------------------------------- the test itself catches what it should

_UNKNOWN = '''
router = APIRouter(prefix="/api/tickets")
@router.get("/export-everything")
async def export_everything(current_user = Depends(rbac_service.has_permission("view:dashboard"))):
    return []
'''
_WEAKENED = '''
router = APIRouter(prefix="/api/tickets")
@router.post("/{ticket_id}/approve")
async def approve_ticket(ticket_id: str, current_user = Depends(rbac_service.has_permission("view:dashboard"))):
    return {}
'''
_DELEGATING = '''
router = APIRouter(prefix="/api/tickets")
async def _act(user):
    await _staff_only(user)
@router.post("/{ticket_id}/drafts/send")
async def send_draft(ticket_id: str, current_user = Depends(rbac_service.has_permission("view:dashboard"))):
    return await _act(current_user)
@router.get("/mine")
async def mine(current_user = Depends(rbac_service.has_permission("view:dashboard"))):
    return await ticket_access.tickets_scope(current_user)
'''


def test_a_route_that_is_none_of_the_classes_is_found():
    """protects=T-85-125 the classifier itself; fails_when=an unknown route passes as classified."""
    [route] = routes_of(_UNKNOWN)
    assert classify(route, router_guarded=True) is None


def test_a_staff_route_without_its_check_is_found_and_a_delegated_check_counts():
    """protects=WR-502 the classifier itself; fails_when=a staff route with only view:dashboard counts as staff-only,
    or the check reached through a helper does not."""
    [weak] = routes_of(_WEAKENED)
    assert not is_staff_only(weak)
    send, mine = routes_of(_DELEGATING)
    assert is_staff_only(send) and classify(mine, router_guarded=True) == "own-scoped"


def test_a_sixth_module_with_the_prefix_is_found(tmp_path):
    """protects=T-85-125 the scan itself; fails_when=a module with the prefix is missed, or an excluded directory
    (tests, venv*) is read."""
    (tmp_path / "extra_endpoints.py").write_text('router = APIRouter(prefix="/api/tickets")\n', encoding="utf-8-sig")
    (tmp_path / "other.py").write_text('router = APIRouter(prefix="/api/other")\n')
    for skipped in ("tests", "venv311", "pkg/site-packages"):
        (tmp_path / skipped).mkdir(parents=True)
        (tmp_path / skipped / "x.py").write_text('router = APIRouter(prefix="/api/tickets")\n')
    (tmp_path / "service_desk").mkdir()
    (tmp_path / "service_desk" / "nested.py").write_text('app.include_router(r, prefix="/api/tickets")\n')
    assert declaring_modules(tmp_path) == {"extra_endpoints.py", "service_desk/nested.py"}
