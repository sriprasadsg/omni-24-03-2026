import React, { useId } from 'react';
import { formatShare } from '../networkData';
import { formatBitRate, periodDelta, totalOf, type TrafficSummary } from '../opsData';
import { DeltaBadge, RX, Sparkline, TX } from '../ops/OpsKpis';
import type { NodeStatus, TopologyRow } from '../topologyData';

// The four console tiles above the map: what moves now, which way, which endpoints report, and
// whether anything on the map is down. Trend lines come from GET /api/network-devices/traffic.

interface Totals { measured: number; sentBps: number; recvBps: number; links: number; segments: number; zones: number }

const label = 'text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400';
const note = 'font-mono text-[11px] text-gray-500 dark:text-gray-400 whitespace-nowrap';
const bigBase = 'font-mono tabular-nums text-[28px] leading-none font-semibold tracking-tight';
const big = `${bigBase} text-gray-900 dark:text-white`;
const unit = 'ml-1.5 font-mono text-[14px] font-medium text-gray-500 dark:text-gray-400';

const Tile: React.FC<{ title: string; meta: string; alert?: boolean; foot?: React.ReactNode; spark?: React.ReactNode; children: React.ReactNode }> = ({ title, meta, alert, foot, spark, children }) => {
    const id = useId();
    return (
        <section aria-labelledby={id} className={`rounded-2xl bg-white dark:bg-gray-800 border shadow-card p-4 flex flex-col min-w-0 min-h-[8.5rem] ${alert
            ? 'border-red-300 dark:border-red-500/45'
            : 'border-gray-200/80 dark:border-white/[0.07]'}`}>
            <div className="flex items-baseline justify-between gap-3">
                <h2 id={id} className={label}>{title}</h2>
                <span className={note}>{meta}</span>
            </div>
            <div className="mt-3">{children}</div>
            {(foot || spark) && (
                <div className="mt-auto pt-3 flex items-end justify-between gap-3">
                    <div className="min-w-0 text-[11px] text-gray-500 dark:text-gray-400">{foot}</div>
                    {spark && <div className="w-[45%] max-w-[9rem] shrink-0">{spark}</div>}
                </div>
            )}
        </section>
    );
};

const Rate: React.FC<{ bps: number | null }> = ({ bps }) => {
    if (bps == null) return <p className={big}>—</p>;
    const [num, u] = formatBitRate(bps).split(' ');
    return <p className={big}>{num}<span className={unit}>{u}</span></p>;
};

const DOT: Record<string, string> = {
    Live: 'bg-green-500', Idle: 'bg-gray-400 dark:bg-gray-500', 'Not measured': 'bg-amber-500', Down: 'bg-red-500',
};

/** One dot per endpoint, coloured by what it reports now; the label carries the counts. */
const EndpointStrip: React.FC<{ endpoints: TopologyRow[] }> = ({ endpoints }) => {
    const counts = (['Live', 'Idle', 'Not measured', 'Down'] as NodeStatus[]).map(s => [s, endpoints.filter(e => e.status === s).length] as const);
    const shown = endpoints.slice(0, 40);
    return (
        <div>
            <ul role="img" aria-label={counts.map(([s, n]) => `${n} ${s.toLowerCase()}`).join(', ')} className="flex flex-wrap gap-1">
                {shown.map(e => <li key={e.id} title={`${e.name}: ${e.status}`} className={`h-2.5 w-2.5 rounded-[3px] ${DOT[e.status ?? 'Idle']}`} />)}
                {endpoints.length > shown.length && <li className="text-[11px] leading-[10px] text-gray-500 dark:text-gray-400">+{endpoints.length - shown.length}</li>}
            </ul>
            <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1" aria-hidden="true">
                {counts.filter(([, n]) => n > 0).map(([s, n]) => (
                    <span key={s} className="inline-flex items-center gap-1"><span className={`h-1.5 w-1.5 rounded-full ${DOT[s]}`} />{n} {s.toLowerCase()}</span>
                ))}
            </p>
        </div>
    );
};

export const TopologyKpis: React.FC<{ rows: TopologyRow[]; totals: Totals; traffic: TrafficSummary | null; range: string; rangeLabel: string }> = ({ rows, totals, traffic, range, rangeLabel }) => {
    const total = totals.sentBps + totals.recvBps;
    const series = traffic?.series ?? [];
    const hasTrend = series.some(p => p.txBps != null || p.rxBps != null);
    const delta = traffic ? periodDelta(totalOf(traffic.average), totalOf(traffic.previousAverage)) : null;
    const endpoints = rows.filter(r => r.group === 'Endpoints');
    const online = endpoints.filter(r => r.status !== 'Down').length;
    const down = rows.filter(r => r.status === 'Down');
    const count = (g: string) => rows.filter(r => r.group === g).length;

    return (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
            <Tile title="Live transfer" meta="Rx + Tx · now"
                foot={traffic
                    ? <span className="inline-flex flex-wrap items-center gap-1.5"><DeltaBadge delta={delta} rangeLabel={rangeLabel} />{delta != null && <span aria-hidden="true">vs prev {range}</span>}</span>
                    : 'No trend recorded yet'}
                spark={hasTrend ? <Sparkline lines={[{ values: series.map(p => totalOf(p)), stroke: 'stroke-primary-500 dark:stroke-primary-400' }]} /> : undefined}>
                <Rate bps={totals.measured ? total : null} />
                <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">{totals.measured} of {online} online endpoint{online === 1 ? '' : 's'} measured</p>
            </Tile>

            <Tile title="Inbound / outbound" meta="split · now"
                spark={hasTrend ? <Sparkline lines={[{ values: series.map(p => p.rxBps), stroke: RX.stroke }, { values: series.map(p => p.txBps), stroke: TX.stroke }]} /> : undefined}
                foot={totals.measured ? <span className="font-mono tabular-nums">{formatShare(totals.recvBps, total)} in · {formatShare(totals.sentBps, total)} out</span> : 'Nothing measured in the last 5 min'}>
                <dl className="flex flex-wrap items-baseline gap-x-4 gap-y-1 font-mono tabular-nums">
                    {[{ s: RX, name: 'Rx', title: 'Inbound', v: totals.recvBps }, { s: TX, name: 'Tx', title: 'Outbound', v: totals.sentBps }].map(({ s, name, title, v }) => (
                        <div key={name} className="flex items-baseline gap-1.5 min-w-0">
                            <dt className="flex items-center gap-1 text-[11px] text-gray-500 dark:text-gray-400" title={title}>
                                <span className={`h-2 w-2 rounded-sm ${s.bg}`} aria-hidden="true" />{name}<span className="sr-only"> ({title})</span>
                            </dt>
                            <dd className="text-[17px] font-semibold text-gray-900 dark:text-white whitespace-nowrap">{totals.measured ? formatBitRate(v) : '—'}</dd>
                        </div>
                    ))}
                </dl>
                <div role="img" aria-label={`Inbound ${formatShare(totals.recvBps, total)}, outbound ${formatShare(totals.sentBps, total)}`}
                    className="mt-3 flex h-1.5 gap-0.5 rounded-full overflow-hidden bg-gray-100 dark:bg-white/[0.06]">
                    {total > 0 && <>
                        <span className={RX.bg} style={{ flexGrow: totals.recvBps, flexBasis: 0 }} />
                        <span className={TX.bg} style={{ flexGrow: totals.sentBps, flexBasis: 0 }} />
                    </>}
                </div>
            </Tile>

            <Tile title="Endpoints" meta="online / on map" foot={endpoints.length ? <EndpointStrip endpoints={endpoints} /> : 'No agent has checked in yet'}>
                <p className={big}>{online}<span className={unit}>/ {endpoints.length}</span></p>
            </Tile>

            <Tile title="Network" meta={`${totals.zones} zone${totals.zones === 1 ? '' : 's'} · ${totals.segments} VLAN${totals.segments === 1 ? '' : 's'}`} alert={down.length > 0}
                foot={<span className="font-mono tabular-nums">{count('Gateways')} gateways · {count('ISP')} ISP · {rows.filter(r => r.role === 'Hop').length} hops · {count('Devices')} devices · {count('Remote')} remote · {totals.links} links</span>}>
                {down.length ? (
                    <>
                        <p className={`${bigBase} text-red-700 dark:text-red-300`}>{down.length}<span className={unit}>down</span></p>
                        <p className="mt-1.5 text-xs text-red-700 dark:text-red-300 truncate" title={down.map(r => r.name).join(', ')}>{down.map(r => r.name).join(', ')}</p>
                    </>
                ) : (
                    <>
                        <p className={big}>{rows.length}<span className={unit}>nodes</span></p>
                        <p className="mt-1.5 text-xs text-green-700 dark:text-green-400">{rows.length ? 'Nothing down' : 'Nothing on the map yet'}</p>
                    </>
                )}
            </Tile>
        </div>
    );
};
