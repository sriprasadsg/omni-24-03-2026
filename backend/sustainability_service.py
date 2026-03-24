from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict
import random
import datetime

router = APIRouter(prefix="/api/sustainability", tags=["Sustainability & GreenOps"])

# --- Models ---
class ComputeUsage(BaseModel):
    cpuHours: float
    memoryGBHours: float
    gpuHours: float

class EmissionsBreakdown(BaseModel):
    compute: float
    storage: float
    network: float

class CarbonFootprint(BaseModel):
    timestamp: str  # ISO date
    totalEmissions: float  # kg CO2e
    breakdown: EmissionsBreakdown
    region: str # e.g., us-east-1

class SustainabilityMetric(BaseModel):
    id: str
    name: str # e.g., "PUE (Power Usage Effectiveness)"
    value: float
    unit: str
    trend: str # improving, worsening, stable
    target: float

# --- Endpoints ---

@router.get("/carbon-footprint", response_model=List[CarbonFootprint])
async def get_carbon_footprint():
    """Generates 30-day historical carbon footprint data."""
    data = []
    base_emissions = 500.0 # Daily average kg CO2e
    
    for i in range(30):
        date = datetime.datetime.now() - datetime.timedelta(days=i)
        flavor = random.uniform(0.8, 1.2) # Daily variance
        
        daily_total = base_emissions * flavor
        breakdown = EmissionsBreakdown(
            compute=daily_total * 0.6,
            storage=daily_total * 0.3,
            network=daily_total * 0.1
        )
        
        data.append(CarbonFootprint(
            timestamp=date.isoformat(),
            totalEmissions=round(daily_total, 2),
            breakdown=breakdown,
            region="us-east-1"
        ))
    return data

@router.get("/metrics", response_model=List[SustainabilityMetric])
async def get_sustainability_metrics():
    """Returns key GreenOps metrics."""
    return [
        SustainabilityMetric(
            id="m1", name="PUE (Power Usage Effectiveness)", 
            value=1.12, unit="", trend="improving", target=1.1
        ),
        SustainabilityMetric(
            id="m2", name="Renewable Energy Mix", 
            value=85, unit="%", trend="stable", target=100
        ),
        SustainabilityMetric(
            id="m3", name="Carbon Intensity", 
            value=140, unit="gCO2/kWh", trend="worsening", target=100
        ),
        SustainabilityMetric(
            id="m4", name="Water Usage Effectiveness (WUE)", 
            value=0.2, unit="L/kWh", trend="improving", target=0.1
        )
    ]
