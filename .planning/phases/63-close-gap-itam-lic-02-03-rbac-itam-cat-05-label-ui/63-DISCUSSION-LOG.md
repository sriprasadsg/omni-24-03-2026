# Phase 63: Close gap: ITAM-LIC-02/03 RBAC + ITAM-CAT-05 label UI - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-11
**Phase:** 63-Close gap: ITAM-LIC-02/03 RBAC + ITAM-CAT-05 label UI
**Areas discussed:** Label UI entry point, Single vs bulk label scope, Download UX, RBAC fix scope

---

## Label UI entry point

| Option | Description | Selected |
|--------|-------------|----------|
| Per-row action in LifecyclePanel | Add a 'Label' button next to Check Out/Check In/Mark Audited. Smallest change, matches existing pattern. | ✓ |
| New dedicated Labels tab/panel | 7th ITAMConsole tab with its own asset list + selection UI. | |
| Both — row action for single, tab for bulk | Row action for single-asset, plus a Labels tab for bulk. | |

**User's choice:** Per-row action in LifecyclePanel (recommended)

**Follow-up:** Given the row already has 3 text-button actions, what does clicking "Label" do?

| Option | Description | Selected |
|--------|-------------|----------|
| Small dropdown/menu | QR Code / Barcode / Label Sheet (this asset), each its own download. | ✓ |
| Single default download | Immediately downloads the label sheet PDF only. | |
| Opens a small modal | Modal shows QR + barcode previews with download buttons, plus "add to sheet". | |

**User's choice:** Small dropdown/menu (recommended)
**Notes:** No existing dropdown/menu component exists in the codebase — flagged as Claude's discretion for research/planning to resolve the exact implementation.

---

## Single vs bulk label scope

| Option | Description | Selected |
|--------|-------------|----------|
| No — single-asset only | Closes the reachability gap per ITAM-CAT-05's singular "for an asset" wording; bulk deferred. | ✓ |
| Yes — wire bulk selection too | Row checkboxes + toolbar "Print Label Sheet (N selected)". | |

**User's choice:** No — single-asset only (recommended)
**Notes:** Bulk deferred as a noted future enhancement, not part of this phase.

---

## Download UX

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — direct download, no preview | Matches backend's Content-Disposition: attachment; simplest implementation. | ✓ |
| No — add a preview step | Show image/PDF in a lightweight preview before download triggers. | |

**User's choice:** Yes — direct download, no preview (recommended)

---

## RBAC fix scope

| Option | Description | Selected |
|--------|-------------|----------|
| Just the RBAC fix | Swap Depends(get_current_user) → Depends(_require_itam_admin) on both routers + regression tests. | ✓ |
| Also add a coupling test | Additionally test that manage:assets and manage:itam/view:itam stay co-granted. | |

**User's choice:** Just the RBAC fix (recommended)
**Notes:** The permission-string coupling gap stays tracked as tech debt in v4.0-MILESTONE-AUDIT.md, not addressed here.

---

## Claude's Discretion

- Exact dropdown/menu implementation (no existing dropdown component in the codebase — pick minimal `useState`-toggled panel or an inline 3-button group, whichever needs less new code).
- Whether `get_current_user` import stays in either fixed file (only if still used elsewhere in that file).
- Downloaded file naming — respect the backend's existing `Content-Disposition` filename, don't invent a new one.

## Deferred Ideas

- True bulk label printing (multi-select assets → one sheet) — backend already supports it via `MAX_LABEL_SHEET_ASSETS`; deferred to keep this phase minimal.
- `manage:assets` vs `manage:itam`/`view:itam` permission-string coupling test — tracked as tech debt in `v4.0-MILESTONE-AUDIT.md`, not this phase's scope.
