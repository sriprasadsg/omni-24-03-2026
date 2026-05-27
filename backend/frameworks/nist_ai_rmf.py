"""NIST AI RMF — AI Risk Management Framework (NIST AI 100-1)."""
from __future__ import annotations
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "nist_ai_rmf"
FRAMEWORK_NAME = "NIST AI Risk Management Framework"
FRAMEWORK_VERSION = "AI 100-1 (2023)"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB

_AI_THEMES   = {"ai governance", "model", "ai system", "algorithm", "ml", "artificial intelligence"}
_RISK_THEMES = {"risk", "risk management", "impact assessment", "bias"}


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    """DB eval enhanced with AI model registry and risk-register checks."""
    results = await evaluate_from_db(db, "nist_ai_rmf")

    model_count = await db.ai_models.count_documents({})
    if model_count == 0:
        model_count = await db.model_registry.count_documents({})
    risk_count = await db.risks.count_documents({})

    for r in results:
        theme = r.get("theme", "").lower()
        if any(t in theme for t in _AI_THEMES):
            r["model_evidence"] = f"{model_count} AI/ML models in registry"
            if model_count > 0 and r["status"] != "pass":
                r["status"] = "pass"
        if any(t in theme for t in _RISK_THEMES):
            r["risk_evidence"] = f"{risk_count} risks in register"
            if risk_count > 0 and r["status"] != "pass":
                r["status"] = "pass"
    return results
