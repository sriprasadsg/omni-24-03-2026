"""Federated Learning REST API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from auth_types import TokenData
from rbac_service import rbac_service
from rbac_utils import is_super_admin
from federated_learning.fl_coordinator import fl_coordinator, TrainingRound
from federated_learning.fl_participant import participant_manager, Participant
from federated_learning.fl_model import model_registry, ModelVersion

router = APIRouter(prefix="/api/federated", tags=["Federated Learning"])

_PERM = "view:federated_learning"


def _require_own_tenant(current_user: TokenData, tenant_id: str) -> None:
    """Non-super-admin callers may only touch their own tenant's FL data.

    Rounds and model versions have no tenant field in this subsystem's data
    model at all (a round can span participants from multiple tenants) — that's
    an architecture gap beyond what this fix scopes to. Where a tenant_id *is*
    available (participants), it's enforced.
    """
    if is_super_admin(current_user.role):
        return
    if current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized for this tenant's federated learning data")


def _require_own_participant(current_user: TokenData, participant_id: str) -> Participant:
    p = participant_manager.get_participant(participant_id)
    if not p:
        raise HTTPException(status_code=404, detail="Participant not found")
    _require_own_tenant(current_user, p.tenant_id)
    return p


def _participants_all_belong_to(participant_ids: List[str], tenant_id: str) -> bool:
    for pid in participant_ids:
        p = participant_manager.get_participant(pid)
        if not p or p.tenant_id != tenant_id:
            return False
    return True


def _require_own_tenant_participants(current_user: TokenData, participant_ids: List[str]) -> None:
    """Gate round/model operations that span a list of participants but carry no
    tenant field of their own — authorize by requiring every named participant
    to belong to the caller's tenant."""
    if is_super_admin(current_user.role):
        return
    if not current_user.tenant_id or not _participants_all_belong_to(participant_ids, current_user.tenant_id):
        raise HTTPException(status_code=403, detail="Not authorized for one or more of these participants' tenant")


# Request/Response Models
class StartRoundRequest(BaseModel):
    participant_ids: List[str]
    global_model_version: str


class SubmitUpdateRequest(BaseModel):
    round_id: str
    participant_id: str
    encrypted_gradients: str
    sample_count: int
    local_loss: float


class RegisterParticipantRequest(BaseModel):
    tenant_id: str
    name: str
    model_version: str = ""


class RegisterModelRequest(BaseModel):
    name: str
    base_version: str
    round_id: str
    participants: List[str]
    total_samples: int
    metrics: Dict[str, float]


# Coordinator Endpoints
@router.post("/rounds/start")
async def start_round(
    request: StartRoundRequest,
    current_user: TokenData = Depends(rbac_service.has_permission(_PERM)),
):
    """Start a new federated training round."""
    _require_own_tenant_participants(current_user, request.participant_ids)
    round_id = await fl_coordinator.start_round(
        request.participant_ids,
        request.global_model_version,
    )
    return {"round_id": round_id, "status": "started"}


@router.post("/rounds/{round_id}/updates")
async def submit_update(
    round_id: str,
    request: SubmitUpdateRequest,
    current_user: TokenData = Depends(rbac_service.has_permission(_PERM)),
):
    """Submit encrypted model update for a round."""
    _require_own_participant(current_user, request.participant_id)
    from federated_learning.fl_coordinator import ModelUpdate
    update = ModelUpdate(
        participant_id=request.participant_id,
        round_id=request.round_id,
        encrypted_gradients=request.encrypted_gradients,
        sample_count=request.sample_count,
        local_loss=request.local_loss,
        submitted_at=0,  # will be set by coordinator
    )
    success = await fl_coordinator.submit_update(update)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to submit update")
    return {"status": "accepted"}


@router.post("/rounds/{round_id}/aggregate")
async def aggregate_round(
    round_id: str,
    current_user: TokenData = Depends(rbac_service.has_permission(_PERM)),
):
    """Aggregate updates and create new global model."""
    rnd = fl_coordinator.get_round(round_id)
    if not rnd:
        raise HTTPException(status_code=404, detail="Round not found")
    _require_own_tenant_participants(current_user, rnd.participant_ids)

    result = await fl_coordinator.aggregate(round_id)
    if not result:
        raise HTTPException(status_code=400, detail="Aggregation failed")
    return result


@router.get("/rounds")
async def list_rounds(
    limit: int = 10,
    current_user: TokenData = Depends(rbac_service.has_permission(_PERM)),
):
    """List recent training rounds."""
    rounds = fl_coordinator.list_rounds(limit)
    if is_super_admin(current_user.role):
        return rounds
    tenant_id = current_user.tenant_id or ""
    return [
        r for r in rounds
        if _participants_all_belong_to(r.get("participant_ids", []), tenant_id)
    ]


@router.get("/rounds/{round_id}")
async def get_round(
    round_id: str,
    current_user: TokenData = Depends(rbac_service.has_permission(_PERM)),
):
    """Get training round details."""
    rnd = fl_coordinator.get_round(round_id)
    if not rnd:
        raise HTTPException(status_code=404, detail="Round not found")
    _require_own_tenant_participants(current_user, rnd.participant_ids)
    return {
        "round_id": rnd.round_id,
        "status": rnd.status,
        "participants": rnd.participant_ids,
        "updates": list(rnd.updates.keys()),
        "global_model_version": rnd.global_model_version,
        "started_at": rnd.started_at,
    }


# Participant Endpoints
@router.post("/participants/register")
async def register_participant(
    request: RegisterParticipantRequest,
    current_user: TokenData = Depends(rbac_service.has_permission(_PERM)),
):
    """Register a new federated learning participant."""
    _require_own_tenant(current_user, request.tenant_id)
    participant_id = participant_manager.register(
        request.tenant_id,
        request.name,
        request.model_version,
    )
    return {"participant_id": participant_id, "status": "registered"}


@router.delete("/participants/{participant_id}")
async def unregister_participant(
    participant_id: str,
    current_user: TokenData = Depends(rbac_service.has_permission(_PERM)),
):
    """Unregister a participant."""
    _require_own_participant(current_user, participant_id)
    success = participant_manager.unregister(participant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Participant not found")
    return {"status": "unregistered"}


@router.get("/participants")
async def list_participants(
    tenant_id: str = "",
    current_user: TokenData = Depends(rbac_service.has_permission(_PERM)),
):
    """List participants, optionally filtered by tenant."""
    if not is_super_admin(current_user.role):
        tenant_id = current_user.tenant_id or ""
    return participant_manager.list_participants(tenant_id)


@router.get("/participants/{participant_id}")
async def get_participant(
    participant_id: str,
    current_user: TokenData = Depends(rbac_service.has_permission(_PERM)),
):
    """Get participant details."""
    p = _require_own_participant(current_user, participant_id)
    return {
        "participant_id": p.participant_id,
        "tenant_id": p.tenant_id,
        "name": p.name,
        "status": p.status,
        "model_version": p.model_version,
        "sample_count": p.sample_count,
        "local_loss": p.local_loss,
        "last_seen": p.last_seen,
    }


@router.patch("/participants/{participant_id}/status")
async def set_participant_status(
    participant_id: str,
    status: str,
    current_user: TokenData = Depends(rbac_service.has_permission(_PERM)),
):
    """Update participant status."""
    _require_own_participant(current_user, participant_id)
    success = participant_manager.set_status(participant_id, status)
    if not success:
        raise HTTPException(status_code=404, detail="Participant not found")
    return {"status": "updated"}


@router.patch("/participants/{participant_id}/metrics")
async def set_participant_metrics(
    participant_id: str,
    sample_count: int,
    local_loss: float,
    current_user: TokenData = Depends(rbac_service.has_permission(_PERM)),
):
    """Record participant training metrics."""
    _require_own_participant(current_user, participant_id)
    success = participant_manager.set_metrics(participant_id, sample_count, local_loss)
    if not success:
        raise HTTPException(status_code=404, detail="Participant not found")
    return {"status": "updated"}


# Model Registry Endpoints
@router.post("/models/register")
async def register_model(
    request: RegisterModelRequest,
    current_user: TokenData = Depends(rbac_service.has_permission(_PERM)),
):
    """Register a new model version."""
    _require_own_tenant_participants(current_user, request.participants)
    version = model_registry.register_version(
        name=request.name,
        base_version=request.base_version,
        round_id=request.round_id,
        participants=request.participants,
        total_samples=request.total_samples,
        metrics=request.metrics,
    )
    return {"version": version, "status": "registered"}


@router.get("/models")
async def list_models(
    name: str = "",
    limit: int = 20,
    current_user: TokenData = Depends(rbac_service.has_permission(_PERM)),
):
    """List model versions."""
    versions = model_registry.list_versions(name, limit)
    if is_super_admin(current_user.role):
        return versions
    tenant_id = current_user.tenant_id or ""
    visible = []
    for v in versions:
        full = model_registry.get_version(v["version"])
        if full and _participants_all_belong_to(full.participants, tenant_id):
            visible.append(v)
    return visible


@router.get("/models/{version}")
async def get_model(
    version: str,
    current_user: TokenData = Depends(rbac_service.has_permission(_PERM)),
):
    """Get model version details."""
    model = model_registry.get_version(version)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    _require_own_tenant_participants(current_user, model.participants)
    return {
        "version": model.version,
        "name": model.name,
        "base_version": model.base_version,
        "round_id": model.round_id,
        "participants": model.participants,
        "total_samples": model.total_samples,
        "metrics": model.metrics,
        "status": model.status,
        "created_at": model.created_at,
        "metadata": model.metadata,
    }


@router.post("/models/{version}/activate")
async def activate_model(
    version: str,
    current_user: TokenData = Depends(rbac_service.has_permission(_PERM)),
):
    """Set model as active."""
    model = model_registry.get_version(version)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    _require_own_tenant_participants(current_user, model.participants)

    success = model_registry.set_active(version)
    if not success:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"status": "activated"}


@router.post("/models/{version}/rollback")
async def rollback_model(
    version: str,
    current_user: TokenData = Depends(rbac_service.has_permission(_PERM)),
):
    """Rollback to a previous model version."""
    model = model_registry.get_version(version)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found or archived")
    _require_own_tenant_participants(current_user, model.participants)

    success = model_registry.rollback(version)
    if not success:
        raise HTTPException(status_code=404, detail="Model not found or archived")
    return {"status": "rolled_back"}