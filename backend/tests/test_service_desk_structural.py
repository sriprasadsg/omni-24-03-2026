"""Structural fence around the first-line service desk (Phase 85, plan 85-07, D-15 / DESK-03 / DESK-04;
PROH-85-01, PROH-85-02). A pure test: it parses source files, it needs no database and sends no request.

Value: protects=the desk can never reach a mock, scratch or cloud model provider, the LAN address helper or an
agent queue, and the only door to a model stays one loopback client; fails_when=a desk module imports ai_service,
ai_providers, ai_services or any other module of the Phase 81 banned LLM list, local_ip, an omni_scratch or
with_own_model module, imports httpx anywhere but service_desk/model.py, touches the agent_instructions,
instructions or response_tasks collections, or a module under autonomous_ops imports the desk; no_claim=what
the model client does at run time (test_service_desk_model.py) and any file that is not on disk under the
paths named here. Each rule has a negative control (a synthetic source that MUST be reported) so the scan
cannot pass vacuously.
"""
import ast
import glob
import os
import sys
from typing import Dict, List

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_autonomous_ops_structural import BANNED_LLM_MODULES

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_MODULE = "service_desk/model.py"
QUEUE_NAMES = ("agent_instructions", "instructions", "response_tasks")
FORBIDDEN_NAME_PARTS = ("omni_scratch", "with_own_model")
FORBIDDEN_MODULES = ("local_ip",)


def desk_files() -> Dict[str, str]:
    """{path relative to backend: source} for the desk package and every desk endpoint module on disk."""
    patterns = ("service_desk/*.py", "service_desk_*.py", "autonomous_ops_service_desk_endpoints.py")
    found: List[str] = []
    for pattern in patterns:
        found += glob.glob(os.path.join(_BACKEND, pattern))
    out = {}
    for full in sorted(set(found)):
        with open(full, encoding="utf-8-sig", errors="replace") as handle:
            out[os.path.relpath(full, _BACKEND).replace(os.sep, "/")] = handle.read()
    return out


def autonomous_files() -> Dict[str, str]:
    out = {}
    for full in sorted(glob.glob(os.path.join(_BACKEND, "autonomous_ops", "**", "*.py"), recursive=True)):
        with open(full, encoding="utf-8-sig", errors="replace") as handle:
            out[os.path.relpath(full, _BACKEND).replace(os.sep, "/")] = handle.read()
    return out


def imported_names(tree: ast.AST) -> List[str]:
    """Every dotted name a source imports, relative imports included (their leading dots dropped)."""
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                names.append(module)
            names += [f"{module}.{alias.name}" if module else alias.name for alias in node.names]
    return names


def _matches_banned(name: str) -> bool:
    for banned in BANNED_LLM_MODULES:
        if name == banned or name.startswith(banned + ".") or (banned == "langchain" and name.startswith("langchain")):
            return True
    return False


def scan_desk_source(rel: str, src: str) -> List[str]:
    """The rule violations of one desk file."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return [f"{rel}: does not parse"]
    problems: List[str] = []
    for name in imported_names(tree):
        parts = name.split(".")
        if _matches_banned(name):
            problems.append(f"{rel}: imports the banned LLM module {name}")
        if name in FORBIDDEN_MODULES or parts[0] in FORBIDDEN_MODULES:
            problems.append(f"{rel}: imports {name} (a LAN address helper)")
        if any(part in name for part in FORBIDDEN_NAME_PARTS):
            problems.append(f"{rel}: imports {name} (a scratch or own-model provider)")
        if parts[0] == "httpx" and rel != MODEL_MODULE:
            problems.append(f"{rel}: imports httpx; only {MODEL_MODULE} may")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in QUEUE_NAMES:
            problems.append(f"{rel}:{node.lineno}: touches the {node.attr} collection")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in QUEUE_NAMES:
            problems.append(f"{rel}:{node.lineno}: names the {node.value} collection")
    return problems


def scan_autonomous_source(rel: str, src: str) -> List[str]:
    """A module under autonomous_ops must not import the desk."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return [f"{rel}: does not parse"]
    problems = []
    for name in imported_names(tree):
        if any(part == "service_desk" or part.startswith("service_desk_") for part in name.split(".")):
            problems.append(f"{rel}: imports {name}")
    return problems


@pytest.fixture(scope="module")
def desk():
    found = desk_files()
    assert len(found) >= 10, "the scan found too little of the desk to be meaningful"
    assert MODEL_MODULE in found and "service_desk/pipeline.py" in found and "service_desk_endpoints.py" in found
    return found


# ------------------------------------------------------------------ the fence on the real code

def test_the_desk_imports_no_llm_provider_and_no_lan_helper(desk):
    problems = [p for rel, src in desk.items() for p in scan_desk_source(rel, src)
                if "banned LLM" in p or "LAN address" in p or "scratch" in p]
    assert problems == [], "\n".join(problems)


def test_only_the_model_client_imports_httpx(desk):
    problems = [p for rel, src in desk.items() for p in scan_desk_source(rel, src) if "imports httpx" in p]
    assert problems == [], "\n".join(problems)
    assert "import httpx" in desk[MODEL_MODULE], "the one model client must be the module that imports httpx"


def test_no_desk_module_touches_an_agent_queue(desk):
    problems = [p for rel, src in desk.items() for p in scan_desk_source(rel, src) if "collection" in p]
    assert problems == [], "\n".join(problems)


def test_every_desk_file_parses(desk):
    problems = [p for rel, src in desk.items() for p in scan_desk_source(rel, src) if "does not parse" in p]
    assert problems == []


def test_nothing_under_autonomous_ops_imports_the_desk():
    files = autonomous_files()
    assert len(files) >= 10 and "autonomous_ops/gate.py" in files, "the scan found too little to be meaningful"
    problems = [p for rel, src in files.items() for p in scan_autonomous_source(rel, src)]
    assert problems == [], "\n".join(problems)


def test_the_banned_list_is_the_phase_81_list():
    assert {"ai_service", "ai_providers", "ai_services", "ollama", "openai", "anthropic"} <= set(BANNED_LLM_MODULES)


# ------------------------------------------------------------------ negative controls

def test_scanner_reports_a_banned_import():
    for source in ("import ai_service\n", "from ai_service import chat\n", "from ai_providers import MockProvider\n",
                   "from ai_services.omni_scratch_provider import X\n", "import openai\n",
                   "from langchain_core import x\n", "import anthropic.types\n"):
        assert scan_desk_source("service_desk/new.py", source), source


def test_scanner_reports_a_relative_import_of_a_banned_module():
    assert scan_desk_source("service_desk/new.py", "from ..ai_service import chat\n")
    assert scan_desk_source("service_desk/new.py", "from .. import ai_providers\n")


def test_scanner_reports_the_lan_helper_and_scratch_names():
    assert scan_desk_source("service_desk/new.py", "import local_ip\n")
    assert scan_desk_source("service_desk/new.py", "from local_ip import ollama_default_url\n")
    assert scan_desk_source("service_desk/new.py", "from omni_scratch_runner import run\n")
    assert scan_desk_source("service_desk/new.py", "from helpers import with_own_model\n")


def test_scanner_reports_httpx_outside_the_model_client_only():
    assert scan_desk_source("service_desk/pipeline.py", "import httpx\n")
    assert scan_desk_source("service_desk_endpoints.py", "from httpx import AsyncClient\n")
    assert scan_desk_source(MODEL_MODULE, "import httpx\n") == []


def test_scanner_reports_queue_collection_access():
    for source in ("db.agent_instructions.insert_one({})\n", "db['instructions'].find({})\n",
                   "await raw(db).response_tasks.update_one({}, {})\n", "db.get_collection('response_tasks')\n"):
        assert scan_desk_source("service_desk/new.py", source), source
    assert scan_desk_source("service_desk/new.py", "raw(db).service_desk_jobs.find_one({})\n") == []


def test_scanner_reports_a_file_it_cannot_parse():
    assert scan_desk_source("service_desk/new.py", "def broken(:\n") == ["service_desk/new.py: does not parse"]
    assert scan_autonomous_source("autonomous_ops/new.py", "def broken(:\n")


def test_scanner_accepts_the_imports_the_desk_really_uses():
    source = ("from autonomous_ops import gate, ledger\nfrom autonomous_ops.scope import raw\n"
              "from . import retrieval\nfrom .model import OllamaClient\nfrom urllib.parse import urlparse\n")
    assert scan_desk_source("service_desk/pipeline.py", source) == []


def test_the_autonomous_ops_scanner_reports_a_desk_import():
    for source in ("import service_desk\n", "from service_desk import pipeline\n", "from service_desk.model import X\n",
                   "import service_desk_endpoints\n", "from .. import service_desk\n"):
        assert scan_autonomous_source("autonomous_ops/new.py", source), source
    assert scan_autonomous_source("autonomous_ops/gate.py", "from autonomous_ops import ledger\n") == []


def test_scanner_reads_a_source_file_from_disk_like_the_real_run(tmp_path):
    """The scan reads files from disk the same way the real run does."""
    path = tmp_path / "service_desk_probe.py"
    path.write_text("import ai_service\nimport httpx\n", encoding="utf-8")
    problems = scan_desk_source("service_desk_probe.py", path.read_text(encoding="utf-8"))
    assert any("ai_service" in p for p in problems) and any("httpx" in p for p in problems)
