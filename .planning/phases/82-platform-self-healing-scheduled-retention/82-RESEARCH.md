# Phase 82: Platform Self-Healing & Scheduled Retention - Research

**Researched:** 2026-10-27
**Domain:** Host-level watchdog (systemd timer + stdlib Python + polkit), on-call alerting (PagerDuty Events v2 / webhook), FastAPI + MongoDB ingest/outbox/health plumbing, scheduled bounded-batch data retention with a count-only gate
**Confidence:** HIGH for repo integration points and host facts (read this session); MEDIUM for polkit/PagerDuty behaviours (cited docs, live install is the operator's step); LOW only where listed in the Assumptions Log

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Locked by milestone requirements and earlier phases (not re-decided here)**
- Out of scope for v4.3: deleting files to free disk, automatic certificate renewal (agents pin the certificate), the app installing systemd units / editing sudoers or polkit / restarting the live server.
- The Platform tenant is never eligible for tenant autonomy (Phase 81 D-04); the watchdog is how the platform server keeps itself healthy, and it acts under its own fixed list, not the tenant gate.
- Ollama is not installed on this VM: its expected state here is "off", so the watchdog never tries to start it (expected-state registry).
- Retention never touches audit logs, the audit ledger or decision records (HEAL-06). The hash-chained audit ledger keeps its own per-tenant purge (`audit_ledger.purge_expired`, spec C5), untouched by this phase.
- Live-only steps stay the user's: installing the watchdog units, the polkit rule and any drop-ins; stopping/starting MongoDB and the backend for real; alert delivery to the real channel; confirming the first retention count. Never `run-on-ubuntu.sh` (ufw SSH lockout).

**On-call channel**
- **D-01:** The platform's on-call channel (PagerDuty routing key and/or webhook URL) lives in a **root-only file on the server** (e.g. `/etc/omni-watchdog/oncall.env`, readable by root and the watchdog's own user only). The watchdog reads it directly and sends pages itself, so paging works when the backend or MongoDB is down. The backend **never** holds or sees the key.
- **D-02:** Supported channel types: **PagerDuty Events v2** (stable `dedup_key` per incident) and a **plain JSON webhook**; Slack/Teams incoming webhooks are served through the webhook type with the right message shape. No email (SMTP is unset on this VM). No new libraries: stdlib HTTP client in the watchdog.
- **D-03:** **One page per incident**, deduplicated by a stable key, then a **"resolved"** message when it recovers. Alerts raised in the same check run are grouped into one page (no alert storm).
- **D-04:** Because only the watchdog holds the key, every on-call message from the backend — including Phase 81's notices (stop pressed, circuit breaker tripped, rate limit hit: 81 D-15/D-18/D-20) — is **handed to the watchdog to deliver** (it arrives within about a minute). `backend/autonomous_ops/notify.py` keeps posting the in-app notice and additionally queues the on-call message; its callers do not change.
- **D-05:** **Dead-man's switch:** the watchdog records a heartbeat every run. If it goes silent for a few minutes, the backend raises an **in-app alarm only** (Super Admin banner + in-app notification); it cannot page because it has no key. **Paging** for a dead watchdog or a dead VM comes from an **optional external heartbeat URL** (PagerDuty heartbeat, Healthchecks.io or similar) that the watchdog pings every run when configured in the same root-only file. The install checklist strongly recommends configuring it.

**Restart rules and the stop**
- **D-06:** A service counts as down after **2 failed checks in a row** (about 2 minutes), so a slow start is not mistaken for a crash.
- **D-07:** Restart budget: **at most 3 restarts within 30 minutes per service**, waiting **1, then 2, then 4 minutes** between attempts. When the budget is used up the watchdog **stops restarting that service and pages once**.
- **D-08:** The budget **re-arms on its own once the service has stayed healthy for 1 hour** (e.g. after someone fixed it by hand). While the service is still down it stays given up — never a restart loop.
- **D-09:** **MongoDB is restarted before the backend.** When both are down, MongoDB is restarted first and must be healthy before the backend is touched.
- **D-10:** The fixed restart list is **MongoDB, the backend, nginx, and Ollama only where it is expected**. **nginx is added** to the services HEAL-01 names (user-approved clarification: if nginx dies the site is unreachable); it shares the same budget rules. — **Reversibility:** reversible — removing a unit from the list and the polkit rule.
- **D-11:** **"Stop all organizations" pauses the watchdog's restarts.** Checks, warnings and pages continue during a stop; only restarts pause. The watchdog reads the stop from MongoDB when it can (`system_settings` doc `type: "autonomous_ops"`), falls back to the **last stop state it saw** (cached locally) when MongoDB is down, and always honours a **local STOP file** on the server.
- **D-12:** The watchdog runs as its own **dedicated system user (`omni-watchdog`)**, not root. A **polkit rule** shipped in the repo (the operator installs it) lets that user restart **only** `mongod`, `omni-backend`, `nginx` (and `ollama` where expected) and nothing else. Only the on-call file and its own state directory are readable/writable to it. — **Reversibility:** costly — changing the privilege model later means the operator re-installs the units and replaces the polkit rule on every server.

**Warnings**
- **D-13:** Certificates watched: by default the HTTPS certificate nginx serves (`/etc/nginx/ssl/omni.crt`, which agents also pin via `AGENT_CA_CERT_FILE`), **plus any extra certificate file paths listed in the root-only config**. Warnings at 30, 14, 7 and 1 days before expiry; the warning text says that replacing a pinned certificate needs an agent update. Never renew.
- **D-14:** Disk warnings at **80, 90 and 95 percent**. **Disk-fill forecast:** growth rate measured over the **last 7 days**; warn when the disk is forecast to be full within **14 days**, again at **7 days**, and **page at 1 day**. Never delete files.

**Retention**
- **D-15:** **One scheduled retention job for all routine data:** everything the manual job covers today (system metrics, notifications, agent location history, agent uptime rollups) **except audit logs**, **plus** the four agent telemetry collections (`agent_metrics`, `asset_metrics`, `persistence_results`, `logs`). The existing separate `agent_telemetry_retention_loop` is **folded into this job**, so one job, one dry-run and one report cover everything. Never touched: audit logs, the audit ledger, decision records (`autonomy_actions`), compliance evidence. Per-tenant periods come from the existing `retention_policies`. — **Reversibility:** costly — deleted documents cannot be restored; D-18/D-19 are the safety gates. Consequence to surface in the install checklist: until the first count is confirmed, the telemetry purge that runs daily today also waits, so the confirm should happen soon after deploy.
- **D-16:** The manual route (`POST /api/retention/run`) **stops deleting audit logs too**, everywhere. It keeps cleaning everything else.
- **D-17:** The job runs **nightly at 02:00 UTC**, tenant by tenant, in **small bounded batches with short pauses** so MongoDB stays responsive on the 2-vCPU server. The next scheduled run time is shown (the existing `/stats` `next_scheduled` field and the Platform health panel).
- **D-18:** **First run = count only.** It counts what would be deleted per tenant and per data type and deletes nothing. A **Super Admin confirms once for all tenants**; from then on the nightly job deletes.
- **D-19:** When a tenant **shortens** a retention period, the next run goes **back to count-only for that tenant and data type** until a Super Admin confirms; other tenants and unchanged data types keep deleting. **Lengthening** a period needs no confirmation.

**Screen**
- **D-20:** A **Super Admin-only "Platform health" panel on the Autonomous Ops screen** (platform scope, next to the platform stop and platform activity from Phase 81) shows: service states (MongoDB, backend, nginx, Ollama expected-off), watchdog last seen, restart-budget state, certificate expiry, disk usage and forecast, on-call channel status, **Send test alert**, the next retention run, and the **retention count review with Confirm** (D-18/D-19).
- **D-21:** **Send test alert:** the Super Admin clicks the button; the backend records a test request; the watchdog picks it up within a minute, sends it, and reports the outcome; the panel shows "Sent at HH:MM, delivered" or the error. The backend never sees the key (D-01).
- **D-22:** The **"no working on-call channel" banner** and the panel are visible to **Super Admin only**. Tenants never see platform internals.
- **D-23:** Watchdog events (checks that changed state, restarts, warnings, pages, test results) appear in the Activity view **at platform scope, Super Admin only**. They must not leak into tenant views (Phase 81's tenant query already includes platform-scope **stop control** rows for tenant viewers — watchdog events must not ride that path).
- **D-24:** **Before the watchdog is installed:** the panel shows **"Watchdog not installed"** with a link to the install checklist. The dead-man's switch (D-05) **arms only after the first heartbeat ever arrives**, so nothing alarms about a watchdog that was never installed. Disk and certificate checks wait for the watchdog (the backend does not run them meanwhile).

**UI-phase amendments (user-decided 2026-10-27, during /gsd-ui-phase 82)**
- **D-25:** The tenant retention screen that edits per-tenant periods is `components/RetentionPolicyDashboard.tsx` (over `/api/retention/policies`); `RetentionPoliciesDashboard.tsx` named in canonical refs is a different screen (`/api/retention-tiers`). On that screen the **audit-logs card keeps its row but loses its Edit button** and shows the note "Audit logs are kept by the audit ledger's own schedule, not by this cleanup." (follows from D-16).
- **D-26:** The **manual "Run cleanup now"** (`POST /api/retention/run`) **honours the same count-only gate** as the nightly job: data types still waiting for confirmation (first run, or a shortened period per D-19) are only counted until a Super Admin confirms; everything already confirmed is deleted as usual. One rule everywhere, so the review cannot be bypassed with Run now. Extends D-16.

### Claude's Discretion
- Which warnings page versus only appear in the panel/Activity (suggested default: every threshold crossing is one deduplicated on-call message, PagerDuty severity rising from info to critical — e.g. 30-day cert and 80% disk as info, 1-day cert, 95% disk and 1-day forecast as critical).
- Exact rule for "no working channel" (suggested: no channel configured, or the last test/delivery failed).
- How the watchdog reads the stop and writes its events/heartbeat (direct MongoDB with its own credentials versus a backend endpoint with a token, with a local spool when the backend is down) — a research item: MongoDB authentication is still an open readiness item and the research recommends a stdlib-only watchdog.
- Which filesystems are measured (at least the one holding `/` and the MongoDB data directory — the same 247 GB disk on this VM).
- Check method per service (backend readiness URL, MongoDB ping, nginx port probe), batch size and pause length for retention, the exact on-call/heartbeat file format, and the Activity row shape for watchdog events.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope. (Tenant certificate-inventory expiry warnings and an email on-call channel were mentioned as options only, not requested.)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HEAL-01 | Out-of-backend (systemd timer) watchdog checks backend readiness, MongoDB, Ollama-where-expected every minute; restarts from fixed allowlist, MongoDB before backend | "Watchdog design": stdlib checks (OP_MSG ping, `/api/health/ready`, nginx TLS probe), polkit rule, ordering and demo-mode pitfall |
| HEAL-02 | Restart budget with backoff; budget exhausted -> stop restarting and page once | Restart state machine (3 per 30 min, 1/2/4 min waits, re-arm after 1 h healthy), page-once incident model |
| HEAL-03 | Warned 30/14/7/1 days before cert expiry and at 80/90/95% disk; never renews or deletes | Cert via `openssl x509 -enddate` + `ssl.cert_time_to_seconds` (verified live), disk via `os.statvfs` with df semantics, rung/incident-key model |
| HEAL-04 | Warned days ahead of disk-full at current growth | Hourly samples in `state.json`, 7-day least-squares slope, 14/7/1-day rungs |
| HEAL-05 | On-call alert to webhook/PagerDuty with dedup; test alert; banner when no working channel; alert when watchdog stops reporting | Sync protocol (token-authenticated backend endpoint), `oncall_outbox`, PagerDuty Events v2 rules, `health` summary on status poller, dead-man sweep |
| HEAL-06 | Retention per tenant in bounded batches, never audit logs/ledger/decisions; first run dry-run the operator confirms | `retention_job.py` + `retention_gate` model, bounded-batch loop, 409 review token, remove `cleanup_audit_logs` from `run_cleanup` |
| HEAL-07 | Watchdog events in Activity view at platform scope | `kind: "platform_health"` rows in `autonomy_actions`, `list_page` leak guard, bucket/counts changes |
| HEAL-08 | Repo ships unit files, drop-ins, install checklist; app installs nothing | `deploy/omni-watchdog/` layout, static files, structural "installs nothing" test, `systemd-analyze verify` |
</phase_requirements>

## Summary

The phase splits cleanly into two independent halves that meet only in the Platform health panel. **Half A (watchdog)** is a single stdlib-only Python script run by a systemd timer + oneshot as a dedicated `omni-watchdog` user, restarting only `mongod`, `omni-backend`, `nginx` through a polkit rule, checking health with no third-party driver (a hand-built MongoDB `OP_MSG` ping was verified against the live mongod this session, as was the certificate parse). It talks to the backend through **one token-authenticated loopback endpoint** (`/api/internal/watchdog/sync`) that carries its heartbeat, status snapshot and events up and brings the platform stop, queued on-call messages and test-alert requests back down; when the backend is down it keeps a local NDJSON spool and the cached stop state. This is recommended over direct `mongosh`/driver access because MongoDB has no authentication today (any local user could read or write everything, including clearing the stop), `mongosh` costs ~100 MB and seconds every minute on a 7 GB box, and a token endpoint gives the watchdog exactly three capabilities. **Half B (retention)** replaces `agent_telemetry_retention_loop` with one nightly job that evaluates a per-(tenant, data type) gate (`confirmedDays` vs current policy days), counts when gated and deletes in bounded `_id` batches otherwise; "shortened period" is detected by comparison at run time rather than by hooking `retention_policies` writes.

Several traps in the existing code shape the plan: (1) `views.list_page` for the platform tenant returns every row with `tenantId == "platform-admin"`, and the tenant router lets staff name `tenantId=platform-admin`, so new platform-health rows would leak to Platform Support unless the default query excludes `kind: "platform_health"`; (2) `bucket_of` maps any unknown state to `"refused"`; (3) the backend falls into in-memory demo mode if it starts while MongoDB is down and then answers `/api/health/ready` with 503 forever, so after a MongoDB restart the backend usually needs its own restart (this is exactly why D-09 ordering matters); (4) the existing `cleanup_agent_uptime_rollups` filters by the wrong tenant field (`tenant_id` is stored); (5) the shared status poller only fetches platform status in platform scope, but the health banners must show for a Super Admin in any scope.

Everything the app ships is static: unit files, timer, drop-ins, polkit rule, config examples and an `INSTALL.md` checklist under `deploy/omni-watchdog/`. `start-all-services.sh` must NOT be extended to install them (re-running that script is a routine operator action and would silently install a privilege rule). The watchdog script must be installed root-owned outside the checkout, otherwise the backend's `azureuser` could rewrite code that runs with restart rights.

**Primary recommendation:** Build the watchdog as one stdlib script with injected `run`/`now`/`http` seams (tested with a fake systemctl and local fake servers), integrate it through a single token-authenticated `sync` endpoint plus `oncall_outbox`, store watchdog events as `kind: "platform_health"` ledger rows (never `kind: "control"`), and implement retention as a gate-evaluating bounded-batch job whose count/confirm flow is keyed by a review token.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Service checks, restarts, budget state, cert/disk checks, paging | Host OS (systemd timer + `omni-watchdog` script) | — | Must run when backend/MongoDB are down; holds the on-call key (D-01) |
| Privilege boundary for restarts | Host OS (polkit rule, dedicated user) | — | D-12; backend (`azureuser`) must not be able to widen it |
| Heartbeat/event/stop/outbox exchange | API / Backend (`/api/internal/watchdog/*`) | Host OS (local spool + cached stop) | Backend is the only holder of ledger/stop truth; watchdog caches when it is down |
| Dead-man detection, `health` summary, in-app alarm | API / Backend | Database | Backend cannot page (no key); computes silence from `lastSeenAt` |
| Platform-health Activity rows | Database (`autonomy_actions`) via backend ledger | Browser (render) | One ledger, hash-chain mirror, platform scope only (D-23) |
| Retention scheduling, gate, counting, batched deletes | API / Backend (background job, distributed lock) | Database | Needs `retention_policies`, tenants, Mongo access; must survive restarts via stored last-run |
| Retention review/confirm, test alert, health panel | Browser (Super Admin screen) | API / Backend | Permission `control:platform_autonomous_ops` enforced server-side |
| Unit files, drop-ins, polkit rule, checklist | Repo artifacts (`deploy/`) | Operator (installs) | HEAL-08: the app installs nothing |

## Standard Stack

No new runtime dependency anywhere (STACK.md milestone rule). Everything below is stdlib or already installed.

### Core
| Library / Tool | Version | Purpose | Why Standard |
|----------------|---------|---------|--------------|
| Python stdlib (`urllib.request`, `ssl`, `socket`, `struct`, `subprocess`, `json`, `configparser`, `os.statvfs`, `fcntl`) | CPython 3.12.3 [VERIFIED: `python3 --version` on this VM] | Entire watchdog | Runs even if `backend/venv` is broken (CONTEXT specifics) |
| systemd | 255 (255.4-1ubuntu8.18) [VERIFIED: `systemctl --version`] | Timer, oneshot, drop-ins, `LoadCredential=` | Already used for `omni-backup.timer` |
| polkit | 124-2ubuntu1.24.04.4, Duktape engine (`libduktape207`) [VERIFIED: `dpkg -l`] | Per-unit restart authorization | D-12 locked |
| `openssl` CLI | present (`/usr/bin/openssl`) [VERIFIED: `which`] | `openssl x509 -noout -enddate` for cert expiry | Avoids `cryptography` in the watchdog |
| FastAPI / motor / pymongo / APScheduler | existing venv (STACK.md pins; not re-verified) [CITED: .planning/research/STACK.md] | Backend side | Already installed |
| pytest + pytest-asyncio (`asyncio_mode = auto`) | `/home/azureuser/enterprise-omni-agent-ai-platform/pytest.ini:7` [VERIFIED: grep] | Backend + watchdog tests | Existing suite (302 files in `backend/tests`) |
| vitest | `^5.0.0`, script `"test": "vitest run"` [VERIFIED: package.json grep] | UI tests in `src/__tests__/` | Existing |
| node | `/usr/bin/node` [VERIFIED: `which node`] | Run the polkit rule against a stub harness | Only way to unit-test the rule without installing it |

### Supporting
| Tool | Purpose | When to Use |
|------|---------|-------------|
| `systemd-analyze verify` / `security --offline=true` | Lint the shipped unit files without installing | Validation (verified to run unprivileged this session; it flagged `RuntimeMaxSec=` with `Type=oneshot`) |
| `pkcheck --action-id ... --details KEY VALUE --process PID` | Post-install, non-destructive proof of the polkit rule | Install checklist |
| `mongosh` (present, `/usr/bin/mongosh`) | Operator diagnostics only | NOT used by the watchdog |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Backend token endpoint (recommended) | Direct MongoDB via `mongosh` subprocess | MongoDB is unauthenticated: the watchdog user could write anything (clear the stop, forge ledger rows); `mongosh` is a Node binary started every minute; stdlib has no driver. Rejected. |
| Backend token endpoint | Watchdog writes NDJSON, backend tails the directory | One-way: no way to deliver stop, outbox or test requests; needs `azureuser` read access to the watchdog's state dir. Rejected as primary (the spool is kept only as the offline buffer). |
| polkit rule | sudoers with exact `systemctl restart <unit>` lines | Works but D-12 locked polkit; sudoers argument matching is easier to get wrong. |
| Watchdog restarts + stock units | Add `Restart=on-failure` drop-ins too | Recommended as a layer: stock `mongod` and `nginx` units have no `Restart=` [VERIFIED: `systemctl cat`]; systemd handles crashes in 5 s, the watchdog handles hangs and start-limit states. |

**Installation:** none (no packages). Operator-side: `useradd --system`, file copies per `INSTALL.md`.

**Version verification:** no packages installed; versions above come from `python3 --version`, `systemctl --version`, `pkaction --version` (124), `dpkg -l`.

## Package Legitimacy Audit

No external packages are installed by this phase (stdlib + existing venv + system tools only). The `package-legitimacy` gate is therefore not applicable.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                        (every 60 s, systemd timer, User=omni-watchdog)
 +----------------------------------------------------------------------------------+
 |  omni-watchdog.py  (stdlib, root-installed at /usr/local/lib/omni-watchdog/)      |
 |                                                                                  |
 |  read config (watchdog.conf, oncall.env) + state.json + STOP file                |
 |        |                                                                         |
 |        v                                                                         |
 |  CHECKS  -- mongod: systemctl is-active + OP_MSG ping :27017                      |
 |          -- backend: GET 127.0.0.1:5000/api/health/ready (+ /api/health)          |
 |          -- nginx : TLS handshake + any HTTP reply on 127.0.0.1:443               |
 |          -- ollama: only if expected on (else observe-only)                       |
 |          -- certs : openssl x509 -enddate    -- disk : os.statvfs (+ hourly sample)|
 |        |                                                                         |
 |        v                                                                         |
 |  DECIDE  debounce(2) -> budget(3/30min, waits 1/2/4) -> Mongo before backend      |
 |        |                 ^ stop? (STOP file OR synced/cached platform stop)       |
 |        |-- restart: systemctl restart --no-block <unit>  --(polkit rule)--> PID 1 |
 |        |-- incidents opened/escalated/cleared (stable keys, grouped per run)      |
 |        v                                                                         |
 |  PAGE  PagerDuty Events v2 / webhook (key from oncall.env)  + HEARTBEAT_URL ping |
 |        v                                                                         |
 |  SYNC  POST 127.0.0.1:5000/api/internal/watchdog/sync  (Bearer token)             |
 |        |  up: heartbeat, snapshot, events[], delivered[]                          |
 |        |  down: stop, acceptedEventIds, outbox[], testRequest                     |
 |        |-- backend unreachable -> append events to spool, keep cached stop        |
 |        v                                                                         |
 |  EXECUTE tasks (send outbox / test alert) -> POST .../results   -> write state    |
 +----------------------------------------------------------------------------------+
            |                                   ^
            v                                   |
 +------------------------------ backend (azureuser) ------------------------------+
 | watchdog_ingest_endpoints  --> platform_health (singleton docs)                   |
 |    token check (hmac.compare_digest, loopback-only, no X-Forwarded-*)              |
 |    events --> ledger.record_platform_health --> autonomy_actions (kind            |
 |                 "platform_health", tenantId "platform-admin") + audit mirror      |
 | notify.py --> in-app notice (unchanged) + oncall.enqueue --> oncall_outbox        |
 | selfheal sweep (lock, 60 s) --> silent? in-app alarm once (grace after startup)    |
 | retention_job loop (lock, catch-up daily 02:00 UTC) --> gate --> count | delete    |
 | /api/platform/autonomous-ops/{status(+health), health, health/test-alert,         |
 |                               retention/review, retention/confirm, actions}       |
 +----------------------------------------------------------------------------------+
            |
            v   Browser (Super Admin only): banners, Platform health section, review/confirm
```

### Recommended Project Structure
```
deploy/omni-watchdog/                      # static artifacts; the app never installs them
├── omni-watchdog.py                       # -> /usr/local/lib/omni-watchdog/omni-watchdog.py (root:root 0755)
├── systemd/
│   ├── omni-watchdog.service              # oneshot, User=omni-watchdog, hardening
│   ├── omni-watchdog.timer
│   ├── omni-backend.service.d/10-omni-watchdog.conf   # LoadCredential=omni-watchdog-token:...
│   └── mongod.service.d/50-omni-restart.conf          # NEW file name; never touch kernel-rseq-check.conf
├── polkit/49-omni-watchdog.rules
├── etc/watchdog.conf.example              # non-secret: certs, ollama expected, thresholds
├── etc/oncall.env.example                 # secret: routing key / webhook / heartbeat URL
└── INSTALL.md                             # operator checklist (path returned as installChecklist.path)
backend/
├── autonomous_ops/selfheal.py             # platform_health docs, ingest, silent evaluation, sweep loop
├── autonomous_ops/oncall.py               # outbox enqueue/claim/ack
├── autonomous_ops/messages.py             # + platform-health event templates (copy test scans it)
├── watchdog_ingest_endpoints.py           # token-auth routes (required router, see Pitfall 17)
├── retention_job.py                       # type registry, gate, count, bounded delete, run, confirm
├── retention_service.py / retention_endpoints.py   # remove audit deletion, gate-aware manual run, /stats
└── migrations/025_platform_health.py      # indexes for new collections
components/AutonomousOpsPlatformHealth.tsx, AutonomousOpsRetentionReview.tsx, AutonomousOpsHealthBanners.tsx  # per 82-UI-SPEC
```

### Pattern 1: Polkit rule for exactly four unit names (verified harness)
**What:** `org.freedesktop.systemd1.manage-units` carries `unit` and `verb` details; match on both plus `subject.user`. Rules are **ECMA-262 edition 5** (no `let`, `const`, arrow functions, template strings) [CITED: freedesktop.org polkit.8]; this VM's polkit 124 runs Duktape [VERIFIED: `dpkg -l` shows `libduktape207`]. Verbs for unit actions come from systemd: `restart`, `start`, `reset-failed` (and `kill`, `set-property`, ...) [CITED: systemd v255 `src/core/dbus-unit.c`]. A rule that calls a string method on a missing `action.lookup()` value throws a TypeError and polkit denies silently [CITED: web search summary of Arch forum report], so type-guard first.
**When to use:** the shipped `49-omni-watchdog.rules`; install to `/etc/polkit-1/rules.d/` (dir is `root:polkitd 0750` [VERIFIED: `ls -ld`]); polkit auto-reloads on file change [CITED: polkit.8].
**Example (tested this session with a node stub harness: 8/8 cases passed, no ES6 syntax):**
```javascript
// Source: written for this phase; behaviour of manage-units details per systemd dbus-unit.c
polkit.addRule(function(action, subject) {
    var UNITS = ["mongod.service", "omni-backend.service", "nginx.service"];
    var VERBS = ["restart", "start", "reset-failed"];
    if (subject.user !== "omni-watchdog") { return polkit.Result.NOT_HANDLED; }
    if (action.id.indexOf("org.freedesktop.systemd1.") !== 0) { return polkit.Result.NOT_HANDLED; }
    if (action.id === "org.freedesktop.systemd1.manage-units") {
        var unit = action.lookup("unit");
        var verb = action.lookup("verb");
        if (typeof unit === "string" && typeof verb === "string" &&
            UNITS.indexOf(unit) !== -1 && VERBS.indexOf(verb) !== -1) {
            return polkit.Result.YES;
        }
    }
    return polkit.Result.NO;     // every other systemd1 action for this user is denied outright
});
```
Ollama: not installed here, so leave `ollama.service` out of `UNITS` by default and document the one-line addition in `INSTALL.md` for servers where it is expected (D-12 allows it "where expected").
**Test without installing:** (1) `node` harness that evaluates the file with a stub `polkit` object and asserts the 8 cases above (yes for the three units x allowed verbs, no for `ssh.service`, `stop`, missing details, `manage-unit-files`; `null` for other users/actions); (2) a grep-lint that the file contains none of `=>`, `let `, `const `, backticks. (3) Post-install, non-destructive: `sudo -u omni-watchdog bash -c 'pkcheck --action-id org.freedesktop.systemd1.manage-units --details unit nginx.service --details verb restart --process $$; echo $?'` must print 0, and the same with `ssh.service` must be non-zero (`pkcheck` flags verified via `pkcheck --help`: `-a`, `-d KEY VALUE`, `-p PID`). The exact unit string (`nginx.service`, with suffix) is [ASSUMED] until that pkcheck runs.

### Pattern 2: Timer + oneshot with a hard run cap
**What:** `Type=oneshot` ignores `RuntimeMaxSec=` (verified: `systemd-analyze verify` printed "RuntimeMaxSec= has no effect in combination with Type=oneshot. Ignoring."), so cap the run with `TimeoutStartSec=45`. Use `OnBootSec=60` + `OnUnitActiveSec=60` (start-to-start cadence), `AccuracySec=5s`.
```ini
# omni-watchdog.service  (hardening scored by: systemd-analyze security --offline=true)
[Unit]
Description=Omni-Agent AI platform watchdog (one check run)
[Service]
Type=oneshot
User=omni-watchdog
Group=omni-watchdog
ExecStart=/usr/bin/python3 -I /usr/local/lib/omni-watchdog/omni-watchdog.py
TimeoutStartSec=45
StateDirectory=omni-watchdog
StateDirectoryMode=0750
ConfigurationDirectory=omni-watchdog
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
CapabilityBoundingSet=
UMask=0077
```
`ConfigurationDirectory=` would create `/etc/omni-watchdog` as root-owned `0755`; the checklist then sets `root:omni-watchdog 0750` and `oncall.env` `0640` so the watchdog user can read but never write config. [ASSUMED] `ProtectSystem=strict` does not stop `systemctl` reaching the system bus (a read-only mount does not block `connect()`); verify with the first live run (`journalctl -u omni-watchdog`).

### Pattern 3: One sync round trip (the contract to freeze in plan 1)
`POST http://127.0.0.1:5000/api/internal/watchdog/sync` with `Authorization: Bearer <token>`.
```json
{ "v": 1, "host": "omni", "sentAt": "ISO",
  "services": {"mongod": {"state": "healthy|checking|down|restarting|gave_up|expected_off|unexpected_running",
                          "since": "ISO", "failedChecks": 0, "restartsInWindow": 0, "nextRestartAt": null,
                          "budgetReturnsAt": null, "pagedAt": null, "waitingOn": null, "detail": "" }},
  "certs": [{"path": "/etc/nginx/ssl/omni.crt", "notAfter": "ISO", "daysLeft": 811, "rung": 0, "pinned": true, "error": null}],
  "disks": [{"mount": "/", "paths": ["/", "/var/lib/mongodb"], "usedPct": 69.0, "freeBytes": 0, "totalBytes": 0, "rung": 0,
             "forecast": {"state": "ok|flat|insufficient", "days": null, "rung": 0}}],
  "oncall": {"type": "pagerduty|webhook|none", "heartbeatConfigured": true, "last": {"at": "ISO", "ok": true, "error": null, "kind": "page|resolve|test"}},
  "stop": {"effective": false, "source": "database|cache|file|none"},
  "events": [{"id": "hex32", "at": "ISO", "kind": "service_down", "severity": "critical", "target": "mongod", "params": {}}],
  "delivered": [{"id": "outbox-id", "ok": true, "error": null, "at": "ISO"}] }
```
Response: `{"stop": {"active": true, "scope": "platform", "pressedAt": "ISO"}, "acceptedEventIds": [...], "outbox": [{"id","kind":"trigger|resolve","dedupKey","severity","summary","details"}], "testRequest": {"id","requestedAt"} | null}`. After executing tasks the watchdog calls `POST .../results` immediately (`delivered[]`, `testResult`) so the panel updates within one run instead of two (UI-SPEC expects "about a minute", times out at 90 s). If that second call fails, the result rides the next sync.
Rules: event `id` is generated once by the watchdog and persisted in the spool before sending, so re-sends are idempotent (unique `id` index on the ledger row, duplicate key = already ingested). Event `kind` is a closed enum; unknown kinds are dropped with a counter, never stored. The watchdog sends structured fields only; the backend renders user-visible text from `messages.py` (keeps the ACTV-08 copy test meaningful and stops a compromised watchdog injecting arbitrary text). Per-string length caps (error text 300 characters, as UI-SPEC), at most 50 events per call, request body cap.

### Pattern 4: Restart state machine (pure function, unit-tested with injected `now`)
Per service: `failedChecks`, `state`, `downSince`, `restarts[]` (epoch seconds within 30 min), `nextActionAt`, `healthySince`, `pagedAt`.
- check ok: `failedChecks=0`; if `state in (checking,down,restarting)` -> `healthy` + "recovered" event; `healthySince` set on first ok; if `now - healthySince >= 3600` and `state == gave_up` or `restarts` non-empty -> clear budget, emit "budget re-armed" (D-08). A gave-up service that is still down stays given up.
- check fails: `failedChecks += 1`; at 1 -> `checking`; at >= 2 -> `down` (D-06).
- `down` and restart allowed (not stopped, dependency healthy, `now >= nextActionAt`, `len(restarts in last 30 min) < 3`) -> restart now, append timestamp, set `nextActionAt = now + wait[k]` with `wait = [1, 2, 4]` minutes for k = 1, 2, 3 (the wait is the time given for the restart to take effect before judging it).
- after restart 3 and `nextActionAt` passed and still failing -> `gave_up`, emit exactly one page incident, `pagedAt = now`; no further restarts until re-arm.
- Stopped: emit "restart skipped" once per episode, do not touch the counters, keep checking and paging.
- MongoDB first (D-09): evaluate `mongod` before `omni-backend`; if `mongod` is not healthy this run, mark backend `waitingOn: "mongod"` and skip its restart (its failures do not consume budget while blocked). After a successful MongoDB restart, restart the backend if `/api/health/ready` is still not 200 (see Pitfall 1).
- Use `systemctl restart --no-block <unit>` (returns immediately; polkit still checks) and poll health up to ~20 s inside the run, so a 90 s `mongod` stop never overruns `TimeoutStartSec`.
- Optional (milestone STACK.md, not in CONTEXT): skip a `mongod` restart while `omni-backup.service` is active, capped at 30 minutes. Backup runs 02:30 UTC +0-15 min [VERIFIED: omni-backup.timer `OnCalendar=*-*-* 02:30:00 UTC`, `RandomizedDelaySec=15min`].

### Pattern 5: Incidents, rungs and grouped pages
One incident = stable key `check[:subject][:rung]` (e.g. `svc:mongod`, `cert:/etc/nginx/ssl/omni.crt:14d`, `disk:/:90`, `forecast:/:7d`). State in `state.json` `incidents`. On a new run: collect newly opened incidents; if more than one, send **one** grouped trigger whose `dedup_key` is the group's highest-severity member key and map each member's `page_key` to it; send the matching `resolve` only when every member sharing that `page_key` has cleared (D-03). When a ladder check moves to a higher rung, send `resolve` for the old key then `trigger` for the new key (one open incident per check). Disk and forecast clear with hysteresis (clear 2 points / 20% below the threshold) to avoid flapping. PagerDuty facts [CITED: docs.pagerduty.com/developer/send-alert-event]: endpoint `https://events.pagerduty.com/v2/enqueue`; trigger needs `routing_key`, `event_action`, `payload.summary` (max 1024), `payload.source`, `payload.severity` in `critical|error|warning|info`; `dedup_key` max 255; a trigger with a matching open `dedup_key` is applied to that alert, a matching resolved one creates a new alert; resolve needs the same routing key or it is dropped; resolve with no open match is dropped. Retry 429/5xx with backoff (STACK.md; response-code page not read this session, [CITED: .planning/research/STACK.md]); never retry 400. Severity mapping (Claude's-discretion default, matches UI ladder): cert 30d/14d and disk 80% and forecast 14d = `info`; cert 7d, disk 90%, forecast 7d = `warning`; cert 1d/expired, disk 95%, forecast 1d, service gave up = `critical`.
**Test alert** = `trigger` (severity `info`, `dedup_key omni:<host>:test:<requestId>`) immediately followed by `resolve`, so it does not leave an open incident.

### Pattern 6: Retention gate (pure function + stored `confirmedDays`)
New collections: `retention_gate` (one doc per `(tenantId, type)`: `confirmedDays` int or null), `retention_gate_global` (single doc: `confirmedAt`), `retention_counts` (latest count per `(tenantId, type)`: `days`, `count`, `countedAt`, `error`), `retention_job_runs` (summary per run).
```python
def gate_state(policy_days, confirmed_days, global_confirmed):
    """'confirmed' deletes; anything else only counts."""
    if confirmed_days is None:
        # first sight: adopt silently only AFTER the one global confirmation (D-18); before it, count only
        return "confirmed_adopt" if global_confirmed else "first_run"
    return "shortened" if policy_days < confirmed_days else "confirmed"   # lengthening needs no confirmation (D-19)
```
After a run deletes for a `confirmed`/`adopt` row, set `confirmedDays = policy_days` (so a later shorten compares against the lengthened value). Detecting "shortened" by comparison at run time needs no hook on `retention_policies` writes and also covers the second writer of that collection (`retention_tiers_endpoints.py` writes the same collection with a different doc shape [VERIFIED: grep] - always filter by `collection in RETENTION_TYPES`).
**Confirm:** `POST /api/platform/autonomous-ops/retention/confirm {reviewToken}`. `reviewToken = sha256` over the sorted waiting rows `tenant|type|policyDays|count|countedAt`; mismatch with the current waiting set -> `409` (UI-SPEC stale guard); on match set `confirmedDays` for exactly the counted rows (skip rows whose policy days changed since counting, skip rows with a failed count) and set the global flag. Record a platform-health Activity row `retention_confirmed` naming the person.
**Type registry** (collection, tenant field, time field/kind, default days) - the single source for count, delete, UI labels and `/policies` gate flags:

| Type id | Collection | Tenant field | Time field (kind) | Default days |
|---|---|---|---|---|
| `metrics` | `metrics` | `tenantId` [ASSUMED: collection does not exist on this DB] | `timestamp` (ISO string) | 30 |
| `notifications` | `notifications` | `tenantId` | `sent_at` (ISO string) | 30 |
| `agent_location_history` | `agent_location_history` | `tenantId` | `timestamp` (BSON date) | 365 |
| `agent_uptime_rollups` | `agent_uptime_rollups` | `tenant_id` (stored field, verified in a live document) | `timestamp` (BSON date) | 90 |
| `agent_metrics` | same | `tenant_id` | ObjectId creation time | 30 |
| `asset_metrics` | same | `tenant_id` | ObjectId creation time | 30 |
| `persistence_results` | same | `tenantId` | ObjectId creation time | 90 |
| `logs` | same | `tenantId` | ObjectId creation time | 30 |

(Last four exactly as `AGENT_TELEMETRY` at `backend/retention_service.py:8-13`: `"agent_metrics": ("tenant_id", 30)`, `"persistence_results": ("tenantId", 90)`; others read in the same dict. The first four rows' fields were read in `retention_service.py` (cleanup methods), `app_background_tasks.py` (`"tenant_id": tid` in the uptime rollup `$set`), `agent_location_history_service.py` (`"tenantId": tenant_id`), and a live `notifications` document (`tenantId`, `sent_at`).)
**Bounded delete (all types):** loop `ids = find(filter, {_id:1}).sort(_id,1).limit(BATCH)` -> `delete_many({_id: {$in: ids}})` -> `await asyncio.sleep(PAUSE)`; stop on lock lost, wall-clock cap, or empty batch. Recommended defaults `BATCH=500`, `PAUSE=0.5 s`, run cap 60 min, env-overridable [ASSUMED values; measure with the latency test]. Counting uses `count_documents(..., maxTimeMS=30000)`; a failure records `error` on that row ("Couldn't count" in the UI), and that row is excluded from Confirm. Live shape for sizing: `agent_metrics` 121,176 docs, `asset_metrics` 104,892, `logs` 15,570, `persistence_results` 318, `notifications` 11, `agent_uptime_rollups` 49, `agent_location_history` 0, `metrics` collection absent, `audit_logs` 813 [VERIFIED: read-only mongosh counts]; the four telemetry collections have only the `_id` index [VERIFIED: getIndexes], so the `{tenant_field: t, _id: {$lt: cutoff}}` filter is an `_id`-range scan (acceptable at this size; do not add indexes in this phase).
**Scheduling:** a loop (not an in-memory APScheduler cron) with **catch-up**: every 5 minutes, `if now >= today 02:00 UTC and last_scheduled_run_date < today: run` under `distributed_lock.lock_with_renewal` (pattern at `backend/autonomous_ops/reconciler.py:34-35,157`: `LOCK_NAME`, `LOCK_TTL_SECONDS = 120`, `lock_with_renewal(...)`). A cron job in APScheduler's memory store loses a run when the backend (restarted by the watchdog!) is down at 02:00. Retention is not an autonomous action, so the platform stop does not pause it. `next_scheduled` = next 02:00 UTC (pure function) for `/stats` (currently `"next_scheduled": None` at `retention_endpoints.py:110`) and the panel. Register the new loop where `agent_telemetry_retention_loop` is registered (`app_startup.py:523`) and delete that loop (`app_background_tasks.py:367`) and its import (`app_startup.py:515`).

### Anti-Patterns to Avoid
- **Running the watchdog script from the repo checkout:** the checkout is owned by `azureuser` (the backend's user); anything it can edit would run with restart rights. Install a root-owned copy.
- **Having `start-all-services.sh` install the watchdog, polkit rule or user:** violates HEAL-08 ("the app installs nothing") and the script is routinely re-run; ARCHITECTURE.md's note to generate `omni-watchdog.service` there is superseded.
- **Storing watchdog rows as `kind: "control"` with `scope: "platform"`:** that is precisely the shape the tenant query includes (`views.py` list_page `{"tenantId": PLATFORM_TENANT_ID, "kind": "control", "scope": "platform"}`).
- **Hooking `update_policy` to detect shortening:** misses the other writer and direct DB edits; compare at run time.
- **`cleanup_audit_logs`/anything touching `audit_logs` in the new job:** the ledger chain breaks (milestone PITFALLS 16).
- **A shell in the watchdog's subprocess calls:** pass argument lists; unit names come from a constant, never from config or HTTP responses.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cert expiry parsing | DER/ASN.1 parser | `openssl x509 -noout -enddate -in FILE` with `LC_ALL=C`, then `ssl.cert_time_to_seconds()` | Verified live: output `notAfter=Jan 15 15:06:12 2029 GMT` -> 811.6 days; `cert_time_to_seconds` is locale-independent, `strptime("%b")` is not |
| Disk percent | `shutil.disk_usage` math | `os.statvfs` with `df` semantics: `used = f_blocks - f_bfree`, `pct = used / (used + f_bavail)` | Matches `df` (247G, 170G, 69% observed) and honours root-reserved blocks |
| Distributed one-runner lock | new lock | `distributed_lock.lock_with_renewal` | Already hardened in Phase 81 |
| Spool-and-replay | new format | NDJSON idiom of `audit_ledger.replay_spool` (idempotent by id) | `backend/audit_ledger.py:209` |
| PagerDuty/webhook senders in the backend | reuse `PagerDutyConnector` | A stdlib re-implementation inside the watchdog | The watchdog must not import the backend (D-01, CONTEXT code_context) |
| MongoDB driver in the watchdog | pymongo vendoring | 40-line `OP_MSG` `ping` (verified) used only for health | The watchdog never reads or writes data in MongoDB |
| Atomic state writes | in-place writes | write temp + `os.replace` (+ `fsync`) | A kill mid-write must not lose the restart budget |
| Concurrency guard | PID files | `fcntl.flock` on `state.lock` | Manual `--once` runs while the timer fires |
| Review integrity | session state | `reviewToken` hash of the waiting rows | Stateless 409 guard |

**Key insight:** the dangerous parts of this phase are privilege and deletion, both of which have exact standard tools (polkit rule scoped by unit+verb, bounded `_id` batches with a stored gate). Custom escalation paths (sudoers wildcards, shelling out to `mongosh`, ad-hoc `delete_many` over a date) are where regressions come from.

## Runtime State Inventory

> Not a rename/refactor phase; one real migration-like consequence is recorded instead.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `agent_telemetry_retention_loop` (daily, immediate deletes) is replaced by a gated job: until the first Super Admin confirmation, telemetry on this DB (121k `agent_metrics`, 105k `asset_metrics`) is no longer purged (D-15 consequence). New collections `platform_health`, `oncall_outbox`, `retention_gate`, `retention_gate_global`, `retention_counts`, `retention_job_runs` need indexes (migration 025; 024 is the latest, `backend/migrations/024_autonomous_ops.py`). | Code + migration; checklist step "confirm the first count soon after deploy" |
| Live service config | None changed by the app. Operator installs: user, units, polkit rule, `/etc/omni-watchdog/*`, drop-ins. | Documented in `INSTALL.md`; live-only |
| OS-registered state | None before install (`/etc/omni-watchdog`, `/var/lib/omni-watchdog`, user `omni-watchdog` do not exist [VERIFIED: ls / getent]). | none by the app |
| Secrets/env vars | New secret files: `/etc/omni-watchdog/oncall.env` (PagerDuty key/webhook/heartbeat URL) and `/etc/omni-watchdog/ingest.token`. Backend receives the token via `LoadCredential=` (never `oncall.env`). | Operator creates; backend refuses sync (503) while the credential is absent |
| Build artifacts | None (no packages). Existing `mongod.service.d/kernel-rseq-check.conf` must survive: new drop-ins use new file names only. | Checklist asserts the existing drop-in is untouched |

## Common Pitfalls

### Pitfall 1: Backend stays "not ready" after MongoDB comes back (demo-mode lock-in)
**What goes wrong:** `/api/health/ready` returns 503 when `db_status != "ok"` **or** `is_demo_mode()` (`backend/app.py:111-135`). A backend that started while MongoDB was down is in demo mode and stays there.
**How to avoid:** order MongoDB first, then if `/api/health/ready` is still failing after MongoDB is healthy, count the backend as down and restart it (that is within budget and the intended D-09 behaviour). Test: fake backend returning 503 forever after a simulated Mongo recovery.
**Warning signs:** repeated 503 `demo_mode: true` bodies.

### Pitfall 2: Dead-man false alarm right after a backend restart
**What goes wrong:** the backend sees `lastSeenAt` stale for as long as it was down.
**How to avoid:** evaluate silence only when `now - process_started_at > 180 s` and `now - lastSeenAt > 300 s` (A11); the `health` summary uses the same function so banner and notification agree.

### Pitfall 3: Platform-health rows leak to tenants / Platform Support
**What goes wrong:** `list_page` treats `tenant_id == "platform-admin"` as "own rows only", and the tenant router (`/api/autonomous-ops/actions?tenantId=platform-admin`) lets staff name that tenant (`_tenant_for` skips `require_tenant` for it).
**How to avoid:** `list_page(..., include_platform_health=False)` default adds `{"kind": {"$ne": "platform_health"}}`; only the platform route passes `True`. Add a test that Platform Support and a tenant admin calling the tenant router get zero such rows and that `counts` cannot reveal them. Add a separate `PlatformBucket = Bucket | "platform_health"` for the platform route only (`Bucket` is `Literal["all", "pending", ..., "simulation"]` at `autonomous_ops_endpoints.py:32`).

### Pitfall 4: `bucket_of` calls unknown rows "refused"
**What goes wrong:** `return _STATE_BUCKET.get(row.get("state"), "refused")` (`views.py:165`). A `platform_health` row would render as refused/denied.
**How to avoid:** map `row["kind"] == "platform_health"` to the new `"platform_health"` bucket before the state lookup; keep it out of `BUCKET_STATES` (`ledger.counts` iterates that dict) and add `counts.platform_health` via `count_documents({"tenantId": PLATFORM, "kind": "platform_health"})` on the platform first page.

### Pitfall 5: Existing uptime-rollup cleanup deletes the wrong rows
**What goes wrong:** rollups store `tenant_id`, while the tenant wrapper injects `tenantId`; `cleanup_agent_uptime_rollups` goes through `self.db` (wrapped) with a time-only filter.
**How to avoid:** use the type registry above through the raw handle with the stored field.

### Pitfall 6: `RuntimeMaxSec` silently ignored; run overlap
Use `TimeoutStartSec=45` + `flock`; never let a `systemctl restart` block (use `--no-block`).

### Pitfall 7: Locale-dependent date parsing, DST, clock jumps
Use `ssl.cert_time_to_seconds`; keep all timestamps as epoch seconds in `state.json`; ignore negative intervals larger than 5 minutes (clock step).

### Pitfall 8: Clobbering the existing MongoDB drop-in
`/etc/systemd/system/mongod.service.d/kernel-rseq-check.conf` sets `Environment="GLIBC_TUNABLES=glibc.pthread.rseq=1"` (MongoDB 8.0.34 / SERVER-121912). New drop-in is `50-omni-restart.conf`; the checklist runs `systemctl cat mongod` before and after and diffs. After any watchdog-triggered `mongod` restart the health check is the `OP_MSG` ping, not `is-active`.

### Pitfall 9: Watchdog script/config writable by the backend user
Install the script root-owned under `/usr/local/lib/omni-watchdog/`; `/etc/omni-watchdog` `root:omni-watchdog 0750`; state dir owned by `omni-watchdog` only (the backend must not be able to edit `state.json` and reset the budget).

### Pitfall 10: Shared status poller only fetches platform status in platform scope
`resolveAutonomousOpsScope` returns `tenant` for a Super Admin who entered a tenant, so `platformStatus` (carrying the new `health`) is not fetched and the health banners would vanish while viewing a tenant, contradicting UI-SPEC section 2. The provider must additionally fetch the platform status for holders of `control:platform_autonomous_ops` regardless of scope (still one poller, 30 s, `STATUS_POLL_MS`).

### Pitfall 11: Test alert leaves a PagerDuty incident open
Send `trigger` then `resolve` with the same `dedup_key` and routing key (resolve with a different routing key is dropped [CITED]).

### Pitfall 12: Disk percent does not fall after retention
WiredTiger reuses freed space internally and rarely returns it to the OS [ASSUMED]; do not promise the disk warning clears after a purge. The forecast/warnings stay honest; compaction is out of scope.

### Pitfall 13: Retention overlaps the nightly backup
Retention starts 02:00 UTC, `mongodump` backup 02:30-02:45 UTC. Cap the wall clock (60 min) and pause between batches; first run is count-only so the first real overlap is the first confirmed night.

### Pitfall 14: Shortening twice before confirming; lengthening not adopted
90 -> 60 -> 30 must still show "was 90 days"; a lengthen must raise `confirmedDays` or a later shorten from the new value would compare against the stale lower number (covered by the gate function above).

### Pitfall 15: State file corruption / duplicate pages
Atomic writes; on JSON decode failure rename the file to `state.json.bad-<ts>` and start empty (budget resets, but the first run re-detects reality; log an event). Persist `pagedAt`/incident keys *before* sending the page and mark `sent` after, so a crash leans to at-most-one duplicate PagerDuty trigger, which `dedup_key` collapses.

### Pitfall 16: Outbox redelivery after a lost acknowledgement
At-least-once: the watchdog remembers the last 500 delivered outbox ids in `state.json` and never re-sends them; PagerDuty `dedup_key = omni:<host>:<outbox id>` collapses any residual duplicate. Expire undelivered outbox messages after 24 h (TTL) so a channel set up next week does not page about last week.

### Pitfall 17: New routes trip the existing drift tests
`backend/tests/test_route_auth_baseline.py` fails on any route without a recognised guard that is not in `REVIEWED_UNAUTHENTICATED` (precedent entries include `("GET", "/api/agents/{agent_id}/instructions")` under "Credential checked inside the handler"). The token routes must be added there with that justification (or use a `_require_*` dependency the walker recognises - check `tests/_route_walk.py` `PERM_DEP` regex first). Also register the router in `_REQUIRED_ROUTERS` style only if its absence should fail startup (recommended: not required; the platform keeps running without the watchdog endpoint), and run `test_catalogue_route_parity` / `test_platform_role_routes`.

### Pitfall 18: ACTV-08 copy test only scans listed files
New component files and every new server message module must be added to the `files` array of `shared/autonomous-ops-banned-terms.json` AND to the hard-coded `EXPECTED_FILES` list in `backend/tests/test_autonomous_ops_copy.py` (it asserts the two agree) and the vitest copy test, in the same plan that creates the file.

## Code Examples

### Stdlib MongoDB health check (verified against the live mongod: reply opcode 2013, `ok` 1.0)
```python
# Source: probe run this session against 127.0.0.1:27017 (no auth); ping needs no auth on MongoDB >= 3.6.10 [CITED: jira.mongodb.org SERVER-38390]
import socket, struct
def _bson(items):
    body = b""
    for k, v in items:
        if isinstance(v, int):
            body += b"\x10" + k.encode() + b"\x00" + struct.pack("<i", v)
        else:
            s = v.encode() + b"\x00"
            body += b"\x02" + k.encode() + b"\x00" + struct.pack("<i", len(s)) + s
    return struct.pack("<i", len(body) + 5) + body + b"\x00"
def mongo_ping(host="127.0.0.1", port=27017, timeout=3.0) -> bool:
    msg = struct.pack("<I", 0) + b"\x00" + _bson([("ping", 1), ("$db", "admin")])
    hdr = struct.pack("<iiii", 16 + len(msg), 1, 0, 2013)           # OP_MSG
    with socket.create_connection((host, port), timeout) as s:
        s.settimeout(timeout); s.sendall(hdr + msg)
        resp = s.recv(4096)
    return len(resp) > 16 and struct.unpack("<i", resp[12:16])[0] == 2013   # any well-formed reply = server alive
```
Healthy = a well-formed `OP_MSG` reply (even `ok: 0 Unauthorized` once auth is enabled proves the server answers). Pair it with `systemctl is-active mongod`.

### Certificate expiry (verified live)
```python
import subprocess, ssl, time
def cert_days_left(path):
    out = subprocess.run(["openssl", "x509", "-noout", "-enddate", "-in", path], capture_output=True, text=True,
                         env={"LC_ALL": "C", "PATH": "/usr/bin"}, timeout=5, check=True).stdout.strip()
    return (ssl.cert_time_to_seconds(out.split("=", 1)[1]) - time.time()) / 86400.0   # 811.6 on /etc/nginx/ssl/omni.crt
```

### Disk percent with `df` semantics + 7-day slope
```python
import os
def disk(path):
    s = os.statvfs(path); used = (s.f_blocks - s.f_bfree) * s.f_frsize; avail = s.f_bavail * s.f_frsize
    return used, avail, 100.0 * used / (used + avail)
# one sample/hour appended to state["disk"][mount] (keep 8 days); forecast needs >= 7 days of span:
# slope = least-squares bytes/s over the last 7 days; days_to_full = avail / slope if slope > 0 else None
```
Dedupe mounts by `os.stat(path).st_dev` so `/` and `/var/lib/mongodb` render as one entry listing both paths (UI-SPEC S4 zero-one-many).

### Retention bounded delete + gate loop (shape)
```python
async def delete_old(coll, flt, lost, batch=500, pause=0.5, deadline=None):
    total = 0
    while not lost() and (deadline is None or time.monotonic() < deadline):
        ids = [d["_id"] async for d in coll.find(flt, {"_id": 1}).sort("_id", 1).limit(batch)]
        if not ids:
            break
        total += (await coll.delete_many({"_id": {"$in": ids}})).deleted_count
        await asyncio.sleep(pause)
    return total
```

### Backend token check (loopback + no proxy headers)
```python
async def _require_watchdog(request: Request):
    token = _load_credential()                        # os.environ["CREDENTIALS_DIRECTORY"]/omni-watchdog-token; None -> 503
    sent = request.headers.get("authorization", "")
    if request.client is None or request.client.host not in ("127.0.0.1", "::1") \
       or any(h in request.headers for h in ("x-forwarded-for", "x-real-ip", "forwarded")):
        raise HTTPException(403)
    if not token or not hmac.compare_digest(sent.encode(), f"Bearer {token}".encode()):
        raise HTTPException(401)
```
nginx always sets `X-Forwarded-For`/`X-Real-IP` on `/api` [VERIFIED: `/etc/nginx/sites-enabled/omni-platform` `location /api`], so the endpoint is unreachable through nginx even though uvicorn listens on `0.0.0.0:5000` [VERIFIED: `ss -ltnp`].

### Backend drop-in delivering the token without giving `azureuser` the file
```ini
# omni-backend.service.d/10-omni-watchdog.conf   (LoadCredential= accepted by systemd 255: systemd-analyze verify clean)
[Service]
LoadCredential=omni-watchdog-token:/etc/omni-watchdog/ingest.token
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Root watchdog (milestone ARCHITECTURE Pattern 6) | Dedicated `omni-watchdog` user + polkit unit/verb rule | CONTEXT D-12, 2026-10-27 | Smaller blast radius; script must be root-owned |
| Watchdog uses pymongo + env credentials (STACK.md) | Token endpoint, no MongoDB credentials in the watchdog | this research | MongoDB auth can be enabled later with no watchdog change |
| Events tailed from NDJSON by backend (ARCHITECTURE) | Push on every run + local spool only while backend is down | this research | Enables stop/outbox/test delivery in the same round trip |

**Deprecated/outdated:** `sd_notify` `WatchdogSec=` for the backend is out of this phase's scope (HEAL requirements do not name it); do not add it.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | D-07's "waiting 1, then 2, then 4 minutes between attempts" means: restart 1 at down-detection, then 1 min until restart 2, 2 min until restart 3, 4 min after restart 3 before declaring gave-up (about 9 min after detection, page once) | Pattern 4 | Different timing; user may have meant waits before each attempt. Confirm in discuss/plan-check. |
| A2 | MongoDB `ping` stays answerable without authentication on 8.0 once auth is enabled (cited only for >= 3.6.10) | Code Examples | Health check would read "down" after MongoDB auth is turned on; mitigated by treating any well-formed reply (even Unauthorized) as alive; confirm when auth is enabled |
| A3 | polkit passes `unit` as the full name with suffix (`nginx.service`) | Pattern 1 | Rule never matches, restarts denied; caught by the post-install `pkcheck` step |
| A4 | `ProtectSystem=strict` + `PrivateTmp` do not block `systemctl` talking to the system bus | Pattern 2 | Watchdog cannot restart; first live run shows it; relax hardening |
| A5 | Retention batch size 500, pause 0.5 s, 60-minute cap are safe on 2 vCPU | Pattern 6 | Latency spike or run never finishes; measure in the latency test |
| A6 | `metrics` collection uses `tenantId` and ISO-string `timestamp` (collection absent on this DB) | Pattern 6 table | Job counts 0 or deletes nothing for that type; harmless but verify |
| A7 | Notices from Phase 81 (stop, breaker, rate limit) should be PagerDuty `trigger` events at `warning`/`info` with no auto-resolve | Pattern 5 | Operators must resolve manually; alternative is Change Events (not researched) |
| A8 | Skipping a `mongod` restart while `omni-backup.service` is active (capped 30 min) is wanted | Pattern 4 | Delays recovery during backup if wanted off; it comes from milestone STACK.md, not CONTEXT |
| A9 | WiredTiger rarely returns freed disk to the OS after deletes | Pitfall 12 | Messaging only |
| A10 | 5-minute silence threshold and 3-minute post-start grace for the dead-man | Pitfall 2 | Late/early alarm; UI-SPEC defers the value to the backend |
| A11 | Outbound HTTPS to `events.pagerduty.com` / the webhook host is allowed from the VM | Pattern 5 | Pages never arrive; the test alert is the check |
| A12 | New (tenant, type) rows seen after the global confirmation are adopted silently (`confirmedDays = policy days`) | Pattern 6 | A new tenant's first-night deletes are unreviewed (it has no old data); alternative is count-only for them |
| A13 | `POST /api/retention/policies/audit_logs` should now be refused (409) since it no longer drives deletion | Open Questions | Existing callers/compliance checks that write it would fail |
| A14 | Hourly disk samples and a 7-day least-squares slope are acceptable for the forecast | Pattern 5 / Code | Noisy forecast around nightly backups; revisit with real data |

## Open Questions

1. **Timing of the 1/2/4-minute waits (A1).** Recommendation: adopt the reading in Pattern 4 and put the exact timeline in the plan's acceptance criteria so the user can veto it at plan-check.
2. **"Count now" for the first review.** Without a button the first count appears at the next 02:00 UTC run (or when a tenant admin uses Run cleanup now). UI-SPEC defines no such button. Recommendation: keep the spec; the checklist tells the operator the first count lands the next night, or trigger one via the manual run by a Super Admin.
3. **PagerDuty noise from Phase 81 notices (A7).** Recommendation: ship as `warning`/`info` triggers; revisit if the operator finds it noisy.
4. **Refuse writes to the `audit_logs` policy (A13).** Recommendation: refuse with 409 and a clear message to match the UI; confirm that `frameworks/iso27001.py` (`"check_collection": "retention_policies"`) only checks the collection exists.
5. **Race on stop press then immediate backend crash.** A stop pressed less than a minute before the backend dies is not yet in the watchdog's cache, so one restart may happen while stopped. Accepted (restarting a service is not an autonomous action on tenants); an optional hardening is a backend-written world-readable stop mirror file, not recommended now.
6. **Install checklist URL.** `installChecklist.url` is `null` (the app serves no repo files); the UI renders the path text (UI-SPEC H8).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| systemd | timer, drop-ins, `LoadCredential=` | yes | 255 (255.4-1ubuntu8.18) | — |
| polkit (Duktape) | restart privilege | yes | 124-2ubuntu1.24.04.4 | sudoers (not recommended; D-12) |
| Python 3 | watchdog | yes | 3.12.3 | — |
| openssl, curl | cert check, operator checks | yes | `/usr/bin/openssl`, `/usr/bin/curl` | `ssl._ssl._test_decode_cert` (verified to work: returned `Jan 15 15:06:12 2029 GMT`, private API) |
| MongoDB | backend + ping | yes (`bindIp: 127.0.0.1`, no auth) | 8.0 | — |
| `mongosh` | operator diagnostics only | yes | — | not used at runtime |
| node | polkit rule test harness | yes | `/usr/bin/node` | — |
| `systemd-analyze` | unit lint tests | yes | 255 | — |
| nginx | check target | yes, TLS on :443 with `/etc/nginx/ssl/omni.crt` | — | — |
| Ollama | optional check | no (`ollama.service could not be found`) | — | expected-off registry; never started |
| user `omni-watchdog`, `/etc/omni-watchdog`, `/var/lib/omni-watchdog` | install | no | — | Operator creates (checklist) |
| Outbound HTTPS to PagerDuty/webhook | paging | unknown | — | Live-only verification via test alert |

**Missing dependencies with no fallback:** none block planning. The user/dirs/rule are operator install steps (live-only).
**Missing dependencies with fallback:** Ollama (expected off).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (`asyncio_mode = auto`) for backend and watchdog; vitest 5 for UI; node stub for the polkit rule |
| Config file | `/home/azureuser/enterprise-omni-agent-ai-platform/pytest.ini`; `vite.config.ts` (vitest) |
| Quick run command | `cd /home/azureuser/enterprise-omni-agent-ai-platform/backend && venv/bin/python -m pytest tests/test_watchdog_*.py tests/test_retention_job*.py tests/test_platform_health*.py -x -q` |
| Full suite command | `cd /home/azureuser/enterprise-omni-agent-ai-platform && npm test && (cd backend && venv/bin/python -m pytest tests/ -q)` |

Real-Mongo fixture: `tests/_mongo_test_db.py` (`mongo_db`, throwaway `omni_test_*` database, skips when MongoDB unreachable; it is reachable on this VM). HTTP fixtures: `tests/_autonomous_ops_http.py` (`Api` class mounting the Phase 81 routers with identity chosen per request). Seed helpers: `tests/autonomy_support.py` (`seed_tenant`, `seed_platform_stop`). `conftest.py` pins a throwaway DB name and a throwaway audit spool.

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HEAL-01 | checks via fakes: Mongo `OP_MSG` ping against a local fake server; backend ready/503/demo; nginx TLS reply; Ollama expected-off never started; Mongo restarted before backend; backend still 503 after Mongo recovery -> restarted | unit (injected `run`/`now`/http) | `pytest tests/test_watchdog_checks.py tests/test_watchdog_restart.py -x` | no, Wave 0 |
| HEAL-02 | 2-fail debounce, 3 restarts/30 min, 1/2/4 waits, gave-up pages exactly once, re-arm after 1 h healthy, stopped = skipped (counters untouched), STOP file / cached stop / database stop precedence | unit, table-driven over time | `pytest tests/test_watchdog_restart.py -x` | no, Wave 0 |
| HEAL-03 | cert rungs at 30/14/7/1 days and expired from a generated test cert (openssl in tmp dir); disk rungs 80/90/95 with hysteresis via injected `statvfs`; "never deletes/renews" = structural grep | unit + structural | `pytest tests/test_watchdog_warnings.py -x` | no, Wave 0 |
| HEAL-04 | forecast: <7 days history -> insufficient; flat -> flat; growth -> days; 14/7/1 rungs | unit | `pytest tests/test_watchdog_warnings.py::test_forecast -x` | no, Wave 0 |
| HEAL-05 | PagerDuty/webhook payload shapes against a local fake HTTP server (dedup_key, resolve, severity map, retries only on 429/5xx, grouped page, test = trigger+resolve); outbox enqueue from `notify`; ack; dead-man: silent after 300 s only after first heartbeat, grace after backend start; `health` summary values; no secret in any API response | unit + real-Mongo + HTTP | `pytest tests/test_watchdog_oncall.py tests/test_platform_health_sync.py tests/test_platform_health_status.py -x` | no, Wave 0 |
| HEAL-06 | gate function table; first run counts only; confirm deletes next run; shortened -> back to count-only for that tenant+type only; lengthen adopts; 409 on changed review token; audit_logs/`autonomy_actions` untouched incl. after manual run; batches bounded (seed N, assert batch sizes and pauses called); API latency stays under budget during a run | unit + real-Mongo | `pytest tests/test_retention_job.py tests/test_retention_gate.py tests/test_retention_endpoints_phase82.py -x` | no, Wave 0 |
| HEAL-07 | ingest creates `kind: "platform_health"` rows idempotently; Super Admin platform list shows them with `counts.platform_health`; tenant admin and Platform Support (including `tenantId=platform-admin`) see none; bucket mapping | real-Mongo + HTTP | `pytest tests/test_platform_health_activity.py -x` | no, Wave 0 |
| HEAL-08 | units pass `systemd-analyze verify`; no `RuntimeMaxSec` with oneshot; polkit rule node harness 8/8 + ES5 lint; drop-ins have new file names only; `INSTALL.md` exists and names every file; no backend module under the new paths calls `systemctl`/writes `/etc`; `start-all-services.sh` does not reference the watchdog | structural/unit | `pytest tests/test_watchdog_artifacts.py -x` | no, Wave 0 |
| UI (D-20..D-26) | banners (priority, arming, scope), section states, test-alert state machine, review table/confirm dialog/409, Activity pill + client-side drop outside platform scope, tenant retention notices, copy test file list | vitest | `npx vitest run src/__tests__/AutonomousOpsPlatformHealth.test.tsx src/__tests__/AutonomousOpsRetentionReview.test.tsx src/__tests__/AutonomousOpsHealthBanners.test.tsx src/__tests__/autonomousOpsCopy.test.ts` | no, Wave 0 (copy test exists) |
| Drift | route auth baseline, catalogue parity, ACTV-08 file lists | existing | `pytest tests/test_route_auth_baseline.py tests/test_catalogue_route_parity.py tests/test_autonomous_ops_copy.py -x` | yes |

### Sampling Rate
- **Per task commit:** the targeted test file(s) for the module touched (each < 30 s).
- **Per wave merge:** the quick run command plus the three drift tests above.
- **Phase gate:** full backend suite and `npm test` green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `backend/tests/test_watchdog_*.py` (checks, restart, warnings, oncall, artifacts) importing `deploy/omni-watchdog/omni-watchdog.py` through `importlib.util.spec_from_file_location` (hyphen in the file name); fake `systemctl` runner, fake clock, local `http.server` fakes for backend/PagerDuty/webhook, a socket fake for the Mongo ping
- [ ] `backend/tests/test_platform_health_*.py`, `test_retention_job.py`, `test_retention_gate.py`, `test_retention_endpoints_phase82.py` using `mongo_db` and the `Api` helper
- [ ] `src/__tests__/AutonomousOpsPlatformHealth.test.tsx`, `AutonomousOpsRetentionReview.test.tsx`, `AutonomousOpsHealthBanners.test.tsx`
- [ ] `backend/tests/polkit_rule_harness.js` (the verified stub harness) and the ES5 lint
- [ ] Add every new file to `shared/autonomous-ops-banned-terms.json` `files` and to `EXPECTED_FILES` in `test_autonomous_ops_copy.py` and the vitest copy test
- [ ] Add the token routes to `REVIEWED_UNAUTHENTICATED` in `test_route_auth_baseline.py` with the "credential checked inside the handler" comment
- [ ] Migration 025 test following `test_autonomous_ops_migration.py`

**Live-only (cannot be automated here):** creating the user and installing units/rule/drop-ins; real stop/start of MongoDB and the backend; real PagerDuty/webhook delivery and the external heartbeat; confirming the first retention count; the post-install `pkcheck` checks; observing a watchdog-triggered `mongod` restart keeps the `GLIBC_TUNABLES` drop-in effective.

## Security Domain

### Applicable ASVS Categories (level 1 per `.planning/config.json` `security_asvs_level`)

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (watchdog -> backend) | static bearer token from a systemd credential, `hmac.compare_digest`, loopback-only, rejects `X-Forwarded-*`; super-admin routes keep `_require_platform_autonomy_control` + `_require_interactive_session` |
| V3 Session Management | no new sessions | existing |
| V4 Access Control | yes | `control:platform_autonomous_ops` on every panel route; polkit unit+verb allowlist; platform-health rows excluded by default query |
| V5 Input Validation | yes | pydantic models with closed enums, string caps (300), event count cap (50), body size cap on `sync`; watchdog treats all HTTP responses as untrusted (unit names are constants) |
| V6 Cryptography | yes (minimal) | TLS verification on for PagerDuty/webhook (default `ssl` context); `hmac.compare_digest`; no custom crypto; the nginx probe uses an unverified context to `127.0.0.1` only because it checks liveness, not identity |
| V7 Logging | yes | never log routing key, webhook URL, heartbeat URL or token; ledger rows never carry them |
| V12 Files | yes | root-owned script; `0640 root:omni-watchdog` secrets; state dir private to the watchdog; atomic writes; no symlink-following writes in a directory the backend can write |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Compromised backend (`azureuser`) widens the watchdog's power | Elevation of privilege | Root-owned script and config, polkit unit+verb rule, dedicated user |
| Forged heartbeat/events from the network | Spoofing | token + loopback + no proxy headers; port 5000 is open on `0.0.0.0` today, so the token is the control |
| Watchdog event text injection into the Activity UI | Tampering | closed event enum, backend renders text from `messages.py`, React text rendering |
| On-call key disclosure to browser/logs/API | Information disclosure | key only in `oncall.env`; API exposes `type` and booleans only; test asserts no key field in any response |
| Platform internals visible to tenants | Information disclosure | server-side default filter + client second guard (Pitfall 3) |
| Retention deletes evidence | Tampering / repudiation | type registry excludes `audit_logs`, `autonomy_*`; structural test; count-only gate |
| Stale confirmation approves a bigger deletion | Tampering | `reviewToken` 409 guard, required checkbox in UI |
| Restart loop / alert storm | DoS | budget, debounce, grouped pages, dedup keys |
| Command injection through config/response values | Tampering | `subprocess` with argument lists and constant unit names; no `shell=True` |

## Sources

### Primary (HIGH confidence)
- Repo files read this session: `backend/retention_service.py`, `backend/retention_endpoints.py`, `backend/app_background_tasks.py` (loops at 347, 367), `backend/app_startup.py` (508-523), `backend/distributed_lock.py`, `backend/autonomous_ops/{__init__,settings,stop,ledger,views,messages,notify,reconciler}.py`, `backend/autonomous_ops_platform_endpoints.py`, `backend/autonomous_ops_endpoints.py`, `backend/app.py` (health routes), `backend/scheduler.py`, `backend/router_registry.py`, `backend/migrations/024_autonomous_ops.py`, `backend/tests/{conftest,_autonomous_ops_http,autonomy_support,_mongo_test_db,test_route_auth_baseline,test_autonomous_ops_copy}.py`, `contexts/AutonomousOpsStatusContext.tsx`, `services/autonomousOpsApi.ts`, `shared/autonomous-ops-banned-terms.json`, `start-all-services.sh`, 82-CONTEXT/UI-SPEC, milestone research (SUMMARY/ARCHITECTURE/STACK/PITFALLS).
- Live host facts read-only: `/etc/systemd/system/{omni-backend.service,omni-backup.service,omni-backup.timer,mongod.service.d/*}`, `systemctl cat mongod nginx`, `/etc/mongod.conf`, `/etc/nginx/sites-enabled/omni-platform`, `/etc/nginx/ssl/omni.crt`, `/usr/share/polkit-1/actions/org.freedesktop.systemd1.policy`, `/etc/polkit-1/rules.d` permissions, `ss -ltnp`, `df`, read-only `mongosh` counts/indexes/sample documents.
- Experiments in `/tmp/claude-1000/-home-azureuser-enterprise-omni-agent-ai-platform/eb9ff284-6f67-4d57-b7b7-6a5c7d91fee0/scratchpad/` : `probe.py` (OP_MSG ping, cert parse), `49-omni-watchdog.rules` + `rule_harness.js` (8/8 pass), `units/` (`systemd-analyze verify` / `security`).

### Secondary (MEDIUM confidence)
- https://www.freedesktop.org/software/polkit/docs/latest/polkit.8.html (ECMA-262 ed. 5, rules dirs and order, auto-reload, `polkit.Result` values)
- https://raw.githubusercontent.com/systemd/systemd/v255/src/core/dbus-unit.c (unit-action verbs `restart`, `reset-failed`, ...)
- https://docs.pagerduty.com/developer/send-alert-event (Events v2 fields, `dedup_key` semantics, severity values, summary limit)
- MongoDB Jira SERVER-38390 / SERVER-12143 (unauthenticated `ping`) via web search summary

### Tertiary (LOW confidence)
- Arch forum / blog snippets about null `action.lookup` and exact unit names (web search summary only)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - stdlib/system tools probed on this VM; no new packages
- Architecture: HIGH for backend integration (code read); MEDIUM for polkit/systemd hardening interplay until the live install
- Pitfalls: HIGH for repo-derived ones (1-5, 10, 17, 18), MEDIUM for host-behaviour ones

**Research date:** 2026-10-27
**Valid until:** 2026-11-26 (stable domain; re-check if MongoDB auth is enabled or polkit/systemd are upgraded)
