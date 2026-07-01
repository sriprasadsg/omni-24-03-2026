"""SASTServiceAnalysisMixin: scan analysis helpers for SASTService."""

import os as _os
from typing import Any, Dict, List

_SSL_VERIFY = _os.getenv("DISABLE_SSL_VERIFY", "").lower() not in ("1", "true", "yes")


class VulnerabilitySeverity:
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ScanStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SASTServiceAnalysisMixin:
    """Mixin providing scan analysis helpers for SASTService."""

    async def _fetch_sonarqube_issues(self, project_key: str) -> List[Dict[str, Any]]:
        """Fetch real issues from SonarQube REST API."""
        import aiohttp
        base = self.sonarqube_config["url"].rstrip("/")
        token = self.sonarqube_config["token"]
        severity_map = {
            "BLOCKER": "critical", "CRITICAL": "critical",
            "MAJOR": "high", "MINOR": "medium", "INFO": "info",
        }
        try:
            auth = aiohttp.BasicAuth(token, "")
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(auth=auth, timeout=timeout) as session:
                resp = await session.get(
                    f"{base}/api/issues/search",
                    params={"projectKeys": project_key, "types": "VULNERABILITY,BUG",
                            "statuses": "OPEN,CONFIRMED,REOPENED", "ps": 100},
                    ssl=_SSL_VERIFY,
                )
                if resp.status != 200:
                    self.logger.warning("SonarQube returned %s — falling back to pattern scan", resp.status)
                    return await self._pattern_scan("")
                data = await resp.json()
                score_map = {"critical": 9.0, "high": 7.0, "medium": 5.0, "low": 2.0, "info": 1.0}
                vulns = []
                for issue in data.get("issues", []):
                    sev = severity_map.get(issue.get("severity", "MINOR"), "medium")
                    vulns.append({
                        "title": issue.get("message", "Unknown issue"),
                        "description": issue.get("message", ""),
                        "severity": sev,
                        "severity_score": score_map.get(sev, 5.0),
                        "category": issue.get("type", "Bug"),
                        "cwe_id": next((t for t in issue.get("tags", []) if t.startswith("cwe")), ""),
                        "owasp_category": issue.get("owaspTop10", ""),
                        "file_path": issue.get("component", "").split(":")[-1],
                        "line_number": issue.get("line", 0),
                        "code_snippet": issue.get("message", ""),
                        "recommendation": f"Fix {issue.get('rule', 'rule')} per SonarQube guidance",
                    })
                return vulns
        except Exception as exc:
            self.logger.warning("SonarQube fetch failed (%s) — falling back to pattern scan", exc)
            return await self._pattern_scan("")

    async def _pattern_scan(self, _repository_url: str) -> List[Dict[str, Any]]:
        """Pattern-based fallback: searches DB code files for known risky patterns."""
        import re
        risky_patterns = [
            (r"eval\s*\(", "critical", "CWE-95", "Use of eval() allows arbitrary code execution"),
            (r"exec\s*\(", "critical", "CWE-78", "Use of exec() may allow command injection"),
            (r"(?:password|secret|api_key)\s*=\s*['\"][^'\"]{4,}", "critical", "CWE-798",
             "Hardcoded credential detected"),
            (r"f['\"].*SELECT.*\{", "high", "CWE-89", "Possible SQL injection via f-string"),
            (r"dangerouslySetInnerHTML", "high", "CWE-79",
             "dangerouslySetInnerHTML bypasses React XSS protection"),
            (r"subprocess\.call\(.*shell=True", "high", "CWE-78",
             "shell=True in subprocess is vulnerable to injection"),
            (r"pickle\.loads\(", "high", "CWE-502", "Deserializing untrusted pickle data"),
            (r"yaml\.load\([^,)]+\)", "medium", "CWE-502",
             "yaml.load without Loader= is unsafe; use yaml.safe_load"),
            (r"random\.(randint|random|choice)\(", "medium", "CWE-338",
             "Cryptographically weak random number generator"),
        ]
        score_map = {"critical": 9.0, "high": 7.0, "medium": 5.0}
        vulns: List[Dict[str, Any]] = []
        try:
            code_files = await self.db.code_files.find(
                {}, {"_id": 0, "path": 1, "content": 1}
            ).to_list(length=200)
            for file_doc in code_files:
                path = file_doc.get("path", "unknown")
                content = file_doc.get("content", "")
                for line_num, line in enumerate(content.splitlines(), 1):
                    for pattern, severity, cwe, description in risky_patterns:
                        if re.search(pattern, line):
                            vulns.append({
                                "title": description,
                                "description": description,
                                "severity": severity,
                                "severity_score": score_map.get(severity, 3.0),
                                "category": "Pattern Match",
                                "cwe_id": cwe,
                                "owasp_category": "",
                                "file_path": path,
                                "line_number": line_num,
                                "code_snippet": line.strip()[:120],
                                "recommendation": f"Review and remediate {cwe}",
                            })
        except Exception as exc:
            self.logger.warning("Pattern scan failed: %s", exc)
        return vulns

    def _calculate_code_quality_score(self, vulnerabilities: List[Dict[str, Any]]) -> float:
        if not vulnerabilities:
            return 100.0
        severity_weights = {
            VulnerabilitySeverity.CRITICAL: 20,
            VulnerabilitySeverity.HIGH: 10,
            VulnerabilitySeverity.MEDIUM: 5,
            VulnerabilitySeverity.LOW: 2,
            VulnerabilitySeverity.INFO: 1,
        }
        total_penalty = sum(severity_weights.get(v["severity"], 1) for v in vulnerabilities)
        return round(max(0, 100 - total_penalty), 1)

    def _calculate_maintainability_score(self, _scan: Dict[str, Any]) -> float:
        return 75.0

    def _calculate_reliability_score(self, _scan: Dict[str, Any]) -> float:
        return 80.0

    def _calculate_security_score(self, scan: Dict[str, Any]) -> float:
        return scan.get("code_quality_score", 70.0)

    def _calculate_coverage_score(self, _scan: Dict[str, Any]) -> float:
        return 65.0

    def _generate_summary(self, vulnerabilities: List[Dict[str, Any]]) -> Dict[str, Any]:
        severity_counts = {
            VulnerabilitySeverity.CRITICAL: 0,
            VulnerabilitySeverity.HIGH: 0,
            VulnerabilitySeverity.MEDIUM: 0,
            VulnerabilitySeverity.LOW: 0,
            VulnerabilitySeverity.INFO: 0,
        }
        for vuln in vulnerabilities:
            severity = vuln.get("severity", VulnerabilitySeverity.INFO)
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        return {
            "total": len(vulnerabilities),
            "by_severity": severity_counts,
            "critical_count": severity_counts[VulnerabilitySeverity.CRITICAL],
            "high_count": severity_counts[VulnerabilitySeverity.HIGH],
            "medium_count": severity_counts[VulnerabilitySeverity.MEDIUM],
            "low_count": severity_counts[VulnerabilitySeverity.LOW],
        }

    def _load_security_patterns(self) -> List[Dict[str, Any]]:
        return [
            {
                "pattern": r"password\s*=\s*['\"][^'\"]+['\"]",
                "severity": VulnerabilitySeverity.CRITICAL,
                "description": "Hardcoded password detected",
            },
            {
                "pattern": r"api[_-]?key\s*=\s*['\"][^'\"]+['\"]",
                "severity": VulnerabilitySeverity.CRITICAL,
                "description": "Hardcoded API key detected",
            },
            {
                "pattern": r"eval\s*\(",
                "severity": VulnerabilitySeverity.HIGH,
                "description": "Use of eval() detected - potential code injection",
            },
        ]
