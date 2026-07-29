import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase
from database import get_database
from rbac_utils import require_permission
from ai_auditor_service import get_auditor

_AUDITOR_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}

logger = logging.getLogger("ai_auditor_api")
router = APIRouter()


@router.get("/audit-framework/{framework_id}")
async def get_audit_framework(
    framework_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:compliance")),
):
    """
    Retrieves details for a specific compliance framework.
    """
    caller_tenant = (
        current_user.get("tenant_id") if isinstance(current_user, dict)
        else getattr(current_user, "tenant_id", None)
    )
    # Built-in frameworks are global (tenantId: None/"global"/absent) — a
    # tenant-only equality filter made every built-in framework 404 for
    # tenant users. Scope: caller's own frameworks OR the global registry.
    fw_filter: dict = {"id": framework_id}
    if caller_tenant:
        fw_filter["$or"] = [
            {"tenantId": caller_tenant},
            {"tenantId": {"$in": [None, "global"]}},
            {"tenantId": {"$exists": False}},
        ]

    framework = await db.compliance_frameworks.find_one(fw_filter)
    if not framework:
        raise HTTPException(status_code=404, detail="Framework not found or not accessible")

    framework.pop("_id", None)
    return framework


@router.post("/audit-framework/{framework_id}")
async def audit_framework_evidence(
    framework_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:compliance")),
):
    """
    Triggers the local LLM to evaluate all collected evidence for a specific framework.
    Runs in background to prevent timeouts.
    """
    logger.info("[AI AUDITOR] Starting audit for framework: %s", framework_id)

    # 1. Fetch Framework Controls — scope to caller's tenant unless super admin
    caller_tenant = (
        current_user.get("tenant_id") if isinstance(current_user, dict)
        else getattr(current_user, "tenant_id", None)
    )
    caller_role = (
        current_user.get("role") if isinstance(current_user, dict)
        else getattr(current_user, "role", None)
    )
    # Same global-framework scope as the GET route above: tenant users may
    # audit their own frameworks AND the built-in global registry entries
    # (tenantId None/"global"/absent) — evidence reads below stay scoped to
    # the caller's tenant via the tenant-isolated db handle.
    fw_filter: dict = {"id": framework_id}
    if caller_role not in _AUDITOR_SUPER_ROLES and caller_tenant:
        fw_filter["$or"] = [
            {"tenantId": caller_tenant},
            {"tenantId": {"$in": [None, "global"]}},
            {"tenantId": {"$exists": False}},
        ]
    framework = await db.compliance_frameworks.find_one(fw_filter)
    if not framework:
        logger.error("[AI AUDITOR] Framework not found: %s", framework_id)
        raise HTTPException(status_code=404, detail="Framework not found")

    controls_map = {c["id"]: c for c in framework.get("controls", [])}
    if not controls_map:
        return {"status": "success", "message": "No controls to audit"}

    async def run_ai_audit_task():
        logger.info("[AI AUDITOR] Background task started for %s", framework_id)
        auditor = get_auditor()

        # 2. Fetch Evidence
        asset_compliance = await db.asset_compliance.find(
            {"controlId": {"$in": list(controls_map.keys())}}
        ).to_list(length=500)

        logger.info("[AI AUDITOR] Found %d asset-control pairs with evidence.", len(asset_compliance))

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

            logger.debug("[AI AUDITOR] Evaluating %s for asset %s", control_id, ac.get("assetId"))

            # Run inference (async — routes through the shared local AI provider)
            try:
                ai_result = await auditor.evaluate_evidence(
                    framework_name=framework.get("name", framework_id),
                    control_desc=control_desc,
                    evidence_text=combined_evidence,
                )

                verified = ai_result.get("verified", False)
                reasoning = ai_result.get("reasoning", "AI Error")
                evaluation_record = {
                    "verified": verified,
                    "reasoning": reasoning,
                    "evaluatedAt": ai_result.get("evaluatedAt"),
                    "model_used": auditor.model_id,
                }

                # Populate the columns the compliance UI reads: Findings (reason)
                # from the auditor's reasoning, and Suggested Actions (remediation)
                # generated by the LLM for FAILED controls only.
                set_fields = {"ai_evaluation": evaluation_record, "reason": reasoning}
                if not verified:
                    try:
                        from ai_service import ai_service
                        suggestion = await ai_service.suggest_remediation(
                            control_id=control_id,
                            control_description=control_desc,
                            failure_reason=reasoning,
                            asset_context=str(ac.get("assetId", "")),
                        )
                        if suggestion:
                            set_fields["remediation"] = suggestion
                    except Exception as sx:
                        logger.warning("[AI AUDITOR] remediation suggestion failed for %s: %s", control_id, sx)

                await db.asset_compliance.update_one(
                    {"_id": ac["_id"]},
                    {"$set": set_fields},
                )
                evaluated_count += 1
                verdict = "PASS" if verified else "FAIL"
                logger.info("[AI AUDITOR] %s -> %s (%d evaluated)", control_id, verdict, evaluated_count)
            except Exception as e:
                logger.error("[AI AUDITOR] Error evaluating %s: %s", control_id, e)

        logger.info(
            "[AI AUDITOR] Framework audit complete: %s (%d controls evaluated)",
            framework_id, evaluated_count,
        )

    # Start background task
    background_tasks.add_task(run_ai_audit_task)

    return {
        "status": "success",
        "message": f"AI Auditor started in background. Evaluation for {len(controls_map)} controls initiated.",
    }
