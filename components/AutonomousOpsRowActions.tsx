import React, { useId, useRef, useState } from 'react';
import {
    AutonomousOpsApiError, AutonomousOpsOpenView, AutonomousOpsRow, undoAutonomousOpsAction,
} from '../services/autonomousOpsApi';
import { useAutonomousOpsStatus } from '../contexts/AutonomousOpsStatusContext';
import { DESK_SETTINGS_CHANGED } from '../services/serviceDesk/settingsApi';
import { showToast } from '../utils/toast';
import { ChevronRightIcon, ExternalLinkIcon, RefreshCcwIcon } from './icons';
import { ACTIVITY, fill } from './serviceDesk/serviceDeskCopy';

/**
 * What a row can do and how suggestions stay readable in volume (83-10, UI-SPEC sections 3 and 5).
 * Every string here is rendered as React text: nothing is HTML, nothing is turned into a link except the
 * two fixed links that go through `onOpenView`. The server decides who may act (`canUndo`); this file
 * never works that out.
 */

const Dash = '—';

const SECONDARY_BUTTON =
    'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ' +
    'px-4 py-2 text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-60';
const TEXT_BUTTON = 'text-sm font-semibold text-gray-900 dark:text-white underline underline-offset-2';
const MUTED = 'text-gray-600 dark:text-gray-400';

/** Where an opener can land inside Patching: the Rollouts tab, with the Start dialog open on a suggestion's draft. */
export interface OpenViewPayload {
    tab: 'rollouts';
    draft: string;
}

/**
 * The openers the screen allows: a target is present only when the viewer may open that screen. `draftRollout` is
 * display only (the viewer may open Patching and start rollouts): it turns a vulnerability suggestion's link into
 * Draft a rollout. The server checks again when the draft is read and when Start is pressed.
 */
export type OpenViewHandlers =
    Partial<Record<AutonomousOpsOpenView, (payload?: OpenViewPayload) => void>> & {
        draftRollout?: boolean;
        /** Phase 85: opens Tickets for a service desk row. Present only when the viewer may open that screen. */
        internalTickets?: (ticketId: string | null) => void;
    };

/** Builds the openers from what the viewer may open; undefined when the screen cannot navigate at all. */
export function buildOpenViewHandlers(
    go: ((view: AutonomousOpsOpenView | 'internalTickets', payload?: OpenViewPayload) => void) | undefined,
    can: { canPatch: boolean; canFim: boolean; canDraft: boolean; canTickets?: boolean },
): OpenViewHandlers | undefined {
    if (!go) return undefined;
    const out: OpenViewHandlers = {};
    if (can.canPatch) {
        out.patchManagement = payload => (payload ? go('patchManagement', payload) : go('patchManagement'));
        if (can.canDraft) out.draftRollout = true;
    }
    if (can.canFim) out.fimMonitoring = () => go('fimMonitoring');
    // The screen opens on Tickets; the ticket id reaches this handler so the screen can select it once it accepts an intent.
    if (can.canTickets) out.internalTickets = () => go('internalTickets');
    return out;
}

/** What the list hands every Result cell. */
export interface ResultContext {
    tenantId: string | null;
    /** Incident ids whose card is rendered above; a Pending row links to one of these and to no other. */
    decisionIds?: ReadonlySet<string>;
    onOpenView?: OpenViewHandlers;
    onRowChanged: (row: AutonomousOpsRow) => void;
    /** Called when the server says the row is not in the state we showed, so the list reloads. */
    onStale?: () => void;
}

// ---------------------------------------------------------------- block times (RESP-02)

const hasToken = (text: string | null | undefined) => !!text && (text.includes('{until}') || text.includes('{at}'));

function localDate(iso: string | null | undefined): Date | null {
    if (!iso) return null;
    const at = new Date(iso);
    return Number.isNaN(at.getTime()) ? null : at;
}

/** Fills {until} (Mon D, HH:MM) and {at} (HH:MM) from blockedUntil in the viewer's local time, 24-hour clock. */
export function fillBlockTimes(text: string | null | undefined, blockedUntil: string | null | undefined): string | null {
    if (!text) return text ?? null;
    if (!hasToken(text)) return text;
    const at = localDate(blockedUntil);
    const until = at
        ? at.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
        : Dash;
    const clock = at
        ? at.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
        : Dash;
    return text.split('{until}').join(until).split('{at}').join(clock);
}

/** The full local timestamp for the result's title, only when the text carries a time. */
const fullTimestamp = (row: AutonomousOpsRow): string | undefined => {
    const at = hasToken(row.resultText) ? localDate(row.blockedUntil) : null;
    return at ? at.toLocaleString() : undefined;
};

// ---------------------------------------------------------------- Undo and the Review link

const hostOf = (row: AutonomousOpsRow) => row.host || 'this computer';

const UNDO_FALLBACK = "Couldn't undo this action. Check your connection and try again.";
const BREAKER_TEXT =
    'Several automatic actions in a row were undone or failed, so this organization dropped to Suggest only. A person with manage access can restore it.';

/** The server's sentence without its closing full stop, so it can sit inside the frame. */
const quoted = (detail: string) => detail.trim().replace(/\.+$/, '');

/** A service desk row is the one that names a ticket (Phase 85); its toasts and links use the desk's own words. */
const isDeskRow = (row: AutonomousOpsRow): boolean => !!row.ticketNumber;

export const RowActions: React.FC<{
    row: AutonomousOpsRow;
    tenantId: string | null;
    decisionIds?: ReadonlySet<string>;
    onRowChanged: (row: AutonomousOpsRow) => void;
    onStale?: () => void;
}> = ({ row, tenantId, decisionIds, onRowChanged, onStale }) => {
    const { refresh } = useAutonomousOpsStatus();
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const sent = useRef(false);
    const button = useRef<HTMLButtonElement>(null);

    const undo = async () => {
        if (sent.current) return;
        sent.current = true;
        setPending(true);
        setError(null);
        try {
            const out = await undoAutonomousOpsAction(row.id, tenantId);
            // A 200 means the undo was sent; an answer without the row only means the list must be read again (WR-29).
            const cell = button.current?.closest<HTMLElement>('[data-result-cell]');
            if (out?.action?.id) onRowChanged(out.action); else onStale?.();
            cell?.focus();
            if (isDeskRow(row)) {
                // A withdrawn answer: the desk's breaker is its own, so the security breaker text never applies here.
                if (out?.deskBreakerTripped) {
                    showToast(ACTIVITY.undoToastBreaker, 'info');
                    window.dispatchEvent(new Event(DESK_SETTINGS_CHANGED));
                } else {
                    showToast(fill(ACTIVITY.undoToast, { number: row.ticketNumber ?? '' }), 'success');
                }
            } else if (out?.breakerTripped) {
                showToast(`Undo sent to ${hostOf(row)}. ${BREAKER_TEXT}`, 'info');
                void refresh();
            } else {
                showToast(`Undo sent to ${hostOf(row)}.`, 'success');
            }
        } catch (err) {
            const detail = err instanceof AutonomousOpsApiError ? quoted(err.detail) : '';
            setError(detail ? `Couldn't undo this action: ${detail}. Try again.` : UNDO_FALLBACK);
            if (err instanceof AutonomousOpsApiError && err.status === 409) onStale?.();
        } finally {
            sent.current = false;
            setPending(false);
        }
    };

    const incident = row.bucket === 'pending' && !isDeskRow(row) ? row.incidentId : null;
    const review = !!incident && !!decisionIds?.has(incident);
    const goToCard = () => {
        const card = document.getElementById(`approval-${incident}`);
        card?.scrollIntoView?.({ block: 'center' });
        card?.focus();
    };

    if (row.canUndo !== true && !review && !error) return null;
    return (
        <div className="mt-2 flex flex-wrap items-start gap-2">
            {review && (
                <button type="button" className={TEXT_BUTTON} onClick={goToCard}>Review in Needs your decision</button>
            )}
            {(row.canUndo === true || error) && (
                <div className="flex min-w-0 flex-col items-start gap-1">
                    {row.canUndo === true && (
                        <>
                            <button
                                ref={button}
                                type="button"
                                className={SECONDARY_BUTTON}
                                disabled={pending}
                                aria-label={isDeskRow(row)
                                    ? fill(ACTIVITY.undoAria, { number: row.ticketNumber ?? '' })
                                    : `Undo: ${row.actionLabel} on ${hostOf(row)}`}
                                onClick={undo}
                            >
                                <RefreshCcwIcon size={16} aria-hidden="true" className={pending ? 'animate-spin' : ''} />
                                {pending ? ACTIVITY.undoing : ACTIVITY.undo}
                            </button>
                            {row.undoHint && <p className="break-words text-xs text-gray-500 dark:text-gray-400">{row.undoHint}</p>}
                        </>
                    )}
                    {error && <p role="alert" className="break-words text-xs text-red-700 dark:text-red-300">{error}</p>}
                </div>
            )}
        </div>
    );
};

// ---------------------------------------------------------------- suggestions in volume (UI-SPEC 5)

const VIEW_LABEL: Record<AutonomousOpsOpenView, string> = {
    patchManagement: 'Open patching',
    fimMonitoring: 'Open file integrity',
};

/** Only these two kinds are grouped; a single-signal or correlation suggestion is an ordinary row. */
export const isGroupedSuggestion = (row: AutonomousOpsRow): boolean =>
    row.suggestion?.kind === 'vulnerability' || row.suggestion?.kind === 'file_change';

const viewFor = (row: AutonomousOpsRow): AutonomousOpsOpenView =>
    row.suggestion?.openView ?? (row.suggestion?.kind === 'file_change' ? 'fimMonitoring' : 'patchManagement');

const nounFor = (row: AutonomousOpsRow, n: number): string => {
    if (row.suggestion?.kind === 'file_change') return n === 1 ? 'file' : 'files';
    return n === 1 ? 'vulnerability' : 'vulnerabilities';
};

/** `draft` turns the link into Draft a rollout for that suggestion; it only opens the dialog and never starts anything. */
const ViewLink: React.FC<{ view: AutonomousOpsOpenView; onOpenView?: OpenViewHandlers; draft?: { id: string; host: string | null } }> = ({ view, onOpenView, draft }) => {
    const open = onOpenView?.[view];
    if (!open) return <span className={`text-sm ${MUTED}`}>{VIEW_LABEL[view]}</span>;
    const drafting = !!draft && view === 'patchManagement' && onOpenView?.draftRollout === true;
    return (
        <button
            type="button"
            className={`${TEXT_BUTTON} inline-flex items-center gap-1`}
            aria-label={drafting ? `Draft a rollout for the vulnerabilities on ${draft?.host || 'this computer'}` : undefined}
            onClick={() => (drafting && draft ? open({ tab: 'rollouts', draft: draft.id }) : open())}
        >
            {drafting ? 'Draft a rollout' : VIEW_LABEL[view]}
            <ExternalLinkIcon size={12} aria-hidden="true" />
        </button>
    );
};

/** The link out and the details disclosure of a grouped suggestion. The items come with the row, so there is no fetch. */
export const SuggestionBody: React.FC<{ row: AutonomousOpsRow; onOpenView?: OpenViewHandlers }> = ({ row, onOpenView }) => {
    const [open, setOpen] = useState(false);
    const panelId = useId();
    const suggestion = row.suggestion;
    if (!suggestion || !isGroupedSuggestion(row)) return null;
    const view = viewFor(row);
    const items = suggestion.items;
    return (
        <div className="mt-2 flex flex-col items-start gap-2">
            <div className="flex flex-wrap items-center gap-2">
                <ViewLink view={view} onOpenView={onOpenView} draft={suggestion.kind === 'vulnerability' ? { id: row.id, host: row.host } : undefined} />
                {items.length > 0 && (
                    <button type="button" className={`${TEXT_BUTTON} inline-flex items-center gap-1`} aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(o => !o)}>
                        <ChevronRightIcon size={16} aria-hidden="true" className={open ? 'rotate-90' : ''} />
                        {open ? 'Hide details' : 'Show details'}
                    </button>
                )}
            </div>
            {open && (
                <div id={panelId} className="flex flex-col gap-2">
                    <ul className="flex flex-col gap-1">
                        {items.map((item, i) => (
                            <li key={i} className="break-words text-xs text-gray-600 dark:text-gray-400">
                                <span className="break-all font-mono">{item.cve ?? item.path ?? Dash}</span>
                                {item.package && <span>{` ${item.package}`}</span>}
                            </li>
                        ))}
                    </ul>
                    {suggestion.count > items.length && (
                        <p className={`break-words text-sm ${MUTED}`}>
                            {`Showing ${items.length} of ${suggestion.count}. `}
                            <ViewLink view={view} onOpenView={onOpenView} />
                            {' to see all of them.'}
                        </p>
                    )}
                </div>
            )}
        </div>
    );
};

const SHOWN_IN_TARGET = 3;

/** The Target cell of a grouped suggestion: the host, then at most three ids or paths and how many more there are. */
export const TargetSummary: React.FC<{ row: AutonomousOpsRow }> = ({ row }) => {
    const suggestion = row.suggestion;
    const shown = (suggestion?.items ?? []).slice(0, SHOWN_IN_TARGET);
    const count = suggestion?.count ?? 0;
    const more = count - shown.length;
    return (
        <>
            <div className="break-words text-sm font-semibold text-gray-900 dark:text-white">{row.host || Dash}</div>
            {shown.length === 0 ? (
                <div className="text-xs text-gray-500 dark:text-gray-400">{`${count} ${nounFor(row, count)}`}</div>
            ) : (
                <>
                    {shown.map((item, i) => (
                        <div key={i} className="break-all font-mono text-xs text-gray-500 dark:text-gray-400">{item.cve ?? item.path ?? Dash}</div>
                    ))}
                    {more > 0 && <div className="text-xs text-gray-500 dark:text-gray-400">{`+${more} more`}</div>}
                </>
            )}
        </>
    );
};

// ---------------------------------------------------------------- service desk rows (Phase 85)

/**
 * "Open ticket {TKT-number}" (UI-SPEC 5). A link through the Tickets opener when the viewer may open that screen,
 * else the same words as plain text. Approve and Deny never appear on a desk row: a draft is decided on the ticket.
 */
export const DeskTicketLink: React.FC<{ row: AutonomousOpsRow; onOpenView?: OpenViewHandlers }> = ({ row, onOpenView }) => {
    if (!row.ticketNumber) return null;
    const label = fill(ACTIVITY.openTicket, { number: row.ticketNumber });
    const open = onOpenView?.internalTickets;
    return (
        <div className="mt-2">
            {open ? (
                <button type="button" className={`${TEXT_BUTTON} inline-flex items-center gap-1`} onClick={() => open(row.ticketId ?? null)}>
                    {label}
                    <ExternalLinkIcon size={12} aria-hidden="true" />
                </button>
            ) : (
                <span className={`break-words text-sm ${MUTED}`}>{label}</span>
            )}
        </div>
    );
};

// ---------------------------------------------------------------- the Result cell

/** Result text, then the suggestion body and the row actions, in one focusable wrapper (both layouts share it). */
export const ResultCell: React.FC<{ row: AutonomousOpsRow; text: string | null; ctx: ResultContext }> = ({ row, text, ctx }) => (
    <div data-result-cell tabIndex={-1} className="min-w-0">
        <span className={`break-words text-sm ${MUTED}`} title={fullTimestamp(row)}>{text ?? Dash}</span>
        <SuggestionBody row={row} onOpenView={ctx.onOpenView} />
        <DeskTicketLink row={row} onOpenView={ctx.onOpenView} />
        <RowActions row={row} tenantId={ctx.tenantId} decisionIds={ctx.decisionIds} onRowChanged={ctx.onRowChanged} onStale={ctx.onStale} />
    </div>
);
