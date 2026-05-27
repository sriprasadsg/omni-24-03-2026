"""ISO 9001:2015 — Quality Management Systems."""
from __future__ import annotations
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "iso9001_2015"
FRAMEWORK_NAME = "ISO 9001:2015"
FRAMEWORK_VERSION = "2015"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    return await evaluate_from_db(db, "iso9001_2015")
