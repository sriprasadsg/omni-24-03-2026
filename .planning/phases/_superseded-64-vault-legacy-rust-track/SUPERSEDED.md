---
status: superseded
superseded_at: 2026-08-17T18:55:00Z
superseded_by: .planning/phases/64-rotate-key-autonomous-remediation-action/
---

# Superseded: earlier "Phase 64 rotate_key" attempt

This directory (originally `.planning/phases/64-rotate_key-autonomous-remediation-action/`,
underscore slug) held a separate, independent planning attempt at the same phase
number as the canonical `64-rotate-key-autonomous-remediation-action/` directory
(hyphen slug). Both existed simultaneously in `.planning/phases/`, and ROADMAP.md's
Phase 64 section was showing the canonical track's plan descriptions ("dispatch arms",
"grounded re-verify") but had picked up completion evidence from this track instead,
falsely marking the phase 3/3 complete.

## What this track actually shipped

Real, merged code from this track's commits (`81182a19`, `6d0d297e`, `25762b3e`,
`32b33ef9`, `5c1280ee`, `df8a9086`, `d4ca3d77`):

- `backend/vault_client.py` + `backend/secret_manager_service.py` + `backend/config.py`
  — a generic HashiCorp Vault secrets-management capability. **Not removed** — this is
  a real, separate capability outside rotate_key's scope, left as-is. Its tests
  (`test_secret_manager_service.py::test_vault_client_*`) fail without a live Vault
  server; that's expected/pre-existing, not a regression from this cleanup.
- `backend/skill_handlers.py::handle_rotate_key` + `backend/skill_registry.py` — an
  AI-chat `/rotate-key <key_id>` slash command, wired into `ai_service.py`. **Not
  removed** — real, live code, a different (manual, chat-triggered) entry point than
  the vulnerability-scan-triggered playbook flow the canonical track builds. It writes
  a generic `agent_instructions` document that no agent-side handler currently
  consumes end-to-end (neither track has finished the dispatch-arm wiring) — a known
  gap, tracked under the canonical track's phase completion, not reintroduced here.
- SSH key rotation logic in `agent-rust/` — **the legacy, unshipped agent tree**
  (see project memory: `agent-install/omni-agent-rs/` is canonical/shipped since
  2026-07-16; `agent-rust/` is legacy). This track's own `64-03-SUMMARY.md` (still in
  this directory) explicitly documents it as stubbed placeholders: "writes dummy
  content to key files", "does not perform actual file modifications", "simplified
  filename-based check rather than parsing actual key material". Dead code from a
  shipping standpoint — left in place (not deleted), just no longer tracked as
  phase-64 completion evidence.

## Why the canonical track wins

`64-rotate-key-autonomous-remediation-action/` went through the full
discuss→research→plan→verify pipeline (CONTEXT.md, DISCUSSION-LOG.md, RESEARCH.md,
PATTERNS.md, VALIDATION.md, VERIFICATION.md all present), targets the canonical
`agent-install/omni-agent-rs/` tree, and its plan 03 (`ssh_key_rotation.rs`) is a
real, rigorous design (byte-for-byte backup/restore, structured `KeyNotFound`/
`LockoutRefused` errors, grounded post-write re-verify) — not a stub. Plans 01 and 02
are genuinely executed there with matching SUMMARY.md files. Plan 03 was designed but
never executed; that gap is being closed under the canonical directory, not here.
