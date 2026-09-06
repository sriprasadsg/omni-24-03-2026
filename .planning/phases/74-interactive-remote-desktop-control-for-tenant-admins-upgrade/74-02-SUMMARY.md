---
phase: 74-interactive-remote-desktop-control-for-tenant-admins-upgrade
plan: 02
type: execute
wave: 1
depends_on: ["74-01"]
files_modified:
  - backend/control_session_audit_service.py
  - backend/tunnel_endpoints.py
  - backend/remote_endpoints.py
autonomous: true
requirements: []

estimate:
  tokens: 50000
  raw_tokens: 50000
  tasks: 3
  confidence: high

must_haves:
  truths:
    - "Audit trail uses OCSF remote_control.event format."
    - "Session teardown drains all WS queues and transitions status to closed."
    - "Only one active control session per agent (already_controlled guard)."
    - "Agent auth verifies agent key for consent endpoint."
  artifacts:
    - backend/control_session_audit_service.py (audit trail)
    - backend/tunnel_endpoints.py (session close, tunnel)
    - backend/remote_endpoints.py (consent endpoint, RBAC)
  key_links:
    - "backend/remote_endpoints.py: already_controlled guard (409)"
---

# Phase 74-02: Backend Audit, Control & Protection

Implemented audit trail, session control, and platform protection for interactive remote desktop.

## Accomplishments
- Implemented OCSF audit trail in `backend/control_session_audit_service.py`.
- Implemented `close_session` in `backend/tunnel_endpoints.py` to handle clean teardowns.
- Implemented consent endpoint and capabilities probe in `backend/remote_endpoints.py`.
- Added `already_controlled` guard (409) for session management.

## Files Created/Modified
- `backend/control_session_audit_service.py`: Audit service.
- `backend/tunnel_endpoints.py`: Tunnel and session management.
- `backend/remote_endpoints.py`: Consent and capabilities.

## Success Criteria
- Audit trails are correct and OCSF-compliant.
- Session teardown is atomic and clean.
- Only single active control session permitted.

## Status
Complete.
