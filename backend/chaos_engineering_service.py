from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import random
import uuid

# Simplified prefix
router = APIRouter(prefix="/api/chaos", tags=["Chaos Engineering"])

class ChaosExperiment(BaseModel):
    id: str
    tenantId: str
    name: str
    type: str  # 'CPU Hog', 'Latency Injection', 'Pod Failure'
    target: str
    status: str  # 'Scheduled', 'Running', 'Completed', 'Failed'
    lastRun: str


# No mock data - all experiments stored in MongoDB

@router.get("/experiments", response_model=List[ChaosExperiment])
async def get_experiments():
    """
    Get a list of all chaos experiments from database.
    """
    from database import get_database
    db = get_database()
    experiments = await db.chaos_experiments.find({}, {"_id": 0}).to_list(length=100)
    return [ChaosExperiment(**exp) for exp in experiments] if experiments else []

@router.post("/experiments", response_model=ChaosExperiment)
async def create_experiment(experiment: ChaosExperiment):
    """
    Create a new chaos experiment in database.
    """
    from database import get_database
    db = get_database()
    
    new_experiment = experiment
    if not new_experiment.id:
        new_experiment.id = str(uuid.uuid4())
    
    await db.chaos_experiments.insert_one(new_experiment.dict())
    return new_experiment

@router.post("/experiments/{experiment_id}/run")
async def run_experiment(experiment_id: str):
    """
    Run a specific chaos experiment.
    """
    from database import get_database
    db = get_database()
    
    experiment = await db.chaos_experiments.find_one({"id": experiment_id})
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    
    # Update status
    await db.chaos_experiments.update_one(
        {"id": experiment_id},
        {"$set": {
            "status": "Running",
            "lastRun": datetime.now().isoformat()
        }}
    )
    
    return {"message": f"Experiment {experiment_id} started successfully", "status": "Running"}
