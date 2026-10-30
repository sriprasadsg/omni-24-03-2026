import React, { useCallback, useEffect, useRef, useState } from 'react';
import { fetchRetentionReview } from '../services/autonomousOpsApi';
import type { RetentionReview, RetentionReviewItem } from '../services/autonomousOpsApi';
import { useUser } from '../contexts/UserContext';
import { formatWhen } from './AutonomousOpsActivityList';
import { SECONDARY_BUTTON } from './AutonomousOpsHealthCards';
import { HEALTH_SKELETON, HealthCell, HealthChip, HealthNotice } from './AutonomousOpsHealthChips';
import { RetentionConfirmDialog, plural } from './AutonomousOpsRetentionConfirmDialog';
import type { RetentionReviewSnapshot } from './AutonomousOpsRetentionConfirmDialog';
import { TrashIcon } from './icons';

export const RETENTION_POLL_MS = 30_000;
const MUTED = 'break-words text-xs text-gray-500 dark:text-gray-400';
const CONFIRM_BUTTON =
    'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-red-600 px-4 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60';
const SCOPE_NOTE = 'Audit logs, the audit ledger, decision records and compliance evidence are never deleted by this job.';

const number = (n: number) => n.toLocaleString('en-US');

/** The schedule is UTC, so the date ("Oct 31, 2026") and time ("02:00") of a run are stated in UTC. */
function utcParts(iso: string): { date: string; time: string } | null {
    const at = new Date(iso);
    if (Number.isNaN(at.getTime())) return null;
    return {
        date: at.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }),
        time: at.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' }),
    };
}

/** A server message without its closing full stop, so it reads inside "Failed: {error}. It tries again...". */
const plain = (message: string) => message.trim().replace(/[.\s]+$/, '');

// ── data ────────────────────────────────────────────────────────────────────

interface ReviewState { review: RetentionReview; items: RetentionReviewItem[]; nextOffset: number | null }

const readable = (review: RetentionReview | null | undefined): review is RetentionReview => Array.isArray(review?.items);

/**
 * The first page on mount, then every 30 s while the tab is visible and when the page Refresh counter changes.
 * A background read never shows a skeleton; a failure keeps the last review. Rows already loaded by Load more
 * stay while the token is unchanged, because the token covers every waiting row and its count.
 */
function useRetentionReview(refreshSignal: number) {
    const [state, setState] = useState<ReviewState | null>(null);
    const [failed, setFailed] = useState(false);
    const [loadingMore, setLoadingMore] = useState(false);
    const [moreFailed, setMoreFailed] = useState(false);
    const alive = useRef(true);
    const lastSignal = useRef(refreshSignal);
    const current = useRef<ReviewState | null>(null);
    const moreBusy = useRef(false);
    current.current = state;

    const load = useCallback(async () => {
        try {
            const next = await fetchRetentionReview(0);
            if (!alive.current) return;
            if (!readable(next)) throw new Error('unreadable retention review');
            setState(prev => (prev && prev.review.reviewToken === next.reviewToken && prev.items.length > next.items.length
                ? { review: next, items: prev.items, nextOffset: prev.nextOffset }
                : { review: next, items: next.items, nextOffset: next.nextOffset }));
            setFailed(false);
        } catch {
            if (alive.current) setFailed(true);
        }
    }, []);

    const loadMore = useCallback(async () => {
        const at = current.current;
        if (moreBusy.current || !at || at.nextOffset === null) return;
        moreBusy.current = true;
        setLoadingMore(true);
        setMoreFailed(false);
        try {
            const page = await fetchRetentionReview(at.nextOffset);
            if (!alive.current) return;
            if (!readable(page)) throw new Error('unreadable retention review');
            if (current.current?.review.reviewToken !== page.reviewToken) {
                await load(); // the counts changed under us: a page of the new review would not line up, start again
                return;
            }
            setState(prev => (prev ? { ...prev, items: [...prev.items, ...page.items], nextOffset: page.nextOffset } : prev));
        } catch {
            if (alive.current) setMoreFailed(true);
        } finally {
            moreBusy.current = false;
            if (alive.current) setLoadingMore(false);
        }
    }, [load]);

    useEffect(() => {
        alive.current = true;
        void load();
        const timer = setInterval(() => { if (document.visibilityState !== 'hidden') void load(); }, RETENTION_POLL_MS);
        return () => { alive.current = false; clearInterval(timer); };
    }, [load]);

    useEffect(() => {
        if (refreshSignal === lastSignal.current) return;
        lastSignal.current = refreshSignal;
        void load();
    }, [refreshSignal, load]);

    const reload = useCallback(() => { setFailed(false); void load(); }, [load]);
    return { state, load, reload, loadMore, loadingMore, moreFailed, loading: state === null && !failed, loadFailed: state === null && failed };
}

// ── review rows ─────────────────────────────────────────────────────────────

const rowKey = (item: RetentionReviewItem) => `${item.tenantId}:${item.type}`;
const whyText = (item: RetentionReviewItem) => (item.reason === 'shortened' && item.previousDays !== null
    ? `Retention period shortened from ${item.previousDays} to ${item.days} days`
    : 'First run');
const wouldDelete = (item: RetentionReviewItem) => (item.count === null || item.countError
    ? <span className="text-sm font-normal text-red-600 dark:text-red-400">Couldn't count</span>
    : `${number(item.count)} records`);
const keeps = (item: RetentionReviewItem) => (
    <>
        <span className="block">{`${item.days} days`}</span>
        {item.previousDays !== null && <span className={`block ${MUTED}`}>{`was ${item.previousDays} days`}</span>}
    </>
);
const dataType = (item: RetentionReviewItem) => (
    <>
        <span className="block break-words text-gray-900 dark:text-white">{item.label}</span>
        <span className={`block font-mono ${MUTED}`}>{item.collection}</span>
    </>
);

const ReviewTable: React.FC<{ items: RetentionReviewItem[] }> = ({ items }) => (
    <table className="hidden xl:table w-full text-sm">
        <caption className="sr-only">Retention counts waiting for confirmation</caption>
        <thead>
            <tr className="text-left text-xs font-semibold text-gray-500 dark:text-gray-400">
                <th scope="col" className="min-w-[200px] px-4 py-2">Organization</th>
                <th scope="col" className="w-56 px-4 py-2">Data type</th>
                <th scope="col" className="w-32 px-4 py-2">Keeps</th>
                <th scope="col" className="w-40 px-4 py-2 text-right">Would be deleted</th>
                <th scope="col" className="min-w-[200px] px-4 py-2">Why it waits</th>
            </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 dark:divide-white/10">
            {items.map(item => (
                <tr key={rowKey(item)}>
                    <td className="px-4 py-4 align-top font-semibold text-gray-900 dark:text-white"><span className="break-words">{item.tenantName}</span></td>
                    <td className="px-4 py-4 align-top">{dataType(item)}</td>
                    <td className="px-4 py-4 align-top tabular-nums text-gray-900 dark:text-white">{keeps(item)}</td>
                    <td className="px-4 py-4 text-right align-top font-semibold tabular-nums text-gray-900 dark:text-white">{wouldDelete(item)}</td>
                    <td className="px-4 py-4 align-top">
                        <HealthChip kind="waiting" />
                        <span className={`mt-1 block ${MUTED}`}>{whyText(item)}</span>
                    </td>
                </tr>
            ))}
        </tbody>
    </table>
);

const CardField: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
    <div className="min-w-0">
        <dt className="text-xs text-gray-500 dark:text-gray-400">{label}</dt>
        <dd className="mt-1 break-words text-sm text-gray-900 dark:text-white">{children}</dd>
    </div>
);

/** Below xl the table becomes stacked cards: no horizontal scroll, names wrap. */
const ReviewCards: React.FC<{ items: RetentionReviewItem[] }> = ({ items }) => (
    <ul role="list" aria-label="Retention rows waiting for confirmation, card view" className="xl:hidden divide-y divide-gray-200 dark:divide-white/10">
        {items.map(item => (
            <li key={rowKey(item)} className="flex flex-col gap-4 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                    <span className="min-w-0 break-words text-sm font-semibold text-gray-900 dark:text-white">{item.tenantName}</span>
                    <HealthChip kind="waiting" />
                </div>
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <CardField label="Data type">{dataType(item)}</CardField>
                    <CardField label="Keeps"><span className="tabular-nums">{keeps(item)}</span></CardField>
                    <CardField label="Would be deleted"><span className="font-semibold tabular-nums">{wouldDelete(item)}</span></CardField>
                    <CardField label="Why">{whyText(item)}</CardField>
                </dl>
            </li>
        ))}
    </ul>
);

const Footer: React.FC<{ shown: number; total: number; more: boolean; loading: boolean; failed: boolean; onMore: () => void }> = ({
    shown, total, more, loading, failed, onMore,
}) => (
    <div className="flex flex-wrap items-center justify-between gap-4">
        <p className={MUTED}>{total === 1 ? 'Showing 1 row' : `Showing ${number(shown)} of ${number(total)} rows`}</p>
        {more && (
            <div className="flex flex-wrap items-center gap-4">
                {failed && <p role="status" className="break-words text-xs text-red-600 dark:text-red-400">Couldn't load more rows.</p>}
                <button type="button" className={SECONDARY_BUTTON} onClick={onMore} disabled={loading}>
                    {loading ? 'Loading...' : 'Load more rows'}
                </button>
            </div>
        )}
    </div>
);

// ── card ────────────────────────────────────────────────────────────────────

const LoadingBody: React.FC = () => (
    <div aria-busy="true" className="flex flex-col gap-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[0, 1, 2].map(i => <div key={i} className={`h-16 ${HEALTH_SKELETON}`} />)}
        </div>
        <div className={`h-40 ${HEALTH_SKELETON}`} />
    </div>
);

const lastRunHelp = (run: NonNullable<RetentionReview['lastRun']>): string => {
    const where = `${plural(run.tenants, 'organization', 'organizations')}`;
    return run.deleted > 0
        ? `Deleted ${plural(run.deleted, 'record', 'records')} across ${where}.`
        : `Counted ${plural(run.counted, 'record', 'records')} across ${where}. Deleted nothing.`;
};

/**
 * The Scheduled data retention card, the last block of the Platform health section (D-18, D-20). It has its own
 * fetch, so it renders when the health document failed or the watchdog is not installed.
 */
export const AutonomousOpsRetentionReview: React.FC<{ refreshSignal?: number }> = ({ refreshSignal = 0 }) => {
    const { hasPermission } = useUser();
    const canConfirm = hasPermission('control:platform_autonomous_ops' as any);
    const { state, load, reload, loadMore, loadingMore, moreFailed, loading, loadFailed } = useRetentionReview(refreshSignal);
    const [snapshot, setSnapshot] = useState<RetentionReviewSnapshot | null>(null);
    const review = state?.review ?? null;
    const items = state?.items ?? [];

    const openDialog = () => {
        if (review) setSnapshot({ reviewToken: review.reviewToken, totals: review.totals, countedAt: review.countedAt });
    };
    const confirmed = () => { setSnapshot(null); void load(); };

    const running = review?.mode === 'running';
    const countable = review ? review.totals.rows - review.totals.uncountable : 0;
    const next = review ? utcParts(review.nextRun) : null;
    const run = review?.lastRun ?? null;
    const last = run?.at ? formatWhen(run.at) : null;
    const counted = review?.countedAt ? formatWhen(review.countedAt) : null;
    return (
        <div className="card flex flex-col gap-6 p-6">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Scheduled data retention</h3>
            {loading && <LoadingBody />}
            {loadFailed && (
                <HealthNotice tone="red" role="alert">
                    <p>Couldn't load the retention review. Check your connection and try again.</p>
                    <p>
                        <button type="button" onClick={reload} className="text-sm font-semibold underline underline-offset-2">
                            Reload retention review
                        </button>
                    </p>
                </HealthNotice>
            )}
            {review && (
                <>
                    <dl className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        <HealthCell
                            label="Mode"
                            value={<HealthChip kind={review.mode === 'running' ? 'running_now' : review.mode} />}
                            help={review.mode === 'counting_only' ? 'Nothing is deleted yet. Counts are listed below for review.'
                                : review.mode === 'deleting_nightly' ? "Records older than each organization's retention period are deleted every night." : undefined}
                        />
                        <HealthCell
                            label="Next run"
                            value={<time dateTime={review.nextRun} title={new Date(review.nextRun).toLocaleString()}>{next ? `${next.date}, ${next.time} UTC` : '—'}</time>}
                            help="Runs organization by organization in small batches."
                        />
                        <HealthCell
                            label="Last run"
                            value={last ? <span title={last.title}>{last.text}</span> : 'Never'}
                            help={run && !run.error ? lastRunHelp(run) : undefined}
                        />
                    </dl>
                    {run?.error && (
                        <HealthNotice tone="red" role="alert">
                            <p>{`Failed: ${plain(run.error)}. It tries again at the next run.`}</p>
                        </HealthNotice>
                    )}
                </>
            )}
            <p className={MUTED}>{SCOPE_NOTE}</p>
            {review && review.notCountedYet && items.length === 0 && (
                <HealthNotice tone="blue">
                    <p>{`The first run only counts what would be deleted. It runs at ${next?.time ?? '02:00'} UTC on ${next?.date ?? 'its next date'}, and you confirm the counts here before anything is removed.`}</p>
                </HealthNotice>
            )}
            {review && !review.notCountedYet && items.length === 0 && (
                <p className="text-sm text-gray-600 dark:text-gray-400">
                    Nothing is waiting for confirmation. If an organization shortens a retention period, its next run only counts until you confirm it again.
                </p>
            )}
            {review && items.length > 0 && (
                <div className="flex flex-col gap-4">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Waiting for your confirmation</h4>
                        {counted && review.countedAt && (
                            <time dateTime={review.countedAt} title={counted.title} className={`tabular-nums ${MUTED}`}>{`Counted ${counted.text}`}</time>
                        )}
                    </div>
                    <p className="text-sm text-gray-700 dark:text-gray-200">
                        {`${plural(review.totals.records, 'record', 'records')} across ${plural(review.totals.tenants, 'organization', 'organizations')} would be deleted.`}
                    </p>
                    <ReviewTable items={items} />
                    <ReviewCards items={items} />
                    <Footer
                        shown={items.length} total={review.total} more={state?.nextOffset !== null}
                        loading={loadingMore} failed={moreFailed} onMore={() => { void loadMore(); }}
                    />
                    {canConfirm && (
                        <div className="flex flex-wrap items-center gap-4">
                            <button type="button" className={CONFIRM_BUTTON} onClick={openDialog} disabled={running || countable <= 0}>
                                <TrashIcon size={16} aria-hidden="true" />
                                Confirm deletion
                            </button>
                            <p className={MUTED}>
                                {running ? 'A run is in progress. Confirm after it finishes.'
                                    : countable <= 0 ? 'No row could be counted, so there is nothing to confirm yet.'
                                        : "One confirmation covers every row listed. Deleted records can't be restored."}
                            </p>
                        </div>
                    )}
                </div>
            )}
            <RetentionConfirmDialog open={snapshot !== null} review={snapshot} onClose={() => setSnapshot(null)} onConfirmed={confirmed} />
        </div>
    );
};

export default AutonomousOpsRetentionReview;
