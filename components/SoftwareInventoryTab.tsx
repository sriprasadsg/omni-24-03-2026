import React, { useState, useMemo } from 'react';
import { SearchIcon, ChevronDownIcon, ChevronRightIcon, TrashIcon, RefreshCwIcon, AlertTriangleIcon, CheckIcon, XIcon } from './icons';

interface AgentEntry {
    agent_id: string;
    agent_name: string;
    version: string;
    latest_version?: string;
    is_outdated: boolean;
    last_scanned: string;
}

interface SoftwareEntry {
    name: string;
    agent_count: number;
    versions: string[];
    pkg_type: string;
    is_outdated: boolean;
    agents: AgentEntry[];
    last_scanned: string;
}

interface Props {
    inventory: SoftwareEntry[];
    loading: boolean;
    onRefresh: () => void;
    onUninstall: (packageId: string, agentIds: string[]) => void;
}

const PKG_BADGE: Record<string, string> = {
    winget: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
    apt: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
    dnf: 'bg-green-500/20 text-green-300 border-green-500/30',
    rpm: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
    pip: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
    unknown: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
};

export const SoftwareInventoryTab: React.FC<Props> = ({ inventory, loading, onRefresh, onUninstall }) => {
    const [search, setSearch] = useState('');
    const [filter, setFilter] = useState<'all' | 'outdated'>('all');
    const [expanded, setExpanded] = useState<Set<string>>(new Set());
    const [confirmEntry, setConfirmEntry] = useState<{ name: string; agentIds: string[] } | null>(null);
    const [selectedAgentIds, setSelectedAgentIds] = useState<Record<string, Set<string>>>({});

    const filtered = useMemo(() => {
        let list = inventory;
        if (filter === 'outdated') list = list.filter(s => s.is_outdated);
        if (search.trim()) {
            const q = search.toLowerCase();
            list = list.filter(s => s.name.toLowerCase().includes(q) || s.pkg_type.toLowerCase().includes(q));
        }
        return list;
    }, [inventory, search, filter]);

    const toggleExpand = (name: string) => {
        setExpanded(prev => {
            const s = new Set(prev);
            s.has(name) ? s.delete(name) : s.add(name);
            return s;
        });
    };

    const toggleAgentSelection = (swName: string, agentId: string) => {
        setSelectedAgentIds(prev => {
            const existing = new Set(prev[swName] || []);
            existing.has(agentId) ? existing.delete(agentId) : existing.add(agentId);
            return { ...prev, [swName]: existing };
        });
    };

    const getSelectedAgents = (entry: SoftwareEntry): string[] => {
        const sel = selectedAgentIds[entry.name];
        if (sel && sel.size > 0) return Array.from(sel);
        return entry.agents.map(a => a.agent_id);
    };

    const handleUninstallClick = (entry: SoftwareEntry) => {
        const agentIds = getSelectedAgents(entry);
        setConfirmEntry({ name: entry.name, agentIds });
    };

    const outdatedCount = inventory.filter(s => s.is_outdated).length;

    return (
        <div className="flex flex-col space-y-4 h-full">
            {/* Toolbar */}
            <div className="flex items-center gap-3 flex-shrink-0">
                <div className="relative flex-1 max-w-sm">
                    <SearchIcon size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                    <input
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        placeholder="Search software..."
                        className="w-full pl-8 pr-3 py-2 text-sm rounded-lg bg-slate-800 border border-slate-700 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500/60"
                    />
                </div>
                <div className="flex rounded-lg overflow-hidden border border-slate-700">
                    {(['all', 'outdated'] as const).map(f => (
                        <button
                            key={f}
                            onClick={() => setFilter(f)}
                            className={`px-3 py-2 text-xs font-medium transition-colors ${filter === f ? 'bg-slate-600 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-700'}`}
                        >
                            {f === 'all' ? `All (${inventory.length})` : `Outdated (${outdatedCount})`}
                        </button>
                    ))}
                </div>
                <button
                    onClick={onRefresh}
                    disabled={loading}
                    className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
                    title="Refresh inventory"
                >
                    <RefreshCwIcon size={15} className={loading ? 'animate-spin' : ''} />
                </button>
                <span className="text-xs text-slate-500 ml-auto">{filtered.length} package{filtered.length !== 1 ? 's' : ''}</span>
            </div>

            {/* Table */}
            <div className="flex-1 overflow-y-auto rounded-xl border border-slate-700/60 bg-slate-900/40">
                {loading ? (
                    <div className="flex items-center justify-center h-48 text-slate-500 gap-2">
                        <RefreshCwIcon size={18} className="animate-spin" />
                        <span className="text-sm">Loading inventory…</span>
                    </div>
                ) : filtered.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-48 text-slate-500 gap-2">
                        <span className="text-2xl">📦</span>
                        <span className="text-sm">{search ? 'No matching software found' : 'No software inventory collected yet'}</span>
                        <span className="text-xs text-slate-600">Agents send inventory on each heartbeat</span>
                    </div>
                ) : (
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-slate-700/60 text-left">
                                <th className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider w-8"></th>
                                <th className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Package</th>
                                <th className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Type</th>
                                <th className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Version(s)</th>
                                <th className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider text-center">Agents</th>
                                <th className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Status</th>
                                <th className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map(entry => {
                                const isExpanded = expanded.has(entry.name);
                                const selCount = (selectedAgentIds[entry.name]?.size) || 0;
                                return (
                                    <React.Fragment key={entry.name}>
                                        <tr
                                            className="border-b border-slate-800/60 hover:bg-slate-800/40 transition-colors group cursor-pointer"
                                            onClick={() => toggleExpand(entry.name)}
                                        >
                                            <td className="px-4 py-3 text-slate-500">
                                                {isExpanded
                                                    ? <ChevronDownIcon size={14} />
                                                    : <ChevronRightIcon size={14} />}
                                            </td>
                                            <td className="px-4 py-3 font-medium text-slate-200">{entry.name}</td>
                                            <td className="px-4 py-3">
                                                <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${PKG_BADGE[entry.pkg_type] ?? PKG_BADGE.unknown}`}>
                                                    {entry.pkg_type}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 text-slate-400 text-xs">
                                                {entry.versions.slice(0, 2).join(', ')}
                                                {entry.versions.length > 2 && ` +${entry.versions.length - 2} more`}
                                            </td>
                                            <td className="px-4 py-3 text-center">
                                                <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-slate-700 text-slate-300 text-xs font-bold">
                                                    {entry.agent_count}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3">
                                                {entry.is_outdated ? (
                                                    <span className="flex items-center gap-1 text-amber-400 text-xs">
                                                        <AlertTriangleIcon size={12} /> Outdated on some agents
                                                    </span>
                                                ) : (
                                                    <span className="flex items-center gap-1 text-green-400 text-xs">
                                                        <CheckIcon size={12} /> Up to date
                                                    </span>
                                                )}
                                            </td>
                                            <td className="px-4 py-3 text-right" onClick={e => e.stopPropagation()}>
                                                <button
                                                    onClick={() => handleUninstallClick(entry)}
                                                    className="px-3 py-1.5 text-xs font-medium rounded-lg bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20 transition-colors flex items-center gap-1 ml-auto"
                                                    title={selCount > 0 ? `Uninstall from ${selCount} selected agent(s)` : `Uninstall from all ${entry.agent_count} agent(s)`}
                                                >
                                                    <TrashIcon size={12} />
                                                    {selCount > 0 ? `Uninstall (${selCount})` : 'Uninstall All'}
                                                </button>
                                            </td>
                                        </tr>

                                        {/* Expanded agent rows */}
                                        {isExpanded && (
                                            <tr className="border-b border-slate-800/60 bg-slate-800/20">
                                                <td colSpan={7} className="px-8 py-3">
                                                    <div className="space-y-1.5">
                                                        <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2">
                                                            Agents with this package — select to uninstall from specific agents
                                                        </p>
                                                        {entry.agents.map(agent => {
                                                            const isSel = selectedAgentIds[entry.name]?.has(agent.agent_id) ?? false;
                                                            return (
                                                                <div
                                                                    key={agent.agent_id}
                                                                    onClick={() => toggleAgentSelection(entry.name, agent.agent_id)}
                                                                    className={`flex items-center justify-between rounded-lg px-3 py-2 cursor-pointer transition-colors ${isSel ? 'bg-red-500/10 border border-red-500/30' : 'bg-slate-800/60 border border-transparent hover:border-slate-600'}`}
                                                                >
                                                                    <div className="flex items-center gap-2.5">
                                                                        <div className={`w-4 h-4 rounded flex items-center justify-center border ${isSel ? 'bg-red-500 border-red-500' : 'border-slate-600'}`}>
                                                                            {isSel && <CheckIcon size={10} className="text-white" />}
                                                                        </div>
                                                                        <span className="text-sm text-slate-200 font-medium">{agent.agent_name}</span>
                                                                        <span className="text-xs text-slate-500">{agent.version}</span>
                                                                        {agent.is_outdated && agent.latest_version && (
                                                                            <span className="text-xs text-amber-400">→ {agent.latest_version} available</span>
                                                                        )}
                                                                    </div>
                                                                    {agent.last_scanned && (
                                                                        <span className="text-[10px] text-slate-600">
                                                                            scanned {new Date(agent.last_scanned).toLocaleDateString()}
                                                                        </span>
                                                                    )}
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                </td>
                                            </tr>
                                        )}
                                    </React.Fragment>
                                );
                            })}
                        </tbody>
                    </table>
                )}
            </div>

            {/* Confirm uninstall dialog */}
            {confirmEntry && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog">
                    <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setConfirmEntry(null)} />
                    <div className="relative w-full max-w-md rounded-2xl shadow-2xl overflow-hidden"
                        style={{ background: 'rgba(12,12,30,0.97)', border: '1px solid rgba(255,255,255,0.10)' }}>
                        <div className="p-5 border-b border-white/[0.07] flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-red-500/15 border border-red-500/30">
                                    <TrashIcon size={16} className="text-red-400" />
                                </div>
                                <div>
                                    <p className="text-[10px] font-semibold uppercase tracking-widest text-red-400/70">Confirm Uninstall</p>
                                    <p className="text-sm font-bold text-white">{confirmEntry.name}</p>
                                </div>
                            </div>
                            <button onClick={() => setConfirmEntry(null)} className="p-1.5 rounded-lg text-slate-500 hover:text-white hover:bg-white/[0.08] transition-all">
                                <XIcon size={15} />
                            </button>
                        </div>
                        <div className="p-5 space-y-3">
                            <p className="text-sm text-slate-300">
                                This will uninstall <span className="text-white font-semibold">{confirmEntry.name}</span> from{' '}
                                <span className="text-red-400 font-semibold">{confirmEntry.agentIds.length} agent{confirmEntry.agentIds.length !== 1 ? 's' : ''}</span>.
                            </p>
                            <p className="text-xs text-slate-500">The agent will execute the uninstall silently. This action cannot be undone automatically.</p>
                        </div>
                        <div className="px-5 py-4 flex gap-3 border-t border-white/[0.06]">
                            <button
                                onClick={() => setConfirmEntry(null)}
                                className="flex-1 py-2 rounded-xl text-sm font-medium text-slate-400 hover:text-white hover:bg-white/[0.07] transition-all border border-white/[0.07]"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={() => {
                                    onUninstall(confirmEntry.name, confirmEntry.agentIds);
                                    setConfirmEntry(null);
                                    // Clear agent selection for this package after uninstall
                                    setSelectedAgentIds(prev => { const n = { ...prev }; delete n[confirmEntry.name]; return n; });
                                }}
                                className="flex-1 py-2 rounded-xl text-sm font-semibold bg-red-600 hover:bg-red-500 text-white transition-colors"
                            >
                                Uninstall Now
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default SoftwareInventoryTab;
