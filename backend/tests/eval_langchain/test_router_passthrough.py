"""Live 9router `tools`/`response_format` passthrough smoke test.

Resolves RESEARCH Open Question 3 (LOW confidence): does the project-local
9router gateway forward `tools`/`response_format` request fields through to
Anthropic when addressed via `init_chat_model(model_provider="openai",
base_url=AI_ROUTER_URL)`, or does it strip/reject them?

This is the single highest-uncertainty integration point in Phase 39 — every
downstream agent-migration plan (39-06 auditor, 39-07 chat, 39-08
questionnaire, 39-09 narrative) depends on `create_agent(response_format=...)`
working through the gateway. Front-loading this test turns a silent
assumption into a go/no-go decision:

  PASS -> downstream agents use `create_agent(response_format=Schema)`
          directly (auto `ProviderStrategy`).
  FAIL -> downstream agents use the documented fallback: native
          `langchain-anthropic` `ChatAnthropic` direct route, or
          `ToolStrategy` tool-call emulation (AI-SPEC Section 4b /
          Pitfall 6).

Guarded to skip cleanly (never error) when `AI_ROUTER_URL` is unset — a
gateway-less CI/sandbox must not fail collection. Uses only the async
`ainvoke` call path (never the sync/blocking invoke call, never a manually
managed event loop) per AI-SPEC Section 4b's async-first rule; this backend
runs a single uvicorn event loop.
"""
import os

import pytest
from pydantic import BaseModel, Field

try:
    from langchain.agents import create_agent
    from langchain.chat_models import init_chat_model
    from langchain.tools import tool

    LANGCHAIN_AVAILABLE = True
except Exception:  # pragma: no cover - defensive, mirrors eval_questionnaire_auto_answer.py
    LANGCHAIN_AVAILABLE = False
    create_agent = init_chat_model = tool = None

AI_ROUTER_URL = os.environ.get("AI_ROUTER_URL")
AI_ROUTER_KEY = os.environ.get("AI_ROUTER_KEY", "")
AI_ROUTER_MODEL = os.environ.get("AI_ROUTER_MODEL", "claude-sonnet-4-6")

pytestmark = [
    pytest.mark.eval,
    pytest.mark.llm,
    pytest.mark.skipif(
        not AI_ROUTER_URL or not LANGCHAIN_AVAILABLE,
        reason=(
            "AI_ROUTER_URL not set (no live 9router gateway reachable in this "
            "environment) or langchain not installed — see 39-02-SUMMARY.md "
            "for the recorded fallback decision"
        ),
    ),
]

ECHO_PROBE_TEXT = "router-passthrough-check"

if LANGCHAIN_AVAILABLE:

    @tool
    def echo(text: str) -> str:
        """Echo the provided text back verbatim."""
        return text

else:  # pragma: no cover
    echo = None


class EchoResponse(BaseModel):
    """Minimal two-field structured-output schema for the response_format probe."""

    text: str = Field(description="The echoed text, verbatim")
    length: int = Field(description="Character length of the echoed text")


def _build_model():
    return init_chat_model(
        model=AI_ROUTER_MODEL,
        model_provider="openai",  # 9router speaks OpenAI-compatible wire format
        base_url=AI_ROUTER_URL,
        api_key=AI_ROUTER_KEY,
        temperature=0.0,
        max_tokens=256,
        timeout=30,
    )


async def test_router_tool_and_response_format_passthrough():
    """Live smoke test: bound-tool call + response_format structured output via 9router."""
    model = _build_model()

    # (a) Tool-call passthrough: bind one trivial tool, verify the model is
    # able to emit a tool call through the gateway.
    tool_agent = create_agent(model=model, tools=[echo])
    tool_result = await tool_agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": f"Call the echo tool with the text '{ECHO_PROBE_TEXT}'.",
                }
            ]
        }
    )
    tool_messages = tool_result.get("messages", [])
    tool_call_passthrough = any(getattr(m, "tool_calls", None) for m in tool_messages)

    # (b) response_format passthrough: create_agent(response_format=Schema)
    # verifies structured-output request/response shapes survive the gateway.
    structured_agent = create_agent(model=model, tools=[], response_format=EchoResponse)
    structured_result = await structured_agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Echo the text '{ECHO_PROBE_TEXT}' and report its "
                        f"length as {len(ECHO_PROBE_TEXT)}."
                    ),
                }
            ]
        }
    )
    structured_response = structured_result.get("structured_response")
    structured_passthrough = isinstance(structured_response, EchoResponse)

    passed = tool_call_passthrough and structured_passthrough
    decision = "PASS" if passed else "FAIL"
    downstream_path = (
        "response_format directly on create_agent (ProviderStrategy)"
        if passed
        else (
            "documented fallback -- native langchain-anthropic ChatAnthropic "
            "direct route, or ToolStrategy tool-call emulation "
            "(AI-SPEC Section 4b / Pitfall 6)"
        )
    )
    # Machine-readable decision line surfaced into pytest output and picked up
    # by the plan SUMMARY.
    print(f"[9ROUTER_PASSTHROUGH_DECISION] result={decision} downstream_path={downstream_path}")

    assert tool_call_passthrough, "9router did not forward the bound tool call to the model"
    assert structured_passthrough, "9router did not forward the response_format structured output"
