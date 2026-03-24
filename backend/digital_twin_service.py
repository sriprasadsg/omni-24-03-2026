from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any
import random
import time

router = APIRouter(prefix="/api/digital_twin", tags=["Digital Twin"])

class SimulationRequest(BaseModel):
    action_type: str  # "patch", "config_change", "firewall_rule"
    target_id: str
    details: str

class SimulationResult(BaseModel):
    success_probability: float
    impact_score: int  # 0-100 (100 = high impact/risk)
    predicted_downtime: str
    conflicts: List[str]
    compliance_check: str

@router.post("/simulate")
async def run_simulation(request: SimulationRequest):
    """
    Simulates a network change on the Digital Twin.
    """
    # Simulate computation time
    time.sleep(1.5)
    
    # Mock Logic based on input
    prob = random.uniform(85.0, 99.9)
    conflicts = []
    
    if "KB2026" in request.details:
        conflicts.append("Legacy App 'PaymentGateway' compatibility warning")
        prob = 75.5
    
    if request.action_type == "firewall_rule":
        if "allow all" in request.details.lower():
             return SimulationResult(
                success_probability=100.0,
                impact_score=99,
                predicted_downtime="0s",
                conflicts=["CRITICAL: Violates Zero Trust Policy", "Overly permissive rule"],
                compliance_check="FAILED"
             )
    
    return SimulationResult(
        success_probability=round(prob, 1),
        impact_score=random.randint(5, 30),
        predicted_downtime=f"{random.randint(0, 120)}s",
        conflicts=conflicts,
        compliance_check="PASSED"
    )

@router.get("/state")
async def get_twin_state():
    """Returns the current sync status of the twin"""
    return {
        "sync_status": "Synced",
        "last_sync": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "assets_modeled": 1240,
        "network_segments": 15
    }
