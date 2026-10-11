import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';
import { 
    Activity, 
    Database, 
    Cpu, 
    HardDrive, 
    Layers, 
    Users, 
    CheckCircle, 
    AlertCircle, 
    Clock, 
    ChevronRight,
    RefreshCw,
    Shield
} from 'lucide-react';

interface SystemHealth {
    status: string;
    uptime: string;
    resources: {
        cpu_percent: number;
        memory_percent: number;
        memory_used_gb: number;
        memory_total_gb: number;
        disk_percent: number;
        available: boolean;
    };
    database: {
        connected: boolean;
        // Size details are only returned to super-admins (shared database)
        collections?: number;
        data_size_mb?: number;
        storage_size_mb?: number;
        indexes?: number;
    };
    queues: {
        alert_queue: number;
        open_alerts: number;
        deployment_tasks: number;
        running_playbooks: number;
    };
    agent_fleet: {
        total: number;
        online: number;
        offline: number;
        stale: number;
        health_pct: number;
    };
    background_tasks: Array<{
        name: string;
        interval: string;
        status: string;
    }>;
}

type InfraAlert = { level: 'critical' | 'warning' | 'ok'; title: string; detail: string };

const ALERT_STYLE = {
    critical: { box: 'bg-red-50 dark:bg-red-900/20 border-red-500', icon: 'text-red-500', title: 'text-red-900 dark:text-red-200', text: 'text-red-700 dark:text-red-300' },
    warning: { box: 'bg-amber-50 dark:bg-amber-900/20 border-amber-500', icon: 'text-amber-500', title: 'text-amber-900 dark:text-amber-200', text: 'text-amber-700 dark:text-amber-300' },
    ok: { box: 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-500', icon: 'text-emerald-500', title: 'text-emerald-900 dark:text-emerald-200', text: 'text-emerald-700 dark:text-emerald-300' },
};

// Alerts derived from the live health snapshot (nothing here is canned)
export const infraAlerts = (h: SystemHealth): InfraAlert[] => {
    const out: InfraAlert[] = [];
    if (!h.database?.connected) out.push({ level: 'critical', title: 'Database Disconnected', detail: 'The backend cannot reach MongoDB.' });
    const r = h.resources;
    if (r?.available) {
        if (r.cpu_percent >= 90) out.push({ level: 'warning', title: 'High CPU', detail: `CPU at ${r.cpu_percent}%.` });
        if (r.memory_percent >= 90) out.push({ level: 'warning', title: 'High Memory', detail: `Memory at ${r.memory_percent}%.` });
        if (r.disk_percent >= 85) out.push({ level: r.disk_percent >= 95 ? 'critical' : 'warning', title: 'Disk Space Low', detail: `Disk at ${r.disk_percent}%.` });
    }
    if ((h.queues?.alert_queue ?? 0) >= 500) out.push({ level: 'warning', title: 'Alert Queue Backlog', detail: `${h.queues.alert_queue} alerts waiting.` });
    const f = h.agent_fleet;
    if (f?.stale) out.push({ level: 'warning', title: 'Stale Agents', detail: `${f.stale} agent(s) stopped reporting recently.` });
    if (f?.offline) out.push({ level: 'warning', title: 'Agents Offline', detail: `${f.offline} of ${f.total} agent(s) offline.` });
    const stopped = (h.background_tasks || []).filter(t => t.status !== 'running');
    if (stopped.length) out.push({ level: 'warning', title: 'Background Tasks Not Running', detail: stopped.map(t => t.name).join(', ') });
    if (!out.length) out.push({ level: 'ok', title: 'All Checks Passing', detail: 'Database, resources, queues, agents and background tasks look healthy.' });
    return out;
};

export const SystemHealthDashboard: React.FC = () => {
    const [health, setHealth] = useState<SystemHealth | null>(null);
    const [loading, setLoading] = useState(true);

    const fetchHealth = async () => {
        setLoading(true);
        try {
            const res = await authFetch('/api/system/health');
            const data = await res.json();
            setHealth(data);
        } catch (error) {
            console.error('Error fetching system health:', error);
        }
        setLoading(false);
    };

    useEffect(() => {
        fetchHealth();
        const interval = setInterval(fetchHealth, 15000);
        return () => clearInterval(interval);
    }, []);

    if (loading && !health) {
        return (
            <div className="flex items-center justify-center h-screen bg-slate-50 dark:bg-slate-900">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
            </div>
        );
    }

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'healthy': return 'bg-emerald-500';
            case 'degraded': return 'bg-amber-500';
            case 'critical': return 'bg-red-500';
            default: return 'bg-slate-500';
        }
    };

    const getResourceColor = (pct: number) => {
        if (pct > 90) return 'bg-red-500';
        if (pct > 70) return 'bg-amber-500';
        return 'bg-indigo-500';
    };

    return (
        <div className="p-6 bg-slate-50 dark:bg-slate-900 min-h-screen space-y-6">
            <div className="flex justify-between items-center">
                <div className="flex items-center space-x-4">
                    <div className={`w-3 h-3 rounded-full ${getStatusColor(health?.status || '')} animate-pulse`}></div>
                    <div>
                        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">System Health</h1>
                        <p className="text-sm text-slate-500">Uptime: {health?.uptime} • Version 2030.0</p>
                    </div>
                </div>
                <button 
                    onClick={fetchHealth}
                    className="p-2 hover:bg-white dark:hover:bg-slate-800 rounded-full transition-all text-slate-400"
                >
                    <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {/* Resource Stats */}
                <div className="bg-white dark:bg-slate-800 p-6 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700">
                    <div className="flex items-center justify-between mb-4">
                        <Cpu className="w-6 h-6 text-indigo-500" />
                        <span className="text-xs font-bold text-slate-400 uppercase">Compute</span>
                    </div>
                    <div className="space-y-4">
                        <div>
                            <div className="flex justify-between text-sm mb-1">
                                <span className="text-slate-600 dark:text-slate-400">CPU Usage</span>
                                <span className="font-bold">{health?.resources.cpu_percent}%</span>
                            </div>
                            <div className="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-2">
                                <div 
                                    className={`h-2 rounded-full transition-all duration-500 ${getResourceColor(health?.resources.cpu_percent || 0)}`} 
                                    style={{ width: `${health?.resources.cpu_percent}%` }}
                                ></div>
                            </div>
                        </div>
                        <div>
                            <div className="flex justify-between text-sm mb-1">
                                <span className="text-slate-600 dark:text-slate-400">Memory ({health?.resources.memory_used_gb}GB)</span>
                                <span className="font-bold">{health?.resources.memory_percent}%</span>
                            </div>
                            <div className="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-2">
                                <div 
                                    className={`h-2 rounded-full transition-all duration-500 ${getResourceColor(health?.resources.memory_percent || 0)}`} 
                                    style={{ width: `${health?.resources.memory_percent}%` }}
                                ></div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Database Stats */}
                <div className="bg-white dark:bg-slate-800 p-6 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700">
                    <div className="flex items-center justify-between mb-4">
                        <Database className="w-6 h-6 text-emerald-500" />
                        <span className="text-xs font-bold text-slate-400 uppercase">Persistence</span>
                    </div>
                    <div className="space-y-2">
                        <div className="flex justify-between py-1">
                            <span className="text-sm text-slate-600 dark:text-slate-400">Connection</span>
                            <span className={`text-xs px-2 py-0.5 rounded font-bold ${health?.database.connected ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                                {health?.database.connected ? 'STABLE' : 'ERROR'}
                            </span>
                        </div>
                        <div className="flex justify-between py-1">
                            <span className="text-sm text-slate-600 dark:text-slate-400">Storage Used</span>
                            <span className="font-bold text-slate-900 dark:text-white">{health?.database.data_size_mb != null ? `${health.database.data_size_mb} MB` : '—'}</span>
                        </div>
                        <div className="flex justify-between py-1">
                            <span className="text-sm text-slate-600 dark:text-slate-400">Collections</span>
                            <span className="font-bold text-slate-900 dark:text-white">{health?.database.collections ?? '—'}</span>
                        </div>
                    </div>
                </div>

                {/* Agent Fleet */}
                <div className="bg-white dark:bg-slate-800 p-6 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700">
                    <div className="flex items-center justify-between mb-4">
                        <Users className="w-6 h-6 text-blue-500" />
                        <span className="text-xs font-bold text-slate-400 uppercase">Agent Fleet</span>
                    </div>
                    <div className="flex items-end justify-between">
                        <div>
                            <p className="text-3xl font-bold text-slate-900 dark:text-white">{health?.agent_fleet.total}</p>
                            <p className="text-sm text-slate-500">Total Agents</p>
                        </div>
                        <div className="text-right">
                            <p className="text-sm font-bold text-emerald-500">{health?.agent_fleet.online} Online</p>
                            <p className="text-sm font-bold text-slate-400">{health?.agent_fleet.stale} Stale</p>
                        </div>
                    </div>
                    <div className="mt-4 flex space-x-1">
                        {[...Array(10)].map((_, i) => (
                            <div key={i} className={`flex-1 h-1 rounded-full ${i < (health?.agent_fleet.health_pct || 0) / 10 ? 'bg-emerald-500' : 'bg-slate-200'}`}></div>
                        ))}
                    </div>
                </div>

                {/* Queue Health */}
                <div className="bg-white dark:bg-slate-800 p-6 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700">
                    <div className="flex items-center justify-between mb-4">
                        <Layers className="w-6 h-6 text-purple-500" />
                        <span className="text-xs font-bold text-slate-400 uppercase">Processing Pipelines</span>
                    </div>
                    <div className="space-y-3">
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-slate-600 dark:text-slate-400">Alert Queue</span>
                            <span className={`text-sm font-bold ${health?.queues.alert_queue && health?.queues.alert_queue > 100 ? 'text-red-500' : 'text-slate-900 dark:text-white'}`}>
                                {health?.queues.alert_queue}
                            </span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-slate-600 dark:text-slate-400">Playbooks</span>
                            <span className="text-sm font-bold text-slate-900 dark:text-white">{health?.queues.running_playbooks} active</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-slate-600 dark:text-slate-400">Tasks</span>
                            <span className="text-sm font-bold text-slate-900 dark:text-white">{health?.queues.deployment_tasks}</span>
                        </div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Background Loops */}
                <div className="lg:col-span-2 bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
                    <div className="p-6 border-b border-slate-100 dark:border-slate-700 flex justify-between items-center">
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center">
                            <Clock className="w-5 h-5 mr-2 text-indigo-500" />
                            Background Processing Loops
                        </h2>
                        <span className="text-xs px-2 py-1 bg-slate-100 dark:bg-slate-700 rounded-full font-bold text-slate-500">
                            {health?.background_tasks.filter(t => t.status === 'running').length ?? 0} ACTIVE
                        </span>
                    </div>
                    <div className="divide-y divide-slate-100 dark:divide-slate-700">
                        {health?.background_tasks.map((task, idx) => (
                            <div key={idx} className="p-4 hover:bg-slate-50 dark:hover:bg-slate-900/50 transition-colors flex items-center justify-between group">
                                <div className="flex items-center space-x-4">
                                    <div className="w-8 h-8 rounded-lg bg-slate-100 dark:bg-slate-700 flex items-center justify-center">
                                        <Activity className="w-4 h-4 text-slate-400 group-hover:text-indigo-500 transition-colors" />
                                    </div>
                                    <div>
                                        <p className="font-bold text-slate-900 dark:text-white">{task.name}</p>
                                        <p className="text-xs text-slate-500">Polling Interval: {task.interval}</p>
                                    </div>
                                </div>
                                <div className="flex items-center space-x-3">
                                    <div className={`flex items-center text-xs font-bold uppercase tracking-wider ${task.status === 'running' ? 'text-emerald-500' : 'text-amber-500'}`}>
                                        {task.status === 'running' ? <CheckCircle className="w-3 h-3 mr-1" /> : <AlertCircle className="w-3 h-3 mr-1" />}
                                        {task.status}
                                    </div>
                                    <ChevronRight className="w-4 h-4 text-slate-300" />
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* System Logs / Alerts */}
                <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 p-6">
                    <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-6 flex items-center">
                        <Shield className="w-5 h-5 mr-2 text-indigo-500" />
                        Infrastructure Alerts
                    </h2>
                    <div className="space-y-4">
                        {health && infraAlerts(health).map((a, idx) => (
                            <div key={idx} className={`p-3 border-l-4 rounded flex space-x-3 ${ALERT_STYLE[a.level].box}`}>
                                {a.level === 'ok'
                                    ? <CheckCircle className={`w-5 h-5 flex-shrink-0 mt-0.5 ${ALERT_STYLE[a.level].icon}`} />
                                    : <AlertCircle className={`w-5 h-5 flex-shrink-0 mt-0.5 ${ALERT_STYLE[a.level].icon}`} />}
                                <div>
                                    <p className={`text-sm font-bold ${ALERT_STYLE[a.level].title}`}>{a.title}</p>
                                    <p className={`text-xs opacity-80 ${ALERT_STYLE[a.level].text}`}>{a.detail}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
};
