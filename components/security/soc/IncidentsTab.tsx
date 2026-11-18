import React, { useEffect, useRef, useState } from 'react';
import { Briefcase, Check, ChevronRight, Layers, RotateCcw, UserMinus, UserPlus, X } from 'lucide-react';
import { authFetch } from '../../../services/apiService';
import { showToast } from '../../../utils/toast';
import { EmptyNote, ghostButton } from '../../network/NetworkKit';
import {
    actOnIncident, caseFromIncident, triageIncident, endpointName, fetchIncident, fetchIncidents, formatSince, formatWhen, RESOLUTION_LABEL,
    type IncidentDetail, type IncidentPage, type QueueStatus, type Resolution, type SocAlert, type SocIncident,
} from './socData';
import { SeverityBadge, SeverityIcon, StatusText, field, primaryButton, segment, segmented, subhead } from './SocKit';
import { TriagePanel } from './TriagePanel';

const STATUSES: { key: QueueStatus; label: string }[] = [{ key: 'active', label: 'Active' }, { key: 'closed', label: 'Closed' }, { key: 'all', label: 'All' }];
const CLOSE_AS: Resolution[] = ['resolved', 'false_positive', 'benign'];
const hostOf = (i: SocIncident) => i.hostname || endpointName({ hostname: null, agentId: i.agentId ?? null });

/** Attack stages in ATT&CK order, as a chain. */
const Stages: React.FC<{ tactics: string[] }> = ({ tactics }) => tactics.length ? (
    <ol className="flex flex-wrap items-center gap-1" aria-label="Attack stages in order">
        {tactics.map((t, i) => (
            <li key={t} className="flex items-center gap-1">
                {i > 0 && <ChevronRight className="w-3 h-3 text-gray-400" aria-hidden="true" />}
                <span className="rounded-md px-1.5 py-0.5 text-[11px] font-medium bg-gray-100 dark:bg-white/[0.06] text-gray-700 dark:text-gray-300">{t}</span>
            </li>
        ))}
    </ol>
) : <span className="text-xs text-gray-500 dark:text-gray-400">No MITRE technique named</span>;

const IncidentDrawer: React.FC<{ id: string; onClose: () => void; onOpenAlert: (a: SocAlert) => void; onCaseOpened: (c: Record<string, unknown>) => void; onChanged: () => void }> = ({ id, onClose, onOpenAlert, onCaseOpened, onChanged }) => {
    const [inc, setInc] = useState<IncidentDetail | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [closeAs, setCloseAs] = useState<Resolution>('resolved');
    const [note, setNote] = useState('');
    const [closeAlerts, setCloseAlerts] = useState(true);
    const closeRef = useRef<HTMLButtonElement>(null);
    const panelRef = useRef<HTMLDivElement>(null);

    // Escape closes; Tab stays inside the drawer while it is open.
    const onKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Escape') { e.stopPropagation(); onClose(); return; }
        if (e.key !== 'Tab' || !panelRef.current) return;
        const focusable = panelRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), [href], input, select, textarea');
        if (!focusable.length) return;
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };

    useEffect(() => {
        const returnTo = document.activeElement as HTMLElement | null;
        closeRef.current?.focus();
        return () => { returnTo?.focus?.(); };
    }, []);
    useEffect(() => {
        fetchIncident(authFetch, id).then(setInc).catch(e => setError(e instanceof Error ? e.message : 'The incident could not be loaded'));
    }, [id]);

    const run = async (work: () => Promise<IncidentDetail | null>, done: string) => {
        setBusy(true);
        try {
            const next = await work();
            if (next) setInc(next);
            showToast(done, 'success');
            onChanged();
        } catch (e) {
            showToast(e instanceof Error ? e.message : 'Nothing was changed', 'error');
        } finally {
            setBusy(false);
        }
    };
    const act = (action: 'acknowledge' | 'assign' | 'unassign' | 'close' | 'reopen', done: string, extra = {}) =>
        run(() => actOnIncident(authFetch, id, { action, ...extra }), done);

    const openAlerts = inc ? inc.timeline.filter(a => a.status !== 'closed').length : 0;
    const active = inc && inc.status !== 'closed';
    return (
        <div className="fixed inset-0 z-50" onKeyDown={onKeyDown}>
            <div className="absolute inset-0 bg-gray-950/40 backdrop-blur-[2px]" onClick={onClose} aria-hidden="true" />
            <div ref={panelRef} role="dialog" aria-modal="true" aria-labelledby="soc-incident-title"
                className="absolute inset-y-0 right-0 w-[min(34rem,100%)] flex flex-col bg-white dark:bg-gray-900 border-l border-gray-200/80 dark:border-white/10 shadow-2xl">
                <div className="flex items-start gap-3 px-5 py-4 border-b border-gray-200/70 dark:border-white/[0.07]">
                    <div className="min-w-0 flex-1">
                        <p className="flex items-center gap-2">{inc && <SeverityBadge severity={inc.severity} />}<span className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Incident</span></p>
                        <h2 id="soc-incident-title" className="mt-1.5 text-[17px] font-semibold text-gray-900 dark:text-white break-words">{inc ? inc.title : 'Incident'}</h2>
                        {inc && <p className="mt-1"><StatusText status={inc.status} resolution={inc.resolution} /></p>}
                    </div>
                    <button ref={closeRef} type="button" onClick={onClose} aria-label="Close incident details"
                        className="grid place-items-center h-8 w-8 rounded-lg text-gray-500 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/[0.06]">
                        <X className="w-4 h-4" aria-hidden="true" />
                    </button>
                </div>
                <div className="flex-1 overflow-y-auto px-5 py-5 space-y-6 custom-scrollbar">
                    {error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>}
                    {!inc && !error && <p className="text-sm text-gray-500 dark:text-gray-400">Loading…</p>}
                    {inc && (<>
                        <section>
                            <h3 className={subhead}>What happened</h3>
                            <dl className="mt-1 text-[13px] space-y-1.5">
                                <div className="flex gap-3"><dt className="w-32 shrink-0 text-xs text-gray-500 dark:text-gray-400">Endpoint</dt><dd className="text-gray-900 dark:text-white">{hostOf(inc)}</dd></div>
                                <div className="flex gap-3"><dt className="w-32 shrink-0 text-xs text-gray-500 dark:text-gray-400">Alerts</dt><dd className="text-gray-900 dark:text-white">{inc.alertCount}, from {formatWhen(inc.startedAt)} to {formatWhen(inc.lastAlertAt)}{inc.grouping ? ' · still collecting' : ''}</dd></div>
                                <div className="flex gap-3"><dt className="w-32 shrink-0 text-xs text-gray-500 dark:text-gray-400">Assigned to</dt><dd className="text-gray-900 dark:text-white">{inc.assignee || 'Nobody'}</dd></div>
                                {inc.closedAt && <div className="flex gap-3"><dt className="w-32 shrink-0 text-xs text-gray-500 dark:text-gray-400">Closed</dt><dd className="text-gray-900 dark:text-white">{formatWhen(inc.closedAt)}{inc.closedBy && ` by ${inc.closedBy}`}{inc.closeNote && <span className="block text-xs text-gray-600 dark:text-gray-300">{inc.closeNote}</span>}</dd></div>}
                                {inc.autonomyIncidentId && <div className="flex gap-3"><dt className="w-32 shrink-0 text-xs text-gray-500 dark:text-gray-400">Autonomous Ops</dt><dd className="text-gray-900 dark:text-white">Also tracked there ({inc.autonomyIncidentId})</dd></div>}
                            </dl>
                        </section>
                        <TriagePanel alertId={id} triage={inc.aiSummary} canRun askLabel="Summarise this incident"
                            runner={() => triageIncident(authFetch, id)} onTriaged={t => setInc({ ...inc, aiSummary: t })}
                            onStep={() => document.getElementById('soc-incident-handle')?.scrollIntoView?.({ block: 'center' })} />
                        <section>
                            <h3 className={subhead}>Attack stages</h3>
                            <div className="mt-2"><Stages tactics={inc.tactics} /></div>
                        </section>
                        <section>
                            <h3 className={subhead}>Timeline</h3>
                            <ol className="mt-2 border-l border-gray-200 dark:border-white/10 ml-1.5 space-y-2">
                                {inc.timeline.map(a => (
                                    <li key={a.id} className="pl-3 relative">
                                        <span className="absolute -left-[5px] top-2 h-2 w-2 rounded-full bg-gray-300 dark:bg-white/30" aria-hidden="true" />
                                        <button type="button" onClick={() => onOpenAlert(a)} className="text-left w-full rounded-lg px-1.5 py-1 hover:bg-gray-50 dark:hover:bg-white/[0.03]">
                                            <span className="flex items-center gap-1.5 text-[13px] font-medium text-gray-900 dark:text-white"><SeverityIcon severity={a.severity} />{a.title}</span>
                                            <span className="block text-[11px] text-gray-500 dark:text-gray-400">{formatWhen(a.createdAt)} · {a.typeLabel}{a.occurrences > 1 ? ` · seen ${a.occurrences} times` : ''} · <StatusText status={a.status} resolution={a.resolution} /></span>
                                        </button>
                                    </li>
                                ))}
                            </ol>
                        </section>
                        <section className="space-y-3">
                            <h3 id="soc-incident-handle" className={subhead}>Handle the incident</h3>
                            <div className="flex flex-wrap gap-2">
                                {inc.status === 'open' && <button type="button" className={primaryButton} disabled={busy} onClick={() => act('acknowledge', 'Incident acknowledged')}><Check className="w-4 h-4" aria-hidden="true" />Acknowledge</button>}
                                {active && (inc.assignee
                                    ? <button type="button" className={ghostButton} disabled={busy} onClick={() => act('unassign', 'Incident unassigned')}><UserMinus className="w-4 h-4" aria-hidden="true" />Unassign</button>
                                    : <button type="button" className={ghostButton} disabled={busy} onClick={() => act('assign', 'Incident assigned to you')}><UserPlus className="w-4 h-4" aria-hidden="true" />Assign to me</button>)}
                                <button type="button" className={ghostButton} disabled={busy} onClick={() => run(async () => { const r = await caseFromIncident(authFetch, id); onCaseOpened(r.case); return null; }, 'Case opened')}>
                                    <Briefcase className="w-4 h-4" aria-hidden="true" />{inc.caseId ? 'Show case' : 'Open a case'}
                                </button>
                                {!active && <button type="button" className={ghostButton} disabled={busy} onClick={() => act('reopen', 'Incident reopened')}><RotateCcw className="w-4 h-4" aria-hidden="true" />Reopen</button>}
                            </div>
                            {active && (
                                <fieldset className="rounded-xl border border-gray-200/80 dark:border-white/[0.08] p-3">
                                    <legend className="px-1 text-[13px] font-medium text-gray-900 dark:text-white">Close this incident</legend>
                                    <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                                        {CLOSE_AS.map(r => (
                                            <label key={r} className="flex items-center gap-2 text-sm text-gray-800 dark:text-gray-200 cursor-pointer">
                                                <input type="radio" name="incident-close-as" checked={closeAs === r} onChange={() => setCloseAs(r)} />{RESOLUTION_LABEL[r]}
                                            </label>
                                        ))}
                                    </div>
                                    <label className="block mt-3"><span className="text-xs text-gray-600 dark:text-gray-300">Note (optional)</span>
                                        <textarea value={note} onChange={e => setNote(e.target.value)} maxLength={2000} rows={2} className={`${field} mt-1 h-auto w-full px-3 py-2`} />
                                    </label>
                                    {openAlerts > 0 && (
                                        <label className="mt-2 flex items-center gap-2 text-sm text-gray-800 dark:text-gray-200 cursor-pointer">
                                            <input type="checkbox" checked={closeAlerts} onChange={e => setCloseAlerts(e.target.checked)} />Also close its {openAlerts} open alert{openAlerts === 1 ? '' : 's'} the same way
                                        </label>
                                    )}
                                    <button type="button" className={`${ghostButton} mt-3`} disabled={busy}
                                        onClick={() => act('close', `Incident closed as ${RESOLUTION_LABEL[closeAs].toLowerCase()}`, { resolution: closeAs, note: note.trim() || undefined, closeAlerts: openAlerts > 0 && closeAlerts })}>
                                        Close incident as {RESOLUTION_LABEL[closeAs].toLowerCase()}
                                    </button>
                                </fieldset>
                            )}
                        </section>
                    </>)}
                </div>
            </div>
        </div>
    );
};

interface Campaign { kind: string; key: string; label: string; endpoints: { agentId: string; hostname: string }[]; alertCount: number; severity: SocIncident['severity']; active: number; lastAt?: string | null }
const KIND_LABEL: Record<string, string> = { hash: 'Same file', ip: 'Same IP', technique: 'Same technique', detection: 'Same detection' };

/** The same hash, IP, technique or detection on two or more endpoints in the last 7 days. */
const Campaigns: React.FC<{ reloadKey: number }> = ({ reloadKey }) => {
    const [items, setItems] = useState<Campaign[] | null>(null);
    useEffect(() => {
        authFetch('/api/security/soc/campaigns?days=7').then(r => (r.ok ? r.json() : { items: [] })).then(d => setItems(Array.isArray(d?.items) ? d.items : []))
            .catch(() => setItems([]));
    }, [reloadKey]);
    if (!items || items.length === 0) return null;
    return (
        <section aria-label="Across endpoints" className="p-4 border-b border-gray-200/70 dark:border-white/[0.07]">
            <h3 className={subhead}>Across endpoints (last 7 days)</h3>
            <ul className="mt-2 space-y-2">
                {items.slice(0, 6).map(c => (
                    <li key={`${c.kind}-${c.key}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
                        <SeverityBadge severity={c.severity} />
                        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">{KIND_LABEL[c.kind] ?? c.kind}</span>
                        <span className="font-medium text-gray-900 dark:text-white">{c.label}</span>
                        <span className="text-xs text-gray-600 dark:text-gray-300">on {c.endpoints.length} endpoints ({c.endpoints.map(e => e.hostname).join(', ')}) · {c.alertCount} alerts, {c.active} active · last {formatSince(c.lastAt)}</span>
                    </li>
                ))}
            </ul>
        </section>
    );
};

/** Incidents: an endpoint's alerts less than an hour apart, most severe first. */
export const IncidentsTab: React.FC<{ reloadKey: number; onOpenAlert: (a: SocAlert) => void; onCaseOpened: (c: Record<string, unknown>) => void; onChanged: () => void }> = ({ reloadKey, onOpenAlert, onCaseOpened, onChanged }) => {
    const [status, setStatus] = useState<QueueStatus>('active');
    const [page, setPage] = useState<IncidentPage | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [open, setOpen] = useState<string | null>(null);
    const [bump, setBump] = useState(0);

    useEffect(() => {
        let alive = true;
        fetchIncidents(authFetch, status).then(p => { if (alive) { setPage(p); setError(null); } })
            .catch(e => { if (alive) setError(e instanceof Error ? e.message : 'Incidents could not be loaded'); });
        return () => { alive = false; };
    }, [status, reloadKey, bump]);

    return (
        <section aria-label="Incidents" className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card min-w-0">
            <div className="p-4 flex flex-wrap items-center justify-between gap-2 border-b border-gray-200/70 dark:border-white/[0.07]">
                <div role="group" aria-label="Status" className={segmented}>
                    {STATUSES.map(s => <button key={s.key} type="button" aria-pressed={status === s.key} onClick={() => setStatus(s.key)} className={segment(status === s.key)}>{s.label}</button>)}
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400">An endpoint's alerts less than an hour apart form one incident.</p>
            </div>
            <Campaigns reloadKey={reloadKey + bump} />
            {error && !page ? <p role="alert" className="p-5 text-sm text-red-700 dark:text-red-300">{error}</p>
                : !page ? <p className="p-5 text-sm text-gray-500 dark:text-gray-400">Loading incidents…</p>
                : page.items.length === 0 ? <EmptyNote icon={<Layers className="w-5 h-5" />} title={status === 'active' ? 'No active incidents' : 'No incidents here'} />
                : (
                    <ul className="divide-y divide-gray-100 dark:divide-white/[0.05]">
                        {page.items.map(i => (
                            <li key={i.id}>
                                <button type="button" onClick={() => setOpen(i.id)} className="w-full text-left px-4 py-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 hover:bg-gray-50/80 dark:hover:bg-white/[0.02]">
                                    <SeverityBadge severity={i.severity} />
                                    <span className="min-w-0 flex-1 basis-64">
                                        <span className="block truncate text-sm font-medium text-gray-900 dark:text-white">{i.title}</span>
                                        <span className="block text-xs text-gray-500 dark:text-gray-400">{hostOf(i)} · {i.alertCount} alert{i.alertCount === 1 ? '' : 's'} · last {formatSince(i.lastAlertAt)}{i.grouping ? ' · still collecting' : ''}</span>
                                    </span>
                                    <span className="basis-full sm:basis-auto"><Stages tactics={i.tactics} /></span>
                                    <StatusText status={i.status} resolution={i.resolution} />
                                </button>
                            </li>
                        ))}
                    </ul>
                )}
            {open && <IncidentDrawer id={open} onClose={() => setOpen(null)} onOpenAlert={a => { setOpen(null); onOpenAlert(a); }}
                onCaseOpened={c => { setOpen(null); onCaseOpened(c); }} onChanged={() => { setBump(b => b + 1); onChanged(); }} />}
        </section>
    );
};
