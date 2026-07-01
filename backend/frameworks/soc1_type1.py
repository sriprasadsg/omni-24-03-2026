"""SOC 1 Type I (SSAE 18) — Point-in-time assessment of financial reporting controls."""
from __future__ import annotations
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "soc1_type1"
FRAMEWORK_NAME = "SOC 1 Type I (SSAE 18)"
FRAMEWORK_VERSION = "SSAE 18 / ISAE 3402"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    return await evaluate_from_db(db, "soc1_type1")
