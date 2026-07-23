# ETW Real-Time Telemetry Engine — Design

Status: **Proposed** · Target: `agent-rust` (Windows agent, service `OmniAgentRust`) · Author: platform/agent

## 1. Problem

The Windows agent is **poll-based**. Every detection capability (persistence, shadow-AI, FIM,
YARA, UEBA, compliance) runs on a timer — 5 s to 120 min — and most shell out to
`powershell.exe`. Consequences:

- **Detection latency.** A malicious process that spawns, injects, exfiltrates, and exits inside
  a poll window is never observed. Point-in-time snapshots miss transient behaviour.
- **No causality.** Snapshots have no parent→child process lineage, no event ordering, no
  correlation between a process launch and the network connection it opened.
- **Noisy + evadable.** PowerShell shell-outs are slow, blocked under Constrained Language Mode /
  WDAC, and trivially visible to an adversary watching for `powershell.exe` spawns.

Real endpoint detection needs a **streaming host event source**. On Windows the native one is
**ETW (Event Tracing for Windows)** — the same telemetry backbone Sysmon and commercial EDRs use.

## 2. Goals / Non-Goals

**Goals**
- Continuous, low-latency stream of process/network/registry/file/image-load/DNS events.
- In-process **real-time consumer** (no dependency on Sysmon being installed).
- Parent→child process tree + event correlation, emitted as structured events to the backend.
- A small **behavioural rule engine** running against the live stream (not just signatures).
- Bounded CPU/memory; graceful degradation and backpressure under event storms.
- Fits the existing supervised-task + offline-spool architecture.

**Non-Goals (v1)**
- Kernel driver / minifilter of our own (use ETW kernel providers, no signed driver to ship).
- Full memory forensics / live memory scanning (separate effort).
- Cross-platform (`#[cfg(windows)]` only; Linux path is a no-op stub).
- Replacing existing compliance/evidence collectors — this is additive.

## 3. Background: ETW in one screen

- **Providers** emit events (kernel + user-mode). Identified by GUID or name.
- **Sessions** are kernel-managed trace buffers. A session subscribes to providers and keeps
  ring buffers.
- **Consumers** read events from a session in real time (`ProcessTrace` on a `PROCESSTRACE_MODE_REAL_TIME`
  session) or from an `.etl` file.
- We run one **real-time session** as the SYSTEM service, subscribe to a curated provider set, and
  consume events on a dedicated OS thread.

Two session flavours we need:
- **NT Kernel Logger / system trace** (`SystemTraceProvider`, kernel process/thread/image/file/net
  flags). One classic kernel session per machine historically — modern Windows allows additional
  **system logger** sessions (`EVENT_TRACE_SYSTEM_LOGGER_MODE`).
- **Manifest/user providers** (DNS-Client, PowerShell, WMI-Activity, ETW-TI). Subscribed by GUID on
  a normal real-time session.

## 4. Providers to subscribe (v1)

| Provider | GUID / name | Events used | Detection value |
|---|---|---|---|
| Kernel-Process | `Microsoft-Windows-Kernel-Process` | ProcessStart/Stop, ImageLoad, ThreadStart | Process tree, LOLBins, unsigned image loads |
| Kernel-Network | `Microsoft-Windows-Kernel-Network` | TCP/UDP connect, send/recv | C2 beaconing, exfil, port scans |
| Kernel-Registry | `Microsoft-Windows-Kernel-Registry` | SetValue, CreateKey | Persistence (Run keys, services), tamper |
| Kernel-File | `Microsoft-Windows-Kernel-File` | Create/Write/Delete/Rename | Ransomware mass-write, drop-and-run |
| DNS-Client | `Microsoft-Windows-DNS-Client` | Query/Response | DGA, DNS tunnelling, IOC domains |
| PowerShell | `Microsoft-Windows-PowerShell` | 4103/4104 script block | Fileless / obfuscated scripts |
| WMI-Activity | `Microsoft-Windows-WMI-Activity` | Operation | WMI persistence / lateral movement |
| ETW-TI (Threat-Intel) | `Microsoft-Windows-Threat-Intelligence` | Alloc/Protect/WriteVM, Read/Write process | Process injection, hollowing, AMSI-adjacent |

> ETW-TI requires the process be a **PPL / anti-malware-signed** binary or Secure ETW. v1 ships
> providers that work for a SYSTEM service today; ETW-TI is gated behind a "requires EDR signing"
> follow-up (see §10 Risks). Process-injection coverage in v1 comes from Kernel-Process +
> heuristics until ETW-TI is unlocked.

## 5. Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │  omni-agent.exe (SYSTEM service)             │
                    │                                              │
  ETW kernel/user   │   ┌────────────┐   mpsc    ┌─────────────┐   │
  providers ───────▶│──▶│ ETW consumer│─────────▶│ correlator  │   │
                    │   │ (OS thread) │  RawEvent │ + rule eval │   │
                    │   └────────────┘           └──────┬──────┘   │
                    │        ▲ session ctrl              │ Detection│
                    │        │                           ▼          │
                    │   ┌────┴─────┐             ┌──────────────┐   │
                    │   │ supervisor│             │ batch+upload │──┼──▶ backend
                    │   │ (restart) │             │ (+spool)     │   │   /api/agents/{id}/telemetry
                    │   └──────────┘             └──────────────┘   │
                    └─────────────────────────────────────────────┘
```

Components:

1. **ETW consumer** — dedicated `std::thread` (ETW `ProcessTrace` blocks). Decodes each event via
   `TdhGetEventInformation` / `TdhGetProperty`, maps to a `RawEvent`, pushes onto a bounded
   `tokio::sync::mpsc` (or crossbeam) channel.
2. **Correlator** — async task. Maintains an in-memory **process table** (pid → {ppid, image,
   signer, cmdline, start_time, session}) so network/registry/file events are enriched with the
   owning process lineage. LRU-bounded (e.g. 8 k live processes) with TTL on exit.
3. **Rule engine** — evaluates behavioural rules against enriched events (§7). Emits `Detection`
   objects.
4. **Batcher/uploader** — coalesces enriched events + detections into batched POSTs on a cadence
   (e.g. every 2 s or 512 events, whichever first). Reuses the offline **`Spool`** so telemetry
   survives backend outages.
5. **Supervisor** — the existing `supervise()` wraps the whole engine; a panic restarts it and
   re-arms the session.

## 6. Rust implementation approach

Two viable paths:

- **`ferrisetw` crate** (recommended for v1) — safe wrapper over real-time ETW sessions, provider
  subscription, and TDH schema parsing. Fastest path to a working consumer; MIT.
- **Raw `windows` crate** (`Win32::System::Diagnostics::Etw` + `Etw`/`Tdh`) — full control, no extra
  dep, but ~1000 lines of unsafe FFI (session start/stop, `OpenTrace`, `ProcessTrace`, TDH parsing).

Decision: **start with `ferrisetw`**, keep the `RawEvent` boundary provider-agnostic so we can
swap to raw `windows` later without touching the correlator/rule layers.

New module layout:
```
src/etw/
  mod.rs          # engine entry: start_engine(cfg, client, spool, running)
  session.rs      # session lifecycle, provider enable, restart
  schema.rs       # RawEvent + provider→RawEvent decoders
  correlator.rs   # process table, enrichment, LRU/TTL
  rules.rs        # behavioural rule set + evaluation
  upload.rs       # batching, backend contract, spool integration
```

`Cargo.toml` (windows-gated):
```toml
[target.'cfg(windows)'.dependencies]
ferrisetw = "1"        # or raw windows Etw/Tdh features
```
Non-Windows: `mod.rs` exposes a `start_engine` stub that logs "ETW unsupported" and returns, so
`cargo check`/CI on Linux stays green.

Wiring into `agent.rs` (one line, supervised):
```rust
#[cfg(windows)]
supervise("etw_engine", running.clone(), {
    let (c, cl, r, sp) = (shared_cfg.clone(), client.clone(), running.clone(), spool.clone());
    move || etw::start_engine(c.clone(), cl.clone(), r.clone(), sp.clone())
});
```

## 7. Behavioural rule engine (v1 rule set)

Rules run on **enriched** events (process lineage attached). Each rule → severity + MITRE technique.

| Rule | Signal | MITRE |
|---|---|---|
| LOLBin spawn | `certutil/mshta/rundll32/regsvr32/bitsadmin` with network child or remote arg | T1218 |
| Office→shell | `winword/excel/outlook` spawns `cmd/powershell/wscript` | T1566/T1059 |
| Suspicious parent | `services.exe`/`lsass.exe` unexpected child | T1055/T1543 |
| Run-key persistence | Registry SetValue under `...\CurrentVersion\Run*` | T1547.001 |
| Mass file write | N file writes/sec by one pid over threshold + entropy | T1486 (ransomware) |
| Beaconing | Periodic same-dst connections, low jitter, from one pid | T1071 |
| Unsigned image in system dir | ImageLoad of unsigned DLL from `System32`/temp | T1574 |
| DNS tunnelling | High-entropy / high-volume TXT queries per pid | T1071.004 |

Rules are **data-driven** (a `Vec<Rule>` with typed predicates) so new rules ship without an engine
rewrite. A later version can pull the rule set from the backend (like `threat_intel_poller`).

## 8. Backend contract

New endpoint (additive): `POST /api/agents/{id}/telemetry`
```json
{
  "batch_id": "uuid",
  "collected_at": "RFC3339",
  "events": [
    { "ts":"…","kind":"process_start","pid":123,"ppid":45,
      "image":"C:\\…\\x.exe","signer":"…","cmdline":"…","user":"…" },
    { "ts":"…","kind":"net_connect","pid":123,"dst":"1.2.3.4:443","proto":"tcp" }
  ],
  "detections": [
    { "rule":"office_spawns_shell","severity":"high","mitre":"T1566",
      "pid":123,"process_tree":[…],"evidence":{…} }
  ]
}
```
Events are down-sampled/summarised server-side; detections are always sent. Reuses existing
bearer-auth + `Spool` retry path.

## 9. Performance & resource limits

- **Bounded channel** (e.g. 64 k events). On overflow → **drop + counter**, never block the ETW
  callback (blocking a consumer stalls the kernel session and can lose events system-wide).
- **Provider keyword/level filters** at subscription time so the kernel filters before we decode
  (cheaper than filtering in userland).
- Target budget: **< 3 % CPU** steady-state on a workstation, **< 150 MB** RSS. Emit self-metrics
  (events/sec, drops, queue depth) in the heartbeat `meta`.
- **Adaptive shedding**: under sustained storm, disable the highest-volume providers
  (Kernel-File first) and log it, keeping process/net/registry.

## 10. Security & self-protection

- Session runs as **SYSTEM**; ETW real-time consume needs `SeSystemProfilePrivilege` (SYSTEM has it).
- Name the session deterministically (`OmniAgent-ETW`) and **re-attach/restart** if an adversary
  runs `logman stop` on it — the supervisor + a session-health probe detect a stopped session and
  recreate it. Emit a tamper detection when that happens.
- ETW-TI / secure providers need the agent to be **PPL anti-malware signed** — tracked as a
  prerequisite; not blocking for the v1 provider set.

## 11. Phased rollout

1. **P1 — pipeline skeleton.** `ferrisetw` session + Kernel-Process only → `RawEvent` → process
   table → batched upload. Prove latency + resource budget. (No rules yet.)
2. **P2 — core providers.** Add Kernel-Network, Kernel-Registry, DNS-Client. Correlation enrichment.
3. **P3 — rule engine.** Ship the §7 rule set + `/telemetry` detections; wire into existing
   response actions (kill_process / isolate on high-severity).
4. **P4 — hardening.** Adaptive shedding, session-tamper detection, self-metrics in heartbeat.
5. **P5 — ETW-TI.** After PPL signing lands: injection/hollowing coverage.

## 12. Risks

| Risk | Mitigation |
|---|---|
| Consumer callback blocking → system-wide event loss | Bounded non-blocking channel, drop+count, never allocate/POST in callback |
| ETW-TI needs PPL signing we don't have yet | Gate to P5; v1 injection heuristics from Kernel-Process |
| TDH schema parsing brittleness across Win versions | Use `ferrisetw` schema cache; integration-test on Win10/11/Server 2019/2022 |
| Event storm resource blowup | Keyword filters + adaptive shedding + hard RSS/CPU budget with self-shutdown |
| Second system-logger session limits on older Windows | Detect + fall back to manifest providers only; log capability downgrade |

## 13. Testing / validation

- Unit: `RawEvent` decoders against captured `.etl` fixtures per provider.
- Integration (Windows CI): drive known behaviours (spawn LOLBin, write Run key, mass-write files),
  assert the matching detection is emitted within N ms.
- Soak: 24 h run, assert CPU/RSS budget and zero unbounded growth.
- Red-team smoke: Atomic Red Team techniques mapped to §7 rules.
