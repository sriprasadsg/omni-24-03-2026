import React, { useCallback, useEffect, useState } from 'react';
import { API_BASE, authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

interface HardwareInfo {
    serialNumber?: string | null;
    smbiosUuid?: string | null;
    macAddresses?: string[];
    osFamily?: string;
    osVersion?: string;
    deviceType?: string;
}

export interface PendingAgent {
    id: string;
    tenantId: string;
    hostname: string;
    status: 'Pending' | 'Rejected';
    pendingReason?: string;
    pendingSince?: string;
    rejectedAt?: string;
    lastSeen?: string;
    ipAddress?: string;
    publicIp?: string;
    sourceIp?: string;
    platform?: string;
    version?: string;
    loggedInUser?: string;
    hardware?: HardwareInfo;
}

interface SeatLicense {
    maxAgents: number;
    seatsUsed: number;
    seatsAvailable: number;
}

interface PendingList {
    agents: PendingAgent[];
    tenants: Record<string, { name?: string; license: SeatLicense }>;
    canDecide: boolean;
}

const REASONS: Record<string, string> = {
    seat_limit: 'License limit reached',
    duplicate_hardware_id: 'Machine already enrolled under another name',
    not_allowlisted: 'Not on the hardware allowlist',
    key_exhausted: 'Install key used up, expired or revoked',
    license_expired: 'License expired',
};

const reasonText = (reason?: string) => {
    if (reason?.startsWith('sublimit:os:')) return `OS sub-limit full (${reason.slice('sublimit:os:'.length).replace('_', ' ')})`;
    if (reason?.startsWith('sublimit:group:')) return `Agent group sub-limit full (${reason.slice('sublimit:group:'.length)})`;
    return REASONS[reason || ''] || reason;
};

const errorOf = async (res: Response): Promise<{ message: string; license?: SeatLicense }> => {
    const body = await res.json().catch(() => ({}));
    return { message: body.error || body.detail || `HTTP ${res.status}`, license: body.license };
};

const when = (iso?: string) => (iso ? new Date(iso).toLocaleString() : '—');

/**
 * Agents waiting for approval (spec C3). An install past a tenant's seat limit
 * is held here instead of being refused: super admins approve it (it takes a
 * seat, optionally raising the limit) or reject it (that machine cannot enroll
 * in the tenant again). Tenant users see their own tenant's list read-only.
 * Renders nothing while no agent is waiting or rejected.
 */
export const PendingAgentsPanel: React.FC<{ tenantId?: string | null }> = ({ tenantId }) => {
    const [data, setData] = useState<PendingList | null>(null);
    const [busy, setBusy] = useState(false);
    const [selected, setSelected] = useState<Set<string>>(new Set());
    // Approval refused for lack of a seat: offer to raise the limit for this agent.
    const [needsSeat, setNeedsSeat] = useState<{ agentId: string; license?: SeatLicense } | null>(null);

    const load = useCallback(async () => {
        const qs = tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
        try {
            const res = await authFetch(`${API_BASE}/agents/pending${qs}`, { method: 'GET' });
            if (!res.ok) throw new Error((await errorOf(res)).message);
            setData(await res.json());
        } catch (e) {
            console.warn('Pending agents unavailable:', e);
        }
    }, [tenantId]);

    useEffect(() => {
        load();
        const timer = window.setInterval(load, 60_000);
        return () => window.clearInterval(timer);
    }, [load]);

    const approve = async (agentId: string, raiseLimitBy = 0) => {
        setBusy(true);
        try {
            const res = await authFetch(`${API_BASE}/agents/pending/${agentId}/approve`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ raiseLimitBy }),
            });
            if (res.status === 409) {
                const err = await errorOf(res);
                if (err.message.startsWith('no_free_seat')) {
                    setNeedsSeat({ agentId, license: err.license });
                    return;
                }
                throw new Error(err.message);
            }
            if (!res.ok) throw new Error((await errorOf(res)).message);
            setNeedsSeat(null);
            showToast('Agent approved; it connects at its next check-in', 'success');
            await load();
        } catch (e) {
            showToast(`Approve failed: ${(e as Error).message}`, 'error');
        } finally {
            setBusy(false);
        }
    };

    const reject = async (agent: PendingAgent) => {
        if (!window.confirm(`Reject ${agent.hostname}? This machine will not be able to enroll in this tenant again unless you approve it later.`)) return;
        setBusy(true);
        try {
            const res = await authFetch(`${API_BASE}/agents/pending/${agent.id}/reject`, { method: 'POST' });
            if (!res.ok) throw new Error((await errorOf(res)).message);
            showToast(`${agent.hostname} rejected`, 'success');
            await load();
        } catch (e) {
            showToast(`Reject failed: ${(e as Error).message}`, 'error');
        } finally {
            setBusy(false);
        }
    };

    const bulk = async (action: 'approve' | 'reject', raiseLimit = false) => {
        const agentIds = [...selected];
        if (!agentIds.length) return;
        if (action === 'reject' && !window.confirm(`Reject ${agentIds.length} agent(s)? Their machines will not be able to enroll again.`)) return;
        setBusy(true);
        try {
            const res = await authFetch(`${API_BASE}/agents/pending/bulk`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action, agentIds, raiseLimit }),
            });
            if (!res.ok) throw new Error((await errorOf(res)).message);
            const out = await res.json();
            showToast(`${out.succeeded} ${action === 'approve' ? 'approved' : 'rejected'}${out.failed ? `, ${out.failed} failed` : ''}`,
                out.failed ? 'warning' : 'success');
            setSelected(new Set());
            await load();
        } catch (e) {
            showToast(`Bulk ${action} failed: ${(e as Error).message}`, 'error');
        } finally {
            setBusy(false);
        }
    };

    if (!data || data.agents.length === 0) return null;
    const pendingCount = data.agents.filter(a => a.status === 'Pending').length;
    const toggle = (id: string) => setSelected(prev => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id); else next.add(id);
        return next;
    });
    const btn = 'px-2 py-1 text-xs rounded-md disabled:opacity-50';

    return (
        <div className="rounded-2xl p-5 bg-amber-500/[0.06] ring-1 ring-inset ring-amber-500/25"
             data-testid="pending-agents-panel">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <h3 className="text-sm font-bold text-gray-800 dark:text-white">
                    Agents waiting for approval ({pendingCount})
                </h3>
                {data.canDecide && selected.size > 0 && (
                    <div className="flex gap-2">
                        <button type="button" disabled={busy} onClick={() => bulk('approve')}
                                className={`${btn} bg-green-600 text-white`}>Approve {selected.size}</button>
                        <button type="button" disabled={busy} onClick={() => bulk('approve', true)}
                                className={`${btn} bg-green-700 text-white`}>Approve {selected.size} and add seats</button>
                        <button type="button" disabled={busy} onClick={() => bulk('reject')}
                                className={`${btn} bg-red-600 text-white`}>Reject {selected.size}</button>
                    </div>
                )}
            </div>
            <p className="text-xs text-gray-600 dark:text-gray-300 mb-3">
                {data.canDecide
                    ? 'These installs went past a license limit and are held until you decide. They hold no seat and send no data meanwhile.'
                    : 'These computers are waiting for a free license seat. Contact your provider to add seats.'}
            </p>
            {needsSeat && (
                <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-amber-800 dark:text-amber-200" role="alert">
                    No free seat{needsSeat.license ? ` (${needsSeat.license.seatsUsed}/${needsSeat.license.maxAgents} in use)` : ''}.
                    <button type="button" disabled={busy} onClick={() => approve(needsSeat.agentId, 1)}
                            className={`${btn} bg-green-600 text-white`}>Approve and raise limit by 1</button>
                    <button type="button" onClick={() => setNeedsSeat(null)} className={`${btn} border border-gray-400`}>Cancel</button>
                </div>
            )}
            <div className="overflow-x-auto">
                <table className="min-w-full text-xs text-left text-gray-700 dark:text-gray-200">
                    <thead className="text-gray-500 dark:text-gray-400">
                        <tr>
                            {data.canDecide && <th className="py-1 pr-2" />}
                            <th className="py-1 pr-3">Computer</th>
                            {!tenantId && <th className="py-1 pr-3">Tenant</th>}
                            <th className="py-1 pr-3">Why</th>
                            <th className="py-1 pr-3">Identity</th>
                            <th className="py-1 pr-3">User / version</th>
                            <th className="py-1 pr-3">First / last seen</th>
                            {data.canDecide && <th className="py-1" />}
                        </tr>
                    </thead>
                    <tbody>
                        {data.agents.map(agent => {
                            const tenant = data.tenants[agent.tenantId];
                            const hw = agent.hardware || {};
                            return (
                                <tr key={agent.id} className="border-t border-amber-200 dark:border-amber-800 align-top">
                                    {data.canDecide && (
                                        <td className="py-1 pr-2">
                                            <input type="checkbox" aria-label={`Select ${agent.hostname}`}
                                                   checked={selected.has(agent.id)} onChange={() => toggle(agent.id)} />
                                        </td>
                                    )}
                                    <td className="py-1 pr-3">
                                        <div className="font-medium">{agent.hostname}</div>
                                        <div className="text-gray-500">{agent.ipAddress}{agent.sourceIp && agent.sourceIp !== agent.ipAddress ? ` via ${agent.sourceIp}` : ''}</div>
                                    </td>
                                    {!tenantId && (
                                        <td className="py-1 pr-3">
                                            {tenant?.name || agent.tenantId}
                                            {tenant && <div className="text-gray-500">{tenant.license.seatsUsed}/{tenant.license.maxAgents} seats</div>}
                                        </td>
                                    )}
                                    <td className="py-1 pr-3">
                                        {agent.status === 'Rejected'
                                            ? <span className="text-red-600 dark:text-red-400">Rejected {when(agent.rejectedAt)}</span>
                                            : reasonText(agent.pendingReason)}
                                    </td>
                                    <td className="py-1 pr-3 font-mono">
                                        {hw.serialNumber && <div>S/N {hw.serialNumber}</div>}
                                        {hw.smbiosUuid && <div title="SMBIOS UUID">{hw.smbiosUuid}</div>}
                                        {(hw.macAddresses || []).slice(0, 2).map(mac => <div key={mac}>{mac}</div>)}
                                        {!hw.serialNumber && !hw.smbiosUuid && !(hw.macAddresses || []).length && <span className="text-gray-500">not reported</span>}
                                    </td>
                                    <td className="py-1 pr-3">
                                        <div>{agent.loggedInUser || '—'}</div>
                                        <div className="text-gray-500">{[hw.osFamily || agent.platform, hw.osVersion].filter(Boolean).join(' ')} · v{agent.version}</div>
                                    </td>
                                    <td className="py-1 pr-3">
                                        <div>{when(agent.pendingSince)}</div>
                                        <div className="text-gray-500">{when(agent.lastSeen)}</div>
                                    </td>
                                    {data.canDecide && (
                                        <td className="py-1 whitespace-nowrap">
                                            <button type="button" disabled={busy} onClick={() => approve(agent.id)}
                                                    className={`${btn} bg-green-600 text-white mr-1`}>Approve</button>
                                            {agent.status === 'Pending' && (
                                                <button type="button" disabled={busy} onClick={() => reject(agent)}
                                                        className={`${btn} bg-red-600 text-white`}>Reject</button>
                                            )}
                                        </td>
                                    )}
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
};
