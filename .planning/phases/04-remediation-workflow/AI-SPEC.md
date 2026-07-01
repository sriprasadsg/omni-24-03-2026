---
phase: "04"
ai_capability: "remediation-suggestion"
framework: "claude-api-direct"
model: "claude-haiku-4-5-20251001"
---

## Framework Selection

The project already routes all LLM calls through `ai_service.generate_text()`, which
provides provider abstraction, PII/injection guardrails, circuit-breaker retry, and
audit logging — everything Phase 4 needs. Adding a separate orchestration framework
(LangChain, LlamaIndex, etc.) would introduce new packages and a redundant abstraction
layer for what is, at its core, a single-shot prompt → structured text call.

## AI Capability Design

**Input** (assembled by `remediation_task_service.py` before calling the LLM):
- `control_id` and `control_description` — what the compliance rule requires
- `failure_reason` — the current non-compliant / warning status detail
- `asset_context` — asset type, OS, tags (pulled from `assets` collection)

**Output**: a plain-text ordered list of 3–5 actionable remediation steps, written for
a security engineer, ending with a verification step the agent can re-scan against.

**Prompt structure**:
```
You are a compliance remediation advisor. Given a failed compliance control,
return exactly 3–5 numbered remediation steps. Be specific and actionable.
Do not include explanations outside the numbered list.

Control: {control_id} — {control_description}
Failure reason: {failure_reason}
Asset: {asset_type}, OS: {asset_os}

Remediation steps:
```

Temperature: 0.2 (deterministic, factual output preferred over creativity).

## Implementation Notes

- Extend `ai_service.IncidentAnalyzer` with a new method
  `suggest_remediation(control_id, control_description, failure_reason, asset_context)`.
  Call `self.generate_text(prompt, source="remediation_suggestion")` — no new provider
  wiring needed; the existing fallback chain (Anthropic → Gemini → Ollama → Mock) applies.
- Add a `POST /api/remediation-tasks/{task_id}/suggest` endpoint in the new
  `remediation_task_endpoints.py` (Phase 4 primary file). The endpoint fetches the task
  + asset record, builds context, calls `ai_service.suggest_remediation()`, stores the
  result as `task.ai_suggestion` in `compliance_remediation_tasks`, and returns it.
- No streaming needed — suggestions are short (<300 tokens) and displayed in a modal.

## Evaluation Strategy

Manual spot-check rubric applied to 5–10 representative failed controls before launch:

| Dimension         | Pass criteria                                                   |
|-------------------|-----------------------------------------------------------------|
| Actionability     | Every step contains a concrete command, setting, or UI action   |
| Specificity       | Steps reference the actual control / asset type, not generic advice |
| Completeness      | Final step is a verification action (re-scan trigger or test)   |
| Safety            | No step suggests disabling security controls or bypassing RBAC  |
| Length            | 3–5 steps; no step exceeds two sentences                        |

Automated gate: run guardrail_service output scan on every LLM response before
storing (`generate_text` already does this via `source="remediation_suggestion"`).
