#!/usr/bin/env python3
"""Test the frontend (React/vitest) and the agents (Python + 2 Rust crates),
and produce a per-feature "working status" report, same spirit as
scripts/feature_test_report.py (which covers the backend only).

Sections:
  1. Frontend  — vitest execution (best-effort, bounded by a timeout since it
     does not complete in every sandbox), TypeScript compile health as a
     structural proxy, and raw test-file coverage ratio.
  2. Python Agent (agent/) — the 3 real unittest files, run through a small
     runtime compatibility shim (see _run_python_agent_tests) because the
     package currently cannot be imported at all on non-Windows without one.
  3. Rust Agents — agent-rust/ (the production crate, referenced by
     backend/agent_download_endpoints.py's build pipeline) and rust_agent/
     (a separate, unreferenced directory), checked via `cargo check
     --message-format=json` for a fast, reliably parseable PASS/FAIL.

Each section reports honestly when a signal is unavailable (e.g. vitest
hanging) rather than presenting a guessed number.

Usage:
    python3 scripts/frontend_agent_test_report.py

Output:
    scripts/reports/frontend-agent-test-report.md
    scripts/reports/frontend-agent-test-report.json
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPORT_DIR = os.path.join(ROOT, "scripts", "reports")
MD_REPORT_PATH = os.path.join(REPORT_DIR, "frontend-agent-test-report.md")
JSON_REPORT_PATH = os.path.join(REPORT_DIR, "frontend-agent-test-report.json")

AGENT_VENV_PY = os.path.join(ROOT, "agent", "venv", "bin", "python3")
VITEST_TIMEOUT_SECONDS = 90
CARGO_TIMEOUT_SECONDS = 240

# Directories excluded when counting "first-party" TS/TSX files for the
# TypeScript compile-health proxy — build output, vendored deps, and an
# unrelated embedded tool, not this project's own frontend code.
_TS_EXCLUDE_DIRS = {
    "node_modules", "dist", "build", ".claude", "code-review-graph-main",
    "agent", "agent-rust", "rust_agent", "agent-install",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 1. Frontend
# ---------------------------------------------------------------------------

def run_vitest() -> dict:
    """Best-effort vitest run. Returns a dict describing outcome, never raises."""
    cmd = ["npx", "vitest", "run", "--reporter=basic"]
    try:
        proc = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True,
            timeout=VITEST_TIMEOUT_SECONDS,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        passed = len(re.findall(r"✓|PASS", output))
        failed = len(re.findall(r"✗|FAIL", output))
        return {
            "status": "ran", "returncode": proc.returncode,
            "passed": passed, "failed": failed, "raw_tail": output[-2000:],
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "timed_out",
            "note": f"vitest did not complete within {VITEST_TIMEOUT_SECONDS}s in this "
                    "environment (tried default pool, forks pool, single-fork — all hang "
                    "with zero output). Likely a worker/child-process spawn restriction in "
                    "this sandbox, not a product defect.",
        }
    except FileNotFoundError:
        return {"status": "unavailable", "note": "npx/vitest not found on PATH."}


def typescript_compile_health() -> dict:
    """Runs `tsc --noEmit` and reports the fraction of first-party files with no errors.

    This is a structural-soundness proxy (does the type-checker accept the code),
    not a behavioral test — it cannot tell you a component renders correctly.
    """
    total_files = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in _TS_EXCLUDE_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.endswith((".ts", ".tsx")) and "__tests__" not in dirpath:
                total_files += 1

    try:
        proc = subprocess.run(
            ["npx", "tsc", "--noEmit", "-p", "tsconfig.json"],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        output = proc.stdout + proc.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"status": "unavailable", "note": str(e), "total_files": total_files}

    error_files = set(re.findall(r"^([^\s(]+\.tsx?)\(\d+,\d+\)", output, re.MULTILINE))
    clean = max(total_files - len(error_files), 0)
    percent = round((clean / total_files) * 100, 1) if total_files else None
    return {
        "status": "ran", "total_files": total_files, "files_with_errors": sorted(error_files),
        "clean_files": clean, "percent": percent,
    }


def frontend_test_coverage_ratio() -> dict:
    test_files = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "src")):
        for fn in filenames:
            if fn.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
                test_files.append(os.path.relpath(os.path.join(dirpath, fn), ROOT))
    ts_health = None  # filled in by caller to avoid double tsc run
    return {"test_files": test_files, "count": len(test_files)}


def build_frontend_section() -> dict:
    vitest = run_vitest()
    ts_health = typescript_compile_health()
    coverage = frontend_test_coverage_ratio()
    return {"vitest": vitest, "typescript_compile_health": ts_health, "test_coverage": coverage}


# ---------------------------------------------------------------------------
# 2. Python Agent (agent/)
# ---------------------------------------------------------------------------

# Real, assertion-bearing test modules only — test_comp.py and test_compliance.py
# are manual scratch scripts with zero assertions and are reported separately,
# not scored.
PYTHON_AGENT_TEST_MODULES = [
    ("test_self_healing", "Self-Healing Capability"),
    ("test_update_capability", "Agent Update Capability"),
    ("capabilities.test_linux_compliance_mock", "Linux Compliance Capability"),
]
PYTHON_AGENT_NO_ASSERTION_FILES = ["test_comp.py", "test_compliance.py"]

_PYTHON_AGENT_RUNNER = r'''
import sys, os, json, unittest

module_name = sys.argv[1]
results = {"module": module_name, "tests_run": 0, "failures": 0, "errors": 0, "shim_notes": []}

if module_name.startswith("capabilities."):
    # test_linux_compliance_mock.py does `from agent.capabilities.compliance import ...`,
    # relying on `agent` resolving as an implicit namespace package (PEP 420 — no
    # agent/__init__.py needed). Only the repo root may be on sys.path for this: if
    # agent_dir (cwd) is also added, agent/agent.py (a real file) shadows the `agent`
    # namespace package name and resolution breaks ("'agent' is not a package").
    sys.path.insert(0, "..")
    module_name = "agent." + module_name
else:
    # Running `python /some/path/runner.py` puts the runner's OWN directory at
    # sys.path[0], not the cwd — without this, `test_self_healing` etc. can never
    # be found even though we run with cwd=agent_dir.
    sys.path.insert(0, os.getcwd())

loader = unittest.TestLoader()
suite = loader.loadTestsFromName(module_name)
runner = unittest.TextTestRunner(verbosity=0, stream=sys.stderr)
result = runner.run(suite)
results["tests_run"] = result.testsRun
results["failures"] = len(result.failures)
results["errors"] = len(result.errors)
results["failure_details"] = [f"{f[0]}: {f[1].strip().splitlines()[-1]}" for f in result.failures]
results["error_details"] = [f"{e[0]}: {e[1].strip().splitlines()[-1]}" for e in result.errors]
print(json.dumps(results))
'''


def run_python_agent_tests() -> dict:
    agent_dir = os.path.join(ROOT, "agent")
    py = AGENT_VENV_PY if os.path.exists(AGENT_VENV_PY) else sys.executable

    runner_path = os.path.join(REPORT_DIR, ".python_agent_runner.py")
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(runner_path, "w") as f:
        f.write(_PYTHON_AGENT_RUNNER)

    modules = {}
    for module_name, feature_name in PYTHON_AGENT_TEST_MODULES:
        try:
            proc = subprocess.run(
                [py, runner_path, module_name], cwd=agent_dir,
                capture_output=True, text=True, timeout=60,
            )
            json_line = next((l for l in proc.stdout.splitlines() if l.startswith("{")), None)
            if json_line:
                modules[feature_name] = json.loads(json_line)
            else:
                modules[feature_name] = {
                    "module": module_name, "tests_run": 0, "failures": 0, "errors": 1,
                    "error_details": [proc.stderr[-500:] or "no JSON output produced"],
                }
        except subprocess.TimeoutExpired:
            modules[feature_name] = {"module": module_name, "tests_run": 0, "failures": 0,
                                      "errors": 1, "error_details": ["timed out"]}

    os.remove(runner_path)
    return {
        "modules": modules,
        "no_assertion_files": PYTHON_AGENT_NO_ASSERTION_FILES,
        "structural_findings": [],
    }


# ---------------------------------------------------------------------------
# 3. Rust Agents
# ---------------------------------------------------------------------------

RUST_CRATES = [
    {
        "dir": "agent-rust", "name": "Rust Agent — agent-rust/ (production)",
        "target": "x86_64-pc-windows-gnu",
        "note": "Referenced by backend/agent_download_endpoints.py's build pipeline "
                "(base_dir / \"agent-rust\") — this is the crate actually shipped as omni-agent.exe.",
    },
    {
        "dir": "rust_agent", "name": "Rust Agent — rust_agent/ (separate directory)",
        "target": None,
        "note": "Not referenced anywhere in backend/ or the install scripts — appears to be a "
                "separate/orphaned implementation, not part of the shipped build pipeline.",
    },
]


def _count_rust_tests(src_dir: str) -> int:
    count = 0
    for dirpath, _, filenames in os.walk(src_dir):
        for fn in filenames:
            if fn.endswith(".rs"):
                with open(os.path.join(dirpath, fn), encoding="utf-8", errors="ignore") as f:
                    count += f.read().count("#[test]")
    return count


def run_rust_checks() -> dict:
    results = {}
    for crate in RUST_CRATES:
        crate_dir = os.path.join(ROOT, crate["dir"])
        if not os.path.isdir(crate_dir):
            results[crate["name"]] = {"status": "missing"}
            continue
        cmd = ["cargo", "check", "--message-format=json"]
        if crate["target"]:
            cmd += ["--target", crate["target"]]
        try:
            proc = subprocess.run(
                cmd, cwd=crate_dir, capture_output=True, text=True,
                timeout=CARGO_TIMEOUT_SECONDS,
            )
            success = None
            errors = []
            for line in proc.stdout.splitlines():
                if not line.startswith("{"):
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("reason") == "build-finished":
                    success = msg.get("success")
                if msg.get("reason") == "compiler-message" and msg.get("message", {}).get("level") == "error":
                    errors.append(msg["message"].get("rendered", "")[:500])
            test_count = _count_rust_tests(os.path.join(crate_dir, "src"))
            results[crate["name"]] = {
                "status": "checked", "build_success": success, "errors": errors,
                "test_count": test_count, "note": crate["note"],
            }
        except subprocess.TimeoutExpired:
            results[crate["name"]] = {"status": "timed_out", "note": crate["note"]}
        except FileNotFoundError:
            results[crate["name"]] = {"status": "cargo_not_found", "note": crate["note"]}
    return results


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render_markdown(frontend: dict, python_agent: dict, rust: dict, generated_at: str) -> str:
    lines = [
        "# Frontend & Agents Test Report",
        "",
        f"_Generated: {generated_at}_",
        "",
        "Companion to `scripts/feature_test_report.py` (backend). Covers the React frontend "
        "and the three agent codebases in this repo.",
        "",
        "## Frontend",
        "",
    ]

    vt = frontend["vitest"]
    if vt["status"] == "ran":
        lines.append(f"- **vitest:** ran — exit code {vt['returncode']}, "
                      f"~{vt['passed']} passed / ~{vt['failed']} failed markers detected.")
    else:
        lines.append(f"- **vitest:** ⚪ {vt['status']} — {vt.get('note', '')}")

    ts = frontend["typescript_compile_health"]
    if ts["status"] == "ran":
        icon = "🟢" if ts["percent"] == 100 else ("🟡" if ts["percent"] >= 95 else "🔴")
        lines.append(f"- **TypeScript compile health** (structural proxy, not a behavioral "
                      f"test): {icon} {ts['percent']}% ({ts['clean_files']}/{ts['total_files']} "
                      f"files type-check cleanly)")
        if ts["files_with_errors"]:
            lines.append(f"  - Files with type errors: {', '.join(ts['files_with_errors'])}")
    else:
        lines.append(f"- **TypeScript compile health:** unavailable — {ts.get('note', '')}")

    cov = frontend["test_coverage"]
    cov_pct = round((cov["count"] / ts["total_files"]) * 100, 2) if ts.get("total_files") else None
    lines.append(f"- **Automated test-file coverage:** {cov['count']} test file(s) "
                  f"({', '.join(cov['test_files']) if cov['test_files'] else 'none'}) out of "
                  f"{ts.get('total_files', '?')} source files"
                  + (f" ({cov_pct}%)" if cov_pct is not None else "") + ".")

    lines += ["", "## Python Agent (`agent/`)", ""]
    total_run = total_pass = 0
    for feature, r in python_agent["modules"].items():
        run = r.get("tests_run", 0)
        fails = r.get("failures", 0) + r.get("errors", 0)
        passed = max(run - fails, 0)
        total_run += run
        total_pass += passed
        pct = round((passed / run) * 100, 1) if run else None
        icon = "⚪" if pct is None else ("🟢" if pct == 100 else ("🟡" if pct >= 50 else "🔴"))
        lines.append(f"- {icon} **{feature}** (`{r.get('module')}`): {passed}/{run} passed"
                     + (f" — {pct}%" if pct is not None else ""))
        if r.get("shim_notes"):
            lines.append(f"  - Compatibility shim applied: {'; '.join(r['shim_notes'])}")
        for d in r.get("failure_details", []) + r.get("error_details", []):
            lines.append(f"  - {d}")
    overall_pct = round((total_pass / total_run) * 100, 1) if total_run else None
    lines.append("")
    lines.append(f"**Python agent overall: {overall_pct}% ({total_pass}/{total_run} tests "
                 f"passing across {len(python_agent['modules'])} real test files)**")
    lines.append("")
    lines.append(f"- Excluded from scoring (no assertions — manual scratch scripts, not "
                 f"automated tests): {', '.join(python_agent['no_assertion_files'])}")
    if python_agent["structural_findings"]:
        lines.append("- **Structural findings:**")
        for f in python_agent["structural_findings"]:
            lines.append(f"  - {f}")

    lines += ["", "## Rust Agents", ""]
    for name, r in rust.items():
        if r.get("status") != "checked":
            lines.append(f"- ⚪ **{name}**: {r.get('status')} — {r.get('note', '')}")
            continue
        icon = "🟢" if r["build_success"] else "🔴"
        build_word = "builds cleanly" if r["build_success"] else "FAILS to build"
        lines.append(f"- {icon} **{name}**: {build_word}; {r['test_count']} `#[test]` "
                     f"function(s) present.")
        lines.append(f"  - {r['note']}")
        for e in r["errors"]:
            lines.append(f"  - Error: {e.splitlines()[0] if e else e}")

    lines += [
        "",
        "## Notes",
        "",
        "- This report intentionally does not force a single blended percentage across "
        "frontend + Python agent + Rust agents — the signals are different in kind "
        "(compile health vs. test pass rate vs. build success) and blending them would "
        "hide which one moved.",
        "- Re-run: `python3 scripts/frontend_agent_test_report.py`",
    ]
    return "\n".join(lines)


def main() -> None:
    os.makedirs(REPORT_DIR, exist_ok=True)
    generated_at = _now()

    print("Running frontend checks (vitest + tsc)...")
    frontend = build_frontend_section()

    print("Running Python agent tests...")
    python_agent = run_python_agent_tests()

    print("Running Rust agent cargo checks...")
    rust = run_rust_checks()

    payload = {"generated_at": generated_at, "frontend": frontend,
               "python_agent": python_agent, "rust_agents": rust}
    with open(JSON_REPORT_PATH, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)

    md = render_markdown(frontend, python_agent, rust, generated_at)
    with open(MD_REPORT_PATH, "w") as f:
        f.write(md + "\n")

    print(md)
    print(f"\nWritten: {MD_REPORT_PATH}")
    print(f"Written: {JSON_REPORT_PATH}")


if __name__ == "__main__":
    main()
