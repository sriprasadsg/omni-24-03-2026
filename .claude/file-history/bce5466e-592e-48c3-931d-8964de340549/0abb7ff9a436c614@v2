"""
Automated compliance evidence collection service.

Responsibilities:
  1. Build a reverse mapping: control_id -> [check_names that produce evidence for it]
  2. Detect coverage gaps: controls with no evidence collected in the last N days
  3. Dispatch collection sweeps: send 'Run Compliance Checks' instructions to all
     active agents so they include the relevant checks in their next heartbeat
  4. Run a scheduled background loop (called from app_background_tasks.py)

Sweep interval: every 6 hours by default (configurable via COMPLIANCE_SWEEP_INTERVAL_H env var).
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("compliance_auto_evidence")

_SWEEP_INTERVAL_H = float(os.getenv("COMPLIANCE_SWEEP_INTERVAL_H", "6"))


# ---------------------------------------------------------------------------
# Reverse mapping: control_id -> check_names
# ---------------------------------------------------------------------------

_reverse_map: dict[str, list[str]] = {}


def get_reverse_mapping() -> dict[str, list[str]]:
    """Return (and lazily build) the control_id → check_names reverse mapping."""
    global _reverse_map
    if _reverse_map:
        return _reverse_map

    from compliance_evidence_processor import COMPLIANCE_CHECK_MAPPINGS

    rev: dict[str, list[str]] = {}
    for check_name, control_ids in COMPLIANCE_CHECK_MAPPINGS.items():
        for ctrl in control_ids:
            rev.setdefault(ctrl, []).append(check_name)

    _reverse_map = rev
    logger.info(
        "[AutoEvidence] Reverse mapping built: %d controls, %d checks",
        len(rev),
        len(COMPLIANCE_CHECK_MAPPINGS),
    )
    return rev


def checks_for_control(control_id: str) -> list[str]:
    """Return the check names that can provide evidence for the given control."""
    return get_reverse_mapping().get(control_id, [])


# ---------------------------------------------------------------------------
# Coverage gap detection
# ---------------------------------------------------------------------------

async def get_coverage_gaps(
    db,
    tenant_id: Optional[str],
    since_days: int = 30,
    framework_id: Optional[str] = None,
) -> dict:
    """
    Identify compliance controls with no evidence collected within the last
    `since_days` days.

    Returns a dict:
      {
        "total_controls": int,
        "covered": int,
        "gap_controls": [{"controlId": ..., "frameworkId": ..., "checks": [...]}],
      }
    """
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
    rev = get_reverse_mapping()

    # Load controls from DB
    fw_query: dict = {}
    if framework_id:
        fw_query["id"] = framework_id
    if tenant_id:
        fw_query["$or"] = [{"tenantId": tenant_id}, {"tenantId": {"$exists": False}}]

    try:
        frameworks = await db.compliance_frameworks.find(fw_query).to_list(length=200)
    except Exception:
        frameworks = []

    all_controls: list[dict] = []
    for fw in frameworks:
        for ctrl in fw.get("controls", []):
            ctrl_id = ctrl.get("id") or ctrl.get("controlId") or ""
            if ctrl_id:
                all_controls.append({"controlId": ctrl_id, "frameworkId": fw.get("id", "")})

    if not all_controls:
        # Fall back to mapping keys when DB has no framework data
        for ctrl_id in rev:
            all_controls.append({"controlId": ctrl_id, "frameworkId": "auto"})

    # Check which controls have recent evidence
    asset_query: dict = {"evidence.collectedAt": {"$gte": since}}
    if tenant_id:
        asset_query["tenantId"] = tenant_id

    try:
        covered_docs = await db.asset_compliance.find(
            asset_query, {"controlId": 1}
        ).to_list(length=10000)
        covered_ids = {d["controlId"] for d in covered_docs if d.get("controlId")}
    except Exception:
        covered_ids = set()

    gaps = []
    for entry in all_controls:
        ctrl_id = entry["controlId"]
        if ctrl_id not in covered_ids:
            gaps.append({
                "controlId": ctrl_id,
                "frameworkId": entry["frameworkId"],
                "checks": checks_for_control(ctrl_id),
            })

    return {
        "total_controls": len(all_controls),
        "covered": len(all_controls) - len(gaps),
        "gap_count": len(gaps),
        "coverage_pct": round(
            100 * (len(all_controls) - len(gaps)) / max(len(all_controls), 1), 1
        ),
        "gap_controls": gaps,
        "since_days": since_days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Dispatch collection sweep
# ---------------------------------------------------------------------------

async def dispatch_collection_sweep(db, tenant_id: Optional[str] = None) -> dict:
    """
    Send 'Run Compliance Scan' instructions to all active agents.
    Agents will execute their compliance checks and include results
    in their next heartbeat, which `process_automated_evidence` then maps
    to control IDs automatically.

    Returns a summary of how many agents were targeted.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Find agents active in the last 10 minutes
    recent_threshold = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    agent_query: dict = {
        "$or": [
            {"status": "Online"},
            {"lastSeen": {"$gte": recent_threshold}},
        ]
    }
    if tenant_id:
        agent_query["tenantId"] = tenant_id

    try:
        agents = await db.agents.find(agent_query, {"id": 1, "hostname": 1, "tenantId": 1}).to_list(length=1000)
    except Exception as exc:
        logger.error("[AutoEvidence] Failed to query agents: %s", exc)
        return {"dispatched": 0, "error": str(exc)}

    if not agents:
        logger.info("[AutoEvidence] No active agents found for sweep (tenant=%s)", tenant_id)
        return {"dispatched": 0}

    instructions = [
        {
            "agent_id": agent["id"],
            "instruction": "Run Compliance Scan",
            "status": "pending",
            "created_at": now,
            "created_by": "auto_evidence_sweep",
            "priority": "normal",
            "tenantId": agent.get("tenantId"),
        }
        for agent in agents
        if agent.get("id")
    ]

    if instructions:
        try:
            await db.agent_instructions.insert_many(instructions)
        except Exception as exc:
            logger.error("[AutoEvidence] Failed to insert instructions: %s", exc)
            return {"dispatched": 0, "error": str(exc)}

    logger.info(
        "[AutoEvidence] Dispatched compliance sweep to %d agent(s) (tenant=%s)",
        len(instructions),
        tenant_id or "all",
    )
    return {
        "dispatched": len(instructions),
        "agent_ids": [a["id"] for a in agents if a.get("id")],
        "swept_at": now,
    }


async def dispatch_sweep_all_tenants(db) -> dict:
    """Sweep all tenants — called from the scheduled background loop."""
    try:
        tenants = await db.tenants.find({}, {"id": 1}).to_list(length=500)
    except Exception as exc:
        logger.error("[AutoEvidence] Failed to load tenants: %s", exc)
        return {"total_dispatched": 0}

    total = 0
    for tenant in tenants:
        tid = tenant.get("id")
        if not tid:
            continue
        result = await dispatch_collection_sweep(db, tenant_id=tid)
        total += result.get("dispatched", 0)

    logger.info("[AutoEvidence] Full sweep complete: %d instructions across all tenants", total)
    return {"total_dispatched": total, "swept_at": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# Scheduled background loop
# ---------------------------------------------------------------------------

async def compliance_evidence_sweep_loop() -> None:
    """
    Background loop: every COMPLIANCE_SWEEP_INTERVAL_H hours, dispatch a
    compliance collection sweep to all active agents across all tenants.
    """
    interval_s = _SWEEP_INTERVAL_H * 3600
    logger.info(
        "[AutoEvidence] Evidence sweep loop started (interval=%.0fh)", _SWEEP_INTERVAL_H
    )

    # Initial delay of 5 minutes so the server finishes startup first
    await asyncio.sleep(300)

    while True:
        try:
            from database import get_database
            from tenant_context import set_tenant_id

            set_tenant_id("platform-admin")
            db = get_database()
            result = await dispatch_sweep_all_tenants(db)
            logger.info("[AutoEvidence] Sweep: %s", result)
        except Exception as exc:
            logger.error("[AutoEvidence] Sweep loop error: %s", exc)

        await asyncio.sleep(interval_s)
