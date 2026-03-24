import React, { useState, useEffect } from 'react';
import { NetworkIcon, ServerIcon, ActivityIcon, ShieldCheckIcon, AlertTriangleIcon, BarChart3Icon } from './icons';
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { fetchAgents } from '../services/apiService';

const COLORS = ['#8884d8', '#82ca9d', '#ffc658', '#0088fe', '#00C49F', '#FFBB28', '#FF8042', '#a4de6c'];

export const WebMonitoringDashboard: React.FC = () => {
    const [agents, setAgents] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [webConnections, setWebConnections] = useState<any[]>([]);
    const [webLogs, setWebLogs] = useState<any[]>([]);

    useEffect(() => {
        const loadData = async () => {
            try {
                const agentsData = await fetchAgents();
                setAgents(agentsData);

                // Aggregate data from all agents
                const connections: any[] = [];
                const logs: any[] = [];

                agentsData.forEach((agent: any) => {
                    const meta = agent.meta || {};

                    // Web Monitor Data
                    if (meta.web_monitor && meta.web_monitor.web_connections) {
                        connections.push(...meta.web_monitor.web_connections);
                    }

                    // Web Log Data (Nginx/Apache/IIS logged via logs capability)
                    // In a real scenario, we'd have a specific field or parse general logs
                    // For now, let's look for web-related log markers in the meta or general logs
                    if (meta.log_collection && Array.isArray(meta.log_collection)) {
                        meta.log_collection.forEach((log: any) => {
                            if (log.message && (log.message.includes('HTTP') || log.message.includes('GET') || log.message.includes('POST'))) {
                                logs.push(log);
                            }
                        });
                    }
                });

                setWebConnections(connections);
                setWebLogs(logs);
            } catch (error) {
                console.error('Error loading web monitoring data:', error);
            } finally {
                setLoading(false);
            }
        };
        loadData();
    }, []);

    // Process data for charts
    const getTopDestinations = () => {
        const counts: Record<string, number> = {};
        webConnections.forEach(conn => {
            const host = conn.remote_host || conn.remote_ip;
            counts[host] = (counts[host] || 0) + 1;
        });

        return Object.entries(counts)
            .map(([name, value]) => ({ name, value }))
            .sort((a, b) => b.value - a.value)
            .slice(0, 8);
    };

    const getLogDistribution = () => {
        const counts: Record<string, number> = {
            'Nginx': 0,
            'Apache': 0,
            'IIS': 0,
            'Other': 0
        };

        // Count based on server markers in logs
        // This is a simplified heuristic
        webLogs.forEach(log => {
            const msg = (log.message || '').toLowerCase();
            if (msg.includes('nginx')) counts['Nginx']++;
            else if (msg.includes('apache')) counts['Apache']++;
            else if (msg.includes('iis') || msg.includes('w3wp')) counts['IIS']++;
            else counts['Other']++;
        });

        return Object.entries(counts)
            .map(([name, value]) => ({ name, value }))
            .filter(item => item.value > 0);
    };

    const destinationsData = getTopDestinations();
    const logData = getLogDistribution();

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
            </div>
        );
    }

    return (
        <div className="p-6 space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-black text-gray-800 dark:text-gray-100 italic tracking-tighter">
                        WEB MONITORING <span className="text-primary-600 not-italic">LIVE</span>
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400 font-bold uppercase text-xs tracking-widest">
                        Outbound Request Tracking & Web Server Log Analysis
                    </p>
                </div>
                <div className="flex gap-4">
                    <div className="glass-premium px-4 py-2 rounded-2xl border-l-4 border-primary-500">
                        <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest">Active Connections</p>
                        <p className="text-2xl font-black text-gray-800 dark:text-gray-100">{webConnections.length}</p>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Destination Distribution */}
                <div className="glass-premium p-6 rounded-3xl border border-white/10 relative overflow-hidden group">
                    <div className="absolute top-0 right-0 p-8 opacity-5 group-hover:opacity-10 transition-opacity">
                        <NetworkIcon size={120} />
                    </div>
                    <h2 className="text-xl font-black text-gray-800 dark:text-gray-100 italic mb-6">TOP DESTINATIONS</h2>

                    <div className="h-[300px] w-full">
                        {destinationsData.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie
                                        data={destinationsData}
                                        cx="50%"
                                        cy="50%"
                                        innerRadius={60}
                                        outerRadius={80}
                                        paddingAngle={5}
                                        dataKey="value"
                                    >
                                        {destinationsData.map((entry, index) => (
                                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                        ))}
                                    </Pie>
                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '12px', color: '#fff' }}
                                        itemStyle={{ color: '#fff' }}
                                    />
                                    <Legend />
                                </PieChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="flex flex-col items-center justify-center h-full text-gray-500 italic">
                                <ActivityIcon size={48} className="mb-2 opacity-20" />
                                <p>No outbound web traffic detected yet</p>
                            </div>
                        )}
                    </div>
                </div>

                {/* Web Service Log Distribution */}
                <div className="glass-premium p-6 rounded-3xl border border-white/10 relative overflow-hidden group">
                    <div className="absolute top-0 right-0 p-8 opacity-5 group-hover:opacity-10 transition-opacity">
                        <ServerIcon size={120} />
                    </div>
                    <h2 className="text-xl font-black text-gray-800 dark:text-gray-100 italic mb-6">WEB SERVER LOGS</h2>

                    <div className="h-[300px] w-full">
                        {logData.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie
                                        data={logData}
                                        cx="50%"
                                        cy="50%"
                                        innerRadius={60}
                                        outerRadius={80}
                                        paddingAngle={5}
                                        dataKey="value"
                                    >
                                        {logData.map((entry, index) => (
                                            <Cell key={`cell-${index}`} fill={COLORS[(index + 4) % COLORS.length]} />
                                        ))}
                                    </Pie>
                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '12px', color: '#fff' }}
                                        itemStyle={{ color: '#fff' }}
                                    />
                                    <Legend />
                                </PieChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="flex flex-col items-center justify-center h-full text-gray-500 italic">
                                <BarChart3Icon size={48} className="mb-2 opacity-20" />
                                <p>No web server logs collected yet</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* List of recent connections */}
            <div className="glass-premium p-6 rounded-3xl border border-white/10">
                <h2 className="text-xl font-black text-gray-800 dark:text-gray-100 italic mb-6 flex items-center gap-2">
                    <ActivityIcon className="text-primary-500" /> RECENT WEB ACTIVITY
                </h2>
                <div className="overflow-x-auto">
                    <table className="w-full text-left">
                        <thead>
                            <tr className="text-gray-400 text-[10px] font-black uppercase tracking-widest border-b border-white/5">
                                <th className="pb-4 px-4 font-black">Agent / Process</th>
                                <th className="pb-4 px-4 font-black">Destination</th>
                                <th className="pb-4 px-4 font-black">Port</th>
                                <th className="pb-4 px-4 font-black">Timestamp</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                            {webConnections.slice(0, 10).map((conn, idx) => (
                                <tr key={idx} className="hover:bg-white/5 transition-colors group">
                                    <td className="py-4 px-4">
                                        <div className="flex flex-col">
                                            <span className="font-bold text-gray-800 dark:text-gray-200">{conn.process || 'Unknown'}</span>
                                            <span className="text-[10px] text-gray-500 uppercase tracking-tighter">PID: {conn.pid}</span>
                                        </div>
                                    </td>
                                    <td className="py-4 px-4">
                                        <div className="flex items-center gap-2">
                                            <div className="h-2 w-2 rounded-full bg-primary-500 animate-pulse" />
                                            <span className="font-mono text-sm text-gray-700 dark:text-gray-300">
                                                {conn.remote_host || conn.remote_ip}
                                            </span>
                                        </div>
                                    </td>
                                    <td className="py-4 px-4">
                                        <span className={`px-2 py-0.5 rounded-md text-[10px] font-black ${conn.port === 443 ? 'bg-green-100 text-green-700 dark:bg-green-900/30' : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30'}`}>
                                            {conn.port === 443 ? 'HTTPS' : conn.port === 80 ? 'HTTP' : conn.port}
                                        </span>
                                    </td>
                                    <td className="py-4 px-4 text-xs text-gray-500">
                                        {new Date(conn.timestamp).toLocaleString()}
                                    </td>
                                </tr>
                            ))}
                            {webConnections.length === 0 && (
                                <tr>
                                    <td colSpan={4} className="py-20 text-center text-gray-500 italic">
                                        No active web connections reported by agents.
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
