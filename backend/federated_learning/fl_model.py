"""Federated Learning Model Registry — versioned model storage and distribution.

Tracks global model versions across federated rounds. Supports rollback
to previous versions and A/B testing between model variants.
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class ModelVersion:
    """Registered model version."""
    version: str
    name: str
    base_version: str  # parent version this was derived from
    round_id: str  # FL round that produced this version
    participants: List[str]
    total_samples: int
    metrics: Dict[str, float]  # loss, accuracy, etc.
    status: str = "active"  # active | deprecated | archived
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ModelRegistry:
    """Central registry for federated model versions."""

    def __init__(self):
        self.models: Dict[str, ModelVersion] = {}
        self.active_version: Optional[str] = None

    def register_version(
        self,
        name: str,
        base_version: str,
        round_id: str,
        participants: List[str],
        total_samples: int,
        metrics: Dict[str, float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Register a new model version."""
        version = f"fl_{hashlib.md5(f'{name}{time.time()}'.encode()).hexdigest()[:10]}"
        model = ModelVersion(
            version=version,
            name=name,
            base_version=base_version,
            round_id=round_id,
            participants=participants,
            total_samples=total_samples,
            metrics=metrics,
            metadata=metadata or {},
        )
        self.models[version] = model
        logger.info(
            "Model registered: %s (base: %s, round: %s, participants: %d)",
            version, base_version, round_id, len(participants),
        )
        return version

    def get_version(self, version: str) -> Optional[ModelVersion]:
        """Get model version by ID."""
        return self.models.get(version)

    def set_active(self, version: str) -> bool:
        """Set a version as active (production)."""
        if version not in self.models:
            return False
        self.active_version = version
        logger.info("Model %s set as active", version)
        return True

    def list_versions(
        self,
        name: str = "",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """List model versions, optionally filtered by name."""
        versions = list(self.models.values())
        if name:
            versions = [v for v in versions if v.name == name]
        versions.sort(key=lambda v: v.created_at, reverse=True)
        return [
            {
                "version": v.version,
                "name": v.name,
                "base_version": v.base_version,
                "round_id": v.round_id,
                "participants": len(v.participants),
                "total_samples": v.total_samples,
                "metrics": v.metrics,
                "status": v.status,
                "created_at": v.created_at,
            }
            for v in versions[:limit]
        ]

    def rollback(self, version: str) -> bool:
        """Rollback to a previous version."""
        target = self.models.get(version)
        if not target or target.status == "archived":
            return False
        self.active_version = version
        target.status = "active"
        logger.info("Rolled back to model %s", version)
        return True


# Singleton model registry
model_registry = ModelRegistry()
