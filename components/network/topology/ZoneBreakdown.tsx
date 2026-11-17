import React, { useId } from 'react';
import { AlertTriangle } from 'lucide-react';
import { formatBitRate } from '../opsData';
import { RX, TX } from '../ops/OpsKpis';
import type { Destination, ZoneShare } from '../topologyData';

// Each zone's share of the transfer measured now (split into inbound and outbound), its nodes and
// outages (a zone is a filter for the map and the node table), then the hosts endpoints connect to.

const pct = (part: number, whole: number) => {
    if (!whole) return '—';
    const v = (part / whole) * 100;
    return v > 0 && v < 0.1 ? '<0.1%' : `${v.toFixed(1)}%`;
};

export const ZoneBreakdown: React.FC<{ zones: ZoneShare[]; zone: string; onZone: (zone: string) => void; destinations: Destination[]; onOpen: (id: string) => void }> = ({ zones, zone, onZone, destinations, onOpen }) => {
    const id = useId();
    const total = zones.reduce((s, z) => s + z.sentBps + z.recvBps, 0);
    return (
        <section aria-labelledby={id} className="h-full flex flex-col rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card min-w-0">
            <div className="flex items-baseline gap-3 px-4 pt-3.5 pb-2">
                <h2 id={id} className="text-[15px] font-semibold text-gray-900 dark:text-white">Zone distribution</h2>
                <span className="font-mono text-[11px] text-gray-500 dark:text-gray-400">{total ? `${formatBitRate(total)} measured` : 'no transfer measured'}</span>
            </div>
            <div className="flex-1 overflow-y-auto px-2 pb-2 custom-scrollbar">
            <ul>
                {zones.map(z => {
                    const moved = z.sentBps + z.recvBps;
                    const active = zone === z.zone;
                    return (
                        <li key={z.zone}>
                            <button type="button" aria-pressed={active} onClick={() => onZone(active ? '' : z.zone)}
                                className={`w-full rounded-xl px-2.5 py-2.5 text-left transition-colors ${active
                                    ? 'bg-primary-500/[0.08] ring-1 ring-inset ring-primary-500/30'
                                    : 'hover:bg-gray-50 dark:hover:bg-white/[0.03]'}`}>
                                <span className="flex items-baseline justify-between gap-3">
                                    <span className="min-w-0 truncate">
                                        <span className="text-[13.5px] font-semibold text-gray-900 dark:text-white">{z.zone}</span>
                                        <span className="ml-2 text-[11px] text-gray-500 dark:text-gray-400">
                                            {z.endpoints ? `${z.endpoints} endpoint${z.endpoints === 1 ? '' : 's'}` : `${z.nodes} node${z.nodes === 1 ? '' : 's'}`}
                                            {z.vlans.length ? ` · VLAN ${z.vlans.join(', ')}` : ''}
                                        </span>
                                    </span>
                                    <span className="font-mono tabular-nums text-[13px] font-semibold text-gray-900 dark:text-white">{pct(moved, total)}</span>
                                </span>
                                {/* Track = all transfer measured now; the filled part is this zone's, split Rx | Tx. */}
                                <span aria-hidden="true" className="mt-2 flex h-1.5 rounded-full overflow-hidden bg-gray-100 dark:bg-white/[0.06]">
                                    {total > 0 && moved > 0 && <>
                                        <span className={RX.bg} style={{ width: `${(z.recvBps / total) * 100}%` }} />
                                        <span className={TX.bg} style={{ width: `${(z.sentBps / total) * 100}%` }} />
                                    </>}
                                </span>
                                <span className="mt-1.5 flex items-center justify-between gap-3 text-[11px] text-gray-500 dark:text-gray-400">
                                    <span className="font-mono tabular-nums truncate">
                                        {moved ? `↓ ${formatBitRate(z.recvBps)} · ↑ ${formatBitRate(z.sentBps)}` : 'No live transfer'}
                                    </span>
                                    <span className="shrink-0 inline-flex items-center gap-2">
                                        {z.nodes} node{z.nodes === 1 ? '' : 's'}
                                        {z.down > 0 && (
                                            <span className="inline-flex items-center gap-0.5 font-medium text-red-700 dark:text-red-300">
                                                {z.down} down<AlertTriangle className="w-3 h-3" aria-hidden="true" />
                                            </span>
                                        )}
                                    </span>
                                </span>
                            </button>
                        </li>
                    );
                })}
                {zones.length === 0 && <li className="px-2.5 py-8 text-center text-sm text-gray-500 dark:text-gray-400">No zones yet.</li>}
            </ul>

            <section aria-labelledby={`${id}-dest`} className="mt-2 mx-2.5 pt-3 border-t border-gray-100 dark:border-white/[0.06]">
                <h3 id={`${id}-dest`} className="flex items-baseline justify-between gap-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400">
                    Latest connections<span className="font-mono normal-case tracking-normal font-normal">open · by host</span>
                </h3>
                {destinations.length ? (
                    <ul className="mt-2 -mx-2.5">
                        {destinations.map(d => (
                            <li key={d.id}>
                                <button type="button" onClick={() => onOpen(d.id)}
                                    className="w-full flex items-center justify-between gap-3 rounded-lg px-2.5 py-1.5 text-left hover:bg-gray-50 dark:hover:bg-white/[0.03]">
                                    <span className="min-w-0">
                                        <span className="block font-mono text-[12.5px] text-gray-900 dark:text-white truncate">{d.name}{d.ports.length ? <span className="text-gray-500 dark:text-gray-400">:{d.ports.join(',')}</span> : null}</span>
                                        <span className="block text-[11px] text-gray-500 dark:text-gray-400 truncate">{d.processes.join(', ') || 'process not reported'} · from {d.from.join(', ')}</span>
                                    </span>
                                    <span className="shrink-0 font-mono tabular-nums text-[12px] text-gray-700 dark:text-gray-300">{d.connections} open</span>
                                </button>
                            </li>
                        ))}
                    </ul>
                ) : (
                    <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">None reported. Outbound connections come from the agent's Web Monitor; the Windows agent does not report them yet.</p>
                )}
            </section>
            </div>
            <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-gray-100 dark:border-white/[0.06] text-[11px] text-gray-500 dark:text-gray-400">
                <span className="flex items-center gap-3">
                    <span className="inline-flex items-center gap-1.5"><span className={`h-2 w-2 rounded-sm ${RX.bg}`} aria-hidden="true" />Rx share</span>
                    <span className="inline-flex items-center gap-1.5"><span className={`h-2 w-2 rounded-sm ${TX.bg}`} aria-hidden="true" />Tx share</span>
                </span>
                <span>{zone ? <button type="button" onClick={() => onZone('')} className="font-medium text-primary-700 dark:text-primary-300 hover:underline">Show all zones</button> : 'Pick a zone to filter'}</span>
            </div>
        </section>
    );
};
