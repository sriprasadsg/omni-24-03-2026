import React, { useCallback, useEffect, useRef, useState } from 'react';
import { fetchRetentionReview } from '../services/autonomousOpsApi';
import type { RetentionReview, RetentionReviewItem } from '../services/autonomousOpsApi';
import { useUser } from '../contexts/UserContext';
import { formatWhen } from './AutonomousOpsActivityList';
import { HealthCell, HealthChip } from './AutonomousOpsHealthChips';
import { RetentionConfirmDialog, plural } from './AutonomousOpsRetentionConfirmDialog';
import type { RetentionReviewSnapshot } from './AutonomousOpsRetentionConfirmDialog';
import { TrashIcon } from './icons';

export const RETENTION_POLL_MS = 30_000;
const MUTED = 'break-words text-xs text-gray-500 dark:text-gray-400';
const CONFIRM_BUTTON =
    'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-red-600 px-4 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60';
const SCOPE_NOTE = 'Audit logs, the audit ledger, decision records and compliance evidence are never deleted by this job.';

const number = (n: number) => n.toLocaleString('en-US');

/** "Oct 31, 2026, 02:00 UTC": the schedule is UTC, so the date and time are stated in UTC. */
function nextRunText(iso: string): string {
    const at = new Date(iso);
    if (Number.isNaN(at.getTime())) return '—';
    const date = at.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
    const time = at.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' });
    return `${date}, ${time} UTC`;
}

// ── data ────────────────────────────────────────────────────────────────────

interface ReviewState { review: RetentionReview; items: RetentionReviewItem[]; nextOffset: number | null }

/**
 * The first page on mount, then every 30 s while the tab is visible and when the page Refresh counter changes.
 * A background read never shows a skeleton; a failure keeps the last review. Rows already loaded by Load more
 * stay while the token is unchanged, because the token covers every waiting row and its count.
 */
function useRetentionReview(refreshSignal: number) {
    const [state, setState] = useState<ReviewState | null>(null);
    const [failed, setFailed] = useState(false);
    const alive = useRef(true);
    const lastSignal = useRef(refreshSignal);

    const load = useCallback(async () => {
        try {
            const next = await fetchRetentionReview(0);
            if (!alive.current) return;
            if (!Array.isArray(next?.items)) throw new Error('unreadable retention review');
            setState(prev => (prev && prev.review.reviewToken === next.reviewToken && prev.items.length > next.items.length
                ? { review: next, items: prev.items, nextOffset: prev.nextOffset }
                : { review: next, items: next.items, nextOffset: next.nextOffset }));
            setFailed(false);
        } catch {
            if (alive.current) setFailed(true);
        }
    }, []);

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

    return { state, load, failed };
}

// ── review table ────────────────────────────────────────────────────────────

const ReviewTable: React.FC<{ items: RetentionReviewItem[] }> = ({ items }) => (
    <table className="w-full text-sm">
        <caption className="sr-only">Retention counts waiting for confirmation</caption>
        <thead>
            <tr className="text-left text-xs font-semibold text-gray-500 dark:text-gray-400">
                <th scope="col" className="px-4 py-2">Organization</th>
                <th scope="col" className="w-56 px-4 py-2">Data type</th>
                <th scope="col" className="w-32 px-4 py-2">Keeps</th>
                <th scope="col" className="w-40 px-4 py-2 text-right">Would be deleted</th>
                <th scope="col" className="px-4 py-2">Why it waits</th>
            </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 dark:divide-white/10">
            {items.map(item => (
                <tr key={`${item.tenantId}:${item.type}`}>
                    <td className="px-4 py-4 align-top font-semibold text-gray-900 dark:text-white"><span className="break-words">{item.tenantName}</span></td>
                    <td className="px-4 py-4 align-top">
                        <span className="block break-words text-gray-900 dark:text-white">{item.label}</span>
                        <span className={`block font-mono ${MUTED}`}>{item.collection}</span>
                    </td>
                    <td className="px-4 py-4 align-top tabular-nums text-gray-900 dark:text-white">{`${item.days} days`}</td>
                    <td className="px-4 py-4 text-right align-top font-semibold tabular-nums text-gray-900 dark:text-white">
                        {item.count === null ? '—' : `${number(item.count)} records`}
                    </td>
                    <td className="px-4 py-4 align-top"><HealthChip kind="waiting" /></td>
                </tr>
            ))}
        </tbody>
    </table>
);

// ── card ────────────────────────────────────────────────────────────────────

/**
 * The Scheduled data retention card, the last block of the Platform health section (D-18, D-20). It has its own
 * fetch, so it renders when the health document failed or the watchdog is not installed.
 */
export const AutonomousOpsRetentionReview: React.FC<{ refreshSignal?: number }> = ({ refreshSignal = 0 }) => {
    const { hasPermission } = useUser();
    const canConfirm = hasPermission('control:platform_autonomous_ops' as any);
    const { state, load } = useRetentionReview(refreshSignal);
    const [snapshot, setSnapshot] = useState<RetentionReviewSnapshot | null>(null);
    const review = state?.review ?? null;

    const openDialog = () => {
        if (review) setSnapshot({ reviewToken: review.reviewToken, totals: review.totals, countedAt: review.countedAt });
    };
    const closeDialog = () => setSnapshot(null);
    const confirmed = () => { setSnapshot(null); void load(); };

    const next = review ? nextRunText(review.nextRun) : null;
    const last = review?.lastRun?.at ? formatWhen(review.lastRun.at) : null;
    return (
        <div className="card flex flex-col gap-6 p-6">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Scheduled data retention</h3>
            {review && (
                <dl className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <HealthCell
                        label="Mode"
                        value={<HealthChip kind={review.mode === 'running' ? 'running_now' : review.mode} />}
                    />
                    <HealthCell
                        label="Next run"
                        value={<time dateTime={review.nextRun} title={new Date(review.nextRun).toLocaleString()}>{next}</time>}
                        help="Runs organization by organization in small batches."
                    />
                    <HealthCell label="Last run" value={last ? <span title={last.title}>{last.text}</span> : 'Never'} />
                </dl>
            )}
            <p className={MUTED}>{SCOPE_NOTE}</p>
            {review && state && state.items.length > 0 && (
                <div className="flex flex-col gap-4">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Waiting for your confirmation</h4>
                    </div>
                    <p className="text-sm text-gray-700 dark:text-gray-200">
                        {`${plural(review.totals.records, 'record', 'records')} across ${plural(review.totals.tenants, 'organization', 'organizations')} would be deleted.`}
                    </p>
                    <ReviewTable items={state.items} />
                    {canConfirm && (
                        <div className="flex flex-wrap items-center gap-4">
                            <button type="button" className={CONFIRM_BUTTON} onClick={openDialog}>
                                <TrashIcon size={16} aria-hidden="true" />
                                Confirm deletion
                            </button>
                            <p className={MUTED}>One confirmation covers every row listed. Deleted records can't be restored.</p>
                        </div>
                    )}
                </div>
            )}
            <RetentionConfirmDialog open={snapshot !== null} review={snapshot} onClose={closeDialog} onConfirmed={confirmed} />
        </div>
    );
};

export default AutonomousOpsRetentionReview;
