import React from 'react';
import { Filter } from 'lucide-react';
import { EmptyNote, ghostButton } from '../../network/NetworkKit';
import { SEVERITIES, formatWhen, type Severity } from './socData';
import { SeverityBadge, subhead } from './SocKit';
import { COLUMNS, RANGE_LABEL, type HuntCatalogue, type HuntGroup, type HuntResult, type HuntRow } from './huntData';

const cell = (row: HuntRow, key: string): string => {
    const v = key === 'endpoint' ? row.hostname || row.agentId : row[key];
    return v === null || v === undefined || v === '' ? '—' : String(v);
};

/** A hunt's answer: the total (the same count the database gives), the top groups when counting, the newest rows. */
export const HuntResults: React.FC<{
    result: HuntResult; catalogue: HuntCatalogue | null; onDrill: (field: string, value: string) => void;
}> = ({ result, catalogue, onDrill }) => {
    const q = result.query;
    const countLabel = q.countBy ? catalogue?.sources[q.source].fields.find(f => f.name === q.countBy)?.label ?? q.countBy : null;
    const top = result.groups[0]?.count || 1;
    const columns = COLUMNS[q.source];
    const groupName = (g: HuntGroup) => (g.value === null || g.value === '' ? '(none)' : g.label ? `${g.label}` : String(g.value));

    return (
        <div className="space-y-4">
            <p className="text-sm text-gray-800 dark:text-gray-200" role="status">
                <strong className="tabular-nums">{result.total.toLocaleString()}</strong> match{result.total === 1 ? '' : 'es'} in the last {RANGE_LABEL[q.range]}
                <span className="text-xs text-gray-500 dark:text-gray-400"> · counted in {result.tookMs} ms, {formatWhen(result.until)}</span>
            </p>

            {q.countBy && (
                <section aria-label={`Counted by ${countLabel}`}>
                    <h4 className={subhead}>By {countLabel}{result.groupCount > result.groups.length ? ` · top ${result.groups.length} of ${result.groupCount}` : ` · ${result.groupCount} value${result.groupCount === 1 ? '' : 's'}`}</h4>
                    {result.groups.length === 0 ? <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">No values.</p> : (
                        <ul className="mt-2 space-y-1">
                            {result.groups.map(g => (
                                <li key={String(g.value)} className="flex items-center gap-3 text-[13px]">
                                    <span className="w-56 shrink-0 truncate font-mono text-[12px] text-gray-900 dark:text-white" title={g.label ? `${g.label} (${g.value})` : String(g.value)}>{groupName(g)}</span>
                                    <span className="flex-1 h-2 rounded-full bg-gray-100 dark:bg-white/[0.06]" aria-hidden="true">
                                        <span className="block h-2 rounded-full bg-primary-500/70" style={{ width: `${Math.max(2, (g.count / top) * 100)}%` }} />
                                    </span>
                                    <span className="w-16 text-right tabular-nums text-gray-800 dark:text-gray-200">{g.count.toLocaleString()}</span>
                                    {g.value !== null && g.value !== '' && (
                                        <button type="button" className={`${ghostButton} h-7 px-2`} title={`Only ${groupName(g)}`} aria-label={`Filter to ${countLabel} ${groupName(g)}`}
                                            onClick={() => onDrill(q.countBy as string, String(g.value))}>
                                            <Filter className="w-3.5 h-3.5" aria-hidden="true" />
                                        </button>
                                    )}
                                </li>
                            ))}
                        </ul>
                    )}
                </section>
            )}

            {result.rows.length === 0 ? (
                <EmptyNote icon={<Filter className="w-5 h-5" />} title="Nothing matched">Widen the time range or remove a filter.</EmptyNote>
            ) : (
                <section aria-label="Matching rows">
                    <h4 className={subhead}>{result.total > result.rows.length ? `Newest ${result.rows.length} of ${result.total.toLocaleString()}` : 'Matches'}, newest first</h4>
                    <div className="mt-2 overflow-x-auto">
                        <table className="w-full text-left text-[13px]">
                            <thead className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
                                <tr><th scope="col" className="py-1.5 pr-3 font-semibold whitespace-nowrap">Time</th>
                                    {columns.map(c => <th key={c.key} scope="col" className="py-1.5 pr-3 font-semibold whitespace-nowrap">{c.label}</th>)}</tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 dark:divide-white/[0.05]">
                                {result.rows.map((r, i) => (
                                    <tr key={`${r.time}-${i}`} className="align-top">
                                        <td className="py-1.5 pr-3 whitespace-nowrap tabular-nums text-gray-600 dark:text-gray-300">{formatWhen(r.time)}</td>
                                        {columns.map(c => (
                                            <td key={c.key} className={`py-1.5 pr-3 text-gray-900 dark:text-gray-100 ${c.mono ? 'font-mono text-[12px]' : ''} ${c.wide ? 'min-w-[16rem] break-words' : 'whitespace-nowrap'}`}>
                                                {c.key === 'severity' && SEVERITIES.includes(String(r.severity).toLowerCase() as Severity)
                                                    ? <SeverityBadge severity={String(r.severity).toLowerCase() as Severity} /> : cell(r, c.key)}
                                            </td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </section>
            )}
        </div>
    );
};
