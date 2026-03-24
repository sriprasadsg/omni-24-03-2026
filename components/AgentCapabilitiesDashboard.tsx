import React, { useState, useEffect } from 'react';
import { Shield, Activity, HardDrive, FileSearch, Cpu, Play, Square, RefreshCw, Layers } from 'lucide-react';
import { fetchAgents as apiFetchAgents } from '../services/apiService';

interface Capability {
    id: string;
    name: string;
    enabled: boolean;
    status: 'Running' | 'Stopped' | 'Error' | 'Installing';
    last_run?: string;
    metrics: { [key: string]: any };
    error?: string;
}

interface Agent {
    id: string;
    hostname: string;
    status: string;
    capabilities?: Capability[];
}

export const AgentCapabilitiesDashboard: React.FC = () => {
    const [agents, setAgents] = useState<Agent[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        fetchAgents();
        const interval = setInterval(fetchAgents, 30000);
        return () => clearInterval(interval);
    }, []);

    const fetchAgents = async () => {
        try {
            setError(null);
            const data = await apiFetchAgents();

            // If capabilities aren't directly on the agent root, extract them
            const mappedAgents = data.map((a: any) => ({
                ...a,
                capabilities: a.capabilities || (a.meta && a.meta.capabilities) || []
            }));

            setAgents(mappedAgents);
        } catch (err: any) {
            console.error('Error fetching agents:', err);
            setError(err.message || 'Failed to fetch agent capability data');
        } finally {
            setLoading(false);
        }
    };

    const getStatusBadge = (status: string) => {
        switch (status) {
            case 'Running':
                return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">Running</span>;
            case 'Stopped':
                return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400">Stopped</span>;
            case 'Error':
                return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400">Error</span>;
            default:
                return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400">{status}</span>;
        }
    };

    const getCapabilityIcon = (id: string, className = "h-5 w-5") => {
        const iconClass = `${className} text-gray-400 dark:text-gray-500`;
        switch (id) {
            case 'system_metrics': return <Cpu className={iconClass} />;
            case 'process_monitor': return <Activity className={iconClass} />;
            case 'file_integrity': return <FileSearch className={iconClass} />;
            case 'vulnerability_scanner': return <Shield className={iconClass} />;
            case 'ebpf_tracing': return <Layers className={iconClass} />;
            default: return <HardDrive className={iconClass} />;
        }
    };

    return (
        <div className="space-y-6 animate-fade-in">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Agent Capabilities</h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        Real-time telemetry and management of active agent capabilities.
                    </p>
                </div>
                <button
                    onClick={fetchAgents}
                    className="flex items-center px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 dark:bg-slate-800 dark:text-gray-300 dark:border-slate-600 dark:hover:bg-slate-700 transition-colors"
                >
                    <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                    Refresh
                </button>
            </div>

            {error && (
                <div className="p-4 bg-red-50 border border-red-200 rounded-lg dark:bg-red-900/20 dark:border-red-800">
                    <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
                </div>
            )}

            <div className="grid gap-6">
                {loading && agents.length === 0 ? (
                    <div className="text-center py-12">
                        <RefreshCw className="h-8 w-8 animate-spin mx-auto text-indigo-500" />
                        <p className="mt-4 text-gray-500 dark:text-gray-400">Loading agent capabilities...</p>
                    </div>
                ) : agents.length === 0 ? (
                    <div className="bg-white dark:bg-slate-800 rounded-xl border border-gray-200 dark:border-slate-700 p-8 text-center">
                        <HardDrive className="h-12 w-12 mx-auto text-gray-400 mb-4" />
                        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">No Agents Discovered</h3>
                        <p className="text-gray-500 dark:text-gray-400">
                            Deploy an agent to begin capturing capability data and telemetry.
                        </p>
                    </div>
                ) : (
                    agents.map((agent) => (
                        <div key={agent.id} className="bg-white dark:bg-slate-800 rounded-xl border border-gray-200 dark:border-slate-700 shadow-sm overflow-hidden">
                            <div className="px-6 py-4 border-b border-gray-200 dark:border-slate-700 bg-gray-50/50 dark:bg-slate-800/50 flex justify-between items-center">
                                <div className="flex items-center space-x-3">
                                    <div className={`w-3 h-3 rounded-full ${agent.status === 'Online' ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)]' : 'bg-red-500'}`}></div>
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                                        {agent.hostname} <span className="text-sm font-normal text-gray-500 dark:text-gray-400 ml-2">({agent.id})</span>
                                    </h3>
                                </div>
                                <div className="text-sm text-gray-500 dark:text-gray-400 flex items-center">
                                    <Activity className="w-4 h-4 mr-1.5" />
                                    {agent.capabilities?.length || 0} Capabilities Active
                                </div>
                            </div>

                            <div className="p-6">
                                {(!agent.capabilities || agent.capabilities.length === 0) ? (
                                    <div className="text-center py-6 text-gray-500 dark:text-gray-400 italic">
                                        No capability execution data available for this agent yet.
                                    </div>
                                ) : (
                                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                                        {agent.capabilities.map((cap) => (
                                            <div key={cap.id} className="border border-gray-200 dark:border-slate-700 rounded-lg p-4 bg-white dark:bg-slate-800 hover:border-indigo-300 dark:hover:border-indigo-700 transition-colors">
                                                <div className="flex justify-between items-start mb-3">
                                                    <div className="flex items-center space-x-3">
                                                        <div className="p-2 bg-indigo-50 dark:bg-indigo-900/30 rounded-lg">
                                                            {getCapabilityIcon(cap.id)}
                                                        </div>
                                                        <div>
                                                            <h4 className="font-medium text-gray-900 dark:text-white">{cap.name}</h4>
                                                            <p className="text-xs text-gray-500 dark:text-gray-400">{cap.id}</p>
                                                        </div>
                                                    </div>
                                                    {getStatusBadge(cap.status)}
                                                </div>

                                                <div className="space-y-3 mt-4 pt-4 border-t border-gray-100 dark:border-slate-700/50">
                                                    {cap.metrics && Object.entries(cap.metrics).map(([key, val]) => {
                                                        // Format metric names safely
                                                        const safeKey = typeof key === 'string' ? key.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ') : 'Metric';
                                                        
                                                        const renderMetricValue = (k: string, v: any): React.ReactNode => {
                                                            if (v === null || v === undefined) return 'N/A';

                                                            if (typeof v === 'object' && !Array.isArray(v)) {
                                                                // Handle Specific Nested Objects
                                                                if (k === 'cpu') {
                                                                    return `${v.percent?.toFixed(1) || 0}% (${v.count || 0} Cores)`;
                                                                }
                                                                if (k === 'memory') {
                                                                    const totalGB = (v.total / (1024 ** 3)).toFixed(1);
                                                                    return `${v.percent?.toFixed(1) || 0}% (of ${totalGB}GB)`;
                                                                }
                                                                if (k === 'network') {
                                                                    const sentMB = (v.bytes_sent / (1024 ** 2)).toFixed(1);
                                                                    const recvMB = (v.bytes_recv / (1024 ** 2)).toFixed(1);
                                                                    return `↑${sentMB}MB ↓${recvMB}MB`;
                                                                }
                                                                return JSON.stringify(v);
                                                            }

                                                            if (Array.isArray(v)) {
                                                                if (k === 'disk' || k === 'disks') {
                                                                    return (
                                                                        <div className="space-y-1">
                                                                            {v.slice(0, 2).map((d: any, i: number) => (
                                                                                <div key={i} className="text-[10px] flex justify-between">
                                                                                    <span className="truncate max-w-[40px] opacity-70">{d.mountpoint}:</span>
                                                                                    <span>{d.percent}%</span>
                                                                                </div>
                                                                            ))}
                                                                        </div>
                                                                    );
                                                                }
                                                                if (k === 'installedSoftware' || k === 'software_inventory') {
                                                                    return `${v.length} Packages`;
                                                                }
                                                                return `${v.length} Items`;
                                                            }

                                                            if (typeof v === 'number') {
                                                                let displayVal = v % 1 === 0 ? v.toString() : v.toFixed(1);
                                                                if (k.toLowerCase().includes('percent') || k.toLowerCase().includes('usage')) displayVal += '%';
                                                                return displayVal;
                                                            }

                                                            return String(v);
                                                        };

                                                        return (
                                                            <div key={key} className="flex justify-between items-start text-sm py-1 border-b border-gray-50 dark:border-slate-700/30 last:border-0">
                                                                <span className="text-gray-500 dark:text-gray-400">{safeKey}</span>
                                                                <div className="font-medium text-gray-900 dark:text-gray-300 font-mono text-right truncate ml-2">
                                                                    {renderMetricValue(key, val)}
                                                                </div>
                                                            </div>
                                                        );
                                                    })}

                                                    {Object.keys(cap.metrics || {}).length === 0 && (
                                                        <div className="text-xs text-gray-400 text-center py-2">Waiting for first telemetry payload...</div>
                                                    )}
                                                </div>

                                                {cap.error && (
                                                    <div className="mt-3 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-2 rounded border border-red-100 dark:border-red-900/30">
                                                        {cap.error}
                                                    </div>
                                                )}

                                                <div className="mt-4 flex justify-end space-x-2">
                                                    <button className="text-xs flex items-center px-2 py-1 text-gray-600 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 bg-gray-100 dark:bg-slate-700 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 rounded transition-colors">
                                                        {cap.status === 'Running' ? <Square className="w-3 h-3 mr-1" /> : <Play className="w-3 h-3 mr-1" />}
                                                        {cap.status === 'Running' ? 'Stop' : 'Start'}
                                                    </button>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
};
