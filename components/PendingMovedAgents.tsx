import React, { useCallback, useEffect, useRef, useState } from 'react';
import { API_BASE, authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

interface MovedAgent {
    id: string;
    tenantId: string;
    tenantName?: string | null;
    hostname?: string | null;
    replacedReason?: string;
    movedAt?: string | null;
}

const dateOf = (iso?: string | null) => {
    const d = iso ? new Date(iso) : null;
    return d && !Number.isNaN(d.getTime())
        ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
        : '—';
};

const messageOf = async (res: Response) => {
    const body = await res.json().catch(() => ({}));
    return body.error || body.detail || `HTTP ${res.status}`;
};

/**
 * Agents retired because their computer enrolled in another organization (D-37, D-38, D-43), for
 * platform deciders only. The server answers 403 to everyone else, which renders nothing, as do an
 * empty list and any load failure (the host panel's next poll retries). `refreshKey` moves whenever
 * the host panel reloads, so an approved move appears without a remount.
 */
export const PendingMovedAgents: React.FC<{ refreshKey?: number }> = ({ refreshKey = 0 }) => {
    const [rows, setRows] = useState<MovedAgent[] | null>(null);
    const [busyId, setBusyId] = useState<string | null>(null);
    const headingRef = useRef<HTMLHeadingElement>(null);

    const load = useCallback(async () => {
        try {
            const res = await authFetch(`${API_BASE}/agents/pending/moved`, { method: 'GET' });
            if (!res.ok) { setRows(null); return; }
            const body = await res.json();
            setRows(Array.isArray(body.agents) ? body.agents : null);
        } catch {
            setRows(null);
        }
    }, []);

    useEffect(() => { load(); }, [load, refreshKey]);

    const restore = async (row: MovedAgent) => {
        const name = row.hostname || 'Agent';
        const org = row.tenantName || 'another organization';
        if (!window.confirm(`Restore ${name} in ${org}? It takes a seat again at its next check-in, unless the computer is live in another organization.`)) return;
        setBusyId(row.id);
        try {
            const res = await authFetch(`${API_BASE}/agents/pending/${row.id}/restore`, { method: 'POST' });
            if (!res.ok) throw new Error(await messageOf(res));
            setRows(prev => (prev || []).filter(r => r.id !== row.id));
            showToast(`${name} restored. It takes a seat again at its next check-in.`, 'success');
            headingRef.current?.focus();
        } catch (e) {
            showToast(`Restore failed: ${(e as Error).message}`, 'error');
            await load();
        } finally {
            setBusyId(null);
        }
    };

    if (!rows || rows.length === 0) return null;

    return (
        <div className="card p-4 mt-4" data-testid="pending-moved-agents">
            <h3 ref={headingRef} tabIndex={-1} className="text-sm font-semibold text-gray-800 dark:text-white">
                Agents retired by a move ({rows.length})
            </h3>
            <p className="mt-1 mb-2 text-xs text-gray-600 dark:text-gray-300">
                These agents were retired because their computer enrolled in another organization. Restoring one brings it back as Inactive.
            </p>
            <ul className={`divide-y divide-gray-200 dark:divide-gray-700 ${rows.length > 8 ? 'max-h-72 overflow-y-auto' : ''}`}>
                {rows.map(row => {
                    const name = row.hostname || 'Agent';
                    const org = row.tenantName || 'another organization';
                    const how = row.replacedReason === 'moved_silent' ? 'silent copy' : 'approved move';
                    return (
                        <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm text-gray-700 dark:text-gray-200">
                            <span className="break-words min-w-0">{`${name} in ${org}, moved ${dateOf(row.movedAt)} (${how})`}</span>
                            <button type="button" disabled={busyId === row.id} aria-label={`Restore ${name} in ${org}`}
                                    onClick={() => restore(row)}
                                    className="min-h-8 px-2 text-sm font-semibold rounded-md border border-gray-400 text-gray-700 dark:text-gray-200 disabled:opacity-50">
                                Restore
                            </button>
                        </li>
                    );
                })}
            </ul>
        </div>
    );
};
