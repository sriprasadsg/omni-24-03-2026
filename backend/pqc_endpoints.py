"""
PQC Endpoints â€” Post-Quantum Cryptography REST API.

Exposes the hybrid Kyber-768 / X25519 key exchange engine at /api/pqc/*.

Routes:
  GET  /api/pqc/status             - service config and active session count
  POST /api/pqc/keypair            - generate a hybrid public/private keypair
  POST /api/pqc/handshake          - establish a quantum-safe session for an agent
  POST /api/pqc/encrypt            - encrypt a payload using an active session
  GET  /api/pqc/sessions           - list active PQC sessions (admin)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from authentication_service import get_current_user
from pqc_service import pqc_engine

router = APIRouter(prefix="/api/pqc", tags=["PQC"])

_ADMIN_ROLES = {"Super Admin", "superadmin", "super_admin", "platform-admin", "Tenant Admin"}


class HandshakeRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=200)
    agent_public_key: str = Field(..., min_length=1, max_length=512)


class EncryptRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=200)
    data: str = Field(..., min_length=1, max_length=65536)


@router.get("/status")
async def pqc_status(current_user=Depends(get_current_user)):
    return {
        "enabled": pqc_engine.pqc_enabled,
        "standard": pqc_engine.current_standard,
        "classical_standard": pqc_engine.classical_standard,
        "active_sessions": len(pqc_engine.active_sessions),
    }


@router.post("/keypair")
async def generate_keypair(current_user=Depends(get_current_user)):
    public_key, private_key = pqc_engine.generate_hybrid_keypair()
    return {
        "public_key": public_key,
        "private_key": private_key,
        "algorithm": f"{pqc_engine.classical_standard} + {pqc_engine.current_standard}",
    }


@router.post("/handshake")
async def perform_handshake(body: HandshakeRequest, current_user=Depends(get_current_user)):
    result = pqc_engine.perform_hybrid_handshake(body.agent_id, body.agent_public_key)
    return result


@router.post("/encrypt")
async def encrypt_payload(body: EncryptRequest, current_user=Depends(get_current_user)):
    try:
        ciphertext = pqc_engine.encrypt_payload(body.session_id, body.data)
        return {"session_id": body.session_id, "ciphertext": ciphertext}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sessions")
async def list_sessions(current_user=Depends(get_current_user)):
    role = getattr(current_user, "role", "") or (current_user.get("role", "") if isinstance(current_user, dict) else "")
    if role not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required")
    sessions = [
        {k: v for k, v in sess.items() if k != "master_secret"}
        for sess in pqc_engine.active_sessions.values()
    ]
    return {"sessions": sessions, "count": len(sessions)}

