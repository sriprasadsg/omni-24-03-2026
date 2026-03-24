"""
SAST Scan Engine — Phase 5
Integrates with Semgrep for real static analysis security testing.
Falls back to Bandit for Python-only scanning if Semgrep not available.
"""
import subprocess
import json
import os
import tempfile
import shutil
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


def run_semgrep_scan(target_path: str, rules: str = "auto") -> Dict[str, Any]:
    """
    Run a Semgrep scan on a directory or file.
    Returns findings in a normalized format.
    """
    semgrep_bin = shutil.which("semgrep")
    if not semgrep_bin:
        logger.warning("Semgrep not found. Install with: pip install semgrep")
        return {"success": False, "error": "Semgrep not installed", "findings": []}

    token = os.getenv("SEMGREP_APP_TOKEN")
    cmd = [semgrep_bin, "--json", "--quiet"]
    if token:
        cmd += ["--config", "policy"]
        os.environ["SEMGREP_APP_TOKEN"] = token
    else:
        cmd += ["--config", rules]

    cmd.append(target_path)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        output = json.loads(result.stdout) if result.stdout.strip() else {}
        raw_findings = output.get("results", [])

        findings = []
        for f in raw_findings:
            findings.append({
                "id": f.get("check_id", "unknown"),
                "title": f.get("extra", {}).get("message", f.get("check_id", "")),
                "severity": f.get("extra", {}).get("severity", "ERROR").lower(),
                "file": f.get("path", ""),
                "line": f.get("start", {}).get("line", 0),
                "code_snippet": f.get("extra", {}).get("lines", ""),
                "cwe": f.get("extra", {}).get("metadata", {}).get("cwe", []),
                "owasp": f.get("extra", {}).get("metadata", {}).get("owasp", []),
                "fix_recommendation": f.get("extra", {}).get("metadata", {}).get("fix", ""),
                "tool": "semgrep",
            })

        return {
            "success": True,
            "tool": "semgrep",
            "total_findings": len(findings),
            "findings": findings,
            "errors": output.get("errors", []),
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Scan timed out after 5 minutes", "findings": []}
    except json.JSONDecodeError:
        return {"success": False, "error": "Failed to parse Semgrep output", "findings": []}
    except Exception as e:
        logger.error(f"Semgrep error: {e}")
        return {"success": False, "error": str(e), "findings": []}


def run_bandit_scan(target_path: str) -> Dict[str, Any]:
    """
    Run Bandit Python security scanner as a fallback.
    """
    bandit_bin = shutil.which("bandit")
    if not bandit_bin:
        return {"success": False, "error": "Bandit not installed (pip install bandit)", "findings": []}

    try:
        result = subprocess.run(
            [bandit_bin, "-r", target_path, "-f", "json", "-q"],
            capture_output=True, text=True, timeout=120
        )
        output = json.loads(result.stdout) if result.stdout.strip() else {}
        raw = output.get("results", [])

        findings = []
        for f in raw:
            findings.append({
                "id": f.get("test_id", "unknown"),
                "title": f.get("test_name", ""),
                "severity": f.get("issue_severity", "medium").lower(),
                "file": f.get("filename", ""),
                "line": f.get("line_number", 0),
                "code_snippet": f.get("code", ""),
                "cwe": [f.get("test_id", "")],
                "owasp": [],
                "fix_recommendation": f.get("more_info", ""),
                "tool": "bandit",
            })

        return {
            "success": True,
            "tool": "bandit",
            "total_findings": len(findings),
            "findings": findings,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        return {"success": False, "error": str(e), "findings": []}


def scan_code(target_path: str, prefer_tool: str = "semgrep") -> Dict[str, Any]:
    """
    Scan code using preferred tool, with automatic fallback.
    """
    if prefer_tool == "bandit":
        result = run_bandit_scan(target_path)
    else:
        result = run_semgrep_scan(target_path)
        if not result["success"] and "not installed" in result.get("error", ""):
            logger.info("Semgrep unavailable, falling back to Bandit")
            result = run_bandit_scan(target_path)

    return result


def save_upload_and_scan(file_content: bytes, filename: str) -> Dict[str, Any]:
    """
    Save uploaded file to temp dir, run scan, clean up.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        target = os.path.join(tmpdir, filename)
        with open(target, "wb") as f:
            f.write(file_content)
        return scan_code(tmpdir)
