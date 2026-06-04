import React from 'react';
import { SearchIcon, ServerIcon } from './icons';
import { Agent } from '../types';

interface Props {
    filteredAgents: Agent[];
    selectedAgentIds: Set<string>;
    filter: string;
    onFilterChange: (value: string) => void;
    onSelectAll: () => void;
    onToggle: (id: string) => void;
}

export function SoftwareAgentSelector({
    filteredAgents, selectedAgentIds, filter, onFilterChange, onSelectAll, onToggle
}: Props) {
    return (
        <div className="col-span-8 flex flex-col min-h-0">
            <div className="glass-panel flex-1 flex flex-col min-h-0 overflow-hidden">
                <div className="p-4 border-b border-slate-700/50 flex items-center justify-between">
                    <div className="relative w-64">
                        <SearchIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400 w-4 h-4" />
                        <input
                            type="text"
                            placeholder="Filter agents..."
                            value={filter}
                            onChange={(e) => onFilterChange(e.target.value)}
                            className="w-full bg-slate-900 border border-slate-700/50 rounded pl-9 pr-4 py-1.5 focus:outline-none focus:border-blue-500/50"
                        />
                    </div>
                    <div className="text-sm text-slate-400">Showing {filteredAgents.length} agents</div>
                </div>
                <div className="flex-1 overflow-y-auto">
                    <table className="w-full text-left border-collapse">
                        <thead className="bg-slate-900/50 sticky top-0 z-10 backdrop-blur-md">
                            <tr>
                                <th className="p-4 w-12 text-center">
                                    <input
                                        type="checkbox"
                                        checked={filteredAgents.length > 0 && selectedAgentIds.size === filteredAgents.length}
                                        onChange={onSelectAll}
                                        className="rounded bg-slate-800 border-slate-600 text-blue-500 focus:ring-0"
                                    />
                                </th>
                                <th className="p-4 font-medium text-slate-400">Hostname</th>
                                <th className="p-4 font-medium text-slate-400">Platform</th>
                                <th className="p-4 font-medium text-slate-400">Status</th>
                                <th className="p-4 font-medium text-slate-400">IP Address</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-700/50">
                            {filteredAgents.map(agent => (
                                <tr
                                    key={agent.id}
                                    className={`hover:bg-slate-800/30 transition-colors cursor-pointer ${selectedAgentIds.has(agent.id) ? 'bg-blue-500/5' : ''}`}
                                    onClick={() => onToggle(agent.id)}
                                >
                                    <td className="p-4 text-center" onClick={(e) => e.stopPropagation()}>
                                        <input
                                            type="checkbox"
                                            checked={selectedAgentIds.has(agent.id)}
                                            onChange={() => onToggle(agent.id)}
                                            className="rounded bg-slate-800 border-slate-600 text-blue-500 focus:ring-0"
                                        />
                                    </td>
                                    <td className="p-4 flex items-center space-x-3">
                                        <div className="w-8 h-8 rounded bg-slate-800 flex items-center justify-center">
                                            <ServerIcon className="w-4 h-4 text-slate-400" />
                                        </div>
                                        <span className="font-medium text-slate-200">{agent.hostname}</span>
                                    </td>
                                    <td className="p-4 text-slate-300">{agent.platform}</td>
                                    <td className="p-4">
                                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${agent.status === 'Online' ? 'bg-green-500/10 text-green-400' : 'bg-slate-500/10 text-slate-400'}`}>
                                            {agent.status}
                                        </span>
                                    </td>
                                    <td className="p-4 text-slate-400 font-mono text-sm">{agent.ipAddress}</td>
                                </tr>
                            ))}
                            {filteredAgents.length === 0 && (
                                <tr>
                                    <td colSpan={5} className="p-8 text-center text-slate-500">No agents found matching filter.</td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
