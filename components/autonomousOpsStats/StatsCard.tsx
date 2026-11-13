import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { fetchAutonomousOpsStatistics } from '../../services/autonomousOpsReporting';
import type { AutonomousOpsStatistics, StatsWindow } from '../../services/autonomousOpsReporting';
import { HEALTH_SKELETON, HealthNotice, clockOrDash } from '../AutonomousOpsHealthChips';
import { EmptyStateCard } from '../AutonomousOpsActivityList';
import { BarChart3Icon, ChevronRightIcon, FlaskConicalIcon, InfoIcon } from '../icons';
import { StatsRuleTable } from './StatsRuleTable';
import { TimeSavedBlock } from './TimeSavedBlock';
import {
    EMPTY_BODY, ESTIMATE_CHIP, READOUT_DECISIONS, READOUT_DONE, READOUT_TIME_SAVED, READOUT_UNDONE, STATS_LOAD_ERROR,
    RULES_HEADING, STATS_LOAD_FAILED_SUMMARY, STATS_PERIOD_GROUP, STATS_PERIOD_LABEL, STATS_TITLE, TRY_AGAIN, emptyHeading, formatMinutes,
    periodLabel, periodPillLabel, simulationLine, summaryLine, updatedLine,
} from './reportingCopy';

interface StatsCardProps {
    /** viewingTenantId: the organization platform staff entered from Tenants, else null. */
    tenantId: string | null;
    days: StatsWindow;
    onDaysChange: (days: StatsWindow) => void;
    /** Bumped by the screen's Refresh button. */
    refreshSignal: number;
}

const WINDOWS: StatsWindow[] = [7, 30, 90];
const PILL_BASE = 'min-h-8 px-3 text-xs font-semibold rounded-full border';
const PILL_IDLE = 'border-gray-300 text-gray-700 dark:border-white/10 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/[0.06]';
const PILL_ACTIVE = 'border-transparent bg-primary-500/10 text-primary-700 ring-1 ring-inset ring-primary-500/30 dark:text-primary-300';
const OUTLINE_CHIP =
    'inline-flex items-center gap-1 rounded-full border border-gray-300 dark:border-gray-600 px-2 py-1 text-xs font-semibold text-gray-700 dark:text-gray-200 break-words';

const Readout: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
    <div className="min-w-0 rounded-lg border border-gray-200 p-4 dark:border-white/10">
        <dt className="text-xs text-gray-500 dark:text-gray-400">{label}</dt>
        <dd className="mt-1 flex flex-wrap items-center gap-2 break-words text-lg font-semibold tabular-nums text-gray-900 dark:text-white">{children}</dd>
    </div>
);

const SIMULATION_BLOCK = 'flex items-start gap-2 rounded-lg border border-dashed border-gray-400 p-4 dark:border-gray-500';

/** A period with no decision of any kind (a simulation counts as one): the card shows the empty state instead of c, d and e. */
const hasNothing = (stats: AutonomousOpsStatistics): boolean =>
    !stats.shadowOnly && stats.totals.fired === 0 && stats.totals.wouldHaveDone === 0 && stats.rules.length === 0;

/**
 * The Statistics card (86-UI-SPEC section 2, ACTV-05, ACTV-07): one summary line that always carries the
 * headline and the word "estimate", and an expanded body with the period, the four headline cells, the
 * separate simulation line and the Time saved block. Simulation is never added to a real count.
 * One fetch on mount; refetch on expand, on a period change and on the screen's Refresh. No polling.
 * Read-only: nothing here writes. Server text renders as React text only.
 */
export const StatsCard: React.FC<StatsCardProps> = ({ tenantId, days, onDaysChange, refreshSignal }) => {
    const uid = useId();
    const bodyId = `${uid}-body`;
    const [expanded, setExpanded] = useState(false);
    const [stats, setStats] = useState<AutonomousOpsStatistics | null>(null);
    const [failed, setFailed] = useState(false);
    const [loading, setLoading] = useState(true);
    const [expandTick, setExpandTick] = useState(0);
    const latest = useRef(0);
    const shownFor = useRef('');

    const load = useCallback(async () => {
        const mine = ++latest.current;
        const key = `${days}|${tenantId ?? ''}`;
        // A new period or organization shows skeletons in place instead of the previous numbers.
        if (shownFor.current !== key) setStats(null);
        setLoading(true);
        try {
            const next = await fetchAutonomousOpsStatistics(days, tenantId);
            if (mine !== latest.current) return;
            shownFor.current = key;
            setStats(next);
            setFailed(false);
        } catch {
            if (mine !== latest.current) return;
            shownFor.current = '';
            setStats(null);
            setFailed(true);
        } finally {
            if (mine === latest.current) setLoading(false);
        }
    }, [days, tenantId]);

    useEffect(() => { void load(); }, [load, refreshSignal, expandTick]);

    const toggle = () => {
        if (!expanded) setExpandTick(n => n + 1);
        setExpanded(v => !v);
    };

    return (
        <section className="card p-6" aria-labelledby={`${uid}-title`}>
            <div className="min-w-0">
                <h2 id={`${uid}-title`} className="text-lg font-semibold leading-tight text-gray-900 dark:text-white">
                    <button type="button" aria-expanded={expanded} aria-controls={bodyId} onClick={toggle} className="inline-flex items-center gap-2 text-left">
                        <BarChart3Icon size={20} aria-hidden="true" />
                        <span>{STATS_TITLE}</span>
                        <ChevronRightIcon size={16} aria-hidden="true" className={expanded ? 'rotate-90' : ''} />
                    </button>
                </h2>
                {loading && !stats && !failed && <div className={`mt-2 h-4 w-64 ${HEALTH_SKELETON}`} />}
                {stats && <p className="mt-2 break-words text-sm text-gray-600 dark:text-gray-400">{summaryLine(stats)}</p>}
                {failed && !stats && <p className="mt-2 break-words text-sm text-gray-600 dark:text-gray-400">{STATS_LOAD_FAILED_SUMMARY}</p>}
            </div>

            {expanded && (
                <div id={bodyId} aria-busy={loading} className="mt-6 flex flex-col gap-6 border-t border-gray-200 pt-6 dark:border-white/10">
                    <div className="flex flex-wrap items-center justify-between gap-4">
                        <div className="flex flex-wrap items-center gap-2">
                            <span className="text-xs font-semibold text-gray-700 dark:text-gray-200">{STATS_PERIOD_LABEL}</span>
                            <div role="group" aria-label={STATS_PERIOD_GROUP} className="flex flex-wrap gap-2">
                                {WINDOWS.map(w => (
                                    <button
                                        key={w} type="button" aria-pressed={w === days} onClick={() => onDaysChange(w)}
                                        className={`${PILL_BASE} ${w === days ? PILL_ACTIVE : PILL_IDLE}`}
                                    >
                                        {periodPillLabel(w)}
                                    </button>
                                ))}
                            </div>
                        </div>
                        {stats && <span className="text-xs text-gray-500 dark:text-gray-400">{updatedLine(clockOrDash(stats.generatedAt))}</span>}
                    </div>

                    {failed && !stats && (
                        <HealthNotice tone="red" role="alert">
                            <p>{STATS_LOAD_ERROR}</p>
                            <p>
                                <button type="button" onClick={() => void load()} className="text-sm font-semibold underline underline-offset-2">{TRY_AGAIN}</button>
                            </p>
                        </HealthNotice>
                    )}

                    {loading && !stats && !failed && (
                        <>
                            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                                {[0, 1, 2, 3].map(i => <div key={i} className={`h-20 ${HEALTH_SKELETON}`} />)}
                            </div>
                            <div className={`h-40 ${HEALTH_SKELETON}`} />
                        </>
                    )}

                    {stats && (
                        <>
                            <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label={periodLabel(stats.days)}>
                                <Readout label={READOUT_DECISIONS}>{stats.totals.fired}</Readout>
                                <Readout label={READOUT_DONE}>{stats.totals.done}</Readout>
                                <Readout label={READOUT_UNDONE}>{stats.totals.undone}</Readout>
                                <Readout label={READOUT_TIME_SAVED}>
                                    <span>{formatMinutes(stats.timeSaved.minutes)}</span>
                                    <span className={OUTLINE_CHIP}><InfoIcon size={12} aria-hidden="true" />{ESTIMATE_CHIP}</span>
                                </Readout>
                            </dl>

                            {hasNothing(stats) ? (
                                <EmptyStateCard icon={BarChart3Icon} heading={emptyHeading(stats.days)}>
                                    <p className="max-w-prose break-words text-sm text-gray-600 dark:text-gray-400">{EMPTY_BODY}</p>
                                </EmptyStateCard>
                            ) : (
                                <>
                                    {(stats.shadowOnly || stats.totals.wouldHaveDone > 0) && (
                                        <div className={SIMULATION_BLOCK}>
                                            <FlaskConicalIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
                                            <p className="min-w-0 break-words text-sm text-gray-700 dark:text-gray-200">{simulationLine(stats.totals.wouldHaveDone)}</p>
                                        </div>
                                    )}
                                    <TimeSavedBlock timeSaved={stats.timeSaved} shadowOnly={stats.shadowOnly} />
                                    {stats.rules.length > 0 && (
                                        <section className="flex flex-col gap-2">
                                            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{RULES_HEADING}</h3>
                                            <StatsRuleTable rules={stats.rules} totals={stats.totals} days={stats.days} />
                                        </section>
                                    )}
                                </>
                            )}
                        </>
                    )}
                </div>
            )}
        </section>
    );
};

export default StatsCard;
