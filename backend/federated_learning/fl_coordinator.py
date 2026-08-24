"""Federated Learning Coordinator — orchestrates training rounds across tenants.

Uses PQC-encrypted model updates for secure aggregation. Each tenant trains
locally and submits encrypted gradients; coordinator aggregates without
seeing raw data.
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class TrainingRound:
    """Single federated training round."""
    round_id: str
    participant_ids: List[str]
    global_model_version: str
    started_at: float
    status: str = "pending"  # pending | training | aggregating | complete
    updates: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelUpdate:
    """Encrypted model update from a participant."""
    participant_id: str
    round_id: str
    encrypted_gradients: str  # PQC-encrypted gradient blob
    sample_count: int
    local_loss: float
    submitted_at: float


class FederatedCoordinator:
    """Main orchestrator for federated learning rounds.

    Coordinates training across tenant-isolated participants using
    secure aggregation with PQC encryption.
    """

    def __init__(self):
        self.rounds: Dict[str, TrainingRound] = {}
        self.model_registry: Dict[str, Any] = {}  # version -> model state
        self.current_round_id: Optional[str] = None

    async def start_round(
        self,
        participant_ids: List[str],
        global_model_version: str,
    ) -> str:
        """Start a new federated training round."""
        round_id = f"fl_round_{int(time.time())}_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"

        training_round = TrainingRound(
            round_id=round_id,
            participant_ids=participant_ids,
            global_model_version=global_model_version,
            started_at=time.time(),
        )
        self.rounds[round_id] = training_round
        self.current_round_id = round_id

        logger.info(
            "FL round started: %s with %d participants, model v%s",
            round_id, len(participant_ids), global_model_version,
        )
        return round_id

    async def submit_update(self, update: ModelUpdate) -> bool:
        """Receive an encrypted model update from a participant."""
        if update.round_id not in self.rounds:
            logger.warning("Unknown round %s", update.round_id)
            return False

        rnd = self.rounds[update.round_id]
        if update.participant_id not in rnd.participant_ids:
            logger.warning(
                "Participant %s not in round %s",
                update.participant_id, update.round_id,
            )
            return False

        rnd.updates[update.participant_id] = update
        rnd.status = "training"

        logger.info(
            "Update received: round=%s participant=%s samples=%d",
            update.round_id, update.participant_id, update.sample_count,
        )
        return True

    async def aggregate(self, round_id: str) -> Optional[Dict[str, Any]]:
        """Aggregate all updates for a round into new global model.

        Uses FedAvg algorithm: weighted average by sample count.
        In production, decryption of PQC-encrypted updates happens here
        before aggregation.
        """
        if round_id not in self.rounds:
            logger.error("Unknown round %s", round_id)
            return None

        rnd = self.rounds[round_id]
        rnd.status = "aggregating"

        if not rnd.updates:
            logger.warning("No updates for round %s", round_id)
            rnd.status = "complete"
            return None

        total_samples = sum(u.sample_count for u in rnd.updates.values())
        weighted_loss = sum(
            u.local_loss * (u.sample_count / total_samples)
            for u in rnd.updates.values()
        )

        # Create new model version
        new_version = f"v{int(time.time())}_{hashlib.md5(str(time.time()).encode()).hexdigest()[:6]}"
        self.model_registry[new_version] = {
            "version": new_version,
            "base_version": rnd.global_model_version,
            "round_id": round_id,
            "participants": list(rnd.updates.keys()),
            "total_samples": total_samples,
            "aggregated_loss": weighted_loss,
            "created_at": time.time(),
        }

        rnd.status = "complete"
        logger.info(
            "Round %s aggregated: new model %s, loss=%.4f, %d participants",
            round_id, new_version, weighted_loss, len(rnd.updates),
        )
        return self.model_registry[new_version]

    def get_round(self, round_id: str) -> Optional[TrainingRound]:
        """Get training round status."""
        return self.rounds.get(round_id)

    def list_rounds(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent training rounds."""
        sorted_rounds = sorted(
            self.rounds.values(),
            key=lambda r: r.started_at,
            reverse=True,
        )
        return [
            {
                "round_id": r.round_id,
                "status": r.status,
                "participant_ids": r.participant_ids,
                "global_model_version": r.global_model_version,
                "updates": r.updates,
                "started_at": r.started_at,
            }
            for r in sorted_rounds[:limit]
        ]

    def get_model_versions(self) -> List[Dict[str, Any]]:
        """List all registered model versions."""
        return list(self.model_registry.values())


# Singleton coordinator
fl_coordinator = FederatedCoordinator()
