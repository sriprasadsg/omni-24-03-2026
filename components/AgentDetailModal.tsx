import React, { useState } from 'react';
import { Agent, AgentPlatform, AgentStatus, AgentCapability, Asset, VulnerabilitySeverity, Tenant } from '../types';
import { XIcon, ServerIcon, CheckIcon, XCircleIcon, AlertCircleIcon, LinuxIcon, WindowsIcon, DockerIcon, KubernetesIcon, BarChart3Icon, ShieldSearchIcon, ShieldIcon, FileTextIcon, FileShieldIcon, ShieldCheckIcon, ShieldZapIcon, CogIcon, LightbulbIcon, UsersIcon, ComponentIcon, GitMergeIcon, HistoryIcon, ShieldAlertIcon, TerminalSquareIcon, ArrowRightIcon, ZapIcon, SearchIcon, NetworkIcon, CloudShieldIcon, GlobeIcon, EyeIcon, BotIcon, PackageCheckIcon, BoxIcon, TestTubeIcon, ActivityIcon, SendIcon, RadarIcon, BinocularsIcon, ClipboardCheckIcon, HeartHandshakeIcon, DownloadIcon, WorkflowIcon, BrainCircuitIcon, RefreshCwIcon, DatabaseIcon, HardDriveIcon } from './icons';
import { useUser } from '../contexts/UserContext';
import { useTimeZone } from '../contexts/TimeZoneContext';
import { RuntimeSecurityTab } from './RuntimeSecurityTab';
import { AgentComplianceTab, ComplianceData, ComplianceRule } from './AgentComplianceTab';
import { PredictiveHealthTab } from './PredictiveHealthTab';
import { AgentOverviewTab } from './AgentOverviewTab';
import { AgentSoftwareTab } from './AgentSoftwareTab';
import { AgentPatchingTab } from './AgentPatchingTab';
import { ConfirmationModal } from './ConfirmationModal';
import { moveAgent, fetchTenants, fetchAssetCompliance, runAgentComplianceScan, fetchAssets } from '../services/apiService';
import { showToast } from '../utils/toast';


interface AgentDetailModalProps {
    isOpen: boolean;
    onClose: () => void;
    agent: Agent | null;
    asset?: Asset;
    onManageCapabilities: (agent: Agent) => void;
    onViewRemediationLogs: (agent: Agent) => void;
    onViewLogs: (agent: Agent) => void;
    onRunDiagnostics?: (agent: Agent) => void;
    onDeleteAgent?: (agent: Agent) => void;
    onRefresh?: () => void;
    isRefreshing?: boolean;
}

function formatRelativeTime(date: Date): string {
    const secs = Math.floor((Date.now() - date.getTime()) / 1000);
    if (secs < 5) return 'just now';
    if (secs < 60) return `${secs}s ago`;
    return `${Math.floor(secs / 60)}m ago`;
}

const statusInfo: Record<AgentStatus, { icon: React.ReactNode; textClass: string; }> = {
    Online: { icon: <CheckIcon size={16} />, textClass: 'text-green-600 dark:text-green-400' },
    Offline: { icon: <XCircleIcon size={16} />, textClass: 'text-gray-500' },
    Error: { icon: <AlertCircleIcon size={16} />, textClass: 'text-red-600 dark:text-red-400' },
    Quarantined: { icon: <ShieldIcon size={16} />, textClass: 'text-amber-600 dark:text-amber-400' },
};

const platformIcons: Record<AgentPlatform, React.ReactNode> = {
    Linux: <LinuxIcon size={20} className="text-gray-500 dark:text-gray-400" />,
    Windows: <WindowsIcon size={20} className="text-blue-500" />,
    macOS: <ServerIcon size={20} className="text-gray-500 dark:text-gray-400" />,
    Docker: <DockerIcon size={20} className="text-sky-600" />,
    Kubernetes: <KubernetesIcon size={20} className="text-indigo-500" />,
    'AWS EC2': <ServerIcon size={20} className="text-orange-500" />,
};

const capabilityInfo: Record<AgentCapability, { icon: React.ReactNode; label: string; }> = {
    // Core telemetry
    metrics_collection: { icon: <BarChart3Icon size={16} />,  label: 'Metric Collection' },
    log_collection:     { icon: <FileTextIcon size={16} />,   label: 'Log Collection' },
    process_monitor:    { icon: <ActivityIcon size={16} />,   label: 'Process Monitor' },
    log_shipper:        { icon: <SendIcon size={16} />,        label: 'Log Shipper' },
    // Security detection
    vulnerability_scanning:       { icon: <ShieldSearchIcon size={16} />, label: 'Vulnerability Scanning' },
    fim:                           { icon: <FileShieldIcon size={16} />,   label: 'File Integrity Monitoring' },
    real_time_fim:                 { icon: <RadarIcon size={16} />,        label: 'Real-Time FIM' },
    compliance_enforcement:        { icon: <ShieldCheckIcon size={16} />,  label: 'Compliance Enforcement' },
    runtime_security:              { icon: <ShieldZapIcon size={16} />,    label: 'Runtime Security (XDR)' },
    edr_realtime:                  { icon: <ZapIcon size={16} />,          label: 'EDR Real-Time' },
    persistence_detection:         { icon: <SearchIcon size={16} />,       label: 'Persistence Detection' },
    deception_monitor:             { icon: <BinocularsIcon size={16} />,   label: 'Deception Monitor' },
    // Network & cloud
    network_discovery: { icon: <NetworkIcon size={16} />,        label: 'Network Discovery' },
    cloud_metadata:    { icon: <CloudShieldIcon size={16} />,    label: 'Cloud Metadata Collector' },
    web_monitor:       { icon: <GlobeIcon size={16} />,           label: 'Web Monitor' },
    remote_access:     { icon: <TerminalSquareIcon size={16} />, label: 'Remote Access' },
    // Data & privacy
    pii_scanner:                   { icon: <EyeIcon size={16} />,            label: 'PII Data Scanner' },
    sbom_analysis:                 { icon: <ComponentIcon size={16} />,      label: 'SBOM Analysis' },
    compliance_evidence_collector: { icon: <ClipboardCheckIcon size={16} />, label: 'Compliance Evidence Collector' },
    vendor_risk:                   { icon: <HeartHandshakeIcon size={16} />, label: 'Vendor Risk Scanner' },
    // Advanced AI
    predictive_health: { icon: <LightbulbIcon size={16} />, label: 'Predictive Health AI' },
    ueba:              { icon: <UsersIcon size={16} />,      label: 'Behavior Analytics (UEBA)' },
    ebpf_tracing:      { icon: <GitMergeIcon size={16} />,  label: 'eBPF Kernel Tracing' },
    shadow_ai:         { icon: <BotIcon size={16} />,        label: 'Shadow AI Detector' },
    // Remediation
    system_patching:              { icon: <PackageCheckIcon size={16} />, label: 'Autonomous Patching' },
    patch_installer:              { icon: <DownloadIcon size={16} />,     label: 'Patch Installer' },
    software_management:          { icon: <BoxIcon size={16} />,          label: 'Software Management' },
    remediation_executor:         { icon: <WorkflowIcon size={16} />,     label: 'Remediation Executor' },
    autonomous_response:          { icon: <BrainCircuitIcon size={16} />, label: 'Autonomous Response' },
    agent_update:                 { icon: <RefreshCwIcon size={16} />,    label: 'Agent Self-Update' },
    vss_manager:                  { icon: <DatabaseIcon size={16} />,     label: 'VSS Manager' },
    backup_verifier:              { icon: <HardDriveIcon size={16} />,    label: 'Backup Verifier' },
    process_injection_simulation: { icon: <TestTubeIcon size={16} />,     label: 'Injection Simulator' },
};

const severityClasses: Record<VulnerabilitySeverity, string> = {
    Critical: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
    High: 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
    Medium: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
    Low: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
    Informational: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
};

const DetailRow: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
    <div className="py-2 sm:grid sm:grid-cols-3 sm:gap-4">
        <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">{label}</dt>
        <dd className="mt-1 text-sm text-gray-900 dark:text-gray-200 sm:mt-0 sm:col-span-2">{children}</dd>
    </div>
);

const REMEDIATION_STEPS: Record<string, string> = {
    // Windows Firewall
    'PCI-1.1.1': 'Enable Windows Firewall for all profiles (Domain, Private, Public) via "WF.msc" or GPO.',
    'CC6.6': 'Ensure host-based firewalls are active and configured to default deny inbound traffic.',

    // Antivirus
    'PCI-5.1': 'Install and enable Windows Defender or a compatible enterprise EDR/Antivirus solution.',
    'CC6.8': 'Ensure anti-malware software is installed, updated, and running.',

    // Password Policy
    'PCI-8.1.1': 'Configure password policy to require at least 12 characters and complexity via Group Policy (secpol.msc).',
    'CC6.1': 'Enforce strong access control and password policies.',

    // RDP
    'PCI-2.2.4': 'Enable Network Level Authentication (NLA) for RDP in System Properties -> Remote.',

    // Encryption
    'PCI-3.4': 'Enable BitLocker Drive Encryption on the system drive using "manage-bde" or Control Panel.',

    // Updates
    'PCI-6.2': 'Enable the Windows Update service and ensure automatic updates are configured.',
    'CC7.3': 'Ensure system patches and updates are applied regularly.',

    // Logging
    'PCI-10.1': 'Enable Audit Logging Policy in Group Policy (Audit Policy -> System Security).',
    'CC9.2': 'Ensure security auditing is enabled to track access and changes.',

    // Network
    'PCI-1.1': 'Close high-risk network ports (e.g., 21, 23, 445) unless explicitly required.',
    'PCI-4.1': 'Disable weak TLS versions (1.0, 1.1) and force TLS 1.2+ via Registry or IIS Crypto.',

    // Linux
    'PCI-2.2.4-ssh': 'Disable SSH Root Login in /etc/ssh/sshd_config (PermitRootLogin no).',
};

// Start of Mapping Modification
const CHECK_NAME_MAPPING: Record<string, string> = {
    'PCI-1.1.1': 'Windows Firewall Profiles',
    'CC6.6': 'Windows Firewall Profiles',
    'PCI-5.1': 'Windows Defender Antivirus',
    'CC6.8': 'Windows Defender Antivirus',
    'PCI-8.1.1': 'Password Policy (Min Length)',
    'PCI-2.2.4': 'RDP NLA Required',
    'PCI-3.4': 'BitLocker Encryption',
    'PCI-6.2': 'Windows Update Service',
    'PCI-10.1': 'Audit Logging Policy',
    'PCI-1.1': 'Risky Network Ports',
    'PCI-4.1': 'TLS Security Config',
    'Guest Account': 'Guest Account Disabled'
};

export const AgentDetailModal: React.FC<AgentDetailModalProps> = ({ isOpen, onClose, agent, asset, onManageCapabilities, onViewRemediationLogs, onViewLogs, onRunDiagnostics, onDeleteAgent, onRefresh, isRefreshing }) => {
    const { hasPermission, currentUser } = useUser();
    const canRemediate = hasPermission('remediate:agents');
    const canTriggerScan = currentUser?.role === 'Super Admin' || currentUser?.role === 'Tenant Admin';
    const { timeZone } = useTimeZone();

    const canViewLogs = hasPermission('view:agent_logs');
    const [activeTab, setActiveTab] = useState<'overview' | 'runtime' | 'compliance' | 'health' | 'software' | 'patching'>('overview');
    const [fetchedComplianceData, setFetchedComplianceData] = useState<ComplianceData | null>(null);
    const [tenantName, setTenantName] = useState<string>('Loading...');

    const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());
    React.useEffect(() => {
        if (agent) setLastRefreshed(new Date());
    }, [agent]);

    React.useEffect(() => {
        if (!isOpen || !onRefresh) return;
        const id = setInterval(onRefresh, 30_000);
        return () => clearInterval(id);
    }, [isOpen, onRefresh]);

    // Clear compliance data whenever a different agent is opened so stale data
    // from the previous agent never shows while the new fetch is in flight.
    React.useEffect(() => {
        setFetchedComplianceData(null);
    }, [agent?.id]);

    React.useEffect(() => {
        if (isOpen && agent) {
            if (currentUser && agent.tenantId === currentUser.tenantId) {
                setTenantName(currentUser.tenantName || agent.tenantId);
            } else {
                setTenantName('Loading...');
                fetchTenants().then(res => {
                    const t = res.find(x => x.id === agent.tenantId);
                    setTenantName(t ? t.name : 'Unknown Tenant');
                }).catch(() => setTenantName('Unknown Tenant'));
            }
        }
    }, [isOpen, agent?.id, currentUser]);

    // Move Agent State
    const [isMoveModalOpen, setIsMoveModalOpen] = useState(false);
    const [isConfirmMoveOpen, setIsConfirmMoveOpen] = useState(false);
    const [targetTenantId, setTargetTenantId] = useState('');
    const [tenants, setTenants] = useState<Tenant[]>([]);
    const [isMoving, setIsMoving] = useState(false);

    const handleOpenMoveModal = async () => {
        setIsMoveModalOpen(true);
        // Fetch tenants dynamically to ensure fresh list
        try {
            const res = await fetchTenants();
            setTenants(res);
        } catch (e) {
            console.error("Failed to fetch tenants", e);
            showToast("Failed to load tenants list. Please try again.", 'error');
        }
    };

    const handleMoveAgent = async () => {
        if (!targetTenantId) return;

        setIsMoving(true);
        try {
            await moveAgent(agent.id, targetTenantId);
            showToast("Agent moved successfully.", 'success');
            setIsMoveModalOpen(false);
            onClose(); // Close main modal as agent might disappear from current view
            window.location.reload(); // Simple reload to refresh all data views
        } catch (e: any) {
            console.error("Move Agent Error:", e);
            showToast(`Failed to move agent: ${e.message || "Unknown error"}`, 'error');
        } finally {
            setIsMoving(false);
        }
    };


    const handleRefreshCompliance = async () => {
        if (!agent?.id) return;
        try {
            console.log("Triggering compliance scan for agent:", agent.id);
            await runAgentComplianceScan(agent.id);
            // Optionally we might want to wait a bit or poll, but for now just triggering re-fetch
            // logic by "faking" a state update or better yet, just calling the fetch logic again.
            // Since the fetch is in useEffect dependent on isOpen/activeTab, we can force a re-fetch
            // But checking the useEffect, it depends on asset.id.
            // Best way: extract fetch logic or just invoke it here.

            // Re-fetch logic (duplicated from useEffect for simplicity in this context)
            const id = asset?.id || agent?.assetId;
            if (id) {
                console.log('Refreshing compliance data for Asset ID:', id);
                await fetchAssetCompliance(id);
                setRefreshTrigger(prev => prev + 1);
            }

        } catch (e) {
            console.error("Failed to refresh compliance:", e);
            showToast("Failed to trigger scan. Check console.", 'error');
        }
    };

    const [refreshTrigger, setRefreshTrigger] = useState(0);

    // Single compliance-fetch effect. Depends on refreshTrigger so manual refresh works.
    // Falls back to deriving assetId from hostname (matches backend's "asset-{hostname}" convention)
    // when agent.assetId is not yet populated (e.g. agent registered but hasn't heartbeated yet).
    React.useEffect(() => {
        const derivedId = asset?.id || agent?.assetId || (agent?.hostname ? `asset-${agent.hostname}` : undefined);
        if (isOpen && activeTab === 'compliance' && derivedId) {
            const id = derivedId;
            console.log('DEBUG: Fetching compliance for Asset ID:', id);

            if (id) {
                fetchAssetCompliance(id).then(rawData => {
                    // Transform raw API data (List of MongoDB docs) to ComplianceData format expected by Tab
                    if (Array.isArray(rawData) && rawData.length > 0) {
                        const rules = rawData.map((item: any) => {
                            // Extract status
                            let status: 'passed' | 'failed' | 'warning' = 'warning';
                            if (item.status === 'Compliant') status = 'passed';
                            if (item.status === 'Non-Compliant') status = 'failed';
                            if (item.status === 'Warning') status = 'warning';

                            // Extract Title from first evidence item if possible
                            const evidenceItem = item.evidence && item.evidence[0];
                            const title = evidenceItem?.name || item.controlId;
                            const category = (typeof item.controlId === 'string' ? item.controlId.split('-')[0] : 'General') || 'General';

                            // Determine Remediation
                            let remediation = undefined;
                            if (status === 'failed') {
                                remediation = REMEDIATION_STEPS[item.controlId];
                                // Heuristic fallback if direct ID match fails but title implies something
                                if (!remediation && title.includes('Firewall')) remediation = REMEDIATION_STEPS['PCI-1.1.1'];
                                if (!remediation && title.includes('Defender')) remediation = REMEDIATION_STEPS['PCI-5.1'];
                                if (!remediation && title.includes('Password')) remediation = REMEDIATION_STEPS['PCI-8.1.1'];
                            }

                            // Extract Check Name for Auto-Fix
                            // Priority 1: Direct field from backend (newly added)
                            // Priority 2: Explicit Mapping from ID
                            // Priority 3: Parse from Evidence Name "System Check: [Name]"
                            let checkNameRaw = item.checkName;

                            if (!checkNameRaw && CHECK_NAME_MAPPING[item.controlId]) {
                                checkNameRaw = CHECK_NAME_MAPPING[item.controlId];
                            }

                            if (!checkNameRaw && evidenceItem?.name && evidenceItem.name.startsWith("System Check: ")) {
                                checkNameRaw = evidenceItem.name.replace("System Check: ", "");
                            }

                            return {
                                id: item.controlId,
                                title: title,
                                checkName: checkNameRaw, // Inject checkName
                                status: status,
                                category: category,
                                evidence: evidenceItem?.content,
                                description: `Control ID: ${item.controlId}`,
                                remediation: remediation // Inject Remediation
                            } as ComplianceRule;
                        });

                        // Deduplicate Rules: Keep the "worst" status if duplicates exist
                        const uniqueRulesMap = new Map<string, ComplianceRule>();

                        rules.forEach((rule: any) => {
                            const existing = uniqueRulesMap.get(rule.id);
                            if (!existing) {
                                uniqueRulesMap.set(rule.id, rule);
                            } else {
                                // Merge Logic: Prioritize Failed > Warning > Passed
                                const priority = { 'failed': 3, 'warning': 2, 'passed': 1 };
                                const currentP = priority[existing.status] || 0;
                                const newP = priority[rule.status] || 0;

                                if (newP > currentP) {
                                    uniqueRulesMap.set(rule.id, rule);
                                }
                            }
                        });

                        const uniqueRules = Array.from(uniqueRulesMap.values());

                        const passed = uniqueRules.filter((r: any) => r.status === 'passed').length;
                        const failed = uniqueRules.filter((r: any) => r.status === 'failed').length;
                        const warnings = uniqueRules.filter((r: any) => r.status === 'warning').length;
                        const total = uniqueRules.length;
                        const score = total > 0 ? Math.round((passed / total) * 100) : 0;

                        setFetchedComplianceData({
                            score,
                            total_rules: total,
                            passed,
                            failed,
                            warnings,
                            rules: uniqueRules,
                            framework: 'Asset Security'
                        });
                    } else if (Array.isArray(rawData) && rawData.length === 0) {
                        // No scan data yet — leave fetchedComplianceData null so tab shows "No compliance data available"
                        setFetchedComplianceData(null);
                    } else if (rawData !== null) {
                        console.warn('Compliance fetch returned unexpected format:', typeof rawData);
                        setFetchedComplianceData(null);
                    }
                    // rawData === null means the API call itself failed (already logged in apiService)
                }).catch(err => {
                    console.error("Failed to fetch compliance", err);
                });
            } else {
                console.warn('DEBUG: Skipping compliance fetch. No assetId or hostname. Agent:', agent?.id);
            }
        }
    }, [isOpen, activeTab, asset?.id, agent?.assetId, agent?.hostname, refreshTrigger]);


    if (!isOpen || !agent) return null;

    const currentStatus = statusInfo[agent.status] || statusInfo.Offline;

    // Extract runtime security data from agent meta
    const runtimeSecurityData = (agent.meta as any)?.runtime_security;
    const complianceData = (agent.meta as any)?.compliance_enforcement;
    const healthData = (agent.meta as any)?.predictive_health;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-4xl p-6 m-4 max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
                <div className="flex-shrink-0 flex justify-between items-start mb-4">
                    <div className="flex items-center">
                        <div className="mr-3 p-2 bg-gray-100 dark:bg-gray-700 rounded-lg">
                            {platformIcons[agent.platform] || <ServerIcon size={24} className="text-gray-500" />}
                        </div>
                        <div>
                            <div className="flex items-center space-x-2">
                                <h2 className="text-xl font-bold text-gray-900 dark:text-white">{agent.hostname}</h2>
                                <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${currentStatus.textClass} bg-opacity-10 bg-current border border-current border-opacity-20`}>
                                    {currentStatus.icon}
                                    <span className="ml-1">{agent.status}</span>
                                </span>
                            </div>
                            <div className="flex items-center text-sm text-gray-500 dark:text-gray-400 mt-1">
                                <span className="font-mono">{agent.ipAddress}</span>
                                <span className="mx-2">•</span>
                                <span>v{agent.version}</span>
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center space-x-1 mr-2">
                        <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
                            Updated {formatRelativeTime(lastRefreshed)}
                        </span>
                        <button
                            onClick={onRefresh}
                            disabled={isRefreshing || !onRefresh}
                            title="Refresh now"
                            className="p-1 rounded text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-40 focus:outline-none"
                        >
                            <RefreshCwIcon size={14} className={isRefreshing ? 'animate-spin' : ''} />
                        </button>
                    </div>
                    <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
                        <XIcon size={20} />
                    </button>
                </div>

                {/* Tab Navigation */}
                <div className="flex-shrink-0 border-b border-gray-200 dark:border-gray-700 -mx-6 px-6 overflow-x-auto">
                    <nav className="-mb-px flex space-x-6" aria-label="Tabs">
                        <button
                            onClick={() => setActiveTab('overview')}
                            className={`flex items-center whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === 'overview'
                                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'
                                } `}
                        >
                            <ServerIcon size={16} className="mr-2" />
                            Overview
                        </button>
                        <button
                            onClick={() => setActiveTab('runtime')}
                            className={`flex items-center whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === 'runtime'
                                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'
                                } `}
                        >
                            <ShieldZapIcon size={16} className="mr-2" />
                            Runtime Security
                        </button>
                        <button
                            onClick={() => setActiveTab('compliance')}
                            className={`flex items-center whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === 'compliance'
                                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'
                                } `}
                        >
                            <ShieldCheckIcon size={16} className="mr-2" />
                            Compliance
                        </button>
                        <button
                            onClick={() => setActiveTab('health')}
                            className={`flex items-center whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === 'health'
                                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'
                                } `}
                        >
                            <LightbulbIcon size={16} className="mr-2" />
                            Predictive Health
                        </button>
                        <button
                            onClick={() => setActiveTab('software')}
                            className={`flex items-center whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === 'software'
                                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'
                                } `}
                        >
                            <ComponentIcon size={16} className="mr-2" />
                            Software
                        </button>
                        <button
                            onClick={() => setActiveTab('patching')}
                            className={`flex items-center whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === 'patching'
                                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'
                                } `}
                        >
                            <HistoryIcon size={16} className="mr-2" />
                            Patching
                        </button>
                    </nav>
                </div>

                <div className="flex-grow overflow-y-auto pr-2 pt-4">
                    {activeTab === 'overview' ? (
                        <AgentOverviewTab
                            agent={agent}
                            asset={asset}
                            tenantName={tenantName}
                            currentStatusIcon={currentStatus.icon}
                            currentStatusTextClass={currentStatus.textClass}
                            platformIcon={platformIcons[agent.platform] || <ServerIcon size={20} className="text-gray-500 dark:text-gray-400" />}
                            capabilityInfo={capabilityInfo}
                            onViewRemediationLogs={onViewRemediationLogs}
                            hasPermission={hasPermission}
                        />
                    ) : activeTab === 'runtime' ? (
                        <RuntimeSecurityTab data={runtimeSecurityData} />
                    ) : activeTab === 'compliance' ? (
                        <AgentComplianceTab
                            data={fetchedComplianceData || complianceData}
                            agentId={agent.id}
                            onRefresh={canTriggerScan ? handleRefreshCompliance : undefined}
                        />
                    ) : activeTab === 'software' ? (
                        <AgentSoftwareTab agent={agent} asset={asset} />
                    ) : activeTab === 'patching' ? (
                        <AgentPatchingTab agent={agent} />
                    ) : (
                        <PredictiveHealthTab data={healthData} />
                    )}
                </div>

                <div className="flex-shrink-0 mt-6 flex justify-between items-center pt-4 border-t border-gray-200 dark:border-gray-700">
                    <div className="flex space-x-2">
                        {canRemediate ? (
                            <>
                                <button type="button" onClick={() => onManageCapabilities(agent)}
                                    className="flex items-center px-3 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none"
                                >
                                    <CogIcon size={16} className="mr-2" />
                                    Manage Capabilities
                                </button>
                                {onRunDiagnostics && (
                                    <button type="button" onClick={() => onRunDiagnostics(agent)}
                                        className="flex items-center px-3 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none"
                                        title="Run Diagnostics"
                                    >
                                        <TerminalSquareIcon size={16} className="mr-2" />
                                        Run Diagnostics
                                    </button>
                                )}
                            </>
                        ) : null}
                        {canViewLogs ? (
                            <button type="button" onClick={() => onViewLogs(agent)}
                                className="flex items-center px-3 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none"
                            >
                                <FileTextIcon size={16} className="mr-2" />
                                View Logs
                            </button>
                        ) : null}

                        {/* Move Button (Super Admin Only) */}
                        {currentUser?.role === 'Super Admin' && (
                            <button
                                type="button"
                                onClick={handleOpenMoveModal}
                                className="flex items-center px-3 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none"
                                title="Move Agent to another Tenant"
                            >
                                <ArrowRightIcon size={16} className="mr-2" />
                                Move
                            </button>
                        )}

                        {/* Delete Button */}
                        {canRemediate && onDeleteAgent && (
                            <button
                                type="button"
                                onClick={() => {
                                    if (window.confirm(`Are you sure you want to delete agent ${agent.hostname}? This action cannot be undone.`)) {
                                        onDeleteAgent(agent);
                                        onClose();
                                    }
                                }}
                                className="flex items-center px-3 py-2 text-sm font-medium text-red-700 bg-white dark:bg-gray-700 border border-red-300 dark:border-red-600 rounded-md shadow-sm hover:bg-red-50 dark:hover:bg-red-900/20 focus:outline-none"
                            >
                                <XCircleIcon size={16} className="mr-2" />
                                Delete Agent
                            </button>
                        )}
                    </div>
                    <button type="button" onClick={onClose}
                        className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700"
                    >
                        Close
                    </button>
                </div>
            </div>

            {/* Move Agent Modal */}
            {isMoveModalOpen && (
                <div className="fixed inset-0 bg-black bg-opacity-60 z-[60] flex justify-center items-center">
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 w-96">
                        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">Move Agent to Tenant</h3>
                        <p className="text-sm text-gray-500 mb-4">Select the target tenant to transfer <strong>{agent.hostname}</strong> to.</p>

                        <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Target Tenant</label>
                            <select
                                value={targetTenantId}
                                onChange={(e) => setTargetTenantId(e.target.value)}
                                className="w-full border-gray-300 rounded-md shadow-sm dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:ring-primary-500 focus:border-primary-500"
                            >
                                <option value="">Select Tenant...</option>
                                {tenants.filter(t => t.id !== agent.tenantId).map(t => (
                                    <option key={t.id} value={t.id}>{t.name} ({t.subscriptionTier})</option>
                                ))}
                            </select>
                        </div>

                        <div className="flex justify-end space-x-2">
                            <button
                                onClick={() => setIsMoveModalOpen(false)}
                                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-md dark:text-gray-300 dark:hover:bg-gray-700"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={() => setIsConfirmMoveOpen(true)}
                                disabled={!targetTenantId || isMoving}
                                className="px-4 py-2 text-sm text-white bg-primary-600 hover:bg-primary-700 rounded-md disabled:opacity-50"
                            >
                                {isMoving ? 'Moving...' : 'Move Agent'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Confirmation Modal for Move */}
            <ConfirmationModal
                isOpen={isConfirmMoveOpen}
                onClose={() => setIsConfirmMoveOpen(false)}
                onConfirm={handleMoveAgent}
                title="Confirm Move Agent"
                message={`Are you sure you want to move ${agent.hostname} to another tenant? This will transfer ownership and data.`}
                confirmText="Move Agent"
                isDestructive={false}
            />
        </div>
    );
};
