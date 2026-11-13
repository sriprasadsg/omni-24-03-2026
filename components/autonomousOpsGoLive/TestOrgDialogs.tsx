import React, { useId, useRef, useState } from 'react';
import { clearTestOrganization, markTestOrganization } from '../../services/autonomousOpsGoLive';
import type { GoLiveOrganization } from '../../services/autonomousOpsGoLive';
import type { AutonomousOpsApiError } from '../../services/autonomousOpsApi';
import { showToast } from '../../utils/toast';
import { Modal } from '../Modal';
import { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
import { ACCENT_BUTTON } from '../AutonomousOpsResponseSettingsDialogs';
import { AlertTriangleIcon } from '../icons';
import {
    CLEAR_BODY, CLEAR_FALLBACK, CLEAR_FORBIDDEN, MARK_BODY, MARK_FALLBACK, MARK_FORBIDDEN, TEST_ORG_CANCEL, TEST_ORG_CLEAR,
    TEST_ORG_CLEARING, TEST_ORG_KEEP, TEST_ORG_MARKING, TEST_ORG_USE, TYPE_NAME_REASON, clearTitle, clearedToast, markTitle,
    markTypeLabel, markedToast, typeNameHelper,
} from './goLiveCopy';

interface TestOrgDialogProps {
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
 * The sentence for a failed write: the server's own plain sentence for a 4xx (409, 422, 404 name the cause), the 403 and
 * fallback sentences otherwise. Rendered as React text only.
 */
function failureSentence(e: unknown, forbidden: string, fallback: string): string {
    const err = e as Partial<AutonomousOpsApiError>;
    if (err.status === 403) return forbidden;
    const detail = typeof err.detail === 'string' ? err.detail.trim() : '';
    return typeof err.status === 'number' && err.status >= 400 && err.status < 500 && detail ? detail : fallback;
}

/**
 * Use {name} as the go-live test organization? (D-23): the confirm stays disabled until the trimmed input equals the
 * organization name exactly. The server decides every outcome; a 409 or 422 is shown as its own sentence, and a 409 refetches
 * because another organization may have been marked meanwhile. Esc and Cancel are ignored while the request is in flight.
 */
export const MarkTestOrgDialog: React.FC<TestOrgDialogProps> = ({ org, onClose, onDone }) => {
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
            await markTestOrganization(org.id, typed.trim());
            showToast(markedToast(org.name), 'success');
            onDone();
            onClose();
        } catch (e) {
            setError(failureSentence(e, MARK_FORBIDDEN, MARK_FALLBACK));
            if ((e as Partial<AutonomousOpsApiError>).status === 409) onDone();
            inFlight.current = false;
            setPending(false);
        }
    };

    const reasonId = `${uid}-reason`;
    const helpId = `${uid}-help`;
    return (
        <Modal
            isOpen onClose={onClose} title={<WrappedTitle text={markTitle(org.name)} />} size="md" showClose={false}
            closeOnBackdrop={false} closeOnEsc={!pending}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} onClick={onClose} disabled={pending}>{TEST_ORG_CANCEL}</button>
                    <button
                        type="button" className={ACCENT_BUTTON} onClick={() => void submit()} disabled={pending || !matches}
                        aria-describedby={matches ? undefined : reasonId}
                    >
                        {pending ? TEST_ORG_MARKING : TEST_ORG_USE}
                    </button>
                </>
            )}
        >
            <div className="flex flex-col gap-4">
                <p className="break-words text-sm text-gray-700 dark:text-gray-200">{MARK_BODY}</p>
                <div className="flex flex-col gap-1">
                    <label htmlFor={`${uid}-name`} className="text-sm font-semibold text-gray-900 dark:text-white">{markTypeLabel(org.name)}</label>
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
 * Clear the test mark on {name}? (D-23): one confirm, no typed name. The row only offers it while the organization's shadow
 * mode is on; the server still refuses with a 409 sentence otherwise, shown here as an alert.
 */
export const ClearTestOrgDialog: React.FC<TestOrgDialogProps> = ({ org, onClose, onDone }) => {
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const inFlight = useRef(false);

    const submit = async () => {
        if (inFlight.current) return;
        inFlight.current = true;
        setPending(true);
        setError(null);
        try {
            await clearTestOrganization(org.id);
            showToast(clearedToast(org.name), 'success');
            onDone();
            onClose();
        } catch (e) {
            setError(failureSentence(e, CLEAR_FORBIDDEN, CLEAR_FALLBACK));
            if ((e as Partial<AutonomousOpsApiError>).status === 409) onDone();
            inFlight.current = false;
            setPending(false);
        }
    };

    return (
        <Modal
            isOpen onClose={onClose} title={<WrappedTitle text={clearTitle(org.name)} />} size="md" showClose={false}
            closeOnBackdrop={false} closeOnEsc={!pending}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} onClick={onClose} disabled={pending} autoFocus>{TEST_ORG_KEEP}</button>
                    <button type="button" className={ACCENT_BUTTON} onClick={() => void submit()} disabled={pending}>
                        {pending ? TEST_ORG_CLEARING : TEST_ORG_CLEAR}
                    </button>
                </>
            )}
        >
            <div className="flex flex-col gap-4">
                <p className="break-words text-sm text-gray-700 dark:text-gray-200">{CLEAR_BODY}</p>
                {error && <ErrorBlock message={error} />}
            </div>
        </Modal>
    );
};
