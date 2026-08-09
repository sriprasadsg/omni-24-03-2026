
// This file will be populated with application-specific types as features are rebuilt.
export type Theme = 'light' | 'dark';

export type AppView =
  | 'dashboard'
  | 'riskRegister'
  | 'vendorManagement'
  | 'trustCenter'
  | 'trustPage'
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
  | 'securityIntelConnectors'
  | 'security'
  | 'compliance'
  | 'programs'
  | 'inboundQuestionnaires'
  | 'governanceDocuments'
  | 'aiAssistantChat'
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
  | 'shadowAI'
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
  | 'yaraRules'
  | 'alertManagement'
  | 'complianceEvidence'
  | 'remediationWorkflow'
  | 'mlops'
  | 'mitreAttack'
  | 'dlp'
  | 'ticketing'
  | 'internalTickets'
  | 'siem'
  | 'ueba'
  | 'vulnerabilities'
  | 'dataUtilization'
  | 'siemRules'
  | 'pentest'
  | 'incidentResponse'
  | 'mdr'
  | 'xdr'
  | 'apm'
  | 'agentApproval'
  | 'customFrameworks'
  | 'deception'
  | 'cloudIntegrations'
  | 'jitAccess'
  | 'incidentWarRoom'
  | 'privacy'
  | 'geoSecurity'
  | 'scheduledReports'
  | 'secretsManagement'
  | 'hadr'
  | 'correlations'
  | 'knowledgeBase'
  | 'retentionPolicy'
  | 'apiSecurity'
  | 'databaseMonitoring'
  | 'k8sSecurity'
  | 'ndr'
  | 'insiderThreat'
  | 'emailSecurity'
  | 'predictiveHealth'
  | 'goalSystem'
  | 'integrationsHub'
  | 'supplyChain'
  | 'futureTech'
  | 'complianceFrameworks'
  | 'fim'
  | 'runtimeSecurity'
  | 'sast'
  | 'remoteAccess'
  | 'aiRemediation'
  | 'rollback'
  | 'pipelineSecurity'
  | 'iacSecurity'
  | 'containerScan'
  | 'pam'
  | 'baaManagement'
  | 'codeReviewGraph'
  | 'supportChat'
  | 'agentChat'
  | 'chat'
  | 'bundleManagement'
  | 'certificates'
  | 'aiAnomaly'
  | 'problemManagement'
  | 'changeManagement'
  | 'ticketWebhooks'
  | 'notificationPrefs'
  | 'windowsAutopilot'
  | 'conditionalAccess'
  | 'mobileDeviceManagement'
  | 'branchSites'
  | 'appCatalog'
  | 'assetIntelligence'
  | 'mobileAppManagement'
  | 'androidEnterprise'
  | 'deviceConfigProfiles'
  | 'firmwareDriverUpdates'
  | 'advancedHunting'
  | 'detectionRules'
  | 'connectorsHub'
  | 'securityCopilot'
  | 'msspMonitoring'
  | 'attackTimeline'
  | 'geographicMap'
  | 'retentionPolicies'
  | 'scaAssessment'
  | 'agentGroups'
  | 'configDrift'
  | 'fimMonitoring'
  | 'activeResponse'
  | 'saasIntegrations'
  | 'cloudAccounts'
  | 'notificationsRouting'
  | 'apiExtensions'
  | 'iacContainer'
  | 'privacyLegal'
  | 'accessReview'
  | 'apiStatus'
  | 'auditProgram'
  | 'cookieConsent'
  | 'executiveSummary'
  | 'maturityScore'
  | 'modelMonitoring'
  | 'soar'
  | 'deploymentApprovals'
  | 'cloudChecksScanner'
  | 'stagedDeployments'
  | 'fleetObservability'
  | 'fleetGeoMap'
  | 'nativeSecurity'
  | 'itam'; // Added for IT Asset Management Console



export type Permission =
  | 'view:dashboard'
  | 'view:cxo_dashboard'
  | 'view:reporting'
  | 'export:reports'
  | 'view:agents'
  | 'view:agent_capabilities'
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
  | 'manage:experiments'
  | 'view:mdr'
  | 'view:xdr'
  | 'manage:agents'
  | 'view:autopilot'
  | 'manage:autopilot'
  | 'view:conditional_access'
  | 'manage:conditional_access'
  | 'view:mdm'
  | 'manage:mdm'
  | 'view:branch_sites'
  | 'manage:branch_sites'
  | 'view:app_catalog'
  | 'manage:app_catalog'
  | 'view:asset_intelligence'
  | 'manage:asset_intelligence'
  | 'view:mam'
  | 'manage:mam'
  | 'view:android_enterprise'
  | 'manage:android_enterprise'
  | 'view:device_config_profiles'
  | 'manage:device_config_profiles'
  | 'view:firmware_drivers'
  | 'manage:firmware_drivers'
  | 'view:predictive_health'
  | 'view:goal_system'
  | 'view:integrations'
  | 'view:advanced_hunting' | 'manage:advanced_hunting'
  | 'view:detection_rules' | 'manage:detection_rules'
  | 'view:connectors_hub' | 'manage:connectors_hub'
  | 'view:security_copilot'
  | 'view:mssp' | 'manage:mssp'
  | 'view:attack_timeline'
  | 'view:geographic_map'
  | 'view:retention_policies' | 'manage:retention_policies'
  | 'view:sca' | 'manage:sca'
  | 'view:agent_groups' | 'manage:agent_groups'
  | 'view:config_drift' | 'manage:config_drift'
  | 'view:fim' | 'manage:fim'
  | 'view:active_response' | 'manage:active_response'
  | 'view:itam' | 'manage:itam'
  | 'admin:*';


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
  // Bundle-based feature entitlement (new)
  assignedBundles?: string[];
  customFeatures?: string[];
  blockedFeatures?: string[];
};

// ── Feature Bundles ───────────────────────────────────────────────────────────

export type FeatureCategory =
  | 'core' | 'observability' | 'security' | 'compliance'
  | 'patching' | 'devsecops' | 'operations' | 'ai_ml' | 'enterprise';

export interface PlatformFeature {
  key: string;
  name: string;
  description: string;
  category: FeatureCategory;
  minTier: SubscriptionTier;
  permission: string;
}

export interface FeatureBundle {
  key: string;
  name: string;
  description: string;
  color: string;
  icon: string;
  features: PlatformFeature[];
  feature_count: number;
  price_hint: string;
}

export interface TenantFeatures {
  tenant_id: string;
  assigned_bundles: string[];
  custom_features: string[];
  blocked_features: string[];
  effective_features: PlatformFeature[];
  feature_keys: string[];
}

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
  acknowledged?: boolean;
  status?: string;
  type?: string;
  hostname?: string;
  tenantId?: string;
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
  status?: 'pending_review' | 'approved' | 'rejected' | 'needs_revision';
}

export interface AssetCompliance {
  id: string;
  assetId: string;
  controlId: string;
  status: 'Compliant' | 'Non-Compliant' | 'Pending_Evidence' | 'Pending_Review';
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
  details?: Record<string, unknown>;
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
  securityAlerts: AiSecurityAlert[];
}

export interface AiSecurityAlert {
  id: string;
  timestamp: string;
  severity: AlertSeverity;
  message: string;
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
export type AgentStatus = 'Online' | 'Offline' | 'Error' | 'Quarantined';
export type AgentCapability =
  // Core telemetry
  | 'metrics_collection'
  | 'log_collection'
  | 'process_monitor'
  // Security detection
  | 'vulnerability_scanning'
  | 'fim'
  | 'compliance_enforcement'
  | 'runtime_security'
  | 'edr_realtime'
  | 'persistence_detection'
  // Network & cloud
  | 'network_discovery'
  | 'cloud_metadata'
  | 'web_monitor'
  // Data & privacy
  | 'pii_scanner'
  | 'sbom_analysis'
  // Advanced / AI
  | 'predictive_health'
  | 'ueba'
  | 'ebpf_tracing'
  | 'shadow_ai'
  // Remediation
  | 'system_patching'
  | 'software_management'
  | 'process_injection_simulation'
  // Extended capabilities
  | 'remote_access'
  | 'agent_update'
  | 'patch_installer'
  | 'remediation_executor'
  | 'real_time_fim'
  | 'vss_manager'
  | 'autonomous_response'
  | 'log_shipper'
  | 'compliance_evidence_collector'
  | 'vendor_risk'
  | 'backup_verifier'
  | 'deception_monitor';


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
  /** WAN / ISP-assigned public IP resolved by the agent. */
  publicIp?: string;
  /** GeoIP location derived from the public IP (server-side, MaxMind GeoLite2). */
  geo?: GeoLocation;
  lastSeen: string;
  remediationAttempts?: { timestamp: string }[];
  capabilities?: AgentCapability[];
  meta?: Record<string, unknown>;
  health: AgentHealth;
}

export interface GeoLocation {
  country?: string;
  country_code?: string;
  city?: string;
  region?: string;
  latitude?: number;
  longitude?: number;
  /** Heuristic-only flag (GSEC-01) — never an authoritative "detected" classification. */
  vpn_heuristic?: boolean;
  asn?: {
    number?: number | string;
    org?: string;
  };
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
  osType?: string;
  osFullName?: string;
  criticality?: 'critical' | 'high' | 'medium' | 'low';
  agentStatus?: AgentStatus;
  agentVersion?: string;
  agentId?: string;
  agentCapabilities?: AgentCapability[];

  // ITAM (Phases 56-60) — additive fields on the same assets collection,
  // present on manual assets and progressively backfilled on agent-discovered
  // ones. All optional: pre-existing agent-discovered assets predate these.
  assetTag?: string;
  assetSource?: 'agent' | 'manual';
  lifecycleStatus?: ItamLifecycleStatus;
  manufacturerId?: string;
  categoryId?: string;
  locationId?: string;
  supplierId?: string;
  modelId?: string;
  purchaseCostCents?: number;
  purchaseDate?: string;
  poNumber?: string;
  warrantyMonths?: number;
  assignedToType?: 'user' | 'location';
  assignedToId?: string;
  components?: string[];
  notes?: string;
}

export type ItamLifecycleStatus = 'deployable' | 'deployed' | 'archived' | 'retired' | 'disposed' | 'broken';

export type ItamCatalogKind = 'manufacturers' | 'categories' | 'locations' | 'suppliers' | 'models';

export interface ItamCatalogEntity {
  id: string;
  tenantId: string;
  name: string;
  notes?: string;
  // Model-only fields (kind === 'models')
  usefulLifeYears?: number;
  salvageValueCents?: number;
  [key: string]: unknown;
}

export interface ItamLicense {
  id: string;
  tenantId: string;
  name: string;
  seatCount: number;
  expiryDate?: string;
  isReassignable?: boolean;
  notes?: string;
  manufacturerId?: string;
  seatsAssigned?: number;
  seatsAvailable?: number;
  isExpired?: boolean;
  daysUntilExpiry?: number | null;
}

export interface ItamLicenseAssignment {
  id: string;
  licenseId: string;
  targetType: 'user' | 'asset';
  targetId: string;
  assignedAt: string;
  assignedBy: string;
  note?: string;
}

export interface ItamConsumable {
  id: string;
  tenantId: string;
  name: string;
  initialQuantity: number;
  availableQuantity: number;
  unitType: string;
  notes?: string;
}

export interface ItamComponent {
  id: string;
  tenantId: string;
  name: string;
  type?: string;
  serialNumber?: string;
  manufacturerId?: string;
  modelId?: string;
  parentAssetId?: string | null;
}

export interface ItamAssignmentHistoryEntry {
  action: string;
  targetType?: string;
  targetId?: string;
  note?: string;
  actorUsername?: string;
  ts: string;
}

export interface ItamBookValue {
  assetId: string;
  modelId?: string | null;
  purchaseCostCents?: number | null;
  purchaseDate?: string | null;
  bookValueCents: number | null;
  reason?: string;
  yearsElapsed?: number;
  annualDepreciationCents?: number;
  usefulLifeYears?: number;
  salvageValueCents?: number;
}

export interface ItamWarrantyStatus {
  assetId: string;
  purchaseDate?: string | null;
  warrantyMonths?: number | null;
  alertWindowDays: number;
  warrantyAlertSentAt?: string | null;
  warrantyStatus: 'none' | 'active' | 'expiring' | 'expired' | string;
  warrantyExpiresAt: string | null;
  daysToExpiry: number | null;
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
  // SLA enrichment fields (populated by patch_enrichment_endpoints)
  sla_hours?: number;
  patch_deadline?: number; // Unix timestamp (seconds)
  sla_status?: 'compliant' | 'at_risk' | 'overdue';
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
  verdict: 'Malicious' | 'Suspicious' | 'Harmless' | 'Unknown';
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
  [key: string]: string | number;
}

export interface Integration {
  id: string; // Changed from literal union to string to support custom IDs
  name: string;
  description: string;
  category: 'Collaboration' | 'Ticketing' | 'SIEM' | 'Observability' | 'Security' | 'Community & Partners' | 'Custom' | string;
  isEnabled: boolean;
  config: SlackIntegrationConfig | PagerDutyIntegrationConfig | JiraIntegrationConfig | Record<string, string | number | boolean>;
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

export interface AiTool {
  id: string;
  name: string;
  type: 'ollama' | 'openai_compatible' | 'custom';
  endpoint: string;
  model: string;
  apiKey?: string;
}

export interface LlmSettings {
  provider: 'Gemini' | 'Local' | 'Omni-LLM-Scratch' | 'Anthropic Claude';
  apiKey: string;
  model: string;
  host?: string;
  ollamaUrl?: string;
  ollamaModel?: string;
  customModels?: string[];
  customTools?: AiTool[];
  voiceBotSettings?: VoiceBotSettings;
}

export type DataSourceType = 'PostgreSQL' | 'AWS S3' | 'MongoDB';
export type DataSourceStatus = 'Connected' | 'Error' | 'Pending';

export interface PostgreSQLDataSourceConfig {
  host: string;
  port: number;
  database: string;
  username: string;
  password?: string;
  ssl?: boolean;
}

export interface S3DataSourceConfig {
  bucket: string;
  region: string;
  prefix?: string;
  accessKeyId?: string;
}

export interface MongoDBDataSourceConfig {
  uri: string;
  database: string;
}

export interface DataSource {
  id: string;
  tenantId: string;
  name: string;
  type: DataSourceType;
  status: DataSourceStatus;
  config: PostgreSQLDataSourceConfig | S3DataSourceConfig | MongoDBDataSourceConfig;
  lastTested: string | null;
}

export type CloudProvider = 'AWS' | 'GCP' | 'Azure' | 'OCI' | 'IBM' | 'Alibaba' | 'DigitalOcean' | 'Cloudflare' | 'VMware' | 'Huawei';

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
  requestBody?: Record<string, unknown>;
  responseBody?: Record<string, unknown>;
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
  payload: Record<string, unknown>;
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
  details: Record<string, unknown>;
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
  source: string;
  target: string;
  vulnerability: string; // e.g., 'CVE-2023-1234'
}
export interface AttackPath {
  id: string;
  tenantId: string;
  name: string;
  nodes: AttackPathNode[];
  edges: AttackPathEdge[];
  simulated?: boolean;
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
  metrics: { accuracy?: number; latency?: number; [key: string]: number | undefined };
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
    fair_inputs?: { lef_min: number; lef_likely: number; lef_max: number; lm_min: number; lm_likely: number; lm_max: number; iterations?: number };
    fair_results?: { mean: number; p10: number; p50: number; p90: number; exceedance_curve: { loss: number; probability: number }[] };
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
    trust_slug?: string;
    trust_domain?: string;
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

// ── Support Chat ──────────────────────────────────────────────────────────────

export interface SupportMessage {
    id: string;
    sender_id: string;
    sender_role: string;
    content: string;
    created_at: string;
}

export interface SupportConversation {
    id: string;
    tenant_id: string;
    subject: string;
    chat_type: 'user_to_admin' | 'admin_to_superadmin' | 'admin_to_user';
    status: 'open' | 'in_progress' | 'resolved' | 'closed';
    initiator_id: string;
    initiator_name?: string;
    initiator_email?: string;
    initiator_role: string;
    target_user_id?: string;
    target_user_name?: string;
    messages?: SupportMessage[];
    message_count?: number;
    last_message?: SupportMessage;
    readers?: Record<string, string>;  // username → ISO timestamp of last read
    original_convo_id?: string;
    original_subject?: string;
    original_user_name?: string;
    original_user_email?: string;
    created_at: string;
    updated_at: string;
    resolved_at?: string;
}

export interface TenantUser {
    id: string;
    email: string;
    name: string;
    role: string;
    status: string;
}

export interface CustomYaraRule {
    id: string;
    name: string;
    content: string;
    description?: string;
    enabled: boolean;
    tenantId?: string;
    createdBy?: string;
    createdAt?: string;
    updatedAt?: string;
    source?: 'builtin' | 'custom';
    category?: string;
    severity?: string;
    mitre?: string;
    family?: string;
}

export interface RemediationTask {
    id: string;
    title: string;
    control_id: string;
    framework_id: string;
    asset_id?: string;
    status: 'open' | 'in_progress' | 'resolved' | 'dismissed';
    priority: 'low' | 'medium' | 'high' | 'critical';
    assignee?: string;
    assignee_type?: 'agent' | 'user';
    due_date?: string;
    description?: string;
    resolution_notes?: string;
    ai_suggestion?: string;
    agent_id?: string;
    created_by: string;
    created_at: string;
    updated_at: string;
    tenantId: string;
    ticket_provider?: 'jira' | 'servicenow';
    ticket_ref?: string;
    ticket_url?: string;
    sla_status?: 'ok' | 'at_risk' | 'breached' | 'none';
}

export interface FrameworkScore {
    framework_id: string;
    framework_name: string;
    short_name: string;
    score: number;
    passing: number;
    failing: number;
    partial: number;
    total_controls: number;
}

export interface ComplianceScorePayload {
    overall_score: number;
    frameworks: FrameworkScore[];
    computed_at: string;
    tenant_id: string;
}

export interface SecurityFinding {
  source: 'scan' | 'vulnerability' | 'fim';
  severity: 'critical' | 'high' | 'medium' | 'low' | 'informational';
  hostname?: string;
  target?: string;
  verdict_or_detail?: string;
  ts: string;
}

export type RemediationStatus =
  | 'pending_approval' | 'dispatching' | 'dispatched'
  | 'resolved' | 'failed' | 'unverified' | 'deferred' | 'denied' | 'dry_run' | 'no_playbook';

export interface RemediationQueueItem {
  id: string;
  tenantId: string;
  agentId?: string;
  findingId: string;
  findingType: string;
  findingSeverity: string;
  findingResourceId?: string;
  playbookName: string;
  status: RemediationStatus;
  createdAt: string;
}

export interface RemediationAuditEntry {
  remediation_id: string;
  tenantId: string;
  ts: string;
  // selected | pending_approval | dispatched | verified | rollback_dispatched
  // | escalated | override_approved | override_denied | dry_run | deferred
  // | dispatch_incomplete | dispatch_failed
  stage: string;
  agentId?: string;
  finding?: { id: string; type: string; severity: string };
  playbook?: string;
  approver?: string;
  reason?: string;
  steps_dispatched?: { action: string; task_id?: string; status: string }[];
  rollback_steps?: { action: string; task_id?: string; status: string }[];
  verification_result?: string;
}

export interface FimStatus {
  agent_id: string;
  hostname?: string;
  events_count: number;
}

export interface SecuritySummary {
  totalFindings: number;
  criticalFindings: number;
  openRemediations: number;
  agentsWithFim: number;
  fimDriftDetected: boolean;
}

export interface RemediationPlaybookStep {
  action: string;
  params: Record<string, any>;
  destructive: boolean;
}

export interface RemediationPlaybook {
  id: string;
  name: string;
  finding_class: string;
  match?: Record<string, any>;
  steps: RemediationPlaybookStep[];
  rollback: { action: string; params: Record<string, any> }[];
  source?: 'vendored' | 'operator';
  tenantId?: string;
  createdAt?: string;
  createdBy?: string;
}
