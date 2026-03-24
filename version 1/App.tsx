

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { LoginPage } from './LoginPage';
import { Dashboard } from './components/Dashboard';
import { ReportingDashboard } from './components/ReportingDashboard';
import { AgentsDashboard } from './components/AgentsDashboard';
import { AssetManagementDashboard } from './components/AssetManagementDashboard';
import { PatchManagementDashboard } from './components/PatchManagementDashboard';
import { CloudSecurityDashboard } from './components/CloudSecurityDashboard';
import { SecurityDashboard } from './components/SecurityDashboard';
import { ComplianceDashboard } from './components/ComplianceDashboard';
import { AIGovernanceDashboard } from './components/AIGovernanceDashboard';
import { FinOpsDashboard } from './components/FinOpsDashboard';
import { AuditLogDashboard } from './components/AuditLogDashboard';
import { SettingsDashboard } from './components/SettingsDashboard';
import { TenantManagementDashboard } from './components/TenantManagementDashboard';
import { AddNewTenantModal } from './components/AddNewTenantModal';
import { ManageTenantModal } from './components/ManageTenantModal';
import { RegisterAgentModal } from './components/RegisterAgentModal';
import { ChatFab } from './components/ChatFab';
import { ChatAssistant } from './components/ChatAssistant';
import { AICommandBar, Command } from './components/AICommandBar';
import { LogExplorerDashboard } from './components/LogExplorerDashboard';
import { ThreatHuntingDashboard } from './components/ThreatHuntingDashboard';
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


import { Theme, ThemeContext } from './contexts/ThemeContext';
import { UserContext } from './contexts/UserContext';

import * as api from './services/apiService';
import { AppView, User, Role, Tenant, Metric, Alert, ComplianceFramework, AiSystem, Asset, Patch, SecurityCase, Playbook, SecurityEvent, CloudAccount, CSPMFinding, Notification, AuditLog, Integration, AlertRule, Agent, DatabaseSettings, LlmSettings, DataSource, Sbom, SoftwareComponent, AgentUpgradeJob, PatchDeploymentJob, Permission, Filter, LogEntry, UebaFinding, ModelExperiment, RegisteredModel, ModelStage, AutomationPolicy, SastFinding, CodeRepository, ApiDocEndpoint, IncidentImpactGraph, NewUserPayload, AgentPlatform, SubscriptionTier, SensitiveDataFinding, AttackPath, ServiceTemplate, ProvisionedService, DoraMetrics, ChaosExperiment, ProactiveInsight, Trace, ServiceMap, VulnerabilityScanJob, NetworkDevice, ThreatIntelResult, NewTenantPayload } from './types';
import { SUBSCRIPTION_TIERS } from './constants';
import { AlertTriangleIcon } from './components/icons';

// FIX: Added mappings for new AppViews to satisfy the Record type.
const viewPermissionMap: Record<AppView, Permission> = {
  dashboard: 'view:dashboard',
  reporting: 'view:reporting',
  agents: 'view:agents',
  assetManagement: 'view:assets',
  patchManagement: 'view:patching',
  cloudSecurity: 'view:cloud_security',
  security: 'view:security',
  compliance: 'view:compliance',
  aiGovernance: 'view:ai_governance',
  finops: 'view:finops',
  auditLog: 'view:audit_log',
  settings: 'manage:settings',
  tenantManagement: 'manage:tenants',
  logExplorer: 'view:logs',
  threatHunting: 'view:threat_hunting',
  profile: 'view:profile',
  automation: 'view:automation',
  devsecops: 'view:devsecops',
  developer_hub: 'view:developer_hub',
  incidentImpact: 'investigate:security',
  proactiveInsights: 'view:insights',
  distributedTracing: 'view:tracing',
  dataSecurity: 'view:dspm',
  attackPath: 'view:attack_path',
  serviceCatalog: 'view:service_catalog',
  doraMetrics: 'view:dora_metrics',
  chaosEngineering: 'view:chaos',
  networkObservability: 'view:network',
};


const App: React.FC = () => {
  // Global App State
  const [theme, setTheme] = useState<Theme>('light');
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [currentView, setCurrentView] = useState<AppView>('patchManagement');
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [viewingTenantId, setViewingTenantId] = useState<string | null>(null);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isCommandBarOpen, setIsCommandBarOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filter State for Dashboards
  const [agentFilters, setAgentFilters] = useState<Filter[]>([]);
  const [assetFilters, setAssetFilters] = useState<Filter[]>([]);
  const [viewingImpactFor, setViewingImpactFor] = useState<{ type: 'alert' | 'case', id: string} | null>(null);


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

  // Modal State
  const [isAddTenantModalOpen, setIsAddTenantModalOpen] = useState(false);
  const [managingTenant, setManagingTenant] = useState<Tenant | null>(null);
  const [isRegisterAgentModalOpen, setIsRegisterAgentModalOpen] = useState(false);
  const [newlyGeneratedKey, setNewlyGeneratedKey] = useState<{name: string, key: string} | null>(null);
  
  useEffect(() => {
    const root = window.document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, [theme]);
  
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

  // Initial Data Load
  useEffect(() => {
    const loadAllData = async () => {
      try {
        const [
          usersData, rolesData, tenantsData, metricsData, alertsData, complianceData,
          aiSystemsData, assetsData, patchesData, securityCasesData, playbooksData,
          securityEventsData, cloudAccountsData, cspmFindingsData, notificationsData,
          auditLogsData, integrationsData, alertRulesData, historicalData, agentsData,
          dbSettingsData, llmSettingsData, dataSourcesData, sbomsData, softwareComponentsData,
          agentUpgradeJobsData, patchDeploymentJobsData, vulnerabilityScanJobsData, logsData, uebaFindingsData, modelExperimentsData, registeredModelsData,
          automationPoliciesData, sastFindingsData, codeRepositoriesData, apiDocsData, incidentImpactGraphData,
          sensitiveDataFindingsData, attackPathsData, serviceTemplatesData, provisionedServicesData, doraMetricsData, chaosExperimentsData,
          proactiveInsightsData, tracesData, serviceMapData, threatIntelFeedData, networkDevicesData,
        ] = await Promise.all([
          api.fetchUsers(), api.fetchRoles(), api.fetchTenants(), api.fetchMetrics(),
          api.fetchAlerts(), api.fetchComplianceFrameworks(), api.fetchAiSystems(),
          api.fetchAssets(), api.fetchPatches(), api.fetchSecurityCases(),
          api.fetchPlaybooks(), api.fetchSecurityEvents(), api.fetchCloudAccounts(),
          api.fetchCspmFindings(), api.fetchNotifications(), api.fetchAuditLogs(),
          api.fetchIntegrations(), api.fetchAlertRules(), api.fetchHistoricalData(),
          api.fetchAgents(), api.fetchDatabaseSettings(), api.fetchLlmSettings(),
          api.fetchDataSources(), api.fetchSboms(), api.fetchSoftwareComponents(),
          api.fetchAgentUpgradeJobs(), api.fetchPatchDeploymentJobs(), api.fetchVulnerabilityScanJobs(), api.fetchLogs(), api.fetchUebaFindings(),
          api.fetchModelExperiments(), api.fetchRegisteredModels(), api.fetchAutomationPolicies(),
          api.fetchSastFindings(), api.fetchCodeRepositories(), api.fetchApiDocs(),
          api.fetchIncidentImpactGraph('dummy-id'), api.fetchSensitiveDataFindings(),
          api.fetchAttackPaths(), api.fetchServiceTemplates(), api.fetchProvisionedServices(),
          api.fetchDoraMetrics(), api.fetchChaosExperiments(), api.fetchProactiveInsights(),
          api.fetchTraces(), api.fetchServiceMap(), api.fetchThreatIntelFeed(), api.fetchNetworkDevices(),
        ]);

        setUsers(usersData);
        setRoles(rolesData);
        setTenants(tenantsData);
        setMetrics(metricsData);
        setAlerts(alertsData);
        setComplianceFrameworks(complianceData);
        setAiSystems(aiSystemsData);
        setAssets(assetsData);
        setPatches(patchesData);
        setSecurityCases(securityCasesData);
        setPlaybooks(playbooksData);
        setSecurityEvents(securityEventsData);
        setCloudAccounts(cloudAccountsData);
        setCspmFindings(cspmFindingsData);
        setNotifications(notificationsData);
        setAuditLogs(auditLogsData);
        setIntegrations(integrationsData);
        setAlertRules(alertRulesData);
        setHistoricalData(historicalData);
        setAgents(agentsData);
        setDatabaseSettings(dbSettingsData);
        setLlmSettings(llmSettingsData);
        setDataSources(dataSourcesData);
        setSboms(sbomsData);
        setSoftwareComponents(softwareComponentsData);
        setAgentUpgradeJobs(agentUpgradeJobsData);
        setPatchDeploymentJobs(patchDeploymentJobsData);
        setVulnerabilityScanJobs(vulnerabilityScanJobsData);
        setLogs(logsData);
        setUebaFindings(uebaFindingsData);
        setModelExperiments(modelExperimentsData);
        setRegisteredModels(registeredModelsData);
        setAutomationPolicies(automationPoliciesData);
        setSastFindings(sastFindingsData);
        setCodeRepositories(codeRepositoriesData);
        setApiDocs(apiDocsData);
        setIncidentImpactGraph(incidentImpactGraphData);
        setSensitiveDataFindings(sensitiveDataFindingsData);
        setAttackPaths(attackPathsData);
        setServiceTemplates(serviceTemplatesData);
        setProvisionedServices(provisionedServicesData);
        setDoraMetrics(doraMetricsData);
        setChaosExperiments(chaosExperimentsData);
        setProactiveInsights(proactiveInsightsData);
        setTraces(tracesData);
        setServiceMap(serviceMapData);
        setThreatIntelFeed(threatIntelFeedData);
        setNetworkDevices(networkDevicesData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An unknown error occurred.');
      }
    };
    loadAllData();
  }, []);

  const activeTenantId = viewingTenantId || currentUser?.tenantId;

  // --- DERIVED STATE & CONTEXT ---
  const { enabledFeatures, hasPermission } = useMemo(() => {
    if (!currentUser) return { enabledFeatures: [], hasPermission: () => false };
    
    const role = roles.find(r => r.name === currentUser.role);
    if (!role) return { enabledFeatures: [], hasPermission: () => false };

    let effectiveFeatures: Permission[];
    
    // Super admin has all permissions, always.
    if (currentUser.role === 'Super Admin') {
        effectiveFeatures = role.permissions;
    } else {
        const tenant = tenants.find(t => t.id === currentUser.tenantId);
        if (!tenant) return { enabledFeatures: [], hasPermission: () => false };
        // Intersect role permissions with tenant's enabled features
        effectiveFeatures = role.permissions.filter(p => tenant.enabledFeatures.includes(p));
    }

    const checkPermission = (permission: Permission): boolean => effectiveFeatures.includes(permission);

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
          patches: patches.filter(p => p.affectedAssets.some(assetId => assets.find(a => a.id === assetId)?.tenantId === activeTenantId)),
          patchDeploymentJobs: patchDeploymentJobs, // Assume global for now
          vulnerabilityScanJobs: vulnerabilityScanJobs, // Assume global for now
          cloudAccounts: cloudAccounts.filter(c => c.tenantId === activeTenantId),
          cspmFindings: cspmFindings.filter(f => f.tenantId === activeTenantId),
          notifications: notifications.filter(n => tenants.find(t => t.id === activeTenantId)), // Simple filter for demo
          auditLogs: auditLogs.filter(log => log.details.includes(activeTenantId) || log.userName.includes(tenants.find(t=>t.id === activeTenantId)?.name || 'non-existent')),
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
      };
  }, [activeTenantId, alerts, assets, agents, securityEvents, securityCases, complianceFrameworks, aiSystems, patches, patchDeploymentJobs, vulnerabilityScanJobs, cloudAccounts, cspmFindings, notifications, auditLogs, integrations, alertRules, tenants, dataSources, sboms, softwareComponents, agentUpgradeJobs, logs, uebaFindings, modelExperiments, registeredModels, automationPolicies, sastFindings, codeRepositories, sensitiveDataFindings, attackPaths, serviceTemplates, provisionedServices, doraMetrics, chaosExperiments, proactiveInsights, traces, serviceMap, networkDevices]);


  // --- EVENT HANDLERS & API CALLS ---
  const login = useCallback(async (email: string, password: string): Promise<boolean> => {
    await api.mockDelay(500); // Simulate network latency
    // FIX: Add optional chaining for password as it's optional on the User type
    const user = users.find(u => u.email.toLowerCase() === email.toLowerCase() && u.password === password);
    if (user) {
      setCurrentUser(user);
      setViewingTenantId(user.role === 'Super Admin' ? null : user.tenantId);
      setCurrentView('dashboard');
      return true;
    }
    return false;
  }, [users]);

  const signup = async (payload: Omit<NewUserPayload, 'tenantName'>): Promise<boolean> => {
    const tenant = tenants.find(t => t.id === payload.tenantId);
    if (!tenant) {
        console.error("Invalid tenant selected during signup");
        return false;
    }
    const emailExists = users.some(u => u.email.toLowerCase() === payload.email.toLowerCase());
    if (emailExists) {
        console.error("Email already exists");
        return false;
    }

    const newUserPayload: NewUserPayload = { ...payload, tenantName: tenant.name };
    const allUsers = await api.addUser(newUserPayload);
    setUsers(allUsers);

    // Automatically log in the new user
    const newUser = allUsers.find(u => u.email.toLowerCase() === payload.email.toLowerCase());
    if (newUser) {
        setCurrentUser(newUser);
        setViewingTenantId(newUser.role === 'Super Admin' ? null : newUser.tenantId);
        setCurrentView('dashboard');
        return true;
    }
    return false;
  };

  // FIX: Add registerTenant function to satisfy UserContextType.
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
    setCurrentUser(null);
    setViewingTenantId(null);
  }, []);
  
  const handleSetCurrentView = useCallback((view: AppView) => {
      const requiredPermission = viewPermissionMap[view];
      if (hasPermission(requiredPermission)) {
          setCurrentView(view);
      } else {
          console.warn(`User does not have permission to view: ${view}`);
          // Optionally show an error message to the user
      }
  }, [hasPermission]);

  const toggleTheme = useCallback(() => {
    setTheme(prevTheme => (prevTheme === 'light' ? 'dark' : 'light'));
  }, []);

  const handleAddNewTenant = async (name: string) => {
    const {newTenant, newAdminUser} = await api.addTenant(name);
    setTenants(prev => [...prev, newTenant]);
    setUsers(prev => [...prev, newAdminUser]);
    setIsAddTenantModalOpen(false);
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

  const handleDeleteTenant = (tenantId: string) => {
      api.deleteTenant(tenantId).then(() => {
          setTenants(prev => prev.filter(t => t.id !== tenantId));
          setUsers(prev => prev.filter(u => u.tenantId !== tenantId));
      });
  };

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
    });
  };

  const handleRunVulnerabilityScan = async (assetId: string) => {
      await api.runVulnerabilityScan(assetId);
      // Refetch assets to get updated scan date
      api.fetchAssets().then(setAssets);
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
      const newJob = await api.scheduleVulnerabilityScan(assetIds, scanType, scheduleTime);
      setVulnerabilityScanJobs(prev => [newJob, ...prev]);
      // The job simulation will eventually update asset scan dates.
      // We can refetch assets after a reasonable delay.
      setTimeout(() => {
          api.fetchAssets().then(setAssets);
      }, (assetIds.length * 2000) + 5000); // Rough estimate
  };

  const handleUpdateUser = (userId: string, updates: { role?: string, status?: 'Active' | 'Disabled' }) => {
      api.updateUser(userId, updates).then(updatedUser => {
          setUsers(prev => prev.map(u => u.id === userId ? updatedUser : u));
      });
  };

  const handleResetPassword = async (userId: string, userName: string) => {
    if (window.confirm(`Are you sure you want to reset the password for ${userName}?`)) {
        await api.resetPassword(userId);
        alert(`A password reset link has been sent to the user's email (simulated).`);
    }
  };

  const handleAddNewUser = async (user: NewUserPayload) => {
      const allUsers = await api.addUser(user);
      setUsers(allUsers);
  };

  const handleProfileUpdate = (updates: { name: string, avatar: string }) => {
      if (currentUser) {
          api.updateUser(currentUser.id, updates).then(updatedUser => {
              setCurrentUser(updatedUser);
              setUsers(prev => prev.map(u => u.id === updatedUser.id ? updatedUser : u));
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
    if(!activeTenantId) return;
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
  
  const handleUploadSbom = async (applicationName: string) => {
      if(!activeTenantId) return;
      const { newSbom, newComponents } = await api.uploadSbom(applicationName, activeTenantId);
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

  const userContextValue = useMemo(() => ({
    currentUser,
    login,
    logout,
    signup,
    registerTenant,
    hasPermission,
    enabledFeatures,
  }), [currentUser, login, logout, signup, registerTenant, hasPermission, enabledFeatures]);

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
        <ThemeContext.Provider value={{ theme, toggleTheme }}>
            <UserContext.Provider value={userContextValue}>
                <LoginPage />
            </UserContext.Provider>
        </ThemeContext.Provider>
    );
  }
  
  const renderView = () => {
    if(viewingImpactFor && currentView === 'incidentImpact' && incidentImpactGraph) {
        return <IncidentImpactDashboard graph={incidentImpactGraph} context={viewingImpactFor} alerts={alerts} cases={securityCases} />;
    }

    switch (currentView) {
      case 'dashboard': return <Dashboard metrics={metrics} alerts={tenantData.alerts} complianceFrameworks={tenantData.complianceFrameworks} aiSystems={tenantData.aiSystems} currentUser={currentUser} setCurrentView={handleSetCurrentView} />;
      case 'reporting': return <ReportingDashboard historicalData={historicalData} assets={tenantData.assets} />;
      case 'agents': return <AgentsDashboard agents={tenantData.agents} assets={tenantData.assets} registrationKey={tenants.find(t=>t.id === activeTenantId)?.registrationKey || null} onRegisterAgent={() => setIsRegisterAgentModalOpen(true)} onUpdateAgent={handleUpdateAgent} agentUpgradeJobs={tenantData.agentUpgradeJobs} onScheduleUpgrade={handleScheduleUpgrade} filters={agentFilters} onClearFilters={() => setAgentFilters([])} logs={tenantData.logs}/>;
      case 'assetManagement': return <AssetManagementDashboard assets={tenantData.assets} patches={tenantData.patches} onRunVulnerabilityScan={handleRunVulnerabilityScan} filters={assetFilters} onClearFilters={() => setAssetFilters([])} />;
      case 'patchManagement': return <PatchManagementDashboard patches={tenantData.patches} assets={tenantData.assets} patchDeploymentJobs={tenantData.patchDeploymentJobs} onSchedulePatchDeployment={handleSchedulePatchDeployment} vulnerabilityScanJobs={tenantData.vulnerabilityScanJobs} onScheduleVulnerabilityScan={handleScheduleVulnerabilityScan} />;
      case 'cloudSecurity': return <CloudSecurityDashboard cloudAccounts={tenantData.cloudAccounts} findings={tenantData.cspmFindings} onAddAccount={handleAddCloudAccount} />;
      case 'security': return <SecurityDashboard securityCases={tenantData.securityCases} playbooks={playbooks} securityEvents={tenantData.securityEvents} users={users} onCaseUpdate={handleCaseUpdate} onGeneratePlaybook={handleGeneratePlaybook} onAnalyzeImpact={handleAnalyzeImpact} threatIntelFeed={threatIntelFeed} />;
      case 'compliance': return <ComplianceDashboard complianceFrameworks={tenantData.complianceFrameworks} />;
      case 'aiGovernance': return <AIGovernanceDashboard aiSystems={tenantData.aiSystems} users={users} onUpdateSystem={handleUpdateSystem} onAddNewSystem={handleAddNewSystem} registeredModels={tenantData.registeredModels} modelExperiments={tenantData.modelExperiments} onPromoteModel={handlePromoteModel} />;
      case 'finops': return <FinOpsDashboard tenants={tenants.filter(t => t.id !== 'platform-admin')} isSuperAdminView={currentUser.role === 'Super Admin'} />;
      case 'auditLog': return <AuditLogDashboard logs={tenantData.auditLogs} />;
      case 'settings': return <SettingsDashboard integrations={tenantData.integrations} alertRules={tenantData.alertRules} roles={roles} users={users.filter(u => activeTenantId ? u.tenantId === activeTenantId : true)} apiKeys={tenants.find(t=>t.id === activeTenantId)?.apiKeys || []} newlyGeneratedKey={newlyGeneratedKey} onAcknowledgeNewKey={() => setNewlyGeneratedKey(null)} onGenerateApiKey={handleGenerateApiKey} onRevokeApiKey={handleRevokeApiKey} onSaveAlertRule={(rule) => api.saveAlertRule(rule).then(saved => setAlertRules(prev => prev.map(r => r.id === saved.id ? saved : r)))} onDeleteAlertRule={(id) => api.deleteAlertRule(id).then(() => setAlertRules(prev => prev.filter(r => r.id !== id)))} onSaveIntegration={(int) => api.saveIntegration(int).then(saved => setIntegrations(prev => prev.map(i => i.id === saved.id ? saved : i)))} onToggleIntegration={(id) => { const int = integrations.find(i=>i.id===id); if(int) api.saveIntegration({...int, isEnabled: !int.isEnabled}).then(saved => setIntegrations(prev => prev.map(i => i.id === saved.id ? saved : i))) }} onSaveRole={handleSaveRole} onDeleteRole={handleDeleteRole} tenants={tenants} onAddNewUser={handleAddNewUser} onUpdateUser={handleUpdateUser} onResetPassword={handleResetPassword} databaseSettings={databaseSettings} llmSettings={llmSettings} onSaveInfrastructure={(updates) => api.saveInfrastructure(updates).then(res => { if(res.db) setDatabaseSettings(res.db); if(res.llm) setLlmSettings(res.llm);})} dataSources={tenantData.dataSources} onSaveDataSource={(source) => api.saveDataSource({...source, tenantId: activeTenantId!}).then(saved => { setDataSources(prev => {const exists = prev.some(s=>s.id === saved.id); if(exists) return prev.map(s=>s.id === saved.id ? saved: s); return [...prev, saved]; })})} onDeleteDataSource={(id) => api.deleteDataSource(id).then(()=>setDataSources(prev => prev.filter(s=>s.id !== id)))} onTestDataSource={(id) => api.testDataSourceConnection(dataSources.find(ds => ds.id === id)!).then(() => api.fetchDataSources().then(setDataSources))} onSaveTenantFeatures={handleTenantAdminFeatureSave} />;
      case 'tenantManagement': return <TenantManagementDashboard tenants={tenants.filter(t => t.id !== 'platform-admin')} onAddNewTenant={() => setIsAddTenantModalOpen(true)} onViewTenant={(id) => setViewingTenantId(id)} onManageTenant={(t) => setManagingTenant(tenants.find( T => T.id === t.id) || null)} onDeleteTenant={handleDeleteTenant} assets={assets} aiSystems={aiSystems} securityEvents={securityEvents}/>;
      case 'logExplorer': return <LogExplorerDashboard logs={tenantData.logs} />;
      case 'threatHunting': return <ThreatHuntingDashboard findings={tenantData.uebaFindings} auditLogs={auditLogs} users={users} />;
      case 'profile': return <UserProfilePage onProfileUpdate={handleProfileUpdate} />;
      case 'automation': return <AutomationPoliciesDashboard policies={tenantData.automationPolicies} onUpdatePolicy={handleUpdateAutomationPolicy} />;
      case 'devsecops': return <DevSecOpsDashboard sboms={tenantData.sboms} softwareComponents={tenantData.softwareComponents} onUploadSbom={handleUploadSbom} sastFindings={tenantData.sastFindings} repositories={tenantData.codeRepositories} />;
      case 'developer_hub': return <DeveloperHubDashboard endpoints={apiDocs} />;
      case 'proactiveInsights': return <ProactiveInsightsDashboard insights={tenantData.proactiveInsights} />;
      case 'distributedTracing': return <DistributedTracingDashboard traces={tenantData.traces} serviceMap={tenantData.serviceMap} />;
      case 'dataSecurity': return <DataSecurityDashboard findings={tenantData.sensitiveDataFindings} />;
      case 'attackPath': return <AttackPathDashboard attackPaths={tenantData.attackPaths} />;
      case 'serviceCatalog': return <ServiceCatalogDashboard templates={tenantData.serviceTemplates} provisionedServices={tenantData.provisionedServices} />;
      case 'doraMetrics': return <DoraMetricsDashboard metrics={tenantData.doraMetrics} />;
      case 'chaosEngineering': return <ChaosEngineeringDashboard experiments={tenantData.chaosExperiments} />;
      case 'networkObservability': return <NetworkObservabilityDashboard networkDevices={tenantData.networkDevices} onAddDevice={handleAddNewDevice} />;
      default: return <Dashboard metrics={metrics} alerts={tenantData.alerts} complianceFrameworks={tenantData.complianceFrameworks} aiSystems={tenantData.aiSystems} currentUser={currentUser} setCurrentView={handleSetCurrentView} />;
    }
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      <UserContext.Provider value={userContextValue}>
        <div className="flex h-screen bg-gray-100 dark:bg-gray-900 text-gray-800 dark:text-gray-200">
          <Sidebar 
            isOpen={isSidebarOpen} 
            currentView={currentView}
            setCurrentView={handleSetCurrentView}
            isViewingTenant={!!viewingTenantId}
            onBackToTenants={() => setViewingTenantId(null)}
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
            />
            <main className="flex-1 overflow-x-hidden overflow-y-auto p-4 md:p-6">
              {renderView()}
            </main>
          </div>
        </div>
        <ChatFab onClick={() => setIsChatOpen(true)} />

        <AddNewTenantModal isOpen={isAddTenantModalOpen} onClose={() => setIsAddTenantModalOpen(false)} onSave={handleAddNewTenant} />
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
        />
        <AICommandBar
          isOpen={isCommandBarOpen}
          onClose={() => setIsCommandBarOpen(false)}
          onExecuteCommand={handleExecuteCommand}
        />
      </UserContext.Provider>
    </ThemeContext.Provider>
  );
};

export default App;