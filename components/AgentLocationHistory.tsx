import React, { useState, useMemo } from 'react';
import { HistoryIcon, ChevronDownIcon, GlobeIcon, WifiIcon } from './icons';
import * as api from '../services/apiService';
import { LocationHistoryEntry } from '../services/apiService';
import { flagEmoji, formatGeo } from '../utils/geo';

interface AgentLocationHistoryProps {
    agentId: string;
}

function formatLocationTimestamp(ts: string): string {
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

// Human-readable, largest-two-units-only dwell format, computed client-side
// at render time — never trusted from a stored/backend-supplied field
// (46-UI-SPEC.md Behavior Contract; the backend's own `dwell_seconds` is
// deliberately ignored, see services/apiService.ts LocationHistoryEntry).
function formatDwell(ms: number): string {
    const minutes = Math.floor(ms / 60000);
    if (minutes < 1) return 'just arrived';
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ${minutes % 60}m`;
    const days = Math.floor(hours / 24);
    return `${days}d ${hours % 24}h`;
}

// Location History panel (GAUD-02) — lazy-expand-on-toggle, read-only, append-only.
// Structural clone of EscalationHistoryPanel.tsx. No edit/delete/confirm/destructive
// control of any kind — this is a locked D-10 constraint.
export const AgentLocationHistory: React.FC<AgentLocationHistoryProps> = ({ agentId }) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [entries, setEntries] = useState<LocationHistoryEntry[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [fetched, setFetched] = useState(false);

    const handleToggle = async () => {
        if (!isExpanded && !fetched) {
            setLoading(true);
            setError(null);
            try {
                const data = await api.fetchAgentLocationHistory(agentId);
                setEntries(data.entries ?? []);
                setFetched(true);
            } catch {
                setError('Failed to load location history. Retry by collapsing and expanding this panel.');
            } finally {
                setLoading(false);
            }
        }
        setIsExpanded(prev => !prev);
    };

    // Oldest first — matches EscalationHistoryPanel's ascending convention.
    // Dwell for row i = timestamp(i+1) - timestamp(i); last row (most recent,
    // current location) = now - timestamp(last), suffixed " (ongoing)".
    const sortedEntries = useMemo(
        () => [...entries].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()),
        [entries]
    );

    return (
        <div>
            <div
                className="flex items-center justify-between px-4 py-2 bg-gray-100 dark:bg-gray-700/50 rounded-t-md border border-gray-200 dark:border-gray-700 cursor-pointer"
                onClick={handleToggle}
                role="button"
                tabIndex={0}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') handleToggle(); }}
                aria-label={isExpanded ? 'Collapse location history panel' : 'Expand location history panel'}
            >
                <span className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-1.5">
                    <HistoryIcon size={14} />
                    Location History
                    <span className="text-xs font-normal text-gray-400">({entries.length} locations)</span>
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
                    {!loading && !error && sortedEntries.length === 0 && (
                        <p className="px-4 py-6 text-center text-xs text-gray-400 italic">
                            No location changes recorded for this agent.
                        </p>
                    )}
                    {!loading && !error && sortedEntries.map((entry, idx) => {
                        const isLast = idx === sortedEntries.length - 1;
                        const startMs = new Date(entry.timestamp).getTime();
                        const endMs = isLast ? Date.now() : new Date(sortedEntries[idx + 1].timestamp).getTime();
                        const dwellLabel = `${formatDwell(endMs - startMs)}${isLast ? ' (ongoing)' : ''}`;

                        return (
                            <div key={`loc-${idx}-${entry.timestamp}`} className="px-4 py-3">
                                <div className="flex items-start gap-2">
                                    <div className="flex-shrink-0 mt-0.5">
                                        <GlobeIcon size={14} className="text-primary-500 dark:text-primary-400" />
                                    </div>
                                    <div className="min-w-0">
                                        <p className="text-xs font-semibold text-gray-800 dark:text-gray-200 flex items-center flex-wrap">
                                            {entry.geo?.country_code && <span aria-hidden>{flagEmoji(entry.geo.country_code)}</span>}
                                            <span className="ml-1">{formatGeo(entry.geo)}</span>
                                            {entry.vpn_heuristic === true && (
                                                <span className="ml-2 inline-flex items-center gap-1 bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300 text-[11px] font-semibold px-2 py-1 rounded-full uppercase tracking-wide">
                                                    <WifiIcon size={10} />
                                                    likely VPN/hosting
                                                </span>
                                            )}
                                        </p>
                                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                                            <span className="font-mono">{entry.publicIp}</span>
                                            {' '}&middot;{' '}
                                            {formatLocationTimestamp(entry.timestamp)} UTC
                                            {' '}&middot;{' '}
                                            {dwellLabel}
                                        </p>
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
