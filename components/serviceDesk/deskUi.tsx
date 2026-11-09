import React from 'react';
import { SparklesIcon } from '../icons';
import { KB, MARK, fill } from './serviceDeskCopy';

/**
 * Small pieces the ticket-screen desk components share (85-20): the chip anatomy and tones of 81-UI-SPEC (a 12px
 * decorative icon plus visible text, so meaning never rests on colour alone), the text styles, the buttons the
 * older Autonomous Ops files do not export, and the date and time words. No tone, size or weight is added.
 */

export { ACCENT_BUTTON } from '../AutonomousOpsResponseSettingsDialogs';
export { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
export { HealthNotice } from '../AutonomousOpsHealthChips';

const CHIP_BASE = 'inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold border';
const TONES = {
    blue: 'bg-blue-50 text-blue-800 border-blue-200 dark:bg-blue-400/10 dark:text-blue-200 dark:border-blue-400/25',
    neutral: 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-white/[0.06] dark:text-gray-200 dark:border-white/10',
    outline: 'bg-transparent text-gray-700 border-gray-300 dark:text-gray-200 dark:border-gray-600',
};

/** One chip of the 85 vocabulary: BLUE for a draft, NEUTRAL for requester-visible and AI items, OUTLINE for withdrawn. */
export const DeskChip: React.FC<{ tone: keyof typeof TONES; icon: React.FC<any>; children: React.ReactNode }> = ({
    tone, icon: Icon, children,
}) => (
    <span className={`${CHIP_BASE} ${TONES[tone]}`}>
        <Icon size={12} aria-hidden="true" />
        {children}
    </span>
);

/** 12px, 400, muted: helper, reason and meta lines. */
export const MUTED = 'break-words text-xs text-gray-500 dark:text-gray-400';
/** 14px, 400: answer and article text. Never truncated and never clamped. */
export const BODY_TEXT = 'whitespace-pre-wrap break-words text-sm text-gray-900 dark:text-white';
/** Red confirm: the one destructive button of the phase (Discard draft), the 40px consequential shape. */
export const RED_BUTTON =
    'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-red-600 px-4 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60';
/** A quiet text button (Try again, Show original, Back to answer). */
export const TEXT_BUTTON =
    'inline-flex min-h-8 items-center text-sm font-semibold underline underline-offset-2 text-gray-700 dark:text-gray-200 disabled:opacity-60';
/** Red role-alert line under a row of buttons. */
export const ERROR_LINE = 'break-words text-sm text-red-700 dark:text-red-300';

/** The D-13 mark every AI answer wears: "AI-assisted answer from your IT knowledge base". */
export const AiMark: React.FC = () => (
    <p className="flex items-center gap-1 text-xs font-semibold text-gray-700 dark:text-gray-200">
        <SparklesIcon size={12} aria-hidden="true" />
        {MARK}
    </p>
);

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const pad = (n: number) => String(n).padStart(2, '0');
const parse = (iso: string | null | undefined): Date | null => {
    const at = iso ? new Date(iso) : null;
    return at && !Number.isNaN(at.getTime()) ? at : null;
};

/** "Tue 12 Nov" on the viewer's own calendar (R3). An unreadable moment reads as an empty string, never "Invalid Date". */
export function formatDay(iso: string | null | undefined): string {
    const at = parse(iso);
    return at ? `${DAYS[at.getDay()]} ${at.getDate()} ${MONTHS[at.getMonth()]}` : '';
}

/** "14:30" on the viewer's own 24-hour clock. */
export function formatHm(iso: string | null | undefined): string {
    const at = parse(iso);
    return at ? `${pad(at.getHours())}:${pad(at.getMinutes())}` : '';
}

/** "Tue 12 Nov, 14:30". */
export function formatDayTime(iso: string | null | undefined): string {
    const day = formatDay(iso);
    return day ? `${day}, ${formatHm(iso)}` : '';
}

/** The server's message from a failed call, without its closing full stop, or '' when it gave none. */
export function failureMessage(e: unknown): string {
    const detail = (e as { detail?: unknown } | null)?.detail;
    return typeof detail === 'string' ? detail.trim().replace(/[.\s]+$/, '') : '';
}

/** The HTTP status of a failed call, or 0 when the request never got an answer. */
export function failureStatus(e: unknown): number {
    const status = (e as { status?: unknown } | null)?.status;
    return typeof status === 'number' ? status : 0;
}

/**
 * One failure line in plain words (UI-SPEC Copywriting Contract): `withMessage` filled with the server's own message,
 * or `fallback` when it gave none. A refusal with no message and status 403 is the Platform organization's, which the
 * service desk is not available to.
 */
export function failureLine(e: unknown, withMessage: string, fallback: string): string {
    const message = failureMessage(e) || (failureStatus(e) === 403 ? KB.platformRefused.replace(/[.\s]+$/, '') : '');
    return message ? fill(withMessage, { message }) : fallback;
}
