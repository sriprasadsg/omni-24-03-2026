# Requirements: Native Security Scanning & Autonomous Remediation Agent

**Milestone goal:** Build native security scanning and autonomous remediation capabilities into the OmniAgent — replacing external integrations (VirusTotal API, Wazuh SIEM) with built-in agent modules. Agent can scan files/URLs/IPs/hashes for threats, detect vulnerabilities on endpoints, monitor file integrity, and autonomously remediate issues via a playbook system.

**Numbering:** continues from the v3.3 milestone. Phases start at **50**.

---

## Native Security Scanning (NSCAN)

- [ ] **NSCAN-01**: Agent can scan a file against embedded malware signatures (ClamAV database subset + custom signatures) and YARA rules, returning verdict (Clean/Suspicious/Malicious) with confidence score. Works offline — no external API.
- [ ] **NSCAN-02**: Agent can scan a URL/IP/domain/hash against bundled threat-intel feeds (malicious URL lists, C2 IP ranges, known-bad hashes) and return reputation verdict. Feeds updated via signed bundle, no live lookup.
- [ ] **NSCAN-03**: Agent exposes scan API (`scan_file`, `scan_url`, `scan_hash`, `scan_ip`) callable by operator or triggered by FIM/behavioral events.

## Vulnerability Detection Engine (VULN)

- [ ] **VULN-01**: Agent scans local system for known CVEs (package version matching against bundled NVD/CVE feed), misconfigurations (weak SSH, open ports, deprecated protocols), and exposed secrets. Returns prioritized finding list.
- [ ] **VULN-02**: Vulnerability feed bundled as signed update; agent applies delta updates autonomously. No external NVD API calls at scan time.
- [ ] **VULN-03**: Findings include CVE ID, CVSS, affected package/path, remediation hint, and playbook reference.

## File Integrity Monitoring (FIM)

- [ ] **FIM-01**: Agent monitors configured critical paths (binaries, configs, scripts, keys) for create/modify/delete/permission changes. Uses inotify/fanotify (Linux) or USN Journal (Windows) — low overhead.
- [x] **FIM-02**: Change events include hash before/after, process tree, user context. Alerts routed to local queue for remediation engine.
- [ ] **FIM-03**: Baseline snapshots signed; drift detection on agent restart.

## Autonomous Remediation (AUTO)

- [ ] **AUTO-01**: Remediation engine receives finding (from VULN, FIM, NSCAN) → selects matching playbook → executes action → verifies fix → emits completion event. Human override always available at any step.
- [ ] **AUTO-02**: Playbook system: YAML-defined remediation actions per finding class (patch package, kill process, restore file from backup, block IP, rotate key, disable service). Extensible by operators.
- [ ] **AUTO-03**: Safety guards: dry-run mode, approval gate for destructive actions, rollback on verification failure, max concurrent remediations per agent.
- [ ] **AUTO-04**: Remediation audit trail — immutable log of finding, playbook selected, actions taken, verification result, operator override if any.

## Integration & Operator UI (INT)

- [ ] **INT-01**: Operator dashboard shows live scan status, findings feed, remediation queue, and audit trail. All per-tenant.
- [ ] **INT-02**: Operator can trigger on-demand scans, approve/deny pending remediations, view playbook library, create custom playbooks.
- [ ] **INT-03**: API endpoints for all agent security functions (scan, vuln-scan, fim-status, remediation-trigger, playbook CRUD).

---

## Future Requirements (deferred)

- **Behavioral anomaly detection** — ML-based process/tree anomaly detection (execution frequency, privilege escalation chains, lateral movement patterns).
- **Network traffic analysis** — agent-side PCAP-less flow analysis for C2 beaconing, data exfiltration patterns.
- **Supply chain verification** — SBOM verification, sigstore cosign validation, reproducible build attestation.
- **Distributed agent coordination** — agents share threat signals peer-to-peer (gossip protocol) for fleet-wide herd immunity.

## Out of Scope

- **External SIEM forwarding** — this milestone builds native capabilities; SIEM export remains separate (existing `integration_service_siem.py`).
- **Cloud workload scanning** — agent runs on endpoints; cloud-native scanning is separate (existing CSPM modules).
- **Managed threat hunting service** — operator-driven only; no SaaS backend analysis.

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| NSCAN-01 | Phase 50 | Planned |
| NSCAN-02 | Phase 50 | Planned |
| NSCAN-03 | Phase 50 | Planned |
| VULN-01 | Phase 51 | Planned |
| VULN-02 | Phase 51 | Planned |
| VULN-03 | Phase 51 | Planned |
| FIM-01 | Phase 52 | Planned |
| FIM-02 | Phase 52 | Planned |
| FIM-03 | Phase 52 | Planned |
| AUTO-01 | Phase 53 | Planned |
| AUTO-02 | Phase 53 | Planned |
| AUTO-03 | Phase 53 | Planned |
| AUTO-04 | Phase 53 | Planned |
| INT-01 | Phase 54 | Planned |
| INT-02 | Phase 54 | Planned |
| INT-03 | Phase 54 | Planned |

**Coverage:** 16 requirements across 5 phases (50–54), no orphans.

*Last updated: 2026-07-30 — Native Security & Autonomous Remediation milestone defined.*
