"""
Omni-Scratch: the platform's own language model, written and trained from scratch.

A small decoder-only (GPT-style) transformer built from plain PyTorch layers — no
pretrained weights. It is trained inside this project (omni_scratch_train.py) on the
project docs plus security Q&A distilled from the local open-source teacher model
(Ollama); omni_scratch_provider.py serves it and falls back to the teacher whenever
the model is not confident.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class OmniConfig:
    vocab_size: int = 8000
    block_size: int = 256   # context length in tokens
    n_layer: int = 6
    n_head: int = 6
    n_embd: int = 384       # ~14M parameters at these defaults
    dropout: float = 0.1


class CausalSelfAttention(nn.Module):
    def __init__(self, cfg: OmniConfig):
        super().__init__()
        assert cfg.n_embd % cfg.n_head == 0, "n_embd must be divisible by n_head"
        self.qkv = nn.Linear(cfg.n_embd, 3 * cfg.n_embd)
        self.proj = nn.Linear(cfg.n_embd, cfg.n_embd)
        self.n_head = cfg.n_head
        self.dropout = cfg.dropout
        self.resid_drop = nn.Dropout(cfg.dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, T, C = x.shape
        q, k, v = self.qkv(x).split(C, dim=2)
        q, k, v = (t.view(B, T, self.n_head, C // self.n_head).transpose(1, 2) for t in (q, k, v))
        y = F.scaled_dot_product_attention(
            q, k, v, is_causal=True, dropout_p=self.dropout if self.training else 0.0
        )
        y = y.transpose(1, 2).contiguous().view(B, T, C)
        return self.resid_drop(self.proj(y))


class Block(nn.Module):
    """Pre-norm transformer block: attention + MLP, each with a residual connection."""

    def __init__(self, cfg: OmniConfig):
        super().__init__()
        self.ln1 = nn.LayerNorm(cfg.n_embd)
        self.attn = CausalSelfAttention(cfg)
        self.ln2 = nn.LayerNorm(cfg.n_embd)
        self.mlp = nn.Sequential(
            nn.Linear(cfg.n_embd, 4 * cfg.n_embd),
            nn.GELU(),
            nn.Linear(4 * cfg.n_embd, cfg.n_embd),
            nn.Dropout(cfg.dropout),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.attn(self.ln1(x))
        return x + self.mlp(self.ln2(x))


class OmniLLM(nn.Module):
    def __init__(self, cfg: OmniConfig):
        super().__init__()
        self.cfg = cfg
        self.tok_emb = nn.Embedding(cfg.vocab_size, cfg.n_embd)
        self.pos_emb = nn.Embedding(cfg.block_size, cfg.n_embd)
        self.drop = nn.Dropout(cfg.dropout)
        self.blocks = nn.ModuleList(Block(cfg) for _ in range(cfg.n_layer))
        self.ln_f = nn.LayerNorm(cfg.n_embd)
        self.head = nn.Linear(cfg.n_embd, cfg.vocab_size, bias=False)
        self.head.weight = self.tok_emb.weight  # weight tying
        self.apply(self._init_weights)

    @staticmethod
    def _init_weights(module: nn.Module) -> None:
        if isinstance(module, (nn.Linear, nn.Embedding)):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
        if isinstance(module, nn.Linear) and module.bias is not None:
            nn.init.zeros_(module.bias)

    def num_params(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def forward(
        self,
        idx: torch.Tensor,
        targets: Optional[torch.Tensor] = None,
        loss_mask: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
        """Return (logits, loss). loss_mask (same shape as targets) limits the loss to
        selected positions — used to train only on the assistant's half of a Q&A pair."""
        _, T = idx.shape
        if T > self.cfg.block_size:
            raise ValueError(f"sequence length {T} exceeds block_size {self.cfg.block_size}")
        pos = torch.arange(T, device=idx.device)
        x = self.drop(self.tok_emb(idx) + self.pos_emb(pos))
        for block in self.blocks:
            x = block(x)
        logits = self.head(self.ln_f(x))
        if targets is None:
            return logits, None
        loss = F.cross_entropy(logits.view(-1, logits.size(-1)), targets.view(-1), reduction="none")
        if loss_mask is not None:
            mask = loss_mask.view(-1).float()
            loss = (loss * mask).sum() / mask.sum().clamp(min=1.0)
        else:
            loss = loss.mean()
        return logits, loss

    @torch.no_grad()
    def generate(
        self,
        idx: torch.Tensor,
        max_new_tokens: int,
        temperature: float = 0.7,
        top_k: int = 40,
        stop_id: Optional[int] = None,
    ) -> Tuple[torch.Tensor, float]:
        """Sample up to max_new_tokens. Returns (ids including the prompt, confidence),
        where confidence is the mean probability the model gave the tokens it chose."""
        self.eval()
        chosen_probs = []
        for _ in range(max_new_tokens):
            logits, _ = self(idx[:, -self.cfg.block_size:])
            logits = logits[:, -1, :] / max(temperature, 1e-5)
            if top_k:
                kth = torch.topk(logits, min(top_k, logits.size(-1))).values[:, [-1]]
                logits = logits.masked_fill(logits < kth, float("-inf"))
            probs = F.softmax(logits, dim=-1)
            nxt = torch.multinomial(probs, num_samples=1)
            if stop_id is not None and idx.size(0) == 1 and nxt.item() == stop_id:
                break  # early stop only for single-sequence generation (serving)
            chosen_probs.append(probs.gather(1, nxt).mean().item())
            idx = torch.cat([idx, nxt], dim=1)
        confidence = sum(chosen_probs) / len(chosen_probs) if chosen_probs else 0.0
        return idx, confidence


def save_checkpoint(model: OmniLLM, path: Path, **extra) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    torch.save({"config": asdict(model.cfg), "state_dict": model.state_dict(), **extra}, tmp)
    tmp.replace(path)  # atomic: a crash mid-save never leaves a corrupt checkpoint


def load_checkpoint(path: Path) -> Tuple[OmniLLM, dict]:
    ckpt = torch.load(path, map_location="cpu", weights_only=True)
    model = OmniLLM(OmniConfig(**ckpt["config"]))
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    meta = {k: v for k, v in ckpt.items() if k not in ("config", "state_dict")}
    return model, meta
