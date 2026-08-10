import React, { useState, useEffect } from 'react';
import * as api from '../services/apiService';
import { showToast } from '../utils/toast';

export const RemediationSlaSettings: React.FC = () => {
    const [windowDays, setWindowDays] = useState<number>(7);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        api.fetchRemediationSlaWindow().then(d => setWindowDays(d.windowDays ?? 7));
    }, []);

    const isValid = windowDays >= 1 && windowDays <= 365;

    const handleSave = async () => {
        if (!isValid) return;
        setSaving(true);
        try {
            await api.saveRemediationSlaWindow(windowDays);
            showToast('SLA window updated', 'success');
        } catch {
            showToast('Failed to save threshold — please try again', 'error');
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="space-y-6">
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600 p-4">
                <p className="text-sm font-medium text-gray-900 dark:text-white mb-4">Remediation SLA</p>
                <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        At-Risk Window
                    </label>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                        Tasks with fewer than this many days until their due date are flagged "at risk".
                    </p>
                    <div className="flex items-center">
                        <input
                            type="number"
                            min={1}
                            max={365}
                            value={windowDays}
                            onChange={e =>
                                setWindowDays(Math.min(365, Math.max(1, parseInt(e.target.value, 10) || 1)))
                            }
                            className="w-24 px-3 py-2 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-gray-100"
                        />
                        <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">days</span>
                    </div>
                    {!isValid && (
                        <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                            Must be between 1 and 365 days.
                        </p>
                    )}
                </div>
                <div className="mt-4">
                    <button
                        onClick={handleSave}
                        disabled={!isValid || saving}
                        className="px-4 py-2 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {saving ? 'Saving...' : 'Save SLA Window'}
                    </button>
                </div>
            </div>
        </div>
    );
};
