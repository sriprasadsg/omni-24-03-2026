import React, { useEffect, useId, useRef, useState } from 'react';
import { AlertTriangleIcon, CheckCircleIcon, CheckIcon, InfoIcon, SparklesIcon } from '../icons';
import { confirmFixed, stillNeedHelp } from '../../services/serviceDesk/ticketApi';
import type { RequesterItem, TicketDeskView } from '../../services/serviceDesk/types';
import { CitedArticles } from './CitedArticles';
import {
    ACCENT_BUTTON, AiMark, BODY_TEXT, ERROR_LINE, HealthNotice, MUTED, SECONDARY_BUTTON, TEXT_BUTTON,
    failureMessage, failureStatus, formatDay, formatDayTime,
} from './deskUi';
import { FOOTER, REQUESTER, fill } from './serviceDeskCopy';

/** The most a requester can add to "I still need help" (the server refuses more). */
const NOTE_MAX = 1000;

type Notice = 'confirmed' | 'helped' | 'handed_off' | 'withdrawn';

interface Props {
    ticketId: string;
    view: TicketDeskView;
    /** Called after a confirm or a help request (and after a 409), so the screen reads the ticket and the desk view again. */
    onChanged?: () => void | Promise<void>;
}

const noticeText = (notice: Notice, confirmedAt: string | null): string => {
    switch (notice) {
        case 'confirmed': return fill(REQUESTER.confirmed, { at: formatDayTime(confirmedAt || new Date().toISOString()) });
        case 'helped': return REQUESTER.helped;
        case 'withdrawn': return REQUESTER.withdrawn;
        default: return REQUESTER.handedOff;
    }
};

const noticeLook = (notice: Notice): { tone: 'blue' | 'amber'; icon: React.FC<any> } => {
    if (notice === 'withdrawn') return { tone: 'amber', icon: AlertTriangleIcon };
    return { tone: 'blue', icon: notice === 'confirmed' ? CheckCircleIcon : InfoIcon };
};

/**
 * The requester's answer panel (UI-SPEC section 4, D-07, D-13, D-14): the first block of a ticket the viewer raised,
 * once the desk has something the requester can see. The AI answer with its mark, the cited articles, the return date,
 * replies from IT with the staff name, and the two buttons while the server says the requester can answer
 * (`canConfirm`). Once they have answered, or the desk handed the ticket to a person, a notice replaces the buttons.
 * Nothing renders when nothing is visible to the requester, so the ticket looks as it does today. The panel only
 * presents what the server's requester view says; it never derives who may act.
 */
export const RequesterAnswerPanel: React.FC<Props> = ({ ticketId, view, onChanged }) => {
    const requester = view.requester;
    const [asking, setAsking] = useState(false);
    const [note, setNote] = useState('');
    const [pending, setPending] = useState<'confirm' | 'help' | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [local, setLocal] = useState<'confirmed' | 'helped' | null>(null);
    const busy = useRef(false);
    const acted = useRef(false);
    const live = useRef(true);
    const noticeRef = useRef<HTMLDivElement>(null);
    const noteRef = useRef<HTMLTextAreaElement>(null);
    const headingId = useId();
    const noteId = useId();

    useEffect(() => {
        live.current = true;
        return () => { live.current = false; };
    }, []);

    const notice: Notice | null = (requester?.notice ?? null) || local;
    useEffect(() => {
        if (notice && acted.current) noticeRef.current?.focus();
    }, [notice]);
    useEffect(() => {
        if (asking) noteRef.current?.focus();
    }, [asking]);

    if (!view.isRequester || !requester) return null;

    const items: RequesterItem[] = requester.items ?? [];
    const withdrawn = notice === 'withdrawn';
    const answers = withdrawn ? [] : items.filter(item => item.kind === 'answer');
    const replies = items.filter(item => item.kind === 'reply');
    if (!answers.length && !notice) return null;

    const canAnswer = requester.canConfirm && !notice;

    const run = async (kind: 'confirm' | 'help') => {
        if (busy.current) return;
        busy.current = true;
        acted.current = true;
        setPending(kind);
        setError(null);
        try {
            if (kind === 'confirm') await confirmFixed(ticketId); else await stillNeedHelp(ticketId, note);
            if (!live.current) return;
            setLocal(kind === 'confirm' ? 'confirmed' : 'helped');
            setAsking(false);
            await onChanged?.();
        } catch (e) {
            if (!live.current) return;
            const message = failureMessage(e);
            setError(message ? fill(REQUESTER.error, { message }) : REQUESTER.errorFallback);
            if (failureStatus(e) === 409) await onChanged?.();
        } finally {
            busy.current = false;
            if (live.current) setPending(null);
        }
    };

    const look = notice ? noticeLook(notice) : null;
    return (
        <section id="service-desk-answer" tabIndex={-1} aria-labelledby={headingId} className="card overflow-hidden">
            <div className="flex flex-wrap items-center gap-2 border-b border-gray-200 px-6 py-4 dark:border-white/10">
                <SparklesIcon size={20} aria-hidden="true" />
                <h3 id={headingId} className="text-sm font-semibold text-gray-900 dark:text-white">{REQUESTER.title}</h3>
            </div>
            <div className="flex flex-col gap-4 px-6 py-4">
                {answers.map(answer => (
                    <div key={answer.id} className="flex flex-col gap-2">
                        <AiMark />
                        <p className={BODY_TEXT}>{answer.text}</p>
                        {answer.citations.length > 0 && (
                            <div className="flex flex-col gap-1">
                                <p className="text-xs font-semibold text-gray-700 dark:text-gray-200">{REQUESTER.basedOn}</p>
                                <CitedArticles ticketId={ticketId} citations={answer.citations} />
                            </div>
                        )}
                    </div>
                ))}
                {answers.length > 0 && canAnswer && <p className={MUTED}>{FOOTER}</p>}
                {answers.length > 0 && canAnswer && requester.returnAt && formatDay(requester.returnAt) && (
                    <p className={MUTED}>{fill(REQUESTER.returnClock, { date: formatDay(requester.returnAt) })}</p>
                )}
                {replies.length > 0 && (
                    <ul className="flex flex-col gap-3">
                        {replies.map(reply => (
                            <li key={reply.id} className="flex flex-col gap-1">
                                <p className={MUTED}>{`${reply.author || REQUESTER.replyAuthorFallback} · ${formatDayTime(reply.at)}`}</p>
                                <p className={BODY_TEXT}>{reply.text}</p>
                            </li>
                        ))}
                    </ul>
                )}
                {notice && look && (
                    <div ref={noticeRef} tabIndex={-1}>
                        <HealthNotice tone={look.tone} icon={look.icon} role="status">
                            <p>{noticeText(notice, requester.confirmedAt)}</p>
                        </HealthNotice>
                    </div>
                )}
                {canAnswer && (
                    <div className="flex flex-col gap-3">
                        <div className="flex flex-wrap items-start gap-2">
                            <div className="flex flex-col gap-1">
                                <button type="button" className={ACCENT_BUTTON} disabled={pending !== null} onClick={() => run('confirm')}>
                                    <CheckIcon size={16} aria-hidden="true" />
                                    {pending === 'confirm' ? REQUESTER.saving : REQUESTER.fixed}
                                </button>
                                <p className={MUTED}>{REQUESTER.fixedHint}</p>
                            </div>
                            {!asking && (
                                <button type="button" className={SECONDARY_BUTTON} disabled={pending !== null} onClick={() => setAsking(true)}>
                                    {REQUESTER.stillNeedHelp}
                                </button>
                            )}
                        </div>
                        {asking && (
                            <div className="flex flex-col gap-2">
                                <label htmlFor={noteId} className="text-sm font-semibold text-gray-900 dark:text-white">{REQUESTER.noteLabel}</label>
                                <textarea
                                    id={noteId}
                                    ref={noteRef}
                                    rows={3}
                                    maxLength={NOTE_MAX}
                                    value={note}
                                    onChange={e => setNote(e.target.value.slice(0, NOTE_MAX))}
                                    className="min-h-24 w-full rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                                />
                                <p className={`${MUTED} tabular-nums`}>{fill(REQUESTER.noteCounter, { n: note.length })}</p>
                                <div className="flex flex-wrap items-center gap-2">
                                    <button type="button" className={SECONDARY_BUTTON} disabled={pending !== null} onClick={() => run('help')}>
                                        {pending === 'help' ? REQUESTER.sending : REQUESTER.sendToIt}
                                    </button>
                                    <button type="button" className={TEXT_BUTTON} disabled={pending !== null} onClick={() => { setAsking(false); setError(null); }}>
                                        {REQUESTER.backToAnswer}
                                    </button>
                                </div>
                            </div>
                        )}
                        {error && <p role="alert" className={ERROR_LINE}>{error}</p>}
                    </div>
                )}
            </div>
        </section>
    );
};
