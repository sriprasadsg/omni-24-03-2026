import React from 'react';
import type { DeskMode, PostingBlocker } from '../../services/serviceDesk/types';
import { HealthChip } from '../AutonomousOpsHealthChips';
import { CheckCircleIcon, ClockIcon } from '../icons';
import { MODES, READINESS, SETTINGS, fill } from './serviceDeskCopy';

const HELPER = 'break-words text-xs text-gray-500 dark:text-gray-400';

const ORDER: DeskMode[] = ['off', 'drafts', 'post'];

const LEVEL_LABEL: Record<string, string> = { off: 'Off', suggest: 'Suggest', undoable_auto: 'Undoable-auto' };

interface ModeGroupProps {
    /** The staged choice. */
    value: DeskMode;
    onChange: (mode: DeskMode) => void;
    disabled?: boolean;
    /** True while the desk breaker is stored: Post answers cannot be chosen until Restore Post answers. */
    postLocked: boolean;
    labelId: string;
    reasonId: string;
}

/**
 * The three options of D-03 as a radiogroup (UI-SPEC 2c). A label wraps a visually hidden radio so the arrow keys move
 * between them; the selected option is a heavier neutral outline plus a check, never the accent, so Post answers never
 * looks like the safe default.
 */
export const DeskModeGroup: React.FC<ModeGroupProps> = ({ value, onChange, disabled, postLocked, labelId, reasonId }) => (
    <div className="flex flex-col gap-2">
        <p id={labelId} className="break-words text-sm font-semibold text-gray-900 dark:text-white">{SETTINGS.modeGroupLabel}</p>
        <div role="radiogroup" aria-labelledby={labelId} className="grid gap-4 lg:grid-cols-3">
            {ORDER.map(mode => {
                const locked = mode === 'post' && postLocked;
                const selected = value === mode;
                return (
                    <label
                        key={mode}
                        className={`relative flex min-h-10 min-w-0 cursor-pointer flex-col gap-1 rounded-lg border p-4 ${
                            selected
                                ? 'border-gray-900 ring-1 ring-gray-900 dark:border-gray-100 dark:ring-gray-100'
                                : 'border-gray-300 dark:border-gray-600'
                        } ${locked || disabled ? 'cursor-not-allowed opacity-60' : ''}`}
                    >
                        <input
                            type="radio" name={`${labelId}-mode`} value={mode} checked={selected}
                            disabled={disabled || locked}
                            aria-describedby={locked ? reasonId : undefined}
                            onChange={() => onChange(mode)} className="sr-only"
                        />
                        <span className="flex items-start justify-between gap-2">
                            <span className="break-words text-sm font-semibold text-gray-900 dark:text-white">{MODES[mode].title}</span>
                            {selected && <CheckCircleIcon size={16} aria-hidden="true" className="shrink-0 text-gray-900 dark:text-gray-100" />}
                        </span>
                        <span className={HELPER}>{MODES[mode].description}</span>
                        {locked && <span id={reasonId} className={HELPER}>{SETTINGS.restoreFirst}</span>}
                    </label>
                );
            })}
        </div>
        <p className={HELPER}>{SETTINGS.modeHelper}</p>
        <p className={HELPER}>{SETTINGS.postingHelper}</p>
    </div>
);

type ReadinessKey = 'level' | 'shadow' | 'stop' | 'hourlyLimit' | 'deskBreaker';

const ROWS: Array<{ code: PostingBlocker['code']; key: ReadinessKey }> = [
    { code: 'level', key: 'level' },
    { code: 'shadow', key: 'shadow' },
    { code: 'stop', key: 'stop' },
    { code: 'hourly_limit', key: 'hourlyLimit' },
    { code: 'desk_breaker', key: 'deskBreaker' },
];

/** The sentence a not-met condition shows; the first one is also what the Post answers dialog quotes. */
export function blockerText(blocker: PostingBlocker): string {
    const row = ROWS.find(r => r.code === blocker.code);
    if (!row) return '';
    const copy = READINESS[row.key];
    if (blocker.code === 'level') return fill(copy.notMet, { level: LEVEL_LABEL[blocker.level ?? ''] ?? blocker.level ?? 'Off' });
    return copy.notMet;
}

/**
 * Will answers be posted? (UI-SPEC 2d). Five rows, each met or not met, drawn only from the server's own blocker list: the
 * card never works out a condition itself. The caller shows it only while the saved mode is Post answers.
 */
export const DeskReadiness: React.FC<{ blockers: PostingBlocker[]; posting: boolean; labelId: string }> = ({ blockers, posting, labelId }) => (
    <div className="flex flex-col gap-2" role="status" aria-labelledby={labelId}>
        <div className="flex flex-wrap items-center gap-2">
            <p id={labelId} className="text-sm font-semibold text-gray-900 dark:text-white">{READINESS.label}</p>
            {posting
                ? <HealthChip kind="healthy" label={READINESS.chipPosting} />
                : <HealthChip kind="checking" label={READINESS.chipDraftsForNow} />}
        </div>
        <ul className="flex flex-col gap-2">
            {ROWS.map(row => {
                const unmet = blockers.find(b => b.code === row.code);
                const Icon = unmet ? ClockIcon : CheckCircleIcon;
                return (
                    <li key={row.code} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-200">
                        <Icon
                            size={16} aria-hidden="true"
                            className={`mt-0.5 shrink-0 ${unmet ? 'text-amber-600 dark:text-amber-300' : 'text-green-600 dark:text-green-300'}`}
                        />
                        <span className="min-w-0 break-words">{unmet ? blockerText(unmet) : READINESS[row.key].met}</span>
                    </li>
                );
            })}
        </ul>
    </div>
);
