import React from 'react';
import { Modal } from './Modal';
import { SECONDARY_BUTTON } from './AutonomousOpsHealthCards';
import { HealthNotice } from './AutonomousOpsHealthChips';

/** The accent confirm of a dialog that lifts a safeguard (83-UI-SPEC colour item 8), the same pattern as Resume automatic actions. */
export const ACCENT_BUTTON =
    'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-primary-600 px-4 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60';

/** A server message without its closing full stop, so it reads inside "...: {message}. Try again." */
export const plain = (message: string) => message.trim().replace(/[.\s]+$/, '');

export const plural = (n: number, one: string, many: string) => `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`;

interface TurnOffProps {
    open: boolean;
    /** The organization the rule is being turned off for; wraps when long. */
    tenantName: string;
    /** Other values the same Save writes, so the person sees everything that will change. */
    alsoBlockHours: number | null;
    alsoServices: number | null;
    pending: boolean;
    /** The full sentence to show in the red block, already worded. */
    error: string | null;
    onCancel: () => void;
    onConfirm: () => void;
}

/**
 * Turn off the two-source rule? (83-UI-SPEC section 7). Shown when a Save would turn the rule from On to Off, before
 * anything is written. Neither the Cancel button nor Esc closes it while the request is in flight.
 */
export const TurnOffRuleDialog: React.FC<TurnOffProps> = ({
    open, tenantName, alsoBlockHours, alsoServices, pending, error, onCancel, onConfirm,
}) => {
    if (!open) return null;
    const also: string[] = [];
    if (alsoBlockHours !== null) also.push(`block length ${plural(alsoBlockHours, 'hour', 'hours')}`);
    if (alsoServices !== null) also.push(`${plural(alsoServices, 'service', 'services')} watched`);
    return (
        <Modal
            isOpen
            onClose={onCancel}
            title="Turn off the two-source rule?"
            size="md"
            showClose={false}
            closeOnBackdrop={false}
            closeOnEsc={!pending}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} onClick={onCancel} disabled={pending}>Cancel</button>
                    <button type="button" className={ACCENT_BUTTON} onClick={onConfirm} disabled={pending}>
                        {pending ? 'Saving...' : 'Turn off the rule'}
                    </button>
                </>
            )}
        >
            <div className="flex flex-col gap-4">
                <p className="break-words text-sm text-gray-700 dark:text-gray-200">
                    {`With the rule off, one source is enough for Autonomous Ops to block an IP address or quarantine a file on its own for ${tenantName}. Blocks and quarantines can still be undone, and every other limit still applies: the never-touch list, 20 automatic actions an hour, and the circuit breaker.`}
                </p>
                <HealthNotice tone="amber" role="status">
                    <p>This change is recorded in the activity list and the audit log with your name.</p>
                </HealthNotice>
                {also.length > 0 && (
                    <p className="break-words text-xs text-gray-500 dark:text-gray-400">{`Also saving: ${also.join('; ')}.`}</p>
                )}
                {error && (
                    <HealthNotice tone="red" role="alert">
                        <p>{error}</p>
                    </HealthNotice>
                )}
            </div>
        </Modal>
    );
};
