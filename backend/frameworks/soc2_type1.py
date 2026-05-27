"""SOC 2 Type I — Point-in-time assessment of Trust Services Criteria."""
from __future__ import annotations
from typing import Any, Dict, List
from . import soc2

FRAMEWORK_ID = "soc2_type1"
FRAMEWORK_NAME = "SOC 2 Type I"
FRAMEWORK_VERSION = "2017 (updated 2022)"
CONTROLS: List[Dict[str, Any]] = soc2.CONTROLS  # same control set, different report type


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    """Reuses SOC 2 live checks — same criteria, point-in-time report scope."""
    return await soc2.evaluate_controls(db)
