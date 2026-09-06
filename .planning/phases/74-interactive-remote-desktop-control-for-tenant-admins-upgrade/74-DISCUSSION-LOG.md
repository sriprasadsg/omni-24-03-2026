# Phase 74: Interactive Remote Desktop Control - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-26
**Phase:** 74-interactive-remote-desktop-control-for-tenant-admins-upgrade
**Areas discussed:** Consent flow on the endpoint, Input scope — full control vs. restricted, Endpoint-side kill switch, Which agent gets this — Rust-only or also legacy Python

---

## Consent flow on the endpoint

| Question | Selected |
|---|---|
| Require Accept dialog when a user is logged in? | **Yes, block until Accept** (vs. "RBAC permission alone gates it") |
| Behavior when no interactive user is logged in? | **Refuse gracefully** (vs. "Allow anyway — permission substitutes for consent") |
| Consent dialog disclosure? | **Show requester identity** (vs. "Generic message only") |
| Consent persistence? | **Per-session only, always prompt** (vs. "Allow a persistent trust toggle") |

**Notes:** All four picks matched the recommended option. User confirmed "Next area" without further discussion.

---

## Input scope — full control vs. restricted

| Question | Selected |
|---|---|
| Combo blocking? | **Full passthrough** (vs. "Block dangerous combos") |
| Permission tiers? | **Binary — view-only OR full control** (vs. "Add a mouse-only middle tier") |
| Clipboard sync in scope? | **Out of scope for this phase** (vs. "Include basic one-way clipboard") |
| Local input during control session? | **Both can act simultaneously** (vs. "Lock local input while admin has control") |

**Notes:** All four picks matched the recommended option.

---

## Endpoint-side kill switch

| Question | Selected |
|---|---|
| Local "Stop Sharing" affordance? | **Yes — persistent on-screen indicator + stop control** (vs. "No local UI") |
| Admin-side disconnect? | **Yes, always** (vs. "No — only the endpoint can end it") |
| Platform-admin cross-tenant force-kill? | **Yes, add a platform-admin kill-all** (vs. "No — only the 2 session participants") |
| Tunnel drop behavior? | **Treat as session end — re-consent required** (vs. "Auto-resume within a grace window") |

**Notes:** All four picks matched the recommended option.

---

## Which agent gets this — Rust-only or also legacy Python

| Question | Selected |
|---|---|
| Agent scope? | **Both agents** (recommended was "Rust-canonical only") |
| OS-mismatch response wording? | **You decide** |
| Faster capture required for completion? | **Yes, stretch-only** (vs. "Make it required") |

**Notes:** User explicitly rejected the lower-cost "Rust-canonical only" recommendation in favor of building interactive control into both the canonical Rust agent and the legacy Python agent, despite this roughly doubling the SendInput/consent-dialog implementation surface. Confirmed the legacy Python agent is already Windows-only (`is_compatible()` gates on `os == "Windows"`), so this decision does not add new cross-platform scope — it's the same OS target, implemented twice.

---

## Claude's Discretion

- Exact Windows-only rejection response wording/shape for control requests (reuse existing `desktop_stream_run` error vs. a distinct message).
- Exact Windows input-injection mechanism on the Python agent side (`ctypes` call to `user32.SendInput` vs. a library).
- Exact consent-dialog implementation (native modal vs. custom always-on-top window) for both agent languages.
- Exact audit-log record shape for control sessions (fields, reuse of `remediation_audit_service.py` pattern).

## Deferred Ideas

- Clipboard sync (admin↔endpoint copy/paste) — real Zoho Assist feature, explicitly deferred to a future phase due to its own data-exfiltration threat-model questions.
