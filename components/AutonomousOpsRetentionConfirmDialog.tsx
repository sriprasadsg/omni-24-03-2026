import React, { useRef, useState } from 'react';
import { Modal } from './Modal';
import { AlertTriangleIcon, TrashIcon } from './icons';
import { SECONDARY_BUTTON } from './AutonomousOpsHealthCards';
import { formatClock } from './AutonomousOpsHealthBanners';
import { confirmRetention } from '../services/autonomousOpsApi';
import type { AutonomousOpsApiError, RetentionReview } from '../services/autonomousOpsApi';
import { showToast } from '../utils/toast';

const CONFIRM_BUTTON =
    'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-red-600 px-4 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60';

/** What the Super Admin saw when the dialog opened: the token confirms exactly these counts, never a later poll. */
export type RetentionReviewSnapshot = Pick<RetentionReview, 'reviewToken' | 'totals' | 'countedAt'>;

/** A server message without its closing full stop, so it reads inside "...: {message}. Try again." */
const plain = (message: string) => message.trim().replace(/[.\s]+$/, '');

export const plural = (n: number, one: string, many: string) => `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`;

interface DialogProps {
    open: boolean;
    review: RetentionReviewSnapshot | null;
    /** Close without doing anything: Keep waiting and Esc. */
    onClose: () => void;
    /** The dialog is done and the card must close it and fetch the review again. */
    onConfirmed: () => void;
}

const Inner: React.FC<{ review: RetentionReviewSnapshot; onClose: () => void; onConfirmed: () => void }> = ({ review, onClose, onConfirmed }) => {
    const [checked, setChecked] = useState(false);
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [stale, setStale] = useState(false);
    const inFlight = useRef(false);

    const { totals } = review;
    const summary = `${plural(totals.records, 'record', 'records')} across ${plural(totals.tenants, 'organization', 'organizations')}`
        + (review.countedAt ? `, counted ${formatClock(review.countedAt)}.` : '.');
    const uncountable = totals.uncountable;

    const submit = async () => {
        if (inFlight.current || !checked) return;
        inFlight.current = true;
        setPending(true);
        setError(null);
        try {
            await confirmRetention(review.reviewToken);
            showToast('Retention confirmed. Old records will be deleted from the next nightly run.', 'success');
            onConfirmed();
        } catch (e) {
            const err = e as Partial<AutonomousOpsApiError>;
            if (err.status === 409) {
                // The nightly job recounted since this review loaded: the token no longer matches what was reviewed.
                setStale(true);
                setChecked(false);
            } else if (err.status === 403) {
                showToast('Only a platform administrator can confirm deletion.', 'error');
                onConfirmed();
            } else {
                const message = err.detail ? plain(err.detail) : '';
                setError(message
                    ? `Couldn't confirm deletion: ${message}. Try again.`
                    : "Couldn't confirm deletion. Check your connection and try again.");
            }
        } finally {
            inFlight.current = false;
            setPending(false);
        }
    };

    // Keep waiting promises that nothing was deleted, which stops being true once the request has been sent:
    // neither the button nor Esc may close the dialog until the answer arrives.
    return (
        <Modal
            isOpen
            onClose={onClose}
            title="Confirm deletion of old records?"
            size="md"
            showClose={false}
            closeOnBackdrop={false}
            closeOnEsc={!pending}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} onClick={onClose} disabled={pending}>Keep waiting</button>
                    {stale ? (
                        <button type="button" className={SECONDARY_BUTTON} onClick={onConfirmed}>Reload review</button>
                    ) : (
                        <button type="button" className={CONFIRM_BUTTON} onClick={submit} disabled={pending || !checked}>
                            <TrashIcon size={16} aria-hidden="true" />
                            {pending ? 'Confirming...' : 'Confirm deletion'}
                        </button>
                    )}
                </>
            )}
        >
            <div className="flex flex-col gap-4">
                <label className="flex items-start gap-2 text-sm font-semibold text-gray-900 dark:text-white">
                    <input
                        type="checkbox"
                        checked={checked}
                        onChange={e => setChecked(e.target.checked)}
                        aria-required="true"
                        disabled={stale}
                        className="mt-0.5 h-4 w-4 shrink-0"
                    />
                    <span className="min-w-0 break-words">I have reviewed the counts for every organization listed.</span>
                </label>
                <p className="break-words text-sm text-gray-600 dark:text-gray-400">
                    From the next nightly run at 02:00 UTC, records older than each organization's retention period will be deleted. Deleted records can't be restored.
                </p>
                <div className="break-words rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700 dark:border-white/10 dark:bg-white/[0.04] dark:text-gray-200">
                    <p>{summary}</p>
                    {uncountable > 0 && (
                        <p>{`${plural(uncountable, 'row', 'rows')} could not be counted and ${uncountable === 1 ? 'stays' : 'stay'} waiting.`}</p>
                    )}
                </div>
                <p className="break-words text-xs text-gray-500 dark:text-gray-400">
                    Audit logs, the audit ledger, decision records and compliance evidence are never deleted.
                </p>
                {stale && (
                    <div role="alert" className="flex items-start gap-2 break-words rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-300">
                        <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
                        <span className="min-w-0">The counts changed since you opened this review. Reload the review and check the new counts before confirming.</span>
                    </div>
                )}
                {error && (
                    <div role="alert" className="flex items-start gap-2 break-words rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-300">
                        <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
                        <span className="min-w-0">{error}</span>
                    </div>
                )}
            </div>
        </Modal>
    );
};

/**
 * The Confirm deletion dialog (82-UI-SPEC section 7, T-82-42). The one destructive action of the phase:
 * the review checkbox is the first focusable element and gates the button, nothing submits from the
 * keyboard, and one click sends one request. Closing and reopening starts from a clean dialog.
 */
export const RetentionConfirmDialog: React.FC<DialogProps> = ({ open, review, onClose, onConfirmed }) =>
    open && review ? <Inner review={review} onClose={onClose} onConfirmed={onConfirmed} /> : null;

export default RetentionConfirmDialog;
