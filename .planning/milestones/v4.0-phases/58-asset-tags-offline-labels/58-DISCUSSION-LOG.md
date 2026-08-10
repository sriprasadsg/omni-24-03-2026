# Phase 58: Asset Tags & Offline Labels - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-05
**Phase:** 58-Asset Tags & Offline Labels
**Areas discussed:** Label Content, QR Payload, Print Layout

---

## Label Content

| Option | Description | Selected |
|--------|-------------|----------|
| Tag + name + model | Human-readable text under the codes so someone without a scanner can still identify the asset. Matches typical asset-tag label conventions (Snipe-IT parity). | ✓ |
| Asset tag only | Minimal — just the QR code, 1D barcode, and the tag string itself. Smaller label, less to lay out. | |

**User's choice:** Tag + name + model (Recommended)
**Notes:** None.

---

## QR Payload

| Option | Description | Selected |
|--------|-------------|----------|
| Bare asset tag string | Symmetric with the 1D barcode (Code128 — alphanumeric-friendly, matches the assetTag field format). Simplest offline-safe payload; any future scan flow just looks up the tag. | ✓ |
| Structured payload (e.g. tag + tenant/asset id) | More self-describing for a future mobile scan-to-lookup flow, but adds complexity now for a capability not yet scoped. | |

**User's choice:** Bare asset tag string (Recommended)
**Notes:** None.

---

## Print Layout

| Option | Description | Selected |
|--------|-------------|----------|
| Standard Avery-style label sheet | Fixed-size label cells matching a common Avery product (e.g. 30-per-sheet address-label dimensions) — labels line up with pre-cut sticker sheets many orgs already stock. | ✓ |
| Simple uniform grid sized to the page | Just tile labels evenly across Letter/A4 with margins — no commitment to a specific commercial product's dimensions. User cuts by hand or uses plain paper. | |

**User's choice:** Standard Avery-style label sheet (Recommended)
**Notes:** None.

---

## Claude's Discretion

- Exact Avery product/dimensions to target (no specific product named by the user).
- 1D barcode symbology (Code128, following from the bare-tag-string QR framing).
- Label border/cut-lines, font sizing, exact PDF page margins.
- Bulk-selection API shape (query param list vs POST body) for "one or more assets".

## Deferred Ideas

None — discussion stayed within phase scope.
