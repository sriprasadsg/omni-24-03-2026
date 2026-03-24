import React, { useState, useEffect } from 'react';
import { ShieldCheckIcon, PlusIcon, TrashIcon, AlertTriangleIcon, ActivityIcon, CpuIcon } from './icons';
import * as api from '../services/apiService';

export const AiPolicyEngine: React.FC = () => {
    const [policies, setPolicies] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newPolicy, setNewPolicy] = useState({
        name: '',
        description: '',
        rules: [] as any[],
        scope: { framework: '' },
        isActive: true
    });

    useEffect(() => {
        loadPolicies();
    }, []);

    const loadPolicies = async () => {
        setLoading(true);
        try {
            const data = await api.fetchAiPolicies();
            setPolicies(data);
        } catch (e) {
            console.error("Failed to load policies", e);
        } finally {
            setLoading(false);
        }
    };

    const handleCreatePolicy = async () => {
        try {
            await api.createAiPolicy({
                ...newPolicy,
                id: `policy-${Math.random().toString(36).substr(2, 9)}`,
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString()
            });
            setShowCreateModal(false);
            loadPolicies();
        } catch (e) {
            alert("Failed to create policy");
        }
    };

    const addRule = () => {
        setNewPolicy({
            ...newPolicy,
            rules: [...newPolicy.rules, { id: `rule-${Date.now()}`, name: '', condition: '', action: 'notify_admin', params: { severity: 'Medium' } }]
        });
    };

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Governance Policies</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Define automated rules for AI model compliance.</p>
                </div>
                <button
                    onClick={() => setShowCreateModal(true)}
                    className="flex items-center px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
                >
                    <PlusIcon size={16} className="mr-2" />
                    New Policy
                </button>
            </div>

            {loading ? (
                <div className="flex justify-center py-10">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {policies.map(policy => (
                        <div key={policy.id} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm hover:shadow-md transition-shadow">
                            <div className="flex justify-between items-start mb-4">
                                <div className="flex items-center">
                                    <div className="p-2 bg-primary-50 dark:bg-primary-900/20 rounded-lg mr-3">
                                        <ShieldCheckIcon size={20} className="text-primary-600 dark:text-primary-400" />
                                    </div>
                                    <div>
                                        <h4 className="font-bold text-gray-900 dark:text-white">{policy.name}</h4>
                                        <span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${policy.isActive ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                                            {policy.isActive ? 'Active' : 'Inactive'}
                                        </span>
                                    </div>
                                </div>
                                <button className="text-gray-400 hover:text-red-500 transition-colors">
                                    <TrashIcon size={16} />
                                </button>
                            </div>
                            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4 line-clamp-2">{policy.description}</p>

                            <div className="space-y-2">
                                <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Rules ({policy.rules.length})</div>
                                {policy.rules.map((rule: any) => (
                                    <div key={rule.id} className="flex items-center text-xs text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-gray-900/50 p-2 rounded border border-gray-100 dark:border-gray-800">
                                        <ActivityIcon size={12} className="mr-2 text-primary-500" />
                                        <span className="font-medium mr-2">{rule.name}:</span>
                                        <code className="text-primary-600 dark:text-primary-400">{rule.condition}</code>
                                    </div>
                                ))}
                            </div>

                            <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-700 flex justify-between items-center text-xs text-gray-500">
                                <div className="flex items-center">
                                    <CpuIcon size={12} className="mr-1" />
                                    Scope: {policy.scope?.framework || 'All Frameworks'}
                                </div>
                                <div>Updated {new Date(policy.updatedAt).toLocaleDateString()}</div>
                            </div>
                        </div>
                    ))}
                    {policies.length === 0 && (
                        <div className="col-span-full py-20 text-center bg-gray-50 dark:bg-gray-800/50 rounded-xl border border-dashed border-gray-300 dark:border-gray-700">
                            <ShieldCheckIcon size={48} className="mx-auto text-gray-300 mb-4" />
                            <p className="text-gray-500">No policies defined yet.</p>
                        </div>
                    )}
                </div>
            )}

            {/* Create Policy Modal */}
            {showCreateModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden">
                        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                            <h3 className="text-xl font-bold text-gray-900 dark:text-white">Create Governance Policy</h3>
                        </div>
                        <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Policy Name</label>
                                <input
                                    type="text"
                                    value={newPolicy.name}
                                    onChange={e => setNewPolicy({ ...newPolicy, name: e.target.value })}
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                                    placeholder="e.g., Production Safety Standards"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
                                <textarea
                                    value={newPolicy.description}
                                    onChange={e => setNewPolicy({ ...newPolicy, description: e.target.value })}
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                                    rows={2}
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Scope (Framework)</label>
                                    <select
                                        value={newPolicy.scope.framework}
                                        onChange={e => setNewPolicy({ ...newPolicy, scope: { framework: e.target.value } })}
                                        className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg"
                                    >
                                        <option value="">All Frameworks</option>
                                        <option value="PyTorch">PyTorch</option>
                                        <option value="TensorFlow">TensorFlow</option>
                                        <option value="Sklearn">Sklearn</option>
                                    </select>
                                </div>
                            </div>

                            <div className="space-y-3">
                                <div className="flex justify-between items-center">
                                    <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Rules</label>
                                    <button onClick={addRule} className="text-xs text-primary-600 font-bold hover:underline">+ Add Rule</button>
                                </div>
                                {newPolicy.rules.map((rule, idx) => (
                                    <div key={rule.id} className="p-4 bg-gray-50 dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 space-y-3">
                                        <div className="flex justify-between items-center">
                                            <input
                                                type="text"
                                                value={rule.name}
                                                onChange={e => {
                                                    const rules = [...newPolicy.rules];
                                                    rules[idx].name = e.target.value;
                                                    setNewPolicy({ ...newPolicy, rules });
                                                }}
                                                className="bg-transparent font-bold text-sm focus:outline-none"
                                                placeholder="Rule Name"
                                            />
                                            <button onClick={() => {
                                                const rules = newPolicy.rules.filter((_, i) => i !== idx);
                                                setNewPolicy({ ...newPolicy, rules });
                                            }} className="text-gray-400 hover:text-red-500"><TrashIcon size={14} /></button>
                                        </div>
                                        <input
                                            type="text"
                                            value={rule.condition}
                                            onChange={e => {
                                                const rules = [...newPolicy.rules];
                                                rules[idx].condition = e.target.value;
                                                setNewPolicy({ ...newPolicy, rules });
                                            }}
                                            className="w-full px-3 py-1.5 text-xs font-mono bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded"
                                            placeholder="e.g., metrics.accuracy > 0.9"
                                        />
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-end space-x-3">
                            <button onClick={() => setShowCreateModal(false)} className="px-4 py-2 text-gray-600 hover:text-gray-800 font-medium">Cancel</button>
                            <button onClick={handleCreatePolicy} className="px-6 py-2 bg-primary-600 text-white rounded-lg font-bold hover:bg-primary-700 shadow-lg shadow-primary-500/30">Save Policy</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
