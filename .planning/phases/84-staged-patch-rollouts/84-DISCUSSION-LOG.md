# Phase 84: Staged Patch Rollouts - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-11-05
**Phase:** 84-staged-patch-rollouts
**Areas discussed:** Maintenance window, What runs without a click, Rings and starting a rollout, Halt and revert

---

## Maintenance window

**Where the window comes from**

| Option | Description | Selected |
|--------|-------------|----------|
| Recurring windows (Recommended) | Fix the Settings windows (time zone, past midnight), show them in Change Management; each ring installs in the next open window | ✓ |
| One approved change per rollout | Rollout links to a CAB-approved change; installs only between its scheduled start and end | |
| Both | Recurring window open AND an approved change | |

**Time zone**

| Option | Description | Selected |
|--------|-------------|----------|
| One per tenant (Recommended) | Each tenant sets one zone for all its windows | ✓ |
| Per window | Each window carries its own zone | |
| UTC only | Keep today's behaviour | |

**Tenant with no window**

| Option | Description | Selected |
|--------|-------------|----------|
| Can't start (Recommended) | Start disabled with "Add a maintenance window first" | ✓ |
| Starts but waits | Rollout waits for a window to be added | |
| Default window | Every tenant gets an editable default window | |

**Window closes partway through a ring**

| Option | Description | Selected |
|--------|-------------|----------|
| Expire at window end (Recommended) | Instructions expire when the window closes; running installs finish; next window picks the host up | ✓ |
| Fixed expiry | Fixed lifetime (e.g. 4 h) regardless of window | |
| Stop and halt | Unfinished ring halts the rollout at window close | |

---

## What runs without a click

**Which patches count as reversible**

| Option | Description | Selected |
|--------|-------------|----------|
| Linux packages only (Recommended) | Linux package whose current version is still offered; Windows always needs approval | |
| Linux + uninstallable Windows KBs | As above plus KBs Windows marks uninstallable on that host | ✓ |
| Nothing automatic | Every install waits for per-ring approval | |

**Notes:** The user chose the broader option over the research default, accepting that Windows' flag is not always reliable before install.

**Reboot-to-take-effect Linux packages (kernel, glibc, systemd)**

| Option | Description | Selected |
|--------|-------------|----------|
| No, need approval (Recommended) | Counted as not reversible | ✓ |
| Yes, like any package | Install alone; reboot still waits | |

**Approval card for install and reboot**

| Option | Description | Selected |
|--------|-------------|----------|
| Two lines, two clicks (Recommended) | Install and Reboot lines, each own Approve/Deny; Reboot appears after installs | ✓ |
| One click covers both | One Approve per ring | |

**When an approved reboot happens**

| Option | Description | Selected |
|--------|-------------|----------|
| In window, 5-min warning (Recommended) | At once if a window is open, else next window; 300 s warning | ✓ |
| In window, 1-min warning | Same timing, 60 s warning | |
| At the window's end | Late in the window | |

---

## Rings and starting a rollout

**Ring makeup**

| Option | Description | Selected |
|--------|-------------|----------|
| Agent groups (Recommended) | Each ring = one or more existing agent groups; leftovers join the last ring | ✓ |
| Percentages | Automatic split (e.g. 5% / 25% / rest) | |
| Picked per rollout | Operator ticks hosts each time | |

**Default soak and failure limit**

| Option | Description | Selected |
|--------|-------------|----------|
| 24 h soak, strict canary (Recommended) | 24 h soak; any canary failure halts; later rings >10% once ≥10 reported, else any failure | ✓ |
| Longer canary soak | Canary 3 days, later rings 1 day | |
| Short soak | 4 h per ring | |

**Who starts a rollout**

| Option | Description | Selected |
|--------|-------------|----------|
| Operator starts (Recommended) | Operator picks patches; vulnerability suggestion opens a pre-filled draft | ✓ |
| Platform drafts weekly | Weekly draft shown as a suggestion | |
| Platform starts some itself | Reversible-only rollouts start on their own | |

**Canary lacks an operating system in the rollout**

| Option | Description | Selected |
|--------|-------------|----------|
| Refuse to start (Recommended) | Start disabled, names the missing OS | ✓ |
| First ring with it is canary | That ring gets canary rules | |
| Drop those patches | Start without them | |

**Host already in an active rollout**

| Option | Description | Selected |
|--------|-------------|----------|
| Left out, listed (Recommended) | New rollout starts without busy hosts and lists them | ✓ |
| Refuse the new rollout | Can't start until hosts are free | |
| Queue for those hosts | Reach them after the current rollout | |

---

## Halt and revert

**Revert scope on a failed ring**

| Option | Description | Selected |
|--------|-------------|----------|
| The whole failed ring (Recommended) | Every host in the ring that installed; earlier rings keep it | ✓ |
| Only the failed hosts | Healthy hosts keep the patch | |
| Everything so far | All rings reverted | |

**Does the revert wait for someone**

| Option | Description | Selected |
|--------|-------------|----------|
| On its own; reboot waits (Recommended) | Runs at once as an undo (also outside window and during a stop); reboot needs approval | ✓ |
| Needs one approval | Halt automatic, revert approved per ring | |
| Halt only | Revert button, nothing uninstalled until pressed | |

**After a halt**

| Option | Description | Selected |
|--------|-------------|----------|
| Resume or cancel (Recommended) | Resume (manage, typed reason) re-runs the gate; Cancel ends; no skipping | ✓ |
| Also skip hosts | Continue without the failed hosts | |
| Cancel only | Start a new rollout to retry | |

**Silent host after reboot**

| Option | Description | Selected |
|--------|-------------|----------|
| 30 minutes (Recommended) | No new-boot heartbeat in 30 min halts the ring | ✓ |
| 15 minutes | Faster, risks false halts on slow Windows updates | |
| 2 hours | Tolerant, blocks longer | |

**Host offline for the whole ring**

| Option | Description | Selected |
|--------|-------------|----------|
| Not reached, ring goes on (Recommended) | Not a failure; patched later; canary needs ≥1 install per OS | ✓ |
| Ring waits for it | Ring finishes only when every host installed | |

---

## Claude's Discretion

- Health-gate service list (lean: Phase 83 watched services + agent service).
- How long a rollout stays active for "not reached" hosts.
- Revert-during-stop vs the delivery hold-back.
- Canary auto-installs vs Phase 81 per-host decision, 20/hour limit and breaker.
- Retiring or fencing the old `staged_deployments` service.
- Monthly window recurrence.
- Screen placement, layout and copy (UI-SPEC).

## Deferred Ideas

- Platform-drafted weekly rollouts or self-started reversible rollouts.
- Rollouts tied to a CAB-approved Change Management change.
- Known-bad patch list across tenants (AOPS-F4).
