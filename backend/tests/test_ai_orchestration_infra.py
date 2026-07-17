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


# ---------------------------------------------------------------------------
# memory.py
# ---------------------------------------------------------------------------


class TestMemoryThreadId:
    def test_make_thread_id_contains_tenant_prefix(self):
        from ai_orchestration.memory import make_thread_id

        thread_id = make_thread_id("tA", "c1")
        assert "tA:" in thread_id
        assert thread_id == "tA:c1"

    def test_make_thread_id_distinct_across_tenants_same_conversation(self):
        from ai_orchestration.memory import make_thread_id

        thread_a = make_thread_id("tA", "c1")
        thread_b = make_thread_id("tB", "c1")
        assert thread_a != thread_b

    def test_make_thread_id_requires_tenant_id(self):
        from ai_orchestration.memory import make_thread_id

        with pytest.raises(ValueError):
            make_thread_id("", "c1")

    def test_make_thread_id_requires_conversation_id(self):
        from ai_orchestration.memory import make_thread_id

        with pytest.raises(ValueError):
            make_thread_id("tA", "")

    def test_memory_module_no_in_process_dict_pattern(self):
        import ai_orchestration.memory as memory_mod
        src = open(memory_mod.__file__).read()
        assert "demo_sessions" not in src.lower()
        assert "AsyncSqliteSaver" in src
        assert "data" in src  # stored under a data/ path

    async def test_checkpointer_lifespan_dev_mode_yields_in_memory_saver(self):
        from langgraph.checkpoint.memory import InMemorySaver
        from ai_orchestration.memory import checkpointer_lifespan

        async with checkpointer_lifespan(dev_mode=True) as checkpointer:
            assert isinstance(checkpointer, InMemorySaver)

    async def test_checkpointer_lifespan_default_yields_persistent_sqlite_saver(self):
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        import ai_orchestration.memory as memory_mod
        from ai_orchestration.memory import checkpointer_lifespan

        async with checkpointer_lifespan(dev_mode=False) as checkpointer:
            assert isinstance(checkpointer, AsyncSqliteSaver)
        assert os.path.isdir(memory_mod.DATA_DIR)
        assert "data" in memory_mod.CHECKPOINT_DB_PATH.split(os.sep)


# ---------------------------------------------------------------------------
# tracing.py
# ---------------------------------------------------------------------------


class TestTracingWiring:
    def test_required_span_attributes_present(self):
        from ai_orchestration.tracing import REQUIRED_SPAN_ATTRIBUTES

        assert "tenant_id" in REQUIRED_SPAN_ATTRIBUTES
        assert "surface" in REQUIRED_SPAN_ATTRIBUTES
        assert "PROMPT_VERSION" in REQUIRED_SPAN_ATTRIBUTES
        assert "model_provenance" in REQUIRED_SPAN_ATTRIBUTES

    def test_attach_span_attributes_sets_all_four(self):
        from ai_orchestration.tracing import attach_span_attributes

        span = MagicMock()
        attach_span_attributes(
            span,
            tenant_id="tenant-a",
            surface="auditor",
            prompt_version="v1",
            model_provenance="primary",
        )
        calls = {call.args[0]: call.args[1] for call in span.set_attribute.call_args_list}
        assert calls["tenant_id"] == "tenant-a"
        assert calls["surface"] == "auditor"
        assert calls["PROMPT_VERSION"] == "v1"
        assert calls["model_provenance"] == "primary"

    def test_instrument_langchain_degrades_on_import_error(self, monkeypatch):
        import sys as _sys
        from ai_orchestration.tracing import instrument_langchain

        # Simulate the package being absent: any import of
        # openinference.instrumentation.langchain raises ImportError.
        monkeypatch.setitem(_sys.modules, "openinference.instrumentation.langchain", None)
        provider = MagicMock()
        result = instrument_langchain(provider)
        assert result is False  # degraded, no exception raised

    def test_instrument_langchain_succeeds_when_package_present(self):
        from ai_orchestration.tracing import instrument_langchain

        provider = MagicMock()
        # openinference-instrumentation-langchain IS installed (39-01) — this
        # should succeed against a real (mocked) tracer_provider without a
        # live Phoenix endpoint (instrument() only registers callback hooks).
        result = instrument_langchain(provider)
        assert result is True

    def test_app_startup_wires_langchain_instrumentor(self):
        import app_startup

        src = open(app_startup.__file__).read()
        assert src.count("LangChainInstrumentor") >= 1

    def test_app_startup_imports_cleanly(self):
        import app_startup  # noqa: F401 — import-success is the assertion
