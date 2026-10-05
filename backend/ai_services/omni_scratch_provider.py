"""
OmniScratchProvider — serves the platform's own from-scratch model (omni_llm_scratch.py).

It wraps the open-source teacher provider (Ollama). Only plain chat questions are offered
to the own model (via answer_question); it answers when it is confident, otherwise — and
for every other generation request (long prompts, chat history, JSON/structured output,
streaming) — the teacher answers. Counters show how much the own model already handles.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import AsyncIterator, Optional

from ai_providers import AIProvider
from ai_services import omni_scratch_data as data

logger = logging.getLogger(__name__)

MIN_CONFIDENCE = float(os.getenv("OMNI_SCRATCH_MIN_CONFIDENCE", "0.45"))
MAX_QUESTION_CHARS = 400
_active: Optional["OmniScratchProvider"] = None


class OmniScratchProvider(AIProvider):
    def __init__(self, teacher: AIProvider):
        global _active
        self.teacher = teacher
        self._model = None
        self._tok = None
        self._lock = threading.Lock()
        self.stats = {"own_answers": 0, "deferred_to_teacher": 0, "last_confidence": None}
        _active = self

    @property
    def name(self) -> str:
        return f"Omni-Scratch (fallback: {self.teacher.name})"

    async def configure(self, settings: dict) -> bool:
        return await self.teacher.configure(settings)

    @staticmethod
    def available() -> bool:
        return data.CHECKPOINT_PATH.exists() and data.TOKENIZER_PATH.exists()

    def _load(self):
        with self._lock:
            if self._model is None:
                from ai_services.omni_llm_scratch import load_checkpoint

                self._model, _ = load_checkpoint(data.CHECKPOINT_PATH)
                self._tok = data.load_tokenizer()
        return self._model, self._tok

    def _answer_sync(self, question: str):
        import torch

        model, tok = self._load()
        ids = torch.tensor([tok.encode(data.format_qa(question)).ids])
        if ids.shape[1] >= model.cfg.block_size // 2:
            return "", 0.0
        out, confidence = model.generate(ids, max_new_tokens=160, temperature=0.6, top_k=30,
                                         stop_id=tok.token_to_id(data.EOT))
        return tok.decode(out[0, ids.shape[1]:].tolist()).strip(), confidence

    async def answer_question(self, question: str) -> Optional[str]:
        """The own model's answer to a plain question, or None to defer to the teacher."""
        question = (question or "").strip()
        if not question or len(question) > MAX_QUESTION_CHARS or not self.available():
            return None
        try:
            answer, confidence = await asyncio.to_thread(self._answer_sync, question)
        except Exception as exc:  # a broken/partial checkpoint must never break chat
            logger.warning("[OmniScratch] own model failed, deferring to teacher: %s", exc)
            return None
        self.stats["last_confidence"] = round(confidence, 3)
        if len(answer) >= 20 and confidence >= MIN_CONFIDENCE:
            self.stats["own_answers"] += 1
            return answer
        self.stats["deferred_to_teacher"] += 1
        return None

    async def generate(self, prompt, temperature: Optional[float] = None, max_tokens: int = 1024) -> str:
        return await self.teacher.generate(prompt, temperature=temperature, max_tokens=max_tokens)

    async def generate_stream(self, prompt) -> AsyncIterator[str]:
        async for chunk in self.teacher.generate_stream(prompt):
            yield chunk


def with_own_model(teacher: AIProvider) -> AIProvider:
    """Wrap the teacher with the own model when one has been trained (and it is enabled)."""
    enabled = os.getenv("OMNI_SCRATCH_ENABLED", "true").lower() in ("1", "true", "yes")
    return OmniScratchProvider(teacher) if enabled and OmniScratchProvider.available() else teacher


def active_stats() -> Optional[dict]:
    return dict(_active.stats, min_confidence=MIN_CONFIDENCE) if _active else None
