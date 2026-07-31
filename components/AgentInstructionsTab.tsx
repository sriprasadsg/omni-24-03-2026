import React, { useEffect, useState } from 'react';
import { Agent } from '../types';
import { RefreshCwIcon, AlertCircleIcon } from './icons';
import { authFetch } from '../services/apiService';

interface InstructionEntry {
    id: string;
    instruction: string;
    status: string;
    created_at?: string;
    created_by?: string;
    sent_at?: string;
    updated_at?: string;
    error?: string | null;
    message?: string | null;
}

const statusClasses: Record<string, string> = {
    pending: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
    sent: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
    delivered: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
    SUCCESS: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
    FAILURE: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
};

function formatTs(ts?: string): string {
    if (!ts) return '—';
    const d = new Date(ts);
    return isNaN(d.getTime()) ? ts : d.toLocaleString();
}

export const AgentInstructionsTab: React.FC<{ agent: Agent }> = ({ agent }) => {
    const [entries, setEntries] = useState<InstructionEntry[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [refreshTick, setRefreshTick] = useState(0);

    useEffect(() => {
        let cancelled = false;
        setIsLoading(true);
        setError(null);
        authFetch(`/api/agents/${agent.id}/instructions/history`)
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(data => {
                if (!cancelled) setEntries(Array.isArray(data) ? data : []);
            })
            .catch(e => {
                if (!cancelled) setError(e.message || 'Failed to load instruction history');
            })
            .finally(() => {
                if (!cancelled) setIsLoading(false);
            });
        return () => { cancelled = true; };
    }, [agent.id, refreshTick]);

    return (
        <div>
            <div className="flex justify-between items-center mb-3">
                <div>
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Instruction History</h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                        Commands queued for this agent — updates, scans, software installs — and who requested them.
                    </p>
                </div>
                <button
                    onClick={() => setRefreshTick(t => t + 1)}
                    disabled={isLoading}
                    title="Refresh"
                    className="p-1.5 rounded text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-40 focus:outline-none"
                >
                    <RefreshCwIcon size={14} className={isLoading ? 'animate-spin' : ''} />
                </button>
            </div>

            {error ? (
                <div className="flex items-center text-sm text-red-600 dark:text-red-400 py-4">
                    <AlertCircleIcon size={16} className="mr-2" />
                    {error}
                </div>
            ) : isLoading ? (
                <p className="text-sm text-gray-500 dark:text-gray-400 py-4">Loading…</p>
            ) : entries.length === 0 ? (
                <p className="text-sm text-gray-500 dark:text-gray-400 py-4">No instructions have been sent to this agent.</p>
            ) : (
                <div className="overflow-x-auto border border-gray-200 dark:border-gray-700 rounded-md">
                    <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
                        <thead className="bg-gray-50 dark:bg-gray-700/50">
                            <tr>
                                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Instruction</th>
                                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Status</th>
                                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Requested By</th>
                                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Created</th>
                                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Result</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                            {entries.map(e => (
                                <tr key={e.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                                    <td className="px-3 py-2 font-mono text-xs text-gray-900 dark:text-gray-200 max-w-[16rem] truncate" title={e.instruction}>
                                        {e.instruction || '—'}
                                    </td>
                                    <td className="px-3 py-2">
                                        <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${statusClasses[e.status] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'}`}>
                                            {e.status}
                                        </span>
                                    </td>
                                    <td className="px-3 py-2 text-gray-700 dark:text-gray-300">{e.created_by || '—'}</td>
                                    <td className="px-3 py-2 text-gray-500 dark:text-gray-400 whitespace-nowrap">{formatTs(e.created_at)}</td>
                                    <td className="px-3 py-2 text-gray-500 dark:text-gray-400 max-w-[20rem]">
                                        {e.error
                                            ? <span className="text-red-600 dark:text-red-400" title={e.error}>{e.error.length > 120 ? e.error.slice(0, 120) + '…' : e.error}</span>
                                            : (e.message ? (e.message.length > 120 ? e.message.slice(0, 120) + '…' : e.message) : '—')}
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
