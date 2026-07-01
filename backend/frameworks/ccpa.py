"""CCPA/CPRA — California Consumer Privacy Act / California Privacy Rights Act."""
from __future__ import annotations
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "ccpa"
FRAMEWORK_NAME = "California Consumer Privacy Act (CCPA/CPRA)"
FRAMEWORK_VERSION = "CPRA 2023"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    return await evaluate_from_db(db, "ccpa")
