# Phase 59: Procurement & Finance (Warranty & Depreciation) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-05
**Phase:** 59-procurement-finance-warranty-depreciation
**Areas discussed:** Money representation, Supplier reference, Warranty expiry alert delivery, Depreciation schedule

**Mode:** Auto (no interactive prompts) — user explicitly asked to continue through Phases 59-61 autonomously, checking in only at `gate="blocking-human"` checkpoints. All choices below are Claude-selected recommended defaults, logged here for audit.

---

## Money Representation

| Option | Description | Selected |
|--------|-------------|----------|
| Integer cents | `purchaseCostCents: int`, no float drift | ✓ |
| Float dollars | `purchaseCost: float` | |
| Decimal/string | `purchaseCost: str` parsed as Decimal | |

**Selected:** Integer cents. No prior money-handling convention exists elsewhere in the codebase; integer cents is the standard defense against floating-point drift in depreciation arithmetic.

---

## Supplier Reference

| Option | Description | Selected |
|--------|-------------|----------|
| Reference by id | `supplierId` pointing at Phase 56's Supplier catalog entity | ✓ |
| Free-text name | `supplierName: str`, no FK | |

**Selected:** Reference by id — matches the existing `manufacturerId`/`categoryId` pattern already used on `AssetModelCreate`.

---

## Warranty Expiry Alert Delivery

| Option | Description | Selected |
|--------|-------------|----------|
| Background sweep + notification_service | Mirrors `compliance_remediation_sla_service.py`'s tenant-safe scheduler pattern | ✓ |
| On-demand check only (no proactive alert) | Would not satisfy "proactive expiry alerts" in ITAM-FIN-02 | |
| New standalone notification mechanism | Reinvents infra that already exists | |

**Selected:** Background sweep cloning `run_sla_pass`/`start_remediation_sla_scheduler`'s raw-`db`-plus-explicit-`set_tenant_id` pattern, delivering via existing `notification_service.send_notification`. This is the specific recurring bug class the v4.0 milestone research flagged as highest-severity risk (tenant-isolation violations in background schedulers) — called out explicitly rather than left implicit.

---

## Depreciation Schedule

| Option | Description | Selected |
|--------|-------------|----------|
| Straight-line, params at Model level, computed at read time | Matches locked requirement text exactly | ✓ |
| Straight-line, params at Asset level | Contradicts requirement's explicit "assigned at the model level" | |
| Multiple depreciation methods | Requirement only asks for straight-line | |

**Selected:** Straight-line only, params on the Model entity, computed at read time, floored at salvage value. This isn't really a gray area — the requirement text already locks it — logged here for completeness.

---

## Claude's Discretion

- Per-tenant config doc `type` string/field names for the warranty alert window (mirror `evidence_staleness`/`remediation_sla_at_risk` naming).
- Partial-year depreciation proration (day/month) vs whole-year-boundary — default to whole-year unless research finds a reason not to.
- Webhook/notification `event_type` string for warranty alerts.
- PO number format — free text, no validation pattern specified.

## Deferred Ideas

None — discussion stayed within phase scope.
