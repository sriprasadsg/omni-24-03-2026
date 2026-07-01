import React, { useState } from 'react';
import { ClockIcon, ChevronDownIcon, PlusIcon, RefreshCwIcon, TrashIcon } from './icons';
import * as api from '../services/apiService';

interface ChainOfCustodyPanelProps {
    controlId: string;
}

const ACTION_LABELS: Record<string, string> = {
    create: 'uploaded evidence',
    update: 'updated evidence',
    delete: 'deleted evidence',
};

function formatTimestamp(ts: string): string {
    try {
        return new Date(ts).toLocaleString('en-US', {
            timeZone: 'UTC',
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch {
        return ts;
    }
}

export const ChainOfCustodyPanel: React.FC<ChainOfCustodyPanelProps> = ({ controlId }) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [entries, setEntries] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [fetched, setFetched] = useState(false);

    const handleToggle = async () => {
        if (!isExpanded && !fetched) {
            setLoading(true);
            setError(null);
            try {
                const data = await api.fetchControlAuditLog(controlId);
                setEntries(data.entries ?? []);
                setFetched(true);
            } catch {
                setError('Failed to load audit log');
            } finally {
                setLoading(false);
            }
        }
        setIsExpanded(prev => !prev);
    };

    return (
        <div className="mt-4">
            <div
                className="flex items-center justify-between px-4 py-2 bg-gray-100 dark:bg-gray-700/50 rounded-t-md border border-gray-200 dark:border-gray-700 cursor-pointer"
                onClick={handleToggle}
                role="button"
                tabIndex={0}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') handleToggle(); }}
                aria-label={isExpanded ? 'Collapse chain of custody panel' : 'Expand chain of custody panel'}
            >
                <span className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-1.5">
                    <ClockIcon size={14} />
                    Chain of Custody
                    <span className="text-xs font-normal text-gray-400">({entries.length} events)</span>
                </span>
                <ChevronDownIcon
                    size={14}
                    className={`text-gray-500 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                />
            </div>

            {isExpanded && (
                <div className="border border-t-0 border-gray-200 dark:border-gray-700 rounded-b-md divide-y divide-gray-100 dark:divide-gray-700/50 bg-white dark:bg-gray-800">
                    {loading && (
                        <div className="flex justify-center py-4">
                            <svg className="animate-spin h-4 w-4 text-gray-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                            </svg>
                        </div>
                    )}
                    {!loading && error && (
                        <p className="px-4 py-4 text-xs text-red-500">
                            Failed to load audit log. Retry by collapsing and expanding this panel.
                        </p>
                    )}
                    {!loading && !error && entries.length === 0 && (
                        <p className="px-4 py-6 text-center text-xs text-gray-400 italic">
                            No chain-of-custody events recorded for this evidence.
                        </p>
                    )}
                    {!loading && !error && entries.map((entry, idx) => {
                        const actionType = entry.action_type ?? '';
                        const actor = entry.actor ?? 'unknown';
                        const ts = entry.timestamp ?? '';
                        const evidenceId = entry.evidenceId ?? '';
                        const snapshot = entry.snapshot_after ?? entry.snapshot_before ?? null;

                        let actionIcon: React.ReactNode;
                        if (actionType === 'create') {
                            actionIcon = <PlusIcon size={14} className="text-green-600 dark:text-green-400" />;
                        } else if (actionType === 'update') {
                            actionIcon = <RefreshCwIcon size={14} className="text-blue-600 dark:text-blue-400" />;
                        } else {
                            actionIcon = <TrashIcon size={14} className="text-red-500 dark:text-red-400" />;
                        }

                        return (
                            <div key={idx} className="px-4 py-3">
                                <div className="flex items-start gap-2">
                                    <div className="flex-shrink-0 mt-0.5">
                                        {actionIcon}
                                    </div>
                                    <div className="min-w-0">
                                        <p className="text-xs font-semibold text-gray-800 dark:text-gray-200">
                                            {actor} <span className="font-normal text-gray-500">{ACTION_LABELS[actionType] ?? actionType}</span>
                                        </p>
                                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                                            {formatTimestamp(ts)} UTC &middot; Evidence {evidenceId}
                                        </p>
                                        {actionType === 'update' && snapshot && (
                                            <details className="mt-1">
                                                <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600 dark:hover:text-gray-300">
                                                    Show change
                                                </summary>
                                                <pre className="mt-1 text-xs text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-700/50 p-2 rounded overflow-x-auto whitespace-pre-wrap break-words">
                                                    {JSON.stringify(snapshot, null, 2)}
                                                </pre>
                                            </details>
                                        )}
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};
