---
phase: 23
plan: "03"
subsystem: frontend
tags: [windows, agent-installation, evidence, ui, powershell]
dependency_graph:
  requires: ["23-01", "23-02"]
  provides: [windows-install-ui, powershell-evidence-badge]
  affects: [components/AgentInstallation.tsx, components/AssetComplianceList.tsx]
tech_stack:
  added: []
  patterns: [extracted-sub-component, details-collapsible]
key_files:
  created:
    - components/WindowsInstallTab.tsx
  modified:
    - components/AgentInstallation.tsx
    - components/AssetComplianceList.tsx
decisions:
  - Extracted Windows tab content to WindowsInstallTab.tsx to keep AgentInstallation.tsx under 500 lines
  - Used native <details> element for 28-checks collapsible (no state required)
  - PS badge placed before the Automated/Manual badge for quick visual identification
metrics:
  duration: "3m 13s"
  completed: "2026-06-24T08:57:29Z"
  tasks_completed: 5
  files_changed: 3
status: complete
---

# Phase 23 Plan 03: Frontend Windows Agent Install UI + Evidence Display Summary

## One-liner

Windows install tab updated to 3-step PS flow (service install, immediate collect, standalone collect) with EXE download card, 28-check collapsible panel, and purple "PS" source badge for PowerShell evidence.

## Tasks Completed

| Task | Description | Status | Commit |
|------|-------------|--------|--------|
| 1 | Update Windows install tab with 3-step flow + 28-checks panel | Done | 0b3d6e4 |
| 2 | Add PowerShell source badge to AssetComplianceList.tsx | Done | 0b3d6e4 |
| 3 | Verify no TypeScript errors in modified files | Done | — |
| 4 | Commit all changes | Done | 0b3d6e4 |
| 5 | Write SUMMARY.md | Done | — |

## What Was Built

### WindowsInstallTab.tsx (new component, 110 lines)

Extracted Windows tab content into a dedicated sub-component to keep `AgentInstallation.tsx` under 500 lines (it was 412, would have exceeded 480 after additions).

Contains:
- **EXE download card** — blue banner linking to `/api/agent-updates/download/OmniAgent-Setup.exe` with `download` attribute
- **Step 1** — Install Agent Service: downloads and runs `win-install.ps1` with `-ApiUrl` and `-RegistrationKey` params
- **Step 2** — Collect Evidence Now: runs the installed `C:\Program Files\OmniAgent\Collect-Evidence.ps1`
- **Step 3** — Standalone Evidence Collection: downloads and runs `Collect-Evidence.ps1` directly without service install
- **28 Checks collapsible** — native `<details>` element listing all 28 Windows compliance checks grouped by 9 categories

### AgentInstallation.tsx (modified, 420 lines)

- Added import for `WindowsInstallTab`
- Replaced `<CodeBlock command={commands[activeTab]} />` for the Windows tab with `<WindowsInstallTab backendUrl={serverUrl} registrationKey={registrationKey || ''} />`
- All other tabs (Linux, Python, Docker, Kubernetes) unchanged

### AssetComplianceList.tsx (modified)

Added PowerShell source badge rendered before the Automated/Manual badge:
- `ev.agent_type === 'powershell'` → purple badge `PS` (bg-purple-100 / text-purple-800)
- Existing `Automated`/`Manual` badge logic unchanged

## Deviations from Plan

### Auto-extracted Sub-component (Rule 2 — CLAUDE.md constraint)

**Found during:** Task 1
**Issue:** Adding all Windows tab content inline to `AgentInstallation.tsx` would have pushed it to approximately 490 lines, close to the 480-line threshold in CLAUDE.md.
**Fix:** Extracted to `components/WindowsInstallTab.tsx`. The component self-contains its own `CodeBlock` copy (to avoid circular imports or prop drilling the component), and the `WIN_CHECKS` data array.
**Files modified:** components/WindowsInstallTab.tsx (created), components/AgentInstallation.tsx (import added, conditional render)

## TypeScript Verification

`npx tsc --noEmit` produced 4 pre-existing errors in unmodified files:
- `components/AgentDetailModal.tsx:576` — type overlap (pre-existing)
- `components/FrameworkDetail.tsx:68` — toast type (pre-existing)
- `components/RemediationTaskModal.tsx:51,101` — missing `assignee_type` (pre-existing)

Zero errors in files modified by this plan.

## Acceptance Criteria

- [x] Windows tab shows 3 distinct code blocks (install service, collect now, standalone)
- [x] All 28 check names displayed grouped by category in a toggleable panel
- [x] Download EXE installer card rendered in Windows tab header
- [x] `agent_type === "powershell"` renders purple "PS" badge in evidence source column
- [x] Existing Linux / Docker / Kubernetes tabs are unchanged
- [x] No TypeScript compilation errors in modified files

## Self-Check: PASSED

- components/WindowsInstallTab.tsx: FOUND
- components/AgentInstallation.tsx: FOUND
- components/AssetComplianceList.tsx: FOUND
- Commit 0b3d6e4: FOUND
