import React, { useState, useEffect } from 'react';
import { ShieldCheckIcon, DatabaseIcon, ClockIcon, CheckCircleIcon, XCircleIcon, AlertTriangleIcon, PlayIcon } from './icons';

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
    const [activeTab, setActiveTab] = useState<'overview' | 'backups' | 'restore' | 'dr-tests'>('overview');

    useEffect(() => {
        loadData();

        // Auto-refresh every 30 seconds
        const interval = setInterval(loadData, 30000);
        return () => clearInterval(interval);
    }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            const [backupsRes, statusRes, healthRes, testsRes] = await Promise.all([
                fetch('/api/hadr/backups', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                }),
                fetch('/api/hadr/status', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                }),
                fetch('/api/hadr/health', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                }),
                fetch('/api/hadr/test-history', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                })
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
            const response = await fetch('/api/hadr/backup', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify({ backup_type: backupType })
            });

            if (response.ok) {
                alert('Backup initiated successfully');
                await loadData();
            } else {
                const error = await response.json();
                alert(error.detail || 'Failed to create backup');
            }
        } catch (error) {
            console.error('Failed to create backup:', error);
            alert('Failed to create backup');
        }
    };

    const handleTestDR = async () => {
        if (!confirm('This will test disaster recovery procedures. Continue?')) return;

        try {
            const response = await fetch('/api/hadr/test-dr', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                }
            });

            if (response.ok) {
                const result = await response.json();
                alert(`DR Test ${result.success ? 'PASSED' : 'FAILED'}\nDuration: ${result.duration_minutes} minutes`);
                await loadData();
            } else {
                const error = await response.json();
                alert(error.detail || 'DR test failed');
            }
        } catch (error) {
            console.error('DR test failed:', error);
            alert('DR test failed');
        }
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'healthy': return 'text-green-600 dark:text-green-400';
            case 'degraded': return 'text-amber-600 dark:text-amber-400';
            case 'critical': return 'text-red-600 dark:text-red-400';
            default: return 'text-gray-600 dark:text-gray-400';
        }
    };

    const getBackupStatusColor = (status: string) => {
        switch (status) {
            case 'completed':
            case 'verified':
                return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300';
            case 'in_progress':
                return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300';
            case 'failed':
                return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300';
            default:
                return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300';
        }
    };

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-600 to-cyan-600 bg-clip-text text-transparent">
                        High Availability & Disaster Recovery
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400 mt-1">
                        RTO: 15 minutes | RPO: 1 hour
                    </p>
                </div>
                <div className="flex gap-3">
                    <button
                        onClick={() => handleCreateBackup('full')}
                        className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-semibold transition-colors shadow-lg"
                    >
                        Create Backup
                    </button>
                    <button
                        onClick={handleTestDR}
                        className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors shadow-lg"
                    >
                        Test DR
                    </button>
                </div>
            </div>

            {/* Health Status Cards */}
            {healthStatus && (
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className={`bg-gradient-to-br ${healthStatus.status === 'healthy' ? 'from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 border-green-200 dark:border-green-700' :
                            healthStatus.status === 'degraded' ? 'from-amber-50 to-amber-100 dark:from-amber-900/20 dark:to-amber-800/20 border-amber-200 dark:border-amber-700' :
                                'from-red-50 to-red-100 dark:from-red-900/20 dark:to-red-800/20 border-red-200 dark:border-red-700'
                        } rounded-xl p-6 border shadow-lg`}>
                        <div className="flex items-center gap-3 mb-2">
                            <ShieldCheckIcon size={32} className={getStatusColor(healthStatus.status)} />
                            <p className="text-sm font-semibold text-gray-600 dark:text-gray-400">System Status</p>
                        </div>
                        <p className={`text-2xl font-bold ${getStatusColor(healthStatus.status)} uppercase`}>
                            {healthStatus.status}
                        </p>
                    </div>

                    <div className={`bg-gradient-to-br ${healthStatus.database_connected ? 'from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 border-green-200 dark:border-green-700' :
                            'from-red-50 to-red-100 dark:from-red-900/20 dark:to-red-800/20 border-red-200 dark:border-red-700'
                        } rounded-xl p-6 border shadow-lg`}>
                        <div className="flex items-center gap-3 mb-2">
                            <DatabaseIcon size={32} className={healthStatus.database_connected ? 'text-green-600' : 'text-red-600'} />
                            <p className="text-sm font-semibold text-gray-600 dark:text-gray-400">Database</p>
                        </div>
                        <p className={`text-2xl font-bold ${healthStatus.database_connected ? 'text-green-600' : 'text-red-600'}`}>
                            {healthStatus.database_connected ? 'Connected' : 'Disconnected'}
                        </p>
                    </div>

                    <div className={`bg-gradient-to-br ${healthStatus.rpo_compliant ? 'from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 border-green-200 dark:border-green-700' :
                            'from-red-50 to-red-100 dark:from-red-900/20 dark:to-red-800/20 border-red-200 dark:border-red-700'
                        } rounded-xl p-6 border shadow-lg`}>
                        <div className="flex items-center gap-3 mb-2">
                            <ClockIcon size={32} className={healthStatus.rpo_compliant ? 'text-green-600' : 'text-red-600'} />
                            <p className="text-sm font-semibold text-gray-600 dark:text-gray-400">RPO Compliance</p>
                        </div>
                        <p className={`text-2xl font-bold ${healthStatus.rpo_compliant ? 'text-green-600' : 'text-red-600'}`}>
                            {healthStatus.rpo_compliant ? 'Compliant' : 'Non-Compliant'}
                        </p>
                    </div>

                    <div className={`bg-gradient-to-br ${healthStatus.rto_achievable ? 'from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 border-green-200 dark:border-green-700' :
                            'from-amber-50 to-amber-100 dark:from-amber-900/20 dark:to-amber-800/20 border-amber-200 dark:border-amber-700'
                        } rounded-xl p-6 border shadow-lg`}>
                        <div className="flex items-center gap-3 mb-2">
                            <PlayIcon size={32} className={healthStatus.rto_achievable ? 'text-green-600' : 'text-amber-600'} />
                            <p className="text-sm font-semibold text-gray-600 dark:text-gray-400">RTO Status</p>
                        </div>
                        <p className={`text-2xl font-bold ${healthStatus.rto_achievable ? 'text-green-600' : 'text-amber-600'}`}>
                            {healthStatus.rto_achievable ? 'Achievable' : 'Test Needed'}
                        </p>
                    </div>
                </div>
            )}

            {/* Issues Alert */}
            {healthStatus && healthStatus.issues.length > 0 && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-xl p-6">
                    <div className="flex items-start gap-3">
                        <AlertTriangleIcon size={24} className="text-red-600 dark:text-red-400 flex-shrink-0 mt-1" />
                        <div>
                            <h3 className="text-lg font-bold text-red-900 dark:text-red-100 mb-2">Critical Issues Detected</h3>
                            <ul className="space-y-1">
                                {healthStatus.issues.map((issue, idx) => (
                                    <li key={idx} className="text-sm text-red-700 dark:text-red-300">• {issue}</li>
                                ))}
                            </ul>
                        </div>
                    </div>
                </div>
            )}

            {/* Backup Statistics */}
            {backupStatus && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-lg">
                        <p className="text-sm text-gray-600 dark:text-gray-400 font-semibold mb-2">Total Backups</p>
                        <p className="text-3xl font-bold text-gray-900 dark:text-gray-100">
                            {Object.values(backupStatus.status_counts).reduce((sum, s) => sum + s.count, 0)}
                        </p>
                    </div>
                    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-lg">
                        <p className="text-sm text-gray-600 dark:text-gray-400 font-semibold mb-2">Storage Used</p>
                        <p className="text-3xl font-bold text-gray-900 dark:text-gray-100">
                            {backupStatus.total_size_gb.toFixed(2)} GB
                        </p>
                    </div>
                    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-lg">
                        <p className="text-sm text-gray-600 dark:text-gray-400 font-semibold mb-2">Last Backup</p>
                        <p className="text-lg font-bold text-gray-900 dark:text-gray-100">
                            {backupStatus.latest_backup_time ? new Date(backupStatus.latest_backup_time).toLocaleString() : 'Never'}
                        </p>
                    </div>
                </div>
            )}

            {/* Tabs */}
            <div className="flex gap-2 border-b border-gray-200 dark:border-gray-700">
                {(['overview', 'backups', 'restore', 'dr-tests'] as const).map((tab) => (
                    <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={`px-6 py-3 font-semibold transition-all ${activeTab === tab
                                ? 'border-b-2 border-blue-600 text-blue-600 dark:text-blue-400'
                                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                            }`}
                    >
                        {tab.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}
                    </button>
                ))}
            </div>

            {/* Backups Tab */}
            {activeTab === 'backups' && (
                <div className="space-y-4">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Backup History</h2>
                    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-lg overflow-hidden">
                        <table className="w-full">
                            <thead className="bg-gray-50 dark:bg-gray-700/50">
                                <tr>
                                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Backup ID</th>
                                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Type</th>
                                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Status</th>
                                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Started</th>
                                    <th className="text-right py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Size</th>
                                </tr>
                            </thead>
                            <tbody>
                                {backups.map((backup) => (
                                    <tr key={backup.id} className="border-t border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                        <td className="py-3 px-4 text-sm font-mono text-gray-900 dark:text-gray-100">{backup.backup_id}</td>
                                        <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300 uppercase">{backup.backup_type}</td>
                                        <td className="py-3 px-4">
                                            <span className={`px-2 py-1 rounded-full text-xs font-bold ${getBackupStatusColor(backup.status)}`}>
                                                {backup.status.toUpperCase()}
                                            </span>
                                        </td>
                                        <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300">
                                            {new Date(backup.started_at).toLocaleString()}
                                        </td>
                                        <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300 text-right">
                                            {(backup.size_bytes / (1024 * 1024)).toFixed(2)} MB
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* DR Tests Tab */}
            {activeTab === 'dr-tests' && (
                <div className="space-y-4">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Disaster Recovery Test History</h2>
                    <div className="grid grid-cols-1 gap-4">
                        {drTests.map((test) => (
                            <div key={test.id} className={`bg-white dark:bg-gray-800 rounded-xl border ${test.success ? 'border-green-200 dark:border-green-700' : 'border-red-200 dark:border-red-700'
                                } p-6 shadow-lg`}>
                                <div className="flex items-start justify-between mb-4">
                                    <div>
                                        <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">{test.test_id}</h3>
                                        <p className="text-sm text-gray-600 dark:text-gray-400">{new Date(test.started_at).toLocaleString()}</p>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        {test.success ? (
                                            <CheckCircleIcon size={32} className="text-green-600" />
                                        ) : (
                                            <XCircleIcon size={32} className="text-red-600" />
                                        )}
                                        <span className={`text-lg font-bold ${test.success ? 'text-green-600' : 'text-red-600'}`}>
                                            {test.success ? 'PASSED' : 'FAILED'}
                                        </span>
                                    </div>
                                </div>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                                    <div>
                                        <p className="text-xs text-gray-600 dark:text-gray-400">Duration</p>
                                        <p className="text-lg font-bold text-gray-900 dark:text-gray-100">{test.duration_minutes?.toFixed(2)} min</p>
                                    </div>
                                    <div>
                                        <p className="text-xs text-gray-600 dark:text-gray-400">RTO Achieved</p>
                                        <p className={`text-lg font-bold ${test.rto_achieved ? 'text-green-600' : 'text-red-600'}`}>
                                            {test.rto_achieved ? 'Yes' : 'No'}
                                        </p>
                                    </div>
                                </div>
                                {test.errors && test.errors.length > 0 && (
                                    <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-lg p-3">
                                        <p className="text-sm font-semibold text-red-700 dark:text-red-300 mb-1">Errors:</p>
                                        <ul className="text-xs text-red-600 dark:text-red-400 space-y-1">
                                            {test.errors.map((error, idx) => (
                                                <li key={idx}>• {error}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};
