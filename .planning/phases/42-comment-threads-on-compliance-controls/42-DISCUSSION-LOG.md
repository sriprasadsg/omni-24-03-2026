# Phase 42: Comment Threads on Compliance Controls - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-20
**Phase:** 42-comment-threads-on-compliance-controls
**Areas discussed:** Who can comment, @mention notification delivery, Comment editing/deletion, @mention autocomplete

---

## Who can comment

| Option | Description | Selected |
|--------|-------------|----------|
| admin/super_admin/compliance_reviewer | Mirrors existing evidence-review restriction. | ✓ (Claude's choice) |
| Any authenticated tenant user | Broader access. | |
| You decide | | ✓ |

**User's choice:** You decide → Claude chose admin/super_admin/compliance_reviewer (Recommended)

---

## @mention notification delivery

| Option | Description | Selected |
|--------|-------------|----------|
| In-app only | Existing notification system (bell icon / NotificationsDashboard). | ✓ (Claude's choice) |
| In-app + email | Also send email via notification_service.py. | |
| You decide | | ✓ |

**User's choice:** You decide → Claude chose in-app only (Recommended)

---

## Comment editing/deletion

| Option | Description | Selected |
|--------|-------------|----------|
| No — immutable | Append-only, chain-of-custody-log precedent. | ✓ (Claude's choice) |
| Yes, edit/delete own | Standard comment-thread UX. | |
| You decide | | ✓ |

**User's choice:** You decide → Claude chose immutable (Recommended)

---

## @mention autocomplete

| Option | Description | Selected |
|--------|-------------|----------|
| Plain-text parsing | Parse @username after posting, no live search UI. | ✓ (Claude's choice) |
| Live autocomplete | User-search dropdown while typing. | |
| You decide | | ✓ |

**User's choice:** You decide → Claude chose plain-text parsing (Recommended for v1)

## Claude's Discretion

All 4 areas above — user deferred each explicitly ("You decide").

## Deferred Ideas

- Live @mention autocomplete — future enhancement if needed
- Email notification delivery — future enhancement if needed
