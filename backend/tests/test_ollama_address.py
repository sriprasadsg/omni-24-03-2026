"""Where the platform's AI service looks for the local model (local_ip.ollama_candidate_urls, OllamaProvider).

Live on 2026-11-18 the saved setting named this server's LAN address (http://10.0.0.4:11434) while Ollama
listened on 127.0.0.1 only, so every AI feature outside the SOC fell back to the mock provider.
protects/fails_when/no_claim per test.
"""
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ai_providers
import local_ip

LAN = "10.0.0.4"


@pytest.fixture
def on_lan(monkeypatch):
    monkeypatch.setattr(local_ip, "get_local_ip", lambda: LAN)


def test_this_machines_address_also_tries_loopback_and_a_remote_one_is_tried_alone(on_lan):
    """protects=a saved LAN address of this machine is followed by 127.0.0.1 (same port); no address gives loopback
    first; a saved host without a scheme gets http://; a remote host is tried alone; fails_when=the AI service never
    reaches a loopback-only Ollama, or a configured remote server is silently replaced by the local one; no_claim=-"""
    assert local_ip.ollama_candidate_urls(f"http://{LAN}:11434/") == [f"http://{LAN}:11434", "http://127.0.0.1:11434"]
    assert local_ip.ollama_candidate_urls(f"{LAN}:11500") == [f"http://{LAN}:11500", "http://127.0.0.1:11500"]
    assert local_ip.ollama_candidate_urls(None) == ["http://127.0.0.1:11434", f"http://{LAN}:11434"]
    assert local_ip.ollama_candidate_urls("http://gpu-box.internal:11434") == ["http://gpu-box.internal:11434"]


@pytest.mark.asyncio
async def test_provider_uses_loopback_when_the_saved_lan_address_does_not_answer(on_lan, monkeypatch):
    """protects=configure() skips the dead LAN address, settles on 127.0.0.1, keeps the saved model and runs a
    one-token test with room for a cold model load; fails_when=the provider gives up after the first address (the
    live MockProvider fallback) or the start-up test can time out on a 12 s model load; no_claim=a real Ollama"""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, request.url.path, request.extensions.get("timeout", {}).get("read")))
        if request.url.host == LAN:
            raise httpx.ConnectError("connection refused", request=request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}]})
        body = request.read().decode()
        assert '"num_predict": 1' in body or '"num_predict":1' in body
        return httpx.Response(200, json={"response": "hi"})

    real = httpx.AsyncClient
    monkeypatch.setattr(ai_providers.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    provider = ai_providers.OllamaProvider()
    assert await provider.configure({"ollamaUrl": f"http://{LAN}:11434", "ollamaModel": "llama3.2:3b"}) is True
    assert provider.base_url == "http://127.0.0.1:11434" and provider.model_name == "llama3.2:3b"
    assert [(h, p) for h, p, _ in seen] == [(LAN, "/api/tags"), ("127.0.0.1", "/api/tags"), ("127.0.0.1", "/api/generate")]
    assert seen[-1][2] == 60.0


@pytest.mark.asyncio
async def test_provider_reports_failure_when_no_address_answers(on_lan, monkeypatch):
    """protects=configure() returns False when nothing answers, so the caller can fall back honestly;
    fails_when=a dead model is reported as configured; no_claim=-"""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    real = httpx.AsyncClient
    monkeypatch.setattr(ai_providers.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    assert await ai_providers.OllamaProvider().configure({"ollamaUrl": f"http://{LAN}:11434"}) is False
