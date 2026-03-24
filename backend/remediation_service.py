from datetime import datetime
from models import RemediationRequest
from tasks import execute_remediation_script  # Import Celery task reference

# In a real scenario, this would import OpenAI/Anthropic client
# from openai import OpenAI 

class RemediationService:
    @staticmethod
    async def generate_fix_proposal(tenant_id: str, asset_id: str, vulnerability_id: str, cve_id: str) -> RemediationRequest:
        """
        Simulates calling an LLM to generate a remediation script for a given CVE.
        """
        print(f"🤖 AI generating fix for {cve_id} on asset {asset_id}...")
        
        # MOCK LLM LOGIC
        # In reality: prompt = f"Write a PowerShell script to fix {cve_id}..."
        
        mock_script = ""
        action = ""
        
        if "SQL" in cve_id or "Injection" in cve_id:
            action = "Sanitize Input & Update Config"
            mock_script = "# Fixed SQL Injection Vulnerability\nUpdate-WebConfig -SafeMode $true"
        elif "Log4j" in cve_id:
            action = "Patch Log4j Library"
            mock_script = "Remove-Item -Path 'C:\\Apps\\Log4j-2.14.jar' -Force\nCopy-Item 'C:\\Patches\\Log4j-2.17.jar' -Destination 'C:\\Apps\\'"
        else:
            action = "Generic Security Patch"
            mock_script = "apt-get update && apt-get upgrade -y security-packages"

        return RemediationRequest(
            id=f"rem-{int(datetime.now().timestamp())}",
            tenantId=tenant_id,
            assetId=asset_id,
            vulnerabilityId=vulnerability_id,
            proposedAction=action,
            scriptContent=mock_script,
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
        from bson import ObjectId

        if request.status != "Pending":
            raise ValueError("Only Pending requests can be executed.")
            
        print(f"✅ Approving remediation {request.id}. Dispatching to specific agent...")
        
        # Update status
        request.status = "In Progress"
        request.updatedAt = datetime.now().isoformat()
        
        # Trigger Celery Task async
        # In a real app, we'd pass the actual Agent ID
        execute_remediation_script.delay(request.scriptContent, "powershell")
        
        # Update Database: Mark Vulnerability as Patched
        db = get_database()
        try:
            # Try to convert to ObjectId, if valid
            try:
                vuln_obj_id = ObjectId(request.vulnerabilityId)
                query = {"_id": vuln_obj_id}
            except:
                # Fallback to string search if ID format differs
                query = {"id": request.vulnerabilityId}  # Legacy support or seeded id

            # Also try matching by string ID in case the seeded data uses 'id' field
            # Ideally we check both but find_one_and_update is simplest
            
            # Simple approach: Try by _id first
            result = await db.vulnerabilities.update_one(
                {"$or": [{"_id": vuln_obj_id if 'vuln_obj_id' in locals() else "dummy"}, {"id": request.vulnerabilityId}]},
                {"$set": {"status": "Patched", "remediatedAt": datetime.now().isoformat()}}
            )
            
            if result.modified_count > 0:
                print(f"🎉 Vulnerability {request.vulnerabilityId} marked as PATCHED in DB.")
                request.status = "Executed" # Or 'Patched'
            else:
                print(f"⚠️ Warning: Could not find vulnerability {request.vulnerabilityId} to patch.")

        except Exception as e:
            print(f"❌ Error updating DB status: {e}")

        return request

