import React, { useId, useRef, useState } from 'react';
import { setOrganizationShadow } from '../../services/autonomousOpsGoLive';
import type { GoLiveOrganization } from '../../services/autonomousOpsGoLive';
import type { AutonomousOpsApiError } from '../../services/autonomousOpsApi';
import { showToast } from '../../utils/toast';
import { Modal } from '../Modal';
import { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
import { ACCENT_BUTTON, plain } from '../AutonomousOpsResponseSettingsDialogs';
import { AlertTriangleIcon } from '../icons';
import {
    KEEP_LIFTED, KEEP_SHADOW_ON, LIFTING, LIFT_BUTTON, LIFT_FALLBACK, LIFT_FORBIDDEN, LIFT_REASSURANCE, RESTORE_FALLBACK,
    RESTORE_FORBIDDEN, SAVING, TURN_ON, TYPE_NAME_LABEL, TYPE_NAME_REASON, liftBody, liftEvidence, liftRefused, liftTitle,
    liftedToast, restoreBody, restoreFailed, restoreTitle, restoredToast, typeNameHelper,
} from './goLiveCopy';

interface ShadowDialogProps {
    org: GoLiveOrganization;
    onClose: () => void;
    /** Called after the server answered (a write or a refusal); the card refetches so the table shows the truth. */
    onDone: () => void;
}

const FIELD =
    'min-h-10 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white';

/** The title wraps: the Modal title row truncates, and an organization name can be long. */
const WrappedTitle: React.FC<{ text: string }> = ({ text }) => <span className="block whitespace-normal break-words">{text}</span>;

const ErrorBlock: React.FC<{ message: string }> = ({ message }) => (
    <div role="alert" className="flex items-start gap-2 break-words rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-300">
        <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
        <span className="min-w-0">{message}</span>
    </div>
);

/**
 * Lift shadow mode for {name}? (86-UI-SPEC section 6d, E11, D-15): the one place shadow mode is lifted. The accent confirm
 * stays disabled until the trimmed input equals the organization name exactly. The server still gates the lift: a 409 shows
 * its reasons, keeps the input and refetches the table. Esc and Keep shadow mode on are ignored while the request is in flight.
 */
export const LiftShadowDialog: React.FC<ShadowDialogProps> = ({ org, onClose, onDone }) => {
    const uid = useId();
    const [typed, setTyped] = useState('');
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const inFlight = useRef(false);
    const matches = typed.trim() === org.name.trim();

    const submit = async () => {
        if (inFlight.current || !matches) return;
        inFlight.current = true;
        setPending(true);
        setError(null);
        try {
            await setOrganizationShadow(org.id, false);
            showToast(liftedToast(org.name), 'success');
            onDone();
            onClose();
        } catch (e) {
            const err = e as Partial<AutonomousOpsApiError>;
            if (err.status === 403) setError(LIFT_FORBIDDEN);
            else if (err.status === 409) {
                setError(liftRefused(plain(err.detail ?? '')));
                onDone();        // the table refetches so the reasons on screen are the server's current ones
            } else setError(LIFT_FALLBACK);
            inFlight.current = false;
            setPending(false);
        }
    };

    const reasonId = `${uid}-reason`;
    const helpId = `${uid}-help`;
    return (
        <Modal
            isOpen onClose={onClose} title={<WrappedTitle text={liftTitle(org.name)} />} size="md" showClose={false}
            closeOnBackdrop={false} closeOnEsc={!pending}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} onClick={onClose} disabled={pending}>{KEEP_SHADOW_ON}</button>
                    <button
                        type="button" className={ACCENT_BUTTON} onClick={() => void submit()} disabled={pending || !matches}
                        aria-describedby={matches ? undefined : reasonId}
                    >
                        {pending ? LIFTING : LIFT_BUTTON}
                    </button>
                </>
            )}
        >
            <div className="flex flex-col gap-4">
                <p className="break-words text-sm text-gray-700 dark:text-gray-200">{liftBody(org.name)}</p>
                <div className="break-words rounded-lg border border-gray-200 p-4 text-sm text-gray-900 dark:border-white/10 dark:text-white">
                    {liftEvidence(org.daysObserved ?? 0, org.wouldHaveDone)}
                </div>
                <p className="break-words text-xs text-gray-500 dark:text-gray-400">{LIFT_REASSURANCE}</p>
                <div className="flex flex-col gap-1">
                    <label htmlFor={`${uid}-name`} className="text-sm font-semibold text-gray-900 dark:text-white">{TYPE_NAME_LABEL}</label>
                    <p id={helpId} className="break-words text-xs text-gray-500 dark:text-gray-400">{typeNameHelper(org.name)}</p>
                    <input
                        id={`${uid}-name`} type="text" autoComplete="off" autoFocus value={typed} disabled={pending}
                        aria-describedby={matches ? helpId : `${helpId} ${reasonId}`}
                        onChange={e => setTyped(e.target.value)} className={FIELD}
                    />
                    {!matches && <p id={reasonId} className="break-words text-xs text-gray-500 dark:text-gray-400">{TYPE_NAME_REASON}</p>}
                </div>
                {error && <ErrorBlock message={error} />}
            </div>
        </Modal>
    );
};

/**
 * Turn shadow mode back on for {name}? (86-UI-SPEC section 6d, E12, R11): always allowed, never gated, no typed name. One
 * confirm so an accidental click cannot flip a live organization. Keep it lifted takes first focus.
 */
export const RestoreShadowDialog: React.FC<ShadowDialogProps> = ({ org, onClose, onDone }) => {
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const inFlight = useRef(false);

    const submit = async () => {
        if (inFlight.current) return;
        inFlight.current = true;
        setPending(true);
        setError(null);
        try {
            await setOrganizationShadow(org.id, true);
            showToast(restoredToast(org.name), 'success');
            onDone();
            onClose();
        } catch (e) {
            const err = e as Partial<AutonomousOpsApiError>;
            if (err.status === 403) setError(RESTORE_FORBIDDEN);
            else setError(err.detail ? restoreFailed(plain(err.detail)) : RESTORE_FALLBACK);
            inFlight.current = false;
            setPending(false);
        }
    };

    return (
        <Modal
            isOpen onClose={onClose} title={<WrappedTitle text={restoreTitle(org.name)} />} size="md" showClose={false}
            closeOnBackdrop={false} closeOnEsc={!pending}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} onClick={onClose} disabled={pending} autoFocus>{KEEP_LIFTED}</button>
                    <button type="button" className={ACCENT_BUTTON} onClick={() => void submit()} disabled={pending}>
                        {pending ? SAVING : TURN_ON}
                    </button>
                </>
            )}
        >
            <div className="flex flex-col gap-4">
                <p className="break-words text-sm text-gray-700 dark:text-gray-200">{restoreBody(org.name)}</p>
                {error && <ErrorBlock message={error} />}
            </div>
        </Modal>
    );
};
