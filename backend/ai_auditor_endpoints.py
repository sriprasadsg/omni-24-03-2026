import logging
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from database import get_database
from rbac_utils import require_permission
from ai_auditor_service import get_auditor

logger = logging.getLogger("ai_auditor_api")
router = APIRouter()

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

@router.post("/audit-framework/{framework_id}")
async def audit_framework_evidence(
    framework_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Triggers the local LLM to evaluate all collected evidence for a specific framework.
    Runs in background to prevent timeouts.
    """
    print(f"\n[AI AUDITOR] --- Starting Audit for {framework_id} ---")
    
    # 1. Fetch Framework Controls
    framework = await db.compliance_frameworks.find_one({"id": framework_id})
    if not framework:
        print(f"[AI AUDITOR] Error: Framework {framework_id} not found")
        raise HTTPException(status_code=404, detail="Framework not found")
        
    controls_map = {c["id"]: c for c in framework.get("controls", [])}
    if not controls_map:
        return {"status": "success", "message": "No controls to audit"}

    async def run_ai_audit_task():
        print(f"[AI AUDITOR] Background Task Started for {framework_id}")
        auditor = get_auditor()
        
        # 2. Fetch Evidence
        asset_compliance = await db.asset_compliance.find(
            {"controlId": {"$in": list(controls_map.keys())}}
        ).to_list(length=500)
        
        print(f"[AI AUDITOR] Found {len(asset_compliance)} asset-control pairs with evidence.")
        
        evaluated_count = 0
        
        for ac in asset_compliance:
            control_id = ac.get("controlId")
            evidence_list = ac.get("evidence", [])
            
            if not evidence_list:
                continue
                
            ctrl = controls_map.get(control_id, {})
            control_desc = ctrl.get("description", "") + " " + ctrl.get("name", "")
            
            # Combine all technical evidence content
            combined_evidence = ""
            for ev in evidence_list:
                content = ev.get("content", "") or ev.get("details", "")
                if content:
                    combined_evidence += f"\n--- Evidence: {ev.get('name')} ---\n{content}\n"

            if not combined_evidence.strip():
                continue
            
            print(f"[AI AUDITOR] [{evaluated_count+1}] Evaluating {control_id} for asset {ac.get('assetId')}...")
            
            # Run inference
            try:
                ai_result = auditor.evaluate_evidence(
                    framework_name=framework.get("name", framework_id),
                    control_desc=control_desc,
                    evidence_text=combined_evidence
                )
                
                evaluation_record = {
                    "verified": ai_result.get("verified", False),
                    "reasoning": ai_result.get("reasoning", "AI Error"),
                    "evaluatedAt": ai_result.get("evaluatedAt"),
                    "model_used": auditor.model_id
                }
                
                # Update Database
                await db.asset_compliance.update_one(
                    {"_id": ac["_id"]},
                    {"$set": {"ai_evaluation": evaluation_record}}
                )
                evaluated_count += 1
                print(f"[AI AUDITOR] [{evaluated_count}] DONE: {control_id} -> {'PASS' if ai_result['verified'] else 'FAIL'}")
            except Exception as e:
                print(f"[AI AUDITOR] Error evaluating {control_id}: {e}")

        print(f"[AI AUDITOR] --- Framework Audit Complete: {framework_id} ({evaluated_count} controls evaluated) ---")

    # Start background task
    background_tasks.add_task(run_ai_audit_task)

    return {
        "status": "success", 
        "message": f"AI Auditor started in background. Evaluation for {len(controls_map)} controls initiated."
    }
