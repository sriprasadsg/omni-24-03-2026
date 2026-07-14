"""FAIR risk quantification endpoint — POST /api/risks/{risk_id}/fair-simulation.

Runs a Monte Carlo FAIR simulation for an existing risk and persists the inputs
and results onto that risk. Kept separate from risk_endpoints.py to keep both
files small and the simulation concern isolated.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, model_validator

from risk_service import risk_service
from risk_fair_service import run_fair_simulation
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/risks", tags=["Risk Management"])

_MAX_LM = 1_000_000_000  # $1B per-event loss ceiling — guards against absurd inputs.


class FairInputs(BaseModel):
    lef_min: float = Field(ge=0)
    lef_likely: float = Field(ge=0)
    lef_max: float = Field(ge=0)
    lm_min: float = Field(ge=0, le=_MAX_LM)
    lm_likely: float = Field(ge=0, le=_MAX_LM)
    lm_max: float = Field(ge=0, le=_MAX_LM)
    iterations: int = Field(default=10000, ge=1000, le=100000)

    @model_validator(mode="after")
    def _check_ordering(self) -> "FairInputs":
        if not (self.lef_min <= self.lef_likely <= self.lef_max):
            raise ValueError("LEF must satisfy min <= likely <= max")
        if not (self.lm_min <= self.lm_likely <= self.lm_max):
            raise ValueError("LM must satisfy min <= likely <= max")
        return self


@router.post("/{risk_id}/fair-simulation")
async def run_risk_fair_simulation(
    risk_id: str,
    inputs: FairInputs,
    current_user: TokenData = Depends(get_current_user),
):
    """Run a FAIR Monte Carlo simulation for a risk and persist the outcome."""
    role = getattr(current_user, "role", "")
    tenant_id = getattr(current_user, "tenant_id", None) or None

    inputs_dict = inputs.model_dump()
    try:
        results = run_fair_simulation(inputs_dict)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    updated = await risk_service.attach_fair_results(
        risk_id, inputs_dict, results, tenant_id=tenant_id, role=role
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Risk not found")
    return updated
