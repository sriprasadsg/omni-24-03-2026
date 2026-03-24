import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid

class ModelRetrainingService:
    def __init__(self):
        # Simulated Model Registry
        self.registry = [
            {"id": "model-phishing-v1", "name": "Phishing Detector", "version": "1.0.0", "stage": "Production", "accuracy": 0.95, "created_at": "2025-12-01T10:00:00Z"},
            {"id": "model-intrusion-v1", "name": "Intrusion Detection", "version": "1.2.0", "stage": "Production", "accuracy": 0.92, "created_at": "2025-12-15T14:30:00Z"},
            {"id": "model-anomaly-v1", "name": "Anomaly Detector", "version": "2.0.1", "stage": "Production", "accuracy": 0.88, "created_at": "2026-01-10T09:15:00Z"}
        ]
        
        # Training Jobs History
        self.jobs = []
        
        # Current active jobs
        self.active_jobs = {}

    async def trigger_retraining(self, model_name: str, reason: str = "manual") -> str:
        """idempotent trigger for a training job"""
        job_id = f"job-{uuid.uuid4().hex[:8]}"
        
        job_record = {
            "job_id": job_id,
            "model_name": model_name,
            "status": "Pending",
            "progress": 0,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "end_time": None,
            "reason": reason,
            "metrics": {}
        }
        
        self.jobs.insert(0, job_record)
        self.active_jobs[job_id] = job_record
        
        # Start background simulation
        asyncio.create_task(self._simulate_training_pipeline(job_id, model_name))
        
        return job_id

    async def _simulate_training_pipeline(self, job_id: str, model_name: str):
        """Simulate a 4-step pipeline: Data Prep -> Train -> Eval -> Register"""
        job = self.active_jobs[job_id]
        
        try:
            # Step 1: Data Prep
            job["status"] = "Data Preparation"
            for i in range(0, 25):
                job["progress"] = i
                await asyncio.sleep(0.1)
                
            # Step 2: Training
            job["status"] = "Training Model"
            for i in range(25, 75):
                job["progress"] = i
                await asyncio.sleep(0.1)
                
            # Step 3: Evaluation
            job["status"] = "Evaluating"
            for i in range(75, 90):
                job["progress"] = i
                await asyncio.sleep(0.1)
            
            # Generate dummy metrics
            import random
            accuracy = 0.85 + (random.random() * 0.14) # 0.85 - 0.99
            f1_score = accuracy - 0.02
            
            job["metrics"] = {"accuracy": round(accuracy, 4), "f1_score": round(f1_score, 4)}
            
            # Step 4: Register New Version
            job["status"] = "Registering"
            await asyncio.sleep(1)
            
            # Register new model version
            base_version = 1
            # Find latest version for this name
            existing = [m for m in self.registry if m["name"] == model_name]
            if existing:
                base_version = len(existing) + 1
                
            new_version_id = f"model-{model_name.lower().split()[0]}-v{base_version}"
            
            new_model_entry = {
                "id": new_version_id,
                "name": model_name,
                "version": f"{base_version}.0.0",
                "stage": "Staging", # Default to staging
                "accuracy": round(accuracy, 4),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            self.registry.insert(0, new_model_entry)
            
            # Complete Job
            job["status"] = "Completed"
            job["progress"] = 100
            job["end_time"] = datetime.now(timezone.utc).isoformat()
            job["new_version_id"] = new_version_id
            
        except Exception as e:
            job["status"] = "Failed"
            job["error"] = str(e)
            job["end_time"] = datetime.now(timezone.utc).isoformat()
        
        # Cleanup active jobs map but keep in history list
        # We don't remove from active_jobs immediately so FE can poll it, but in real app this logic differs
        pass

    def get_models(self) -> List[Dict[str, Any]]:
        return self.registry

    def get_history(self) -> List[Dict[str, Any]]:
        return self.jobs

    def promote_model(self, model_id: str):
        """Promote a Staging model to Production"""
        # Find model
        target = next((m for m in self.registry if m["id"] == model_id), None)
        if not target:
            raise ValueError("Model not found")
        
        # Demote current production model of same name
        for m in self.registry:
            if m["name"] == target["name"] and m["stage"] == "Production":
                m["stage"] = "Archived"
        
        # Promote target
        target["stage"] = "Production"
        return target

# Global instance
mlops_service = ModelRetrainingService()
