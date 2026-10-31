# Phase 83: Autonomous Security Response - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-31
**Phase:** 83-autonomous-security-response
**Areas discussed:** Two-signal rule, Finding outcomes, Timers and budgets, Fences and agent support, Settings

---

## Two-signal rule

| Question | Options | Selected |
|----------|---------|----------|
| What counts as a second signal? | Two origins (Recommended) / Intel feeds only / You decide | Two origins |
| Which automatic actions need two signals? | Block and quarantine (Recommended) / Block only / All three | Block and quarantine |
| How far apart can the two signals be? | 24 hours, then act (Recommended) / 7 days, then act / Never promote | 24 hours, then act |
| Can a tenant turn the rule off? | Always on (Recommended) / Tenant admin can disable / Super Admin only | Free text |

**User's choice on the last question:** "both tenant admin can only handel up to their tenant and super admin can do it for all the tenants"
**Notes:** This differs from the recommended option and loosens RESP-08, so RESP-08 and roadmap criterion 1 were amended to say "by default". Scouting showed automatic IP blocks would almost never fire under an intel-only reading on this VM.

---

## Finding outcomes

| Question | Options | Selected |
|----------|---------|----------|
| A running malicious file fails quarantine | Card: kill, then quarantine (Recommended) / Report failed only / Retry after reboot | Card: kill, then quarantine |
| What does a vulnerability produce? | Suggestion only (Recommended) / Cards for critical only / Card for every one | Suggestion only |
| What does a file change produce? | Suggestion, unless flagged (Recommended) / Card anyway / Nothing | Suggestion, unless flagged |
| Confirm research D6 classes | All three need approval (Recommended) / Let disable_service run | All three need approval |

**Notes:** Scouting confirmed nothing in the backend sets `backup_path`, so a restore card could never succeed today.

---

## Timers and budgets

| Question | Options | Selected |
|----------|---------|----------|
| Which services are watched? | Tenant's chosen list (Recommended) / Any crashed service / Starter list plus tenant's | Tenant's chosen list |
| Restart budget | 3 in an hour, then card (Recommended) / 1 in an hour, then card / 5 in an hour, then card | 3 in an hour, then card |
| Who changes block length? | Tenant admin, 1 h to 7 days (Recommended) / Fixed at 24 hours / Super Admin only | Tenant admin, 1 h to 7 days |
| After a block expires | New decision (Recommended) / Card to extend / Extend while flagged | New decision |
| Isolation auto-revert | 4 hours (Recommended) / 1 hour / 24 hours | 4 hours |
| What is one incident? | Same host, 1-hour gap (Recommended) / Same host, 15-minute gap / Same host, 24 hours | Same host, 1-hour gap |
| Approving a card | Approve each action (Recommended) / One click approves all | Approve each action |
| Confirm research D5 | Yes, no Undo button (Recommended) / Require approval instead | Yes, no Undo button |

**Notes:** Scouting showed agents do not report service failures, so RESP-04 also needs new agent reporting.

---

## Fences and agent support

| Question | Options | Selected |
|----------|---------|----------|
| Research D8: swarm and SOAR | Fence, report honestly (Recommended) / Move behind the gate / Delete both | Fence, report honestly |
| Which agent gets the new actions? | Rust only (Recommended) / Rust and Python | Rust only |
| Which operating systems? | Windows and Linux (Recommended) / Windows only | Windows and Linux |
| Capability ticks | Keep existing ticks (Recommended) / A tick per action | Keep existing ticks |

**Notes:** The re-check confirmed `db.instructions` has writers and no readers. It also found SOAR setting `agents.isolated` for hosts that received nothing.

---

## Settings

| Question | Options | Selected |
|----------|---------|----------|
| Where do tenants change the new settings? | Panel on the screen (Recommended) / API only / All settings in the panel | Panel on the screen |

---

## Claude's Discretion

Origin table detail, "all tenants" read as a bulk write to each tenant's setting, isolation's 4 hours as a fixed default, backoff intervals, quarantine location and format, which capability carries service-failure reporting, how suggestions are shown, and layout and copy of the screen additions.

## Deferred Ideas

Feeding real signatures to agents from the public feeds, keeping file content for real restores, and screens for level, maximum level and never-touch.
