"""SOC 1 (SSAE 18) — Internal Controls over Financial Reporting."""
from __future__ import annotations
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "soc1_type2"
FRAMEWORK_NAME = "SOC 1 Type II (SSAE 18)"
FRAMEWORK_VERSION = "SSAE 18 / ISAE 3402"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    return await evaluate_from_db(db, "soc1_type2")
