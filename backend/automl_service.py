import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid
import random

class AutoMLService:
    def __init__(self):
        # Store studies and their trials
        self.studies: Dict[str, Dict[str, Any]] = {}
        
    def create_study(self, study_name: str, objective_metric: str = "accuracy") -> str:
        """Create a new HPO study"""
        study_id = f"study-{uuid.uuid4().hex[:8]}"
        self.studies[study_id] = {
            "id": study_id,
            "name": study_name,
            "objective": objective_metric,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "trials": [],
            "status": "Active"
        }
        return study_id

    async def run_trials(self, study_id: str, n_trials: int = 5):
        """Run multiple trials in parallel (simulated)"""
        if study_id not in self.studies:
            raise ValueError("Study not found")
            
        study = self.studies[study_id]
        
        # Simulate running trials
        tasks = []
        for i in range(n_trials):
            tasks.append(self._execute_trial(study_id, i))
            
        await asyncio.gather(*tasks)
        
        return len(study["trials"])

    async def _execute_trial(self, study_id: str, trial_idx: int):
        """Simulate training a model with random params"""
        # 1. Sample Hyperparameters
        params = {
            "learning_rate": round(random.uniform(0.0001, 0.1), 5),
            "batch_size": random.choice([16, 32, 64, 128]),
            "optimizer": random.choice(["adam", "sgd", "rmsprop"]),
            "layers": random.randint(1, 5)
        }
        
        trial_id = f"trial-{uuid.uuid4().hex[:6]}"
        
        # 2. Simulate Training Duration based on batch_size/layers
        duration = (params["layers"] * 0.2) + (params["batch_size"] / 100)
        await asyncio.sleep(duration) 
        
        # 3. Simulate Result (complex function of params + noise)
        # Optimal: LR=0.01, Batch=32, layers=3 -> Accuracy ~0.95
        
        score_base = 0.70
        
        # Learning Rate Penalty
        lr_dist = abs(params["learning_rate"] - 0.01)
        score_base -= (lr_dist * 2) # heavily penalize bad LR
        
        # Batch Size Bonus
        if params["batch_size"] == 32: score_base += 0.05
        
        # Layers Bonus
        if params["layers"] == 3: score_base += 0.05
        
        # Noise
        score = score_base + random.uniform(-0.02, 0.05)
        score = max(0.0, min(0.99, score)) # Clamp 0-1
        
        trial_result = {
            "trial_id": trial_id,
            "params": params,
            "value": round(score, 4),
            "state": "Complete",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        self.studies[study_id]["trials"].append(trial_result)

    def get_study(self, study_id: str) -> Optional[Dict[str, Any]]:
        if study_id not in self.studies:
            return None
            
        study = self.studies[study_id]
        
        # Find best trial
        trials = study["trials"]
        if trials:
            best_trial = max(trials, key=lambda x: x["value"])
            return {**study, "best_trial": best_trial}
            
        return study

    def get_all_studies(self) -> List[Dict[str, Any]]:
        # return summary list
        return [
            {
                "id": s["id"], 
                "name": s["name"], 
                "trials_count": len(s["trials"]),
                "best_score": max([t["value"] for t in s["trials"]]) if s["trials"] else 0,
                "created_at": s["created_at"]
            }
            for s in self.studies.values()
        ]

# Global instance
automl_service = AutoMLService()
