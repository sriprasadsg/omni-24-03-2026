"""Spec C1 AC7: no role set may mix the tenant admin with the platform owner again.

Value: protects=cross-tenant role checks use auth_roles.platform_scope_roles() and
"403 unless admin" checks use auth_roles.tenant_admin_roles(), so the tenant role
"admin" cannot be put next to "Super Admin" by hand; fails_when=a set/list/tuple literal
in backend/*.py or backend/frameworks/*.py holds a super-admin spelling and a tenant-admin
spelling, or such a literal is unioned onto a *SUPER* set; no_claim=role checks written as
chained == comparisons, and sets built at runtime.
"""
import ast
import glob
import os

_BACKEND = os.path.join(os.path.dirname(__file__), "..")
SUPER = {"Super Admin", "super_admin", "superadmin", "platform-admin", "platform_admin", "Platform Owner",
         "platform_owner"}
TENANT_ADMIN = {"admin", "Admin", "Tenant Admin", "tenant_admin"}

# (file, assignment target or None for the whole file): reviewed on purpose.
_ALLOWED = {
    ("auth_roles.py", None),  # the canonical module: display names of tenant_admin_roles()
}


def _strings(node):
    return {e.value for e in getattr(node, "elts", []) if isinstance(e, ast.Constant) and isinstance(e.value, str)}


def _target(node, parents):
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            return node.targets[0].id
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            return node.target.id
    return None


def _mentions_super(node) -> bool:
    return any(isinstance(n, ast.Name) and "SUPER" in n.id for n in ast.walk(node))


def scan(source: str, name: str):
    tree = ast.parse(source)
    parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
    out = []
    for node in ast.walk(tree):
        hit = False
        if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
            vals = _strings(node)
            hit = bool(vals & SUPER and vals & TENANT_ADMIN)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            for lit, other in ((node.left, node.right), (node.right, node.left)):
                if isinstance(lit, (ast.Set, ast.List, ast.Tuple)) and _strings(lit) & TENANT_ADMIN \
                        and _mentions_super(other):
                    hit = True
        if hit and (name, None) not in _ALLOWED and (name, _target(node, parents)) not in _ALLOWED:
            out.append(f"{name}:{node.lineno}")
    return out


def test_no_mixed_tenant_admin_and_super_admin_role_sets():
    offenders = []
    paths = glob.glob(os.path.join(_BACKEND, "*.py")) + glob.glob(os.path.join(_BACKEND, "frameworks", "*.py"))
    for path in sorted(paths):
        with open(path, encoding="utf-8-sig") as fh:
            offenders += scan(fh.read(), os.path.basename(path))
    assert not offenders, ("role sets mixing the tenant admin with the platform owner (use "
                           "auth_roles.platform_scope_roles() or tenant_admin_roles()): " + ", ".join(offenders))


def test_scanner_flags_a_new_mixed_literal():
    assert scan('_X_ROLES = {"Super Admin", "super_admin", "admin"}\n', "x.py") == ["x.py:1"]
    assert scan('if role in ("admin", "super_admin"):\n    pass\n', "x.py") == ["x.py:1"]


def test_scanner_flags_a_union_onto_a_super_set():
    assert scan('_A = _SUPER_ROLES | {"Tenant Admin", "admin"}\n', "x.py") == ["x.py:1"]


def test_scanner_allows_pure_sets_and_the_reviewed_sites():
    assert scan('_T = {"admin", "Tenant Admin"}\n_S = {"Super Admin", "super_admin"}\n', "x.py") == []
