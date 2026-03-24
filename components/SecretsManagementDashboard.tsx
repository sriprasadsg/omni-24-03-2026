import React, { useState, useEffect } from 'react';
import { KeyIcon, ShieldCheckIcon, ClockIcon, AlertTriangleIcon, RefreshCwIcon, TrashIcon, EyeIcon, EyeOffIcon } from './icons';

interface Secret {
    id: string;
    name: string;
    secret_type: string;
    tenant_id: string;
    description?: string;
    status: string;
    version: number;
    rotation_enabled: boolean;
    rotation_days?: number;
    next_rotation?: string;
    created_at: string;
    last_accessed?: string;
    access_count: number;
}

interface AuditLog {
    id: string;
    secret_id: string;
    action: string;
    tenant_id: string;
    user: string;
    timestamp: string;
    details?: any;
}

interface SecretStats {
    total_secrets: number;
    by_status: Record<string, number>;
    by_type: Record<string, number>;
    rotation_needed: number;
}

interface ScanFinding {
    type: string;
    file_path: string;
    line: number;
    pattern: string;
    severity: string;
    recommendation: string;
}

export const SecretsManagementDashboard: React.FC = () => {
    const [secrets, setSecrets] = useState<Secret[]>([]);
    const [stats, setStats] = useState<SecretStats | null>(null);
    const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
    const [scanFindings, setScanFindings] = useState<ScanFinding[]>([]);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'secrets' | 'rotation' | 'audit' | 'scan'>('secrets');
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [showValueModal, setShowValueModal] = useState(false);
    const [selectedSecret, setSelectedSecret] = useState<Secret | null>(null);
    const [secretValue, setSecretValue] = useState('');

    // Form state
    const [formData, setFormData] = useState({
        name: '',
        value: '',
        secret_type: 'api_key',
        description: '',
        rotation_enabled: true
    });

    useEffect(() => {
        loadData();

        // Auto-refresh every 30 seconds
        const interval = setInterval(loadData, 30000);
        return () => clearInterval(interval);
    }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            const [secretsRes, statsRes, auditRes] = await Promise.all([
                fetch('/api/secrets/list', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                }),
                fetch('/api/secrets/stats', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                }),
                fetch('/api/secrets/audit-log?limit=50', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                })
            ]);

            if (secretsRes.ok) setSecrets(await secretsRes.json());
            if (statsRes.ok) setStats(await statsRes.json());
            if (auditRes.ok) setAuditLogs(await auditRes.json());
        } catch (error) {
            console.error('Failed to load secrets data:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleCreateSecret = async (e: React.FormEvent) => {
        e.preventDefault();

        try {
            const response = await fetch('/api/secrets/create', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify(formData)
            });

            if (response.ok) {
                alert('Secret created successfully');
                setShowCreateModal(false);
                setFormData({ name: '', value: '', secret_type: 'api_key', description: '', rotation_enabled: true });
                await loadData();
            } else {
                const error = await response.json();
                alert(error.detail || 'Failed to create secret');
            }
        } catch (error) {
            console.error('Failed to create secret:', error);
            alert('Failed to create secret');
        }
    };

    const handleRotateSecret = async (name: string) => {
        if (!confirm(`Rotate secret "${name}"? This will generate a new value.`)) return;

        try {
            const response = await fetch('/api/secrets/rotate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify({ name })
            });

            if (response.ok) {
                const result = await response.json();
                alert(`Secret rotated successfully!\nNew value: ${result.new_value}\n\nPlease update your applications with this new value.`);
                await loadData();
            } else {
                const error = await response.json();
                alert(error.detail || 'Failed to rotate secret');
            }
        } catch (error) {
            console.error('Failed to rotate secret:', error);
            alert('Failed to rotate secret');
        }
    };

    const handleRevokeSecret = async (name: string) => {
        if (!confirm(`Revoke secret "${name}"? This action cannot be undone.`)) return;

        try {
            const response = await fetch('/api/secrets/revoke', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify({ name })
            });

            if (response.ok) {
                alert('Secret revoked successfully');
                await loadData();
            } else {
                const error = await response.json();
                alert(error.detail || 'Failed to revoke secret');
            }
        } catch (error) {
            console.error('Failed to revoke secret:', error);
            alert('Failed to revoke secret');
        }
    };

    const handleViewSecret = async (secret: Secret) => {
        try {
            const response = await fetch(`/api/secrets/${secret.name}/value`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });

            if (response.ok) {
                const data = await response.json();
                setSecretValue(data.value);
                setSelectedSecret(secret);
                setShowValueModal(true);
            } else {
                const error = await response.json();
                alert(error.detail || 'Failed to get secret value');
            }
        } catch (error) {
            console.error('Failed to get secret value:', error);
            alert('Failed to get secret value');
        }
    };

    const handleScanFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/secrets/scan', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: formData
            });

            if (response.ok) {
                const result = await response.json();
                setScanFindings(result.findings);
                setActiveTab('scan');

                if (result.findings_count === 0) {
                    alert('No hardcoded secrets found! ✅');
                } else {
                    alert(`Found ${result.findings_count} potential hardcoded secrets. Check the Scan tab.`);
                }
            } else {
                const error = await response.json();
                alert(error.detail || 'Failed to scan file');
            }
        } catch (error) {
            console.error('Failed to scan file:', error);
            alert('Failed to scan file');
        }
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'active': return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300';
            case 'rotating': return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300';
            case 'deprecated': return 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300';
            case 'revoked': return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300';
            default: return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300';
        }
    };

    const getTypeIcon = (type: string) => {
        switch (type) {
            case 'api_key': return '🔑';
            case 'database_password': return '🗄️';
            case 'encryption_key': return '🔐';
            case 'certificate': return '📜';
            case 'ssh_key': return '🖥️';
            case 'oauth_token': return '🎫';
            case 'webhook_secret': return '🪝';
            default: return '🔒';
        }
    };

    const isRotationDue = (secret: Secret) => {
        if (!secret.next_rotation) return false;
        return new Date(secret.next_rotation) <= new Date();
    };

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">
                        Secrets Management
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400 mt-1">
                        Centralized secrets storage with automatic rotation
                    </p>
                </div>
                <div className="flex gap-3">
                    <label className="px-6 py-3 bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-semibold transition-colors shadow-lg cursor-pointer">
                        Scan File
                        <input type="file" className="hidden" onChange={handleScanFile} accept=".py,.js,.ts,.java,.go,.rb,.php" />
                    </label>
                    <button
                        onClick={() => setShowCreateModal(true)}
                        className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors shadow-lg"
                    >
                        Create Secret
                    </button>
                </div>
            </div>

            {/* Statistics Cards */}
            {stats && (
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-800/20 rounded-xl p-6 border border-purple-200 dark:border-purple-700 shadow-lg">
                        <div className="flex items-center gap-3 mb-2">
                            <KeyIcon size={32} className="text-purple-600" />
                            <p className="text-sm font-semibold text-purple-600 dark:text-purple-400">Total Secrets</p>
                        </div>
                        <p className="text-3xl font-bold text-purple-900 dark:text-purple-100">{stats.total_secrets}</p>
                    </div>

                    <div className="bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 rounded-xl p-6 border border-green-200 dark:border-green-700 shadow-lg">
                        <div className="flex items-center gap-3 mb-2">
                            <ShieldCheckIcon size={32} className="text-green-600" />
                            <p className="text-sm font-semibold text-green-600 dark:text-green-400">Active</p>
                        </div>
                        <p className="text-3xl font-bold text-green-900 dark:text-green-100">{stats.by_status.active || 0}</p>
                    </div>

                    <div className={`bg-gradient-to-br ${stats.rotation_needed > 0
                            ? 'from-red-50 to-red-100 dark:from-red-900/20 dark:to-red-800/20 border-red-200 dark:border-red-700'
                            : 'from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 border-blue-200 dark:border-blue-700'
                        } rounded-xl p-6 border shadow-lg`}>
                        <div className="flex items-center gap-3 mb-2">
                            <ClockIcon size={32} className={stats.rotation_needed > 0 ? 'text-red-600' : 'text-blue-600'} />
                            <p className="text-sm font-semibold text-gray-600 dark:text-gray-400">Rotation Needed</p>
                        </div>
                        <p className={`text-3xl font-bold ${stats.rotation_needed > 0 ? 'text-red-600' : 'text-blue-600'}`}>
                            {stats.rotation_needed}
                        </p>
                    </div>

                    <div className="bg-gradient-to-br from-amber-50 to-amber-100 dark:from-amber-900/20 dark:to-amber-800/20 rounded-xl p-6 border border-amber-200 dark:border-amber-700 shadow-lg">
                        <div className="flex items-center gap-3 mb-2">
                            <AlertTriangleIcon size={32} className="text-amber-600" />
                            <p className="text-sm font-semibold text-amber-600 dark:text-amber-400">Revoked</p>
                        </div>
                        <p className="text-3xl font-bold text-amber-900 dark:text-amber-100">{stats.by_status.revoked || 0}</p>
                    </div>
                </div>
            )}

            {/* Tabs */}
            <div className="flex gap-2 border-b border-gray-200 dark:border-gray-700">
                {(['secrets', 'rotation', 'audit', 'scan'] as const).map((tab) => (
                    <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={`px-6 py-3 font-semibold transition-all ${activeTab === tab
                                ? 'border-b-2 border-purple-600 text-purple-600 dark:text-purple-400'
                                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                            }`}
                    >
                        {tab.charAt(0).toUpperCase() + tab.slice(1)}
                    </button>
                ))}
            </div>

            {/* Secrets Tab */}
            {activeTab === 'secrets' && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-lg overflow-hidden">
                    <table className="w-full">
                        <thead className="bg-gray-50 dark:bg-gray-700/50">
                            <tr>
                                <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Name</th>
                                <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Type</th>
                                <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Status</th>
                                <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Version</th>
                                <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Next Rotation</th>
                                <th className="text-right py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {secrets.map((secret) => (
                                <tr key={secret.id} className="border-t border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                    <td className="py-3 px-4">
                                        <div className="flex items-center gap-2">
                                            <span className="text-xl">{getTypeIcon(secret.secret_type)}</span>
                                            <div>
                                                <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">{secret.name}</p>
                                                {secret.description && (
                                                    <p className="text-xs text-gray-600 dark:text-gray-400">{secret.description}</p>
                                                )}
                                            </div>
                                        </div>
                                    </td>
                                    <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300">{secret.secret_type.replace('_', ' ')}</td>
                                    <td className="py-3 px-4">
                                        <span className={`px-2 py-1 rounded-full text-xs font-bold ${getStatusColor(secret.status)}`}>
                                            {secret.status.toUpperCase()}
                                        </span>
                                    </td>
                                    <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300">v{secret.version}</td>
                                    <td className="py-3 px-4">
                                        {secret.next_rotation ? (
                                            <span className={`text-sm ${isRotationDue(secret) ? 'text-red-600 font-bold' : 'text-gray-700 dark:text-gray-300'}`}>
                                                {new Date(secret.next_rotation).toLocaleDateString()}
                                                {isRotationDue(secret) && ' ⚠️'}
                                            </span>
                                        ) : (
                                            <span className="text-sm text-gray-500">Manual</span>
                                        )}
                                    </td>
                                    <td className="py-3 px-4 text-right">
                                        <div className="flex gap-2 justify-end">
                                            <button
                                                onClick={() => handleViewSecret(secret)}
                                                className="p-2 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded transition-colors"
                                                title="View secret"
                                            >
                                                <EyeIcon size={18} />
                                            </button>
                                            {secret.status === 'active' && secret.rotation_enabled && (
                                                <button
                                                    onClick={() => handleRotateSecret(secret.name)}
                                                    className="p-2 text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20 rounded transition-colors"
                                                    title="Rotate secret"
                                                >
                                                    <RefreshCwIcon size={18} />
                                                </button>
                                            )}
                                            {secret.status === 'active' && (
                                                <button
                                                    onClick={() => handleRevokeSecret(secret.name)}
                                                    className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors"
                                                    title="Revoke secret"
                                                >
                                                    <TrashIcon size={18} />
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Rotation Tab */}
            {activeTab === 'rotation' && (
                <div className="space-y-4">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Secrets Requiring Rotation</h2>
                    <div className="grid grid-cols-1 gap-4">
                        {secrets.filter(s => isRotationDue(s)).map((secret) => (
                            <div key={secret.id} className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-xl p-6">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">{secret.name}</h3>
                                        <p className="text-sm text-gray-600 dark:text-gray-400">Type: {secret.secret_type.replace('_', ' ')}</p>
                                        <p className="text-sm text-red-600 dark:text-red-400 font-semibold mt-1">
                                            Due: {new Date(secret.next_rotation!).toLocaleString()}
                                        </p>
                                    </div>
                                    <button
                                        onClick={() => handleRotateSecret(secret.name)}
                                        className="px-6 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg font-semibold transition-colors"
                                    >
                                        Rotate Now
                                    </button>
                                </div>
                            </div>
                        ))}
                        {secrets.filter(s => isRotationDue(s)).length === 0 && (
                            <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-700 rounded-xl p-12 text-center">
                                <ShieldCheckIcon size={64} className="mx-auto mb-4 text-green-600 opacity-50" />
                                <p className="text-green-700 dark:text-green-300 font-semibold">All secrets are up to date! ✅</p>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Audit Tab */}
            {activeTab === 'audit' && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-lg overflow-hidden">
                    <table className="w-full">
                        <thead className="bg-gray-50 dark:bg-gray-700/50">
                            <tr>
                                <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Timestamp</th>
                                <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Action</th>
                                <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">User</th>
                                <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Details</th>
                            </tr>
                        </thead>
                        <tbody>
                            {auditLogs.map((log) => (
                                <tr key={log.id} className="border-t border-gray-100 dark:border-gray-700">
                                    <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300">
                                        {new Date(log.timestamp).toLocaleString()}
                                    </td>
                                    <td className="py-3 px-4">
                                        <span className={`px-2 py-1 rounded-full text-xs font-bold ${log.action === 'create' ? 'bg-green-100 text-green-700' :
                                                log.action === 'read' ? 'bg-blue-100 text-blue-700' :
                                                    log.action === 'update' ? 'bg-amber-100 text-amber-700' :
                                                        log.action === 'rotate' ? 'bg-purple-100 text-purple-700' :
                                                            log.action === 'revoke' ? 'bg-red-100 text-red-700' :
                                                                'bg-gray-100 text-gray-700'
                                            }`}>
                                            {log.action.toUpperCase()}
                                        </span>
                                    </td>
                                    <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300">{log.user}</td>
                                    <td className="py-3 px-4 text-sm text-gray-600 dark:text-gray-400">
                                        {log.details && JSON.stringify(log.details)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Scan Tab */}
            {activeTab === 'scan' && (
                <div className="space-y-4">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Secret Scan Results</h2>
                    {scanFindings.length > 0 ? (
                        <div className="grid grid-cols-1 gap-4">
                            {scanFindings.map((finding, idx) => (
                                <div key={idx} className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-xl p-6">
                                    <div className="flex items-start gap-4">
                                        <AlertTriangleIcon size={24} className="text-red-600 flex-shrink-0 mt-1" />
                                        <div className="flex-1">
                                            <div className="flex items-center gap-3 mb-2">
                                                <span className="px-2 py-1 bg-red-600 text-white text-xs font-bold rounded">
                                                    {finding.severity.toUpperCase()}
                                                </span>
                                                <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                                                    {finding.type.replace('_', ' ').toUpperCase()}
                                                </span>
                                            </div>
                                            <p className="text-sm text-gray-700 dark:text-gray-300 mb-1">
                                                <span className="font-semibold">File:</span> {finding.file_path} (Line {finding.line})
                                            </p>
                                            <p className="text-sm text-red-700 dark:text-red-300 font-semibold">
                                                ⚠️ {finding.recommendation}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="bg-gray-50 dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-12 text-center">
                            <ShieldCheckIcon size={64} className="mx-auto mb-4 text-gray-400 opacity-50" />
                            <p className="text-gray-600 dark:text-gray-400">No scan results yet. Upload a file to scan for hardcoded secrets.</p>
                        </div>
                    )}
                </div>
            )}

            {/* Create Secret Modal */}
            {showCreateModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white dark:bg-gray-800 rounded-xl p-8 max-w-md w-full mx-4 shadow-2xl">
                        <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Create New Secret</h2>
                        <form onSubmit={handleCreateSecret} className="space-y-4">
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Name</label>
                                <input
                                    type="text"
                                    value={formData.name}
                                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                    required
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Value</label>
                                <input
                                    type="password"
                                    value={formData.value}
                                    onChange={(e) => setFormData({ ...formData, value: e.target.value })}
                                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                    required
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Type</label>
                                <select
                                    value={formData.secret_type}
                                    onChange={(e) => setFormData({ ...formData, secret_type: e.target.value })}
                                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                >
                                    <option value="api_key">API Key</option>
                                    <option value="database_password">Database Password</option>
                                    <option value="encryption_key">Encryption Key</option>
                                    <option value="certificate">Certificate</option>
                                    <option value="ssh_key">SSH Key</option>
                                    <option value="oauth_token">OAuth Token</option>
                                    <option value="webhook_secret">Webhook Secret</option>
                                </select>
                            </div>
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Description (optional)</label>
                                <input
                                    type="text"
                                    value={formData.description}
                                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                />
                            </div>
                            <div className="flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    checked={formData.rotation_enabled}
                                    onChange={(e) => setFormData({ ...formData, rotation_enabled: e.target.checked })}
                                    className="w-4 h-4"
                                />
                                <label className="text-sm text-gray-700 dark:text-gray-300">Enable automatic rotation</label>
                            </div>
                            <div className="flex gap-3 pt-4">
                                <button
                                    type="button"
                                    onClick={() => setShowCreateModal(false)}
                                    className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    className="flex-1 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors"
                                >
                                    Create
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* View Secret Modal */}
            {showValueModal && selectedSecret && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white dark:bg-gray-800 rounded-xl p-8 max-w-md w-full mx-4 shadow-2xl">
                        <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Secret Value</h2>
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Name</label>
                                <p className="text-gray-900 dark:text-gray-100">{selectedSecret.name}</p>
                            </div>
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Value</label>
                                <div className="p-4 bg-gray-100 dark:bg-gray-700 rounded-lg font-mono text-sm break-all">
                                    {secretValue}
                                </div>
                            </div>
                            <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg p-4">
                                <p className="text-sm text-amber-700 dark:text-amber-300">
                                    ⚠️ This access has been logged for audit purposes.
                                </p>
                            </div>
                            <button
                                onClick={() => {
                                    setShowValueModal(false);
                                    setSecretValue('');
                                    setSelectedSecret(null);
                                }}
                                className="w-full px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors"
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
