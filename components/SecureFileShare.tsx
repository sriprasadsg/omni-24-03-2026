import React, { useState, useEffect } from 'react';
import {
    Link as LinkIcon, Lock, Clock, Eye, Trash2, Copy, FileText, Plus, Check
} from 'lucide-react';

interface SharedFile {
    id: string;
    file_name: string;
    file_url: string;
    created_at: string;
    expires_at: string | null;
    access_token: string;
    access_count: number;
    max_accesses: number | null;
    password_protected: boolean;
    is_active: boolean;
}

export default function SecureFileShare() {
    const [shares, setShares] = useState<SharedFile[]>([]);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [loading, setLoading] = useState(true);
    const [copiedId, setCopiedId] = useState<string | null>(null);

    // Form State
    const [newShare, setNewShare] = useState({
        file_name: 'Audit_Report_2025.pdf', // Mock selection
        file_url: '/docs/audit_report.pdf',
        expires_in_days: 7,
        password_protected: false,
        password: '',
        max_accesses: 10
    });

    useEffect(() => {
        fetchShares();
    }, []);

    const fetchShares = async () => {
        try {
            const response = await fetch('/api/file-share/shares');
            if (response.ok) {
                setShares(await response.json());
            }
        } catch (error) {
            console.error("Error fetching shares", error);
        } finally {
            setLoading(false);
        }
    };

    const handleCreateShare = async () => {
        const expires_at = new Date();
        expires_at.setDate(expires_at.getDate() + newShare.expires_in_days);

        try {
            const response = await fetch('/api/file-share/shares', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_name: newShare.file_name,
                    file_url: newShare.file_url,
                    created_by: 'admin',
                    expires_at: expires_at.toISOString(),
                    password_protected: newShare.password_protected,
                    password: newShare.password_protected ? newShare.password : null,
                    max_accesses: newShare.max_accesses
                })
            });

            if (response.ok) {
                const created = await response.json();
                setShares(prev => [...prev, created]);
                setShowCreateModal(false);
            }
        } catch (error) {
            console.error("Error creating share", error);
        }
    };

    const handleRevoke = async (id: string) => {
        try {
            const response = await fetch(`/api/file-share/shares/${id}`, {
                method: 'DELETE'
            });
            if (response.ok) {
                setShares(prev => prev.filter(s => s.id !== id));
            }
        } catch (error) {
            console.error("Error revoking share", error);
        }
    };

    const copyToClipboard = (token: string, id: string) => {
        const link = `${window.location.origin}/shared/${token}`;
        navigator.clipboard.writeText(link);
        setCopiedId(id);
        setTimeout(() => setCopiedId(null), 2000);
    };

    return (
        <div className="p-6 max-w-7xl mx-auto space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">
                        Secure File Sharing
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400">
                        Create time-limited, audited links for sensitive documents.
                    </p>
                </div>
                <button
                    onClick={() => setShowCreateModal(true)}
                    className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg flex items-center gap-2 transition-colors"
                >
                    <Plus className="w-4 h-4" />
                    New Share Link
                </button>
            </div>

            <div className="bg-white dark:bg-[#0f1115] rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
                <table className="w-full text-left text-sm">
                    <thead className="bg-gray-50 dark:bg-[#0b0c0e] text-gray-500 dark:text-gray-400 uppercase text-xs">
                        <tr>
                            <th className="px-6 py-3 font-medium">File</th>
                            <th className="px-6 py-3 font-medium">Security</th>
                            <th className="px-6 py-3 font-medium">Expires</th>
                            <th className="px-6 py-3 font-medium">Access Count</th>
                            <th className="px-6 py-3 font-medium">Link</th>
                            <th className="px-6 py-3 font-medium text-right">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                        {shares.map(share => (
                            <tr key={share.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                                <td className="px-6 py-4 font-medium flex items-center gap-2">
                                    <FileText className="w-4 h-4 text-gray-400" />
                                    {share.file_name}
                                </td>
                                <td className="px-6 py-4">
                                    {share.password_protected ? (
                                        <span className="flex items-center gap-1 text-green-600 text-xs font-medium bg-green-50 px-2 py-0.5 rounded-full w-fit">
                                            <Lock className="w-3 h-3" /> Password
                                        </span>
                                    ) : (
                                        <span className="text-xs text-gray-400">Public Link</span>
                                    )}
                                </td>
                                <td className="px-6 py-4 text-gray-500">
                                    {share.expires_at ? new Date(share.expires_at).toLocaleDateString() : 'Never'}
                                </td>
                                <td className="px-6 py-4">
                                    <div className="flex items-center gap-2">
                                        <div className="w-full bg-gray-200 rounded-full h-1.5 w-16">
                                            <div
                                                className="bg-purple-500 h-1.5 rounded-full"
                                                style={{ width: `${Math.min(((share.access_count / (share.max_accesses || 100)) * 100), 100)}%` }}
                                            ></div>
                                        </div>
                                        <span className="text-xs text-gray-500">
                                            {share.access_count} / {share.max_accesses || '∞'}
                                        </span>
                                    </div>
                                </td>
                                <td className="px-6 py-4">
                                    <button
                                        onClick={() => copyToClipboard(share.access_token, share.id)}
                                        className="text-blue-500 hover:text-blue-600 text-xs font-medium flex items-center gap-1"
                                    >
                                        {copiedId === share.id ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                                        {copiedId === share.id ? 'Copied' : 'Copy Link'}
                                    </button>
                                </td>
                                <td className="px-6 py-4 text-right">
                                    <button
                                        onClick={() => handleRevoke(share.id)}
                                        className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                                        title="Revoke Access"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
                {shares.length === 0 && !loading && (
                    <div className="p-12 text-center text-gray-400">
                        No active share links. Create one to get started.
                    </div>
                )}
            </div>

            {/* Create Modal */}
            {showCreateModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
                    <div className="bg-white dark:bg-gray-800 rounded-xl max-w-md w-full p-6 shadow-xl">
                        <h2 className="text-lg font-bold mb-4 text-gray-900 dark:text-white">Create Secure Link</h2>

                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">File</label>
                                <select
                                    className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                    value={newShare.file_name}
                                    onChange={(e) => setNewShare({ ...newShare, file_name: e.target.value })}
                                >
                                    <option value="Audit_Report_2025.pdf">Audit_Report_2025.pdf</option>
                                    <option value="Security_Whitepaper.pdf">Security_Whitepaper.pdf</option>
                                    <option value="Compliance_Cert.pdf">Compliance_Cert.pdf</option>
                                </select>
                            </div>

                            <div className="flex gap-4">
                                <div className="flex-1">
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Expires In (Days)</label>
                                    <input
                                        type="number"
                                        className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                        value={newShare.expires_in_days}
                                        onChange={(e) => setNewShare({ ...newShare, expires_in_days: parseInt(e.target.value) })}
                                    />
                                </div>
                                <div className="flex-1">
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Max Accesses</label>
                                    <input
                                        type="number"
                                        className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                        value={newShare.max_accesses}
                                        onChange={(e) => setNewShare({ ...newShare, max_accesses: parseInt(e.target.value) })}
                                    />
                                </div>
                            </div>

                            <div className="flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    id="pw-protect"
                                    checked={newShare.password_protected}
                                    onChange={(e) => setNewShare({ ...newShare, password_protected: e.target.checked })}
                                />
                                <label htmlFor="pw-protect" className="text-sm font-medium text-gray-700 dark:text-gray-300">Password Protect</label>
                            </div>

                            {newShare.password_protected && (
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Password</label>
                                    <input
                                        type="text"
                                        className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                                        value={newShare.password}
                                        onChange={(e) => setNewShare({ ...newShare, password: e.target.value })}
                                        placeholder="Enter secure password"
                                    />
                                </div>
                            )}
                        </div>

                        <div className="flex justify-end gap-3 mt-6">
                            <button
                                onClick={() => setShowCreateModal(false)}
                                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleCreateShare}
                                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg"
                            >
                                Create Link
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
