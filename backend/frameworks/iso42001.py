"""ISO/IEC 42001:2023 — Artificial Intelligence Management Systems."""
from __future__ import annotations
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "iso42001"
FRAMEWORK_NAME = "ISO/IEC 42001:2023"
FRAMEWORK_VERSION = "2023"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    return await evaluate_from_db(db, "iso42001")
