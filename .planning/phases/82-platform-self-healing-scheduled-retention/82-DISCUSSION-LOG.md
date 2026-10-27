# Phase 82: Platform Self-Healing & Scheduled Retention - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-27
**Phase:** 82-platform-self-healing-scheduled-retention
**Areas discussed:** On-call alert channel, Restart rules and the stop, Retention scope and first run, Where it shows on screen, Which certificates are watched, Before the watchdog is installed, How it gets restart rights, Retention policy changes

---

## On-call alert channel

| Option | Description | Selected |
|--------|-------------|----------|
| Root-only file | Key/URL in a root-only file the watchdog reads directly; works when backend/MongoDB are down | ✓ |
| Super Admin screen | Entered in the app, stored encrypted; watchdog needs a cached copy | |
| Both | Screen plus a root-only cached copy | |

| Option | Description | Selected |
|--------|-------------|----------|
| PagerDuty + webhook | Events v2 with dedup key plus plain JSON webhook (Slack/Teams via webhook format) | ✓ |
| PagerDuty only | One channel type | |
| Add email too | Needs SMTP details (unset on this VM) | |

| Option | Description | Selected |
|--------|-------------|----------|
| Backend + optional external ping | Backend notices a silent watchdog; optional external heartbeat URL covers a dead VM | ✓ |
| Backend only | No outside service | |
| External ping only | Needs an external account first | |

| Option | Description | Selected |
|--------|-------------|----------|
| Once, then 'resolved' | One deduplicated page per incident, grouped per run, resolved message on recovery | ✓ |
| Repeat every hour | Re-page hourly | |
| Once, plus a daily reminder | Daily reminder while unresolved | |

**Follow-up (raised while writing context):** the root-only key means the backend cannot page. Options: in-app alarm + external ping (✓), let the backend read the key too, a separate backend-only key.
**User's choice:** In-app alarm + external ping. Backend shows a Super Admin banner and in-app notification when the watchdog goes silent; paging for a dead watchdog/VM comes from the optional external heartbeat URL.

---

## Restart rules and the stop

| Option | Description | Selected |
|--------|-------------|----------|
| 3 in 30 min, backing off | 2 failed checks before a restart; waits 1, 2, 4 min; then give up and page once | ✓ |
| 5 in an hour | More persistent | |
| 1 restart, then page | Most cautious | |

| Option | Description | Selected |
|--------|-------------|----------|
| After 1 hour healthy | Budget resets once the service stays healthy for an hour | ✓ |
| Only when you reset it | Manual reset command | |
| Automatically after 24 hours | Retries a day later regardless | |

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, restarts pause | Platform stop pauses restarts; checks/warnings/pages continue; cached stop state; local STOP file | ✓ |
| No, self-healing keeps going | Stop covers customer machines only | |
| Its own separate switch | Separate pause file | |

| Option | Description | Selected |
|--------|-------------|----------|
| Watch and restart nginx | nginx joins the fixed list and budget | ✓ |
| Watch and page only | Never restart nginx | |
| Only the three named | Backend, MongoDB, Ollama as written | |

---

## Retention scope and first run

| Option | Description | Selected |
|--------|-------------|----------|
| One job for all routine data | Manual job's scope minus audit logs, plus the 4 telemetry collections; one dry-run and report | ✓ |
| Manual job minus audit logs | Leave the telemetry loop separate | |
| Telemetry and metrics only | Smallest scope | |

| Option | Description | Selected |
|--------|-------------|----------|
| Stop it everywhere | Manual route no longer deletes audit logs either | ✓ |
| Keep it manual-only | Admin can still delete old audit logs manually | |

| Option | Description | Selected |
|--------|-------------|----------|
| Nightly at 02:00 UTC | Tenant by tenant, small batches with pauses | ✓ |
| Every 6 hours | | |
| Weekly (Sunday 02:00 UTC) | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Super Admin, once for all | First run counts only; one confirm | ✓ |
| Each tenant's admin | Per-tenant confirm | |
| Super Admin, per tenant | Confirm tenant by tenant | |

---

## Where it shows on screen

| Option | Description | Selected |
|--------|-------------|----------|
| Platform panel on Autonomous Ops | Super Admin-only panel in platform scope with status, warnings, test alert, retention review/confirm | ✓ |
| Existing System Health screen | Spread over System Health and Retention Policies | |
| API-only, banner in UI | Like Phase 81 settings | |

| Option | Description | Selected |
|--------|-------------|----------|
| Button; watchdog sends it | Backend records the request; watchdog sends within a minute; panel shows result | ✓ |
| Server command only | | |
| Both | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Super Admin only | Panel and "no working channel" banner | ✓ |
| Super Admin + Platform Support (read-only) | | |

| Option | Description | Selected |
|--------|-------------|----------|
| 14, 7 and 1 days ahead | 7-day growth window; page at 1 day | ✓ |
| 30 days ahead | | |
| 7 days ahead only | | |

---

## Which certificates are watched

| Option | Description | Selected |
|--------|-------------|----------|
| HTTPS cert + your list | /etc/nginx/ssl/omni.crt by default plus extra paths in the root-only config; warns that pinned-cert replacement needs an agent update | ✓ |
| Only the HTTPS cert | From the nginx config | |
| What port 443 actually serves | Live check plus listed files | |

---

## Before the watchdog is installed

| Option | Description | Selected |
|--------|-------------|----------|
| Show 'not installed', no alarms | Panel links the checklist; dead-man arms after the first heartbeat; disk/cert checks wait | ✓ |
| Not installed + backend checks | Backend runs disk/cert checks meanwhile (in-app only) | |
| Persistent warning banner | Banner on every page until installed | |

---

## How it gets restart rights

| Option | Description | Selected |
|--------|-------------|----------|
| Own user + narrow polkit rule | `omni-watchdog` user; polkit allows restarting only the listed units | ✓ |
| Run as root | Simplest | |
| Own user + sudoers rule | Same effect via sudo | |

---

## Retention policy changes

| Option | Description | Selected |
|--------|-------------|----------|
| Back to a count first | Shortened period → count-only for that tenant/data type until a Super Admin confirms; lengthening needs no confirm | ✓ |
| Delete straight away | | |
| Count only if it's a big drop | Threshold-based | |

---

## Claude's Discretion

- Which warnings page versus only appear in the panel/Activity (default suggested in CONTEXT.md)
- Exact "no working channel" rule
- How the watchdog reads the stop and writes events/heartbeat (direct MongoDB vs backend endpoint, local spool) — research item
- Filesystems measured, per-service check method, retention batch size/pause, file formats, Activity row shape

## Deferred Ideas

None — discussion stayed within phase scope.
