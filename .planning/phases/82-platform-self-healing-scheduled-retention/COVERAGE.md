# API Coverage — PagerDuty Events API v2 and on-call webhooks (Phase 82)

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
> Caller: the host watchdog only (`deploy/omni-watchdog/omni_watchdog/paging.py`, plan 82-05). The backend never calls these services (D-01).

| capability | decision | reason |
|---|---|---|
| pagerduty-events-v2-trigger | INTEGRATE | |
| pagerduty-events-v2-resolve | INTEGRATE | |
| pagerduty-events-v2-dedup-key | INTEGRATE | |
| pagerduty-events-v2-severity | INTEGRATE | |
| pagerduty-events-v2-custom-details | INTEGRATE | |
| pagerduty-events-v2-source-and-summary | INTEGRATE | |
| pagerduty-events-v2-acknowledge | OPT-OUT | explicitly out of scope — acknowledging is the on-call person's act in PagerDuty; the watchdog only triggers and resolves (D-03) |
| pagerduty-change-events | OPT-OUT | not needed — Phase 81 notices are sent as triggers (planner assumption A-82-A7); revisit if operators find them noisy |
| pagerduty-events-v2-links-and-images | OPT-OUT | not needed — the platform serves no public URL for the panel (installChecklist.url is null) and pages carry text only |
| pagerduty-retry-on-429-and-5xx | INTEGRATE | |
| external-heartbeat-ping (PagerDuty heartbeat, Healthchecks.io or similar URL) | INTEGRATE | |
| webhook-json-post | INTEGRATE | |
| webhook-slack-incoming-message-shape | INTEGRATE | |
| webhook-teams-incoming-message-shape | INTEGRATE | |
| email-channel | OPT-OUT | explicitly out of scope — D-02: no email channel (SMTP is unset on this VM) |
