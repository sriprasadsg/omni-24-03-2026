"""Migration 036: security alerts ready for the SOC console (Security Overview and Alert Management).

Nothing is deleted. For every ``security_alerts`` row:
* an ``id`` when it has none (rows written before soc_alerts.record_alert mostly had none);
* ``tenantId`` / ``agent_id`` lifted out of ``metadata`` when only metadata had them (UEBA alerts,
  which tenants could not see);
* status ``new`` read as ``open``; ``lastSeenAt`` and ``occurrences``.

Shadow-AI alerts: the process name is recovered from the scan that raised the alert (the writer read
``name`` but agents send ``process``, so titles said "unknown"). Repeats of one active process on one
endpoint are folded into the first (status ``merged`` + ``mergedInto`` on the others), which counts
them, as record_alert does from now on.

The Omni-Agent server's own local LLM (Ollama, which the platform's AI runs on, and the
``llama-server`` runner it starts from /usr/lib/ollama) is approved on the server's agent, as the owner
decided on 2026-11-18; their active alerts close as approved
(``autoClosed``, so they stay out of the console's response times). The approval shows in the
console and can be revoked there. Indexes for the console's reads. A second run changes nothing.
"""
import logging
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "SOC console: alert ids, tenants from metadata, repeated AI-process alerts folded, server Ollama approved, indexes."

logger = logging.getLogger(__name__)

ACTIVE = ["open", "new", "acknowledged"]
PID = re.compile(r"PID (\d+)")
SERVER_LLM = ("ollama", "llama-server")
SERVER_LLM_REASON = "The platform's own local LLM (Ollama) on the Omni-Agent server"


async def _lift_tenants(col) -> int:
    n = 0
    async for d in col.find({"tenantId": {"$in": [None, ""]}, "metadata.tenantId": {"$nin": [None, ""]}},
                            {"_id": 1, "metadata": 1, "agent_id": 1}):
        sets = {"tenantId": d["metadata"]["tenantId"]}
        if not d.get("agent_id") and d["metadata"].get("agent_id"):
            sets["agent_id"] = d["metadata"]["agent_id"]
        await col.update_one({"_id": d["_id"]}, {"$set": sets})
        n += 1
    return n


async def _name_ai_processes(db, col) -> int:
    n = 0
    async for d in col.find({"type": "shadow_ai_process", "process": {"$exists": False}},
                            {"_id": 1, "agent_id": 1, "created_at": 1, "description": 1}):
        scan = await db.shadow_ai_scans.find_one({"agent_id": d.get("agent_id"), "scanned_at": d.get("created_at")},
                                                 {"_id": 0, "local_ai_processes": 1})
        procs = [p for p in (scan or {}).get("local_ai_processes") or [] if isinstance(p, dict)]
        pid = PID.search(d.get("description") or "")
        match = next((p for p in procs if pid and str(p.get("pid")) == pid.group(1)), procs[0] if len(procs) == 1 else None)
        name = str((match or {}).get("process") or (match or {}).get("name") or "").strip()
        if not name:
            continue
        await col.update_one({"_id": d["_id"]}, {"$set": {
            "process": name, "exe": match.get("exe"), "title": f"Unapproved AI process: {name}",
            "description": f"Local AI process '{name}' (PID {match.get('pid')}) detected on agent {d.get('agent_id')}",
        }})
        n += 1
    return n


async def _fold_repeats(col) -> int:
    groups = defaultdict(list)
    async for d in col.find({"type": "shadow_ai_process", "status": {"$in": ACTIVE}},
                            {"_id": 1, "id": 1, "tenantId": 1, "agent_id": 1, "process": 1, "created_at": 1,
                             "lastSeenAt": 1, "occurrences": 1}):
        key = (d.get("tenantId"), d.get("agent_id"), str(d.get("process") or "unknown").lower())
        groups[key].append(d)
    folded = 0
    for (_, agent, process), rows in groups.items():
        rows.sort(key=lambda r: str(r.get("created_at") or ""))
        first, rest = rows[0], rows[1:]
        sets = {"group": f"shadow_ai_process:{agent}:{process}"}  # record_alert counts later repeats on it
        if rest:
            sets["occurrences"] = sum(int(r.get("occurrences") or 1) for r in rows)
            sets["lastSeenAt"] = max(str(r.get("lastSeenAt") or r.get("created_at") or "") for r in rows) or None
        await col.update_one({"_id": first["_id"]}, {"$set": sets})
        if rest:
            await col.update_many({"_id": {"$in": [r["_id"] for r in rest]}},
                                  {"$set": {"status": "merged", "mergedInto": first["id"]}})
            folded += len(rest)
    return folded


async def _approve_server_llm(db, col) -> int:
    from network_topology_service import server_identity

    names = server_identity()["names"]
    now = datetime.now(timezone.utc).isoformat()
    closed = 0
    async for agent in db.agents.find({}, {"_id": 0, "id": 1, "tenantId": 1, "hostname": 1}):
        if str(agent.get("hostname") or "").lower() not in names:
            continue
        for process in SERVER_LLM:
            key = {"tenantId": agent.get("tenantId"), "process": process, "agentId": agent.get("id")}
            await db.approved_ai_processes.update_one(key, {"$setOnInsert": {
                **key, "id": str(uuid.uuid4()), "hostname": agent.get("hostname"), "reason": SERVER_LLM_REASON,
                "approvedBy": "system (owner decision, 2026-11-18)", "approvedAt": now,
            }}, upsert=True)
        result = await col.update_many(
            {"tenantId": agent.get("tenantId"), "agent_id": agent.get("id"), "type": "shadow_ai_process",
             "process": {"$in": list(SERVER_LLM)}, "status": {"$in": ACTIVE}},
            {"$set": {"status": "closed", "resolution": "approved", "closedAt": now, "closedBy": "system",
                      "closeNote": SERVER_LLM_REASON, "autoClosed": True}})
        closed += result.modified_count
    return closed


async def up(db: AsyncIOMotorDatabase) -> None:
    col = db.security_alerts
    lifted = await _lift_tenants(col)
    ids = 0
    async for d in col.find({"id": {"$exists": False}}, {"_id": 1}):
        await col.update_one({"_id": d["_id"]}, {"$set": {"id": str(uuid.uuid4())}})
        ids += 1
    await col.update_many({"status": "new"}, {"$set": {"status": "open"}})
    await col.update_many({"lastSeenAt": {"$exists": False}},
                          [{"$set": {"lastSeenAt": {"$ifNull": ["$created_at", "$timestamp"]}}}])
    await col.update_many({"occurrences": {"$exists": False}}, {"$set": {"occurrences": 1}})
    named = await _name_ai_processes(db, col)
    folded = await _fold_repeats(col)
    approved = await _approve_server_llm(db, col)

    await col.create_index([("tenantId", 1), ("status", 1), ("severity", 1)], name="soc_queue")
    await col.create_index([("tenantId", 1), ("created_at", -1)], name="soc_recent")
    await col.create_index([("tenantId", 1), ("group", 1), ("status", 1)], name="soc_group")
    await col.create_index("id", name="soc_id")
    await db.approved_ai_processes.create_index([("tenantId", 1), ("process", 1), ("agentId", 1)],
                                                unique=True, name="approval_once")
    logger.info("migration 036: %d tenants lifted, %d ids, %d AI processes named, %d repeats folded, "
                "%d server LLM alerts approved", lifted, ids, named, folded, approved)
