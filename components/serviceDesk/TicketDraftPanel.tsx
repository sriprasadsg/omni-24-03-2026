import React, { useEffect, useId, useRef, useState } from 'react';
import { Modal } from '../Modal';
import { InfoIcon, LockIcon, PencilIcon, SendIcon, SparklesIcon, TrashIcon } from '../icons';
import { discardDraft, editAndSendDraft, sendDraft } from '../../services/serviceDesk/ticketApi';
import type { DraftView, TicketDeskView } from '../../services/serviceDesk/types';
import { formatRelativeTime } from '../../utils/timeUtils';
import { showToast } from '../../utils/toast';
import { CitedArticles } from './CitedArticles';
import {
    ACCENT_BUTTON, AiMark, BODY_TEXT, DeskChip, ERROR_LINE, HealthNotice, MUTED, RED_BUTTON, SECONDARY_BUTTON, TEXT_BUTTON,
    failureMessage, failureStatus, formatHm,
} from './deskUi';
import { DIALOGS, DRAFT_PANEL, FOOTER, TOASTS, VALIDATION, fill } from './serviceDeskCopy';

interface Props {
    ticketId: string;
    view: TicketDeskView;
    /** The signed-in person's name, for the result line ("Sent to Dana by Sam at 14:30"). */
    actorName?: string;
    /** Called after a send or a discard (and after a 409), so the screen reads the ticket and the desk view again. */
    onChanged?: () => void | Promise<void>;
}

type Pending = 'send' | 'edit' | 'discard' | null;
type Decision = { kind: 'sent' | 'discarded'; at: string; reporter: string };

/** "written 2 hours ago": the relative words in the middle of a sentence read in lower case. */
const relative = (iso: string): string => {
    const text = formatRelativeTime(iso);
    return text ? text.charAt(0).toLowerCase() + text.slice(1) : text;
};

const blockedLine = (draft: DraftView, status: string): string | null => {
    if (!draft.blockedReason) return null;
    if (draft.blockedText) return draft.blockedText;
    if (draft.blockedReason === 'ticket_closed') return fill(DRAFT_PANEL.closedBlocked, { state: status });
    if (draft.blockedReason === 'person_replied') return DRAFT_PANEL.personReplied;
    if (draft.blockedReason === 'no_requester') return DRAFT_PANEL.noRequester;
    return null;
};

/**
 * The staff draft panel (UI-SPEC section 3, D-09, D-10): the first block under a ticket's header while a draft is
 * waiting. Staff send it as is, edit and send it, or discard it, and the result replaces the panel in the same spot.
 * Every refusal is shown in plain words from the server's text. The server sends a draft only to someone other than
 * the requester and says (`canActOnDraft`, `blockedReason`) whether it can go out right now, so the panel never works
 * that out itself: a draft that cannot be sent keeps its answer visible with the reason, and Discard draft stays.
 */
export const TicketDraftPanel: React.FC<Props> = ({ ticketId, view, actorName, onChanged }) => {
    const draft = view.draft;
    const [editing, setEditing] = useState(false);
    const [text, setText] = useState('');
    const [askDiscardEdits, setAskDiscardEdits] = useState(false);
    const [pending, setPending] = useState<Pending>(null);
    const [error, setError] = useState<string | null>(null);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [dialogError, setDialogError] = useState<string | null>(null);
    const [handled, setHandled] = useState<string | null>(null);
    const [decision, setDecision] = useState<Decision | null>(null);
    const busy = useRef(false);
    const live = useRef(true);
    const resultRef = useRef<HTMLDivElement>(null);
    const editRef = useRef<HTMLTextAreaElement>(null);
    const headingId = useId();
    const consequenceId = useId();
    const helperId = useId();
    const reasonId = useId();

    useEffect(() => {
        live.current = true;
        return () => { live.current = false; };
    }, []);
    useEffect(() => { if (decision) resultRef.current?.focus(); }, [decision]);
    useEffect(() => { if (editing) editRef.current?.focus(); }, [editing]);

    // A different draft (another ticket, or a new one) starts from its own text.
    const draftId = draft?.commentId ?? null;
    useEffect(() => {
        setEditing(false); setAskDiscardEdits(false); setError(null); setHandled(null);
    }, [draftId]);

    if (decision) {
        const line = decision.kind === 'sent'
            ? fill(DRAFT_PANEL.resultSent, { reporter: decision.reporter, name: actorName || 'you', time: formatHm(decision.at) })
            : fill(DRAFT_PANEL.resultDiscarded, { name: actorName || 'you', time: formatHm(decision.at) });
        return (
            <section id="service-desk-draft" tabIndex={-1} aria-label={DRAFT_PANEL.title} className="card overflow-hidden">
                <div ref={resultRef} role="status" tabIndex={-1} className="px-6 py-4 text-sm text-gray-900 dark:text-white">{line}</div>
            </section>
        );
    }
    if (!draft || view.isRequester) return null;

    const blocked = blockedLine(draft, view.status);
    const noRequester = draft.blockedReason === 'no_requester';
    const sendBlocked = !draft.canActOnDraft;
    const original = draft.answer;
    const trimmed = text.trim();
    const unchanged = trimmed === original.trim();
    const tooLong = text.length > draft.maxAnswerLength || trimmed.length > draft.maxAnswerLength;
    const canSendEdit = trimmed.length > 0 && !unchanged && !tooLong;

    const finish = (kind: Decision['kind']) => {
        setDecision({ kind, at: new Date().toISOString(), reporter: draft.reporter });
        setEditing(false);
        setDialogOpen(false);
    };

    const fail = async (e: unknown, template: string, fallback: string, inDialog: boolean) => {
        const message = failureMessage(e);
        if (failureStatus(e) === 409 && message === DRAFT_PANEL.alreadyHandled.replace(/[.\s]+$/, '')) {
            setHandled(DRAFT_PANEL.alreadyHandled);
            setDialogOpen(false);
            setEditing(false);
        } else {
            const line = message ? fill(template, { message }) : fallback;
            if (inDialog) setDialogError(line); else setError(line);
        }
        if (failureStatus(e) === 409) await onChanged?.();
    };

    const run = async (kind: Exclude<Pending, null>) => {
        if (busy.current) return;
        busy.current = true;
        setPending(kind);
        setError(null);
        setDialogError(null);
        try {
            if (kind === 'send') await sendDraft(ticketId, draft.commentId);
            else if (kind === 'edit') await editAndSendDraft(ticketId, draft.commentId, trimmed);
            else await discardDraft(ticketId, draft.commentId);
            if (!live.current) return;
            if (kind === 'discard') showToast(TOASTS.draftDiscarded, 'success');
            finish(kind === 'discard' ? 'discarded' : 'sent');
            await onChanged?.();
        } catch (e) {
            if (!live.current) return;
            if (kind === 'discard') await fail(e, DRAFT_PANEL.discardFailed, DRAFT_PANEL.discardFailedFallback, true);
            else await fail(e, DRAFT_PANEL.sendFailed, DRAFT_PANEL.sendFailedFallback, false);
        } finally {
            busy.current = false;
            if (live.current) setPending(null);
        }
    };

    const startEdit = () => { setText(original); setAskDiscardEdits(false); setError(null); setEditing(true); };
    const leaveEdit = () => { setEditing(false); setAskDiscardEdits(false); setError(null); };
    const onEditKey = (e: React.KeyboardEvent) => {
        if (e.key !== 'Escape') return;
        e.preventDefault();
        if (text === original) leaveEdit(); else setAskDiscardEdits(true);
    };

    const consequence = fill(DRAFT_PANEL.consequence, { reporter: draft.reporter });
    const anyPending = pending !== null;
    return (
        <section id="service-desk-draft" tabIndex={-1} aria-labelledby={headingId} className="card overflow-hidden">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-gray-200 px-6 py-4 dark:border-white/10">
                <div className="flex min-w-0 items-start gap-2">
                    <SparklesIcon size={20} aria-hidden="true" className="mt-0.5 shrink-0" />
                    <div className="min-w-0">
                        <h3 id={headingId} className="text-sm font-semibold text-gray-900 dark:text-white">{DRAFT_PANEL.title}</h3>
                        <p className={MUTED}>{fill(DRAFT_PANEL.subtitle, { relative: relative(draft.createdAt), n: draft.articleCount })}</p>
                    </div>
                </div>
                <DeskChip tone="blue" icon={LockIcon}>{DRAFT_PANEL.chipDraft}</DeskChip>
            </div>
            {draft.draftReasonText && (
                <p className={`${MUTED} flex items-start gap-1 px-6 pt-4`}>
                    <InfoIcon size={12} aria-hidden="true" className="mt-0.5 shrink-0" />
                    {draft.draftReasonText}
                </p>
            )}
            <div className="flex flex-col gap-2 px-6 py-4">
                <p className="text-xs font-semibold text-gray-700 dark:text-gray-200">{DRAFT_PANEL.seenLabel}</p>
                {editing ? (
                    <div className="flex flex-col gap-2">
                        <label htmlFor={`${helperId}-edit`} className="text-sm font-semibold text-gray-900 dark:text-white">{DRAFT_PANEL.editLabel}</label>
                        <textarea
                            id={`${helperId}-edit`}
                            ref={editRef}
                            rows={8}
                            value={text}
                            aria-describedby={helperId}
                            onChange={e => { setText(e.target.value); setAskDiscardEdits(false); }}
                            onKeyDown={onEditKey}
                            className="min-h-40 w-full rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                        />
                        <p className={`${tooLong ? 'text-red-700 dark:text-red-300' : 'text-gray-500 dark:text-gray-400'} text-xs tabular-nums`}>
                            {fill(DRAFT_PANEL.counter, { n: text.length, max: draft.maxAnswerLength })}
                        </p>
                        <p id={helperId} className={MUTED}>{DRAFT_PANEL.editHelper}</p>
                    </div>
                ) : (
                    <div className="flex flex-col gap-2 rounded-lg border border-gray-200 p-4 dark:border-white/10">
                        <AiMark />
                        <p className={BODY_TEXT}>{original}</p>
                        {draft.citations.length > 0 && (
                            <div className="flex flex-col gap-1">
                                <p className="text-xs font-semibold text-gray-700 dark:text-gray-200">{DRAFT_PANEL.basedOn}</p>
                                <CitedArticles ticketId={ticketId} citations={draft.citations} />
                            </div>
                        )}
                        <p className={MUTED}>{FOOTER}</p>
                    </div>
                )}
            </div>
            <div className="flex flex-col gap-2 px-6 pb-4">
                {handled ? (
                    <p role="status" className="text-sm text-gray-900 dark:text-white">{handled}</p>
                ) : (
                    <>
                        {noRequester ? (
                            <p id={reasonId} role="status" className={MUTED}>{blocked}</p>
                        ) : (
                            <p id={consequenceId} className={MUTED}>{consequence}</p>
                        )}
                        {!noRequester && blocked && <p id={reasonId} role="status" className={MUTED}>{blocked}</p>}
                        {editing && !sendBlocked && unchanged && <p className={MUTED}>{VALIDATION.editUnchanged}</p>}
                        {askDiscardEdits && (
                            <p className="flex flex-wrap items-center gap-2 text-sm text-gray-900 dark:text-white">
                                {DRAFT_PANEL.discardEdits}
                                <button type="button" className={TEXT_BUTTON} onClick={leaveEdit}>{DRAFT_PANEL.discardEditsConfirm}</button>
                                <button type="button" className={TEXT_BUTTON} onClick={() => { setAskDiscardEdits(false); editRef.current?.focus(); }}>{DRAFT_PANEL.keepEditing}</button>
                            </p>
                        )}
                        <div className="flex flex-wrap items-center gap-2">
                            {!noRequester && !editing && (
                                <button type="button" className={ACCENT_BUTTON} disabled={anyPending || sendBlocked}
                                    aria-describedby={sendBlocked ? reasonId : consequenceId} onClick={() => run('send')}>
                                    <SendIcon size={16} aria-hidden="true" />
                                    {pending === 'send' ? DRAFT_PANEL.sending : DRAFT_PANEL.sendAsIs}
                                </button>
                            )}
                            {!noRequester && editing && (
                                <button type="button" className={ACCENT_BUTTON} disabled={anyPending || sendBlocked || !canSendEdit}
                                    aria-describedby={consequenceId} onClick={() => run('edit')}>
                                    <SendIcon size={16} aria-hidden="true" />
                                    {pending === 'edit' ? DRAFT_PANEL.sending : DRAFT_PANEL.sendEdit}
                                </button>
                            )}
                            {!noRequester && !editing && (
                                <button type="button" className={SECONDARY_BUTTON} disabled={anyPending || sendBlocked} onClick={startEdit}>
                                    <PencilIcon size={16} aria-hidden="true" />
                                    {DRAFT_PANEL.editAndSend}
                                </button>
                            )}
                            {!noRequester && editing && (
                                <button type="button" className={SECONDARY_BUTTON} disabled={anyPending} onClick={leaveEdit}>{DRAFT_PANEL.backToDraft}</button>
                            )}
                            {!editing && (
                                <button type="button" className={SECONDARY_BUTTON} disabled={anyPending}
                                    onClick={() => { setDialogError(null); setDialogOpen(true); }}>
                                    <TrashIcon size={16} aria-hidden="true" />
                                    {DRAFT_PANEL.discardDraft}
                                </button>
                            )}
                        </div>
                        {error && <p role="alert" className={ERROR_LINE}>{error}</p>}
                    </>
                )}
            </div>
            {dialogOpen && (
                <Modal
                    isOpen
                    onClose={() => setDialogOpen(false)}
                    title={DIALOGS.discard.title}
                    size="md"
                    showClose={false}
                    closeOnBackdrop={false}
                    closeOnEsc={pending !== 'discard'}
                    footer={(
                        <>
                            <button type="button" className={SECONDARY_BUTTON} disabled={pending === 'discard'} onClick={() => setDialogOpen(false)}>
                                {DIALOGS.discard.keep}
                            </button>
                            <button type="button" className={RED_BUTTON} disabled={pending === 'discard'} onClick={() => run('discard')}>
                                {pending === 'discard' ? DIALOGS.discard.pending : DIALOGS.discard.confirm}
                            </button>
                        </>
                    )}
                >
                    <div className="flex flex-col gap-4">
                        <p className="break-words text-sm text-gray-700 dark:text-gray-200">{DIALOGS.discard.body}</p>
                        {dialogError && (
                            <HealthNotice tone="red" role="alert">
                                <p>{dialogError}</p>
                            </HealthNotice>
                        )}
                    </div>
                </Modal>
            )}
        </section>
    );
};
