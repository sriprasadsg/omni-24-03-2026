"""The platform's own from-scratch model: architecture, data formatting, serving/fallback."""
import asyncio

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("tokenizers")

from ai_services import omni_scratch_data as data  # noqa: E402
from ai_services.omni_llm_scratch import OmniConfig, OmniLLM, load_checkpoint, save_checkpoint  # noqa: E402
from ai_services import omni_scratch_provider as prov  # noqa: E402
from ai_services.omni_scratch_train import _sft_example  # noqa: E402

TINY = OmniConfig(vocab_size=64, block_size=16, n_layer=2, n_head=2, n_embd=32, dropout=0.0)


def test_forward_loss_mask_and_generate():
    model = OmniLLM(TINY)
    x = torch.randint(0, 64, (2, 16))
    logits, loss = model(x, x)
    assert logits.shape == (2, 16, 64) and loss.item() > 0
    mask = torch.zeros(2, 16)
    _, masked = model(x, x, mask)  # nothing selected -> zero loss, not NaN
    assert masked.item() == 0.0
    out, conf = model.generate(x[:, :4], max_new_tokens=5)
    assert out.shape == (2, 9) and 0.0 < conf <= 1.0


def test_checkpoint_roundtrip(tmp_path):
    model = OmniLLM(TINY)
    save_checkpoint(model, tmp_path / "m.pt", val_loss=1.5)
    loaded, meta = load_checkpoint(tmp_path / "m.pt")
    assert meta["val_loss"] == 1.5
    x = torch.randint(0, 64, (1, 8))
    assert torch.allclose(model.eval()(x)[0], loaded(x)[0])


def test_tokenizer_and_answer_only_mask(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data, "TOKENIZER_PATH", tmp_path / "tokenizer.json")
    texts = ["Endpoint detection and response monitors endpoints for threats."] * 20
    tok = data.train_tokenizer(texts + [data.format_qa("What is EDR?", "It monitors endpoints.")], vocab_size=300)
    assert tok.decode(tok.encode("monitors endpoints").ids) == "monitors endpoints"
    assert tok.token_to_id(data.EOT) is not None and tok.token_to_id(data.ASSISTANT) is not None
    ids, mask = _sft_example(tok, "What is EDR?", "It monitors endpoints.", block=48, pad_id=tok.token_to_id(data.PAD))
    prompt_len = len(tok.encode(data.format_qa("What is EDR?")).ids)
    assert len(ids) == len(mask) == 49
    assert not any(mask[:prompt_len]) and all(mask[prompt_len:prompt_len + 3])


class _Teacher:
    name = "teacher"

    async def generate(self, prompt, temperature=None, max_tokens=1024):
        return "teacher answer"


def test_provider_defers_without_model_and_on_low_confidence(monkeypatch):
    p = prov.OmniScratchProvider(_Teacher())
    monkeypatch.setattr(prov.OmniScratchProvider, "available", staticmethod(lambda: False))
    assert asyncio.run(p.answer_question("What is EDR?")) is None
    assert prov.with_own_model(_Teacher()).__class__ is _Teacher  # nothing trained -> no wrap
    monkeypatch.setattr(prov.OmniScratchProvider, "available", staticmethod(lambda: True))
    monkeypatch.setattr(p, "_answer_sync", lambda q: ("A vague guess about things.", 0.05))
    assert asyncio.run(p.answer_question("What is EDR?")) is None
    assert p.stats["deferred_to_teacher"] == 1
    assert asyncio.run(p.generate("Return JSON with fields")) == "teacher answer"


def test_provider_answers_when_confident(monkeypatch):
    p = prov.OmniScratchProvider(_Teacher())
    monkeypatch.setattr(prov.OmniScratchProvider, "available", staticmethod(lambda: True))
    monkeypatch.setattr(p, "_answer_sync", lambda q: ("EDR monitors endpoints for threats.", 0.9))
    assert asyncio.run(p.answer_question("What is EDR?")) == "EDR monitors endpoints for threats."
    assert p.stats["own_answers"] == 1
