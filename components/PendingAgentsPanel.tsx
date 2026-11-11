import React, { useCallback, useEffect, useRef, useState } from 'react';
import { API_BASE, authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';
import { PendingMovedAgents } from './PendingMovedAgents';

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
    /** Sent to platform readers only (D-36): the other organization this computer is live in. */
    crossTenant?: { agentId: string; tenantId: string; tenantName?: string; hostname?: string };
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
    trial_ended: 'Free trial ended',
    cross_tenant_duplicate: 'This computer is enrolled in another organization; waiting for platform approval',
};

const NEW_NETWORK = 'new_network';
const CROSS_TENANT = 'cross_tenant_duplicate';

const reasonText = (agent: PendingAgent) => {
    const reason = agent.pendingReason;
    if (reason === NEW_NETWORK) return `New network ${agent.sourceIp ?? 'unknown address'}, waiting for platform approval`;
    if (reason?.startsWith('sublimit:os:')) return `OS sub-limit full (${reason.slice('sublimit:os:'.length).replace('_', ' ')})`;
    if (reason?.startsWith('sublimit:group:')) return `Agent group sub-limit full (${reason.slice('sublimit:group:'.length)})`;
    return REASONS[reason || ''] || reason;
};

/** The warning shown before a bulk approval that would move computers or allow networks (D-37, D-42). */
const bulkConfirmText = (agents: PendingAgent[]) => {
    const moves = agents.filter(a => a.pendingReason === CROSS_TENANT).length;
    const networks = agents.filter(a => a.pendingReason === NEW_NETWORK).length;
    if (!moves && !networks) return '';
    const parts = [`Approve ${agents.length} computer${agents.length === 1 ? '' : 's'}?`];
    if (moves) parts.push(`${moves} ${moves === 1 ? 'is' : 'are'} enrolled in another organization: approving moves each one and retires its agent there.`);
    if (networks) parts.push(`${networks} ${networks === 1 ? 'waits' : 'wait'} for a new network: approving allows each one's address exactly.`);
    return parts.join(' ');
};

const errorOf = async (res: Response): Promise<{ message: string; license?: SeatLicense }> => {
    const body = await res.json().catch(() => ({}));
    return { message: body.error || body.detail || `HTTP ${res.status}`, license: body.license };
};

const when = (iso?: string) => (iso ? new Date(iso).toLocaleString() : '—');

/**
 * Agents waiting for approval (spec C3; Phase 88). An install past a seat limit, from a new
 * network, from a computer enrolled in another organization or after a trial ended is held here
 * instead of being refused: platform deciders approve it (it takes a seat, optionally raising the
 * limit; a new network is allowed, optionally as a bounded range; a cross-tenant move needs
 * confirmation) or reject it. Tenant users see their own tenant's list read-only and never
 * another organization's name (D-36).
 * Renders nothing while no agent is waiting or rejected.
 */
export const PendingAgentsPanel: React.FC<{ tenantId?: string | null }> = ({ tenantId }) => {
    const [data, setData] = useState<PendingList | null>(null);
    const [busy, setBusy] = useState(false);
    const [selected, setSelected] = useState<Set<string>>(new Set());
    // Approval refused for lack of a seat: offer to raise the limit for this agent.
    // The typed range is kept so the retry sends the same widenTo.
    const [needsSeat, setNeedsSeat] = useState<{ agentId: string; license?: SeatLicense; widenTo?: string } | null>(null);
    // Per-row range text and the 422 answer shown under it.
    const [ranges, setRanges] = useState<Record<string, string>>({});
    const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
    const headingRef = useRef<HTMLHeadingElement>(null);
    // Moves with every reload so the moved-agents list refetches alongside (S7).
    const [refreshKey, setRefreshKey] = useState(0);

    const load = useCallback(async () => {
        const qs = tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
        try {
            const res = await authFetch(`${API_BASE}/agents/pending${qs}`, { method: 'GET' });
            if (!res.ok) throw new Error((await errorOf(res)).message);
            setData(await res.json());
            setRefreshKey(k => k + 1);
        } catch (e) {
            console.warn('Pending agents unavailable:', e);
        }
    }, [tenantId]);

    useEffect(() => {
        load();
        const timer = window.setInterval(load, 60_000);
        return () => window.clearInterval(timer);
    }, [load]);

    const setRowError = (agentId: string, message?: string) => setRowErrors(prev => {
        const next = { ...prev };
        if (message) next[agentId] = message; else delete next[agentId];
        return next;
    });

    const approve = async (agentId: string, raiseLimitBy = 0, widenTo?: string) => {
        const agent = data?.agents.find(a => a.id === agentId);
        const range = widenTo?.trim();
        setBusy(true);
        setRowError(agentId);
        try {
            const res = await authFetch(`${API_BASE}/agents/pending/${agentId}/approve`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(range ? { raiseLimitBy, widenTo: range } : { raiseLimitBy }),
            });
            if (res.status === 409) {
                const err = await errorOf(res);
                if (err.message.startsWith('no_free_seat')) {
                    setNeedsSeat({ agentId, license: err.license, widenTo: range });
                    return;
                }
                if (err.message.startsWith('reason_changed')) {
                    showToast('The reason for this hold changed: this computer is now enrolled in another organization. Review it again.', 'warning');
                    setNeedsSeat(null);
                    setRanges(prev => { const next = { ...prev }; delete next[agentId]; return next; });
                    await load();
                    return;
                }
                throw new Error(err.message);
            }
            if (res.status === 422) {
                setRowError(agentId, `Couldn't allow this network: ${(await errorOf(res)).message}. Try again.`);
                return;
            }
            if (!res.ok) throw new Error((await errorOf(res)).message);
            const out = await res.json().catch(() => ({}));
            setNeedsSeat(null);
            showToast(approvedText(agent, out, data?.tenants[agent?.tenantId || '']?.name), 'success');
            headingRef.current?.focus();
            await load();
        } catch (e) {
            showToast(`Approve failed: ${(e as Error).message}`, 'error');
        } finally {
            setBusy(false);
        }
    };

    // A cross-tenant move is confirmed first (D-37); the confirm names the other organization to platform deciders only.
    const approveMove = (agent: PendingAgent) => {
        const thisOrg = data?.tenants[agent.tenantId]?.name || 'this organization';
        const other = agent.crossTenant?.tenantName || 'the other organization';
        if (!window.confirm(`Approve moves this computer to ${thisOrg}. Its agent in ${other} is retired and that seat is freed.`)) return;
        approve(agent.id);
    };

    const reject = async (agent: PendingAgent) => {
        const notBlocked = agent.pendingReason === CROSS_TENANT || agent.pendingReason === 'duplicate_hardware_id';
        const warning = notBlocked
            ? `Reject ${agent.hostname}? It stays out of this organization. The computer is not added to the blocked list.`
            : `Reject ${agent.hostname}? This machine will not be able to enroll in this tenant again unless you approve it later.`;
        if (!window.confirm(warning)) return;
        setBusy(true);
        try {
            const res = await authFetch(`${API_BASE}/agents/pending/${agent.id}/reject`, { method: 'POST' });
            if (!res.ok) throw new Error((await errorOf(res)).message);
            showToast(`${agent.hostname} rejected`, 'success');
            headingRef.current?.focus();
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
        if (action === 'approve') {
            const warning = bulkConfirmText((data?.agents || []).filter(a => selected.has(a.id)));
            if (warning && !window.confirm(warning)) return;
        }
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

    if (!data) return null;
    // An approved move leaves nothing waiting but a retired agent to restore: deciders keep the moved list.
    if (data.agents.length === 0) return data.canDecide ? <PendingMovedAgents refreshKey={refreshKey} /> : null;
    const pendingCount = data.agents.filter(a => a.status === 'Pending').length;
    const toggle = (id: string) => setSelected(prev => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id); else next.add(id);
        return next;
    });
    const btn = 'px-2 py-1 text-xs rounded-md disabled:opacity-50';

    return (
        <>
        <div className="rounded-2xl p-5 bg-amber-500/[0.06] ring-1 ring-inset ring-amber-500/25"
             data-testid="pending-agents-panel">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <h3 ref={headingRef} tabIndex={-1} className="text-sm font-bold text-gray-800 dark:text-white">
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
                    ? 'These computers were held by a license rule and wait for your decision. They hold no seat and send no data meanwhile.'
                    : 'These computers are waiting for approval. Contact your provider if one of them should be let in.'}
            </p>
            {needsSeat && (
                <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-amber-800 dark:text-amber-200" role="alert">
                    No free seat{needsSeat.license ? ` (${needsSeat.license.seatsUsed}/${needsSeat.license.maxAgents} in use)` : ''}.
                    <button type="button" disabled={busy} onClick={() => approve(needsSeat.agentId, 1, needsSeat.widenTo)}
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
                                            : reasonText(agent)}
                                        {agent.status === 'Pending' && agent.pendingReason === CROSS_TENANT && data.canDecide && agent.crossTenant && (
                                            <div className="text-gray-500">
                                                Live in {agent.crossTenant.tenantName || 'another organization'}
                                                {agent.crossTenant.hostname ? ` as ${agent.crossTenant.hostname}` : ''}
                                            </div>
                                        )}
                                        {agent.status === 'Pending' && agent.pendingReason === NEW_NETWORK && data.canDecide && (
                                            <div className="mt-1">
                                                <label htmlFor={`range-${agent.id}`} className="block font-semibold text-gray-600 dark:text-gray-300">Range (optional)</label>
                                                <input id={`range-${agent.id}`} type="text" value={ranges[agent.id] ?? ''} disabled={busy || !agent.sourceIp}
                                                       onChange={e => setRanges(prev => ({ ...prev, [agent.id]: e.target.value }))}
                                                       placeholder="e.g. 198.51.100.0/24" aria-describedby={`range-help-${agent.id}`}
                                                       className="mt-1 block w-56 min-h-8 px-2 font-mono text-xs rounded-md border border-gray-400 bg-white dark:bg-gray-800 dark:text-white disabled:opacity-50" />
                                                <div id={`range-help-${agent.id}`} className="mt-1 text-gray-500">
                                                    {agent.sourceIp
                                                        ? <>Leave empty to allow only <span className="font-mono break-all">{agent.sourceIp}</span>. A range must contain it and be at most a /24 (IPv6: /48).</>
                                                        : 'No address was observed, so no network can be allowed.'}
                                                </div>
                                            </div>
                                        )}
                                        {rowErrors[agent.id] && (
                                            <div role="alert" className="mt-1 text-red-600 dark:text-red-400">{rowErrors[agent.id]}</div>
                                        )}
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
                                            {agent.status === 'Pending' && agent.pendingReason === NEW_NETWORK ? (
                                                <button type="button" disabled={busy || !agent.sourceIp} aria-label={`Allow network for ${agent.hostname}`}
                                                        onClick={() => approve(agent.id, 0, ranges[agent.id])}
                                                        className={`${btn} min-h-8 bg-green-700 text-white mr-1`}>Allow network</button>
                                            ) : agent.status === 'Pending' && agent.pendingReason === CROSS_TENANT ? (
                                                <button type="button" disabled={busy} aria-label={`Approve move of ${agent.hostname}`}
                                                        onClick={() => approveMove(agent)}
                                                        className={`${btn} min-h-8 bg-green-700 text-white mr-1`}>Approve move</button>
                                            ) : (
                                                <button type="button" disabled={busy} onClick={() => approve(agent.id)}
                                                        className={`${btn} bg-green-600 text-white mr-1`}>Approve</button>
                                            )}
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
        {data.canDecide && <PendingMovedAgents refreshKey={refreshKey} />}
        </>
    );
};

/** The success toast: the plain legacy text, or what a network allowance or a move did (UI-SPEC S6). */
const approvedText = (agent: PendingAgent | undefined, out: { networkAllowed?: boolean; network?: string }, thisOrg?: string) => {
    if (out.network && out.networkAllowed === true) return `Approved. ${out.network} is now an allowed network.`;
    if (out.network && out.networkAllowed === false) {
        return `Approved. ${out.network} was not added: it is already allowed, or the list of allowed networks is full.`;
    }
    if (agent?.pendingReason === CROSS_TENANT && agent.crossTenant) {
        return `Approved. ${agent.hostname} moved to ${thisOrg || 'this organization'}; its agent in ${agent.crossTenant.tenantName || 'the other organization'} was retired.`;
    }
    return 'Agent approved; it connects at its next check-in';
};
