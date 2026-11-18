import React, { useEffect, useMemo, useState } from 'react';
import { ExternalLink, FileText, Grid3x3, ShieldCheck, Table2 } from 'lucide-react';
import { authFetch } from '../../../services/apiService';
import { EmptyNote } from '../../network/NetworkKit';
import { fetchCoverage, type CoverageLevel, type CoverageTechnique, type MitreCoverage, type SocRange } from './socData';
import { segment, segmented, subhead } from './SocKit';

// Coverage is an ordinal scale on one hue (blue ramp steps 250/550 in light, 600/350 in dark, validated with the
// dataviz validator --ordinal). Every level also has its own icon, border and label, so colour is never alone.
const LEVEL: Record<CoverageLevel, { label: string; cell: string; icon: React.ElementType | null }> = {
    detected: { label: 'Detected on your endpoints', icon: ShieldCheck,
        cell: 'bg-[#1c5cab] text-white border-[#1c5cab] dark:bg-[#5598e7] dark:text-gray-950 dark:border-[#5598e7]' },
    rule: { label: 'SIEM rule waiting for its logs', icon: FileText,
        cell: 'bg-[#86b6ef] text-gray-900 border-dashed border-[#1c5cab] dark:bg-[#184f95] dark:text-white dark:border-[#5598e7]' },
    none: { label: 'Not covered', icon: null,
        cell: 'bg-gray-50 text-gray-600 border-gray-200 dark:bg-white/[0.03] dark:text-gray-400 dark:border-white/10' },
};
const attackUrl = (id: string) => `https://attack.mitre.org/techniques/${id.replace('.', '/')}/`;

const Detail: React.FC<{ t: CoverageTechnique | null; tactic?: string; rangeLabel: string; siemNote: string }> = ({ t, tactic, rangeLabel, siemNote }) => {
    if (!t) return <p className="text-sm text-gray-500 dark:text-gray-400">Point at or pick a technique to see what covers it.</p>;
    return (
        <div className="space-y-3 text-[13px]">
            <div>
                <p className={subhead}>{tactic}</p>
                <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{t.id} {t.name !== t.id && t.name}</p>
                <p className="mt-0.5 text-xs text-gray-600 dark:text-gray-300">{LEVEL[t.level].label}{t.subTechniques.length > 0 && ` · includes ${t.subTechniques.join(', ')}`}</p>
                {t.id !== t.name && /^T\d{4}/.test(t.id) && (
                    <a href={attackUrl(t.id)} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-primary-700 dark:text-primary-300 hover:underline">
                        About this technique on attack.mitre.org<ExternalLink className="w-3 h-3" aria-hidden="true" />
                    </a>
                )}
            </div>
            <div>
                <p className={subhead}>Endpoint detections</p>
                {t.detections.length === 0 ? <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">No built-in detection looks for this.</p> : (
                    <ul className="mt-1 space-y-1">
                        {t.detections.map(d => (
                            <li key={`${d.type}-${d.technique}`} className="text-gray-800 dark:text-gray-200">
                                <span className="font-medium">{d.label}</span> ({d.technique}): {d.what}.
                                <span className="block text-xs text-gray-600 dark:text-gray-300">{d.endpoints ? `Runs on ${d.endpoints} endpoint${d.endpoints === 1 ? '' : 's'}` : 'No endpoint runs this check, so it does not count'}</span>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
            <div>
                <p className={subhead}>SIEM rules</p>
                {t.ruleCount === 0 ? <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">None name this technique.</p> : (<>
                    <ul className="mt-1 space-y-0.5">
                        {t.rules.map(r => <li key={`${r.name}-${r.technique}`} className="text-gray-800 dark:text-gray-200">{r.name} <span className="text-xs text-gray-500 dark:text-gray-400">({r.technique}{r.library ? ', platform library' : ''}{r.state ? ` · ${r.state}` : ''})</span></li>)}
                    </ul>
                    {t.ruleCount > t.rules.length && <p className="text-xs text-gray-500 dark:text-gray-400">and {t.ruleCount - t.rules.length} more</p>}
                    <p className="mt-1 text-xs text-gray-600 dark:text-gray-300">{siemNote}</p>
                </>)}
            </div>
            <div>
                <p className={subhead}>Alerts in the last {rangeLabel}</p>
                <p className="mt-1 text-gray-800 dark:text-gray-200">{t.seen ? `${t.seen} alert${t.seen === 1 ? '' : 's'}, ${t.active} still active` : 'None'}</p>
            </div>
        </div>
    );
};

/** ATT&CK coverage: which techniques the endpoints' detections cover, which only a SIEM rule names, what alerts named. */
export const CoverageTab: React.FC<{ range: SocRange; rangeLabel: string }> = ({ range, rangeLabel }) => {
    const [data, setData] = useState<MitreCoverage | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [picked, setPicked] = useState<string | null>(null);
    const [hovered, setHovered] = useState<string | null>(null);
    const [asTable, setAsTable] = useState(false);

    useEffect(() => {
        let alive = true;
        fetchCoverage(authFetch, range).then(d => { if (alive) { setData(d); setError(null); } })
            .catch(e => { if (alive) setError(e instanceof Error ? e.message : 'ATT&CK coverage could not be loaded'); });
        return () => { alive = false; };
    }, [range]);

    const index = useMemo(() => {
        const out: Record<string, { t: CoverageTechnique; tactic: string }> = {};
        data?.tactics.forEach(tac => tac.techniques.forEach(t => { out[`${tac.id}:${t.id}`] = { t, tactic: tac.name }; }));
        return out;
    }, [data]);

    if (error && !data) return <p role="alert" className="p-5 text-sm text-red-700 dark:text-red-300">{error}</p>;
    if (!data) return <p className="p-5 text-sm text-gray-500 dark:text-gray-400">Loading ATT&CK coverage…</p>;
    const shown = index[hovered ?? picked ?? ''] ?? null;
    const siemNote = data.siemLogs
        ? `The SIEM recognised ${data.siemLogs} event${data.siemLogs === 1 ? '' : 's'} from you in the last ${data.siemLogDays} days. A running rule counts as coverage; one waiting for its log source does not.`
        : `The SIEM has recognised no events from you in the last ${data.siemLogDays} days, so these rules cannot fire yet.`;
    const { totals } = data;

    return (
        <section aria-label="ATT&CK coverage" className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card min-w-0">
            <div className="p-4 flex flex-wrap items-start justify-between gap-3 border-b border-gray-200/70 dark:border-white/[0.07]">
                <div className="min-w-0">
                    <h2 className="text-[15px] font-semibold text-gray-900 dark:text-white">MITRE ATT&CK coverage</h2>
                    <p className="mt-1 text-[13px] text-gray-700 dark:text-gray-300">
                        <span className="font-semibold tabular-nums">{totals.detected}</span> of {totals.techniques} techniques are detected on your {data.endpoints} endpoint{data.endpoints === 1 ? '' : 's'};{' '}
                        <span className="font-semibold tabular-nums">{totals.ruleOnly}</span> more have a SIEM rule only;{' '}
                        <span className="font-semibold tabular-nums">{totals.seen}</span> were named by alerts in the last {rangeLabel}.
                    </p>
                </div>
                <div role="group" aria-label="View" className={segmented}>
                    <button type="button" aria-pressed={!asTable} onClick={() => setAsTable(false)} className={segment(!asTable)}><Grid3x3 className="inline w-4 h-4 mr-1" aria-hidden="true" />Matrix</button>
                    <button type="button" aria-pressed={asTable} onClick={() => setAsTable(true)} className={segment(asTable)}><Table2 className="inline w-4 h-4 mr-1" aria-hidden="true" />Table</button>
                </div>
            </div>
            <ul className="px-4 pt-3 flex flex-wrap gap-x-5 gap-y-2" aria-label="Legend">
                {(Object.keys(LEVEL) as CoverageLevel[]).map(l => {
                    const Icon = LEVEL[l].icon;
                    return (
                        <li key={l} className="flex items-center gap-1.5 text-xs text-gray-700 dark:text-gray-300">
                            <span className={`inline-grid place-items-center h-4 w-6 rounded border ${LEVEL[l].cell}`} aria-hidden="true">{Icon && <Icon className="w-3 h-3" />}</span>{LEVEL[l].label}
                        </li>
                    );
                })}
                <li className="text-xs text-gray-700 dark:text-gray-300">A number in a cell: alerts that named it in the last {rangeLabel}</li>
            </ul>
            {totals.techniques === 0 ? <EmptyNote icon={<Grid3x3 className="w-5 h-5" />} title="No techniques to show" /> : (
                <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_19rem] gap-0">
                    <div className="min-w-0 p-4">
                        {asTable ? (
                            <div className="overflow-x-auto custom-scrollbar">
                                <table className="w-full text-[13px]">
                                    <thead><tr className="text-left text-xs text-gray-500 dark:text-gray-400">
                                        <th scope="col" className="py-1.5 pr-3 font-medium">Tactic</th><th scope="col" className="py-1.5 pr-3 font-medium">Technique</th>
                                        <th scope="col" className="py-1.5 pr-3 font-medium">Coverage</th><th scope="col" className="py-1.5 pr-3 font-medium">Detections</th>
                                        <th scope="col" className="py-1.5 pr-3 font-medium">SIEM rules</th><th scope="col" className="py-1.5 font-medium">Alerts</th>
                                    </tr></thead>
                                    <tbody className="divide-y divide-gray-100 dark:divide-white/[0.05]">
                                        {data.tactics.flatMap(tac => tac.techniques.map(t => (
                                            <tr key={`${tac.id}:${t.id}`} className="text-gray-800 dark:text-gray-200">
                                                <td className="py-1.5 pr-3">{tac.name}</td><td className="py-1.5 pr-3">{t.id} {t.name !== t.id && t.name}</td>
                                                <td className="py-1.5 pr-3">{LEVEL[t.level].label}</td>
                                                <td className="py-1.5 pr-3">{t.detections.filter(d => d.endpoints).map(d => d.label).join(', ') || '—'}</td>
                                                <td className="py-1.5 pr-3 tabular-nums">{t.ruleCount || '—'}</td><td className="py-1.5 tabular-nums">{t.seen || '—'}</td>
                                            </tr>
                                        )))}
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            <div>
                                {/* Tactic columns wrap in ATT&CK order, so every tactic is on screen at any width. */}
                                <div className="grid gap-x-2 gap-y-4 grid-cols-[repeat(auto-fill,minmax(8.5rem,1fr))]" onMouseLeave={() => setHovered(null)}>
                                    {data.tactics.map(tac => {
                                        const covered = tac.techniques.filter(t => t.level === 'detected').length;
                                        return (
                                            <div key={tac.id} className="min-w-0" role="group" aria-label={`${tac.name}: ${covered} of ${tac.techniques.length} detected`}>
                                                <p className="text-[12px] font-semibold text-gray-900 dark:text-white leading-tight min-h-[2rem]">{tac.name}</p>
                                                <p className="text-[11px] text-gray-500 dark:text-gray-400 mb-1.5 tabular-nums">{covered}/{tac.techniques.length} detected</p>
                                                <ul className="space-y-[2px]">
                                                    {tac.techniques.map(t => {
                                                        const key = `${tac.id}:${t.id}`;
                                                        const Icon = LEVEL[t.level].icon;
                                                        return (
                                                            <li key={t.id}>
                                                                <button type="button" onClick={() => setPicked(key)} onMouseEnter={() => setHovered(key)}
                                                                    onFocus={() => setHovered(key)} onBlur={() => setHovered(null)} aria-pressed={picked === key}
                                                                    aria-label={`${t.id} ${t.name}: ${LEVEL[t.level].label}${t.seen ? `, ${t.seen} alerts` : ''}`}
                                                                    className={`w-full text-left rounded-md border px-1.5 py-1 transition-shadow ${LEVEL[t.level].cell} ${picked === key ? 'ring-2 ring-offset-1 ring-primary-500 dark:ring-offset-gray-800' : 'hover:ring-1 hover:ring-primary-400'}`}>
                                                                    <span className="flex items-center gap-1 text-[10px] font-mono opacity-90">{Icon && <Icon className="w-3 h-3" aria-hidden="true" />}{t.id}
                                                                        {t.seen > 0 && <span className="ml-auto font-sans font-semibold tabular-nums">{t.seen}</span>}</span>
                                                                    <span className="block text-[11px] leading-snug line-clamp-2">{t.name}</span>
                                                                </button>
                                                            </li>
                                                        );
                                                    })}
                                                </ul>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}
                    </div>
                    <aside aria-label="Technique details" aria-live="polite" className="border-t xl:border-t-0 xl:border-l border-gray-200/70 dark:border-white/[0.07] p-4">
                        <div className="xl:sticky xl:top-4"><Detail t={shown?.t ?? null} tactic={shown?.tactic} rangeLabel={rangeLabel} siemNote={siemNote} /></div>
                    </aside>
                </div>
            )}
            <div className="px-4 pb-4">
                <p className={subhead}>Detections and where they run</p>
                <ul className="mt-1.5 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1 text-[13px] text-gray-800 dark:text-gray-200">
                    {data.checks.map(c => (
                        <li key={c.type}>{c.label}: {c.endpoints ? `${c.endpoints} endpoint${c.endpoints === 1 ? '' : 's'}` : 'no endpoint'}
                            <span className="text-xs text-gray-500 dark:text-gray-400"> · {c.techniques.length ? c.techniques.join(', ') : 'not an ATT&CK technique'}</span></li>
                    ))}
                </ul>
            </div>
        </section>
    );
};
