export interface FeatureHelp {
  title: string;
  description: string;
  capabilities: string[];
  audience?: string;
}

const defaultHelp: FeatureHelp = {
  title: 'Feature Help',
  description: 'This feature is part of the Enterprise Omni-Agent AI Platform. Use the navigation to explore its capabilities.',
  capabilities: ['View and manage data', 'Configure settings', 'Export reports'],
};

export const featureHelpContent: Record<string, FeatureHelp> = {
  // ── Core Dashboards ───────────────────────────────────────────────────────
  dashboard: {
    title: 'Main Dashboard',
    description: 'Central command center showing real-time metrics across your entire security posture — agent health, active alerts, compliance scores, and AI system status at a glance.',
    capabilities: ['Executive KPI overview', 'Critical alert feed', 'Compliance status summary', 'AI system health indicators', 'Quick navigation tiles'],
    audience: 'All users',
  },
  cxoDashboard: {
    title: 'CXO Dashboard',
    description: 'Executive-level view aggregating business risk, cost exposure, compliance posture, and security trends. Designed for board-level reporting and strategic decision-making.',
    capabilities: ['Business risk score', 'Cloud spend analysis', 'Compliance posture overview', 'Trend forecasting', 'Board-ready export'],
    audience: 'C-level executives and senior management',
  },
  reporting: {
    title: 'Reporting Dashboard',
    description: 'Historical data visualization and custom report builder. Schedule automated report delivery via email or generate on-demand exports in PDF and Excel formats.',
    capabilities: ['Custom date range filtering', 'Multi-format export (PDF, Excel)', 'Scheduled report delivery', 'Asset and vulnerability trending', 'Compliance report generation'],
    audience: 'Security managers, compliance teams',
  },

  // ── Agents & Assets ───────────────────────────────────────────────────────
  agents: {
    title: 'Agents Dashboard',
    description: 'Manage and monitor all deployed Omni-Agents across your infrastructure. View real-time health, trigger diagnostics, authorize autonomous remediation, and remotely control endpoints.',
    capabilities: ['Agent health monitoring', 'Remote command execution', 'Autonomous remediation authorization', 'Agent self-healing and auto-update', 'Bulk upgrade management', 'Agent quarantine and release'],
    audience: 'Security operations, IT operations',
  },
  assets: {
    title: 'Asset Management',
    description: 'Complete inventory of all IT assets discovered and tracked by your agents. Correlates hardware, software, vulnerabilities, and compliance status for each asset.',
    capabilities: ['Asset discovery and inventory', 'Vulnerability correlation', 'On-demand scan triggering', 'Software inventory tracking', 'Asset risk scoring'],
    audience: 'IT administrators, security teams',
  },
  patching: {
    title: 'Patch Management',
    description: 'Full patch lifecycle management for Windows and Linux systems. Track CVEs, schedule deployments, manage approvals, and roll back failed patches with complete audit trails.',
    capabilities: ['CVE patch tracking', 'Staged deployment workflows', 'Approval gates and scheduling', 'Rollback support', 'Compliance tracking', 'ML-based failure prediction'],
    audience: 'IT operations, security engineers',
  },
  software: {
    title: 'Software Inventory',
    description: 'Comprehensive catalog of installed software across all managed endpoints. Identifies outdated packages, license compliance issues, and shadow software installations.',
    capabilities: ['Software version tracking', 'Outdated package detection', 'License compliance analysis', 'Shadow software identification'],
    audience: 'IT administrators, compliance teams',
  },

  // ── Security Operations ───────────────────────────────────────────────────
  security: {
    title: 'Security Operations Center',
    description: 'Central hub for managing security incidents, events, and cases. Correlates alerts across all detection layers, executes playbooks, and provides AI-assisted triage and investigation.',
    capabilities: ['Security case management', 'Alert correlation and triage', 'AI-assisted investigation', 'Playbook execution', 'Event timeline visualization', 'Impact analysis triggering'],
    audience: 'Security analysts, SOC teams',
  },
  threatHunting: {
    title: 'Threat Hunting',
    description: 'Proactive threat discovery using UEBA behavioral analytics and AI-driven hunt queries. Identify advanced persistent threats before they trigger traditional alerts.',
    capabilities: ['UEBA behavioral analysis', 'AI hunt query interface', 'Anomaly timeline visualization', 'Hunt hypothesis management', 'IoC correlation'],
    audience: 'Threat hunters, senior security analysts',
  },
  threatIntelligence: {
    title: 'Threat Intelligence',
    description: 'Live threat intelligence feed aggregating IOCs from VirusTotal, URLhaus, MalwareBazaar, and AlienVault OTX. Scan IPs, domains, URLs, and file hashes for known threats.',
    capabilities: ['VirusTotal artifact scanning', 'Multi-source IOC feed (URLhaus, MalwareBazaar, OTX)', 'Auto-detection of artifact type', 'IOC enrichment for security events', 'Feed export'],
    audience: 'Threat intelligence analysts, SOC teams',
  },
  ueba: {
    title: 'UEBA — User & Entity Behavior Analytics',
    description: 'Detects insider threats and account compromise through multi-rule behavioral analysis. Monitors 10+ behavioral patterns including brute force, impossible travel, mass downloads, and shadow AI usage.',
    capabilities: ['10-rule behavioral engine', 'Risk scoring (0–100)', 'Impossible travel detection', 'Brute force detection with auto-IP ban', 'Shadow AI usage detection', 'Blockchain-backed audit trail'],
    audience: 'Security analysts, compliance teams',
  },
  edr: {
    title: 'Endpoint Detection & Response (EDR)',
    description: 'Real-time telemetry collection and threat detection at the endpoint level. Detects process injection, persistence mechanisms, and runtime anomalies across all managed agents.',
    capabilities: ['Real-time endpoint telemetry', 'Process injection detection', 'File Integrity Monitoring (FIM)', 'Runtime security monitoring', 'Automated alert generation'],
    audience: 'Security operations, incident responders',
  },
  mdr: {
    title: 'Managed Detection & Response (MDR)',
    description: 'Managed security service layer providing 24/7 monitoring, threat containment, and guided response. Combines automated detection with expert-driven investigation workflows.',
    capabilities: ['24/7 threat monitoring', 'Automated containment actions', 'Guided response playbooks', 'SLA-tracked case management', 'Expert escalation workflows'],
    audience: 'Security managers, managed service operators',
  },
  xdr: {
    title: 'Extended Detection & Response (XDR)',
    description: 'Unified detection and response across endpoints, network, cloud, and identity layers. Correlates signals from all security controls into a single, prioritized incident view.',
    capabilities: ['Cross-layer signal correlation', 'Unified incident timeline', 'Network + endpoint + cloud integration', 'AI-driven attack chain reconstruction', 'Automated response orchestration'],
    audience: 'SOC teams, security architects',
  },
  soar: {
    title: 'Security Orchestration & Automation (SOAR)',
    description: 'Automates security response workflows by orchestrating actions across integrated tools. Build, test, and execute playbooks that span multiple security systems without manual intervention.',
    capabilities: ['Visual playbook builder', 'Multi-system action orchestration', 'Automated case creation', 'Integration with 50+ security tools', 'Response metrics and reporting'],
    audience: 'SOC engineers, security automation teams',
  },
  incidentImpact: {
    title: 'Incident Impact Analysis',
    description: 'Blast radius assessment for active security incidents. Maps affected systems, quantifies business impact, and identifies lateral movement paths to prioritize containment.',
    capabilities: ['Affected system mapping', 'Business impact quantification', 'Lateral movement path visualization', 'Containment recommendation', 'Executive impact summary'],
    audience: 'Incident responders, security managers',
  },
  attackPath: {
    title: 'Attack Path Analysis',
    description: 'Visualizes the most likely paths an attacker could take to reach critical assets. Identifies choke points, high-risk exposures, and optimal remediation steps to reduce attack surface.',
    capabilities: ['Graph-based attack path visualization', 'Critical asset exposure scoring', 'Choke point identification', 'Remediation priority ranking', 'MITRE ATT&CK mapping'],
    audience: 'Security architects, penetration testers',
  },
  pentest: {
    title: 'Penetration Testing',
    description: 'Manage and track penetration test engagements. Integrates external pentesting tools (Nmap, OWASP ZAP, Nuclei) and correlates findings with existing vulnerability data.',
    capabilities: ['Engagement lifecycle management', 'External tool orchestration (Nmap, ZAP, Nuclei)', 'Finding deduplication', 'Vulnerability correlation', 'Report generation'],
    audience: 'Penetration testers, red team, security engineers',
  },
  persistence: {
    title: 'Persistence Detection',
    description: 'Detects and inventories persistence mechanisms installed by attackers or malware — registry run keys, scheduled tasks, startup items, and service modifications.',
    capabilities: ['Registry persistence detection', 'Scheduled task monitoring', 'Startup item tracking', 'Service modification alerts', 'Cross-platform (Windows/Linux)'],
    audience: 'Threat hunters, incident responders',
  },
  deception: {
    title: 'Deception Technology',
    description: 'Deploys honeypots, honey tokens, and deceptive assets to lure and detect attackers inside your network. Any interaction with a deception asset is a high-fidelity alert.',
    capabilities: ['Honeypot deployment', 'Honey token tracking', 'Deceptive credential alerts', 'Lateral movement detection', 'Zero false-positive alerts'],
    audience: 'Security operations, threat hunters',
  },
  insiderThreat: {
    title: 'Insider Threat Detection',
    description: 'Identifies malicious or negligent insider behavior through behavioral analytics, data access patterns, and anomalous activity scoring — without invasive monitoring.',
    capabilities: ['Behavioral baseline profiling', 'Data exfiltration detection', 'Privileged access abuse detection', 'Risk scoring and trending', 'Privacy-respecting monitoring'],
    audience: 'Security teams, HR and compliance',
  },
  emailSecurity: {
    title: 'Email Security',
    description: 'Monitors email-based threats including phishing, business email compromise, and malicious attachments. Integrates with email gateways to provide header analysis and link inspection.',
    capabilities: ['Phishing detection', 'BEC attack indicators', 'Attachment sandbox analysis', 'Header inspection', 'Domain spoofing alerts'],
    audience: 'Security analysts, IT administrators',
  },
  supplyChain: {
    title: 'Supply Chain Security',
    description: 'Monitors third-party software dependencies and vendor relationships for supply chain attack vectors. Tracks CVEs in open-source packages and flags compromised dependencies.',
    capabilities: ['Dependency vulnerability tracking', 'Vendor risk scoring', 'Package integrity verification', 'SBOM correlation', 'Compromised dependency alerts'],
    audience: 'DevSecOps, security architects',
  },

  // ── Compliance & Governance ───────────────────────────────────────────────
  compliance: {
    title: 'Compliance Dashboard',
    description: 'Track compliance posture across multiple frameworks — SOC 2, ISO 27001, HIPAA, PCI-DSS, GDPR, and more. Collect evidence, manage controls, and generate audit-ready reports.',
    capabilities: ['Multi-framework support (SOC2, ISO27001, HIPAA, PCI-DSS)', 'Control tracking and evidence collection', 'AI-assisted evidence analysis', 'Compliance scoring', 'Automated report generation'],
    audience: 'Compliance teams, auditors, security managers',
  },
  aiGovernance: {
    title: 'AI Governance',
    description: 'Inventory, risk-assess, and govern all AI systems in your organization. Track model lifecycle, ethics compliance, bias metrics, and shadow AI deployments.',
    capabilities: ['AI system inventory', 'Model risk assessment', 'Ethics and bias tracking', 'Shadow AI detection', 'Model approval workflows', 'Regulatory compliance (EU AI Act)'],
    audience: 'AI governance teams, compliance, executives',
  },
  dspm: {
    title: 'Data Security Posture Management (DSPM)',
    description: 'Discovers, classifies, and monitors sensitive data across cloud storage and databases. Identifies over-permissioned data stores and PII exposure risks.',
    capabilities: ['Sensitive data discovery', 'PII/PHI/PCI classification', 'Over-permission detection', 'Data flow mapping', 'Risk remediation guidance'],
    audience: 'Data security teams, privacy officers',
  },
  sbom: {
    title: 'Software Bill of Materials (SBOM)',
    description: 'Generates and manages SBOMs for all software assets. Tracks component licenses, vulnerability exposure, and dependency trees to support supply chain compliance.',
    capabilities: ['SBOM generation (SPDX, CycloneDX)', 'License compliance tracking', 'Vulnerable component identification', 'Dependency tree visualization', 'Export for audits'],
    audience: 'DevSecOps, compliance, procurement',
  },
  dataGovernance: {
    title: 'Data Governance',
    description: 'Establishes policies, ownership, and quality standards for organizational data. Manages data lineage, retention policies, and access controls to ensure regulatory compliance.',
    capabilities: ['Data policy management', 'Ownership and stewardship', 'Data lineage tracking', 'Quality monitoring', 'Retention enforcement'],
    audience: 'Data governance teams, compliance',
  },
  privacyConsent: {
    title: 'Privacy & Consent Management',
    description: 'Tracks user consent, data subject rights requests, and privacy compliance across all data processing activities. Monitors GDPR, CCPA, and other privacy regulation adherence.',
    capabilities: ['Consent tracking and audit trail', 'Data subject rights (DSR) management', 'Privacy impact assessments', 'GDPR/CCPA compliance monitoring', 'Consent revocation handling'],
    audience: 'Privacy officers, compliance teams, legal',
  },
  complianceFrameworks: {
    title: 'Compliance Frameworks',
    description: 'Custom compliance framework builder. Define your own control families, map evidence to controls, and track compliance against internal policies or industry-specific standards.',
    capabilities: ['Custom framework creation', 'Control mapping and inheritance', 'Evidence attachment', 'Gap analysis', 'Framework export'],
    audience: 'Compliance architects, auditors',
  },
  pam: {
    title: 'Privileged Access Management (PAM)',
    description: 'Vaults, controls, and monitors privileged account usage across servers, databases, and cloud resources. Enforces least-privilege and records all privileged sessions.',
    capabilities: ['Credential vaulting', 'Session recording and playback', 'Least-privilege enforcement', 'Privileged account discovery', 'Access request workflows'],
    audience: 'IT administrators, security teams',
  },
  jitAccess: {
    title: 'Just-In-Time (JIT) Privileged Access',
    description: 'Eliminates standing privileges by granting time-bound elevated access only when needed. Access is automatically revoked after the approved window, reducing attack surface.',
    capabilities: ['Time-bound access grants', 'Approval workflow', 'Automatic revocation', 'Session monitoring', 'Audit trail'],
    audience: 'IT administrators, security teams',
  },

  // ── Operations & Automation ───────────────────────────────────────────────
  automation: {
    title: 'Automation Policies',
    description: 'Define event-driven automation rules that trigger actions across your security stack. Connect detection signals to response actions without manual intervention.',
    capabilities: ['Policy-as-code editor', 'Event trigger configuration', 'Multi-action orchestration', 'Condition-based branching', 'Policy version history'],
    audience: 'Security engineers, DevSecOps',
  },
  playbooks: {
    title: 'Playbooks',
    description: 'Pre-built and custom incident response playbooks that standardize and accelerate response workflows. Build visual playbooks with drag-and-drop actions and conditional logic.',
    capabilities: ['Visual playbook builder', 'Pre-built playbook library', 'Conditional logic and branching', 'Integration with 50+ tools', 'Execution logging and metrics'],
    audience: 'SOC analysts, security engineers',
  },
  rollback: {
    title: 'Rollback & Checkpoints',
    description: 'System-level checkpoint management for safe rollback of configuration changes, patch deployments, and automated actions. Maintain a recoverable state before any risky operation.',
    capabilities: ['Automatic checkpoint creation', 'One-click rollback', 'Change diff visualization', 'Scheduled checkpoint policies', 'Audit trail for all rollbacks'],
    audience: 'IT operations, change management teams',
  },
  changeManagement: {
    title: 'Change Management',
    description: 'Structured workflow for proposing, reviewing, approving, and auditing all infrastructure and security changes. Integrates with ticketing systems and enforces change windows.',
    capabilities: ['Change request lifecycle', 'Approval workflows', 'Change window enforcement', 'Risk assessment', 'Post-change verification'],
    audience: 'IT operations, ITSM teams',
  },
  chaosEngineering: {
    title: 'Chaos Engineering',
    description: 'Proactively test system resilience by injecting controlled failures. Design and run chaos experiments to identify weaknesses before they cause production incidents.',
    capabilities: ['Experiment designer', 'Failure injection library', 'Blast radius controls', 'Resilience scoring', 'Hypothesis tracking'],
    audience: 'SRE, platform engineering, security teams',
  },
  jobs: {
    title: 'Jobs',
    description: 'View and manage all background tasks, scheduled operations, and async jobs across the platform. Monitor execution status, retry failed jobs, and review job history.',
    capabilities: ['Job queue monitoring', 'Execution status tracking', 'Manual retry and cancellation', 'Scheduled job management', 'Execution history'],
    audience: 'Platform administrators, IT operations',
  },

  // ── Observability ─────────────────────────────────────────────────────────
  logs: {
    title: 'Log Explorer',
    description: 'Full-text search and analysis across all agent, system, and application logs. Supports regex queries, time-based filtering, and structured log parsing.',
    capabilities: ['Full-text search', 'Regex query support', 'Time-based filtering', 'Log level filtering', 'Export to SIEM'],
    audience: 'Security analysts, DevOps engineers',
  },
  tracing: {
    title: 'Distributed Tracing',
    description: 'End-to-end request tracing across distributed services. Identify latency bottlenecks, failed service calls, and performance regressions in microservice architectures.',
    capabilities: ['Service dependency mapping', 'Trace waterfall visualization', 'Latency percentile analysis', 'Error rate tracking', 'Performance bottleneck identification'],
    audience: 'Platform engineers, DevOps, SRE',
  },
  networkObservability: {
    title: 'Network Observability',
    description: 'Real-time visibility into network traffic, device health, and connectivity across your infrastructure. Detects anomalous traffic patterns and unauthorized connections.',
    capabilities: ['Network device monitoring', 'Traffic flow analysis', 'Anomalous connection detection', 'Bandwidth utilization', 'Network topology mapping'],
    audience: 'Network engineers, security operations',
  },
  systemHealth: {
    title: 'System Health',
    description: 'Platform-level health monitoring for all backend services, database connections, and agent communication channels. Diagnose and resolve platform issues proactively.',
    capabilities: ['Backend service health checks', 'Database connection monitoring', 'Agent communication status', 'API latency tracking', 'Platform uptime metrics'],
    audience: 'Platform administrators',
  },
  predictiveHealth: {
    title: 'Predictive Health Analytics',
    description: 'Machine learning-powered predictions for agent and system health. Forecasts potential failures, patch deployment risks, and resource exhaustion before they occur.',
    capabilities: ['ML-based failure prediction (Random Forest)', 'Anomaly detection (Isolation Forest)', 'Resource exhaustion forecasting', 'Patch risk scoring', 'Recommendation engine'],
    audience: 'IT operations, security engineers',
  },
  streamingDashboard: {
    title: 'Real-Time Streaming',
    description: 'Live event streaming dashboard showing events per second, latency metrics, and stream processing health. Monitors the real-time data pipeline that powers all live alerts.',
    capabilities: ['Events-per-second metrics', 'Latency monitoring', 'Stream processing status', 'Consumer group health', 'Backlog alerting'],
    audience: 'Platform engineers, DevOps',
  },

  // ── Cloud & Infrastructure ────────────────────────────────────────────────
  cloudSecurity: {
    title: 'Cloud Security Posture (CSPM)',
    description: 'Continuous monitoring of cloud infrastructure security configuration across AWS, Azure, and GCP. Identifies misconfigurations, policy violations, and compliance gaps.',
    capabilities: ['Multi-cloud support (AWS, Azure, GCP)', 'Misconfiguration detection', 'CIS benchmark compliance', 'Remediation guidance', 'Cloud resource inventory'],
    audience: 'Cloud security teams, DevSecOps',
  },
  cloudIntegrations: {
    title: 'Cloud Integrations',
    description: 'Connect and manage cloud account credentials for AWS, Azure, GCP, and other providers. Configure automated scanning, data ingestion, and cross-cloud visibility.',
    capabilities: ['Cloud account onboarding', 'Credential management', 'Automated scan scheduling', 'Cross-account visibility', 'IAM role configuration'],
    audience: 'Cloud architects, IT administrators',
  },
  secretsManagement: {
    title: 'Secrets Management',
    description: 'Centralized vault for storing and accessing API keys, database credentials, certificates, and other secrets. Enforces rotation policies and audit-trails all access.',
    capabilities: ['Encrypted secret storage', 'Rotation policy enforcement', 'Access audit trail', 'Integration with apps and CI/CD', 'Secret leak detection'],
    audience: 'DevSecOps, developers, IT administrators',
  },
  hadr: {
    title: 'HA/DR & Backups',
    description: 'High-availability and disaster recovery configuration for the platform. Manage backup schedules, test recovery procedures, and monitor replication health.',
    capabilities: ['Backup schedule management', 'Recovery time objective (RTO) tracking', 'Replication health monitoring', 'Restore testing', 'Failover configuration'],
    audience: 'Platform administrators, IT operations',
  },
  retentionPolicy: {
    title: 'Data Retention',
    description: 'Configure and enforce data retention policies across logs, events, and compliance evidence. Automate data archival and deletion to meet regulatory requirements.',
    capabilities: ['Per-data-type retention rules', 'Automated archival', 'Compliance-driven deletion', 'Retention policy audit', 'GDPR/HIPAA retention templates'],
    audience: 'Compliance teams, data governance, legal',
  },
  certificates: {
    title: 'Certificate Management',
    description: 'Track TLS/SSL certificate inventory across all domains and services. Get alerts before expiry, manage certificate lifecycle, and detect unauthorized certificates.',
    capabilities: ['Certificate expiry tracking', 'Automated renewal alerts', 'Domain coverage visualization', 'Unauthorized certificate detection', 'Certificate chain validation'],
    audience: 'IT administrators, security teams',
  },

  // ── AI & ML ───────────────────────────────────────────────────────────────
  mlOps: {
    title: 'MLOps',
    description: 'Machine learning operations management — monitor model performance, track experiments, manage model versions, and deploy updates with approval workflows.',
    capabilities: ['Model performance monitoring', 'Experiment tracking', 'Model versioning and registry', 'Approval-gated deployment', 'Drift detection'],
    audience: 'Data scientists, ML engineers',
  },
  modelTraining: {
    title: 'Model Training',
    description: 'Initiate and monitor ML model training runs for patch failure prediction and anomaly detection. Track training progress, accuracy metrics, and model artifact storage.',
    capabilities: ['Training job management', 'Real-time training metrics', 'Model accuracy tracking', 'Synthetic seed data fallback', 'Artifact storage (backend/models/)'],
    audience: 'Data scientists, security engineers',
  },
  modelMonitoring: {
    title: 'Model Monitoring',
    description: 'Continuous monitoring of deployed ML models for performance degradation, prediction drift, and data quality issues. Triggers retraining alerts when thresholds are breached.',
    capabilities: ['Prediction accuracy tracking', 'Feature drift detection', 'Data quality monitoring', 'Retraining trigger alerts', 'Model comparison dashboard'],
    audience: 'Data scientists, ML engineers',
  },
  automl: {
    title: 'AutoML',
    description: 'Automated machine learning pipeline that selects, trains, and optimizes models without manual feature engineering. Accelerates model development for security use cases.',
    capabilities: ['Automated feature selection', 'Hyperparameter optimization', 'Model comparison', 'One-click deployment', 'Explainability reports'],
    audience: 'Data scientists, security analysts',
  },
  aiRemediation: {
    title: 'AI Remediation',
    description: 'AI-powered autonomous remediation service that executes approved response actions on agents. Manages the confidence threshold, blast-radius controls, and human approval gates.',
    capabilities: ['Confidence-gated action execution', 'Blast-radius controls', 'Human approval gate', 'Remediation outcome tracking', 'Forbidden action blocklist'],
    audience: 'Security operations, platform administrators',
  },
  xai: {
    title: 'Explainable AI (XAI)',
    description: 'Provides human-readable explanations for AI-driven security decisions. Understand why the AI flagged an alert, recommended a remediation, or predicted a patch failure.',
    capabilities: ['Decision explanation engine', 'Feature importance visualization', 'Confidence score breakdown', 'Alert reasoning trails', 'Model audit reports'],
    audience: 'Security analysts, compliance teams, auditors',
  },

  // ── DevSecOps ─────────────────────────────────────────────────────────────
  devSecOps: {
    title: 'DevSecOps',
    description: 'Integrates security into the development pipeline. Manages SBOM, SAST findings, container scans, and IaC security from a single pane of glass.',
    capabilities: ['SBOM generation and tracking', 'SAST findings management', 'Container image scanning', 'IaC security analysis', 'Developer security portal'],
    audience: 'Developers, DevSecOps engineers, security teams',
  },
  sast: {
    title: 'Static Application Security Testing (SAST)',
    description: 'Analyzes source code and binaries for security vulnerabilities without executing the application. Integrates with CI/CD to catch issues before deployment.',
    capabilities: ['Source code vulnerability scanning', 'CI/CD integration', 'False positive management', 'CWE/OWASP mapping', 'Developer remediation guidance'],
    audience: 'Developers, DevSecOps engineers',
  },
  pipelineSecurity: {
    title: 'Pipeline Security',
    description: 'Monitors and enforces security policies across CI/CD pipelines. Detects secrets in code, insecure configurations, and unauthorized pipeline modifications.',
    capabilities: ['Secret detection in pipelines', 'Pipeline configuration analysis', 'Unauthorized modification alerts', 'Dependency check integration', 'Policy-as-code enforcement'],
    audience: 'DevSecOps, platform engineers',
  },
  containerScan: {
    title: 'Container Security Scanning',
    description: 'Scans container images for vulnerabilities, malware, and misconfigurations before and after deployment. Monitors running containers for runtime threats.',
    capabilities: ['Image layer scanning', 'Base image vulnerability detection', 'Runtime anomaly detection', 'Registry integration', 'Kubernetes admission control'],
    audience: 'DevSecOps, cloud engineers',
  },
  codeReviewGraph: {
    title: 'Code Review Graph',
    description: 'Graph-based visualization of code ownership, review patterns, and security risk concentration across repositories. Identifies high-risk code areas with low review coverage.',
    capabilities: ['Code ownership mapping', 'Review coverage heatmaps', 'Security risk concentration', 'Reviewer recommendation', 'PR risk scoring'],
    audience: 'Engineering managers, security architects',
  },
  apiSecurity: {
    title: 'API Security',
    description: 'Discovers, inventories, and monitors all APIs across your organization. Detects exposed sensitive data, broken authentication, and API abuse patterns.',
    capabilities: ['API discovery and inventory', 'Sensitive data exposure detection', 'Authentication weakness detection', 'Rate limiting abuse monitoring', 'OWASP API Top 10 coverage'],
    audience: 'API developers, security engineers',
  },

  // ── Platform Management ───────────────────────────────────────────────────
  settings: {
    title: 'Settings & Configuration',
    description: 'Central configuration hub for integrations, alert rules, user management, API keys, email notifications, and platform appearance. Tenant admins and super admins can customize their environment.',
    capabilities: ['Email notification SMTP configuration', 'Integration marketplace', 'Alert rule management', 'User and role management', 'API key generation', 'Dark mode and appearance'],
    audience: 'Tenant admins, super admins',
  },
  tenantManagement: {
    title: 'Tenant Management',
    description: 'Create, configure, and manage all tenants in the multi-tenant platform. Set subscription tiers, enable/disable features, and monitor per-tenant usage and health.',
    capabilities: ['Tenant creation and deletion', 'Subscription tier management', 'Feature flag control', 'Per-tenant agent and asset counts', 'Tenant impersonation'],
    audience: 'Super admins only',
  },
  finops: {
    title: 'FinOps & Billing',
    description: 'Track cloud and platform spending across all tenants. Manage budgets, view invoices, analyze cost trends, and optimize resource allocation to reduce waste.',
    capabilities: ['Cost tracking by tenant and service', 'Budget management and alerts', 'Invoice history', 'Cost optimization recommendations', 'Multi-cloud cost aggregation'],
    audience: 'Finance teams, executives, platform admins',
  },
  auditLog: {
    title: 'Audit Log',
    description: 'Immutable, tamper-evident audit trail of all user actions and system events. SHA-256 hash-chained records ensure no log entry can be altered or deleted without detection.',
    capabilities: ['Comprehensive action logging', 'SHA-256 hash chain integrity', 'Tenant-scoped filtering', 'Action rollback support', 'Export for compliance audits'],
    audience: 'Compliance teams, security managers, auditors',
  },
  webhooks: {
    title: 'Webhook Management',
    description: 'Configure outbound webhooks to notify external systems of security events, compliance changes, and platform alerts. Supports Slack, Teams, PagerDuty, and custom endpoints.',
    capabilities: ['Event subscription management', 'Slack, Teams, PagerDuty integration', 'Custom endpoint configuration', 'Delivery monitoring and retry', 'SSRF-protected URL validation'],
    audience: 'Security engineers, platform administrators',
  },
  notificationPrefs: {
    title: 'Notification Preferences',
    description: 'Configure your personal notification channels and event subscriptions. Choose which security events, ticket updates, and platform alerts you receive via email, Slack, or Teams.',
    capabilities: ['Per-channel toggle (email, Slack, Teams)', 'Per-event subscription control', 'Ticket event notifications', 'SLA breach alerts', 'Preference persistence across sessions'],
    audience: 'All users',
  },

  // ── Analytics ─────────────────────────────────────────────────────────────
  dora: {
    title: 'DORA Metrics',
    description: 'Tracks the four key DORA DevOps metrics: deployment frequency, lead time for changes, mean time to recovery, and change failure rate across all development teams.',
    capabilities: ['Deployment frequency tracking', 'Lead time measurement', 'MTTR calculation', 'Change failure rate trending', 'Team comparison benchmarks'],
    audience: 'Engineering managers, DevOps teams',
  },
  dataWarehouse: {
    title: 'Data Warehouse',
    description: 'Long-term analytics storage and query interface for all platform data. Run custom analytical queries across historical security events, compliance records, and operational metrics.',
    capabilities: ['Historical data queries', 'Custom analytical dashboards', 'Cross-dataset joins', 'Data export (CSV, Parquet)', 'Scheduled query reports'],
    audience: 'Data analysts, security researchers',
  },
  advancedBi: {
    title: 'Advanced BI Dashboard',
    description: 'Business intelligence visualizations combining security, operational, and financial data. Build custom charts, pivot tables, and KPI scorecards for strategic reporting.',
    capabilities: ['Custom chart builder', 'Pivot tables', 'KPI scorecard creation', 'Multi-dataset visualization', 'Scheduled dashboard delivery'],
    audience: 'Analysts, managers, executives',
  },

  // ── Others ────────────────────────────────────────────────────────────────
  knowledgeBase: {
    title: 'Knowledge Base (RAG)',
    description: 'AI-powered knowledge management system using Retrieval-Augmented Generation. Upload documents, SOPs, and runbooks and query them in natural language for instant answers.',
    capabilities: ['Document ingestion and indexing', 'Natural language querying (RAG)', 'SOP and runbook storage', 'AI-assisted search', 'Knowledge gap detection'],
    audience: 'All security staff, analysts, administrators',
  },
  serviceCatalog: {
    title: 'Service Catalog',
    description: 'Pre-approved service templates and infrastructure blueprints. Provision new services through standardized, security-reviewed templates with automated compliance validation.',
    capabilities: ['Service template library', 'One-click provisioning', 'Compliance pre-validation', 'Deployment history', 'Template version management'],
    audience: 'Developers, platform engineers, IT operations',
  },
  goals: {
    title: 'Goal System',
    description: 'Define, decompose, and track operational and security goals. AI-powered goal decomposition breaks high-level objectives into actionable tasks dispatched to agents.',
    capabilities: ['Goal definition and decomposition', 'AI task breakdown', 'Progress tracking', 'Agent task dispatch', 'Goal approval workflows'],
    audience: 'Security managers, executives',
  },
  zeroTrustQuantum: {
    title: 'Zero Trust & Quantum Security',
    description: 'Monitors zero trust policy enforcement across your environment and assesses quantum-readiness of your cryptographic infrastructure for post-quantum migration planning.',
    capabilities: ['Zero trust policy visualization', 'Quantum-vulnerable algorithm detection', 'Post-quantum readiness scoring', 'Crypto inventory analysis', 'Compliance mapping (NIST PQC)'],
    audience: 'Security architects, CISOs',
  },
  sustainability: {
    title: 'Sustainability Dashboard',
    description: 'Tracks carbon footprint, energy consumption, and green computing metrics across cloud and on-premises infrastructure. Supports ESG reporting and sustainability goal setting.',
    capabilities: ['Carbon footprint tracking', 'Energy consumption metrics', 'Green computing recommendations', 'ESG report generation', 'Sustainability goal management'],
    audience: 'CISOs, sustainability teams, executives',
  },
  unifiedFutureOps: {
    title: '2030 Advanced Operations',
    description: 'Next-generation operations dashboard combining AIOps capacity predictions, real-time analytics, multi-cloud cost optimization, privacy management, and blockchain audit trails.',
    capabilities: ['AIOps capacity predictions', 'Real-time streaming analytics', 'Multi-cloud cost optimization', 'Privacy and consent tracking', 'Blockchain immutable audit chain'],
    audience: 'Platform architects, advanced operations teams',
  },
  supportTickets: {
    title: 'Support Tickets',
    description: 'Manage internal support requests and incidents. Create, assign, escalate, and resolve tickets with SLA tracking, collaboration threads, and integration with ITSM tools.',
    capabilities: ['Ticket lifecycle management', 'SLA breach alerting', 'Collaboration threads', 'ITSM integration (Jira, ServiceNow)', 'Priority and escalation rules'],
    audience: 'IT support teams, all users',
  },
  subscriptionManagement: {
    title: 'Subscription & Billing',
    description: 'View and manage your platform subscription tier, billing cycle, and payment methods. Upgrade or downgrade your plan, review invoices, and configure auto-renewal settings.',
    capabilities: ['Subscription plan management', 'Invoice history', 'Payment method management', 'Usage-based billing overview', 'Auto-renewal configuration'],
    audience: 'Tenant admins, finance teams',
  },
};

export { defaultHelp };
export default featureHelpContent;
