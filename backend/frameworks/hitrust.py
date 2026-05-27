"""HITRUST CSF v11 — Health Information Trust Alliance Common Security Framework."""
from __future__ import annotations
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "hitrust_csf"
FRAMEWORK_NAME = "HITRUST CSF v11"
FRAMEWORK_VERSION = "v11"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    return await evaluate_from_db(db, "hitrust_csf")
