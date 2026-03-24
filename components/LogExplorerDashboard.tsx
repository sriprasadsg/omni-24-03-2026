import React, { useState, useEffect } from 'react';
import { SearchIcon, FilterIcon, RefreshCw, BarChart2Icon, DatabaseIcon, CpuIcon, CloudIcon, ShieldCheckIcon, AlertTriangleIcon } from 'lucide-react';

export const LogExplorerDashboard: React.FC = () => {
    // Basic fetch wrapper for API calls
    const fetchApi = async (url: string, options: any = {}) => {
        const response = await fetch(url, options);
        if (!response.ok) throw new Error(`API error: ${response.status}`);
        return response.json();
    };
    const [searchQuery, setSearchQuery] = useState('');
    const [sourceFilter, setSourceFilter] = useState('');
    const [logs, setLogs] = useState<any[]>([]);
    const [stats, setStats] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    const loadData = async () => {
        setLoading(true);
        try {
            const [logsRes, statsRes] = await Promise.all([
                fetchApi(`/api/siem/logs?q=${searchQuery}&source=${sourceFilter}`),
                fetchApi('/api/siem/aggregations')
            ]);
            setLogs(logsRes.logs || []);
            setStats(statsRes);
        } catch (error) {
            console.error("Failed to load SIEM logs", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, [sourceFilter]); // Re-fetch when source changes

    // Handle Enter key in search
    const handleSearchKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            loadData();
        }
    };

    const getSourceIcon = (type: string) => {
        switch (type) {
            case 'aws_cloudtrail': return <CloudIcon className="text-orange-400" size={16} />;
            case 'okta_system': return <ShieldCheckIcon className="text-blue-400" size={16} />;
            case 'syslog': return <DatabaseIcon className="text-green-400" size={16} />;
            default: return <CpuIcon className="text-gray-400" size={16} />;
        }
    };

    const getSeverityColor = (sev: string | number) => {
        const s = String(sev).toLowerCase();
        if (s === 'high' || s === 'critical' || s === 'warning' || Number(s) >= 7) return 'text-red-400 bg-red-400/10 border-red-500/20';
        if (s === 'medium' || Number(s) >= 4) return 'text-yellow-400 bg-yellow-400/10 border-yellow-500/20';
        return 'text-green-400 bg-green-400/10 border-green-500/20';
    };

    return (
        <div className="p-6 space-y-6">
            <header className="flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-indigo-500 flex items-center gap-3">
                        <DatabaseIcon className="text-blue-400" />
                        Log Explorer (SIEM)
                    </h1>
                    <p className="text-white/60 mt-1">Centralized log ingestion and threat hunting</p>
                </div>
            </header>

            {/* Top Toolbar (Search & Filter) */}
            <div className="glass p-4 rounded-xl flex items-center gap-4">
                <div className="relative flex-1">
                    <SearchIcon className="absolute left-3 top-3 text-white/40" size={18} />
                    <input
                        type="text"
                        placeholder="Search logs using KQL-like syntax (e.g. source_ip:10.0.0.1 AND severity:High)..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onKeyDown={handleSearchKeyDown}
                        className="w-full bg-black/20 border border-white/10 rounded-lg pl-10 pr-4 py-2 text-white focus:outline-none focus:border-blue-500/50"
                    />
                </div>
                <select
                    value={sourceFilter}
                    onChange={(e) => setSourceFilter(e.target.value)}
                    className="bg-black/20 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-blue-500/50"
                >
                    <option value="">All Sources</option>
                    <option value="syslog">Syslog / Network</option>
                    <option value="aws_cloudtrail">AWS CloudTrail</option>
                    <option value="okta_system">Okta System Logs</option>
                </select>
                <button
                    onClick={loadData}
                    className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 transition-colors"
                >
                    <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
                    Search
                </button>
            </div>

            {/* Visualization Stats Panel */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                <div className="glass p-6 rounded-xl md:col-span-1">
                    <h3 className="text-sm font-medium text-white/60 flex items-center gap-2 mb-4">
                        <FilterIcon size={16} /> Log Sources
                    </h3>
                    <div className="space-y-4">
                        {stats && stats.sources && Object.entries(stats.sources).map(([key, count]) => (
                            <div key={key} className="flex justify-between items-center text-sm">
                                <span className="flex items-center gap-2 text-white/80 capitalize">
                                    {getSourceIcon(key)} {key.replace('_', ' ')}
                                </span>
                                <span className="font-mono text-white/60">{String(count)}</span>
                            </div>
                        ))}
                        {(!stats || Object.keys(stats.sources || {}).length === 0) && (
                            <div className="text-white/40 text-sm italic">No data ingested</div>
                        )}
                    </div>
                </div>

                <div className="glass p-6 rounded-xl md:col-span-3 flex flex-col">
                    <h3 className="text-sm font-medium text-white/60 flex items-center gap-2 mb-4">
                        <BarChart2Icon size={16} /> Volume Timeline
                    </h3>
                    {/* Fake histogram visualizer */}
                    <div className="flex-1 flex items-end gap-2 h-32 relative group">
                        {stats?.histogram?.map((bar: any, i: number) => {
                            const max = Math.max(...stats.histogram.map((h: any) => h.count));
                            const height = max > 0 ? (bar.count / max) * 100 : 5;
                            return (
                                <div key={i} className="flex-1 flex flex-col justify-end group">
                                    <div
                                        className="w-full bg-blue-500/40 rounded-t-sm hover:bg-blue-400 transition-all"
                                        style={{ height: `${height}%` }}
                                        title={`Time: ${bar.time}, Count: ${bar.count}`}
                                    ></div>
                                </div>
                            );
                        })}
                        {(!stats || !stats.histogram) && (
                            <div className="absolute inset-0 flex items-center justify-center text-white/40">
                                No timeline data available
                            </div>
                        )}
                    </div>
                    <div className="flex justify-between text-xs text-white/40 mt-2">
                        <span>Past Hour</span>
                        <span>Now</span>
                    </div>
                </div>
            </div>

            {/* Log Table */}
            <div className="glass rounded-xl overflow-hidden shadow-2xl">
                <div className="p-4 border-b border-white/5 flex justify-between items-center bg-white/5">
                    <h2 className="text-lg font-semibold flex items-center gap-2">
                        <DatabaseIcon className="text-blue-400" size={20} />
                        Log Events
                    </h2>
                    <span className="text-xs font-mono text-white/40">{logs.length} events loaded</span>
                </div>
                <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
                    <table className="w-full text-left border-collapse">
                        <thead className="sticky top-0 bg-[#1a1b23] z-10">
                            <tr>
                                <th className="p-4 text-xs font-medium text-white/40 uppercase tracking-wider whitespace-nowrap">Timestamp</th>
                                <th className="p-4 text-xs font-medium text-white/40 uppercase tracking-wider whitespace-nowrap">Source</th>
                                <th className="p-4 text-xs font-medium text-white/40 uppercase tracking-wider whitespace-nowrap">Severity</th>
                                <th className="p-4 text-xs font-medium text-white/40 uppercase tracking-wider">Message</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5 text-sm font-mono align-top">
                            {logs.length === 0 ? (
                                <tr>
                                    <td colSpan={4} className="p-8 text-center text-white/40">
                                        No logs matching your query.
                                    </td>
                                </tr>
                            ) : (
                                logs.map((log: any) => (
                                    <tr key={log.id} className="hover:bg-white/5 transition-colors group">
                                        <td className="p-4 whitespace-nowrap text-white/60">
                                            {new Date(log.timestamp).toLocaleString()}
                                        </td>
                                        <td className="p-4 whitespace-nowrap">
                                            <div className="flex items-center gap-2">
                                                {getSourceIcon(log.log_type)}
                                                <span className="capitalize">{log.log_type.replace('_', ' ')}</span>
                                            </div>
                                        </td>
                                        <td className="p-4 whitespace-nowrap">
                                            <span className={`px-2 py-1 rounded-full text-xs font-medium border ${getSeverityColor(log.severity)}`}>
                                                {log.severity || 'Info'}
                                            </span>
                                        </td>
                                        <td className="p-4 text-white/80 break-words max-w-[500px]">
                                            <div className="truncate group-hover:whitespace-normal group-hover:break-all">
                                                {log.raw_message || JSON.stringify(log)}
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};
