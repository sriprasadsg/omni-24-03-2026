import React, { useId, useState } from 'react';
import { EyeIcon, InfoIcon, LockIcon, SparklesIcon, XCircleIcon } from '../icons';
import type { CommentVisibility } from '../../services/serviceDesk/ticketApi';
import { BODY_TEXT, DeskChip, MUTED, TEXT_BUTTON } from './deskUi';
import { REPLY_PICKER, fill } from './serviceDeskCopy';

interface PickerProps {
    value: CommentVisibility;
    onChange: (value: CommentVisibility) => void;
    /** The server's `canReplyToRequester` flag: false for a ticket raised by an automated source or one the requester cannot read. */
    canReplyToRequester: boolean;
    /** True until the server's flag is known; the choice stays off without a reason line, so it never claims something untrue. */
    unknown?: boolean;
    /** The person who raised the ticket, named in the info line. */
    reporter: string;
    disabled?: boolean;
}

/**
 * "Who can see this comment" (UI-SPEC section 3, D-11): Staff only is the default, Reply to requester is a deliberate
 * choice. The screen resets it to Staff only after every send and when another ticket opens, so nothing is ever
 * sticky. Reply to requester is off with its reason when the server says there is no requester to reply to.
 */
export const ReplyVisibilityPicker: React.FC<PickerProps> = ({
    value, onChange, canReplyToRequester, unknown = false, reporter, disabled = false,
}) => {
    const name = useId();
    const reasonId = useId();
    const replyOff = unknown || !canReplyToRequester;
    const row = 'flex min-h-10 cursor-pointer items-center gap-2 rounded-lg px-2 text-sm text-gray-900 dark:text-white';
    return (
        <div className="flex flex-col gap-1 pb-2">
            <div role="radiogroup" aria-label={REPLY_PICKER.label} className="flex flex-wrap gap-x-4">
                <label className={row}>
                    <input type="radio" name={name} checked={value === 'staff' || replyOff} disabled={disabled} onChange={() => onChange('staff')} />
                    <LockIcon size={16} aria-hidden="true" />
                    {REPLY_PICKER.staffOnly}
                </label>
                <label className={`${row} ${replyOff ? 'cursor-not-allowed opacity-60' : ''}`}>
                    <input
                        type="radio"
                        name={name}
                        checked={value === 'requester' && !replyOff}
                        disabled={disabled || replyOff}
                        aria-describedby={!unknown && !canReplyToRequester ? reasonId : undefined}
                        onChange={() => { if (!replyOff) onChange('requester'); }}
                    />
                    <EyeIcon size={16} aria-hidden="true" />
                    {REPLY_PICKER.replyToRequester}
                </label>
            </div>
            {!unknown && !canReplyToRequester && <p id={reasonId} className={MUTED}>{REPLY_PICKER.noTarget}</p>}
            {value === 'requester' && !replyOff && (
                <p className={`${MUTED} flex items-start gap-1`}>
                    <InfoIcon size={12} aria-hidden="true" className="mt-0.5 shrink-0" />
                    {fill(REPLY_PICKER.note, { reporter: reporter || 'The requester' })}
                </p>
            )}
        </div>
    );
};

/** The parts of a stored comment the marks read. A comment with none of them is a plain staff-only note (R13). */
export interface DeskComment {
    kind?: string | null;
    visibility?: string | null;
    text: string;
    ai?: { state?: string; sentBy?: { id?: string; name?: string } | null } | null;
}

const isWithdrawn = (c: DeskComment) => c.kind === 'ai_answer' && c.ai?.state === 'withdrawn';

/**
 * The marks beside a comment (UI-SPEC section 3): `Sent to requester` on a requester-visible comment, `AI-assisted`
 * with `Sent by {name}` or `Posted automatically` on an AI answer, `Withdrawn` on a withdrawn answer and `Draft` on a
 * draft. A plain staff-only comment carries no mark.
 */
export const CommentMarks: React.FC<{ comment: DeskComment }> = ({ comment }) => {
    const kind = comment.kind ?? null;
    if (kind === 'ai_draft') {
        return <div className="mt-1 flex flex-wrap items-center gap-2"><DeskChip tone="blue" icon={LockIcon}>{REPLY_PICKER.chipDraft}</DeskChip></div>;
    }
    if (kind === 'ai_answer') {
        const sentBy = comment.ai?.sentBy;
        const who = sentBy?.name || sentBy?.id || '';
        return (
            <div className="mt-1 flex flex-wrap items-center gap-2">
                <DeskChip tone="neutral" icon={SparklesIcon}>{REPLY_PICKER.chipAiAssisted}</DeskChip>
                {isWithdrawn(comment) && <DeskChip tone="outline" icon={XCircleIcon}>{REPLY_PICKER.chipWithdrawn}</DeskChip>}
                <span className={MUTED}>{who ? fill(REPLY_PICKER.sentBy, { name: who }) : REPLY_PICKER.postedAutomatically}</span>
            </div>
        );
    }
    if (comment.visibility === 'requester' && kind !== 'requester_reply') {
        return <div className="mt-1 flex flex-wrap items-center gap-2"><DeskChip tone="neutral" icon={EyeIcon}>{REPLY_PICKER.chipSentToRequester}</DeskChip></div>;
    }
    return null;
};

/** The text of a comment. A withdrawn answer reads "This answer was withdrawn." and keeps its original behind Show original. */
export const CommentBody: React.FC<{ comment: DeskComment; className?: string }> = ({ comment, className }) => {
    const [shown, setShown] = useState(false);
    const regionId = useId();
    const style = className ?? BODY_TEXT;
    if (!isWithdrawn(comment)) return <p className={style}>{comment.text}</p>;
    return (
        <div className="flex flex-col gap-1">
            <p className={style}>{REPLY_PICKER.withdrawnText}</p>
            <button type="button" className={`${TEXT_BUTTON} self-start`} aria-expanded={shown} aria-controls={regionId} onClick={() => setShown(v => !v)}>
                {REPLY_PICKER.showOriginal}
            </button>
            {shown && <p id={regionId} className={style}>{comment.text}</p>}
        </div>
    );
};
