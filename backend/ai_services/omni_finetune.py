"""
OmniFineTuner — QLoRA fine-tuning loop for TinyLlama-1.1B-Chat-v1.0.

Uses:
  - transformers  → AutoTokenizer, AutoModelForCausalLM
  - peft          → LoraConfig, get_peft_model, PeftModel
  - trl           → SFTTrainer, SFTConfig
  - bitsandbytes  → BitsAndBytesConfig (NF4 4-bit quantization)
  - datasets      → load_dataset (JSONL → Dataset)

The adapter is saved to OMNI_ADAPTER_PATH (default: omni_data/adapter/).
The base model is cached at OMNI_BASE_MODEL_CACHE (default: omni_data/base_model/).
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

BASE_MODEL_ID   = os.getenv("OMNI_BASE_MODEL", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
ADAPTER_PATH    = Path(os.getenv("OMNI_ADAPTER_PATH",    "omni_data/adapter"))
BASE_CACHE_PATH = Path(os.getenv("OMNI_BASE_MODEL_CACHE", "omni_data/base_model"))
DATASET_JSONL   = Path(os.getenv("OMNI_DATASET_PATH",    "omni_data/dataset.jsonl"))

# Training hyperparameters — tunable via env
_EPOCHS       = int(os.getenv("OMNI_EPOCHS",    "3"))
_BATCH_SIZE   = int(os.getenv("OMNI_BATCH",     "2"))
_GRAD_ACC     = int(os.getenv("OMNI_GRAD_ACC",  "4"))
_LR           = float(os.getenv("OMNI_LR",      "2e-4"))
_MAX_SEQ_LEN  = int(os.getenv("OMNI_MAX_SEQ",   "512"))
_LORA_R       = int(os.getenv("OMNI_LORA_R",    "16"))
_LORA_ALPHA   = int(os.getenv("OMNI_LORA_ALPHA","32"))


def _alpaca_format(example: Dict[str, str]) -> Dict[str, str]:
    """
    Convert instruction-tuning triplet to TinyLlama chat template string.
    TinyLlama uses <|system|>...<|user|>...<|assistant|>... format.
    """
    system = "You are Chitti, an enterprise security AI assistant."
    user_msg = example.get("instruction", "")
    if example.get("input", "").strip():
        user_msg = f"{user_msg}\n\n{example['input']}"
    output = example.get("output", "")
    text = (
        f"<|system|>\n{system}</s>\n"
        f"<|user|>\n{user_msg}</s>\n"
        f"<|assistant|>\n{output}</s>"
    )
    return {"text": text}


class OmniFineTuner:
    """
    Manages QLoRA fine-tuning of TinyLlama-1.1B on the Omni dataset.

    Usage (async context):
        tuner = OmniFineTuner()
        for progress in tuner.train(dataset_path, on_progress=cb):
            pass  # cb receives {"epoch": int, "step": int, "loss": float, "status": str}
    """

    def __init__(self):
        self.adapter_path    = ADAPTER_PATH
        self.base_cache_path = BASE_CACHE_PATH
        self.base_model_id   = BASE_MODEL_ID

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def is_trained(self) -> bool:
        """True if a saved LoRA adapter exists on disk."""
        return (self.adapter_path / "adapter_config.json").exists()

    def get_info(self) -> Dict[str, Any]:
        config_path = self.adapter_path / "adapter_config.json"
        if not config_path.exists():
            return {"trained": False, "adapter_path": str(self.adapter_path)}
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
        return {
            "trained":      True,
            "base_model":   cfg.get("base_model_name_or_path", self.base_model_id),
            "lora_r":       cfg.get("r", _LORA_R),
            "adapter_path": str(self.adapter_path),
        }

    def train(
        self,
        dataset_path: Optional[Path] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Run QLoRA fine-tuning synchronously (call from a background thread/process).

        on_progress is called with progress dicts at each logging step and epoch end.
        Returns final metrics dict.
        """
        jsonl = dataset_path or DATASET_JSONL
        if not jsonl.exists():
            raise FileNotFoundError(f"Dataset not found: {jsonl}. Run dataset builder first.")

        _report = on_progress or (lambda x: None)

        # ── 1. Imports (deferred so server starts without GPU) ──────────
        try:
            import torch
            from datasets import load_dataset
            from peft import LoraConfig, get_peft_model, TaskType
            from transformers import (
                AutoModelForCausalLM,
                AutoTokenizer,
                BitsAndBytesConfig,
                TrainerCallback,
                TrainerControl,
                TrainerState,
                TrainingArguments,
            )
            from trl import SFTTrainer, SFTConfig
        except ImportError as exc:
            raise ImportError(
                f"Missing fine-tuning dependency: {exc}. "
                "Install: pip install peft trl datasets bitsandbytes"
            ) from exc

        _report({"status": "Loading dataset", "epoch": 0, "step": 0, "loss": 0.0})

        # ── 2. Load & format dataset ────────────────────────────────────
        raw = load_dataset("json", data_files=str(jsonl), split="train")
        dataset = raw.map(_alpaca_format, remove_columns=raw.column_names)
        logger.info("Fine-tune dataset: %d samples", len(dataset))

        _report({"status": "Loading base model", "epoch": 0, "step": 0, "loss": 0.0})

        # ── 3. 4-bit quantisation config ────────────────────────────────
        use_4bit = torch.cuda.is_available()
        bnb_cfg = None
        if use_4bit:
            bnb_cfg = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
            )

        # ── 4. Load tokenizer + base model ──────────────────────────────
        # B615: set OMNI_FINETUNE_MODEL_REVISION env var to a specific HuggingFace
        # commit hash in production to prevent model substitution between runs.
        _ft_revision = os.environ.get("OMNI_FINETUNE_MODEL_REVISION")
        self.base_cache_path.mkdir(parents=True, exist_ok=True)
        tokenizer = AutoTokenizer.from_pretrained(
            self.base_model_id,
            revision=_ft_revision,
            cache_dir=str(self.base_cache_path),
            trust_remote_code=True,
        )
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.padding_side = "right"

        model = AutoModelForCausalLM.from_pretrained(
            self.base_model_id,
            revision=_ft_revision,
            cache_dir=str(self.base_cache_path),
            quantization_config=bnb_cfg,
            device_map="auto" if use_4bit else "cpu",
            trust_remote_code=True,
        )
        model.config.use_cache = False

        # ── 5. LoRA adapter ─────────────────────────────────────────────
        lora_cfg = LoraConfig(
            r=_LORA_R,
            lora_alpha=_LORA_ALPHA,
            target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
            lora_dropout=0.05,
            bias="none",
            task_type=TaskType.CAUSAL_LM,
        )
        model = get_peft_model(model, lora_cfg)
        model.print_trainable_parameters()

        _report({"status": "Training", "epoch": 0, "step": 0, "loss": 0.0})

        # ── 6. Progress callback ─────────────────────────────────────────
        class _ProgressCB(TrainerCallback):
            def on_log(self, args, state: TrainerState, control: TrainerControl, logs=None, **kw):
                if logs:
                    _report({
                        "status":  "Training",
                        "epoch":   int(state.epoch or 0),
                        "step":    state.global_step,
                        "loss":    round(logs.get("loss", logs.get("train_loss", 0.0)), 4),
                        "lr":      logs.get("learning_rate", _LR),
                    })

            def on_epoch_end(self, args, state: TrainerState, control: TrainerControl, **kw):
                _report({
                    "status": f"Epoch {int(state.epoch or 0)} complete",
                    "epoch":  int(state.epoch or 0),
                    "step":   state.global_step,
                    "loss":   0.0,
                })

        # ── 7. SFT training ─────────────────────────────────────────────
        output_tmp = self.adapter_path.parent / "adapter_tmp"
        output_tmp.mkdir(parents=True, exist_ok=True)

        sft_cfg = SFTConfig(
            output_dir=str(output_tmp),
            num_train_epochs=_EPOCHS,
            per_device_train_batch_size=_BATCH_SIZE,
            gradient_accumulation_steps=_GRAD_ACC,
            learning_rate=_LR,
            fp16=torch.cuda.is_available() and not use_4bit,
            bf16=use_4bit and torch.cuda.is_available(),
            logging_steps=10,
            save_steps=0,             # we save manually after training
            warmup_ratio=0.03,
            lr_scheduler_type="cosine",
            report_to="none",
            dataset_text_field="text",
            max_seq_length=_MAX_SEQ_LEN,
            packing=False,
        )

        trainer = SFTTrainer(
            model=model,
            train_dataset=dataset,
            args=sft_cfg,
            processing_class=tokenizer,
            callbacks=[_ProgressCB()],
        )

        train_result = trainer.train()

        # ── 8. Save adapter ─────────────────────────────────────────────
        _report({"status": "Saving adapter", "epoch": _EPOCHS, "step": train_result.global_step, "loss": 0.0})
        self.adapter_path.mkdir(parents=True, exist_ok=True)
        trainer.model.save_pretrained(str(self.adapter_path))
        tokenizer.save_pretrained(str(self.adapter_path))

        _report({"status": "Completed", "epoch": _EPOCHS, "step": train_result.global_step, "loss": 0.0})
        logger.info("Fine-tuning complete. Adapter saved to %s", self.adapter_path)

        return {
            "status":       "Completed",
            "global_step":  train_result.global_step,
            "train_loss":   round(train_result.training_loss, 4),
            "adapter_path": str(self.adapter_path),
        }
