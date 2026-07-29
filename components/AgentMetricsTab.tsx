import React, { useEffect, useState } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Agent } from '../types';
import { CpuIcon, MemoryStickIcon, HardDriveIcon } from './icons';
import { fetchAgentMetricsHistory, AgentMetricsHistoryPoint } from '../services/apiService';
import { useTimeZone } from '../contexts/TimeZoneContext';
import { AgentUptimeTimeline } from './AgentUptimeTimeline';

interface AgentMetricsTabProps {
    agent: Agent;
}

interface ChartPoint {
    timestamp: string;
    cpu: number;
    memory: number;
    disk: number;
}

const RANGE_PRESETS = [1, 6, 24, 48] as const;
type RangeHours = typeof RANGE_PRESETS[number];

// FOBS-01/02: agent-scoped CPU/memory/disk recharts AreaCharts + embedded
// uptime timeline, driven by a shared <=48h range selector (D-02).
// Consumes GET /agents/{id}/metrics/history — NOT the asset-metrics endpoint
// MetricsChartsTab.tsx uses (D-04 CORRECTION).
export const AgentMetricsTab: React.FC<AgentMetricsTabProps> = ({ agent }) => {
    const agentId = agent.id;
    const { timeZone } = useTimeZone();
    const [hours, setHours] = useState<RangeHours>(24);
    const [data, setData] = useState<ChartPoint[]>([]);
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        if (!agentId) return;
        let mounted = true;
        setIsLoading(true);
        fetchAgentMetricsHistory(agentId, hours).then(res => {
            if (!mounted) return;
            const metrics = res.metrics || [];
            const formatted = metrics.map((m: AgentMetricsHistoryPoint) => ({
                timestamp: new Date(m.timestamp).toLocaleTimeString(undefined, {
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: false,
                    timeZone: timeZone
                }),
                cpu: m.cpu_percent ?? 0,
                memory: m.memory_percent ?? 0,
                disk: m.disk_percent ?? 0,
            }));
            setData(formatted);
        }).catch(() => {
            if (mounted) setData([]);
        }).finally(() => {
            if (mounted) setIsLoading(false);
        });
        return () => { mounted = false; };
    }, [agentId, hours, timeZone]);

    return (
        <div className="space-y-6">
            {/* Range Selector */}
            <div className="flex justify-between items-center">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Agent Metrics</h3>
                <div className="flex space-x-2">
                    {RANGE_PRESETS.map(preset => (
                        <button
                            key={preset}
                            onClick={() => setHours(preset)}
                            className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${hours === preset
                                ? 'bg-primary-600 text-white'
                                : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                                }`}
                        >
                            {preset}H
                        </button>
                    ))}
                </div>
            </div>

            {/* Uptime (shares the same range selector) */}
            <AgentUptimeTimeline agentId={agentId} hours={hours} />

            {/* CPU Usage Chart */}
            <div className="bg-white dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                <div className="flex items-center mb-3">
                    <CpuIcon size={20} className="text-blue-500 mr-2" />
                    <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">CPU Usage</h4>
                </div>
                <ResponsiveContainer width="100%" height={200}>
                    <AreaChart data={data}>
                        <defs>
                            <linearGradient id="colorAgentCpu" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8} />
                                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.1} />
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                        <XAxis
                            dataKey="timestamp"
                            tick={{ fontSize: 11, fill: '#9ca3af' }}
                            interval="preserveStartEnd"
                        />
                        <YAxis
                            tick={{ fontSize: 11, fill: '#9ca3af' }}
                            domain={[0, 100]}
                            label={{ value: '%', position: 'insideLeft', fill: '#9ca3af' }}
                        />
                        <Tooltip
                            contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '0.375rem' }}
                            labelStyle={{ color: '#e5e7eb' }}
                        />
                        <Area type="monotone" dataKey="cpu" stroke="#3b82f6" fillOpacity={1} fill="url(#colorAgentCpu)" />
                    </AreaChart>
                </ResponsiveContainer>
            </div>

            {/* Memory Usage Chart */}
            <div className="bg-white dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                <div className="flex items-center mb-3">
                    <MemoryStickIcon size={20} className="text-purple-500 mr-2" />
                    <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Memory Usage</h4>
                </div>
                <ResponsiveContainer width="100%" height={200}>
                    <AreaChart data={data}>
                        <defs>
                            <linearGradient id="colorAgentMemory" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#a855f7" stopOpacity={0.8} />
                                <stop offset="95%" stopColor="#a855f7" stopOpacity={0.1} />
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                        <XAxis dataKey="timestamp" tick={{ fontSize: 11, fill: '#9ca3af' }} interval="preserveStartEnd" />
                        <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} domain={[0, 100]} label={{ value: '%', position: 'insideLeft', fill: '#9ca3af' }} />
                        <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '0.375rem' }} labelStyle={{ color: '#e5e7eb' }} />
                        <Area type="monotone" dataKey="memory" stroke="#a855f7" fillOpacity={1} fill="url(#colorAgentMemory)" />
                    </AreaChart>
                </ResponsiveContainer>
            </div>

            {/* Disk Usage Chart */}
            <div className="bg-white dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                <div className="flex items-center mb-3">
                    <HardDriveIcon size={20} className="text-green-500 mr-2" />
                    <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Disk Usage</h4>
                </div>
                <ResponsiveContainer width="100%" height={200}>
                    <AreaChart data={data}>
                        <defs>
                            <linearGradient id="colorAgentDisk" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#10b981" stopOpacity={0.8} />
                                <stop offset="95%" stopColor="#10b981" stopOpacity={0.1} />
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                        <XAxis dataKey="timestamp" tick={{ fontSize: 11, fill: '#9ca3af' }} interval="preserveStartEnd" />
                        <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} domain={[0, 100]} label={{ value: '%', position: 'insideLeft', fill: '#9ca3af' }} />
                        <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '0.375rem' }} labelStyle={{ color: '#e5e7eb' }} />
                        <Area type="monotone" dataKey="disk" stroke="#10b981" fillOpacity={1} fill="url(#colorAgentDisk)" />
                    </AreaChart>
                </ResponsiveContainer>
            </div>

            {isLoading && (
                <div className="bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 text-center">
                    <p className="text-sm text-gray-600 dark:text-gray-400">Loading metrics data...</p>
                </div>
            )}

            {!isLoading && data.length === 0 && (
                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                    <p className="font-medium text-blue-800 dark:text-blue-200">No metrics data available</p>
                    <p className="text-sm text-blue-700 dark:text-blue-300 mt-2">
                        Metrics will appear once this agent begins sending heartbeat data with metrics_collection enabled.
                    </p>
                </div>
            )}
        </div>
    );
};
