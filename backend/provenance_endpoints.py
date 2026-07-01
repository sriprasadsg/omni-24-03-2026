"""
Provenance Endpoints — Cryptographic log provenance via Merkle trees.

Routes:
  POST /api/provenance/sign    - sign a block of log entries, returns Merkle root + block hash
  POST /api/provenance/verify  - verify a log block against its provenance record
  GET  /api/provenance/status  - chain length and root hash
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import List, Any, Dict, Optional

from authentication_service import get_current_user
from provenance_verifier import provenance_engine

router = APIRouter(prefix="/api/provenance", tags=["Provenance"])


class LogEntry(BaseModel):
    timestamp: str = Field(..., min_length=1)
    agent_id: str = ""
    event: str = Field(..., min_length=1)
    data: Any = None


class SignRequest(BaseModel):
    logs: List[LogEntry] = Field(..., min_items=1)


class VerifyRequest(BaseModel):
    block: Dict[str, Any]
    logs: List[LogEntry] = Field(..., min_items=1)
    previous_block_hash: str = ""


@router.post("/sign")
async def sign_block(body: SignRequest, current_user=Depends(get_current_user)):
    raw_logs = [e.model_dump() for e in body.logs]
    record = provenance_engine.sign_block(raw_logs)
    return {**record, "entries_signed": len(body.logs)}


@router.post("/verify")
async def verify_block(body: VerifyRequest, current_user=Depends(get_current_user)):
    raw_logs = [e.model_dump() for e in body.logs]
    valid = provenance_engine.verify_integrity(body.block, raw_logs, body.previous_block_hash)
    return {
        "valid": valid,
        "block_hash": body.block.get("block_hash"),
        "merkle_root": body.block.get("merkle_root"),
    }


@router.get("/status")
async def chain_status(current_user=Depends(get_current_user)):
    chain = provenance_engine.log_chain
    return {
        "chain_length": len(chain),
        "latest_hash": chain[-1] if chain else None,
        "standard": "RFC-9162-Modified-2027",
    }
