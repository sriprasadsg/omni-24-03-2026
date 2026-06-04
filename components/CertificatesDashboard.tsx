import React, { useState, useEffect, useMemo } from 'react';
import { authFetch } from '../services/apiService';
import { ShieldCheckIcon, PlusCircleIcon, TrashIcon, AlertTriangleIcon, CheckIcon, CogIcon, XIcon } from './icons';

interface Certificate {
    id: string;
    name: string;
    domain?: string;
    issuer?: string;
    subject?: string;
    expires_at: string;
    issued_at?: string;
    environment?: string;
    notes?: string;
    asset_id?: string;
    days_until_expiry?: number | null;
}

interface Summary { expired: number; critical: number; warning: number; ok: number; unknown: number; total: number }

const expiryBadge = (days: number | null | undefined) => {
    if (days == null) return { label: 'Unknown', cls: 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400' };
    if (days < 0) return { label: `Expired ${Math.abs(days)}d ago`, cls: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300 font-bold' };
    if (days <= 7) return { label: `${days}d — CRITICAL`, cls: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300 font-bold' };
    if (days <= 30) return { label: `${days}d — Warning`, cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' };
    return { label: `${days}d`, cls: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' };
};

const BLANK_FORM = { name: '', domain: '', issuer: '', expires_at: '', issued_at: '', environment: 'production', notes: '' };

export const CertificatesDashboard: React.FC = () => {
    const [certs, setCerts] = useState<Certificate[]>([]);
    const [summary, setSummary] = useState<Summary | null>(null);
    const [loading, setLoading] = useState(true);
    const [showAdd, setShowAdd] = useState(false);
    const [form, setForm] = useState({ ...BLANK_FORM });
    const [saving, setSaving] = useState(false);
    const [filterEnv, setFilterEnv] = useState('All');
    const [filterExpiry, setFilterExpiry] = useState('All');
    const [toast, setToast] = useState<string | null>(null);

    const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(null), 3000); };

    const load = async () => {
        setLoading(true);
        const [certsRes, summaryRes] = await Promise.all([
            authFetch('/api/certificates').then(r => r.ok ? r.json() : []),
            authFetch('/api/certificates/summary').then(r => r.ok ? r.json() : null),
        ]);
        setCerts(Array.isArray(certsRes) ? certsRes : []);
        setSummary(summaryRes);
        setLoading(false);
    };

    useEffect(() => { load(); }, []);

    const handleSave = async () => {
        if (!form.name.trim() || !form.expires_at) { showToast('Name and expiry date are required'); return; }
        setSaving(true);
        try {
            const res = await authFetch('/api/certificates', { method: 'POST', body: JSON.stringify(form) });
            if (res.ok) { setShowAdd(false); setForm({ ...BLANK_FORM }); load(); showToast('Certificate added'); }
            else { showToast('Failed to save'); }
        } finally { setSaving(false); }
    };

    const handleDelete = async (id: string, name: string) => {
        if (!window.confirm(`Delete certificate "${name}"?`)) return;
        await authFetch(`/api/certificates/${id}`, { method: 'DELETE' });
        setCerts(prev => prev.filter(c => c.id !== id));
        showToast('Deleted');
    };

    const environments = useMemo(() => ['All', ...new Set(certs.map(c => c.environment || 'production'))], [certs]);

    const filtered = useMemo(() => certs.filter(c => {
        if (filterEnv !== 'All' && c.environment !== filterEnv) return false;
        const d = c.days_until_expiry;
        // null/undefined means expiry is unknown — only show in 'All', not in any named bucket
        if (filterExpiry === 'Expired')  return d != null && d < 0;
        if (filterExpiry === 'Critical') return d != null && d >= 0 && d <= 7;
        if (filterExpiry === 'Warning')  return d != null && d > 7 && d <= 30;
        if (filterExpiry === 'OK')       return d != null && d > 30;
        return true;
    }), [certs, filterEnv, filterExpiry]);

    const summaryCards = summary ? [
        { label: 'Expired', value: summary.expired, color: 'text-red-600', border: 'border-l-red-600' },
        { label: 'Critical (<7d)', value: summary.critical, color: 'text-red-500', border: 'border-l-red-400' },
        { label: 'Warning (<30d)', value: summary.warning, color: 'text-amber-600', border: 'border-l-amber-400' },
        { label: 'Healthy', value: summary.ok, color: 'text-green-600', border: 'border-l-green-400' },
        { label: 'Total', value: summary.total, color: 'text-gray-700 dark:text-gray-200', border: 'border-l-gray-400' },
    ] : [];

    return (
        <div className="container mx-auto space-y-5">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-2xl font-semibold text-gray-800 dark:text-white">Certificate Management</h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Track TLS/SSL certificate expiry across your infrastructure</p>
                </div>
                <button onClick={() => setShowAdd(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700">
                    <PlusCircleIcon size={16} /> Add Certificate
                </button>
            </div>

            {/* Summary cards */}
            {summary && (
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                    {summaryCards.map(({ label, value, color, border }) => (
                        <div key={label} className={`bg-white dark:bg-gray-800 rounded-lg p-4 shadow-sm border border-gray-200 dark:border-gray-700 border-l-4 ${border}`}>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</p>
                            <p className={`text-2xl font-bold ${color}`}>{value}</p>
                        </div>
                    ))}
                </div>
            )}

            {/* Filters + table */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
                <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center gap-3 flex-wrap">
                    <ShieldCheckIcon size={18} className="text-primary-500" />
                    <span className="text-sm font-semibold text-gray-800 dark:text-white">
                        {filtered.length} certificate{filtered.length !== 1 ? 's' : ''}
                    </span>
                    <select value={filterExpiry} onChange={e => setFilterExpiry(e.target.value)}
                        className="ml-auto px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 dark:text-gray-200">
                        {['All', 'Expired', 'Critical', 'Warning', 'OK'].map(v => <option key={v}>{v}</option>)}
                    </select>
                    <select value={filterEnv} onChange={e => setFilterEnv(e.target.value)}
                        className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 dark:text-gray-200">
                        {environments.map(e => <option key={e}>{e}</option>)}
                    </select>
                </div>

                {loading ? (
                    <div className="flex items-center justify-center p-12 text-gray-500">
                        <CogIcon size={18} className="animate-spin mr-2" /> Loading…
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm text-left">
                            <thead className="text-xs uppercase bg-gray-50 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                                <tr>
                                    <th className="px-4 py-3">Name / Domain</th>
                                    <th className="px-4 py-3">Issuer</th>
                                    <th className="px-4 py-3">Expires</th>
                                    <th className="px-4 py-3">Status</th>
                                    <th className="px-4 py-3">Env</th>
                                    <th className="px-4 py-3"></th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                                {filtered.length === 0 && (
                                    <tr><td colSpan={6} className="px-4 py-10 text-center text-gray-500 dark:text-gray-400">No certificates found</td></tr>
                                )}
                                {filtered.map(cert => {
                                    const badge = expiryBadge(cert.days_until_expiry);
                                    return (
                                        <tr key={cert.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/40">
                                            <td className="px-4 py-3">
                                                <p className="font-medium text-gray-900 dark:text-white text-sm">{cert.name}</p>
                                                {cert.domain && <p className="text-xs text-gray-400 font-mono">{cert.domain}</p>}
                                            </td>
                                            <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400">{cert.issuer || '—'}</td>
                                            <td className="px-4 py-3 text-xs text-gray-600 dark:text-gray-300 whitespace-nowrap">
                                                {cert.expires_at ? cert.expires_at.slice(0, 10) : '—'}
                                            </td>
                                            <td className="px-4 py-3">
                                                <span className={`px-2 py-0.5 rounded-full text-xs ${badge.cls}`}>{badge.label}</span>
                                            </td>
                                            <td className="px-4 py-3 text-xs text-gray-500">{cert.environment || 'production'}</td>
                                            <td className="px-4 py-3">
                                                <button onClick={() => handleDelete(cert.id, cert.name)}
                                                    className="p-1 text-gray-400 hover:text-red-600">
                                                    <TrashIcon size={14} />
                                                </button>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Add Certificate Modal */}
            {showAdd && (
                <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowAdd(false)}>
                    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center justify-between p-5 border-b border-gray-200 dark:border-gray-700">
                            <h3 className="font-semibold text-gray-900 dark:text-white">Add Certificate</h3>
                            <button onClick={() => setShowAdd(false)}><XIcon size={18} className="text-gray-400" /></button>
                        </div>
                        <div className="p-5 space-y-3">
                            {[
                                ['name', 'Name *', 'text', 'e.g. api.company.com'],
                                ['domain', 'Domain', 'text', 'e.g. api.company.com'],
                                ['issuer', 'Issuer', 'text', "e.g. Let's Encrypt"],
                                ['expires_at', 'Expires At *', 'date', ''],
                                ['issued_at', 'Issued At', 'date', ''],
                            ].map(([field, label, type, placeholder]) => (
                                <div key={field}>
                                    <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">{label}</label>
                                    <input type={type as string} value={(form as any)[field]} placeholder={placeholder as string}
                                        onChange={e => setForm(f => ({ ...f, [field as string]: e.target.value }))}
                                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-white focus:ring-2 focus:ring-primary-500 outline-none" />
                                </div>
                            ))}
                            <div>
                                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Environment</label>
                                <select value={form.environment} onChange={e => setForm(f => ({ ...f, environment: e.target.value }))}
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-white focus:ring-2 focus:ring-primary-500 outline-none">
                                    {['production', 'staging', 'development', 'internal'].map(v => <option key={v}>{v}</option>)}
                                </select>
                            </div>
                        </div>
                        <div className="flex gap-3 p-5 border-t border-gray-200 dark:border-gray-700">
                            <button onClick={() => setShowAdd(false)}
                                className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-gray-700">
                                Cancel
                            </button>
                            <button onClick={handleSave} disabled={saving}
                                className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg text-sm hover:bg-primary-700 disabled:opacity-50">
                                {saving ? <CogIcon size={14} className="animate-spin" /> : <CheckIcon size={14} />}
                                Save
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {toast && (
                <div className="fixed bottom-6 right-6 px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white bg-primary-600 z-50">{toast}</div>
            )}
        </div>
    );
};
