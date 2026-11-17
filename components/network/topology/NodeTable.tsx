import React, { useId, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { formatAgo } from '../networkData';
import { formatBitRate } from '../opsData';
import { RX, TX } from '../ops/OpsKpis';
import { NODE_GROUPS, type NodeGroup, type NodeStatus, type TopologyRow } from '../topologyData';

// Every node on the map, busiest first: the list alternative to the graph, and its drill-down.

type StatusFilter = 'All statuses' | 'Healthy' | 'Down' | 'Not measured';
const STATUS_FILTERS: StatusFilter[] = ['All statuses', 'Healthy', 'Down', 'Not measured'];

const STATUS_STYLE: Record<NodeStatus, { dot: string; text: string }> = {
    Live: { dot: 'bg-green-500', text: 'text-green-700 dark:text-green-400' },
    Up: { dot: 'bg-green-500', text: 'text-green-700 dark:text-green-400' },
    Idle: { dot: 'bg-gray-400', text: 'text-gray-600 dark:text-gray-300' },
    Connected: { dot: 'bg-[#2a78d6] dark:bg-[#3987e5]', text: 'text-gray-700 dark:text-gray-300' },
    Unknown: { dot: 'bg-gray-400', text: 'text-gray-600 dark:text-gray-300' },
    'Not measured': { dot: 'bg-amber-500', text: 'text-amber-700 dark:text-amber-300' },
    Down: { dot: 'bg-red-500', text: 'text-red-700 dark:text-red-300' },
};

const passes = (r: TopologyRow, f: StatusFilter) =>
    f === 'All statuses' || (f === 'Healthy' ? r.status !== 'Down' && r.status !== 'Not measured' : r.status === f);

const th = 'px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400 whitespace-nowrap';
const td = 'px-3 py-2';
const mono = 'font-mono tabular-nums text-[12.5px]';

export const NodeTable: React.FC<{ rows: TopologyRow[]; selectedId: string | null; onOpen: (id: string) => void; now: number }> = ({ rows, selectedId, onOpen, now }) => {
    const [group, setGroup] = useState<'All' | NodeGroup>('All');
    const [status, setStatus] = useState<StatusFilter>('All statuses');
    const titleId = useId();
    const shown = useMemo(() => rows.filter(r => (group === 'All' || r.group === group) && passes(r, status)), [rows, group, status]);
    const measured = rows.reduce((s, r) => s + (r.sentBps ?? 0) + (r.recvBps ?? 0), 0);

    return (
        <section aria-labelledby={titleId} className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card min-w-0">
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="flex items-baseline gap-3 min-w-0">
                    <h2 id={titleId} className="text-[15px] font-semibold text-gray-900 dark:text-white">Live nodes · Top talkers</h2>
                    <span className="font-mono text-[11px] text-gray-500 dark:text-gray-400">{shown.length}/{rows.length} nodes{measured ? ` · ${formatBitRate(measured)}` : ''}</span>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    <div role="group" aria-label="Node type" className="inline-flex h-8 p-0.5 rounded-lg border border-gray-200/80 dark:border-white/[0.08] bg-gray-50 dark:bg-white/[0.03]">
                        {(['All', ...NODE_GROUPS] as const).map(g => (
                            <button key={g} type="button" aria-pressed={group === g} onClick={() => setGroup(g)}
                                className={`px-2.5 rounded-md text-xs font-medium transition-colors ${group === g
                                    ? 'bg-white dark:bg-white/[0.08] text-gray-900 dark:text-white shadow-sm'
                                    : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white'}`}>{g}</button>
                        ))}
                    </div>
                    <label className="relative">
                        <span className="sr-only">Status</span>
                        <select value={status} onChange={e => setStatus(e.target.value as StatusFilter)}
                            className="h-8 appearance-none rounded-lg pl-3 pr-8 text-xs bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.08] text-gray-800 dark:text-gray-100">
                            {STATUS_FILTERS.map(s => <option key={s}>{s}</option>)}
                        </select>
                        <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" aria-hidden="true" />
                    </label>
                </div>
            </div>

            {/* relative: the sr-only cells are absolutely positioned and must stay inside this scroll box. */}
            <div className="relative max-h-[30rem] overflow-auto custom-scrollbar border-t border-gray-100 dark:border-white/[0.06]">
                <table className="w-full text-sm">
                    <caption className="sr-only">Nodes on the network map, the busiest first</caption>
                    <thead className="sticky top-0 z-10 bg-white dark:bg-gray-800">
                        <tr className="border-b border-gray-100 dark:border-white/[0.06]">
                            <th scope="col" className={`${th} w-10 text-right`}>#</th>
                            <th scope="col" className={th}>Node</th>
                            <th scope="col" className={th}>Via</th>
                            <th scope="col" className={th}>Role</th>
                            <th scope="col" className={th} aria-sort="descending">Transfer ↓</th>
                            <th scope="col" className={`${th} text-right`}>Links</th>
                            <th scope="col" className={`${th} text-right`}>Updated</th>
                            <th scope="col" className={th}>Status</th>
                            <th scope="col" className="w-8"><span className="sr-only">Open</span></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-white/[0.04]">
                        {shown.map((r, i) => {
                            const total = r.sentBps == null ? null : r.sentBps + (r.recvBps ?? 0);
                            const st = r.status ? STATUS_STYLE[r.status] : null;
                            return (
                                <tr key={r.id} onClick={() => onOpen(r.id)}
                                    className={`group cursor-pointer transition-colors hover:bg-gray-50/80 dark:hover:bg-white/[0.03] ${selectedId === r.id ? 'bg-primary-500/[0.06]' : ''}`}>
                                    <td className={`${td} ${mono} text-right text-gray-500 dark:text-gray-400`}>{i + 1}</td>
                                    <td className={`${td} max-w-[16rem]`}>
                                        {/* The row click is a mouse shortcut; this button is the keyboard and screen-reader path. */}
                                        <button type="button" onClick={e => { e.stopPropagation(); onOpen(r.id); }}
                                            className="max-w-full truncate text-left font-medium text-gray-900 dark:text-white hover:text-primary-700 dark:hover:text-primary-300">
                                            {r.name}
                                        </button>
                                        {r.ip && r.ip !== r.name && <span className={`${mono} ml-1 text-gray-500 dark:text-gray-400`}>{r.ip}</span>}
                                    </td>
                                    <td className={`${td} max-w-[14rem] truncate text-gray-700 dark:text-gray-300`}>
                                        {r.via ? <>{r.group === 'Remote' ? 'from ' : ''}{r.via}{r.viaCount > 1 && <span className="text-gray-500 dark:text-gray-400"> +{r.viaCount - 1}</span>}</> : '—'}
                                    </td>
                                    <td className={td}>
                                        <span className="inline-flex rounded-md border border-gray-200 dark:border-white/10 px-1.5 py-0.5 font-mono text-[11px] uppercase text-gray-700 dark:text-gray-300">{r.role}</span>
                                    </td>
                                    <td className={`${td} whitespace-nowrap`}>
                                        {total == null ? <span className="text-gray-500 dark:text-gray-400">—</span> : (
                                            <span className="inline-flex items-center gap-2.5">
                                                <span className={`${mono} w-[5.5rem] text-gray-900 dark:text-white`}>{formatBitRate(total)}</span>
                                                <span aria-hidden="true" className="flex h-1.5 w-14 gap-px rounded-full overflow-hidden bg-gray-100 dark:bg-white/[0.06]">
                                                    {total > 0 && <>
                                                        <span className={RX.bg} style={{ flexGrow: r.recvBps ?? 0, flexBasis: 0 }} />
                                                        <span className={TX.bg} style={{ flexGrow: r.sentBps ?? 0, flexBasis: 0 }} />
                                                    </>}
                                                </span>
                                                <span className="sr-only">(in {formatBitRate(r.recvBps)}, out {formatBitRate(r.sentBps)})</span>
                                            </span>
                                        )}
                                    </td>
                                    <td className={`${td} ${mono} text-right text-gray-700 dark:text-gray-300`}>{r.links}</td>
                                    <td className={`${td} ${mono} text-right whitespace-nowrap text-gray-600 dark:text-gray-400`}>
                                        {r.updated && !Number.isNaN(Date.parse(r.updated)) ? formatAgo(Date.parse(r.updated), now) : '—'}
                                    </td>
                                    <td className={`${td} whitespace-nowrap`}>
                                        {st ? <span className={`inline-flex items-center gap-1.5 text-[12.5px] font-medium ${st.text}`}><span className={`h-1.5 w-1.5 rounded-full ${st.dot}`} aria-hidden="true" />{r.status}</span>
                                            : <span className="text-[12.5px] text-gray-500 dark:text-gray-400">Added by the map</span>}
                                    </td>
                                    <td className="pr-3 text-gray-400 group-hover:text-gray-600 dark:group-hover:text-gray-300"><ChevronRight className="w-4 h-4" aria-hidden="true" /></td>
                                </tr>
                            );
                        })}
                        {shown.length === 0 && (
                            <tr><td colSpan={9} className="px-4 py-10 text-center text-gray-500 dark:text-gray-400">{rows.length ? 'No node matches these filters.' : 'Nothing on the map yet.'}</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </section>
    );
};
