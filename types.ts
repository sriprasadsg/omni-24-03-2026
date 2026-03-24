
// This file will be populated with application-specific types as features are rebuilt.
export type Theme = 'light' | 'dark';

export type AppView =
  | 'dashboard'
  | 'riskRegister'
  | 'vendorManagement'
  | 'trustCenter'
  | 'secureFileShare'
  | 'securityTraining'
  | 'reporting'
  | 'agents'
  | 'agentCapabilities'
  | 'assetManagement'
  | 'patchManagement'
  | 'vulnerabilityManagement'
  | 'softwareUpdates'
  | 'cloudSecurity'
  | 'security'
  | 'compliance'
  | 'aiGovernance'
  | 'finops'
  | 'auditLog'
  | 'settings'
  | 'tenantManagement'
  | 'userManagement'
  | 'roleManagement'
  | 'apiKeys'
  | 'integrations'
  | 'notifications'
  | 'playbooks'
  | 'threatIntelligence'
  | 'proactiveInsights'
  | 'distributedTracing'
  | 'dataSecurity'
  | 'attackPath'
  | 'serviceCatalog'
  | 'doraMetrics'
  | 'chaosEngineering'
  | 'networkObservability'
  | 'servicePricing'
  | 'tasks'
  | 'softwareDeployment'
  | 'webhooks'
  | 'digitalTwin'
  | 'complianceOracle'
  | 'cissporacle'
  | 'sustainability'
  | 'llmops'
  | 'zeroTrustQuantum'
  | 'futureOps'
  | 'unifiedOps'
  | 'jobs'
  | 'securitySimulation'
  | 'persistenceDetection'
  | 'approvalWorkflows'
  | 'biDashboard'
  | 'systemHealth'
  | 'paymentSettings'
  | 'subscriptionManagement'
  | 'invoices'
  | 'dastFindings'
  | 'persistence'
  | 'securityAudit'
  | 'advancedBi'
  | 'cxo'
  | 'dataWarehouse'
  | 'swarm'
  | 'dast'
  | 'serviceMesh'
  | 'networkTopology'
  | 'automl'
  | 'xai'
  | 'abTesting'
  | 'logExplorer'
  | 'threatHunting'
  | 'profile'
  | 'automation'
  | 'devsecops'
  | 'sbom'
  | 'developer_hub'
  | 'incidentImpact'
  | 'streaming'
  | 'dataGovernance'
  | 'webMonitoring'
  | 'edr'
  | 'mlops'
  | 'mitreAttack'
  | 'dlp'
  | 'ticketing'
  | 'siem'
  | 'ueba'
  | 'vulnerabilities'
  | 'dataUtilization'
  | 'siemRules'
  | 'pentest'
  | 'incidentResponse';


export type Permission =
  | 'view:dashboard'
  | 'view:cxo_dashboard'
  | 'view:reporting'
  | 'export:reports'
  | 'view:agents'
  | 'view:software_deployment'
  | 'view:agent_logs'
  | 'remediate:agents'
  | 'view:assets'
  | 'view:patching'
  | 'manage:patches'
  | 'view:security'
  | 'manage:security_cases'
  | 'manage:security_playbooks'
  | 'investigate:security'
  | 'view:compliance'
  | 'manage:compliance_evidence'
  | 'view:ai_governance'
  | 'manage:ai_risks'
  | 'manage:settings'
  | 'manage:tenants'
  | 'view:cloud_security'
  | 'view:finops'
  | 'view:audit_log'
  | 'manage:rbac'
  | 'manage:api_keys'
  | 'view:logs'
  | 'view:threat_hunting'
  | 'view:profile'
  | 'view:automation'
  | 'manage:automation'
  | 'view:devsecops'
  | 'view:developer_hub'
  | 'view:insights'
  | 'view:tracing'
  // 2030 Vision Permissions
  | 'view:dspm'
  | 'view:attack_path'
  | 'view:service_catalog'
  | 'view:dora_metrics'
  | 'view:chaos'
  | 'view:network'
  | 'manage:pricing'
  | 'manage:playbooks'
  | 'view:software_updates'
  | 'view:sbom'
  | 'view:persistence'
  | 'view:vulnerabilities'
  | 'view:security_audit'
  | 'view:advanced_bi'
  | 'view:llmops'
  | 'view:unified_ops'
  | 'view:swarm'
  | 'service:compliance_soc2'
  | 'service:compliance_iso27001'
  | 'view:threat_intel'
  | 'view:sustainability'
  | 'view:zero_trust'
  | 'view:zero_trust'
  | 'view:jobs'
  | 'view:analytics'
  | 'view:governance'
  | 'view:mlops'
  | 'view:automl'
  | 'view:xai'
  | 'view:web_monitoring'
  | 'manage:experiments';


export type Filter = {
  type: string;
  value: string;
};

export type User = {
  id: string;
  tenantId: string;
  tenantName: string;
  name: string;
  email: string;
  // FIX: Added optional password to align with login logic.
  password?: string;
  role: string;
  avatar: string;
  status: 'Active' | 'Disabled';
  permissions?: Permission[];  // Added: permissions from backend
};

export type NewUserPayload = {
  name: string;
  email: string;
  role: string;
  tenantId: string;
  tenantName: string;
};

// FIX: Add NewTenantPayload to satisfy UserContext type requirements in App.tsx
export type NewTenantPayload = {
  name: string;
  email: string;
  password: string;
  companyName: string;
};

export type Role = {
  id: string;
  name: string;
  description: string;
  permissions: Permission[];
  isEditable: boolean;
  tenantId: string;
};

export type FinOpsData = {
  currentMonthCost: number;
  forecastedCost: number;
  potentialSavings: number;
  costBreakdown: { service: string, cost: number }[];
  costTrend: { month: string, actual: number, forecast: number }[];
};

export type SubscriptionTier = 'Free' | 'Pro' | 'Enterprise' | 'Custom';

export type Tenant = {
  id: string;
  name: string;
  subscriptionTier: SubscriptionTier;
  registrationKey: string;
  dataIngestionGB: number;
  apiCallsMillions: number;
  aiComputeVCPUHours: number;
  enabledFeatures: Permission[];
  apiKeys: ApiKey[];
  budget: { monthlyLimit: number };
  finOpsData?: FinOpsData;
  voiceBotSettings?: VoiceBotSettings;
  agentCount?: number;
};

export type MetricType = 'cpu' | 'memory' | 'disk' | 'network' | 'security_event';
export type MetricChangeType = 'increase' | 'decrease';

export interface MetricDataPoint {
  time: string;
  value: number;
}
export interface Metric {
  id: string;
  type: MetricType;
  title: string;
  value: string;
  change: string;
  changeType: MetricChangeType;
  data: MetricDataPoint[];
}

export type AlertSeverity = 'Critical' | 'High' | 'Medium' | 'Low';
export interface Alert {
  id: string;
  severity: AlertSeverity;
  message: string;
  source: string;
  timestamp: string;
}

export interface ComplianceFramework {
  id: string;
  name: string;
  shortName: string;
  description: string;
  status: 'Compliant' | 'Pending' | 'At Risk';
  progress: number;
  controls: Control[];
  nistFunctions?: NistFunction[];
}

export type ControlStatus = 'Implemented' | 'In Progress' | 'Not Implemented' | 'At Risk';

export interface Control {
  id: string;
  name: string;
  description: string;
  category?: string;
  status: ControlStatus;
  lastReviewed: string;
  evidence: { id: string, name: string, url: string }[];
  manual_evidence_instructions?: string;
}

export interface AssetComplianceEvidence {
  id: string;
  name: string;
  url: string;
  date: string;
}

export interface AssetCompliance {
  id: string;
  assetId: string;
  controlId: string;
  status: 'Compliant' | 'Non-Compliant' | 'Pending_Evidence';
  evidence: AssetComplianceEvidence[];
  lastUpdated: string;
  reason?: string;
  remediation?: string;
  ai_evaluation?: {
    verified: boolean;
    reasoning: string;
    evaluatedAt: string;
    model_used: string;
  };
}

export interface NistFunction {
  id: 'identify' | 'protect' | 'detect' | 'respond' | 'recover';
  name: string;
  progress: number;
}

export interface FeedbackLog {
  id: string;
  timestamp: string;
  vote: 'up' | 'down';
}

export interface SecurityEvent {
  id: string;
  tenantId: string;
  timestamp: string;
  severity: AlertSeverity;
  description: string;
  type: string;
  source: {
    ip: string;
    hostname: string;
  };
  mitreAttack?: {
    technique: string;
    url: string;
  };
  details?: any;
}

export type AiSystemStatus = 'Active' | 'In Development' | 'Sunset';

export interface AiSystem {
  id: string;
  tenantId: string;
  name: string;
  description: string;
  version: string;
  owner: string;
  status: AiSystemStatus;
  lastAssessmentDate: string;
  impactAssessment: ImpactAssessment;
  fairnessMetrics: FairnessMetric[];
  risks: AiRisk[];
  documentation: AiSystemDocumentationLink[];
  controls: {
    isEnabled: boolean;
    confidenceThreshold: number;
    lastRetrainingTriggered: string | null;
  };
  performanceData: { time: string, latency: number, throughput: number, errorRate: number }[];
  securityAlerts: any[]; // Placeholder
}

export interface ImpactAssessment {
  summary: string;
  initialRisks: { title: string, detail: string }[];
  mitigations: { title: string, detail: string }[];
}

export interface FairnessMetric {
  id: string;
  name: string;
  description: string;
  value: string;
  status: 'Pass' | 'Warning' | 'Fail';
}

export type AiRiskSeverity = 'Critical' | 'High' | 'Medium' | 'Low';
export type AiRiskStatus = 'Open' | 'Mitigated' | 'Accepted' | 'Closed';
export type AiRiskMitigationStatus = 'Not Started' | 'In Progress' | 'Pending Review' | 'Completed';
export type MitigationTaskStatus = 'To Do' | 'In Progress' | 'Done';
export type TaskPriority = 'Low' | 'Medium' | 'High';

export interface AiRisk {
  id: string;
  title: string;
  detail: string;
  severity: AiRiskSeverity;
  status: AiRiskStatus;
  mitigationStatus: AiRiskMitigationStatus;
  mitigationTasks: MitigationTask[];
  history: RiskHistoryLog[];
}

export interface MitigationTask {
  id: string;
  description: string;
  owner: string;
  dueDate: string;
  status: MitigationTaskStatus;
  priority: TaskPriority;
}

export interface RiskHistoryLog {
  id: string;
  timestamp: string;
  user: string;
  action: 'Created' | 'Edited' | 'AI Analyzed';
  details: string;
}

export interface AiSystemDocumentationLink {
  id: string;
  title: string;
  url: string;
  type: 'Model Card' | 'Technical Paper' | 'API Reference' | 'Other';
}

export type AgentPlatform = 'Linux' | 'Windows' | 'macOS' | 'Docker' | 'Kubernetes' | 'AWS EC2';
export type AgentStatus = 'Online' | 'Offline' | 'Error';
export type AgentCapability =
  | 'metrics_collection'
  | 'vulnerability_scanning'
  | 'log_collection'
  | 'fim'
  | 'compliance_enforcement'
  | 'runtime_security'
  // 2030 Vision Capabilities
  | 'predictive_health'
  | 'ueba'
  | 'sbom_analysis'
  | 'ebpf_tracing';


export interface AgentHealthCheck {
  name: 'Connectivity' | 'Service Status' | 'Cache Write Access';
  status: 'Pass' | 'Fail';
  message: string;
}

export interface AgentHealth {
  overallStatus: 'Healthy' | 'Degraded' | 'Unhealthy';
  checks: AgentHealthCheck[];
}

export interface Agent {
  id: string;
  tenantId: string;
  assetId: string;
  hostname: string;
  platform: AgentPlatform;
  status: AgentStatus;
  version: string;
  ipAddress: string;
  lastSeen: string;
  remediationAttempts?: { timestamp: string }[];
  capabilities?: AgentCapability[];
  meta?: any;
  health: AgentHealth;
}

export interface AgenticStep {
  type: 'goal' | 'thought' | 'action' | 'observation';
  content: string;
  timestamp: string;
}

export type LogSeverity = 'INFO' | 'WARN' | 'ERROR' | 'DEBUG';
export interface LogEntry {
  id: string;
  timestamp: string;
  service: string;
  hostname: string;
  agentId?: string; // Added for precise filtering
  severity: LogSeverity;
  message: string;
}

export type VulnerabilitySeverity = 'Critical' | 'High' | 'Medium' | 'Low' | 'Informational';
export type VulnerabilityStatus = 'Open' | 'Patched' | 'Risk Accepted';
export interface Vulnerability {
  id: string;
  cveId?: string;
  severity: VulnerabilitySeverity;
  status: VulnerabilityStatus;
  affectedSoftware: string;
}

export interface Asset {
  id: string;
  tenantId: string;
  hostname: string;
  osName: string;
  osVersion: string;
  osEdition?: string;
  osDisplayVersion?: string;
  osInstalledOn?: string;
  osBuild?: string;
  osExperience?: string;
  kernel: string;
  ipAddress: string;
  macAddress: string;
  macAddresses?: { interface: string, mac: string }[];
  cpuModel: string;
  ram: string;
  disks: { device: string, total: string, used: string, free: string, usedPercent: number, type: string, isRemovable?: boolean }[];
  serialNumber: string;
  installedSoftware: { name: string, version: string, installDate?: string, updateAvailable?: boolean }[];
  criticalFiles: { path: string, status: 'Matched' | 'Mismatch', lastModified: string, checksum: string }[];
  lastScanned: string;
  patchStatus: {
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
  vulnerabilities: Vulnerability[];
  agentStatus?: AgentStatus;
  agentVersion?: string;
  agentCapabilities?: AgentCapability[];
}

export type PatchSeverity = 'Critical' | 'High' | 'Medium' | 'Low';
export type PatchStatus = 'Pending' | 'Deployed' | 'Failed' | 'Superseded';
export interface Patch {
  id: string;
  cveId: string;
  description: string;
  severity: PatchSeverity;
  status: PatchStatus;
  releaseDate: string;
  affectedAssets: string[];
}

export type CaseStatus = 'New' | 'In Progress' | 'On Hold' | 'Resolved';
export interface SecurityCase {
  id: string;
  tenantId: string;
  title: string;
  status: CaseStatus;
  severity: AlertSeverity;
  owner: string;
  createdAt: string;
  updatedAt: string;
  relatedEvents: SecurityEvent[];
  comments: Comment[];
  enrichmentData: ThreatIntelResult[];
}

export interface Comment {
  id: string;
  timestamp: string;
  user: string;
  content: string;
}

export interface ThreatIntelResult {
  id: string;
  artifact: string;
  artifactType: 'ip' | 'hash' | 'domain';
  source: string;
  verdict: 'Malicious' | 'Suspicious' | 'Harmless';
  detectionRatio: string;
  scanDate: string;
  reportUrl: string;
}

export type SecurityView = 'metrics' | 'events' | 'cases' | 'playbooks';
export type PlaybookStepType = 'Analysis' | 'Enrichment' | 'Containment' | 'Eradication' | 'Communication';

export type PlaybookConditionOperator = 'equals' | 'not_equals' | 'contains' | 'starts_with';

export type PlaybookConditionField = 'event.severity' | 'event.source.ip' | 'event.type' | 'event.description';

export interface PlaybookCondition {
  id: string;
  field: PlaybookConditionField;
  operator: PlaybookConditionOperator;
  value: string;
}

export interface Playbook {
  id: string;
  name: string;
  description: string;
  trigger: string;
  source: 'User' | 'AI-Generated';
  conditions: PlaybookCondition[];
  steps: {
    id: string;
    name: string;
    description: string;
    type: PlaybookStepType;
    command: string;
  }[];
}

export interface Sbom {
  id: string;
  applicationName: string;
  uploadedAt: string;
  componentCount: number;
}

export interface SoftwareComponent {
  id: string;
  name: string;
  version: string;
  type: 'library' | 'framework' | 'application';
  supplier: string;
  licenses: { id: string, name: string }[];
  hashes?: Record<string, string>;
  vulnerabilities: {
    cve: string;
    severity: VulnerabilitySeverity;
    summary: string;
  }[];
}

export interface HistoricalData {
  date: string;
  [key: string]: any;
}

export interface Integration {
  id: string; // Changed from literal union to string to support custom IDs
  name: string;
  description: string;
  category: 'Collaboration' | 'Ticketing' | 'SIEM' | 'Observability' | 'Security' | 'Community & Partners' | 'Custom' | string;
  isEnabled: boolean;
  config: SlackIntegrationConfig | PagerDutyIntegrationConfig | JiraIntegrationConfig | Record<string, any>;
}

export interface SlackIntegrationConfig {
  webhookUrl: string;
  channel: string;
  severityThreshold: AlertSeverity;
  notificationTypes: string[];
}

export interface PagerDutyIntegrationConfig {
  apiKey: string;
}

export interface JiraIntegrationConfig {
  apiUrl: string;
  apiToken: string;
  projectKey: string;
}

export interface AlertRule {
  id: string;
  name: string;
  metric: MetricType;
  condition: '>' | '<' | '==';
  threshold: number;
  duration?: number;
  severity: AlertSeverity;
  isEnabled: boolean;
}

export interface ApiKey {
  id: string;
  name: string;
  key: string;
  createdAt: string;
  userId: string;
}

export interface DatabaseSettings {
  type: 'PostgreSQL' | 'MySQL' | 'MongoDB';
  host: string;
  port: number;
  username: string;
  databaseName: string;
}

export interface VoiceBotSettings {
  enabled: boolean;
  voiceURI: string;
  pitch: number;
  rate: number;
}

export interface LlmSettings {
  provider: 'Gemini' | 'Local';
  apiKey: string;
  model: string;
  host?: string;
  customModels?: string[];
  voiceBotSettings?: VoiceBotSettings;
}

export type DataSourceType = 'PostgreSQL' | 'AWS S3' | 'MongoDB';
export type DataSourceStatus = 'Connected' | 'Error' | 'Pending';

export interface DataSource {
  id: string;
  tenantId: string;
  name: string;
  type: DataSourceType;
  status: DataSourceStatus;
  config: any;
  lastTested: string | null;
}

export type CloudProvider = 'AWS' | 'GCP' | 'Azure';

export interface CloudAccount {
  id: string;
  tenantId: string;
  provider: CloudProvider;
  name: string;
  accountId: string;
  status: 'Connected' | 'Error';
}

export type CSPMFindingSeverity = 'Critical' | 'High' | 'Medium' | 'Low' | 'Informational';

export interface CSPMFinding {
  id: string;
  tenantId: string;
  title: string;
  description: string;
  severity: CSPMFindingSeverity;
  provider: CloudProvider;
  resourceId: string;
  lastSeen: string;
  remediation: {
    cli: string;
    console: string;
  };
}

export interface Notification {
  id: string;
  message: string;
  timestamp: string;
  isRead: boolean;
  linkTo: AppView;
}

export interface AuditLog {
  id: string;
  timestamp: string;
  userName: string;
  action: string;
  resourceType: string;
  resourceId: string;
  details: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export type PlaybookExecutionStatus = 'idle' | 'running' | 'completed' | 'failed';
export interface PlaybookExecutionStep {
  timestamp: string;
  message: string;
  status: 'running' | 'success' | 'error';
}

export type AgentUpgradeJobStatus = 'Scheduled' | 'Queued' | 'In Progress' | 'Completed' | 'Completed with errors' | 'Failed';

export interface AgentUpgradeJob {
  id: string;
  scheduledAt: string;
  startedAt: string | null;
  completedAt: string | null;
  targetVersion: string;
  status: AgentUpgradeJobStatus;
  agentIds: string[];
  progress: number;
  statusLog: { timestamp: string, message: string }[];
}

export type PatchDeploymentJobStatus = 'Scheduled' | 'Queued' | 'In Progress' | 'Completed' | 'Completed with errors' | 'Failed';

export interface PatchDeploymentJob {
  id: string;
  scheduledAt: string;
  startedAt: string | null;
  completedAt: string | null;
  targetPatchIds: string[];
  targetAssetIds: string[];
  status: PatchDeploymentJobStatus;
  progress: number;
  statusLog: { timestamp: string, message: string }[];
  deploymentType: 'Immediate' | 'Scheduled';
}

export type VulnerabilityScanJobStatus = 'Scheduled' | 'Queued' | 'In Progress' | 'Completed' | 'Completed with errors' | 'Failed';

export interface VulnerabilityScanJob {
  id: string;
  scheduledAt: string;
  startedAt: string | null;
  completedAt: string | null;
  targetAssetIds: string[];
  status: VulnerabilityScanJobStatus;
  progress: number;
  statusLog: { timestamp: string, message: string }[];
  scanType: 'Immediate' | 'Scheduled';
}

export interface UebaFinding {
  id: string;
  userId: string;
  riskScore: number;
  summary: string;
  timestamp: string;
  relatedLogIds: string[];
  details: string;
  status: 'Open' | 'Investigating' | 'Closed';
}

export interface ModelExperiment {
  id: string;
  modelName: string;
  createdAt: string;
  status: 'Running' | 'Completed' | 'Failed';
  metrics: {
    accuracy: number;
    precision: number;
    recall: number;
    f1Score: number;
  };
  parameters: {
    learningRate: number;
    epochs: number;
    batchSize: number;
  };
}

export type ModelStage = 'Development' | 'Staging' | 'Production' | 'Archived';
export interface RegisteredModel {
  id: string;
  name: string;
  description: string;
  latestVersion: string;
  stage: ModelStage;
  versions: {
    version: string;
    experimentId: string;
    promotedAt: string;
    promotedBy: string;
  }[];
}

// --- 2030 Vision Features ---

export interface AutomationPolicy {
  id: string;
  name: string;
  description: string;
  trigger: 'agent.error' | 'alert.critical';
  conditions: {
    field: string;
    operator: 'contains' | 'equals';
    value: string;
  }[];
  action: 'remediate.agent' | 'create.case';
  isEnabled: boolean;
}

export interface SastFinding {
  id: string;
  repositoryId: string;
  fileName: string;
  line: number;
  type: 'SQL Injection' | 'Cross-Site Scripting' | 'Insecure Deserialization';
  severity: 'High' | 'Medium' | 'Low';
  codeSnippet: string;
}

export interface CodeRepository {
  id: string;
  name: string;
  url: string;
  lastScan: string;
  secretFindings: number;
  dependencyVulnerabilities: number;
  sastFindings: number;
}

export interface ApiDocEndpoint {
  id: string;
  method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  path: string;
  description: string;
  requestBody?: any;
  responseBody?: any;
}

export interface IncidentImpactGraph {
  nodes: { id: string, label: string, type: 'Alert' | 'Service' | 'KPI' }[];
  edges: { from: string, to: string, label?: string }[];
}

// --- 2030 - Part 2 Features ---

export type ProactiveInsightType = 'PREDICTIVE_ALERT' | 'ANOMALY_DETECTION' | 'ROOT_CAUSE_ANALYSIS';

export type WebhookEvent =
  | 'agent.online'
  | 'agent.offline'
  | 'agent.error'
  | 'vulnerability.detected'
  | 'security.alert'
  | 'compliance.violation'
  | 'patch.deployed'
  | 'asset.discovered';

export interface Webhook {
  id: string;
  name: string;
  url: string;
  events: WebhookEvent[];
  status: 'Active' | 'Disabled';
  failureCount: number;
  secret?: string;
  createdAt?: string;
}

export interface WebhookDelivery {
  id: string;
  webhookId: string;
  event: WebhookEvent;
  payload: any;
  deliveredAt: string;
  success: boolean;
  responseStatus?: number;
  error?: string;
}

export interface ProactiveInsight {
  id: string;
  type: ProactiveInsightType;
  title: string;
  summary: string;
  timestamp: string;
  severity: 'High' | 'Medium' | 'Low';
  details: any;
}

export type TraceStatus = 'OK' | 'ERROR';

export interface TraceSpan {
  id: string;
  name: string;
  service: string;
  startTime: number; // unix timestamp (ms)
  duration: number; // ms
  status: TraceStatus;
  parentId?: string;
  children: TraceSpan[];
}

export interface Trace {
  id: string;
  rootSpan: TraceSpan;
  totalDuration: number;
  serviceCount: number;
  errorCount: number;
  timestamp: string;
}

export interface ServiceMapNode {
  id: string; // service name
  requestCount: number;
  errorCount: number;
  avgLatency: number;
}

export interface ServiceMapEdge {
  from: string;
  to: string;
  requestCount: number;
}

export interface ServiceMap {
  nodes: ServiceMapNode[];
  edges: ServiceMapEdge[];
}

// --- 2030 - Full Implementation Types ---

export type DataClassification = 'PII' | 'Financial' | 'IP' | 'Public';
export interface SensitiveDataFinding {
  id: string;
  tenantId: string;
  assetId: string;
  assetName: string;
  classification: DataClassification;
  resource: string; // e.g., 's3://bucket/path/to/file' or 'db://table/column'
  finding: string; // e.g., 'Publicly Exposed S3 Bucket containing PII'
  severity: 'Critical' | 'High' | 'Medium';
}

export interface AttackPathNode {
  id: string;
  type: 'Public Asset' | 'Internal Service' | 'Database' | 'Crown Jewel';
  label: string;
  vulnerabilities: number;
}
export interface AttackPathEdge {
  from: string;
  to: string;
  label: string; // e.g., 'Exploits CVE-2023-1234'
}
export interface AttackPath {
  id: string;
  tenantId: string;
  name: string;
  nodes: AttackPathNode[];
  edges: AttackPathEdge[];
}

export interface ServiceTemplate {
  id: string;
  name: string;
  description: string;
  type: 'Go Microservice' | 'Python API' | 'Node.js Web App' | 'Service' | 'Container';
  tags: string[];
  icon?: string;
  category?: string;
  version?: string;
}

export interface ProvisionedService {
  id: string;
  templateId: string;
  name: string;
  owner: string;
  provisionedAt: string;
  status: 'Provisioning' | 'Running' | 'Error' | 'Active' | 'Healthy';
  endpoints?: string[];
  createdAt?: string;
}

export interface DoraMetrics {
  tenantId: string;
  date: string;
  deploymentFrequency: number; // per day
  leadTimeForChanges: number; // hours
  changeFailureRate: number; // percentage
  meanTimeToRecovery: number; // hours
}

export interface BusinessKpi {
  date: string;
  revenue: number;
  userSignups: number;
  cpu: number;
}

export interface ChaosExperiment {
  id: string;
  tenantId: string;
  name: string;
  type: 'CPU Hog' | 'Latency Injection' | 'Pod Failure';
  target: string;
  status: 'Scheduled' | 'Running' | 'Completed' | 'Failed';
  lastRun: string;
}

export type CloudWorkloadType = 'VM' | 'Container' | 'Function';
export interface CloudWorkload {
  id: string;
  tenantId: string;
  name: string;
  type: CloudWorkloadType;
  provider: CloudProvider;
  vulnerabilities: number;
  status: 'Running' | 'Stopped';
}

export interface KubernetesFinding {
  id: string;
  tenantId: string;
  cluster: string;
  namespace: string;
  kind: 'Pod' | 'Deployment' | 'Service';
  resourceName: string;
  finding: string;
  severity: 'Critical' | 'High' | 'Medium';
}

export type NetworkDeviceType = 'Router' | 'Switch' | 'Firewall';
export type NetworkDeviceStatus = 'Up' | 'Down' | 'Warning';

export interface NetworkDeviceInterface {
  id: string;
  name: string;
  status: 'Up' | 'Down';
  inOctets: number;
  outOctets: number;
}

export interface ConfigBackup {
  id: string;
  timestamp: string;
  diff: string | null; // null for initial backup
}

export interface NetworkDevice {
  id: string;
  tenantId: string;
  hostname: string;
  ipAddress: string;
  macAddress: string;
  deviceType: NetworkDeviceType | string;
  role?: 'Firewall' | 'Core Switch' | 'Access Switch' | 'Load Balancer' | 'Gateway' | 'Endpoint' | string;
  zone?: 'Internet' | 'DMZ' | 'Internal LAN' | 'Management' | string;
  metrics?: {
    throughput_in: number;
    throughput_out: number;
    latency: number;
    activeSessions: number;
    cpu_usage?: number;
    memory_usage?: number;
  };
  model: string;
  vendor?: string;     // Added
  osVersion?: string;
  openPorts?: number[]; // Added
  scanEngine?: string;  // Added
  status: NetworkDeviceStatus;
  lastSeen: string;
  interfaces: NetworkDeviceInterface[];
  configBackups: ConfigBackup[];
  vulnerabilities: Vulnerability[];
  vlanId?: string | number;
}

export interface TourStep {
  targetElementId?: string;
  title: string;
  text: string;
  position: 'top' | 'bottom' | 'left' | 'right' | 'center';
  nextView?: AppView;
}

export type Priority = 'Low' | 'Medium' | 'High';

export interface Task {
  id: number;
  text: string;
  priority: Priority;
  completed: boolean;
}

export interface TrafficFlow {
  id: string;
  sourceId: string;
  targetId: string;
  protocol: 'HTTP' | 'HTTPS' | 'SSH' | 'DNS' | 'DB' | 'Other';
  status: 'allowed' | 'blocked' | 'dropped';
  throughput: number;
  latency: number;
  timestamp: string;
}

// --- AI Governance Types ---

export interface AiModelVersion {
  version: string;
  createdAt: string;
  createdBy: string;
  status: 'Staging' | 'Production' | 'Archived';
  metrics: { accuracy?: number, latency?: number, [key: string]: any };
}

export interface AiModel {
  id: string;
  tenantId: string;
  name: string;
  description: string;
  framework: string;
  type: string;
  owner: string;
  versions: AiModelVersion[];
  currentVersion: string;
  riskLevel: 'Low' | 'Medium' | 'High' | 'Critical';
  createdAt: string;
  updatedAt: string;
}

export interface AiPolicyRule {
  id: string;
  name: string;
  condition: string;
  action: string;
}

export interface AiPolicy {
  id: string;
  tenantId: string;
  name: string;
  description: string;
  rules: AiPolicyRule[];
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface DastFinding {
  id: string;
  scanId: string;
  title: string;
  severity: 'Critical' | 'High' | 'Medium' | 'Low';
  description: string;
  remediation: string;
  url: string;
}

export interface DastScan {
  id: string;
  targetUrl: string;
  status: 'Scheduled' | 'Running' | 'Completed' | 'Failed';
  riskScore: number;
  startTime: string; // ISO date
  endTime?: string;
  findingsCount: number;
  findings: DastFinding[];
}

export interface SustainabilityBreakdown {
  compute: number;
  storage: number;
  network: number;
}

export interface CarbonFootprint {
  id: string;
  totalEmissions: number;
  breakdown: SustainabilityBreakdown;
  timestamp: string;
}

export interface SustainabilityMetric {
  id: string;
  name: string;
  value: number;
  unit: string;
  trend: 'improving' | 'worsening' | 'stable';
  target?: number;
}

// Zero Trust & Quantum Security Types
export interface DeviceTrustFactors {
  osPatched: boolean;
  antivirusActive: boolean;
  diskEncrypted: boolean;
  compliantLocation: boolean;
}

export interface DeviceTrustScore {
  deviceId: string;
  score: number;
  factors: DeviceTrustFactors;
  lastUpdated?: string;
}

export interface SessionRiskFactors {
  unusualLocation: boolean;
  unusualTime: boolean;
  newDevice: boolean;
  suspiciousActivity: boolean;
}

export interface UserSessionRisk {
  sessionId: string;
  userId: string;
  authLevel: string;
  riskScore: number;
  factors: SessionRiskFactors;
  timestamp?: string;
}

export interface CryptographicInventory {
  id: string;
  algorithm: string;
  usage: string;
  quantumVulnerable: boolean;
  migrationPriority: string;
  replacementAlgorithm: string;
}

// Governance & Risk Management Types
export interface Risk {
    id: string;
    title: string;
    description: string;
    category: 'Enterprise' | 'AI' | 'Compliance' | 'Third-Party' | 'Cyber';
    status: 'Open' | 'Mitigated' | 'Accepted' | 'Transferred' | 'Avoided';
    likelihood: number;
    impact: number;
    risk_score: number;
    owner: string;
    mitigation_plan?: string;
    created_at: string;
    updated_at: string;
}

export interface VendorAssessment {
    id: string;
    assessment_date: string;
    reviewer: string;
    risk_score: number;
    status: string;
    findings: string[];
}

export interface Vendor {
    id: string;
    name: string;
    website: string;
    criticality: 'Low' | 'Medium' | 'High' | 'Critical';
    category: string;
    contact_name: string;
    contact_email: string;
    contract_start: string;
    contract_end: string;
    status: 'Active' | 'Inactive' | 'Pending Review';
    assessments: VendorAssessment[];
    linked_sboms: string[];
}

export interface TrustProfile {
    company_name: string;
    description: string;
    contact_email: string;
    logo_url: string;
    compliance_frameworks: string[];
    public_documents: { name: string, url: string }[];
    private_documents: { name: string, url: string }[];
}

export interface AccessRequest {
    id: string;
    requester_email: string;
    company: string;
    reason: string;
    status: 'Pending' | 'Approved' | 'Denied';
    requested_at: string;
}
