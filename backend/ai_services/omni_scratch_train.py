"""
Train the from-scratch Omni model.

    cd backend && venv/bin/python -m ai_services.omni_scratch_train all
    (stages: generate | tokenizer | train | all; see --help)

1. generate  — distil passages + Q&A from the local teacher model (Ollama); resumable.
2. tokenizer — train a byte-level BPE tokenizer on the corpus (nothing pretrained).
3. train     — pretrain on docs + passages (+ formatted Q&A), then instruction-tune on
               the Q&A pairs with the loss on the answer tokens only. Writes the model to
               DATA_DIR/omni_scratch.pt and live progress to DATA_DIR/status.json.
Runs at low CPU priority so the platform's services stay responsive.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from datetime import datetime, timezone
from typing import List, Tuple

import torch

from ai_services.omni_llm_scratch import OmniConfig, OmniLLM, save_checkpoint
from ai_services import omni_scratch_data as data

EVAL_QUESTIONS = [
    "What is EDR?",
    "How do you defend against ransomware?",
    "What does the principle of least privilege mean?",
]


def write_status(**fields) -> None:
    data.DATA_DIR.mkdir(parents=True, exist_ok=True)
    current = {}
    if data.STATUS_PATH.exists():
        try:
            current = json.loads(data.STATUS_PATH.read_text())
        except json.JSONDecodeError:
            current = {}
    current.update(fields, updated_at=datetime.now(timezone.utc).isoformat())
    tmp = data.STATUS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(current, indent=1))
    tmp.replace(data.STATUS_PATH)


def _lr(step: int, total: int, base: float, warmup: int = 100) -> float:
    if step < warmup:
        return base * (step + 1) / warmup
    progress = (step - warmup) / max(1, total - warmup)
    return base * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * progress)))


def _sft_example(tok, question: str, answer: str, block: int, pad_id: int) -> Tuple[List[int], List[int]]:
    """Token ids (block+1) and a mask that is 1 only on answer tokens."""
    prompt = tok.encode(data.format_qa(question)).ids
    reply = tok.encode(answer.strip() + data.EOT).ids
    ids = (prompt + reply)[: block + 1]
    mask = ([0] * len(prompt) + [1] * len(reply))[: block + 1]
    pad = block + 1 - len(ids)
    return ids + [pad_id] * pad, mask + [0] * pad


def sample_answer(model: OmniLLM, tok, question: str, max_new_tokens: int = 120) -> Tuple[str, float]:
    ids = torch.tensor([tok.encode(data.format_qa(question)).ids])
    out, conf = model.generate(ids, max_new_tokens, temperature=0.7, top_k=40,
                               stop_id=tok.token_to_id(data.EOT))
    return tok.decode(out[0, ids.shape[1]:].tolist()).strip(), conf


def train(pretrain_steps: int, sft_steps: int, batch_size: int, lr: float, cfg: OmniConfig) -> dict:
    torch.manual_seed(1337)
    random.seed(1337)
    tok = data.load_tokenizer()
    cfg.vocab_size = tok.get_vocab_size()
    eot, pad = tok.token_to_id(data.EOT), tok.token_to_id(data.PAD)
    texts, qa = data.corpus()
    if not qa:
        raise SystemExit("No Q&A pairs yet — run the 'generate' stage first.")
    random.shuffle(qa)
    n_val = max(1, len(qa) // 10)
    qa_val, qa_train = qa[:n_val], qa[n_val:]

    # Pretraining stream: docs + passages + training Q&A (formatted), separated by EOT.
    stream: List[int] = []
    for text in texts + [data.format_qa(q, a) for q, a in qa_train]:
        stream.extend(tok.encode(text).ids + [eot])
    stream_t = torch.tensor(stream, dtype=torch.long)
    split = int(len(stream_t) * 0.95)
    pre_train, pre_val = stream_t[:split], stream_t[split:]

    sft_train = [_sft_example(tok, q, a, cfg.block_size, pad) for q, a in qa_train]
    sft_val = [_sft_example(tok, q, a, cfg.block_size, pad) for q, a in qa_val]

    model = OmniLLM(cfg)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.1, betas=(0.9, 0.95))
    total = pretrain_steps + sft_steps
    write_status(stage="train", step=0, total_steps=total, params=model.num_params(),
                 corpus_tokens=len(stream), qa_train=len(qa_train), qa_val=len(qa_val))

    def lm_batch(src: torch.Tensor):
        ix = torch.randint(0, len(src) - cfg.block_size - 1, (batch_size,))
        x = torch.stack([src[i:i + cfg.block_size] for i in ix])
        y = torch.stack([src[i + 1:i + 1 + cfg.block_size] for i in ix])
        return x, y, None

    def sft_batch(examples):
        picked = random.sample(examples, min(batch_size, len(examples)))
        ids = torch.tensor([e[0] for e in picked])
        mask = torch.tensor([e[1] for e in picked])
        return ids[:, :-1], ids[:, 1:], mask[:, 1:]

    @torch.no_grad()
    def evaluate(sft: bool) -> float:
        model.eval()
        losses = []
        for _ in range(8):
            if sft:
                x, y, m = sft_batch(sft_val)
            elif len(pre_val) > cfg.block_size + 1:
                x, y, m = lm_batch(pre_val)
            else:
                return float("nan")
            losses.append(model(x, y, m)[1].item())
        model.train()
        return sum(losses) / len(losses)

    model.train()
    best_val, t0, loss_val, val = float("inf"), time.time(), float("nan"), float("nan")
    for step in range(total):
        sft = step >= pretrain_steps
        for group in opt.param_groups:
            group["lr"] = _lr(step, total, lr)
        x, y, m = sft_batch(sft_train) if sft else lm_batch(pre_train)
        _, loss = model(x, y, m)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        loss_val = loss.item()
        if step % 25 == 0 or step == total - 1:
            done = step + 1
            eta = (time.time() - t0) / done * (total - done)
            write_status(stage="sft" if sft else "pretrain", step=done, loss=round(loss_val, 4),
                         eta_seconds=int(eta))
        if (step + 1) % 250 == 0 or step == total - 1:
            val = evaluate(sft)
            write_status(val_loss=round(val, 4))
            if sft and val < best_val:
                best_val = val
                save_checkpoint(model, data.CHECKPOINT_PATH, val_loss=val, step=step + 1,
                                trained_at=datetime.now(timezone.utc).isoformat())
        if step + 1 == pretrain_steps:
            save_checkpoint(model, data.CHECKPOINT_PATH, val_loss=float("nan"), step=step + 1,
                            trained_at=datetime.now(timezone.utc).isoformat())

    samples = {q: dict(zip(("answer", "confidence"), sample_answer(model, tok, q))) for q in EVAL_QUESTIONS}
    write_status(stage="done", best_val_loss=round(best_val, 4), samples=samples,
                 minutes=round((time.time() - t0) / 60, 1))
    return {"best_val_loss": best_val, "samples": samples}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["generate", "tokenizer", "train", "all"])
    ap.add_argument("--max-topics", type=int, default=0, help="limit teacher topics (0 = all)")
    ap.add_argument("--pretrain-steps", type=int, default=1500)
    ap.add_argument("--sft-steps", type=int, default=1500)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--n-layer", type=int, default=6)
    ap.add_argument("--n-embd", type=int, default=384)
    ap.add_argument("--n-head", type=int, default=6)
    args = ap.parse_args()

    try:
        os.nice(10)  # keep the platform responsive while training on CPU
    except OSError:
        pass
    torch.set_num_threads(os.cpu_count() or 1)

    if args.stage in ("generate", "all"):
        write_status(stage="generate")
        added = data.generate_teacher_data(
            args.max_topics,
            progress=lambda i, n, t: write_status(stage="generate", topic=t, topic_index=i, topics_total=n),
        )
        print(f"teacher data: +{added} rows -> {data.GENERATED_PATH}")
    if args.stage in ("tokenizer", "all"):
        texts, qa = data.corpus()
        tok = data.train_tokenizer(texts + [data.format_qa(q, a) for q, a in qa])
        print(f"tokenizer: vocab {tok.get_vocab_size()} -> {data.TOKENIZER_PATH}")
    if args.stage in ("train", "all"):
        cfg = OmniConfig(n_layer=args.n_layer, n_embd=args.n_embd, n_head=args.n_head)
        result = train(args.pretrain_steps, args.sft_steps, args.batch_size, args.lr, cfg)
        print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
