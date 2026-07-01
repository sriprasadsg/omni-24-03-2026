import React, { useState, useEffect } from 'react';
import { KeyIcon, ShieldCheckIcon, ClockIcon, AlertTriangleIcon } from './icons';
import { authFetch } from '../services/apiService';
import { Secret, SecretsTableTab } from './SecretsTableTab';
import { CreateSecretModal, ViewSecretModal } from './SecretsModals';
import { showToast } from '../utils/toast';

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
    const [rotatedValue, setRotatedValue] = useState<string | null>(null);
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

    const showToast = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 4000);
    };
    const [formData, setFormData] = useState({
        name: '', value: '', secret_type: 'api_key', description: '', rotation_enabled: true
    });

    useEffect(() => {
        loadData();
        const interval = setInterval(loadData, 30000);
        return () => clearInterval(interval);
    }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            const [secretsRes, statsRes, auditRes] = await Promise.all([
                authFetch('/api/secrets/list'),
                authFetch('/api/secrets/stats'),
                authFetch('/api/secrets/audit-log?limit=50'),
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
        // Clear the sensitive value from state immediately — do not wait for the response
        const payload = { ...formData };
        setFormData({ name: '', value: '', secret_type: 'api_key', description: '', rotation_enabled: true });
        try {
            const response = await authFetch('/api/secrets/create', { method: 'POST', body: JSON.stringify(payload) });
            if (response.ok) {
                showToast('Secret created successfully');
                setShowCreateModal(false);
                await loadData();
            } else {
                const error = await response.json();
                showToast(error.detail || 'Failed to create secret', false);
            }
        } catch (error) {
            console.error('Failed to create secret:', error);
            showToast('Failed to create secret', false);
        }
    };

    const handleRotateSecret = async (name: string) => {
        if (!window.confirm(`Rotate secret "${name}"? This will generate a new value.`)) return;
        try {
            const response = await authFetch('/api/secrets/rotate', { method: 'POST', body: JSON.stringify({ name }) });
            if (response.ok) {
                const result = await response.json();
                // Show new value in a secure in-page modal — never via alert() which appears
                // in the OS window title and is visible to screen-recording software
                setRotatedValue(result.new_value ?? null);
                showToast('Secret rotated — copy the new value below before dismissing', true);
                await loadData();
            } else {
                const error = await response.json();
                showToast(error.detail || 'Failed to rotate secret', false);
            }
        } catch (error) {
            console.error('Failed to rotate secret:', error);
            showToast('Failed to rotate secret', false);
        }
    };

    const handleRevokeSecret = async (name: string) => {
        if (!confirm(`Revoke secret "${name}"? This action cannot be undone.`)) return;
        try {
            const response = await authFetch('/api/secrets/revoke', { method: 'POST', body: JSON.stringify({ name }) });
            if (response.ok) {
                showToast('Secret revoked successfully', true);
                await loadData();
            } else {
                const error = await response.json();
                showToast(error.detail || 'Failed to revoke secret', false);
            }
        } catch (error) {
            console.error('Failed to revoke secret:', error);
            showToast('Failed to revoke secret', false);
        }
    };

    const handleViewSecret = async (secret: Secret) => {
        try {
            const response = await authFetch(`/api/secrets/${secret.name}/value`);
            if (response.ok) {
                const data = await response.json();
                setSecretValue(data.value);
                setSelectedSecret(secret);
                setShowValueModal(true);
                // Auto-clear the plaintext value after 60 s — limits exposure window
                setTimeout(() => {
                    setSecretValue('');
                    setShowValueModal(false);
                }, 60_000);
            } else {
                const error = await response.json();
                showToast(error.detail || 'Failed to get secret value', false);
            }
        } catch (error) {
            console.error('Failed to get secret value:', error);
            showToast('Failed to get secret value', false);
        }
    };

    const handleScanFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        const fd = new FormData();
        fd.append('file', file);
        try {
            const response = await fetch('/api/secrets/scan', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${sessionStorage.getItem('token')}` },
                body: fd
            });
            if (response.ok) {
                const result = await response.json();
                setScanFindings(result.findings);
                setActiveTab('scan');
                if (result.findings_count === 0) {
                    showToast('No hardcoded secrets found!', true);
                } else {
                    showToast(`Found ${result.findings_count} potential hardcoded secrets. Check the Scan tab.`, false);
                }
            } else {
                const error = await response.json();
                showToast(error.detail || 'Failed to scan file', false);
            }
        } catch (error) {
            console.error('Failed to scan file:', error);
            showToast('Failed to scan file', false);
        }
    };

    const isRotationDue = (secret: Secret) => {
        if (!secret.next_rotation) return false;
        return new Date(secret.next_rotation) <= new Date();
    };

    return (
        <div className="p-6 space-y-6">
            {/* In-page toast — never use alert() for security-sensitive messages */}
            {toast && (
                <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white ${toast.ok ? 'bg-green-600' : 'bg-red-600'}`}>
                    {toast.msg}
                </div>
            )}

            {/* Rotated secret modal — shows new value securely, not via OS alert */}
            {rotatedValue !== null && (
                <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-md p-6 space-y-4">
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Secret Rotated</h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400">Copy this value now — it will not be shown again.</p>
                        <div className="flex items-center gap-2">
                            <code className="flex-1 px-3 py-2 bg-gray-100 dark:bg-gray-700 rounded text-sm font-mono text-gray-900 dark:text-white break-all select-all">
                                {rotatedValue}
                            </code>
                            <button onClick={() => navigator.clipboard.writeText(rotatedValue)}
                                className="px-3 py-2 text-sm bg-primary-600 text-white rounded hover:bg-primary-700">
                                Copy
                            </button>
                        </div>
                        <button onClick={() => setRotatedValue(null)}
                            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
                            Done
                        </button>
                    </div>
                </div>
            )}

            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">
                        Secrets Management
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400 mt-1">Centralized secrets storage with automatic rotation</p>
                </div>
                <div className="flex gap-3">
                    <label className="px-6 py-3 bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-semibold transition-colors shadow-lg cursor-pointer">
                        Scan File
                        <input type="file" className="hidden" onChange={handleScanFile} accept=".py,.js,.ts,.java,.go,.rb,.php" />
                    </label>
                    <button onClick={() => setShowCreateModal(true)}
                        className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors shadow-lg">
                        Create Secret
                    </button>
                </div>
            </div>

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

            <div className="flex gap-2 border-b border-gray-200 dark:border-gray-700">
                {(['secrets', 'rotation', 'audit', 'scan'] as const).map((tab) => (
                    <button key={tab} onClick={() => setActiveTab(tab)}
                        className={`px-6 py-3 font-semibold transition-all ${activeTab === tab
                            ? 'border-b-2 border-purple-600 text-purple-600 dark:text-purple-400'
                            : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'}`}>
                        {tab.charAt(0).toUpperCase() + tab.slice(1)}
                    </button>
                ))}
            </div>

            {activeTab === 'secrets' && (
                <SecretsTableTab
                    secrets={secrets}
                    isRotationDue={isRotationDue}
                    onView={handleViewSecret}
                    onRotate={handleRotateSecret}
                    onRevoke={handleRevokeSecret}
                />
            )}

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
                                    <button onClick={() => handleRotateSecret(secret.name)}
                                        className="px-6 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg font-semibold transition-colors">
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
                                    <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300">{new Date(log.timestamp).toLocaleString()}</td>
                                    <td className="py-3 px-4">
                                        <span className={`px-2 py-1 rounded-full text-xs font-bold ${log.action === 'create' ? 'bg-green-100 text-green-700' :
                                            log.action === 'read' ? 'bg-blue-100 text-blue-700' :
                                            log.action === 'update' ? 'bg-amber-100 text-amber-700' :
                                            log.action === 'rotate' ? 'bg-purple-100 text-purple-700' :
                                            log.action === 'revoke' ? 'bg-red-100 text-red-700' :
                                            'bg-gray-100 text-gray-700'}`}>
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

            {showCreateModal && (
                <CreateSecretModal
                    formData={formData}
                    onChange={setFormData}
                    onSubmit={handleCreateSecret}
                    onClose={() => setShowCreateModal(false)}
                />
            )}

            {showValueModal && selectedSecret && (
                <ViewSecretModal
                    secret={selectedSecret}
                    secretValue={secretValue}
                    onClose={() => { setShowValueModal(false); setSecretValue(''); setSelectedSecret(null); }}
                />
            )}
        </div>
    );
};
