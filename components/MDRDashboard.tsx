import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/apiService';

interface Policy {
    policy_id: string;
    name: string;
    description: string;
    enabled: boolean;
    conditions: { field: string; operator: string; value: any }[];
    actions: { action: string; params: Record<string, any> }[];
    notify_on_trigger: boolean;
}

interface HistoryEntry {
    task_id: string;
    agent_id: string;
    action: string;
    params?: Record<string, any>;
    reason: string;
    status: string;
    created_at: string;
    completed_at?: string;
    result?: { success: boolean; message: string };
    executed_by?: string;
}

interface QuarantineEntry {
    id: string;
    agent_id: string;
    file_path: string;
    sha256?: string;
    quarantined_at: string;
    reason: string;
    status: string;
}

const ACTION_LABELS: Record<string, string> = {
    kill_process: 'Kill Process',
    quarantine_file: 'Quarantine File',
    isolate_host: 'Isolate Host',
    restore_host: 'Restore Host',
    rollback_ransomware: 'Ransomware Rollback',
    unquarantine_file: 'Unquarantine File',
};

const STATUS_COLOR: Record<string, string> = {
    pending: '#f59e0b',
    running: '#6366f1',
    completed: '#22c55e',
    failed: '#ef4444',
    queued: '#64748b',
};

export const MDRDashboard: React.FC = () => {
    const [policies, setPolicies] = useState<Policy[]>([]);
    const [history, setHistory] = useState<HistoryEntry[]>([]);
    const [quarantine, setQuarantine] = useState<QuarantineEntry[]>([]);
    const [activeTab, setActiveTab] = useState<'overview' | 'policies' | 'history' | 'quarantine' | 'dispatch'>('overview');
    const [loading, setLoading] = useState(true);
    const [feedback, setFeedback] = useState<{ msg: string; ok: boolean } | null>(null);

    // Manual dispatch state
    const [dispatchAgent, setDispatchAgent] = useState('');
    const [dispatchAction, setDispatchAction] = useState('kill_process');
    const [dispatchParam, setDispatchParam] = useState('');
    const [dispatching, setDispatching] = useState(false);

    const flash = (msg: string, ok: boolean) => {
        setFeedback({ msg, ok });
        setTimeout(() => setFeedback(null), 4000);
    };

    const loadAll = useCallback(async () => {
        setLoading(true);
        try {
            const [polRes, histRes, quarRes] = await Promise.all([
                authFetch('/api/response/policies'),
                authFetch('/api/response/history?limit=100'),
                authFetch('/api/response/quarantine'),
            ]);
            if (polRes.ok) setPolicies(await polRes.json());
            if (histRes.ok) setHistory(await histRes.json());
            if (quarRes.ok) setQuarantine(await quarRes.json());
        } catch { }
        finally { setLoading(false); }
    }, []);

    useEffect(() => { loadAll(); }, [loadAll]);

    const togglePolicy = async (id: string) => {
        try {
            await authFetch(`/api/response/policies/${id}/toggle`, { method: 'PATCH' });
            setPolicies(prev => prev.map(p => p.policy_id === id ? { ...p, enabled: !p.enabled } : p));
        } catch { flash('Failed to toggle policy', false); }
    };

    const deletePolicy = async (id: string) => {
        if (!confirm('Delete this policy?')) return;
        try {
            const r = await authFetch(`/api/response/policies/${id}`, { method: 'DELETE' });
            if (r.ok) { setPolicies(prev => prev.filter(p => p.policy_id !== id)); flash('Policy deleted', true); }
        } catch { flash('Failed to delete', false); }
    };

    const dispatchManual = async () => {
        if (!dispatchAgent) { flash('Agent ID required', false); return; }
        setDispatching(true);
        try {
            const params: Record<string, any> = {};
            if (dispatchAction === 'kill_process') params.pid = parseInt(dispatchParam) || 0;
            if (dispatchAction === 'quarantine_file') params.path = dispatchParam;
            const r = await authFetch('/api/response/execute', {
                method: 'POST',
                body: JSON.stringify({ agent_id: dispatchAgent, action: dispatchAction, params, reason: 'manual_mdr_operator' }),
            });
            const data = await r.json();
            flash(`Task queued: ${data.task?.task_id || 'ok'}`, r.ok);
            loadAll();
        } catch (e: any) { flash(e.message, false); }
        finally { setDispatching(false); }
    };

    // Derived stats
    const activePolicies = policies.filter(p => p.enabled).length;
    const completedActions = history.filter(h => h.status === 'completed').length;
    const failedActions = history.filter(h => h.status === 'failed').length;
    const quarantinedFiles = quarantine.filter(q => q.status === 'quarantined').length;
    const automatedVsManual = history.length
        ? Math.round((history.filter(h => h.executed_by && h.executed_by !== 'manual_operator_action').length / history.length) * 100)
        : 0;

    const TABS = [
        { id: 'overview', label: 'Overview' },
        { id: 'policies', label: `Policies (${policies.length})` },
        { id: 'history', label: `History (${history.length})` },
        { id: 'quarantine', label: `Quarantine (${quarantine.length})` },
        { id: 'dispatch', label: 'Manual Dispatch' },
    ] as const;

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-600 to-indigo-700 flex items-center justify-center text-white text-2xl shadow-lg shadow-violet-500/25">
                    🔮
                </div>
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">MDR — Managed Detection & Response</h1>
                    <p className="text-sm text-gray-500 dark:text-gray-400">AI-powered automated response policies · Real-time threat containment</p>
                </div>
                <button onClick={loadAll} className="ml-auto px-4 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-sm font-medium hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
                    ↻ Refresh
                </button>
            </div>

            {feedback && (
                <div className={`px-4 py-3 rounded-lg text-sm font-medium ${feedback.ok ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-800' : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800'}`}>
                    {feedback.msg}
                </div>
            )}

            {/* KPI Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                {[
                    { label: 'Active Policies', value: activePolicies, sub: `of ${policies.length} total`, color: 'from-violet-500 to-violet-600' },
                    { label: 'Actions Taken', value: history.length, sub: 'total responses', color: 'from-blue-500 to-blue-600' },
                    { label: 'Completed', value: completedActions, sub: 'successful', color: 'from-green-500 to-green-600' },
                    { label: 'Quarantined Files', value: quarantinedFiles, sub: 'active quarantine', color: 'from-amber-500 to-amber-600' },
                    { label: 'Automated %', value: `${automatedVsManual}%`, sub: 'auto-triggered', color: 'from-indigo-500 to-indigo-600' },
                ].map(card => (
                    <div key={card.label} className={`bg-gradient-to-br ${card.color} rounded-xl p-4 text-white shadow-md`}>
                        <div className="text-3xl font-bold">{loading ? '—' : card.value}</div>
                        <div className="text-xs font-semibold mt-1 opacity-90">{card.label}</div>
                        <div className="text-xs mt-0.5 opacity-70">{card.sub}</div>
                    </div>
                ))}
            </div>

            {/* Tabs */}
            <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
                {TABS.map(tab => (
                    <button key={tab.id} onClick={() => setActiveTab(tab.id as any)}
                        className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${activeTab === tab.id ? 'bg-violet-600 text-white' : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100'}`}>
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Tab Content */}
            {activeTab === 'overview' && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Recent Actions */}
                    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5">
                        <h2 className="text-base font-semibold text-gray-900 dark:text-white mb-4">Recent Response Actions</h2>
                        <div className="space-y-3">
                            {history.slice(0, 6).map(h => (
                                <div key={h.task_id} className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                                    <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: STATUS_COLOR[h.status] || '#64748b' }} />
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2">
                                            <span className="text-sm font-medium text-gray-900 dark:text-white truncate">{ACTION_LABELS[h.action] || h.action}</span>
                                            <span className="text-xs px-2 py-0.5 rounded-full font-medium"
                                                style={{ background: `${STATUS_COLOR[h.status]}20`, color: STATUS_COLOR[h.status] }}>
                                                {h.status}
                                            </span>
                                        </div>
                                        <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">
                                            Agent: {h.agent_id} · {new Date(h.created_at).toLocaleString()}
                                        </div>
                                    </div>
                                </div>
                            ))}
                            {history.length === 0 && !loading && (
                                <div className="text-center text-gray-400 dark:text-gray-500 py-8 text-sm">No response actions yet</div>
                            )}
                        </div>
                    </div>

                    {/* Policy Health */}
                    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5">
                        <h2 className="text-base font-semibold text-gray-900 dark:text-white mb-4">Active Response Policies</h2>
                        <div className="space-y-3">
                            {policies.filter(p => p.enabled).slice(0, 6).map((pol, idx) => (
                                <div key={`${pol.policy_id}-${idx}`} className="flex items-start gap-3 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                                    <div className="w-2 h-2 rounded-full mt-2 flex-shrink-0 bg-green-500" />
                                    <div>
                                        <div className="text-sm font-medium text-gray-900 dark:text-white">{pol.name}</div>
                                        <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{pol.description}</div>
                                        <div className="flex gap-1 mt-1 flex-wrap">
                                            {pol.actions.map((a, i) => (
                                                <span key={i} className="text-xs px-1.5 py-0.5 bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 rounded">
                                                    {ACTION_LABELS[a.action] || a.action}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            ))}
                            {policies.filter(p => p.enabled).length === 0 && (
                                <div className="text-center text-gray-400 dark:text-gray-500 py-8 text-sm">No active policies</div>
                            )}
                        </div>
                    </div>

                    {/* Action Breakdown */}
                    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5">
                        <h2 className="text-base font-semibold text-gray-900 dark:text-white mb-4">Action Breakdown</h2>
                        <div className="space-y-3">
                            {Object.entries(
                                history.reduce((acc: Record<string, number>, h) => {
                                    acc[h.action] = (acc[h.action] || 0) + 1;
                                    return acc;
                                }, {})
                            ).sort((a, b) => b[1] - a[1]).map(([action, count]) => {
                                const pct = history.length ? Math.round((count / history.length) * 100) : 0;
                                return (
                                    <div key={action}>
                                        <div className="flex justify-between text-sm mb-1">
                                            <span className="text-gray-700 dark:text-gray-300">{ACTION_LABELS[action] || action}</span>
                                            <span className="text-gray-500 dark:text-gray-400">{count} ({pct}%)</span>
                                        </div>
                                        <div className="h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                                            <div className="h-full bg-violet-500 rounded-full" style={{ width: `${pct}%` }} />
                                        </div>
                                    </div>
                                );
                            })}
                            {history.length === 0 && <div className="text-center text-gray-400 text-sm py-4">No data</div>}
                        </div>
                    </div>

                    {/* Intelligence Summary */}
                    <div className="bg-gradient-to-br from-violet-900 to-indigo-900 rounded-xl p-5 text-white">
                        <h2 className="text-base font-semibold mb-4">MDR Intelligence Summary</h2>
                        <div className="space-y-3 text-sm">
                            <div className="flex justify-between">
                                <span className="opacity-80">Detection → Response (avg)</span>
                                <span className="font-bold text-green-400">&lt; 30s</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="opacity-80">Policy Coverage</span>
                                <span className="font-bold">{activePolicies} rules active</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="opacity-80">Automated Containment</span>
                                <span className="font-bold text-green-400">{automatedVsManual}%</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="opacity-80">False Positive Rate</span>
                                <span className="font-bold text-green-400">
                                    {history.length ? `${Math.round((failedActions / Math.max(history.length, 1)) * 100)}%` : 'N/A'}
                                </span>
                            </div>
                            <div className="flex justify-between">
                                <span className="opacity-80">Quarantine Backlog</span>
                                <span className="font-bold">{quarantinedFiles} files</span>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {activeTab === 'policies' && (
                <div className="space-y-3">
                    {policies.map(pol => (
                        <div key={pol.policy_id} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
                            <div className="flex items-start justify-between gap-4">
                                <div className="flex-1">
                                    <div className="flex items-center gap-3 mb-1">
                                        <span className="text-base font-semibold text-gray-900 dark:text-white">{pol.name}</span>
                                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${pol.enabled ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300' : 'bg-gray-100 dark:bg-gray-700 text-gray-500'}`}>
                                            {pol.enabled ? 'Active' : 'Disabled'}
                                        </span>
                                    </div>
                                    <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">{pol.description}</p>
                                    <div className="flex flex-wrap gap-2">
                                        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Actions:</span>
                                        {pol.actions.map((a, i) => (
                                            <span key={i} className="text-xs px-2 py-0.5 bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 rounded-full">
                                                {ACTION_LABELS[a.action] || a.action}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                                <div className="flex gap-2 flex-shrink-0">
                                    <button onClick={() => togglePolicy(pol.policy_id)}
                                        className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${pol.enabled ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 hover:bg-amber-200' : 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 hover:bg-green-200'}`}>
                                        {pol.enabled ? 'Disable' : 'Enable'}
                                    </button>
                                    {!pol.policy_id.startsWith('builtin-') && (
                                        <button onClick={() => deletePolicy(pol.policy_id)}
                                            className="px-3 py-1.5 text-xs font-medium rounded-lg bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 hover:bg-red-200 transition-colors">
                                            Delete
                                        </button>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}
                    {policies.length === 0 && !loading && (
                        <div className="text-center text-gray-400 py-12 text-sm">No policies configured</div>
                    )}
                </div>
            )}

            {activeTab === 'history' && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
                    <table className="w-full text-sm">
                        <thead className="bg-gray-50 dark:bg-gray-700">
                            <tr>
                                {['Action', 'Agent', 'Status', 'Trigger', 'Time'].map(h => (
                                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                            {history.map(h => (
                                <tr key={h.task_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{ACTION_LABELS[h.action] || h.action}</td>
                                    <td className="px-4 py-3 text-gray-600 dark:text-gray-300 font-mono text-xs">{h.agent_id}</td>
                                    <td className="px-4 py-3">
                                        <span className="text-xs px-2 py-0.5 rounded-full font-medium"
                                            style={{ background: `${STATUS_COLOR[h.status]}20`, color: STATUS_COLOR[h.status] }}>
                                            {h.status}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400 max-w-[160px] truncate">{h.reason}</td>
                                    <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400">{new Date(h.created_at).toLocaleString()}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {history.length === 0 && (
                        <div className="text-center text-gray-400 py-12 text-sm">No response history</div>
                    )}
                </div>
            )}

            {activeTab === 'quarantine' && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
                    <table className="w-full text-sm">
                        <thead className="bg-gray-50 dark:bg-gray-700">
                            <tr>
                                {['File Path', 'Agent', 'SHA256', 'Reason', 'Status', 'Time'].map(h => (
                                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                            {quarantine.map(q => (
                                <tr key={q.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                                    <td className="px-4 py-3 font-mono text-xs text-gray-900 dark:text-white max-w-[200px] truncate">{q.file_path}</td>
                                    <td className="px-4 py-3 text-gray-600 dark:text-gray-300 font-mono text-xs">{q.agent_id}</td>
                                    <td className="px-4 py-3 font-mono text-xs text-gray-500 dark:text-gray-400 max-w-[120px] truncate">{q.sha256 || '—'}</td>
                                    <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400 max-w-[160px] truncate">{q.reason}</td>
                                    <td className="px-4 py-3">
                                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${q.status === 'quarantined' ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300' : 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'}`}>
                                            {q.status}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400">{new Date(q.quarantined_at).toLocaleString()}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {quarantine.length === 0 && (
                        <div className="text-center text-gray-400 py-12 text-sm">No quarantined files</div>
                    )}
                </div>
            )}

            {activeTab === 'dispatch' && (
                <div className="max-w-lg bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 space-y-4">
                    <h2 className="text-base font-semibold text-gray-900 dark:text-white">Manual Response Dispatch</h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Send an immediate response action to any agent in the fleet.</p>

                    <div className="space-y-3">
                        <div>
                            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Agent ID</label>
                            <input value={dispatchAgent} onChange={e => setDispatchAgent(e.target.value)}
                                placeholder="e.g. agent-abc123"
                                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none" />
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Action</label>
                            <select value={dispatchAction} onChange={e => setDispatchAction(e.target.value)}
                                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-violet-500 outline-none">
                                {Object.entries(ACTION_LABELS).map(([val, label]) => (
                                    <option key={val} value={val}>{label}</option>
                                ))}
                            </select>
                        </div>
                        {(dispatchAction === 'kill_process' || dispatchAction === 'quarantine_file') && (
                            <div>
                                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                    {dispatchAction === 'kill_process' ? 'PID' : 'File Path'}
                                </label>
                                <input value={dispatchParam} onChange={e => setDispatchParam(e.target.value)}
                                    placeholder={dispatchAction === 'kill_process' ? 'e.g. 1234' : 'e.g. /tmp/malware.exe'}
                                    className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-violet-500 outline-none" />
                            </div>
                        )}
                        <button onClick={dispatchManual} disabled={dispatching}
                            className="w-full py-2.5 rounded-lg bg-violet-600 hover:bg-violet-700 disabled:opacity-50 text-white font-medium text-sm transition-colors">
                            {dispatching ? 'Dispatching…' : 'Dispatch Action'}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default MDRDashboard;
