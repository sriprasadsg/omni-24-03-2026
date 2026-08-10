import React, { useState, useEffect, useMemo, useCallback, lazy, Suspense, useRef } from 'react';

// Suppress console.log in production builds
if (!import.meta.env.DEV) {
   
  console.log = () => {};
}
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { ErrorBoundary } from './components/ErrorBoundary';
import { LoginPage } from './components/LoginPage';
import { Dashboard } from './components/Dashboard';
import { AIAssistantChat } from './components/AIAssistantChat';
import { SkeletonDashboard } from './components/ui/skeleton';

// ── Always-visible UI (eager) ─────────────────────────────────────────────────
import { AddNewTenantModal } from './components/AddNewTenantModal';
import { TenantOnboardingWizard } from './components/TenantOnboardingWizard';
import { ManageTenantModal } from './components/ManageTenantModal';
import { RegisterAgentModal } from './components/RegisterAgentModal';
import { ChatFab } from './components/ChatFab';
import SupportChatToast, { SupportToastData } from './components/SupportChatToast';
import SupportChatWindow from './components/SupportChatWindow';
import { ChatAssistant } from './components/ChatAssistant';
import { AICommandBar, Command } from './components/AICommandBar';
import { GlobalSearchModal } from './components/GlobalSearchModal';
import TaskList from './components/TaskList';
import TaskForm from './components/TaskForm';

// ── Lazy-loaded dashboard components ──────────────────────────────────────────
const CXODashboard = lazy(() => import('./components/CXODashboard').then(m => ({ default: m.CXODashboard })));
const ReportingDashboard = lazy(() => import('./components/ReportingDashboard').then(m => ({ default: m.ReportingDashboard })));
const AgentsDashboard = lazy(() => import('./components/AgentsDashboard').then(m => ({ default: m.AgentsDashboard })));
const AgentCapabilitiesDashboard = lazy(() => import('./components/AgentCapabilitiesDashboard').then(m => ({ default: m.AgentCapabilitiesDashboard })));
const AssetManagementDashboard = lazy(() => import('./components/AssetManagementDashboard').then(m => ({ default: m.AssetManagementDashboard })));
const PatchManagementDashboard = lazy(() => import('./components/PatchManagementDashboard'));
const VulnerabilityManagement = lazy(() => import('./components/VulnerabilityManagement'));
const SoftwareUpdateManagement = lazy(() => import('./components/SoftwareUpdateManagement').then(m => ({ default: m.SoftwareUpdateManagement })));
const CloudSecurityDashboard = lazy(() => import('./components/CloudSecurityDashboard').then(m => ({ default: m.CloudSecurityDashboard })));
const SecurityDashboard = lazy(() => import('./components/SecurityDashboard').then(m => ({ default: m.SecurityDashboard })));
const ComplianceDashboard = lazy(() => import('./components/ComplianceDashboard').then(m => ({ default: m.ComplianceDashboard })));
const ProgramsDashboard = lazy(() => import('./components/ProgramsDashboard').then(m => ({ default: m.ProgramsDashboard })));
const InboundQuestionnaireDashboard = lazy(() => import('./components/InboundQuestionnaireDashboard').then(m => ({ default: m.InboundQuestionnaireDashboard })));
const SaaSIntegrationsDashboard = lazy(() => import('./components/SaaSIntegrationsDashboard'));
const PrivacyLegalDashboard = lazy(() => import('./components/PrivacyLegalDashboard').then(m => ({ default: m.PrivacyLegalDashboard })));
const CloudAccountsDashboard = lazy(() => import('./components/CloudAccountsDashboard').then(m => ({ default: m.CloudAccountsDashboard })));
const NotificationsDashboard = lazy(() => import('./components/NotificationsDashboard').then(m => ({ default: m.NotificationsDashboard })));
const ApiExtensionsDashboard = lazy(() => import('./components/ApiExtensionsDashboard').then(m => ({ default: m.ApiExtensionsDashboard })));
const IacContainerDashboard = lazy(() => import('./components/IacContainerDashboard').then(m => ({ default: m.IacContainerDashboard })));
const ApprovalDashboard = lazy(() => import('./components/ApprovalDashboard').then(m => ({ default: m.ApprovalDashboard })));
const CloudChecksScanner = lazy(() => import('./components/CloudChecksScanner'));
const StagedDeploymentsPage = lazy(() => import('./components/StagedDeploymentVisualizer').then(m => ({ default: m.StagedDeploymentsPage })));
const AIGovernanceDashboard = lazy(() => import('./components/AIGovernanceDashboard').then(m => ({ default: m.AIGovernanceDashboard })));
const FinOpsBillingPage = lazy(() => import('./components/FinOpsBillingPage').then(m => ({ default: m.FinOpsBillingPage })));
const AuditLogDashboard = lazy(() => import('./components/AuditLogDashboard').then(m => ({ default: m.AuditLogDashboard })));
const SecurityAuditDashboard = lazy(() => import('./components/SecurityAuditDashboard').then(m => ({ default: m.SecurityAuditDashboard })));
const SettingsDashboard = lazy(() => import('./components/SettingsDashboard').then(m => ({ default: m.SettingsDashboard })));
const SiemRulesDashboard = lazy(() => import('./components/SiemRulesDashboard').then(m => ({ default: m.SiemRulesDashboard })));
const IncidentResponseDashboard = lazy(() => import('./components/IncidentResponseDashboard').then(m => ({ default: m.IncidentResponseDashboard })));
const TenantManagementDashboard = lazy(() => import('./components/TenantManagementDashboard').then(m => ({ default: m.TenantManagementDashboard })));
const LogExplorerDashboard = lazy(() => import('./components/LogExplorerDashboard').then(m => ({ default: m.LogExplorerDashboard })));
const ThreatHuntingDashboard = lazy(() => import('./components/ThreatHuntingDashboard').then(m => ({ default: m.ThreatHuntingDashboard })));
const ThreatIntelFeedEnhanced = lazy(() => import('./components/ThreatIntelFeedEnhanced').then(m => ({ default: m.ThreatIntelFeedEnhanced })));
const SecurityIntelConnectors = lazy(() => import('./components/SecurityIntelConnectors').then(m => ({ default: m.SecurityIntelConnectors })));
const UserProfilePage = lazy(() => import('./components/UserProfilePage').then(m => ({ default: m.UserProfilePage })));
const AutomationPoliciesDashboard = lazy(() => import('./components/AutomationPoliciesDashboard').then(m => ({ default: m.AutomationPoliciesDashboard })));
const DevSecOpsDashboard = lazy(() => import('./components/DevSecOpsDashboard').then(m => ({ default: m.DevSecOpsDashboard })));
const DeveloperHubDashboard = lazy(() => import('./components/DeveloperHubDashboard').then(m => ({ default: m.DeveloperHubDashboard })));
const IncidentImpactDashboard = lazy(() => import('./components/IncidentImpactDashboard').then(m => ({ default: m.IncidentImpactDashboard })));
const ProactiveInsightsDashboard = lazy(() => import('./components/ProactiveInsightsDashboard').then(m => ({ default: m.ProactiveInsightsDashboard })));
const DistributedTracingDashboard = lazy(() => import('./components/DistributedTracingDashboard').then(m => ({ default: m.DistributedTracingDashboard })));
const DataSecurityDashboard = lazy(() => import('./components/DataSecurityDashboard').then(m => ({ default: m.DataSecurityDashboard })));
const AttackPathDashboard = lazy(() => import('./components/AttackPathDashboard').then(m => ({ default: m.AttackPathDashboard })));
const ServiceCatalogDashboard = lazy(() => import('./components/ServiceCatalogDashboard').then(m => ({ default: m.ServiceCatalogDashboard })));
const DoraMetricsDashboard = lazy(() => import('./components/DoraMetricsDashboard').then(m => ({ default: m.DoraMetricsDashboard })));
const ChaosEngineeringDashboard = lazy(() => import('./components/ChaosEngineeringDashboard').then(m => ({ default: m.ChaosEngineeringDashboard })));
const NetworkObservabilityDashboard = lazy(() => import('./components/NetworkObservabilityDashboard').then(m => ({ default: m.NetworkObservabilityDashboard })));
const DataUtilizationDashboard = lazy(() => import('./components/DataUtilizationDashboard').then(m => ({ default: m.DataUtilizationDashboard })));
const ServicePricingPage = lazy(() => import('./components/ServicePricingPage').then(m => ({ default: m.ServicePricingPage })));
const WebhookManagement = lazy(() => import('./components/WebhookManagement').then(m => ({ default: m.WebhookManagement })));
const SustainabilityDashboard = lazy(() => import('./components/SustainabilityDashboard').then(m => ({ default: m.SustainabilityDashboard })));
const ZeroTrustQuantumDashboard = lazy(() => import('./components/ZeroTrustQuantumDashboard'));
const PaymentSettings = lazy(() => import('./components/PaymentSettings'));
const SubscriptionManagement = lazy(() => import('./components/SubscriptionManagement'));
const InvoiceList = lazy(() => import('./components/InvoiceList'));
const FutureOpsDashboard = lazy(() => import('./components/UnifiedFutureOpsDashboard'));
const RiskRegister = lazy(() => import('./components/RiskRegister'));
import { InteractiveVoiceBot } from './components/InteractiveVoiceBot';
import { CharacterTourBot } from './components/CharacterTourBot';
import { CallOverlay } from './components/CallOverlay';
const VendorManagement = lazy(() => import('./components/VendorManagement'));
const TrustCenter = lazy(() => import('./components/TrustCenter'));
const GovernanceDocumentsDashboard = lazy(() => import('./components/GovernanceDocumentsDashboard').then(m => ({ default: m.GovernanceDocumentsDashboard })));
const TrustPage = lazy(() => import('./components/TrustPage'));
const SecureFileShare = lazy(() => import('./components/SecureFileShare'));
const SecurityTraining = lazy(() => import('./components/SecurityTraining'));
const LLMOpsDashboard = lazy(() => import('./components/LLMOpsDashboard'));
const JobsDashboard = lazy(() => import('./components/JobsDashboard').then(m => ({ default: m.JobsDashboard })));
const SoftwareDeployment = lazy(() => import('./components/SoftwareDeployment').then(m => ({ default: m.SoftwareDeployment })));
const PlaybookBuilder = lazy(() => import('./components/PlaybookBuilder'));
const SecuritySimulation = lazy(() => import('./components/SecuritySimulation').then(m => ({ default: m.SecuritySimulation })));
const PersistenceDashboard = lazy(() => import('./components/PersistenceDashboard').then(m => ({ default: m.PersistenceDashboard })));
const MultiStepApprovalDashboard = lazy(() => import('./components/MultiStepApprovalDashboard').then(m => ({ default: m.MultiStepApprovalDashboard })));
const CertificatesDashboard = lazy(() => import('./components/CertificatesDashboard').then(m => ({ default: m.CertificatesDashboard })));
const AIAnomalyDashboard = lazy(() => import('./components/AIAnomalyDashboard').then(m => ({ default: m.AIAnomalyDashboard })));
const SwarmDashboard = lazy(() => import('./components/SwarmDashboard'));
const SimulationDashboard = lazy(() => import('./components/SimulationDashboard'));
const ComplianceOracleDashboard = lazy(() => import('./components/ComplianceOracleDashboard'));
const CISSPOracle = lazy(() => import('./components/CISSPOracle'));

import { ThemeProvider } from './contexts/ThemeProvider';
import { TimeZoneProvider } from './contexts/TimeZoneContext';
import { FeaturesProvider } from './contexts/FeaturesContext';

import { UserContext } from '@/contexts/UserContext';
const AdvancedBiDashboard = lazy(() => import('./components/AdvancedBiDashboard').then(m => ({ default: m.AdvancedBiDashboard })));
const BundleManagementDashboard = lazy(() => import('./components/BundleManagementDashboard'));
const DataWarehouseDashboard = lazy(() => import('./components/DataWarehouseDashboard').then(m => ({ default: m.DataWarehouseDashboard })));
const StreamingDashboard = lazy(() => import('./components/StreamingDashboard').then(m => ({ default: m.StreamingDashboard })));
const DataGovernanceDashboard = lazy(() => import('./components/DataGovernanceDashboard').then(m => ({ default: m.DataGovernanceDashboard })));
const MLOpsDashboard = lazy(() => import('./components/MLOpsDashboard').then(m => ({ default: m.MLOpsDashboard })));
const AutoMLDashboard = lazy(() => import('./components/AutoMLDashboard').then(m => ({ default: m.AutoMLDashboard })));
const XAIDashboard = lazy(() => import('./components/XAIDashboard').then(m => ({ default: m.XAIDashboard })));
const ABTestingDashboard = lazy(() => import('./components/ABTestingDashboard').then(m => ({ default: m.ABTestingDashboard })));
const DASTDashboard = lazy(() => import('./components/DASTDashboard').then(m => ({ default: m.DASTDashboard })));
const ServiceMeshDashboard = lazy(() => import('./components/ServiceMeshDashboard').then(m => ({ default: m.ServiceMeshDashboard })));
const WebMonitoringDashboard = lazy(() => import('./components/WebMonitoringDashboard').then(m => ({ default: m.WebMonitoringDashboard })));
const EDRDashboard = lazy(() => import('./components/EDRDashboard').then(m => ({ default: m.EDRDashboard })));
const YaraRuleEditor = lazy(() => import('./components/YaraRuleEditor').then(m => ({ default: m.YaraRuleEditor })));
const AlertManagementDashboard = lazy(() => import('./components/AlertManagementDashboard').then(m => ({ default: m.AlertManagementDashboard })));
const ComplianceEvidenceStatusDashboard = lazy(() => import('./components/ComplianceEvidenceStatusDashboard').then(m => ({ default: m.ComplianceEvidenceStatusDashboard })));
const RemediationDashboard = lazy(() => import('./components/RemediationDashboard').then(m => ({ default: m.RemediationDashboard })));
const UEBADashboard = lazy(() => import('./components/UEBADashboard').then(m => ({ default: m.UEBADashboard })));
const MDRDashboard = lazy(() => import('./components/MDRDashboard').then(m => ({ default: m.MDRDashboard })));
const XDRDashboard = lazy(() => import('./components/XDRDashboard').then(m => ({ default: m.XDRDashboard })));
const APMDashboard = lazy(() => import('./components/APMDashboard').then(m => ({ default: m.APMDashboard })));
const AgentApprovalDashboard = lazy(() => import('./components/AgentApprovalDashboard'));
const ThreatDashboard = lazy(() => import('./components/ThreatDashboard'));
const CloudIntegrationsDashboard = lazy(() => import('./components/CloudIntegrationsDashboard'));
const JITAccessDashboard = lazy(() => import('./components/JITAccessDashboard'));
const AutopilotDashboard = lazy(() => import('./components/AutopilotDashboard'));
const ConditionalAccessDashboard = lazy(() => import('./components/ConditionalAccessDashboard'));
const MobileDashboard = lazy(() => import('./components/MobileDashboard'));
const BranchSitesDashboard = lazy(() => import('./components/BranchSitesDashboard'));
const AppCatalogDashboard = lazy(() => import('./components/AppCatalogDashboard'));
const AssetIntelligenceDashboard = lazy(() => import('./components/AssetIntelligenceDashboard'));
const MAMDashboard = lazy(() => import('./components/MAMDashboard'));
const AndroidEnterpriseDashboard = lazy(() => import('./components/AndroidEnterpriseDashboard'));
const DeviceConfigProfilesDashboard = lazy(() => import('./components/DeviceConfigProfilesDashboard'));
const FirmwareDriverDashboard = lazy(() => import('./components/FirmwareDriverDashboard'));
const AdvancedHuntingDashboard = lazy(() => import('./components/AdvancedHuntingDashboard'));
const DetectionRulesDashboard = lazy(() => import('./components/DetectionRulesDashboard'));
const ConnectorsHubDashboard = lazy(() => import('./components/ConnectorsHubDashboard'));
const SecurityCopilotDashboard = lazy(() => import('./components/SecurityCopilotDashboard'));
const MSSPDashboard = lazy(() => import('./components/MSSPDashboard'));
const AttackTimelineDashboard = lazy(() => import('./components/AttackTimelineDashboard'));
const GeographicAttackMap = lazy(() => import('./components/GeographicAttackMap'));
const RetentionPoliciesDashboard = lazy(() => import('./components/RetentionPoliciesDashboard'));
const SCADashboard = lazy(() => import('./components/SCADashboard'));
const AgentGroupsDashboard = lazy(() => import('./components/AgentGroupsDashboard'));
const ConfigDriftDashboard = lazy(() => import('./components/ConfigDriftDashboard'));
const FIMDashboard = lazy(() => import('./components/FIMDashboard'));
const ActiveResponseDashboard = lazy(() => import('./components/ActiveResponseDashboard'));
const IncidentWarRoomDashboard = lazy(() => import('./components/IncidentWarRoomDashboard'));
const PrivacyDashboard = lazy(() => import('./components/PrivacyDashboard'));
const SecuritySettingsDashboard = lazy(() => import('./components/SecuritySettingsDashboard').then(m => ({ default: m.SecuritySettingsDashboard })));
const FleetObservabilityDashboard = lazy(() => import('./components/FleetObservabilityDashboard').then(m => ({ default: m.FleetObservabilityDashboard })));
const FleetGeoMap = lazy(() => import('./components/FleetGeoMap').then(m => ({ default: m.FleetGeoMap })));
const NativeSecurityConsole = lazy(() => import('./components/NativeSecurityConsole').then(m => ({ default: m.NativeSecurityConsole })));
const ITAMConsole = lazy(() => import('./components/itam/ITAMConsole'));
const ScheduledReportsDashboard = lazy(() => import('./components/ScheduledReportsDashboard'));
const SecretsManagementDashboard = lazy(() => import('./components/SecretsManagementDashboard').then(m => ({ default: m.SecretsManagementDashboard })));
const CustomFrameworkBuilder = lazy(() => import('./components/CustomFrameworkBuilder'));
const DeceptionDashboard = lazy(() => import('./components/DeceptionDashboard'));
const NetworkTopologyMap = lazy(() => import('./components/NetworkTopologyMap').then(m => ({ default: m.NetworkTopologyMap })));
const ShadowAI = lazy(() => import('./components/ShadowAI').then(m => ({ default: m.ShadowAI })));
const KnowledgeBaseDashboard = lazy(() => import('./components/KnowledgeBaseDashboard'));
const RetentionPolicyDashboard = lazy(() => import('./components/RetentionPolicyDashboard'));
const APISecurityDashboard = lazy(() => import('./components/APISecurityDashboard'));
const DAMDashboard = lazy(() => import('./components/DAMDashboard'));
const K8sSecurityDashboard = lazy(() => import('./components/K8sSecurityDashboard'));
const NDRDashboard = lazy(() => import('./components/NDRDashboard'));
const InsiderThreatDashboard = lazy(() => import('./components/InsiderThreatDashboard'));
const EmailSecurityDashboard = lazy(() => import('./components/EmailSecurityDashboard'));
const SupplyChainDashboard = lazy(() => import('./components/SupplyChainDashboard'));
const HADRDashboard = lazy(() => import('./components/HADRDashboard').then(m => ({ default: m.HADRDashboard })));
const CorrelationDashboard = lazy(() => import('./components/CorrelationDashboard').then(m => ({ default: m.CorrelationDashboard })));
const CodeReviewGraphDashboard = lazy(() => import('./components/CodeReviewGraphDashboard').then(m => ({ default: m.CodeReviewGraphDashboard })));

const PentestDashboard = lazy(() => import('./components/PentestDashboard').then(m => ({ default: m.PentestDashboard })));
const FutureTechDashboard = lazy(() => import('./components/FutureTechDashboard'));
const PredictiveHealthDashboard = React.lazy(() => import('./components/PredictiveHealthDashboard').then(m => ({ default: m.PredictiveHealthDashboard })));
const SystemHealthDashboard = React.lazy(() => import('./components/SystemHealthDashboard').then(m => ({ default: m.SystemHealthDashboard })));
const GoalSystemDashboard = React.lazy(() => import('./components/GoalSystemDashboard').then(m => ({ default: m.GoalSystemDashboard })));
const IntegrationsHub = React.lazy(() => import('./components/IntegrationsHub').then(m => ({ default: m.IntegrationsHub })));
const ComplianceFrameworksDashboard = React.lazy(() => import('./components/ComplianceFrameworksDashboard').then(m => ({ default: m.ComplianceFrameworksDashboard })));
const RemoteAccessDashboard = React.lazy(() => import('./components/RemoteAccessDashboard').then(m => ({ default: m.RemoteAccessDashboard })));
const AgentChatPanel = React.lazy(() => import('./components/AgentChatPanel'));
const ChatHub = React.lazy(() => import('./components/ChatHub'));
const AIRemediationDashboard = React.lazy(() => import('./components/AIRemediationDashboard').then(m => ({ default: m.AIRemediationDashboard })));
const RollbackDashboard = React.lazy(() => import('./components/RollbackDashboard').then(m => ({ default: m.RollbackDashboard })));
const FimAlertsDashboard = React.lazy(() => import('./components/FimAlertsPanel').then(m => ({ default: m.FimAlertsPanel })));
const RuntimeSecurityDashboard = React.lazy(() => import('./components/RuntimeSecurityTab').then(m => ({ default: m.RuntimeSecurityTab })));
const SASTDashboardLazy = React.lazy(() => import('./components/SASTDashboard').then(m => ({ default: m.SASTDashboard })));
const PipelineSecurityDashboard = React.lazy(() => import('./components/PipelineSecurityDashboard').then(m => ({ default: m.PipelineSecurityDashboard })));
const IaCSecurityDashboard = React.lazy(() => import('./components/IaCSecurityDashboard').then(m => ({ default: m.IaCSecurityDashboard })));
const ContainerScanDashboard = React.lazy(() => import('./components/ContainerScanDashboard').then(m => ({ default: m.ContainerScanDashboard })));
const PAMDashboard = React.lazy(() => import('./components/PAMDashboard').then(m => ({ default: m.PAMDashboard })));
const BAAManagement = React.lazy(() => import('./components/BAAManagement').then(m => ({ default: m.BAAManagement })));
const MitreAttackHeatmap = React.lazy(() => import('./components/MitreAttackHeatmap'));
const SupportChatDashboard = React.lazy(() => import('./components/SupportChatPanel'));
const DLPDashboard = React.lazy(() => import('./components/DLPDashboard'));
const TicketingIntegration = React.lazy(() => import('./components/TicketingIntegration'));
const InternalTicketsDashboard = React.lazy(() => import('./components/InternalTicketsDashboard'));
const ProblemManagementDashboard = lazy(() => import('./components/ProblemManagementDashboard'));
const ChangeManagementDashboard = lazy(() => import('./components/ChangeManagementDashboard'));
const TicketWebhooksDashboard = lazy(() => import('./components/TicketWebhooksDashboard'));
const NotificationPreferencesDashboard = lazy(() => import('./components/NotificationPreferencesDashboard'));
const AccessReviewDashboard = lazy(() => import('./components/AccessReviewDashboard'));
const ApiStatusDashboard = lazy(() => import('./components/ApiStatusDashboard').then(m => ({ default: m.ApiStatusDashboard })));
const AuditProgramDashboard = lazy(() => import('./components/AuditProgramDashboard'));
const CookieConsentDashboard = lazy(() => import('./components/CookieConsentDashboard'));
const ExecutiveDashboard = lazy(() => import('./components/ExecutiveDashboard').then(m => ({ default: m.ExecutiveDashboard })));
const MaturityScoreDashboard = lazy(() => import('./components/MaturityScoreDashboard'));
const ModelMonitoringDashboard = lazy(() => import('./components/ModelMonitoringDashboard').then(m => ({ default: m.ModelMonitoringDashboard })));
const SOARDashboard = lazy(() => import('./components/SOARDashboard').then(m => ({ default: m.SOARDashboard })));


import * as api from './services/apiService';
// WebSocket for real-time notifications
import { socketService } from './services/socketService';
import { AppView, User, Role, Tenant, Metric, Alert, ComplianceFramework, AiSystem, Asset, Patch, SecurityCase, Playbook, SecurityEvent, CloudAccount, CSPMFinding, Notification as AppNotification, AuditLog, Integration, AlertRule, Agent, DatabaseSettings, LlmSettings, DataSource, Sbom, SoftwareComponent, AgentUpgradeJob, PatchDeploymentJob, Permission, Filter, LogEntry, UebaFinding, ModelExperiment, RegisteredModel, ModelStage, AutomationPolicy, SastFinding, CodeRepository, ApiDocEndpoint, IncidentImpactGraph, NewUserPayload, AgentPlatform, SubscriptionTier, SensitiveDataFinding, AttackPath, ServiceTemplate, ProvisionedService, DoraMetrics, ChaosExperiment, ProactiveInsight, Trace, ServiceMap, VulnerabilityScanJob, NetworkDevice, ThreatIntelResult, NewTenantPayload, Task, Priority, AssetCompliance } from './types';
import { SUBSCRIPTION_TIERS } from './constants';
import { AlertTriangleIcon } from './components/icons';
import { showToast } from './utils/toast';

const API_BASE = '/api';

// FIX: Added mappings for new AppViews to satisfy the Record type.
const viewPermissionMap: Record<AppView, Permission> = {
  dashboard: 'view:dashboard',
  reporting: 'view:reporting',
  agents: 'view:agents',
  agentCapabilities: 'view:agents',
  assetManagement: 'view:assets',
  patchManagement: 'view:patching',
  vulnerabilityManagement: 'view:patching',
  softwareUpdates: 'view:software_updates',
  cloudSecurity: 'view:cloud_security',
  security: 'view:security',
  compliance: 'view:compliance',
  programs: 'view:compliance',
  inboundQuestionnaires: 'view:compliance',
  governanceDocuments: 'view:compliance',
  trustPage: 'view:compliance',
  aiAssistantChat: 'view:dashboard',
  aiGovernance: 'view:ai_governance',
  finops: 'view:finops',
  auditLog: 'view:audit_log',
  settings: 'manage:settings',
  tenantManagement: 'manage:tenants',
  userManagement: 'manage:rbac',
  roleManagement: 'manage:rbac',
  apiKeys: 'manage:api_keys',
  integrations: 'manage:settings',
  notifications: 'view:dashboard',
  swarm: 'view:dashboard',
  logExplorer: 'view:logs',
  threatHunting: 'view:threat_hunting',
  profile: 'view:profile',
  automation: 'view:automation',
  devsecops: 'view:devsecops',
  sbom: 'view:sbom', // Added mapping for SBOM view
  developer_hub: 'view:developer_hub',
  incidentImpact: 'investigate:security',
  playbooks: 'manage:playbooks',
  threatIntelligence: 'view:threat_intel',
  proactiveInsights: 'view:insights',
  distributedTracing: 'view:tracing',
  dataSecurity: 'view:dspm',
  attackPath: 'view:attack_path',
  serviceCatalog: 'view:service_catalog',
  doraMetrics: 'view:dora_metrics',
  chaosEngineering: 'view:chaos',
  networkObservability: 'view:network',
  dataUtilization: 'view:network',
  servicePricing: 'manage:pricing',
  tasks: 'view:profile',
  softwareDeployment: 'view:software_deployment',
  // 2030 Industry Features
  webhooks: 'manage:settings',
  digitalTwin: 'view:dashboard',
  riskRegister: 'view:compliance',
  vendorManagement: 'view:compliance',
  trustCenter: 'view:compliance',
  secureFileShare: 'manage:compliance_evidence',
  securityTraining: 'view:compliance',
  complianceOracle: 'view:compliance',
  cissporacle: 'view:compliance',
  sustainability: 'view:dashboard',
  llmops: 'view:ai_governance',
  zeroTrustQuantum: 'view:security',
  futureOps: 'view:dashboard',
  futureTech: 'view:dashboard',
  unifiedOps: 'view:dashboard',
  jobs: 'view:dashboard',
  securitySimulation: 'view:security',
  persistenceDetection: 'view:security',
  approvalWorkflows: 'view:ai_governance',
  biDashboard: 'view:reporting',
  systemHealth: 'manage:settings',
  paymentSettings: 'manage:settings',
  subscriptionManagement: 'view:dashboard',
  invoices: 'view:dashboard',
  securityAudit: 'view:security_audit',
  advancedBi: 'view:advanced_bi',
  pentest: 'view:security',
  cxo: 'view:cxo_dashboard',
  dataWarehouse: 'view:reporting',
  streaming: 'view:analytics',
  dataGovernance: 'view:governance',
  mlops: 'view:mlops',
  automl: 'view:automl',
  xai: 'view:xai',
  abTesting: 'manage:experiments',
  dast: 'view:security', // reusing security permission for now
  serviceMesh: 'view:network',
  persistence: 'view:persistence',
  networkTopology: 'view:network',
  webMonitoring: 'view:web_monitoring',
  edr: 'view:security',
  mdr: 'view:mdr',
  xdr: 'view:xdr',
  mitreAttack: 'view:security',
  dlp: 'view:security',
  ticketing: 'manage:settings',
  internalTickets: 'view:dashboard',
  siem: 'view:security',
  ueba: 'view:security',
  vulnerabilities: 'view:vulnerabilities',
  siemRules: 'view:security',
  incidentResponse: 'investigate:security',
  apm: 'view:tracing',
  agentApproval: 'view:agents',
  cloudIntegrations: 'manage:settings',
  jitAccess: 'manage:settings',
  windowsAutopilot: 'view:autopilot',
  conditionalAccess: 'view:conditional_access',
  mobileDeviceManagement: 'view:mdm',
  branchSites: 'view:branch_sites',
  appCatalog: 'view:app_catalog',
  assetIntelligence: 'view:asset_intelligence',
  mobileAppManagement: 'view:mam',
  androidEnterprise: 'view:android_enterprise',
  deviceConfigProfiles: 'view:device_config_profiles',
  firmwareDriverUpdates: 'view:firmware_drivers',
  advancedHunting: 'view:advanced_hunting',
  detectionRules: 'view:detection_rules',
  connectorsHub: 'view:connectors_hub',
  securityCopilot: 'view:security_copilot',
  msspMonitoring: 'view:mssp',
  attackTimeline: 'view:attack_timeline',
  geographicMap: 'view:geographic_map',
  retentionPolicies: 'view:retention_policies',
  scaAssessment: 'view:sca',
  agentGroups: 'view:agent_groups',
  configDrift: 'view:config_drift',
  fimMonitoring: 'view:fim',
  activeResponse: 'view:active_response',
  incidentWarRoom: 'investigate:security',
  privacy: 'view:compliance',
  geoSecurity: 'manage:settings',
  fleetObservability: 'manage:agents',
  fleetGeoMap: 'manage:agents',
  scheduledReports: 'view:reporting',
  secretsManagement: 'manage:settings',
  customFrameworks: 'view:compliance',
  deception: 'view:security',
  shadowAI: 'view:security',
  hadr: 'manage:settings',
  correlations: 'view:security',
  knowledgeBase: 'view:dashboard',
  retentionPolicy: 'manage:settings',
  apiSecurity: 'view:security',
  databaseMonitoring: 'view:security',
  k8sSecurity: 'view:security',
  ndr: 'view:security',
  insiderThreat: 'view:security',
  emailSecurity: 'view:security',
  supplyChain: 'view:devsecops',
  predictiveHealth: 'view:predictive_health',
  goalSystem: 'view:goal_system',
  integrationsHub: 'view:integrations',
  complianceFrameworks: 'view:compliance',
  fim: 'view:security',
  runtimeSecurity: 'view:security',
  sast: 'view:security',
  remoteAccess: 'view:agents',
  agentChat: 'manage:agents',
  chat: 'manage:agents',
  aiRemediation: 'view:ai_governance',
  rollback: 'manage:settings',
  pipelineSecurity: 'view:devsecops',
  iacSecurity: 'view:devsecops',
  containerScan: 'view:devsecops',
  pam: 'manage:settings',
  baaManagement: 'view:compliance',
  codeReviewGraph: 'view:devsecops',
  supportChat: 'view:dashboard',
  bundleManagement: 'manage:tenants',
  certificates: 'view:assets',
  aiAnomaly: 'view:security',
  yaraRules: 'view:security',
  alertManagement: 'view:security',
  complianceEvidence: 'view:compliance',
  remediationWorkflow: 'view:compliance',
  problemManagement: 'view:security',
  changeManagement: 'manage:settings',
  ticketWebhooks: 'manage:settings',
  notificationPrefs: 'view:profile',
  securityIntelConnectors: 'view:security',
  saasIntegrations: 'view:compliance',
  privacyLegal: 'view:compliance',
  cloudAccounts: 'view:cloud_security',
  notificationsRouting: 'view:automation',
  apiExtensions: 'view:devsecops',
  iacContainer: 'view:cloud_security',
  accessReview: 'view:compliance',
  apiStatus: 'manage:settings',
  auditProgram: 'view:compliance',
  cookieConsent: 'view:compliance',
  executiveSummary: 'view:reporting',
  maturityScore: 'view:compliance',
  modelMonitoring: 'view:mlops',
  soar: 'manage:playbooks',
  deploymentApprovals: 'view:patching',
  cloudChecksScanner: 'view:cloud_security',
  stagedDeployments: 'view:software_deployment',
  nativeSecurity: 'manage:active_response',
  itam: 'manage:itam',
};


// ── Notification sound — synthesized two-tone chime (no audio file needed) ──
function playNotificationSound() {
    try {
        const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
        if (!AudioCtx) return;
        const ctx = new AudioCtx();
        const play = (freq: number, startAt: number, dur: number) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.type = 'sine';
            osc.frequency.setValueAtTime(freq, ctx.currentTime + startAt);
            gain.gain.setValueAtTime(0, ctx.currentTime + startAt);
            gain.gain.linearRampToValueAtTime(0.18, ctx.currentTime + startAt + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + startAt + dur);
            osc.start(ctx.currentTime + startAt);
            osc.stop(ctx.currentTime + startAt + dur);
        };
        play(880,  0,    0.22);   // A5 — first tone
        play(1108, 0.20, 0.28);   // C#6 — second tone (chord-like chime)
        setTimeout(() => ctx.close().catch(() => {}), 800);
    } catch { /* autoplay policy blocked — silent fail */ }
}

const App: React.FC = () => {
  // Global App State
  // Global App State
  // Theme managed by ThemeProvider
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [currentView, setCurrentView] = useState<AppView>('dashboard');
  // Ref so WebSocket handlers can read the latest view without being re-registered on every navigation
  const currentViewRef = useRef<AppView>('dashboard');
  useEffect(() => { currentViewRef.current = currentView; }, [currentView]);
  // Kept in a ref so the support-message socket handler (stable closure) can
  // tell whether the floating support window is already open.
  const isSupportChatOpenRef = useRef(false);

  // Refresh metrics every 30 s while the dashboard is visible
  useEffect(() => {
    if (currentView !== 'dashboard') return;
    const tick = async () => {
      const fresh = await api.fetchMetrics();
      if (fresh && fresh.length > 0) setMetrics(fresh);
    };
    const timer = setInterval(tick, 30_000);
    return () => clearInterval(timer);
  }, [currentView]);

  // Refresh recent alerts every 60 s while the dashboard is visible
  // Note: fetchAlerts() without tenantId uses server-side tenant from the JWT
  useEffect(() => {
    if (currentView !== 'dashboard') return;
    const tick = async () => {
      const fresh = await api.fetchAlerts();
      if (fresh && fresh.length > 0) setAlerts(fresh as Alert[]);
    };
    const timer = setInterval(tick, 60_000);
    return () => clearInterval(timer);
  }, [currentView]);

  // ── Support chat in-app toast queue & unread count ────────────────────────
  const [supportToasts, setSupportToasts] = useState<SupportToastData[]>([]);
  const [supportUnreadCount, setSupportUnreadCount] = useState(0);
  // Conversation to auto-open when the user lands on the Support tab (deep-link
  // from a toast / OS notification / admin-initiated chat).
  const [pendingSupportConvo, setPendingSupportConvo] = useState<string | null>(null);
  // Floating, docked support-chat window (opened from a toast / notification).
  const [isSupportChatOpen, setIsSupportChatOpen] = useState(false);
  useEffect(() => { isSupportChatOpenRef.current = isSupportChatOpen; }, [isSupportChatOpen]);

  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [viewingTenantId, setViewingTenantId] = useState<string | null>(null);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isCommandBarOpen, setIsCommandBarOpen] = useState(false);
  const [isGlobalSearchOpen, setIsGlobalSearchOpen] = useState(false);
  const [brandingConfig, setBrandingConfig] = useState<{ logoUrl?: string, companyName?: string }>({});
  const [error, setError] = useState<string | null>(null);

  // Filter State for Dashboards
  const [agentFilters, setAgentFilters] = useState<Filter[]>([]);
  const [assetFilters, setAssetFilters] = useState<Filter[]>([]);
  const [viewingImpactFor, setViewingImpactFor] = useState<{ type: 'alert' | 'case', id: string } | null>(null);

  // Version Check and Cache Clear to fix stale tenant IDs
  /*
  useEffect(() => {
    const APP_VERSION = '2.0.1'; // Increment to force clear
    const storedVersion = localStorage.getItem('app_version');

    if (storedVersion !== APP_VERSION) {
      console.warn(`App version mismatch (stored: ${storedVersion}, current: ${APP_VERSION}). Clearing cache.`);
      // Preserve token if possible? No, safer to clear all for this specific bug.
      // But clearing all logs user out. That's fine.
      localStorage.clear();
      sessionStorage.clear();
      localStorage.setItem('app_version', APP_VERSION);

      // Reload to ensure clean state
      window.location.reload();
    }
  }, []);
  */
  useEffect(() => {
    api.startTokenRefreshCycle();
    return () => api.stopTokenRefreshCycle();
  }, []);


  // Data State
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [complianceFrameworks, setComplianceFrameworks] = useState<ComplianceFramework[]>([]);
  const [aiSystems, setAiSystems] = useState<AiSystem[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [patches, setPatches] = useState<Patch[]>([]);
  const [securityCases, setSecurityCases] = useState<SecurityCase[]>([]);
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [securityEvents, setSecurityEvents] = useState<SecurityEvent[]>([]);
  const [cloudAccounts, setCloudAccounts] = useState<CloudAccount[]>([]);
  const [cspmFindings, setCspmFindings] = useState<CSPMFinding[]>([]);
  // notifications state removed — NotificationCenter manages its own state independently
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [alertRules, setAlertRules] = useState<AlertRule[]>([]);
  const [historicalData, setHistoricalData] = useState<any>({});
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentsRefreshInterval, setAgentsRefreshInterval] = useState<NodeJS.Timeout | null>(null);
  const [databaseSettings, setDatabaseSettings] = useState<DatabaseSettings | null>(null);
  const [llmSettings, setLlmSettings] = useState<LlmSettings | null>(null);
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [sboms, setSboms] = useState<Sbom[]>([]);
  const [softwareComponents, setSoftwareComponents] = useState<SoftwareComponent[]>([]);
  const [agentUpgradeJobs, setAgentUpgradeJobs] = useState<AgentUpgradeJob[]>([]);
  const [patchDeploymentJobs, setPatchDeploymentJobs] = useState<PatchDeploymentJob[]>([]);
  const [vulnerabilityScanJobs, setVulnerabilityScanJobs] = useState<VulnerabilityScanJob[]>([]);
  const [networkDevices, setNetworkDevices] = useState<NetworkDevice[]>([]);
  const [threatIntelFeed, setThreatIntelFeed] = useState<ThreatIntelResult[]>([]);
  const [threatIntelModalResult, setThreatIntelModalResult] = useState<ThreatIntelResult | null>(null);
  const [assetComplianceData, setAssetComplianceData] = useState<AssetCompliance[]>([]);

  // Future-proofing data state
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [uebaFindings, setUebaFindings] = useState<UebaFinding[]>([]);
  const [modelExperiments, setModelExperiments] = useState<ModelExperiment[]>([]);
  const [registeredModels, setRegisteredModels] = useState<RegisteredModel[]>([]);
  const [automationPolicies, setAutomationPolicies] = useState<AutomationPolicy[]>([]);
  const [sastFindings, setSastFindings] = useState<SastFinding[]>([]);
  const [codeRepositories, setCodeRepositories] = useState<CodeRepository[]>([]);
  const [apiDocs, setApiDocs] = useState<ApiDocEndpoint[]>([]);
  const [incidentImpactGraph, setIncidentImpactGraph] = useState<IncidentImpactGraph | null>(null);
  const [sensitiveDataFindings, setSensitiveDataFindings] = useState<SensitiveDataFinding[]>([]);
  const [attackPaths, setAttackPaths] = useState<AttackPath[]>([]);
  const [serviceTemplates, setServiceTemplates] = useState<ServiceTemplate[]>([]);
  const [provisionedServices, setProvisionedServices] = useState<ProvisionedService[]>([]);
  const [doraMetrics, setDoraMetrics] = useState<DoraMetrics[]>([]);
  const [chaosExperiments, setChaosExperiments] = useState<ChaosExperiment[]>([]);
  const [proactiveInsights, setProactiveInsights] = useState<ProactiveInsight[]>([]);
  const [traces, setTraces] = useState<Trace[]>([]);
  const [serviceMap, setServiceMap] = useState<ServiceMap | null>(null);
  const [myTasks, setMyTasks] = useState<Task[]>([]);
  const [serverLockedFeatures, setServerLockedFeatures] = useState<Record<string, string>>({});

  // Modal State
  const [isAddTenantModalOpen, setIsAddTenantModalOpen] = useState(false);
  const [managingTenant, setManagingTenant] = useState<Tenant | null>(null);
  const [isRegisterAgentModalOpen, setIsRegisterAgentModalOpen] = useState(false);
  const [newlyGeneratedKey, setNewlyGeneratedKey] = useState<{ name: string, key: string } | null>(null);

  // Theme side effects managed by ThemeProvider

  // Hash Navigation Effect
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.slice(1).toLowerCase(); // remove '#'
      if (!hash) return;

      // Explicit mapping for friendlier URLs
      const hashToView: Record<string, AppView> = {
        'assets': 'assetManagement',
        'agents': 'agents',
        'patching': 'patchManagement',
        'security': 'security',
        'compliance': 'compliance',
        'aigovernance': 'aiGovernance',
        'tickets': 'internalTickets',
        'helpdesk': 'internalTickets',
      };

      const view = hashToView[hash] || Object.keys(viewPermissionMap).find(key => key.toLowerCase() === hash) as AppView | undefined;

      if (view) {
        handleSetCurrentView(view);
      }
    };

    // Handle initial hash
    handleHashChange();

    // Listen for changes
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [currentUser]); // Re-run when user logs in to ensure we navigate to the hash view


  // Command Bar key listener
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'k') {
        event.preventDefault();
        setIsCommandBarOpen(prev => !prev);
      }
      // Ctrl+/ opens global data search
      if ((event.metaKey || event.ctrlKey) && event.key === '/') {
        event.preventDefault();
        setIsGlobalSearchOpen(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const [isBackendConnected, setIsBackendConnected] = useState(true);

  // Data Loading Function
  const loadAllData = useCallback(async () => {
    // Prevent unauthenticated calls which trigger redirect loops
    const token = sessionStorage.getItem('token');
    if (!token) {
      console.warn("Skipping loadAllData: No token found");
      return;
    }

    // Only super-admins can list all tenants; skip the call to avoid repeated 403s
    const _jwtPayload = (() => { try { return JSON.parse(atob(token.split('.')[1])); } catch { return {}; } })();
    const _isSuperAdmin = ['Super Admin', 'superadmin', 'super_admin', 'platform-admin'].includes(_jwtPayload.role || '');

    try {
      const results = await Promise.allSettled([
        api.fetchUsers(), api.fetchRoles(), _isSuperAdmin ? api.fetchTenants() : Promise.resolve([]), api.fetchMetrics(),
        api.fetchAlerts(), api.fetchComplianceFrameworks(), api.fetchAiSystems(),
        api.fetchAssets(), api.fetchPatches(), api.fetchSecurityCases(),
        api.fetchPlaybooks(), api.fetchSecurityEvents(), api.fetchCloudAccounts(),
        api.fetchCspmFindings(), api.fetchAuditLogs(),
        api.fetchIntegrations(), api.fetchAlertRules(), api.fetchHistoricalData(viewingTenantId || undefined),
        api.fetchAgents(), api.fetchInfrastructure(), api.fetchDataSources(),
        api.fetchSboms(), api.fetchSoftwareComponents(),
        api.fetchAgentUpgradeJobs(), api.fetchPatchDeploymentJobs(), api.fetchVulnerabilityScanJobs(), api.fetchLogs(), api.fetchUebaFindings(),
        api.fetchModelExperiments(), api.fetchRegisteredModels(), api.fetchAutomationPolicies(),
        api.fetchSastFindings(), api.fetchCodeRepositories(), api.fetchApiDocs(),
        api.fetchSensitiveDataFindings(),
        api.fetchAttackPaths(), api.fetchServiceTemplates(), api.fetchProvisionedServices(),
        api.fetchDoraMetrics(), api.fetchChaosExperiments(), api.fetchProactiveInsights(),
        api.fetchTraces(), api.fetchServiceMap(), api.fetchThreatIntelFeed(), api.fetchNetworkDevices(),
        api.fetchGlobalComplianceData(), api.fetchTasks(),
      ]);

      const getResult = <T,>(index: number, fallback: T): T => {
        const result = results[index];
        if (result.status === 'fulfilled') {
          return result.value as T;
        } else {
          console.warn(`Data fetch failed for index ${index}, using fallback. Reason:`, result.reason);
          return fallback;
        }
      };

      setUsers(getResult(0, []));
      setRoles(getResult(1, []));
      setTenants(getResult(2, []));
      setMetrics(getResult(3, [])); // No mock data for metrics yet, or use empty
      setAlerts(getResult(4, []));
      setComplianceFrameworks(getResult(5, []));
      setAiSystems(getResult(6, []));
      setAssets(getResult(7, [])); // Use only real assets from database, no mock fallback
      setPatches(getResult(8, []));
      setSecurityCases(getResult(9, []));
      setPlaybooks(getResult(10, []));
      setSecurityEvents(getResult(11, []));
      setCloudAccounts(getResult(12, []));
      setCspmFindings(getResult(13, []));
      setAuditLogs(getResult(14, []));
      setIntegrations(getResult(15, []));
      setAlertRules(getResult(16, []));
      setHistoricalData(getResult(17, {}));
      setAgents(getResult(18, []));
      const infra = getResult(19, { db: null, llm: null });
      setDatabaseSettings(infra?.db || null);
      setLlmSettings(infra?.llm || null);
      setDataSources(getResult(20, []));
      setSboms(getResult(21, []));
      setSoftwareComponents(getResult(22, []));
      setAgentUpgradeJobs(getResult(23, []));
      setPatchDeploymentJobs(getResult(24, []));
      setVulnerabilityScanJobs(getResult(25, []));
      setLogs(getResult(26, []));
      setUebaFindings(getResult(27, []));
      setModelExperiments(getResult(28, []));
      setRegisteredModels(getResult(29, []));
      setAutomationPolicies(getResult(30, []));
      setSastFindings(getResult(31, []));
      setCodeRepositories(getResult(32, []));
      setApiDocs(getResult(33, []));
      setSensitiveDataFindings(getResult(34, []));
      setAttackPaths(getResult(35, []));
      setServiceTemplates(getResult(36, []));
      setProvisionedServices(getResult(37, []));
      setDoraMetrics(getResult(38, []));
      setChaosExperiments(getResult(39, []));
      setProactiveInsights(getResult(40, []));
      setTraces(getResult(41, []));
      setServiceMap(getResult(42, null));
      setThreatIntelFeed(getResult(43, []));
      const netDevs = getResult(44, []);
      setNetworkDevices(netDevs);
      setAssetComplianceData(getResult(45, []));
      setMyTasks(getResult(46, []));

      // Check if any critical data failed to determine "Backend Connected" status roughly
      const criticalFailures = results.slice(0, 3).filter(r => r.status === 'rejected').length;
      if (criticalFailures > 0) {
        setIsBackendConnected(false);
        setError('Backend connection issues detected. Running in offline mode with demo data.');
      } else {
        setError(null);
      }

    } catch (err) {
      console.error("Critical error in loadAllData:", err);
      setError('Failed to load application data.');
    }
  }, []);

  // ==================== AUTHENTICATION FUNCTIONS ====================

  const handleLogin = async (email: string, password: string): Promise<boolean> => {
    try {
      const data = await api.login(email, password);

      if (data.success && data.user) {
        // Store authentication tokens
        if (data.access_token) sessionStorage.setItem('token', data.access_token);
        if (data.refresh_token) sessionStorage.setItem('refresh_token', data.refresh_token);

        // Merge subscriptionTier from tenant into user object so badge can read it across all roles
        setCurrentUser({ ...data.user, subscriptionTier: data.tenant?.subscriptionTier || 'Free' });
        setViewingTenantId((data.user.role === 'Super Admin' || data.user.role === 'superadmin' || data.user.role === 'super_admin') ? null : data.user.tenantId);
        setCurrentView('dashboard');
        api.startTokenRefreshCycle();

        // Fetch server-confirmed feature flags (non-blocking)
        api.fetchPlatformFeatures().then(f => setServerLockedFeatures(f.locked)).catch(() => {});

        // Load all data in background (non-blocking)
        loadAllData().catch(err => console.error('Error loading data:', err));

        return true;
      }

      return false;
    } catch (error) {
      console.error('[Frontend] Login error:', error);
      return false;
    }
  };

  const handleSignup = async (payload: { companyName: string; name: string; email: string; password: string }): Promise<boolean> => {
    try {
      const response = await fetch(`${API_BASE}/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Signup failed');
      }

      if (data.success && data.user) {
        // Store authentication tokens
        if (data.access_token) sessionStorage.setItem('token', data.access_token);
        if (data.refresh_token) sessionStorage.setItem('refresh_token', data.refresh_token);

        // Merge subscriptionTier from tenant into user object
        setCurrentUser({ 
          ...data.user, 
          subscriptionTier: data.tenant?.subscriptionTier || 'Free' 
        });

        // Set viewing tenant id
        setViewingTenantId(data.tenant?.id || data.user?.tenantId || null);
        api.startTokenRefreshCycle();

        // Load all data after successful signup
        await loadAllData();
        return true;
      }

      return false;
    } catch (error: any) {
      console.error('Signup error:', error);
      // Re-throw so the form can catch and display the error message
      throw error;
    }
  };


  const handleLogout = () => {
    api.stopTokenRefreshCycle();
    setCurrentUser(null);
    sessionStorage.removeItem('token');
    sessionStorage.removeItem('refresh_token');
    // Reload to the login page — clearing React state and any cached data
    window.location.href = '/';
  };

  const handleRegisterTenant = async (payload: NewTenantPayload): Promise<boolean> => {
    // For now, use the signup endpoint
    // This can be expanded if separate tenant registration is needed
    return handleSignup({
      companyName: payload.companyName,
      name: payload.name,
      email: payload.email,
      password: payload.password
    });
  };


  // SSO callback — exchange one-time code for JWT before restoreSession runs
  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.pathname !== '/sso-callback') return;
    const code = url.searchParams.get('code');
    const errorParam = url.searchParams.get('error');

    if (errorParam) {
      window.history.replaceState({}, '', '/');
      return;
    }

    if (!code) {
      window.history.replaceState({}, '', '/');
      return;
    }

    fetch('/api/sso/exchange', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    })
      .then(r => r.json())
      .then(d => {
        if (d.access_token) {
          sessionStorage.setItem('token', d.access_token);
        }
      })
      .catch(() => {})
      .finally(() => {
        window.history.replaceState({}, '', '/');
        window.location.reload();
      });
  }, []);

  // Initial Data Load
  useEffect(() => {
    const restoreSession = async () => {
      const user = await api.fetchCurrentUser();
      if (user) {
        setCurrentUser(user);
        setViewingTenantId((user.role === 'Super Admin' || user.role === 'superadmin' || user.role === 'super_admin') ? null : user.tenantId);
        // Fetch server-confirmed feature flags
        api.fetchPlatformFeatures().then(f => setServerLockedFeatures(f.locked)).catch(() => {});
        // Only load data AFTER session is restored
        loadAllData();
      } else {
        // If no session, we stay on login page. Do NOT load data.
        console.warn("No active session found on startup.");
      }
    };

    // Only try to restore session if we don't have a user yet
    if (!currentUser) {
      restoreSession();
    } else {
      // If we already have a user (e.g. from login), ensure data is loaded
      loadAllData();
    }
  }, [currentUser, loadAllData]);

  // Health Check & Auto-Reconnect
  useEffect(() => {
    const checkHealth = async () => {
      const isConnected = await api.checkBackendHealth();
      setIsBackendConnected(prev => {
        if (prev !== isConnected) {
          if (isConnected) {
              loadAllData(); // Auto-refresh on reconnection
          } else {
            // Backend connection lost, mark agents as offline
            setAgents(prevAgents => prevAgents.map(a => ({ ...a, status: 'Offline' })));
          }
        }
        return isConnected;
      });
    };

    checkHealth(); // Check immediately
    const interval = setInterval(checkHealth, 10000); // Poll every 10s
    return () => clearInterval(interval);
  }, [loadAllData]);

  // Periodic Data Refresh (every 30s)
  useEffect(() => {
    if (!isBackendConnected) return;
    const interval = setInterval(() => {
      loadAllData();
    }, 30000);
    return () => clearInterval(interval);
  }, [isBackendConnected, loadAllData]);

  // Targeted Polling for Agents View (every 5s)
  useEffect(() => {
    if (currentView !== 'agents' || !isBackendConnected) return;

    // Initial fetch when entering view is covered by loadAllData or previous state
    const interval = setInterval(() => {
      api.fetchAgents().then((agentsData: Agent[]) => {
        // Deduplicate agents by ID (keep the latest entry)
        const uniqueAgents = Object.values(
          agentsData.reduce((acc: Record<string, Agent>, agent: Agent) => {
            acc[agent.id] = agent;
            return acc;
          }, {})
        );
        setAgents(uniqueAgents as Agent[]);
      }).catch(err => console.error("Error polling agents:", err));
    }, 5000);

    return () => clearInterval(interval);
  }, [currentView, isBackendConnected]);

  // Calculate activeTenantId BEFORE using it in WebSocket useEffect
  const activeTenantId = viewingTenantId || currentUser?.tenantId;

  // WebSocket Connection Management
  useEffect(() => {
    if (currentUser && activeTenantId) {
      socketService.connect(activeTenantId);

      const handleAgentStatusChange = (data: { agent_id: string; status: string; timestamp: string }) => {
        setAgents(prev => prev.map(agent =>
          agent.id === data.agent_id
            ? { ...agent, status: data.status as any, lastSeen: data.timestamp }
            : agent
        ));
      };

      const handleSecurityEvent = (event: any) => {
        setSecurityEvents(prev => [event, ...prev]);
      };

      const handleNotification = (data: any) => {
        playNotificationSound();
        console.log('[App] Notification received:', data);
      };

      const handleComplianceAlert = (data: any) => {
        playNotificationSound();
        console.warn('[App] Compliance alert received:', data);
        setCurrentView('compliance');
      };

      socketService.on('agent_status_change', handleAgentStatusChange);
      socketService.on('security_event', handleSecurityEvent);
      socketService.on('notification', handleNotification);
      socketService.on('compliance_alert', handleComplianceAlert);

      return () => {
        socketService.off('agent_status_change', handleAgentStatusChange);
        socketService.off('security_event', handleSecurityEvent);
        socketService.off('notification', handleNotification);
        socketService.off('compliance_alert', handleComplianceAlert);
        socketService.disconnect();
      };
    }
  }, [currentUser, activeTenantId]);

  // ── Browser notification permission ──────────────────────────────────────
  useEffect(() => {
    if (currentUser && 'Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }, [currentUser]);

  // ── Support chat: in-app toast + sound + OS notification + unread count ────
  useEffect(() => {
    if (!currentUser) return;
    const myId = (currentUser as any)?.email ?? (currentUser as any)?.username ?? '';
    const handler = (data: any) => {
      // A new inbound message OR a freshly-opened conversation (e.g. an admin
      // starting a direct chat with this user) should both surface a notification.
      const isNewConvo = data.event === 'new_conversation';
      if (data.event !== 'new_message' && !isNewConvo) return;

      // For new_conversation the whole convo object is spread onto `data`
      // (id/subject/messages/initiator_*); for new_message it's convo_id + message.
      const convoId = isNewConvo ? (data.id ?? '') : (data.convo_id ?? '');
      const msg = isNewConvo ? (data.messages?.[data.messages.length - 1] ?? null) : (data.message ?? null);

      // Don't notify the person who just acted (initiator/sender receives the
      // broadcast too — they're already looking at the conversation).
      const senderId = msg?.sender_id ?? data.initiator_id ?? '';
      if (senderId && senderId === myId) return;

      const isOnSupportChat = !document.hidden && (
        isSupportChatOpenRef.current ||
        ['supportChat', 'chat'].includes(currentViewRef.current)
      );

      // 1. Notification sound (always play unless already on support chat page)
      if (!isOnSupportChat) {
        playNotificationSound();
      }

      // 2. Increment unread badge + update tab title
      if (!isOnSupportChat) {
        setSupportUnreadCount(prev => prev + 1);
      }

      // 3. In-app toast (visible from any page while tab is open)
      if (!isOnSupportChat) {
        const toast: SupportToastData = {
          id: `${convoId}-${msg?.id ?? Date.now()}`,
          senderRole: msg?.sender_role ?? data.initiator_role ?? 'user',
          senderName: msg?.sender_id ?? data.initiator_name ?? '',
          preview: String(msg?.content ?? data.subject ?? '').slice(0, 160),
          convoId,
          at: Date.now(),
        };
        setSupportToasts(prev => [...prev.slice(-4), toast]); // max 5 stacked
      }

      // 4. OS-level push notification (works when tab is hidden/minimised)
      if (document.hidden && 'Notification' in window && Notification.permission === 'granted') {
        const sender = (msg?.sender_role ?? data.initiator_role ?? 'Someone').replace(/_/g, ' ');
        const preview = String(msg?.content ?? data.subject ?? '').slice(0, 120);
        const title = isNewConvo ? `New chat from ${sender}` : `New support message from ${sender}`;
        const notif = new Notification(title, {
          body: preview || 'You have a new support message.',
          icon: '/favicon.ico',
          tag: `support-${convoId}`,
        });
        notif.onclick = () => {
          window.focus();
          setPendingSupportConvo(convoId);
          setIsSupportChatOpen(true);
          notif.close();
        };
      }
    };
    socketService.on('support_message', handler);
    return () => socketService.off('support_message', handler);
  }, [currentUser, setCurrentView]);

  // ── Browser tab title badge ───────────────────────────────────────────────
  useEffect(() => {
    const base = 'Omni-Agent AI';
    document.title = supportUnreadCount > 0 ? `(${supportUnreadCount}) ${base}` : base;
  }, [supportUnreadCount]);

  // ── Reset unread count when user navigates to any chat view ────────────────
  useEffect(() => {
    if (['supportChat', 'chat'].includes(currentView)) {
      setSupportUnreadCount(0);
    }
  }, [currentView]);

  // --- DERIVED STATE & CONTEXT ---
  const { enabledFeatures, hasPermission } = useMemo(() => {
    if (!currentUser) return { enabledFeatures: [], hasPermission: () => false };

    // FIX: Super Admin bypasses all lookups (roles, tenants) to ensure visibility
    if (currentUser.role === 'Super Admin' || currentUser.role === 'superadmin' || currentUser.role === 'super_admin') {
      return {
        enabledFeatures: [],
        hasPermission: (perm: any) => {
          // console.log('[App] Super Admin Access:', perm);
          return true;
        }
      };
    }

    // Use permissions from currentUser object (provided by backend during login/signup)
    let effectiveFeatures: Permission[] = [];

    if (currentUser.permissions && Array.isArray(currentUser.permissions) && currentUser.permissions.length > 0) {
      // Backend included permissions in the user object
      const userPerms = currentUser.permissions as Permission[];

      const tenant = tenants.find(t => t.id === currentUser.tenantId);
      if (tenant && currentUser.role !== 'Super Admin') {
        // Intersect user permissions with tenant's enabled features
        effectiveFeatures = userPerms.filter(p => tenant.enabledFeatures.includes(p));
      } else {
        effectiveFeatures = userPerms;
      }
    } else {
      // Fallback to role-based lookup (case-insensitive)
      const roleLower = currentUser.role?.trim().toLowerCase() || '';
      const role = roles.find(r => r.name?.trim().toLowerCase() === roleLower);

      if (role) {
        // If role grants "all" permissions, skip tenant intersection
        if (role.permissions.includes('all' as Permission)) {
          effectiveFeatures = ['all' as Permission];
        } else {
          const tenant = tenants.find(t => t.id === currentUser.tenantId);
          effectiveFeatures = tenant
            ? role.permissions.filter(p => tenant.enabledFeatures.includes(p))
            : role.permissions;
        }
      }
      // If no role found, effectiveFeatures stays [] — checkPermission handles "all" shortcut below
    }

    const checkPermission = (permission: Permission): boolean => {
      const roleName = currentUser?.role?.trim().toLowerCase() || '';
      const isSuperAdmin = roleName === 'super admin' || roleName === 'superadmin' || roleName === 'super_admin' || roleName === 'platform-admin';
      if (isSuperAdmin) return true;
      // "all" permission grants access to everything
      if (effectiveFeatures.includes('all' as Permission)) return true;
      return effectiveFeatures.includes(permission);
    };

    return { enabledFeatures: effectiveFeatures, hasPermission: checkPermission };
  }, [currentUser, roles, tenants]);



  const tenantData = useMemo(() => {
    if (!activeTenantId || activeTenantId === 'platform-admin') {
      return {
        alerts: alerts,
        assets: assets,
        agents: agents,
        securityEvents: securityEvents,
        securityCases: securityCases,
        complianceFrameworks: complianceFrameworks,
        aiSystems: aiSystems,
        patches: patches,
        patchDeploymentJobs: patchDeploymentJobs,
        vulnerabilityScanJobs: vulnerabilityScanJobs,
        cloudAccounts: cloudAccounts,
        cspmFindings: cspmFindings,
        auditLogs: auditLogs,
        integrations: integrations,
        alertRules: alertRules,
        dataSources: dataSources,
        sboms: sboms,
        softwareComponents: softwareComponents,
        agentUpgradeJobs: agentUpgradeJobs,
        logs: logs,
        uebaFindings: uebaFindings,
        modelExperiments: modelExperiments,
        registeredModels: registeredModels,
        automationPolicies: automationPolicies,
        sastFindings: sastFindings,
        codeRepositories: codeRepositories,
        sensitiveDataFindings: sensitiveDataFindings,
        attackPaths: attackPaths,
        serviceTemplates: serviceTemplates,
        provisionedServices: provisionedServices,
        doraMetrics: doraMetrics,
        chaosExperiments: chaosExperiments,
        proactiveInsights: proactiveInsights,
        traces: traces,
        serviceMap: serviceMap,
        networkDevices: networkDevices,
        assetComplianceData: assetComplianceData,
      };
    }
    return {
      alerts: alerts.filter(a => tenants.find(t => t.id === activeTenantId)), // Simple filter for demo
      assets: assets.filter(a => a.tenantId === activeTenantId),
      agents: agents.filter(a => a.tenantId === activeTenantId),
      securityEvents: securityEvents.filter(s => s.tenantId === activeTenantId),
      securityCases: securityCases.filter(s => s.tenantId === activeTenantId),
      complianceFrameworks: complianceFrameworks, // Assuming frameworks are global
      aiSystems: aiSystems.filter(s => s.tenantId === activeTenantId),
      patches: patches.filter(p => p.affectedAssets?.some(assetId => assets.find(a => a.id === assetId)?.tenantId === activeTenantId)),
      patchDeploymentJobs: patchDeploymentJobs, // Assume global for now
      vulnerabilityScanJobs: vulnerabilityScanJobs, // Assume global for now
      cloudAccounts: cloudAccounts.filter(c => c.tenantId === activeTenantId),
      cspmFindings: cspmFindings.filter(f => f.tenantId === activeTenantId),
      auditLogs: auditLogs.filter(log => {
        const detailsStr = typeof log.details === 'string' ? log.details : JSON.stringify(log.details || {});
        const userName = log.userName || '';
        return detailsStr.includes(activeTenantId) || userName.includes(tenants.find(t => t.id === activeTenantId)?.name || 'non-existent');
      }),
      integrations: integrations, // Global for demo
      alertRules: alertRules, // Global for demo
      dataSources: dataSources.filter(d => d.tenantId === activeTenantId),
      sboms: sboms,
      softwareComponents: softwareComponents,
      agentUpgradeJobs: agentUpgradeJobs,
      logs: logs,
      uebaFindings: uebaFindings,
      modelExperiments: modelExperiments,
      registeredModels: registeredModels,
      automationPolicies: automationPolicies,
      sastFindings: sastFindings,
      codeRepositories: codeRepositories,
      sensitiveDataFindings: sensitiveDataFindings.filter(f => f.tenantId === activeTenantId),
      attackPaths: attackPaths.filter(p => p.tenantId === activeTenantId),
      serviceTemplates: serviceTemplates, // global
      provisionedServices: provisionedServices, // global
      doraMetrics: doraMetrics.filter(d => d.tenantId === activeTenantId),
      chaosExperiments: chaosExperiments.filter(c => c.tenantId === activeTenantId),
      proactiveInsights: proactiveInsights, // global
      traces: traces, // global
      serviceMap: serviceMap, // global
      networkDevices: networkDevices.filter(d => d.tenantId === activeTenantId),
      assetComplianceData: assetComplianceData.filter(ac => assets.some(a => a.id === ac.assetId && a.tenantId === activeTenantId)),
    };
  }, [activeTenantId, alerts, assets, agents, securityEvents, securityCases, complianceFrameworks, aiSystems, patches, patchDeploymentJobs, vulnerabilityScanJobs, cloudAccounts, cspmFindings, auditLogs, integrations, alertRules, tenants, dataSources, sboms, softwareComponents, agentUpgradeJobs, logs, uebaFindings, modelExperiments, registeredModels, automationPolicies, sastFindings, codeRepositories, sensitiveDataFindings, attackPaths, serviceTemplates, provisionedServices, doraMetrics, chaosExperiments, proactiveInsights, traces, serviceMap, networkDevices, assetComplianceData]);


  // --- EVENT HANDLERS & API CALLS ---
  // Removed duplicate login function

  const signup = async (payload: { companyName: string; name: string; email: string; password: string }): Promise<boolean> => {
    try {
      const result = await api.signupNewUser(payload);

      if (result.success && result.user && result.tenant) {
        // Update local state
        setUsers(prev => [...prev, result.user!]);
        setTenants(prev => [...prev, result.tenant!]);
        return true;
      }

      console.error("Signup failed:", result.error);
      showToast(result.error || "Signup failed. Please try again.", 'error');
      return false;
    } catch (error) {
      console.error("Signup error:", error);
      showToast("An error occurred during signup. Please try again.", 'error');
      return false;
    }
  };
  // FIX: Add registerTenant function to satisfy UserContext type requirements in App.tsx
  const registerTenant = useCallback(async (payload: NewTenantPayload): Promise<boolean> => {
    const { success, newUser, newTenant } = await api.registerNewTenant(payload);
    if (success && newUser && newTenant) {
      setUsers(prev => [...prev, newUser]);
      setTenants(prev => [...prev, newTenant]);
      setCurrentUser(newUser);
      setViewingTenantId(newUser.tenantId);
      setCurrentView('dashboard');
      return true;
    }
    return false;
  }, []);

  const logout = useCallback(() => {
    // Must clear stored tokens — omitting these leaves the refresh token active
    // allowing a new access token to be silently obtained after "logout".
    sessionStorage.removeItem('token');
    sessionStorage.removeItem('refresh_token');
    api.stopTokenRefreshCycle();
    setCurrentUser(null);
    setViewingTenantId(null);
    window.location.href = '/';
  }, []);

  const handleSetCurrentView = useCallback((view: AppView) => {
    // Super Admin can access all views without permission check
    if (currentUser?.role === 'Super Admin' || currentUser?.role === 'superadmin') {
      setCurrentView(view);
      return;
    }

    const requiredPermission = viewPermissionMap[view];
    if (hasPermission(requiredPermission)) {
      setCurrentView(view);
    } else {
      console.warn(`User does not have permission to view: ${view}`);
      // Optionally show an error message to the user
    }
  }, [hasPermission, currentUser]);



  const handleAddNewTenant = async (tenantData: { name: string; subscriptionTier: string }) => {
    try {
      const newTenant = await api.addTenant(tenantData);
      setTenants(prev => [...prev, newTenant]);
      showToast(`Tenant "${tenantData.name}" created successfully.`, 'success');
    } catch (error: any) {
      console.error('[App] Error adding tenant:', error);
      showToast(error.message || "Failed to add tenant. Please try again.", 'error');
    }
  };

  const handleSaveTenantFeatures = (tenantId: string, updates: { features: Permission[], tier: SubscriptionTier }) => {
    api.updateTenantFeatures(tenantId, updates.features, updates.tier).then(updatedTenant => {
      setTenants(prev => prev.map(t => t.id === tenantId ? updatedTenant : t));
      setManagingTenant(null);
    });
  };

  // FIX: Create an adapter function to handle calls from TenantFeatureManagement which doesn't provide a tier.
  const handleTenantAdminFeatureSave = (tenantId: string, features: Permission[]) => {
    let newTier: SubscriptionTier = 'Custom';
    const sortedFeatures = [...features].sort();

    // Find if the selection matches a predefined tier
    for (const tierName of (Object.keys(SUBSCRIPTION_TIERS) as Exclude<SubscriptionTier, 'Custom'>[])) {
      const tierPermissions = [...SUBSCRIPTION_TIERS[tierName].permissions].sort();
      if (JSON.stringify(sortedFeatures) === JSON.stringify(tierPermissions)) {
        newTier = tierName;
        break;
      }
    }

    handleSaveTenantFeatures(tenantId, { features, tier: newTier });
  };

  const handleDeleteTenant = async (tenantId: string) => {
    try {
      await api.deleteTenant(tenantId);
      setTenants(prev => prev.filter(t => t.id !== tenantId));
      setUsers(prev => prev.filter(u => u.tenantId !== tenantId));
      showToast('Tenant deleted successfully', 'success');
    } catch (error) {
      console.error('[App] Error deleting tenant:', error);
      showToast(`Failed to delete tenant: ${error instanceof Error ? error.message : 'Unknown error'}`, 'error');
    }
  };

  // Duplicate handleAddNewTenant removed

  const handleRegisterAgent = (data: { hostname: string, ipAddress: string, platform: AgentPlatform, version: string, assetId: string | 'new' }) => {
    if (!activeTenantId) {
      showToast("Cannot register agent: No active tenant selected.", 'error');
      return;
    }
    api.registerAgent({ ...data, tenantId: activeTenantId }).then(({ newAgent, newAsset }) => {
      setAgents(prev => [...prev, newAgent]);
      if (newAsset) {
        setAssets(prev => [...prev, newAsset]);
      }
      setIsRegisterAgentModalOpen(false);
    });
  };

  const handleUpdateAgent = (agent: Agent) => {
    api.updateAgent(agent).then(updatedAgent => {
      setAgents(prev => prev.map(a => a.id === updatedAgent.id ? updatedAgent : a));
    }).catch(error => {
      console.error("Failed to update agent:", error);
    });
  };

  const handleDeleteAgent = async (agent: Agent) => {
    try {
      console.log(`[App] Attempting to delete agent: ${agent.hostname} (${agent.id})`);
      const response = await api.deleteAgent(agent.id);

      if (response && response.success) {
        console.log(`[App] Agent deleted successfully: ${agent.id}`);
        setAgents(prev => prev.filter(a => a.id !== agent.id));
        // Provide visual feedback
        // Note: Ideally use a toast notification here
      } else {
        console.error(`[App] Failed to delete agent, backend response:`, response);
        showToast(`Failed to delete agent: ${response?.message || "Unknown error"}`, 'error');
      }
    } catch (error) {
      console.error("Failed to delete agent (Exception):", error);
      showToast("Failed to delete agent. See console for details.", 'error');
    }
  };

  const handleDeleteAsset = async (asset: Asset) => {
    try {
      console.log(`[App] Deleting asset: ${asset.hostname} (${asset.id})`);
      await api.deleteAsset(asset.id);

      setAssets(prev => prev.filter(a => a.id !== asset.id));
      console.log(`[App] Asset deleted successfully`);
    } catch (error) {
      console.error("Failed to delete asset:", error);
      showToast(`Failed to delete asset: ${error instanceof Error ? error.message : 'Unknown error'}`, 'error');
    }
  };

  const handleRunVulnerabilityScan = async (assetId: string) => {
    await api.runVulnerabilityScan(assetId);
    // Refetch assets to get updated scan date and ensure UI waits for new data
    await api.fetchAssets().then(setAssets);
  };

  const handleScheduleUpgrade = (agentIds: string[], targetVersion: string) => {
    api.scheduleAgentUpgrade(agentIds, targetVersion).then(newJob => {
      setAgentUpgradeJobs(prev => [newJob, ...prev]);
    });
  };

  const handleSchedulePatchDeployment = async (patchIds: string[], assetIds: string[], deploymentType: 'Immediate' | 'Scheduled', scheduleTime?: string): Promise<void> => {
    const newJob = await api.schedulePatchDeployment(patchIds, assetIds, deploymentType, scheduleTime);
    setPatchDeploymentJobs(prev => [newJob, ...prev]);
    // The job simulation will eventually change patch statuses, so we refetch patches after a while
    setTimeout(() => {
      api.fetchPatches().then(setPatches);
    }, (assetIds.length * 1500) + 5000); // Wait until job simulation is likely complete
  };

  const handleScheduleVulnerabilityScan = async (assetIds: string[], scanType: 'Immediate' | 'Scheduled', scheduleTime?: string): Promise<void> => {
    // Calling backend service to schedule scan
    const newJob = await api.scheduleVulnerabilityScan(assetIds, scanType, scheduleTime);
    setVulnerabilityScanJobs(prev => [newJob, ...prev]);
    // The job simulation will eventually update asset scan dates.
    // We can refetch assets after a reasonable delay.
    setTimeout(() => {
      api.fetchAssets().then(setAssets);
    }, (assetIds.length * 2000) + 5000); // Rough estimate
  };

  const handleUpdateUser = (userId: string, updates: any) => {
    api.updateUser(userId, updates).then(allUsers => {
      setUsers(allUsers);
    }).catch(error => {
      showToast(error.message || "Failed to update user.", 'error');
    });
  };

  const handleDeleteUser = (userId: string) => {
    if (window.confirm("Are you sure you want to delete this user? This action cannot be undone.")) {
      api.deleteUser(userId).then(allUsers => {
        setUsers(allUsers);
      }).catch(error => {
        showToast(error.message || "Failed to delete user.", 'error');
      });
    }
  };

  const handleResetPassword = async (userId: string, userName: string) => {
    if (window.confirm(`Are you sure you want to reset the password for ${userName}?`)) {
      await api.resetPassword(userId);
      showToast(`Password reset link sent to the user's email.`, 'success');
    }
  };

  const handleAddNewUser = async (user: NewUserPayload) => {
    try {
      const allUsers = await api.addUser(user);
      setUsers(allUsers);
    } catch (error: any) {
      showToast(error.message || "Failed to add user. Please try again.", 'error');
    }
  };

  const handleProfileUpdate = (updates: { name: string, avatar: string }) => {
    if (currentUser) {
      api.updateUser(currentUser.id, updates).then(allUsers => {
        setUsers(allUsers);
        const updatedSelf = allUsers.find(u => u.id === currentUser.id);
        if (updatedSelf) setCurrentUser(updatedSelf);
      }).catch(error => {
        showToast(error.message || "Failed to update profile.", 'error');
      });
    }
  };

  const handleGenerateApiKey = (name: string) => {
    if (activeTenantId && currentUser) {
      api.generateApiKey(activeTenantId, name, currentUser.id).then(keyInfo => {
        setNewlyGeneratedKey(keyInfo);
      });
    }
  };

  const handleRevokeApiKey = (keyId: string) => {
    if (activeTenantId && window.confirm("Are you sure you want to revoke this API key? This action is permanent.")) {
      api.revokeApiKey(activeTenantId, keyId).then(() => {
        api.fetchTenants().then(setTenants); // Re-fetch to update keys
      });
    }
  };

  const handleSaveRole = (role: Role) => {
    api.saveRole(role).then(savedRole => {
      setRoles(prev => {
        const exists = prev.some(r => r.id === savedRole.id);
        if (exists) return prev.map(r => r.id === savedRole.id ? savedRole : r);
        return [...prev, savedRole];
      });
    });
  };

  const handleDeleteRole = (roleId: string) => {
    api.deleteRole(roleId).then(() => {
      setRoles(prev => prev.filter(r => r.id !== roleId));
    });
  };

  const handleCaseUpdate = async (caseItem: SecurityCase): Promise<SecurityCase> => {
    const updatedCase = await api.updateSecurityCase(caseItem);
    setSecurityCases(prev => {
      const exists = prev.some(c => c.id === updatedCase.id);
      return exists
        ? prev.map(c => c.id === updatedCase.id ? updatedCase : c)
        : [updatedCase, ...prev];
    });
    return updatedCase;
  };

  const handleGeneratePlaybook = async (prompt: string): Promise<void> => {
    try {
      const newPlaybook = await api.generatePlaybook(prompt);
      setPlaybooks(prev => [newPlaybook, ...prev]);
    } catch (error) {
      showToast(`Failed to generate playbook: ${error instanceof Error ? error.message : 'Unknown error'}`, 'error');
    }
  };

  const handleUpdateSystem = (system: AiSystem) => {
    api.updateAiSystem(system).then(updatedSystem => {
      setAiSystems(prev => prev.map(s => s.id === updatedSystem.id ? updatedSystem : s));
    });
  };

  const handleAddNewSystem = (data: Omit<AiSystem, 'id' | 'tenantId' | 'lastAssessmentDate' | 'fairnessMetrics' | 'impactAssessment' | 'risks' | 'documentation' | 'controls' | 'performanceData' | 'securityAlerts'>) => {
    if (!activeTenantId) return;
    api.addAiSystem(data, activeTenantId).then(newSystem => {
      setAiSystems(prev => [...prev, newSystem]);
    });
  };

  const handlePromoteModel = (modelId: string, toStage: ModelStage) => {
    api.promoteModel(modelId, toStage).then(updatedModel => {
      setRegisteredModels(prev => prev.map(m => m.id === updatedModel.id ? updatedModel : m));
    });
  };

  const handleUpdateAutomationPolicy = (policy: AutomationPolicy) => {
    api.updateAutomationPolicy(policy).then(updatedPolicy => {
      setAutomationPolicies(prev => prev.map(p => p.id === updatedPolicy.id ? updatedPolicy : p));
    });
  };

  const handleAddAutomationPolicy = (policy: Omit<AutomationPolicy, 'id'>) => {
    api.createAutomationPolicy(policy).then(newPolicy => {
      setAutomationPolicies(prev => [newPolicy, ...prev]);
    });
  };

  const handleUploadSbom = async (file: File) => {
    if (!activeTenantId) return;
    const { newSbom, newComponents } = await api.uploadSbom(file);
    setSboms(prev => [newSbom, ...prev]);
    setSoftwareComponents(prev => [...prev, ...newComponents]);
  };

  const handleAnalyzeImpact = (type: 'alert' | 'case', id: string) => {
    api.fetchIncidentImpactGraph(id).then(graph => {
      setIncidentImpactGraph(graph);
      setViewingImpactFor({ type, id });
      handleSetCurrentView('incidentImpact');
    });
  };

  const handleAddNewDevice = (deviceData: Omit<NetworkDevice, 'id' | 'tenantId' | 'status' | 'lastSeen' | 'interfaces' | 'configBackups' | 'vulnerabilities'>) => {
    if (!activeTenantId) return;
    api.addNetworkDevice(deviceData, activeTenantId).then(newDevice => {
      setNetworkDevices(prev => [...prev, newDevice]);
    });
  };

  const handleAddCloudAccount = async (accountData: Omit<CloudAccount, 'id' | 'tenantId' | 'status'>) => {
    if (!activeTenantId) return;
    const newAccount = await api.addCloudAccount(accountData, activeTenantId);
    setCloudAccounts(prev => [...prev, newAccount]);
  };

  const handleExecuteCommand = (command: Command) => {
    switch (command.name) {
      case 'navigateToView':
        handleSetCurrentView(command.args.view as AppView);
        break;
      case 'applyFilter':
        const { view, filterType, value } = command.args;
        const newFilter = { type: filterType, value };
        if (view === 'agents') {
          setAgentFilters([newFilter]);
        } else if (view === 'assetManagement') {
          setAssetFilters([newFilter]);
        }
        handleSetCurrentView(view);
        break;
    }
    setIsCommandBarOpen(false);
  };

  const handleAddTask = async (text: string, priority: Priority) => {
    try {
      const newTask = await api.createTask(text, priority);
      setMyTasks(prev => [newTask, ...prev]);
    } catch {
      const newTask: Task = { id: Date.now(), text, priority, completed: false };
      setMyTasks(prev => [newTask, ...prev]);
    }
  };

  const handleToggleTask = async (id: number) => {
    const task = myTasks.find(t => t.id === id);
    if (!task) return;
    setMyTasks(prev => prev.map(t => t.id === id ? { ...t, completed: !t.completed } : t));
    try {
      await api.updateTask(id, { completed: !task.completed });
    } catch {
      setMyTasks(prev => prev.map(t => t.id === id ? { ...t, completed: task.completed } : t));
    }
  };

  const handleDeleteTask = async (id: number) => {
    setMyTasks(prev => prev.filter(t => t.id !== id));
    try {
      await api.deleteTask(id);
    } catch {
      // deletion best-effort; task already removed from UI
    }
  };

  const userContextValue = useMemo(() => ({
    currentUser,
    login: handleLogin,
    logout,
    signup,
    registerTenant,
    hasPermission,
    enabledFeatures,
    serverLockedFeatures,
  }), [currentUser, handleLogin, logout, signup, registerTenant, hasPermission, enabledFeatures, serverLockedFeatures]);

  // --- RENDER LOGIC ---
  if (error) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-100 dark:bg-gray-900">
        <div className="p-8 bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl text-center">
          <AlertTriangleIcon className="mx-auto text-red-500" size={48} />
          <h2 className="mt-4 text-2xl font-bold text-gray-800 dark:text-white">Connection Error</h2>
          <p className="mt-2 text-gray-600 dark:text-gray-300 whitespace-pre-wrap">{error}</p>
        </div>
      </div>
    );
  }

  if (!currentUser) {
    return (
      <ThemeProvider>
        <UserContext.Provider value={userContextValue}>
          <LoginPage users={users} onLogin={handleLogin} onSignup={handleSignup} />
        </UserContext.Provider>
      </ThemeProvider>
    );
  }

  const renderView = () => {
    if (viewingImpactFor && currentView === 'incidentImpact' && incidentImpactGraph) {
      // Pass-through to switch case
    }

    switch (currentView) {
      case 'dashboard': return <ErrorBoundary name="Dashboard"><Dashboard metrics={metrics} alerts={tenantData.alerts} complianceFrameworks={tenantData.complianceFrameworks} aiSystems={tenantData.aiSystems} agents={tenantData.agents} currentUser={currentUser} setCurrentView={handleSetCurrentView} /></ErrorBoundary>;
      case 'cxo': return <ErrorBoundary name="CXODashboard"><CXODashboard /></ErrorBoundary>;
      case 'executiveSummary': return <ErrorBoundary name="ExecutiveDashboard"><ExecutiveDashboard tenantId={activeTenantId} /></ErrorBoundary>;
      case 'reporting': return <ErrorBoundary name="ReportingDashboard"><ReportingDashboard historicalData={historicalData} assets={tenantData.assets} /></ErrorBoundary>;
      case 'agents': return <ErrorBoundary name="AgentsDashboard"><AgentsDashboard
        agents={tenantData.agents}
        assets={tenantData.assets}
        registrationKey={tenants.find(t => t.id === activeTenantId)?.registrationKey || null}
        onRegisterAgent={() => setIsRegisterAgentModalOpen(true)}
        onUpdateAgent={handleUpdateAgent}
        agentUpgradeJobs={tenantData.agentUpgradeJobs}
        onScheduleUpgrade={handleScheduleUpgrade}
        filters={agentFilters}
        onClearFilters={() => setAgentFilters([])}
        logs={tenantData.logs}
        tenants={tenants.filter(t => t.id !== 'platform-admin')}
        onSelectTenant={(id) => setViewingTenantId(id)}
        onDeleteAgent={handleDeleteAgent}
        activeTenantId={activeTenantId}
        subscriptionTier={
          tenants.find(t => t.id === activeTenantId)?.subscriptionTier ||
          (currentUser as any)?.subscriptionTier ||
          'Free'
        }
      /></ErrorBoundary>;
      case 'agentCapabilities': return <ErrorBoundary name="AgentCapabilitiesDashboard"><AgentCapabilitiesDashboard /></ErrorBoundary>;
      case 'assetManagement': return <ErrorBoundary name="AssetManagementDashboard"><AssetManagementDashboard assets={tenantData.assets} patches={tenantData.patches} onRunVulnerabilityScan={handleRunVulnerabilityScan} filters={assetFilters} onClearFilters={() => setAssetFilters([])} vulnerabilityScanJobs={tenantData.vulnerabilityScanJobs} onScheduleVulnerabilityScan={handleScheduleVulnerabilityScan} onDeleteAsset={handleDeleteAsset} /></ErrorBoundary>;
      case 'softwareUpdates': return <ErrorBoundary name="SoftwareUpdateManagement"><SoftwareUpdateManagement assets={tenantData.assets} /></ErrorBoundary>;
      case 'patchManagement': return <ErrorBoundary name="PatchManagementDashboard"><PatchManagementDashboard patches={tenantData.patches} assets={tenantData.assets} patchDeploymentJobs={tenantData.patchDeploymentJobs} onSchedulePatchDeployment={handleSchedulePatchDeployment} vulnerabilityScanJobs={tenantData.vulnerabilityScanJobs} onScheduleVulnerabilityScan={handleScheduleVulnerabilityScan} /></ErrorBoundary>;
      case 'deploymentApprovals': return <ErrorBoundary name="ApprovalDashboard"><ApprovalDashboard currentUser={currentUser} /></ErrorBoundary>;
      case 'stagedDeployments': return <ErrorBoundary name="StagedDeploymentsPage"><StagedDeploymentsPage /></ErrorBoundary>;
      case 'vulnerabilityManagement': return <ErrorBoundary name="VulnerabilityManagement"><VulnerabilityManagement /></ErrorBoundary>;
      case 'cloudSecurity': return <ErrorBoundary name="CloudSecurityDashboard"><CloudSecurityDashboard cloudAccounts={tenantData.cloudAccounts} findings={tenantData.cspmFindings} onAddAccount={handleAddCloudAccount} /></ErrorBoundary>;
      case 'cloudAccounts': return <ErrorBoundary name="CloudAccountsDashboard"><CloudAccountsDashboard /></ErrorBoundary>;
      case 'cloudChecksScanner': return <ErrorBoundary name="CloudChecksScanner"><CloudChecksScanner /></ErrorBoundary>;
      case 'iacContainer': return <ErrorBoundary name="IacContainerDashboard"><IacContainerDashboard /></ErrorBoundary>;
      case 'security': return <ErrorBoundary name="SecurityDashboard"><SecurityDashboard securityCases={tenantData.securityCases} playbooks={playbooks} securityEvents={tenantData.securityEvents} users={users} onCaseUpdate={handleCaseUpdate} onGeneratePlaybook={handleGeneratePlaybook} onAnalyzeImpact={handleAnalyzeImpact} threatIntelFeed={threatIntelFeed} /></ErrorBoundary>;
      case 'compliance': return <ErrorBoundary name="ComplianceDashboard"><ComplianceDashboard complianceFrameworks={tenantData.complianceFrameworks} assets={tenantData.assets} assetComplianceData={tenantData.assetComplianceData || []} /></ErrorBoundary>;
      case 'programs': return <ErrorBoundary name="ProgramsDashboard"><ProgramsDashboard /></ErrorBoundary>;
      case 'inboundQuestionnaires': return <ErrorBoundary name="InboundQuestionnaireDashboard"><InboundQuestionnaireDashboard /></ErrorBoundary>;
      case 'governanceDocuments': return <ErrorBoundary name="GovernanceDocumentsDashboard"><GovernanceDocumentsDashboard /></ErrorBoundary>;
      case 'auditProgram': return <ErrorBoundary name="AuditProgramDashboard"><AuditProgramDashboard /></ErrorBoundary>;
      case 'accessReview': return <ErrorBoundary name="AccessReviewDashboard"><AccessReviewDashboard /></ErrorBoundary>;
      case 'cookieConsent': return <ErrorBoundary name="CookieConsentDashboard"><CookieConsentDashboard /></ErrorBoundary>;
      case 'maturityScore': return <ErrorBoundary name="MaturityScoreDashboard"><MaturityScoreDashboard /></ErrorBoundary>;
      case 'saasIntegrations': return <ErrorBoundary name="SaaSIntegrationsDashboard"><SaaSIntegrationsDashboard /></ErrorBoundary>;
      case 'aiGovernance': return <ErrorBoundary name="AIGovernanceDashboard"><AIGovernanceDashboard aiSystems={tenantData.aiSystems} users={users} onUpdateSystem={handleUpdateSystem} onAddNewSystem={handleAddNewSystem} registeredModels={tenantData.registeredModels} modelExperiments={tenantData.modelExperiments} onPromoteModel={handlePromoteModel} /></ErrorBoundary>;
      case 'finops': return <ErrorBoundary name="FinOpsBillingPage"><FinOpsBillingPage tenants={tenants} isSuperAdminView={currentUser.role === 'Super Admin' || currentUser.role === 'superadmin'} /></ErrorBoundary>;
      case 'auditLog': return <ErrorBoundary name="AuditLogDashboard"><AuditLogDashboard logs={tenantData.auditLogs} /></ErrorBoundary>;
      case 'settings': return <ErrorBoundary name="SettingsDashboard"><SettingsDashboard integrations={tenantData.integrations} alertRules={tenantData.alertRules} roles={roles} users={currentUser.role === 'Super Admin' || currentUser.role === 'superadmin' ? users : users.filter(u => activeTenantId ? u.tenantId === activeTenantId : true)} apiKeys={tenants.find(t => t.id === activeTenantId)?.apiKeys || []} newlyGeneratedKey={newlyGeneratedKey} onAcknowledgeNewKey={() => setNewlyGeneratedKey(null)} onGenerateApiKey={handleGenerateApiKey} onRevokeApiKey={handleRevokeApiKey} onSaveAlertRule={(rule) => api.saveAlertRule(rule).then(saved => setAlertRules(prev => { const exists = prev.some(r => r.id === saved.id); return exists ? prev.map(r => r.id === saved.id ? saved : r) : [...prev, saved]; }))} onDeleteAlertRule={(id) => api.deleteAlertRule(id).then(() => setAlertRules(prev => prev.filter(r => r.id !== id)))} onSaveIntegration={(int) => api.saveIntegration(int).then(saved => setIntegrations(prev => prev.map(i => i.id === saved.id ? saved : i)))} onToggleIntegration={(id) => { const int = integrations.find(i => i.id === id); if (int) api.saveIntegration({ ...int, isEnabled: !int.isEnabled }).then(saved => setIntegrations(prev => prev.map(i => i.id === saved.id ? saved : i))) }} onSaveRole={handleSaveRole} onDeleteRole={handleDeleteRole} tenants={tenants} onAddNewUser={handleAddNewUser} onUpdateUser={handleUpdateUser} onResetPassword={handleResetPassword} databaseSettings={databaseSettings} llmSettings={llmSettings} onSaveInfrastructure={(updates) => api.saveInfrastructure(updates).then(res => { if (res.db) setDatabaseSettings(res.db); if (res.llm) setLlmSettings(res.llm); })} dataSources={tenantData.dataSources} onSaveDataSource={(source) => api.saveDataSource({ ...source, tenantId: activeTenantId! }).then(saved => { setDataSources(prev => { const exists = prev.some(s => s.id === saved.id); if (exists) return prev.map(s => s.id === saved.id ? saved : s); return [...prev, saved]; }) })} onDeleteDataSource={(id) => api.deleteDataSource(id).then(() => setDataSources(prev => prev.filter(s => s.id !== id)))} onTestDataSource={(id) => api.testDataSourceConnection(dataSources.find(ds => ds.id === id)!).then(() => api.fetchDataSources().then(setDataSources))} onSaveTenantFeatures={handleTenantAdminFeatureSave} onSaveTenantVoiceBotSettings={(settings) => activeTenantId ? api.updateTenantVoiceBotSettings(activeTenantId, settings).then(updated => { setTenants(prev => prev.map(t => t.id === updated.id ? updated : t)); }) : Promise.resolve()} onDeleteUser={handleDeleteUser} /></ErrorBoundary>;
      case 'bundleManagement': return <ErrorBoundary name="BundleManagementDashboard"><Suspense fallback={<SkeletonDashboard />}><BundleManagementDashboard /></Suspense></ErrorBoundary>;
      case 'tenantManagement': return <ErrorBoundary name="TenantManagementDashboard"><TenantManagementDashboard tenants={tenants.filter(t => t.id !== 'platform-admin')} onAddNewTenant={() => setIsAddTenantModalOpen(true)} onViewTenant={(id) => { setViewingTenantId(id); handleSetCurrentView('agents'); }} onManageTenant={(t) => setManagingTenant(tenants.find(T => T.id === t.id) || null)} handleDelete={handleDeleteTenant} handleUpdateTenant={async (id, data) => { await api.updateTenantFeatures(id, data.enabledFeatures || [], data.subscriptionTier || 'Free'); loadAllData(); }} /></ErrorBoundary>;
      case 'siem': return <ErrorBoundary name="ThreatDashboard"><ThreatDashboard /></ErrorBoundary>;
      case 'siemRules': return <ErrorBoundary name="SiemRulesDashboard"><SiemRulesDashboard /></ErrorBoundary>;
      case 'incidentResponse': return <ErrorBoundary name="IncidentResponseDashboard"><IncidentResponseDashboard /></ErrorBoundary>;
      case 'logExplorer': return <ErrorBoundary name="LogExplorerDashboard"><LogExplorerDashboard /></ErrorBoundary>;
      case 'threatHunting': return <ErrorBoundary name="ThreatHuntingDashboard"><ThreatHuntingDashboard findings={tenantData.uebaFindings} auditLogs={auditLogs} users={users} /></ErrorBoundary>;
      case 'incidentImpact': return <ErrorBoundary name="IncidentImpactDashboard"><IncidentImpactDashboard graph={incidentImpactGraph!} context={viewingImpactFor} alerts={tenantData.alerts} cases={tenantData.securityCases} onAnalyze={handleAnalyzeImpact} /></ErrorBoundary>;
      case 'pentest': return <ErrorBoundary name="PentestDashboard"><PentestDashboard tenantId={activeTenantId ?? ''} /></ErrorBoundary>;
      case 'playbooks': return <ErrorBoundary name="PlaybookBuilder"><PlaybookBuilder /></ErrorBoundary>;
      case 'soar': return <ErrorBoundary name="SOARDashboard"><SOARDashboard tenantId={activeTenantId ?? ''} /></ErrorBoundary>;
      case 'threatIntelligence': return (
        <ErrorBoundary name="ThreatIntelligence">
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Threat Intelligence</h1>
            </div>
            <ThreatIntelFeedEnhanced tenantId={activeTenantId ?? ''} />
          </div>
        </ErrorBoundary>
      );
      case 'securityIntelConnectors': return (
        <ErrorBoundary name="SecurityIntelConnectors">
          <SecurityIntelConnectors />
        </ErrorBoundary>
      );
      case 'profile': return <ErrorBoundary name="UserProfilePage"><UserProfilePage onProfileUpdate={handleProfileUpdate} /></ErrorBoundary>;
      case 'automation': return <ErrorBoundary name="AutomationPoliciesDashboard"><AutomationPoliciesDashboard policies={tenantData.automationPolicies} onUpdatePolicy={handleUpdateAutomationPolicy} onAddPolicy={handleAddAutomationPolicy} /></ErrorBoundary>;
      case 'notificationsRouting': return <ErrorBoundary name="NotificationsDashboard"><NotificationsDashboard /></ErrorBoundary>;
      case 'devsecops': return <ErrorBoundary name="DevSecOpsDashboard"><DevSecOpsDashboard sboms={tenantData.sboms} softwareComponents={tenantData.softwareComponents} onUploadSbom={handleUploadSbom} sastFindings={tenantData.sastFindings} repositories={tenantData.codeRepositories} initialTab="sast" mode="sast-only" /></ErrorBoundary>;
      case 'apiExtensions': return <ErrorBoundary name="ApiExtensionsDashboard"><ApiExtensionsDashboard /></ErrorBoundary>;
      case 'sbom': return <ErrorBoundary name="DevSecOpsDashboardSbom"><DevSecOpsDashboard sboms={tenantData.sboms} softwareComponents={tenantData.softwareComponents} onUploadSbom={handleUploadSbom} sastFindings={tenantData.sastFindings} repositories={tenantData.codeRepositories} initialTab="sbom" mode="sbom-only" /></ErrorBoundary>;
      case 'developer_hub': return <ErrorBoundary name="DeveloperHubDashboard"><DeveloperHubDashboard endpoints={apiDocs} /></ErrorBoundary>;
      case 'proactiveInsights': return <ErrorBoundary name="ProactiveInsightsDashboard"><ProactiveInsightsDashboard insights={tenantData.proactiveInsights} /></ErrorBoundary>;
      case 'distributedTracing': return <ErrorBoundary name="DistributedTracingDashboard"><DistributedTracingDashboard traces={tenantData.traces} serviceMap={tenantData.serviceMap} /></ErrorBoundary>;
      case 'dataSecurity': return <ErrorBoundary name="DataSecurityDashboard"><DataSecurityDashboard findings={tenantData.sensitiveDataFindings} /></ErrorBoundary>;
      case 'attackPath': return <ErrorBoundary name="AttackPathDashboard"><AttackPathDashboard attackPaths={tenantData.attackPaths} /></ErrorBoundary>;
      case 'serviceCatalog':
        return <ErrorBoundary name="ServiceCatalogDashboard"><ServiceCatalogDashboard templates={tenantData.serviceTemplates} provisionedServices={tenantData.provisionedServices} /></ErrorBoundary>;
      case 'servicePricing':
        return <ErrorBoundary name="ServicePricingPage"><ServicePricingPage /></ErrorBoundary>;
      case 'doraMetrics': return <ErrorBoundary name="DoraMetricsDashboard"><DoraMetricsDashboard metrics={tenantData.doraMetrics} /></ErrorBoundary>;
      case 'chaosEngineering': return <ErrorBoundary name="ChaosEngineeringDashboard"><ChaosEngineeringDashboard /></ErrorBoundary>;
      case 'networkObservability': console.log("[App] Rendering NetworkObservability with:", tenantData.networkDevices); return <ErrorBoundary name="NetworkObservabilityDashboard"><NetworkObservabilityDashboard networkDevices={tenantData.networkDevices} onAddDevice={handleAddNewDevice} onRefresh={loadAllData} /></ErrorBoundary>;
      case 'dataUtilization': return <ErrorBoundary name="DataUtilizationDashboard"><DataUtilizationDashboard /></ErrorBoundary>;
      case 'tasks': return (
        <ErrorBoundary name="Tasks">
          <div className="max-w-4xl mx-auto">
            <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-6">My Tasks</h2>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
              <TaskForm onAdd={handleAddTask} />
              <TaskList tasks={myTasks} onToggle={handleToggleTask} onDelete={handleDeleteTask} />
            </div>
          </div>
        </ErrorBoundary>
      );
      // 2030 Industry Features
      case 'webhooks': return <ErrorBoundary name="WebhookManagement"><WebhookManagement /></ErrorBoundary>;
      case 'sustainability': return <ErrorBoundary name="SustainabilityDashboard"><SustainabilityDashboard /></ErrorBoundary>;
      case 'zeroTrustQuantum': return <ErrorBoundary name="ZeroTrustQuantumDashboard"><ZeroTrustQuantumDashboard /></ErrorBoundary>;
      case 'paymentSettings': return <ErrorBoundary name="PaymentSettings"><PaymentSettings /></ErrorBoundary>;
      case 'subscriptionManagement': return <ErrorBoundary name="SubscriptionManagement"><SubscriptionManagement /></ErrorBoundary>;
      case 'invoices': return <ErrorBoundary name="InvoiceList"><InvoiceList /></ErrorBoundary>;
      case 'unifiedOps':
      case 'futureOps':
        return <ErrorBoundary name="FutureOpsDashboard"><FutureOpsDashboard /></ErrorBoundary>;
      case 'futureTech':
        return <ErrorBoundary name="FutureTechDashboard"><FutureTechDashboard /></ErrorBoundary>;
      case 'swarm': return <ErrorBoundary name="SwarmDashboard"><Suspense fallback={<SkeletonDashboard />}><SwarmDashboard /></Suspense></ErrorBoundary>;
      case 'digitalTwin': return <ErrorBoundary name="SimulationDashboard"><Suspense fallback={<SkeletonDashboard />}><SimulationDashboard /></Suspense></ErrorBoundary>;
      case 'riskRegister': return <ErrorBoundary name="RiskRegister"><RiskRegister /></ErrorBoundary>;
      case 'vendorManagement': return <ErrorBoundary name="VendorManagement"><VendorManagement /></ErrorBoundary>;
      case 'trustCenter': return <ErrorBoundary name="TrustCenter"><TrustCenter /></ErrorBoundary>;
      case 'trustPage': return <ErrorBoundary name="TrustPage"><TrustPage /></ErrorBoundary>;
      case 'secureFileShare': return <ErrorBoundary name="SecureFileShare"><SecureFileShare /></ErrorBoundary>;
      case 'securityTraining': return <ErrorBoundary name="SecurityTraining"><SecurityTraining /></ErrorBoundary>;
      case 'complianceOracle': return <ErrorBoundary name="ComplianceOracleDashboard"><Suspense fallback={<SkeletonDashboard />}><ComplianceOracleDashboard /></Suspense></ErrorBoundary>;
      case 'cissporacle': return <ErrorBoundary name="CISSPOracle"><Suspense fallback={<SkeletonDashboard />}><CISSPOracle /></Suspense></ErrorBoundary>;
      case 'complianceFrameworks': return <ErrorBoundary name="ComplianceFrameworksDashboard"><Suspense fallback={<SkeletonDashboard />}><ComplianceFrameworksDashboard /></Suspense></ErrorBoundary>;
      case 'jobs': return <ErrorBoundary name="JobsDashboard"><Suspense fallback={<SkeletonDashboard />}><JobsDashboard /></Suspense></ErrorBoundary>;
      case 'llmops': return <ErrorBoundary name="LLMOpsDashboard"><Suspense fallback={<SkeletonDashboard />}><LLMOpsDashboard /></Suspense></ErrorBoundary>;
      case 'softwareDeployment': return <ErrorBoundary name="SoftwareDeployment"><Suspense fallback={<SkeletonDashboard />}><SoftwareDeployment /></Suspense></ErrorBoundary>;
      case 'securitySimulation': return <ErrorBoundary name="SecuritySimulation"><Suspense fallback={<SkeletonDashboard />}><SecuritySimulation /></Suspense></ErrorBoundary>;
      case 'dast': return <ErrorBoundary name="DASTDashboard"><DASTDashboard /></ErrorBoundary>;
      case 'serviceMesh': return <ErrorBoundary name="ServiceMeshDashboard"><ServiceMeshDashboard /></ErrorBoundary>;
      case 'persistence':
      case 'persistenceDetection': return <ErrorBoundary name="PersistenceDashboard"><Suspense fallback={<SkeletonDashboard />}><PersistenceDashboard /></Suspense></ErrorBoundary>;
      case 'approvalWorkflows': return <ErrorBoundary name="MultiStepApprovalDashboard"><Suspense fallback={<SkeletonDashboard />}><MultiStepApprovalDashboard /></Suspense></ErrorBoundary>;
      case 'advancedBi':
      case 'biDashboard': return <ErrorBoundary name="AdvancedBiDashboard"><AdvancedBiDashboard tenantId={activeTenantId || undefined} /></ErrorBoundary>;
      case 'systemHealth': return <ErrorBoundary name="SystemHealthDashboard"><Suspense fallback={<SkeletonDashboard />}><SystemHealthDashboard /></Suspense></ErrorBoundary>;
      case 'apiStatus': return <ErrorBoundary name="ApiStatusDashboard"><ApiStatusDashboard /></ErrorBoundary>;
      case 'predictiveHealth': return <ErrorBoundary name="PredictiveHealthDashboard"><Suspense fallback={<SkeletonDashboard />}><PredictiveHealthDashboard /></Suspense></ErrorBoundary>;
      case 'goalSystem': return <ErrorBoundary name="GoalSystemDashboard"><Suspense fallback={<SkeletonDashboard />}><GoalSystemDashboard /></Suspense></ErrorBoundary>;
      case 'integrationsHub': return <ErrorBoundary name="IntegrationsHub"><Suspense fallback={<SkeletonDashboard />}><IntegrationsHub /></Suspense></ErrorBoundary>;
      case 'securityAudit': return <ErrorBoundary name="SecurityAuditDashboard"><SecurityAuditDashboard /></ErrorBoundary>;
      case 'dataWarehouse': return <ErrorBoundary name="DataWarehouseDashboard"><DataWarehouseDashboard /></ErrorBoundary>;
      case 'streaming': return <ErrorBoundary name="StreamingDashboard"><StreamingDashboard /></ErrorBoundary>;
      case 'dataGovernance': return <ErrorBoundary name="DataGovernanceDashboard"><DataGovernanceDashboard /></ErrorBoundary>;
      case 'webMonitoring': return <ErrorBoundary name="WebMonitoringDashboard"><WebMonitoringDashboard /></ErrorBoundary>;
      case 'mlops': return <ErrorBoundary name="MLOpsDashboard"><MLOpsDashboard /></ErrorBoundary>;
      case 'modelMonitoring': return <ErrorBoundary name="ModelMonitoringDashboard"><ModelMonitoringDashboard tenantId={activeTenantId ?? ''} /></ErrorBoundary>;
      case 'automl': return <ErrorBoundary name="AutoMLDashboard"><AutoMLDashboard /></ErrorBoundary>;
      case 'xai': return <ErrorBoundary name="XAIDashboard"><XAIDashboard /></ErrorBoundary>;
      case 'abTesting': return <ErrorBoundary name="ABTestingDashboard"><ABTestingDashboard /></ErrorBoundary>;
      case 'edr': return <ErrorBoundary name="EDRDashboard"><EDRDashboard token={sessionStorage.getItem('token') || undefined} /></ErrorBoundary>;
      case 'yaraRules': return <ErrorBoundary name="YaraRuleEditor"><Suspense fallback={<SkeletonDashboard />}><YaraRuleEditor /></Suspense></ErrorBoundary>;
      case 'alertManagement': return <ErrorBoundary name="AlertManagementDashboard"><Suspense fallback={<SkeletonDashboard />}><AlertManagementDashboard /></Suspense></ErrorBoundary>;
      case 'complianceEvidence': return <ErrorBoundary name="ComplianceEvidenceStatusDashboard"><Suspense fallback={<SkeletonDashboard />}><ComplianceEvidenceStatusDashboard agents={tenantData.agents} /></Suspense></ErrorBoundary>;
      case 'remediationWorkflow': return <ErrorBoundary name="RemediationDashboard"><Suspense fallback={<SkeletonDashboard />}><RemediationDashboard /></Suspense></ErrorBoundary>;
      case 'mdr': return <ErrorBoundary name="MDRDashboard"><MDRDashboard /></ErrorBoundary>;
      case 'xdr': return <ErrorBoundary name="XDRDashboard"><XDRDashboard /></ErrorBoundary>;
      case 'mitreAttack': return <ErrorBoundary name="MitreAttackHeatmap"><Suspense fallback={<SkeletonDashboard />}><MitreAttackHeatmap /></Suspense></ErrorBoundary>;
      case 'dlp': return <ErrorBoundary name="DLPDashboard"><Suspense fallback={<SkeletonDashboard />}><DLPDashboard /></Suspense></ErrorBoundary>;
      case 'ticketing': return <ErrorBoundary name="TicketingIntegration"><Suspense fallback={<SkeletonDashboard />}><TicketingIntegration /></Suspense></ErrorBoundary>;
      case 'internalTickets': return <ErrorBoundary name="InternalTicketsDashboard"><Suspense fallback={<SkeletonDashboard />}><InternalTicketsDashboard currentUserEmail={currentUser?.email ?? ''} /></Suspense></ErrorBoundary>;
      case 'ueba': return <ErrorBoundary name="UEBADashboard"><UEBADashboard /></ErrorBoundary>;
      case 'vulnerabilities': return <ErrorBoundary name="VulnerabilityManagement2"><VulnerabilityManagement /></ErrorBoundary>;
      case 'apm': return <ErrorBoundary name="APMDashboard"><APMDashboard tenantId={activeTenantId || ''} /></ErrorBoundary>;
      case 'agentApproval': return <ErrorBoundary name="AgentApprovalDashboard"><AgentApprovalDashboard /></ErrorBoundary>;
      case 'cloudIntegrations': return <ErrorBoundary name="CloudIntegrationsDashboard"><CloudIntegrationsDashboard /></ErrorBoundary>;
      case 'jitAccess': return <ErrorBoundary name="JITAccessDashboard"><JITAccessDashboard /></ErrorBoundary>;
      case 'windowsAutopilot': return <ErrorBoundary name="AutopilotDashboard"><Suspense fallback={<SkeletonDashboard />}><AutopilotDashboard /></Suspense></ErrorBoundary>;
      case 'conditionalAccess': return <ErrorBoundary name="ConditionalAccessDashboard"><Suspense fallback={<SkeletonDashboard />}><ConditionalAccessDashboard /></Suspense></ErrorBoundary>;
      case 'mobileDeviceManagement': return <ErrorBoundary name="MobileDashboard"><Suspense fallback={<SkeletonDashboard />}><MobileDashboard /></Suspense></ErrorBoundary>;
      case 'branchSites': return <ErrorBoundary name="BranchSitesDashboard"><Suspense fallback={<SkeletonDashboard />}><BranchSitesDashboard /></Suspense></ErrorBoundary>;
      case 'appCatalog': return <ErrorBoundary name="AppCatalogDashboard"><Suspense fallback={<SkeletonDashboard />}><AppCatalogDashboard /></Suspense></ErrorBoundary>;
      case 'assetIntelligence': return <ErrorBoundary name="AssetIntelligenceDashboard"><Suspense fallback={<SkeletonDashboard />}><AssetIntelligenceDashboard /></Suspense></ErrorBoundary>;
      case 'mobileAppManagement': return <ErrorBoundary name="MAMDashboard"><Suspense fallback={<SkeletonDashboard />}><MAMDashboard /></Suspense></ErrorBoundary>;
      case 'androidEnterprise': return <ErrorBoundary name="AndroidEnterpriseDashboard"><Suspense fallback={<SkeletonDashboard />}><AndroidEnterpriseDashboard /></Suspense></ErrorBoundary>;
      case 'deviceConfigProfiles': return <ErrorBoundary name="DeviceConfigProfilesDashboard"><Suspense fallback={<SkeletonDashboard />}><DeviceConfigProfilesDashboard /></Suspense></ErrorBoundary>;
      case 'firmwareDriverUpdates': return <ErrorBoundary name="FirmwareDriverDashboard"><Suspense fallback={<SkeletonDashboard />}><FirmwareDriverDashboard /></Suspense></ErrorBoundary>;
      case 'advancedHunting': return <ErrorBoundary name="AdvancedHuntingDashboard"><Suspense fallback={<SkeletonDashboard />}><AdvancedHuntingDashboard /></Suspense></ErrorBoundary>;
      case 'detectionRules': return <ErrorBoundary name="DetectionRulesDashboard"><Suspense fallback={<SkeletonDashboard />}><DetectionRulesDashboard /></Suspense></ErrorBoundary>;
      case 'connectorsHub': return <ErrorBoundary name="ConnectorsHubDashboard"><Suspense fallback={<SkeletonDashboard />}><ConnectorsHubDashboard /></Suspense></ErrorBoundary>;
      case 'securityCopilot': return <ErrorBoundary name="SecurityCopilotDashboard"><Suspense fallback={<SkeletonDashboard />}><SecurityCopilotDashboard /></Suspense></ErrorBoundary>;
      case 'msspMonitoring': return <ErrorBoundary name="MSSPDashboard"><Suspense fallback={<SkeletonDashboard />}><MSSPDashboard /></Suspense></ErrorBoundary>;
      case 'attackTimeline': return <ErrorBoundary name="AttackTimelineDashboard"><Suspense fallback={<SkeletonDashboard />}><AttackTimelineDashboard /></Suspense></ErrorBoundary>;
      case 'geographicMap': return <ErrorBoundary name="GeographicAttackMap"><Suspense fallback={<SkeletonDashboard />}><GeographicAttackMap /></Suspense></ErrorBoundary>;
      case 'retentionPolicies': return <ErrorBoundary name="RetentionPoliciesDashboard"><Suspense fallback={<SkeletonDashboard />}><RetentionPoliciesDashboard /></Suspense></ErrorBoundary>;
      case 'scaAssessment': return <ErrorBoundary name="SCADashboard"><Suspense fallback={<SkeletonDashboard />}><SCADashboard /></Suspense></ErrorBoundary>;
      case 'agentGroups': return <ErrorBoundary name="AgentGroupsDashboard"><Suspense fallback={<SkeletonDashboard />}><AgentGroupsDashboard /></Suspense></ErrorBoundary>;
      case 'configDrift': return <ErrorBoundary name="ConfigDriftDashboard"><Suspense fallback={<SkeletonDashboard />}><ConfigDriftDashboard /></Suspense></ErrorBoundary>;
      case 'fimMonitoring': return <ErrorBoundary name="FIMDashboard"><Suspense fallback={<SkeletonDashboard />}><FIMDashboard /></Suspense></ErrorBoundary>;
      case 'activeResponse': return <ErrorBoundary name="ActiveResponseDashboard"><Suspense fallback={<SkeletonDashboard />}><ActiveResponseDashboard /></Suspense></ErrorBoundary>;
      case 'incidentWarRoom': return <ErrorBoundary name="IncidentWarRoomDashboard"><IncidentWarRoomDashboard /></ErrorBoundary>;
      case 'privacy': return <ErrorBoundary name="PrivacyDashboard"><PrivacyDashboard /></ErrorBoundary>;
      case 'geoSecurity': return <ErrorBoundary name="SecuritySettingsDashboard"><SecuritySettingsDashboard /></ErrorBoundary>;
      case 'fleetObservability': return <ErrorBoundary name="FleetObservabilityDashboard"><FleetObservabilityDashboard /></ErrorBoundary>;
      case 'fleetGeoMap': return <ErrorBoundary name="FleetGeoMap"><FleetGeoMap /></ErrorBoundary>;
      case 'nativeSecurity': return <ErrorBoundary name="NativeSecurityConsole"><NativeSecurityConsole /></ErrorBoundary>;
      case 'itam': return <ErrorBoundary name="ITAMConsole"><ITAMConsole tenants={tenants} isSuperAdminView={currentUser.role === 'Super Admin' || currentUser.role === 'superadmin' || currentUser.role === 'super_admin'} /></ErrorBoundary>;
      case 'privacyLegal': return <ErrorBoundary name="PrivacyLegalDashboard"><PrivacyLegalDashboard /></ErrorBoundary>;
      case 'scheduledReports': return <ErrorBoundary name="ScheduledReportsDashboard"><ScheduledReportsDashboard /></ErrorBoundary>;
      case 'secretsManagement': return <ErrorBoundary name="SecretsManagementDashboard"><SecretsManagementDashboard /></ErrorBoundary>;
      case 'customFrameworks': return <ErrorBoundary name="CustomFrameworkBuilder"><CustomFrameworkBuilder /></ErrorBoundary>;
      case 'deception': return <ErrorBoundary name="DeceptionDashboard"><DeceptionDashboard /></ErrorBoundary>;
      case 'shadowAI': return <ErrorBoundary name="ShadowAI"><ShadowAI /></ErrorBoundary>;
      case 'networkTopology': return <ErrorBoundary name="NetworkTopologyMap"><NetworkTopologyMap refreshKey={0} /></ErrorBoundary>;
      case 'hadr': return <ErrorBoundary name="HADRDashboard"><HADRDashboard /></ErrorBoundary>;
      case 'correlations': return <ErrorBoundary name="CorrelationDashboard"><CorrelationDashboard tenantId={activeTenantId || ''} /></ErrorBoundary>;
      case 'knowledgeBase': return <ErrorBoundary name="KnowledgeBaseDashboard"><KnowledgeBaseDashboard /></ErrorBoundary>;
      case 'retentionPolicy': return <ErrorBoundary name="RetentionPolicyDashboard"><RetentionPolicyDashboard /></ErrorBoundary>;
      case 'apiSecurity': return <ErrorBoundary name="APISecurityDashboard"><APISecurityDashboard /></ErrorBoundary>;
      case 'databaseMonitoring': return <ErrorBoundary name="DAMDashboard"><DAMDashboard /></ErrorBoundary>;
      case 'k8sSecurity': return <ErrorBoundary name="K8sSecurityDashboard"><K8sSecurityDashboard /></ErrorBoundary>;
      case 'ndr': return <ErrorBoundary name="NDRDashboard"><NDRDashboard /></ErrorBoundary>;
      case 'insiderThreat': return <ErrorBoundary name="InsiderThreatDashboard"><InsiderThreatDashboard /></ErrorBoundary>;
      case 'emailSecurity': return <ErrorBoundary name="EmailSecurityDashboard"><EmailSecurityDashboard /></ErrorBoundary>;
      case 'supplyChain': return <ErrorBoundary name="SupplyChainDashboard"><SupplyChainDashboard /></ErrorBoundary>;
      case 'fim': return <ErrorBoundary name="FimAlertsDashboard"><Suspense fallback={<SkeletonDashboard />}><FimAlertsDashboard /></Suspense></ErrorBoundary>;
      case 'runtimeSecurity': return <ErrorBoundary name="RuntimeSecurityDashboard"><Suspense fallback={<SkeletonDashboard />}><RuntimeSecurityDashboard /></Suspense></ErrorBoundary>;
      case 'sast': return <ErrorBoundary name="SASTDashboard"><Suspense fallback={<SkeletonDashboard />}><SASTDashboardLazy /></Suspense></ErrorBoundary>;
      case 'remoteAccess': return <ErrorBoundary name="RemoteAccessDashboard"><Suspense fallback={<SkeletonDashboard />}><RemoteAccessDashboard /></Suspense></ErrorBoundary>;
      case 'agentChat': return <ErrorBoundary name="ChatHubEndpoint"><Suspense fallback={<SkeletonDashboard />}><ChatHub initialTab="endpoint" /></Suspense></ErrorBoundary>;
      case 'aiRemediation': return <ErrorBoundary name="AIRemediationDashboard"><Suspense fallback={<SkeletonDashboard />}><AIRemediationDashboard /></Suspense></ErrorBoundary>;
      case 'rollback': return <ErrorBoundary name="RollbackDashboard"><Suspense fallback={<SkeletonDashboard />}><RollbackDashboard /></Suspense></ErrorBoundary>;
      case 'pipelineSecurity': return <ErrorBoundary name="PipelineSecurityDashboard"><Suspense fallback={<SkeletonDashboard />}><PipelineSecurityDashboard /></Suspense></ErrorBoundary>;
      case 'iacSecurity': return <ErrorBoundary name="IaCSecurityDashboard"><Suspense fallback={<SkeletonDashboard />}><IaCSecurityDashboard /></Suspense></ErrorBoundary>;
      case 'containerScan': return <ErrorBoundary name="ContainerScanDashboard"><Suspense fallback={<SkeletonDashboard />}><ContainerScanDashboard /></Suspense></ErrorBoundary>;
      case 'pam': return <ErrorBoundary name="PAMDashboard"><Suspense fallback={<SkeletonDashboard />}><PAMDashboard /></Suspense></ErrorBoundary>;
      case 'baaManagement': return <ErrorBoundary name="BAAManagement"><Suspense fallback={<SkeletonDashboard />}><BAAManagement /></Suspense></ErrorBoundary>;
      case 'codeReviewGraph': return <ErrorBoundary name="CodeReviewGraphDashboard"><CodeReviewGraphDashboard /></ErrorBoundary>;
      case 'supportChat': return <ErrorBoundary name="ChatHubSupport"><Suspense fallback={<SkeletonDashboard />}><ChatHub initialTab="support" initialSupportConvoId={pendingSupportConvo} onSupportConvoConsumed={() => setPendingSupportConvo(null)} /></Suspense></ErrorBoundary>;
      case 'chat': return <ErrorBoundary name="ChatHub"><Suspense fallback={<SkeletonDashboard />}><ChatHub initialTab={pendingSupportConvo ? 'support' : 'endpoint'} initialSupportConvoId={pendingSupportConvo} onSupportConvoConsumed={() => setPendingSupportConvo(null)} /></Suspense></ErrorBoundary>;
      case 'certificates': return <ErrorBoundary name="CertificatesDashboard"><Suspense fallback={<SkeletonDashboard />}><CertificatesDashboard /></Suspense></ErrorBoundary>;
      case 'aiAnomaly': return <ErrorBoundary name="AIAnomalyDashboard"><Suspense fallback={<SkeletonDashboard />}><AIAnomalyDashboard /></Suspense></ErrorBoundary>;
      case 'problemManagement': return <ErrorBoundary name="ProblemManagementDashboard"><Suspense fallback={<SkeletonDashboard />}><ProblemManagementDashboard /></Suspense></ErrorBoundary>;
      case 'changeManagement': return <ErrorBoundary name="ChangeManagementDashboard"><Suspense fallback={<SkeletonDashboard />}><ChangeManagementDashboard /></Suspense></ErrorBoundary>;
      case 'ticketWebhooks': return <ErrorBoundary name="TicketWebhooksDashboard"><Suspense fallback={<SkeletonDashboard />}><TicketWebhooksDashboard /></Suspense></ErrorBoundary>;
      case 'notificationPrefs': return <ErrorBoundary name="NotificationPreferencesDashboard"><Suspense fallback={<SkeletonDashboard />}><NotificationPreferencesDashboard /></Suspense></ErrorBoundary>;
      case 'aiAssistantChat': return <ErrorBoundary name="AIAssistantChat"><AIAssistantChat /></ErrorBoundary>;
      default: return <ErrorBoundary name="Dashboard"><Dashboard metrics={metrics} alerts={tenantData.alerts} complianceFrameworks={tenantData.complianceFrameworks} aiSystems={tenantData.aiSystems} agents={tenantData.agents} currentUser={currentUser} setCurrentView={handleSetCurrentView} /></ErrorBoundary>;

    }
  };

  return (
    <TimeZoneProvider>
      <ThemeProvider>
        <UserContext.Provider value={{
          currentUser,
          login: handleLogin,
          signup: handleSignup,
          logout: handleLogout,
          registerTenant: handleRegisterTenant,
          enabledFeatures,
          hasPermission,
          serverLockedFeatures,
        }}>
          <FeaturesProvider>
          <ErrorBoundary name="AppLayout">
            {!currentUser ? (
              <LoginPage users={users} onLogin={handleLogin} onSignup={handleSignup} />
            ) : (
              <div className={`flex h-screen bg-gray-100 dark:bg-gray-900 font-sans transition-colors duration-200`}>
              {!isBackendConnected && (
                <div className="fixed top-0 left-0 right-0 z-[60] bg-red-600 text-white px-4 py-2 text-center text-sm font-medium flex items-center justify-center shadow-lg animate-pulse">
                  <AlertTriangleIcon size={18} className="mr-2" />
                  <span>Backend connection lost. Displaying cached data. Attempting to reconnect...</span>
                </div>
              )}
              <Sidebar
                isOpen={isSidebarOpen}
                currentView={currentView}
                setCurrentView={handleSetCurrentView}
                isViewingTenant={!!viewingTenantId}
                onBackToTenants={() => setViewingTenantId(null)}
                branding={brandingConfig}
              />
              <div className="flex-1 flex flex-col overflow-hidden">
                <Header
                  allUsers={users}
                  onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
                  onOpenCommandBar={() => setIsCommandBarOpen(true)}
                  onOpenSearch={() => setIsGlobalSearchOpen(true)}
                  setCurrentView={handleSetCurrentView}
                  onStartTour={() => window.dispatchEvent(new Event('start-genesis-tour'))}
                  currentView={currentView}
                />
                <main className={`flex-1 overflow-x-hidden ${['supportChat', 'agentChat', 'chat'].includes(currentView) ? 'overflow-hidden' : 'overflow-y-auto p-4 md:p-6'}`}>
                  <ErrorBoundary name="MainContent">
                    <Suspense fallback={<SkeletonDashboard />}>
                      {renderView()}
                    </Suspense>
                  </ErrorBoundary>
                </main>
              </div>
            </div>
            )}
          </ErrorBoundary>

          <ErrorBoundary name="CharacterTourBot">
            {currentUser && (
               <CharacterTourBot
                  currentUser={currentUser}
                  currentView={currentView}
                  setCurrentView={handleSetCurrentView}
               />
            )}
          </ErrorBoundary>

          <ErrorBoundary name="InteractiveVoiceBot">
            {currentUser && (
              <InteractiveVoiceBot
                currentUser={currentUser}
                currentView={currentView}
                setCurrentView={handleSetCurrentView}
                voiceBotSettings={tenants.find(t => t.id === activeTenantId)?.voiceBotSettings || llmSettings?.voiceBotSettings || null}
              />
            )}
          </ErrorBoundary>
          <ChatFab onClick={() => setIsChatOpen(true)} />

          {/* Global audio/video call overlay (incoming ring + in-call window) */}
          {currentUser && (
            <ErrorBoundary name="CallOverlay">
              <CallOverlay />
            </ErrorBoundary>
          )}

          {/* Support chat in-app toast notifications */}
          <SupportChatToast
            toasts={supportToasts}
            onDismiss={id => setSupportToasts(prev => prev.filter(t => t.id !== id))}
            onOpen={convoId => {
              if (convoId) setPendingSupportConvo(convoId);
              setIsSupportChatOpen(true);
              setSupportToasts(prev => prev.filter(t => t.convoId !== convoId));
              setSupportUnreadCount(0);
            }}
          />

          {/* Floating, docked interactive support chat window */}
          <SupportChatWindow
            isOpen={isSupportChatOpen}
            initialConvoId={pendingSupportConvo}
            onConvoConsumed={() => setPendingSupportConvo(null)}
            onClose={() => setIsSupportChatOpen(false)}
          />

          {/* Sidebar Items are in Sidebar.tsx */}


          <TenantOnboardingWizard isOpen={isAddTenantModalOpen} onClose={() => setIsAddTenantModalOpen(false)} onComplete={(tenant) => { setTenants(prev => [...prev, tenant]); setIsAddTenantModalOpen(false); }} />
          {/* Legacy simple modal kept but replaced by wizard above */}
          {managingTenant && (
            <ManageTenantModal
              isOpen={!!managingTenant}
              onClose={() => setManagingTenant(null)}
              tenant={managingTenant}
              onSave={handleSaveTenantFeatures}
              onDelete={handleDeleteTenant}
            />
          )}
          <RegisterAgentModal
            isOpen={isRegisterAgentModalOpen}
            onClose={() => setIsRegisterAgentModalOpen(false)}
            onSave={handleRegisterAgent}
            assets={tenantData.assets}
          />
          <ChatAssistant
            isOpen={isChatOpen}
            onClose={() => setIsChatOpen(false)}
            context={{ currentView }}
            onNavigate={(view) => setCurrentView(view as any)}
          />
          <AICommandBar
            isOpen={isCommandBarOpen}
            onClose={() => setIsCommandBarOpen(false)}
            onExecuteCommand={handleExecuteCommand}
          />
          <GlobalSearchModal
            isOpen={isGlobalSearchOpen}
            onClose={() => setIsGlobalSearchOpen(false)}
            onNavigate={(view) => { handleSetCurrentView(view as any); setIsGlobalSearchOpen(false); }}
          />
          </FeaturesProvider>
        </UserContext.Provider>
      </ThemeProvider>
    </TimeZoneProvider>
  );
};

export default App;
