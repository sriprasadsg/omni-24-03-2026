from datetime import datetime, timezone
import uuid
from typing import List, Dict, Any, Optional
from database import get_database
from models import AiModel, AiModelVersion, AiPolicy, AiPolicyRule

class AiGovernanceService:
    def __init__(self, db):
        self.db = db

    # --- Model Registry ---
    async def list_models(self, tenant_id: str) -> List[dict]:
        import logging
        logging.warning(f"[DEBUG] AiGovernanceService.list_models - Requested Tenant: {tenant_id}")
        return await self.db.ai_models.find({"tenantId": tenant_id}, {"_id": 0}).to_list(length=None)

    async def get_model(self, model_id: str, tenant_id: str) -> Optional[dict]:
        return await self.db.ai_models.find_one({"id": model_id, "tenantId": tenant_id}, {"_id": 0})

    async def register_model(self, model_data: AiModel) -> dict:
        # Check if already exists
        existing = await self.db.ai_models.find_one({"id": model_data.id})
        if existing:
            raise ValueError(f"Model ID {model_data.id} already exists.")
        
        await self.db.ai_models.insert_one(model_data.dict())
        return model_data.dict()

    async def add_model_version(self, model_id: str, tenant_id: str, version_data: AiModelVersion) -> dict:
        model = await self.get_model(model_id, tenant_id)
        if not model:
            raise ValueError("Model not found")

        # Check version uniqueness
        if any(v['version'] == version_data.version for v in model.get('versions', [])):
             raise ValueError(f"Version {version_data.version} already exists for this model.")

        await self.db.ai_models.update_one(
            {"id": model_id, "tenantId": tenant_id},
            {
                "$push": {"versions": version_data.dict()},
                "$set": {"currentVersion": version_data.version, "updatedAt": datetime.now(timezone.utc).isoformat()}
            }
        )
        return version_data.dict()
    
    # --- Policy Engine ---
    async def list_policies(self, tenant_id: str) -> List[dict]:
        return await self.db.ai_policies.find({"tenantId": tenant_id}, {"_id": 0}).to_list(length=None)
    
    async def create_policy(self, policy: AiPolicy) -> dict:
        await self.db.ai_policies.insert_one(policy.dict())
        return policy.dict()
    
    async def evaluate_model_compliance(self, model_id: str, tenant_id: str) -> dict:
        """
        Evaluates a single model against all active policies.
        Returns a compliance report.
        """
        model = await self.get_model(model_id, tenant_id)
        if not model:
            return {"error": "Model not found"}
            
        policies = await self.db.ai_policies.find({"tenantId": tenant_id, "isActive": True}, {"_id": 0}).to_list(length=None)
        
        report = {
            "modelId": model_id,
            "modelName": model.get("name"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "compliant": True,
            "violations": []
        }
        
        for policy in policies:
            # Check scope
            scope = policy.get('scope', {})
            if scope.get('framework') and scope['framework'] != model.get('framework'):
                continue
            if scope.get('type') and scope['type'] != model.get('type'):
                continue
                
            for rule in policy.get('rules', []):
                condition = rule.get('condition', '')
                rule_name = rule.get('name', 'Unnamed Rule')
                
                # Dynamic Rule Evaluation
                violation_msg = None
                
                # 1. Framework Match
                if "framework" in condition:
                    required_framework = condition.split("==")[-1].strip().strip("'").strip('"')
                    if model.get('framework') != required_framework:
                        violation_msg = f"Framework '{model.get('framework')}' does not match required '{required_framework}'."
                
                # 2. Risk Level Limit
                elif "riskLevel" in condition:
                    # Simplified: riskLevel in ['Low', 'Medium']
                    if "in" in condition:
                        try:
                            allowed_levels = eval(condition.split("in")[-1].strip())
                            if model.get('riskLevel') not in allowed_levels:
                                violation_msg = f"Risk level '{model.get('riskLevel')}' is not in allowed list: {allowed_levels}."
                        except:
                            violation_msg = "Invalid riskLevel condition format."
                    elif "==" in condition:
                        required_level = condition.split("==")[-1].strip().strip("'").strip('"')
                        if model.get('riskLevel') != required_level:
                            violation_msg = f"Risk level '{model.get('riskLevel')}' does not match required '{required_level}'."

                # 3. Metric Thresholds (e.g. metrics.accuracy > 0.9)
                elif "metrics." in condition:
                    try:
                        parts = condition.split()
                        metric_path = parts[0] # e.g. metrics.accuracy
                        operator = parts[1]    # e.g. <
                        threshold = float(parts[2]) # e.g. 0.9
                        
                        metric_name = metric_path.split(".")[-1]
                        # Get metric from model's current version
                        current_version_str = model.get("currentVersion")
                        current_version = next((v for v in model.get("versions", []) if v["version"] == current_version_str), None)
                        
                        if current_version:
                            val = current_version.get("metrics", {}).get(metric_name)
                            if val is not None:
                                if operator == "<" and not (val < threshold):
                                    violation_msg = f"Metric '{metric_name}' value {val} is not less than {threshold}."
                                elif operator == ">" and not (val > threshold):
                                    violation_msg = f"Metric '{metric_name}' value {val} is not greater than {threshold}."
                                elif operator == "<=" and not (val <= threshold):
                                    violation_msg = f"Metric '{metric_name}' value {val} is not less than or equal to {threshold}."
                                elif operator == ">=" and not (val >= threshold):
                                    violation_msg = f"Metric '{metric_name}' value {val} is not greater than or equal to {threshold}."
                            else:
                                violation_msg = f"Required metric '{metric_name}' is missing from current version."
                        else:
                            violation_msg = "Model has no current version to evaluate metrics."
                    except Exception as e:
                        print(f"Error evaluating metric rule: {e}")
                        violation_msg = f"Rule evaluation error: {str(e)}"

                if violation_msg:
                    report['compliant'] = False
                    report['violations'].append({
                        "policyId": policy.get("id"),
                        "policyName": policy.get("name"),
                        "ruleId": rule.get("id"),
                        "ruleName": rule_name,
                        "message": violation_msg,
                        "severity": rule.get("params", {}).get("severity", "Medium")
                    })
                        
        return report

    async def run_ai_expert_evaluation(self, model_id: str, tenant_id: str) -> dict:
        """
        Runs a deep-dive AI expert evaluation for a model using the SecurityExpert model.
        """
        model = await self.get_model(model_id, tenant_id)
        if not model:
            return {"error": "Model not found"}

        from ai_service import ai_service
        import json

        # Prepare context for the AI
        current_version_str = model.get("currentVersion")
        current_version = next((v for v in model.get("versions", []) if v["version"] == current_version_str), {})
        
        context = {
            "model_name": model.get("name"),
            "description": model.get("description"),
            "framework": model.get("framework"),
            "risk_level": model.get("riskLevel"),
            "metrics": current_version.get("metrics", {})
        }

        prompt = f"""
        You are the 'SecurityExpert', a specialized AI Auditor for ISO 42001 (AI Governance).
        Analyze the following AI model for compliance and ethical alignment.
        
        MODEL CONTEXT:
        {json.dumps(context, indent=2)}

        Provide a structured expert evaluation focusing on:
        1. **Transparency & Accountability**: Risk of black-box behavior.
        2. **Fairness & Non-Discrimination**: Potential for bias based on model type/metrics.
        3. **Security & Robustness**: Vulnerability to adversarial attacks (Prompt injection, data poisoning).
        4. **ISO 42001 Alignment**: Executive opinion on current compliance status.

        Return your response in raw JSON format:
        {{
            "overallScore": 1-100,
            "expertOpinion": "summary of the model's governance state",
            "keyRisks": ["risk1", "risk2"],
            "mitigationRoadmap": ["step1", "step2"],
            "iso42001Status": "Compliant/Warning/Needs Review"
        }}
        """

        try:
            # Force Use of SecurityExpert Model
            # Note: We assume Ollama is config'd to use SecurityExpert if it exists, 
            # or we can pass a 'model' hint if the provider supports it.
            # For this implementation, we'll use the generic generate_text which uses the default (which should be llama3.2:3b/SecurityExpert)
            print(f"[DEBUG] Triggering AI Expert Evaluation for model: {model_id}")
            raw_response = await ai_service.generate_text(prompt)
            print(f"[DEBUG] Raw AI Response: {raw_response[:200]}...") # Log first 200 chars
            
            # More robust extraction
            cleaned_text = raw_response.strip()
            if "```json" in cleaned_text:
                cleaned_text = cleaned_text.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned_text:
                cleaned_text = cleaned_text.split("```")[1].split("```")[0].strip()
                
            print(f"[DEBUG] Cleaned JSON Text: {cleaned_text}")
            result = json.loads(cleaned_text)
            
            # Save to Database as an 'Expert Scan'
            scan_id = str(uuid.uuid4())
            scan_record = {
                "id": scan_id,
                "modelId": model_id,
                "tenantId": tenant_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "Expert Scan",
                "result": result
            }
            await self.db.ai_governance_scans.insert_one(scan_record)
            
            return scan_record
        except Exception as e:
            print(f"Expert Evaluation Failed: {e}")
            return {"error": f"AI Expert evaluation failed: {str(e)}"}

def get_ai_governance_service(db):
    return AiGovernanceService(db)
