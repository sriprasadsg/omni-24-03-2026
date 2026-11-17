import React, { useId } from 'react';
import { Activity, ArrowDownLeft, ArrowDownRight, ArrowUpRight, Gauge, PackageX } from 'lucide-react';
import { formatShare } from '../networkData';
import { formatBitRate, periodDelta, totalOf, type TrafficSummary } from '../opsData';

// Tx and Rx keep the platform's sent/received colours (NetworkKit SERIES, validated in both themes).
export const TX = { name: 'Tx', hex: { light: '#0891B2', dark: '#0EA5C4' }, stroke: 'stroke-[#0891B2] dark:stroke-[#0EA5C4]', bg: 'bg-[#0891B2] dark:bg-[#0EA5C4]' };
export const RX = { name: 'Rx', hex: { light: '#eb6834', dark: '#d95926' }, stroke: 'stroke-[#eb6834] dark:stroke-[#d95926]', bg: 'bg-[#eb6834] dark:bg-[#d95926]' };

/** Lines sharing one y scale; gaps where a value is null. Decorative: the tile states the numbers. */
export const Sparkline: React.FC<{ lines: { values: (number | null)[]; stroke: string }[]; className?: string }> = ({ lines, className = 'h-8' }) => {
    const max = Math.max(1, ...lines.flatMap(l => l.values.filter((v): v is number => v != null)));
    const path = (values: (number | null)[]) => values.map((v, i) => {
        if (v == null) return '';
        const x = values.length > 1 ? (i / (values.length - 1)) * 100 : 50;
        const y = 26 - (v / max) * 24;
        return `${i === 0 || values[i - 1] == null ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(' ');
    return (
        <svg viewBox="0 0 100 28" preserveAspectRatio="none" className={`w-full overflow-visible ${className}`} aria-hidden="true">
            {lines.map((l, i) => <path key={i} d={path(l.values)} fill="none" strokeWidth={1.5} vectorEffect="non-scaling-stroke" className={l.stroke} />)}
        </svg>
    );
};

export const DeltaBadge: React.FC<{ delta: number | null; rangeLabel: string }> = ({ delta, rangeLabel }) => {
    if (delta == null) return <span className="text-[11px] text-gray-500 dark:text-gray-400">No earlier data</span>;
    const up = delta >= 0;
    const Icon = up ? ArrowUpRight : ArrowDownRight;
    return (
        <span title={`Average over this ${rangeLabel} against the ${rangeLabel} before it`}
            className="inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-[11px] font-mono tabular-nums bg-gray-100 dark:bg-white/[0.06] text-gray-700 dark:text-gray-300">
            <Icon className="w-3 h-3" aria-hidden="true" />
            <span className="sr-only">{up ? 'Up' : 'Down'} </span>{Math.abs(delta) < 1 ? '<1' : Math.abs(delta).toFixed(0)}%
            <span className="sr-only"> on the previous {rangeLabel}</span>
        </span>
    );
};

const KpiTile: React.FC<{ icon: React.ReactNode; label: string; badge?: React.ReactNode; sub?: React.ReactNode; spark?: React.ReactNode; children: React.ReactNode }> = ({ icon, label, badge, sub, spark, children }) => {
    const id = useId();
    return (
        <section aria-labelledby={id} className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card p-4 flex flex-col min-w-0">
            <div className="flex items-center gap-2 min-w-0">
                <span className="grid place-items-center h-7 w-7 rounded-lg bg-primary-500/10 text-primary-600 dark:text-primary-400 ring-1 ring-inset ring-primary-500/20 shrink-0" aria-hidden="true">{icon}</span>
                <h2 id={id} className="text-[13px] font-medium text-gray-600 dark:text-gray-400 truncate">{label}</h2>
                {badge && <span className="ml-auto shrink-0">{badge}</span>}
            </div>
            <div className="mt-2.5">{children}</div>
            {sub && <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{sub}</div>}
            {spark && <div className="mt-auto pt-3">{spark}</div>}
        </section>
    );
};

const NotMeasured: React.FC<{ why: string }> = ({ why }) => (
    <>
        <p className="flex items-center gap-2">
            <span className="font-mono text-[26px] leading-none text-gray-400 dark:text-gray-500">—</span>
            <span className="inline-flex rounded-md px-1.5 py-0.5 text-[11px] font-medium bg-gray-100 dark:bg-white/[0.06] text-gray-600 dark:text-gray-300">Not measured</span>
        </p>
        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{why}</p>
    </>
);

const bigValue = 'font-mono tabular-nums text-[26px] leading-none font-semibold tracking-tight text-gray-900 dark:text-white';

export const OpsKpis: React.FC<{ data: TrafficSummary; rangeLabel: string }> = ({ data, rangeLabel }) => {
    const { current, series } = data;
    const total = current.txBps + current.rxBps;
    const delta = periodDelta(totalOf(data.average), totalOf(data.previousAverage));
    return (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
            <KpiTile icon={<Activity className="w-4 h-4" />} label="Total throughput" badge={<DeltaBadge delta={delta} rangeLabel={rangeLabel} />}
                sub={`${current.measured} of ${current.online} online endpoint${current.online === 1 ? '' : 's'} measured now`}
                spark={<Sparkline lines={[{ values: series.map(p => totalOf(p)), stroke: 'stroke-primary-500 dark:stroke-primary-400' }]} />}>
                <p className={bigValue}>{current.measured ? formatBitRate(total) : '—'}</p>
            </KpiTile>

            <KpiTile icon={<ArrowDownLeft className="w-4 h-4" />} label="Inbound vs outbound"
                sub={
                    <div role="img" aria-label={`Inbound ${formatShare(current.rxBps, total)}, outbound ${formatShare(current.txBps, total)}`}
                        className="mt-1 flex h-1.5 gap-0.5 rounded-full overflow-hidden bg-gray-100 dark:bg-white/[0.06]">
                        {total > 0 && <>
                            <span className={RX.bg} style={{ flexGrow: current.rxBps, flexBasis: 0 }} />
                            <span className={TX.bg} style={{ flexGrow: current.txBps, flexBasis: 0 }} />
                        </>}
                    </div>
                }
                spark={<Sparkline lines={[{ values: series.map(p => p.rxBps), stroke: RX.stroke }, { values: series.map(p => p.txBps), stroke: TX.stroke }]} />}>
                <dl className="grid grid-cols-2 gap-2">
                    {[RX, TX].map(s => (
                        <div key={s.name} className="min-w-0">
                            <dt className="flex items-center gap-1.5 text-[11px] text-gray-500 dark:text-gray-400"><span className={`h-2 w-2 rounded-sm ${s.bg}`} aria-hidden="true" />{s.name === 'Rx' ? 'Inbound (Rx)' : 'Outbound (Tx)'}</dt>
                            <dd className="font-mono tabular-nums text-[17px] font-semibold text-gray-900 dark:text-white truncate">
                                {current.measured ? formatBitRate(s.name === 'Rx' ? current.rxBps : current.txBps) : '—'}
                            </dd>
                        </div>
                    ))}
                </dl>
            </KpiTile>

            <KpiTile icon={<Gauge className="w-4 h-4" />} label="Avg latency / jitter">
                <NotMeasured why="Agents do not report round-trip times yet." />
            </KpiTile>

            <KpiTile icon={<PackageX className="w-4 h-4" />} label="Packet loss">
                <NotMeasured why="Agents report bytes and packets sent, not drops or retransmits." />
            </KpiTile>
        </div>
    );
};
