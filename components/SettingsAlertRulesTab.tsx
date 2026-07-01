import React from 'react';
import { AlertRule } from '../types';
import { PlusCircleIcon, PencilIcon, TrashIcon } from './icons';

interface Props {
    alertRules: AlertRule[];
    canManageSettings: boolean;
    onNew: () => void;
    onEdit: (rule: AlertRule) => void;
    onDelete: (id: string) => void;
}

export function SettingsAlertRulesTab({ alertRules, canManageSettings, onNew, onEdit, onDelete }: Props) {
    return (
        <div>
            <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold">Alerting Rules</h3>
                {canManageSettings && (
                    <button onClick={onNew} className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                        <PlusCircleIcon size={16} className="mr-1.5" />
                        New Alert Rule
                    </button>
                )}
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                    <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                        <tr>
                            <th scope="col" className="px-4 py-3">Rule Name</th>
                            <th scope="col" className="px-4 py-3">Condition</th>
                            <th scope="col" className="px-4 py-3">Severity</th>
                            <th scope="col" className="px-4 py-3">Status</th>
                            <th scope="col" className="px-4 py-3">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {alertRules.map(rule => (
                            <tr key={rule.id} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
                                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{rule.name}</td>
                                <td className="px-4 py-3 font-mono text-xs">{`${rule.metric} ${rule.condition} ${rule.threshold}${rule.metric === 'cpu' || rule.metric === 'disk' ? '%' : ''} for ${rule.duration}m`}</td>
                                <td className="px-4 py-3">{rule.severity}</td>
                                <td className="px-4 py-3">
                                    <span className={`px-2 py-1 text-xs font-medium rounded-full ${rule.isEnabled ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300' : 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300'}`}>
                                        {rule.isEnabled ? 'Enabled' : 'Disabled'}
                                    </span>
                                </td>
                                <td className="px-4 py-3">
                                    {canManageSettings && (
                                        <div className="flex items-center space-x-2">
                                            <button onClick={() => onEdit(rule)} className="p-1.5 text-gray-500 hover:text-primary-600"><PencilIcon size={14} /></button>
                                            <button onClick={() => onDelete(rule.id)} className="p-1.5 text-gray-500 hover:text-red-600"><TrashIcon size={14} /></button>
                                        </div>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
