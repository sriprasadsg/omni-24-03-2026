# Phase 53 — REVIEWS (self-review, 2026-07-30)

> Reviewer: claude-self (adversarial; no independent external model available). Highest-risk phase — reviewed hardest.

## BLOCKER — The execute→verify loop's "await the agent result" is not grounded
`53-03` Task 3 says the engine, after dispatching steps, "await[s] the agent result (via the instruction result / a bounded poll)." But the existing `execute_plan` is fire-and-forget: it inserts into `agent_instructions` and returns `"queued"`. There is no established synchronous agent→backend action-result channel confirmed in the plan. If the engine blocks awaiting a result that never returns through a defined path, the loop stalls.
**Fix:** decouple. Define verification as **re-running the finding's own check** (re-scan the file / re-query the vuln / re-hash the FIM path) after a bounded delay — independent of the action result. Remove the "await the agent result" language, OR first confirm the concrete mechanism by which agent action results reach the backend (an instruction-result endpoint / status update on the `agent_instructions` doc) and cite it. This is the phase's core loop — it must not rest on an unverified channel.

## HIGH — In-memory concurrency cap breaks under multiple uvicorn workers
`53-04` proposes "an in-memory guarded map" for the per-agent concurrency cap. Production runs multiple workers/processes — an in-memory counter is per-process and won't enforce a global cap.
**Fix:** track in-flight remediations in the DB (a count/lease on a collection) so the cap holds across workers; release on completion/timeout with a TTL to avoid leaked slots.

## HIGH — Deterministic YAML playbook schema vs the existing playbook store are unreconciled
`53-01` says operator-authored playbooks load "via the existing `enhanced_playbook_endpoints`," but the existing store shape (LLM `ai_playbook_service` steps: action/trigger/notification) differs from the deterministic `{finding_class, steps:[{action, params, destructive}], rollback}` schema. If they don't reconcile, operator CRUD (INT-02 / 54) won't round-trip the new playbooks.
**Fix:** define the mapping between the two schemas (or a separate collection for deterministic playbooks) explicitly in 53-01; make 54's playbook CRUD target the right store.

## MED — `rotate_key` action is under-specified and dangerous
`53-02` `rotate_key` "rotate a named, allowlisted credential/key" — which keys? Rotating the wrong key can lock out the host or break services. The allowlist + rotation semantics are vague for a destructive, hard-to-rollback action.
**Fix:** narrow `rotate_key` to a concrete, tested, reversible target set (or defer it to a follow-up and ship the other four actions). Ensure a rollback exists.

## MED — Rollback for irreversible actions
Some actions (kill_process, patch_package) have no clean rollback. The plan flags "missing rollback → leave + flag," but a killed process or applied patch can't be undone by an unblock/enable. Ensure `verify=failed` on an irreversible action escalates to a human alert rather than implying an automated undo.

## Accepted
- Backend-orchestrated, reuse execute_plan/agent_instructions — correct (agent-local would duplicate).
- Deterministic YAML (no LLM in the destructive path) + approval-gate default-on + append-only audit — strong guardrails.
