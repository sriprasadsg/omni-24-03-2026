from ai_service import ai_service
import json
from database import get_database

class AIRemediationService:
    def __init__(self):
        self.model = None
        self.is_configured = False

        pass # Initialization handled by ai_service

    async def generate_cspm_remediation(self, finding: dict):
        """Generate remediation plan for CSPM finding"""
        if not self.is_configured:
            await self.initialize()
            
        if not self.is_configured:
            return {"remediation": "AI Service not configured. Please set API Key in Settings."}

        prompt = f"""
        Provide a detailed remediation plan for this cloud security finding:
        Title: {finding.get('title')}
        Provider: {finding.get('provider')}
        Description: {finding.get('description')}
        Resource: {finding.get('resourceId')}
        
        Include:
        1. Explanation of the risk
        2. Step-by-step manual remediation
        3. CLI commands if applicable
        """
        
        try:
            response_text = await ai_service.generate_text(prompt, source="remediation")
            return {"remediation": response_text}
        except Exception as e:
            return {"remediation": f"Error generating remediation: {str(e)}"}

    async def generate_iac_fix(self, finding: dict):
        """Generate Terraform/IaC code to fix the finding"""
        if not self.is_configured:
            await self.initialize()
            
        if not self.is_configured:
            return {"code": "# AI Service not configured"}

        prompt = f"""
        Generate Terraform (HCL) code to fix this security issue:
        Title: {finding.get('title')}
        Resource: {finding.get('resourceId')}
        Provider: {finding.get('provider')}
        
        Return ONLY the code block.
        """
        
        try:
            response_text = await ai_service.generate_text(prompt, source="iac_fix")
            text = response_text
            # Extract code block
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("hcl") or text.startswith("terraform"):
                    text = text.split("\n", 1)[1]
            return {"code": text.strip()}
        except Exception as e:
            return {"code": f"# Error generating code: {str(e)}"}

ai_remediation_service = AIRemediationService()
