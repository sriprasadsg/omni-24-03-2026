"""Phase 88 plan 04: no module but plan_service writes a tenant's subscriptionTier (AST drift guard).

Value: protects=every plan change is audited, announced and seat-checked because change_plan is the only
writer; fails_when=a new module sets subscriptionTier through a $set, a $setOnInsert or a subscript
assignment (the scanner reads source only; a document literal, a filter and a projection are not writes);
no_claim=the runtime behavior of change_plan (test_plan_change.py) and writes built by a variable key.
"""
import ast
import os

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
PLAN_WRITER_ALLOWLIST = {"plan_service.py"}
# An operator's one-off script, run by hand from deploy-ubuntu.sh and run-on-ubuntu.sh (never imported by the app):
# it sets every tenant to Enterprise with all features and is not a plan change a person makes in the product.
_SKIP_FILES = {"unlock_enterprise_features.py"}
_FIELD = "subscriptionTier"
_UPDATE_OPERATORS = ("$set", "$setOnInsert")


def _str_key(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def writes_subscription_tier(source: str) -> bool:
    """True when the source sets subscriptionTier: a {"$set" | "$setOnInsert": {"subscriptionTier": x}} update, or an
    assignment to a subscript whose key is the constant "subscriptionTier" (update_data["subscriptionTier"] = x).
    An insert document literal, a filter and a projection are reads or creations, not changes."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if _str_key(key) in _UPDATE_OPERATORS and isinstance(value, ast.Dict):
                    if any(_str_key(k) == _FIELD for k in value.keys):
                        return True
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Subscript) and _str_key(target.slice) == _FIELD:
                    return True
    return False


def modules(root: str) -> set:
    """Backend modules are flat files in backend/ (tests, scripts and migrations live in sub-folders, and the
    folder also holds virtualenvs that must not be walked), so only its top level is scanned."""
    found = set()
    for fn in sorted(os.listdir(root)):
        path = os.path.join(root, fn)
        if not fn.endswith(".py") or fn in _SKIP_FILES or not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            try:
                if writes_subscription_tier(fh.read()):
                    found.add(fn)
            except (SyntaxError, ValueError):
                continue
    return found


def test_only_plan_service_writes_subscription_tier():
    found = modules(BACKEND_DIR)
    assert found - PLAN_WRITER_ALLOWLIST == set(), (
        f"{sorted(found - PLAN_WRITER_ALLOWLIST)} write subscriptionTier; route the change through plan_service.change_plan")
    assert found == PLAN_WRITER_ALLOWLIST, f"the scanner no longer sees {sorted(PLAN_WRITER_ALLOWLIST - found)}"


def test_the_scanner_tells_writes_from_reads_and_creations():
    assert writes_subscription_tier("db.t.update_one({}, {'$set': {'subscriptionTier': x}})")
    assert writes_subscription_tier("db.t.update_one({}, {'$setOnInsert': {'subscriptionTier': x}}, upsert=True)")
    assert writes_subscription_tier("update_data['subscriptionTier'] = x")
    assert not writes_subscription_tier("db.t.insert_one({'id': 1, 'subscriptionTier': 'Free'})")
    assert not writes_subscription_tier("db.t.find_one({'subscriptionTier': 'Pro'})")
    assert not writes_subscription_tier("db.t.find({}, {'subscriptionTier': 1})")


def test_the_scanner_reports_a_rogue_module_by_name(tmp_path):
    (tmp_path / "rogue.py").write_text("async def f(db):\n    await db.t.update_one({}, {'$set': {'subscriptionTier': 'Pro'}})\n")
    (tmp_path / "quiet.py").write_text("DOC = {'subscriptionTier': 'Free'}\n")
    (tmp_path / "broken.py").write_text("def (:\n")
    assert modules(str(tmp_path)) == {"rogue.py"}
