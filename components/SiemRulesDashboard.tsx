import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ShieldIcon, PlusIcon, Trash2Icon, SaveIcon, ToggleLeftIcon, ToggleRightIcon, ActivityIcon } from 'lucide-react';
import * as api from '../services/apiService';
import { socketService } from '../services/socketService';

const SEV_COLORS: Record<string, string> = {
    Critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    High:     'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
    Medium:   'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    Low:      'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
};

export const SiemRulesDashboard: React.FC = () => {
    const [rules, setRules] = useState<any[]>([]);
    const [isCreating, setIsCreating] = useState(false);
    const [editingRule, setEditingRule] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [liveMatchRuleId, setLiveMatchRuleId] = useState<string | null>(null);

    // Form state
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [severity, setSeverity] = useState('Medium');
    const [conditionKey, setConditionKey] = useState('action');
    const [conditionValue, setConditionValue] = useState('');
    const [remediation, setRemediation] = useState('');

    const fetchRules = useCallback(async () => {
        setLoading(true);
        try {
            const response = await api.authFetch('/api/siem/rules');
            if (response.ok) setRules(await response.json());
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    }, []);

    // Initial load
    useEffect(() => { fetchRules(); }, [fetchRules]);

    // WebSocket: live match_count updates
    useEffect(() => {
        const onRuleMatch = (data: any) => {
            setRules(prev => prev.map(r =>
                r.id === data.rule_id ? { ...r, match_count: data.match_count } : r
            ));
            // Flash the matched rule briefly
            setLiveMatchRuleId(data.rule_id);
            setTimeout(() => setLiveMatchRuleId(null), 2000);
        };
        socketService.on('siem_rule_match', onRuleMatch);
        return () => socketService.off('siem_rule_match', onRuleMatch);
    }, []);

    // Polling fallback: refresh match_counts every 30 s
    useEffect(() => {
        const interval = setInterval(fetchRules, 30_000);
        return () => clearInterval(interval);
    }, [fetchRules]);


    const handleSave = async () => {
        const ruleData = {
            name, description, severity,
            enabled: editingRule ? editingRule.enabled : true,
            conditions: { [conditionKey]: conditionValue },
            remediation,
        };
        try {
            const method = editingRule ? 'PUT' : 'POST';
            const url = editingRule ? `/api/siem/rules/${editingRule.id}` : '/api/siem/rules';
            const res = await api.authFetch(url, { method, body: JSON.stringify(ruleData) });
            if (!res.ok) throw new Error(await res.text());
            setIsCreating(false);
            setEditingRule(null);
            fetchRules();
        } catch (e) { console.error(e); }
    };

    const handleDelete = async (id: string) => {
        if (!window.confirm('Delete this rule?')) return;
        await api.authFetch(`/api/siem/rules/${id}`, { method: 'DELETE' });
        fetchRules();
    };

    const handleToggle = async (id: string) => {
        try {
            const res = await api.authFetch(`/api/siem/rules/${id}/toggle`, { method: 'PATCH' });
            if (res.ok) {
                const data = await res.json();
                setRules(prev => prev.map(r => r.id === id ? { ...r, enabled: data.enabled } : r));
            }
        } catch (e) { console.error(e); }
    };

    const openEdit = (rule: any) => {
        const k = Object.keys(rule.conditions || {})[0] || 'action';
        setConditionKey(k);
        setConditionValue(rule.conditions?.[k] || '');
        setName(rule.name);
        setDescription(rule.description || '');
        setSeverity(rule.severity || 'Medium');
        setRemediation(rule.remediation || '');
        setEditingRule(rule);
    };

    const resetForm = () => {
        setName(''); setDescription(''); setSeverity('Medium');
        setConditionKey('action'); setConditionValue(''); setRemediation('');
    };

    const totalActive = rules.filter(r => r.enabled).length;
    const totalMatches = rules.reduce((sum, r) => sum + (r.match_count || 0), 0);

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex justify-between items-start">
                <div>
                    <h1 className="text-2xl font-bold dark:text-white flex items-center gap-2">
                        <ShieldIcon className="text-indigo-600" /> SIEM Correlation Rules
                        <span className="flex items-center gap-1 text-xs font-medium text-green-600 bg-green-50 dark:bg-green-900/30 dark:text-green-400 px-2 py-0.5 rounded-full border border-green-200 dark:border-green-800">
                            <ActivityIcon size={11} className="animate-pulse" /> Live
                        </span>
                    </h1>
                    <p className="text-gray-500 text-sm mt-1">Manage rules for the native SIEM detection engine — match counts update in real time</p>
                </div>
                {!isCreating && !editingRule && (
                    <button
                        onClick={() => { resetForm(); setIsCreating(true); }}
                        className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 text-sm font-medium"
                    >
                        <PlusIcon size={16} /> New Rule
                    </button>
                )}
            </div>

            {/* Stats bar */}
            {!isCreating && !editingRule && rules.length > 0 && (
                <div className="grid grid-cols-3 gap-4">
                    {[
                        { label: 'Total Rules', value: rules.length, color: 'text-indigo-600' },
                        { label: 'Active Rules', value: totalActive, color: 'text-green-600' },
                        { label: 'Total Matches', value: totalMatches.toLocaleString(), color: 'text-orange-600' },
                    ].map(s => (
                        <div key={s.label} className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 text-center">
                            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
                            <div className="text-xs text-gray-500 mt-1">{s.label}</div>
                        </div>
                    ))}
                </div>
            )}

            {/* Form panel */}
            {(isCreating || editingRule) && (
                <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
                    <h2 className="text-lg font-semibold mb-4 dark:text-white">
                        {editingRule ? 'Edit Rule' : 'Create Correlation Rule'}
                    </h2>
                    <div className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium dark:text-gray-300 mb-1">Rule Name</label>
                            <input
                                type="text" value={name} onChange={e => setName(e.target.value)}
                                className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                placeholder="e.g. Multiple Failed Logins"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium dark:text-gray-300 mb-1">Description</label>
                            <textarea
                                value={description} onChange={e => setDescription(e.target.value)} rows={2}
                                className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                placeholder="What does this rule detect?"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium dark:text-gray-300 mb-1">Severity</label>
                            <select
                                value={severity} onChange={e => setSeverity(e.target.value)}
                                className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            >
                                <option>Critical</option><option>High</option>
                                <option>Medium</option><option>Low</option>
                            </select>
                        </div>
                        <div className="border border-gray-200 dark:border-gray-700 p-4 rounded bg-gray-50 dark:bg-gray-900">
                            <h3 className="text-sm font-semibold mb-3 dark:text-white">Detection Criteria</h3>
                            <div className="flex gap-4">
                                <div className="flex-1">
                                    <label className="block text-xs font-medium dark:text-gray-400 mb-1">Event Field</label>
                                    <select
                                        value={conditionKey} onChange={e => setConditionKey(e.target.value)}
                                        className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white text-sm"
                                    >
                                        <option value="action">Action</option>
                                        <option value="category">Category</option>
                                        <option value="source">Source</option>
                                    </select>
                                </div>
                                <div className="flex-1">
                                    <label className="block text-xs font-medium dark:text-gray-400 mb-1">Equals Value</label>
                                    <input
                                        type="text" value={conditionValue} onChange={e => setConditionValue(e.target.value)}
                                        className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white text-sm"
                                        placeholder="e.g. login_failed"
                                    />
                                </div>
                            </div>
                        </div>
                        <div>
                            <label className="block text-sm font-medium dark:text-gray-300 mb-1">Remediation Steps</label>
                            <input
                                type="text" value={remediation} onChange={e => setRemediation(e.target.value)}
                                className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                placeholder="e.g. Block IP, notify security team"
                            />
                        </div>
                        <div className="flex justify-end gap-3 mt-4">
                            <button
                                onClick={() => { setIsCreating(false); setEditingRule(null); }}
                                className="px-4 py-2 border rounded text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 text-sm"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleSave}
                                className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded flex items-center gap-2 text-sm"
                            >
                                <SaveIcon size={14} /> Save Rule
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Rules table */}
            {!isCreating && !editingRule && (
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
                    {loading ? (
                        <div className="p-8 text-center text-gray-400">Loading rules...</div>
                    ) : (
                        <table className="w-full text-left text-sm">
                            <thead className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
                                <tr>
                                    <th className="p-4 font-semibold text-xs text-gray-500 uppercase tracking-wider">Rule</th>
                                    <th className="p-4 font-semibold text-xs text-gray-500 uppercase tracking-wider">Severity</th>
                                    <th className="p-4 font-semibold text-xs text-gray-500 uppercase tracking-wider">MITRE ATT&amp;CK</th>
                                    <th className="p-4 font-semibold text-xs text-gray-500 uppercase tracking-wider text-center">Matches</th>
                                    <th className="p-4 font-semibold text-xs text-gray-500 uppercase tracking-wider">Status</th>
                                    <th className="p-4 font-semibold text-xs text-gray-500 uppercase tracking-wider">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                                {rules.length === 0 ? (
                                    <tr>
                                        <td colSpan={6} className="p-10 text-center text-gray-400">
                                            No correlation rules defined. Click <strong>New Rule</strong> to create one.
                                        </td>
                                    </tr>
                                ) : rules.map(rule => (
                                    <tr key={rule.id} className={`transition-colors ${!rule.enabled ? 'opacity-60' : ''} ${liveMatchRuleId === rule.id ? 'bg-orange-50 dark:bg-orange-900/20' : 'hover:bg-gray-50 dark:hover:bg-gray-700/40'}`}>
                                        <td className="p-4 max-w-xs">
                                            <div className="font-medium dark:text-white">{rule.name}</div>
                                            <div className="text-xs text-gray-500 mt-0.5 line-clamp-1">{rule.description}</div>
                                            {rule.remediation && (
                                                <div className="text-xs text-indigo-500 mt-0.5 truncate" title={rule.remediation}>
                                                    ↳ {rule.remediation}
                                                </div>
                                            )}
                                        </td>
                                        <td className="p-4 whitespace-nowrap">
                                            <span className={`px-2 py-0.5 text-xs font-semibold rounded-full ${SEV_COLORS[rule.severity] || SEV_COLORS.Low}`}>
                                                {rule.severity}
                                            </span>
                                        </td>
                                        <td className="p-4 max-w-[200px]">
                                            {rule.mitre_tactic ? (
                                                <div>
                                                    <div className="text-xs font-medium text-purple-600 dark:text-purple-400">{rule.mitre_tactic}</div>
                                                    <div className="text-xs text-gray-500 mt-0.5 leading-tight">{rule.mitre_technique}</div>
                                                    {rule.threat_actor && (
                                                        <div className="text-xs text-rose-500 dark:text-rose-400 mt-1 truncate" title={rule.threat_actor}>
                                                            {rule.threat_actor}
                                                        </div>
                                                    )}
                                                </div>
                                            ) : (
                                                <code className="text-xs bg-gray-100 dark:bg-gray-900 px-2 py-1 rounded text-gray-700 dark:text-gray-300">
                                                    {JSON.stringify(rule.conditions)}
                                                </code>
                                            )}
                                        </td>
                                        <td className="p-4 text-center">
                                            <span className={`font-mono text-sm font-semibold ${(rule.match_count || 0) > 0 ? 'text-orange-600' : 'text-gray-400'}`}>
                                                {(rule.match_count || 0).toLocaleString()}
                                            </span>
                                        </td>
                                        <td className="p-4">
                                            <button
                                                onClick={() => handleToggle(rule.id)}
                                                title={rule.enabled ? 'Click to disable' : 'Click to enable'}
                                                className="flex items-center gap-1.5 text-sm hover:opacity-70 transition-opacity"
                                            >
                                                {rule.enabled ? (
                                                    <>
                                                        <ToggleRightIcon size={20} className="text-green-500" />
                                                        <span className="text-green-600 font-medium">Active</span>
                                                    </>
                                                ) : (
                                                    <>
                                                        <ToggleLeftIcon size={20} className="text-gray-400" />
                                                        <span className="text-gray-400">Disabled</span>
                                                    </>
                                                )}
                                            </button>
                                        </td>
                                        <td className="p-4">
                                            <div className="flex items-center gap-3">
                                                <button
                                                    onClick={() => openEdit(rule)}
                                                    className="text-indigo-600 hover:text-indigo-800 text-xs font-medium"
                                                >
                                                    Edit
                                                </button>
                                                <button
                                                    onClick={() => handleDelete(rule.id)}
                                                    className="text-red-500 hover:text-red-700"
                                                    title="Delete rule"
                                                >
                                                    <Trash2Icon size={15} />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            )}
        </div>
    );
};
