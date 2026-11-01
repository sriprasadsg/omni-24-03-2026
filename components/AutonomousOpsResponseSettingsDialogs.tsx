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

interface ApplyAllProps {
    open: boolean;
    /** One line per ticked setting, for example "Two-source rule: off" and "Block length: 12 hours". */
    lines: string[];
    /** How many organizations this click will write. */
    organizations: number;
    /** True when the rule is being turned off everywhere: adds the amber block and the required checkbox. */
    loosening: boolean;
    pending: boolean;
    error: string | null;
    onCancel: () => void;
    onConfirm: () => void;
}

const ApplyAllInner: React.FC<Omit<ApplyAllProps, 'open'>> = ({ lines, organizations, loosening, pending, error, onCancel, onConfirm }) => {
    // The box starts unchecked each time the dialog opens and stays ticked through a retry of the failed organizations.
    const [understood, setUnderstood] = React.useState(false);
    const blocked = loosening && !understood;
    return (
        <Modal
            isOpen
            onClose={onCancel}
            title="Apply to every organization?"
            size="md"
            showClose={false}
            closeOnBackdrop={false}
            closeOnEsc={!pending}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} onClick={onCancel} disabled={pending}>Cancel</button>
                    <button type="button" className={ACCENT_BUTTON} onClick={onConfirm} disabled={pending || blocked}>
                        {pending ? 'Applying...' : 'Apply to every organization'}
                    </button>
                </>
            )}
        >
            <div className="flex flex-col gap-4">
                {loosening && (
                    <label className="flex items-start gap-2 text-sm font-semibold text-gray-900 dark:text-white">
                        <input
                            type="checkbox" checked={understood} aria-required="true" disabled={pending}
                            onChange={e => setUnderstood(e.target.checked)} className="mt-0.5 h-4 w-4 shrink-0"
                        />
                        <span className="min-w-0 break-words">I understand this changes every organization.</span>
                    </label>
                )}
                <p className="break-words text-sm text-gray-700 dark:text-gray-200">
                    This writes the setting to each organization on its own. An organization's administrator can change it back afterwards. The platform organization is not changed.
                </p>
                <div className="flex flex-col gap-1 break-words rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700 dark:border-white/10 dark:bg-white/[0.04] dark:text-gray-200">
                    {lines.map(line => <p key={line}>{line}</p>)}
                    <p className="tabular-nums">{`${plural(organizations, 'organization', 'organizations')} will be changed.`}</p>
                </div>
                {loosening && (
                    <HealthNotice tone="amber" role="status">
                        <p>Turning the rule off lets one source block an IP address or quarantine a file on its own in every organization. Every other limit still applies.</p>
                    </HealthNotice>
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

/**
 * Apply to every organization? (83-UI-SPEC section 7). The platform form opens it before anything is written. Turning the
 * rule off needs the required box first, which is the first focusable element. Esc and Cancel are ignored while the request is in flight.
 */
export const ApplyAllDialog: React.FC<ApplyAllProps> = ({ open, ...rest }) => (open ? <ApplyAllInner {...rest} /> : null);
