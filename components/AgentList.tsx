import React, { useState, useMemo } from 'react';
import { Agent, AgentPlatform, AgentStatus, Asset, Filter } from '../types';
import {
    WindowsIcon, LinuxIcon, DockerIcon, KubernetesIcon, ServerIcon, HistoryIcon,
    FileTextIcon, TerminalSquareIcon, ArrowUpIcon, ArrowDownIcon,
    CogIcon, DownloadIcon, PlusCircleIcon, TrashIcon, ShieldIcon, WifiIcon, ZapIcon
} from './icons';
import { ConfirmationModal } from './ConfirmationModal';
import { useUser } from '../contexts/UserContext';
import { useTimeZone } from '../contexts/TimeZoneContext';
import { flagEmoji, formatGeo } from '../utils/geo';

interface AgentListProps {
    agents: Agent[];
    assets: Asset[];
    selectedAgentIds: Set<string>;
    upgradingAgentIds: Set<string>;
    onToggleSelection: (agentId: string) => void;
    onSelectAll: (filteredAgentIds: string[]) => void;
    onViewLogs: (agent: Agent) => void;
    onRunDiagnostics: (agent: Agent) => void;
    onViewDetails: (agent: Agent) => void;
    onAuthorizeRemediation: (agent: Agent) => void;
    onViewRemediationLogs: (agent: Agent) => void;
    onBulkDiagnostics: () => void;
    onBulkRemediate: () => void;
    onBulkDelete?: () => void;
    onUpdateAgent: (agent: Agent) => void;
    onRegisterAgent: () => void;
    filters: Filter[];
    onDeleteAgent?: (agent: Agent) => void;
    onQuarantineAgent?: (agent: Agent) => void;
    onToggleSoftwareExclusion?: (agent: Agent) => void;
}

const statusPills: Record<AgentStatus, string> = {
    Online: 'text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 ring-emerald-500/20',
    Offline: 'text-gray-700 dark:text-gray-300 bg-gray-500/10 ring-gray-500/20',
    Error: 'text-red-700 dark:text-red-300 bg-red-500/10 ring-red-500/20',
    Quarantined: 'text-amber-700 dark:text-amber-300 bg-amber-500/10 ring-amber-500/20',
};

const statusDots: Record<AgentStatus, string> = {
    Online: 'bg-emerald-500',
    Offline: 'bg-gray-400',
    Error: 'bg-red-500',
    Quarantined: 'bg-amber-500',
};

const platformIcons: Record<AgentPlatform, React.ReactNode> = {
    Linux: <LinuxIcon size={18} className="text-gray-600 dark:text-gray-300" />,
    Windows: <WindowsIcon size={18} className="text-blue-600 dark:text-blue-400" />,
    macOS: <ServerIcon size={18} className="text-gray-600 dark:text-gray-300" />,
    Docker: <DockerIcon size={18} className="text-sky-600 dark:text-sky-400" />,
    Kubernetes: <KubernetesIcon size={18} className="text-blue-600 dark:text-blue-400" />,
    'AWS EC2': <ServerIcon size={18} className="text-orange-600 dark:text-orange-400" />,
};

const statusOptions: ('All' | AgentStatus)[] = ['All', 'Online', 'Offline', 'Error', 'Quarantined'];

// Heartbeat staleness: an agent reported Online is effectively offline after 2 missed minutes
// (4x 30s heartbeat). Cards, the status filter and the dashboard counts all use this.
export const AGENT_OFFLINE_AFTER_SECS = 120;
export const effectiveAgentStatus = (agent: Agent, now = Date.now()): AgentStatus => {
    const lastSeenMs = agent.lastSeen ? new Date(agent.lastSeen).getTime() : 0;
    const staleSecs = lastSeenMs > 0 ? Math.floor((now - lastSeenMs) / 1000) : Infinity;
    return agent.status === 'Online' && staleSecs > AGENT_OFFLINE_AFTER_SECS ? 'Offline' : agent.status;
};

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

const iconButton = 'grid place-items-center h-8 w-8 rounded-lg text-gray-500 dark:text-gray-400 transition-colors disabled:opacity-40 disabled:cursor-not-allowed';
const term = 'text-gray-500 dark:text-gray-400';

const AgentCard: React.FC<{
    agent: Agent;
    asset: Asset | undefined;
    isSelected: boolean;
    isUpgrading: boolean;
    onToggleSelection: (agentId: string) => void;
    onViewLogs: (agent: Agent) => void;
    onRunDiagnostics: (agent: Agent) => void;
    onViewDetails: (agent: Agent) => void;
    onAuthorizeRemediation: (agent: Agent) => void;
    onViewRemediationLogs: (agent: Agent) => void;
    canRemediate: boolean;
    canViewLogs: boolean;
    onDeleteAgent?: (agent: Agent) => void;
    onQuarantineAgent?: (agent: Agent) => void;
    onToggleSoftwareExclusion?: (agent: Agent) => void;
    onRequestDelete: (agent: Agent) => void;
}> = ({ agent, asset, isSelected, isUpgrading, onToggleSelection, onViewLogs, onRunDiagnostics, onViewDetails, onAuthorizeRemediation, onViewRemediationLogs, canRemediate, canViewLogs, onDeleteAgent, onQuarantineAgent, onToggleSoftwareExclusion, onRequestDelete }) => {
    const { timeZone } = useTimeZone();

    const handleDeleteClick = (e: React.MouseEvent) => {
        e.stopPropagation();
        onRequestDelete(agent);
    };

    const now = new Date().getTime();
    const lastSeenMs = agent.lastSeen ? new Date(agent.lastSeen).getTime() : 0;
    const staleSecs = lastSeenMs > 0 ? Math.floor((now - lastSeenMs) / 1000) : Infinity;
    const _OFFLINE_THRESHOLD = AGENT_OFFLINE_AFTER_SECS;
    const effectiveStatus = effectiveAgentStatus(agent, now);
    const hearbeatColor = staleSecs < _OFFLINE_THRESHOLD
        ? 'text-emerald-700 dark:text-emerald-300' : staleSecs < 600
        ? 'text-amber-700 dark:text-amber-300' : 'text-red-700 dark:text-red-300';
    const hearbeatDot = staleSecs < _OFFLINE_THRESHOLD
        ? 'bg-emerald-500 animate-pulse' : staleSecs < 600
        ? 'bg-amber-400' : 'bg-red-500';
    const lastSeenLabel = (() => {
        if (!lastSeenMs) return '—';
        if (staleSecs < 60) return `${staleSecs}s ago`;
        if (staleSecs < 3600) return `${Math.floor(staleSecs / 60)}m ago`;
        if (staleSecs < 86400) return `${Math.floor(staleSecs / 3600)}h ago`;
        return new Date(agent.lastSeen).toLocaleDateString(undefined, { timeZone });
    })();

    // Rate limiting check
    const oneHourAgo = now - 60 * 60 * 1000;
    const recentAttempts = (agent.remediationAttempts || []).filter(
        attempt => new Date(attempt.timestamp).getTime() > oneHourAgo
    );
    const remediationDisabled = recentAttempts.length >= 3;
    const hasRemediationAttempts = agent.remediationAttempts && agent.remediationAttempts.length > 0;
    const isExcluded = !!(agent as any).excludeFromSoftwareOps;

    return (
        <div className={`relative flex flex-col rounded-2xl bg-white dark:bg-gray-800 border shadow-card transition-colors ${isSelected
            ? 'border-primary-500/50 ring-1 ring-primary-500/40'
            : 'border-gray-200/80 dark:border-white/[0.07] hover:border-primary-500/30'} ${isUpgrading ? 'opacity-70' : ''}`}>
            <input
                type="checkbox"
                checked={isSelected}
                onChange={(e) => {
                    e.stopPropagation();
                    onToggleSelection(agent.id);
                }}
                onClick={(e) => e.stopPropagation()}
                className="absolute top-4 right-4 z-10 h-4 w-4 rounded accent-cyan-600 cursor-pointer"
                aria-label={`Select agent ${agent.hostname}`}
            />
            <div role="button" tabIndex={0} onClick={() => onViewDetails(agent)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onViewDetails(agent); }}
                aria-label={`${agent.hostname}, ${effectiveStatus}. Open details`}
                className="p-5 flex-1 cursor-pointer rounded-t-2xl hover:bg-gray-50/70 dark:hover:bg-white/[0.02] transition-colors">
                <div className="flex items-start gap-3 pr-7">
                    <span className="grid place-items-center h-10 w-10 flex-shrink-0 rounded-xl bg-gray-100 dark:bg-white/[0.05] ring-1 ring-inset ring-gray-200/70 dark:ring-white/[0.06]">
                        {platformIcons[agent.platform] ?? <ServerIcon size={18} className="text-gray-500" />}
                    </span>
                    <div className="min-w-0">
                        <h4 className="font-semibold text-[15px] text-gray-900 dark:text-white truncate">{agent.hostname}</h4>
                        <p className="text-xs text-gray-500 dark:text-gray-400 font-mono mt-0.5 truncate">{agent.ipAddress}</p>
                    </div>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold ring-1 ring-inset ${statusPills[effectiveStatus] || statusPills.Offline}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${statusDots[effectiveStatus] || statusDots.Offline}`} aria-hidden="true" />
                        {effectiveStatus}
                    </span>
                    {isUpgrading && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold text-amber-700 dark:text-amber-300 bg-amber-500/10 ring-1 ring-inset ring-amber-500/20" title="Upgrade in progress">
                            <CogIcon size={11} className="animate-spin" /> Upgrading
                        </span>
                    )}
                    {agent.tenantId === 'platform-admin' && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold text-primary-700 dark:text-primary-300 bg-primary-500/10 ring-1 ring-inset ring-primary-500/20" title="Belongs to Platform Super Admin">
                            <ShieldIcon size={11} /> Super Admin
                        </span>
                    )}
                    {isExcluded && (
                        <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold text-amber-700 dark:text-amber-300 bg-amber-500/10 ring-1 ring-inset ring-amber-500/20" title="Excluded from software operations">
                            No software ops
                        </span>
                    )}
                </div>
                <dl className="mt-4 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-[13px] text-gray-800 dark:text-gray-200">
                    <dt className={term}>OS</dt>
                    <dd className="truncate">{asset?.osName || agent.platform}</dd>
                    <dt className={term}>Version</dt>
                    <dd className="font-mono text-xs self-center">{agent.version}</dd>
                    <dt className={term}>Last seen</dt>
                    <dd className="flex items-center gap-1.5">
                        <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${hearbeatDot}`} title={agent.lastSeen ? new Date(agent.lastSeen).toLocaleString(undefined, { timeZone }) : 'Never'} />
                        <span className={`text-xs font-medium ${hearbeatColor}`}>{lastSeenLabel}</span>
                    </dd>
                    {agent.publicIp && (
                        <>
                            <dt className={term}>Public IP</dt>
                            <dd className="font-mono text-xs self-center truncate">{agent.publicIp}</dd>
                        </>
                    )}
                    {agent.geo && formatGeo(agent.geo) && (
                        <>
                            <dt className={term}>Location</dt>
                            <dd className="text-xs flex items-center gap-1.5 min-w-0 self-center">
                                {agent.geo.country_code && <span aria-hidden>{flagEmoji(agent.geo.country_code)}</span>}
                                <span className="truncate">{formatGeo(agent.geo)}</span>
                                {agent.geo.vpn_heuristic === true && (
                                    <span className="flex-shrink-0 inline-flex items-center gap-1 px-1.5 py-px rounded-full text-[10px] font-semibold text-amber-700 dark:text-amber-300 bg-amber-500/10 ring-1 ring-inset ring-amber-500/20">
                                        <WifiIcon size={10} />
                                        likely VPN/hosting
                                    </span>
                                )}
                            </dd>
                        </>
                    )}
                </dl>
            </div>
            <div className="px-3 py-2 border-t border-gray-100 dark:border-white/[0.06] flex items-center justify-end gap-1 min-h-[49px]">
                {canRemediate && agent.status === 'Error' ? (
                    <button
                        onClick={(e) => { e.stopPropagation(); onAuthorizeRemediation(agent); }}
                        disabled={remediationDisabled || isUpgrading}
                        title={isUpgrading ? "Agent is currently being upgraded." : remediationDisabled ? `Remediation limit reached (${recentAttempts.length}/3 in last hour). Try again later.` : "Autonomous Remediation"}
                        className="flex items-center gap-1.5 h-8 px-3 text-xs font-semibold text-white rounded-lg bg-primary-600 hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <ZapIcon size={13} />
                        Remediate
                    </button>
                ) : (
                    <>
                        {hasRemediationAttempts && (
                            <button disabled={isUpgrading} onClick={(e) => { e.stopPropagation(); onViewRemediationLogs(agent); }} className={`${iconButton} hover:text-primary-700 hover:bg-primary-500/10 dark:hover:text-primary-300`} title="View Remediation History" aria-label={`Remediation history for ${agent.hostname}`}><HistoryIcon size={16} /></button>
                        )}
                        {canViewLogs && (
                            <button disabled={isUpgrading} onClick={(e) => { e.stopPropagation(); onViewLogs(agent); }} className={`${iconButton} hover:text-gray-900 hover:bg-gray-900/[0.05] dark:hover:text-white dark:hover:bg-white/[0.07]`} title="View Logs" aria-label={`Logs for ${agent.hostname}`}><FileTextIcon size={16} /></button>
                        )}
                        {canRemediate && (
                            <>
                                <button disabled={isUpgrading} onClick={(e) => { e.stopPropagation(); onRunDiagnostics(agent); }} className={`${iconButton} hover:text-emerald-700 hover:bg-emerald-500/10 dark:hover:text-emerald-300`} title="Run Diagnostics" aria-label={`Run diagnostics on ${agent.hostname}`}><TerminalSquareIcon size={16} /></button>
                                {onQuarantineAgent && agent.status !== 'Quarantined' && (
                                    <button disabled={isUpgrading} onClick={(e) => { e.stopPropagation(); onQuarantineAgent(agent); }} className={`${iconButton} hover:text-amber-700 hover:bg-amber-500/10 dark:hover:text-amber-300`} title="Quarantine Agent" aria-label={`Quarantine ${agent.hostname}`}><ShieldIcon size={16} /></button>
                                )}
                                {onToggleSoftwareExclusion && (
                                    <button
                                        disabled={isUpgrading}
                                        onClick={(e) => { e.stopPropagation(); onToggleSoftwareExclusion(agent); }}
                                        aria-pressed={isExcluded}
                                        className={`${iconButton} ${isExcluded ? 'text-amber-700 dark:text-amber-300 bg-amber-500/10' : 'hover:text-amber-700 hover:bg-amber-500/10 dark:hover:text-amber-300'}`}
                                        title={isExcluded ? 'Remove software exclusion' : 'Exclude from software operations'}
                                        aria-label={isExcluded ? `Include ${agent.hostname} in software operations` : `Exclude ${agent.hostname} from software operations`}
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                            <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
                                            <line x1="8" y1="21" x2="16" y2="21"></line>
                                            <line x1="12" y1="17" x2="12" y2="21"></line>
                                            {isExcluded && <line x1="4" y1="4" x2="20" y2="20" strokeWidth="2.5"></line>}
                                        </svg>
                                    </button>
                                )}
                                {onDeleteAgent && (
                                    <button disabled={isUpgrading} onClick={handleDeleteClick} className={`${iconButton} hover:text-red-700 hover:bg-red-500/10 dark:hover:text-red-300`} title="Delete Agent" aria-label={`Delete ${agent.hostname}`}><TrashIcon size={16} /></button>
                                )}
                            </>
                        )}
                    </>
                )}
            </div>
        </div>
    );
};


export const AgentList: React.FC<AgentListProps> = (props) => {
    const {
        agents, assets, selectedAgentIds, upgradingAgentIds, onToggleSelection, onSelectAll,
        onViewLogs, onRunDiagnostics, onViewDetails, onAuthorizeRemediation, onViewRemediationLogs,
        onBulkDiagnostics, onBulkRemediate, onBulkDelete, onRegisterAgent, filters
    } = props;

    const { hasPermission } = useUser();
    const canRemediate = hasPermission('remediate:agents');
    const canViewLogs = hasPermission('view:agent_logs');

    const [statusFilter, setStatusFilter] = useState<'All' | AgentStatus>('All');
    const [platformFilter, setPlatformFilter] = useState<'All' | AgentPlatform>('All');
    type SortableKeys = 'hostname' | 'version' | 'lastSeen';
    const [sortConfig, setSortConfig] = useState<{ key: SortableKeys; direction: 'ascending' | 'descending' } | null>({ key: 'lastSeen', direction: 'descending' });
    const [agentToDelete, setAgentToDelete] = useState<Agent | null>(null);

    const uniquePlatforms = useMemo(() => ['All', ...Array.from(new Set(agents.map(a => a.platform)))], [agents]);

    const statusCounts = useMemo(() => {
        const now = Date.now();
        const counts: Record<string, number> = { All: agents.length };
        agents.forEach(a => { const s = effectiveAgentStatus(a, now); counts[s] = (counts[s] || 0) + 1; });
        return counts;
    }, [agents]);

    const requestSort = (key: SortableKeys) => {
        let direction: 'ascending' | 'descending' = 'ascending';
        if (sortConfig && sortConfig.key === key && sortConfig.direction === 'ascending') {
            direction = 'descending';
        }
        setSortConfig({ key, direction });
    };

    const getSortIndicator = (key: SortableKeys) => {
        if (!sortConfig || sortConfig.key !== key) return null;
        if (sortConfig.direction === 'ascending') return <ArrowUpIcon size={12} className="inline-block" />;
        return <ArrowDownIcon size={12} className="inline-block" />;
    };

    const sortedAndFilteredAgents = useMemo(() => {
        let filteredAgents = [...agents];

        const now = Date.now();
        if (statusFilter !== 'All') {
            filteredAgents = filteredAgents.filter(agent => effectiveAgentStatus(agent, now) === statusFilter);
        }
        if (platformFilter !== 'All') {
            filteredAgents = filteredAgents.filter(agent => agent.platform === platformFilter);
        }
        // Filters set by a command ("show agents in error"): status and platform, any case.
        filters.forEach(f => {
            const want = String(f.value).toLowerCase();
            if (f.type === 'status') filteredAgents = filteredAgents.filter(a => effectiveAgentStatus(a, now).toLowerCase() === want);
            if (f.type === 'platform') filteredAgents = filteredAgents.filter(a => String(a.platform).toLowerCase() === want);
        });

        if (sortConfig !== null) {
            filteredAgents.sort((a, b) => {
                let valA, valB;
                if (sortConfig.key === 'lastSeen') {
                    valA = parseLastSeen(a.lastSeen);
                    valB = parseLastSeen(b.lastSeen);
                } else {
                    // Numeric-aware, so version 2.1.10 sorts after 2.1.9.
                    const order = String(a[sortConfig.key] ?? '').localeCompare(String(b[sortConfig.key] ?? ''), undefined, { numeric: true, sensitivity: 'base' });
                    return sortConfig.direction === 'ascending' ? order : -order;
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
    }, [agents, statusFilter, platformFilter, sortConfig, filters]);

    const filteredAgentIds = useMemo(() => sortedAndFilteredAgents.map(a => a.id), [sortedAndFilteredAgents]);
    const allOnPageSelected = filteredAgentIds.length > 0 && filteredAgentIds.every(id => selectedAgentIds.has(id));

    const sortButton = (key: SortableKeys, label: string) => (
        <button
            onClick={() => requestSort(key)}
            aria-pressed={sortConfig?.key === key}
            className={`flex items-center gap-1 whitespace-nowrap h-8 px-2.5 rounded-[10px] text-xs font-medium transition-colors ${sortConfig?.key === key
                ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'}`}
        >
            {label} {getSortIndicator(key)}
        </button>
    );

    return (
        <div>
            <div className="px-5 py-3 border-b border-gray-100 dark:border-white/[0.06] flex flex-col xl:flex-row xl:items-center gap-3">
                <div role="group" aria-label="Filter by status" className="inline-flex self-start p-0.5 rounded-xl overflow-x-auto max-w-full bg-gray-100 dark:bg-white/[0.05] ring-1 ring-inset ring-gray-200/70 dark:ring-white/[0.06]">
                    {statusOptions.map(opt => (
                        <button
                            key={opt}
                            onClick={() => setStatusFilter(opt)}
                            aria-pressed={statusFilter === opt}
                            className={`flex items-center gap-1.5 whitespace-nowrap h-8 px-2.5 rounded-[10px] text-xs font-medium transition-colors ${statusFilter === opt
                                ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
                                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'}`}
                        >
                            {opt !== 'All' && <span className={`h-1.5 w-1.5 rounded-full ${statusDots[opt]}`} aria-hidden="true" />}
                            {opt}
                            <span className="tabular-nums text-gray-500 dark:text-gray-400">{statusCounts[opt] || 0}</span>
                        </button>
                    ))}
                </div>
                <select
                    value={platformFilter}
                    onChange={(e) => setPlatformFilter(e.target.value as 'All' | AgentPlatform)}
                    aria-label="Platform"
                    className="h-9 pl-3 pr-8 text-[13px] font-medium rounded-xl text-gray-700 dark:text-gray-200 bg-white dark:bg-white/[0.04] border border-gray-200 dark:border-white/10 focus:outline-none focus:border-primary-500 self-start"
                >
                    {uniquePlatforms.map((opt, i) => <option key={`platform-${opt}-${i}`} value={opt}>{opt === 'All' ? 'All platforms' : opt}</option>)}
                </select>
                <div role="group" aria-label="Sort by" className="xl:ml-auto inline-flex self-start items-center max-w-full overflow-x-auto p-0.5 rounded-xl bg-gray-100 dark:bg-white/[0.05] ring-1 ring-inset ring-gray-200/70 dark:ring-white/[0.06]">
                    <span className="px-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Sort</span>
                    {sortButton('hostname', 'Hostname')}
                    {sortButton('version', 'Version')}
                    {sortButton('lastSeen', 'Last seen')}
                </div>
            </div>

            {canRemediate && selectedAgentIds.size > 0 && (
                <div role="region" aria-label="Bulk actions" className="mx-5 mt-4 flex flex-wrap items-center gap-2 px-2.5 py-1.5 rounded-xl bg-primary-500/[0.08] ring-1 ring-inset ring-primary-500/25">
                    <span className="text-xs font-semibold text-primary-700 dark:text-primary-300 tabular-nums">{selectedAgentIds.size} selected</span>
                    <button onClick={onBulkRemediate} className="ml-auto flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs font-semibold text-white bg-primary-600 hover:bg-primary-700 transition-colors">
                        <ZapIcon size={13} /> Remediate
                    </button>
                    <button onClick={onBulkDiagnostics} className="flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-900/[0.05] dark:hover:bg-white/[0.07] transition-colors">
                        <TerminalSquareIcon size={13} /> Diagnostics
                    </button>
                    {onBulkDelete && (
                        <button onClick={onBulkDelete} className="flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs font-medium text-red-700 dark:text-red-300 hover:bg-red-500/10 transition-colors">
                            <TrashIcon size={13} /> Delete
                        </button>
                    )}
                </div>
            )}

            <div className="p-5">
                {sortedAndFilteredAgents.length > 0 ? (
                    <>
                        <div className="flex items-center mb-4">
                            <input
                                id="select-all-agents"
                                type="checkbox"
                                checked={allOnPageSelected}
                                onChange={() => onSelectAll(filteredAgentIds)}
                                className="h-4 w-4 rounded accent-cyan-600 cursor-pointer"
                            />
                            <label htmlFor="select-all-agents" className="ml-2 text-[13px] font-medium text-gray-700 dark:text-gray-300 cursor-pointer select-none">
                                Select all ({filteredAgentIds.length})
                            </label>
                        </div>
                        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
                            {sortedAndFilteredAgents.map(agent => (
                                <AgentCard
                                    key={agent.id}
                                    agent={agent}
                                    asset={assets.find(a => a.id === agent.assetId)}
                                    isSelected={selectedAgentIds.has(agent.id)}
                                    isUpgrading={upgradingAgentIds.has(agent.id)}
                                    onToggleSelection={onToggleSelection}
                                    onViewLogs={onViewLogs}
                                    onRunDiagnostics={onRunDiagnostics}
                                    onViewDetails={onViewDetails}
                                    onAuthorizeRemediation={onAuthorizeRemediation}
                                    onViewRemediationLogs={onViewRemediationLogs}
                                    canRemediate={canRemediate}
                                    canViewLogs={canViewLogs}
                                    onDeleteAgent={props.onDeleteAgent}
                                    onQuarantineAgent={props.onQuarantineAgent}
                                    onToggleSoftwareExclusion={props.onToggleSoftwareExclusion}
                                    onRequestDelete={setAgentToDelete}
                                />
                            ))}
                        </div>
                    </>
                ) : (
                    <div className="py-14 text-center">
                        <ServerIcon size={28} className="mx-auto text-gray-400" />
                        <h3 className="mt-3 text-sm font-medium text-gray-700 dark:text-gray-300">
                            {agents.length > 0 ? 'No agents match these filters' : 'No agents registered yet'}
                        </h3>
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 max-w-md mx-auto">
                            {agents.length > 0 ? 'Pick another status or platform to see them.' : 'Get started by running the installation script on your hosts or manually registering an agent.'}
                        </p>
                        {agents.length > 0 && (
                            <button
                                onClick={() => { setStatusFilter('All'); setPlatformFilter('All'); }}
                                className="mt-5 h-9 px-4 text-sm font-semibold text-white rounded-xl bg-primary-600 hover:bg-primary-700"
                            >
                                Show all agents
                            </button>
                        )}
                        {agents.length === 0 && (
                            <div className="mt-5 flex justify-center items-center gap-2">
                                <button
                                    onClick={() => document.getElementById('agent-installation-section')?.scrollIntoView({ behavior: 'smooth' })}
                                    className="flex items-center gap-2 h-9 px-4 text-sm font-semibold text-white rounded-xl bg-primary-600 hover:bg-primary-700"
                                >
                                    <DownloadIcon size={15} />
                                    Install Agent
                                </button>
                                <button
                                    onClick={onRegisterAgent}
                                    className="flex items-center gap-2 h-9 px-4 text-sm font-medium text-gray-700 dark:text-gray-200 glass rounded-xl"
                                >
                                    <PlusCircleIcon size={15} />
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
        </div>
    );
};
