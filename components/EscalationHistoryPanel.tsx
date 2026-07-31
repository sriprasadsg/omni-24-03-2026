import React, { useState } from 'react';
import { HistoryIcon, ChevronDownIcon, AlertTriangleIcon } from './icons';
import * as api from '../services/apiService';

interface EscalationHistoryPanelProps {
    taskId: string;
}

interface EscalationEntry {
    escalation_level: number;
    created_at: string;
    notified: string[];
}

function formatEscalationTimestamp(ts: string): string {
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

function summarizeNotified(notified: string[]): string {
    if (!notified || notified.length === 0) return 'none';
    return notified.join(', ');
}

// Escalation History panel (SLA-02) — lazy-expand-on-toggle, read-only, append-only.
// Structural clone of ChainOfCustodyPanel.tsx. No edit/delete/confirm/destructive
// control of any kind — this is a locked SLA-02 constraint.
export const EscalationHistoryPanel: React.FC<EscalationHistoryPanelProps> = ({ taskId }) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [entries, setEntries] = useState<EscalationEntry[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [fetched, setFetched] = useState(false);

    const handleToggle = async () => {
        if (!isExpanded && !fetched) {
            setLoading(true);
            setError(null);
            try {
                const data = await api.fetchRemediationEscalations(taskId);
                setEntries(data.entries ?? []);
                setFetched(true);
            } catch {
                setError('Failed to load escalation history. Retry by collapsing and expanding this panel.');
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
                aria-label={isExpanded ? 'Collapse escalation history panel' : 'Expand escalation history panel'}
            >
                <span className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-1.5">
                    <HistoryIcon size={14} />
                    Escalation History
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
                            {error}
                        </p>
                    )}
                    {!loading && !error && entries.length === 0 && (
                        <p className="px-4 py-6 text-center text-xs text-gray-400 italic">
                            No escalations recorded for this task.
                        </p>
                    )}
                    {!loading && !error && entries.map((entry, idx) => (
                        <div key={`esc-${idx}-${entry.created_at}`} className="px-4 py-3">
                            <div className="flex items-start gap-2">
                                <div className="flex-shrink-0 mt-0.5">
                                    <AlertTriangleIcon size={14} className="text-yellow-600 dark:text-yellow-400" />
                                </div>
                                <div className="min-w-0">
                                    <p className="text-xs font-semibold text-gray-800 dark:text-gray-200">
                                        Tier {entry.escalation_level} escalation
                                    </p>
                                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                                        {formatEscalationTimestamp(entry.created_at)} UTC &middot; Notified: {summarizeNotified(entry.notified)}
                                    </p>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};
