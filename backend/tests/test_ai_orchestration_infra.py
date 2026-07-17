"""Unit tests for Phase 39 ai_orchestration infra: models.py, memory.py, tracing.py.

Convention: hermetic — no live model/gateway/network calls. Model construction
(`init_chat_model(...)`) is lazy for every provider used here (ChatOpenAI,
ChatOllama, ChatAnthropic all construct without a network round-trip), so a
mocked Motor-style `db` handle is sufficient to exercise the full tenant
settings -> model factory path.

Naming: `-k models` selects factory tests, `-k memory` selects checkpointer/
thread-id tests, `-k tracing` selects instrumentation-wiring tests — matching
this plan's three per-task `<verify>` commands.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from ai_orchestration.models import (
    ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH,
    build_model_for_tenant,
    invalidate_tenant_model_cache,
    model_provenance,
)


def _mock_db(settings_doc):
    # spec=["system_settings"] prevents MagicMock's attribute auto-creation
    # from spoofing a truthy `db._db` (the ai_service.py `raw = db._db if
    # hasattr(db, "_db") else db` unwrap pattern models.py mirrors).
    db = MagicMock(spec=["system_settings"])
    db.system_settings = MagicMock()
    db.system_settings.find_one = AsyncMock(return_value=settings_doc)
    return db


# ---------------------------------------------------------------------------
# models.py
# ---------------------------------------------------------------------------


class TestModelsFactory:
    async def test_router_settings_build_fallback_chain(self):
        os.environ.pop("AI_ROUTER_URL", None)
        os.environ.pop("AI_ROUTER_KEY", None)
        settings = {
            "type": "llm",
            "tenantId": "tenant-a",
            "provider": "9router",
            "routerUrl": "http://localhost:9999/v1",
            "apiKey": "test-router-key",
            "model": "claude-sonnet-4-6",
        }
        db = _mock_db(settings)
        chain = await build_model_for_tenant("tenant-a", db, surface="auditor")
        assert hasattr(chain, "with_fallbacks") or hasattr(chain, "runnable")
        db.system_settings.find_one.assert_awaited_once_with(
            {"type": "llm", "tenantId": "tenant-a"}
        )

    async def test_ollama_settings_build_chain(self):
        settings = {
            "type": "llm",
            "tenantId": "tenant-b",
            "provider": "ollama",
            "ollamaUrl": "http://localhost:11434",
            "ollamaModel": "llama3.2:3b",
        }
        db = _mock_db(settings)
        chain = await build_model_for_tenant("tenant-b", db, surface="questionnaire")
        assert chain is not None

    async def test_anthropic_settings_build_chain(self):
        settings = {
            "type": "llm",
            "tenantId": "tenant-c",
            "provider": "anthropic",
            "apiKey": "test-anthropic-key",
            "model": "claude-sonnet-4-6",
        }
        db = _mock_db(settings)
        chain = await build_model_for_tenant("tenant-c", db, surface="narrative")
        assert chain is not None

    async def test_no_tenant_settings_defaults_to_router_or_degrades_gracefully(self):
        db = _mock_db(None)
        os.environ["OLLAMA_URL"] = "http://localhost:11434"
        chain = await build_model_for_tenant("tenant-unknown", db, surface="chat")
        assert chain is not None

    async def test_unavailable_gemini_provider_degrades_to_local_without_raising(self):
        settings = {
            "type": "llm",
            "tenantId": "tenant-d",
            "provider": "Gemini",
            "apiKey": "test-gemini-key",
            "model": "gemini-2.0-flash",
        }
        db = _mock_db(settings)
        # langchain-google-genai is intentionally not installed for this
        # phase (39-01-SUMMARY.md pinned only 8 langchain-ecosystem packages);
        # this must degrade to the local Ollama primary, never raise.
        chain = await build_model_for_tenant("tenant-d", db, surface="chat")
        assert chain is not None

    def test_models_uses_init_chat_model_and_with_fallbacks(self):
        import ai_orchestration.models as models_mod
        src = open(models_mod.__file__).read()
        assert "init_chat_model" in src
        assert ".with_fallbacks(" in src

    def test_models_reuses_single_ai_service_cache_no_second_cache(self):
        import ai_orchestration.models as models_mod
        src = open(models_mod.__file__).read()
        assert "system_settings" in src
        assert "invalidate_tenant_provider" in src
        assert "_tenant_providers" not in src

    def test_invalidate_tenant_model_cache_delegates_to_ai_service(self, monkeypatch):
        from ai_orchestration import models as models_mod

        called = {}

        def fake_invalidate(tenant_id):
            called["tenant_id"] = tenant_id

        monkeypatch.setattr(models_mod.ai_service, "invalidate_tenant_provider", fake_invalidate)
        invalidate_tenant_model_cache("tenant-x")
        assert called["tenant_id"] == "tenant-x"

    def test_model_provenance_primary(self):
        response = MagicMock()
        response.response_metadata = {"model_name": "claude-sonnet-4-6"}
        result = model_provenance(response, primary_model_name="claude-sonnet-4-6")
        assert result == "primary"

    def test_model_provenance_fallback(self):
        response = MagicMock()
        response.response_metadata = {"model": "llama3.2:3b"}
        result = model_provenance(
            response, primary_model_name="claude-sonnet-4-6", fallback_model_name="llama3.2:3b"
        )
        assert result.startswith("fallback:")
        assert "llama3.2:3b" in result

    def test_model_provenance_missing_metadata_defaults_primary(self):
        response = MagicMock()
        response.response_metadata = {}
        result = model_provenance(response, primary_model_name="claude-sonnet-4-6")
        assert result == "primary"

    def test_router_passthrough_decision_recorded(self):
        # 39-02 recorded UNRESOLVED-IN-THIS-SANDBOX, conservatively FAIL.
        assert ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH == "FAIL"
