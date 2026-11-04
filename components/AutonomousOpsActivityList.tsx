import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    AutonomousOpsRow, AutonomousOpsBucket, AutonomousOpsActionsPage, AutonomousOpsCounts,
    fetchAutonomousOpsActions, fetchPlatformAutonomousOpsActions,
} from '../services/autonomousOpsApi';
import { STATUS_POLL_MS, useAutonomousOpsStatus } from '../contexts/AutonomousOpsStatusContext';
import { HealthChip } from './AutonomousOpsHealthChips';
import {
    OpenViewHandlers, ResultCell, ResultContext, TargetSummary, fillBlockTimes, isGroupedSuggestion,
} from './AutonomousOpsRowActions';
import {
    AlertTriangleIcon, CheckCircleIcon, ClockIcon, FlaskConicalIcon, HistoryIcon, InfoIcon, PauseCircleIcon,
    PlayCircleIcon, RefreshCcwIcon, ShieldLockIcon, SlidersHorizontalIcon, XCircleIcon,
} from './icons';

export const PAGE_SIZE = 25;

type ChipKey = 'pending' | 'done' | 'undone' | 'failed' | 'refused' | 'suggested' | 'simulation' | 'stop' | 'resume' | 'setting';

const CHIP_BASE = 'inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold border';
const AMBER = 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-400/10 dark:text-amber-200 dark:border-amber-400/25';
const NEUTRAL = 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-white/[0.06] dark:text-gray-200 dark:border-white/10';

const CHIPS: Record<ChipKey, { label: string; Icon: React.FC<any>; classes: string }> = {
    pending: { label: 'Pending', Icon: ClockIcon, classes: AMBER },
    done: { label: 'Done', Icon: CheckCircleIcon, classes: 'bg-green-50 text-green-800 border-green-200 dark:bg-green-400/10 dark:text-green-200 dark:border-green-400/25' },
    undone: { label: 'Undone', Icon: RefreshCcwIcon, classes: NEUTRAL },
    failed: { label: 'Failed', Icon: XCircleIcon, classes: 'bg-red-50 text-red-700 border-red-200 dark:bg-red-400/10 dark:text-red-300 dark:border-red-400/25' },
    refused: { label: 'Refused', Icon: ShieldLockIcon, classes: 'bg-transparent text-gray-700 border-gray-300 dark:text-gray-200 dark:border-gray-600' },
    suggested: { label: 'Suggested', Icon: InfoIcon, classes: 'bg-blue-50 text-blue-800 border-blue-200 dark:bg-blue-400/10 dark:text-blue-200 dark:border-blue-400/25' },
    simulation: { label: 'Simulation', Icon: FlaskConicalIcon, classes: 'bg-transparent text-gray-800 border-dashed border-gray-400 dark:text-gray-100 dark:border-gray-500' },
    stop: { label: 'Stop', Icon: PauseCircleIcon, classes: AMBER },
    resume: { label: 'Resume', Icon: PlayCircleIcon, classes: NEUTRAL },
    // A change to the two-source rule, block length or watched services: neutral, no new tone (A-83-SETTING-CHIP).
    setting: { label: 'Setting', Icon: SlidersHorizontalIcon, classes: NEUTRAL },
};

const STOPPING_EVENTS = new Set(['stop_pressed', 'platform_stop_pressed', 'breaker_tripped']);
const SETTING_EVENTS = new Set(['two_signal_on', 'two_signal_off', 'block_length_changed', 'watched_services_changed']);

function chipKeyFor(row: AutonomousOpsRow): ChipKey {
    if (row.bucket === 'control') {
        if (row.controlEvent && SETTING_EVENTS.has(row.controlEvent)) return 'setting';
        return row.controlEvent && STOPPING_EVENTS.has(row.controlEvent) ? 'stop' : 'resume';
    }
    // platform_health rows never reach here: RowChip renders them with HealthChip.
    return row.bucket as ChipKey;
}

/** The State chip of a row: the Phase 82 health vocabulary for watchdog rows, the Phase 81 chips for the rest. */
const RowChip: React.FC<{ row: AutonomousOpsRow }> = ({ row }) => (
    row.bucket === 'platform_health'
        ? <HealthChip kind={row.healthChip ?? 'unknown'} />
        : <StateChip chip={chipKeyFor(row)} />
);

export const StateChip: React.FC<{ chip: ChipKey }> = ({ chip }) => {
    const { label, Icon, classes } = CHIPS[chip];
    return (
        <span className={`${CHIP_BASE} ${classes}`}>
            <Icon size={12} aria-hidden="true" />
            {label}
        </span>
    );
};

const SIM_PREFIX = 'Nothing was done.';
const SIM_LEAD = 'Nothing was done. This is what would have happened: ';

/** What the Result cell says. A simulation can never read as something that was carried out. */
export function resultFor(row: AutonomousOpsRow): string | null {
    const text = fillBlockTimes(row.resultText, row.blockedUntil);
    if (row.bucket !== 'simulation') return text || null;
    if (!text) return SIM_PREFIX;
    return text.startsWith(SIM_PREFIX) ? text : `${SIM_LEAD}${text}`;
}

const DAY_MS = 24 * 60 * 60 * 1000;

export function formatWhen(iso: string, now: number = Date.now()): { text: string; title: string } {
    const at = new Date(iso);
    if (Number.isNaN(at.getTime())) return { text: '—', title: '' };
    const title = at.toLocaleString();
    const age = now - at.getTime();
    if (age >= 0 && age < DAY_MS) {
        const minutes = Math.floor(age / 60_000);
        if (minutes < 1) return { text: 'Just now', title };
        if (minutes < 60) return { text: `${minutes} min ago`, title };
        return { text: `${Math.floor(minutes / 60)} hr ago`, title };
    }
    const text = at.toLocaleString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
    });
    return { text, title };
}

const Dash = '—';

const WhenLine: React.FC<{ row: AutonomousOpsRow; className?: string }> = ({ row, className = '' }) => {
    const when = formatWhen(row.createdAt);
    return (
        <time dateTime={row.createdAt} title={when.title} className={`text-xs text-gray-500 dark:text-gray-400 tabular-nums ${className}`}>
            {when.text}
        </time>
    );
};

const WhatRan: React.FC<{ row: AutonomousOpsRow }> = ({ row }) => {
    const under = row.bucket === 'platform_health' ? row.source : row.classLine;
    return (
        <>
            <div className="text-sm font-semibold text-gray-900 dark:text-white break-words">{row.actionLabel}</div>
            {under && <div className="text-xs text-gray-500 dark:text-gray-400 break-words">{under}</div>}
        </>
    );
};

const Why: React.FC<{ row: AutonomousOpsRow }> = ({ row }) => (
    <>
        <div className="text-sm text-gray-600 dark:text-gray-400 break-words">{row.reasonText || Dash}</div>
        {row.ruleId && <div className="font-mono text-xs text-gray-500 dark:text-gray-400 break-all">{row.ruleId}</div>}
    </>
);

const Target: React.FC<{ row: AutonomousOpsRow }> = ({ row }) => {
    if (!row.host && !row.target) return <span className="text-sm text-gray-600 dark:text-gray-400">{Dash}</span>;
    return (
        <>
            {row.host && <div className="text-sm font-semibold text-gray-900 dark:text-white break-words">{row.host}</div>}
            {row.target
                ? <div className="font-mono text-xs text-gray-500 dark:text-gray-400 break-all">{row.target}</div>
                : row.bucket === 'platform_health' && <div className="text-xs text-gray-500 dark:text-gray-400">{Dash}</div>}
        </>
    );
};

const Result: React.FC<{ row: AutonomousOpsRow; ctx: ResultContext }> = ({ row, ctx }) => (
    <ResultCell row={row} text={resultFor(row)} ctx={ctx} />
);

/** A grouped suggestion summarises its Target; every other row shows the host and target as sent. */
const TargetCell: React.FC<{ row: AutonomousOpsRow }> = ({ row }) => (isGroupedSuggestion(row) ? <TargetSummary row={row} /> : <Target row={row} />);

const SIM_RULE = 'border-l-2 border-dashed border-gray-400 dark:border-gray-500';

const ActivityTable: React.FC<{ rows: AutonomousOpsRow[]; ctx: ResultContext }> = ({ rows, ctx }) => (
    <div className="hidden xl:block">
        <table className="w-full text-sm">
            <caption className="sr-only">Autonomous Ops activity</caption>
            <thead>
                <tr className="text-left text-xs font-semibold text-gray-500 dark:text-gray-400">
                    <th scope="col" className="w-40 px-4 py-4">State</th>
                    <th scope="col" className="w-56 px-4 py-4">What ran</th>
                    <th scope="col" className="min-w-[240px] px-4 py-4">Why (the rule)</th>
                    <th scope="col" className="w-48 px-4 py-4">Target</th>
                    <th scope="col" className="min-w-[200px] px-4 py-4">Result</th>
                </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-white/10">
                {rows.map(row => (
                    <tr key={row.id}>
                        <td className={`px-4 py-4 align-top ${row.bucket === 'simulation' ? SIM_RULE : ''}`}>
                            <div className="flex flex-col items-start gap-2">
                                <RowChip row={row} />
                                <WhenLine row={row} />
                            </div>
                        </td>
                        <td className="px-4 py-4 align-top"><WhatRan row={row} /></td>
                        <td className="px-4 py-4 align-top"><Why row={row} /></td>
                        <td className="px-4 py-4 align-top"><TargetCell row={row} /></td>
                        <td className="px-4 py-4 align-top"><Result row={row} ctx={ctx} /></td>
                    </tr>
                ))}
            </tbody>
        </table>
    </div>
);

const ActivityCards: React.FC<{ rows: AutonomousOpsRow[]; ctx: ResultContext }> = ({ rows, ctx }) => (
    <ul className="xl:hidden divide-y divide-gray-200 dark:divide-white/10">
        {rows.map(row => (
            <li key={row.id} className={`p-4 flex flex-col gap-2 ${row.bucket === 'simulation' ? SIM_RULE : ''}`}>
                <div className="flex items-center justify-between gap-2">
                    <RowChip row={row} />
                    <WhenLine row={row} />
                </div>
                <div><WhatRan row={row} /></div>
                <dl className="flex flex-col gap-2">
                    <div>
                        <dt className="text-xs text-gray-500 dark:text-gray-400">Why</dt>
                        <dd><Why row={row} /></dd>
                    </div>
                    <div>
                        <dt className="text-xs text-gray-500 dark:text-gray-400">Target</dt>
                        <dd><TargetCell row={row} /></dd>
                    </div>
                    <div>
                        <dt className="text-xs text-gray-500 dark:text-gray-400">Result</dt>
                        <dd><Result row={row} ctx={ctx} /></dd>
                    </div>
                </dl>
            </li>
        ))}
    </ul>
);

const SECONDARY_BUTTON =
    'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ' +
    'px-4 py-2 text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-60';
const TEXT_BUTTON = 'text-sm font-semibold text-gray-900 dark:text-white underline underline-offset-2';

/** Centred card body used for "no activity" and "Select an organization" (UI-SPEC 3d, 3f). */
export const EmptyStateCard: React.FC<{
    icon: React.FC<any>;
    heading: string;
    headingLevel?: 'h2' | 'h3';
    children?: React.ReactNode;
}> = ({ icon: Icon, heading, headingLevel = 'h3', children }) => {
    const Heading = headingLevel;
    return (
        <div className="flex flex-col items-center gap-4 px-8 py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gray-100 dark:bg-white/[0.06]">
                <Icon size={24} aria-hidden="true" className="text-gray-500 dark:text-gray-400" />
            </div>
            <Heading className="max-w-prose break-words text-lg font-semibold leading-tight text-gray-900 dark:text-white">{heading}</Heading>
            {children}
        </div>
    );
};

const FILTERS: { key: AutonomousOpsBucket; label: string; empty: string }[] = [
    { key: 'all', label: 'All', empty: '' },
    { key: 'pending', label: 'Pending', empty: 'No pending actions.' },
    { key: 'done', label: 'Done', empty: 'No done actions.' },
    { key: 'undone', label: 'Undone', empty: 'No undone actions.' },
    { key: 'failed', label: 'Failed', empty: 'No failed actions.' },
    { key: 'refused', label: 'Refused', empty: 'No refused actions.' },
    { key: 'suggested', label: 'Suggested', empty: 'No suggested actions.' },
    { key: 'simulation', label: 'Simulation', empty: 'No simulated actions.' },
];
/** Appended after Simulation in platform scope only (D-23). */
const PLATFORM_HEALTH_FILTER: (typeof FILTERS)[number] = {
    key: 'platform_health', label: 'Platform health', empty: 'No platform health events.',
};

const PILL_BASE = 'min-h-8 px-3 text-xs font-semibold rounded-full border';
const PILL_IDLE = 'border-gray-300 text-gray-700 dark:border-white/10 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/[0.06]';
const PILL_ACTIVE = 'border-transparent bg-primary-500/10 text-primary-700 ring-1 ring-inset ring-primary-500/30 dark:text-primary-300';

const BODY_COPY = 'max-w-prose break-words text-sm text-gray-600 dark:text-gray-400';

function emptyBody(platform: boolean, shadow: boolean): string {
    if (platform) return 'Nothing has been recorded at platform level yet. Stop and resume events appear here.';
    return shadow
        ? "Autonomous Ops hasn't made any decisions for this organization yet. Shadow mode is on, so when it does, entries are marked as a simulation and nothing is carried out."
        : "Autonomous Ops hasn't made any decisions for this organization yet. When it does, each one appears here with the rule behind it.";
}

const mergeRows = (current: AutonomousOpsRow[], more: AutonomousOpsRow[]) => {
    const seen = new Set(current.map(r => r.id));
    return [...current, ...more.filter(r => !seen.has(r.id))];
};

export interface ActivityListProps {
    /** `platform` reads the platform-scope list; `tenant` reads tenantId (platform staff) or the viewer's own tenant. */
    scope: { kind: 'tenant'; tenantId: string | null } | { kind: 'platform' };
    /** Bumped by the screen's Refresh button; reloads the first page without a skeleton. */
    refreshSignal?: number;
    /** Incident ids whose approval card is rendered above the list; a Pending row links only to one of these. */
    decisionIds?: ReadonlySet<string>;
    /** The screens a suggestion may open; a target is present only when the viewer may open it. */
    onOpenView?: OpenViewHandlers;
}

export const AutonomousOpsActivityList: React.FC<ActivityListProps> = ({ scope, refreshSignal = 0, decisionIds, onOpenView }) => {
    const { status, platformStatus } = useAutonomousOpsStatus();
    const platform = scope.kind === 'platform';
    const tenantId = scope.kind === 'tenant' ? scope.tenantId : null;

    const [picked, setBucket] = useState<AutonomousOpsBucket>('all');
    // The Platform health filter exists in platform scope only; elsewhere a leftover pick reads as All.
    const bucket: AutonomousOpsBucket = !platform && picked === 'platform_health' ? 'all' : picked;
    const [rows, setRows] = useState<AutonomousOpsRow[]>([]);
    const [nextCursor, setNextCursor] = useState<string | null>(null);
    const [counts, setCounts] = useState<AutonomousOpsCounts | null>(null);
    const [total, setTotal] = useState<number | null>(null);
    const [loading, setLoading] = useState(true);
    const [failed, setFailed] = useState(false);
    const [loadingMore, setLoadingMore] = useState(false);
    const [moreFailed, setMoreFailed] = useState(false);
    const generation = useRef(0);
    const busy = useRef(false);
    const loud = useRef(false);
    const pages = useRef(1);

    const request = useCallback((cursor: string | null): Promise<AutonomousOpsActionsPage> => (
        platform
            ? fetchPlatformAutonomousOpsActions({ bucket, limit: PAGE_SIZE, cursor })
            : fetchAutonomousOpsActions({ bucket, limit: PAGE_SIZE, cursor, tenantId })
    ), [platform, tenantId, bucket]);

    /** Loud: filter or scope change, Try again (skeleton). Silent: poll, focus (no skeleton, rows kept; skipped
     *  once Load more was used, so a timer never throws loaded pages away). Forced silent: Refresh, a decision and
     *  a stale row (WR-23): always reads the first page, replaces any load in flight and starts again at page one. */
    const loadFirst = useCallback((silent: boolean, force = false) => {
        if (silent && !force && (busy.current || pages.current > 1)) return;
        const mine = ++generation.current;
        if (!silent) {
            loud.current = true;
            pages.current = 1;
            setLoading(true);
            setFailed(false);
            setRows([]);
            setNextCursor(null);
        }
        if (!silent || force) {
            busy.current = true;
            setLoadingMore(false);
            setMoreFailed(false);
        }
        request(null)
            .then(page => {
                if (mine !== generation.current) return;
                pages.current = 1;
                setRows(page.items);
                setNextCursor(page.nextCursor ?? null);
                setCounts(page.counts ?? null);
                setTotal(typeof page.total === 'number' ? page.total : null);
                setFailed(false);
                setLoading(false);
                loud.current = false;
                busy.current = false;
            })
            .catch(() => {
                if (mine !== generation.current) return;
                busy.current = false;
                // A quiet reload that fails keeps the rows; one that replaced a loud load shows that load's error.
                if (!loud.current) return;
                loud.current = false;
                setFailed(true);
                setLoading(false);
            });
    }, [request]);

    useEffect(() => { loadFirst(false); }, [loadFirst]);

    const seenSignal = useRef(refreshSignal);
    useEffect(() => {
        if (seenSignal.current === refreshSignal) return;
        seenSignal.current = refreshSignal;
        loadFirst(true, true);
    }, [refreshSignal, loadFirst]);

    const latest = useRef(loadFirst);
    latest.current = loadFirst;
    useEffect(() => {
        const refresh = () => { if (document.visibilityState !== 'hidden') latest.current(true); };
        const timer = setInterval(refresh, STATUS_POLL_MS);
        window.addEventListener('focus', refresh);
        return () => { clearInterval(timer); window.removeEventListener('focus', refresh); };
    }, []);

    const loadMore = () => {
        if (!nextCursor || busy.current) return;
        const mine = generation.current;
        busy.current = true;
        setLoadingMore(true);
        setMoreFailed(false);
        request(nextCursor)
            .then(page => {
                if (mine !== generation.current) return;
                setRows(prev => mergeRows(prev, page.items));
                setNextCursor(page.nextCursor ?? null);
                pages.current += 1;
            })
            .catch(() => { if (mine === generation.current) setMoreFailed(true); })
            .finally(() => {
                if (mine !== generation.current) return;
                busy.current = false;
                setLoadingMore(false);
            });
    };

    // A simulation, control or platform-health row is shown only where the contract allows it, whatever the
    // server sent: platform-health rows never leave the platform scope (D-23, H11, T-82-44).
    const onRowChanged = useCallback((next: AutonomousOpsRow) => setRows(prev => prev.map(r => (r.id === next.id ? next : r))), []);
    const onStale = useCallback(() => loadFirst(true, true), [loadFirst]);
    const ctx: ResultContext = { tenantId, decisionIds, onOpenView, onRowChanged, onStale };

    const visible = useMemo(
        () => rows.filter(r => (platform || r.bucket !== 'platform_health') && (bucket === 'all' || r.bucket === bucket)),
        [rows, bucket, platform],
    );
    const filters = platform ? [...FILTERS, PLATFORM_HEALTH_FILTER] : FILTERS;
    const filter = filters.find(f => f.key === bucket) ?? FILTERS[0];
    const watchdogNotInstalled = platformStatus?.health?.watchdog === 'not_installed';
    const shown = visible.length;
    const footer = total !== null && total > shown
        ? `Showing ${shown} of ${total} actions`
        : shown === 1 ? 'Showing 1 action' : `Showing ${shown} actions`;

    return (
        <>
            <div role="group" aria-label="Filter activity by state" className="flex flex-wrap gap-2">
                {filters.map(f => {
                    const count = counts && f.key !== 'all' ? counts[f.key] : undefined;
                    return (
                        <button
                            key={f.key}
                            type="button"
                            aria-pressed={bucket === f.key}
                            onClick={() => setBucket(f.key)}
                            className={`${PILL_BASE} ${bucket === f.key ? PILL_ACTIVE : PILL_IDLE}`}
                        >
                            {f.label}
                            {typeof count === 'number' && <span className="tabular-nums"> {count}</span>}
                        </button>
                    );
                })}
            </div>

            <div className="card overflow-hidden" aria-busy={loading}>
                {loading ? (
                    <div className="flex flex-col gap-2 p-4">
                        {Array.from({ length: 5 }, (_, i) => (
                            <div key={i} data-skeleton="row" className="h-24 xl:h-14 animate-pulse rounded-lg bg-gray-100 dark:bg-white/[0.06]" />
                        ))}
                    </div>
                ) : failed ? (
                    <div role="alert" className="flex flex-wrap items-center gap-4 p-4 text-sm text-red-700 dark:text-red-300">
                        <AlertTriangleIcon size={20} aria-hidden="true" className="shrink-0" />
                        <span className="min-w-0 break-words">Couldn't load activity. Check your connection and try again.</span>
                        <button type="button" className={SECONDARY_BUTTON} onClick={() => loadFirst(false)}>Try again</button>
                    </div>
                ) : shown === 0 ? (
                    bucket === 'all' ? (
                        <EmptyStateCard icon={HistoryIcon} heading="No activity yet">
                            <p className={BODY_COPY}>{emptyBody(platform, !!status?.shadow.effective)}</p>
                        </EmptyStateCard>
                    ) : bucket === 'platform_health' && watchdogNotInstalled ? (
                        <EmptyStateCard icon={HistoryIcon} heading="No platform health events yet.">
                            <p className={BODY_COPY}>Events appear here once the watchdog is installed and reporting.</p>
                        </EmptyStateCard>
                    ) : (
                        <EmptyStateCard icon={HistoryIcon} heading={filter.empty}>
                            <button type="button" className={TEXT_BUTTON} onClick={() => setBucket('all')}>Show all activity</button>
                        </EmptyStateCard>
                    )
                ) : (
                    <>
                        <ActivityTable rows={visible} ctx={ctx} />
                        <ActivityCards rows={visible} ctx={ctx} />
                        <div className="flex flex-col items-center gap-2 border-t border-gray-200 p-4 dark:border-white/10">
                            {moreFailed ? (
                                <div role="alert" className="flex flex-wrap items-center justify-center gap-4 text-sm text-red-700 dark:text-red-300">
                                    <span className="break-words">Couldn't load more activity. Try again.</span>
                                    <button type="button" className={SECONDARY_BUTTON} onClick={loadMore}>Try again</button>
                                </div>
                            ) : nextCursor ? (
                                <button type="button" className={SECONDARY_BUTTON} onClick={loadMore} disabled={loadingMore}>
                                    {loadingMore ? 'Loading...' : 'Load more'}
                                </button>
                            ) : null}
                            <p className="text-xs text-gray-500 dark:text-gray-400 tabular-nums">{footer}</p>
                        </div>
                    </>
                )}
            </div>
        </>
    );
};
