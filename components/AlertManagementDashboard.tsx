import React, { useState, useEffect, useMemo } from 'react';
import { Alert, AlertSeverity } from '../types';
import { fetchAlerts, bulkAcknowledgeAlerts, bulkDismissAlerts, bulkDeleteAlerts } from '../services/apiService';
import { scanArtifact, ThreatIntelScan } from '../services/threatIntelService';
import { AlertTriangleIcon, CheckIcon, TrashIcon, XCircleIcon, CogIcon, SearchIcon, ShieldCheckIcon } from './icons';

function extractSourceArtifact(source: any): { artifact: string; type: 'ip' | 'domain' } | null {
    const raw: string = typeof source === 'string' ? source : (source?.hostname || source?.ip || '');
    if (!raw || raw === '—') return null;
    const isIp = /^\d{1,3}(\.\d{1,3}){3}$/.test(raw);
    return { artifact: raw, type: isIp ? 'ip' : 'domain' };
}

const verdictStyle: Record<string, string> = {
    malicious:  'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
    suspicious: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    harmless:   'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
    clean:      'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
    unknown:    'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400',
};

const SEVERITY_ORDER: Record<string, number> = { Critical: 0, High: 1, Medium: 2, Low: 3, Info: 4 };

const severityBadge = (severity: string) => {
    const map: Record<string, string> = {
        Critical: 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300',
        High: 'bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300',
        Medium: 'bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300',
        Low: 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300',
        Info: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
    };
    return map[severity] ?? map.Info;
};

const statusBadge = (alert: Alert) => {
    if (alert.status === 'dismissed') return 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400';
    if (alert.acknowledged || alert.status === 'acknowledged') return 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300';
    return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300';
};

const statusLabel = (alert: Alert) => {
    if (alert.status === 'dismissed') return 'Dismissed';
    if (alert.acknowledged || alert.status === 'acknowledged') return 'Acknowledged';
    return 'Open';
};

export const AlertManagementDashboard: React.FC = () => {
    const [alerts, setAlerts] = useState<Alert[]>([]);
    const [loading, setLoading] = useState(true);
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [severityFilter, setSeverityFilter] = useState<string>('All');
    const [statusFilter, setStatusFilter] = useState<string>('All');
    const [search, setSearch] = useState('');
    const [operating, setOperating] = useState<string | null>(null);
    const [toast, setToast] = useState<{ msg: string; type: 'success' | 'error' } | null>(null);
    const [reputations, setReputations] = useState<Map<string, ThreatIntelScan | 'scanning' | 'error'>>(new Map());

    const checkReputation = async (alert: Alert) => {
        const source = extractSourceArtifact(alert.source);
        if (!source) { showToast('No scannable source for this alert', 'error'); return; }
        setReputations(prev => new Map(prev).set(alert.id, 'scanning'));
        try {
            const result = await scanArtifact(source.artifact, source.type, alert.tenantId || '');
            setReputations(prev => new Map(prev).set(alert.id, result));
        } catch {
            setReputations(prev => new Map(prev).set(alert.id, 'error'));
        }
    };

    const showToast = (msg: string, type: 'success' | 'error' = 'success') => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 3500);
    };

    useEffect(() => {
        setLoading(true);
        fetchAlerts().then(data => {
            setAlerts(data as Alert[]);
            setLoading(false);
        });
    }, []);

    const filtered = useMemo(() => {
        return alerts
            .filter(a => severityFilter === 'All' || a.severity === severityFilter)
            .filter(a => {
                const st = statusLabel(a);
                return statusFilter === 'All' || st === statusFilter;
            })
            .filter(a => {
                if (!search.trim()) return true;
                const q = search.toLowerCase();
                return (a.message || '').toLowerCase().includes(q)
                    || (a.source || '').toLowerCase().includes(q)
                    || (a.hostname || '').toLowerCase().includes(q);
            })
            .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 99) - (SEVERITY_ORDER[b.severity] ?? 99));
    }, [alerts, severityFilter, statusFilter, search]);

    const allFilteredSelected = filtered.length > 0 && filtered.every(a => selected.has(a.id));

    const toggleAll = () => {
        if (allFilteredSelected) {
            setSelected(prev => {
                const next = new Set(prev);
                filtered.forEach(a => next.delete(a.id));
                return next;
            });
        } else {
            setSelected(prev => new Set([...prev, ...filtered.map(a => a.id)]));
        }
    };

    const toggle = (id: string) => {
        setSelected(prev => {
            const next = new Set(prev);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
        });
    };

    const applyLocalPatch = (ids: string[], patch: Partial<Alert>) => {
        setAlerts(prev => prev.map(a => ids.includes(a.id) ? { ...a, ...patch } : a));
        setSelected(new Set());
    };

    const handleAcknowledge = async () => {
        const ids = Array.from(selected);
        setOperating('ack');
        try {
            const res = await bulkAcknowledgeAlerts(ids);
            applyLocalPatch(ids, { acknowledged: true, status: 'acknowledged' });
            showToast(`${res.modified} alert(s) acknowledged`);
        } catch (e) {
            showToast(e instanceof Error ? e.message : 'Failed', 'error');
        } finally {
            setOperating(null);
        }
    };

    const handleDismiss = async () => {
        const ids = Array.from(selected);
        setOperating('dismiss');
        try {
            const res = await bulkDismissAlerts(ids);
            applyLocalPatch(ids, { status: 'dismissed' });
            showToast(`${res.modified} alert(s) dismissed`);
        } catch (e) {
            showToast(e instanceof Error ? e.message : 'Failed', 'error');
        } finally {
            setOperating(null);
        }
    };

    const handleDelete = async () => {
        const ids = Array.from(selected);
        if (!window.confirm(`Delete ${ids.length} alert(s)? This cannot be undone.`)) return;
        setOperating('delete');
        try {
            const res = await bulkDeleteAlerts(ids);
            setAlerts(prev => prev.filter(a => !ids.includes(a.id)));
            setSelected(new Set());
            showToast(`${res.deleted} alert(s) deleted`);
        } catch (e) {
            showToast(e instanceof Error ? e.message : 'Failed', 'error');
        } finally {
            setOperating(null);
        }
    };

    const severities: AlertSeverity[] = ['Critical', 'High', 'Medium', 'Low'];

    return (
        <div className="container mx-auto space-y-5">
            <div>
                <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-1">Alert Management</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">Review, acknowledge, and dismiss security alerts.</p>
            </div>

            {/* Filters */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 flex flex-wrap gap-3 items-center">
                <div className="flex items-center border border-gray-300 dark:border-gray-600 rounded-md overflow-hidden flex-1 min-w-[200px]">
                    <SearchIcon size={16} className="ml-3 text-gray-400 flex-shrink-0" />
                    <input
                        type="text"
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        placeholder="Search alerts..."
                        className="flex-1 px-3 py-2 text-sm bg-transparent text-gray-900 dark:text-gray-100 focus:outline-none"
                    />
                </div>
                <select
                    value={severityFilter}
                    onChange={e => setSeverityFilter(e.target.value)}
                    className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200"
                >
                    <option value="All">All Severities</option>
                    {severities.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <select
                    value={statusFilter}
                    onChange={e => setStatusFilter(e.target.value)}
                    className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200"
                >
                    {['All', 'Open', 'Acknowledged', 'Dismissed'].map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <span className="text-xs text-gray-500 dark:text-gray-400 ml-auto">
                    {filtered.length} of {alerts.length} alert{alerts.length !== 1 ? 's' : ''}
                </span>
            </div>

            {/* Bulk action toolbar */}
            {selected.size > 0 && (
                <div className="bg-primary-50 dark:bg-primary-900/30 border border-primary-200 dark:border-primary-700 rounded-lg px-4 py-3 flex flex-wrap items-center gap-3">
                    <span className="text-sm font-semibold text-primary-800 dark:text-primary-200">
                        {selected.size} selected
                    </span>
                    <button
                        onClick={handleAcknowledge}
                        disabled={!!operating}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-green-700 bg-green-100 dark:bg-green-900/40 dark:text-green-300 rounded-md hover:bg-green-200 disabled:opacity-50"
                    >
                        {operating === 'ack' ? <CogIcon size={13} className="animate-spin" /> : <CheckIcon size={13} />}
                        Acknowledge
                    </button>
                    <button
                        onClick={handleDismiss}
                        disabled={!!operating}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 dark:bg-gray-700 dark:text-gray-200 rounded-md hover:bg-gray-200 disabled:opacity-50"
                    >
                        {operating === 'dismiss' ? <CogIcon size={13} className="animate-spin" /> : <XCircleIcon size={13} />}
                        Dismiss
                    </button>
                    <button
                        onClick={handleDelete}
                        disabled={!!operating}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-700 bg-red-100 dark:bg-red-900/40 dark:text-red-300 rounded-md hover:bg-red-200 disabled:opacity-50"
                    >
                        {operating === 'delete' ? <CogIcon size={13} className="animate-spin" /> : <TrashIcon size={13} />}
                        Delete
                    </button>
                    <button
                        onClick={() => setSelected(new Set())}
                        className="ml-auto text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                    >
                        Clear selection
                    </button>
                </div>
            )}

            {/* Table */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
                {loading ? (
                    <div className="flex items-center justify-center p-12 text-gray-500 dark:text-gray-400">
                        <CogIcon size={20} className="animate-spin mr-2" /> Loading alerts...
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm text-left">
                            <thead className="text-xs uppercase bg-gray-50 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                                <tr>
                                    <th className="px-4 py-3 w-10">
                                        <input
                                            type="checkbox"
                                            checked={allFilteredSelected}
                                            onChange={toggleAll}
                                            className="rounded text-primary-600 focus:ring-primary-500"
                                        />
                                    </th>
                                    <th className="px-4 py-3">Severity</th>
                                    <th className="px-4 py-3">Message</th>
                                    <th className="px-4 py-3">Source</th>
                                    <th className="px-4 py-3">Status</th>
                                    <th className="px-4 py-3">Time</th>
                                    <th className="px-4 py-3">Reputation</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                                {filtered.length === 0 && (
                                    <tr>
                                        <td colSpan={6} className="px-4 py-10 text-center text-gray-500 dark:text-gray-400">
                                            <AlertTriangleIcon size={24} className="mx-auto mb-2 opacity-40" />
                                            No alerts match the current filters
                                        </td>
                                    </tr>
                                )}
                                {filtered.map(alert => (
                                    <tr
                                        key={alert.id}
                                        className={`hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors ${selected.has(alert.id) ? 'bg-primary-50/50 dark:bg-primary-900/20' : ''}`}
                                    >
                                        <td className="px-4 py-3">
                                            <input
                                                type="checkbox"
                                                checked={selected.has(alert.id)}
                                                onChange={() => toggle(alert.id)}
                                                className="rounded text-primary-600 focus:ring-primary-500"
                                            />
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${severityBadge(alert.severity)}`}>
                                                {alert.severity}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 max-w-xs">
                                            <p className="truncate text-gray-800 dark:text-gray-200 text-sm" title={alert.message}>
                                                {alert.message}
                                            </p>
                                            {alert.hostname && (
                                                <p className="text-xs text-gray-400 font-mono mt-0.5">{alert.hostname}</p>
                                            )}
                                        </td>
                                        <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400">
                                            {typeof alert.source === 'string' ? alert.source : (alert.source as any)?.hostname || '—'}
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusBadge(alert)}`}>
                                                {statusLabel(alert)}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
                                            {alert.timestamp ? new Date(alert.timestamp).toLocaleString() : '—'}
                                        </td>
                                        <td className="px-4 py-3">
                                            {(() => {
                                                const rep = reputations.get(alert.id);
                                                const hasSource = !!extractSourceArtifact(alert.source);
                                                if (!hasSource) return <span className="text-xs text-gray-400">—</span>;
                                                if (!rep) return (
                                                    <button onClick={() => checkReputation(alert)}
                                                        className="flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-primary-600 dark:text-primary-400 border border-primary-300 dark:border-primary-700 rounded hover:bg-primary-50 dark:hover:bg-primary-900/30">
                                                        <ShieldCheckIcon size={11} /> Check
                                                    </button>
                                                );
                                                if (rep === 'scanning') return (
                                                    <span className="flex items-center gap-1 text-xs text-gray-500"><CogIcon size={11} className="animate-spin" /> Scanning…</span>
                                                );
                                                if (rep === 'error') return (
                                                    <span className="text-xs text-red-500">Failed</span>
                                                );
                                                const verdict = (rep as ThreatIntelScan).verdict?.toLowerCase() || 'unknown';
                                                return (
                                                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${verdictStyle[verdict] || verdictStyle.unknown}`}>
                                                        {(rep as ThreatIntelScan).malicious != null && (rep as ThreatIntelScan).malicious! > 0 && (
                                                            <AlertTriangleIcon size={10} />
                                                        )}
                                                        {verdict}
                                                    </span>
                                                );
                                            })()}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Toast */}
            {toast && (
                <div className={`fixed bottom-6 right-6 px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white z-50 ${toast.type === 'success' ? 'bg-green-600' : 'bg-red-600'}`}>
                    {toast.msg}
                </div>
            )}
        </div>
    );
};
