import React, { useMemo } from 'react';
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { BarChart3 } from 'lucide-react';
import { EmptyNote, Panel, useChartTheme } from '../NetworkKit';
import { formatBitRate, seriesStats, type SeriesStats, type TrafficSummary } from '../opsData';
import { RX, TX } from './OpsKpis';

const timeLabel = (ms: number, withDate: boolean) =>
    new Date(ms).toLocaleTimeString([], withDate ? { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' } : { hour: '2-digit', minute: '2-digit' });

const StatRow: React.FC<{ label: string; swatch: string; stats: SeriesStats }> = ({ label, swatch, stats }) => (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs">
        <span className="flex items-center gap-1.5 w-24 shrink-0 text-gray-600 dark:text-gray-300"><span className={`h-2 w-2 rounded-sm ${swatch}`} aria-hidden="true" />{label}</span>
        {(['min', 'max', 'p95'] as const).map(k => (
            <span key={k} className="whitespace-nowrap text-gray-500 dark:text-gray-400">
                {k} <span className="font-mono tabular-nums text-gray-800 dark:text-gray-200">{formatBitRate(stats[k])}</span>
            </span>
        ))}
    </div>
);

const ChartTooltip: React.FC<any> = ({ active, payload, label, stats }) => {
    if (!active || !payload?.length) return null;
    const point = payload[0].payload;
    return (
        <div className="rounded-xl border border-gray-200/80 dark:border-white/10 bg-white dark:bg-gray-800 shadow-lg px-3 py-2 text-xs min-w-[220px]">
            <p className="font-medium text-gray-900 dark:text-white">{new Date(label).toLocaleString()}</p>
            {[{ s: RX, v: point.rx, st: stats.rx }, { s: TX, v: point.tx, st: stats.tx }].map(({ s, v, st }) => (
                <div key={s.name} className="mt-1.5">
                    <p className="flex items-center gap-2 text-gray-700 dark:text-gray-200">
                        <span className={`h-2 w-2 rounded-sm ${s.bg}`} aria-hidden="true" />{s.name === 'Rx' ? 'Inbound (Rx)' : 'Outbound (Tx)'}
                        <span className="ml-auto pl-4 font-mono tabular-nums font-semibold">{v == null ? 'no data' : formatBitRate(v)}</span>
                    </p>
                    <p className="pl-4 font-mono tabular-nums text-[11px] text-gray-500 dark:text-gray-400">
                        min {formatBitRate(st.min)} · max {formatBitRate(st.max)} · p95 {formatBitRate(st.p95)}
                    </p>
                </div>
            ))}
        </div>
    );
};

export const ThroughputChart: React.FC<{ data: TrafficSummary; scope: string }> = ({ data, scope }) => {
    const chart = useChartTheme();
    const mode = chart.dark ? 'dark' : 'light';
    const rows = useMemo(() => data.series.map(p => ({ t: Date.parse(p.t), rx: p.rxBps, tx: p.txBps })), [data.series]);
    const stats = useMemo(() => ({ rx: seriesStats(data.series, 'rxBps'), tx: seriesStats(data.series, 'txBps') }), [data.series]);
    const hasData = rows.some(r => r.rx != null || r.tx != null);
    const withDate = data.rangeSeconds > 6 * 3600;
    const bucket = data.bucketSeconds >= 60 ? `${data.bucketSeconds / 60}-minute` : `${data.bucketSeconds}-second`;

    return (
        <Panel title="Throughput" note={`Inbound and outbound across ${scope}, ${bucket} averages of measured rates`}
            actions={
                <ul aria-label="Legend" className="flex items-center gap-4 text-xs text-gray-600 dark:text-gray-300">
                    {[RX, TX].map(s => <li key={s.name} className="flex items-center gap-1.5"><span className={`h-2.5 w-2.5 rounded-sm ${s.bg}`} aria-hidden="true" />{s.name === 'Rx' ? 'Inbound (Rx)' : 'Outbound (Tx)'}</li>)}
                    <li className="flex items-center gap-1.5"><span className="w-4 border-t border-dashed border-gray-400" aria-hidden="true" />p95</li>
                </ul>
            }>
            {hasData ? (
                <>
                    <div className="mb-3 space-y-1">
                        <StatRow label="Inbound (Rx)" swatch={RX.bg} stats={stats.rx} />
                        <StatRow label="Outbound (Tx)" swatch={TX.bg} stats={stats.tx} />
                    </div>
                    <ResponsiveContainer width="100%" height={260}>
                        <AreaChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                            <defs>
                                {[['rx', RX.hex[mode]], ['tx', TX.hex[mode]]].map(([id, color]) => (
                                    <linearGradient key={id} id={`ops-${id}`} x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor={color} stopOpacity={0.28} />
                                        <stop offset="100%" stopColor={color} stopOpacity={0.02} />
                                    </linearGradient>
                                ))}
                            </defs>
                            <CartesianGrid vertical={false} stroke={chart.grid} />
                            <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={(v: any) => timeLabel(v, withDate)}
                                tick={{ fill: chart.text, fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={48} />
                            <YAxis tickFormatter={(v: any) => formatBitRate(v)} width={72} tick={{ fill: chart.text, fontSize: 11 }} tickLine={false} axisLine={false} />
                            <Tooltip cursor={{ stroke: chart.text, strokeDasharray: '3 3' }} content={<ChartTooltip stats={stats} />} />
                            {stats.rx.p95 != null && <ReferenceLine y={stats.rx.p95} stroke={RX.hex[mode]} strokeDasharray="4 4" strokeOpacity={0.55} />}
                            {stats.tx.p95 != null && <ReferenceLine y={stats.tx.p95} stroke={TX.hex[mode]} strokeDasharray="4 4" strokeOpacity={0.55} />}
                            <Area type="monotone" dataKey="rx" name="Inbound (Rx)" stroke={RX.hex[mode]} fill="url(#ops-rx)" strokeWidth={2} connectNulls={false}
                                isAnimationActive={false} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: chart.surface }} />
                            <Area type="monotone" dataKey="tx" name="Outbound (Tx)" stroke={TX.hex[mode]} fill="url(#ops-tx)" strokeWidth={2} connectNulls={false}
                                isAnimationActive={false} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: chart.surface }} />
                        </AreaChart>
                    </ResponsiveContainer>
                </>
            ) : (
                <div className="h-[300px]">
                    <EmptyNote icon={<BarChart3 className="w-5 h-5" />} title="No transfer measured in this range">
                        A rate appears about a minute after an endpoint's agent reports its byte counters twice. History is kept for 48 hours.
                    </EmptyNote>
                </div>
            )}
        </Panel>
    );
};
