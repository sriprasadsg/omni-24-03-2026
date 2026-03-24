import React, { useState, useEffect } from 'react';
import { ZapIcon, PlusIcon, EditIcon, TrashIcon, ToggleRightIcon, ToggleLeftIcon } from './icons';

interface Policy {
    id: string;
    name: string;
    tenant_id: string;
    conditions: any;
    actions: any[];
    enabled: boolean;
    priority: number;
    execution_count: number;
    last_executed: string | null;
    created_at: string;
}

interface PolicyManagerProps {
    tenantId?: string;
}

export const PolicyManager: React.FC<PolicyManagerProps> = ({ tenantId }) => {
    const [policies, setPolicies] = useState<Policy[]>([]);
    const [loading, setLoading] = useState(true);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newPolicy, setNewPolicy] = useState({
        name: '',
        conditions: {
            severity: [],
            cvss_score: { min: 0 },
            asset_groups: []
        },
        actions: [{ type: 'auto_deploy_staged', config: {} }],
        priority: 0
    });

    useEffect(() => {
        fetchPolicies();
    }, [tenantId]);

    const fetchPolicies = async () => {
        try {
            const url = `/api/policies${tenantId ? `?tenant_id=${tenantId}` : ''}`;
            const response = await fetch(url);
            const data = await response.json();
            setPolicies(data.policies || []);
        } catch (error) {
            console.error('Error fetching policies:', error);
        } finally {
            setLoading(false);
        }
    };

    const togglePolicyStatus = async (policyId: string, currentStatus: boolean) => {
        try {
            const response = await fetch(`/api/policies/${policyId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: !currentStatus })
            });

            if (response.ok) {
                fetchPolicies();
            }
        } catch (error) {
            console.error('Error toggling policy:', error);
        }
    };

    const deletePolicy = async (policyId: string) => {
        if (!confirm('Are you sure you want to delete this policy?')) return;

        try {
            const response = await fetch(`/api/policies/${policyId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                fetchPolicies();
            }
        } catch (error) {
            console.error('Error deleting policy:', error);
        }
    };

    const createPolicy = async () => {
        try {
            const response = await fetch('/api/policies', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...newPolicy,
                    tenant_id: tenantId
                })
            });

            if (response.ok) {
                setShowCreateModal(false);
                fetchPolicies();
                // Reset form
                setNewPolicy({
                    name: '',
                    conditions: { severity: [], cvss_score: { min: 0 }, asset_groups: [] },
                    actions: [{ type: 'auto_deploy_staged', config: {} }],
                    priority: 0
                });
            }
        } catch (error) {
            console.error('Error creating policy:', error);
        }
    };

    const getActionTypeLabel = (type: string) => {
        const labels: Record<string, string> = {
            auto_deploy: 'Auto Deploy',
            auto_deploy_staged: 'Staged Deploy',
            request_approval: 'Request Approval',
            notify_only: 'Notify Only',
            quarantine: 'Quarantine'
        };
        return labels[type] || type;
    };

    if (loading) {
        return <div className="p-6">Loading policies...</div>;
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-2xl font-semibold text-gray-800 dark:text-white flex items-center">
                        <ZapIcon size={28} className="mr-3 text-primary-500" />
                        Patch Automation Policies
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        Define automated patch deployment rules based on severity, CVSS, EPSS, and compliance
                    </p>
                </div>
                <button
                    onClick={() => setShowCreateModal(true)}
                    className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 flex items-center gap-2 font-medium"
                >
                    <PlusIcon size={18} />
                    New Policy
                </button>
            </div>

            {/* Policies List */}
            {policies.length === 0 ? (
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-12 text-center">
                    <ZapIcon size={64} className="mx-auto mb-4 text-gray-400 opacity-50" />
                    <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">
                        No Policies Configured
                    </h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                        Create automated policies to streamline patch deployment
                    </p>
                    <button
                        onClick={() => setShowCreateModal(true)}
                        className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
                    >
                        Create First Policy
                    </button>
                </div>
            ) : (
                <div className="grid grid-cols-1 gap-4">
                    {policies.map(policy => (
                        <div key={policy.id} className="bg-white dark:bg-gray-800 rounded-lg shadow-md border border-gray-200 dark:border-gray-700">
                            <div className="p-6">
                                {/* Header Row */}
                                <div className="flex justify-between items-start mb-4">
                                    <div className="flex-1">
                                        <div className="flex items-center gap-3 mb-2">
                                            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                                                {policy.name}
                                            </h3>
                                            <span className="px-2 py-1 rounded text-xs font-semibold bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-300">
                                                Priority: {policy.priority}
                                            </span>
                                            {policy.enabled ? (
                                                <span className="px-2 py-1 rounded text-xs font-semibold bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300">
                                                    Active
                                                </span>
                                            ) : (
                                                <span className="px-2 py-1 rounded text-xs font-semibold bg-gray-100 text-gray-800 dark:bg-gray-900/50 dark:text-gray-300">
                                                    Disabled
                                                </span>
                                            )}
                                        </div>
                                        <div className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
                                            <p>Executed: {policy.execution_count} times</p>
                                            {policy.last_executed && (
                                                <p>Last execution: {new Date(policy.last_executed).toLocaleString()}</p>
                                            )}
                                        </div>
                                    </div>

                                    {/* Actions */}
                                    <div className="flex items-center gap-2">
                                        <button
                                            onClick={() => togglePolicyStatus(policy.id, policy.enabled)}
                                            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
                                            title={policy.enabled ? 'Disable' : 'Enable'}
                                        >
                                            {policy.enabled ? (
                                                <ToggleRightIcon size={20} className="text-green-600" />
                                            ) : (
                                                <ToggleLeftIcon size={20} className="text-gray-400" />
                                            )}
                                        </button>
                                        <button
                                            onClick={() => deletePolicy(policy.id)}
                                            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-red-600"
                                            title="Delete"
                                        >
                                            <TrashIcon size={18} />
                                        </button>
                                    </div>
                                </div>

                                {/* Conditions */}
                                <div className="mb-4">
                                    <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Conditions</h4>
                                    <div className="flex flex-wrap gap-2">
                                        {policy.conditions.severity && policy.conditions.severity.length > 0 && (
                                            <span className="px-3 py-1 bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300 rounded text-xs">
                                                Severity: {policy.conditions.severity.join(', ')}
                                            </span>
                                        )}
                                        {policy.conditions.cvss_score && (
                                            <span className="px-3 py-1 bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300 rounded text-xs">
                                                CVSS ≥ {policy.conditions.cvss_score.min}
                                            </span>
                                        )}
                                        {policy.conditions.epss_score && (
                                            <span className="px-3 py-1 bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300 rounded text-xs">
                                                EPSS ≥ {(policy.conditions.epss_score.min * 100).toFixed(1)}%
                                            </span>
                                        )}
                                        {policy.conditions.asset_groups && policy.conditions.asset_groups.length > 0 && (
                                            <span className="px-3 py-1 bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300 rounded text-xs">
                                                Groups: {policy.conditions.asset_groups.join(', ')}
                                            </span>
                                        )}
                                    </div>
                                </div>

                                {/* Actions */}
                                <div>
                                    <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Actions</h4>
                                    <div className="flex flex-wrap gap-2">
                                        {policy.actions.map((action: any, idx: number) => (
                                            <span key={idx} className="px-3 py-1 bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300 rounded text-xs font-medium">
                                                {getActionTypeLabel(action.type)}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Create Policy Modal */}
            {showCreateModal && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6">
                        <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-4">Create New Policy</h3>

                        <div className="space-y-4">
                            {/* Name */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    Policy Name
                                </label>
                                <input
                                    type="text"
                                    value={newPolicy.name}
                                    onChange={(e) => setNewPolicy({ ...newPolicy, name: e.target.value })}
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
                                    placeholder="e.g., Auto-deploy critical patches"
                                />
                            </div>

                            {/* Severity */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    Severity (select multiple)
                                </label>
                                <div className="flex gap-2">
                                    {['Critical', 'High', 'Medium', 'Low'].map(sev => (
                                        <label key={sev} className="flex items-center gap-2">
                                            <input
                                                type="checkbox"
                                                checked={newPolicy.conditions.severity.includes(sev)}
                                                onChange={(e) => {
                                                    const updated = e.target.checked
                                                        ? [...newPolicy.conditions.severity, sev]
                                                        : newPolicy.conditions.severity.filter(s => s !== sev);
                                                    setNewPolicy({
                                                        ...newPolicy,
                                                        conditions: { ...newPolicy.conditions, severity: updated }
                                                    });
                                                }}
                                            />
                                            <span className="text-sm">{sev}</span>
                                        </label>
                                    ))}
                                </div>
                            </div>

                            {/* CVSS */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    Minimum CVSS Score (0-10)
                                </label>
                                <input
                                    type="number"
                                    min="0"
                                    max="10"
                                    step="0.1"
                                    value={newPolicy.conditions.cvss_score.min}
                                    onChange={(e) => setNewPolicy({
                                        ...newPolicy,
                                        conditions: {
                                            ...newPolicy.conditions,
                                            cvss_score: { min: parseFloat(e.target.value) }
                                        }
                                    })}
                                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white w-32"
                                />
                            </div>

                            {/* Action Type */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    Action Type
                                </label>
                                <select
                                    value={newPolicy.actions[0].type}
                                    onChange={(e) => setNewPolicy({
                                        ...newPolicy,
                                        actions: [{ type: e.target.value, config: {} }]
                                    })}
                                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
                                >
                                    <option value="auto_deploy_staged">Staged Deployment</option>
                                    <option value="auto_deploy">Immediate Deployment</option>
                                    <option value="request_approval">Request Approval</option>
                                    <option value="notify_only">Notify Only</option>
                                    <option value="quarantine">Quarantine</option>
                                </select>
                            </div>

                            {/* Priority */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    Priority (higher = executed first)
                                </label>
                                <input
                                    type="number"
                                    value={newPolicy.priority}
                                    onChange={(e) => setNewPolicy({ ...newPolicy, priority: parseInt(e.target.value) })}
                                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white w-32"
                                />
                            </div>
                        </div>

                        {/* Footer */}
                        <div className="flex gap-3 mt-6">
                            <button
                                onClick={createPolicy}
                                className="flex-1 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 font-medium"
                            >
                                Create Policy
                            </button>
                            <button
                                onClick={() => setShowCreateModal(false)}
                                className="flex-1 px-4 py-2 bg-gray-300 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-400 dark:hover:bg-gray-600 font-medium"
                            >
                                Cancel
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
