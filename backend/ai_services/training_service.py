"""
TrainingService — orchestrates dataset building + QLoRA fine-tuning.

Workflow:
  1. build_dataset()   — pulls MongoDB → JSONL via OmniDatasetBuilder
  2. start_training()  — kicks off OmniFineTuner in a background thread
  3. get_status()      — returns live progress + history
"""

import asyncio
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .omni_finetune import OmniFineTuner
from .dataset_builder import OmniDatasetBuilder

logger = logging.getLogger(__name__)


class TrainingService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TrainingService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.tuner          = OmniFineTuner()
        self.builder        = OmniDatasetBuilder()
        self.current_job: Optional[Dict[str, Any]] = None
        self.history: list  = []
        self.is_training    = False
        self._initialized   = True

    # ------------------------------------------------------------------ #
    # Dataset                                                              #
    # ------------------------------------------------------------------ #

    async def build_dataset(self) -> Dict[str, Any]:
        """Pull MongoDB data and write JSONL training set. Returns stats."""
        from database import get_database
        db = get_database()
        if db is None:
            return {"error": "Database not available"}
        self.builder.set_db(db)
        try:
            stats = await self.builder.build()
            return stats
        except Exception as exc:
            logger.error("Dataset build failed: %s", exc)
            return {"error": "Dataset build failed"}

    def get_dataset_stats(self) -> Dict[str, Any]:
        """Return cached stats from the last build (no DB call)."""
        return OmniDatasetBuilder.last_stats()

    # ------------------------------------------------------------------ #
    # Training                                                             #
    # ------------------------------------------------------------------ #

    async def start_training(self, model_name: str = "Omni-Local-V1") -> Dict[str, Any]:
        if self.is_training:
            return {"error": "Training already in progress"}

        dataset_path = Path(self.get_dataset_stats().get("path", "omni_data/dataset.jsonl"))
        if not dataset_path.exists():
            # Try to build automatically
            logger.info("Dataset missing — building now before training...")
            stats = await self.build_dataset()
            if "error" in stats:
                return {"error": f"Dataset build failed: {stats['error']}"}

        self.is_training = True
        self.history     = []
        self.current_job = {
            "model_name":    model_name,
            "start_time":    datetime.now().isoformat(),
            "epochs":        int(__import__("os").getenv("OMNI_EPOCHS", "3")),
            "current_epoch": 0,
            "step":          0,
            "loss":          0.0,
            "status":        "Initializing",
        }

        # Run fine-tuning in a daemon thread (avoids blocking the event loop)
        loop = asyncio.get_event_loop()
        thread = threading.Thread(
            target=self._run_training_thread,
            args=(loop,),
            daemon=True,
            name="omni-finetune",
        )
        thread.start()
        return {"status": "success", "message": "Fine-tuning started in background"}

    def _run_training_thread(self, loop: asyncio.AbstractEventLoop) -> None:
        def on_progress(prog: Dict[str, Any]) -> None:
            epoch  = prog.get("epoch", 0)
            step   = prog.get("step",  0)
            loss   = prog.get("loss",  0.0)
            status = prog.get("status", "Training")

            self.current_job.update({
                "current_epoch": epoch,
                "step":          step,
                "loss":          loss,
                "status":        status,
            })

            if loss > 0:
                self.history.append({
                    "epoch": epoch,
                    "step":  step,
                    "loss":  loss,
                })

            logger.info("Fine-tune progress | %s | epoch=%d step=%d loss=%.4f",
                        status, epoch, step, loss)

        try:
            result = self.tuner.train(on_progress=on_progress)
            self.current_job.update({
                "status":   "Completed",
                "end_time": datetime.now().isoformat(),
                "loss":     result.get("train_loss", 0.0),
            })
        except Exception as exc:
            logger.error("Fine-tuning failed: %s", exc)
            self.current_job.update({
                "status":   f"Failed: {exc}",
                "end_time": datetime.now().isoformat(),
            })
        finally:
            self.is_training = False

    # ------------------------------------------------------------------ #
    # Status / Info                                                        #
    # ------------------------------------------------------------------ #

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_training":    self.is_training,
            "current_job":    self.current_job,
            "history":        self.history[-20:],
            "model_info":     self.tuner.get_info(),
            "dataset_stats":  self.get_dataset_stats(),
        }

    def get_model_info(self) -> Dict[str, Any]:
        return self.tuner.get_info()


_service = TrainingService()


def get_training_service() -> TrainingService:
    return _service
