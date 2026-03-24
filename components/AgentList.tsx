
import React, { useState, useMemo } from 'react';
import { Agent, AgentPlatform, AgentStatus, Asset, Filter } from '../types';
import {
    WindowsIcon, LinuxIcon, DockerIcon, KubernetesIcon, ServerIcon, HistoryIcon,
    RefreshCwIcon, FileTextIcon, TerminalSquareIcon, ArrowUpIcon, ArrowDownIcon,
    FilterIcon, CheckIcon, XCircleIcon, AlertCircleIcon, ZapIcon, CogIcon, DownloadIcon, PlusCircleIcon, TrashIcon, ShieldIcon
} from './icons';
import { ConfirmationModal } from './ConfirmationModal';
import { useUser } from '../contexts/UserContext';
import { useTimeZone } from '../contexts/TimeZoneContext';

interface AgentListProps {
    agents: Agent[];
    assets: Asset[];
    selectedAgentIds: Set<string>;
    upgradingAgentIds: Set<string>;
    onToggleSelection: (agentId: string) => void;
    onSelectAll: (filteredAgentIds: string[]) => void;
    onRestartAgent: (agent: Agent) => void;
    onViewLogs: (agent: Agent) => void;
    onRunDiagnostics: (agent: Agent) => void;
    onViewDetails: (agent: Agent) => void;
    onAuthorizeRemediation: (agent: Agent) => void;
    onViewRemediationLogs: (agent: Agent) => void;
    onBulkRestart: () => void;
    onBulkDiagnostics: () => void;
    onBulkRemediate: () => void;
    onUpdateAgent: (agent: Agent) => void;
    onRegisterAgent: () => void;
    onRemoteControl: (agent: Agent) => void;
    filters: Filter[];
    onDeleteAgent?: (agent: Agent) => void;
}

const statusInfo: Record<AgentStatus, {
    icon: React.ReactNode;
    cardBorder: string;
    badgeClasses: string;
}> = {
    Online: {
        icon: <CheckIcon size={14} className="mr-1.5" />,
        cardBorder: 'border-l-4 border-green-500',
        badgeClasses: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
    },
    Offline: {
        icon: <XCircleIcon size={14} className="mr-1.5" />,
        cardBorder: 'border-l-4 border-gray-500',
        badgeClasses: 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
    },
    Error: {
        icon: <AlertCircleIcon size={14} className="mr-1.5" />,
        cardBorder: 'border-l-4 border-red-500',
        badgeClasses: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300 font-bold',
    },
};

const platformIcons: Record<AgentPlatform, React.ReactNode> = {
    Linux: <LinuxIcon size={20} className="text-gray-500 dark:text-gray-400" />,
    Windows: <WindowsIcon size={20} className="text-blue-500" />,
    macOS: <ServerIcon size={20} className="text-gray-500 dark:text-gray-400" />,
    Docker: <DockerIcon size={20} className="text-sky-600" />,
    Kubernetes: <KubernetesIcon size={20} className="text-indigo-500" />,
    'AWS EC2': <ServerIcon size={20} className="text-orange-500" />,
};

const statusOptions: ('All' | AgentStatus)[] = ['All', 'Online', 'Offline', 'Error'];

const parseLastSeen = (lastSeen: string): number => {
    // A more robust parser
    const now = new Date().getTime();
    try {
        const date = new Date(lastSeen);
        if (!isNaN(date.getTime())) {
            return (now - date.getTime()) / 1000; // seconds ago
        }
    } catch (e) { /* ignore */ }

    // Fallback for simple strings like "3m ago"
    if (!lastSeen || !lastSeen.includes(' ')) return Infinity;
    const parts = lastSeen.split(' ');
    if (parts.length < 2) return Infinity;
    const value = parseInt(parts[0], 10);
    if (isNaN(value)) return Infinity;

    const unit = parts[1].toLowerCase();
    if (unit.startsWith('m')) return value * 60;
    if (unit.startsWith('h')) return value * 60 * 60;
    if (unit.startsWith('d')) return value * 60 * 60 * 24;
    return value; // Assume seconds
};

const AgentCard: React.FC<{
    agent: Agent;
    asset: Asset | undefined;
    isSelected: boolean;
    isUpgrading: boolean;
    onToggleSelection: (agentId: string) => void;
    onRestartAgent: (agent: Agent) => void;
    onViewLogs: (agent: Agent) => void;
    onRunDiagnostics: (agent: Agent) => void;
    onViewDetails: (agent: Agent) => void;
    onAuthorizeRemediation: (agent: Agent) => void;
    onViewRemediationLogs: (agent: Agent) => void;
    onRemoteControl: (agent: Agent) => void;
    canRemediate: boolean;
    canViewLogs: boolean;
    onDeleteAgent?: (agent: Agent) => void;
    onRequestDelete: (agent: Agent) => void;
}> = ({ agent, asset, isSelected, isUpgrading, onToggleSelection, onRestartAgent, onViewLogs, onRunDiagnostics, onViewDetails, onAuthorizeRemediation, onViewRemediationLogs, onRemoteControl, canRemediate, canViewLogs, onDeleteAgent, onRequestDelete }) => {
    const info = statusInfo[agent.status] || statusInfo.Offline;
    const { timeZone } = useTimeZone();

    const handleDeleteClick = (e: React.MouseEvent) => {
        e.stopPropagation();
        onRequestDelete(agent);
    };

    // Rate limiting check
    const now = new Date().getTime();
    const oneHourAgo = now - 60 * 60 * 1000;
    const recentAttempts = (agent.remediationAttempts || []).filter(
        attempt => new Date(attempt.timestamp).getTime() > oneHourAgo
    );
    const remediationDisabled = recentAttempts.length >= 3;
    const hasRemediationAttempts = agent.remediationAttempts && agent.remediationAttempts.length > 0;

    return (
        <div className={`glass rounded-2xl shadow-lg flex flex-col justify-between transition-all duration-300 w-full relative ${info.cardBorder} ${isSelected ? 'ring-2 ring-primary-500 shadow-[0_0_20px_rgba(0,210,255,0.4)]' : 'hover:scale-[1.02] hover:shadow-[0_0_25px_rgba(0,210,255,0.2)]'} ${isUpgrading ? 'opacity-70' : ''}`}>
            <div className="absolute top-4 right-4 z-10">
                <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={(e) => {
                        e.stopPropagation();
                        onToggleSelection(agent.id);
                    }}
                    onClick={(e) => e.stopPropagation()}
                    className="h-5 w-5 rounded text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:checked:bg-primary-500"
                    aria-label={`Select agent ${agent.hostname}`}
                />
            </div>
            <div role="button" tabIndex={0} onClick={() => onViewDetails(agent)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onViewDetails(agent); }} className="p-5 h-full cursor-pointer hover:bg-white/5 dark:hover:bg-gray-700/30 transition-colors rounded-t-2xl">
                <div>
                    <div className="flex justify-between items-start">
                        <div>
                            <h4 className="font-bold text-lg text-gray-900 dark:text-white truncate pr-10">{agent.hostname}</h4>
                            <p className="text-xs text-gray-500 dark:text-gray-400 font-mono mt-1">{agent.ipAddress}</p>
                        </div>
                        <div className="flex items-center">
                            {/* FIX: Wrapped CogIcon in a span to apply the title attribute, resolving a TypeScript error. */}
                            {isUpgrading && <span title="Upgrade in progress"><CogIcon size={16} className="text-amber-500 animate-spin mr-2" /></span>}
                            {agent.tenantId === 'platform-admin' && (
                                <span className="flex items-center text-[10px] font-bold px-2 py-0.5 rounded-full bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-300 shadow-sm border border-purple-200 dark:border-purple-700 uppercase tracking-wider mr-2" title="Belongs to Platform Super Admin">
                                    <ShieldIcon size={12} className="mr-1" />
                                    Super Admin
                                </span>
                            )}
                            <span className={`flex items-center text-xs font-bold px-2.5 py-1 rounded-full ${info.badgeClasses} shadow-sm`}>
                                {info.icon}
                                <span>{agent.status}</span>
                            </span>
                        </div>
                    </div>
                    <div className="mt-4 text-sm text-gray-600 dark:text-gray-300 space-y-2">
                        <div className="flex items-center">
                            <span className="w-24 font-medium text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wide">OS</span>
                            <div className="flex items-center space-x-2 text-gray-800 dark:text-gray-200">
                                {platformIcons[agent.platform]}
                                <span className="font-medium">{asset?.osName || agent.platform}</span>
                            </div>
                        </div>
                        <div className="flex items-center">
                            <span className="w-24 font-medium text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wide">Version</span>
                            <span className="text-gray-800 dark:text-gray-200 font-mono text-xs">{agent.version}</span>
                        </div>
                        <div className="flex items-center">
                            <span className="w-24 font-medium text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wide">Last Seen</span>
                            <span className="text-gray-800 dark:text-gray-200 text-xs">{new Date(agent.lastSeen).toLocaleString(undefined, { timeZone })}</span>
                        </div>
                    </div>
                </div>
            </div>
            <div className="px-5 pb-5">
                <div className="mt-4 pt-4 border-t border-gray-200/50 dark:border-gray-700/50 flex items-center justify-end space-x-2">
                    {canRemediate && agent.status === 'Error' ? (
                        <button
                            onClick={(e) => { e.stopPropagation(); onAuthorizeRemediation(agent); }}
                            disabled={remediationDisabled || isUpgrading}
                            title={isUpgrading ? "Agent is currently being upgraded." : remediationDisabled ? `Remediation limit reached (${recentAttempts.length}/3 in last hour). Try again later.` : "Autonomous Remediation"}
                            className={`flex items-center px-3 py-1.5 text-sm font-semibold text-white bg-gradient-to-r from-primary-600 to-primary-500 rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 shadow-lg shadow-primary-500/30 ${remediationDisabled || isUpgrading ? 'grayscale cursor-not-allowed' : 'hover:from-primary-500 hover:to-primary-400 animate-pulse'}`}
                        >
                            <ZapIcon size={14} className="mr-1.5" />
                            Remediate
                        </button>
                    ) : (
                        <>
                            {hasRemediationAttempts && (
                                <button disabled={isUpgrading} onClick={(e) => { e.stopPropagation(); onViewRemediationLogs(agent); }} className="p-2 rounded-lg text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 dark:text-gray-400 dark:hover:text-indigo-400 dark:hover:bg-indigo-900/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed" title="View Remediation History"><HistoryIcon size={16} /></button>
                            )}
                            {canViewLogs && (
                                <button disabled={isUpgrading} onClick={(e) => { e.stopPropagation(); onViewLogs(agent); }} className="p-2 rounded-lg text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed" title="View Logs"><FileTextIcon size={16} /></button>
                            )}
                            {canRemediate && (
                                <>
                                    <button disabled={isUpgrading || agent.status === 'Offline'} onClick={(e) => { e.stopPropagation(); onRemoteControl(agent); }} className="p-2 rounded-lg text-gray-500 hover:text-purple-600 hover:bg-purple-50 dark:text-gray-400 dark:hover:text-purple-400 dark:hover:bg-purple-900/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed" title="Remote Control Terminal"><TerminalSquareIcon size={16} /></button>
                                    <button disabled={isUpgrading} onClick={(e) => { e.stopPropagation(); onRestartAgent(agent); }} className="p-2 rounded-lg text-gray-500 hover:text-blue-600 hover:bg-blue-50 dark:text-gray-400 dark:hover:text-blue-400 dark:hover:bg-blue-900/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed" title="Restart Agent"><RefreshCwIcon size={16} /></button>
                                    <button disabled={isUpgrading} onClick={(e) => { e.stopPropagation(); onRunDiagnostics(agent); }} className="p-2 rounded-lg text-gray-500 hover:text-green-600 hover:bg-green-50 dark:text-gray-400 dark:hover:text-green-400 dark:hover:bg-green-900/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed" title="Run Diagnostics"><TerminalSquareIcon size={16} /></button>
                                    {onDeleteAgent && (
                                        <button disabled={isUpgrading} onClick={handleDeleteClick} className="p-2 rounded-lg text-gray-500 hover:text-red-600 hover:bg-red-50 dark:text-gray-400 dark:hover:text-red-400 dark:hover:bg-red-900/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed" title="Delete Agent"><TrashIcon size={16} /></button>
                                    )}
                                </>
                            )}
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};


export const AgentList: React.FC<AgentListProps> = (props) => {
    const {
        agents, assets, selectedAgentIds, upgradingAgentIds, onToggleSelection, onSelectAll,
        onRestartAgent, onViewLogs, onRunDiagnostics, onViewDetails, onAuthorizeRemediation, onViewRemediationLogs,
        onBulkRestart, onBulkDiagnostics, onBulkRemediate, onRegisterAgent, onRemoteControl, filters
    } = props;

    const { timeZone } = useTimeZone();

    const { hasPermission } = useUser();
    const canRemediate = hasPermission('remediate:agents');
    const canViewLogs = hasPermission('view:agent_logs');

    const [statusFilter, setStatusFilter] = useState<'All' | AgentStatus>('All');
    const [platformFilter, setPlatformFilter] = useState<'All' | AgentPlatform>('All');
    type SortableKeys = 'hostname' | 'version' | 'lastSeen';
    const [sortConfig, setSortConfig] = useState<{ key: SortableKeys; direction: 'ascending' | 'descending' } | null>({ key: 'lastSeen', direction: 'descending' });
    const [agentToDelete, setAgentToDelete] = useState<Agent | null>(null);

    const uniquePlatforms = useMemo(() => ['All', ...Array.from(new Set(agents.map(a => a.platform)))], [agents]);

    const requestSort = (key: SortableKeys) => {
        let direction: 'ascending' | 'descending' = 'ascending';
        if (sortConfig && sortConfig.key === key && sortConfig.direction === 'ascending') {
            direction = 'descending';
        }
        setSortConfig({ key, direction });
    };

    const getSortIndicator = (key: SortableKeys) => {
        if (!sortConfig || sortConfig.key !== key) return null;
        if (sortConfig.direction === 'ascending') return <ArrowUpIcon size={12} className="ml-1 inline-block" />;
        return <ArrowDownIcon size={12} className="ml-1 inline-block" />;
    };

    const sortedAndFilteredAgents = useMemo(() => {
        let filteredAgents = [...agents];

        if (statusFilter !== 'All') {
            filteredAgents = filteredAgents.filter(agent => agent.status === statusFilter);
        }
        if (platformFilter !== 'All') {
            filteredAgents = filteredAgents.filter(agent => agent.platform === platformFilter);
        }

        if (sortConfig !== null) {
            filteredAgents.sort((a, b) => {
                let valA, valB;
                if (sortConfig.key === 'lastSeen') {
                    valA = parseLastSeen(a.lastSeen);
                    valB = parseLastSeen(b.lastSeen);
                } else {
                    valA = a[sortConfig.key];
                    valB = b[sortConfig.key];
                }

                if (valA < valB) {
                    return sortConfig.direction === 'ascending' ? -1 : 1;
                }
                if (valA > valB) {
                    return sortConfig.direction === 'ascending' ? 1 : -1;
                }
                return 0;
            });
        }

        // Deduplicate agents by ID to prevent key collisions
        const uniqueAgents = Array.from(new Map(filteredAgents.map(a => [a.id, a])).values());

        return uniqueAgents;
    }, [agents, statusFilter, platformFilter, sortConfig]);

    // FIX: Added JSX return statement to fix compile error.
    const filteredAgentIds = useMemo(() => sortedAndFilteredAgents.map(a => a.id), [sortedAndFilteredAgents]);
    const allOnPageSelected = filteredAgentIds.length > 0 && filteredAgentIds.every(id => selectedAgentIds.has(id));

    return (
        <div>
            {/* Filter and Controls Bar with Glassmorphism */}
            <div className="p-4 border-b border-gray-200/50 dark:border-gray-700/50 flex flex-col md:flex-row gap-4 items-center glass rounded-t-xl mb-4 bg-white/50 dark:bg-gray-800/50">
                <div className="relative flex-grow w-full md:w-auto group">
                    <FilterIcon size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-primary-500 transition-colors" />
                    <select
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value as 'All' | AgentStatus)}
                        className="w-full pl-10 pr-4 py-2 bg-white/80 dark:bg-gray-700/80 border border-gray-300 dark:border-gray-600 rounded-lg shadow-sm sm:text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
                    >
                        {statusOptions.map(opt => <option key={opt} value={opt}>{opt === 'All' ? 'All Statuses' : opt}</option>)}
                    </select>
                </div>
                <div className="relative flex-grow w-full md:w-auto group">
                    <FilterIcon size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-primary-500 transition-colors" />
                    <select
                        value={platformFilter}
                        onChange={(e) => setPlatformFilter(e.target.value as 'All' | AgentPlatform)}
                        className="w-full pl-10 pr-4 py-2 bg-white/80 dark:bg-gray-700/80 border border-gray-300 dark:border-gray-600 rounded-lg shadow-sm sm:text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
                    >
                        {uniquePlatforms.map((opt, i) => <option key={`platform-${opt}-${i}`} value={opt}>{opt === 'All' ? 'All Platforms' : opt}</option>)}
                    </select>
                </div>
                <div className="flex-shrink-0 flex items-center space-x-3 bg-white/50 dark:bg-gray-800/50 p-1.5 rounded-lg border border-gray-200 dark:border-gray-700">
                    <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider pl-1">Sort</span>
                    <div className="h-4 w-px bg-gray-300 dark:bg-gray-600 mx-2"></div>
                    <button onClick={() => requestSort('hostname')} className={`text-xs font-medium px-2 py-1 rounded transition-colors ${sortConfig?.key === 'hostname' ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300' : 'text-gray-600 dark:text-gray-300 hover:text-primary-500'}`}>Hostname {getSortIndicator('hostname')}</button>
                    <button onClick={() => requestSort('version')} className={`text-xs font-medium px-2 py-1 rounded transition-colors ${sortConfig?.key === 'version' ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300' : 'text-gray-600 dark:text-gray-300 hover:text-primary-500'}`}>Version {getSortIndicator('version')}</button>
                    <button onClick={() => requestSort('lastSeen')} className={`text-xs font-medium px-2 py-1 rounded transition-colors ${sortConfig?.key === 'lastSeen' ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300' : 'text-gray-600 dark:text-gray-300 hover:text-primary-500'}`}>Last Seen {getSortIndicator('lastSeen')}</button>
                </div>
            </div>

            {canRemediate && selectedAgentIds.size > 0 && (
                <div className="p-4 border border-primary-200 dark:border-primary-800 bg-primary-50/50 dark:bg-primary-900/20 flex flex-col sm:flex-row justify-between items-center gap-4 rounded-lg mb-4 backdrop-blur-sm">
                    <p className="text-sm font-semibold text-primary-800 dark:text-primary-200">{selectedAgentIds.size} agent(s) selected.</p>
                    <div className="flex items-center space-x-3">
                        <button onClick={onBulkRemediate} className="px-4 py-2 text-xs font-bold uppercase tracking-wider text-white bg-primary-600 rounded-lg hover:bg-primary-700 shadow-md shadow-primary-500/20 transition-all">Remediate</button>
                        <button onClick={onBulkRestart} className="px-4 py-2 text-xs font-bold uppercase tracking-wider text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 hover:border-gray-400 shadow-sm dark:bg-gray-800 dark:text-gray-200 dark:border-gray-600 dark:hover:bg-gray-700 transition-all">Restart</button>
                        <button onClick={onBulkDiagnostics} className="px-4 py-2 text-xs font-bold uppercase tracking-wider text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 hover:border-gray-400 shadow-sm dark:bg-gray-800 dark:text-gray-200 dark:border-gray-600 dark:hover:bg-gray-700 transition-all">Diagnostics</button>
                    </div>
                </div>
            )}

            <div className="p-4 pt-0">
                {sortedAndFilteredAgents.length > 0 ? (
                    <>
                        <div className="flex items-center mb-4 pl-1">
                            <input
                                id="select-all-agents"
                                type="checkbox"
                                checked={allOnPageSelected}
                                onChange={() => onSelectAll(filteredAgentIds)}
                                className="h-4 w-4 rounded text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800"
                            />
                            <label htmlFor="select-all-agents" className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300 cursor-pointer select-none">
                                Select all ({filteredAgentIds.length})
                            </label>
                        </div>
                        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
                            {sortedAndFilteredAgents.map(agent => (
                                <AgentCard
                                    key={agent.id}
                                    agent={agent}
                                    asset={assets.find(a => a.id === agent.assetId)}
                                    isSelected={selectedAgentIds.has(agent.id)}
                                    isUpgrading={upgradingAgentIds.has(agent.id)}
                                    onToggleSelection={onToggleSelection}
                                    onRestartAgent={onRestartAgent}
                                    onViewLogs={onViewLogs}
                                    onRunDiagnostics={onRunDiagnostics}
                                    onViewDetails={onViewDetails}
                                    onAuthorizeRemediation={onAuthorizeRemediation}
                                    onViewRemediationLogs={onViewRemediationLogs}
                                    onRemoteControl={onRemoteControl}
                                    canRemediate={canRemediate}
                                    canViewLogs={canViewLogs}
                                    onDeleteAgent={props.onDeleteAgent}
                                    onRequestDelete={setAgentToDelete}
                                />
                            ))}
                        </div>
                    </>
                ) : (
                    <div className="text-center py-24 px-6 border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-2xl bg-gray-50/50 dark:bg-gray-800/30 backdrop-blur-sm">
                        <div className="w-24 h-24 mx-auto bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center mb-6 shadow-inner">
                            <ServerIcon size={48} className="text-gray-400 dark:text-gray-500" strokeWidth={1} />
                        </div>
                        <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                            {filters.length > 0 ? 'No agents match your filter' : 'No agents registered yet'}
                        </h3>
                        <p className="mt-2 text-gray-500 dark:text-gray-400 max-w-md mx-auto mb-8">
                            {filters.length > 0 ? 'Try adjusting your filters or search criteria.' : 'Get started by running the installation script on your hosts or manually registering an agent.'}
                        </p>
                        {filters.length === 0 && (
                            <div className="flex justify-center items-center space-x-4">
                                <button
                                    onClick={() => document.getElementById('agent-installation-section')?.scrollIntoView({ behavior: 'smooth' })}
                                    className="flex items-center px-6 py-3 text-sm font-bold text-white bg-primary-600 rounded-xl hover:bg-primary-700 shadow-lg shadow-primary-500/30 transition-all hover:scale-105"
                                >
                                    <DownloadIcon size={18} className="mr-2" />
                                    Install Agent
                                </button>
                                <button
                                    onClick={onRegisterAgent}
                                    className="flex items-center px-6 py-3 text-sm font-bold text-gray-700 bg-white border border-gray-200 rounded-xl hover:bg-gray-50 hover:border-gray-300 shadow-md dark:bg-gray-800 dark:text-gray-200 dark:border-gray-700 dark:hover:bg-gray-700 transition-all hover:scale-105"
                                >
                                    <PlusCircleIcon size={18} className="mr-2" />
                                    Manual Register
                                </button>
                            </div>
                        )}
                    </div>
                )}
            </div>


            <ConfirmationModal
                isOpen={!!agentToDelete}
                onClose={() => setAgentToDelete(null)}
                onConfirm={() => {
                    if (agentToDelete && props.onDeleteAgent) {
                        props.onDeleteAgent(agentToDelete);
                    }
                }}
                title="Delete Agent"
                message={`Are you sure you want to delete the agent ${agentToDelete?.hostname}? This action cannot be undone.`}
                confirmText="Delete"
                isDestructive={true}
            />
        </div >
    );
};
