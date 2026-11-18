import React from 'react';
import { ArrowDownRight, ArrowUpRight, BellRing, Clock, MonitorSmartphone, ShieldAlert } from 'lucide-react';
import { KpiTile, NotMeasured, Sparkline } from '../../network/ops/OpsKpis';
import { formatDuration, newAlertDelta, SEVERITY_META, TREND_BANDS, type SocSummary } from './socData';
import { SeverityCounts } from './SocKit';

const bigValue = 'font-mono tabular-nums text-[26px] leading-none font-semibold tracking-tight text-gray-900 dark:text-white';

const ChangeBadge: React.FC<{ now: number; before: number; rangeLabel: string }> = ({ now, before, rangeLabel }) => {
    const delta = newAlertDelta(now, before);
    if (delta == null) return <span className="text-[11px] text-gray-500 dark:text-gray-400">{now ? 'None the period before' : ''}</span>;
    const up = delta >= 0;
    const Icon = up ? ArrowUpRight : ArrowDownRight;
    return (
        <span title={`New alerts in this ${rangeLabel} against the ${rangeLabel} before it (${before})`}
            className="inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-[11px] font-mono tabular-nums bg-gray-100 dark:bg-white/[0.06] text-gray-700 dark:text-gray-300">
            <Icon className="w-3 h-3" aria-hidden="true" />
            <span className="sr-only">{up ? 'Up' : 'Down'} </span>{Math.abs(delta) < 1 ? '<1' : Math.abs(delta).toFixed(0)}%
            <span className="sr-only"> on the previous {rangeLabel}</span>
        </span>
    );
};

/** Active alerts split by severity: proportions only; the numbers are the labels beside it. */
const SeveritySplit: React.FC<{ data: SocSummary }> = ({ data }) => {
    const counts = data.kpis.activeBySeverity;
    const total = TREND_BANDS.reduce((a, s) => a + counts[s] + (s === 'low' ? counts.info : 0), 0);
    if (!total) return null;
    return (
        <div aria-hidden="true" className="mt-2 flex h-1.5 gap-0.5 rounded-full overflow-hidden bg-gray-100 dark:bg-white/[0.06]">
            {TREND_BANDS.map(s => {
                const v = counts[s] + (s === 'low' ? counts.info : 0);
                return v ? <span key={s} className={SEVERITY_META[s].swatch} style={{ flexGrow: v, flexBasis: 0 }} /> : null;
            })}
        </div>
    );
};

export const SocKpis: React.FC<{ data: SocSummary; rangeLabel: string }> = ({ data, rangeLabel }) => {
    const k = data.kpis;
    const ack = k.timeToAcknowledge, close = k.timeToClose;
    return (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
            <KpiTile icon={<ShieldAlert className="w-4 h-4" />} label="Active alerts"
                sub={<>
                    <SeverityCounts counts={k.activeBySeverity} />
                    <SeveritySplit data={data} />
                    <p className="mt-1.5">{k.open} open · {k.active - k.open} acknowledged{data.counts.activeIncidents != null && ` · ${data.counts.activeIncidents} active incident${data.counts.activeIncidents === 1 ? '' : 's'}`}</p>
                </>}>
                <p className={bigValue}>{k.active}</p>
            </KpiTile>

            <KpiTile icon={<BellRing className="w-4 h-4" />} label={`New in the last ${rangeLabel}`}
                badge={<ChangeBadge now={k.newInRange} before={k.newPrevious} rangeLabel={rangeLabel} />}
                sub={k.occurrencesInRange > k.newInRange
                    ? `From ${k.occurrencesInRange} detections; a repeat adds to its alert`
                    : `${k.newPrevious} in the ${rangeLabel} before`}
                spark={<Sparkline lines={[{ values: data.trend.map(p => p.critical + p.high + p.medium + p.low + p.info), stroke: 'stroke-primary-500 dark:stroke-primary-400' }]} />}>
                <p className={bigValue}>{k.newInRange}</p>
            </KpiTile>

            <KpiTile icon={<Clock className="w-4 h-4" />} label="Response time">
                {ack.count || close.count ? (
                    <dl className="grid grid-cols-2 gap-2">
                        {[{ label: 'To acknowledge', v: ack }, { label: 'To close', v: close }].map(({ label, v }) => (
                            <div key={label} className="min-w-0">
                                <dt className="text-[11px] text-gray-500 dark:text-gray-400">{label}</dt>
                                <dd className="font-mono tabular-nums text-[17px] font-semibold text-gray-900 dark:text-white truncate">{formatDuration(v.seconds)}</dd>
                                <dd className="text-[11px] text-gray-500 dark:text-gray-400">{v.count ? `average of ${v.count}` : 'none yet'}</dd>
                            </div>
                        ))}
                    </dl>
                ) : <NotMeasured why={`No alert was acknowledged or closed in the last ${rangeLabel}. Times appear once analysts act on alerts.`} />}
            </KpiTile>

            <KpiTile icon={<MonitorSmartphone className="w-4 h-4" />} label="Endpoints with active alerts"
                sub={<>
                    {k.endpointsOnline} of {k.endpoints} endpoint{k.endpoints === 1 ? '' : 's'} online
                    {k.removedWithActive > 0 && <p>{k.removedWithActive} removed endpoint{k.removedWithActive === 1 ? '' : 's'} still {k.removedWithActive === 1 ? 'has' : 'have'} alerts</p>}
                </>}>
                <p className={bigValue}>{k.endpointsWithActive}</p>
            </KpiTile>
        </div>
    );
};
