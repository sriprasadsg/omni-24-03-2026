import React, { useState, useEffect } from 'react';
import { Agent, AgentCapability } from '../types';
import { XIcon, CogIcon, BarChart3Icon, ShieldSearchIcon, FileTextIcon, FileShieldIcon, ShieldCheckIcon, ShieldZapIcon, SaveIcon, LightbulbIcon, UsersIcon, ComponentIcon, GitMergeIcon, ActivityIcon, ZapIcon, NetworkIcon, CloudShieldIcon, GlobeIcon, EyeIcon, BotIcon, PackageCheckIcon, BoxIcon, SearchIcon, TestTubeIcon, MonitorIcon, TerminalSquareIcon, DownloadIcon, RefreshCwIcon, WorkflowIcon, RadarIcon, DatabaseIcon, BrainCircuitIcon, SendIcon, ClipboardCheckIcon, HeartHandshakeIcon, HardDriveIcon, BinocularsIcon } from './icons';

interface ManageAgentCapabilitiesModalProps {
    isOpen: boolean;
    onClose: () => void;
    agent: Agent | null;
    onSave: (updatedAgent: Agent) => void;
}

const CAPABILITY_GROUPS: { title: string; items: { id: AgentCapability; icon: React.ReactNode; label: string; description: string }[] }[] = [
    {
        title: 'Core Telemetry',
        items: [
            { id: 'metrics_collection',  icon: <BarChart3Icon />,  label: 'Metric Collection',   description: 'Collects CPU, memory, disk, and network metrics in real time.' },
            { id: 'log_collection',      icon: <FileTextIcon />,   label: 'Log Collection',       description: 'Gathers and forwards system, application, and security logs.' },
            { id: 'process_monitor',     icon: <ActivityIcon />,   label: 'Process Monitor',      description: 'Tracks running processes, parent-child chains, and resource usage.' },
            { id: 'log_shipper',         icon: <SendIcon />,        label: 'Log Shipper',          description: 'Forwards structured log streams to SIEM and remote backends.' },
        ],
    },
    {
        title: 'Security Detection',
        items: [
            { id: 'vulnerability_scanning',       icon: <ShieldSearchIcon />, label: 'Vulnerability Scanning',       description: 'Scans installed packages and libraries for known CVEs.' },
            { id: 'fim',                           icon: <FileShieldIcon />,   label: 'File Integrity Monitoring',    description: 'Detects unauthorized changes to critical system files.' },
            { id: 'real_time_fim',                 icon: <RadarIcon />,        label: 'Real-Time FIM',                description: 'Streams file system changes in real time via inotify/FSEvents.' },
            { id: 'compliance_enforcement',        icon: <ShieldCheckIcon />,  label: 'Compliance Enforcement',       description: 'Enforces security baselines and policy controls.' },
            { id: 'runtime_security',              icon: <ShieldZapIcon />,    label: 'Runtime Security (XDR)',       description: 'Detects and blocks malicious runtime behavior via XDR.' },
            { id: 'edr_realtime',                  icon: <ZapIcon />,          label: 'EDR Real-Time',                description: 'Continuous endpoint telemetry feeding the EDR pipeline.' },
            { id: 'persistence_detection',         icon: <SearchIcon />,       label: 'Persistence Detection',        description: 'Identifies attacker persistence mechanisms (registry, crons, services).' },
            { id: 'deception_monitor',             icon: <BinocularsIcon />,   label: 'Deception Monitor',            description: 'Monitors honeypot and canary tokens for unauthorized access.' },
        ],
    },
    {
        title: 'Network & Cloud',
        items: [
            { id: 'network_discovery', icon: <NetworkIcon />,        label: 'Network Discovery',        description: 'Discovers and maps local network topology and open ports.' },
            { id: 'cloud_metadata',    icon: <CloudShieldIcon />,   label: 'Cloud Metadata Collector',  description: 'Collects cloud instance metadata from AWS/Azure/GCP.' },
            { id: 'web_monitor',       icon: <GlobeIcon />,          label: 'Web Monitor',               description: 'Monitors web endpoint availability, TLS health, and response times.' },
            { id: 'remote_access',     icon: <TerminalSquareIcon />, label: 'Remote Access',              description: 'Provides secure remote terminal and desktop access to the agent host.' },
        ],
    },
    {
        title: 'Data & Privacy',
        items: [
            { id: 'pii_scanner',                    icon: <EyeIcon />,            label: 'PII Data Scanner',               description: 'Scans file systems and memory for personally identifiable information.' },
            { id: 'sbom_analysis',                  icon: <ComponentIcon />,      label: 'SBOM Analysis',                  description: 'Analyzes Software Bill of Materials for supply-chain vulnerabilities.' },
            { id: 'compliance_evidence_collector',  icon: <ClipboardCheckIcon />, label: 'Compliance Evidence Collector',   description: 'Automatically gathers and uploads compliance evidence artifacts.' },
            { id: 'vendor_risk',                    icon: <HeartHandshakeIcon />, label: 'Vendor Risk Scanner',             description: 'Assesses third-party software vendor risk on the endpoint.' },
        ],
    },
    {
        title: 'Advanced AI & Observability',
        items: [
            { id: 'predictive_health', icon: <LightbulbIcon />,  label: 'Predictive Health AI',   description: 'Uses ML to predict agent and host health degradation.' },
            { id: 'ueba',              icon: <UsersIcon />,       label: 'Behavior Analytics (UEBA)', description: 'Detects insider threats and anomalous user/entity behavior.' },
            { id: 'ebpf_tracing',      icon: <GitMergeIcon />,   label: 'eBPF Kernel Tracing',     description: 'Provides deep kernel-level syscall visibility using eBPF.' },
            { id: 'shadow_ai',         icon: <BotIcon />,         label: 'Shadow AI Detector',      description: 'Identifies unauthorized AI model usage and data leakage risks.' },
        ],
    },
    {
        title: 'Remediation & Management',
        items: [
            { id: 'system_patching',              icon: <PackageCheckIcon />,   label: 'Autonomous Patching',          description: 'Automatically applies OS and package patches on schedule.' },
            { id: 'patch_installer',              icon: <DownloadIcon />,       label: 'Patch Installer',              description: 'Installs individual patches and hotfixes on demand.' },
            { id: 'software_management',          icon: <BoxIcon />,            label: 'Software Management',          description: 'Manages software installation, updates, and removal.' },
            { id: 'remediation_executor',         icon: <WorkflowIcon />,       label: 'Remediation Executor',         description: 'Runs remediation scripts and playbook actions on the endpoint.' },
            { id: 'autonomous_response',          icon: <BrainCircuitIcon />,   label: 'Autonomous Response',          description: 'Executes automated incident containment actions without human approval.' },
            { id: 'agent_update',                 icon: <RefreshCwIcon />,      label: 'Agent Self-Update',            description: 'Keeps the agent binary and capabilities up to date automatically.' },
            { id: 'vss_manager',                  icon: <DatabaseIcon />,       label: 'VSS Manager',                  description: 'Manages Volume Shadow Copy Services for backup and rollback.' },
            { id: 'backup_verifier',              icon: <HardDriveIcon />,      label: 'Backup Verifier',              description: 'Verifies the integrity of local and cloud backup snapshots.' },
            { id: 'process_injection_simulation', icon: <TestTubeIcon />,       label: 'Injection Simulator',          description: 'Simulates process injection attacks to validate EDR detection.' },
        ],
    },
];

// Flat list kept for backward-compat (used by legacy callers)
const allCapabilities = CAPABILITY_GROUPS.flatMap(g => g.items);

export const ManageAgentCapabilitiesModal: React.FC<ManageAgentCapabilitiesModalProps> = ({ isOpen, onClose, agent, onSave }) => {
    const [enabledCapabilities, setEnabledCapabilities] = useState<Set<AgentCapability>>(new Set());

    useEffect(() => {
        if (agent) {
            // Backend's GET /agents endpoint transforms capabilities from string IDs
            // to rich objects {id, name, enabled, status}. Normalise back to string IDs
            // so Set lookups (has / delete / add) work correctly.
            const ids = (agent.capabilities || []).map(
                (c: any) => (typeof c === 'string' ? c : c.id) as AgentCapability
            );
            setEnabledCapabilities(new Set(ids));
        }
    }, [agent]);

    const handleToggle = (capability: AgentCapability) => {
        setEnabledCapabilities(prev => {
            const next = new Set(prev);
            if (next.has(capability)) next.delete(capability);
            else next.add(capability);
            return next;
        });
    };

    const allIds = allCapabilities.map(c => c.id);
    const allEnabled = allIds.every(id => enabledCapabilities.has(id));
    const noneEnabled = allIds.every(id => !enabledCapabilities.has(id));

    const handleSelectAll = () =>
        setEnabledCapabilities(allEnabled ? new Set() : new Set(allIds));

    const handleGroupToggle = (groupItems: { id: AgentCapability }[]) => {
        const ids = groupItems.map(c => c.id);
        const allOn = ids.every(id => enabledCapabilities.has(id));
        setEnabledCapabilities(prev => {
            const next = new Set(prev);
            ids.forEach(id => allOn ? next.delete(id) : next.add(id));
            return next;
        });
    };

    const handleSave = () => {
        if (agent) {
            // Always save as plain string IDs so the DB stays canonical.
            const ids = Array.from(enabledCapabilities).map(
                (c: any) => (typeof c === 'string' ? c : c.id) as AgentCapability
            );
            onSave({ ...agent, capabilities: ids });
        }
    };

    if (!isOpen || !agent) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl p-6 m-4 max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
                <div className="flex-shrink-0 flex justify-between items-start mb-4">
                    <div>
                        <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center">
                            <CogIcon className="mr-3 text-primary-500" />
                            Manage Agent Capabilities
                        </h2>
                        <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">{agent.hostname}</p>
                    </div>
                    <div className="flex items-center gap-2">
                        {/* Global select-all / clear-all */}
                        <button
                            onClick={handleSelectAll}
                            className={`px-3 py-1 text-xs font-semibold rounded-full border transition-colors ${
                                allEnabled
                                    ? 'bg-red-50 border-red-300 text-red-600 hover:bg-red-100 dark:bg-red-900/20 dark:border-red-700 dark:text-red-400'
                                    : 'bg-primary-50 border-primary-300 text-primary-700 hover:bg-primary-100 dark:bg-primary-900/20 dark:border-primary-700 dark:text-primary-400'
                            }`}
                        >
                            {allEnabled ? 'Disable All' : 'Enable All'}
                        </button>
                        <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700">
                            <XIcon size={20} />
                        </button>
                    </div>
                </div>

                {/* Summary bar */}
                <div className="flex-shrink-0 mb-3 flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400 px-1">
                    <span className="font-medium text-primary-600 dark:text-primary-400">{enabledCapabilities.size} enabled</span>
                    <span>·</span>
                    <span>{allIds.length - enabledCapabilities.size} disabled</span>
                    <span>·</span>
                    <span>{allIds.length} total</span>
                </div>

                <div className="flex-grow space-y-5 overflow-y-auto pr-2">
                    {CAPABILITY_GROUPS.map(group => {
                        const groupAllOn = group.items.every(c => enabledCapabilities.has(c.id));
                        const groupSomeOn = group.items.some(c => enabledCapabilities.has(c.id));
                        return (
                            <div key={group.title}>
                                {/* Group header with per-group select-all */}
                                <div className="flex items-center justify-between mb-2 px-1">
                                    <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                                        {group.title}
                                    </p>
                                    <button
                                        onClick={() => handleGroupToggle(group.items)}
                                        className={`text-[10px] font-semibold px-2 py-0.5 rounded border transition-colors ${
                                            groupAllOn
                                                ? 'text-gray-500 border-gray-300 hover:text-red-500 hover:border-red-300 dark:border-gray-600'
                                                : 'text-primary-600 border-primary-300 hover:bg-primary-50 dark:text-primary-400 dark:border-primary-700'
                                        }`}
                                    >
                                        {groupAllOn ? 'Disable All' : groupSomeOn ? 'Enable Rest' : 'Enable All'}
                                    </button>
                                </div>

                                <div className="space-y-2">
                                    {group.items.map(cap => {
                                        const isEnabled = enabledCapabilities.has(cap.id);
                                        return (
                                            <div
                                                key={cap.id}
                                                onClick={() => handleToggle(cap.id)}
                                                className={`p-3 rounded-lg border flex items-center justify-between cursor-pointer transition-all duration-150 ${
                                                    isEnabled
                                                        ? 'bg-gray-50 dark:bg-gray-700/50 border-gray-200 dark:border-gray-600 hover:border-primary-400'
                                                        : 'bg-gray-50/40 dark:bg-gray-800/30 border-gray-100 dark:border-gray-700/50 opacity-50 hover:opacity-70'
                                                }`}
                                            >
                                                <div className="flex items-center">
                                                    <div className={`flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-full mr-4 transition-colors ${
                                                        isEnabled
                                                            ? 'bg-gray-100 dark:bg-gray-700 text-primary-500 dark:text-primary-400'
                                                            : 'bg-gray-100 dark:bg-gray-700/50 text-gray-400 dark:text-gray-600'
                                                    }`}>
                                                        {cap.icon}
                                                    </div>
                                                    <div>
                                                        <p className={`font-semibold text-sm ${isEnabled ? 'text-gray-800 dark:text-gray-200' : 'text-gray-400 dark:text-gray-500'}`}>
                                                            {cap.label}
                                                            {!isEnabled && <span className="ml-2 text-[10px] font-normal text-gray-400 dark:text-gray-600 italic">disabled</span>}
                                                        </p>
                                                        <p className="text-xs text-gray-500 dark:text-gray-400">{cap.description}</p>
                                                    </div>
                                                </div>
                                                {/* Toggle switch — click on row also toggles */}
                                                <button
                                                    type="button"
                                                    onClick={e => { e.stopPropagation(); handleToggle(cap.id); }}
                                                    className={`${isEnabled ? 'bg-primary-600' : 'bg-gray-300 dark:bg-gray-600'} relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 dark:ring-offset-gray-800`}
                                                    role="switch"
                                                    aria-checked={isEnabled}
                                                >
                                                    <span
                                                        aria-hidden="true"
                                                        className={`${isEnabled ? 'translate-x-5' : 'translate-x-0'} pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out`}
                                                    />
                                                </button>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        );
                    })}
                </div>

                <div className="flex-shrink-0 mt-6 flex justify-end space-x-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                    <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md">Cancel</button>
                    <button onClick={handleSave} className="flex items-center px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                        <SaveIcon size={16} className="mr-2" />
                        Save Capabilities
                    </button>
                </div>
            </div>
        </div>
    );
};
