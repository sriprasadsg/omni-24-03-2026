"""
OmniLocalProvider — inference wrapper around the fine-tuned TinyLlama adapter.

Raises OmniLowConfidenceError when the model's per-token confidence (geometric
mean of top-1 softmax probabilities) is below the configured threshold, allowing
the caller to fall back to a stronger external LLM.

Confidence formula:
    confidence = exp( (1/T) * sum( log(p_t) ) )
    where p_t = softmax(logits_t)[argmax_t]  for each generated token t.

This is equivalent to the geometric mean of per-token probabilities.
"""

import logging
import math
import os
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

ADAPTER_PATH        = Path(os.getenv("OMNI_ADAPTER_PATH",    "omni_data/adapter"))
BASE_MODEL_ID       = os.getenv("OMNI_BASE_MODEL",           "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
BASE_CACHE_PATH     = Path(os.getenv("OMNI_BASE_MODEL_CACHE", "omni_data/base_model"))
CONFIDENCE_THRESHOLD = float(os.getenv("OMNI_CONFIDENCE_THRESHOLD", "0.35"))
MAX_NEW_TOKENS      = int(os.getenv("OMNI_MAX_NEW_TOKENS",   "256"))


class OmniLowConfidenceError(Exception):
    """Raised when the local model's confidence is below the threshold."""
    def __init__(self, partial_text: str, confidence: float):
        super().__init__(
            f"Local model confidence {confidence:.3f} < threshold {CONFIDENCE_THRESHOLD:.3f}"
        )
        self.partial_text = partial_text
        self.confidence   = confidence


class OmniLocalProvider:
    """
    Loads the fine-tuned LoRA adapter on top of TinyLlama and runs inference.
    Models are loaded lazily on first call to generate().

    This provider is intentionally NOT a subclass of AIProvider so it can be
    used standalone without importing the main ai_service module.
    """

    CONFIDENCE_THRESHOLD = CONFIDENCE_THRESHOLD

    def __init__(self):
        self._model     = None
        self._tokenizer = None
        self._loaded    = False
        self._load_error: Optional[str] = None

    # ------------------------------------------------------------------ #
    # AIProvider-compatible interface                                      #
    # ------------------------------------------------------------------ #

    @property
    def name(self) -> str:
        return "Omni-Local (Fine-tuned)"

    async def configure(self, _settings: dict) -> bool:
        """
        Returns True if a trained adapter exists on disk.
        Actual model loading is deferred to the first generate() call.
        """
        available = (ADAPTER_PATH / "adapter_config.json").exists()
        if not available:
            # Warn at WARNING level so operators know the local model is absent and
            # external LLM APIs (Gemini/Anthropic) will be used instead, incurring API costs.
            logger.warning(
                "OmniLocalProvider: adapter not found at %s — falling back to external LLM. "
                "Set OMNI_LOCAL_ENABLED=false to suppress this warning, or train an adapter first.",
                ADAPTER_PATH,
            )
        return available

    async def generate(self, prompt: str) -> str:
        """
        Generate a response. Raises OmniLowConfidenceError if confidence < threshold.
        """
        if not self._loaded:
            self._load_model()

        if self._load_error:
            raise RuntimeError(f"OmniLocalProvider failed to load: {self._load_error}")

        formatted = self._format_prompt(prompt)
        text, confidence = self._generate_with_confidence(formatted)

        logger.debug("OmniLocalProvider confidence=%.3f threshold=%.3f", confidence, self.CONFIDENCE_THRESHOLD)

        if confidence < self.CONFIDENCE_THRESHOLD:
            raise OmniLowConfidenceError(text, confidence)

        return text

    async def generate_stream(self, prompt: str):
        """Stream by yielding the full response as one chunk (local models don't token-stream)."""
        yield await self.generate(prompt)

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _load_model(self) -> None:
        try:
            import torch
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

            use_4bit = torch.cuda.is_available()
            bnb_cfg  = None
            if use_4bit:
                bnb_cfg = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_compute_dtype=torch.bfloat16,
                )

            logger.info("OmniLocalProvider: loading base model %s", BASE_MODEL_ID)
            # B615: set OMNI_BASE_MODEL_REVISION env var to a specific HuggingFace
            # commit hash in production to prevent model substitution between deployments.
            _base_revision = os.environ.get("OMNI_BASE_MODEL_REVISION")
            tokenizer = AutoTokenizer.from_pretrained(
                str(ADAPTER_PATH),  # tokenizer is saved alongside adapter
                trust_remote_code=True,
            )
            tokenizer.pad_token = tokenizer.eos_token

            base = AutoModelForCausalLM.from_pretrained(
                BASE_MODEL_ID,
                revision=_base_revision,
                cache_dir=str(BASE_CACHE_PATH),
                quantization_config=bnb_cfg,
                device_map="auto" if use_4bit else "cpu",
                trust_remote_code=True,
            )
            base.config.use_cache = True

            logger.info("OmniLocalProvider: loading LoRA adapter from %s", ADAPTER_PATH)
            model = PeftModel.from_pretrained(base, str(ADAPTER_PATH))
            model.eval()

            self._tokenizer = tokenizer
            self._model     = model
            self._loaded    = True
            logger.info("OmniLocalProvider: model ready")

        except Exception as exc:
            self._load_error = str(exc)
            self._loaded     = True  # prevent retry loops; error is surfaced on generate()
            logger.error("OmniLocalProvider: load failed — %s", exc)

    def _format_prompt(self, raw_prompt: str) -> str:
        system = "You are Chitti, an enterprise security AI assistant."
        return (
            f"<|system|>\n{system}</s>\n"
            f"<|user|>\n{raw_prompt}</s>\n"
            f"<|assistant|>\n"
        )

    def _generate_with_confidence(self, formatted_prompt: str) -> Tuple[str, float]:
        """
        Run greedy decoding with scores=True, compute geometric-mean confidence.
        Returns (generated_text, confidence).
        """
        import torch

        inputs = self._tokenizer(
            formatted_prompt,
            return_tensors="pt",
            truncation=True,
            max_length=512,
        ).to(self._model.device)

        with torch.no_grad():
            out = self._model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=False,          # greedy
                return_dict_in_generate=True,
                output_scores=True,
                pad_token_id=self._tokenizer.eos_token_id,
            )

        # Decode generated tokens (exclude the prompt prefix)
        input_len = inputs["input_ids"].shape[1]
        gen_ids   = out.sequences[0][input_len:]
        text      = self._tokenizer.decode(gen_ids, skip_special_tokens=True).strip()

        # Compute geometric mean of per-token top-1 softmax probabilities
        if out.scores:
            log_prob_sum = 0.0
            for score_t in out.scores:
                probs   = torch.softmax(score_t[0], dim=-1)
                top_p   = probs.max().item()
                log_prob_sum += math.log(max(top_p, 1e-9))
            confidence = math.exp(log_prob_sum / len(out.scores))
        else:
            confidence = 0.0

        return text, confidence
