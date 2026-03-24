import sys
import os
from pathlib import Path

# Add 'agent' directory to sys.path
agent_dir = str(Path(__file__).parent.parent / "agent")
if agent_dir not in sys.path:
    sys.path.append(agent_dir)

from celery_app import celery_app

# Import Agent Components (Lazy import inside task to avoid import errors during worker startup if path issues)
# But here we try top-level
try:
    from agent import AgentCapabilityManager, load_config
except ImportError:
    # If running from backend dir, agent might not be found without sys.path
    pass

@celery_app.task(name='tasks.add')
def add(x, y):
    """
    Simple task to verify Celery worker is up and running.
    """
    time.sleep(2) # Simulate work
    return x + y

@celery_app.task(name='tasks.run_agent_task_async')
def run_agent_task_async(task_description: str, agent_id: str = "default"):
    """
    Executes the actual Agent Logic in a background process.
    """
    print(f"[Worker] Starting Agent Task: {task_description}")
    
    try:
        from agent import AgentCapabilityManager, load_config
        
        # 1. Load Config
        cfg = load_config()
        
        # 2. Initialize Agent
        print("... Initializing Agent Manager ...")
        manager = AgentCapabilityManager(cfg)
        manager.fetch_configuration() # Hydrate from backend if needed
        
        # 3. Execute Instruction
        print("... Executing Instruction ...")
        result = manager.execute_single_instruction(task_description)
        
        return result
        
    except Exception as e:
        print(f"[Worker] Task Failed: {e}")
        return {
            "status": "failed",
            "error": str(e)
        }

@celery_app.task(name='tasks.execute_remediation_script')
def execute_remediation_script(script_content: str, language: str = "powershell"):
    """
    Executes a remediation script (PowerShell/Bash) securely.
    IN REALITY: This would send a command to the actual Agent via WebSocket/HTTP.
    FOR DEMO: We simulate execution.
    """
    import time
    print(f"[Worker] Executing Remediation Script ({language})...")
    print(f"Content: {script_content[:50]}...")
    
    time.sleep(3) # Simulate execution time
    
    # Mock Success
    return {
        "status": "success",
        "output": "Package updated successfully. Service restarted. Vulnerability mitigated."
    }

@celery_app.task(name='tasks.run_periodic_patch_scan')
def run_periodic_patch_scan():
    """
    Periodic task to trigger software scans on active agents and check for SLA breaches.
    """
    from pymongo import MongoClient
    from datetime import datetime, timezone
    from patch_service import get_patch_service
    
    mongo_url = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    client = MongoClient(mongo_url)
    db = client['omni-agent']
    
    print("[Worker] Running periodic patch scan...")
    
    # 1. Trigger scans for active agents
    active_agents_list = list(db.agents.find({
        "last_seen": {"$gt": datetime.now(timezone.utc).timestamp() - 3600} # Active in last hour
    }))
    
    for agent in active_agents_list:
        agent_id = str(agent.get("_id") or agent.get("id"))
        tenant_id = agent.get("tenant_id")
        
        # Add 'run_software_scan' instruction
        db.instructions.insert_one({
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "type": "run_software_scan",
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    
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
            
    print(f"[Worker] Periodic scan complete. Triggered {len(active_agents_list)} agent scans. Found {breach_count} SLA breaches.")
    return {"scans_triggered": len(active_agents_list), "breaches_found": breach_count}

