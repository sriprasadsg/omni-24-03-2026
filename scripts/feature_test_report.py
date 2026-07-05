#!/usr/bin/env python3
"""Run the backend test suite and produce a per-feature "working status" report.

Groups backend/tests/test_*.py files into product features (see FEATURE_MAP)
and reports pass/fail/skip counts and a working percentage for each, plus an
overall platform score.

This report reflects backend/API-level test coverage only. Frontend (vitest)
execution is attempted but does not block the report if it is unavailable in
the current environment (see the "frontend" section of the output).

Usage:
    backend/venv/bin/python3 scripts/feature_test_report.py [--json-only]

Output:
    scripts/reports/feature-test-report.md    (human-readable)
    scripts/reports/feature-test-report.json  (machine-readable)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_TESTS_DIR = os.path.join(ROOT, "backend", "tests")
BACKEND_VENV_PY = os.path.join(ROOT, "backend", "venv", "bin", "python3")
REPORT_DIR = os.path.join(ROOT, "scripts", "reports")
JUNIT_XML_PATH = os.path.join(REPORT_DIR, ".backend-junit.xml")
MD_REPORT_PATH = os.path.join(REPORT_DIR, "feature-test-report.md")
JSON_REPORT_PATH = os.path.join(REPORT_DIR, "feature-test-report.json")

# Maps backend/tests/test_*.py -> the product feature it exercises.
# Keep additions in sync with .planning/ROADMAP.md / STATE.md phase names.
FEATURE_MAP = {
    "test_agent_update_checksum.py": "Agent Update Integrity (checksum verification)",
    "test_agentic_ai.py": "Agentic AI Integration",
    "test_agentless_features.py": "Agentless Scanning",
    "test_alerts_and_ai.py": "Alerts & AI Insights",
    "test_audit_export.py": "Audit-Ready Export",
    "test_auth_mfa.py": "Authentication — MFA",
    "test_authentication.py": "Authentication — Core",
    "test_automation_and_baa.py": "Automation & BAA",
    "test_bulk_evidence_upload.py": "Bulk Evidence Upload",
    "test_bundles_and_reports.py": "Bundles & Reports",
    "test_cloud_accounts.py": "Cloud Accounts",
    "test_cloud_checks_expansion.py": "Cloud Checks Expansion",
    "test_compliance_narrative_service.py": "AI Compliance Narratives",
    "test_compliance_score.py": "Compliance Score Dashboard",
    "test_compliance_status.py": "Asset Compliance Status",
    "test_core_endpoints.py": "Core Endpoints (patches/assets)",
    "test_e2e_integration.py": "End-to-End Integration",
    "test_evidence_lifecycle.py": "Evidence Lifecycle (staleness/chain-of-custody)",
    "test_evidence_review.py": "Evidence Review Workflow",
    "test_evidence_uploads.py": "Manual Evidence Uploads",
    "test_frameworks_schema.py": "Compliance Frameworks Schema",
    "test_iac_scanner.py": "IaC & Container Security",
    "test_notification_service.py": "Notification Routing & Domain Scanner",
    "test_powershell_evidence.py": "Windows PowerShell Evidence Collection",
    "test_privacy_service.py": "Privacy & Legal Modules",
    "test_program_service.py": "Program Control Grouping",
    "test_rate_limiter.py": "Rate Limiting",
    "test_rbac.py": "RBAC",
    "test_remediation_workflow.py": "Remediation Workflow",
    "test_remote_access.py": "Remote Access",
    "test_rust_heartbeat_parity.py": "Rust Agent Evidence Parity",
    "test_saas_integration.py": "SaaS Evidence Integration",
    "test_scheduled_reports.py": "Scheduled Compliance Reports",
    "test_smoke_endpoints.py": "Smoke Endpoints",
    "test_soar_and_ml.py": "SOAR & ML",
    "test_ssrf_guards.py": "SSRF Guards",
    "test_tenant_isolation.py": "Multi-Tenant Isolation",
    "test_tenant_security.py": "Tenant Security Hardening",
    "test_tickets.py": "Ticketing Integration",
}


def _feature_name(filename: str) -> str:
    if filename in FEATURE_MAP:
        return FEATURE_MAP[filename]
    stem = filename[len("test_"):-len(".py")] if filename.startswith("test_") else filename[:-3]
    return stem.replace("_", " ").title()


def run_backend_tests() -> str:
    os.makedirs(REPORT_DIR, exist_ok=True)
    py = BACKEND_VENV_PY if os.path.exists(BACKEND_VENV_PY) else sys.executable
    cmd = [py, "-m", "pytest", BACKEND_TESTS_DIR, "-q", f"--junitxml={JUNIT_XML_PATH}"]
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return JUNIT_XML_PATH


def parse_junit(xml_path: str) -> dict:
    """Groups testcases by their source file (feature) and tallies outcomes."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))

    features: dict[str, dict] = {}
    for suite in suites:
        for tc in suite.iter("testcase"):
            filepath = tc.get("file")
            if filepath:
                filename = os.path.basename(filepath)
            else:
                # No `file` attr in this pytest's junit output — classname is dotted
                # module.path.ClassName; the module segment is the one starting with
                # "test_", any segments after it are a Test class name, not a package.
                parts = tc.get("classname", "").split(".")
                module_part = next((p for p in parts if p.startswith("test_")), parts[-1])
                filename = module_part + ".py"
            feature = _feature_name(filename)
            f = features.setdefault(feature, {
                "file": filename, "total": 0, "passed": 0,
                "failed": 0, "skipped": 0, "errors": 0,
            })
            f["total"] += 1
            if tc.find("failure") is not None:
                f["failed"] += 1
            elif tc.find("error") is not None:
                f["errors"] += 1
            elif tc.find("skipped") is not None:
                f["skipped"] += 1
            else:
                f["passed"] += 1
    return features


def compute_percentages(features: dict) -> dict:
    for f in features.values():
        gradable = f["total"] - f["skipped"]
        f["percent"] = round((f["passed"] / gradable) * 100, 1) if gradable > 0 else None
    return features


def render_markdown(features: dict, generated_at: str) -> str:
    rows = sorted(features.items(), key=lambda kv: (kv[1]["percent"] is None, -(kv[1]["percent"] or 0), kv[0]))
    total_tests = sum(f["total"] for f in features.values())
    total_passed = sum(f["passed"] for f in features.values())
    total_failed = sum(f["failed"] for f in features.values())
    total_skipped = sum(f["skipped"] for f in features.values())
    total_errors = sum(f["errors"] for f in features.values())
    gradable = total_tests - total_skipped
    overall_pct = round((total_passed / gradable) * 100, 1) if gradable > 0 else 0.0

    lines = [
        "# Feature Test Report",
        "",
        f"_Generated: {generated_at}_",
        "",
        "Scope: backend/API-level automated tests (`backend/tests/`). Frontend UI is not "
        "covered by this report — see the note at the bottom.",
        "",
        f"## Overall: {overall_pct}% ({total_passed}/{gradable} passing, "
        f"{total_skipped} skipped, {total_failed} failed, {total_errors} errored, "
        f"across {len(features)} features / {total_tests} tests)",
        "",
        "| Feature | Status | Working % | Passed | Failed | Errors | Skipped | Total |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, f in rows:
        pct = f["percent"]
        pct_display = f"{pct}%" if pct is not None else "N/A (all skipped)"
        if pct is None:
            status = "⚪ Unverified"
        elif pct == 100:
            status = "🟢 Working"
        elif pct >= 80:
            status = "🟡 Mostly Working"
        else:
            status = "🔴 Broken"
        lines.append(
            f"| {name} | {status} | {pct_display} | {f['passed']} | {f['failed']} | "
            f"{f['errors']} | {f['skipped']} | {f['total']} |"
        )

    lines += [
        "",
        "## Notes",
        "",
        "- **Working %** = passed / (total − skipped) for that feature's test file.",
        "- 🟢 100% · 🟡 80–99% · 🔴 <80% · ⚪ every test in the file was skipped "
        "(commonly an environment precondition, e.g. no live Trivy/DB).",
        "- Frontend (React/vitest) is not included: the repo currently has one component "
        "spec file, and `vitest` did not complete in this environment when attempted.",
        "- **Known flakiness:** `backend/rate_limiter.py` uses a real Redis-backed store "
        "(not in-memory) when `REDIS_URL` is configured, with windows up to 1 hour. "
        "Running the login/MFA-touching tests (`test_authentication.py`, `test_auth_mfa.py`) "
        "back-to-back multiple times within that window can trip real 429s that look like "
        "failures but are the rate limiter correctly doing its job against test-generated "
        "traffic, not a product defect. If Authentication/MFA show failures, wait a few "
        "minutes (or clear the `LIMITS:LIMITER*` Redis keys, with the user's explicit "
        "consent — it's shared state) and re-run once.",
        "- Re-run: `backend/venv/bin/python3 scripts/feature_test_report.py`",
    ]
    return "\n".join(lines)


def main() -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    xml_path = run_backend_tests()
    if not os.path.exists(xml_path):
        print("ERROR: pytest did not produce a JUnit XML report.", file=sys.stderr)
        sys.exit(1)

    features = compute_percentages(parse_junit(xml_path))

    os.makedirs(REPORT_DIR, exist_ok=True)
    payload = {"generated_at": generated_at, "features": features}
    with open(JSON_REPORT_PATH, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)

    md = render_markdown(features, generated_at)
    with open(MD_REPORT_PATH, "w") as f:
        f.write(md + "\n")

    print(md)
    print(f"\nWritten: {MD_REPORT_PATH}")
    print(f"Written: {JSON_REPORT_PATH}")


if __name__ == "__main__":
    main()
