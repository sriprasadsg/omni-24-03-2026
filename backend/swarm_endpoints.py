from datetime import timezone
from fastapi import APIRouter, BackgroundTasks, Query, Body, Depends
from pydantic import BaseModel
from typing import Dict, Any
import uuid
import time
import asyncio
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/swarm", tags=["Swarm"])

# --- Models ---
class SwarmMission(BaseModel):
    goal: str
    priority: str

class AgentMessage(BaseModel):
    agent_name: str
    role: str
    message: str
    timestamp: float

# --- In-memory Store ---
missions = {}

# ── Goal → instruction mapping ─────────────────────────────────────────────

def _goal_to_instructions(goal: str) -> list[dict]:
    """Map a free-text mission goal to typed agent instructions."""
    g = goal.lower()
    instructions = []
    if any(k in g for k in ("scan", "vulnerabilit", "assess", "audit")):
        instructions.append({"type": "vulnerability_scan", "instruction": f"Swarm mission: {goal}"})
    if any(k in g for k in ("patch", "fix", "remediat", "update")):
        instructions.append({"type": "os_patch_install", "instruction": f"Swarm mission: {goal}"})
    if any(k in g for k in ("monitor", "watch", "detect", "threat hunt")):
        instructions.append({"type": "threat_hunt", "instruction": f"Swarm mission: {goal}"})
    if any(k in g for k in ("collect", "log", "ship")):
        instructions.append({"type": "log_collection", "instruction": f"Swarm mission: {goal}"})
    if any(k in g for k in ("isolat", "quarantin", "block")):
        instructions.append({"type": "isolate_host", "instruction": f"Swarm mission: {goal}"})
    if not instructions:
        instructions.append({"type": "general_task", "instruction": f"Swarm mission: {goal}"})
    return instructions


# ── Real swarm lifecycle ────────────────────────────────────────────────────

async def run_swarm_lifecycle(mission_id: str, goal: str):
    """
    Real swarm execution:
    1. AI coordinator generates a typed instruction plan for the goal.
    2. Instructions are dispatched to all online agents via MongoDB.
    3. Progress is logged per agent.
    """
    db = get_database()
    now = lambda: time.time()  # noqa

    def _log(agent_name: str, role: str, msg: str):
        if mission_id in missions:
            missions[mission_id]["logs"].append(AgentMessage(
                agent_name=agent_name, role=role, message=msg, timestamp=now()
            ))

    _log("Coordinator", "Manager", f"Received goal: '{goal}'. Analysing online agents…")

    # ── AI-enhanced planning ───────────────────────────────────────────────────
    from ai_service import ai_service
    ai_instructions: list[dict] = []
    if not ai_service.is_configured:
        await ai_service.initialize()
    if ai_service.is_configured:
        prompt = f"""You are the coordinator of an autonomous security agent swarm.
Goal: {goal}

Return a JSON array of 3-5 objects, each with "type" (one of: vulnerability_scan, os_patch_install, threat_hunt, log_collection, isolate_host, general_task) and "instruction" (one short sentence).
Example: [{{"type": "vulnerability_scan", "instruction": "Scan all endpoints for critical CVEs"}}]"""
        try:
            import json, re as _re
            raw = await ai_service.generate_text(prompt, source="swarm_coordinator")
            raw = raw.replace("```json", "").replace("```", "").strip()
            m = _re.search(r'\[.*\]', raw, _re.DOTALL)
            if m:
                ai_instructions = json.loads(m.group(0))
        except Exception:
            ai_instructions = []

    if ai_instructions:
        _log("Coordinator", "Manager",
             f"AI plan: {len(ai_instructions)} steps — " + ", ".join(i.get("type", "") for i in ai_instructions))

    # Fetch all online agents across tenants (swarm is platform-wide)
    agents = await db.agents.find({"status": "Online"}, {"id": 1, "hostname": 1, "tenantId": 1}).to_list(length=100)
    agent_count = len(agents)

    if agent_count == 0:
        _log("Coordinator", "Manager", "No online agents found. Mission queued — will execute when agents come online.")
        if mission_id in missions:
            missions[mission_id]["status"] = "Queued"
        return

    _log("Coordinator", "Manager", f"Found {agent_count} online agent(s). Planning instruction dispatch...")

    instructions = ai_instructions if ai_instructions else _goal_to_instructions(goal)
    _log("Coordinator", "Manager",
         f"Plan: {len(instructions)} instruction type(s) → {', '.join(i['type'] for i in instructions)}")

    dispatched = 0
    created_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()

    for agent in agents:
        agent_id = agent["id"]
        hostname = agent.get("hostname", agent_id)
        for instr in instructions:
            await db.agent_instructions.insert_one({
                "agent_id": agent_id,
                "instruction": instr["instruction"],
                "type": instr["type"],
                "status": "pending",
                "created_at": created_at,
                "job_id": mission_id,
                "metadata": {"mission_id": mission_id, "goal": goal},
                "payload": {},
            })
            dispatched += 1
            _log(hostname, "Worker",
                 f"Queued [{instr['type']}]: {instr['instruction'][:80]}")

    await asyncio.sleep(1)
    _log("Coordinator", "Manager",
         f"Dispatched {dispatched} instruction(s) to {agent_count} agent(s). Awaiting results via /api/deployments/{{job_id}}/result.")

    if mission_id in missions:
        missions[mission_id]["status"] = "Running"
        missions[mission_id]["agents_dispatched"] = agent_count
        missions[mission_id]["instructions_dispatched"] = dispatched

    # Persist mission to DB
    await db.swarm_missions.update_one(
        {"id": mission_id},
        {"$set": {
            "status": "Running",
            "agents_dispatched": agent_count,
            "instructions_dispatched": dispatched,
            "updatedAt": created_at,
        }},
        upsert=True,
    )

# --- Endpoints ---

@router.post("/start")
async def start_mission(mission: SwarmMission, background_tasks: BackgroundTasks, _current_user: TokenData = Depends(get_current_user)):
    mission_id = str(uuid.uuid4())
    db = get_database()
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    missions[mission_id] = {
        "id": mission_id,
        "goal": mission.goal,
        "priority": mission.priority,
        "status": "Running",
        "logs": [],
        "createdAt": now,
    }
    await db.swarm_missions.insert_one({
        "id": mission_id,
        "goal": mission.goal,
        "priority": mission.priority,
        "status": "Running",
        "createdAt": now,
    })
    background_tasks.add_task(run_swarm_lifecycle, mission_id, mission.goal)
    return {"mission_id": mission_id, "status": "Started"}

@router.get("/status/{mission_id}")
async def get_mission_status(mission_id: str, _current_user: TokenData = Depends(get_current_user)):
    return missions.get(mission_id, {"error": "Mission not found"})

@router.get("/list")
async def list_missions(_current_user: TokenData = Depends(get_current_user)):
    """
    Return all swarm missions from MongoDB, merging in-memory logs for active ones.
    This ensures missions survive server restarts.
    """
    db = get_database()
    db_missions = await db.swarm_missions.find({}, {"_id": 0}).sort("createdAt", -1).to_list(length=200)

    results = []
    for m in db_missions:
        mid = m.get("id")
        # Merge in-memory logs if the mission is still active in this process
        if mid and mid in missions:
            mem = missions[mid]
            clean_logs = []
            for log in mem.get("logs", []):
                clean_logs.append(log.dict() if isinstance(log, AgentMessage) else log)
            m["logs"] = clean_logs
            m["status"] = mem.get("status", m.get("status"))
        else:
            m.setdefault("logs", [])
        results.append(m)

    return results

@router.get("/topology")
async def get_swarm_topology(db=Depends(get_database), _current_user: TokenData = Depends(get_current_user)):
    """Real swarm topology built from agent documents in the database."""
    agents = await db.agents.find({}, {
        "_id": 0, "id": 1, "hostname": 1, "status": 1,
        "tenantId": 1, "gossip_port": 1, "ip_address": 1,
        "swarm_peers": 1, "capabilities": 1,
    }).to_list(length=200)

    nodes = []
    for agent in agents:
        status = agent.get("status", "Unknown")
        capabilities = agent.get("capabilities", [])
        role = "Leader" if "swarm_coordinator" in capabilities else (
            "Inference" if "autonomous_response" in capabilities else "Worker"
        )
        nodes.append({
            "id": agent.get("id"),
            "name": agent.get("hostname", agent.get("id")),
            "role": role,
            "status": "Active" if status == "Online" else status,
            "tenantId": agent.get("tenantId"),
        })

    # Build links from stored peer relationships
    links = []
    seen = set()
    for agent in agents:
        src = agent.get("id")
        for peer_id in agent.get("swarm_peers", []):
            key = tuple(sorted((src, peer_id)))
            if key not in seen:
                seen.add(key)
                links.append({"source": src, "target": peer_id, "value": 1})

    return {"nodes": nodes, "links": links}


# ── Real Swarm Peer Discovery (DB-backed) ──────────────────────────────────────

@router.get("/peers")
async def get_swarm_peers(
    agent_id: str = Query(..., description="Requesting agent's ID"),
    db=Depends(get_database),
    _current_user: TokenData = Depends(get_current_user),
):
    """
    Return other online agents in the same tenant so the SwarmCoordinator
    can establish P2P gossip connections.
    Only agents that have reported a gossip_port are included.
    """
    agent = await db.agents.find_one({"id": agent_id}, {"tenantId": 1})
    if not agent:
        return {"peers": []}

    tenant_id = agent.get("tenantId", "default")
    peers_cursor = db.agents.find(
        {
            "tenantId": tenant_id,
            "status": "Online",
            "id": {"$ne": agent_id},
            "swarm.gossip_port": {"$exists": True},
        },
        {"_id": 0, "id": 1, "swarm.ip_address": 1, "swarm.gossip_port": 1},
    )
    peers = await peers_cursor.to_list(length=50)
    result = [
        {
            "agent_id": p["id"],
            "ip_address": p.get("swarm", {}).get("ip_address", ""),
            "port": p.get("swarm", {}).get("gossip_port", 15000),
        }
        for p in peers
        if p.get("swarm", {}).get("ip_address")
    ]
    return {"peers": result}


@router.post("/report")
async def report_swarm_topology(
    payload: Dict[str, Any] = Body(...),
    db=Depends(get_database),
    _current_user: TokenData = Depends(get_current_user),
):
    """
    Agent SwarmCoordinator reports its gossip endpoint and current peer list.
    Stored on the agent document so /peers can return live addresses.
    """
    agent_id   = payload.get("agent_id")
    ip_address = payload.get("ip_address")
    gossip_port = payload.get("gossip_port")
    peers      = payload.get("peers", [])

    if not agent_id:
        return {"success": False, "reason": "agent_id required"}

    await db.agents.update_one(
        {"id": agent_id},
        {"$set": {
            "swarm.ip_address":   ip_address,
            "swarm.gossip_port":  gossip_port,
            "swarm.peers":        peers,
            "swarm.last_seen":    time.time(),
        }},
    )
    return {"success": True}

