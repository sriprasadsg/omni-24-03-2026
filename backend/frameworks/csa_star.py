"""CSA STAR (CCM v4) — Cloud Security Alliance Security, Trust, Assurance and Risk."""
from __future__ import annotations
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "csa_star"
FRAMEWORK_NAME = "CSA STAR (CCM v4)"
FRAMEWORK_VERSION = "CCM v4"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    return await evaluate_from_db(db, "csa_star")
