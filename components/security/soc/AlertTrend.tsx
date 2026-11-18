import React, { useMemo } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { BarChart3 } from 'lucide-react';
import { EmptyNote, Panel, useChartTheme } from '../../network/NetworkKit';
import { SEVERITY_META, TREND_BANDS, type Severity, type SocRange, type SocSummary } from './socData';
import { SeverityIcon } from './SocKit';

interface Row { t: number; critical: number; high: number; medium: number; low: number; total: number }

const tickFormat = (range: SocRange) => (t: number) => {
    const d = new Date(t);
    if (range === '30d') return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    if (range === '7d') return d.toLocaleDateString(undefined, { weekday: 'short', hour: '2-digit' });
    return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
};

const bucketLabel = (t: number, seconds: number) => {
    const from = new Date(t), to = new Date(t + seconds * 1000);
    const opts: Intl.DateTimeFormatOptions = seconds >= 86400
        ? { month: 'short', day: 'numeric' }
        : { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' };
    return seconds >= 86400 ? from.toLocaleDateString(undefined, opts) : `${from.toLocaleString(undefined, opts)} – ${to.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}`;
};

const TrendTooltip: React.FC<{ active?: boolean; payload?: { payload: Row }[]; bucketSeconds: number }> = ({ active, payload, bucketSeconds }) => {
    if (!active || !payload?.length) return null;
    const row = payload[0].payload;
    return (
        <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200/80 dark:border-white/10 shadow-lg px-3 py-2 text-xs">
            <p className="font-medium text-gray-900 dark:text-white">{bucketLabel(row.t, bucketSeconds)}</p>
            <ul className="mt-1.5 space-y-1">
                {TREND_BANDS.map(s => (
                    <li key={s} className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
                        <span className={`h-2 w-2 rounded-sm ${SEVERITY_META[s].swatch}`} aria-hidden="true" />
                        <span className="flex-1">{s === 'low' ? 'Low / info' : SEVERITY_META[s].label}</span>
                        <span className="font-mono tabular-nums">{row[s as keyof Row]}</span>
                    </li>
                ))}
            </ul>
            <p className="mt-1.5 pt-1.5 border-t border-gray-100 dark:border-white/[0.06] flex justify-between text-gray-600 dark:text-gray-300">
                <span>Total</span><span className="font-mono tabular-nums">{row.total}</span>
            </p>
        </div>
    );
};

/** New alerts per time bucket, stacked by severity, with a legend, totals and a written summary. */
export const AlertTrend: React.FC<{ data: SocSummary; rangeLabel: string }> = ({ data, rangeLabel }) => {
    const theme = useChartTheme();
    const rows: Row[] = useMemo(() => data.trend.map(p => {
        const low = p.low + p.info;
        return { t: Date.parse(p.t), critical: p.critical, high: p.high, medium: p.medium, low, total: p.critical + p.high + p.medium + low };
    }), [data.trend]);
    const totals = TREND_BANDS.reduce((acc, s) => ({ ...acc, [s]: rows.reduce((a, r) => a + (r[s as keyof Row] as number), 0) }), {} as Record<Severity, number>);
    const all = rows.reduce((a, r) => a + r.total, 0);
    const busiest = rows.reduce<Row | null>((best, r) => (r.total > (best?.total ?? 0) ? r : best), null);

    return (
        <Panel title="Alert trend" note={`New alerts in the last ${rangeLabel}, by severity`}>
            <ul className="flex flex-wrap gap-x-5 gap-y-1.5 text-[13px]" aria-label="Legend">
                {TREND_BANDS.map(s => (
                    <li key={s} className="flex items-center gap-1.5 text-gray-700 dark:text-gray-300">
                        <span className={`h-2.5 w-2.5 rounded-sm ${SEVERITY_META[s].swatch}`} aria-hidden="true" />
                        <SeverityIcon severity={s} className="w-3 h-3" />
                        {s === 'low' ? 'Low / info' : SEVERITY_META[s].label}
                        <span className="font-mono tabular-nums text-gray-500 dark:text-gray-400">{totals[s]}</span>
                    </li>
                ))}
            </ul>
            {all === 0 ? (
                <EmptyNote icon={<BarChart3 className="w-5 h-5" />} title={`No new alerts in the last ${rangeLabel}`}>
                    Alerts raised earlier and still open are in the queue.
                </EmptyNote>
            ) : (
                <>
                    <div className="mt-3 h-[240px]" aria-hidden="true">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: -18 }} barCategoryGap="18%">
                                <CartesianGrid vertical={false} stroke={theme.grid} />
                                <XAxis dataKey="t" tickFormatter={tickFormat(data.range)} tick={{ fill: theme.text, fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={24} />
                                <YAxis allowDecimals={false} tick={{ fill: theme.text, fontSize: 11 }} tickLine={false} axisLine={false} width={44} />
                                <Tooltip cursor={{ fill: theme.cursor }} content={<TrendTooltip bucketSeconds={data.bucketSeconds} />} />
                                {TREND_BANDS.map(s => (
                                    <Bar key={s} dataKey={s} stackId="sev" fill={SEVERITY_META[s].hex} stroke={theme.surface} strokeWidth={1}
                                        isAnimationActive={false} maxBarSize={28} />
                                ))}
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                    <p className="mt-2 text-xs text-gray-600 dark:text-gray-300">
                        {all} new alert{all === 1 ? '' : 's'}: {TREND_BANDS.filter(s => totals[s]).map(s => `${totals[s]} ${s === 'low' ? 'low or info' : SEVERITY_META[s].label.toLowerCase()}`).join(', ')}.
                        {busiest && ` Busiest: ${bucketLabel(busiest.t, data.bucketSeconds)} (${busiest.total}).`}
                    </p>
                </>
            )}
        </Panel>
    );
};
