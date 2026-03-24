import React, { useState } from 'react';
import { AutomationPolicy } from '../types';
import { useUser } from '../contexts/UserContext';
import { WorkflowIcon, ZapIcon, AlertTriangleIcon, PlusIcon, XIcon } from './icons';

interface AutomationPoliciesDashboardProps {
    policies: AutomationPolicy[];
    onUpdatePolicy: (policy: AutomationPolicy) => void;
    onAddPolicy: (policy: Omit<AutomationPolicy, 'id'>) => void;
}

const TRIGGERS: { value: AutomationPolicy['trigger']; label: string; icon: React.ReactNode }[] = [
    { value: 'agent.error', label: 'Agent Error', icon: <AlertTriangleIcon size={14} className="mr-1.5 text-red-400" /> },
    { value: 'alert.critical', label: 'Critical Alert', icon: <ZapIcon size={14} className="mr-1.5 text-amber-400" /> },
];

const ACTIONS: { value: AutomationPolicy['action']; label: string }[] = [
    { value: 'remediate.agent', label: 'Remediate Agent' },
    { value: 'create.case', label: 'Create Security Case' },
];

const triggerMap = Object.fromEntries(TRIGGERS.map(t => [t.value, t]));
const actionMap = Object.fromEntries(ACTIONS.map(a => [a.value, a]));

// ── Add Policy Modal ────────────────────────────────────────────────────────
interface AddPolicyModalProps {
    onClose: () => void;
    onSave: (policy: Omit<AutomationPolicy, 'id'>) => void;
}

const EMPTY_CONDITION = { field: '', operator: 'contains' as const, value: '' };

const AddPolicyModal: React.FC<AddPolicyModalProps> = ({ onClose, onSave }) => {
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [trigger, setTrigger] = useState<AutomationPolicy['trigger']>('agent.error');
    const [action, setAction] = useState<AutomationPolicy['action']>('remediate.agent');
    const [conditions, setConditions] = useState([{ ...EMPTY_CONDITION }]);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');

    const addCondition = () => setConditions(c => [...c, { ...EMPTY_CONDITION }]);
    const removeCondition = (i: number) => setConditions(c => c.filter((_, idx) => idx !== i));
    const updateCondition = (i: number, key: keyof typeof EMPTY_CONDITION, val: string) =>
        setConditions(c => c.map((cond, idx) => idx === i ? { ...cond, [key]: val } : cond));

    const handleSave = async () => {
        if (!name.trim()) { setError('Policy name is required.'); return; }
        if (!description.trim()) { setError('Description is required.'); return; }
        const validConditions = conditions.filter(c => c.field.trim() && c.value.trim());
        setSaving(true);
        onSave({ name: name.trim(), description: description.trim(), trigger, action, conditions: validConditions, isEnabled: true });
        onClose();
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in">
            <div className="relative bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
                    <div className="flex items-center gap-3">
                        <div className="p-2 rounded-xl bg-primary-500/10">
                            <WorkflowIcon className="text-primary-500" size={20} />
                        </div>
                        <div>
                            <h2 className="text-lg font-bold text-gray-900 dark:text-white">New Automation Policy</h2>
                            <p className="text-xs text-gray-500 dark:text-gray-400">Define a rule for autonomous agent action</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 transition-colors">
                        <XIcon size={18} />
                    </button>
                </div>

                <div className="p-6 space-y-5">
                    {error && (
                        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400">
                            <AlertTriangleIcon size={14} />
                            {error}
                        </div>
                    )}

                    {/* Name */}
                    <div>
                        <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5 uppercase tracking-wide">
                            Policy Name <span className="text-red-500">*</span>
                        </label>
                        <input
                            type="text"
                            value={name}
                            onChange={e => { setName(e.target.value); setError(''); }}
                            placeholder="e.g. Auto-Remediate Offline Agents"
                            className="w-full px-3 py-2.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 transition"
                        />
                    </div>

                    {/* Description */}
                    <div>
                        <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5 uppercase tracking-wide">
                            Description <span className="text-red-500">*</span>
                        </label>
                        <textarea
                            value={description}
                            onChange={e => { setDescription(e.target.value); setError(''); }}
                            rows={2}
                            placeholder="Describe what this policy does and when it applies…"
                            className="w-full px-3 py-2.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 transition resize-none"
                        />
                    </div>

                    {/* Trigger + Action (side by side) */}
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5 uppercase tracking-wide">Trigger</label>
                            <select
                                value={trigger}
                                onChange={e => setTrigger(e.target.value as AutomationPolicy['trigger'])}
                                className="w-full px-3 py-2.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500 transition"
                            >
                                {TRIGGERS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5 uppercase tracking-wide">Action</label>
                            <select
                                value={action}
                                onChange={e => setAction(e.target.value as AutomationPolicy['action'])}
                                className="w-full px-3 py-2.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500 transition"
                            >
                                {ACTIONS.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
                            </select>
                        </div>
                    </div>

                    {/* Conditions */}
                    <div>
                        <div className="flex items-center justify-between mb-2">
                            <label className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                                Conditions <span className="text-gray-400 font-normal normal-case">(optional)</span>
                            </label>
                            <button
                                onClick={addCondition}
                                className="flex items-center gap-1 text-xs text-primary-500 hover:text-primary-600 font-medium transition-colors"
                            >
                                <PlusIcon size={12} /> Add condition
                            </button>
                        </div>
                        <div className="space-y-2">
                            {conditions.map((cond, i) => (
                                <div key={i} className="flex gap-2 items-center">
                                    <input
                                        type="text"
                                        value={cond.field}
                                        onChange={e => updateCondition(i, 'field', e.target.value)}
                                        placeholder="Field (e.g. severity)"
                                        className="flex-1 px-2.5 py-2 text-xs rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                                    />
                                    <select
                                        value={cond.operator}
                                        onChange={e => updateCondition(i, 'operator', e.target.value)}
                                        className="px-2 py-2 text-xs rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                                    >
                                        <option value="contains">contains</option>
                                        <option value="equals">equals</option>
                                    </select>
                                    <input
                                        type="text"
                                        value={cond.value}
                                        onChange={e => updateCondition(i, 'value', e.target.value)}
                                        placeholder="Value"
                                        className="flex-1 px-2.5 py-2 text-xs rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                                    />
                                    {conditions.length > 1 && (
                                        <button onClick={() => removeCondition(i)} className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-gray-400 hover:text-red-500 transition-colors">
                                            <XIcon size={14} />
                                        </button>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Footer */}
                <div className="flex items-center justify-between p-6 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 rounded-b-2xl">
                    <p className="text-xs text-gray-500 dark:text-gray-400">Policy will be <span className="font-semibold text-green-500">enabled</span> by default</p>
                    <div className="flex gap-3">
                        <button
                            onClick={onClose}
                            className="px-4 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                        >
                            Cancel
                        </button>
                        <button
                            onClick={handleSave}
                            disabled={saving}
                            className="px-4 py-2 text-sm rounded-lg bg-primary-600 hover:bg-primary-700 text-white font-semibold shadow-sm transition-colors disabled:opacity-60"
                        >
                            {saving ? 'Saving…' : 'Create Policy'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

// ── Main Dashboard ──────────────────────────────────────────────────────────
export const AutomationPoliciesDashboard: React.FC<AutomationPoliciesDashboardProps> = ({ policies, onUpdatePolicy, onAddPolicy }) => {
    const { hasPermission } = useUser();
    const canManage = hasPermission('manage:automation');
    const [showModal, setShowModal] = useState(false);

    const handleToggle = (policy: AutomationPolicy) => {
        if (!canManage) return;
        onUpdatePolicy({ ...policy, isEnabled: !policy.isEnabled });
    };

    const handleSavePolicy = (policy: Omit<AutomationPolicy, 'id'>) => {
        onAddPolicy(policy);
        setShowModal(false);
    };

    return (
        <>
            <div className="container mx-auto">
                {/* Page header */}
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
                    <div>
                        <h2 className="text-2xl font-semibold text-gray-800 dark:text-white">Automation Policies</h2>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                            Define rules for when the Omni-Agent AI can perform actions autonomously.
                        </p>
                    </div>
                    {canManage && (
                        <button
                            id="add-policy-btn"
                            onClick={() => setShowModal(true)}
                            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-primary-600 hover:bg-primary-700 text-white text-sm font-semibold shadow-md hover:shadow-primary-500/30 transition-all duration-200 active:scale-95 whitespace-nowrap"
                        >
                            <PlusIcon size={16} />
                            Add Policy
                        </button>
                    )}
                </div>

                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                    <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
                        <h3 className="text-lg font-semibold flex items-center text-gray-800 dark:text-white">
                            <WorkflowIcon className="mr-2 text-primary-500" />
                            Closed-Loop Remediation Policies
                        </h3>
                        <span className="text-xs text-gray-400 bg-gray-100 dark:bg-gray-700 px-2.5 py-1 rounded-full font-medium">
                            {policies.length} {policies.length === 1 ? 'policy' : 'policies'}
                        </span>
                    </div>

                    {policies.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                            <WorkflowIcon size={40} className="mb-3 opacity-30" />
                            <p className="text-sm font-medium">No policies defined yet</p>
                            <p className="text-xs mt-1">Click <span className="font-semibold text-primary-500">Add Policy</span> to create your first automation rule</p>
                        </div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                                <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                                    <tr>
                                        <th scope="col" className="px-6 py-3">Policy</th>
                                        <th scope="col" className="px-6 py-3">Trigger</th>
                                        <th scope="col" className="px-6 py-3">Action</th>
                                        <th scope="col" className="px-6 py-3">Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {policies.map(policy => {
                                        const trig = triggerMap[policy.trigger];
                                        const act = actionMap[policy.action];
                                        return (
                                            <tr key={policy.id} className="bg-white dark:bg-gray-800 border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                                                <td className="px-6 py-4">
                                                    <p className="font-semibold text-gray-800 dark:text-gray-200">{policy.name}</p>
                                                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{policy.description}</p>
                                                    {policy.conditions.length > 0 && (
                                                        <div className="flex flex-wrap gap-1 mt-1.5">
                                                            {policy.conditions.map((c, i) => (
                                                                <span key={i} className="text-xs font-mono bg-gray-100 dark:bg-gray-900 px-1.5 py-0.5 rounded text-gray-600 dark:text-gray-300">
                                                                    {c.field} {c.operator} &quot;{c.value}&quot;
                                                                </span>
                                                            ))}
                                                        </div>
                                                    )}
                                                </td>
                                                <td className="px-6 py-4">
                                                    <span className="inline-flex items-center text-xs font-medium text-gray-700 dark:text-gray-300">
                                                        {trig?.icon}
                                                        {trig?.label ?? policy.trigger}
                                                    </span>
                                                </td>
                                                <td className="px-6 py-4">
                                                    <span className="font-mono text-xs px-2 py-1 bg-gray-100 dark:bg-gray-900 rounded-md text-gray-700 dark:text-gray-300">
                                                        {act?.label ?? policy.action}
                                                    </span>
                                                </td>
                                                <td className="px-6 py-4">
                                                    <button
                                                        type="button"
                                                        className={`${policy.isEnabled ? 'bg-primary-600' : 'bg-gray-200 dark:bg-gray-600'} ${!canManage ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'} relative inline-flex h-6 w-11 flex-shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 dark:ring-offset-gray-800`}
                                                        role="switch"
                                                        aria-checked={policy.isEnabled}
                                                        onClick={() => handleToggle(policy)}
                                                        disabled={!canManage}
                                                        title={!canManage ? 'Permission Denied' : policy.isEnabled ? 'Disable policy' : 'Enable policy'}
                                                    >
                                                        <span
                                                            aria-hidden="true"
                                                            className={`${policy.isEnabled ? 'translate-x-5' : 'translate-x-0'} pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out`}
                                                        />
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
            </div>

            {showModal && (
                <AddPolicyModal
                    onClose={() => setShowModal(false)}
                    onSave={handleSavePolicy}
                />
            )}
        </>
    );
};
