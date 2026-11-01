import sys
import os
from pathlib import Path

from celery_app import celery_app

@celery_app.task(name='tasks.add')
def add(x, y):
    """
    Simple task to verify Celery worker is up and running.
    """
    return x + y

@celery_app.task(name='tasks.run_agent_task_async')
def run_agent_task_async(task_description: str, agent_id: str = "default"):
    """
    Retired: this used to run agent capabilities on the worker host itself, so
    instructions meant for an endpoint (some derived from ticket text) would run
    on the platform server. Instructions now go to the target agent through
    agent_instructions. Messages already queued drain here without executing.
    """
    print(f"[Worker] Refusing local agent task for {agent_id!r}: {task_description[:80]!r}")
    return {
        "status": "refused",
        "error": "Agent instructions are delivered to the endpoint agent, never run on the worker",
    }

@celery_app.task(name='tasks.execute_remediation_script')
def execute_remediation_script(script_content: str, language: str = "powershell", agent_id: str = None, tenant_id: str = None):
    """
    Fenced (RESP-11, D-18). This task used to queue a script for an endpoint agent and poll for
    its result, outside the Autonomous Ops gate. It now sends nothing, opens no database client
    and answers not_sent at once. Containment and remediation are decided in Autonomous Ops.
    """
    from autonomous_ops.response_messages import FENCE

    print(f"[Worker] Not sent: remediation script ({language}) for agent {agent_id}")
    return {"status": "not_sent", "output": FENCE["worker"]}

@celery_app.task(name='tasks.run_periodic_patch_scan')
def run_periodic_patch_scan():
    """
    Periodic task that checks for SLA breaches in the software inventory. It no longer queues
    software-scan instructions for agents (RESP-11, D-18).
    """
    from pymongo import MongoClient
    from datetime import datetime, timezone
    from patch_service import get_patch_service
    
    mongo_url = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    client = MongoClient(mongo_url)
    db = client['omni-agent']
    
    print("[Worker] Running periodic patch scan...")
    
    # 1. The loop that queued a software-scan instruction per active agent was removed (RESP-11,
    #    D-18): it wrote the old instructions collection, which nothing reads.

    # 2. Check for SLA breaches in existing inventory
    patch_service = get_patch_service()
    outdated_items = list(db.software_inventory.find({"is_outdated": True}))
    
    breach_count = 0
    for item in outdated_items:
        sla_check = patch_service.check_software_sla(item)
        if sla_check["breached"]:
            breach_count += 1
            # Log as a compliance alert
            db.compliance_alerts.update_one(
                {"package_name": item["name"], "agent_id": item["agent_id"]},
                {"$set": {
                    "tenant_id": item.get("tenant_id"),
                    "agent_name": item.get("agent_name"),
                    "package_name": item["name"],
                    "current_version": item["current_version"],
                    "latest_version": item["latest_version"],
                    "update_status": item["update_status"],
                    "sla_days": sla_check["sla_days"],
                    "age_days": sla_check["age_days"],
                    "breach_date": datetime.now(timezone.utc).isoformat(),
                    "status": "active_breach"
                }},
                upsert=True
            )
            
    print(f"[Worker] Periodic scan complete. Triggered 0 agent scans. Found {breach_count} SLA breaches.")
    return {"scans_triggered": 0, "breaches_found": breach_count}

