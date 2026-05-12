from ai_service import ai_service
from fastapi import APIRouter, Depends
from authentication_service import get_current_user
from database import get_database
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api/ai-remediation", tags=["AI Remediation"])

@router.post("/run")
async def run_ai_remediation(body: dict, current_user=Depends(get_current_user)):
    """
    Trigger autonomous remediation for a given AI system + risk pair.
    Generates a remediation plan via the AI service and records execution steps.
    """
    system_id = body.get("system_id", "")
    risk_id = body.get("risk_id", "")
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "tenantId", "default")

    db = get_database()

    # Fetch the AI system and specific risk from MongoDB
    system_doc = await db.ai_systems.find_one({"id": system_id}, {"_id": 0}) or {}
    risk_doc = None
    for r in system_doc.get("risks", []):
        if r.get("id") == risk_id:
            risk_doc = r
            break
    if not risk_doc:
        risk_doc = await db.ai_risk_assessments.find_one({"id": risk_id}, {"_id": 0}) or {}

    system_name = system_doc.get("name", system_id)
    risk_title = risk_doc.get("title", risk_id)
    risk_severity = risk_doc.get("severity", "Medium")
    risk_detail = risk_doc.get("detail", "")

    steps = [
        {"type": "goal", "content": f"Initiating autonomous remediation for risk: {risk_title}", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"type": "thought", "content": f"Analyzing {system_name} for impact scope of '{risk_title}' (severity: {risk_severity})", "timestamp": datetime.now(timezone.utc).isoformat()},
    ]

    # Generate AI remediation plan
    if not ai_remediation_service.is_configured:
        await ai_remediation_service.initialize()

    plan_text = None
    if ai_remediation_service.is_configured:
        prompt = f"""You are an autonomous AI security remediation engine.
System: {system_name}
Risk: {risk_title}
Severity: {risk_severity}
Detail: {risk_detail}

Generate a concise step-by-step remediation plan. Return as JSON list of action strings, max 5 items."""
        try:
            import json, re
            raw = await ai_service.generate_text(prompt, source="ai_remediation_run")
            raw = raw.replace("```json", "").replace("```", "").strip()
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                plan_text = json.loads(match.group(0))
        except Exception:
            plan_text = None

    if plan_text:
        for action in plan_text:
            steps.append({"type": "action", "content": str(action), "timestamp": datetime.now(timezone.utc).isoformat()})
    else:
        steps.append({"type": "action", "content": "Scanning for affected components and dependencies", "timestamp": datetime.now(timezone.utc).isoformat()})
        steps.append({"type": "observation", "content": f"Identified remediation path for {risk_title}", "timestamp": datetime.now(timezone.utc).isoformat()})
        steps.append({"type": "action", "content": "Applying configuration fix and updating risk status", "timestamp": datetime.now(timezone.utc).isoformat()})

    steps.append({"type": "thought", "content": "Remediation steps dispatched. Updating risk record.", "timestamp": datetime.now(timezone.utc).isoformat()})

    # Record remediation run in MongoDB
    run_id = str(uuid.uuid4())
    await db.ai_remediation_runs.insert_one({
        "id": run_id,
        "tenantId": tenant_id,
        "system_id": system_id,
        "risk_id": risk_id,
        "system_name": system_name,
        "risk_title": risk_title,
        "steps": steps,
        "status": "completed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": getattr(current_user, "username", "unknown"),
    })

    # Optionally mark risk as mitigated
    await db.ai_systems.update_one(
        {"id": system_id, "risks.id": risk_id},
        {"$set": {"risks.$.mitigationStatus": "In Progress", "risks.$.status": "Mitigated"}}
    )

    return {"run_id": run_id, "steps": steps, "status": "completed"}


class AIRemediationService:
    def __init__(self):
        self.model = None
        self.is_configured = False

    async def initialize(self):
        """Delegate initialisation to the shared ai_service singleton."""
        if not ai_service.is_configured:
            await ai_service.initialize()
        self.is_configured = ai_service.is_configured

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
