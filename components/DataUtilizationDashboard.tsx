import React, { useState, useEffect } from 'react';
import { Network, Server, ArrowUpCircle, ArrowDownCircle, RefreshCw, Activity, AlertCircle } from 'lucide-react';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
    PieChart, Pie, Cell, LineChart, Line, AreaChart, Area
} from 'recharts';

interface AgentUtilization {
    id: string;
    hostname: string;
    ipAddress: string;
    os: string;
    bytesSent: number;
    bytesRecv: number;
}

interface UtilizationData {
    totalBytesSent: number;
    totalBytesRecv: number;
    agents: AgentUtilization[];
}

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f43f5e'];

const formatBytes = (bytes: number, decimals = 2) => {
    if (!+bytes) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
};

export const DataUtilizationDashboard: React.FC = () => {
    const [data, setData] = useState<UtilizationData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchUtilizationData = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetch('/api/agents/network-utilization', {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                }
            });
            if (!response.ok) throw new Error('Failed to fetch data');
            const result = await response.json();
            setData(result);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchUtilizationData();
        const interval = setInterval(fetchUtilizationData, 60000); // refresh every minute
        return () => clearInterval(interval);
    }, []);

    if (loading && !data) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500"></div>
            </div>
        );
    }

    if (error && !data) {
        return (
            <div className="bg-red-50 dark:bg-red-900/20 border-l-4 border-red-500 p-4 m-4 rounded-md">
                <div className="flex">
                    <AlertCircle className="h-6 w-6 text-red-500 mr-4" />
                    <div>
                        <h3 className="text-lg font-medium text-red-800 dark:text-red-200">Error Loading Data</h3>
                        <p className="mt-1 text-red-700 dark:text-red-300">{error}</p>
                    </div>
                </div>
            </div>
        );
    }

    const chartData = data?.agents.slice(0, 10).map(agent => ({
        name: agent.hostname.length > 15 ? agent.hostname.substring(0, 15) + '...' : agent.hostname,
        sent: agent.bytesSent,
        received: agent.bytesRecv,
        total: agent.bytesSent + agent.bytesRecv
    })) || [];

    const pieData = data?.agents.slice(0, 8).map((agent, index) => ({
        name: agent.hostname,
        value: agent.bytesSent + agent.bytesRecv,
        color: COLORS[index % COLORS.length]
    })) || [];

    // Group into 'Others' if many agents
    if (data && data.agents.length > 8) {
        const othersValue = data.agents.slice(8).reduce((acc, curr) => acc + curr.bytesSent + curr.bytesRecv, 0);
        pieData.push({ name: 'Others', value: othersValue, color: '#9ca3af' });
    }

    // Custom Formatter for Charts
    const chartTooltipFormatter = (value: number) => {
        return formatBytes(value);
    };

    return (
        <div className="container mx-auto space-y-6 animate-fade-in pb-12">
            <div className="flex justify-between items-center bg-white dark:bg-gray-800 p-6 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700">
                <div>
                    <h2 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-indigo-600 dark:from-blue-400 dark:to-indigo-400">
                        Data Utilization Dashboard
                    </h2>
                    <p className="text-gray-500 dark:text-gray-400 mt-1 flex items-center">
                        <Activity className="w-4 h-4 mr-2" /> Monitor bandwidth consumption across all agent endpoints
                    </p>
                </div>
                <button
                    onClick={fetchUtilizationData}
                    disabled={loading}
                    className="flex items-center space-x-2 px-4 py-2 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 rounded-lg hover:bg-indigo-100 dark:hover:bg-indigo-900/50 transition-colors"
                >
                    <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                    <span>Refresh</span>
                </button>
            </div>

            {/* High-level KPIs */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-sm border border-gray-100 dark:border-gray-700 flex items-center space-x-4">
                    <div className="p-4 bg-blue-100 dark:bg-blue-900/30 rounded-xl text-blue-600 dark:text-blue-400">
                        <Network className="w-8 h-8" />
                    </div>
                    <div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Bandwidth</p>
                        <h3 className="text-2xl font-bold text-gray-900 dark:text-white">
                            {formatBytes((data?.totalBytesSent || 0) + (data?.totalBytesRecv || 0))}
                        </h3>
                    </div>
                </div>

                <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-sm border border-gray-100 dark:border-gray-700 flex items-center space-x-4">
                    <div className="p-4 bg-emerald-100 dark:bg-emerald-900/30 rounded-xl text-emerald-600 dark:text-emerald-400">
                        <ArrowUpCircle className="w-8 h-8" />
                    </div>
                    <div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Upload (Sent)</p>
                        <h3 className="text-2xl font-bold text-gray-900 dark:text-white">
                            {formatBytes(data?.totalBytesSent || 0)}
                        </h3>
                    </div>
                </div>

                <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-sm border border-gray-100 dark:border-gray-700 flex items-center space-x-4">
                    <div className="p-4 bg-amber-100 dark:bg-amber-900/30 rounded-xl text-amber-600 dark:text-amber-400">
                        <ArrowDownCircle className="w-8 h-8" />
                    </div>
                    <div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Download (Recv)</p>
                        <h3 className="text-2xl font-bold text-gray-900 dark:text-white">
                            {formatBytes(data?.totalBytesRecv || 0)}
                        </h3>
                    </div>
                </div>
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-6">
                    <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-6">Top Agents by Bandwidth</h3>
                    <div className="h-80 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={chartData} margin={{ top: 10, right: 30, left: 20, bottom: 5 }}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#374151" opacity={0.2} />
                                <XAxis dataKey="name" tick={{ fill: '#6b7280' }} tickLine={false} axisLine={false} />
                                <YAxis tickFormatter={formatBytes} tick={{ fill: '#6b7280' }} tickLine={false} axisLine={false} />
                                <Tooltip
                                    formatter={chartTooltipFormatter}
                                    contentStyle={{ backgroundColor: '#1f2937', borderColor: '#374151', color: '#f9fafb', borderRadius: '8px' }}
                                />
                                <Legend iconType="circle" />
                                <Bar dataKey="sent" name="Sent" stackId="a" fill="#3b82f6" radius={[0, 0, 4, 4]} />
                                <Bar dataKey="received" name="Received" stackId="a" fill="#10b981" radius={[4, 4, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-6">
                    <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-6">Bandwidth Distribution</h3>
                    <div className="h-80 w-full flex justify-center items-center">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie
                                    data={pieData}
                                    cx="50%"
                                    cy="50%"
                                    innerRadius={60}
                                    outerRadius={100}
                                    paddingAngle={5}
                                    dataKey="value"
                                >
                                    {pieData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.color} />
                                    ))}
                                </Pie>
                                <Tooltip
                                    formatter={chartTooltipFormatter}
                                    contentStyle={{ backgroundColor: '#1f2937', borderColor: '#374151', color: '#f9fafb', borderRadius: '8px' }}
                                />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>

            {/* Detailed Table */}
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 overflow-hidden">
                <div className="px-6 py-5 border-b border-gray-100 dark:border-gray-700">
                    <h3 className="text-lg font-semibold text-gray-800 dark:text-white flex items-center">
                        <Server className="w-5 h-5 mr-2 text-indigo-500" /> Endpoint Utilization Details
                    </h3>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="bg-gray-50 dark:bg-gray-900/50 text-gray-500 dark:text-gray-400 text-sm">
                                <th className="px-6 py-4 font-medium">Agent / Hostname</th>
                                <th className="px-6 py-4 font-medium">IP Address</th>
                                <th className="px-6 py-4 font-medium">OS Platform</th>
                                <th className="px-6 py-4 font-medium">Data Sent</th>
                                <th className="px-6 py-4 font-medium">Data Received</th>
                                <th className="px-6 py-4 font-medium">Total Bandwidth</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                            {data?.agents.map((agent) => (
                                <tr key={agent.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                                    <td className="px-6 py-4">
                                        <div className="flex flex-col">
                                            <span className="font-medium text-gray-900 dark:text-white">{agent.hostname}</span>
                                            <span className="text-xs text-gray-500 dark:text-gray-400">{agent.id}</span>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-700 dark:text-gray-300">
                                        {agent.ipAddress}
                                    </td>
                                    <td className="px-6 py-4">
                                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-300">
                                            {agent.os}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-sm font-medium text-blue-600 dark:text-blue-400">
                                        {formatBytes(agent.bytesSent)}
                                    </td>
                                    <td className="px-6 py-4 text-sm font-medium text-emerald-600 dark:text-emerald-400">
                                        {formatBytes(agent.bytesRecv)}
                                    </td>
                                    <td className="px-6 py-4 text-sm font-bold text-gray-900 dark:text-white">
                                        {formatBytes(agent.bytesSent + agent.bytesRecv)}
                                    </td>
                                </tr>
                            ))}
                            {(!data?.agents || data.agents.length === 0) && (
                                <tr>
                                    <td colSpan={6} className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
                                        No endpoint data available. Ensure agents are running and submitting telemetry.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};
