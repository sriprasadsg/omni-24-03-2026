"""Evaluator-optimizer (self-reflection) primitive for the agent surfaces.

Gap #2 from the capability review. Guardrails reject bad output; nothing
revises it. This adds a bounded reflect-and-revise loop: produce output →
evaluate it against criteria → if it fails and budget remains, feed the
critique back and regenerate → repeat.

Two layers, both hermetically testable:

  * `reflect_and_revise(...)` — the generic loop. Fully dependency-injected
    (`evaluate`/`regenerate`/`accept` callables), so it runs with fakes in
    unit tests, no LLM anywhere.
  * `build_llm_critic(...)` — builds an async `evaluate` callable backed by the
    per-tenant model factory, for real use.

Safety: reflection is a QUALITY mechanism, never a safety override. A caller's
`accept` predicate should short-circuit fail-closed outcomes
(`insufficient_evidence`, guardrail blocks) so the loop never tries to "revise"
a conservative verdict into a confident one. The loop only ever returns one of
the outputs the `regenerate` callable actually produced — it cannot fabricate.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger("ai_orchestration.reflection")


@dataclass
class ReflectionOutcome:
    """Result of a reflect-and-revise loop.

    `output` is the final (possibly revised) output. `revised` is True when at
    least one regeneration happened. `iterations` counts evaluate calls made.
    `critiques` is the ordered list of critiques that drove each revision."""

    output: Any
    revised: bool = False
    iterations: int = 0
    critiques: list[str] = field(default_factory=list)


# evaluate(output) -> (accepted, critique); regenerate(critique) -> new output
EvaluateFn = Callable[[Any], Awaitable[tuple[bool, str]]]
RegenerateFn = Callable[[str], Awaitable[Any]]
AcceptFn = Callable[[Any], bool]


async def reflect_and_revise(
    initial: Any,
    *,
    evaluate: EvaluateFn,
    regenerate: RegenerateFn,
    accept: Optional[AcceptFn] = None,
    max_iters: int = 1,
) -> ReflectionOutcome:
    """Run a bounded evaluator-optimizer loop over `initial`.

    Parameters
    ----------
    initial: the first output to consider.
    evaluate: async (output) -> (accepted: bool, critique: str). When it raises,
        the loop stops and returns the best output so far (fail-open on the
        evaluator only — never blocks a result on a critic failure).
    regenerate: async (critique) -> revised output.
    accept: optional fast synchronous short-circuit — if it returns True for an
        output, that output is accepted without ever calling `evaluate`
        (used to skip reflection on already-good or fail-closed outputs).
    max_iters: maximum number of regeneration attempts (>= 0). 0 disables the
        loop entirely and returns `initial` unchanged.
    """
    outcome = ReflectionOutcome(output=initial)
    if max_iters <= 0:
        return outcome

    if accept is not None and accept(initial):
        return outcome

    current = initial
    for _ in range(max_iters):
        try:
            accepted, critique = await evaluate(current)
        except Exception as exc:  # critic failure must not block a result
            logger.warning("[reflection] evaluator failed; keeping current output: %s", exc)
            return outcome
        outcome.iterations += 1
        if accepted or not critique:
            outcome.output = current
            return outcome
        outcome.critiques.append(critique)
        try:
            revised = await regenerate(critique)
        except Exception as exc:  # regeneration failure keeps the prior output
            logger.warning("[reflection] regenerate failed; keeping prior output: %s", exc)
            return outcome
        current = revised
        outcome.output = revised
        outcome.revised = True
        if accept is not None and accept(current):
            return outcome

    return outcome


def build_llm_critic(
    model: Any,
    *,
    criteria: str,
    render: Callable[[Any], str],
) -> EvaluateFn:
    """Build an async `evaluate` callable backed by a chat model.

    `model` is a per-tenant model (from `build_model_for_tenant`). `criteria`
    is the rubric text. `render(output)` turns a structured output into the
    text the critic should judge. The critic is asked to reply either
    `ACCEPT` or `REVISE: <specific, actionable critique>`; anything that
    isn't a clear ACCEPT is treated as a revise with the model's text as the
    critique. Evaluator errors propagate to `reflect_and_revise`, which
    fails open (keeps the current output)."""

    system = (
        "You are a strict quality reviewer. Judge the candidate output against "
        "the criteria. If it fully meets them, reply with exactly 'ACCEPT'. "
        "Otherwise reply 'REVISE: ' followed by one specific, actionable "
        "instruction to improve it. Never rewrite the output yourself.\n\n"
        f"Criteria:\n{criteria}"
    )

    async def _evaluate(output: Any) -> tuple[bool, str]:
        rendered = render(output)
        resp = await model.ainvoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Candidate output:\n{rendered}"},
            ]
        )
        text = (getattr(resp, "content", "") or "").strip()
        if text.upper().startswith("ACCEPT"):
            return True, ""
        critique = text.split(":", 1)[1].strip() if ":" in text else text
        return False, critique or "output did not meet criteria"

    return _evaluate
