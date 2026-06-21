import React, { useState } from 'react';
import { ChevronDownIcon, PlusIcon, RefreshCwIcon, TrashIcon, ClockIcon } from './icons';
import * as api from '../services/apiService';

interface ChainOfCustodyPanelProps {
    controlId: string;
}

function ActionIcon({ actionType }: { actionType: string }) {
    if (actionType === 'create') {
        return <PlusIcon size={14} className="text-green-600 dark:text-green-400 flex-shrink-0" />;
    }
    if (actionType === 'delete') {
        return <TrashIcon size={14} className="text-red-600 dark:text-red-400 flex-shrink-0" />;
    }
    return <RefreshCwIcon size={14} className="text-blue-600 dark:text-blue-400 flex-shrink-0" />;
}

function actionLabel(actionType: string): string {
    if (actionType === 'create') return 'uploaded evidence';
    if (actionType === 'delete') return 'deleted evidence';
    return 'updated evidence';
}

function formatTimestamp(ts: string): string {
    try {
        return new Date(ts).toLocaleString('en-US', {
            timeZone: 'UTC',
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        }) + ' UTC';
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
        const expanding = !isExpanded;
        setIsExpanded(expanding);
        if (expanding && !fetched) {
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
    };

    return (
        <div className="mt-3">
            <div
                role="button"
                tabIndex={0}
                onClick={handleToggle}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') handleToggle(); }}
                aria-label={isExpanded ? 'Collapse chain of custody panel' : 'Expand chain of custody panel'}
                className="flex items-center justify-between px-4 py-2 bg-gray-100 dark:bg-gray-700/50 rounded-t-md border border-gray-200 dark:border-gray-700 cursor-pointer"
            >
                <div className="flex items-center gap-1.5">
                    <ClockIcon size={14} className="text-gray-500 dark:text-gray-400" />
                    <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">Chain of Custody</span>
                    <span className="text-xs font-normal text-gray-400">({entries.length} events)</span>
                </div>
                <ChevronDownIcon
                    size={14}
                    className={`text-gray-500 dark:text-gray-400 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
                />
            </div>
            {isExpanded && (
                <div className="border border-t-0 border-gray-200 dark:border-gray-700 rounded-b-md divide-y divide-gray-100 dark:divide-gray-700/50 bg-white dark:bg-gray-800">
                    {loading && (
                        <div className="flex items-center justify-center py-6">
                            <svg className="animate-spin h-5 w-5 text-gray-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
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
                    {!loading && !error && entries.map((entry: any, idx: number) => (
                        <div key={entry.id ?? idx} className="px-4 py-3">
                            <div className="flex items-start gap-2">
                                <ActionIcon actionType={entry.action_type} />
                                <div className="flex-1 min-w-0">
                                    <p className="text-xs text-gray-800 dark:text-gray-200">
                                        <span className="font-medium">{entry.actor}</span>
                                        {' '}{actionLabel(entry.action_type)}
                                    </p>
                                    <p className="text-xs text-gray-400 mt-0.5">
                                        {formatTimestamp(entry.timestamp)}
                                        {entry.evidenceId ? ` · Evidence ${entry.evidenceId}` : ''}
                                    </p>
                                    {entry.action_type === 'update' && (entry.snapshot_after || entry.snapshot_before) && (
                                        <details className="mt-1">
                                            <summary className="text-xs text-blue-500 cursor-pointer">Show change</summary>
                                            <pre className="mt-1 text-xs bg-gray-50 dark:bg-gray-700 rounded p-2 overflow-auto max-h-40 whitespace-pre-wrap break-all">
                                                {JSON.stringify(entry.snapshot_after ?? entry.snapshot_before, null, 2)}
                                            </pre>
                                        </details>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};
