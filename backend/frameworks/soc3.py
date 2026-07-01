"""SOC 3 — General-use report on Trust Services Criteria (publicly releasable)."""
from __future__ import annotations
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "soc3"
FRAMEWORK_NAME = "SOC 3"
FRAMEWORK_VERSION = "2017 (updated 2022)"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    return await evaluate_from_db(db, "soc3")
