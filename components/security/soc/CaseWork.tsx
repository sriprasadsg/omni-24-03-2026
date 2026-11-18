import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ClipboardList, Download, Eye, EyeOff, Fingerprint, ListChecks, Paperclip, Plus, StickyNote, Upload } from 'lucide-react';
import { authFetch } from '../../../services/apiService';
import { showToast } from '../../../utils/toast';
import { ghostButton } from '../../network/NetworkKit';
import {
    addAlertIndicators, addCaseEvidence, addCaseTask, addStandardSteps, downloadCaseFile, fetchCaseWork, formatWhen, setEvidenceExcluded,
    updateCaseTask, uploadCaseFile, type CaseEvidence, type CaseTask, type CaseWork as Work, type IndicatorKind, type TaskStatus,
} from './socData';
import { field, subhead } from './SocKit';

const TASK_LABEL: Record<TaskStatus, string> = { todo: 'To do', in_progress: 'In progress', done: 'Done', skipped: 'Skipped' };
const KIND_LABEL: Record<IndicatorKind, string> = { user: 'User', process: 'Process', file: 'File', ip: 'IP address', domain: 'Domain', hash: 'Hash', other: 'Other' };
const CUSTODY: Record<string, string> = { added: 'Added', downloaded: 'Downloaded', excluded: 'Excluded', restored: 'Included again' };
const size = (n?: number) => (n == null ? '' : n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`);

const EvidenceItem: React.FC<{ item: CaseEvidence; caseId: string; canEdit: boolean; busy: boolean; onChange: (work: () => Promise<unknown>, done: string) => void }> = ({ item, caseId, canEdit, busy, onChange }) => {
    const [excluding, setExcluding] = useState(false);
    const [reason, setReason] = useState('');
    const Icon = item.kind === 'file' ? Paperclip : item.kind === 'note' ? StickyNote : Fingerprint;
    return (
        <li className={`rounded-lg border border-gray-200/80 dark:border-white/[0.08] p-2.5 ${item.excluded ? 'opacity-60' : ''}`}>
            <div className="flex items-start gap-2">
                <Icon className="w-4 h-4 mt-0.5 text-gray-500 dark:text-gray-400 shrink-0" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                    <p className="text-[11px] text-gray-500 dark:text-gray-400">
                        {item.kind === 'indicator' ? KIND_LABEL[item.indicatorKind ?? 'other'] : item.kind === 'file' ? `File · ${size(item.size)}` : 'Note'}
                        {item.excluded && ' · Excluded'}{item.alertIds?.length ? ` · from ${item.alertIds.length} alert${item.alertIds.length === 1 ? '' : 's'}` : ''}
                    </p>
                    <p className={`text-[13px] text-gray-900 dark:text-white break-words ${item.kind === 'note' ? '' : 'font-mono'}`}>{item.value}</p>
                    {item.sha256 && <p className="text-[11px] font-mono text-gray-500 dark:text-gray-400 break-all">SHA-256 {item.sha256}</p>}
                    {item.note && <p className="mt-0.5 text-xs text-gray-600 dark:text-gray-300 break-words">{item.note}</p>}
                    <details className="mt-1">
                        <summary className="cursor-pointer text-[11px] text-gray-500 dark:text-gray-400">Custody ({item.custody.length})</summary>
                        <ol className="mt-1 space-y-0.5 text-[11px] text-gray-600 dark:text-gray-300">
                            {item.custody.map((c, i) => <li key={i}>{CUSTODY[c.action] ?? c.action} by {c.by}, {formatWhen(c.at)}{c.note ? ` · ${c.note}` : ''}</li>)}
                        </ol>
                    </details>
                </div>
                <div className="flex shrink-0 gap-1">
                    {item.kind === 'file' && (
                        <button type="button" className={ghostButton} disabled={busy} aria-label={`Download ${item.value}`}
                            onClick={() => onChange(() => downloadCaseFile(authFetch, caseId, item), 'Downloaded; the download is on its custody log')}>
                            <Download className="w-4 h-4" aria-hidden="true" />
                        </button>
                    )}
                    {canEdit && (item.excluded
                        ? <button type="button" className={ghostButton} disabled={busy} onClick={() => onChange(() => setEvidenceExcluded(authFetch, caseId, item.id, false), 'Evidence included again')}><Eye className="w-4 h-4" aria-hidden="true" />Include</button>
                        : <button type="button" className={ghostButton} disabled={busy} aria-expanded={excluding} onClick={() => setExcluding(x => !x)}><EyeOff className="w-4 h-4" aria-hidden="true" />Exclude</button>)}
                </div>
            </div>
            {excluding && !item.excluded && (
                <form className="mt-2 flex flex-wrap gap-2" onSubmit={e => { e.preventDefault(); if (reason.trim()) { onChange(() => setEvidenceExcluded(authFetch, caseId, item.id, true, reason.trim()), 'Evidence excluded; it is kept'); setExcluding(false); } }}>
                    <label className="flex-1 min-w-[12rem]"><span className="sr-only">Why is it excluded?</span>
                        <input value={reason} onChange={e => setReason(e.target.value)} maxLength={500} placeholder="Why it does not matter" className={`${field} w-full px-3`} /></label>
                    <button type="submit" className={ghostButton} disabled={busy || !reason.trim()}>Exclude</button>
                </form>
            )}
        </li>
    );
};

/** A case's tasks and evidence (stored apart from the case, so saving a comment never overwrites them). */
export const CaseWork: React.FC<{ caseId: string }> = ({ caseId }) => {
    const [work, setWork] = useState<Work | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [taskTitle, setTaskTitle] = useState('');
    const [evKind, setEvKind] = useState<'indicator' | 'note'>('indicator');
    const [indKind, setIndKind] = useState<IndicatorKind>('ip');
    const [evValue, setEvValue] = useState('');
    const [skipping, setSkipping] = useState<string | null>(null);
    const [skipNote, setSkipNote] = useState('');
    const fileRef = useRef<HTMLInputElement>(null);

    const load = useCallback(() => {
        fetchCaseWork(authFetch, caseId).then(w => { setWork(w); setError(null); })
            .catch(e => setError(e instanceof Error ? e.message : 'Tasks and evidence could not be loaded'));
    }, [caseId]);
    useEffect(() => { load(); }, [load]);

    const run = async (job: () => Promise<unknown>, done: string) => {
        setBusy(true);
        try {
            await job();
            showToast(done, 'success');
            load();
        } catch (e) {
            showToast(e instanceof Error ? e.message : 'Nothing was changed', 'error');
        } finally {
            setBusy(false);
        }
    };
    const setStatus = (t: CaseTask, status: TaskStatus, note?: string) =>
        run(() => updateCaseTask(authFetch, caseId, t.id, { status, ...(note ? { note } : {}) }), `Task marked ${TASK_LABEL[status].toLowerCase()}`);

    if (error && !work) return <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>;
    if (!work) return <p className="text-sm text-gray-500 dark:text-gray-400">Loading tasks and evidence…</p>;
    const open = work.tasks.filter(t => t.status === 'todo' || t.status === 'in_progress').length;
    const { canEdit } = work;

    return (
        <div className="space-y-5">
            <section aria-labelledby={`tasks-${caseId}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 id={`tasks-${caseId}`} className={`${subhead} flex items-center gap-1.5`}><ListChecks className="w-3.5 h-3.5" aria-hidden="true" />
                        Tasks {work.tasks.length > 0 && <span className="normal-case font-normal tracking-normal">· {work.tasks.length - open} of {work.tasks.length} finished</span>}</h3>
                    {canEdit && work.standardSteps.length > 0 && (
                        <button type="button" className={ghostButton} disabled={busy} onClick={() => run(() => addStandardSteps(authFetch, caseId), 'Standard steps added')}>
                            <ClipboardList className="w-4 h-4" aria-hidden="true" />Add the standard steps ({work.standardSteps.length})
                        </button>
                    )}
                </div>
                {work.tasks.length === 0 ? <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">No tasks yet.</p> : (
                    <ul className="mt-2 space-y-1.5">
                        {work.tasks.map(t => {
                            const finished = t.status === 'done' || t.status === 'skipped';
                            return (
                                <li key={t.id} className="rounded-lg px-2 py-1.5 hover:bg-gray-50 dark:hover:bg-white/[0.03]">
                                    <div className="flex items-start gap-2">
                                        <input type="checkbox" className="mt-1" checked={t.status === 'done'} disabled={!canEdit || busy || t.status === 'skipped'}
                                            aria-label={`${t.title}: ${t.status === 'done' ? 'done' : 'not done'}`} onChange={e => setStatus(t, e.target.checked ? 'done' : 'todo')} />
                                        <div className="min-w-0 flex-1">
                                            <p className={`text-[13px] text-gray-900 dark:text-white break-words ${finished ? 'line-through decoration-gray-400' : ''}`}>{t.title}</p>
                                            <p className="text-[11px] text-gray-500 dark:text-gray-400">{TASK_LABEL[t.status]}{t.assignee ? ` · ${t.assignee}` : ''}
                                                {t.closedBy ? ` · by ${t.closedBy}, ${formatWhen(t.closedAt)}` : ''}{t.note ? ` · ${t.note}` : ''}</p>
                                        </div>
                                        {canEdit && !finished && (
                                            <div className="flex shrink-0 gap-1 text-xs">
                                                {t.status === 'todo' && <button type="button" className="px-2 py-1 rounded-md text-primary-700 dark:text-primary-300 hover:bg-primary-500/10" disabled={busy} onClick={() => setStatus(t, 'in_progress')}>Start</button>}
                                                <button type="button" className="px-2 py-1 rounded-md text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/[0.06]" disabled={busy} aria-expanded={skipping === t.id}
                                                    onClick={() => { setSkipping(s => (s === t.id ? null : t.id)); setSkipNote(''); }}>Skip</button>
                                            </div>
                                        )}
                                        {canEdit && finished && <button type="button" className="px-2 py-1 rounded-md text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/[0.06]" disabled={busy} onClick={() => setStatus(t, 'todo')}>Reopen</button>}
                                    </div>
                                    {skipping === t.id && (
                                        <form className="mt-1.5 ml-6 flex flex-wrap gap-2" onSubmit={e => { e.preventDefault(); if (skipNote.trim()) { setStatus(t, 'skipped', skipNote.trim()); setSkipping(null); } }}>
                                            <label className="flex-1 min-w-[12rem]"><span className="sr-only">Why is it skipped?</span>
                                                <input value={skipNote} onChange={e => setSkipNote(e.target.value)} maxLength={1000} placeholder="Why it does not apply" className={`${field} w-full px-3`} /></label>
                                            <button type="submit" className={ghostButton} disabled={busy || !skipNote.trim()}>Skip task</button>
                                        </form>
                                    )}
                                </li>
                            );
                        })}
                    </ul>
                )}
                {canEdit && (
                    <form className="mt-2 flex gap-2" onSubmit={e => { e.preventDefault(); const title = taskTitle.trim(); if (title) { run(() => addCaseTask(authFetch, caseId, title), 'Task added'); setTaskTitle(''); } }}>
                        <label className="flex-1"><span className="sr-only">New task</span>
                            <input value={taskTitle} onChange={e => setTaskTitle(e.target.value)} maxLength={200} placeholder="Add a task" className={`${field} w-full px-3`} /></label>
                        <button type="submit" className={ghostButton} disabled={busy || !taskTitle.trim()}><Plus className="w-4 h-4" aria-hidden="true" />Add</button>
                    </form>
                )}
            </section>

            <section aria-labelledby={`evidence-${caseId}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 id={`evidence-${caseId}`} className={`${subhead} flex items-center gap-1.5`}><Fingerprint className="w-3.5 h-3.5" aria-hidden="true" />Evidence ({work.evidence.length})</h3>
                    {canEdit && work.alertIndicators.length > 0 && (
                        <button type="button" className={ghostButton} disabled={busy} onClick={() => run(() => addAlertIndicators(authFetch, caseId), 'Indicators from the alerts added')}>
                            <Plus className="w-4 h-4" aria-hidden="true" />Add {work.alertIndicators.length} indicator{work.alertIndicators.length === 1 ? '' : 's'} from the alerts
                        </button>
                    )}
                </div>
                {work.evidence.length === 0 ? <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">No evidence yet.</p> : (
                    <ul className="mt-2 space-y-2">
                        {work.evidence.map(item => <EvidenceItem key={item.id} item={item} caseId={caseId} canEdit={canEdit} busy={busy} onChange={run} />)}
                    </ul>
                )}
                {canEdit && (
                    <div className="mt-3 rounded-xl border border-gray-200/80 dark:border-white/[0.08] p-3 space-y-2">
                        <form className="flex flex-wrap gap-2" onSubmit={e => {
                            e.preventDefault();
                            const value = evValue.trim();
                            if (!value) return;
                            run(() => addCaseEvidence(authFetch, caseId, evKind === 'note' ? { kind: 'note', value } : { kind: 'indicator', value, indicatorKind: indKind }), 'Evidence added');
                            setEvValue('');
                        }}>
                            <label><span className="sr-only">Kind of evidence</span>
                                <select value={evKind} onChange={e => setEvKind(e.target.value as 'indicator' | 'note')} className={`${field} px-2`}>
                                    <option value="indicator">Indicator</option><option value="note">Note</option>
                                </select></label>
                            {evKind === 'indicator' && (
                                <label><span className="sr-only">Kind of indicator</span>
                                    <select value={indKind} onChange={e => setIndKind(e.target.value as IndicatorKind)} className={`${field} px-2`}>
                                        {(Object.keys(KIND_LABEL) as IndicatorKind[]).map(k => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
                                    </select></label>
                            )}
                            <label className="flex-1 min-w-[12rem]"><span className="sr-only">{evKind === 'note' ? 'Note' : 'Indicator value'}</span>
                                <input value={evValue} onChange={e => setEvValue(e.target.value)} maxLength={evKind === 'note' ? 4000 : 500}
                                    placeholder={evKind === 'note' ? 'What you found' : 'Value, e.g. 45.33.32.156'} className={`${field} w-full px-3`} /></label>
                            <button type="submit" className={ghostButton} disabled={busy || !evValue.trim()}><Plus className="w-4 h-4" aria-hidden="true" />Add</button>
                        </form>
                        <div className="flex flex-wrap items-center gap-2">
                            <input ref={fileRef} type="file" className="sr-only" id={`evidence-file-${caseId}`} onChange={e => {
                                const file = e.target.files?.[0];
                                e.target.value = '';
                                if (file) run(() => uploadCaseFile(authFetch, caseId, file), `${file.name} added with its SHA-256`);
                            }} />
                            <button type="button" className={ghostButton} disabled={busy} onClick={() => fileRef.current?.click()}><Upload className="w-4 h-4" aria-hidden="true" />Add a file</button>
                            <span className="text-xs text-gray-500 dark:text-gray-400">At most 25 MB. Files are kept with their SHA-256 and only ever downloaded, never opened here.</span>
                        </div>
                    </div>
                )}
            </section>
        </div>
    );
};
