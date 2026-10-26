import React, { useRef, useState } from 'react';
import { Modal } from './Modal';
import { AlertTriangleIcon } from './icons';
import { stoppedBy, stopReasonLine } from './AutonomousOpsStopBanner';
import { showToast } from '../utils/toast';
import {
    AutonomousOpsApiError, StopView,
    pressPlatformStop, pressStop, resumePlatformStop, resumeStop,
} from '../services/autonomousOpsApi';

export const REASON_MAX = 500;

export type StopDialogKind = 'stop' | 'resume';
/** `tenant` acts on one organization; `platform` is the Super Admin's platform-wide stop. */
export type StopDialogScope = 'tenant' | 'platform';

const SECONDARY_BUTTON =
    'inline-flex items-center justify-center min-h-10 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ' +
    'px-4 text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-60';
const STOP_BUTTON =
    'inline-flex items-center justify-center min-h-10 rounded-lg bg-red-600 px-4 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60';
const RESUME_BUTTON =
    'inline-flex items-center justify-center min-h-10 rounded-lg bg-primary-600 px-4 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60';

/** A server message without its closing full stop, so it reads inside "...: {message}. Try again." */
function plain(message: string): string {
    return message.trim().replace(/[.\s]+$/, '');
}

interface Copy {
    title: string;
    confirm: string;
    pending: string;
    toast: string;
    label: string;
    failurePrefix: string;
}

function copyFor(kind: StopDialogKind, scope: StopDialogScope): Copy {
    if (kind === 'stop') {
        return scope === 'platform'
            ? {
                title: 'Stop automatic actions for every organization?', confirm: 'Stop all organizations', pending: 'Stopping...',
                toast: 'Automatic actions stopped for every organization.', label: 'Reason (optional)',
                failurePrefix: "Couldn't stop automatic actions",
            }
            : {
                title: 'Stop automatic actions?', confirm: 'Stop automatic actions', pending: 'Stopping...',
                toast: 'Automatic actions stopped.', label: 'Reason (optional)',
                failurePrefix: "Couldn't stop automatic actions",
            };
    }
    return scope === 'platform'
        ? {
            title: 'Resume automatic actions for every organization?', confirm: 'Resume all organizations', pending: 'Resuming...',
            toast: 'Automatic actions resumed for every organization.', label: 'Reason for resuming',
            failurePrefix: "Couldn't resume automatic actions",
        }
        : {
            title: 'Resume automatic actions?', confirm: 'Resume automatic actions', pending: 'Resuming...',
            toast: 'Automatic actions resumed.', label: 'Reason for resuming',
            failurePrefix: "Couldn't resume automatic actions",
        };
}

function failureText(copy: Copy, kind: StopDialogKind, scope: StopDialogScope, detail: string): string {
    const message = detail ? plain(detail) : '';
    if (!message) return `${copy.failurePrefix}. Check your connection and try again.`;
    const hint = kind === 'stop' && scope === 'tenant'
        ? ' If it keeps failing, ask a platform administrator to use the platform-wide stop.'
        : '';
    return `${copy.failurePrefix}: ${message}. Try again.${hint}`;
}

function bodyText(kind: StopDialogKind, scope: StopDialogScope, tenantName: string, shadow: boolean): string {
    if (kind === 'stop') {
        return scope === 'platform'
            ? 'This halts new automatic decisions across the whole platform and holds back queued automatic instructions for all organizations. Only a platform administrator can resume it.'
            : `This stops new automatic decisions for ${tenantName} right away. Actions already queued for agents are held back and will not run. Approval requests can't be approved until you resume, and they keep their 24-hour clock. Undo still works.`;
    }
    const clause = scope === 'tenant' && shadow ? ' in shadow mode, so nothing is carried out' : '';
    return `Actions that were held back during the stop were cancelled and will not run. New decisions can start again${clause}.`;
}

async function send(kind: StopDialogKind, scope: StopDialogScope, reason: string, tenantId: string | null) {
    if (scope === 'platform') {
        return kind === 'stop' ? pressPlatformStop({ reason }) : resumePlatformStop({ reason });
    }
    return kind === 'stop' ? pressStop({ reason, tenantId }) : resumeStop({ reason, tenantId });
}

interface StopDialogProps {
    kind: StopDialogKind;
    scope: StopDialogScope;
    tenantName: string;
    /** Platform staff acting on one organization; tenant roles pass nothing. */
    tenantId?: string | null;
    /** The stop being resumed, shown in the Resume dialog. */
    current?: StopView | null;
    /** Whether shadow mode is on, for the Resume dialog's clause. */
    shadow?: boolean;
    onClose: () => void;
    /** Called after the server answered (success, 409 or 403) so the shared poller refetches. */
    onDone: () => void;
}

/**
 * The Stop and Resume dialogs (D-11, D-14, UI-SPEC 3e). Stopping is one fast confirmation: the
 * reason is optional and Ctrl/Cmd+Enter submits. Resuming is deliberate: a typed reason is
 * required (whitespace counts as empty) and no keyboard shortcut submits. The backdrop never
 * closes the dialog, so a typed reason is not lost.
 */
export const AutonomousOpsStopDialog: React.FC<StopDialogProps> = ({
    kind, scope, tenantName, tenantId = null, current = null, shadow = false, onClose, onDone,
}) => {
    const [reason, setReason] = useState('');
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [emptyError, setEmptyError] = useState(false);
    const inFlight = useRef(false);

    const copy = copyFor(kind, scope);
    const isResume = kind === 'resume';
    const empty = reason.trim() === '';
    const fieldId = `autonomous-ops-${kind}-${scope}-reason`;

    const submit = async () => {
        if (inFlight.current) return;
        if (isResume && empty) { setEmptyError(true); return; }
        inFlight.current = true;
        setPending(true);
        setError(null);
        try {
            await send(kind, scope, reason, tenantId);
            showToast(copy.toast, 'success');
            onDone();
            onClose();
        } catch (e) {
            const err = e as Partial<AutonomousOpsApiError>;
            if (!isResume && err.status === 409) {
                showToast(`Automatic actions were already stopped by ${err.by || 'another person'}.`, 'info');
                onDone();
                onClose();
                return;
            }
            if (isResume && err.status === 403) {
                showToast('Only a platform administrator can resume this stop.', 'error');
                onDone();
                onClose();
                return;
            }
            setError(failureText(copy, kind, scope, err.detail ?? ''));
        } finally {
            inFlight.current = false;
            setPending(false);
        }
    };

    const onReasonKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key !== 'Enter') return;
        if (!isResume) {
            if (e.ctrlKey || e.metaKey) { e.preventDefault(); void submit(); }
            return;
        }
        // Resume has no shortcut; Enter on an empty field only explains what is missing.
        if (empty) { e.preventDefault(); setEmptyError(true); }
    };

    return (
        <Modal
            isOpen
            onClose={onClose}
            title={copy.title}
            size="md"
            showClose={false}
            closeOnBackdrop={false}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} onClick={onClose}>Cancel</button>
                    <button
                        type="button"
                        className={isResume ? RESUME_BUTTON : STOP_BUTTON}
                        onClick={submit}
                        disabled={pending || (isResume && empty)}
                    >
                        {pending ? copy.pending : copy.confirm}
                    </button>
                </>
            )}
        >
            <div className="flex flex-col gap-4">
                {isResume && current && (
                    <div className="break-words rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700 dark:border-white/10 dark:bg-white/[0.04] dark:text-gray-200">
                        <p>{stoppedBy(current)}</p>
                        <p>{stopReasonLine(current)}</p>
                    </div>
                )}
                <p className="break-words text-sm text-gray-600 dark:text-gray-400">{bodyText(kind, scope, tenantName, shadow)}</p>
                <div className="flex flex-col gap-2">
                    <label htmlFor={fieldId} className="text-sm font-semibold text-gray-900 dark:text-white">{copy.label}</label>
                    <textarea
                        id={fieldId}
                        rows={3}
                        maxLength={REASON_MAX}
                        value={reason}
                        onChange={e => { setReason(e.target.value); if (e.target.value.trim()) setEmptyError(false); }}
                        onKeyDown={onReasonKey}
                        aria-required={isResume ? 'true' : undefined}
                        aria-describedby={`${fieldId}-help`}
                        className="w-full rounded-lg border border-gray-300 bg-white p-3 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                    />
                    <div className="flex items-start justify-between gap-4">
                        <p id={`${fieldId}-help`} className="text-xs text-gray-500 dark:text-gray-400">
                            Shown in the banner and the activity list.
                        </p>
                        <span className="shrink-0 text-xs tabular-nums text-gray-500 dark:text-gray-400">{reason.length}/{REASON_MAX}</span>
                    </div>
                    {isResume && emptyError && (
                        <p role="alert" className="text-xs text-red-600 dark:text-red-400">Enter a reason to resume.</p>
                    )}
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
