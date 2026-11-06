/**
 * Staged patch rollouts: the words, tones and icons the rollout screens share (84-UI-SPEC Color table and
 * Copywriting Contract). Server sentences (halt reasons, ring detail lines, Result texts) arrive in the payload
 * from backend/autonomous_ops/rollout/messages.py; this file holds only what the browser itself decides: chip
 * labels, chip tones, icon names, the assurance line and link labels. No component code lives here.
 *
 * Copy rules (ACTV-08): plain English, say "revert" or "put back", never an unqualified word for undoing a change
 * in bulk, no emoji. The directory is scanned by the copy gate.
 */
import type { HostState, RingState, RolloutStatus, SignalState } from '../../services/patchRollouts/types';

/** The tone a chip takes. `dashed` is the Simulation chip; `outline` is OUTLINE_CHIP from Phase 81. */
export type ChipTone = 'amber' | 'blue' | 'green' | 'red' | 'neutral' | 'outline' | 'dashed';

/** `icon` is the export name in components/icons.tsx; the component that renders the chip imports it. */
export interface ChipSpec {
    label: string;
    tone: ChipTone;
    icon: string;
}

/** Shown under the tab header, in the Start dialog and at the head of the halt block's second line. */
export const ASSURANCE_LINE =
    'A rollout halts on failure; reverts where supported. Nothing is installed outside your maintenance window.';

const WAITING: Pick<ChipSpec, 'tone' | 'icon'> = { tone: 'amber', icon: 'ClockIcon' };
const IN_PROGRESS: Pick<ChipSpec, 'tone' | 'icon'> = { tone: 'blue', icon: 'RefreshCwIcon' };
const PASSED: Pick<ChipSpec, 'tone' | 'icon'> = { tone: 'green', icon: 'CheckCircleIcon' };
const FAILED: Pick<ChipSpec, 'tone' | 'icon'> = { tone: 'red', icon: 'XCircleIcon' };
const ENDED: Pick<ChipSpec, 'tone' | 'icon'> = { tone: 'neutral', icon: 'XCircleIcon' };

export const SIMULATION_CHIP: ChipSpec = { label: 'Simulation', tone: 'dashed', icon: 'FlaskConicalIcon' };

/** The rollout-level chip. `Halted` takes the octagon here and the plain cross on a ring. */
export const ROLLOUT_STATUS_CHIP: Record<RolloutStatus, ChipSpec> = {
    waiting_for_approval: { label: 'Waiting for approval', ...WAITING },
    waiting_for_window: { label: 'Waiting for window', ...WAITING },
    running: { label: 'Running', ...IN_PROGRESS },
    halted: { label: 'Halted', tone: 'red', icon: 'AlertOctagonIcon' },
    completed: { label: 'Completed', ...PASSED },
    cancelled: { label: 'Cancelled', ...ENDED },
};

/** One entry per ring state (the 84-01 RING_STATES values). */
export const RING_STATE_CHIP: Record<RingState, ChipSpec> = {
    not_started: { label: 'Not started', tone: 'neutral', icon: 'ClockIcon' },
    waiting_for_window: { label: 'Waiting for window', ...WAITING },
    waiting_for_approval: { label: 'Waiting for approval', ...WAITING },
    installing: { label: 'Installing', ...IN_PROGRESS },
    restarting: { label: 'Restarting', ...IN_PROGRESS },
    soaking: { label: 'Soaking', ...IN_PROGRESS },
    checking_health: { label: 'Checking health', ...IN_PROGRESS },
    passed: { label: 'Passed', ...PASSED },
    halted: { label: 'Halted', ...FAILED },
    reverted: { label: 'Reverted', tone: 'neutral', icon: 'RefreshCcwIcon' },
    cancelled: { label: 'Cancelled', ...ENDED },
};

/** One entry per computer state. `would_*` are the shadow-mode (simulation) states. */
export const HOST_STATE_CHIP: Record<HostState, ChipSpec> = {
    waiting: { label: 'Waiting', ...WAITING },
    installing: { label: 'Installing', ...IN_PROGRESS },
    installed: { label: 'Installed', ...PASSED },
    restarting: { label: 'Restarting', ...IN_PROGRESS },
    healthy: { label: 'Healthy', ...PASSED },
    failed: { label: 'Failed', ...FAILED },
    reverting: { label: 'Reverting', ...IN_PROGRESS },
    reverted: { label: 'Reverted', tone: 'neutral', icon: 'RefreshCcwIcon' },
    not_reverted: { label: 'Not reverted', tone: 'outline', icon: 'ShieldLockIcon' },
    not_reached: { label: 'Not reached', tone: 'outline', icon: 'ClockIcon' },
    left_out: { label: 'Left out', tone: 'outline', icon: 'InfoIcon' },
    would_install: { label: 'Would install', tone: 'dashed', icon: 'FlaskConicalIcon' },
    would_restart: { label: 'Would restart', tone: 'dashed', icon: 'FlaskConicalIcon' },
};

/**
 * The four health-check signals. `agent_only` is a Services row with an empty watched list: it reads as
 * passed and its text says only the agent service is checked. `not_checked` (DEV-2) is a computer whose agent
 * does not report service state yet: it is never shown as Passed and does not halt the ring.
 */
export const SIGNAL_CHIP: Record<SignalState, ChipSpec> = {
    passed: { label: 'Passed', ...PASSED },
    agent_only: { label: 'Passed', ...PASSED },
    failed: { label: 'Failed', ...FAILED },
    waiting: { label: 'Waiting', ...WAITING },
    no_data: { label: 'No data', ...FAILED },
    not_checked: { label: 'Not checked', tone: 'outline', icon: 'InfoIcon' },
};

/** The text links and the secondary buttons the screens share. */
export const LINK_LABELS = {
    maintenance: 'Open maintenance windows',
    rings: 'Open rollout rings',
    agentGroups: 'Open agent groups',
    reviewDecisions: 'Review in Needs your decision',
    draftRollout: 'Draft a rollout',
    manageInSettings: 'Manage in Settings',
    showDetails: 'Show details',
    hideDetails: 'Hide details',
    showHosts: 'Show hosts',
    showComputers: 'Show computers',
    startRollout: 'Start rollout',
    tryAgain: 'Try again',
} as const;

/** The number and the noun that agrees with it: plural(1, 'computer', 'computers') is '1 computer'. */
export function plural(n: number, one: string, many: string): string {
    return `${n} ${n === 1 ? one : many}`;
}
