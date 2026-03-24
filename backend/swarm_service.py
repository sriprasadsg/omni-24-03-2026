from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any
import uuid
import time
import asyncio

router = APIRouter(prefix="/api/swarm", tags=["Swarm"])

class SwarmMission(BaseModel):
    goal: str
    priority: str

class AgentMessage(BaseModel):
    agent_name: str
    role: str
    message: str
    timestamp: float

# In-memory store
missions = {}

async def run_swarm_lifecycle(mission_id: str, goal: str):
    """Simulates the autonomous swarm loop"""
    # 1. Coordinator Planning
    await asyncio.sleep(2)
    if mission_id in missions:
       missions[mission_id]["logs"].append(AgentMessage(
        agent_name="Coordinator", role="Manager", message=f"Received goal: '{goal}'. Analyzing requirements...", timestamp=time.time()
    ))
    
    await asyncio.sleep(2)
    if mission_id in missions:
        missions[mission_id]["logs"].append(AgentMessage(
        agent_name="Coordinator", role="Manager", message="Plan created. Step 1: Scan for vulnerabilities. Step 2: Patch if found.", timestamp=time.time()
    ))

    # 2. Worker Execution (Scanner)
    await asyncio.sleep(2)
    if mission_id in missions:
        missions[mission_id]["logs"].append(AgentMessage(
        agent_name="Scanner-01", role="Researcher", message="Starting generic vulnerability scan on network...", timestamp=time.time()
    ))
    
    await asyncio.sleep(3)
    if mission_id in missions:
        missions[mission_id]["logs"].append(AgentMessage(
        agent_name="Scanner-01", role="Researcher", message="Scan complete. Found critical issue: CVE-2026-1234 (Remote Code Execution).", timestamp=time.time()
    ))

    # 3. Coordinator Decision
    await asyncio.sleep(1)
    if mission_id in missions:
        missions[mission_id]["logs"].append(AgentMessage(
        agent_name="Coordinator", role="Manager", message="Critical issue confirmed. Assigning Patcher-Alpha to remediate.", timestamp=time.time()
    ))

    # 4. Worker Execution (Patcher)
    await asyncio.sleep(2)
    if mission_id in missions:
        missions[mission_id]["logs"].append(AgentMessage(
        agent_name="Patcher-Alpha", role="Engineer", message="Applying patch 'sec-fix-v4.2'. Verifying system stability...", timestamp=time.time()
    ))
    
    await asyncio.sleep(2)
    if mission_id in missions:
        missions[mission_id]["logs"].append(AgentMessage(
        agent_name="Patcher-Alpha", role="Engineer", message="Patch applied successfully. System generated 200 OK responses.", timestamp=time.time()
    ))

    # 5. Conclusion
    await asyncio.sleep(1)
    if mission_id in missions:
        missions[mission_id]["status"] = "Completed"
        missions[mission_id]["logs"].append(AgentMessage(
        agent_name="Coordinator", role="Manager", message="Mission accomplished. Vulnerability resolved.", timestamp=time.time()
    ))

@router.post("/start")
async def start_mission(mission: SwarmMission, background_tasks: BackgroundTasks):
    mission_id = str(uuid.uuid4())
    missions[mission_id] = {
        "id": mission_id,
        "goal": mission.goal,
        "status": "Running",
        "logs": []
    }
    background_tasks.add_task(run_swarm_lifecycle, mission_id, mission.goal)
    return {"mission_id": mission_id, "status": "Started"}

@router.get("/status/{mission_id}")
async def get_mission_status(mission_id: str):
    return missions.get(mission_id, {"error": "Mission not found"})

@router.get("/list")
async def list_missions():
    # Convert logs objects to dicts for JSON serialization
    results = []
    for m in missions.values():
        clean_m = m.copy()
        # Ensure logs are serializable
        clean_logs = []
        for log in m["logs"]:
            if isinstance(log, AgentMessage):
                clean_logs.append(log.dict())
            else:
                clean_logs.append(log)
        clean_m["logs"] = clean_logs
        results.append(clean_m)
    return results
