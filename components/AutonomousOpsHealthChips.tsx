import React from 'react';
import {
    AlertOctagonIcon, AlertTriangleIcon, BellIcon, CheckCircleIcon, ClockIcon, HeartPulseIcon, InfoIcon,
    LockIcon, PauseCircleIcon, RefreshCwIcon, XCircleIcon,
} from './icons';

/** Every chip of the Phase 82 health vocabulary (82-UI-SPEC, New chips). */
export type HealthChipKind =
    | 'healthy' | 'checking' | 'restarting' | 'down' | 'gave_up' | 'expected_off' | 'unknown'
    | 'running' | 'silent' | 'not_installed' | 'ok' | 'notice' | 'warning' | 'critical' | 'pinned'
    | 'working' | 'not_working' | 'not_set_up' | 'not_tested' | 'counting_only' | 'deleting_nightly'
    | 'waiting' | 'running_now' | 'paged' | 'skipped';

// The 81 chip anatomy and tone classes (AutonomousOpsActivityList), unchanged: no tone is added.
const CHIP_BASE = 'inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold border';
const GREEN = 'bg-green-50 text-green-800 border-green-200 dark:bg-green-400/10 dark:text-green-200 dark:border-green-400/25';
const AMBER = 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-400/10 dark:text-amber-200 dark:border-amber-400/25';
const RED = 'bg-red-50 text-red-700 border-red-200 dark:bg-red-400/10 dark:text-red-300 dark:border-red-400/25';
const BLUE = 'bg-blue-50 text-blue-800 border-blue-200 dark:bg-blue-400/10 dark:text-blue-200 dark:border-blue-400/25';
const NEUTRAL = 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-white/[0.06] dark:text-gray-200 dark:border-white/10';
const OUTLINE = 'bg-transparent text-gray-700 border-gray-300 dark:text-gray-200 dark:border-gray-600';

const CHIPS: Record<HealthChipKind, { label: string; Icon: React.FC<any>; classes: string }> = {
    healthy: { label: 'Healthy', Icon: CheckCircleIcon, classes: GREEN },
    checking: { label: 'Checking', Icon: ClockIcon, classes: AMBER },
    restarting: { label: 'Restarting', Icon: RefreshCwIcon, classes: AMBER },
    down: { label: 'Down', Icon: XCircleIcon, classes: RED },
    gave_up: { label: 'Gave up', Icon: AlertOctagonIcon, classes: RED },
    expected_off: { label: 'Expected off', Icon: InfoIcon, classes: OUTLINE },
    unknown: { label: 'Unknown', Icon: InfoIcon, classes: OUTLINE },
    running: { label: 'Running', Icon: HeartPulseIcon, classes: GREEN },
    silent: { label: 'Silent', Icon: AlertOctagonIcon, classes: RED },
    not_installed: { label: 'Not installed', Icon: InfoIcon, classes: OUTLINE },
    ok: { label: 'OK', Icon: CheckCircleIcon, classes: GREEN },
    notice: { label: 'Notice', Icon: InfoIcon, classes: BLUE },
    warning: { label: 'Warning', Icon: AlertTriangleIcon, classes: AMBER },
    critical: { label: 'Critical', Icon: AlertOctagonIcon, classes: RED },
    pinned: { label: 'Pinned by agents', Icon: LockIcon, classes: OUTLINE },
    working: { label: 'Working', Icon: CheckCircleIcon, classes: GREEN },
    not_working: { label: 'Not working', Icon: XCircleIcon, classes: RED },
    not_set_up: { label: 'Not set up', Icon: AlertTriangleIcon, classes: AMBER },
    not_tested: { label: 'Not tested', Icon: InfoIcon, classes: NEUTRAL },
    counting_only: { label: 'Counting only', Icon: ClockIcon, classes: AMBER },
    deleting_nightly: { label: 'Deleting nightly', Icon: CheckCircleIcon, classes: GREEN },
    waiting: { label: 'Waiting for confirmation', Icon: ClockIcon, classes: AMBER },
    running_now: { label: 'Running now', Icon: RefreshCwIcon, classes: AMBER },
    paged: { label: 'Paged', Icon: BellIcon, classes: NEUTRAL },
    skipped: { label: 'Skipped', Icon: PauseCircleIcon, classes: OUTLINE },
};

/** One health chip: an icon (decorative) and the visible text, so meaning never rests on colour alone. */
export const HealthChip: React.FC<{ kind: HealthChipKind }> = ({ kind }) => {
    const { label, Icon, classes } = CHIPS[kind];
    return (
        <span className={`${CHIP_BASE} ${classes}`}>
            <Icon size={12} aria-hidden="true" />
            {label}
        </span>
    );
};

/**
 * The severity ladder shared by certificates, disk fullness and disk forecast: rung 0 is OK, 1 Notice,
 * 2 Warning, 3 Critical. A rung beyond the ladder is Critical; a rung that cannot be read is Unknown.
 */
export function ladderChip(rung: number | null | undefined): HealthChipKind {
    if (typeof rung !== 'number' || Number.isNaN(rung)) return 'unknown';
    if (rung >= 3) return 'critical';
    if (rung >= 2) return 'warning';
    if (rung >= 1) return 'notice';
    return 'ok';
}
