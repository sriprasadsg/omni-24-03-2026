import React, { useId, useRef, useState } from 'react';
import { useUser } from '../../contexts/UserContext';
import { AutonomousOpsApiError } from '../../services/autonomousOpsApi';
import { approveLine, denyLine } from '../../services/patchRollouts/approvals';
import type { ApprovalCard, ApprovalLine } from '../../services/patchRollouts/types';
import { showToast } from '../../utils/toast';
import { StateChip } from '../AutonomousOpsActivityList';
import { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
import { formatExpires } from '../AutonomousOpsIncidentCard';
import { ACCENT_BUTTON, plain, plural } from '../AutonomousOpsResponseSettingsDialogs';
import { ChevronDownIcon, ClockIcon, InfoIcon, LayersIcon, PowerIcon } from '../icons';

/**
 * The rollout approval card of Needs your decision (84-15, UI-SPEC section 6, PTCH-06, D-07, D-08). One card per ring
 * with a step waiting for a person; each line (Install, Restart, Revert restart) has its own Approve and Deny and
 * there is no approve-all. Every control comes from the server's flags on the line; the browser only disables Approve
 * during a stop or once the deadline has passed, and hides the buttons in shadow mode. Every string is React text.
 *
 * DEV-1: the decisions call the rollout line routes (services/patchRollouts/approvals.ts).
 */

const WAITING_LINE = 'Waiting for someone with approval access.';
const BLOCKED_LINE = 'Paused while automatic actions are stopped.';
const DEADLINE_CHIP =
    'inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs font-semibold tabular-nums break-words ' +
    'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-400/10 dark:text-amber-200 dark:border-amber-400/25';
const MUTED = 'break-words text-gray-600 dark:text-gray-400';
const TEXT_BUTTON = 'inline-flex items-center gap-1 text-sm font-semibold text-gray-900 dark:text-white underline underline-offset-2';

type Decision = 'approve' | 'deny';

const FALLBACK: Record<Decision, string> = {
    approve: "Couldn't approve this action. Check your connection and try again.",
    deny: "Couldn't deny this action. Check your connection and try again.",
};
const VERB: Record<Decision, string> = { approve: 'approve this action', deny: 'deny this action' };

/** What this browser knows about a line after a person decided it, until the server's own settled text arrives. */
interface LinePatch { state: 'approved' | 'denied'; result: string }

const isPast = (iso: string | null | undefined, now: number) => {
    const at = iso ? Date.parse(iso) : NaN;
    return Number.isFinite(at) && at <= now;
};
const fullTime = (iso: string | null | undefined) => {
    const at = iso ? new Date(iso) : null;
    return at && !Number.isNaN(at.getTime()) ? at.toLocaleString() : undefined;
};
const clockText = (iso: string) =>
    new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });

/** `Ring 2 of 4: Pilot · 12 computers` gives `Pilot`; empty when the server's subtitle has another shape. */
export const ringNameOf = (subtitle: string): string => /^Ring \d+ of \d+: (.+) · [^·]*$/.exec(subtitle)?.[1] ?? '';

/** Patches named by an Install label (`Install 4 patches on 12 computers`), else 0. */
const patchCountOf = (label: string): number => Number(/^Install ([\d,]+) patch/.exec(label)?.[1]?.replace(/,/g, '') ?? 0);

/** The nearest expiry among the lines still waiting for a person, else the card's own. */
function nearestExpiry(card: ApprovalCard, patches: Record<string, LinePatch>): string | null {
    const open = card.lines.filter(l => l.state === 'pending' && !patches[l.line]);
    if (open.length === 0) return null;
    const times = open.map(l => l.expiresAt).filter((t): t is string => !!t && !Number.isNaN(Date.parse(t)));
    if (times.length === 0) return card.expiresAt;
    return times.reduce((a, b) => (Date.parse(a) <= Date.parse(b) ? a : b));
}

// ---------------------------------------------------------------- one line

interface LineProps {
    card: ApprovalCard;
    line: ApprovalLine;
    patch: LinePatch | undefined;
    now: number;
    stopped: boolean;
    shadow: boolean;
    tenantId: string | null;
    onPatched: (line: ApprovalLine['line'], patch: LinePatch) => void;
    onDecided: (card: ApprovalCard) => void;
    onStale?: () => void;
}

const RolloutLine: React.FC<LineProps> = ({ card, line, patch, now, stopped, shadow, tenantId, onPatched, onDecided, onStale }) => {
    const { currentUser } = useUser();
    const [busy, setBusy] = useState<Decision | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [open, setOpen] = useState(false);
    const sent = useRef(false);
    const row = useRef<HTMLLIElement>(null);
    const ids = useId();
    const ringName = ringNameOf(card.subtitle);

    // A local patch only stands in until the server says the line is no longer pending; then the server's text wins.
    const live = patch !== undefined && line.state === 'pending' ? patch : undefined;
    const waiting = line.state === 'pending' && !live;
    const lineExpired = waiting && isPast(line.expiresAt, now);
    const showControls = waiting && !shadow;
    // During a stop the server reports canApprove false; a person who can deny still sees Approve, disabled (UI-SPEC S7).
    const showApprove = line.canApprove || (stopped && line.canDeny);
    const hasButtons = showApprove || line.canDeny;
    const settledState = live?.state ?? (line.state === 'pending' ? null : line.state);
    const result = live ? live.result
        : lineExpired
            ? `Expired after 24 hours, counted as denied.${ringName ? ` The rollout halts at ${ringName}.` : ''}`
            : line.resultText;
    const named = `${line.label}${ringName ? ` in ${ringName}` : ''}, ${card.name}`;
    const whatId = `${ids}-what`;
    const blockedId = `${ids}-blocked`;
    const chip = settledState === 'denied' || settledState === 'expired' || lineExpired ? 'refused' : 'pending';
    const Icon = line.line === 'install' ? null : PowerIcon;
    const listId = `${ids}-computers`;
    const hasWhat = waiting && !!line.whatHappens;
    const approveDescribedBy = [hasWhat ? whatId : '', stopped ? blockedId : ''].filter(Boolean).join(' ') || undefined;

    const decide = async (kind: Decision) => {
        if (sent.current) return;
        sent.current = true;
        setBusy(kind);
        setError(null);
        const person = currentUser?.name || 'a person';
        const n = line.computerTotal;
        const computers = plural(n, 'computer', 'computers');
        try {
            if (kind === 'approve') {
                const out = await approveLine(card.rolloutId, card.ring, line.line, tenantId);
                const when = out.when === 'window' && out.windowOpensAt
                    ? `when your window opens at ${clockText(out.windowOpensAt)}` : 'now';
                onPatched(line.line, { state: 'approved', result: out.message || `Approved. ${line.label}.` });
                showToast(
                    line.line === 'install'
                        ? `Approved. ${plural(patchCountOf(line.label), 'patch', 'patches')} will install on ${computers} ${when}.`
                        : `Approved. ${n === 1 ? '1 computer restarts' : `${computers} restart`} ${when} with a 5-minute warning.`,
                    'success',
                );
            } else {
                const out = await denyLine(card.rolloutId, card.ring, line.line, tenantId);
                onPatched(line.line, {
                    state: 'denied',
                    result: out.message || `Denied by ${person}.${ringName ? ` The rollout halts at ${ringName}.` : ''}`,
                });
                showToast(`Denied. Nothing was sent to ${computers}.`, 'success');
            }
            onDecided(card);
            row.current?.focus();
        } catch (err) {
            const detail = err instanceof AutonomousOpsApiError ? err.detail : '';
            // A 409 or 404 will not change on a retry: say why and re-read the cards and the stop state.
            const lasting = err instanceof AutonomousOpsApiError && (err.status === 409 || err.status === 404);
            setError(detail ? `Couldn't ${VERB[kind]}: ${plain(detail)}.${lasting ? '' : ' Try again.'}` : FALLBACK[kind]);
            if (lasting) onStale?.();
        } finally {
            sent.current = false;
            setBusy(null);
        }
    };

    const disabled = busy !== null || lineExpired;

    return (
        <li
            ref={row}
            data-line={line.line}
            tabIndex={-1}
            role={!waiting ? 'status' : undefined}
            className="flex flex-col gap-4 px-6 py-4 focus:outline-none lg:flex-row lg:items-start lg:justify-between"
        >
            <div className="flex min-w-0 flex-1 flex-col gap-2">
                <div className="flex flex-wrap items-center gap-2">
                    <StateChip chip={chip as React.ComponentProps<typeof StateChip>['chip']} />
                    {Icon && <Icon size={16} aria-hidden="true" className="shrink-0 text-gray-500 dark:text-gray-400" />}
                    <span className="break-words text-sm font-semibold text-gray-900 dark:text-white">{line.label}</span>
                </div>
                {line.targetText && <p className="break-all font-mono text-xs text-gray-600 dark:text-gray-400">{line.targetText}</p>}
                {line.why && <p className={`text-sm ${MUTED}`}>{line.why}</p>}
                {hasWhat && (
                    <p id={whatId} className="flex items-start gap-1 break-words text-xs text-gray-600 dark:text-gray-400">
                        <InfoIcon size={12} aria-hidden="true" className="mt-0.5 shrink-0" />
                        <span>{line.whatHappens}</span>
                    </p>
                )}
                {line.computers.length > 0 && (
                    <div className="flex flex-col gap-2">
                        <button type="button" className={`${TEXT_BUTTON} self-start`} aria-expanded={open} aria-controls={listId} onClick={() => setOpen(v => !v)}>
                            {open ? 'Hide computers' : 'Show computers'}
                            <ChevronDownIcon size={16} aria-hidden="true" className={open ? 'rotate-180' : ''} />
                        </button>
                        {open && (
                            <div id={listId} className="flex flex-col gap-1">
                                <ul className="flex flex-col gap-1">
                                    {line.computers.map(name => (
                                        <li key={name} className="break-all font-mono text-xs text-gray-900 dark:text-white">{name}</li>
                                    ))}
                                </ul>
                                {line.computerTotal > line.computers.length && (
                                    <p className="text-xs text-gray-600 dark:text-gray-400">{`Showing ${line.computers.length} of ${line.computerTotal}.`}</p>
                                )}
                            </div>
                        )}
                    </div>
                )}
                {result && <p className="break-words text-sm text-gray-900 dark:text-white">{result}</p>}
            </div>

            {showControls && (
                <div className="flex shrink-0 flex-col items-start gap-2">
                    {hasButtons ? (
                        <div className="flex flex-wrap gap-2">
                            {showApprove && (
                                <button
                                    type="button"
                                    className={ACCENT_BUTTON}
                                    disabled={disabled || stopped}
                                    aria-label={`Approve: ${named}`}
                                    aria-describedby={approveDescribedBy}
                                    onClick={() => void decide('approve')}
                                >
                                    {busy === 'approve' ? 'Approving...' : 'Approve'}
                                </button>
                            )}
                            {line.canDeny && (
                                <button
                                    type="button"
                                    className={`${SECONDARY_BUTTON} min-h-10`}
                                    disabled={busy !== null}
                                    aria-label={`Deny: ${named}`}
                                    aria-describedby={hasWhat ? whatId : undefined}
                                    onClick={() => void decide('deny')}
                                >
                                    {busy === 'deny' ? 'Denying...' : 'Deny'}
                                </button>
                            )}
                        </div>
                    ) : (
                        <p className="break-words text-xs text-gray-600 dark:text-gray-400">{WAITING_LINE}</p>
                    )}
                    {hasButtons && stopped && <p id={blockedId} className="break-words text-xs text-gray-600 dark:text-gray-400">{BLOCKED_LINE}</p>}
                    {error && <p role="alert" className="break-words text-sm text-red-600 dark:text-red-400">{error}</p>}
                </div>
            )}
        </li>
    );
};

// ---------------------------------------------------------------- one card

export interface RolloutApprovalCardProps {
    card: ApprovalCard;
    /** The browser clock corrected by the server's (the section passes it). */
    now?: number;
    /** Automatic actions are stopped: Approve is disabled, Deny is not. */
    stopped: boolean;
    shadow: boolean;
    tenantId?: string | null;
    /** A line was decided: the section re-reads its cards. */
    onDecided: (card: ApprovalCard) => void;
    /** The server refused for a lasting reason (a 409 or 404): the section re-reads the cards and the status. */
    onStale?: () => void;
}

export const RolloutApprovalCard: React.FC<RolloutApprovalCardProps> = ({
    card, now = Date.now(), stopped, shadow, tenantId = null, onDecided, onStale,
}) => {
    const titleId = useId();
    const [patches, setPatches] = useState<Record<string, LinePatch>>({});
    const expiry = nearestExpiry(card, patches);
    const chipText = expiry && !isPast(expiry, now) ? formatExpires(expiry, now) : expiry ? 'Expired' : null;

    return (
        <article id={card.anchorId} tabIndex={-1} aria-labelledby={titleId} className="card overflow-hidden focus:outline-none">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-gray-200 px-6 py-4 dark:border-white/10">
                <div className="flex min-w-0 items-start gap-4">
                    <LayersIcon size={20} aria-hidden="true" className="shrink-0 text-gray-500 dark:text-gray-400" />
                    <div className="flex min-w-0 flex-col gap-1">
                        <h3 id={titleId} className="break-words text-sm font-semibold text-gray-900 dark:text-white">{card.name}</h3>
                        <p className="break-words text-xs text-gray-600 dark:text-gray-400">{card.subtitle}</p>
                    </div>
                </div>
                {chipText && (
                    <span className={DEADLINE_CHIP} title={fullTime(expiry)}>
                        <ClockIcon size={12} aria-hidden="true" />
                        {chipText}
                    </span>
                )}
            </div>
            <ul className="divide-y divide-gray-200 dark:divide-white/10">
                {card.lines.map(line => (
                    <RolloutLine
                        key={line.line}
                        card={card}
                        line={line}
                        patch={patches[line.line]}
                        now={now}
                        stopped={stopped}
                        shadow={shadow}
                        tenantId={tenantId}
                        onPatched={(kind, patch) => setPatches(prev => ({ ...prev, [kind]: patch }))}
                        onDecided={onDecided}
                        onStale={onStale}
                    />
                ))}
            </ul>
        </article>
    );
};

export default RolloutApprovalCard;
