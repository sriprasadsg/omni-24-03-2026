from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
import time

from auth_utils import get_current_user

router = APIRouter(prefix="/api/rollback", tags=["Rollback"])


async def _db():
    from database import get_database
    return get_database()


@router.get("/checkpoints")
async def list_checkpoints(db=Depends(_db), current_user=Depends(get_current_user)):
    """Return checkpoints for the caller's tenant, newest first."""
    tenant_id = getattr(current_user, "tenant_id", None)
    query = {} if not tenant_id else {"tenantId": tenant_id}
    cursor = db["rollback_checkpoints"].find(query, {"_id": 0}).sort("timestamp", -1).limit(100)
    return await cursor.to_list(length=100)


@router.get("/checkpoints/{checkpoint_id}")
async def get_checkpoint(checkpoint_id: str, db=Depends(_db), current_user=Depends(get_current_user)):
    tenant_id = getattr(current_user, "tenant_id", None)
    ckpt_filter: dict = {"id": checkpoint_id}
    if tenant_id:
        ckpt_filter["tenantId"] = tenant_id
    doc = await db["rollback_checkpoints"].find_one(ckpt_filter, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return doc


@router.post("/checkpoints/{checkpoint_id}/restore")
async def restore_checkpoint(
    checkpoint_id: str,
    db=Depends(_db),
    current_user=Depends(get_current_user),
):
    """Queue a restore command for the owning agent."""
    ckpt = await db["rollback_checkpoints"].find_one({"id": checkpoint_id})
    if not ckpt:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    if ckpt.get("status") != "available":
        raise HTTPException(status_code=409, detail="Checkpoint is not in 'available' state")

    agent_id = ckpt.get("agent_id")
    command = {
        "type": "rollback",
        "checkpoint_id": checkpoint_id,
        "requested_by": current_user.get("sub"),
        "requested_at": time.time(),
    }
    await db["agent_commands"].insert_one({"agent_id": agent_id, **command})
    await db["rollback_checkpoints"].update_one(
        {"id": checkpoint_id},
        {"$set": {"status": "restore_requested"}},
    )
    return {"status": "queued", "agent_id": agent_id, "checkpoint_id": checkpoint_id}


@router.get("/checkpoints/{checkpoint_id}/status")
async def get_restore_status(checkpoint_id: str, db=Depends(_db), current_user=Depends(get_current_user)):
    """Poll the current status of a checkpoint (available / restore_requested / restoring / restored / failed)."""
    tenant_id = getattr(current_user, "tenant_id", None)
    ckpt_filter: dict = {"id": checkpoint_id}
    if tenant_id:
        ckpt_filter["tenantId"] = tenant_id
    doc = await db["rollback_checkpoints"].find_one(ckpt_filter, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return {
        "checkpoint_id": checkpoint_id,
        "status": doc.get("status", "unknown"),
        "agent_id": doc.get("agent_id"),
        "restored_at": doc.get("restored_at"),
        "error": doc.get("restore_error"),
    }


@router.post("/checkpoints/{checkpoint_id}/status")
async def update_restore_status(checkpoint_id: str, payload: dict, db=Depends(_db),
                                current_user=Depends(get_current_user)):
    """Called by the agent to update restore progress (restoring / restored / failed)."""
    allowed = {"restoring", "restored", "failed", "available"}
    status = payload.get("status", "")
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use: {allowed}")

    tenant_id = getattr(current_user, "tenant_id", None)
    ckpt_filter: dict = {"id": checkpoint_id}
    if tenant_id:
        ckpt_filter["tenantId"] = tenant_id

    update: dict = {"status": status}
    if status == "restored":
        update["restored_at"] = time.time()
    if "error" in payload:
        update["restore_error"] = payload["error"]

    result = await db["rollback_checkpoints"].update_one(ckpt_filter, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return {"ok": True, "checkpoint_id": checkpoint_id, "status": status}


@router.post("/checkpoints")
async def register_checkpoint(payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    """Called by the agent after creating a checkpoint to register it."""
    tenant_id = getattr(current_user, "tenant_id", None)
    payload.setdefault("status", "available")
    payload.setdefault("timestamp", time.time())
    if tenant_id:
        payload["tenantId"] = tenant_id
    await db["rollback_checkpoints"].replace_one(
        {"id": payload["id"]}, payload, upsert=True
    )
    return {"ok": True}
