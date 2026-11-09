import React from 'react';
import { Modal } from '../Modal';
import { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
import { HealthNotice } from '../AutonomousOpsHealthChips';
import { ACCENT_BUTTON } from '../AutonomousOpsResponseSettingsDialogs';
import { PauseCircleIcon } from '../icons';
import { DIALOGS, fill } from './serviceDeskCopy';

interface DialogProps {
    open: boolean;
    pending: boolean;
    /** The full sentence of the red save-error block, already worded; shown inside the dialog so a failure is not hidden behind it. */
    error: string | null;
    onCancel: () => void;
    onConfirm: () => void;
}

const ErrorBlock: React.FC<{ error: string | null }> = ({ error }) => (error ? (
    <HealthNotice tone="red" role="alert">
        <p>{error}</p>
    </HealthNotice>
) : null);

/**
 * Post answers to requesters? (UI-SPEC 2, dialogs). Opens when a Save would newly turn Post answers on, before anything is
 * written. Keep Drafts only takes first focus. Neither it nor Esc closes the dialog while the request is in flight.
 */
export const PostAnswersDialog: React.FC<DialogProps & { firstBlocker: string | null }> = ({
    open, pending, error, firstBlocker, onCancel, onConfirm,
}) => {
    if (!open) return null;
    return (
        <Modal
            isOpen
            onClose={onCancel}
            title={DIALOGS.post.title}
            size="md"
            showClose={false}
            closeOnBackdrop={false}
            closeOnEsc={!pending}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} onClick={onCancel} disabled={pending}>{DIALOGS.post.keep}</button>
                    <button type="button" className={ACCENT_BUTTON} onClick={onConfirm} disabled={pending}>
                        {pending ? DIALOGS.post.pending : DIALOGS.post.confirm}
                    </button>
                </>
            )}
        >
            <div className="flex flex-col gap-4">
                <p className="break-words text-sm text-gray-700 dark:text-gray-200">{DIALOGS.post.body}</p>
                {firstBlocker && (
                    <HealthNotice tone="amber" role="status">
                        <p>{fill(DIALOGS.post.blocker, { blocker: firstBlocker })}</p>
                    </HealthNotice>
                )}
                <ErrorBlock error={error} />
            </div>
        </Modal>
    );
};

/**
 * Restore Post answers? (UI-SPEC 2, dialogs). The only way back after the desk dropped to Drafts only; same pattern as
 * the dialog above, with Restoring... on the accent button.
 */
export const RestorePostingDialog: React.FC<DialogProps> = ({ open, pending, error, onCancel, onConfirm }) => {
    if (!open) return null;
    return (
        <Modal
            isOpen
            onClose={onCancel}
            title={DIALOGS.restore.title}
            size="md"
            showClose={false}
            closeOnBackdrop={false}
            closeOnEsc={!pending}
            icon={<PauseCircleIcon size={20} aria-hidden="true" />}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} onClick={onCancel} disabled={pending}>{DIALOGS.restore.keep}</button>
                    <button type="button" className={ACCENT_BUTTON} onClick={onConfirm} disabled={pending}>
                        {pending ? DIALOGS.restore.pending : DIALOGS.restore.confirm}
                    </button>
                </>
            )}
        >
            <div className="flex flex-col gap-4">
                <p className="break-words text-sm text-gray-700 dark:text-gray-200">{DIALOGS.restore.body}</p>
                <ErrorBlock error={error} />
            </div>
        </Modal>
    );
};
