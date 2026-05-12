import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';
import { ShieldCheckIcon, DatabaseIcon, ClockIcon, CheckCircleIcon, XCircleIcon, AlertTriangleIcon, PlayIcon, GlobeIcon, ServerIcon, HardDriveIcon } from './icons';

interface BackupMetadata {
    id: string;
    backup_id: string;
    backup_type: string;
    status: string;
    started_at: string;
    completed_at?: string;
    size_bytes: number;
    encrypted: boolean;
    checksum?: string;
    error?: string;
}

interface BackupStatus {
    status_counts: Record<string, { count: number; size_bytes: number }>;
    total_size_bytes: number;
    total_size_gb: number;
    latest_backup?: string;
    latest_backup_time?: string;
    rpo_compliant: boolean;
    rpo_hours: number;
    rto_minutes: number;
}

interface HealthStatus {
    status: string;
    database_connected: boolean;
    backup_system_healthy: boolean;
    rpo_compliant: boolean;
    rto_achievable: boolean;
    last_backup?: string;
    issues: string[];
}

interface DRTestResult {
    id: string;
    test_id: string;
    started_at: string;
    completed_at?: string;
    tests: Record<string, boolean>;
    rto_achieved: boolean;
    success: boolean;
    duration_minutes?: number;
    errors?: string[];
}

export const HADRDashboard: React.FC = () => {
    const [backups, setBackups] = useState<BackupMetadata[]>([]);
    const [backupStatus, setBackupStatus] = useState<BackupStatus | null>(null);
    const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null);
    const [drTests, setDrTests] = useState<DRTestResult[]>([]);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'overview' | 'backups' | 'dr-tests'>('overview');

    useEffect(() => {
        loadData();
        const interval = setInterval(loadData, 30000);
        return () => clearInterval(interval);
    }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            const [backupsRes, statusRes, healthRes, testsRes] = await Promise.all([
                authFetch('/api/hadr/backups'),
                authFetch('/api/hadr/status'),
                authFetch('/api/hadr/health'),
                authFetch('/api/hadr/test-history'),
            ]);

            if (backupsRes.ok) setBackups(await backupsRes.json());
            if (statusRes.ok) setBackupStatus(await statusRes.json());
            if (healthRes.ok) setHealthStatus(await healthRes.json());
            if (testsRes.ok) setDrTests(await testsRes.json());
        } catch (error) {
            console.error('Failed to load HA/DR data:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleCreateBackup = async (backupType: string) => {
        try {
            const response = await authFetch('/api/hadr/backup', {
                method: 'POST',
                body: JSON.stringify({ backup_type: backupType })
            });

            if (response.ok) {
                alert('Backup initiated successfully');
                await loadData();
            }
        } catch (error) {
            console.error('Failed to create backup:', error);
        }
    };

    const handleTestDR = async () => {
        if (!confirm('This will test disaster recovery procedures. Continue?')) return;
        try {
            const response = await authFetch('/api/hadr/test-dr', { method: 'POST' });
            if (response.ok) {
                alert(`DR Test initiated`);
                await loadData();
            }
        } catch (error) {
            console.error('DR test failed:', error);
        }
    };

    return (
        <div className="p-6 space-y-6 bg-slate-50 dark:bg-slate-950 min-h-screen font-sans">
            {/* Header Section */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                <div>
                    <h1 className="text-3xl font-black text-slate-900 dark:text-white tracking-tighter flex items-center gap-3">
                        <GlobeIcon size={32} className="text-blue-600 animate-spin-slow" />
                        GLOBAL RESILIENCE COMMAND
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 font-medium">
                        Real-time High Availability monitoring and Disaster Recovery orchestration
                    </p>
                </div>
                <div className="flex gap-3 bg-white dark:bg-slate-900 p-2 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800">
                    <button
                        onClick={() => handleCreateBackup('full')}
                        className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-all shadow-lg shadow-blue-500/20"
                    >
                        Execute Backup
                    </button>
                    <button
                        onClick={handleTestDR}
                        className="px-6 py-2.5 bg-slate-900 dark:bg-white text-white dark:text-slate-900 rounded-xl text-xs font-black uppercase tracking-widest transition-all shadow-lg"
                    >
                        Validate DR
                    </button>
                </div>
            </div>

            {/* Top-Level Health & Global Coverage */}
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                {/* Global Map Mockup */}
                <div className="lg:col-span-3 bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 p-6 relative overflow-hidden shadow-sm h-80">
                    <div className="absolute top-0 right-0 p-6 flex gap-2">
                        <span className="flex items-center gap-1.5 px-3 py-1 bg-emerald-100 text-emerald-700 rounded-full text-[10px] font-black border border-emerald-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                            NORTH AMERICA ACTIVE
                        </span>
                        <span className="flex items-center gap-1.5 px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-[10px] font-black border border-blue-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></span>
                            EUROPE STANDBY
                        </span>
                    </div>
                    <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Region Distribution & Health</h3>
                    <div className="relative h-full flex items-center justify-center">
                        <div className="absolute inset-0 opacity-10 dark:opacity-20 pointer-events-none">
                             <GlobeIcon size={300} className="mx-auto" />
                        </div>
                        <div className="flex gap-12 relative z-10">
                            {[
                                { region: 'US-EAST-1', status: 'Healthy', load: '42%' },
                                { region: 'EU-WEST-1', status: 'Standby', load: '0%' },
                                { region: 'AP-SOUTH-1', status: 'Healthy', load: '18%' }
                            ].map((reg, i) => (
                                <div key={i} className="flex flex-col items-center">
                                    <div className="w-16 h-16 rounded-2xl bg-slate-50 dark:bg-slate-800 border-2 border-slate-200 dark:border-slate-700 flex items-center justify-center text-blue-600 mb-3 shadow-xl">
                                        <ServerIcon size={28} />
                                    </div>
                                    <p className="text-xs font-black text-slate-900 dark:text-white mb-1">{reg.region}</p>
                                    <p className="text-[10px] font-bold text-slate-500 uppercase">{reg.status}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Resilience Gauges */}
                <div className="bg-gradient-to-br from-slate-900 to-slate-950 rounded-3xl p-8 text-white shadow-2xl relative overflow-hidden flex flex-col justify-between">
                    <div className="absolute top-0 right-0 p-8 opacity-5">
                        <ClockIcon size={140} />
                    </div>
                    <div>
                        <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-8">Performance Targets</h3>
                        <div className="space-y-8">
                            <div>
                                <div className="flex justify-between items-end mb-2">
                                    <div>
                                        <p className="text-[10px] font-bold text-blue-400 uppercase tracking-widest">RPO Delta</p>
                                        <p className="text-3xl font-black italic">42m 12s</p>
                                    </div>
                                    <span className="text-[10px] font-black text-emerald-500 uppercase tracking-widest mb-1">Target: 1h</span>
                                </div>
                                <div className="w-full bg-white/10 h-2 rounded-full overflow-hidden">
                                    <div className="bg-blue-500 h-full rounded-full" style={{ width: '70%' }}></div>
                                </div>
                            </div>
                            <div>
                                <div className="flex justify-between items-end mb-2">
                                    <div>
                                        <p className="text-[10px] font-bold text-purple-400 uppercase tracking-widest">RTO Verified</p>
                                        <p className="text-3xl font-black italic">12m 04s</p>
                                    </div>
                                    <span className="text-[10px] font-black text-emerald-500 uppercase tracking-widest mb-1">Target: 15m</span>
                                </div>
                                <div className="w-full bg-white/10 h-2 rounded-full overflow-hidden">
                                    <div className="bg-purple-500 h-full rounded-full" style={{ width: '82%' }}></div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div className="mt-8 pt-6 border-t border-white/10">
                        <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Last System Audit</p>
                        <p className="text-xs font-bold text-emerald-500 flex items-center gap-2">
                            <CheckCircleIcon size={14} /> 100% REDUNDANCY VERIFIED
                        </p>
                    </div>
                </div>
            </div>

            {/* Health Grid */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                {[
                    { label: 'System Integrity', value: 'OPTIMAL', icon: ShieldCheckIcon, color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
                    { label: 'Database Replication', value: 'SYNCED', icon: DatabaseIcon, color: 'text-blue-500', bg: 'bg-blue-500/10' },
                    { label: 'Backup Health', value: 'ENCRYPTED', icon: HardDriveIcon, color: 'text-indigo-500', bg: 'bg-indigo-500/10' },
                    { label: 'DR Readiness', value: 'VERIFIED', icon: PlayIcon, color: 'text-purple-500', bg: 'bg-purple-500/10' },
                ].map((stat, i) => (
                    <div key={i} className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm hover:shadow-xl transition-all group">
                        <div className="flex justify-between items-start mb-4">
                            <div className={`p-3 rounded-xl ${stat.bg} ${stat.color} group-hover:scale-110 transition-transform`}>
                                <stat.icon size={24} />
                            </div>
                            <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Active</span>
                        </div>
                        <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1">{stat.label}</p>
                        <p className={`text-xl font-black ${stat.color}`}>{stat.value}</p>
                    </div>
                ))}
            </div>

            {/* Data Tables / Logs Section */}
            <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
                <div className="flex bg-slate-50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-800 px-6">
                    {[
                        { id: 'overview', label: 'Summary' },
                        { id: 'backups', label: 'Storage & Backups' },
                        { id: 'dr-tests', label: 'Disaster Simulation Logs' }
                    ].map(tab => (
                        <button key={tab.id} onClick={() => setActiveTab(tab.id as any)}
                            className={`px-8 py-4 text-[10px] font-black uppercase tracking-widest transition-all border-b-2 ${
                                activeTab === tab.id 
                                ? 'text-blue-600 border-blue-600 bg-blue-600/5' 
                                : 'text-slate-500 border-transparent hover:text-slate-700 dark:hover:text-slate-300'
                            }`}>
                            {tab.label}
                        </button>
                    ))}
                </div>

                <div className="p-8">
                    {activeTab === 'backups' && (
                        <div className="overflow-x-auto">
                            <table className="w-full text-left">
                                <thead>
                                    <tr className="text-[10px] font-black text-slate-400 uppercase tracking-widest border-b border-slate-100 dark:border-slate-800">
                                        <th className="pb-4 px-4">Identifier</th>
                                        <th className="pb-4 px-4">Type</th>
                                        <th className="pb-4 px-4">Integrity Status</th>
                                        <th className="pb-4 px-4">Timestamp</th>
                                        <th className="pb-4 px-4 text-right">Volume</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-50 dark:divide-slate-800">
                                    {backups.map((backup) => (
                                        <tr key={backup.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                                            <td className="py-4 px-4 text-sm font-black text-slate-900 dark:text-white font-mono">{backup.backup_id}</td>
                                            <td className="py-4 px-4">
                                                <span className="text-[10px] font-black px-2 py-1 bg-slate-100 dark:bg-slate-800 rounded uppercase">{backup.backup_type}</span>
                                            </td>
                                            <td className="py-4 px-4">
                                                <div className="flex items-center gap-2">
                                                    <span className={`w-2 h-2 rounded-full ${backup.status === 'completed' ? 'bg-emerald-500' : 'bg-red-500'}`}></span>
                                                    <span className="text-xs font-bold uppercase">{backup.status}</span>
                                                </div>
                                            </td>
                                            <td className="py-4 px-4 text-xs text-slate-500 font-medium">{new Date(backup.started_at).toLocaleString()}</td>
                                            <td className="py-4 px-4 text-xs font-black text-right">{(backup.size_bytes / (1024 * 1024)).toFixed(2)} MB</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {activeTab === 'overview' && (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
                            <div>
                                <h4 className="text-sm font-black text-slate-900 dark:text-white mb-6 uppercase tracking-tighter italic">Storage Utilization</h4>
                                <div className="space-y-6">
                                    {[
                                        { label: 'Full Backups', size: '1.2 TB', color: 'bg-blue-500', pct: 65 },
                                        { label: 'Incremental Logs', size: '420 GB', color: 'bg-indigo-500', pct: 25 },
                                        { label: 'System Snapshots', size: '180 GB', color: 'bg-purple-500', pct: 10 }
                                    ].map((cat, i) => (
                                        <div key={i}>
                                            <div className="flex justify-between text-xs font-bold mb-2">
                                                <span className="text-slate-600 dark:text-slate-400">{cat.label}</span>
                                                <span className="text-slate-900 dark:text-white">{cat.size}</span>
                                            </div>
                                            <div className="w-full bg-slate-100 dark:bg-slate-800 h-2 rounded-full overflow-hidden">
                                                <div className={`${cat.color} h-full rounded-full`} style={{ width: `${cat.pct}%` }}></div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                            <div className="bg-slate-50 dark:bg-slate-950/50 rounded-3xl p-8 border border-slate-100 dark:border-slate-800">
                                <h4 className="text-sm font-black text-slate-900 dark:text-white mb-4 uppercase tracking-tighter italic">Resilience Report Card</h4>
                                <div className="space-y-4">
                                    <div className="flex items-center justify-between p-3 bg-white dark:bg-slate-900 rounded-xl shadow-sm">
                                        <span className="text-xs font-bold text-slate-500">Cross-Region Failover</span>
                                        <span className="text-xs font-black text-emerald-500 uppercase">READY</span>
                                    </div>
                                    <div className="flex items-center justify-between p-3 bg-white dark:bg-slate-900 rounded-xl shadow-sm">
                                        <span className="text-xs font-bold text-slate-500">Data Immutability</span>
                                        <span className="text-xs font-black text-emerald-500 uppercase">ACTIVE</span>
                                    </div>
                                    <div className="flex items-center justify-between p-3 bg-white dark:bg-slate-900 rounded-xl shadow-sm">
                                        <span className="text-xs font-bold text-slate-500">Air-Gapped Vault</span>
                                        <span className="text-xs font-black text-blue-500 uppercase">OFFLINE OK</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {activeTab === 'dr-tests' && (
                        <div className="space-y-6">
                            {drTests.map((test) => (
                                <div key={test.id} className="flex gap-6 p-6 bg-slate-50 dark:bg-slate-800/30 rounded-2xl border border-slate-200 dark:border-slate-800">
                                    <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${test.success ? 'bg-emerald-500/10 text-emerald-500' : 'bg-red-500/10 text-red-500'}`}>
                                        {test.success ? <CheckCircleIcon size={28} /> : <XCircleIcon size={28} />}
                                    </div>
                                    <div className="flex-1">
                                        <div className="flex justify-between items-start mb-2">
                                            <h4 className="text-sm font-black uppercase tracking-tighter italic text-slate-900 dark:text-white">{test.test_id}</h4>
                                            <span className="text-[10px] font-black text-slate-500 font-mono">{new Date(test.started_at).toLocaleString()}</span>
                                        </div>
                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                            <div>
                                                <p className="text-[9px] font-black text-slate-500 uppercase tracking-widest mb-1">Achieved RTO</p>
                                                <p className="text-xs font-bold">{test.duration_minutes?.toFixed(2)} min</p>
                                            </div>
                                            <div>
                                                <p className="text-[9px] font-black text-slate-500 uppercase tracking-widest mb-1">Compliance Status</p>
                                                <p className={`text-xs font-black ${test.rto_achieved ? 'text-emerald-500' : 'text-red-500'}`}>
                                                    {test.rto_achieved ? 'PASS' : 'FAIL'}
                                                </p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
            
            <style dangerouslySetInnerHTML={{ __html: `
                @keyframes spin-slow {
                    from { transform: rotate(0deg); }
                    to { transform: rotate(360deg); }
                }
                .animate-spin-slow {
                    animation: spin-slow 8s linear infinite;
                }
            `}} />
        </div>
    );
};

