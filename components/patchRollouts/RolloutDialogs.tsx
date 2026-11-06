import React, { useEffect, useId, useRef, useState } from 'react';
import { cancelRollout, resumeRollout } from '../../services/patchRollouts/lifecycle';
import type { RolloutCard } from '../../services/patchRollouts/types';
import { showToast } from '../../utils/toast';
import { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
import { HealthNotice } from '../AutonomousOpsHealthChips';
import { ACCENT_BUTTON, plain } from '../AutonomousOpsResponseSettingsDialogs';
import { AlertTriangleIcon } from '../icons';
import { Modal } from '../Modal';
import { WAIT_FOR_REVERT } from './rolloutCopy';

/**
 * The Resume and Cancel dialogs for a halted rollout (84-18, UI-SPEC section 4, D-16). Resume needs a typed reason and
 * reports whether the health check passed; Cancel says what it ends and what stays. Neither closes on the backdrop, and
 * neither closes on Esc or on its dismiss button while a request is in flight. No button is labelled just Cancel: the
 * dismiss buttons say what staying means (Keep halted, Keep rollout). Server messages are rendered as React text.
 */

export const REASON_MAX = 500;

const RESUME_FALLBACK = "Couldn't resume the rollout. Check your connection and try again.";
const CANCEL_FALLBACK = "Couldn't cancel the rollout. Check your connection and try again.";
const NO_RESUME = "You don't have permission to resume rollouts.";
const NO_CANCEL = "You don't have permission to cancel rollouts.";
const REVERT_RUNNING = 'A revert is still running. It finishes on its own.';
const DANGER_BUTTON =
    'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-red-600 px-4 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60';
const BODY = 'break-words text-sm text-gray-600 dark:text-gray-400';
const ACTION_BUTTON = `${SECONDARY_BUTTON} min-h-10`;

export interface DialogBaseProps {
    rolloutId: string;
    /** The organization platform staff entered from Tenants, else null. */
    tenantId: string | null;
    /** Close without a change, or after the request was answered. */
    onClose: () => void;
    /** The server answered (done, still halted or refused for permission): the parent reads the card again. */
    onDone: () => void;
}

export interface ResumeDialogProps extends DialogBaseProps {
    /** The halted ring, named in the body and in the toast unless the server names another. */
    ringName: string;
}

export interface CancelDialogProps extends DialogBaseProps {
    rolloutName: string;
    /** A revert is still running; Cancel leaves it to finish. */
    revertRunning: boolean;
}

const failureOf = (error: unknown) => {
    const failed = error as { status?: number; detail?: string };
    return { status: failed?.status, detail: typeof failed?.detail === 'string' ? failed.detail : '' };
};

const ErrorBlock: React.FC<{ text: string }> = ({ text }) => (
    <HealthNotice tone="red" icon={AlertTriangleIcon} role="alert"><p className="break-words">{text}</p></HealthNotice>
);

export const ResumeDialog: React.FC<ResumeDialogProps> = ({ rolloutId, ringName, tenantId, onClose, onDone }) => {
    const uid = useId();
    const [reason, setReason] = useState('');
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const inFlight = useRef(false);
    const alive = useRef(true);
    useEffect(() => {
        alive.current = true;
        return () => { alive.current = false; };
    }, []);

    const typed = reason.trim();
    const fieldId = `${uid}-reason`;

    const submit = async () => {
        if (inFlight.current || !typed) return;
        inFlight.current = true;
        setPending(true);
        setError(null);
        try {
            const result = await resumeRollout(rolloutId, typed, tenantId);
            const ring = result?.ring || ringName;
            if (result?.status === 'still_halted') {
                showToast(`The health check for ${ring} still fails. The rollout stays halted.`, 'info');
            } else {
                showToast(`Resuming. ${ring} passed its check and the rollout continues.`, 'success');
            }
            onClose();
            onDone();
        } catch (failure) {
            if (!alive.current) return;
            const { status, detail } = failureOf(failure);
            if (status === 403) {
                showToast(NO_RESUME, 'error');
                onClose();
                onDone();
                return;
            }
            setError(detail ? `Couldn't resume the rollout: ${plain(detail)}. Try again.` : RESUME_FALLBACK);
        } finally {
            inFlight.current = false;
            if (alive.current) setPending(false);
        }
    };

    return (
        <Modal
            isOpen
            onClose={onClose}
            title="Resume this rollout?"
            size="md"
            showClose={false}
            closeOnBackdrop={false}
            closeOnEsc={!pending}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} disabled={pending} onClick={onClose}>Keep halted</button>
                    <button type="button" className={ACCENT_BUTTON} disabled={pending || !typed} onClick={() => void submit()}>
                        {pending ? 'Resuming...' : 'Resume rollout'}
                    </button>
                </>
            )}
        >
            <div className="flex flex-col gap-4">
                <p className={BODY}>
                    {`Resuming runs the health check for ${ringName} again. The rollout continues only if every check passes. Computers that failed are not skipped.`}
                </p>
                <div className="flex flex-col gap-2">
                    <label htmlFor={fieldId} className="text-sm font-semibold text-gray-900 dark:text-white">Reason for resuming</label>
                    <textarea
                        id={fieldId}
                        rows={3}
                        maxLength={REASON_MAX}
                        value={reason}
                        autoFocus
                        aria-required="true"
                        aria-describedby={`${fieldId}-help`}
                        onChange={e => setReason(e.target.value)}
                        className="w-full rounded-lg border border-gray-300 bg-white p-3 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                    />
                    <div className="flex items-start justify-between gap-4">
                        <p id={`${fieldId}-help`} className="break-words text-xs text-gray-500 dark:text-gray-400">
                            Recorded in the activity list and the audit log with your name.
                        </p>
                        <span className="shrink-0 text-xs tabular-nums text-gray-500 dark:text-gray-400">{reason.length}/{REASON_MAX}</span>
                    </div>
                </div>
                {error && <ErrorBlock text={error} />}
            </div>
        </Modal>
    );
};

export const CancelDialog: React.FC<CancelDialogProps> = ({ rolloutId, rolloutName, revertRunning, tenantId, onClose, onDone }) => {
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const inFlight = useRef(false);
    const alive = useRef(true);
    useEffect(() => {
        alive.current = true;
        return () => { alive.current = false; };
    }, []);

    const submit = async () => {
        if (inFlight.current) return;
        inFlight.current = true;
        setPending(true);
        setError(null);
        try {
            await cancelRollout(rolloutId, tenantId);
            showToast(`Rollout "${rolloutName}" cancelled.`, 'success');
            onClose();
            onDone();
        } catch (failure) {
            if (!alive.current) return;
            const { status, detail } = failureOf(failure);
            if (status === 403) {
                showToast(NO_CANCEL, 'error');
                onClose();
                onDone();
                return;
            }
            setError(detail ? `Couldn't cancel the rollout: ${plain(detail)}. Try again.` : CANCEL_FALLBACK);
        } finally {
            inFlight.current = false;
            if (alive.current) setPending(false);
        }
    };

    return (
        <Modal
            isOpen
            onClose={onClose}
            title="Cancel this rollout?"
            size="md"
            showClose={false}
            closeOnBackdrop={false}
            closeOnEsc={!pending}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} disabled={pending} onClick={onClose}>Keep rollout</button>
                    <button type="button" className={DANGER_BUTTON} disabled={pending} onClick={() => void submit()}>
                        {pending ? 'Cancelling...' : 'Cancel rollout'}
                    </button>
                </>
            )}
        >
            <div className="flex flex-col gap-4">
                <p className={BODY}>
                    {`This ends "${rolloutName}". Computers that already have the patches keep them, and nothing further installs. A cancelled rollout can't be started again; start a new one instead.`}
                </p>
                {revertRunning && (
                    <HealthNotice tone="amber" icon={AlertTriangleIcon} role="status"><p>{REVERT_RUNNING}</p></HealthNotice>
                )}
                {error && <ErrorBlock text={error} />}
            </div>
        </Modal>
    );
};

/**
 * Why Resume cannot be pressed right now, or null. The server sets `resumeBlockedReason` while a computer is still being
 * reverted and then also reports `canResume` false; a card that says both `canResume` and `revertRunning` gets the same
 * sentence, so Resume is never offered during a revert.
 */
const resumeBlock = (card: RolloutCard): string | null =>
    card.revertRunning ? (card.resumeBlockedReason || WAIT_FOR_REVERT) : card.resumeBlockedReason || null;

/** The halt block shows Resume rollout when it is allowed, or allowed but waiting on a revert, and Cancel rollout when allowed. */
export const hasHaltActions = (card: RolloutCard): boolean =>
    card.canResume || card.canCancel || !!card.resumeBlockedReason;

/**
 * The only two ways forward for a halted rollout (D-16): Resume rollout and Cancel rollout, each behind its own
 * confirmation. Nothing else: there is no control to skip a failed computer. Both render from the server's flags only;
 * the routes check manage:patches and the session again. `onChanged` reads the card again after either succeeds.
 */
export const HaltActions: React.FC<{ card: RolloutCard; tenantId: string | null; onChanged: () => void }> = ({ card, tenantId, onChanged }) => {
    const uid = useId();
    const [open, setOpen] = useState<'resume' | 'cancel' | null>(null);
    const blocked = resumeBlock(card);
    const showResume = card.canResume || !!card.resumeBlockedReason;
    const reasonId = `${uid}-resume-blocked`;
    const close = () => setOpen(null);

    return (
        <>
            {showResume && (
                <div className="flex flex-col items-start gap-1">
                    <button
                        type="button"
                        className={ACTION_BUTTON}
                        disabled={blocked !== null}
                        aria-describedby={blocked ? reasonId : undefined}
                        onClick={() => setOpen('resume')}
                    >
                        Resume rollout
                    </button>
                    {blocked && <p id={reasonId} className="break-words text-xs">{blocked}</p>}
                </div>
            )}
            {card.canCancel && (
                <div>
                    <button type="button" className={ACTION_BUTTON} onClick={() => setOpen('cancel')}>Cancel rollout</button>
                </div>
            )}
            {open === 'resume' && (
                <ResumeDialog
                    rolloutId={card.id}
                    ringName={card.halt?.ringName ?? ''}
                    tenantId={tenantId}
                    onClose={close}
                    onDone={onChanged}
                />
            )}
            {open === 'cancel' && (
                <CancelDialog
                    rolloutId={card.id}
                    rolloutName={card.name}
                    revertRunning={card.revertRunning}
                    tenantId={tenantId}
                    onClose={close}
                    onDone={onChanged}
                />
            )}
        </>
    );
};
