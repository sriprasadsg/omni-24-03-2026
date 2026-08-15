# Phase 60: Licenses & Consumables - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-05
**Phase:** 60-licenses-consumables
**Areas discussed:** Pre-existing stub plans, Assignment/checkout history reuse, Seat/quantity model, Component attachment

**Mode:** Auto (no interactive prompts) — user explicitly asked to continue through Phases 59-61 autonomously, checking in only at `gate="blocking-human"` checkpoints. All choices below are Claude-selected recommended defaults, logged here for audit.

---

## Pre-Existing Draft Plans

| Option | Description | Selected |
|--------|-------------|----------|
| Treat as superseded, replan properly | Existing 60-01/02/03-PLAN.md are 9-line sketches with no frontmatter, no task structure, no threat model, never plan-checked | ✓ |
| Execute as-is | Risk: no tenant-isolation/RBAC direction, no verification criteria, incompatible with gsd-executor's expected `<task>` format | |

**Selected:** Superseded. Real research + gsd-planner will overwrite these with proper GSD-format plans.

---

## Assignment/Checkout History Reuse

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse `itam_lifecycle_service.write_history`/`db.assignment_history` directly | If record shape generalizes across asset/license/consumable | ✓ (preferred, research to confirm) |
| Clone into parallel `license_history`/`consumable_history` collections | Only if the shared shape genuinely doesn't fit | (fallback) |

**Selected:** Prefer direct reuse; research decides based on actual record-shape fit.

---

## Seat/Quantity Model

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed seat count, polymorphic assign target (user or asset), reject over-assignment | Mirrors Phase 57's `CheckoutRequest` targetType/targetId pattern | ✓ |
| Unlimited assignment, track overage separately | Contradicts "real seat count" framing in the phase goal | |

**Selected:** Fixed seat count with explicit rejection past capacity, atomic quantity decrement for consumables (no-silent-drop, per Phase 58 precedent).

---

## Component Attachment

| Option | Description | Selected |
|--------|-------------|----------|
| `parentAssetId` reference, surfaced on asset detail response | Consistent with how the rest of ITAM models parent/child relationships | ✓ |
| Separate top-level components list, no asset-detail integration | Contradicts requirement's "listed on that asset's record" | |

**Selected:** `parentAssetId` reference, surfaced on asset detail.

---

## Claude's Discretion

- Endpoint/router file naming — decide during research based on existing file line counts (500-line CLAUDE.md limit).
- Whether license expiry needs a proactive-alert sweep (like Phase 59) or read-time-only visibility — research to check REQUIREMENTS.md wording before assuming Phase 59's scheduler pattern applies here.
- Component attached/detached representation (status enum vs nullable FK).

## Deferred Ideas

None — discussion stayed within phase scope.
