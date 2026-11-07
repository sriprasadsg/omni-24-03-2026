/**
 * Staged patch rollouts: the payload types every rollout screen reads (84-02). The backend views (84-09,
 * 84-10) build exactly these shapes, and every rollout UI file imports them from here, so a field is named
 * once. Types only: no fetch code lives here.
 *
 * The server decides every control: a flag such as `canStart` or `canApprove` is the only reason a button
 * renders, and the browser never infers a permission from a role. Every string in a payload is server text
 * and is rendered as React text only. Times are ISO strings (`null` when not known).
 */

/** A rollout as the list shows it: the stored status plus the two waiting states the server derives. */
export type RolloutStatus =
    | 'waiting_for_approval' | 'waiting_for_window' | 'running' | 'halted' | 'completed' | 'cancelled';

/** The 84-01 RING_STATES values. */
export type RingState =
    | 'not_started' | 'waiting_for_window' | 'waiting_for_approval' | 'installing' | 'restarting' | 'soaking'
    | 'checking_health' | 'passed' | 'halted' | 'reverted' | 'cancelled';

export type HostState =
    | 'waiting' | 'installing' | 'installed' | 'restarting' | 'healthy' | 'failed' | 'reverting' | 'reverted'
    | 'not_reverted' | 'not_reached' | 'left_out' | 'would_install' | 'would_restart';

/** `agent_only`: an empty watched-services list. `not_checked` (DEV-2): the agent does not report service state yet. */
export type SignalState = 'passed' | 'failed' | 'waiting' | 'no_data' | 'not_checked' | 'agent_only';

export type SignalName = 'install' | 'inventory' | 'heartbeat' | 'services';

/** Where a text link in a row or block leads. */
export type PreflightLink = 'maintenance' | 'rings' | 'agentGroups';

// ---------------------------------------------------------------- the Rollouts tab

export interface WindowStrip {
    state: 'open' | 'closed' | 'none';
    /** The sentence next to the chip, for example `Closes at 04:00 (Asia/Kolkata).` */
    text: string;
    closesAt: string | null;
    nextOpensAt: string | null;
    /** The IANA name, or null when the organization has none set (windows then use UTC). */
    timeZone: string | null;
}

export interface RolloutFlags {
    canStart: boolean;
    canManageRings: boolean;
    canOpenDecisions: boolean;
    shadow: boolean;
    stopped: boolean;
    stopScope: 'tenant' | 'platform' | null;
    platformTenant: boolean;
}

export interface HealthRow {
    signal: SignalName;
    state: SignalState;
    text: string;
}

export interface HostRow {
    agentId: string;
    hostname: string;
    os: string;
    state: HostState;
    /** The server's Result sentence; it never claims a revert that did not happen. */
    result: string;
    changedAt: string | null;
}

export interface RingView {
    index: number;
    name: string;
    /** Group names, rendered mono. */
    groups: string[];
    state: RingState;
    /** The server's detail line under the chip. */
    detail: string;
    /** Replaces the `Review in Needs your decision` link when the viewer cannot open that screen. */
    waitingText: string | null;
    /** True when the ring waits for approval and the viewer may open Needs your decision. */
    decisionsLink: boolean;
    health: HealthRow[];
    failureRateText: string;
    soakText: string;
    /** The first page of computers, problems first. */
    hosts: HostRow[];
    hostTotal: number;
}

export interface HaltBlock {
    ringName: string;
    /** The reason after `Halted at {ring}: `. */
    reason: string;
    /** The revert summary lines, written by the server so they never overstate. */
    reverts: string[];
}

export interface RolloutCard {
    id: string;
    name: string;
    status: RolloutStatus;
    simulation: boolean;
    patchCount: number;
    computerCount: number;
    startedAt: string | null;
    startedBy: string | null;
    rings: RingView[];
    currentRing: number | null;
    halt: HaltBlock | null;
    notReachedCount: number;
    closesAt: string | null;
    neverReachedCount: number;
    closedText: string | null;
    canResume: boolean;
    canCancel: boolean;
    /** Why Resume is disabled, for `aria-describedby`; null when it is enabled. */
    resumeBlockedReason: string | null;
    revertRunning: boolean;
    /** The server's sentence for the Cancel dialog of a running rollout (nothing is reverted); null otherwise. */
    cancelNote: string | null;
}

export interface RolloutPage {
    items: RolloutCard[];
    total: number;
    offset: number;
    limit: number;
    /** Rollouts that need a person: waiting for approval, or halted and needing Resume or Cancel. */
    attentionCount: number;
    window: WindowStrip;
    flags: RolloutFlags;
    ringsSet: boolean;
    ringsSummary: string;
}

// ---------------------------------------------------------------- Start rollout

export type PreflightCheck =
    | 'window' | 'rings' | 'canary' | 'left_out' | 'offline' | 'autonomous_ops' | 'cap' | 'patches' | 'stopped';

export interface PreflightRow {
    check: PreflightCheck;
    ok: boolean;
    blocker: boolean;
    title: string;
    detail: string;
    link: PreflightLink | null;
    /** At most 10 computer names for the `Show hosts` disclosure. */
    hosts: string[];
    hostTotal: number;
}

export interface Preflight {
    rows: PreflightRow[];
    canStart: boolean;
    firstBlocker: string | null;
    nextWindowText: string | null;
}

export interface PendingPatch {
    patchId: string;
    title: string;
    os: 'windows' | 'linux';
    computers: number;
}

export interface PendingPatchPage {
    items: PendingPatch[];
    total: number;
    offset: number;
    limit: number;
}

export interface StartRequest {
    name: string;
    patchIds: string[];
}

export interface StartResult {
    id: string;
    name: string;
    simulation: boolean;
}

/** A draft filled in from a vulnerability suggestion; nothing is stored until the operator presses Start. */
export interface DraftPayload {
    name: string;
    patchIds: string[];
    /** Suggested patches that are no longer pending and were dropped. */
    removedCount: number;
    host: string;
    cves: string[];
}

// ---------------------------------------------------------------- Rollout rings settings

export interface RingSettingView {
    key: string;
    name: string;
    groupIds: string[];
    soakHours: number;
    failPct: number;
    minSample: number;
}

export interface RingsSettings {
    rings: RingSettingView[];
    /** False when the saved settings could not be read: no rollout can start until they load. */
    readable: boolean;
    groups: Array<{ id: string; name: string; computers: number; ring: string | null }>;
}

// ---------------------------------------------------------------- the approval card in Needs your decision

export type ApprovalLineKind = 'install' | 'reboot' | 'revert_reboot';

export interface ApprovalLine {
    line: ApprovalLineKind;
    state: 'pending' | 'approved' | 'denied' | 'expired';
    label: string;
    /** Mono target text: the first three patch ids then `+{m} more`. */
    targetText: string;
    why: string;
    whatHappens: string;
    /** At most 10 computer names for `Show computers`. */
    computers: string[];
    computerTotal: number;
    canApprove: boolean;
    canDeny: boolean;
    /** The settled Result text once decided; null while pending. */
    resultText: string | null;
    expiresAt: string | null;
}

export interface ApprovalCard {
    kind: 'rollout';
    rolloutId: string;
    ring: string;
    /** `approval-rollout-{rolloutId}-{ring}` */
    anchorId: string;
    name: string;
    subtitle: string;
    expiresAt: string | null;
    lines: ApprovalLine[];
}

export interface LineDecisionResult {
    status: 'approved' | 'denied' | 'stopped' | 'expired' | 'already_handled' | 'refused';
    when: 'now' | 'window' | null;
    windowOpensAt: string | null;
    approved: number;
    refused: Array<{ hostname: string; reason: string }>;
    message: string;
}

// ---------------------------------------------------------------- maintenance windows

export interface MaintenanceWindow {
    id: string;
    name: string;
    recurrence: 'none' | 'daily' | 'weekly';
    /** `HH:MM` in the organization's time zone (recurring windows). */
    startTime: string | null;
    endTime: string | null;
    /** ISO weekdays, 1 (Monday) to 7 (Sunday); null for every day. */
    daysOfWeek: number[] | null;
    /** ISO times of a one-time window. */
    startsAt: string | null;
    endsAt: string | null;
    scheduleText: string;
    nextText: string;
    openNow: boolean;
}

/** What the window dialog sends. */
export interface WindowBody {
    name: string;
    recurrence: 'none' | 'daily' | 'weekly';
    startTime?: string | null;
    endTime?: string | null;
    daysOfWeek?: number[] | null;
    startsAt?: string | null;
    endsAt?: string | null;
}

export interface TimeZoneSettings {
    timeZone: string | null;
}

export interface WindowStatus {
    state: 'open' | 'closed' | 'none';
    text: string;
    timeZone: string | null;
}

/** One row of the read-only list in Change Management. */
export interface ChangeWindowRow {
    id: string;
    name: string;
    scheduleText: string;
    openNow: boolean;
    nextText: string;
}
