/**
 * Shared fixtures for the rollout screen tests (84-14): the 84-09 payload shapes of services/patchRollouts/types.ts.
 * Test files declare their own vi.mock calls; this file only builds data.
 */
import type {
    HostRow, RingView, RolloutCard, RolloutFlags, RolloutPage, WindowStrip,
} from '../../services/patchRollouts/types';

export const MIN = 60_000;
export const HOUR = 60 * MIN;
export const at = (ms: number) => new Date(Date.now() + ms).toISOString();

export const host = (over: Partial<HostRow> = {}): HostRow => ({
    agentId: 'a1', hostname: 'web-01', os: 'Linux', state: 'healthy', result: 'Passed every check at 14:02.',
    changedAt: at(-HOUR), ...over,
});

export const ring = (over: Partial<RingView> = {}): RingView => ({
    index: 0, name: 'Canary', groups: ['canary-hosts'], state: 'passed', detail: '3 computers healthy.',
    waitingText: null, decisionsLink: false, health: [], failureRateText: 'Any failure halts the rollout.',
    soakText: 'Soaks 4 hours after the last install or restart.', hosts: [], hostTotal: 3, ...over,
});

export const card = (over: Partial<RolloutCard> = {}): RolloutCard => ({
    id: 'R1', name: 'November security', status: 'running', simulation: false, patchCount: 2, computerCount: 12,
    startedAt: at(-3 * HOUR), startedBy: 'Asha', currentRing: 1,
    rings: [
        ring({ index: 0, name: 'Canary', state: 'passed', detail: '3 computers healthy.' }),
        ring({ index: 1, name: 'Early', groups: ['early-a', 'early-b'], state: 'installing', detail: '4 of 9 installed.', hostTotal: 9 }),
        ring({ index: 2, name: 'Broad', groups: [], state: 'not_started', detail: 'Starts after Early passes.', hostTotal: 0 }),
    ],
    halt: null, notReachedCount: 0, closesAt: null, neverReachedCount: 0, closedText: null,
    canResume: false, canCancel: false, resumeBlockedReason: null, revertRunning: false, cancelNote: null,
    cancelling: false, cancelRequestedBy: null, cancelRequestedAt: null, cancellingNote: null, ...over,
});

export const flags = (over: Partial<RolloutFlags> = {}): RolloutFlags => ({
    canStart: true, canManageRings: true, canOpenDecisions: true, shadow: false, stopped: false, stopScope: null,
    platformTenant: false, ...over,
});

export const openWindow = (over: Partial<WindowStrip> = {}): WindowStrip => ({
    state: 'open', text: 'Closes at 04:00 (Asia/Kolkata).', closesAt: at(HOUR), nextOpensAt: null,
    timeZone: 'Asia/Kolkata', ...over,
});

export const rolloutPage = (items: RolloutCard[], over: Partial<RolloutPage> = {}): RolloutPage => ({
    items, total: items.length, offset: 0, limit: 10, attentionCount: 0, window: openWindow(), flags: flags(),
    ringsSet: true, ringsSummary: '3 rings set up.', ...over,
});

export const jsonRes = (body: unknown, status = 200) =>
    ({ ok: status < 400, status, json: async () => body }) as unknown as Response;
