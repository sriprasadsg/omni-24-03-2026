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
                            import ast
                            raw_list = condition.split("in")[-1].strip()
                            allowed_levels = ast.literal_eval(raw_list)
                            if not isinstance(allowed_levels, (list, tuple)):
                                raise ValueError("condition must evaluate to a list")
                            if model.get('riskLevel') not in allowed_levels:
                                violation_msg = f"Risk level '{model.get('riskLevel')}' is not in allowed list: {allowed_levels}."
                        except Exception:
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
                        
        # ── Composite risk score ───────────────────────────────────────────────
        severity_deductions = {"Critical": 25, "High": 15, "Medium": 8, "Low": 3}
        model_risk_penalties = {"Critical": 20, "High": 10, "Medium": 5, "Low": 0}

        risk_score = 100
        for v in report["violations"]:
            sev = v.get("severity", "Medium")
            risk_score -= severity_deductions.get(sev, 8)

        model_risk = model.get("riskLevel", "Low")
        risk_score -= model_risk_penalties.get(model_risk, 0)
        risk_score = max(0, min(100, risk_score))

        total_rules = sum(len(p.get("rules", [])) for p in policies)
        compliance_pct = round(
            (1 - len(report["violations"]) / max(total_rules, 1)) * 100, 1
        )

        if risk_score >= 80:
            risk_label = "Low"
        elif risk_score >= 60:
            risk_label = "Medium"
        elif risk_score >= 35:
            risk_label = "High"
        else:
            risk_label = "Critical"

        report["risk_score"] = risk_score
        report["risk_level"] = risk_label
        report["compliance_pct"] = compliance_pct
        report["total_policies_checked"] = len(policies)
        report["total_rules_checked"] = total_rules

        # Persist compliance snapshot
        try:
            snap = {**report, "evaluatedAt": report["timestamp"]}
            await self.db.ai_compliance_snapshots.update_one(
                {"modelId": model_id, "tenantId": tenant_id},
                {"$set": snap},
                upsert=True,
            )
        except Exception:
            pass

        return report

    async def get_governance_dashboard(self, tenant_id: str) -> dict:
        """Return aggregated AI governance health stats for the tenant."""
        models = await self.list_models(tenant_id)
        policies = await self.list_policies(tenant_id)
        active_policies = [p for p in policies if p.get("isActive")]

        snapshots = await self.db.ai_compliance_snapshots.find(
            {"tenantId": tenant_id}, {"_id": 0}
        ).to_list(length=None)

        snap_map = {s["modelId"]: s for s in snapshots}

        total_models = len(models)
        compliant = sum(1 for m in models if snap_map.get(m["id"], {}).get("compliant", False))
        avg_risk = 0
        risk_dist = {"Low": 0, "Medium": 0, "High": 0, "Critical": 0}
        total_violations = 0

        for m in models:
            snap = snap_map.get(m["id"])
            if snap:
                score = snap.get("risk_score", 100)
                avg_risk += score
                rl = snap.get("risk_level", "Low")
                risk_dist[rl] = risk_dist.get(rl, 0) + 1
                total_violations += len(snap.get("violations", []))

        if total_models:
            avg_risk = round(avg_risk / total_models, 1)

        return {
            "total_models": total_models,
            "compliant_models": compliant,
            "non_compliant_models": total_models - compliant,
            "compliance_rate": round(compliant / max(total_models, 1) * 100, 1),
            "average_risk_score": avg_risk,
            "risk_distribution": risk_dist,
            "total_violations": total_violations,
            "active_policies": len(active_policies),
            "total_policies": len(policies),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

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

    async def compute_bias_metrics(self, model_id: str, tenant_id: str) -> dict:
        """
        Compute fairness/bias metrics from the model's prediction history.
        Uses demographic parity, equalized odds proxy, and calibration gap derived
        from prediction_feedback documents tagged with group labels.
        Falls back to metadata-based heuristics when feedback data is sparse.
        """
        model = await self.get_model(model_id, tenant_id)
        if not model:
            return {"error": "Model not found"}

        # Gather recent feedback with optional group labels
        feedback = await self.db.prediction_feedback.find(
            {"model_id": model_id},
            {"_id": 0, "outcome": 1, "group": 1, "predicted": 1, "actual": 1},
        ).limit(2000).to_list(length=2000)

        now = datetime.now(timezone.utc).isoformat()

        if len(feedback) < 10:
            # Not enough data — derive heuristic scores from model metadata
            risk = model.get("riskLevel", "Low")
            heuristic = {"Low": 85, "Medium": 70, "High": 50, "Critical": 30}
            base_score = heuristic.get(risk, 70)
            result = {
                "model_id": model_id,
                "computed_at": now,
                "data_points": len(feedback),
                "data_source": "heuristic",
                "demographic_parity_gap": None,
                "equalized_odds_gap": None,
                "calibration_gap": None,
                "fairness_score": base_score,
                "bias_detected": base_score < 60,
                "risk_level": risk,
                "recommendation": (
                    "Insufficient prediction feedback to compute real bias metrics. "
                    "Score is estimated from model risk level. "
                    "Submit prediction outcomes with group labels to enable real fairness analysis."
                ),
            }
        else:
            # Group feedback by 'group' label (any string — e.g. 'male'/'female', 'A'/'B')
            groups: dict = {}
            for fb in feedback:
                g = fb.get("group", "unknown")
                groups.setdefault(g, {"correct": 0, "total": 0, "pos_pred": 0, "pos_actual": 0})
                groups[g]["total"] += 1
                if fb.get("outcome") == "correct":
                    groups[g]["correct"] += 1
                if fb.get("predicted") in (1, True, "1", "positive"):
                    groups[g]["pos_pred"] += 1
                if fb.get("actual") in (1, True, "1", "positive"):
                    groups[g]["pos_actual"] += 1

            rates = {g: v["correct"] / max(v["total"], 1) for g, v in groups.items()}
            pred_rates = {g: v["pos_pred"] / max(v["total"], 1) for g, v in groups.items()}
            actual_rates = {g: v["pos_actual"] / max(v["total"], 1) for g, v in groups.items()}

            rate_vals = list(rates.values())
            pred_vals = list(pred_rates.values())
            actual_vals = list(actual_rates.values())

            dp_gap = round(max(pred_vals) - min(pred_vals), 3) if len(pred_vals) >= 2 else 0.0
            eo_gap = round(max(actual_vals) - min(actual_vals), 3) if len(actual_vals) >= 2 else 0.0
            cal_gap = round(max(rate_vals) - min(rate_vals), 3) if len(rate_vals) >= 2 else 0.0

            # Lower gap = fairer; map to 0-100 score
            max_gap = max(dp_gap, eo_gap, cal_gap)
            fairness_score = max(0, round((1 - max_gap) * 100, 1))
            bias_detected = max_gap > 0.10  # >10% gap considered significant

            result = {
                "model_id": model_id,
                "computed_at": now,
                "data_points": len(feedback),
                "data_source": "feedback",
                "groups_analyzed": list(groups.keys()),
                "accuracy_by_group": {g: round(r, 3) for g, r in rates.items()},
                "positive_prediction_rate_by_group": {g: round(r, 3) for g, r in pred_rates.items()},
                "demographic_parity_gap": dp_gap,
                "equalized_odds_gap": eo_gap,
                "calibration_gap": cal_gap,
                "fairness_score": fairness_score,
                "bias_detected": bias_detected,
                "recommendation": (
                    f"Bias detected — max gap {max_gap:.2%}. "
                    "Review training data distribution and apply re-weighting or adversarial debiasing."
                    if bias_detected else
                    "No significant bias detected across groups in prediction outcomes."
                ),
            }

        # Persist the bias audit result
        await self.db.ai_bias_audits.update_one(
            {"model_id": model_id, "tenant_id": tenant_id},
            {"$set": {**result, "tenant_id": tenant_id}},
            upsert=True,
        )
        return result


def get_ai_governance_service(db):
    return AiGovernanceService(db)
