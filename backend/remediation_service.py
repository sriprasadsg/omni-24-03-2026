import logging
from datetime import datetime
from models import RemediationRequest
from tasks import execute_remediation_script  # Import Celery task reference

logger = logging.getLogger(__name__)


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
            action = f"AI-generated fix for {cve_id}"
            logger.info("AI remediation script generated for %s", cve_id)
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
        Approves a pending request and dispatches it to the Agent (via Celery).
        Also updates the vulnerability status in the database.
        """
        from database import get_database

        if request.status != "Pending":
            raise ValueError("Only Pending requests can be executed.")

        logger.info("Approving remediation %s — dispatching to agent", request.id)
        
        # Update status
        request.status = "In Progress"
        request.updatedAt = datetime.now().isoformat()
        
        # Trigger Celery Task async
        # In a real app, we'd pass the actual Agent ID
        execute_remediation_script.delay(request.scriptContent, "powershell")
        
        # Update Database: Mark Vulnerability as Patched
        db = get_database()
        try:
            # Match by string 'id' field first (seeded data), fall back to _id ObjectId
            query: dict = {"id": request.vulnerabilityId}
            try:
                from bson import ObjectId
                query = {"$or": [{"id": request.vulnerabilityId}, {"_id": ObjectId(request.vulnerabilityId)}]}
            except Exception:
                pass  # vulnerabilityId is not a valid ObjectId hex — use string id only

            result = await db.vulnerabilities.update_one(
                query,
                {"$set": {"status": "Patched", "remediatedAt": datetime.now().isoformat()}}
            )
            if result.modified_count > 0:
                logger.info("Vulnerability %s marked as PATCHED", request.vulnerabilityId)
                request.status = "Executed"
            else:
                logger.warning("Vulnerability %s not found in DB — already patched or missing", request.vulnerabilityId)
        except Exception as exc:
            logger.error("Error updating vulnerability status: %s", exc)

        return request

