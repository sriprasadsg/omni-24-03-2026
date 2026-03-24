import React, { useMemo, useState, useEffect, useRef } from 'react';
import { BotIcon, DashboardIcon, ShieldCheckIcon, ServerIcon, DatabaseIcon, ShieldAlertIcon, ShieldZapIcon, BarChart3Icon, SettingsIcon, BuildingIcon, ArrowLeftIcon, CloudShieldIcon, DollarSignIcon, ClipboardListIcon, FileTextIcon, UsersIcon, WorkflowIcon, GitPullRequestDraftIcon, BookKeyIcon, LightbulbIcon, GitMergeIcon, DnaIcon, NetworkIcon, PuzzleIcon, GaugeIcon, BombIcon, SunIcon, ShieldLockIcon, Share2Icon, ActivityIcon, BoxIcon, TerminalSquareIcon, FileCodeIcon, SearchIcon, ZapIcon, CrownIcon } from './icons';
import { CreditCard, TrendingUp, FileText, Globe, Lock, UserIcon, ChevronDown, ShieldIcon, TargetIcon, AlertOctagonIcon } from 'lucide-react';
import { AppView, Permission } from '../types';
import { useUser } from '../contexts/UserContext';

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
}

interface NavGroup {
    title: string;
    items: NavItem[];
}

const NavLink: React.FC<{ icon: React.ReactNode; label: string; active?: boolean; onClick: () => void; disabled?: boolean; isOpen: boolean }> = ({ icon, label, active, onClick, disabled, isOpen }) => (
    <button
        onClick={onClick}
        disabled={disabled}
        className={`w-full flex items-center px-3 py-2 text-sm font-medium rounded-lg transition-all duration-200 relative group ${active
            ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400'
            : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5 hover:text-gray-900 dark:hover:text-gray-200'
            } ${disabled ? 'opacity-50 cursor-not-allowed' : ''} `}
        title={!isOpen ? label : undefined}
    >
        <div className={`flex-shrink-0 transition-colors duration-200 ${active ? 'text-primary-600 dark:text-primary-400' : 'text-gray-500 dark:text-gray-500 group-hover:text-gray-700 dark:group-hover:text-gray-300'} `}>
            {icon}
        </div>

        {isOpen && (
            <span className="ml-3 truncate flex-1 text-left">{label}</span>
        )}

        {active && (
            <div className={`absolute left-0 w-1 h-5 bg-primary-500 rounded-r-full -ml-3`} />
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
}> = ({ group, groupIndex, isOpen, currentView, setCurrentView, expandedGroup, setExpandedGroup }) => {
    const isExpanded = expandedGroup === group.title;
    const hasActiveItem = group.items.some(i => i.view === currentView);
    const contentRef = useRef<HTMLDivElement>(null);

    // Auto-expand when this group contains the active view
    useEffect(() => {
        if (hasActiveItem) setExpandedGroup(group.title);
    }, [currentView]); // eslint-disable-line react-hooks/exhaustive-deps

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

    // ── Accordion state: which group header is currently open ──────────────
    const [expandedGroup, setExpandedGroup] = useState<string | null>(null);

    const navGroups: NavGroup[] = useMemo(() => [
        {
            title: "Dashboards & Insights",
            items: [
                { view: 'dashboard', label: 'Overview', icon: <DashboardIcon size={20} />, permission: 'view:dashboard' },
                { view: 'cxo', label: 'CXO Insights', icon: <CrownIcon size={20} />, permission: 'view:cxo_dashboard' },
                { view: 'unifiedOps', label: 'Unified Future Ops', icon: <DashboardIcon size={20} />, permission: 'view:unified_ops' },
                { view: 'proactiveInsights', label: 'Proactive Insights', icon: <LightbulbIcon size={20} />, permission: 'view:insights' },
                { view: 'reporting', label: 'Reporting', icon: <BarChart3Icon size={20} />, permission: 'view:reporting' },
                { view: 'advancedBi', label: 'Advanced BI', icon: <BarChart3Icon size={20} />, permission: 'view:advanced_bi' },
                { view: 'digitalTwin', label: 'Digital Twin', icon: <BoxIcon size={20} />, permission: 'view:dashboard' },
                { view: 'sustainability', label: 'Sustainability', icon: <SunIcon size={20} />, permission: 'view:sustainability' },
            ]
        },
        {
            title: "Observability",
            items: [
                { view: 'distributedTracing', label: 'Distributed Tracing', icon: <GitMergeIcon size={20} />, permission: 'view:tracing' },
                { view: 'logExplorer', label: 'Log Explorer', icon: <FileTextIcon size={20} />, permission: 'view:logs' },
                { view: 'networkObservability', label: 'Network', icon: <NetworkIcon size={20} />, permission: 'view:network' },
                { view: 'dataUtilization', label: 'Data Utilization', icon: <ActivityIcon size={20} />, permission: 'view:network' },
                { view: 'webMonitoring', label: 'Web Monitoring', icon: <Globe size={20} />, permission: 'view:web_monitoring' },
                { view: 'serviceMesh', label: 'Service Mesh', icon: <NetworkIcon size={20} />, permission: 'view:network' },
                { view: 'streaming', label: 'Streaming Analytics', icon: <ActivityIcon size={20} />, permission: 'view:analytics' },
                { view: 'systemHealth', label: 'System Health', icon: <ActivityIcon size={20} />, permission: 'manage:settings' },
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
                { view: 'serviceCatalog', label: 'Service Catalog (IDP)', icon: <PuzzleIcon size={20} />, permission: 'view:service_catalog' },
                { view: 'jobs', label: 'Jobs', icon: <ClipboardListIcon size={20} />, permission: 'view:jobs' },
            ]
        },
        {
            title: "Security (SecOps)",
            items: [
                { view: 'security', label: 'Security Overview', icon: <ShieldZapIcon size={20} />, permission: 'view:security' },
                { view: 'edr', label: 'EDR (Real-Time)', icon: <ShieldZapIcon size={20} />, permission: 'view:security' },
                { view: 'mitreAttack', label: 'MITRE ATT&CK', icon: <NetworkIcon size={20} />, permission: 'view:security' },
                { view: 'dlp', label: 'Data Loss Prevention', icon: <ShieldLockIcon size={20} />, permission: 'view:security' },
                { view: 'cloudSecurity', label: 'Cloud Security', icon: <CloudShieldIcon size={20} />, permission: 'view:cloud_security' },
                { view: 'threatHunting', label: 'Threat Hunting', icon: <SearchIcon size={20} />, permission: 'view:threat_hunting' },
                { view: 'siem', label: 'SIEM Dashboard (OCSF)', icon: <ShieldZapIcon size={20} />, permission: 'view:security' },
                { view: 'playbooks', label: 'SOAR Playbooks', icon: <TerminalSquareIcon size={20} />, permission: 'manage:settings' },
                { view: 'threatIntelligence', label: 'Threat Intelligence', icon: <TargetIcon size={20} />, permission: 'view:threat_intel' },
                { view: 'siemRules', label: 'SIEM Correlation Rules', icon: <ShieldIcon size={20} />, permission: 'view:security' },
                { view: 'incidentResponse', label: 'Incident Response', icon: <AlertOctagonIcon size={20} />, permission: 'investigate:security' },
                { view: 'ueba', label: 'UEBA (Insider Threats)', icon: <UserIcon size={20} />, permission: 'view:security' },
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
            ]
        },

        {
            title: "DevSecOps & Engineering",
            items: [
                { view: 'devsecops', label: 'DevSecOps', icon: <GitPullRequestDraftIcon size={20} />, permission: 'view:devsecops' },
                { view: 'doraMetrics', label: 'DORA Metrics', icon: <GaugeIcon size={20} />, permission: 'view:dora_metrics' },
                { view: 'sbom', label: 'SBOM', icon: <FileCodeIcon size={20} />, permission: 'view:sbom' },
                { view: 'chaosEngineering', label: 'Chaos Engineering', icon: <BombIcon size={20} />, permission: 'view:chaos' },
                { view: 'developer_hub', label: 'Developer Hub', icon: <BookKeyIcon size={20} />, permission: 'view:developer_hub' },
                { view: 'mlops', label: 'MLOps', icon: <WorkflowIcon size={20} />, permission: 'view:mlops' },
                { view: 'llmops', label: 'LLMOps', icon: <BotIcon size={20} />, permission: 'view:llmops' },
                { view: 'automl', label: 'AutoML', icon: <LightbulbIcon size={20} />, permission: 'view:automl' },
                { view: 'abTesting', label: 'A/B Testing', icon: <GitMergeIcon size={20} />, permission: 'manage:experiments' },
                { view: 'xai', label: 'AI Explainability', icon: <DnaIcon size={20} />, permission: 'view:xai' },
            ]
        },
        {
            title: "Governance & Compliance",
            items: [
                { view: 'compliance', label: 'Compliance', icon: <ShieldCheckIcon size={20} />, permission: 'view:compliance' },
                { view: 'complianceOracle', label: 'Compliance Oracle', icon: <BotIcon size={20} />, permission: 'view:compliance' },
                { view: 'cissporacle', label: 'CISSP Oracle', icon: <ShieldCheckIcon size={20} />, permission: 'view:compliance' },
                { view: 'riskRegister', label: 'Risk Register', icon: <ShieldAlertIcon size={20} />, permission: 'view:compliance' },
                { view: 'vendorManagement', label: 'Vendor Mgmt', icon: <UsersIcon size={20} />, permission: 'view:compliance' },
                { view: 'trustCenter', label: 'Trust Center', icon: <Globe size={20} />, permission: 'view:compliance' },
                { view: 'secureFileShare', label: 'Secure Share', icon: <Lock size={20} />, permission: 'manage:compliance_evidence' },
                { view: 'securityTraining', label: 'Training', icon: <BookKeyIcon size={20} />, permission: 'view:compliance' },
                { view: 'aiGovernance', label: 'AI Governance', icon: <BotIcon size={20} />, permission: 'view:ai_governance' },
                { view: 'dataGovernance', label: 'Data Governance', icon: <ShieldCheckIcon size={20} />, permission: 'view:governance' },
                { view: 'auditLog', label: 'Audit Log', icon: <ClipboardListIcon size={20} />, permission: 'view:audit_log' },
                { view: 'approvalWorkflows', label: 'Approvals', icon: <ClipboardListIcon size={20} />, permission: 'view:ai_governance' },
            ]
        },
        {
            title: "Automation & Intelligence",
            items: [
                { view: 'automation', label: 'Automation', icon: <WorkflowIcon size={20} />, permission: 'view:automation' },
                { view: 'playbooks', label: 'Playbooks', icon: <BookKeyIcon size={20} />, permission: 'manage:playbooks' },
                { view: 'swarm', label: 'Autonomous Swarms', icon: <WorkflowIcon size={20} />, permission: 'view:swarm' },
                { view: 'tasks', label: 'My Tasks', icon: <ClipboardListIcon size={20} />, permission: 'view:profile' },
            ]
        },
        {
            title: "Management & Settings",
            items: [
                { view: 'finops', label: 'FinOps & Billing', icon: <DollarSignIcon size={20} />, permission: 'view:finops' },
                { view: 'servicePricing', label: 'Service Pricing', icon: <DollarSignIcon size={20} />, permission: 'manage:settings' },
                { view: 'paymentSettings', label: 'Payment Settings', icon: <CreditCard size={20} />, permission: 'manage:settings' },
                { view: 'subscriptionManagement', label: 'Subscription & Billing', icon: <TrendingUp size={20} />, permission: 'view:dashboard' },
                { view: 'invoices', label: 'Invoices', icon: <FileText size={20} />, permission: 'view:dashboard' },
                { view: 'systemHealth', label: 'System Health', icon: <ActivityIcon size={20} />, permission: 'manage:settings' },
                { view: 'settings', label: 'Settings', icon: <SettingsIcon size={20} />, permission: 'manage:settings' },
                { view: 'tenantManagement', label: 'Tenants', icon: <BuildingIcon size={20} />, permission: 'manage:tenants' },
                { view: 'webhooks', label: 'Webhooks', icon: <Share2Icon size={20} />, permission: 'manage:settings' },
                { view: 'ticketing', label: 'Ticketing Integration', icon: <Share2Icon size={20} />, permission: 'manage:settings' },
                { view: 'dataWarehouse', label: 'Data Warehouse', icon: <DatabaseIcon size={20} />, permission: 'view:reporting' },
            ]
        }
    ], []);

    const visibleGroups = useMemo(() => {
        const isSuperAdmin = currentUser?.role === 'Super Admin' || currentUser?.role === 'superadmin' || currentUser?.role === 'super_admin';

        return navGroups
            .filter(group => isSuperAdmin || group.title !== "Management & Settings")
            .map(group => ({
                ...group,
                items: group.items.filter(item => {
                    if (isViewingTenant && item.permission === 'manage:tenants') return false;

                    // Super Admin sees everything
                    if (isSuperAdmin) {
                        return true;
                    }

                    return hasPermission(item.permission);
                })
            }))
            .filter(group => group.items.length > 0);
    }, [navGroups, isViewingTenant, currentUser, hasPermission]);

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
