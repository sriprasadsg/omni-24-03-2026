import React, { useState, useEffect } from 'react';
import {
    ShieldIcon, PlusIcon, Trash2Icon, PlayIcon, SaveIcon,
    CheckCircleIcon, XCircleIcon, AlertTriangleIcon
} from 'lucide-react';
import * as api from '../services/apiService';

export const SiemRulesDashboard: React.FC = () => {
    const [rules, setRules] = useState<any[]>([]);
    const [isCreating, setIsCreating] = useState(false);
    const [editingRule, setEditingRule] = useState<any>(null);
    const [loading, setLoading] = useState(false);

    // Form state
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [severity, setSeverity] = useState('Medium');
    const [conditionKey, setConditionKey] = useState('action');
    const [conditionValue, setConditionValue] = useState('');
    const [remediation, setRemediation] = useState('');

    useEffect(() => {
        fetchRules();
    }, []);

    const fetchRules = async () => {
        setLoading(true);
        try {
            // Simplified API call for demo purposes. 
            // In a real app this would be a proper Axios wrap in api.ts
            const tenantId = localStorage.getItem('tenantId') || 'platform-admin';
            const response = await fetch(`/api/siem/rules?tenant_id=${tenantId}`);
            if (response.ok) {
                const data = await response.json();
                setRules(data);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        const tenantId = localStorage.getItem('tenantId') || 'platform-admin';
        const ruleData = {
            name,
            description,
            severity,
            enabled: true,
            conditions: { [conditionKey]: conditionValue },
            remediation
        };

        try {
            const method = editingRule ? 'PUT' : 'POST';
            const url = editingRule
                ? `/api/siem/rules/${editingRule.id}?tenant_id=${tenantId}`
                : `/api/siem/rules?tenant_id=${tenantId}`;

            await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(ruleData)
            });
            setIsCreating(false);
            setEditingRule(null);
            fetchRules();
        } catch (e) {
            console.error(e);
        }
    };

    const handleDelete = async (id: string) => {
        const tenantId = localStorage.getItem('tenantId') || 'platform-admin';
        await fetch(`/api/siem/rules/${id}?tenant_id=${tenantId}`, {
            method: 'DELETE'
        });
        fetchRules();
    };

    const resetForm = () => {
        setName('');
        setDescription('');
        setSeverity('Medium');
        setConditionKey('action');
        setConditionValue('');
        setRemediation('');
    };

    return (
        <div className="p-6">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-2xl font-bold dark:text-white flex items-center gap-2">
                        <ShieldIcon className="text-indigo-600" /> SIEM Correlation Rules
                    </h1>
                    <p className="text-gray-500 text-sm mt-1">Manage rules for the native SIEM detection engine</p>
                </div>
                {!isCreating && !editingRule && (
                    <button
                        onClick={() => { resetForm(); setIsCreating(true); }}
                        className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg flex items-center gap-2"
                    >
                        <PlusIcon size={18} /> New Rule
                    </button>
                )}
            </div>

            {(isCreating || editingRule) ? (
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
                                value={description} onChange={e => setDescription(e.target.value)}
                                className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            />
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium dark:text-gray-300 mb-1">Severity</label>
                                <select
                                    value={severity} onChange={e => setSeverity(e.target.value)}
                                    className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                >
                                    <option>Critical</option>
                                    <option>High</option>
                                    <option>Medium</option>
                                    <option>Low</option>
                                </select>
                            </div>
                        </div>

                        <div className="border border-gray-200 dark:border-gray-700 p-4 rounded bg-gray-50 dark:bg-gray-900 mt-4">
                            <h3 className="text-sm font-semibold mb-2 dark:text-white">Detection Criteria (Simplified AND)</h3>
                            <div className="flex gap-4">
                                <div className="flex-1">
                                    <label className="block text-xs font-medium dark:text-gray-400 mb-1">Event Key</label>
                                    <select
                                        value={conditionKey} onChange={e => setConditionKey(e.target.value)}
                                        className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
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
                                        className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
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
                                placeholder="Investigate immediately."
                            />
                        </div>

                        <div className="flex justify-end gap-3 mt-6">
                            <button
                                onClick={() => { setIsCreating(false); setEditingRule(null); }}
                                className="px-4 py-2 border rounded text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleSave}
                                className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded flex items-center gap-2"
                            >
                                <SaveIcon size={16} /> Save Rule
                            </button>
                        </div>
                    </div>
                </div>
            ) : (
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
                    <table className="w-full text-left">
                        <thead className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
                            <tr>
                                <th className="p-4 font-medium text-xs text-gray-500 uppercase">Rule Name</th>
                                <th className="p-4 font-medium text-xs text-gray-500 uppercase">Severity</th>
                                <th className="p-4 font-medium text-xs text-gray-500 uppercase">Criteria</th>
                                <th className="p-4 font-medium text-xs text-gray-500 uppercase">Status</th>
                                <th className="p-4 font-medium text-xs text-gray-500 uppercase">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                            {rules.length === 0 ? (
                                <tr>
                                    <td colSpan={5} className="p-8 text-center text-gray-500 dark:text-gray-400">
                                        No correlation rules defined. Create one to start generating native SIEM alerts.
                                    </td>
                                </tr>
                            ) : rules.map(rule => (
                                <tr key={rule.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                                    <td className="p-4">
                                        <div className="font-medium dark:text-white">{rule.name}</div>
                                        <div className="text-xs text-gray-500 truncate max-w-xs">{rule.description}</div>
                                    </td>
                                    <td className="p-4">
                                        <span className={`px-2 py-1 text-xs rounded-full ${rule.severity === 'Critical' ? 'bg-red-100 text-red-800' :
                                            rule.severity === 'High' ? 'bg-orange-100 text-orange-800' :
                                                rule.severity === 'Medium' ? 'bg-yellow-100 text-yellow-800' :
                                                    'bg-blue-100 text-blue-800'
                                            }`}>
                                            {rule.severity}
                                        </span>
                                    </td>
                                    <td className="p-4">
                                        <div className="text-sm font-mono bg-gray-100 dark:bg-gray-900 px-2 py-1 rounded inline-block text-gray-800 dark:text-gray-300">
                                            {JSON.stringify(rule.conditions)}
                                        </div>
                                    </td>
                                    <td className="p-4">
                                        {rule.enabled ? (
                                            <span className="flex items-center text-green-600 text-sm"><CheckCircleIcon size={16} className="mr-1" /> Active</span>
                                        ) : (
                                            <span className="flex items-center text-gray-500 text-sm"><XCircleIcon size={16} className="mr-1" /> Disabled</span>
                                        )}
                                    </td>
                                    <td className="p-4 flex gap-2">
                                        <button
                                            onClick={() => {
                                                const k = Object.keys(rule.conditions)[0] || 'action';
                                                setConditionKey(k);
                                                setConditionValue(rule.conditions[k] || '');
                                                setName(rule.name);
                                                setDescription(rule.description);
                                                setSeverity(rule.severity || 'Medium');
                                                setRemediation(rule.remediation || '');
                                                setEditingRule(rule);
                                            }}
                                            className="text-blue-600 hover:text-blue-800"
                                        >
                                            Edit
                                        </button>
                                        <button
                                            onClick={() => handleDelete(rule.id)}
                                            className="text-red-500 hover:text-red-700"
                                        >
                                            <Trash2Icon size={18} />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
};
