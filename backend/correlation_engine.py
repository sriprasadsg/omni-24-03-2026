"""
SIEM Correlation Engine aggregator.

Logic is split across three mixin modules:
  correlation_engine_core.py     — event loading, time/entity/pattern detection
  correlation_engine_response.py — playbook triggering, periodic loop, query helpers
  correlation_engine_threat.py   — AI selection, IoC broadcast, threat hunt, kill-chain
"""

from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from correlation_engine_core import CorrelationEngineCoreMixin, _BUILTIN_ATTACK_PATTERNS  # re-exported for correlation_endpoints
from correlation_engine_response import CorrelationEngineResponseMixin
from correlation_engine_threat import CorrelationEngineThreatMixin


class CorrelationEngine(
    CorrelationEngineResponseMixin,
    CorrelationEngineThreatMixin,
    CorrelationEngineCoreMixin,
):
    """SIEM Correlation Engine for detecting attack patterns."""


_correlation_engine: Optional[CorrelationEngine] = None


def get_correlation_engine(db: AsyncIOMotorDatabase) -> CorrelationEngine:
    """Get or create the correlation engine singleton."""
    global _correlation_engine
    if _correlation_engine is None:
        _correlation_engine = CorrelationEngine(db)
    return _correlation_engine
