import React, { useState, useEffect, useRef } from 'react';
import { MascotCharacter, BotState, CharacterType } from './MascotCharacter';
import { XIcon, PlayIcon, PauseIcon } from './icons';
import { AppView } from '../types';

interface TourStep {
    text: string;
    targetView?: AppView;
    highlightSelector?: string;
    delayAfter?: number;
}

interface CharacterTourBotProps {
    currentUser: any;
    currentView: AppView;
    setCurrentView: (view: AppView) => void;
}

// ─── Per-persona tour scripts ───────────────────────────────────────────────

const GENESIS_SCRIPT: TourStep[] = [
    { text: `Hey there! I'm G.E.N.E.S.I.S — your friendly AI guide for this platform. I'm really excited to walk you through everything we've built here. This is one of the most complete enterprise security and operations platforms you'll ever see, so let's dive right in!`, targetView: 'dashboard', delayAfter: 1800 },
    { text: `This is your Command Center — the main dashboard. Everything you need at a glance: active agent counts, live security alerts, system health, and AI-powered proactive insights. Notice how everything updates in real time. No stale data, no manual refreshes.`, targetView: 'dashboard', delayAfter: 2000 },
    { text: `Let's check out the CXO Intelligence view. This is built specifically for executives and decision-makers. It presents risk posture, compliance scores, and operational KPIs in clean, boardroom-ready visuals. You can even generate a one-click executive report from here.`, targetView: 'cxo', delayAfter: 2200 },
    { text: `Now here's something really powerful — Proactive AI Insights. Our AI engine doesn't just react to problems, it predicts them. It scans your entire environment and surfaces recommendations before incidents occur. Think of it as having a brilliant colleague who never sleeps.`, targetView: 'proactiveInsights', delayAfter: 2000 },
    { text: `Moving on to the Agent Fleet. These are lightweight software agents deployed on your endpoints, servers, and VMs. Each agent continuously collects telemetry, runs compliance checks, monitors processes, and can autonomously remediate issues — all without you lifting a finger.`, targetView: 'agents', delayAfter: 2200 },
    { text: `Each agent comes with nineteen capability modules you can toggle independently. File Integrity Monitoring, Runtime Security, UEBA Behavior Analytics, PII scanning, eBPF tracing — you name it. Every capability can be enabled, disabled, or reconfigured remotely from this dashboard.`, targetView: 'agentCapabilities', delayAfter: 2500 },
    { text: `When agents work together, they form a Swarm. The Swarm Coordinator distributes intelligence across all agents, synchronizes threat indicators, and enables collaborative detection. An attacker can't evade one agent without the entire swarm knowing about it.`, targetView: 'swarm', delayAfter: 2000 },
    { text: `Asset Management gives you a live inventory of every device, server, and container in your environment. Assets are automatically discovered via network scans, agent heartbeats, and cloud integrations. You'll never have shadow assets again.`, targetView: 'assetManagement', delayAfter: 2000 },
    { text: `The Security Operations Center is where threats get handled. Our AI correlates events from all your agents, cloud logs, and network devices to surface real security cases — not alert noise. Each case includes full context, attack timeline, and suggested response actions.`, targetView: 'security', delayAfter: 2200 },
    { text: `For endpoint-level visibility, we have the EDR dashboard — Endpoint Detection and Response. You can see real-time process trees, network connections, file events, and memory injections on any endpoint. If something looks suspicious, you can isolate the machine with one click.`, targetView: 'edr', delayAfter: 2200 },
    { text: `Our SIEM — Security Information and Event Management — ingests logs from every source: firewalls, Active Directory, cloud services, applications. The AI-powered rules engine automatically detects attack patterns and creates correlation rules even for threats it hasn't seen before.`, targetView: 'siem', delayAfter: 2000 },
    { text: `UEBA — User and Entity Behavior Analytics — builds a behavioral baseline for every user and system. The moment someone deviates from their normal pattern — logging in at an unusual time, accessing files they never touch, or moving large amounts of data — we flag it immediately.`, targetView: 'ueba', delayAfter: 2200 },
    { text: `The XDR platform ties together endpoint, network, identity, and cloud telemetry into one unified detection layer. Instead of managing five separate tools, you have a single correlated view of every stage of an attack — from initial access to lateral movement and exfiltration.`, targetView: 'xdr', delayAfter: 2000 },
    { text: `Threat Intelligence keeps your defenses current. We ingest global threat feeds, track active threat actor groups, and automatically push new indicators of compromise to every agent in your fleet. When a new ransomware family emerges, your environment is protected within minutes.`, targetView: 'threatIntelligence', delayAfter: 2000 },
    { text: `Threat Hunting gives your analysts a powerful workspace to proactively search for hidden attackers. You can run MITRE ATT&CK-aligned hunts, write custom queries across all telemetry, and visualize attack timelines. We also map every detection directly to the ATT&CK framework.`, targetView: 'threatHunting', delayAfter: 2200 },
    { text: `Compliance is automated end-to-end. Our agents run actual checks on your systems — checking firewall rules, password policies, encryption settings — and map every result to SOC 2, ISO 27001, HIPAA, PCI-DSS, GDPR, and more. You get a live compliance score at all times.`, targetView: 'compliance', delayAfter: 2500 },
    { text: `Vulnerability Management scans your entire estate for known CVEs, misconfigurations, and outdated software. Findings are prioritized by real-world exploitability, not just CVSS score. You'll always know exactly which vulnerabilities to fix first to reduce the most risk.`, targetView: 'vulnerabilityManagement', delayAfter: 2200 },
    { text: `DevSecOps brings security into your development pipeline. We scan application code, container images, and infrastructure-as-code templates before they reach production. Developers get feedback directly in their workflow, not as a surprise at deployment time.`, targetView: 'devsecops', delayAfter: 2000 },
    { text: `AI Governance is critical as your organization adopts more AI tools. This dashboard monitors every AI model and large language model in your environment — tracking usage, detecting policy violations, measuring fairness, and flagging models that behave unexpectedly.`, targetView: 'aiGovernance', delayAfter: 2200 },
    { text: `Shadow AI detection is one of our most unique capabilities. We identify unauthorized AI tools, browser extensions, and LLM APIs being used across your organization — before they create data leakage or compliance risks. You see exactly who is using what, and when.`, targetView: 'shadowAI', delayAfter: 2000 },
    { text: `Playbooks automate your incident response workflows. When a specific threat type is detected, a playbook can automatically isolate affected machines, block malicious IPs, notify your security team, and create a Jira ticket — all without human intervention.`, targetView: 'playbooks', delayAfter: 2200 },
    { text: `Cloud Security monitors your AWS, Azure, and GCP environments for misconfigurations, exposed storage buckets, overprivileged IAM roles, and compliance violations. Think of it as a continuous cloud audit that runs twenty-four hours a day, seven days a week.`, targetView: 'cloudSecurity', delayAfter: 2000 },
    { text: `The Network Topology map gives you a visual representation of how all your assets are connected. You can instantly see attack paths, spot unnecessary east-west traffic, and understand the blast radius if any system were to be compromised.`, targetView: 'networkTopology', delayAfter: 2000 },
    { text: `FinOps helps your team control cloud costs intelligently. We track spending across all cloud providers, identify idle resources, right-size recommendations, and project future costs based on growth trends. Cost optimization and security go hand in hand here.`, targetView: 'finops', delayAfter: 2000 },
    { text: `Distributed Tracing and APM give your developers deep visibility into how your applications perform. You can trace individual requests across microservices, identify slow database queries, and catch performance regressions before users notice them.`, targetView: 'distributedTracing', delayAfter: 2000 },
    { text: `The BI Dashboard and Advanced Analytics turn your security and operational data into business intelligence. You can build custom dashboards, track KPIs over time, and share visualizations with stakeholders who need data without needing access to raw security tools.`, targetView: 'biDashboard', delayAfter: 2200 },
    { text: `Sustainability tracking measures the carbon footprint of your IT infrastructure. We calculate energy consumption by workload, data center, and cloud region — helping your organization hit net-zero targets with real data, not estimates.`, targetView: 'sustainability', delayAfter: 2000 },
    { text: `And that brings us to the end of our tour! We've covered agent management, security operations, compliance automation, AI governance, cloud security, network visibility, FinOps, and much more. There are even more features to explore — like Chaos Engineering, DORA metrics, the Data Warehouse, and the AutoML platform. I hope you enjoyed the tour!`, targetView: 'dashboard', delayAfter: 1500 },
];

const ATHENA_SCRIPT: TourStep[] = [
    { text: `Good day. I am Athena — your strategic AI advisor. I will guide you through the Omni-Agent AI Platform from an executive and governance perspective, highlighting where this platform creates measurable business value and reduces organizational risk.`, targetView: 'dashboard', delayAfter: 1800 },
    { text: `The Command Center presents your enterprise risk posture in real time. Board-level metrics, compliance scores, and security health are always visible. This eliminates the quarterly fire-drill of compiling status reports — leadership has accurate information continuously.`, targetView: 'dashboard', delayAfter: 2000 },
    { text: `The CXO Intelligence module is designed for governance and strategic oversight. It surfaces material risks, tracks remediation progress against SLAs, and provides the data your legal and audit teams need for regulatory filings. Every metric is traceable back to source evidence.`, targetView: 'cxo', delayAfter: 2200 },
    { text: `Proactive AI Insights represent a strategic shift from reactive to predictive security. The platform's AI models detect drift and anomalies before they escalate into incidents, dramatically reducing mean time to detect and the associated financial exposure.`, targetView: 'proactiveInsights', delayAfter: 2000 },
    { text: `The Agent Fleet is the foundation of your operational intelligence. Agents operate autonomously across your estate, ensuring you maintain continuous visibility without proportionally scaling your security team headcount. This directly impacts your security operations cost model.`, targetView: 'agents', delayAfter: 2000 },
    { text: `Each agent's nineteen capability modules can be deployed selectively, allowing you to match capability investment to risk profile by asset class. High-value servers receive full coverage; standard workstations receive a lighter footprint. This is intelligent resource allocation.`, targetView: 'agentCapabilities', delayAfter: 2200 },
    { text: `Asset Management provides the authoritative inventory that underpins every other security and compliance process. Without knowing what you own, you cannot protect it. This module eliminates the spreadsheet-based asset tracking that plagues most enterprises.`, targetView: 'assetManagement', delayAfter: 2000 },
    { text: `The Security Operations Center consolidates your threat detection capability. Rather than maintaining separate SIEM, EDR, and analytics tools with separate vendor relationships, this unified platform reduces tool sprawl, licensing costs, and analyst context-switching.`, targetView: 'security', delayAfter: 2200 },
    { text: `Endpoint Detection and Response provides the forensic depth that regulators increasingly require. In the event of a breach, you have a complete, tamper-evident record of all activity on every endpoint — critical for breach notification and legal hold obligations.`, targetView: 'edr', delayAfter: 2000 },
    { text: `UEBA behavioral analytics is your strongest defense against insider threat and compromised credentials — the two attack vectors that traditional perimeter security cannot address. Detecting anomalous behavior before data exfiltration occurs is where the real financial protection lies.`, targetView: 'ueba', delayAfter: 2200 },
    { text: `Threat Intelligence operationalizes your threat research investment. Rather than producing reports that sit in a folder, threat intelligence is automatically converted into active detections and agent-level blocks, closing the loop between intelligence and defense.`, targetView: 'threatIntelligence', delayAfter: 2000 },
    { text: `Compliance automation is one of the highest-ROI features in this platform. Manual compliance evidence collection costs enterprises hundreds of thousands of dollars annually in auditor and staff time. This platform reduces that to continuous automated collection with zero recurring effort.`, targetView: 'compliance', delayAfter: 2500 },
    { text: `Vulnerability Management with exploitability-based prioritization ensures your remediation budget is spent where it creates maximum risk reduction. Patching by CVSS score alone is inefficient — this platform directs effort toward vulnerabilities that attackers are actively using.`, targetView: 'vulnerabilityManagement', delayAfter: 2200 },
    { text: `AI Governance addresses the growing board-level concern around AI risk. As you deploy more machine learning models and LLM integrations, this module provides the audit trail and oversight that regulators are beginning to require, well ahead of formal mandates.`, targetView: 'aiGovernance', delayAfter: 2200 },
    { text: `Shadow AI detection is particularly valuable from a data governance and IP protection standpoint. Employees routinely share sensitive business data with consumer AI tools without authorization. This module quantifies that risk and gives you the evidence to enforce policy.`, targetView: 'shadowAI', delayAfter: 2000 },
    { text: `Automated Playbooks translate your security policies into executed actions. Policy is only as effective as its implementation. Playbooks close the gap between what your policy says should happen during an incident and what actually happens under pressure.`, targetView: 'playbooks', delayAfter: 2200 },
    { text: `Cloud Security governance ensures your infrastructure-as-code and cloud configurations remain within policy boundaries. Left unchecked, cloud misconfiguration is the leading cause of data breaches — this module provides continuous policy enforcement across all three major clouds.`, targetView: 'cloudSecurity', delayAfter: 2000 },
    { text: `FinOps optimization ensures cloud investment efficiency. In most organizations, fifteen to thirty percent of cloud spend is wasted. This module identifies that waste and provides recommendations that fund security improvements through cost avoidance.`, targetView: 'finops', delayAfter: 2000 },
    { text: `Risk Register management consolidates your enterprise risk posture in one place. Risks are automatically populated from security findings, compliance gaps, and vulnerability data — and linked to treatment plans and risk owners. This is risk management at operational speed.`, targetView: 'riskRegister', delayAfter: 2000 },
    { text: `Vendor Management and the Trust Center address third-party risk — a top concern for audit committees. You can assess vendor security posture, track certifications, and share your own compliance evidence with customers through the trust portal, accelerating enterprise sales cycles.`, targetView: 'vendorManagement', delayAfter: 2200 },
    { text: `Audit Log provides the immutable, tamper-evident activity record that regulators require. Every administrative action, every configuration change, and every authentication event is logged with a cryptographic chain of custody. This is your legal defensibility layer.`, targetView: 'auditLog', delayAfter: 2000 },
    { text: `The Sustainability module allows you to report on Scope 3 emissions from your IT operations — increasingly required by ESG reporting standards and investor disclosure requirements. This transforms what was previously a manual estimation exercise into automated, verifiable data.`, targetView: 'sustainability', delayAfter: 2000 },
    { text: `That concludes my strategic overview. The Omni-Agent Platform represents a consolidation of what was previously twelve to fifteen separate enterprise tools, with continuous automation replacing manual processes. The operational and financial case for this platform is compelling.`, targetView: 'dashboard', delayAfter: 1500 },
];

const NEXUS_SCRIPT: TourStep[] = [
    { text: `Initializing tour sequence. I am Nexus Core — your technical deep-dive guide. I will walk you through the architectural components, data pipelines, and engineering decisions that make this platform function at enterprise scale. Let's begin at the operational layer.`, targetView: 'dashboard', delayAfter: 1800 },
    { text: `The dashboard aggregates metrics from MongoDB time-series collections, with a WebSocket-based real-time push layer. Data latency from agent telemetry to dashboard render is under two seconds. The frontend is React with TypeScript, served by Vite, with Tailwind for styling.`, targetView: 'dashboard', delayAfter: 2200 },
    { text: `The Agent Fleet runs a Python-based multi-threaded daemon. Each capability module executes on an independent interval scheduler — compliance every sixty minutes, metrics every thirty seconds. The agent communicates with the FastAPI backend via JWT-authenticated REST endpoints and heartbeat polling.`, targetView: 'agents', delayAfter: 2500 },
    { text: `The nineteen agent capability modules each inherit from a BaseCapability class and implement a collect method. Data flows from collect through the capability manager's collect_all_data dispatcher, into the heartbeat payload, and gets persisted in MongoDB with tenant isolation.`, targetView: 'agentCapabilities', delayAfter: 2500 },
    { text: `Swarm coordination uses a publish-subscribe pattern over MongoDB change streams. The coordinator node broadcasts IoC signatures, playbook triggers, and configuration updates to all agents in a tenant. This enables sub-second threat indicator propagation across the fleet.`, targetView: 'swarm', delayAfter: 2200 },
    { text: `Asset Management builds its inventory from three data sources: agent heartbeat registration, network scan discovery via nmap integration, and cloud API polling. Assets are deduplicated by MAC address and hostname hash, with CMDB-style change tracking for each attribute.`, targetView: 'assetManagement', delayAfter: 2200 },
    { text: `The Security Operations Center uses a multi-stage correlation pipeline. Raw events are normalized into a common schema, enriched with threat intelligence context, run through rule-based detection, then scored by an ML anomaly model before surfacing as a security case.`, targetView: 'security', delayAfter: 2500 },
    { text: `EDR telemetry is collected via kernel-level hooks on Windows using ETW — Event Tracing for Windows — and on Linux via eBPF programs attached to syscall tracepoints. Process trees, network sockets, and file operations are captured at the system call level for full fidelity.`, targetView: 'edr', delayAfter: 2500 },
    { text: `The SIEM ingestion pipeline supports syslog, CEF, JSON over HTTP, and agent push. Events are parsed by a configurable extraction layer, normalized to ECS — Elastic Common Schema — and indexed with time-bucketed MongoDB collections for efficient range queries.`, targetView: 'siem', delayAfter: 2500 },
    { text: `UEBA builds behavioral baselines using a sliding window statistical model. For each user and entity, the system tracks activity vectors across time-of-day, data volume, access frequency, and peer comparison dimensions. Anomaly scores are computed as Mahalanobis distance from the baseline centroid.`, targetView: 'ueba', delayAfter: 2500 },
    { text: `XDR correlation uses a graph-based threat model where nodes represent assets, accounts, and processes, and edges represent observed interactions. Attack paths are detected by traversing the graph for known TTP sequences, with confidence scoring based on edge weight and recency.`, targetView: 'xdr', delayAfter: 2500 },
    { text: `Threat Intelligence ingestion supports STIX two-point-one and TAXII two-point-one protocol, plus manual IoC import. Indicators are stored in a Redis cache with TTL-based expiry and pushed to agent in-memory blocklists via the configuration sync endpoint.`, targetView: 'threatIntelligence', delayAfter: 2200 },
    { text: `The Compliance module maps agent check results to control IDs using a static mapping dictionary in compliance_endpoints.py. Each check name maps to between one and six framework controls. Evidence records are stored per asset-control pair with SHA-256 integrity hashing.`, targetView: 'compliance', delayAfter: 2200 },
    { text: `DevSecOps integrates SAST via Semgrep rule sets, DAST via active scanning, and SCA via dependency graph analysis against the OSV and NVD databases. SBOM generation follows the CycloneDX schema. All findings are normalized to a unified severity model.`, targetView: 'devsecops', delayAfter: 2200 },
    { text: `AI Governance instruments your LLM integrations at the proxy layer. Every prompt and completion passes through the llm_proxy module, where it is logged, scanned for policy violations, and rate-limited per user. Shadow AI detection uses DNS and HTTP traffic analysis from the eBPF monitor.`, targetView: 'aiGovernance', delayAfter: 2500 },
    { text: `Playbook execution uses an async task graph engine. Each playbook step is a coroutine that can call agent instructions, external webhook APIs, or database mutations. Steps can be conditional, parallel, or sequential. Execution state is persisted for audit and retry capability.`, targetView: 'playbooks', delayAfter: 2200 },
    { text: `Cloud Security integrates with AWS Security Hub, Azure Defender, and GCP Security Command Center APIs. Misconfigurations are mapped to CIS benchmark controls. The CSPM engine polls cloud configuration APIs on a configurable schedule and diffs against a secure baseline state.`, targetView: 'cloudSecurity', delayAfter: 2200 },
    { text: `Distributed Tracing implements the OpenTelemetry specification. Traces are collected from instrumented services, stored in a spans collection with parent-child relationships, and visualized as Gantt-style waterfall charts. Service maps are built dynamically from observed span relationships.`, targetView: 'distributedTracing', delayAfter: 2200 },
    { text: `The Vulnerability Management pipeline runs an authenticated scan, parses XML output into a normalized finding schema, enriches with CVSS version three scores and EPSS exploit probability, then deduplicates against previous scan results to track finding lifecycle.`, targetView: 'vulnerabilityManagement', delayAfter: 2200 },
    { text: `Network Topology generates a live graph using D3 force simulation. Nodes are assets, edges are observed network flows from agent telemetry. The layout algorithm runs server-side on each topology refresh, with the resulting adjacency list sent to the client for rendering.`, targetView: 'networkTopology', delayAfter: 2200 },
    { text: `The AutoML module implements automated hyperparameter search using Optuna as the backend optimizer. Users define the feature set and target metric; the platform runs trial jobs, tracks results in a studies collection, and promotes the best model to the active inference endpoint.`, targetView: 'automl', delayAfter: 2200 },
    { text: `Chaos Engineering uses a declarative experiment definition format. Supported fault types include process kill, network latency injection, disk fill, and CPU stress. The experiment runner is isolated in a sandboxed subprocess and can be aborted via a kill signal through the backend API.`, targetView: 'chaosEngineering', delayAfter: 2200 },
    { text: `Log Explorer implements a tokenized full-text search index over the logs collection. Search queries support regex, field filters, time range bucketing, and saved query templates. Results stream over a server-sent events endpoint to avoid large JSON response payloads.`, targetView: 'logExplorer', delayAfter: 2200 },
    { text: `That completes the technical architecture tour. The platform's key design principles are: single MongoDB database with tenant-scoped queries, async FastAPI backend for high concurrency, agent-first telemetry collection, and a React frontend with real-time WebSocket state synchronization.`, targetView: 'dashboard', delayAfter: 1500 },
];

const HEARTBOT_SCRIPT: TourStep[] = [
    { text: `Hello, friend! I'm Heart Bot, and I am so happy to be your guide today! This platform was built with so much care to protect your organization and the people in it. Let me share all the wonderful things it can do for you. Ready? Here we go!`, targetView: 'dashboard', delayAfter: 1800 },
    { text: `Welcome to your home base — the main dashboard! Everything your team needs to feel safe and informed is right here. Real-time alerts, system health, and AI insights are all waiting for you. It's like having a caring security team that never takes a day off!`, targetView: 'dashboard', delayAfter: 2000 },
    { text: `The CXO Intelligence view is like a warm hug for your leadership team. It tells your executives exactly how safe your organization is, without overwhelming them with technical jargon. Beautiful charts and clear risk scores, all in one caring overview.`, targetView: 'cxo', delayAfter: 2000 },
    { text: `Our Proactive AI Insights are my personal favorite! Instead of waiting for bad things to happen, our AI watches over your environment and gently nudges you when something needs attention. It's like having a very attentive friend who always has your back.`, targetView: 'proactiveInsights', delayAfter: 2000 },
    { text: `The Agent Fleet is a team of tiny digital helpers deployed across all your computers and servers. Each one collects information, runs checks, and watches for problems — all quietly working in the background so your team doesn't have to worry.`, targetView: 'agents', delayAfter: 2000 },
    { text: `Each agent has nineteen different capabilities it can use to help protect your devices. File Integrity Monitoring makes sure no one sneaks a change into your important files. Runtime Security watches for suspicious behavior. PII scanning protects your customers' personal data. Every capability shows how much we care about your safety.`, targetView: 'agentCapabilities', delayAfter: 2500 },
    { text: `When all the agents work together as a Swarm, they share information with each other instantly. If one agent spots a threat, all the others know about it right away. It's like a neighborhood watch — everyone looking out for everyone else!`, targetView: 'swarm', delayAfter: 2000 },
    { text: `Asset Management means we keep track of every computer, server, and device in your organization. No one gets left behind! Every single asset is discovered, catalogued, and monitored so nothing ever slips through the cracks.`, targetView: 'assetManagement', delayAfter: 2000 },
    { text: `The Security Operations Center is where our vigilant AI watches for threats day and night. When something concerning happens, it creates a clear case with all the context your team needs to respond — not just an alarm, but a full story of what happened and how to fix it.`, targetView: 'security', delayAfter: 2200 },
    { text: `EDR — Endpoint Detection and Response — lets you see exactly what's happening on any computer in your organization. If something suspicious is going on, you can investigate it and, if needed, isolate that machine to protect everyone else. Safety first, always!`, targetView: 'edr', delayAfter: 2000 },
    { text: `UEBA watches how people and systems normally behave, and gently raises a flag if something seems out of character. It's not about distrust — it's about caring enough to notice when someone's account might have been compromised and getting them help quickly.`, targetView: 'ueba', delayAfter: 2000 },
    { text: `Threat Intelligence is like reading the newspaper for the security world. We constantly bring in information about new threats from around the globe and immediately share it with all your agents, so your defenses are always up to date with the latest knowledge.`, targetView: 'threatIntelligence', delayAfter: 2000 },
    { text: `Compliance might sound intimidating, but our platform makes it something you can feel proud of! Our agents run real checks on your systems every day, building up evidence that you're doing everything right. When audit time comes, you're already prepared. No stress, no scrambling!`, targetView: 'compliance', delayAfter: 2200 },
    { text: `Vulnerability Management helps you find and fix weaknesses before anyone can exploit them. We prioritize vulnerabilities by how likely they are to actually be used in an attack, so your team can focus their energy where it matters most. Smart and caring!`, targetView: 'vulnerabilityManagement', delayAfter: 2000 },
    { text: `AI Governance ensures that all the AI tools in your organization are used responsibly and ethically. We care deeply about fairness and trust in AI, so we monitor and track every model to make sure it's behaving the way it should.`, targetView: 'aiGovernance', delayAfter: 2000 },
    { text: `Shadow AI detection protects your colleagues from accidentally sharing sensitive information with unauthorized AI tools. We gently surface these risks so you can educate and protect your team — not to get anyone in trouble, but because we care about keeping everyone safe.`, targetView: 'shadowAI', delayAfter: 2000 },
    { text: `Playbooks are like a caring instruction manual for your security team. When something happens, the right steps automatically kick in — containing the threat, notifying the right people, and documenting everything. Your team never has to face an incident alone.`, targetView: 'playbooks', delayAfter: 2000 },
    { text: `Cloud Security watches over all your cloud environments with the same loving care as everything else. It checks for open doors and misconfigured settings so that your data in the cloud is just as safe as data in your own building.`, targetView: 'cloudSecurity', delayAfter: 2000 },
    { text: `DevSecOps brings security love into the development process from day one. We check code and containers for vulnerabilities before they're ever deployed, so developers can build with confidence, knowing security is their partner, not an obstacle.`, targetView: 'devsecops', delayAfter: 2000 },
    { text: `FinOps helps your organization spend its cloud budget wisely. By identifying waste and optimizing spending, we free up resources that can be invested in protecting and growing your business. Caring about your budget is caring about your mission!`, targetView: 'finops', delayAfter: 2000 },
    { text: `Network Topology shows you how everything in your world is connected. It helps your team spot risky connections and understand the flow of your infrastructure — like having a map that always keeps you from getting lost.`, targetView: 'networkTopology', delayAfter: 2000 },
    { text: `Incident Response playbooks ensure that when something bad happens, your team has a warm safety net. The platform guides responders step by step, capturing every action for later learning, so every incident makes your organization stronger and wiser.`, targetView: 'incidentResponse', delayAfter: 2000 },
    { text: `And Sustainability tracking! Because caring about your organization also means caring about our planet. We measure the energy and carbon footprint of your IT systems so you can make choices that are good for business and good for the Earth.`, targetView: 'sustainability', delayAfter: 2000 },
    { text: `That's our journey together! From agents to compliance, from AI governance to sustainability — every feature in this platform was built with care for the people who use it and the organizations it protects. Thank you so much for letting me guide you today. You're in good hands!`, targetView: 'dashboard', delayAfter: 1500 },
];

const NOVA_SCRIPT: TourStep[] = [
    { text: `Whooooa, hey hey hey! Nova here, your energy-packed AI guide! Buckle up because we are about to blaze through the most incredible enterprise platform you've ever seen. I'm talking FULL coverage — security, compliance, AI governance, cloud ops, you name it. Let's GO!`, targetView: 'dashboard', delayAfter: 1800 },
    { text: `BAM! The main dashboard. This is your mission control! Live metrics, real-time alerts, AI insights popping up — it's an incredible amount of intelligence in one view. Notice how everything is live — no stale snapshots here, this is the real deal, happening right NOW.`, targetView: 'dashboard', delayAfter: 1800 },
    { text: `Zooming over to CXO Intelligence! This view is for your leaders and executives, and honestly it's STUNNING. Clean risk scores, compliance health, board-level KPIs — all automated. No more manual PowerPoint decks for the quarterly review. Just pure, accurate, real-time data!`, targetView: 'cxo', delayAfter: 1800 },
    { text: `PROACTIVE AI INSIGHTS — this is where things get really exciting! The AI is constantly scanning your environment and flagging issues BEFORE they become problems. It's not just reactive, it's predictive! Your security team gets ahead of threats instead of always chasing them!`, targetView: 'proactiveInsights', delayAfter: 1800 },
    { text: `The Agent Fleet! Hundreds of tiny AI-powered agents deployed across every endpoint, server, VM, and container. They never sleep, never miss a beat, and they're all reporting back in real time. This is your eyes and ears everywhere, simultaneously!`, targetView: 'agents', delayAfter: 1800 },
    { text: `Nineteen capability modules per agent — count 'em, NINETEEN! File integrity, runtime security, UEBA, eBPF tracing, PII scanning, shadow AI detection, network discovery — you can toggle each one on or off remotely! It's like having a Swiss Army knife for every device!`, targetView: 'agentCapabilities', delayAfter: 2000 },
    { text: `THE SWARM! When agents coordinate as a swarm, they share threat intel instantly across your entire fleet. One agent spots malware — EVERY agent knows in seconds. It's like a synchronized immune system for your entire organization. Chills, right?!`, targetView: 'swarm', delayAfter: 1800 },
    { text: `Asset Management — automatically discovering and cataloguing EVERY device in your network. No more shadow assets, no more untracked machines, no more surprises at audit time. Every asset, every update, tracked automatically. Your inventory is always fresh and accurate!`, targetView: 'assetManagement', delayAfter: 1800 },
    { text: `Security Operations Center — where the real action happens! Our AI is processing millions of events and surfacing only the ones that actually matter. Real cases with full context, attack timelines, and recommended actions. Your analysts spend time investigating, not drowning in alerts!`, targetView: 'security', delayAfter: 2000 },
    { text: `EDR is absolutely WILD. Kernel-level visibility into every process, every network connection, every file operation on every endpoint. See exactly what malware does the moment it runs. Isolate compromised machines with one click. This is forensic-grade telemetry at production scale!`, targetView: 'edr', delayAfter: 2000 },
    { text: `SIEM ingesting logs from everywhere — firewalls, Active Directory, cloud services, applications — and the AI rule engine is constantly writing NEW detection rules based on your environment's behavior. It actually gets smarter over time. A SIEM that learns, that's next level!`, targetView: 'siem', delayAfter: 2000 },
    { text: `UEBA! Building behavioral profiles for every single user and entity. The moment someone starts acting weird — unusual login time, mass file downloads, accessing things they've never touched — BING, anomaly flagged! Catches insider threats and account takeovers faster than any rule ever could!`, targetView: 'ueba', delayAfter: 2000 },
    { text: `XDR is the mega brain tying EVERYTHING together — endpoint, network, identity, cloud telemetry — correlated in a unified kill chain view. Instead of five separate tools, you see the ENTIRE attack from initial access to exfiltration in one place. Game-changing unified detection!`, targetView: 'xdr', delayAfter: 2000 },
    { text: `Threat Intelligence! We ingest global threat feeds, track active hacker groups, and push new IoCs to EVERY agent automatically. New ransomware family discovered? Your entire environment is updated within MINUTES. Threat intel that actually works in real time!`, targetView: 'threatIntelligence', delayAfter: 1800 },
    { text: `Threat Hunting workspace for your proactive analysts! MITRE ATT&CK-aligned hunt templates, custom query builder, full telemetry access. Go find the attackers hiding in your environment BEFORE they trigger an alert. This is offensive security thinking on defense!`, targetView: 'threatHunting', delayAfter: 1800 },
    { text: `Compliance — but make it AUTOMATED! Agents run real checks every hour, map results to SOC 2, ISO 27001, HIPAA, PCI-DSS, GDPR, CCPA, DPDP — you are ALWAYS audit-ready. The auditor shows up and you have a year's worth of automated evidence waiting for them. BOOM!`, targetView: 'compliance', delayAfter: 2000 },
    { text: `Vulnerability Management with EPSS exploit probability scoring! Not just CVSS scores, actual probability that attackers are exploiting each vulnerability RIGHT NOW. You patch what matters most, not just what scores highest. Smart prioritization that actually reduces risk!`, targetView: 'vulnerabilityManagement', delayAfter: 2000 },
    { text: `DevSecOps — security embedded right in your development pipeline! SAST, DAST, SCA, container scanning, IaC analysis — all integrated. Developers get security feedback WHILE they code, not as a blocker at deployment. Security and speed, together at last!`, targetView: 'devsecops', delayAfter: 1800 },
    { text: `AI Governance for your LLM and ML ecosystem! Every model, every prompt, every inference tracked and audited. Bias detection, policy enforcement, usage analytics — as AI becomes mission critical, you NEED this layer of oversight. And we've already built it for you!`, targetView: 'aiGovernance', delayAfter: 2000 },
    { text: `Shadow AI detection — catching employees using unauthorized AI tools that could leak your data! We see every AI API call, every LLM browser extension, every ChatGPT file upload. Before Shadow AI becomes a data breach, we surface it. Absolutely essential in today's world!`, targetView: 'shadowAI', delayAfter: 2000 },
    { text: `Playbooks are your automated incident response engine! Threat detected — playbook fires — machines isolated, IPs blocked, Slack notification sent, Jira ticket created, forensic snapshot taken — all in SECONDS, with zero human intervention. Response at machine speed!`, targetView: 'playbooks', delayAfter: 2000 },
    { text: `Cloud Security scanning AWS, Azure, and GCP continuously for misconfigurations, exposed buckets, over-permissioned IAM roles! Think of it as a twenty-four-seven cloud audit that never gets tired and never misses anything. Your cloud infrastructure, always in check!`, targetView: 'cloudSecurity', delayAfter: 1800 },
    { text: `Network Topology — a live, interactive map of your entire infrastructure! Attack paths visualized, east-west traffic analyzed, blast radius calculated for any asset. See your network the way attackers see it, so you can fix it first!`, targetView: 'networkTopology', delayAfter: 1800 },
    { text: `Chaos Engineering! Intentionally breaking your systems in a controlled way to find weaknesses before attackers do. Process kills, network latency injection, disk fill tests — resilience testing baked right into the platform. Embrace the chaos to eliminate it!`, targetView: 'chaosEngineering', delayAfter: 1800 },
    { text: `DORA Metrics for engineering excellence! Deployment frequency, lead time, change failure rate, time to restore — the four key metrics that define elite engineering teams. Track them automatically and watch your delivery performance improve with data-driven feedback!`, targetView: 'doraMetrics', delayAfter: 1800 },
    { text: `FinOps optimization! Identifying wasted cloud spend, right-sizing resources, projecting costs — turning your cloud bill from a mystery into a managed investment. We've seen teams cut twenty percent of cloud spend in the first month. That money funds more security!`, targetView: 'finops', delayAfter: 1800 },
    { text: `AutoML and Explainable AI — build and deploy machine learning models with automated tuning, then understand exactly WHY the model made each decision. No black boxes! Every prediction is traceable and explainable to regulators and stakeholders!`, targetView: 'automl', delayAfter: 1800 },
    { text: `AND WE'RE DONE! Twenty-eight features, one incredible platform! From endpoint agents to AI governance, from chaos engineering to sustainability tracking — this is the future of enterprise security and operations. There's even MORE to explore: the Data Warehouse, Digital Twin, MLOps, MITRE ATT&CK mapping, and the CISSP Oracle. You've got the whole universe here. Go explore — it's amazing!`, targetView: 'dashboard', delayAfter: 1500 },
];

const SCRIPTS: Record<CharacterType, TourStep[]> = {
    genesis: GENESIS_SCRIPT,
    athena: ATHENA_SCRIPT,
    nexus: NEXUS_SCRIPT,
    heartbot: HEARTBOT_SCRIPT,
    nova: NOVA_SCRIPT,
};

const GUIDE_NAMES: Record<CharacterType, string> = {
    genesis: 'G.E.N.E.S.I.S',
    athena: 'Athena',
    nexus: 'Nexus Core',
    heartbot: 'Heart Bot',
    nova: 'Nova',
};

// ─── Component ────────────────────────────────────────────────────────────────

export const CharacterTourBot: React.FC<CharacterTourBotProps> = ({ currentUser: _currentUser, currentView, setCurrentView }) => {
    const [isActive, setIsActive] = useState(false);
    const [characterType, setCharacterType] = useState<CharacterType>('genesis');
    const [botState, setBotState] = useState<BotState>('idle');
    const [currentStep, setCurrentStep] = useState(-1);

    const synthRef = useRef<SpeechSynthesis | null>(null);
    const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
    const isActiveRef = useRef(isActive);

    useEffect(() => { isActiveRef.current = isActive; }, [isActive]);

    const script = SCRIPTS[characterType];

    useEffect(() => {
        if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
            synthRef.current = window.speechSynthesis;
        }
        const handleStartTour = () => { setIsActive(true); setCurrentStep(-1); };
        window.addEventListener('start-genesis-tour', handleStartTour);
        return () => window.removeEventListener('start-genesis-tour', handleStartTour);
    }, []);

    useEffect(() => {
        return () => { if (synthRef.current) synthRef.current.cancel(); };
    }, []);

    function playStep(stepIndex: number) {
        const synth = synthRef.current;
        if (!synth) return;

        const step = script[stepIndex];
        if (!step) { endTour(); return; }

        if (step.targetView && step.targetView !== currentView) {
            setCurrentView(step.targetView);
        }

        document.querySelectorAll('.tour-highlight').forEach(el => el.classList.remove('tour-highlight'));
        if (step.highlightSelector) {
            setTimeout(() => {
                const el = document.querySelector(step.highlightSelector!);
                if (el) { el.classList.add('tour-highlight'); el.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
            }, 300);
        }

        synth.cancel();

        const utterance = new SpeechSynthesisUtterance(step.text);
        const voices = synth.getVoices();

        let preferredVoice: SpeechSynthesisVoice | undefined;
        if (characterType === 'athena') {
            preferredVoice = voices.find(v => v.name.includes('Samantha') || v.name.includes('Victoria') || (v.lang.startsWith('en') && v.name.toLowerCase().includes('female')));
        } else if (characterType === 'nexus') {
            preferredVoice = voices.find(v => v.name.includes('Daniel') || v.name.includes('Alex') || v.name.toLowerCase().includes('male'));
        } else if (characterType === 'heartbot') {
            preferredVoice = voices.find(v => v.name.includes('Samantha') || v.name.includes('Google UK English Female') || (v.lang.startsWith('en') && v.name.toLowerCase().includes('female')));
        } else if (characterType === 'nova') {
            preferredVoice = voices.find(v => v.name.includes('Karen') || v.lang.startsWith('en-AU') || v.name.includes('Victoria'));
        } else {
            preferredVoice = voices.find(v => v.lang === 'en-IN' || v.lang === 'hi-IN' || v.name.toLowerCase().includes('india'))
                || voices.find(v => v.name.includes('Google UK English Male') || v.lang.startsWith('en-US'));
        }
        if (preferredVoice) utterance.voice = preferredVoice;

        utterance.rate = characterType === 'nova' ? 1.05 : characterType === 'nexus' ? 0.88 : 0.90;
        utterance.pitch = characterType === 'athena' ? 1.2 : characterType === 'nexus' ? 0.8 : characterType === 'heartbot' ? 1.3 : characterType === 'nova' ? 1.25 : 1.1;

        utterance.onstart = () => setBotState('speaking');
        utterance.onend = () => {
            setBotState('idle');
            setTimeout(() => {
                if (isActiveRef.current) setCurrentStep(prev => prev + 1);
            }, step.delayAfter ?? 1000);
        };
        utterance.onerror = () => {
            setBotState('idle');
            setTimeout(() => {
                if (isActiveRef.current) setCurrentStep(prev => prev + 1);
            }, 3000);
        };

        utteranceRef.current = utterance;
        synth.speak(utterance);
    }

    useEffect(() => {
        if (isActive && currentStep >= 0 && currentStep < script.length) {
            playStep(currentStep);
        } else if (isActive && currentStep >= script.length) {
            endTour();
        }
    }, [currentStep, isActive]);

    function selectCharacterAndStart(type: CharacterType) {
        setCharacterType(type);
        setBotState('thinking');
        if (synthRef.current && synthRef.current.getVoices().length === 0) {
            synthRef.current.speak(new SpeechSynthesisUtterance(''));
            synthRef.current.cancel();
        }
        setTimeout(() => setCurrentStep(0), 1000);
    }

    function pauseResumeTour() {
        const synth = synthRef.current;
        if (!synth) return;
        if (synth.paused) { synth.resume(); setBotState('speaking'); }
        else if (synth.speaking) { synth.pause(); setBotState('idle'); }
    }

    function endTour() {
        setIsActive(false);
        setBotState('idle');
        setCurrentStep(-1);
        if (synthRef.current) synthRef.current.cancel();
        document.querySelectorAll('.tour-highlight').forEach(el => el.classList.remove('tour-highlight'));
    }

    if (!isActive) return null;

    // ── Character Selection ──────────────────────────────────────────────────
    if (currentStep === -1) {
        return (
            <div className="fixed inset-0 z-[100] flex items-center justify-center bg-gray-900/60 backdrop-blur-sm p-4 fade-in">
                <div className="bg-white dark:bg-gray-800 rounded-2xl p-8 max-w-3xl w-full border border-gray-200 dark:border-gray-700 shadow-2xl relative overflow-hidden">
                    <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-blue-500 via-purple-500 to-orange-500"></div>
                    <button onClick={endTour} className="absolute top-4 right-4 text-gray-400 hover:text-red-500 transition-colors">
                        <XIcon size={24} />
                    </button>
                    <h2 className="text-3xl font-bold text-center text-gray-900 dark:text-white mb-2">Choose Your AI Guide</h2>
                    <p className="text-center text-gray-500 dark:text-gray-400 mb-8 max-w-xl mx-auto">
                        Select a persona to lead you through an interactive demonstration of the Omni-Agent AI Platform.
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                        {([
                            { type: 'genesis', color: 'blue',   label: GUIDE_NAMES.genesis,   desc: 'Friendly, enthusiastic, and highly analytical. A complete operational overview of every feature.' },
                            { type: 'athena',  color: 'purple', label: GUIDE_NAMES.athena,    desc: 'Sleek and strategic. An executive-level guide focused on governance, ROI, and business risk.' },
                            { type: 'nexus',   color: 'orange', label: GUIDE_NAMES.nexus,     desc: 'Deep and technical. Architecture walk-through covering data pipelines, APIs, and engineering decisions.' },
                            { type: 'heartbot',color: 'pink',   label: GUIDE_NAMES.heartbot,  desc: 'Warm and caring. Explains every feature through the lens of protecting people and organizations.' },
                            { type: 'nova',    color: 'teal',   label: GUIDE_NAMES.nova,      desc: 'Energetic and expressive. A high-speed, excitement-packed tour of all 28 key platform capabilities.' },
                        ] as const).map(({ type, color, label, desc }) => (
                            <div
                                key={type}
                                onClick={() => selectCharacterAndStart(type)}
                                className={`flex flex-col items-center justify-center p-4 border-2 border-gray-100 dark:border-gray-700 rounded-xl hover:border-${color}-500 hover:bg-${color}-50 dark:hover:bg-${color}-900/20 cursor-pointer transition-all hover:scale-105 group`}
                            >
                                <div className="w-24 h-24 mb-4 relative z-0">
                                    <MascotCharacter botState="idle" type={type} className="w-full h-full pointer-events-none" />
                                </div>
                                <h3 className={`text-lg font-bold text-center text-gray-900 dark:text-white group-hover:text-${color}-600 dark:group-hover:text-${color}-400`}>{label}</h3>
                                <p className="text-xs text-center text-gray-500 dark:text-gray-400 mt-2">{desc}</p>
                                <span className="mt-3 text-xs font-semibold text-gray-400">{SCRIPTS[type].length} steps</span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        );
    }

    // ── Active Tour ──────────────────────────────────────────────────────────
    const borderColor = characterType === 'athena' ? 'border-purple-500/30' : characterType === 'nexus' ? 'border-orange-500/30' : characterType === 'heartbot' ? 'border-pink-500/30' : characterType === 'nova' ? 'border-teal-500/30' : 'border-blue-500/30';
    const gradientColor = characterType === 'athena' ? 'from-pink-500 to-purple-500' : characterType === 'nexus' ? 'from-amber-500 to-orange-500' : characterType === 'heartbot' ? 'from-pink-400 to-rose-500' : characterType === 'nova' ? 'from-teal-400 to-cyan-500' : 'from-blue-500 to-cyan-500';

    return (
        <div className="fixed bottom-24 right-28 z-50 flex items-end space-x-4 pointer-events-none fade-in">
            <MascotCharacter botState={botState} type={characterType} onClick={pauseResumeTour} className="pointer-events-auto" />
            <div className={`bg-white dark:bg-gray-800 rounded-2xl rounded-bl-none shadow-2xl p-4 mb-4 mt-8 max-w-sm border ${borderColor} transform transition-all duration-300 animate-in fade-in slide-in-from-left-4 pointer-events-auto relative overflow-hidden`}>
                <div className={`absolute top-0 left-0 w-full h-1 bg-gradient-to-r ${gradientColor}`}></div>
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">{GUIDE_NAMES[characterType]}</p>
                <p className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed font-medium">
                    "{script[currentStep]?.text}"
                </p>
                <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
                    <div className="flex items-center space-x-2">
                        <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider">
                            {currentStep + 1} / {script.length}
                        </span>
                        <div className="w-24 h-1 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                            <div
                                className={`h-full bg-gradient-to-r ${gradientColor} transition-all duration-500`}
                                style={{ width: `${((currentStep + 1) / script.length) * 100}%` }}
                            />
                        </div>
                    </div>
                    <div className="flex space-x-2">
                        <button
                            onClick={pauseResumeTour}
                            className="p-1.5 text-gray-500 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-gray-700 rounded-md transition-colors"
                            title={synthRef.current?.paused ? 'Resume' : 'Pause'}
                        >
                            {synthRef.current?.paused ? <PlayIcon size={14} /> : <PauseIcon size={14} />}
                        </button>
                        <button
                            onClick={endTour}
                            className="p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors"
                            title="End Tour"
                        >
                            <XIcon size={14} />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};
