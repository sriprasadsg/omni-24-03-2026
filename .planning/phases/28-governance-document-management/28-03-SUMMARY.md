# 28-03 Summary: Governance Document Management — Frontend Dashboard + Nav-Wiring

## Overview
Shipped the DOC-01/DOC-02 frontend: a Governance Documents dashboard that lists documents, creates drafts, adds versions, submits for approval, publishes, signs (typed name + consent), and exports the signed PDF. Wired it into navigation so it is actually reachable.

## Changes
1. **`components/GovernanceDocumentsDashboard.tsx`**: New dashboard component (tab-list-modal shape), wired to `/api/governance/documents` endpoints. Includes create draft modal, sign modal (sends only `{typed_name, consent}` to server, threat T-28-07), and PDF export.
2. **Nav-Wiring**: Mandatory wiring into `App.tsx` (lazy import, permission map, render case), `components/Sidebar.tsx` (nav item under "Governance & Compliance"), and `types.ts` (`AppView` union).

## Verification
- `npm run build` succeeds.
- `grep -rn "GovernanceDocumentsDashboard" App.tsx` returns lazy import + render case.
- Dashboard reachable from sidebar; drives all DOC-01/DOC-02 flows.
- Sign form sends only typed name + consent (no server-derived identity/IP/timestamp).

## Status
- **DOC-01/DOC-02 Frontend**: Complete (code implemented). Awaiting final human verification of end-to-end flow. See 28-UAT.md for details.
