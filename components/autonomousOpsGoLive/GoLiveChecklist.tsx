import React, { useEffect, useId, useRef, useState } from 'react';
import { recordGoLiveCheck } from '../../services/autonomousOpsGoLive';
import type { GoLiveCheck, GoLiveCheckId } from '../../services/autonomousOpsGoLive';
import type { AutonomousOpsApiError } from '../../services/autonomousOpsApi';
import { showToast } from '../../utils/toast';
import { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
import { HealthChip } from '../AutonomousOpsHealthChips';
import { ACCENT_BUTTON, plain } from '../AutonomousOpsResponseSettingsDialogs';
import { AlertTriangleIcon, ClipboardCheckIcon } from '../icons';
import {
    CHECKS_LIST_LABEL, CHECK_COPY, CHIP_NOT_RECORDED, CHIP_RECORDED, CLOSE_FORM, DISCARD_ASK, DISCARD_NOTE, EARLIER_RECORDS,
    KEEP_EDITING, NOTE_HELPER, NOTE_LABEL, NOTE_MAX, NOTE_MIN, NOTE_TOO_SHORT, RECORDING, RECORD_AGAIN, RECORD_CHECK,
    RECORD_FALLBACK, RECORD_FORBIDDEN, RECORD_THIS, noteCounter, recordFailed, recordedLine, recordedToast,
} from './goLiveCopy';

const TEXT_BUTTON = 'min-h-8 text-xs font-semibold text-gray-900 underline underline-offset-2 dark:text-white disabled:opacity-60';
const FIELD =
    'min-h-24 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white';

/** The sentence under a failed record: 403 has its own, a refused record shows the server's message, anything else the fallback. */
function recordError(e: unknown): string {
    const err = e as Partial<AutonomousOpsApiError>;
    if (err.status === 403) return RECORD_FORBIDDEN;
    if (typeof err.status === 'number' && err.status < 500 && err.detail) return recordFailed(plain(err.detail));
    return RECORD_FALLBACK;
}

interface RecordFormProps {
    id: GoLiveCheckId;
    title: string;
    /** Called after the record is stored; the card refetches. */
    onRecorded: () => void | Promise<void>;
    onClose: () => void;
}

/**
 * The inline note form under one row (86-UI-SPEC section 6b, E9): no modal. Focus goes to the textarea; Record check stays
 * disabled with its reason until the trimmed note has 10 characters; one request per click; Esc or Close form with typed
 * text asks before discarding. Errors keep the note. The note is sent trimmed; the server trims and bounds it again.
 */
const RecordForm: React.FC<RecordFormProps> = ({ id, title, onRecorded, onClose }) => {
    const uid = useId();
    const [note, setNote] = useState('');
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [asking, setAsking] = useState(false);
    const inFlight = useRef(false);
    const field = useRef<HTMLTextAreaElement>(null);
    const trimmed = note.trim();
    const short = trimmed.length < NOTE_MIN;

    useEffect(() => { field.current?.focus(); }, []);

    const requestClose = () => {
        if (pending) return;
        if (note.trim() === '') { onClose(); return; }
        setAsking(true);
    };

    const submit = async () => {
        if (inFlight.current || short) return;
        inFlight.current = true;
        setPending(true);
        setError(null);
        try {
            await recordGoLiveCheck(id, trimmed);
            showToast(recordedToast(title), 'success');
            void onRecorded();
            onClose();
        } catch (e) {
            setError(recordError(e));
            inFlight.current = false;
            setPending(false);
        }
    };

    return (
        <div
            className="mt-4 flex flex-col gap-2 border-t border-gray-200 pt-4 dark:border-white/10"
            onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); if (asking) setAsking(false); else requestClose(); } }}
        >
            <label htmlFor={`${uid}-note`} className="text-sm font-semibold text-gray-900 dark:text-white">{NOTE_LABEL}</label>
            <p id={`${uid}-help`} className="break-words text-xs text-gray-500 dark:text-gray-400">{NOTE_HELPER}</p>
            <textarea
                id={`${uid}-note`} ref={field} rows={3} maxLength={NOTE_MAX} value={note} disabled={pending}
                aria-describedby={`${uid}-help`} onChange={e => setNote(e.target.value)} className={FIELD}
            />
            <div className="flex flex-wrap items-center justify-between gap-2">
                {short
                    ? <p id={`${uid}-short`} className="break-words text-xs text-gray-500 dark:text-gray-400">{NOTE_TOO_SHORT}</p>
                    : <span />}
                <span className="text-xs tabular-nums text-gray-500 dark:text-gray-400">{noteCounter(note.length)}</span>
            </div>
            {error && (
                <div role="alert" className="flex items-start gap-2 break-words rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-300">
                    <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
                    <span className="min-w-0">{error}</span>
                </div>
            )}
            {asking && (
                <div className="flex flex-wrap items-center gap-4">
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">{DISCARD_ASK}</p>
                    <button type="button" className={TEXT_BUTTON} onClick={onClose}>{DISCARD_NOTE}</button>
                    <button type="button" className={TEXT_BUTTON} onClick={() => { setAsking(false); field.current?.focus(); }}>{KEEP_EDITING}</button>
                </div>
            )}
            <div className="flex flex-wrap items-center gap-4">
                <button
                    type="button" className={ACCENT_BUTTON} onClick={() => void submit()} disabled={pending || short}
                    aria-describedby={short ? `${uid}-short` : undefined}
                >
                    {pending ? RECORDING : RECORD_CHECK}
                </button>
                <button type="button" className={TEXT_BUTTON} onClick={requestClose} disabled={pending}>{CLOSE_FORM}</button>
            </div>
        </div>
    );
};

interface CheckRowProps {
    check: GoLiveCheck;
    open: boolean;
    onOpen: () => void;
    onClose: () => void;
    onRecorded: () => void | Promise<void>;
    buttonRef: (el: HTMLButtonElement | null) => void;
}

const CheckRow: React.FC<CheckRowProps> = ({ check, open, onOpen, onClose, onRecorded, buttonRef }) => {
    const titleId = useId();
    const copy = CHECK_COPY[check.id];
    return (
        <li className="rounded-lg border border-gray-200 p-4 dark:border-white/10">
            <div className="flex flex-wrap items-start justify-between gap-2">
                <p id={titleId} className="min-w-0 break-words text-sm font-semibold text-gray-900 dark:text-white">{copy.title}</p>
                <HealthChip kind={check.recorded ? 'ok' : 'not_tested'} label={check.recorded ? CHIP_RECORDED : CHIP_NOT_RECORDED} />
            </div>
            <p className="mt-1 break-words text-xs text-gray-500 dark:text-gray-400">{copy.description}</p>
            {check.recorded && (
                <div className="mt-2 flex flex-col gap-1">
                    <p className="break-words text-xs text-gray-500 dark:text-gray-400">
                        {recordedLine(check.recordedBy?.display || check.recordedBy?.username || 'an unknown person', check.recordedAt)}
                    </p>
                    {check.note && <p className="whitespace-pre-wrap break-words text-sm text-gray-900 dark:text-white">{check.note}</p>}
                </div>
            )}
            <div className="mt-4 flex flex-wrap items-center gap-2">
                {/* One button for both states, so focus survives the row changing after a record. */}
                <button
                    type="button" ref={buttonRef} className={check.recorded ? TEXT_BUTTON : SECONDARY_BUTTON}
                    aria-describedby={titleId} onClick={onOpen}
                >
                    {!check.recorded && <ClipboardCheckIcon size={16} aria-hidden="true" />}
                    {check.recorded ? RECORD_AGAIN : RECORD_THIS}
                </button>
                {check.recorded && <span className="text-xs text-gray-500 dark:text-gray-400">{EARLIER_RECORDS}</span>}
            </div>
            {open && <RecordForm id={check.id} title={copy.title} onRecorded={onRecorded} onClose={onClose} />}
        </li>
    );
};

interface GoLiveChecklistProps {
    checks: GoLiveCheck[];
    /** Called after a record is stored; the card refetches so the row and the summary update. */
    onRecorded: () => void | Promise<void>;
}

/**
 * The five go-live checks (86-UI-SPEC section 6b, D-14): one row each with a Recorded or Not recorded chip, the latest
 * record in full, and one inline note form at a time. Names, notes and times are server text and render as React text only.
 */
export const GoLiveChecklist: React.FC<GoLiveChecklistProps> = ({ checks, onRecorded }) => {
    const [openId, setOpenId] = useState<GoLiveCheckId | null>(null);
    const buttons = useRef<Partial<Record<GoLiveCheckId, HTMLButtonElement | null>>>({});

    const returnFocusTo = useRef<GoLiveCheckId | null>(null);

    const close = (id: GoLiveCheckId) => {
        returnFocusTo.current = id;
        setOpenId(null);
    };

    // The form has unmounted by now; focus returns to the row's own button.
    useEffect(() => {
        const id = returnFocusTo.current;
        if (openId === null && id) {
            returnFocusTo.current = null;
            buttons.current[id]?.focus();
        }
    }, [openId]);

    return (
        <ol aria-label={CHECKS_LIST_LABEL} className="flex flex-col gap-4">
            {checks.map(check => (
                <CheckRow
                    key={check.id} check={check} open={openId === check.id}
                    onOpen={() => setOpenId(check.id)} onClose={() => close(check.id)} onRecorded={onRecorded}
                    buttonRef={el => { buttons.current[check.id] = el; }}
                />
            ))}
        </ol>
    );
};

export default GoLiveChecklist;
