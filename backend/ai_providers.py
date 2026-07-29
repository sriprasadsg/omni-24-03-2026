"""AI provider implementations: Gemini, Ollama, Anthropic, Mock."""

import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

import httpx

from local_ip import ollama_default_url

logger = logging.getLogger(__name__)


class AIProvider(ABC):
    @abstractmethod
    async def configure(self, settings: dict) -> bool:
        pass

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        pass

    async def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        """Stream response tokens. Default: yield full response as one chunk."""
        yield await self.generate(prompt)

    @property
    @abstractmethod
    def name(self) -> str:
        pass


class GeminiProvider(AIProvider):
    def __init__(self):
        self.client = None
        self.model_name = "gemini-2.0-flash"

    @property
    def name(self) -> str:
        return "Gemini"

    async def configure(self, settings: dict) -> bool:
        api_key = settings.get("apiKey")
        if not api_key:
            return False
        try:
            from google import genai
            self.client = genai.Client(api_key=api_key)
            self.model_name = settings.get("model", "gemini-2.0-flash")
            return True
        except Exception as e:
            logger.warning("Gemini configuration failed: %s", e)
            return False

    async def generate(self, prompt: str) -> str:
        if not self.client:
            raise RuntimeError("Gemini client not initialized")
        response = self.client.models.generate_content(model=self.model_name, contents=prompt)
        return response.text

    async def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        if not self.client:
            raise RuntimeError("Gemini client not initialized")
        try:
            for chunk in self.client.models.generate_content_stream(
                model=self.model_name, contents=prompt
            ):
                if chunk.text:
                    yield chunk.text
        except Exception:
            yield await self.generate(prompt)


class OllamaProvider(AIProvider):
    def __init__(self):
        self.base_url = ollama_default_url()
        self.model_name = "llama3"

    @property
    def name(self) -> str:
        return "Ollama (Local)"

    async def configure(self, settings: dict) -> bool:
        self.base_url = settings.get("ollamaUrl") or ollama_default_url()
        self.model_name = settings.get("ollamaModel", "llama3.2:3b")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code != 200:
                    return False
                models = resp.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                if not any(self.model_name in n or n.startswith(self.model_name.split(":")[0]) for n in model_names):
                    logger.warning(
                        "Ollama running but model '%s' not found. Available: %s",
                        self.model_name, model_names,
                    )
                    return False
                # Quick generation test to verify model actually runs
                test_resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": self.model_name, "prompt": "hi", "stream": False},
                    timeout=15.0,
                )
                return test_resp.status_code == 200
        except Exception as exc:
            logger.debug("Ollama connectivity check failed: %s", exc)
        return False

    async def generate(self, prompt: str) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {"model": self.model_name, "prompt": prompt, "stream": False}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json().get("response", "")

    async def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        import json as _json
        url = f"{self.base_url}/api/generate"
        payload = {"model": self.model_name, "prompt": prompt, "stream": True}
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = _json.loads(line)
                            chunk = data.get("response", "")
                            if chunk:
                                yield chunk
                            if data.get("done"):
                                break
                        except _json.JSONDecodeError:
                            continue
        except Exception:
            yield await self.generate(prompt)


class AnthropicProvider(AIProvider):
    def __init__(self):
        self.api_key: Optional[str] = None
        self.model_name = "claude-sonnet-4-6"

    @property
    def name(self) -> str:
        return "Anthropic Claude"

    async def configure(self, settings: dict) -> bool:
        api_key = settings.get("apiKey") or settings.get("anthropicApiKey")
        if not api_key:
            return False
        self.api_key = api_key
        self.model_name = settings.get("model", "claude-sonnet-4-6")
        return True

    async def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("Anthropic API key not configured")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model_name,
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            return resp.json()["content"][0]["text"]

    async def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        if not self.api_key:
            raise RuntimeError("Anthropic API key not configured")
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.model_name,
                        "max_tokens": 1024,
                        "stream": True,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                ) as resp:
                    resp.raise_for_status()
                    import json as _json
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:]
                        if raw == "[DONE]":
                            break
                        try:
                            data = _json.loads(raw)
                            if data.get("type") == "content_block_delta":
                                text = data.get("delta", {}).get("text", "")
                                if text:
                                    yield text
                        except _json.JSONDecodeError:
                            continue
        except Exception:
            yield await self.generate(prompt)


class OpenAICompatProvider(AIProvider):
    """OpenAI-compatible chat-completions provider (e.g. the 9router gateway).

    Talks to `{base_url}/v1/chat/completions`. Sends stream:false for a single
    JSON body and omits `temperature` for models that reject it (Claude 5 family
    returns 400 "temperature is deprecated for this model").
    """

    def __init__(self):
        self.base_url = ""
        self.api_key = ""
        self.model_name = ""

    @property
    def name(self) -> str:
        return "OpenAI-Compatible"

    async def configure(self, settings: dict) -> bool:
        import os
        self.base_url = (settings.get("baseUrl") or settings.get("routerUrl")
                         or os.getenv("AI_ROUTER_URL") or "").rstrip("/")
        self.api_key = (settings.get("apiKey") or os.getenv("AI_ROUTER_KEY") or "")
        self.model_name = (settings.get("model") or os.getenv("AI_ROUTER_MODEL") or "")
        if not (self.base_url and self.api_key and self.model_name):
            logger.warning("OpenAICompatProvider: baseUrl/apiKey/model incomplete")
            return False
        return True

    def _payload(self, prompt: str) -> dict:
        body = {
            "model": self.model_name,
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
        }
        # Claude 5 models reject temperature; only send it for others.
        if "claude" not in self.model_name.lower():
            body["temperature"] = 0.1
        return body

    async def generate(self, prompt: str) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=self._payload(prompt), headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]


class MockProvider(AIProvider):
    _DEGRADED_NOTICE = (
        "\n\n⚠️ **AI running in limited mode** — no LLM provider is configured. "
        "Configure an LLM (Anthropic, Gemini, or Ollama) in Settings → AI Configuration for full capabilities."
    )

    @property
    def name(self) -> str:
        return "Limited Mode (No LLM configured)"

    async def configure(self, _settings: dict) -> bool:
        return True

    async def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        import asyncio
        full = await self.generate(prompt)
        # Simulate token-by-token streaming: yield word by word
        for i, word in enumerate(full.split(" ")):
            yield word + (" " if i < len(full.split(" ")) - 1 else "")
            await asyncio.sleep(0.04)

    async def generate(self, prompt: str) -> str:
        lower_prompt = prompt.lower()
        if "dashboard" in lower_prompt:
            base = "The dashboard provides a real-time overview of your enterprise security posture. [NAVIGATE:dashboard]"
        elif "agent" in lower_prompt:
            base = "I can help you monitor and manage your active agents. [NAVIGATE:agents]"
        elif "alert" in lower_prompt or "incident" in lower_prompt:
            base = "Navigate to the Alerts section to review and triage active security incidents. [NAVIGATE:alerts]"
        elif "compliance" in lower_prompt:
            base = "Compliance frameworks (NIST, CIS, ISO 27001, HIPAA, PCI-DSS, SOC 2) are available in the Compliance section. [NAVIGATE:compliance]"
        elif "threat" in lower_prompt:
            base = "Threat hunting and intelligence are available in the Threat Intelligence section. [NAVIGATE:threats]"
        else:
            base = "I can assist with security operations, compliance, threat hunting, and agent management."
        return base + self._DEGRADED_NOTICE
