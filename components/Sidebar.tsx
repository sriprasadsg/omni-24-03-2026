import React, { useMemo, useState, useEffect, useRef } from 'react';
import { BotIcon, DashboardIcon, ShieldCheckIcon, ServerIcon, DatabaseIcon, ShieldAlertIcon, ShieldZapIcon, BarChart3Icon, SettingsIcon, BuildingIcon, ArrowLeftIcon, CloudShieldIcon, DollarSignIcon, ClipboardListIcon, FileTextIcon, UsersIcon, WorkflowIcon, GitPullRequestDraftIcon, BookKeyIcon, LightbulbIcon, GitMergeIcon, DnaIcon, NetworkIcon, PuzzleIcon, GaugeIcon, BombIcon, SunIcon, ShieldLockIcon, Share2Icon, ActivityIcon, BoxIcon, FileCodeIcon, SearchIcon, CrownIcon, ZapIcon, SparklesIcon, UploadCloudIcon, BellIcon, ComponentIcon, GavelIcon } from './icons';
import { CreditCard, TrendingUp, FileText, Globe, Lock, UserIcon, ChevronDown, ShieldIcon, TargetIcon, AlertOctagonIcon, MessageSquareQuote as MessageSquareQuoteIcon, Monitor as MonitorIcon, UserCheck, ClipboardCheck, Cookie, RadioTower, BarChart2, Radar } from 'lucide-react';
import { AppView, Permission } from '../types';
import { useUser } from '../contexts/UserContext';
import { useFeatures } from '../contexts/FeaturesContext';
import { fetchSupportUnreadCount } from '../services/apiService';
import { socketService } from '../services/socketService';

// Tier precedence — matches backend TIER_ORDER
const TIER_ORDER: Record<string, number> = { Free: 0, Pro: 1, Enterprise: 2, Custom: 3 };
const tierMeetsMin = (current: string, min?: string) =>
    !min || (TIER_ORDER[current] ?? 0) >= (TIER_ORDER[min] ?? 0);

interface SidebarProps {
    isOpen: boolean;
    currentView: AppView;
    setCurrentView: (view: AppView) => void;
    isViewingTenant: boolean;
    onBackToTenants: () => void;
    branding?: {
        logoUrl?: string;
        companyName?: string;
    };
}

interface NavItem {
    view: AppView;
    label: string;
    icon: React.ReactNode;
    permission: Permission;
    minTier?: 'Pro' | 'Enterprise';
    featureKey?: string; // backend feature_flags.py key — used for server-confirmed locking
    locked?: string; // set at runtime by visibleGroups
}

interface NavGroup {
    title: string;
    items: NavItem[];
}

const NavLink: React.FC<{
    icon: React.ReactNode; label: string; active?: boolean;
    onClick: () => void; disabled?: boolean; isOpen: boolean;
    locked?: string; badge?: number;
}> = ({ icon, label, active, onClick, disabled, isOpen, locked, badge }) => (
    <button
        onClick={locked ? undefined : onClick}
        disabled={disabled}
        title={locked ? `Requires ${locked} plan — click to upgrade` : (!isOpen ? label : undefined)}
        className={`w-full flex items-center px-3 py-2 text-sm font-medium rounded-xl transition-all duration-200 relative group
            ${locked ? 'opacity-40 cursor-not-allowed' : ''}
            ${active && !locked
                ? 'text-primary-400'
                : 'text-slate-500 dark:text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            } ${disabled && !locked ? 'opacity-40 cursor-not-allowed' : ''}`}
        style={active && !locked ? {
            background: 'linear-gradient(135deg, rgba(0,210,255,0.12) 0%, rgba(127,0,255,0.06) 100%)',
            border: '1px solid rgba(0,210,255,0.18)',
        } : undefined}
    >
        {/* Icon */}
        <div className={`relative flex-shrink-0 transition-all duration-200
            ${active && !locked ? 'text-primary-400' : 'text-slate-500 dark:text-slate-500 group-hover:text-slate-700 dark:group-hover:text-slate-300'}`}>
            {icon}
            {!isOpen && !!badge && badge > 0 && (
                <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white">
                    {badge > 9 ? '9+' : badge}
                </span>
            )}
        </div>

        {isOpen && (
            <span className="ml-3 truncate flex-1 text-left tracking-tight">{label}</span>
        )}

        {isOpen && locked && (
            <span className="ml-auto flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-md"
                style={{ background: 'rgba(217,119,6,0.15)', color: '#fbbf24', border: '1px solid rgba(217,119,6,0.25)' }}>
                <Lock size={9} />{locked}
            </span>
        )}

        {isOpen && !locked && !!badge && badge > 0 && (
            <span className="ml-auto flex-shrink-0 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white px-1">
                {badge > 99 ? '99+' : badge}
            </span>
        )}

        {/* Gradient active bar */}
        {!locked && active && (
            <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-r-full -ml-3"
                style={{ background: 'linear-gradient(to bottom, #00d2ff, #7f00ff)' }} />
        )}
    </button>
);

// ─── Accordion Group ────────────────────────────────────────────────────────
const SidebarGroup: React.FC<{
    group: NavGroup;
    groupIndex: number;
    isOpen: boolean;
    currentView: AppView;
    setCurrentView: (view: AppView) => void;
    expandedGroup: string | null;
    setExpandedGroup: (title: string | null) => void;
    badgeCounts?: Record<string, number>;
}> = ({ group, groupIndex, isOpen, currentView, setCurrentView, expandedGroup, setExpandedGroup, badgeCounts }) => {
    const isExpanded = expandedGroup === group.title;
    const hasActiveItem = group.items.some(i => i.view === currentView);
    const contentRef = useRef<HTMLDivElement>(null);

    // Auto-expand when this group contains the active view
    useEffect(() => {
        if (hasActiveItem) setExpandedGroup(group.title);
    }, [currentView]);

    const toggle = () => setExpandedGroup(isExpanded ? null : group.title);

    return (
        <div className="overflow-hidden">
            {/* ── Group Header (accordion toggle) ─────────────────────── */}
            {isOpen ? (
                <button
                    onClick={toggle}
                    className={`w-full flex items-center justify-between px-3 py-1.5 mb-0.5 rounded-md
                        text-xs font-semibold uppercase tracking-wider select-none transition-all duration-200
                        ${isExpanded
                            ? 'text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20'
                            : 'text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/5'
                        }`}
                >
                    <span>{group.title}</span>
                    <ChevronDown
                        size={13}
                        className={`flex-shrink-0 transition-transform duration-300 ${isExpanded ? 'rotate-180' : 'rotate-0'}`}
                    />
                </button>
            ) : (
                /* Collapsed sidebar — just a thin divider between groups */
                groupIndex > 0 && <div className="my-2 border-t border-gray-100 dark:border-gray-800" />
            )}

            {/* ── Accordion Content (smooth slide) ─────────────────────── */}
            <div
                ref={contentRef}
                style={{
                    maxHeight: (!isOpen || isExpanded) ? '1000px' : '0px',
                    opacity: (!isOpen || isExpanded) ? 1 : 0,
                    overflow: 'hidden',
                    transition: 'max-height 0.35s cubic-bezier(0.4,0,0.2,1), opacity 0.25s ease',
                }}
            >
                <div className="space-y-0.5 py-0.5">
                    {group.items.map(item => (
                        <NavLink
                            key={item.view}
                            icon={item.icon}
                            label={item.label}
                            active={currentView === item.view}
                            onClick={() => setCurrentView(item.view)}
                            isOpen={isOpen}
                            locked={item.locked as string | undefined}
                            badge={badgeCounts?.[item.view]}
                        />
                    ))}
                </div>
            </div>
        </div>
    );
};

export const Sidebar: React.FC<SidebarProps> = ({ isOpen, currentView, setCurrentView, isViewingTenant, onBackToTenants, branding }) => {
    const userContext = useUser();
    const hasPermission = userContext?.hasPermission || (() => true);
    const currentUser = userContext?.currentUser;
    const serverLockedFeatures = userContext?.serverLockedFeatures ?? {};
    const { hasFeature, assignedBundles } = useFeatures();
    const isBundleMode = assignedBundles.length > 0;

    // ── Accordion state: which group header is currently open ──────────────
    const [expandedGroup, setExpandedGroup] = useState<string | null>(null);

    // ── Chat unread badge (support + endpoint combined) ───────────────────
    const [supportUnread, setSupportUnread]   = useState(0);
    const [endpointUnread, setEndpointUnread] = useState(0);
    useEffect(() => {
        const fetch = () => fetchSupportUnreadCount().then(setSupportUnread).catch(() => {});
        fetch();
        const id = setInterval(fetch, 30_000);
        return () => clearInterval(id);
    }, []);
    useEffect(() => {
        const handler = (data: any) => {
            if (data.event === 'agent_chat_message' || data.event === 'agent_chat_initiated') {
                setEndpointUnread(prev => prev + 1);
            }
        };
        // Reset endpoint badge whenever user navigates to chat
        if (['chat', 'agentChat'].includes(currentView)) setEndpointUnread(0);
        socketService.on('agent_chat', handler);
        return () => socketService.off('agent_chat', handler);
    }, [currentView]);

    const navGroups: NavGroup[] = useMemo(() => [
        {
            title: "Dashboards & Insights",
            items: [
                { view: 'dashboard', label: 'Overview', icon: <DashboardIcon size={20} />, permission: 'view:dashboard' },
                { view: 'cxo', label: 'CXO Insights', icon: <CrownIcon size={20} />, permission: 'view:cxo_dashboard', minTier: 'Enterprise', featureKey: 'cxo_dashboard' },
                { view: 'executiveSummary', label: 'Executive Summary', icon: <BarChart3Icon size={20} />, permission: 'view:reporting' },
                { view: 'unifiedOps', label: 'Unified Future Ops', icon: <DashboardIcon size={20} />, permission: 'view:unified_ops', minTier: 'Enterprise', featureKey: 'unified_ops' },
                { view: 'proactiveInsights', label: 'Proactive Insights', icon: <LightbulbIcon size={20} />, permission: 'view:insights' },
                { view: 'reporting', label: 'Reporting', icon: <BarChart3Icon size={20} />, permission: 'view:reporting' },
                { view: 'advancedBi', label: 'Advanced BI', icon: <BarChart3Icon size={20} />, permission: 'view:advanced_bi', minTier: 'Enterprise', featureKey: 'advanced_bi' },
                { view: 'digitalTwin', label: 'Digital Twin', icon: <BoxIcon size={20} />, permission: 'view:dashboard', minTier: 'Enterprise', featureKey: 'digital_twin' },
                { view: 'futureTech', label: '2027 Horizon', icon: <ZapIcon size={20} />, permission: 'view:dashboard', minTier: 'Enterprise' },
                { view: 'sustainability', label: 'Sustainability', icon: <SunIcon size={20} />, permission: 'view:sustainability', minTier: 'Enterprise', featureKey: 'sustainability' },
                { view: 'predictiveHealth', label: 'Predictive Health', icon: <ActivityIcon size={20} />, permission: 'view:predictive_health' },
                { view: 'goalSystem', label: 'Goal System', icon: <TargetIcon size={20} />, permission: 'view:goal_system', minTier: 'Enterprise', featureKey: 'goal_system' },
                { view: 'integrationsHub', label: 'Integrations Hub', icon: <PuzzleIcon size={20} />, permission: 'view:integrations' },
            ]
        },
        {
            title: "Observability",
            items: [
                { view: 'distributedTracing', label: 'Distributed Tracing', icon: <GitMergeIcon size={20} />, permission: 'view:tracing' },
                { view: 'apm', label: 'APM', icon: <GaugeIcon size={20} />, permission: 'view:tracing' },
                { view: 'logExplorer', label: 'Log Explorer', icon: <FileTextIcon size={20} />, permission: 'view:logs' },
                { view: 'networkObservability', label: 'Network Observability', icon: <NetworkIcon size={20} />, permission: 'view:network' },
                { view: 'networkTopology', label: 'Network Topology Map', icon: <NetworkIcon size={20} />, permission: 'view:network' },
                { view: 'dataUtilization', label: 'Data Utilization', icon: <ActivityIcon size={20} />, permission: 'view:network' },
                { view: 'webMonitoring', label: 'Web Monitoring', icon: <Globe size={20} />, permission: 'view:web_monitoring' },
                { view: 'serviceMesh', label: 'Service Mesh', icon: <NetworkIcon size={20} />, permission: 'view:network' },
                { view: 'streaming', label: 'Streaming Analytics', icon: <ActivityIcon size={20} />, permission: 'view:analytics' },
            ]
        },
        {
            title: "Infrastructure & Assets",
            items: [
                { view: 'agents', label: 'Agents', icon: <ServerIcon size={20} />, permission: 'view:agents' },
                { view: 'agentCapabilities', label: 'Agent Capabilities', icon: <ServerIcon size={20} />, permission: 'view:agent_capabilities' },
                { view: 'assetManagement', label: 'Assets', icon: <DatabaseIcon size={20} />, permission: 'view:assets' },
                { view: 'patchManagement', label: 'Patching', icon: <ShieldAlertIcon size={20} />, permission: 'view:patching' },
                { view: 'softwareUpdates', label: 'Software Updates', icon: <ShieldAlertIcon size={20} />, permission: 'view:software_updates' },
                { view: 'softwareDeployment', label: 'Software Deployment', icon: <BoxIcon size={20} />, permission: 'view:software_deployment' },
                { view: 'windowsAutopilot', label: 'Windows Autopilot', icon: <MonitorIcon size={20} />, permission: 'view:autopilot' },
                { view: 'mobileDeviceManagement', label: 'Mobile Device Mgmt', icon: <MonitorIcon size={20} />, permission: 'view:mdm' },
                { view: 'mobileAppManagement', label: 'App Management (MAM)', icon: <BoxIcon size={20} />, permission: 'view:mam' },
                { view: 'androidEnterprise', label: 'Android Enterprise', icon: <MonitorIcon size={20} />, permission: 'view:android_enterprise' },
                { view: 'branchSites', label: 'Branch Sites', icon: <BuildingIcon size={20} />, permission: 'view:branch_sites' },
                { view: 'appCatalog', label: 'App Catalog', icon: <BoxIcon size={20} />, permission: 'view:app_catalog' },
                { view: 'assetIntelligence', label: 'Asset Intelligence', icon: <ShieldAlertIcon size={20} />, permission: 'view:asset_intelligence' },
                { view: 'deviceConfigProfiles', label: 'Config Profiles', icon: <SettingsIcon size={20} />, permission: 'view:device_config_profiles' },
                { view: 'firmwareDriverUpdates', label: 'Firmware & Drivers', icon: <ZapIcon size={20} />, permission: 'view:firmware_drivers' },
                { view: 'serviceCatalog', label: 'Service Catalog (IDP)', icon: <PuzzleIcon size={20} />, permission: 'view:service_catalog' },
                { view: 'jobs', label: 'Jobs', icon: <ClipboardListIcon size={20} />, permission: 'view:jobs' },
                { view: 'remoteAccess', label: 'Remote Access', icon: <ActivityIcon size={20} />, permission: 'view:agents' },
                { view: 'chat', label: 'Chat', icon: <MessageSquareQuoteIcon size={20} />, permission: 'manage:agents' },
                { view: 'certificates', label: 'Certificates / TLS', icon: <ShieldCheckIcon size={20} />, permission: 'view:assets' },
            ]
        },
        {
            title: "Security (SecOps)",
            items: [
                { view: 'security', label: 'Security Overview', icon: <ShieldZapIcon size={20} />, permission: 'view:security' },
                { view: 'alertManagement', label: 'Alert Management', icon: <AlertOctagonIcon size={20} />, permission: 'view:security' },
                { view: 'edr', label: 'EDR (Real-Time)', icon: <ShieldZapIcon size={20} />, permission: 'view:security' },
                { view: 'yaraRules', label: 'YARA Rule Editor', icon: <ShieldZapIcon size={20} />, permission: 'view:security' },
                { view: 'mdr', label: 'Managed Detection (MDR)', icon: <ShieldZapIcon size={20} />, permission: 'view:mdr' },
                { view: 'xdr', label: 'Extended Detection (XDR)', icon: <NetworkIcon size={20} />, permission: 'view:xdr' },
                { view: 'mitreAttack', label: 'MITRE ATT&CK', icon: <NetworkIcon size={20} />, permission: 'view:security' },
                { view: 'dlp', label: 'Data Loss Prevention', icon: <ShieldLockIcon size={20} />, permission: 'view:security' },
                { view: 'cloudSecurity', label: 'Cloud Security', icon: <CloudShieldIcon size={20} />, permission: 'view:cloud_security' },
                { view: 'cloudAccounts', label: 'Multi-Account Scanning', icon: <CloudShieldIcon size={20} />, permission: 'view:cloud_security' },
                { view: 'iacContainer', label: 'IaC & Container Security', icon: <FileCodeIcon size={20} />, permission: 'view:cloud_security' },
                { view: 'threatHunting', label: 'Threat Hunting', icon: <SearchIcon size={20} />, permission: 'view:threat_hunting', minTier: 'Pro', featureKey: 'threat_hunting' },
                { view: 'siem', label: 'SIEM Dashboard (OCSF)', icon: <ShieldZapIcon size={20} />, permission: 'view:security' },
                { view: 'threatIntelligence', label: 'Threat Intelligence', icon: <TargetIcon size={20} />, permission: 'view:threat_intel' },
                { view: 'securityIntelConnectors', label: 'Intel Connectors', icon: <ZapIcon size={20} />, permission: 'view:security' },
                { view: 'siemRules', label: 'SIEM Correlation Rules', icon: <ShieldIcon size={20} />, permission: 'view:security' },
                { view: 'incidentResponse', label: 'Incident Response', icon: <AlertOctagonIcon size={20} />, permission: 'investigate:security' },
                { view: 'incidentWarRoom', label: 'Incident War Room', icon: <AlertOctagonIcon size={20} />, permission: 'investigate:security' },
                { view: 'deception', label: 'Deception Technology', icon: <ShieldIcon size={20} />, permission: 'view:security' },
                { view: 'aiAnomaly', label: 'AI Anomaly Detection', icon: <SparklesIcon size={20} />, permission: 'view:security' },
                { view: 'ueba', label: 'UEBA & Insider Threats', icon: <UserIcon size={20} />, permission: 'view:security' },
                { view: 'shadowAI', label: 'Shadow AI Detection', icon: <UserIcon size={20} />, permission: 'view:security' },
                { view: 'ndr', label: 'Network Detection (NDR)', icon: <NetworkIcon size={20} />, permission: 'view:security' },
                { view: 'correlations', label: 'Event Correlations', icon: <ActivityIcon size={20} />, permission: 'view:security' },
                { view: 'emailSecurity', label: 'Email Security', icon: <ShieldLockIcon size={20} />, permission: 'view:security' },
                { view: 'incidentImpact', label: 'Incident Impact', icon: <ActivityIcon size={20} />, permission: 'investigate:security' },
                { view: 'dataSecurity', label: 'Data Security (DSPM)', icon: <DnaIcon size={20} />, permission: 'view:dspm' },
                { view: 'attackPath', label: 'Attack Path', icon: <NetworkIcon size={20} />, permission: 'view:attack_path' },
                { view: 'pentest', label: 'Pentesting', icon: <ShieldAlertIcon size={20} />, permission: 'view:security' },
                { view: 'dast', label: 'DAST', icon: <ShieldAlertIcon size={20} />, permission: 'view:security' },
                { view: 'zeroTrustQuantum', label: 'Zero Trust & Quantum', icon: <ShieldLockIcon size={20} />, permission: 'view:zero_trust' },
                { view: 'vulnerabilityManagement', label: 'Vulnerabilities', icon: <ShieldAlertIcon size={20} />, permission: 'view:vulnerabilities' },
                { view: 'persistenceDetection', label: 'Persistence Detection', icon: <SearchIcon size={20} />, permission: 'view:persistence' },
                { view: 'securitySimulation', label: 'Simulation', icon: <BombIcon size={20} />, permission: 'view:security' },
                { view: 'securityAudit', label: 'Security Audit', icon: <FileTextIcon size={20} />, permission: 'view:security_audit' },
                { view: 'runtimeSecurity', label: 'Runtime Security', icon: <ShieldZapIcon size={20} />, permission: 'view:security' },
                { view: 'pam', label: 'Privileged Access (PAM)', icon: <Lock size={20} />, permission: 'manage:settings' },
                { view: 'advancedHunting', label: 'Advanced KQL Hunting', icon: <SearchIcon size={20} />, permission: 'view:advanced_hunting' },
                { view: 'detectionRules', label: 'Detection Rules', icon: <ShieldIcon size={20} />, permission: 'view:detection_rules' },
                { view: 'connectorsHub', label: 'Connectors Hub', icon: <Share2Icon size={20} />, permission: 'view:connectors_hub' },
                { view: 'securityCopilot', label: 'Security Copilot', icon: <BotIcon size={20} />, permission: 'view:security_copilot' },
                { view: 'attackTimeline', label: 'Attack Timeline', icon: <ActivityIcon size={20} />, permission: 'view:attack_timeline' },
                { view: 'geographicMap', label: 'Geographic Map', icon: <Globe size={20} />, permission: 'view:geographic_map' },
                { view: 'scaAssessment', label: 'SCA Assessment', icon: <ShieldCheckIcon size={20} />, permission: 'view:sca' },
                { view: 'agentGroups', label: 'Agent Groups', icon: <UsersIcon size={20} />, permission: 'view:agent_groups' },
                { view: 'configDrift', label: 'Config Drift', icon: <ActivityIcon size={20} />, permission: 'view:config_drift' },
                { view: 'fimMonitoring', label: 'FIM', icon: <ShieldCheckIcon size={20} />, permission: 'view:fim' },
                { view: 'activeResponse', label: 'Active Response', icon: <ActivityIcon size={20} />, permission: 'view:active_response' },
            ]
        },

        {
            title: "DevSecOps & Engineering",
            items: [
                { view: 'k8sSecurity', label: 'Kubernetes Security', icon: <ShieldCheckIcon size={20} />, permission: 'view:security' },
                { view: 'apiSecurity', label: 'API Security', icon: <NetworkIcon size={20} />, permission: 'view:security' },
                { view: 'databaseMonitoring', label: 'Database Monitor (DAM)', icon: <DatabaseIcon size={20} />, permission: 'view:security' },
                { view: 'supplyChain', label: 'Supply Chain Security', icon: <ShieldCheckIcon size={20} />, permission: 'view:devsecops' },
                { view: 'devsecops', label: 'DevSecOps', icon: <GitPullRequestDraftIcon size={20} />, permission: 'view:devsecops' },
                { view: 'doraMetrics', label: 'DORA Metrics', icon: <GaugeIcon size={20} />, permission: 'view:dora_metrics' },
                { view: 'sbom', label: 'SBOM', icon: <FileCodeIcon size={20} />, permission: 'view:sbom' },
                { view: 'sast', label: 'SAST', icon: <SearchIcon size={20} />, permission: 'view:security' },
                { view: 'codeReviewGraph', label: 'Code Review Graph', icon: <GitPullRequestDraftIcon size={20} />, permission: 'view:devsecops' },
                { view: 'pipelineSecurity', label: 'Pipeline Security', icon: <ShieldCheckIcon size={20} />, permission: 'view:devsecops' },
                { view: 'iacSecurity', label: 'IaC Security', icon: <FileCodeIcon size={20} />, permission: 'view:devsecops' },
                { view: 'containerScan', label: 'Container Scanning', icon: <BoxIcon size={20} />, permission: 'view:devsecops' },
                { view: 'apiExtensions', label: 'API Extensions (MCP/OCSF)', icon: <ComponentIcon size={20} />, permission: 'view:devsecops' },
                { view: 'chaosEngineering', label: 'Chaos Engineering', icon: <BombIcon size={20} />, permission: 'view:chaos', minTier: 'Enterprise', featureKey: 'chaos_engineering' },
                { view: 'developer_hub', label: 'Developer Hub', icon: <BookKeyIcon size={20} />, permission: 'view:developer_hub' },
                { view: 'mlops', label: 'MLOps', icon: <WorkflowIcon size={20} />, permission: 'view:mlops', minTier: 'Enterprise', featureKey: 'mlops' },
                { view: 'modelMonitoring', label: 'Model Monitoring', icon: <Radar size={20} />, permission: 'view:mlops', minTier: 'Enterprise', featureKey: 'mlops' },
                { view: 'llmops', label: 'LLMOps', icon: <BotIcon size={20} />, permission: 'view:llmops', minTier: 'Enterprise', featureKey: 'llmops' },
                { view: 'automl', label: 'AutoML', icon: <LightbulbIcon size={20} />, permission: 'view:automl', minTier: 'Enterprise', featureKey: 'automl' },
                { view: 'abTesting', label: 'A/B Testing', icon: <GitMergeIcon size={20} />, permission: 'manage:experiments' },
                { view: 'xai', label: 'AI Explainability', icon: <DnaIcon size={20} />, permission: 'view:xai' },
            ]
        },
        {
            title: "Governance & Compliance",
            items: [
                { view: 'compliance', label: 'Compliance', icon: <ShieldCheckIcon size={20} />, permission: 'view:compliance' },
                { view: 'programs', label: 'Programs', icon: <ClipboardListIcon size={20} />, permission: 'view:compliance' },
                { view: 'auditProgram', label: 'Audit Programs', icon: <ClipboardCheck size={20} />, permission: 'view:compliance' },
                { view: 'accessReview', label: 'Access Reviews', icon: <UserCheck size={20} />, permission: 'view:compliance' },
                { view: 'cookieConsent', label: 'Cookie Consent', icon: <Cookie size={20} />, permission: 'view:compliance' },
                { view: 'maturityScore', label: 'Maturity Score', icon: <BarChart2 size={20} />, permission: 'view:compliance' },
                { view: 'complianceEvidence', label: 'Evidence Collector', icon: <ShieldCheckIcon size={20} />, permission: 'view:compliance' },
                { view: 'saasIntegrations', label: 'SaaS Evidence Integrations', icon: <UploadCloudIcon size={20} />, permission: 'view:compliance' },
                { view: 'remediationWorkflow', label: 'Remediation', icon: <ShieldAlertIcon size={20} />, permission: 'view:compliance' },
                { view: 'complianceFrameworks', label: 'Framework Evaluator', icon: <ClipboardListIcon size={20} />, permission: 'view:compliance' },
                { view: 'customFrameworks', label: 'Custom Frameworks', icon: <ClipboardListIcon size={20} />, permission: 'view:compliance' },
                { view: 'complianceOracle', label: 'Compliance Oracle', icon: <BotIcon size={20} />, permission: 'view:compliance' },
                { view: 'cissporacle', label: 'CISSP Oracle', icon: <ShieldCheckIcon size={20} />, permission: 'view:compliance', minTier: 'Enterprise', featureKey: 'cissp_oracle' },
                { view: 'privacy', label: 'Privacy (GDPR/CCPA)', icon: <ShieldLockIcon size={20} />, permission: 'view:compliance' },
                { view: 'privacyLegal', label: 'Privacy & Legal (TIA/LIA)', icon: <GavelIcon size={20} />, permission: 'view:compliance' },
                { view: 'riskRegister', label: 'Risk Register', icon: <ShieldAlertIcon size={20} />, permission: 'view:compliance' },
                { view: 'vendorManagement', label: 'Vendor Mgmt', icon: <UsersIcon size={20} />, permission: 'view:compliance' },
                { view: 'trustCenter', label: 'Trust Center', icon: <Globe size={20} />, permission: 'view:compliance' },
                { view: 'secureFileShare', label: 'Secure Share', icon: <Lock size={20} />, permission: 'manage:compliance_evidence' },
                { view: 'securityTraining', label: 'Training', icon: <BookKeyIcon size={20} />, permission: 'view:compliance' },
                { view: 'aiGovernance', label: 'AI Governance', icon: <BotIcon size={20} />, permission: 'view:ai_governance' },
                { view: 'dataGovernance', label: 'Data Governance', icon: <ShieldCheckIcon size={20} />, permission: 'view:governance' },
                { view: 'auditLog', label: 'Audit Log', icon: <ClipboardListIcon size={20} />, permission: 'view:audit_log' },
                { view: 'approvalWorkflows', label: 'Approvals', icon: <ClipboardListIcon size={20} />, permission: 'view:ai_governance' },
                { view: 'baaManagement', label: 'BAA Management', icon: <FileTextIcon size={20} />, permission: 'view:compliance' },
            ]
        },
        {
            title: "Automation & Intelligence",
            items: [
                { view: 'automation', label: 'Automation', icon: <WorkflowIcon size={20} />, permission: 'view:automation' },
                { view: 'notificationsRouting', label: 'Notifications & Domain Scanner', icon: <BellIcon size={20} />, permission: 'view:automation' },
                { view: 'playbooks', label: 'Playbooks', icon: <BookKeyIcon size={20} />, permission: 'manage:playbooks' },
                { view: 'soar', label: 'SOAR Executions', icon: <ZapIcon size={20} />, permission: 'manage:playbooks' },
                { view: 'jitAccess', label: 'JIT Privileged Access', icon: <Lock size={20} />, permission: 'manage:settings' },
                { view: 'conditionalAccess', label: 'Conditional Access', icon: <ShieldCheckIcon size={20} />, permission: 'view:conditional_access' },
                { view: 'scheduledReports', label: 'Scheduled Reports', icon: <ClipboardListIcon size={20} />, permission: 'view:reporting' },
                { view: 'swarm', label: 'Autonomous Swarms', icon: <WorkflowIcon size={20} />, permission: 'view:swarm', minTier: 'Pro', featureKey: 'swarm' },
                { view: 'agentApproval', label: 'Agent Approvals', icon: <ShieldCheckIcon size={20} />, permission: 'view:agents' },
                { view: 'aiRemediation', label: 'AI Remediation', icon: <ZapIcon size={20} />, permission: 'view:ai_governance' },
                { view: 'rollback', label: 'Rollback & Checkpoints', icon: <ActivityIcon size={20} />, permission: 'manage:settings' },
                { view: 'tasks', label: 'My Tasks', icon: <ClipboardListIcon size={20} />, permission: 'view:profile' },
                { view: 'internalTickets', label: 'Tickets', icon: <ClipboardListIcon size={20} />, permission: 'view:dashboard', featureKey: 'tickets' },
                { view: 'problemManagement', label: 'Problem Management', icon: <AlertOctagonIcon size={20} />, permission: 'view:security' },
                { view: 'changeManagement', label: 'Change Management', icon: <WorkflowIcon size={20} />, permission: 'manage:settings' },
                /* Support Chat merged into 'chat' tab hub */
            ]
        },
        {
            title: "Management & Settings",
            items: [
                { view: 'finops', label: 'FinOps & Billing', icon: <DollarSignIcon size={20} />, permission: 'view:finops' },
                { view: 'servicePricing', label: 'Service Pricing', icon: <DollarSignIcon size={20} />, permission: 'manage:pricing' },
                { view: 'paymentSettings', label: 'Payment Settings', icon: <CreditCard size={20} />, permission: 'manage:settings' },
                { view: 'subscriptionManagement', label: 'Subscription Plan', icon: <TrendingUp size={20} />, permission: 'view:dashboard' },
                { view: 'invoices', label: 'Invoices', icon: <FileText size={20} />, permission: 'view:dashboard' },
                { view: 'cloudIntegrations', label: 'Cloud Integrations', icon: <CloudShieldIcon size={20} />, permission: 'manage:settings' },
                { view: 'secretsManagement', label: 'Secrets Management', icon: <Lock size={20} />, permission: 'manage:settings' },
                { view: 'hadr', label: 'HA/DR & Backups', icon: <ShieldCheckIcon size={20} />, permission: 'manage:settings', minTier: 'Enterprise', featureKey: 'hadr' },
                { view: 'retentionPolicy', label: 'Data Retention', icon: <ClipboardListIcon size={20} />, permission: 'manage:settings' },
                { view: 'retentionPolicies', label: 'Retention Tiers', icon: <DatabaseIcon size={20} />, permission: 'view:retention_policies' },
                { view: 'msspMonitoring', label: 'MSSP Monitoring', icon: <BuildingIcon size={20} />, permission: 'view:mssp' },
                { view: 'knowledgeBase', label: 'Knowledge Base (RAG)', icon: <BookKeyIcon size={20} />, permission: 'view:dashboard' },
                { view: 'systemHealth', label: 'System Health', icon: <ActivityIcon size={20} />, permission: 'manage:settings' },
                { view: 'apiStatus', label: 'API Status', icon: <RadioTower size={20} />, permission: 'manage:settings' },
                { view: 'settings', label: 'Settings', icon: <SettingsIcon size={20} />, permission: 'manage:settings' },
                { view: 'tenantManagement', label: 'Tenants', icon: <BuildingIcon size={20} />, permission: 'manage:tenants' },
                { view: 'bundleManagement', label: 'Feature Bundles', icon: <PuzzleIcon size={20} />, permission: 'manage:tenants' },
                { view: 'webhooks', label: 'Webhooks', icon: <Share2Icon size={20} />, permission: 'manage:settings' },
                { view: 'ticketing', label: 'Ticketing Integration', icon: <Share2Icon size={20} />, permission: 'manage:settings' },
                { view: 'ticketWebhooks', label: 'Ticket Webhooks', icon: <Share2Icon size={20} />, permission: 'manage:settings' },
                { view: 'notificationPrefs', label: 'Notification Prefs', icon: <SettingsIcon size={20} />, permission: 'view:profile' },
                { view: 'dataWarehouse', label: 'Data Warehouse', icon: <DatabaseIcon size={20} />, permission: 'view:reporting' },
            ]
        }
    ], []);

    const visibleGroups = useMemo(() => {
        const isSuperAdmin = currentUser?.role === 'Super Admin' || currentUser?.role === 'superadmin' || currentUser?.role === 'super_admin';
        const userTier: string = (currentUser as any)?.subscriptionTier || 'Free';

        return navGroups
            .map(group => ({
                ...group,
                items: group.items
                    .filter(item => {
                        if (isViewingTenant && item.permission === 'manage:tenants') return false;
                        if (isSuperAdmin) return true;
                        if (!hasPermission(item.permission)) return false;
                        // Bundle mode: hide items whose feature the tenant hasn't been assigned
                        if (isBundleMode && item.featureKey && !hasFeature(item.featureKey)) return false;
                        return true;
                    })
                    .map(item => {
                        if (isSuperAdmin) return { ...item, locked: undefined };
                        const serverMinTier = item.featureKey ? serverLockedFeatures[item.featureKey] : undefined;
                        const clientLocked = item.minTier && !tierMeetsMin(userTier, item.minTier);
                        const locked = serverMinTier || (clientLocked ? item.minTier : undefined);
                        return { ...item, locked };
                    }),
            }))
            .filter(group => group.items.length > 0);
    }, [navGroups, isViewingTenant, currentUser, hasPermission, serverLockedFeatures, isBundleMode, hasFeature]);

    return (
        <aside className={`flex-shrink-0 glass border-r-0 flex flex-col transition-all duration-300 ease-in-out z-40 ${isOpen ? 'w-64' : 'w-20'} `} >
            {/* Logo Section */}
            <div className="flex items-center justify-center h-16 border-b border-white/5 bg-transparent" >
                {
                    branding?.logoUrl ? (
                        <img src={branding.logoUrl} alt="Logo" className="h-8 w-auto" />
                    ) : (
                        <div className="bg-gradient-to-tr from-primary-500 to-primary-700 p-1.5 rounded-lg shadow-lg shadow-primary-500/20">
                            <BotIcon className="text-white" size={24} />
                        </div>
                    )}
                {
                    isOpen && (
                        <div className="ml-3 flex flex-col justify-center">
                            <span className="font-bold text-gray-900 dark:text-gray-100 leading-tight">
                                {branding?.companyName || 'Genesis'}
                            </span>
                            <span className="text-[10px] text-gray-500 dark:text-gray-400 font-medium tracking-wider">
                                AI PLATFORM
                            </span>
                        </div>
                    )
                }
            </div>

            {/* Navigation Section */}
            <nav className="flex-1 overflow-y-auto overflow-x-hidden scrollbar-thin scrollbar-thumb-gray-200 dark:scrollbar-thumb-gray-800 p-3 space-y-6" >

                {/* Back to Tenants Link */}
                {
                    (currentUser?.role === 'Super Admin' || currentUser?.role === 'superadmin' || currentUser?.role === 'super_admin') && isViewingTenant && (
                        <div className="mb-2">
                            <button
                                onClick={onBackToTenants}
                                className={`w-full flex items-center px-3 py-2.5 text-sm font-medium rounded-lg
bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400
hover:bg-amber-100 dark:hover:bg-amber-900/30 transition-colors border border-amber-200 dark:border-amber-900/30
                            ${!isOpen && 'justify-center'} `}
                                title="Back to Tenant List"
                            >
                                <ArrowLeftIcon size={18} />
                                {isOpen && <span className="ml-3">Back to Tenants</span>}
                            </button>
                        </div>
                    )
                }

                {/* Navigation Groups */}
                {
                    visibleGroups.map((group, groupIndex) => (
                        <SidebarGroup
                            key={group.title}
                            group={group}
                            groupIndex={groupIndex}
                            isOpen={isOpen}
                            currentView={currentView}
                            setCurrentView={setCurrentView}
                            expandedGroup={expandedGroup}
                            setExpandedGroup={setExpandedGroup}
                            badgeCounts={{ chat: supportUnread + endpointUnread }}
                        />
                    ))
                }
            </nav>

            {/* User Profile / Footer Section */}
            <div className="p-3 border-t border-white/5 bg-transparent" >
                {branding?.companyName && isOpen && (
                    <div className="text-xs text-center text-gray-400 dark:text-gray-600">
                        © 2024 {branding.companyName}
                    </div>
                )}
            </div>
        </aside>
    );
};
