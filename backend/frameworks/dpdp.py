"""DPDP — India Digital Personal Data Protection Act 2023."""
from __future__ import annotations
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "dpdp"
FRAMEWORK_NAME = "Digital Personal Data Protection Act (DPDP)"
FRAMEWORK_VERSION = "2023"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    return await evaluate_from_db(db, "dpdp")
