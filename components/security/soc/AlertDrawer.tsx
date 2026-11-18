import React, { useEffect, useRef, useState } from 'react';
import { Bot, Briefcase, Check, ExternalLink, RotateCcw, UserMinus, UserPlus, X } from 'lucide-react';
import { authFetch } from '../../../services/apiService';
import { showToast } from '../../../utils/toast';
import { ghostButton } from '../../network/NetworkKit';
import {
    actOnAlert, approveAiProcess, caseFromAlert, endpointName, formatWhen, RESOLUTION_LABEL,
    type AlertAction, type Resolution, type SocAlert,
} from './socData';
import { SeverityBadge, StatusText, field, primaryButton, subhead } from './SocKit';
import { ResponsePanel } from './ResponsePanel';

const mono = 'font-mono text-[12px] break-all';
const CLOSE_AS: { key: Resolution; hint: string }[] = [
    { key: 'resolved', hint: 'A real issue that has been dealt with' },
    { key: 'false_positive', hint: 'The detection was wrong' },
    { key: 'benign', hint: 'Real, but expected or harmless' },
];

const label = (key: string) => key.replace(/_/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/^./, c => c.toUpperCase());

const EvidenceValue: React.FC<{ value: unknown }> = ({ value }) => {
    if (Array.isArray(value)) {
        return (
            <ul className="space-y-1">
                {value.slice(0, 20).map((item, i) => (
                    <li key={i} className={mono}>
                        {item && typeof item === 'object' ? Object.entries(item as Record<string, unknown>).map(([k, v]) => `${label(k)}: ${String(v)}`).join(' · ') : String(item)}
                    </li>
                ))}
            </ul>
        );
    }
    if (value && typeof value === 'object') return <span className={mono}>{JSON.stringify(value)}</span>;
    return <span className={mono}>{String(value)}</span>;
};

const Row: React.FC<{ term: string; children: React.ReactNode }> = ({ term, children }) => (
    <div className="grid grid-cols-[8.5rem_minmax(0,1fr)] gap-3 py-1.5">
        <dt className="text-xs text-gray-500 dark:text-gray-400">{term}</dt>
        <dd className="text-[13px] text-gray-900 dark:text-white min-w-0">{children}</dd>
    </div>
);

interface Props {
    alert: SocAlert;
    onClose: () => void;
    onChanged: (alert: SocAlert | null) => void;
    onCaseOpened: (caseItem: Record<string, unknown>) => void;
}

export const AlertDrawer: React.FC<Props> = ({ alert: initial, onClose, onChanged, onCaseOpened }) => {
    const [alert, setAlert] = useState(initial);
    const [busy, setBusy] = useState<string | null>(null);
    const [closeAs, setCloseAs] = useState<Resolution>('resolved');
    const [note, setNote] = useState('');
    const [approveAll, setApproveAll] = useState(false);
    const [reason, setReason] = useState('');
    const panelRef = useRef<HTMLDivElement>(null);
    const closeRef = useRef<HTMLButtonElement>(null);

    useEffect(() => setAlert(initial), [initial]);
    useEffect(() => {
        const returnTo = document.activeElement as HTMLElement | null;
        closeRef.current?.focus();
        return () => { returnTo?.focus?.(); };
    }, []);

    const onKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Escape') { e.stopPropagation(); onClose(); return; }
        if (e.key !== 'Tab' || !panelRef.current) return;
        const focusable = panelRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (!focusable.length) return;
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };

    const run = async (key: string, work: () => Promise<SocAlert | null>, done: string) => {
        setBusy(key);
        try {
            const updated = await work();
            if (updated) setAlert(updated);
            showToast(done, 'success');
            onChanged(updated);
        } catch (e) {
            showToast(e instanceof Error ? e.message : 'Nothing was changed', 'error');
        } finally {
            setBusy(null);
        }
    };

    const act = (action: AlertAction, done: string, extra: { resolution?: Resolution; note?: string } = {}) =>
        run(action, () => actOnAlert(authFetch, alert.id, { action, ...extra }), done);

    const openCase = () => run('case', async () => {
        const res = await caseFromAlert(authFetch, alert.id);
        onCaseOpened(res.case);
        return { ...alert, caseId: res.case.id, status: alert.status === 'open' ? 'acknowledged' : alert.status };
    }, 'Case opened');

    const approve = () => run('approve', async () => {
        const res = await approveAiProcess(authFetch, alert.id, approveAll, reason.trim() || undefined);
        return { ...alert, status: 'closed', resolution: 'approved', closeNote: res.approval.reason || null } as SocAlert;
    }, 'Process approved; its alerts are closed');

    const active = alert.status !== 'closed';
    const process = typeof alert.evidence.process === 'string' ? alert.evidence.process : null;
    const evidence = Object.entries(alert.evidence).filter(([, v]) => v !== null && v !== '' && !(Array.isArray(v) && !v.length));

    return (
        <div className="fixed inset-0 z-50" onKeyDown={onKeyDown}>
            <div className="absolute inset-0 bg-gray-950/40 backdrop-blur-[2px] animate-in fade-in duration-150" onClick={onClose} aria-hidden="true" />
            <div ref={panelRef} role="dialog" aria-modal="true" aria-labelledby="soc-drawer-title"
                className="absolute inset-y-0 right-0 w-[min(32rem,100%)] flex flex-col bg-white dark:bg-gray-900 border-l border-gray-200/80 dark:border-white/10 shadow-2xl animate-in slide-in-from-right-8 duration-200">
                <div className="flex items-start gap-3 px-5 py-4 border-b border-gray-200/70 dark:border-white/[0.07]">
                    <div className="min-w-0 flex-1">
                        <p className="flex items-center gap-2"><SeverityBadge severity={alert.severity} /><span className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{alert.typeLabel}</span></p>
                        <h2 id="soc-drawer-title" className="mt-1.5 text-[17px] font-semibold text-gray-900 dark:text-white break-words">{alert.title}</h2>
                        <p className="mt-1"><StatusText status={alert.status} resolution={alert.resolution} /></p>
                    </div>
                    <button ref={closeRef} type="button" onClick={onClose} aria-label="Close alert details"
                        className="grid place-items-center h-8 w-8 rounded-lg text-gray-500 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/[0.06]">
                        <X className="w-4 h-4" aria-hidden="true" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto px-5 py-5 space-y-6 custom-scrollbar">
                    {alert.description && <p className="text-sm text-gray-700 dark:text-gray-300 break-words">{alert.description}</p>}

                    <section>
                        <h3 className={subhead}>Details</h3>
                        <dl className="mt-1 divide-y divide-gray-100 dark:divide-white/[0.05]">
                            <Row term="Endpoint">{endpointName(alert)}</Row>
                            <Row term="First seen">{formatWhen(alert.createdAt)}</Row>
                            <Row term="Last seen">{formatWhen(alert.lastSeenAt)}{alert.occurrences > 1 && <span className="text-gray-500 dark:text-gray-400"> · seen {alert.occurrences} times</span>}</Row>
                            <Row term="Assigned to">{alert.assignee || 'Nobody'}</Row>
                            {alert.acknowledgedAt && <Row term="Acknowledged">{formatWhen(alert.acknowledgedAt)}{alert.acknowledgedBy && ` by ${alert.acknowledgedBy}`}</Row>}
                            {alert.status === 'closed' && (
                                <Row term="Closed">
                                    {alert.resolution ? RESOLUTION_LABEL[alert.resolution] : 'Closed'}
                                    {alert.closedAt && ` · ${formatWhen(alert.closedAt)}`}{alert.closedBy && ` by ${alert.closedBy}`}
                                    {alert.closeNote && <span className="block text-xs text-gray-600 dark:text-gray-300">{alert.closeNote}</span>}
                                </Row>
                            )}
                            {alert.caseId && <Row term="Case"><span className={mono}>{alert.caseId}</span></Row>}
                        </dl>
                    </section>

                    {alert.mitre.length > 0 && (
                        <section>
                            <h3 className={subhead}>MITRE ATT&CK</h3>
                            <ul className="mt-2 flex flex-wrap gap-2">
                                {alert.mitre.map(t => (
                                    <li key={t}>
                                        <a href={`https://attack.mitre.org/techniques/${t.replace('.', '/')}/`} target="_blank" rel="noopener noreferrer"
                                            className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-mono text-[12px] bg-gray-100 dark:bg-white/[0.06] text-gray-800 dark:text-gray-200 hover:text-primary-700 dark:hover:text-primary-300">
                                            {t}<ExternalLink className="w-3 h-3" aria-hidden="true" /><span className="sr-only"> (opens MITRE ATT&CK)</span>
                                        </a>
                                    </li>
                                ))}
                            </ul>
                        </section>
                    )}

                    {evidence.length > 0 && (
                        <section>
                            <h3 className={subhead}>Evidence</h3>
                            <dl className="mt-1 divide-y divide-gray-100 dark:divide-white/[0.05]">
                                {evidence.map(([k, v]) => <Row key={k} term={label(k)}><EvidenceValue value={v} /></Row>)}
                            </dl>
                        </section>
                    )}

                    {alert.source === 'security' && <ResponsePanel alertId={alert.id} onChanged={() => onChanged(null)} />}

                    <section className="space-y-3">
                        <h3 className={subhead}>Handle the alert</h3>
                        <div className="flex flex-wrap gap-2">
                            {alert.status === 'open' && (
                                <button type="button" className={primaryButton} disabled={!!busy} onClick={() => act('acknowledge', 'Alert acknowledged')}>
                                    <Check className="w-4 h-4" aria-hidden="true" />Acknowledge
                                </button>
                            )}
                            {active && (alert.assignee
                                ? <button type="button" className={ghostButton} disabled={!!busy} onClick={() => act('unassign', 'Alert unassigned')}><UserMinus className="w-4 h-4" aria-hidden="true" />Unassign</button>
                                : <button type="button" className={ghostButton} disabled={!!busy} onClick={() => act('assign', 'Alert assigned to you')}><UserPlus className="w-4 h-4" aria-hidden="true" />Assign to me</button>)}
                            {alert.source === 'security' && (
                                <button type="button" className={ghostButton} disabled={!!busy} onClick={openCase}>
                                    <Briefcase className="w-4 h-4" aria-hidden="true" />{alert.caseId ? 'Show case' : 'Open a case'}
                                </button>
                            )}
                            {!active && (
                                <button type="button" className={ghostButton} disabled={!!busy} onClick={() => act('reopen', 'Alert reopened')}>
                                    <RotateCcw className="w-4 h-4" aria-hidden="true" />Reopen
                                </button>
                            )}
                        </div>

                        {active && (
                            <fieldset className="rounded-xl border border-gray-200/80 dark:border-white/[0.08] p-3">
                                <legend className="px-1 text-[13px] font-medium text-gray-900 dark:text-white">Close this alert</legend>
                                <div className="space-y-1.5">
                                    {CLOSE_AS.map(c => (
                                        <label key={c.key} className="flex items-start gap-2 text-sm text-gray-800 dark:text-gray-200 cursor-pointer">
                                            <input type="radio" name="close-as" value={c.key} checked={closeAs === c.key} onChange={() => setCloseAs(c.key)} className="mt-1" />
                                            <span>{RESOLUTION_LABEL[c.key]}<span className="block text-[11px] text-gray-500 dark:text-gray-400">{c.hint}</span></span>
                                        </label>
                                    ))}
                                </div>
                                <label className="block mt-3">
                                    <span className="text-xs text-gray-600 dark:text-gray-300">Note (optional)</span>
                                    <textarea value={note} onChange={e => setNote(e.target.value)} maxLength={2000} rows={2}
                                        className={`${field} mt-1 h-auto w-full px-3 py-2`} />
                                </label>
                                <button type="button" className={`${ghostButton} mt-3`} disabled={!!busy}
                                    onClick={() => act('close', `Alert closed as ${RESOLUTION_LABEL[closeAs].toLowerCase()}`, { resolution: closeAs, note: note.trim() || undefined })}>
                                    Close as {RESOLUTION_LABEL[closeAs].toLowerCase()}
                                </button>
                            </fieldset>
                        )}

                        {active && alert.type === 'shadow_ai_process' && process && (
                            <fieldset className="rounded-xl border border-gray-200/80 dark:border-white/[0.08] p-3">
                                <legend className="px-1 text-[13px] font-medium text-gray-900 dark:text-white">Approve {process}</legend>
                                <p className="text-xs text-gray-600 dark:text-gray-300">Approved processes raise no alerts. You can remove an approval under Detection health.</p>
                                <div className="mt-2 space-y-1.5 text-sm text-gray-800 dark:text-gray-200">
                                    <label className="flex items-center gap-2 cursor-pointer"><input type="radio" name="approve-scope" checked={!approveAll} onChange={() => setApproveAll(false)} />On {endpointName(alert)} only</label>
                                    <label className="flex items-center gap-2 cursor-pointer"><input type="radio" name="approve-scope" checked={approveAll} onChange={() => setApproveAll(true)} />On all endpoints</label>
                                </div>
                                <label className="block mt-3">
                                    <span className="text-xs text-gray-600 dark:text-gray-300">Reason (optional)</span>
                                    <input value={reason} onChange={e => setReason(e.target.value)} maxLength={500} className={`${field} mt-1 w-full px-3`} />
                                </label>
                                <button type="button" className={`${ghostButton} mt-3`} disabled={!!busy} onClick={approve}>
                                    <Bot className="w-4 h-4" aria-hidden="true" />Approve {process}
                                </button>
                            </fieldset>
                        )}
                    </section>
                </div>
            </div>
        </div>
    );
};
