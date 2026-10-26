import React, { useRef, useState } from 'react';
import { Modal } from './Modal';
import { AlertTriangleIcon } from './icons';
import { showToast } from '../utils/toast';
import { AutonomousOpsApiError, pressStop } from '../services/autonomousOpsApi';

export const REASON_MAX = 500;

const SECONDARY_BUTTON =
    'inline-flex items-center justify-center min-h-10 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ' +
    'px-4 text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-60';
const STOP_BUTTON =
    'inline-flex items-center justify-center min-h-10 rounded-lg bg-red-600 px-4 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60';

/** A server message without its closing full stop, so it reads inside "...: {message}. Try again." */
function plain(message: string): string {
    return message.trim().replace(/[.\s]+$/, '');
}

interface StopDialogProps {
    tenantName: string;
    /** Platform staff acting on one organization; tenant roles pass nothing. */
    tenantId?: string | null;
    onClose: () => void;
    /** Called after the server answered (success or a 409) so the shared poller refetches. */
    onDone: () => void;
}

/**
 * The Stop dialog (D-11, D-14): braking is one fast confirmation. The reason is optional, the focus
 * lands in it, and Ctrl/Cmd+Enter submits. The backdrop never closes it, so a typed reason is not lost.
 */
export const AutonomousOpsStopDialog: React.FC<StopDialogProps> = ({ tenantName, tenantId = null, onClose, onDone }) => {
    const [reason, setReason] = useState('');
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const inFlight = useRef(false);

    const submit = async () => {
        if (inFlight.current) return;
        inFlight.current = true;
        setPending(true);
        setError(null);
        try {
            await pressStop({ reason, tenantId });
            showToast('Automatic actions stopped.', 'success');
            onDone();
            onClose();
        } catch (e) {
            const err = e as Partial<AutonomousOpsApiError>;
            if (err.status === 409) {
                showToast(`Automatic actions were already stopped by ${err.by || 'another person'}.`, 'info');
                onDone();
                onClose();
                return;
            }
            const message = err.detail ? plain(err.detail) : '';
            setError(message
                ? `Couldn't stop automatic actions: ${message}. Try again. If it keeps failing, ask a platform administrator to use the platform-wide stop.`
                : "Couldn't stop automatic actions. Check your connection and try again.");
        } finally {
            inFlight.current = false;
            setPending(false);
        }
    };

    return (
        <Modal
            isOpen
            onClose={onClose}
            title="Stop automatic actions?"
            size="md"
            showClose={false}
            closeOnBackdrop={false}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} onClick={onClose}>Cancel</button>
                    <button type="button" className={STOP_BUTTON} onClick={submit} disabled={pending}>
                        {pending ? 'Stopping...' : 'Stop automatic actions'}
                    </button>
                </>
            )}
        >
            <div className="flex flex-col gap-4">
                <p className="break-words text-sm text-gray-600 dark:text-gray-400">
                    {`This stops new automatic decisions for ${tenantName} right away. Actions already queued for agents are held back and will not run. Approval requests can't be approved until you resume, and they keep their 24-hour clock. Undo still works.`}
                </p>
                <div className="flex flex-col gap-2">
                    <label htmlFor="autonomous-ops-stop-reason" className="text-sm font-semibold text-gray-900 dark:text-white">
                        Reason (optional)
                    </label>
                    <textarea
                        id="autonomous-ops-stop-reason"
                        rows={3}
                        maxLength={REASON_MAX}
                        value={reason}
                        onChange={e => setReason(e.target.value)}
                        onKeyDown={e => {
                            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void submit(); }
                        }}
                        aria-describedby="autonomous-ops-stop-reason-help"
                        className="w-full rounded-lg border border-gray-300 bg-white p-3 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                    />
                    <div className="flex items-start justify-between gap-4">
                        <p id="autonomous-ops-stop-reason-help" className="text-xs text-gray-500 dark:text-gray-400">
                            Shown in the banner and the activity list.
                        </p>
                        <span className="shrink-0 text-xs tabular-nums text-gray-500 dark:text-gray-400">{reason.length}/{REASON_MAX}</span>
                    </div>
                </div>
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

export default AutonomousOpsStopDialog;
