import React, { useEffect, useState } from 'react';
import { Plus, Trash2, Workflow } from 'lucide-react';
import { authFetch } from '../../../services/apiService';
import { showToast } from '../../../utils/toast';
import { EmptyNote, ghostButton } from '../../network/NetworkKit';
import { RESOLUTION_LABEL, SEVERITIES, SEVERITY_META, formatSince, type Resolution, type Severity } from './socData';
import { field, primaryButton, subhead } from './SocKit';

interface Rule {
    id: string; name: string; enabled: boolean;
    conditions: { types: string[]; severities: Severity[]; agentIds: string[]; techniques: string[]; text: string };
    actions: { assignTo: string | null; raiseTo: Severity | null; close: Resolution | null; notify: string[]; openCase: boolean; suggestResponse: string | null };
    stats?: { matched: number; lastMatchedAt: string | null };
}
type Draft = Omit<Rule, 'id' | 'stats'>;
const RESPONSES: Record<string, string> = { isolate_host: 'Isolate host', quarantine_file: 'Quarantine file', block_ip: 'Block IP', kill_process: 'End process' };
const EMPTY: Draft = { name: '', enabled: true, conditions: { types: [], severities: [], agentIds: [], techniques: [], text: '' },
    actions: { assignTo: null, raiseTo: null, close: null, notify: [], openCase: false, suggestResponse: null } };

const call = async (url: string, method = 'GET', body?: unknown) => {
    const res = await authFetch(url, method === 'GET' ? undefined : { method, body: body === undefined ? undefined : JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `HTTP ${res.status}`);
    return data;
};

const summary = (r: Draft, types: Record<string, string>) => {
    const when = [
        r.conditions.types.length && r.conditions.types.map(t => types[t] || t).join(' or '),
        r.conditions.severities.length && `severity ${r.conditions.severities.join(' or ')}`,
        r.conditions.text && `text “${r.conditions.text}”`,
        r.conditions.techniques.length && r.conditions.techniques.join(', '),
    ].filter(Boolean).join(', ');
    const then = [
        r.actions.close && `close as ${RESOLUTION_LABEL[r.actions.close].toLowerCase()}`,
        r.actions.assignTo && `assign to ${r.actions.assignTo}`, r.actions.raiseTo && `raise to ${r.actions.raiseTo}`,
        r.actions.notify.length && `notify (${r.actions.notify.map(n => (n === 'in_app' ? 'in the app' : 'webhook')).join(', ')})`,
        r.actions.openCase && 'open a case', r.actions.suggestResponse && `suggest ${RESPONSES[r.actions.suggestResponse].toLowerCase()}`,
    ].filter(Boolean).join(', ');
    return `When ${when || '…'}, ${then || '…'}.`;
};

/** Automation rules: what happens to new alerts that match. Rules never send a response to an endpoint. */
export const RulesTab: React.FC<{ types: { type: string; label: string }[] }> = ({ types }) => {
    const [rules, setRules] = useState<Rule[] | null>(null);
    const [canEdit, setCanEdit] = useState(false);
    const [draft, setDraft] = useState<Draft | null>(null);
    const [editing, setEditing] = useState<string | null>(null);
    const [preview, setPreview] = useState<{ matched: number; checked: number; examples: { id: string; title: string }[] } | null>(null);
    const [error, setError] = useState<string | null>(null);
    const typeLabel = Object.fromEntries(types.map(t => [t.type, t.label]));

    const load = () => call('/api/security/soc/rules').then(d => { setRules(d.items); setCanEdit(!!d.canEdit); setError(null); })
        .catch(e => setError(e instanceof Error ? e.message : 'Rules could not be loaded'));
    useEffect(() => { load(); }, []);

    const set = (fn: (d: Draft) => Draft) => { setDraft(d => (d ? fn(d) : d)); setPreview(null); };
    const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter(x => x !== v) : [...list, v]);
    const save = async () => {
        if (!draft) return;
        try {
            await call(editing ? `/api/security/soc/rules/${editing}` : '/api/security/soc/rules', editing ? 'PUT' : 'POST', draft);
            showToast(`Rule “${draft.name}” saved; it applies to new alerts`, 'success');
            setDraft(null); setEditing(null); load();
        } catch (e) { showToast(e instanceof Error ? e.message : 'The rule was not saved', 'error'); }
    };
    const run = (fn: () => Promise<unknown>, done: string) => fn().then(() => { showToast(done, 'success'); load(); })
        .catch(e => showToast(e instanceof Error ? e.message : 'Nothing was changed', 'error'));

    const check = (label: string, on: boolean, onChange: () => void) => (
        <label key={label} className="inline-flex items-center gap-1.5 text-sm text-gray-800 dark:text-gray-200 cursor-pointer">
            <input type="checkbox" checked={on} onChange={onChange} />{label}
        </label>
    );

    return (
        <section aria-label="Automation rules" className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card p-4 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-gray-600 dark:text-gray-300 max-w-2xl">Rules run in order on each new alert. They can assign, raise, close, notify, open a case or suggest a response; they never send a response to an endpoint.</p>
                {canEdit && !draft && <button type="button" className={primaryButton} onClick={() => { setDraft(EMPTY); setEditing(null); }}><Plus className="w-4 h-4" aria-hidden="true" />New rule</button>}
            </div>
            {error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>}

            {draft && (
                <div className="rounded-xl border border-gray-200/80 dark:border-white/[0.08] p-4 space-y-4">
                    <label className="block"><span className="text-xs text-gray-600 dark:text-gray-300">Name</span>
                        <input value={draft.name} maxLength={120} onChange={e => set(d => ({ ...d, name: e.target.value }))} className={`${field} mt-1 w-full max-w-md px-3`} />
                    </label>
                    <fieldset><legend className={subhead}>When a new alert</legend>
                        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">{types.map(t => check(t.label, draft.conditions.types.includes(t.type), () => set(d => ({ ...d, conditions: { ...d.conditions, types: toggle(d.conditions.types, t.type) } }))))}</div>
                        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">{SEVERITIES.map(s => check(SEVERITY_META[s].label, draft.conditions.severities.includes(s), () => set(d => ({ ...d, conditions: { ...d.conditions, severities: toggle(d.conditions.severities, s) } }))))}</div>
                        <div className="mt-2 flex flex-wrap gap-3">
                            <label><span className="text-xs text-gray-600 dark:text-gray-300">Text in title or details</span>
                                <input value={draft.conditions.text} maxLength={100} onChange={e => set(d => ({ ...d, conditions: { ...d.conditions, text: e.target.value } }))} className={`${field} mt-1 block w-56 px-3`} /></label>
                            <label><span className="text-xs text-gray-600 dark:text-gray-300">MITRE techniques (comma separated)</span>
                                <input value={draft.conditions.techniques.join(', ')} onChange={e => set(d => ({ ...d, conditions: { ...d.conditions, techniques: e.target.value.split(',').map(t => t.trim()).filter(Boolean) } }))} className={`${field} mt-1 block w-56 px-3`} /></label>
                        </div>
                    </fieldset>
                    <fieldset><legend className={subhead}>Then</legend>
                        <div className="mt-2 flex flex-wrap gap-3 items-end">
                            <label><span className="text-xs text-gray-600 dark:text-gray-300">Close as</span>
                                <select value={draft.actions.close ?? ''} onChange={e => set(d => ({ ...d, actions: { ...d.actions, close: (e.target.value || null) as Resolution | null } }))} className={`${field} mt-1 block px-2`}>
                                    <option value="">Don't close</option>{(['resolved', 'false_positive', 'benign'] as Resolution[]).map(r => <option key={r} value={r}>{RESOLUTION_LABEL[r]}</option>)}</select></label>
                            <label><span className="text-xs text-gray-600 dark:text-gray-300">Assign to (email)</span>
                                <input value={draft.actions.assignTo ?? ''} maxLength={120} onChange={e => set(d => ({ ...d, actions: { ...d.actions, assignTo: e.target.value || null } }))} className={`${field} mt-1 block w-48 px-3`} /></label>
                            <label><span className="text-xs text-gray-600 dark:text-gray-300">Raise severity to</span>
                                <select value={draft.actions.raiseTo ?? ''} onChange={e => set(d => ({ ...d, actions: { ...d.actions, raiseTo: (e.target.value || null) as Severity | null } }))} className={`${field} mt-1 block px-2`}>
                                    <option value="">Leave it</option>{SEVERITIES.map(s => <option key={s} value={s}>{SEVERITY_META[s].label}</option>)}</select></label>
                            <label><span className="text-xs text-gray-600 dark:text-gray-300">Suggest a response</span>
                                <select value={draft.actions.suggestResponse ?? ''} onChange={e => set(d => ({ ...d, actions: { ...d.actions, suggestResponse: e.target.value || null } }))} className={`${field} mt-1 block px-2`}>
                                    <option value="">None</option>{Object.entries(RESPONSES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">
                            {check('Notify admins in the app', draft.actions.notify.includes('in_app'), () => set(d => ({ ...d, actions: { ...d.actions, notify: toggle(d.actions.notify, 'in_app') } })))}
                            {check('Send to webhooks (soc.rule_match)', draft.actions.notify.includes('webhook'), () => set(d => ({ ...d, actions: { ...d.actions, notify: toggle(d.actions.notify, 'webhook') } })))}
                            {check('Open a case', draft.actions.openCase, () => set(d => ({ ...d, actions: { ...d.actions, openCase: !d.actions.openCase } })))}
                        </div>
                    </fieldset>
                    <p className="text-sm text-gray-700 dark:text-gray-300">{summary(draft, typeLabel)}</p>
                    {preview && <p className="text-sm text-gray-800 dark:text-gray-200" role="status">Would have matched <strong>{preview.matched}</strong> of {preview.checked} alerts in the last 7 days{preview.examples.length ? `, e.g. ${preview.examples.slice(0, 3).map(x => `“${x.title}”`).join(', ')}` : ''}.</p>}
                    <div className="flex flex-wrap gap-2">
                        <button type="button" className={ghostButton} onClick={() => call('/api/security/soc/rules/preview', 'POST', draft).then(setPreview).catch(e => showToast(e.message, 'error'))}>Preview on the last 7 days</button>
                        <button type="button" className={primaryButton} onClick={save}>Save rule</button>
                        <button type="button" className={ghostButton} onClick={() => { setDraft(null); setEditing(null); setPreview(null); }}>Cancel</button>
                    </div>
                </div>
            )}

            {rules && rules.length === 0 && !draft && <EmptyNote icon={<Workflow className="w-5 h-5" />} title="No rules yet">{canEdit ? 'Create one to handle routine alerts the same way every time.' : 'An administrator can create rules.'}</EmptyNote>}
            {rules && rules.length > 0 && (
                <ol className="divide-y divide-gray-100 dark:divide-white/[0.05]">
                    {rules.map((r, i) => (
                        <li key={r.id} className="py-3 flex flex-wrap items-start gap-3">
                            <span className="font-mono text-xs text-gray-500 dark:text-gray-400 w-5">{i + 1}</span>
                            <span className="min-w-0 flex-1">
                                <span className="block text-sm font-medium text-gray-900 dark:text-white">{r.name}{!r.enabled && <span className="ml-2 text-xs font-normal text-gray-500">off</span>}</span>
                                <span className="block text-xs text-gray-600 dark:text-gray-300">{summary(r, typeLabel)}</span>
                                <span className="block text-[11px] text-gray-500 dark:text-gray-400">Matched {r.stats?.matched ?? 0} time{r.stats?.matched === 1 ? '' : 's'}{r.stats?.lastMatchedAt ? `, last ${formatSince(r.stats.lastMatchedAt)}` : ''}</span>
                            </span>
                            {canEdit && (
                                <span className="flex gap-2">
                                    <button type="button" className={`${ghostButton} h-8`} onClick={() => run(() => call(`/api/security/soc/rules/${r.id}`, 'PUT', { ...r, enabled: !r.enabled }), r.enabled ? 'Rule switched off' : 'Rule switched on')}>{r.enabled ? 'Switch off' : 'Switch on'}</button>
                                    <button type="button" className={`${ghostButton} h-8`} onClick={() => { setDraft({ name: r.name, enabled: r.enabled, conditions: r.conditions, actions: r.actions }); setEditing(r.id); setPreview(null); }}>Edit</button>
                                    <button type="button" className={`${ghostButton} h-8`} aria-label={`Delete rule ${r.name}`} onClick={() => { if (window.confirm(`Delete the rule “${r.name}”?`)) run(() => call(`/api/security/soc/rules/${r.id}`, 'DELETE'), 'Rule deleted'); }}><Trash2 className="w-3.5 h-3.5" aria-hidden="true" /></button>
                                </span>
                            )}
                        </li>
                    ))}
                </ol>
            )}
        </section>
    );
};
