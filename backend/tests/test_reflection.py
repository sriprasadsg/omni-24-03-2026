"""Hermetic unit tests for the evaluator-optimizer primitive
(ai_orchestration/reflection.py). No live LLM — evaluate/regenerate are fakes.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from ai_orchestration.reflection import (
    ReflectionOutcome,
    build_llm_critic,
    reflect_and_revise,
)


class TestReflectLoop:
    async def test_zero_iters_returns_initial_untouched(self):
        evaluate = AsyncMock()
        regen = AsyncMock()
        out = await reflect_and_revise("x", evaluate=evaluate, regenerate=regen, max_iters=0)
        assert out.output == "x" and out.revised is False and out.iterations == 0
        evaluate.assert_not_awaited()

    async def test_accept_shortcircuit_skips_evaluate(self):
        evaluate = AsyncMock()
        out = await reflect_and_revise(
            "good", evaluate=evaluate, regenerate=AsyncMock(),
            accept=lambda o: o == "good", max_iters=2,
        )
        assert out.output == "good" and out.revised is False
        evaluate.assert_not_awaited()

    async def test_accepted_first_pass_no_revision(self):
        evaluate = AsyncMock(return_value=(True, ""))
        regen = AsyncMock()
        out = await reflect_and_revise("v1", evaluate=evaluate, regenerate=regen, max_iters=2)
        assert out.output == "v1" and out.revised is False and out.iterations == 1
        regen.assert_not_awaited()

    async def test_single_revision_on_critique(self):
        evaluate = AsyncMock(side_effect=[(False, "add a citation"), (True, "")])
        regen = AsyncMock(return_value="v2")
        out = await reflect_and_revise("v1", evaluate=evaluate, regenerate=regen, max_iters=2)
        assert out.output == "v2" and out.revised is True
        assert out.critiques == ["add a citation"]
        regen.assert_awaited_once_with("add a citation")

    async def test_respects_max_iters_budget(self):
        evaluate = AsyncMock(return_value=(False, "still weak"))
        regen = AsyncMock(side_effect=lambda c: "revised")
        out = await reflect_and_revise("v1", evaluate=evaluate, regenerate=regen, max_iters=1)
        assert out.revised is True and out.iterations == 1
        assert regen.await_count == 1  # capped at max_iters

    async def test_evaluator_failure_fails_open(self):
        evaluate = AsyncMock(side_effect=RuntimeError("critic down"))
        regen = AsyncMock()
        out = await reflect_and_revise("v1", evaluate=evaluate, regenerate=regen, max_iters=2)
        assert out.output == "v1" and out.revised is False
        regen.assert_not_awaited()

    async def test_regenerate_failure_keeps_prior(self):
        evaluate = AsyncMock(return_value=(False, "fix it"))
        regen = AsyncMock(side_effect=RuntimeError("regen down"))
        out = await reflect_and_revise("v1", evaluate=evaluate, regenerate=regen, max_iters=2)
        assert out.output == "v1" and out.revised is False


class TestLlmCritic:
    async def test_accept_parsed(self):
        model = MagicMock()
        model.ainvoke = AsyncMock(return_value=MagicMock(content="ACCEPT"))
        critic = build_llm_critic(model, criteria="be good", render=str)
        accepted, critique = await critic("output")
        assert accepted is True and critique == ""

    async def test_revise_parsed_with_critique(self):
        model = MagicMock()
        model.ainvoke = AsyncMock(return_value=MagicMock(content="REVISE: cite evidence id"))
        critic = build_llm_critic(model, criteria="be good", render=str)
        accepted, critique = await critic("output")
        assert accepted is False and critique == "cite evidence id"

    async def test_non_accept_text_treated_as_revise(self):
        model = MagicMock()
        model.ainvoke = AsyncMock(return_value=MagicMock(content="this is weak"))
        critic = build_llm_critic(model, criteria="be good", render=str)
        accepted, critique = await critic("output")
        assert accepted is False and critique == "this is weak"
