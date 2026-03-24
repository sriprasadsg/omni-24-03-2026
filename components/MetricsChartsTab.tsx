import React, { useState, useEffect } from 'react';
import { LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { CpuIcon, MemoryStickIcon, HardDriveIcon, NetworkIcon } from './icons';
import { fetchAssetMetrics } from '../services/apiService';

interface MetricDataPoint {
    timestamp: string;
    cpu: number;
    memory: number;
    disk: number;
    network: number;
}

interface MetricsChartsTabProps {
    assetId: string;
}

import { useTimeZone } from '../contexts/TimeZoneContext';

// ... lines_skipped ...

export const MetricsChartsTab: React.FC<MetricsChartsTabProps> = ({ assetId }) => {
    const [timeRange, setTimeRange] = useState<'1h' | '24h' | '7d' | '30d'>('24h');
    const { timeZone } = useTimeZone();

    const [data, setData] = useState<MetricDataPoint[]>([]);
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        let mounted = true;
        const loadMetrics = async () => {
            setIsLoading(true);
            try {
                const metrics = await fetchAssetMetrics(assetId, timeRange);
                if (mounted) {
                    if (metrics && metrics.length > 0) {
                        // Format timestamps
                        const formatted = metrics.map((m: any) => ({
                            timestamp: new Date(m.timestamp).toLocaleTimeString(undefined, {
                                hour: '2-digit',
                                minute: '2-digit',
                                hour12: false,
                                timeZone: timeZone
                            }),
                            cpu: m.cpu_percent || 0,
                            memory: m.memory_percent || 0,
                            disk: m.disk_percent || 0,
                            network: m.network_bytes_sent_mb || 0
                        }));
                        setData(formatted);
                    } else {
                        // Fallback to empty or keep previous? Let's show empty if no data.
                        // Or for demo purposes, if absolutely no data, strictly show mock?
                        // Better to show empty state message if 0 real data points.
                        setData([]);
                    }
                }
            } catch (err) {
                console.error(err);
            } finally {
                if (mounted) setIsLoading(false);
            }
        };

        loadMetrics();

        // Poll every 30 seconds
        const interval = setInterval(loadMetrics, 30000);
        return () => {
            mounted = false;
            clearInterval(interval);
        };
    }, [assetId, timeRange]);

    return (
        <div className="space-y-6">
            {/* Time Range Selector */}
            <div className="flex justify-between items-center">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Performance Metrics</h3>
                <div className="flex space-x-2">
                    {(['1h', '24h', '7d', '30d'] as const).map(range => (
                        <button
                            key={range}
                            onClick={() => setTimeRange(range)}
                            className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${timeRange === range
                                ? 'bg-primary-600 text-white'
                                : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                                }`}
                        >
                            {range.toUpperCase()}
                        </button>
                    ))}
                </div>
            </div>

            {/* CPU Usage Chart */}
            <div className="bg-white dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                <div className="flex items-center mb-3">
                    <CpuIcon size={20} className="text-blue-500 mr-2" />
                    <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">CPU Usage</h4>
                </div>
                <ResponsiveContainer width="100%" height={200}>
                    <AreaChart data={data}>
                        <defs>
                            <linearGradient id="colorCpu" x1="0" y1="0" x2="0" y2="1">
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
                        <Area type="monotone" dataKey="cpu" stroke="#3b82f6" fillOpacity={1} fill="url(#colorCpu)" />
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
                            <linearGradient id="colorMemory" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#a855f7" stopOpacity={0.8} />
                                <stop offset="95%" stopColor="#a855f7" stopOpacity={0.1} />
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                        <XAxis dataKey="timestamp" tick={{ fontSize: 11, fill: '#9ca3af' }} interval="preserveStartEnd" />
                        <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} domain={[0, 100]} label={{ value: '%', position: 'insideLeft', fill: '#9ca3af' }} />
                        <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '0.375rem' }} labelStyle={{ color: '#e5e7eb' }} />
                        <Area type="monotone" dataKey="memory" stroke="#a855f7" fillOpacity={1} fill="url(#colorMemory)" />
                    </AreaChart>
                </ResponsiveContainer>
            </div>

            {/* Disk & Network - Side by Side */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Disk Usage */}
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                    <div className="flex items-center mb-3">
                        <HardDriveIcon size={20} className="text-green-500 mr-2" />
                        <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Disk Usage</h4>
                    </div>
                    <ResponsiveContainer width="100%" height={150}>
                        <LineChart data={data}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                            <XAxis dataKey="timestamp" tick={{ fontSize: 10, fill: '#9ca3af' }} interval="preserveStartEnd" />
                            <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} domain={[0, 100]} />
                            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '0.375rem' }} labelStyle={{ color: '#e5e7eb' }} />
                            <Line type="monotone" dataKey="disk" stroke="#10b981" strokeWidth={2} dot={false} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>

                {/* Network Throughput */}
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                    <div className="flex items-center mb-3">
                        <NetworkIcon size={20} className="text-orange-500 mr-2" />
                        <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Network I/O</h4>
                    </div>
                    <ResponsiveContainer width="100%" height={150}>
                        <LineChart data={data}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                            <XAxis dataKey="timestamp" tick={{ fontSize: 10, fill: '#9ca3af' }} interval="preserveStartEnd" />
                            <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} />
                            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '0.375rem' }} labelStyle={{ color: '#e5e7eb' }} />
                            <Line type="monotone" dataKey="network" stroke="#f97316" strokeWidth={2} dot={false} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {isLoading && (
                <div className="bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 text-center">
                    <p className="text-sm text-gray-600 dark:text-gray-400">Loading metrics data...</p>
                </div>
            )}

            {!isLoading && data.length === 0 && (
                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                    <p className="font-medium text-blue-800 dark:text-blue-200">📊 No metrics data available</p>
                    <p className="text-sm text-blue-700 dark:text-blue-300 mt-2">
                        Metrics will appear once the agent on this asset begins sending heartbeat data with metrics_collection enabled.
                    </p>
                    <p className="text-xs text-blue-600 dark:text-blue-400 mt-2">
                        Ensure the agent is running and configured with the correct tenant_id in <code className="bg-blue-100 dark:bg-blue-900 px-1 rounded">agent/config.yaml</code>
                    </p>
                </div>
            )}

            {!isLoading && data.length > 0 && (
                <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3">
                    <p className="text-sm text-green-800 dark:text-green-200">
                        ✅ Showing <strong>{data.length}</strong> live data points from agent metrics (updates every 30s)
                    </p>
                </div>
            )}
        </div>
    );
};
