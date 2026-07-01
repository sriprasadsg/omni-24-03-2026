import React, { useState, useEffect } from 'react';
import * as api from '../services/apiService';
import { showToast } from '../utils/toast';

export const EvidenceSettings: React.FC = () => {
    const [threshold, setThreshold] = useState<number>(7);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        api.fetchStalenessThreshold().then(d => setThreshold(d.thresholdDays ?? 7));
    }, []);

    const isValid = threshold >= 1 && threshold <= 365;

    const handleSave = async () => {
        if (!isValid) return;
        setSaving(true);
        try {
            await api.saveStalenessThreshold(threshold);
            showToast('Staleness threshold updated', 'success');
        } catch {
            showToast('Failed to save threshold — please try again', 'error');
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="space-y-6">
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600 p-4">
                <p className="text-sm font-semibold text-gray-900 dark:text-white mb-4">Evidence Quality</p>
                <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        Staleness Threshold
                    </label>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                        Automated evidence older than this many days is flagged as stale.
                    </p>
                    <div className="flex items-center">
                        <input
                            type="number"
                            min={1}
                            max={365}
                            value={threshold}
                            onChange={e =>
                                setThreshold(Math.min(365, Math.max(1, parseInt(e.target.value, 10) || 1)))
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
                        {saving ? 'Saving...' : 'Save Threshold'}
                    </button>
                </div>
            </div>
        </div>
    );
};
