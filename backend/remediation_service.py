import re
import logging
from datetime import datetime
from models import RemediationRequest

logger = logging.getLogger(__name__)

_DANGEROUS_SCRIPT_PATTERNS = [
    re.compile(r'curl\s+\S+\s*\|', re.IGNORECASE),        # curl piped to shell
    re.compile(r'wget\s+\S+\s*\|', re.IGNORECASE),        # wget piped to shell
    re.compile(r'\$\([^)]+\)', re.IGNORECASE),             # bash command substitution
    re.compile(r'`[^`]+`'),                                 # backtick substitution
    re.compile(r'\beval\s*[\(\$]', re.IGNORECASE),         # eval execution
    re.compile(r'\bIEX\s*[\(\$]', re.IGNORECASE),          # PowerShell Invoke-Expression short form
    re.compile(r'Invoke-Expression', re.IGNORECASE),        # PowerShell Invoke-Expression full form
    re.compile(r'Start-Process\s+.*-NoNewWindow', re.IGNORECASE),  # hidden process spawn
]
_MAX_SCRIPT_LENGTH = 10_000


def _validate_remediation_script(script: str) -> str | None:
    """Returns an error description if the script contains dangerous patterns, else None."""
    if len(script) > _MAX_SCRIPT_LENGTH:
        return "Script exceeds maximum allowed length"
    for pattern in _DANGEROUS_SCRIPT_PATTERNS:
        if pattern.search(script):
            return f"Dangerous pattern detected: {pattern.pattern}"
    return None


class RemediationService:
    @staticmethod
    async def generate_fix_proposal(tenant_id: str, asset_id: str, vulnerability_id: str, cve_id: str) -> RemediationRequest:
        """
        Calls the AI service to generate a remediation script for a given CVE.
        Falls back to a rule-based template only if the AI service is unavailable.
        """
        logger.info("AI generating fix for %s on asset %s", cve_id, asset_id)

        action = "Security Patch"
        script_content = ""

        try:
            from ai_service import ai_service
            prompt = (
                f"You are a senior security engineer. Generate a concise remediation script for "
                f"CVE: {cve_id} on asset {asset_id}.\n"
                f"Return ONLY the script (bash or PowerShell as appropriate). "
                f"No explanation, no markdown fencing."
            )
            script_content = await ai_service.generate_text(prompt, source="remediation")
            if script_content.startswith("BLOCKED:"):
                raise ValueError(script_content)
            validation_error = _validate_remediation_script(script_content)
            if validation_error:
                raise ValueError(f"Generated script failed security validation: {validation_error}")
            action = f"AI-generated fix for {cve_id}"
            logger.info("AI remediation script generated and validated for %s", cve_id)
        except Exception as exc:
            logger.warning("AI fix generation failed for %s: %s — using rule-based fallback", cve_id, exc)
            if "SQL" in cve_id or "Injection" in cve_id:
                action = "Sanitize Input & Update Config"
                script_content = "# Remediation: SQL Injection\nUpdate-WebConfig -SafeMode $true"
            elif "Log4j" in cve_id or "log4j" in cve_id.lower():
                action = "Patch Log4j Library"
                script_content = (
                    "Remove-Item -Path 'C:\\Apps\\Log4j-2.14.jar' -Force\n"
                    "Copy-Item 'C:\\Patches\\Log4j-2.17.jar' -Destination 'C:\\Apps\\'"
                )
            else:
                action = "Generic Security Patch"
                script_content = "apt-get update && apt-get upgrade -y --only-upgrade"

        return RemediationRequest(
            id=f"rem-{int(datetime.now().timestamp())}",
            tenantId=tenant_id,
            assetId=asset_id,
            vulnerabilityId=vulnerability_id,
            proposedAction=action,
            scriptContent=script_content,
            status="Pending",
            createdAt=datetime.now().isoformat(),
            updatedAt=datetime.now().isoformat()
        )

    @staticmethod
    async def approve_and_execute(request: RemediationRequest):
        """
        Approves a pending request. Nothing is sent: the script path to agents is fenced (RESP-11,
        D-18) and remediation is decided in Autonomous Ops, so the request reads "Not sent" and the
        vulnerability keeps its status (T-83-27: never a success answer for nothing sent).
        """
        from autonomous_ops.response_messages import FENCE

        if request.status != "Pending":
            raise ValueError("Only Pending requests can be executed.")

        logger.info("Remediation %s approved; nothing sent (script remediation is fenced)", request.id)
        request.status = "Not sent"
        request.executionLog = FENCE["worker"]
        request.updatedAt = datetime.now().isoformat()
        return request

