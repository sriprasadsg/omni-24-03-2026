"""Federated Learning Participant Manager — tracks tenant nodes.

Each participant (tenant agent) trains locally on its own data and
submits only encrypted gradients to the coordinator.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class Participant:
    """A federated learning participant node."""
    participant_id: str
    tenant_id: str
    name: str
    status: str = "registered"  # registered | training | idle | offline
    model_version: str = ""
    sample_count: int = 0
    local_loss: float = 0.0
    joined_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)


class ParticipantManager:
    """Manages participant lifecycle for federated learning."""

    def __init__(self):
        self.participants: Dict[str, Participant] = {}

    def register(
        self,
        tenant_id: str,
        name: str,
        model_version: str = "",
    ) -> str:
        """Register a new participant node."""
        participant_id = f"fl_node_{uuid.uuid4().hex[:8]}"
        participant = Participant(
            participant_id=participant_id,
            tenant_id=tenant_id,
            name=name,
            model_version=model_version,
        )
        self.participants[participant_id] = participant
        logger.info(
            "Participant registered: %s (tenant %s, model %s)",
            participant_id, tenant_id, model_version or "none",
        )
        return participant_id

    def unregister(self, participant_id: str) -> bool:
        """Remove a participant."""
        if participant_id not in self.participants:
            return False
        del self.participants[participant_id]
        logger.info("Participant unregistered: %s", participant_id)
        return True

    def set_status(self, participant_id: str, status: str) -> bool:
        """Update participant status."""
        p = self.participants.get(participant_id)
        if not p:
            return False
        p.status = status
        p.last_seen = time.time()
        return True

    def set_metrics(self, participant_id: str, sample_count: int, local_loss: float) -> bool:
        """Record participant training metrics."""
        p = self.participants.get(participant_id)
        if not p:
            return False
        p.sample_count = sample_count
        p.local_loss = local_loss
        p.last_seen = time.time()
        return True

    def get_participant(self, participant_id: str) -> Optional[Participant]:
        """Get participant by ID."""
        return self.participants.get(participant_id)

    def list_participants(self, tenant_id: str = "") -> List[Dict[str, Any]]:
        """List participants, optionally filtered by tenant."""
        result = []
        for p in self.participants.values():
            if tenant_id and p.tenant_id != tenant_id:
                continue
            result.append({
                "participant_id": p.participant_id,
                "tenant_id": p.tenant_id,
                "name": p.name,
                "status": p.status,
                "model_version": p.model_version,
                "sample_count": p.sample_count,
                "local_loss": p.local_loss,
                "last_seen": p.last_seen,
            })
        return result

    def get_ready_participants(self, min_count: int = 1) -> List[str]:
        """Get participant IDs that are ready to train (status != offline)."""
        return [
            p.participant_id
            for p in self.participants.values()
            if p.status != "offline"
        ][:min_count] if self.participants else []


# Singleton participant manager
participant_manager = ParticipantManager()
