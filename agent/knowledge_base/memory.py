import json
import os
import sys
import time
import logging
from pathlib import Path
from typing import List, Dict
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from local_ip import ollama_default_url

logger = logging.getLogger(__name__)

class AgentMemory:
    """
    Lightweight experience store for the Agent.
    Records past action outcomes and retrieves similar past situations
    using vector similarity (Ollama embeddings) with Jaccard fallback.
    """

    def __init__(self, data_dir="data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.memory_file = self.data_dir / "agent_memory.json"
        self.experiences = self._load_memory()

    # ── Persistence ────────────────────────────────────────────────────────────

    def _load_memory(self) -> List[Dict]:
        if self.memory_file.exists():
            try:
                return json.loads(self.memory_file.read_text())
            except Exception as e:
                logger.error("Failed to load memory: %s", e)
        return []

    def _save_memory(self):
        try:
            self.memory_file.write_text(json.dumps(self.experiences, indent=2))
        except Exception as e:
            logger.error("Failed to save memory: %s", e)

    # ── Storage ────────────────────────────────────────────────────────────────

    def store_experience(self, context: dict, action: str, outcome: dict):
        """Record a new experience with optional vector embedding."""
        summary   = self._summarize_context(context)
        embedding = self._get_embedding(summary)

        experience = {
            "id":              f"exp_{int(time.time())}",
            "timestamp":       time.time(),
            "context_summary": summary,
            "embedding":       embedding,
            "action":          action,
            "outcome":         outcome,
        }
        self.experiences.append(experience)
        # Cap at 1000 entries to avoid unbounded growth
        if len(self.experiences) > 1000:
            self.experiences = self.experiences[-1000:]
        self._save_memory()
        logger.info("Learned new experience: %s → success=%s", action, outcome.get("success"))

    # ── Retrieval ──────────────────────────────────────────────────────────────

    def find_similar_situations(self, current_context: dict) -> List[Dict]:
        """
        Retrieve the top-5 past experiences most similar to the current context.
        Uses cosine similarity on Ollama embeddings when available,
        falls back to Jaccard similarity on the text summary.
        """
        current_summary = self._summarize_context(current_context)
        current_vec     = self._get_embedding(current_summary)
        use_vector      = len(current_vec) > 0

        scored = []
        for exp in self.experiences:
            try:
                if use_vector and exp.get("embedding"):
                    score = self._cosine_similarity(current_vec, exp["embedding"])
                else:
                    score = self._jaccard_similarity(current_summary, exp.get("context_summary", ""))
                if score > 0.4:
                    scored.append((score, exp))
            except Exception:
                pass

        scored.sort(key=lambda x: x[0], reverse=True)
        return [exp for _, exp in scored[:5]]

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _summarize_context(self, context: dict) -> str:
        parts = [f"action:{context.get('action', context.get('instruction', ''))}"]
        if context.get("cpu_usage"):
            parts.append(f"cpu:{context['cpu_usage']}")
        for alert in context.get("alerts", []):
            parts.append(f"alert:{alert.get('type','unknown')}")
        for k in ("params", "payload"):
            val = context.get(k)
            if isinstance(val, dict):
                parts.extend(f"{k}:{v}" for v in list(val.values())[:3] if v)
        return " ".join(str(p) for p in parts)

    def _get_embedding(self, text: str) -> List[float]:
        """Fetch vector embedding from local Ollama with retry; warns when unavailable."""
        import requests as _req
        import logging as _log
        _logger = _log.getLogger(__name__)
        for attempt in range(2):
            try:
                resp = _req.post(
                    f"{ollama_default_url()}/api/embeddings",
                    json={"model": "mxbai-embed-large", "prompt": text},
                    timeout=3 + attempt * 2,  # 3s then 5s
                )
                if resp.status_code == 200:
                    embedding = resp.json().get("embedding", [])
                    if embedding:
                        return embedding
            except Exception as _e:
                if attempt == 0:
                    _logger.debug("Embedding attempt 1 failed: %s — retrying", _e)
                else:
                    _logger.warning(
                        "Ollama embedding unavailable after 2 attempts — falling back to Jaccard similarity. "
                        "Start Ollama with 'ollama pull mxbai-embed-large' for better memory retrieval. Error: %s", _e
                    )
        return []

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        if not vec1 or not vec2:
            return 0.0
        dot  = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = sum(a * a for a in vec1) ** 0.5
        mag2 = sum(b * b for b in vec2) ** 0.5
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot / (mag1 * mag2)

    def _jaccard_similarity(self, ctx1: str, ctx2: str) -> float:
        s1, s2 = set(ctx1.split()), set(ctx2.split())
        if not s1 or not s2:
            return 0.0
        return len(s1 & s2) / len(s1 | s2)
