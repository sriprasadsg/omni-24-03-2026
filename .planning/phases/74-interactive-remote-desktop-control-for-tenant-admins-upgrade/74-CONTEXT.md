# Phase 74: Interactive Remote Desktop Control - Context

**Gathered:** 2026-08-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Upgrade the existing view-only remote-desktop stream (`components/RemoteDesktop.tsx` + `agent-install/omni-agent-rs/src/capabilities/remote_access.rs`) to full attended interactive control, matching Zoho Assist: mouse/keyboard input relay over the existing WebSocket tunnel, Win32 `SendInput`-based replay on the agent, an on-endpoint consent gate before control is granted, a new `control:remote_access` RBAC permission distinct from the existing `view:remote_access`, and session audit logging. Faster/continuous screen capture (replacing the periodic PowerShell screenshot loop) is an optional stretch goal, not required for phase completion.

</domain>

<decisions>
## Implementation Decisions

### Consent flow
- **D-01:** When an interactive user is logged into the target Windows session, control is blocked until that user clicks Accept on a dialog. This is a hard gate — the RBAC permission alone does not grant control. — **Reversibility:** costly — rationale: this is the load-bearing security/UX guarantee the rest of the decisions in this phase (D-04, D-09, D-12) are built around; loosening it later means redesigning the consent state machine those decisions depend on, not a local flag flip.
- **D-02:** When there is no interactive user logged in (headless/Session-0 — common for monitored servers), the control request is refused gracefully, using the same "no interactive desktop available" failure shape the existing `desktop_stream_run` already returns for view-only streaming.
- **D-03:** The consent dialog shows the requesting admin's identity (name/email) and tenant, not a generic message — matches the Zoho Assist/TeamViewer convention and strengthens the audit trail.
- **D-04:** Consent is required every session — no "always allow this tenant" persistent opt-out. — **Reversibility:** costly — rationale: adding a persistent-trust toggle later is a real feature (new storage, new UI, new bypass path through D-01's gate), not a config change, and it directly weakens the per-session consent guarantee this phase establishes.

### Input scope
- **D-05:** Full, unrestricted keyboard and mouse passthrough — no blocklist for OS-level combos (e.g., Ctrl+Alt+Del, which SendInput cannot inject anyway due to Windows' Secure Attention Sequence protection).
- **D-06:** Binary permission model only — `view:remote_access` (screenshot stream, unchanged) or `control:remote_access` (full input). No intermediate "mouse-only" tier. — **Reversibility:** costly — rationale: adding a third tier later means a new permission constant plus a new code path through the RBAC check, the frontend mode switcher, and the agent's input dispatcher — not a local change.
- **D-07:** Clipboard sync (admin↔endpoint copy/paste) is explicitly out of scope for this phase — real Zoho Assist feature, but it opens its own data-exfiltration threat-model questions and belongs in a follow-up phase.
- **D-08:** The local physical user's own mouse/keyboard keeps working during a control session — both parties can act simultaneously, matching Zoho Assist's default attended mode. No local-input lockout mechanism. — **Reversibility:** costly — rationale: adding a lockout later requires new low-level OS input-blocking code that doesn't exist today; this decision means no such code path gets built in this phase.

### Endpoint-side kill switch
- **D-09:** The endpoint (local) user gets a persistent on-screen indicator during a control session with a one-click "stop control" affordance — matches Zoho Assist. This is what makes D-01's consent meaningful (consent that can't be revoked mid-session isn't real consent).
- **D-10:** The tenant admin can also disconnect the session unilaterally from `RemoteAccessDashboard.tsx`.
- **D-11:** A platform-admin/super-admin gets a cross-tenant force-kill for any active control session — reuses the existing `_REMOTE_SUPER_ROLES` bypass pattern already in `backend/remote_endpoints.py`.
- **D-12:** If the WebSocket tunnel drops mid-session, the session is treated as ended — reconnecting requires the endpoint user to accept a fresh consent prompt. No silent auto-resume. — **Reversibility:** costly — rationale: this is the mechanism that makes the per-session consent guarantee (D-04) hold across network interruptions; adding an auto-resume grace window later reopens exactly the "was control silently regranted?" ambiguity this decision closes.

### Agent scope
- **D-13:** Interactive control is built for **both** the canonical Rust agent (`agent-install/omni-agent-rs`) and the legacy Python agent (`agent/capabilities/remote_access.py`) — not Rust-only, despite Rust-only being the lower-cost recommendation (the Python agent isn't the primary install path per Phase 50+ and this doubles the SendInput/consent-dialog implementation surface across two languages). — **Reversibility:** costly — rationale: once both trees implement the same WS frame contract and consent-dialog behavior, dropping the Python side later means deprecating a shipped code path some installed base may depend on, not deleting dead code.
- **D-14:** Faster/continuous screen capture (replacing the current periodic PowerShell screenshot loop with something like Windows Graphics Capture API / DXGI Desktop Duplication) remains a stretch goal only — not required for this phase to be considered complete.

### Claude's Discretion
- Exact wording/shape of the Windows-only rejection response for control requests on non-Windows agents — whether it reuses the identical error string `desktop_stream_run` already returns, or gets a distinct message so the dashboard can tell "wrong OS" apart from "no active session." Left to planner/research.
- Exact Windows input-injection mechanism on the Python agent side (raw `ctypes` call to `user32.SendInput`, or a library like `pywin32`) — Rust side uses the `windows` crate per the existing `remote_access.rs` pattern; Python's equivalent isn't decided. Research should check what's already a dependency before adding one.
- Exact consent-dialog implementation on the endpoint (native Win32 `MessageBox`-style modal vs. a custom always-on-top window) for both agent languages.
- Exact audit-log record shape for control sessions — reuse the append-only pattern from `backend/remediation_audit_service.py` (cited by prior phases as the house pattern); exact fields (session_id, requester, tenant, start/end timestamps, consent-decision, disconnect-reason) left to planner.
- The `control:remote_access` permission name itself is already locked by the ROADMAP.md Phase 74 goal (written before this discussion) — not re-litigated here, just carried forward.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing remote-access surface (extend, don't fork)
- `components/RemoteDesktop.tsx` — current view-only canvas renderer; draws JPEG frames from `renderFrame()`, zero mouse/keyboard handlers today. This is what gains input capture.
- `components/RemoteAccessDashboard.tsx` — Terminal/Desktop mode switcher (`AccessMode = 'desktop' | 'terminal'`); needs the new control affordance and the admin-side disconnect button (D-10).
- `agent-install/omni-agent-rs/src/capabilities/remote_access.rs` — canonical Rust agent. Has `rdp_status`/`set_rdp` (native OS RDP toggle via `netsh` — unrelated to this phase, do not confuse the two), `desktop_stream_run` (JPEG screenshot loop, Windows-only, already returns a "no interactive desktop" error this phase's D-02 reuses), and `tunnel_request()` (adds the required `X-Tenant-Key` header — any new WS message type this phase adds MUST go through this helper, not a bare `connect_async`).
- `agent/capabilities/remote_access.py` — legacy Python agent. `is_compatible()` already gates to Windows only (`system_info.get("os") == "Windows"`), same OS scope as the Rust agent. Has its own separate `enable_rdp`/`disable_rdp` (native toggle) and reverse-shell/desktop-stream WebSocket client using the `websocket-client` library — this is the second implementation surface per D-13.
- `backend/remote_endpoints.py` — `POST /api/remote/session/start` creates the session + agent instruction + tunnel URL; the `protocol` field in the payload is currently stored but not dispatched on anything — this phase needs it to actually signal view vs. control mode to the agent.
- `backend/remote_access_service.py` — `ConnectionManager` pairing user/agent WebSockets by `session_id`; relays bytes both directions today for the shell case.
- `backend/rbac_utils.py` — `view:remote_access` already exists (referenced at two role-permission-list sites). `control:remote_access` is new, named by ROADMAP.md Phase 74's goal.

### Related security/audit patterns to reuse
- `backend/remediation_audit_service.py` — append-only audit write pattern, the house convention per `.planning/phases/64-rotate-key-autonomous-remediation-action/64-CONTEXT.md` (D-09) for security-sensitive agent actions.
- `.planning/phases/64-rotate-key-autonomous-remediation-action/64-CONTEXT.md` — precedent for this project's reversibility-rating style on security-sensitive decisions (D-01 through D-09 there), and the "two Rust agent trees" caveat (only `agent-install/omni-agent-rs/` is shipped; `agent-rust/` is a stale/legacy tree — do not touch it).

### Roadmap
- `ROADMAP.md` — Phase 74 section (Goal, `**Depends on:** Phase 73`)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `RemoteDesktop.tsx`'s existing `wsRef`/`renderFrame` WebSocket plumbing — input capture adds `onMouseDown/Move/Up/Wheel` and `onKeyDown/Up` handlers that serialize and send JSON frames over the same socket, no new connection needed.
- `remote_access.rs`'s `tunnel_request()` helper — reuse for any new input-channel or consent-signaling WebSocket traffic this phase adds.
- `rbac_utils.py`'s existing permission-list pattern (`view:remote_access` sitting alongside `view:secrets`, `manage:agents`, etc. in two role blocks) — `control:remote_access` slots in the same way.

### Established Patterns
- Windows-only gating via `is_compatible()`/`platform.system()` checks (Python) and runtime platform checks (Rust) — both agents already gate the existing remote-desktop feature this way; extend, don't reinvent.
- `_REMOTE_SUPER_ROLES` bypass pattern in `remote_endpoints.py` — model for the platform-admin force-kill (D-11).
- Append-only audit collections (`remediation_audit_service.py`; `assignment_history` from ITAM Phase 57) — model for the new control-session audit trail.

### Integration Points
- New WS message types over the existing `/api/tunnel/{session_id}/agent` and `/user` channels (mouse/key event frames, consent-request/consent-response frames) — same tunnel, new payload shapes, not a new endpoint.
- `remote_endpoints.py`'s `start_remote_session` — the `protocol`/`type` payload needs to actually signal "control" vs. "view" mode to the agent (currently decorative).
- Both agent trees' existing desktop-stream loops each need a paired input-listener task alongside the existing screenshot-capture loop.

</code_context>

<specifics>
## Specific Ideas

No specific UI mockup or reference beyond "Zoho Assist" itself, cited by the user as the target UX for the whole phase — the persistent stop-control affordance (D-09) and requester-identity-in-consent-dialog (D-03) decisions are directly modeled on Zoho Assist's own behavior.

</specifics>

<deferred>
## Deferred Ideas

- Clipboard sync (admin↔endpoint copy/paste) — considered and explicitly deferred to a future phase, see D-07. Not lost, just out of this phase's scope due to its own data-exfiltration threat-model questions.

</deferred>

---

*Phase: 74-interactive-remote-desktop-control-for-tenant-admins-upgrade*
*Context gathered: 2026-08-26*
