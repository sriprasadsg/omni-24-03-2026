import React, { useState } from 'react';
import { Agent, AgentPlatform, AgentStatus, AgentCapability, Asset, VulnerabilitySeverity, Tenant } from '../types';
import { XIcon, ServerIcon, CheckIcon, XCircleIcon, AlertCircleIcon, LinuxIcon, WindowsIcon, DockerIcon, KubernetesIcon, BarChart3Icon, ShieldSearchIcon, FileTextIcon, FileShieldIcon, ShieldCheckIcon, ShieldZapIcon, CogIcon, LightbulbIcon, UsersIcon, ComponentIcon, GitMergeIcon, HistoryIcon, ShieldAlertIcon, TerminalSquareIcon, ArrowRightIcon } from './icons';
import { useUser } from '../contexts/UserContext';
import { useTimeZone } from '../contexts/TimeZoneContext';
import { RuntimeSecurityTab } from './RuntimeSecurityTab';
import { AgentComplianceTab, ComplianceData, ComplianceRule } from './AgentComplianceTab';
import { PredictiveHealthTab } from './PredictiveHealthTab';
import { ConfirmationModal } from './ConfirmationModal';
import { moveAgent, fetchTenants, fetchAssetCompliance, runAgentComplianceScan, linkAgentToAsset, fetchAssets } from '../services/apiService';


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
}

const statusInfo: Record<AgentStatus, { icon: React.ReactNode; textClass: string; }> = {
    Online: { icon: <CheckIcon size={16} />, textClass: 'text-green-600 dark:text-green-400' },
    Offline: { icon: <XCircleIcon size={16} />, textClass: 'text-gray-500' },
    Error: { icon: <AlertCircleIcon size={16} />, textClass: 'text-red-600 dark:text-red-400' },
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
    metrics_collection: { icon: <BarChart3Icon size={16} />, label: "Metric Collection" },
    vulnerability_scanning: { icon: <ShieldSearchIcon size={16} />, label: "Vulnerability Scanning" },
    log_collection: { icon: <FileTextIcon size={16} />, label: "Log Collection" },
    fim: { icon: <FileShieldIcon size={16} />, label: "File Integrity Monitoring" },
    compliance_enforcement: { icon: <ShieldCheckIcon size={16} />, label: "Compliance Enforcement" },
    runtime_security: { icon: <ShieldZapIcon size={16} />, label: "Runtime Security" },
    predictive_health: { icon: <LightbulbIcon size={16} />, label: 'Predictive Health' },
    ueba: { icon: <UsersIcon size={16} />, label: 'Behavior Analytics (UEBA)' },
    sbom_analysis: { icon: <ComponentIcon size={16} />, label: 'SBOM Analysis' },
    ebpf_tracing: { icon: <GitMergeIcon size={16} />, label: 'eBPF Tracing' },
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

export const AgentDetailModal: React.FC<AgentDetailModalProps> = ({ isOpen, onClose, agent, asset, onManageCapabilities, onViewRemediationLogs, onViewLogs, onRunDiagnostics, onDeleteAgent }) => {
    const { hasPermission, currentUser } = useUser();
    const canRemediate = hasPermission('remediate:agents');
    const { timeZone } = useTimeZone();

    const canViewLogs = hasPermission('view:agent_logs');
    const [activeTab, setActiveTab] = useState<'overview' | 'runtime' | 'compliance' | 'health' | 'software'>('overview');
    const [fetchedComplianceData, setFetchedComplianceData] = useState<ComplianceData | null>(null);
    const [tenantName, setTenantName] = useState<string>('Loading...');

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

    // Link Asset State
    const [isLinkingAsset, setIsLinkingAsset] = useState(false);
    const [availableAssets, setAvailableAssets] = useState<Asset[]>([]);
    const [selectedAssetId, setSelectedAssetId] = useState('');
    const [isLinking, setIsLinking] = useState(false);

    const handleOpenLinkModal = async () => {
        setIsLinkingAsset(true);
        try {
            const res = await fetchAssets();
            setAvailableAssets(res);
        } catch (e) {
            console.error("Failed to fetch assets", e);
            alert("Failed to load assets list. Please try again.");
        }
    };

    const handleLinkAsset = async () => {
        if (!selectedAssetId || !agent) return;

        setIsLinking(true);
        try {
            await linkAgentToAsset(agent.id, selectedAssetId);
            alert("Asset linked successfully.");
            setIsLinkingAsset(false);
            window.location.reload(); // Reload to refresh data
        } catch (e: any) {
            console.error("Link Asset Error:", e);
            alert(`Failed to link asset: ${e.message || "Unknown error"}`);
        } finally {
            setIsLinking(false);
        }
    };

    const handleOpenMoveModal = async () => {
        setIsMoveModalOpen(true);
        // Fetch tenants dynamically to ensure fresh list
        try {
            const res = await fetchTenants();
            setTenants(res);
        } catch (e) {
            console.error("Failed to fetch tenants", e);
            alert("Failed to load tenants list. Please try again.");
        }
    };

    const handleMoveAgent = async () => {
        if (!targetTenantId) return;

        setIsMoving(true);
        try {
            await moveAgent(agent.id, targetTenantId);
            alert("Agent moved successfully.");
            setIsMoveModalOpen(false);
            onClose(); // Close main modal as agent might disappear from current view
            window.location.reload(); // Simple reload to refresh all data views
        } catch (e: any) {
            console.error("Move Agent Error:", e);
            alert(`Failed to move agent: ${e.message || "Unknown error"}`);
        } finally {
            setIsMoving(false);
        }
    };

    React.useEffect(() => {
        if (isOpen && activeTab === 'compliance' && (asset?.id || agent?.assetId)) {
            const id = asset?.id || agent?.assetId;
            console.log('DEBUG: Fetching compliance for Asset ID:', id);

            if (id) {
                fetchAssetCompliance(id).then(rawData => {
                    console.log('DEBUG: Raw Compliance Data:', rawData);

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

                        console.log('DEBUG: Transformed Rules:', uniqueRules);

                        setFetchedComplianceData({
                            score,
                            total_rules: total,
                            passed,
                            failed,
                            warnings,
                            rules: uniqueRules,
                            framework: 'Asset Security'
                        });
                    } else {
                        console.warn('DEBUG: No compliance data returned or invalid format');
                        setFetchedComplianceData(null);
                    }
                }).catch(err => {
                    console.error("Failed to fetch compliance", err);
                });
            } else {
                console.warn('DEBUG: Skipping compliance fetch. Missing ID. Agent:', agent, 'Asset:', asset);
            }
        }
    }, [isOpen, activeTab, asset?.id, agent?.assetId]);

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
                const rawData = await fetchAssetCompliance(id);
                // Simple trick to force update if data changed, or we can just update state directly
                // Re-using the same transformation logic would be cleaner if extracted, but for now:
                // Actually we need to re-run the whole transform block.

                // Let's just create a 'refreshTrigger' state to force useEffect re-run
                setRefreshTrigger(prev => prev + 1);
            }

        } catch (e) {
            console.error("Failed to refresh compliance:", e);
            alert("Failed to trigger scan. Check console.");
        }
    };

    const [refreshTrigger, setRefreshTrigger] = useState(0);

    // Update useEffect to depend on refreshTrigger
    React.useEffect(() => {
        if (isOpen && activeTab === 'compliance' && (asset?.id || agent?.assetId)) {
            const id = asset?.id || agent?.assetId;
            console.log('DEBUG: Fetching compliance for Asset ID:', id);

            if (id) {
                fetchAssetCompliance(id).then(rawData => {
                    console.log('DEBUG: Raw Compliance Data:', rawData);

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

                        console.log('DEBUG: Transformed Rules:', uniqueRules);

                        setFetchedComplianceData({
                            score,
                            total_rules: total,
                            passed,
                            failed,
                            warnings,
                            rules: uniqueRules,
                            framework: 'Asset Security'
                        });
                    } else {
                        console.warn('DEBUG: No compliance data returned or invalid format');
                        setFetchedComplianceData(null);
                    }
                }).catch(err => {
                    console.error("Failed to fetch compliance", err);
                });
            } else {
                console.warn('DEBUG: Skipping compliance fetch. Missing ID. Agent:', agent, 'Asset:', asset);
            }
        }
    }, [isOpen, activeTab, asset?.id, agent?.assetId, refreshTrigger]);


    const sortedVulnerabilities = React.useMemo(() => {
        if (!asset || !asset.vulnerabilities) return [];
        return [...asset.vulnerabilities]
            .filter(v => v.status === 'Open')
            .sort((a, b) => {
                const severityOrder: Record<VulnerabilitySeverity, number> = { Critical: 4, High: 3, Medium: 2, Low: 1, Informational: 0 };
                return severityOrder[b.severity] - severityOrder[a.severity];
            });
    }, [asset]);

    if (!isOpen || !agent) return null;

    const currentStatus = statusInfo[agent.status] || statusInfo.Offline;

    // Extract runtime security data from agent meta
    const runtimeSecurityData = agent.meta?.runtime_security;
    const complianceData = agent.meta?.compliance_enforcement;
    const healthData = agent.meta?.predictive_health;

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
                        <div className="space-y-4">
                            <dl>
                                <DetailRow label="Status">
                                    <span className={`flex items - center font - semibold ${currentStatus.textClass} `}>
                                        {currentStatus.icon}
                                        <span className="ml-2">{agent.status}</span>
                                    </span>
                                </DetailRow>
                                <DetailRow label="Platform">
                                    <div className="flex items-center space-x-2">
                                        {platformIcons[agent.platform]}
                                        <span>{agent.platform}</span>
                                    </div>
                                </DetailRow>
                                <DetailRow label="OS Version">
                                    {asset?.osVersion || agent.meta?.os_version || 'Unknown'}
                                </DetailRow>
                                <DetailRow label="Agent Version">{agent.version}</DetailRow>
                                <DetailRow label="Network Interfaces">
                                    <div className="space-y-1">
                                        {asset?.macAddresses?.map((mac, idx) => (
                                            <div key={idx} className="flex space-x-2 text-xs">
                                                <span className="font-semibold text-gray-600 dark:text-gray-400">{mac.interface}:</span>
                                                <span className="font-mono">{mac.mac}</span>
                                            </div>
                                        )) || <span className="font-mono text-xs">{asset?.macAddress || 'Unknown'}</span>}
                                    </div>
                                </DetailRow>
                                <DetailRow label="Last Seen">{new Date(agent.lastSeen).toLocaleString(undefined, { timeZone })}</DetailRow>
                                <DetailRow label="Agent ID"><span className="font-mono text-xs">{agent.id}</span></DetailRow>
                                <DetailRow label="Asset ID">
                                    <div className="flex items-center space-x-2">
                                        <span className="font-mono text-xs text-gray-900 dark:text-gray-200">{agent.assetId || 'Unlinked'}</span>
                                        {(hasPermission('manage:agents') || hasPermission('admin:*')) && (
                                            <button
                                                onClick={handleOpenLinkModal}
                                                className="text-xs text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 flex items-center"
                                            >
                                                <GitMergeIcon size={12} className="mr-1" />
                                                {agent.assetId ? 'Change Link' : 'Link Asset'}
                                            </button>
                                        )}
                                    </div>
                                    {isLinkingAsset && (
                                        <div className="mt-2 text-xs flex items-center space-x-2 border p-2 rounded-md bg-gray-50 dark:bg-gray-800 dark:border-gray-700">
                                            <select
                                                value={selectedAssetId}
                                                onChange={(e) => setSelectedAssetId(e.target.value)}
                                                className="block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-xs dark:bg-gray-700 dark:text-gray-200"
                                            >
                                                <option value="">Select an Asset...</option>
                                                {availableAssets.map(a => (
                                                    <option key={a.id} value={a.id}>{a.hostname} ({a.osType || 'Unknown OS'}) {a.agentStatus === 'Online' ? '⚡' : ''}</option>
                                                ))}
                                            </select>
                                            <button
                                                onClick={handleLinkAsset}
                                                disabled={isLinking || !selectedAssetId}
                                                className="bg-primary-600 text-white px-2 py-1 flex items-center justify-center whitespace-nowrap rounded hover:bg-primary-700 disabled:opacity-50"
                                            >
                                                {isLinking ? 'Linking...' : 'Confirm'}
                                            </button>
                                            <button
                                                onClick={() => setIsLinkingAsset(false)}
                                                disabled={isLinking}
                                                className="bg-gray-200 text-gray-700 px-2 py-1 rounded hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
                                            >
                                                Cancel
                                            </button>
                                        </div>
                                    )}
                                </DetailRow>
                                <DetailRow label="Tenant">
                                    <div className="flex flex-col">
                                        <span className="font-medium text-gray-900 dark:text-gray-100">{tenantName}</span>
                                        <span className="font-mono text-xs text-gray-500">{agent.tenantId}</span>
                                    </div>
                                </DetailRow>
                            </dl>

                            <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">Enabled Capabilities</h3>
                                {agent.capabilities && agent.capabilities.length > 0 ? (
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-3">
                                        {agent.capabilities.map(cap => (
                                            capabilityInfo[cap] ?
                                                <div key={cap} title={capabilityInfo[cap].label} className="flex items-center">
                                                    <div className="flex-shrink-0 w-6 h-6 flex items-center justify-center rounded-full bg-gray-100 dark:bg-gray-700 text-primary-500 dark:text-primary-400">
                                                        {capabilityInfo[cap].icon}
                                                    </div>
                                                    <span className="ml-3 text-sm font-medium text-gray-700 dark:text-gray-300">{capabilityInfo[cap].label}</span>
                                                </div>
                                                : null
                                        ))}
                                    </div>
                                ) : (
                                    <p className="text-sm text-gray-400">No capabilities enabled.</p>
                                )}
                            </div>

                            <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3 flex items-center">
                                    <ShieldAlertIcon size={16} className="mr-2" />
                                    Asset Vulnerabilities
                                </h3>
                                {sortedVulnerabilities.length > 0 ? (
                                    <div className="space-y-2 max-h-40 overflow-y-auto pr-1">
                                        {sortedVulnerabilities.map((vuln, index) => (
                                            <div key={index} className="p-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600 flex justify-between items-center">
                                                <div>
                                                    <p className="font-semibold text-sm text-gray-800 dark:text-gray-200">{vuln.cveId || 'Unknown CVE'}</p>
                                                    <p className="text-xs text-gray-500 dark:text-gray-400">{vuln.affectedSoftware}</p>
                                                </div>
                                                <span className={`px - 2 py - 1 text - xs font - medium rounded - full ${severityClasses[vuln.severity]} `}>
                                                    {vuln.severity}
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <p className="text-sm text-gray-400">No open vulnerabilities detected on the associated asset.</p>
                                )}
                            </div>

                            <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3 flex items-center">
                                    <HistoryIcon size={16} className="mr-2" />
                                    Remediation History
                                </h3>
                                {agent.remediationAttempts && agent.remediationAttempts.length > 0 ? (
                                    <div className="space-y-2 max-h-40 overflow-y-auto pr-1">
                                        {agent.remediationAttempts.map((attempt, index) => {
                                            const isSuccess = (index + agent.hostname.length) % 3 !== 0;
                                            return (
                                                <div key={index} className="p-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600 flex justify-between items-center">
                                                    <div>
                                                        <p className="font-semibold text-sm text-gray-800 dark:text-gray-200">Attempt #{index + 1}</p>
                                                        <p className="text-xs text-gray-500 dark:text-gray-400">{new Date(attempt.timestamp).toLocaleString(undefined, { timeZone })}</p>
                                                    </div>
                                                    <div className="flex items-center space-x-4">
                                                        {isSuccess ? (
                                                            <span className="flex items-center text-xs font-medium text-green-700 bg-green-100 dark:text-green-200 dark:bg-green-900/50 px-2 py-1 rounded-full">
                                                                <CheckIcon size={14} className="mr-1.5" /> Success
                                                            </span>
                                                        ) : (
                                                            <span className="flex items-center text-xs font-medium text-red-700 bg-red-100 dark:text-red-200 dark:bg-red-900/50 px-2 py-1 rounded-full">
                                                                <XCircleIcon size={14} className="mr-1.5" /> Failed
                                                            </span>
                                                        )}
                                                        <button onClick={() => onViewRemediationLogs(agent)} className="text-xs font-medium text-primary-600 hover:underline">
                                                            View Log
                                                        </button>
                                                    </div>
                                                </div>
                                            )
                                        }).reverse()}
                                    </div>
                                ) : (
                                    <p className="text-sm text-gray-400">No remediation attempts have been recorded for this agent.</p>
                                )}
                            </div>
                        </div>
                    ) : activeTab === 'runtime' ? (
                        <RuntimeSecurityTab data={runtimeSecurityData} />
                    ) : activeTab === 'compliance' ? (
                        <AgentComplianceTab
                            data={fetchedComplianceData || complianceData}
                            agentId={agent.id}
                            onRefresh={handleRefreshCompliance}
                        />
                    ) : activeTab === 'software' ? (
                        <div className="space-y-4">
                            {(() => {
                                // Check both asset and agent meta for software data
                                const softwareList = asset?.installedSoftware || agent?.meta?.installed_software || [];

                                return (
                                    <>
                                        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 flex items-center">
                                            <ComponentIcon size={20} className="mr-2" />
                                            Installed Software ({softwareList.length})
                                        </h3>
                                        {softwareList.length > 0 ? (
                                            <div className="overflow-x-auto border border-gray-200 dark:border-gray-700 rounded-lg">
                                                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                                                    <thead className="bg-gray-50 dark:bg-gray-800">
                                                        <tr>
                                                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Name</th>
                                                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Version</th>
                                                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Install Date</th>
                                                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                                                        {softwareList.map((sw, idx) => (
                                                            <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                                                <td className="px-4 py-2 text-sm text-gray-900 dark:text-gray-200 font-medium">
                                                                    <div className="flex items-center">
                                                                        {sw.name}
                                                                        {sw.updateAvailable && (
                                                                            <span title="Update Available" className="ml-2 w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
                                                                        )}
                                                                    </div>
                                                                </td>
                                                                <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400 font-mono text-xs">
                                                                    {sw.version}
                                                                    {sw.latestVersion && (
                                                                        <div className="text-red-500 dark:text-red-400 font-bold mt-1">
                                                                            Latest: {sw.latestVersion}
                                                                        </div>
                                                                    )}
                                                                </td>
                                                                <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">{sw.installDate || 'Unknown'}</td>
                                                                <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">
                                                                    {sw.updateAvailable ? (
                                                                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300">
                                                                            Update Available
                                                                        </span>
                                                                    ) : (
                                                                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300">
                                                                            Up to date
                                                                        </span>
                                                                    )}
                                                                </td>
                                                            </tr>
                                                        ))}
                                                    </tbody>
                                                </table>
                                            </div>
                                        ) : (
                                            <p className="text-gray-500 dark:text-gray-400 italic">No installed software detected.</p>
                                        )}
                                    </>
                                );
                            })()}
                        </div>
                    ) : activeTab === 'patching' ? (
                        <div className="space-y-6">
                            {/* System Information */}
                            <div>
                                <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-3 flex items-center">
                                    <ServerIcon size={20} className="mr-2" />
                                    System Information
                                </h3>
                                <dl className="grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2">
                                    <div className="sm:col-span-1">
                                        <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">BIOS Version</dt>
                                        <dd className="mt-1 text-sm text-gray-900 dark:text-gray-200">{agent.meta?.system_patching?.bios_info?.version || 'Unknown'}</dd>
                                    </div>
                                    <div className="sm:col-span-1">
                                        <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Manufacturer</dt>
                                        <dd className="mt-1 text-sm text-gray-900 dark:text-gray-200">{agent.meta?.system_patching?.bios_info?.manufacturer || 'Unknown'}</dd>
                                    </div>
                                    <div className="sm:col-span-1">
                                        <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Release Date</dt>
                                        <dd className="mt-1 text-sm text-gray-900 dark:text-gray-200">{agent.meta?.system_patching?.bios_info?.release_date || 'Unknown'}</dd>
                                    </div>
                                    <div className="sm:col-span-1">
                                        <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Last Boot Time</dt>
                                        <dd className="mt-1 text-sm text-gray-900 dark:text-gray-200">{agent.meta?.system_patching?.uptime?.boot_time || 'Unknown'}</dd>
                                    </div>
                                </dl>
                            </div>

                            {/* Pending Updates */}
                            <div>
                                <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-3 flex items-center">
                                    <HistoryIcon size={20} className="mr-2" />
                                    Pending Updates ({agent.meta?.system_patching?.pending_updates?.length || 0})
                                </h3>
                                {agent.meta?.system_patching?.pending_updates && agent.meta.system_patching.pending_updates.length > 0 ? (
                                    <div className="overflow-x-auto border border-gray-200 dark:border-gray-700 rounded-lg max-h-60">
                                        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                                            <thead className="bg-gray-50 dark:bg-gray-800 sticky top-0">
                                                <tr>
                                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Update Title</th>
                                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Severity</th>
                                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Mandatory</th>
                                                </tr>
                                            </thead>
                                            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                                                {agent.meta.system_patching.pending_updates.map((update: any, idx: number) => (
                                                    <tr key={idx}>
                                                        <td className="px-4 py-2 text-sm text-gray-900 dark:text-gray-200">{update.title}</td>
                                                        <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">{update.severity}</td>
                                                        <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">{update.mandatory ? 'Yes' : 'No'}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                ) : (
                                    <p className="text-sm text-gray-400 italic">No pending updates found.</p>
                                )}
                            </div>
                        </div>
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
