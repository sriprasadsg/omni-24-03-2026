"""COBIT 2019 — Control Objectives for Information and Related Technologies."""
from __future__ import annotations
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "cobit_2019"
FRAMEWORK_NAME = "COBIT 2019"
FRAMEWORK_VERSION = "2019"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    return await evaluate_from_db(db, "cobit_2019")
