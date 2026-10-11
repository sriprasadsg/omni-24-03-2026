import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';
import { ShieldCheckIcon, ClockIcon, CheckCircleIcon, XCircleIcon, AlertTriangleIcon } from './icons';
import { showToast } from '../utils/toast';

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

export const formatBytes = (bytes: number) => {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
    return `${(bytes / 1024 ** i).toFixed(i ? 1 : 0)} ${units[i]}`;
};

const formatMinutes = (minutes: number) => {
    if (minutes < 1) return `${Math.round(minutes * 60)}s`;
    if (minutes < 60) return `${Math.floor(minutes)}m ${Math.round((minutes % 1) * 60)}s`;
    const h = Math.floor(minutes / 60);
    return h < 48 ? `${h}h ${Math.round(minutes % 60)}m` : `${Math.floor(h / 24)}d ${h % 24}h`;
};

// Everything the overview shows, derived from the HA/DR APIs (no fixed figures)
export const hadrSummary = (
    backups: BackupMetadata[], status: BackupStatus | null, health: HealthStatus | null,
    tests: DRTestResult[], now = Date.now(),
) => {
    const completed = backups.filter(b => b.status === 'completed');
    const latestTime = status?.latest_backup_time
        || completed.map(b => b.completed_at || b.started_at).sort().slice(-1)[0];
    const sinceMin = latestTime ? (now - new Date(latestTime).getTime()) / 60000 : null;
    const lastTest = [...tests].sort((a, b) => b.started_at.localeCompare(a.started_at))[0];
    const totalBytes = backups.reduce((n, b) => n + (b.size_bytes || 0), 0);
    const types = new Map<string, { count: number; bytes: number }>();
    for (const b of backups) {
        const t = types.get(b.backup_type) || { count: 0, bytes: 0 };
        types.set(b.backup_type, { count: t.count + 1, bytes: t.bytes + (b.size_bytes || 0) });
    }
    const rpoTargetMin = status?.rpo_hours ? status.rpo_hours * 60 : null;
    const rtoTargetMin = status?.rto_minutes ?? null;
    const drOk = !!lastTest && lastTest.success && lastTest.rto_achieved;
    return {
        completed: completed.length,
        failed: backups.filter(b => b.status === 'failed').length,
        encrypted: backups.filter(b => b.encrypted).length,
        storedLabel: formatBytes(status?.total_size_bytes ?? totalBytes),
        latestBackupAgo: sinceMin === null ? null : formatMinutes(sinceMin),
        rpoTarget: rpoTargetMin ? formatMinutes(rpoTargetMin) : '—',
        rpoPct: sinceMin !== null && rpoTargetMin ? (sinceMin / rpoTargetMin) * 100 : null,
        lastTestDuration: lastTest?.duration_minutes != null ? formatMinutes(lastTest.duration_minutes) : null,
        rtoTarget: rtoTargetMin ? formatMinutes(rtoTargetMin) : '—',
        rtoPct: lastTest?.duration_minutes != null && rtoTargetMin ? (lastTest.duration_minutes / rtoTargetMin) * 100 : null,
        drState: !lastTest
            ? { ok: false, label: 'NOT TESTED YET' }
            : { ok: drOk, label: `${drOk ? 'PASSED' : 'FAILED'} — ${new Date(lastTest.started_at).toLocaleString()}` },
        byType: [...types.entries()].map(([type, v]) => ({ type, ...v, pct: totalBytes ? Math.round((v.bytes / totalBytes) * 100) : 0 })),
        tiles: [
            { label: 'Database', value: health ? (health.database_connected ? 'CONNECTED' : 'DISCONNECTED') : '—', ok: health ? health.database_connected : null },
            { label: 'Backup System', value: health ? (health.backup_system_healthy ? 'HEALTHY' : 'NEEDS ATTENTION') : '—', ok: health ? health.backup_system_healthy : null },
            { label: 'RPO', value: health ? (health.rpo_compliant ? 'WITHIN TARGET' : 'TARGET MISSED') : '—', ok: health ? health.rpo_compliant : null },
            { label: 'DR Readiness', value: lastTest ? (drOk ? 'TESTED' : 'LAST TEST FAILED') : 'NOT TESTED', ok: lastTest ? drOk : null },
        ],
    };
};

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
                showToast('Backup initiated successfully', 'success');
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
                showToast('DR Test initiated', 'success');
                await loadData();
            }
        } catch (error) {
            console.error('DR test failed:', error);
        }
    };

    const summary = hadrSummary(backups, backupStatus, healthStatus, drTests);

    return (
        <div className="p-6 space-y-6 bg-slate-50 dark:bg-slate-950 min-h-screen font-sans">
            {/* Header Section */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                <div>
                    <h1 className="text-3xl font-black text-slate-900 dark:text-white tracking-tighter flex items-center gap-3">
                        <ShieldCheckIcon size={32} className="text-blue-600" />
                        HA/DR &amp; BACKUPS
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 font-medium">
                        Backups, recovery targets and disaster-recovery tests
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

            {/* Status, targets and health — all from /api/hadr/* */}
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                <div className="lg:col-span-3 bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm">
                    <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Backup &amp; Recovery Status</h3>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        {[
                            { label: 'Latest Backup', value: summary.latestBackupAgo ?? 'No backups yet' },
                            { label: 'Completed / Failed', value: `${summary.completed} / ${summary.failed}` },
                            { label: 'Stored', value: summary.storedLabel },
                            { label: 'Encrypted', value: `${summary.encrypted} of ${backups.length}` },
                        ].map(f => (
                            <div key={f.label} className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/50">
                                <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1">{f.label}</p>
                                <p className="text-lg font-black text-slate-900 dark:text-white">{f.value}</p>
                            </div>
                        ))}
                    </div>
                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-6 mb-2">Reported Issues</h4>
                    {healthStatus?.issues?.length ? (
                        <ul className="space-y-1">
                            {healthStatus.issues.map((issue, i) => (
                                <li key={i} className="text-xs text-amber-600 dark:text-amber-400 flex items-center gap-2">
                                    <AlertTriangleIcon size={12} /> {issue}
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className="text-xs text-slate-500">{healthStatus ? 'No issues reported.' : 'Health check unavailable.'}</p>
                    )}
                </div>

                <div className="bg-gradient-to-br from-slate-900 to-slate-950 rounded-3xl p-8 text-white shadow-2xl relative overflow-hidden flex flex-col justify-between">
                    <div className="absolute top-0 right-0 p-8 opacity-5">
                        <ClockIcon size={140} />
                    </div>
                    <div>
                        <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-8">Recovery Targets</h3>
                        <div className="space-y-8">
                            {[
                                { label: 'RPO — since last backup', value: summary.latestBackupAgo ?? '—', target: summary.rpoTarget, pct: summary.rpoPct, color: 'bg-blue-500', text: 'text-blue-400' },
                                { label: 'RTO — last DR test', value: summary.lastTestDuration ?? '—', target: summary.rtoTarget, pct: summary.rtoPct, color: 'bg-purple-500', text: 'text-purple-400' },
                            ].map(t => (
                                <div key={t.label}>
                                    <div className="flex justify-between items-end mb-2">
                                        <div>
                                            <p className={`text-[10px] font-bold uppercase tracking-widest ${t.text}`}>{t.label}</p>
                                            <p className="text-3xl font-black italic">{t.value}</p>
                                        </div>
                                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Target: {t.target}</span>
                                    </div>
                                    <div className="w-full bg-white/10 h-2 rounded-full overflow-hidden">
                                        <div className={`${t.pct !== null && t.pct > 100 ? 'bg-red-500' : t.color} h-full rounded-full`} style={{ width: `${Math.min(100, t.pct ?? 0)}%` }}></div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                    <div className="mt-8 pt-6 border-t border-white/10">
                        <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Last DR Test</p>
                        <p className={`text-xs font-bold flex items-center gap-2 ${summary.drState.ok ? 'text-emerald-500' : 'text-amber-500'}`}>
                            {summary.drState.ok ? <CheckCircleIcon size={14} /> : <AlertTriangleIcon size={14} />} {summary.drState.label}
                        </p>
                    </div>
                </div>
            </div>

            {/* Health Grid */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                {summary.tiles.map((stat, i) => (
                    <div key={i} className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm">
                        <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1">{stat.label}</p>
                        <p className={`text-xl font-black ${stat.ok === null ? 'text-slate-400' : stat.ok ? 'text-emerald-500' : 'text-red-500'}`}>{stat.value}</p>
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
                                    {backups.length === 0 && (
                                        <tr><td colSpan={5} className="py-8 text-center text-xs text-slate-500">No backups yet.</td></tr>
                                    )}
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
                                <h4 className="text-sm font-black text-slate-900 dark:text-white mb-6 uppercase tracking-tighter italic">Storage by Backup Type</h4>
                                {summary.byType.length === 0 ? (
                                    <p className="text-xs text-slate-500">No backups yet. Use “Execute Backup” to create the first one.</p>
                                ) : (
                                    <div className="space-y-6">
                                        {summary.byType.map(cat => (
                                            <div key={cat.type}>
                                                <div className="flex justify-between text-xs font-bold mb-2">
                                                    <span className="text-slate-600 dark:text-slate-400 capitalize">{cat.type} ({cat.count})</span>
                                                    <span className="text-slate-900 dark:text-white">{formatBytes(cat.bytes)}</span>
                                                </div>
                                                <div className="w-full bg-slate-100 dark:bg-slate-800 h-2 rounded-full overflow-hidden">
                                                    <div className="bg-blue-500 h-full rounded-full" style={{ width: `${cat.pct}%` }}></div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                            <div className="bg-slate-50 dark:bg-slate-950/50 rounded-3xl p-8 border border-slate-100 dark:border-slate-800">
                                <h4 className="text-sm font-black text-slate-900 dark:text-white mb-4 uppercase tracking-tighter italic">Health Checks</h4>
                                <div className="space-y-4">
                                    {summary.tiles.map(t => (
                                        <div key={t.label} className="flex items-center justify-between p-3 bg-white dark:bg-slate-900 rounded-xl shadow-sm">
                                            <span className="text-xs font-bold text-slate-500">{t.label}</span>
                                            <span className={`text-xs font-black uppercase ${t.ok === null ? 'text-slate-400' : t.ok ? 'text-emerald-500' : 'text-red-500'}`}>{t.value}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}

                    {activeTab === 'dr-tests' && (
                        <div className="space-y-6">
                            {drTests.length === 0 && <p className="text-xs text-slate-500 text-center py-8">No DR tests yet. Use “Validate DR” to run one.</p>}
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

