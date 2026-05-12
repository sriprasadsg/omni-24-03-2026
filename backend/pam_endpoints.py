"""Privileged Access Management (PAM) endpoints."""
from __future__ import annotations
import time
from fastapi import APIRouter, HTTPException, Depends
from auth_utils import get_current_user

router = APIRouter(prefix="/api/pam", tags=["PAM"])


async def _db():
    from database import get_database
    return get_database()


# ── Privileged Accounts ────────────────────────────────────────────────────────

@router.get("/accounts")
async def list_privileged_accounts(db=Depends(_db)):
    cursor = db["pam_accounts"].find({}, {"_id": 0}).sort("last_used", -1)
    items = await cursor.to_list(length=200)
    return items


@router.post("/accounts")
async def create_account(payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    payload.setdefault("id", f"pam-{int(time.time())}")
    payload.setdefault("created_at", time.time())
    payload.setdefault("created_by", current_user.get("sub"))
    payload.setdefault("status", "active")
    payload.setdefault("checkout_status", "available")
    await db["pam_accounts"].insert_one(payload)
    payload.pop("_id", None)
    return payload


# ── Session Recording ──────────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(db=Depends(_db)):
    cursor = db["pam_sessions"].find({}, {"_id": 0}).sort("started_at", -1).limit(100)
    items = await cursor.to_list(length=100)
    return items


@router.post("/sessions")
async def start_session(payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    session = {
        "id": f"sess-{int(time.time())}",
        "account_id": payload.get("account_id"),
        "target_host": payload.get("target_host"),
        "protocol": payload.get("protocol", "ssh"),
        "user": current_user.get("sub"),
        "started_at": time.time(),
        "status": "active",
        "duration_seconds": 0,
        "commands_executed": 0,
        "recording_path": f"/recordings/sess-{int(time.time())}.cast",
    }
    await db["pam_sessions"].insert_one(session)
    await db["pam_accounts"].update_one(
        {"id": payload.get("account_id")},
        {"$set": {"checkout_status": "checked_out", "checked_out_by": current_user.get("sub")}}
    )
    session.pop("_id", None)
    return session


@router.post("/sessions/{session_id}/end")
async def end_session(session_id: str, db=Depends(_db), current_user=Depends(get_current_user)):
    session = await db["pam_sessions"].find_one({"id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    duration = int(time.time() - session.get("started_at", time.time()))
    await db["pam_sessions"].update_one(
        {"id": session_id}, {"$set": {"status": "ended", "duration_seconds": duration, "ended_at": time.time()}}
    )
    await db["pam_accounts"].update_one(
        {"id": session.get("account_id")},
        {"$set": {"checkout_status": "available", "last_used": time.time()}}
    )
    return {"ok": True, "duration_seconds": duration}


# ── Credential Vault ───────────────────────────────────────────────────────────

@router.get("/vault")
async def list_vault_entries(db=Depends(_db)):
    cursor = db["pam_vault"].find({}, {"_id": 0, "password": 0, "secret": 0}).sort("last_rotated", -1)
    items = await cursor.to_list(length=200)
    return items


@router.post("/vault/{entry_id}/rotate")
async def rotate_credential(entry_id: str, db=Depends(_db), current_user=Depends(get_current_user)):
    entry = await db["pam_vault"].find_one({"id": entry_id})
    if not entry:
        raise HTTPException(status_code=404, detail="Vault entry not found")
    await db["pam_vault"].update_one(
        {"id": entry_id},
        {"$set": {"last_rotated": time.time(), "rotated_by": current_user.get("sub"),
                  "rotation_count": entry.get("rotation_count", 0) + 1}}
    )
    return {"ok": True, "rotated_at": time.time()}


# ── Command Audit Log ──────────────────────────────────────────────────────────

@router.get("/audit")
async def command_audit_log(db=Depends(_db)):
    cursor = db["pam_command_logs"].find({}, {"_id": 0}).sort("executed_at", -1).limit(200)
    items = await cursor.to_list(length=200)
    return items


@router.get("/stats")
async def pam_stats(db=Depends(_db)):
    accounts = await db["pam_accounts"].count_documents({})
    active_sessions = await db["pam_sessions"].count_documents({"status": "active"})
    vault_entries = await db["pam_vault"].count_documents({})

    # Sessions started in the last 24 hours
    cutoff_24h = time.time() - 86400
    sessions_today = await db["pam_sessions"].count_documents({"started_at": {"$gte": cutoff_24h}})

    # Credential rotations in the last 30 days
    cutoff_30d = time.time() - 86400 * 30
    rotations_30d = await db["pam_vault"].count_documents({"last_rotated": {"$gte": cutoff_30d}})

    # Risk score: percentage of accounts with overdue rotation (>rotation_interval_days since last_rotated)
    all_accounts = await db["pam_accounts"].find({}, {"rotation_days": 1, "last_used": 1}).to_list(length=500)
    overdue = sum(
        1 for a in all_accounts
        if a.get("rotation_days") and a.get("last_used")
        and (time.time() - a["last_used"]) > a["rotation_days"] * 86400
    )
    risk_score = round(overdue / len(all_accounts) * 100) if all_accounts else 0

    return {
        "privileged_accounts": accounts,
        "active_sessions": active_sessions,
        "vault_entries": vault_entries,
        "sessions_today": sessions_today,
        "rotations_last_30d": rotations_30d,
        "risk_score": risk_score,
    }


