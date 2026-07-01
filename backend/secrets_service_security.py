"""
SecretsManagementService security mixin: hardcoded-secret scanning and audit log retrieval.
"""

import re
from typing import Dict, Any, List, Optional


class SecretsManagementSecurityMixin:
    """Secret scanning and access audit log queries."""

    async def scan_for_hardcoded_secrets(
        self, code: str, file_path: str
    ) -> List[Dict[str, Any]]:
        """Scan code for hardcoded secrets (API keys, passwords, tokens, private keys)."""
        patterns = {
            "api_key": [
                r"api[_-]?key['\"]?\s*[:=]\s*['\"]([a-zA-Z0-9]{20,})['\"]",
                r"apikey['\"]?\s*[:=]\s*['\"]([a-zA-Z0-9]{20,})['\"]",
            ],
            "password": [
                r"password['\"]?\s*[:=]\s*['\"]([^'\"]{8,})['\"]",
                r"passwd['\"]?\s*[:=]\s*['\"]([^'\"]{8,})['\"]",
            ],
            "token": [
                r"token['\"]?\s*[:=]\s*['\"]([a-zA-Z0-9]{20,})['\"]",
                r"auth[_-]?token['\"]?\s*[:=]\s*['\"]([a-zA-Z0-9]{20,})['\"]",
            ],
            "private_key": [r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"],
            "aws_key": [r"AKIA[0-9A-Z]{16}"],
        }
        findings = []
        for secret_type, pattern_list in patterns.items():
            for pattern in pattern_list:
                for match in re.finditer(pattern, code, re.IGNORECASE):
                    findings.append({
                        "type": secret_type,
                        "file_path": file_path,
                        "line": code[:match.start()].count('\n') + 1,
                        "pattern": pattern,
                        "severity": "critical",
                        "recommendation": f"Move {secret_type} to secrets management system",
                    })
        return findings

    async def get_secret_access_log(
        self,
        secret_name: Optional[str] = None,
        tenant_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get the secret access audit log."""
        query: Dict[str, Any] = {}
        if secret_name:
            query["secret_name"] = secret_name
        if tenant_id:
            query["tenant_id"] = tenant_id
        cursor = self.db.secret_access_log.find(query).sort("timestamp", -1).limit(limit)
        logs = []
        async for log in cursor:
            log["id"] = str(log.pop("_id"))
            logs.append(log)
        return logs
