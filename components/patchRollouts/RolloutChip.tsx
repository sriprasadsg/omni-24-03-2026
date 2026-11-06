import React from 'react';
import type { ChipSpec, ChipTone } from './rolloutCopy';
import {
    AlertOctagonIcon, CheckCircleIcon, ClockIcon, FlaskConicalIcon, InfoIcon, RefreshCcwIcon, RefreshCwIcon,
    ShieldLockIcon, XCircleIcon,
} from '../icons';

/**
 * One chip of the rollout screens: the Phase 81 chip anatomy (a 12px decorative icon plus visible text, so meaning
 * never rests on colour alone) with the tone and icon chosen by rolloutCopy.ts. No tone is added to Phase 81's.
 */

const CHIP_BASE = 'inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold border break-words';

const TONES: Record<ChipTone, string> = {
    amber: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-400/10 dark:text-amber-200 dark:border-amber-400/25',
    blue: 'bg-blue-50 text-blue-800 border-blue-200 dark:bg-blue-400/10 dark:text-blue-200 dark:border-blue-400/25',
    green: 'bg-green-50 text-green-800 border-green-200 dark:bg-green-400/10 dark:text-green-200 dark:border-green-400/25',
    red: 'bg-red-50 text-red-700 border-red-200 dark:bg-red-400/10 dark:text-red-300 dark:border-red-400/25',
    neutral: 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-white/[0.06] dark:text-gray-200 dark:border-white/10',
    outline: 'bg-transparent text-gray-700 border-gray-300 dark:text-gray-200 dark:border-gray-600',
    dashed: 'bg-transparent text-gray-800 border-dashed border-gray-400 dark:text-gray-100 dark:border-gray-500',
};

/** The icon names rolloutCopy.ts uses, resolved to components/icons.tsx exports. */
const ICONS: Record<string, React.FC<any>> = {
    AlertOctagonIcon, CheckCircleIcon, ClockIcon, FlaskConicalIcon, InfoIcon, RefreshCcwIcon, RefreshCwIcon,
    ShieldLockIcon, XCircleIcon,
};

/** The classes of a chip tone, for a chip whose label is built from a count (`2 not reached`). */
export const chipClasses = (tone: ChipTone) => `${CHIP_BASE} ${TONES[tone]}`;

export const RolloutChip: React.FC<{ spec: ChipSpec; label?: string }> = ({ spec, label }) => {
    const Icon = ICONS[spec.icon] ?? InfoIcon;
    return (
        <span className={chipClasses(spec.tone)}>
            <Icon size={12} aria-hidden="true" />
            {label ?? spec.label}
        </span>
    );
};
