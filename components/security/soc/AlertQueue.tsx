import React, { useEffect, useRef, useState } from 'react';
import { Check, ChevronLeft, ChevronRight, Inbox, Search, X } from 'lucide-react';
import { authFetch } from '../../../services/apiService';
import { showToast } from '../../../utils/toast';
import { EmptyNote, ghostButton } from '../../network/NetworkKit';
import {
    bulkAct, endpointName, fetchSocAlerts, formatSince, formatWhen, RESOLUTION_LABEL, SEVERITIES, SEVERITY_META,
    type AlertPage, type QueueStatus, type Resolution, type Severity, type SocAlert,
} from './socData';
import { SeverityBadge, StatusText, field, segment, segmented } from './SocKit';
import type { QueueFocus } from './SocPanels';

const PAGE = 50;
const STATUSES: { key: QueueStatus; label: string }[] = [
    { key: 'active', label: 'Active' }, { key: 'open', label: 'Open' }, { key: 'acknowledged', label: 'Acknowledged' },
    { key: 'closed', label: 'Closed' }, { key: 'all', label: 'All' },
];
const CLOSE_AS: Resolution[] = ['resolved', 'false_positive', 'benign'];

interface Props {
    focus: QueueFocus | null;
    onClearFocus: () => void;
    types: { type: string; label: string }[];
    reloadKey: number;
    onOpen: (alert: SocAlert) => void;
    onChanged: () => void;
}

export const AlertQueue: React.FC<Props> = ({ focus, onClearFocus, types, reloadKey, onOpen, onChanged }) => {
    const [status, setStatus] = useState<QueueStatus>('active');
    const [severity, setSeverity] = useState<Severity | ''>('');
    const [type, setType] = useState('');
    const [query, setQuery] = useState('');
    const [search, setSearch] = useState('');
    const [offset, setOffset] = useState(0);
    const [page, setPage] = useState<AlertPage | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [closeAs, setCloseAs] = useState<Resolution>('resolved');
    const [sort, setSort] = useState<'severity' | 'risk'>('severity');
    const [busy, setBusy] = useState(false);
    const seq = useRef(0);

    // A panel on the overview ("show these alerts") sets the type or endpoint.
    useEffect(() => { setType(focus?.type ?? ''); setOffset(0); }, [focus]);
    useEffect(() => { const id = setTimeout(() => { setSearch(query); setOffset(0); }, 300); return () => clearTimeout(id); }, [query]);

    useEffect(() => {
        const mine = ++seq.current;
        fetchSocAlerts(authFetch, { status, severity, type: type || undefined, agentId: focus?.agentId, q: search, limit: PAGE, offset, sort })
            .then(p => { if (mine === seq.current) { setPage(p); setError(null); } })
            .catch(e => { if (mine === seq.current) setError(e instanceof Error ? e.message : 'Alerts could not be loaded'); });
    }, [status, severity, type, focus, search, offset, reloadKey, sort]);

    // A selection never outlives the rows it was made on.
    useEffect(() => { setSelected(new Set()); }, [status, severity, type, focus, search, offset]);

    const items = page?.items ?? [];
    const allSelected = items.length > 0 && items.every(a => selected.has(a.id));
    const toggle = (id: string) => setSelected(prev => { const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next; });

    const runBulk = async (action: 'acknowledge' | 'close') => {
        const ids = Array.from(selected);
        setBusy(true);
        try {
            const res = await bulkAct(authFetch, ids, action, action === 'close' ? closeAs : undefined);
            const done = action === 'close' ? `closed as ${RESOLUTION_LABEL[closeAs].toLowerCase()}` : 'acknowledged';
            const skipped = ids.length - res.modified;
            showToast(`${res.modified} alert${res.modified === 1 ? '' : 's'} ${done}${skipped ? `; ${skipped} already were` : ''}`, 'success');
            setSelected(new Set());
            onChanged();
        } catch (e) {
            showToast(e instanceof Error ? e.message : 'The alerts were not changed', 'error');
        } finally {
            setBusy(false);
        }
    };

    const total = page?.total ?? 0;
    const filtered = !!(severity || type || focus || search);
    return (
        <section aria-label="Alert queue" className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card min-w-0">
            <div className="p-4 flex flex-wrap items-center gap-2 border-b border-gray-200/70 dark:border-white/[0.07]">
                <div role="group" aria-label="Status" className={`${segmented} max-w-full overflow-x-auto`}>
                    {STATUSES.map(s => (
                        <button key={s.key} type="button" aria-pressed={status === s.key} onClick={() => { setStatus(s.key); setOffset(0); }} className={segment(status === s.key)}>{s.label}</button>
                    ))}
                </div>
                <label className="sr-only" htmlFor="soc-severity">Severity</label>
                <select id="soc-severity" value={severity} onChange={e => { setSeverity(e.target.value as Severity | ''); setOffset(0); }} className={`${field} px-3`}>
                    <option value="">All severities</option>
                    {SEVERITIES.map(s => <option key={s} value={s}>{SEVERITY_META[s].label}</option>)}
                </select>
                <label className="sr-only" htmlFor="soc-type">Detection type</label>
                <select id="soc-type" value={type} onChange={e => { setType(e.target.value); setOffset(0); }} className={`${field} px-3 max-w-[13rem]`}>
                    <option value="">All detection types</option>
                    {types.map(t => <option key={t.type || 'other'} value={t.type}>{t.label}</option>)}
                </select>
                <label className="sr-only" htmlFor="soc-sort">Sort by</label>
                <select id="soc-sort" value={sort} onChange={e => { setSort(e.target.value as 'severity' | 'risk'); setOffset(0); }} className={`${field} px-3`}>
                    <option value="severity">Sort: severity</option>
                    <option value="risk">Sort: risk</option>
                </select>
                <label className="relative block">
                    <span className="sr-only">Search alerts</span>
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" aria-hidden="true" />
                    <input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search title or details"
                        className={`${field} w-56 max-w-full pl-9 pr-3 placeholder:text-gray-400`} />
                </label>
                {focus?.agentId && (
                    <button type="button" onClick={onClearFocus} className={`${ghostButton} h-8`}>
                        Endpoint: {focus.label}<X className="w-3.5 h-3.5" aria-hidden="true" /><span className="sr-only">Clear endpoint filter</span>
                    </button>
                )}
            </div>

            {selected.size > 0 && (
                <div className="px-4 py-2.5 flex flex-wrap items-center gap-2 bg-primary-500/[0.06] border-b border-primary-500/20" role="region" aria-label="Selected alerts">
                    <span className="text-sm font-medium text-gray-900 dark:text-white">{selected.size} selected</span>
                    <button type="button" disabled={busy} onClick={() => runBulk('acknowledge')} className={`${ghostButton} h-8`}>
                        <Check className="w-3.5 h-3.5" aria-hidden="true" />Acknowledge
                    </button>
                    <span className="inline-flex items-center gap-1">
                        <label className="sr-only" htmlFor="soc-close-as">Close as</label>
                        <select id="soc-close-as" value={closeAs} onChange={e => setCloseAs(e.target.value as Resolution)} className={`${field} h-8 px-2`}>
                            {CLOSE_AS.map(r => <option key={r} value={r}>{RESOLUTION_LABEL[r]}</option>)}
                        </select>
                        <button type="button" disabled={busy} onClick={() => runBulk('close')} className={`${ghostButton} h-8`}>Close</button>
                    </span>
                    <button type="button" onClick={() => setSelected(new Set())} className="ml-auto text-xs text-gray-600 dark:text-gray-300 hover:underline">Clear selection</button>
                </div>
            )}

            {error && !page ? (
                <p role="alert" className="p-5 text-sm text-red-700 dark:text-red-300">{error}</p>
            ) : !page ? (
                <p className="p-5 text-sm text-gray-500 dark:text-gray-400" aria-busy="true">Loading alerts…</p>
            ) : items.length === 0 ? (
                <EmptyNote icon={<Inbox className="w-5 h-5" />} title={filtered ? 'No alert matches these filters' : status === 'active' ? 'No active alerts' : 'No alerts here'}>
                    {status === 'active' && !filtered ? 'Every alert has been closed.' : undefined}
                </EmptyNote>
            ) : (
                <div className="relative overflow-x-auto">
                    <table className="w-full min-w-[780px] text-sm">
                        <thead>
                            <tr className="text-left">
                                <th scope="col" className="w-10 px-4 py-2.5">
                                    <input type="checkbox" checked={allSelected} aria-label="Select all alerts on this page"
                                        onChange={() => setSelected(allSelected ? new Set() : new Set(items.map(a => a.id)))} className="h-4 w-4 rounded" />
                                </th>
                                <th scope="col" className="px-2 py-2.5">Severity</th>
                                <th scope="col" className="px-2 py-2.5">Risk</th>
                                <th scope="col" className="px-2 py-2.5">Alert</th>
                                <th scope="col" className="px-2 py-2.5">Endpoint</th>
                                <th scope="col" className="px-2 py-2.5">Last seen</th>
                                <th scope="col" className="px-4 py-2.5">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {items.map(a => (
                                <tr key={a.id} className="border-t border-gray-100 dark:border-white/[0.05] hover:bg-gray-50/80 dark:hover:bg-white/[0.02]">
                                    <td className="px-4 py-2.5 align-top">
                                        <input type="checkbox" checked={selected.has(a.id)} onChange={() => toggle(a.id)} aria-label={`Select ${a.title}`} className="h-4 w-4 rounded" />
                                    </td>
                                    <td className="px-2 py-2.5 align-top"><SeverityBadge severity={a.severity} /></td>
                                    <td className="px-2 py-2.5 align-top font-mono tabular-nums text-gray-900 dark:text-white" title="Risk 0-100">{a.risk ?? '—'}{a.threatIntel && a.threatIntel.length > 0 && <span className="ml-1 text-[11px] font-sans font-medium text-red-700 dark:text-red-300">intel</span>}</td>
                                    <td className="px-2 py-2.5 align-top max-w-[28rem]">
                                        <button type="button" onClick={() => onOpen(a)} className="block max-w-full text-left font-medium text-gray-900 dark:text-white hover:text-primary-700 dark:hover:text-primary-300 truncate">
                                            {a.title}
                                        </button>
                                        <span className="block text-xs text-gray-500 dark:text-gray-400">
                                            {a.typeLabel}
                                            {a.occurrences > 1 && <> · seen <span className="font-mono tabular-nums">{a.occurrences}</span> times</>}
                                            {a.mitre.length > 0 && <> · <span className="font-mono">{a.mitre.join(', ')}</span></>}
                                            {a.caseId && ' · in a case'}
                                        </span>
                                    </td>
                                    <td className="px-2 py-2.5 align-top text-gray-700 dark:text-gray-300 whitespace-nowrap">{endpointName(a)}</td>
                                    <td className="px-2 py-2.5 align-top text-gray-600 dark:text-gray-300 whitespace-nowrap" title={a.lastSeenAt ?? undefined}>{formatSince(a.lastSeenAt)}</td>
                                    <td className="px-4 py-2.5 align-top">
                                        <StatusText status={a.status} resolution={a.resolution} />
                                        {a.sla && (a.sla.ackBreached || a.sla.closeBreached
                                            ? <span className="block text-[11px] font-medium text-red-700 dark:text-red-300">Overdue to {a.sla.ackBreached ? 'acknowledge' : 'close'}</span>
                                            : <span className="block text-[11px] text-gray-500 dark:text-gray-400">{a.sla.ackDue ? `Acknowledge by ${formatWhen(a.sla.ackDue)}` : `Close by ${formatWhen(a.sla.closeDue)}`}</span>)}
                                        {a.assignee && <span className="block text-[11px] text-gray-500 dark:text-gray-400 truncate max-w-[10rem]">{a.assignee}</span>}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {page && total > 0 && (
                <div className="px-4 py-3 flex items-center justify-between gap-3 border-t border-gray-200/70 dark:border-white/[0.07] text-xs text-gray-600 dark:text-gray-300">
                    <span className="tabular-nums">{offset + 1}–{Math.min(offset + PAGE, total)} of {total}</span>
                    <span className="flex gap-2">
                        <button type="button" className={`${ghostButton} h-8 px-2`} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                            <ChevronLeft className="w-4 h-4" aria-hidden="true" />Previous
                        </button>
                        <button type="button" className={`${ghostButton} h-8 px-2`} disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
                            Next<ChevronRight className="w-4 h-4" aria-hidden="true" />
                        </button>
                    </span>
                </div>
            )}
        </section>
    );
};
