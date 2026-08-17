import React, { lazy } from 'react';

const CXODashboard = lazy(() => import('../components/CXODashboard').then(m => ({ default: m.CXODashboard })));
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

export const ROUTE_MAP: Record<string, React.LazyExoticComponent<any>> = {
'CXODashboard': CXODashboard,
'ReportingDashboard': ReportingDashboard,
'AgentsDashboard': AgentsDashboard,
'AgentCapabilitiesDashboard': AgentCapabilitiesDashboard,
'AssetManagementDashboard': AssetManagementDashboard,
'PatchManagementDashboard': PatchManagementDashboard,
'VulnerabilityManagement': VulnerabilityManagement,
'SoftwareUpdateManagement': SoftwareUpdateManagement,
'CloudSecurityDashboard': CloudSecurityDashboard,
'SecurityDashboard': SecurityDashboard,
'ComplianceDashboard': ComplianceDashboard,
'ProgramsDashboard': ProgramsDashboard,
'InboundQuestionnaireDashboard': InboundQuestionnaireDashboard,
'SaaSIntegrationsDashboard': SaaSIntegrationsDashboard,
'PrivacyLegalDashboard': PrivacyLegalDashboard,
'CloudAccountsDashboard': CloudAccountsDashboard,
'NotificationsDashboard': NotificationsDashboard,
'ApiExtensionsDashboard': ApiExtensionsDashboard,
'IacContainerDashboard': IacContainerDashboard,
'ApprovalDashboard': ApprovalDashboard,
'CloudChecksScanner': CloudChecksScanner,
'StagedDeploymentsPage': StagedDeploymentsPage,
'AIGovernanceDashboard': AIGovernanceDashboard,
'FinOpsBillingPage': FinOpsBillingPage,
'AuditLogDashboard': AuditLogDashboard,
'SecurityAuditDashboard': SecurityAuditDashboard,
'SettingsDashboard': SettingsDashboard,
'SiemRulesDashboard': SiemRulesDashboard,
'IncidentResponseDashboard': IncidentResponseDashboard,
'TenantManagementDashboard': TenantManagementDashboard,
'LogExplorerDashboard': LogExplorerDashboard,
'ThreatHuntingDashboard': ThreatHuntingDashboard,
'ThreatIntelFeedEnhanced': ThreatIntelFeedEnhanced,
'SecurityIntelConnectors': SecurityIntelConnectors,
'UserProfilePage': UserProfilePage,
'AutomationPoliciesDashboard': AutomationPoliciesDashboard,
'DevSecOpsDashboard': DevSecOpsDashboard,
'DeveloperHubDashboard': DeveloperHubDashboard,
'IncidentImpactDashboard': IncidentImpactDashboard,
'ProactiveInsightsDashboard': ProactiveInsightsDashboard,
'DistributedTracingDashboard': DistributedTracingDashboard,
'DataSecurityDashboard': DataSecurityDashboard,
'AttackPathDashboard': AttackPathDashboard,
'ServiceCatalogDashboard': ServiceCatalogDashboard,
'DoraMetricsDashboard': DoraMetricsDashboard,
'ChaosEngineeringDashboard': ChaosEngineeringDashboard,
'NetworkObservabilityDashboard': NetworkObservabilityDashboard,
'DataUtilizationDashboard': DataUtilizationDashboard,
'ServicePricingPage': ServicePricingPage,
'WebhookManagement': WebhookManagement,
'SustainabilityDashboard': SustainabilityDashboard,
'ZeroTrustQuantumDashboard': ZeroTrustQuantumDashboard,
'PaymentSettings': PaymentSettings,
'SubscriptionManagement': SubscriptionManagement,
'InvoiceList': InvoiceList,
'FutureOpsDashboard': FutureOpsDashboard,
'RiskRegister': RiskRegister,
'VendorManagement': VendorManagement,
'TrustCenter': TrustCenter,
'GovernanceDocumentsDashboard': GovernanceDocumentsDashboard,
'TrustPage': TrustPage,
'SecureFileShare': SecureFileShare,
'SecurityTraining': SecurityTraining,
'LLMOpsDashboard': LLMOpsDashboard,
'JobsDashboard': JobsDashboard,
'SoftwareDeployment': SoftwareDeployment,
'PlaybookBuilder': PlaybookBuilder,
'SecuritySimulation': SecuritySimulation,
'PersistenceDashboard': PersistenceDashboard,
'MultiStepApprovalDashboard': MultiStepApprovalDashboard,
'CertificatesDashboard': CertificatesDashboard,
'AIAnomalyDashboard': AIAnomalyDashboard,
'SwarmDashboard': SwarmDashboard,
'SimulationDashboard': SimulationDashboard,
'ComplianceOracleDashboard': ComplianceOracleDashboard,
'CISSPOracle': CISSPOracle,
'AdvancedBiDashboard': AdvancedBiDashboard,
'BundleManagementDashboard': BundleManagementDashboard,
'DataWarehouseDashboard': DataWarehouseDashboard,
'StreamingDashboard': StreamingDashboard,
'DataGovernanceDashboard': DataGovernanceDashboard,
'MLOpsDashboard': MLOpsDashboard,
'AutoMLDashboard': AutoMLDashboard,
'XAIDashboard': XAIDashboard,
'ABTestingDashboard': ABTestingDashboard,
'DASTDashboard': DASTDashboard,
'ServiceMeshDashboard': ServiceMeshDashboard,
'WebMonitoringDashboard': WebMonitoringDashboard,
'EDRDashboard': EDRDashboard,
'YaraRuleEditor': YaraRuleEditor,
'AlertManagementDashboard': AlertManagementDashboard,
'ComplianceEvidenceStatusDashboard': ComplianceEvidenceStatusDashboard,
'RemediationDashboard': RemediationDashboard,
'UEBADashboard': UEBADashboard,
'MDRDashboard': MDRDashboard,
'XDRDashboard': XDRDashboard,
'APMDashboard': APMDashboard,
'AgentApprovalDashboard': AgentApprovalDashboard,
'ThreatDashboard': ThreatDashboard,
'CloudIntegrationsDashboard': CloudIntegrationsDashboard,
'JITAccessDashboard': JITAccessDashboard,
'AutopilotDashboard': AutopilotDashboard,
'ConditionalAccessDashboard': ConditionalAccessDashboard,
'MobileDashboard': MobileDashboard,
'BranchSitesDashboard': BranchSitesDashboard,
'AppCatalogDashboard': AppCatalogDashboard,
'AssetIntelligenceDashboard': AssetIntelligenceDashboard,
'MAMDashboard': MAMDashboard,
'AndroidEnterpriseDashboard': AndroidEnterpriseDashboard,
'DeviceConfigProfilesDashboard': DeviceConfigProfilesDashboard,
'FirmwareDriverDashboard': FirmwareDriverDashboard,
'AdvancedHuntingDashboard': AdvancedHuntingDashboard,
'DetectionRulesDashboard': DetectionRulesDashboard,
'ConnectorsHubDashboard': ConnectorsHubDashboard,
'SecurityCopilotDashboard': SecurityCopilotDashboard,
'MSSPDashboard': MSSPDashboard,
'AttackTimelineDashboard': AttackTimelineDashboard,
'GeographicAttackMap': GeographicAttackMap,
'RetentionPoliciesDashboard': RetentionPoliciesDashboard,
'SCADashboard': SCADashboard,
'AgentGroupsDashboard': AgentGroupsDashboard,
'ConfigDriftDashboard': ConfigDriftDashboard,
'FIMDashboard': FIMDashboard,
'ActiveResponseDashboard': ActiveResponseDashboard,
'IncidentWarRoomDashboard': IncidentWarRoomDashboard,
'PrivacyDashboard': PrivacyDashboard,
'SecuritySettingsDashboard': SecuritySettingsDashboard,
'FleetObservabilityDashboard': FleetObservabilityDashboard,
'FleetGeoMap': FleetGeoMap,
'NativeSecurityConsole': NativeSecurityConsole,
'ITAMConsole': ITAMConsole,
'ScheduledReportsDashboard': ScheduledReportsDashboard,
'SecretsManagementDashboard': SecretsManagementDashboard,
'CustomFrameworkBuilder': CustomFrameworkBuilder,
'DeceptionDashboard': DeceptionDashboard,
'NetworkTopologyMap': NetworkTopologyMap,
'ShadowAI': ShadowAI,
'KnowledgeBaseDashboard': KnowledgeBaseDashboard,
'RetentionPolicyDashboard': RetentionPolicyDashboard,
'APISecurityDashboard': APISecurityDashboard,
'DAMDashboard': DAMDashboard,
'K8sSecurityDashboard': K8sSecurityDashboard,
'NDRDashboard': NDRDashboard,
'InsiderThreatDashboard': InsiderThreatDashboard,
'EmailSecurityDashboard': EmailSecurityDashboard,
'SupplyChainDashboard': SupplyChainDashboard,
'HADRDashboard': HADRDashboard,
'CorrelationDashboard': CorrelationDashboard,
'CodeReviewGraphDashboard': CodeReviewGraphDashboard,
};
