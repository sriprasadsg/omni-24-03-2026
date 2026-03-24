import asyncio
import logging
import random
from datetime import datetime
from typing import Dict, Any, Optional
from .omni_llm_scratch import ScratchTrainer

logger = logging.getLogger(__name__)

class TrainingService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TrainingService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized: return
        self.trainer = ScratchTrainer()
        self.current_job = None
        self.history = []
        self.is_training = False
        self._initialized = True

    async def start_training(self, model_name: str = "Omni-LLM-V1"):
        if self.is_training:
            return {"error": "Training already in progress"}
            
        self.is_training = True
        self.current_job = {
            "model_name": model_name,
            "start_time": datetime.now().isoformat(),
            "epochs": 20,
            "current_epoch": 0,
            "loss": 2.5,
            "accuracy": 0.0,
            "status": "Initializing"
        }
        
        # Start background task
        asyncio.create_task(self._run_training_loop())
        return {"status": "success", "message": "Training started"}

    async def _run_training_loop(self):
        logger.info(f"Starting training loop for {self.current_job['model_name']}")
        
        for epoch in range(1, self.current_job['epochs'] + 1):
            if not self.is_training: break
            
            await asyncio.sleep(3) # Simulate compute time
            
            # Get metrics from trainer
            metrics = self.trainer.train_step(epoch)
            
            self.current_job.update({
                "current_epoch": epoch,
                "loss": metrics["loss"],
                "accuracy": metrics["accuracy"],
                "status": metrics["status"]
            })
            
            self.history.append({
                "epoch": epoch,
                "loss": metrics["loss"],
                "accuracy": metrics["accuracy"]
            })
            
            logger.info(f"Epoch {epoch}: Loss={metrics['loss']}, Acc={metrics['accuracy']}")
            
        self.is_training = False
        self.current_job["status"] = "Completed"
        self.current_job["end_time"] = datetime.now().isoformat()
        logger.info("Training completed successfully")

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_training": self.is_training,
            "current_job": self.current_job,
            "history": self.history[-10:] # Last 10 points for graph
        }

_service = TrainingService()

def get_training_service():
    return _service
