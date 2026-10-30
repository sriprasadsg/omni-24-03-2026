import React from 'react';
import { formatClock } from './AutonomousOpsHealthBanners';
import {
    AlertOctagonIcon, AlertTriangleIcon, BellIcon, CheckCircleIcon, ClockIcon, ExternalLinkIcon, HeartPulseIcon,
    InfoIcon, LockIcon, PauseCircleIcon, RefreshCwIcon, XCircleIcon,
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

/**
 * One health chip: an icon (decorative) and the visible text, so meaning never rests on colour alone.
 * `label` overrides the text for the one chip that wears another chip's tone (a service running where it
 * is not expected reads "Running" in the Notice tone).
 */
export const HealthChip: React.FC<{ kind: HealthChipKind; label?: string }> = ({ kind, label }) => {
    const { label: defaultLabel, Icon, classes } = CHIPS[kind];
    return (
        <span className={`${CHIP_BASE} ${classes}`}>
            <Icon size={12} aria-hidden="true" />
            {label ?? defaultLabel}
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

/** "14:02", or an em dash when the watchdog did not send the time (a missing field always reads as a dash). */
export function clockOrDash(iso: string | null | undefined): string {
    return iso && !Number.isNaN(new Date(iso).getTime()) ? formatClock(iso) : '—';
}

/** Placeholder block for the first load of the Platform health section. */
export const HEALTH_SKELETON = 'animate-pulse rounded-lg bg-gray-200 dark:bg-white/10';

/** The 81 readout cell: label, value, and an optional helper line that wraps. */
export const HealthCell: React.FC<{ label: string; value: React.ReactNode; help?: React.ReactNode }> = ({ label, value, help }) => (
    <div className="min-w-0">
        <dt className="text-xs text-gray-500 dark:text-gray-400">{label}</dt>
        <dd className="mt-1 break-words text-sm font-semibold text-gray-900 dark:text-white">{value}</dd>
        {help && <p className="mt-1 break-words text-xs text-gray-500 dark:text-gray-400">{help}</p>}
    </div>
);

const NOTICE_TONES = {
    amber: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200',
    blue: 'border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-400/25 dark:bg-blue-400/10 dark:text-blue-200',
    red: 'border-red-200 bg-red-50 text-red-700 dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-300',
};

/** A tinted block with a 16px icon: the stop, not-installed, silent and error blocks of the Platform health section. */
export const HealthNotice: React.FC<{
    tone: keyof typeof NOTICE_TONES; icon?: React.FC<any>; role?: 'alert' | 'status'; children: React.ReactNode;
}> = ({ tone, icon, role, children }) => {
    const Icon = icon ?? (tone === 'blue' ? InfoIcon : AlertTriangleIcon);
    return (
        <div role={role} className={`flex items-start gap-2 break-words rounded-lg border p-4 text-sm ${NOTICE_TONES[tone]}`}>
            <Icon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
            <div className="flex min-w-0 flex-1 flex-col gap-2">{children}</div>
        </div>
    );
};

/** A link target is used only when it is https or points at this origin; anything else is shown as text (T-82-40). */
function safeHref(url: string | null | undefined): string | null {
    if (!url) return null;
    try {
        const parsed = new URL(url, window.location.origin);
        return parsed.protocol === 'https:' || parsed.origin === window.location.origin ? url : null;
    } catch {
        return null;
    }
}

/** "View install checklist": a new-tab link when the server gives a safe url, else the label and the repo path as text (D-24, H8). */
export const InstallChecklistLink: React.FC<{ checklist: { path: string; url: string | null } | null | undefined }> = ({ checklist }) => {
    if (!checklist) return null;
    const href = safeHref(checklist.url);
    if (href) {
        return (
            <a href={href} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm font-semibold underline underline-offset-2">
                View install checklist
                <ExternalLinkIcon size={12} aria-hidden="true" />
            </a>
        );
    }
    return (
        <span className="inline-flex flex-wrap items-baseline gap-x-2 text-sm font-semibold">
            <span>View install checklist</span>
            <span className="break-all font-mono text-xs font-normal">{checklist.path}</span>
        </span>
    );
};
