# Phase 40: Rust Agent Modernization & Session Reliability - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-20
**Phase:** 40-rust-agent-modernization-session-reliability
**Areas discussed:** TLS backend, Rollout mechanism, 401 fix scope

---

## TLS backend

| Option | Description | Selected |
|--------|-------------|----------|
| native-tls | Matches pre-0.13 behavior. Uses OS/Windows cert store — safe for endpoints behind corporate proxies with custom root CAs already trusted by Windows. | ✓ |
| rustls (new default) | Pure-Rust, no OS cert-store dependency, smaller attack surface. Risk: breaks trust for endpoints relying on Windows-injected corporate root CAs. | |
| You decide | Let Claude pick based on codebase/deployment context. | |

**User's choice:** native-tls (Recommended)
**Notes:** reqwest 0.13 silently defaults to rustls; explicit pin required so this isn't a silent behavior change on ship.

---

## Rollout mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-push via existing pipeline | Reuse `agent_download_endpoints.py`/`update_endpoints.py` — already-registered agents pull 2.1.0 automatically. | ✓ |
| Manual/opt-in only | Build the executable but don't auto-push; admin triggers per-tenant. | |
| You decide | Let Claude check what the pipeline actually supports and pick. | |

**User's choice:** Auto-push via existing pipeline (Recommended)
**Notes:** Plan must verify the existing pipeline actually supports version-gated auto-push before assuming it — don't take this as a guarantee of current capability.

---

## 401 fix scope

| Option | Description | Selected |
|--------|-------------|----------|
| Narrow fix only | Root-cause and fix the specific refresh-token race. Nothing else. | ✓ |
| Broader session hardening | Also add silent retry-on-401 in frontend, tune proactive-refresh margin. | |
| You decide | Fix root cause first; add hardening only if investigation shows it's needed. | |

**User's choice:** Narrow fix only (Recommended)
**Notes:** Broader hardening deferred — would be scope creep beyond HANDOFF task 10's original ask.

---

## Claude's Discretion

- Exact TLS pin syntax in Cargo.toml
- Whether the update pipeline needs a code change to serve 2.1.0, or already does — to be verified during research/planning
- Test/verification strategy for confirming the 401 race is fixed

## Deferred Ideas

- Broader auth-session hardening (silent retry-on-401, refresh-margin tuning) — revisit only if the 401 investigation shows it's genuinely needed, as a separate future item, not folded into Phase 40.
