"""Every reader of db.notifications goes through the one audience filter (Phase 85, plan 85-31, DESK-01, CR-501).

Value: protects=CR-501 / PROH-85-21 / T-85-109: a repository-wide scan of backend/ finds every function that reads or
changes db.notifications other than by insert; every route among them calls notification_audience.reader_filter,
and the system writers and jobs sit on a named allow-list that may hold no route; fails_when=a route reads or
changes the notices without reader_filter, an allow-listed function is a route, an allow-list entry no longer
touches the collection (the list rots), or fewer than the five known user routes are found (the scan went blind);
no_claim=a collection handle copied into a variable before use, and the notice contents (the behaviour tests of
test_notification_history_audience.py and test_service_desk_notification_audience.py do that).
"""
import ast
import os

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Method names that read or change a collection other than by inserting into it.
_TOUCHING = {
    "find", "find_one", "aggregate", "count_documents", "distinct", "update_one", "update_many", "delete_one",
    "delete_many", "replace_one", "find_one_and_update", "find_one_and_delete", "find_one_and_replace", "watch",
}
_ROUTE_VERBS = {"get", "post", "put", "patch", "delete", "api_route"}

# (path relative to backend/, function name, why it may touch db.notifications without a signed-in reader)
ALLOW_LIST = [
    ("pending_agents.py", "notify_pending", "refreshes the count in the pending-agents summary notice (system writer)"),
    ("retention_service.py", "cleanup_notifications", "the retention job deletes expired notices of every tenant"),
    ("send_pending_emails.py", "send_pending_notifications", "the e-mail sender job reads unsent notices"),
]
# The user routes the scan must find (path, function name): the five routes that serve a signed-in reader.
KNOWN_ROUTES = [
    ("notification_endpoints.py", "get_notifications"),
    ("notification_endpoints.py", "mark_as_read"),
    ("notification_endpoints.py", "mark_all_as_read"),
    ("notification_endpoints.py", "delete_notification"),
    ("reporting_endpoints.py", "get_notification_history"),
]


def _is_notifications(node):
    """``x.notifications`` or ``x["notifications"]``."""
    if isinstance(node, ast.Attribute):
        return node.attr == "notifications"
    if isinstance(node, ast.Subscript):
        return isinstance(node.slice, ast.Constant) and node.slice.value == "notifications"
    return False


def _is_route(fn):
    for dec in getattr(fn, "decorator_list", []):
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in _ROUTE_VERBS:
            owner = dec.func.value
            name = owner.id if isinstance(owner, ast.Name) else getattr(owner, "attr", "")
            if name.endswith("router"):
                return True
    return False


def _own_nodes(scope):
    """The nodes of ``scope`` itself, not those of a function nested in it."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(node))


def scan_source(source, rel="<source>"):
    """[{path, name, route, filtered}] for every function of ``source`` that reads or changes db.notifications."""
    tree = ast.parse(source)
    found = []
    scopes = [(tree, "<module>")] + [(n, n.name) for n in ast.walk(tree)
                                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for scope, name in scopes:
        calls = [n for n in _own_nodes(scope) if isinstance(n, ast.Call)]
        touches = [c for c in calls if isinstance(c.func, ast.Attribute) and c.func.attr in _TOUCHING
                   and _is_notifications(c.func.value)]
        if not touches:
            continue
        filtered = any((isinstance(c.func, ast.Name) and c.func.id == "reader_filter")
                       or (isinstance(c.func, ast.Attribute) and c.func.attr == "reader_filter") for c in calls)
        found.append({"path": rel, "name": name, "route": _is_route(scope), "filtered": filtered})
    return found


def scan_backend(root=BACKEND):
    found = []
    for folder, dirs, files in os.walk(root):
        top = os.path.relpath(folder, root) == "."
        dirs[:] = [d for d in dirs if d not in ("site-packages", "node_modules", "__pycache__")
                   and not (top and (d == "tests" or d.startswith("venv")))]
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(folder, file)
                with open(path, encoding="utf-8-sig") as handle:
                    found += scan_source(handle.read(), os.path.relpath(path, root))
    return found


def problems(found, allow_list=ALLOW_LIST, known_routes=KNOWN_ROUTES):
    """What is wrong with the scan result; an empty list means every reader is accounted for."""
    allowed = {(path, name) for path, name, _ in allow_list}
    out = []
    for item in found:
        key = (item["path"], item["name"])
        if item["route"] and key in allowed:
            out.append(f"{key} is allow-listed but is a route: routes must call reader_filter")
        elif item["route"] and not item["filtered"]:
            out.append(f"route {key} reads or changes db.notifications without reader_filter")
        elif not item["route"] and key not in allowed:
            out.append(f"{key} reads or changes db.notifications and is neither a route nor on the allow-list")
    seen = {(i["path"], i["name"]) for i in found}
    out += [f"allow-list entry {k} no longer touches db.notifications" for k in sorted(allowed - seen)]
    routes = {(i["path"], i["name"]) for i in found if i["route"] and i["filtered"]}
    out += [f"known route {k} not found as a filtered route" for k in known_routes if k not in routes]
    return out


# ---------------------------------------------------------------- the repository

def test_every_notice_reader_in_the_backend_is_filtered_or_a_named_system_job():
    """protects=CR-501 / PROH-85-21 / T-85-109; fails_when=a route builds its own notice query, a new function
    touches db.notifications without being listed, or the allow-list names something that no longer does."""
    found = scan_backend()
    assert problems(found) == []
    assert sum(1 for i in found if i["route"]) >= 5, "the scan found fewer than the five known user routes"


def test_the_allow_list_gives_a_reason_for_each_entry_and_holds_no_route():
    """protects=T-85-109; fails_when=an entry has no reason or is a route."""
    assert all(len(reason) > 10 for _, _, reason in ALLOW_LIST)
    routes = {(i["path"], i["name"]) for i in scan_backend() if i["route"]}
    assert not routes & {(path, name) for path, name, _ in ALLOW_LIST}


# ---------------------------------------------------------------- the checker itself

_UNFILTERED_ROUTE = '''
@router.get("/api/notifications/other")
async def other(current_user=None):
    return await get_database().notifications.find({"tenantId": "t"}).to_list(5)
'''
_FILTERED_ROUTE = '''
@router.get("/api/notifications/other")
async def other(current_user=None):
    query = await reader_filter(current_user, "t")
    return await db["notifications"].find(query).to_list(5)
'''


def test_the_scan_fails_for_a_route_that_reads_the_notices_without_the_filter():
    """protects=T-85-109; fails_when=an unfiltered decorated route passes the check, or a filtered one fails it."""
    bad = scan_source(_UNFILTERED_ROUTE, "x.py")
    assert bad == [{"path": "x.py", "name": "other", "route": True, "filtered": False}]
    assert any("without reader_filter" in p for p in problems(bad, [], []))
    assert problems(scan_source(_FILTERED_ROUTE, "x.py"), [], []) == []


def test_the_scan_fails_for_an_allow_listed_route():
    """protects=T-85-109; fails_when=a route can hide on the allow-list."""
    found = scan_source(_FILTERED_ROUTE, "x.py")
    assert any("is a route" in p for p in problems(found, [("x.py", "other", "pretend job")], []))


def test_the_scan_fails_for_an_allow_list_entry_that_no_longer_touches_the_collection():
    """protects=T-85-109 non-rotting list; fails_when=a stale entry passes, or an insert-only writer is flagged."""
    writer = "async def notify(db):\n    await db.notifications.insert_one({})\n"
    assert scan_source(writer, "w.py") == []
    assert any("no longer touches" in p for p in problems([], [("w.py", "notify", "reason of the entry")], []))
    job = "async def sweep(db):\n    await db.notifications.delete_many({})\n"
    assert any("neither a route nor on the allow-list" in p for p in problems(scan_source(job, "j.py"), [], []))
    assert problems(scan_source(job, "j.py"), [("j.py", "sweep", "the sweep job")], []) == []
