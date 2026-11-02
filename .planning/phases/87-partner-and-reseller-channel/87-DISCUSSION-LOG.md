# Phase 87: Partner and Reseller Channel - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in 87-CONTEXT.md; this log preserves the alternatives considered.

**Date:** 2026-11-02
**Phase:** 87-partner-and-reseller-channel
**Areas discussed:** Partner reach, Seat pool rules, Customer onboarding, Partner identity

---

## Partner reach

| Question | Options presented | Selected |
|----------|-------------------|----------|
| What can a partner admin see inside a customer's organization? | Seats and usage only; Read-only security view; Full management (MSSP) | Seats and usage only |
| Should a customer be able to control what its partner sees? | Fixed by the reach choice; Customer opts in; Super Admin sets per partner | Fixed by the reach choice |
| Can a partner appoint its own sub-dealers? | No, one level only; Yes, two levels | No, one level only |
| Who inside a partner can act for it? | Partner admin + partner viewer; Partner admin only | Partner admin + partner viewer |

## Seat pool rules

| Question | Options presented | Selected |
|----------|-------------------|----------|
| How should a partner's seat pool work? | Fixed pool, split among customers; Usage-counted pool | Fixed pool, split among customers |
| Can a partner take seats back from a customer? | Only unused seats; Any seats, new installs blocked | Only unused seats |
| Super Admin shrinks a pool below what is handed out? | Refuse the change; Allow, block new allotments | Refuse the change |
| Pool expiry or trial seats? | Pool expiry date; No expiry for now; Expiry and trial pools | Pool expiry date |

## Customer onboarding

| Question | Options presented | Selected |
|----------|-------------------|----------|
| Who creates a customer organization and its first admin? | Partner admin creates both; Partner creates org, Super Admin approves; Customer signs up with a partner code | Partner admin creates both |
| Which screens can a partner's customer have? | Super Admin sets a ceiling per partner; Partner picks freely; Super Admin only | Super Admin sets a ceiling per partner |
| Can a customer move away from its partner? | Super Admin moves it; Not in this phase | Super Admin moves it |
| What happens to existing organizations? | Stay direct customers; Assign during migration | Stay direct customers |

## Partner identity

| Question | Options presented | Selected |
|----------|-------------------|----------|
| What is a partner in the system? | Its own organization; Organization that can also run endpoints | Its own organization |
| How does the Super Admin manage partners? | New Partners screen; Inside Tenant Management | New Partners screen |
| What does suspending a partner do? | Partner locked, customers untouched; Partner and customers frozen | Partner locked, customers untouched |
| What should the partner's usage roll-up show? | Seats per customer + export; Also a monthly usage history | Seats per customer + export |

## Claude's Discretion

- Field names, collection layout, migration number.
- Partner portal placement (sidebar section or separate view).
- First sign-in flow for an invited customer admin, reusing existing invite or password-set flows.

## Deferred Ideas

- Partner invoicing and monthly usage history.
- Sub-dealers (two partner levels).
- Customer opt-in to a read-only security view; MSSP-style managed service.
- Customer self-sign-up with a partner code.
- Trial pools.
