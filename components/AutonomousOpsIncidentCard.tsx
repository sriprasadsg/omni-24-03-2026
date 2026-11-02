import React, { useId, useRef, useState } from 'react';
import { useUser } from '../contexts/UserContext';
import { AutonomousOpsApiError } from '../services/autonomousOpsApi';
import { approveAction, confirmIsolation, denyAction } from '../services/autonomousOpsIncidentsApi';
import type { IncidentAction, IncidentCard, IncidentLineBucket, IncidentStep } from '../services/autonomousOpsIncidentsApi';
import { showToast } from '../utils/toast';
import { StateChip, formatWhen } from './AutonomousOpsActivityList';
import { SECONDARY_BUTTON } from './AutonomousOpsHealthCards';
import { HealthNotice } from './AutonomousOpsHealthChips';
import { fillBlockTimes } from './AutonomousOpsRowActions';
import { ACCENT_BUTTON, plain, plural } from './AutonomousOpsResponseSettingsDialogs';
import {
    CheckCircleIcon, ChevronDownIcon, ClockIcon, InfoIcon, LockIcon, PauseCircleIcon, ShieldAlertIcon, XCircleIcon,
} from './icons';

/**
 * One incident card (83-19, UI-SPEC 2a): a header with the nearest deadline and one line per action. Every control
 * comes from the server's flags on the line; the browser only disables Approve and Confirm isolation during a stop,
 * hides the buttons in shadow mode and disables them once a deadline has passed. Every string is React text.
 */

const MIN = 60_000;
const COLLAPSE_AT = 5;
const WAITING_LINE = 'Waiting for someone with approval access.';
const EXPIRED_RESULT = 'This request has expired and counts as denied.';
const BLOCKED_LINE = 'Paused while automatic actions are stopped.';
const ALREADY_MADE = 'This decision was already made.';
const DEADLINE_CHIP =
    'inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs font-semibold tabular-nums break-words ' +
    'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-400/10 dark:text-amber-200 dark:border-amber-400/25';
const MUTED = 'break-words text-gray-600 dark:text-gray-400';
const TEXT_BUTTON = 'inline-flex items-center gap-1 text-sm font-semibold text-gray-900 dark:text-white underline underline-offset-2';

// ---------------------------------------------------------------- countdown text (pure)

function minutesLeft(iso: string, now: number): number {
    const ms = Date.parse(iso) - now;
    return Number.isNaN(ms) ? 0 : Math.floor(Math.max(0, ms) / MIN);
}

/** `Expires in 19 h`, `Expires in 42 min`, `Expires in under 1 min`, or `Expired` once the time has come. */
export function formatExpires(iso: string, now: number = Date.now()): string {
    const ms = Date.parse(iso) - now;
    if (Number.isNaN(ms) || ms <= 0) return 'Expired';
    const minutes = minutesLeft(iso, now);
    if (minutes < 1) return 'Expires in under 1 min';
    return minutes < 60 ? `Expires in ${minutes} min` : `Expires in ${Math.floor(minutes / 60)} h`;
}

/** `Reverts in 3 h 12 min`, `Reverts in 12 min`, `Reverts in under 1 min`. Never negative: a past time reads as under 1 min. */
export function formatReverts(iso: string, now: number = Date.now()): string {
    const minutes = minutesLeft(iso, now);
    if (minutes < 1) return 'Reverts in under 1 min';
    return minutes < 60 ? `Reverts in ${minutes} min` : `Reverts in ${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

const isPast = (iso: string | null | undefined, now: number) => !!iso && !(Date.parse(iso) > now);
const fullTime = (iso: string | null | undefined) => {
    const at = iso ? new Date(iso) : null;
    return at && !Number.isNaN(at.getTime()) ? at.toLocaleString() : undefined;
};

// ---------------------------------------------------------------- what a decision leaves on a line

/** What the browser knows about a line after a person decided it, until the next background read replaces it. */
export interface LinePatch {
    bucket?: IncidentLineBucket;
    result?: string | null;
    message?: string | null;
    confirmedAt?: string | null;
}

export type StopScope = 'tenant' | 'platform' | null;

type Decision = 'approve' | 'deny' | 'confirm';

const FALLBACK: Record<Decision, string> = {
    approve: "Couldn't approve this action. Check your connection and try again.",
    deny: "Couldn't deny this action. Check your connection and try again.",
    confirm: "Couldn't confirm isolation. Check your connection and try again.",
};
const VERB: Record<Decision, string> = { approve: 'approve this action', deny: 'deny this action', confirm: 'confirm isolation' };

const ONE_LINE_TARGET = /\s*\(PID \d+\)$/;

// ---------------------------------------------------------------- one action line

const STEP_ICON: Record<IncidentStep['state'], { Icon: React.FC<any>; word: string }> = {
    pending: { Icon: ClockIcon, word: 'Pending' },
    done: { Icon: CheckCircleIcon, word: 'Done' },
    failed: { Icon: XCircleIcon, word: 'Failed' },
    skipped: { Icon: PauseCircleIcon, word: 'Not run' },
};

interface LineProps {
    card: IncidentCard;
    action: IncidentAction;
    patch: LinePatch | undefined;
    now: number;
    stop: StopScope;
    shadow: boolean;
    cardExpired: boolean;
    tenantId: string | null;
    onDecided: (card: IncidentCard, actionId: string, patch: LinePatch) => void;
}

const ActionLine: React.FC<LineProps> = ({ card, action, patch, now, stop, shadow, cardExpired, tenantId, onDecided }) => {
    const { currentUser } = useUser();
    const [busy, setBusy] = useState<Decision | null>(null);
    const [error, setError] = useState<string | null>(null);
    const sent = useRef(false);
    const row = useRef<HTMLLIElement>(null);
    const ids = useId();
    const host = card.host || 'this computer';

    const settled = patch !== undefined;
    const waiting = action.needsPerson && !settled;
    const openIsolation = waiting && action.command === 'isolate_host' && !action.expiresAt && !!action.revertsAt;
    const lineExpired = waiting && !openIsolation && isPast(action.expiresAt, now);
    const showControls = waiting && !lineExpired && !shadow;
    const hasButtons = openIsolation ? action.canConfirmIsolation : action.canApprove || action.canDeny;
    const blocked = stop !== null;
    const bucket = patch?.bucket ?? action.bucket;
    const confirmedAt = patch?.confirmedAt ?? action.confirmedAt;

    const resultText = lineExpired ? EXPIRED_RESULT : settled ? (patch.result ?? action.result) : action.result;
    const result = resultText
        ? (fillBlockTimes(resultText, action.command === 'isolate_host' ? confirmedAt : action.blockedUntil) ?? resultText)
        : null;
    const consequence = action.consequenceText
        ? (fillBlockTimes(action.consequenceText, action.revertsAt) ?? action.consequenceText)
        : null;

    const processName = action.chain?.process.name;
    const shortTarget = (processName || action.target || '').replace(ONE_LINE_TARGET, '');
    const named = `${action.label}${shortTarget ? ` ${shortTarget}` : ''} on ${host}`;
    const describedBy = [consequence ? `${ids}-what` : '', blocked ? `${ids}-blocked` : ''].filter(Boolean).join(' ') || undefined;

    const decide = async (kind: Decision) => {
        if (sent.current) return;
        sent.current = true;
        setBusy(kind);
        setError(null);
        const person = currentUser?.name || 'a person';
        try {
            if (kind === 'approve') await approveAction(action.id, tenantId);
            else if (kind === 'deny') await denyAction(action.id, tenantId);
            else await confirmIsolation(action.id, tenantId);
            const next: LinePatch = kind === 'approve'
                ? { bucket: 'pending', result: `Approved. Sent to ${host}.` }
                : kind === 'deny'
                    ? { bucket: 'refused', result: `Denied by ${person}.` }
                    : {
                        bucket: 'done', confirmedAt: new Date().toISOString(),
                        result: `Confirmed by ${person} at {at}. The computer stays isolated until a person restores it.`,
                    };
            onDecided(card, action.id, next);
            row.current?.focus();
            showToast(
                kind === 'approve' ? `Approved. Sent to ${host}.`
                    : kind === 'deny' ? `Denied. Nothing was sent to ${host}.`
                        : `Isolation confirmed. ${host} stays isolated until you restore it.`,
                'success',
            );
        } catch (err) {
            const detail = err instanceof AutonomousOpsApiError ? err.detail : '';
            if (err instanceof AutonomousOpsApiError && err.status === 409 && /expired/i.test(detail)) {
                onDecided(card, action.id, { result: EXPIRED_RESULT });
            } else if (err instanceof AutonomousOpsApiError && err.status === 409 && plain(detail) === plain(ALREADY_MADE)) {
                onDecided(card, action.id, { message: ALREADY_MADE });
            } else {
                setError(detail ? `Couldn't ${VERB[kind]}: ${plain(detail)}. Try again.` : FALLBACK[kind]);
            }
        } finally {
            sent.current = false;
            setBusy(null);
        }
    };

    const deadline = !waiting ? null
        : openIsolation ? { text: formatReverts(action.revertsAt as string, now), at: action.revertsAt }
            : action.expiresAt ? { text: formatExpires(action.expiresAt, now), at: action.expiresAt } : null;
    const disabled = busy !== null || cardExpired;
    const steps = !waiting && action.chain && action.chain.steps.length > 0 ? action.chain.steps : null;

    return (
        <li
            ref={row}
            data-action-id={action.id}
            tabIndex={-1}
            role={settled ? 'status' : undefined}
            className="flex flex-col gap-4 px-6 py-4 focus:outline-none lg:flex-row lg:items-start lg:justify-between"
        >
            <div className="flex min-w-0 flex-1 flex-col gap-2">
                <div className="flex flex-wrap items-center gap-2">
                    <StateChip chip={bucket as React.ComponentProps<typeof StateChip>['chip']} />
                    <span className="break-words text-sm font-semibold text-gray-900 dark:text-white">{action.label}</span>
                    {deadline && (
                        <span className={DEADLINE_CHIP} title={fullTime(deadline.at)}>
                            <ClockIcon size={12} aria-hidden="true" />
                            {deadline.text}
                        </span>
                    )}
                </div>
                {action.target && <p className="break-all font-mono text-xs text-gray-600 dark:text-gray-400">{action.target}</p>}
                {action.chain?.path && <p className="break-all font-mono text-xs text-gray-600 dark:text-gray-400">{action.chain.path}</p>}
                {action.reason && <p className={`text-sm ${MUTED}`}>{action.reason}</p>}
                {action.ruleId && <p className="break-all font-mono text-xs text-gray-600 dark:text-gray-400">{action.ruleId}</p>}
                {waiting && action.notice && (
                    <HealthNotice tone="blue">
                        <p>{action.notice}</p>
                    </HealthNotice>
                )}
                {consequence && (
                    <p id={`${ids}-what`} className="flex items-start gap-1 break-words text-xs text-gray-600 dark:text-gray-400">
                        <InfoIcon size={12} aria-hidden="true" className="mt-0.5 shrink-0" />
                        <span>{consequence}</span>
                    </p>
                )}
                {steps && (
                    <ol aria-label="Steps" className="flex flex-col gap-1 text-sm text-gray-900 dark:text-white">
                        {steps.map(step => {
                            const { Icon, word } = STEP_ICON[step.state] ?? STEP_ICON.pending;
                            return (
                                <li key={step.label} className="flex flex-wrap items-center gap-2 break-words">
                                    <Icon size={16} aria-hidden="true" className="shrink-0" />
                                    <span>{step.label}</span>
                                    <span className="text-xs text-gray-600 dark:text-gray-400">{word}</span>
                                </li>
                            );
                        })}
                    </ol>
                )}
                {result && <p className="break-words text-sm text-gray-900 dark:text-white">{result}</p>}
                {patch?.message && <p className="break-words text-sm text-gray-900 dark:text-white">{patch.message}</p>}
            </div>

            {showControls && (
                <div className="flex shrink-0 flex-col items-start gap-2">
                    {hasButtons ? (
                        <div className="flex flex-wrap gap-2">
                            {openIsolation ? (
                                <button
                                    type="button"
                                    className={SECONDARY_BUTTON}
                                    disabled={disabled || blocked}
                                    aria-describedby={describedBy}
                                    onClick={() => void decide('confirm')}
                                >
                                    <LockIcon size={16} aria-hidden="true" />
                                    {busy === 'confirm' ? 'Confirming...' : 'Confirm isolation'}
                                </button>
                            ) : (
                                <>
                                    {action.canApprove && (
                                        <button
                                            type="button"
                                            className={ACCENT_BUTTON}
                                            disabled={disabled || blocked}
                                            aria-label={`Approve: ${named}`}
                                            aria-describedby={describedBy}
                                            onClick={() => void decide('approve')}
                                        >
                                            {busy === 'approve' ? 'Approving...' : 'Approve'}
                                        </button>
                                    )}
                                    {action.canDeny && (
                                        <button
                                            type="button"
                                            className={SECONDARY_BUTTON}
                                            disabled={disabled}
                                            aria-label={`Deny: ${named}`}
                                            aria-describedby={consequence ? `${ids}-what` : undefined}
                                            onClick={() => void decide('deny')}
                                        >
                                            {busy === 'deny' ? 'Denying...' : 'Deny'}
                                        </button>
                                    )}
                                </>
                            )}
                        </div>
                    ) : (
                        <p className="break-words text-xs text-gray-600 dark:text-gray-400">{WAITING_LINE}</p>
                    )}
                    {hasButtons && blocked && (
                        <p id={`${ids}-blocked`} className="break-words text-xs text-gray-600 dark:text-gray-400">{BLOCKED_LINE}</p>
                    )}
                    {error && <p role="alert" className="break-words text-sm text-red-600 dark:text-red-400">{error}</p>}
                </div>
            )}
        </li>
    );
};

// ---------------------------------------------------------------- one card

export interface CardProps {
    card: IncidentCard;
    now: number;
    stop: StopScope;
    shadow: boolean;
    tenantId: string | null;
    patches: Record<string, LinePatch>;
    onDecided: (card: IncidentCard, actionId: string, patch: LinePatch) => void;
}

export const AutonomousOpsIncidentCard: React.FC<CardProps> = ({ card, now, stop, shadow, tenantId, patches, onDecided }) => {
    const titleId = useId();
    const listId = useId();
    const [open, setOpen] = useState(false);
    const lines = card.actions;
    const hidden = Math.max(0, lines.length - COLLAPSE_AT);
    const shown = open ? lines : lines.slice(0, COLLAPSE_AT);
    const active = lines.some(line => line.needsPerson && patches[line.id] === undefined);
    const cardExpired = active && isPast(card.deadlineAt, now);
    const started = card.startedAt ? formatWhen(card.startedAt, now) : null;
    const meta = `${started ? `Started ${started.text} · ` : ''}${plural(card.alertCount, 'alert', 'alerts')}`;
    const chipText = !card.deadlineAt || !active ? null
        : card.deadlineKind === 'reverts' ? formatReverts(card.deadlineAt, now) : formatExpires(card.deadlineAt, now);

    return (
        <article id={`approval-${card.id}`} tabIndex={-1} aria-labelledby={titleId} className="card overflow-hidden focus:outline-none">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-gray-200 px-6 py-4 dark:border-white/10">
                <div className="flex min-w-0 items-start gap-4">
                    <ShieldAlertIcon size={20} aria-hidden="true" className="shrink-0 text-gray-500 dark:text-gray-400" />
                    <div className="flex min-w-0 flex-col gap-1">
                        <h3 id={titleId} className="break-words text-sm font-semibold text-gray-900 dark:text-white">{card.host || 'This computer'}</h3>
                        <p className="break-words text-xs text-gray-600 dark:text-gray-400" title={fullTime(card.startedAt)}>{meta}</p>
                    </div>
                </div>
                {chipText && (
                    <span className={DEADLINE_CHIP} title={fullTime(card.deadlineAt)}>
                        <ClockIcon size={12} aria-hidden="true" />
                        {chipText}
                    </span>
                )}
            </div>
            <ul id={listId} className="divide-y divide-gray-200 dark:divide-white/10">
                {shown.map(action => (
                    <ActionLine
                        key={action.id}
                        card={card}
                        action={action}
                        patch={patches[action.id]}
                        now={now}
                        stop={stop}
                        shadow={shadow}
                        cardExpired={cardExpired}
                        tenantId={tenantId}
                        onDecided={onDecided}
                    />
                ))}
            </ul>
            {hidden > 0 && (
                <div className="border-t border-gray-200 px-6 py-4 dark:border-white/10">
                    <button type="button" className={TEXT_BUTTON} aria-expanded={open} aria-controls={listId} onClick={() => setOpen(v => !v)}>
                        {open ? 'Show fewer actions' : `Show ${hidden} more actions`}
                        <ChevronDownIcon size={16} aria-hidden="true" className={open ? 'rotate-180' : ''} />
                    </button>
                </div>
            )}
        </article>
    );
};

export default AutonomousOpsIncidentCard;
