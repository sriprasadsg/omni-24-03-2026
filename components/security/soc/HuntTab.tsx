import React, { useEffect, useRef, useState } from 'react';
import { BookmarkPlus, Play, Plus, Search, Trash2, Workflow, X } from 'lucide-react';
import { showToast } from '../../../utils/toast';
import { EmptyNote, ghostButton } from '../../network/NetworkKit';
import { Skeleton } from '../../ui/skeleton';
import { formatSince } from './socData';
import { field, primaryButton, segment, segmented, subhead } from './SocKit';
import { HuntResults } from './HuntResults';
import { HuntRulePanel } from './HuntRulePanel';
import {
    EMPTY_DRAFT, OPS, OP_LABEL, RANGES, SOURCES, deleteHunt, describeHunt, fetchHuntFields, fetchHunts, fromQuery, rerunHunt,
    runHunt, sameQuery, saveHunt, toQuery, type DraftFilter, type HuntCatalogue, type HuntDraft, type HuntList, type HuntResult,
    type HuntSource, type SavedHunt,
} from './huntData';

const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);
const card = 'rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card p-4';
const small = 'block text-[11px] text-gray-500 dark:text-gray-400';

/** Hunting: one query over SOC alerts, SIEM events or agent logs; saved hunts rerun on demand; an exact hunt over
 *  SIEM events becomes a SIEM rule. */
export const HuntTab: React.FC = () => {
    const [catalogue, setCatalogue] = useState<HuntCatalogue | null>(null);
    const [list, setList] = useState<HuntList | null>(null);
    const [draft, setDraft] = useState<HuntDraft>(EMPTY_DRAFT);
    const [current, setCurrent] = useState<SavedHunt | null>(null);
    const [result, setResult] = useState<HuntResult | null>(null);
    const [running, setRunning] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [naming, setNaming] = useState<{ name: string; description: string } | null>(null);
    const [ruleFor, setRuleFor] = useState<SavedHunt | null>(null);
    const seq = useRef(0);

    const loadList = () => fetchHunts().then(setList).catch(e => setError(message(e, 'Saved hunts could not be loaded')));
    useEffect(() => {
        fetchHuntFields().then(setCatalogue).catch(e => setError(message(e, 'The hunt fields could not be loaded')));
        loadList();
    }, []);

    const info = catalogue?.sources[draft.source];
    const fields = info?.fields ?? [];
    const query = toQuery(draft);
    const unchanged = !!current && sameQuery(query, current.query);

    // Only the latest request may show its answer (an older, slower one is dropped).
    const execute = async (fn: () => Promise<HuntResult>, onDone?: (out: HuntResult) => void) => {
        const mine = ++seq.current;
        setRunning(true); setError(null);
        try {
            const out = await fn();
            if (mine !== seq.current) return;
            setResult(out); onDone?.(out);
        } catch (e) {
            if (mine === seq.current) { setError(message(e, 'The hunt failed')); setResult(null); }
        } finally {
            if (mine === seq.current) setRunning(false);
        }
    };

    const openSaved = (h: SavedHunt) => {
        setDraft(fromQuery(h.query)); setCurrent(h); setRuleFor(null); setNaming(null);
        execute(() => rerunHunt(h.id), out => {
            const hunt = (out as HuntResult & { hunt: SavedHunt }).hunt;
            setCurrent(hunt);
            setList(l => (l ? { ...l, items: l.items.map(x => (x.id === hunt.id ? hunt : x)) } : l));
        });
    };
    const startNew = () => { setDraft({ ...EMPTY_DRAFT, source: draft.source }); setCurrent(null); setResult(null); setRuleFor(null); setNaming(null); };
    const setSource = (source: HuntSource) => setDraft(d => ({ ...d, source, filters: [], text: '', countBy: null }));
    const setFilter = (i: number, patch: Partial<DraftFilter>) =>
        setDraft(d => ({ ...d, filters: d.filters.map((f, j) => (j === i ? { ...f, ...patch } : f)) }));
    const drill = (name: string, value: string) => {
        const next = { ...draft, countBy: null, filters: [...draft.filters, { field: name, op: 'eq' as const, value }] };
        setDraft(next);
        execute(() => runHunt(toQuery(next)));
    };

    const save = async (asNew: boolean) => {
        if (!naming) return;
        try {
            const saved = await saveHunt({ name: naming.name.trim(), description: naming.description.trim() || undefined, query },
                asNew ? undefined : current?.id);
            showToast(`Hunt “${saved.name}” saved`, 'success');
            setCurrent(saved); setNaming(null); loadList();
        } catch (e) { showToast(message(e, 'The hunt was not saved'), 'error'); }
    };
    const remove = async (h: SavedHunt) => {
        if (!window.confirm(`Delete the saved hunt “${h.name}”?${h.ruleId ? ' Its SIEM rule stays.' : ''}`)) return;
        try {
            await deleteHunt(h.id);
            if (current?.id === h.id) setCurrent(null);
            showToast('Saved hunt deleted', 'success'); loadList();
        } catch (e) { showToast(message(e, 'Nothing was deleted'), 'error'); }
    };

    if (!catalogue && !error) return <div className="space-y-3" aria-busy="true"><Skeleton variant="card" height={220} /><Skeleton variant="card" height={320} /></div>;

    return (
        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_20rem] gap-3">
            <section aria-label="Hunt" className={`${card} space-y-4 min-w-0`}>
                <div className="flex flex-wrap items-center gap-2">
                    <div className={segmented} role="group" aria-label="Search in">
                        {SOURCES.map(s => <button key={s} type="button" className={segment(draft.source === s)} aria-pressed={draft.source === s} onClick={() => setSource(s)}>{catalogue?.sources[s].label ?? s}</button>)}
                    </div>
                    <div className={segmented} role="group" aria-label="Time range">
                        {RANGES.map(r => <button key={r} type="button" className={segment(draft.range === r)} aria-pressed={draft.range === r} onClick={() => setDraft(d => ({ ...d, range: r }))}>{r}</button>)}
                    </div>
                    {current && <span className="text-xs text-gray-600 dark:text-gray-300">Saved hunt: <strong>{current.name}</strong>{unchanged ? '' : ' (changed)'}</span>}
                </div>

                <fieldset className="space-y-2"><legend className={subhead}>Where</legend>
                    {draft.filters.length === 0 && <p className="text-xs text-gray-500 dark:text-gray-400">No filters: every {info?.label.toLowerCase() ?? 'row'} in the range matches.</p>}
                    {draft.filters.map((f, i) => (
                        <div key={i} className="flex flex-wrap items-center gap-2">
                            <select aria-label={`Filter ${i + 1} field`} value={f.field} onChange={e => setFilter(i, { field: e.target.value })} className={`${field} px-2`}>
                                {fields.map(x => <option key={x.name} value={x.name}>{x.label}</option>)}</select>
                            <select aria-label={`Filter ${i + 1} condition`} value={f.op} onChange={e => setFilter(i, { op: e.target.value as DraftFilter['op'], value: e.target.value === 'exists' ? 'yes' : f.value })} className={`${field} px-2`}>
                                {OPS.map(o => <option key={o} value={o}>{OP_LABEL[o]}</option>)}</select>
                            {f.op === 'exists' ? (
                                <select aria-label={`Filter ${i + 1} value`} value={f.value} onChange={e => setFilter(i, { value: e.target.value })} className={`${field} px-2`}>
                                    <option value="yes">yes</option><option value="no">no (missing or empty)</option></select>
                            ) : (
                                <>
                                    <input aria-label={`Filter ${i + 1} value`} value={f.value} maxLength={f.op === 'in' ? 2000 : 200} list={`hunt-values-${i}`}
                                        placeholder={f.op === 'in' ? 'value, value, …' : f.op === 'regex' ? 'pattern, e.g. ^admin' : 'value'}
                                        onChange={e => setFilter(i, { value: e.target.value })} onKeyDown={e => { if (e.key === 'Enter') execute(() => runHunt(query)); }}
                                        className={`${field} w-56 px-3 ${f.op === 'regex' ? 'font-mono' : ''}`} />
                                    <datalist id={`hunt-values-${i}`}>{(fields.find(x => x.name === f.field)?.values ?? []).map(v => <option key={String(v)} value={String(v)} />)}</datalist>
                                </>
                            )}
                            <button type="button" className={`${ghostButton} h-9 px-2`} aria-label={`Remove filter ${i + 1}`} onClick={() => setDraft(d => ({ ...d, filters: d.filters.filter((_, j) => j !== i) }))}>
                                <X className="w-3.5 h-3.5" aria-hidden="true" /></button>
                        </div>
                    ))}
                    <button type="button" className={`${ghostButton} h-8`} disabled={!fields.length || draft.filters.length >= 10}
                        onClick={() => setDraft(d => ({ ...d, filters: [...d.filters, { field: fields[0].name, op: 'eq', value: '' }] }))}>
                        <Plus className="w-3.5 h-3.5" aria-hidden="true" />Add filter</button>
                </fieldset>

                <div className="flex flex-wrap items-end gap-3">
                    <label><span className={small}>Text in {info?.text ?? 'the row'}</span>
                        <input value={draft.text} maxLength={200} onChange={e => setDraft(d => ({ ...d, text: e.target.value }))}
                            onKeyDown={e => { if (e.key === 'Enter') execute(() => runHunt(query)); }} className={`${field} w-64 px-3`} /></label>
                    <label><span className={small}>Count by</span>
                        <select value={draft.countBy ?? ''} onChange={e => setDraft(d => ({ ...d, countBy: e.target.value || null }))} className={`${field} px-2`}>
                            <option value="">Don't count</option>{fields.map(x => <option key={x.name} value={x.name}>{x.label}</option>)}</select></label>
                </div>
                <p className="text-sm text-gray-700 dark:text-gray-300">{describeHunt(query, catalogue)}.</p>

                <div className="flex flex-wrap gap-2">
                    <button type="button" className={primaryButton} disabled={running} onClick={() => execute(() => runHunt(query))}>
                        <Play className="w-4 h-4" aria-hidden="true" />{running ? 'Running…' : 'Run hunt'}</button>
                    {list?.canEdit && !naming && (
                        <button type="button" className={ghostButton} onClick={() => setNaming({ name: current?.name ?? '', description: current?.description ?? '' })}>
                            <BookmarkPlus className="w-4 h-4" aria-hidden="true" />{current ? 'Save…' : 'Save hunt…'}</button>
                    )}
                    {list?.canMakeRules && current && draft.source === 'events' && !current.ruleId && (
                        <button type="button" className={ghostButton} disabled={!unchanged} title={unchanged ? undefined : 'Save the changes first'} onClick={() => setRuleFor(current)}>
                            <Workflow className="w-4 h-4" aria-hidden="true" />Make a rule…</button>
                    )}
                    {current?.ruleId && <span className="self-center text-xs text-gray-600 dark:text-gray-300">Has a SIEM rule ({current.ruleId})</span>}
                    {(current || draft.filters.length > 0 || draft.text) && <button type="button" className={ghostButton} onClick={startNew}>New hunt</button>}
                </div>

                {naming && (
                    <div className="rounded-xl border border-gray-200/80 dark:border-white/[0.08] p-3 flex flex-wrap items-end gap-2">
                        <label><span className={small}>Name</span>
                            <input value={naming.name} maxLength={120} autoFocus onChange={e => setNaming(n => n && { ...n, name: e.target.value })} className={`${field} w-64 px-3`} /></label>
                        <label><span className={small}>Description</span>
                            <input value={naming.description} maxLength={500} onChange={e => setNaming(n => n && { ...n, description: e.target.value })} className={`${field} w-72 px-3`} /></label>
                        {current && <button type="button" className={primaryButton} disabled={!naming.name.trim()} onClick={() => save(false)}>Save changes</button>}
                        <button type="button" className={current ? ghostButton : primaryButton} disabled={!naming.name.trim()} onClick={() => save(true)}>{current ? 'Save as new' : 'Save'}</button>
                        <button type="button" className={ghostButton} onClick={() => setNaming(null)}>Cancel</button>
                    </div>
                )}
                {ruleFor && <HuntRulePanel hunt={ruleFor} catalogue={catalogue} onClose={() => setRuleFor(null)} onCreated={ruleId => { setRuleFor(null); loadList(); setCurrent(c => (c ? { ...c, ruleId } : c)); }} />}

                {error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>}
                {result && !error && <HuntResults result={result} catalogue={catalogue} onDrill={drill} />}
                {!result && !error && !running && <EmptyNote icon={<Search className="w-5 h-5" />} title="Run a hunt">Pick where to look, add filters, and run it. Counts come straight from the stored data.</EmptyNote>}
            </section>

            <aside aria-label="Saved hunts" className={`${card} space-y-3 self-start`}>
                <h3 className={subhead}>Saved hunts</h3>
                {!list && !error && <Skeleton variant="card" height={120} />}
                {list && list.items.length === 0 && <p className="text-xs text-gray-500 dark:text-gray-400">{list.canEdit ? 'None yet. Build a hunt and save it to rerun it later.' : 'None yet.'}</p>}
                {list && list.items.length > 0 && (
                    <ul className="divide-y divide-gray-100 dark:divide-white/[0.05]">
                        {list.items.map(h => (
                            <li key={h.id} className={`py-2.5 flex items-start gap-2 ${current?.id === h.id ? 'bg-primary-500/[0.04] -mx-2 px-2 rounded-lg' : ''}`}>
                                <button type="button" className="min-w-0 flex-1 text-left cursor-pointer" onClick={() => openSaved(h)} aria-label={`Run saved hunt ${h.name}`}>
                                    <span className="block text-sm font-medium text-gray-900 dark:text-white">{h.name}</span>
                                    <span className="block text-xs text-gray-600 dark:text-gray-300">{describeHunt(h.query, catalogue)}</span>
                                    <span className="block text-[11px] text-gray-500 dark:text-gray-400">
                                        {h.lastRunAt ? `${(h.lastCount ?? 0).toLocaleString()} match${h.lastCount === 1 ? '' : 'es'}, run ${formatSince(h.lastRunAt)}` : 'Not run yet'}
                                        {h.ruleId ? ' · has a rule' : ''}</span>
                                </button>
                                {list.canEdit && (
                                    <button type="button" className={`${ghostButton} h-8 px-2`} aria-label={`Delete saved hunt ${h.name}`} onClick={() => remove(h)}>
                                        <Trash2 className="w-3.5 h-3.5" aria-hidden="true" /></button>
                                )}
                            </li>
                        ))}
                    </ul>
                )}
            </aside>
        </div>
    );
};
