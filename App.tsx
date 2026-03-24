import React, { useState, useEffect, useMemo, useCallback, lazy, Suspense } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { ErrorBoundary } from './components/ErrorBoundary';
// ... imports
import { AuditLog as AuditLogComponent } from './components/AuditLog';

import { LoginPage } from './components/LoginPage';
import { CXODashboard } from './components/CXODashboard';
import { Dashboard } from './components/Dashboard';
import { ReportingDashboard } from './components/ReportingDashboard';
import { AgentsDashboard } from './components/AgentsDashboard';
import { AgentCapabilitiesDashboard } from './components/AgentCapabilitiesDashboard';
import { AssetManagementDashboard } from './components/AssetManagementDashboard';
import PatchManagementDashboard from './components/PatchManagementDashboard';
import VulnerabilityManagement from './components/VulnerabilityManagement';
import { SoftwareUpdateManagement } from './components/SoftwareUpdateManagement';
import { CloudSecurityDashboard } from './components/CloudSecurityDashboard';
import { SecurityDashboard } from './components/SecurityDashboard';
import { ComplianceDashboard } from './components/ComplianceDashboard';
import { AIGovernanceDashboard } from './components/AIGovernanceDashboard';
import { FinOpsBillingPage } from './components/FinOpsBillingPage';
import { AuditLogDashboard } from './components/AuditLogDashboard';
import { SecurityAuditDashboard } from './components/SecurityAuditDashboard';
import { SettingsDashboard } from './components/SettingsDashboard';
import { SiemRulesDashboard } from './components/SiemRulesDashboard';
import { TenantManagementDashboard } from './components/TenantManagementDashboard';
import { AddNewTenantModal } from './components/AddNewTenantModal';
import { ManageTenantModal } from './components/ManageTenantModal';
import { RegisterAgentModal } from './components/RegisterAgentModal';
import { ChatFab } from './components/ChatFab';
import { ChatAssistant } from './components/ChatAssistant';
import { AICommandBar, Command } from './components/AICommandBar';
import { LogExplorerDashboard } from './components/LogExplorerDashboard';
import { ThreatHuntingDashboard } from './components/ThreatHuntingDashboard';
import { ThreatIntelFeedEnhanced } from './components/ThreatIntelFeedEnhanced';
import { UserProfilePage } from './components/UserProfilePage';
import { AutomationPoliciesDashboard } from './components/AutomationPoliciesDashboard';
import { DevSecOpsDashboard } from './components/DevSecOpsDashboard';
import { DeveloperHubDashboard } from './components/DeveloperHubDashboard';
import { IncidentImpactDashboard } from './components/IncidentImpactDashboard';
import { ProactiveInsightsDashboard } from './components/ProactiveInsightsDashboard';
import { DistributedTracingDashboard } from './components/DistributedTracingDashboard';
import { DataSecurityDashboard } from './components/DataSecurityDashboard';
import { AttackPathDashboard } from './components/AttackPathDashboard';
import { ServiceCatalogDashboard } from './components/ServiceCatalogDashboard';
import { DoraMetricsDashboard } from './components/DoraMetricsDashboard';
import { ChaosEngineeringDashboard } from './components/ChaosEngineeringDashboard';
import { NetworkObservabilityDashboard } from './components/NetworkObservabilityDashboard';
import { DataUtilizationDashboard } from './components/DataUtilizationDashboard';
import { ServicePricing } from './components/ServicePricing';
import { ServicePricingPage } from './components/ServicePricingPage';
import TaskList from './components/TaskList';
import TaskForm from './components/TaskForm';
// 2030 Industry Features
import { WebhookManagement } from './components/WebhookManagement';
import { SustainabilityDashboard } from './components/SustainabilityDashboard';
const ZeroTrustQuantumDashboard = lazy(() => import('./components/ZeroTrustQuantumDashboard'));
const PaymentSettings = lazy(() => import('./components/PaymentSettings'));
const SubscriptionManagement = lazy(() => import('./components/SubscriptionManagement'));
const InvoiceList = lazy(() => import('./components/InvoiceList'));
const FutureOpsDashboard = lazy(() => import('./components/UnifiedFutureOpsDashboard'));
const RiskRegister = lazy(() => import('./components/RiskRegister'));
import { InteractiveVoiceBot } from './components/InteractiveVoiceBot';
import { CharacterTourBot } from './components/CharacterTourBot';
const VendorManagement = lazy(() => import('./components/VendorManagement'));
const TrustCenter = lazy(() => import('./components/TrustCenter'));
const SecureFileShare = lazy(() => import('./components/SecureFileShare'));
const SecurityTraining = lazy(() => import('./components/SecurityTraining'));
import LLMOpsDashboard from './components/LLMOpsDashboard';
import { JobsDashboard } from './components/JobsDashboard';
import { SoftwareDeployment } from './components/SoftwareDeployment';
import PlaybookBuilder from './components/PlaybookBuilder';
import { SecuritySimulation } from './components/SecuritySimulation';
import { PersistenceDashboard } from './components/PersistenceDashboard';
import { MultiStepApprovalDashboard } from './components/MultiStepApprovalDashboard';
import SwarmDashboard from './components/SwarmDashboard';
import SimulationDashboard from './components/SimulationDashboard';
import ComplianceOracleDashboard from './components/ComplianceOracleDashboard';
import CISSPOracle from './components/CISSPOracle';

import { AdvancedBiDashboard } from './components/AdvancedBiDashboard';
import { ApiStatusDashboard } from './components/ApiStatusDashboard';
import { ThemeProvider } from './contexts/ThemeProvider';
import { TimeZoneProvider } from './contexts/TimeZoneContext';

import { UserContext } from '@/contexts/UserContext';
import { DataWarehouseDashboard } from './components/DataWarehouseDashboard';
import { StreamingDashboard } from './components/StreamingDashboard';
import { DataGovernanceDashboard } from './components/DataGovernanceDashboard';
import { MLOpsDashboard } from './components/MLOpsDashboard';
import { AutoMLDashboard } from './components/AutoMLDashboard';
import { XAIDashboard } from './components/XAIDashboard';
import { ABTestingDashboard } from './components/ABTestingDashboard';
import { DASTDashboard } from './components/DASTDashboard';
import { ServiceMeshDashboard } from './components/ServiceMeshDashboard';
import { WebMonitoringDashboard } from './components/WebMonitoringDashboard';
import { EDRDashboard } from './components/EDRDashboard';
import { UEBADashboard } from './components/UEBADashboard';
import ThreatDashboard from './components/ThreatDashboard';

import { PentestDashboard } from './components/PentestDashboard';
const MitreAttackHeatmap = React.lazy(() => import('./components/MitreAttackHeatmap'));
const DLPDashboard = React.lazy(() => import('./components/DLPDashboard'));
const TicketingIntegration = React.lazy(() => import('./components/TicketingIntegration'));


import * as api from './services/apiService';
// WebSocket for real-time notifications
import { socketService } from './services/socketService';
import { AppView, User, Role, Tenant, Metric, Alert, ComplianceFramework, AiSystem, Asset, Patch, SecurityCase, Playbook, SecurityEvent, CloudAccount, CSPMFinding, Notification, AuditLog, Integration, AlertRule, Agent, DatabaseSettings, LlmSettings, DataSource, Sbom, SoftwareComponent, AgentUpgradeJob, PatchDeploymentJob, Permission, Filter, LogEntry, UebaFinding, ModelExperiment, RegisteredModel, ModelStage, AutomationPolicy, SastFinding, CodeRepository, ApiDocEndpoint, IncidentImpactGraph, NewUserPayload, AgentPlatform, SubscriptionTier, SensitiveDataFinding, AttackPath, ServiceTemplate, ProvisionedService, DoraMetrics, ChaosExperiment, ProactiveInsight, Trace, ServiceMap, VulnerabilityScanJob, NetworkDevice, ThreatIntelResult, NewTenantPayload, Task, Priority, AssetCompliance } from './types';
import { SUBSCRIPTION_TIERS } from './constants';
import { AlertTriangleIcon } from './components/icons';

// API Base URL - Use relative path so Vite proxy handles it correctly and bypasses CORS
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
  dastFindings: 'view:security',
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
  mitreAttack: 'view:security',
  dlp: 'view:security',
  ticketing: 'manage:settings',
  siem: 'view:security',
  ueba: 'view:security',
  vulnerabilities: 'view:vulnerabilities',
  siemRules: 'view:security',
  incidentResponse: 'investigate:security',
};


const App: React.FC = () => {
  // Global App State
  // Global App State
  // Theme managed by ThemeProvider
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [currentView, setCurrentView] = useState<AppView>('dashboard');
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [viewingTenantId, setViewingTenantId] = useState<string | null>(null);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isCommandBarOpen, setIsCommandBarOpen] = useState(false);
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
    console.log("[App] App component mounted and useEffect running");
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
  const [notifications, setNotifications] = useState<Notification[]>([]);
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
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const [isBackendConnected, setIsBackendConnected] = useState(true);

  // Data Loading Function
  const loadAllData = useCallback(async () => {
    // Prevent unauthenticated calls which trigger redirect loops
    const token = localStorage.getItem('token');
    if (!token) {
      console.warn("Skipping loadAllData: No token found");
      return;
    }

    try {
      const results = await Promise.allSettled([
        api.fetchUsers(), api.fetchRoles(), api.fetchTenants(), api.fetchMetrics(),
        api.fetchAlerts(), api.fetchComplianceFrameworks(), api.fetchAiSystems(),
        api.fetchAssets(), api.fetchPatches(), api.fetchSecurityCases(),
        api.fetchPlaybooks(), api.fetchSecurityEvents(), api.fetchCloudAccounts(),
        api.fetchCspmFindings(), api.fetchNotifications(), api.fetchAuditLogs(),
        api.fetchIntegrations(), api.fetchAlertRules(), api.fetchHistoricalData(viewingTenantId || undefined),
        api.fetchAgents(), api.fetchInfrastructure(), api.fetchDataSources(),
        api.fetchSboms(), api.fetchSoftwareComponents(),
        api.fetchAgentUpgradeJobs(), api.fetchPatchDeploymentJobs(), api.fetchVulnerabilityScanJobs(), api.fetchLogs(), api.fetchUebaFindings(),
        api.fetchModelExperiments(), api.fetchRegisteredModels(), api.fetchAutomationPolicies(),
        api.fetchSastFindings(), api.fetchCodeRepositories(), api.fetchApiDocs(),
        api.fetchIncidentImpactGraph('dummy-id'), api.fetchSensitiveDataFindings(),
        api.fetchAttackPaths(), api.fetchServiceTemplates(), api.fetchProvisionedServices(),
        api.fetchDoraMetrics(), api.fetchChaosExperiments(), api.fetchProactiveInsights(),
        api.fetchTraces(), api.fetchServiceMap(), api.fetchThreatIntelFeed(), api.fetchNetworkDevices(),
        api.fetchGlobalComplianceData(),
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
      setNotifications(getResult(14, []));
      setAuditLogs(getResult(15, []));
      setIntegrations(getResult(16, []));
      setAlertRules(getResult(17, []));
      setHistoricalData(getResult(18, {}));
      setAgents(getResult(19, []));
      const infra = getResult(20, { db: null, llm: null });
      setDatabaseSettings(infra?.db || null);
      setLlmSettings(infra?.llm || null);
      setDataSources(getResult(21, []));
      setSboms(getResult(22, []));
      setSoftwareComponents(getResult(23, []));
      setAgentUpgradeJobs(getResult(24, []));
      setPatchDeploymentJobs(getResult(25, []));
      setVulnerabilityScanJobs(getResult(26, []));
      setLogs(getResult(27, []));
      setUebaFindings(getResult(28, []));
      setModelExperiments(getResult(29, []));
      setRegisteredModels(getResult(30, []));
      setAutomationPolicies(getResult(31, []));
      setSastFindings(getResult(32, []));
      setCodeRepositories(getResult(33, []));
      setApiDocs(getResult(34, []));
      setIncidentImpactGraph(getResult(35, null));
      setSensitiveDataFindings(getResult(36, []));
      setAttackPaths(getResult(37, []));
      setServiceTemplates(getResult(38, []));
      setProvisionedServices(getResult(39, []));
      setDoraMetrics(getResult(40, []));
      setChaosExperiments(getResult(41, []));
      setProactiveInsights(getResult(42, []));
      setTraces(getResult(43, []));
      setServiceMap(getResult(44, null));
      setThreatIntelFeed(getResult(45, []));
      const netDevs = getResult(46, []);
      setNetworkDevices(netDevs);
      setAssetComplianceData(getResult(47, []));

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
    console.log(`[Frontend] handleLogin called for ${email}`);
    try {
      const data = await api.login(email, password);
      console.log(`[Frontend] Login response data:`, data);

      if (data.success && data.user) {
        // Store authentication tokens
        if (data.access_token) localStorage.setItem('token', data.access_token);
        if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);

        // Merge subscriptionTier from tenant into user object so badge can read it across all roles
        setCurrentUser({ ...data.user, subscriptionTier: data.tenant?.subscriptionTier || 'Free' });
        setViewingTenantId((data.user.role === 'Super Admin' || data.user.role === 'superadmin' || data.user.role === 'super_admin') ? null : data.user.tenantId);
        setCurrentView('dashboard');

        // Load all data in background (non-blocking)
        loadAllData().catch(err => console.error('Error loading data:', err));

        return true;
      }

      console.log('[Frontend] Login success=false in response');
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
        if (data.access_token) localStorage.setItem('token', data.access_token);
        if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);

        // Merge subscriptionTier from tenant into user object
        setCurrentUser({ 
          ...data.user, 
          subscriptionTier: data.tenant?.subscriptionTier || 'Free' 
        });

        // Set viewing tenant id
        setViewingTenantId(data.tenant?.id || data.user?.tenantId || null);

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
    setCurrentUser(null);
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
    setCurrentView('patchManagement');
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


  // Initial Data Load
  useEffect(() => {
    const restoreSession = async () => {
      const user = await api.fetchCurrentUser();
      if (user) {
        setCurrentUser(user);
        setViewingTenantId((user.role === 'Super Admin' || user.role === 'superadmin' || user.role === 'super_admin') ? null : user.tenantId);
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
            console.log("Backend reconnected, refreshing data...");
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
      console.log("Polling Agents status...");
      api.fetchAgents().then(agentsData => {
        // Deduplicate agents by ID (keep the latest entry)
        const uniqueAgents = Object.values(
          agentsData.reduce((acc, agent) => {
            acc[agent.id] = agent;
            return acc;
          }, {} as Record<string, typeof agentsData[0]>)
        );
        setAgents(uniqueAgents);
      }).catch(err => console.error("Error polling agents:", err));
    }, 5000);

    return () => clearInterval(interval);
  }, [currentView, isBackendConnected]);

  // Calculate activeTenantId BEFORE using it in WebSocket useEffect
  const activeTenantId = viewingTenantId || currentUser?.tenantId;

  // WebSocket Connection Management
  useEffect(() => {
    if (currentUser && activeTenantId) {
      console.log('[App] Establishing WebSocket connection for tenant:', activeTenantId);

      // Connect to WebSocket server
      socketService.connect(activeTenantId);

      // Handler: Agent status changes
      const handleAgentStatusChange = (data: { agent_id: string; status: string; timestamp: string }) => {
        console.log('[App] Agent status updated via WebSocket:', data);
        setAgents(prev => prev.map(agent =>
          agent.id === data.agent_id
            ? { ...agent, status: data.status as any, lastSeen: data.timestamp }
            : agent
        ));
      };

      // Handler: New notifications
      const handleNotification = (notification: any) => {
        console.log('[App] New notification via WebSocket:', notification);
        setNotifications(prev => [{
          id: `notif-${Date.now()}`,
          type: notification.type || 'info',
          title: notification.title || 'Notification',
          message: notification.message,
          timestamp: notification.timestamp || new Date().toISOString(),
          read: false,
          userId: currentUser.id,
          tenantId: activeTenantId
        }, ...prev]);
      };

      // Handler: Security events
      const handleSecurityEvent = (event: any) => {
        console.log('[App] New security event via WebSocket:', event);
        setSecurityEvents(prev => [event, ...prev]);
      };

      // Handler: Compliance alerts
      const handleComplianceAlert = (alert: any) => {
        console.log('[App] Compliance alert via WebSocket:', alert);
        // Add to notifications or handle separately
        handleNotification({
          type: 'warning',
          title: 'Compliance Alert',
          message: alert.message || 'New compliance issue detected',
          ...alert
        });
      };

      // Subscribe to WebSocket events
      socketService.on('agent_status_change', handleAgentStatusChange);
      socketService.on('notification', handleNotification);
      socketService.on('security_event', handleSecurityEvent);
      socketService.on('compliance_alert', handleComplianceAlert);

      console.log('[App] WebSocket event listeners registered');

      // Cleanup on unmount or user/tenant change
      return () => {
        console.log('[App] Cleaning up WebSocket connection');
        socketService.off('agent_status_change', handleAgentStatusChange);
        socketService.off('notification', handleNotification);
        socketService.off('security_event', handleSecurityEvent);
        socketService.off('compliance_alert', handleComplianceAlert);
        socketService.disconnect();
      };
    }
  }, [currentUser, activeTenantId]);

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
    let effectiveFeatures: Permission[];

    if (currentUser.permissions && Array.isArray(currentUser.permissions)) {
      // Backend included permissions in the user object
      const userPerms = currentUser.permissions as Permission[];

      const tenant = tenants.find(t => t.id === currentUser.tenantId);
      if (tenant && currentUser.role !== 'Super Admin') {
        // Intersect user permissions with tenant's enabled features
        effectiveFeatures = userPerms.filter(p => tenant.enabledFeatures.includes(p as string));
      } else {
        effectiveFeatures = userPerms;
      }
    } else {
      // Fallback to role-based lookup (old method)
      const role = roles.find(r => r.name === currentUser.role);
      if (!role) return { enabledFeatures: [], hasPermission: () => false };

      // Super admin has all permissions, always.
      if (currentUser.role === 'Super Admin') {
        effectiveFeatures = role.permissions;
      } else {
        const tenant = tenants.find(t => t.id === currentUser.tenantId);
        if (!tenant) return { enabledFeatures: [], hasPermission: () => false };
        // Intersect role permissions with tenant's enabled features
        effectiveFeatures = role.permissions.filter(p => tenant.enabledFeatures.includes(p));
      }
    }

    const checkPermission = (permission: Permission): boolean => {
      // Super Admin always has permission, regardless of loaded role data
      const roleName = currentUser?.role?.trim().toLowerCase() || '';
      const isSuperAdmin = roleName === 'super admin' || roleName === 'superadmin' || roleName === 'super_admin' || roleName === 'platform-admin';

      if (isSuperAdmin) return true;
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
        notifications: notifications,
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
      notifications: (Array.isArray(notifications) ? notifications : []).filter(n => tenants.find(t => t.id === activeTenantId)), // Simple filter for demo
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
  }, [activeTenantId, alerts, assets, agents, securityEvents, securityCases, complianceFrameworks, aiSystems, patches, patchDeploymentJobs, vulnerabilityScanJobs, cloudAccounts, cspmFindings, notifications, auditLogs, integrations, alertRules, tenants, dataSources, sboms, softwareComponents, agentUpgradeJobs, logs, uebaFindings, modelExperiments, registeredModels, automationPolicies, sastFindings, codeRepositories, sensitiveDataFindings, attackPaths, serviceTemplates, provisionedServices, doraMetrics, chaosExperiments, proactiveInsights, traces, serviceMap, networkDevices, assetComplianceData]);


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
      alert(result.error || "Signup failed. Please try again.");
      return false;
    } catch (error) {
      console.error("Signup error:", error);
      alert("An error occurred during signup. Please try again.");
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
    // Clear user state
    setCurrentUser(null);
    setViewingTenantId(null);
    // Force page reload by assigning to href
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
      console.log('[App] Adding new tenant:', tenantData);
      const newTenant = await api.addTenant(tenantData);
      setTenants(prev => [...prev, newTenant]);
      console.log('[App] Tenant added successfully:', newTenant.id);
      alert(`Tenant "${tenantData.name}" created successfully.`);
    } catch (error: any) {
      console.error('[App] Error adding tenant:', error);
      alert(error.message || "Failed to add tenant. Please try again.");
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
      console.log('[App] Deleting tenant:', tenantId);
      await api.deleteTenant(tenantId);

      // Only update state after successful API call
      setTenants(prev => prev.filter(t => t.id !== tenantId));
      setUsers(prev => prev.filter(u => u.tenantId !== tenantId));

      console.log('[App] Tenant deleted successfully');
      alert('Tenant deleted successfully');
    } catch (error) {
      console.error('[App] Error deleting tenant:', error);
      alert(`Failed to delete tenant: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  // Duplicate handleAddNewTenant removed

  const handleRegisterAgent = (data: { hostname: string, ipAddress: string, platform: AgentPlatform, version: string, assetId: string | 'new' }) => {
    if (!activeTenantId) {
      alert("Cannot register agent: No active tenant selected.");
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
        alert(`Failed to delete agent: ${response?.message || "Unknown error"}`);
      }
    } catch (error) {
      console.error("Failed to delete agent (Exception):", error);
      alert(`Failed to delete agent. See console for details.`);
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
      alert(`Failed to delete asset: ${error instanceof Error ? error.message : 'Unknown error'}`);
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
      alert(error.message || "Failed to update user.");
    });
  };

  const handleDeleteUser = (userId: string) => {
    if (window.confirm("Are you sure you want to delete this user? This action cannot be undone.")) {
      api.deleteUser(userId).then(allUsers => {
        setUsers(allUsers);
      }).catch(error => {
        alert(error.message || "Failed to delete user.");
      });
    }
  };

  const handleResetPassword = async (userId: string, userName: string) => {
    if (window.confirm(`Are you sure you want to reset the password for ${userName}?`)) {
      await api.resetPassword(userId);
      alert(`A password reset link has been sent to the user's email (simulated).`);
    }
  };

  const handleAddNewUser = async (user: NewUserPayload) => {
    try {
      const allUsers = await api.addUser(user);
      setUsers(allUsers);
    } catch (error: any) {
      alert(error.message || "Failed to add user. Please try again.");
    }
  };

  const handleProfileUpdate = (updates: { name: string, avatar: string }) => {
    if (currentUser) {
      api.updateUser(currentUser.id, updates).then(allUsers => {
        setUsers(allUsers);
        const updatedSelf = allUsers.find(u => u.id === currentUser.id);
        if (updatedSelf) setCurrentUser(updatedSelf);
      }).catch(error => {
        alert(error.message || "Failed to update profile.");
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
    setSecurityCases(prev => prev.map(c => c.id === updatedCase.id ? updatedCase : c));
    return updatedCase;
  };

  const handleGeneratePlaybook = async (prompt: string): Promise<void> => {
    try {
      const newPlaybook = await api.generatePlaybook(prompt);
      setPlaybooks(prev => [newPlaybook, ...prev]);
    } catch (error) {
      alert(`Failed to generate playbook: ${error instanceof Error ? error.message : 'Unknown error'}`);
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

  const handleAddTask = (text: string, priority: Priority) => {
    const newTask: Task = {
      id: Date.now(),
      text,
      priority,
      completed: false
    };
    setMyTasks(prev => [...prev, newTask]);
  };

  const handleToggleTask = (id: number) => {
    setMyTasks(prev => prev.map(t => t.id === id ? { ...t, completed: !t.completed } : t));
  };

  const handleDeleteTask = (id: number) => {
    setMyTasks(prev => prev.filter(t => t.id !== id));
  };

  const userContextValue = useMemo(() => ({
    currentUser,
    login: handleLogin,
    logout,
    signup,
    registerTenant,
    hasPermission,
    enabledFeatures,
  }), [currentUser, handleLogin, logout, signup, registerTenant, hasPermission, enabledFeatures]);

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
      case 'dashboard': return <Dashboard metrics={metrics} alerts={tenantData.alerts} complianceFrameworks={tenantData.complianceFrameworks} aiSystems={tenantData.aiSystems} agents={tenantData.agents} currentUser={currentUser} setCurrentView={handleSetCurrentView} />;
      case 'cxo': return <CXODashboard />;
      case 'reporting': return <ReportingDashboard historicalData={historicalData} assets={tenantData.assets} />;
      case 'agents': return <AgentsDashboard
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
      />;
      case 'agentCapabilities': return <AgentCapabilitiesDashboard />;
      case 'assetManagement': return <AssetManagementDashboard assets={tenantData.assets} patches={tenantData.patches} onRunVulnerabilityScan={handleRunVulnerabilityScan} filters={assetFilters} onClearFilters={() => setAssetFilters([])} vulnerabilityScanJobs={tenantData.vulnerabilityScanJobs} onScheduleVulnerabilityScan={handleScheduleVulnerabilityScan} onDeleteAsset={handleDeleteAsset} />;
      case 'softwareUpdates': return <SoftwareUpdateManagement assets={tenantData.assets} />;
      case 'patchManagement': return <PatchManagementDashboard patches={tenantData.patches} assets={tenantData.assets} patchDeploymentJobs={tenantData.patchDeploymentJobs} onSchedulePatchDeployment={handleSchedulePatchDeployment} vulnerabilityScanJobs={tenantData.vulnerabilityScanJobs} onScheduleVulnerabilityScan={handleScheduleVulnerabilityScan} />;
      case 'vulnerabilityManagement': return <VulnerabilityManagement />;
      case 'cloudSecurity': return <CloudSecurityDashboard cloudAccounts={tenantData.cloudAccounts} findings={tenantData.cspmFindings} onAddAccount={handleAddCloudAccount} />;
      case 'security': return <SecurityDashboard securityCases={tenantData.securityCases} playbooks={playbooks} securityEvents={tenantData.securityEvents} users={users} onCaseUpdate={handleCaseUpdate} onGeneratePlaybook={handleGeneratePlaybook} onAnalyzeImpact={handleAnalyzeImpact} threatIntelFeed={threatIntelFeed} />;
      case 'compliance': return <ComplianceDashboard complianceFrameworks={tenantData.complianceFrameworks} assets={tenantData.assets} assetComplianceData={tenantData.assetComplianceData || []} />;
      case 'aiGovernance': return <AIGovernanceDashboard aiSystems={tenantData.aiSystems} users={users} onUpdateSystem={handleUpdateSystem} onAddNewSystem={handleAddNewSystem} registeredModels={tenantData.registeredModels} modelExperiments={tenantData.modelExperiments} onPromoteModel={handlePromoteModel} />;
      case 'finops': return <FinOpsBillingPage tenants={tenants} isSuperAdminView={currentUser.role === 'Super Admin' || currentUser.role === 'superadmin'} />;
      case 'auditLog': return <AuditLogDashboard logs={tenantData.auditLogs} />;
      case 'settings': return <SettingsDashboard integrations={tenantData.integrations} alertRules={tenantData.alertRules} roles={roles} users={currentUser.role === 'Super Admin' || currentUser.role === 'superadmin' ? users : users.filter(u => activeTenantId ? u.tenantId === activeTenantId : true)} apiKeys={tenants.find(t => t.id === activeTenantId)?.apiKeys || []} newlyGeneratedKey={newlyGeneratedKey} onAcknowledgeNewKey={() => setNewlyGeneratedKey(null)} onGenerateApiKey={handleGenerateApiKey} onRevokeApiKey={handleRevokeApiKey} onSaveAlertRule={(rule) => api.saveAlertRule(rule).then(saved => setAlertRules(prev => prev.map(r => r.id === saved.id ? saved : r)))} onDeleteAlertRule={(id) => api.deleteAlertRule(id).then(() => setAlertRules(prev => prev.filter(r => r.id !== id)))} onSaveIntegration={(int) => api.saveIntegration(int).then(saved => setIntegrations(prev => prev.map(i => i.id === saved.id ? saved : i)))} onToggleIntegration={(id) => { const int = integrations.find(i => i.id === id); if (int) api.saveIntegration({ ...int, isEnabled: !int.isEnabled }).then(saved => setIntegrations(prev => prev.map(i => i.id === saved.id ? saved : i))) }} onSaveRole={handleSaveRole} onDeleteRole={handleDeleteRole} tenants={tenants} onAddNewUser={handleAddNewUser} onUpdateUser={handleUpdateUser} onResetPassword={handleResetPassword} databaseSettings={databaseSettings} llmSettings={llmSettings} onSaveInfrastructure={(updates) => api.saveInfrastructure(updates).then(res => { if (res.db) setDatabaseSettings(res.db); if (res.llm) setLlmSettings(res.llm); })} dataSources={tenantData.dataSources} onSaveDataSource={(source) => api.saveDataSource({ ...source, tenantId: activeTenantId! }).then(saved => { setDataSources(prev => { const exists = prev.some(s => s.id === saved.id); if (exists) return prev.map(s => s.id === saved.id ? saved : s); return [...prev, saved]; }) })} onDeleteDataSource={(id) => api.deleteDataSource(id).then(() => setDataSources(prev => prev.filter(s => s.id !== id)))} onTestDataSource={(id) => api.testDataSourceConnection(dataSources.find(ds => ds.id === id)!).then(() => api.fetchDataSources().then(setDataSources))} onSaveTenantFeatures={handleTenantAdminFeatureSave} onSaveTenantVoiceBotSettings={(settings) => activeTenantId ? api.updateTenantVoiceBotSettings(activeTenantId, settings).then(updated => { setTenants(prev => prev.map(t => t.id === updated.id ? updated : t)); }) : Promise.resolve()} onAddTenant={handleAddNewTenant} onDeleteTenant={handleDeleteTenant} />;
      case 'tenantManagement': return <TenantManagementDashboard tenants={tenants.filter(t => t.id !== 'platform-admin')} onAddNewTenant={() => setIsAddTenantModalOpen(true)} onViewTenant={(id) => { setViewingTenantId(id); handleSetCurrentView('agents'); }} onManageTenant={(t) => setManagingTenant(tenants.find(T => T.id === t.id) || null)} handleDelete={handleDeleteTenant} handleUpdateTenant={async (id, data) => { await api.updateTenantFeatures(id, data.enabledFeatures || [], data.subscriptionTier || 'Free'); loadAllData(); }} />;
      case 'siem': return <ThreatDashboard />;
      case 'logExplorer': return <LogExplorerDashboard />;
      case 'threatHunting': return <ThreatHuntingDashboard findings={tenantData.uebaFindings} auditLogs={auditLogs} users={users} />;
      case 'incidentImpact': return <IncidentImpactDashboard graph={incidentImpactGraph!} context={viewingImpactFor} alerts={tenantData.alerts} cases={tenantData.securityCases} onAnalyze={handleAnalyzeImpact} />;
      case 'pentest': return <PentestDashboard tenantId={activeTenantId} />;
      case 'playbooks': return <PlaybookBuilder />;
      case 'threatIntelligence': return (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Threat Intelligence</h1>
          </div>
          <ThreatIntelFeedEnhanced tenantId={activeTenantId} />
        </div>
      );
      case 'profile': return <UserProfilePage onProfileUpdate={handleProfileUpdate} />;
      case 'automation': return <AutomationPoliciesDashboard policies={tenantData.automationPolicies} onUpdatePolicy={handleUpdateAutomationPolicy} onAddPolicy={handleAddAutomationPolicy} />;
      case 'devsecops': return <DevSecOpsDashboard sboms={tenantData.sboms} softwareComponents={tenantData.softwareComponents} onUploadSbom={handleUploadSbom} sastFindings={tenantData.sastFindings} repositories={tenantData.codeRepositories} initialTab="sast" mode="sast-only" />;
      case 'sbom': return <DevSecOpsDashboard sboms={tenantData.sboms} softwareComponents={tenantData.softwareComponents} onUploadSbom={handleUploadSbom} sastFindings={tenantData.sastFindings} repositories={tenantData.codeRepositories} initialTab="sbom" mode="sbom-only" />;
      case 'developer_hub': return <DeveloperHubDashboard endpoints={apiDocs} />;
      case 'proactiveInsights': return <ProactiveInsightsDashboard insights={tenantData.proactiveInsights} />;
      case 'distributedTracing': return <DistributedTracingDashboard traces={tenantData.traces} serviceMap={tenantData.serviceMap} />;
      case 'dataSecurity': return <DataSecurityDashboard findings={tenantData.sensitiveDataFindings} />;
      case 'attackPath': return <AttackPathDashboard attackPaths={tenantData.attackPaths} />;
      case 'serviceCatalog':
        return <ServiceCatalogDashboard templates={tenantData.serviceTemplates} provisionedServices={tenantData.provisionedServices} />;
      case 'servicePricing':
        return <ServicePricingPage />;
      case 'doraMetrics': return <DoraMetricsDashboard metrics={tenantData.doraMetrics} />;
      case 'chaosEngineering': return <ChaosEngineeringDashboard experiments={tenantData.chaosExperiments} />;
      case 'networkObservability': console.log("[App] Rendering NetworkObservability with:", tenantData.networkDevices); return <NetworkObservabilityDashboard networkDevices={tenantData.networkDevices} onAddDevice={handleAddNewDevice} onRefresh={loadAllData} />;
      case 'dataUtilization': return <DataUtilizationDashboard />;
      case 'tasks': return (
        <div className="max-w-4xl mx-auto">
          <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-6">My Tasks</h2>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
            <TaskForm onAdd={handleAddTask} />
            <TaskList tasks={myTasks} onToggle={handleToggleTask} onDelete={handleDeleteTask} />
          </div>
        </div>
      );
      // 2030 Industry Features
      case 'webhooks': return <WebhookManagement />;
      case 'sustainability': return <SustainabilityDashboard />;
      case 'zeroTrustQuantum': return <ZeroTrustQuantumDashboard />;
      case 'paymentSettings': return <PaymentSettings />;
      case 'subscriptionManagement': return <SubscriptionManagement />;
      case 'invoices': return <InvoiceList />;
      case 'unifiedOps':
      case 'futureOps':
        return <FutureOpsDashboard />;
      case 'swarm': return <SwarmDashboard />;
      case 'digitalTwin': return <SimulationDashboard />;
      case 'riskRegister': return <RiskRegister />;
      case 'vendorManagement': return <VendorManagement />;
      case 'trustCenter': return <TrustCenter />;
      case 'secureFileShare': return <SecureFileShare />;
      case 'securityTraining': return <SecurityTraining />;
      case 'complianceOracle': return <ComplianceOracleDashboard />;
      case 'cissporacle': return <CISSPOracle />;
      case 'jobs': return <JobsDashboard />;
      case 'llmops': return <LLMOpsDashboard />;
      case 'softwareDeployment': return <SoftwareDeployment />;
      case 'securitySimulation': return <SecuritySimulation />;
      case 'dast': return <DASTDashboard />;
      case 'serviceMesh': return <ServiceMeshDashboard />;
      case 'persistence':
      case 'persistenceDetection': return <PersistenceDashboard />;
      case 'approvalWorkflows': return <MultiStepApprovalDashboard />;
      case 'advancedBi':
      case 'biDashboard': return <AdvancedBiDashboard tenantId={activeTenantId || undefined} />;
      case 'systemHealth': return <ApiStatusDashboard />;
      case 'securityAudit': return <SecurityAuditDashboard />;
      case 'dataWarehouse': return <DataWarehouseDashboard />;
      case 'streaming': return <StreamingDashboard />;
      case 'dataGovernance': return <DataGovernanceDashboard />;
      case 'webMonitoring': return <WebMonitoringDashboard />;
      case 'mlops': return <MLOpsDashboard />;
      case 'automl': return <AutoMLDashboard />;
      case 'xai': return <XAIDashboard />;
      case 'abTesting': return <ABTestingDashboard />;
      case 'edr': return <EDRDashboard token={localStorage.getItem('access_token') || undefined} />;
      case 'mitreAttack': return <Suspense fallback={<div style={{ color: '#94a3b8', padding: 40 }}>Loading MITRE ATT&CK...</div>}><MitreAttackHeatmap /></Suspense>;
      case 'dlp': return <Suspense fallback={<div style={{ color: '#94a3b8', padding: 40 }}>Loading DLP...</div>}><DLPDashboard /></Suspense>;
      case 'ticketing': return <Suspense fallback={<div style={{ color: '#94a3b8', padding: 40 }}>Loading Ticketing...</div>}><TicketingIntegration /></Suspense>;
      case 'ueba': return <UEBADashboard />;
      case 'vulnerabilities': return <VulnerabilityManagement />;
      default: return <Dashboard metrics={metrics} alerts={tenantData.alerts} complianceFrameworks={tenantData.complianceFrameworks} aiSystems={tenantData.aiSystems} currentUser={currentUser} setCurrentView={handleSetCurrentView} />;

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
          hasPermission
        }}>
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
                  notifications={tenantData.notifications}
                  onNotificationClick={(n) => {
                    handleSetCurrentView(n.linkTo);
                    api.markNotificationAsRead(n.id).then(() => api.fetchNotifications().then(setNotifications));
                  }}
                  onMarkAllAsRead={() => {
                    const unreadIds = tenantData.notifications.filter(n => !n.isRead).map(n => n.id);
                    api.markAllNotificationsAsRead(unreadIds).then(() => api.fetchNotifications().then(setNotifications));
                  }}
                  onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
                  onOpenCommandBar={() => setIsCommandBarOpen(true)}
                  setCurrentView={handleSetCurrentView}
                  onStartTour={() => window.dispatchEvent(new Event('start-genesis-tour'))}
                />
                <main className="flex-1 overflow-x-hidden overflow-y-auto p-4 md:p-6">
                  <ErrorBoundary name="MainContent">
                    {renderView()}
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

          {/* Sidebar Items are in Sidebar.tsx */}


          <AddNewTenantModal isOpen={isAddTenantModalOpen} onClose={() => setIsAddTenantModalOpen(false)} onSave={handleAddNewTenant} />
          {managingTenant && (
            <ManageTenantModal
              isOpen={!!managingTenant}
              onClose={() => setManagingTenant(null)}
              tenant={managingTenant}
              onSave={handleSaveTenantFeatures}
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
          />
          <AICommandBar
            isOpen={isCommandBarOpen}
            onClose={() => setIsCommandBarOpen(false)}
            onExecuteCommand={handleExecuteCommand}
          />
        </UserContext.Provider>
      </ThemeProvider>
    </TimeZoneProvider>
  );
};

export default App;
