"""
Agentic AI decision service — two-turn Claude tool-calling loop for security capability selection.

Consumed by: agentic_tasks_endpoints.py

Architecture:
  AgenticService.run() -> truncate_security_context() -> decide_and_execute()
                       -> _log_decision() -> agent_ai_decisions (MongoDB)
  On exception or CircuitBreakerOpen: _rule_based_fallback()

Key constraints (from AI-SPEC Phase 12):
  - agentic_breaker key is "agentic_ai" (NOT "ai") — separate from ai_breaker
  - tool_choice={"type": "any"} forces stop_reason="tool_use" on Turn 1
  - _log_decision() catches ALL exceptions and logs "AUDIT WRITE FAILURE" — never re-raises
  - TenantIsolatedCollection auto-injects tenantId — do NOT set doc["tenantId"] manually
"""
import asyncio
import copy
import datetime
import json
import logging
import os
import uuid
from typing import Callable, Awaitable, Literal

from anthropic import AsyncAnthropic
from anthropic.types import ToolUseBlock
from pydantic import BaseModel, field_validator, ValidationError

from circuit_breaker import CircuitBreaker, CircuitBreakerOpen
from database import get_database

logger = logging.getLogger(__name__)

# ── Circuit breaker — separate key from ai_breaker to avoid cross-contamination ──
agentic_breaker = CircuitBreaker("agentic_ai", failure_threshold=3, recovery_timeout=60)

# ── Tool definitions (JSON Schema) — verbatim from AI-SPEC Section 3 ──────────
TOOLS: list[dict] = [
    {
        "name": "run_compliance_check",
        "description": (
            "Trigger a CIS/NIST compliance scan on the target agent. "
            "Use when compliance findings are stale (>24h) or missing entirely."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Target agent UUID"},
                "framework": {
                    "type": "string",
                    "enum": ["CIS", "NIST", "ISO27001"],
                    "description": "Compliance framework to evaluate against",
                },
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "run_vulnerability_scan",
        "description": (
            "Run a software vulnerability scan on the target agent. "
            "Use when CVE findings are absent or the last scan is >72h old."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "severity_threshold": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "default": "medium",
                },
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "run_threat_hunt",
        "description": (
            "Execute a MITRE ATT&CK-aligned threat hunt on the agent. "
            "Use when anomalous process or network behavior is detected."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "hunt_profile": {
                    "type": "string",
                    "enum": [
                        "lateral_movement",
                        "credential_access",
                        "persistence",
                        "exfiltration",
                    ],
                },
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "run_persistence_scan",
        "description": (
            "Scan for persistence mechanisms (scheduled tasks, registry run keys, startup items). "
            "Use when new software was installed or a persistence-category alert fired."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "collect_processes",
        "description": (
            "Collect a live process snapshot from the agent. "
            "Use as a baseline step before threat hunting or when process anomalies are suspected."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "include_network": {
                    "type": "boolean",
                    "description": "Whether to include open network connections per process",
                    "default": False,
                },
            },
            "required": ["agent_id"],
        },
    },
]

# ── System prompt (static — NEVER embed dynamic data here, T-12-01) ───────────
SYSTEM_PROMPT = """\
You are a security operations AI integrated into the Omni-Agent platform.
You receive a structured JSON context describing an endpoint's current security
posture — active findings, last scan timestamps, agent capabilities, and recent
alerts. Based on this context, you MUST select exactly one tool that will have
the highest security impact right now. Do not ask clarifying questions.
Do not select a tool that is not in the provided list.
The agent_id is always present in the context; always pass it to the chosen tool."""


# ── Pydantic validation model — enforces Literal enum on tool_name (T-12-02) ──
class AgenticDecision(BaseModel):
    tool_name: Literal[
        "run_compliance_check",
        "run_vulnerability_scan",
        "run_threat_hunt",
        "run_persistence_scan",
        "collect_processes",
    ]
    agent_id: str
    framework: Literal["CIS", "NIST", "ISO27001"] | None = None
    severity_threshold: Literal["low", "medium", "high", "critical"] | None = None
    hunt_profile: Literal[
        "lateral_movement", "credential_access", "persistence", "exfiltration"
    ] | None = None
    include_network: bool = False

    @field_validator("agent_id")
    @classmethod
    def agent_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("agent_id must be a non-empty string")
        return v.strip()


# ── Tool dispatcher helpers — enqueue capability via agent_instructions ───────

async def _dispatch_compliance_check(agent_id: str, framework: str | None = None, **_) -> dict:
    db = get_database()
    payload = {"agent_id": agent_id}
    if framework:
        payload["framework"] = framework
    await db.agent_instructions.insert_one(
        {"type": "run_compliance_check", "agent_id": agent_id, "payload": payload, "status": "pending"}
    )
    return {"status": "queued", "tool": "run_compliance_check"}


async def _dispatch_vulnerability_scan(
    agent_id: str, severity_threshold: str | None = None, **_
) -> dict:
    db = get_database()
    payload = {"agent_id": agent_id}
    if severity_threshold:
        payload["severity_threshold"] = severity_threshold
    await db.agent_instructions.insert_one(
        {"type": "run_vulnerability_scan", "agent_id": agent_id, "payload": payload, "status": "pending"}
    )
    return {"status": "queued", "tool": "run_vulnerability_scan"}


async def _dispatch_threat_hunt(
    agent_id: str, hunt_profile: str | None = None, **_
) -> dict:
    db = get_database()
    payload = {"agent_id": agent_id}
    if hunt_profile:
        payload["hunt_profile"] = hunt_profile
    await db.agent_instructions.insert_one(
        {"type": "run_threat_hunt", "agent_id": agent_id, "payload": payload, "status": "pending"}
    )
    return {"status": "queued", "tool": "run_threat_hunt"}


async def _dispatch_persistence_scan(agent_id: str, **_) -> dict:
    db = get_database()
    await db.agent_instructions.insert_one(
        {"type": "run_persistence_scan", "agent_id": agent_id, "payload": {"agent_id": agent_id}, "status": "pending"}
    )
    return {"status": "queued", "tool": "run_persistence_scan"}


async def _dispatch_collect_processes(
    agent_id: str, include_network: bool = False, **_
) -> dict:
    db = get_database()
    await db.agent_instructions.insert_one(
        {
            "type": "collect_processes",
            "agent_id": agent_id,
            "payload": {"agent_id": agent_id, "include_network": include_network},
            "status": "pending",
        }
    )
    return {"status": "queued", "tool": "collect_processes"}


# ── Tool registry — immutable module-level constant (T-12-02) ─────────────────
TOOL_REGISTRY: dict[str, Callable[..., Awaitable[dict]]] = {
    "run_compliance_check": _dispatch_compliance_check,
    "run_vulnerability_scan": _dispatch_vulnerability_scan,
    "run_threat_hunt": _dispatch_threat_hunt,
    "run_persistence_scan": _dispatch_persistence_scan,
    "collect_processes": _dispatch_collect_processes,
}


# ── Context truncation helpers ────────────────────────────────────────────────

def estimate_tokens(obj: dict) -> int:
    """Rough estimate: 1 token per 4 characters of JSON."""
    return len(json.dumps(obj)) // 4


def truncate_security_context(ctx: dict, max_findings: int = 20) -> dict:
    """Return a bounded copy of ctx for LLM call — per AI-SPEC Section 4b.4."""
    c = copy.deepcopy(ctx)
    if "findings" in c:
        c["findings"] = sorted(
            c["findings"], key=lambda f: f.get("severity_score", 0), reverse=True
        )[:max_findings]
    if "processes" in c:
        c["processes"] = c["processes"][:30]
    if "alerts" in c:
        c["alerts"] = c["alerts"][:5]
    # Strip large blob fields from each finding (T-12-01 prompt injection surface)
    for finding in c.get("findings", []):
        finding.pop("raw_evidence", None)
        finding.pop("pcap_base64", None)
    if estimate_tokens(c) > 3000:
        logger.warning(
            "[AgenticService] Context still large after truncation; keeping findings only."
        )
        c = {"agent_id": ctx.get("agent_id", ""), "findings": c.get("findings", [])[:10]}
    return c


# ── Two-turn tool-calling loop ────────────────────────────────────────────────

async def decide_and_execute(
    agent_id: str, security_context: dict, client: AsyncAnthropic
) -> dict:
    """
    Single-turn tool-calling loop for agentic security decisions.
    Returns a dict with: tool_name, tool_input, tool_result, rationale, tool_use_id, source.
    Raises RuntimeError if model does not select a tool.
    Raises ValueError if tool name is hallucinated or validation fails.
    """
    user_message = (
        f"Security context for agent {agent_id}:\n"
        f"{json.dumps(security_context, indent=2)}\n\n"
        "Select the most impactful security tool to run now."
    )

    # Turn 1: force tool selection with tool_choice="any"
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        temperature=0,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": user_message}],
    )

    if response.stop_reason != "tool_use":
        raise RuntimeError(
            f"Unexpected stop_reason '{response.stop_reason}'; "
            "model did not select a tool despite tool_choice='any'."
        )

    # Extract ToolUseBlock
    tool_use_block = next(
        (b for b in response.content if b.type == "tool_use"), None
    )
    if tool_use_block is None:
        raise RuntimeError(
            "No tool_use block in response despite stop_reason='tool_use'."
        )

    # Build raw input for validation
    raw_input = {**tool_use_block.input, "tool_name": tool_use_block.name}

    # Validate via Pydantic — rejects hallucinated names (T-12-02)
    try:
        decision = AgenticDecision.model_validate(raw_input)
    except ValidationError as exc:
        logger.warning(
            "[AgenticService] tool input failed validation: %s | raw_input=%s",
            exc, raw_input,
        )
        raise ValueError(f"Model returned invalid tool input: {exc}") from exc

    # Guard: registry double-check after Pydantic (defence in depth)
    if decision.tool_name not in TOOL_REGISTRY:
        raise ValueError(
            f"Model selected unknown tool '{decision.tool_name}'. "
            f"Valid tools: {list(TOOL_REGISTRY.keys())}"
        )

    # Execute the selected tool via TOOL_REGISTRY dispatcher
    executor = TOOL_REGISTRY[decision.tool_name]
    tool_result = await executor(
        **decision.model_dump(exclude={"tool_name"}, exclude_none=True)
    )

    # Turn 2: send tool result back, get rationale text for audit log
    rationale_response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        temperature=0,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=[
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": response.content},
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_block.id,
                        "content": str(tool_result),
                    }
                ],
            },
        ],
    )

    rationale = next(
        (b.text for b in rationale_response.content if b.type == "text"), ""
    )

    return {
        "tool_name": decision.tool_name,
        "tool_input": decision.model_dump(exclude={"tool_name"}, exclude_none=True),
        "tool_result": tool_result,
        "rationale": rationale,
        "tool_use_id": tool_use_block.id,
        "source": "agentic_ai",
    }


# ── Rule-based fallback (AI-04) ───────────────────────────────────────────────

async def _rule_based_fallback(agent_id: str, security_context: dict) -> dict:
    """
    Safe default fallback when Anthropic API is unreachable or circuit is open.
    Selects collect_processes as the lowest-risk baseline action.
    """
    tool_result = await _dispatch_collect_processes(agent_id=agent_id)
    return {
        "tool_name": "collect_processes",
        "tool_input": {"agent_id": agent_id},
        "tool_result": tool_result,
        "rationale": "rule_based_fallback",
        "source": "rule_based_fallback",
    }


# ── AgenticService class ──────────────────────────────────────────────────────

class AgenticService:
    """Wraps the two-turn tool-calling loop with MongoDB decision logging."""

    def __init__(self, api_key: str):
        self._client = AsyncAnthropic(api_key=api_key, max_retries=2, timeout=30.0)

    async def run(self, agent_id: str, security_context: dict) -> dict:
        """Execute one agentic decision cycle. Logs result to agent_ai_decisions."""
        decision_id = str(uuid.uuid4())
        started_at = datetime.datetime.utcnow()

        ctx = truncate_security_context(security_context)

        try:
            async with agentic_breaker:
                result = await decide_and_execute(agent_id, ctx, self._client)
        except CircuitBreakerOpen:
            logger.warning(
                "[AgenticService] Circuit breaker open for '%s' — activating rule-based fallback",
                agent_id,
            )
            result = await _rule_based_fallback(agent_id, security_context)
            result["source"] = "rule_based_fallback"
        except Exception as exc:
            logger.error(
                "[AgenticService] Decision failed for agent '%s': %s", agent_id, exc
            )
            result = await _rule_based_fallback(agent_id, security_context)
            result["source"] = "rule_based_fallback"

        await self._log_decision(decision_id, agent_id, result, started_at)
        return result

    async def _log_decision(
        self,
        decision_id: str,
        agent_id: str,
        result: dict,
        started_at: datetime.datetime,
    ) -> None:
        """
        Write audit record to agent_ai_decisions.
        NEVER re-raises — logs "AUDIT WRITE FAILURE" at ERROR on exception (T-12-03).
        TenantIsolatedCollection auto-injects tenantId — do NOT set it manually (T-12-05).
        """
        db = get_database()
        if not db:
            logger.warning(
                "[AgenticService] DB unavailable; decision %s not logged.", decision_id
            )
            return

        doc = {
            "_id": decision_id,
            "agent_id": agent_id,
            "tool_name": result.get("tool_name"),
            "tool_input": result.get("tool_input"),
            "rationale": result.get("rationale", ""),
            "model": "claude-sonnet-4-6",
            "started_at": started_at.isoformat(),
            "completed_at": datetime.datetime.utcnow().isoformat(),
            "source": result.get("source", "agentic_ai"),
        }

        try:
            await db.agent_ai_decisions.insert_one(doc)
        except Exception as exc:
            # CRITICAL: never suppress silently — Critical Failure Mode #3 (AI-SPEC)
            logger.error(
                "[AgenticService] AUDIT WRITE FAILURE for decision %s: %s",
                decision_id,
                exc,
            )
            # Do NOT re-raise — audit failure must not block the agent response


# ── Module-level singleton ────────────────────────────────────────────────────

_service: AgenticService | None = None


def get_agentic_service() -> AgenticService:
    """Return or create the module-level AgenticService singleton."""
    global _service
    if _service is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set — agentic AI path is unavailable. "
                "Set the environment variable to enable AI-driven security decisions."
            )
        _service = AgenticService(api_key)
    return _service
