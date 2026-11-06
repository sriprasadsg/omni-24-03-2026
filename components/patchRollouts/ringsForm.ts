import type { RingInput } from '../../services/patchRollouts/rings';
import type { RingSettingView, RingsSettings } from '../../services/patchRollouts/types';

/**
 * The staged form of the Rollout rings card (84-17, UI-SPEC section 5): the rings as the person edits them (numbers
 * stay text until Save so an empty or half-typed field can be flagged), the checks the card shows inline before it
 * asks the server, and the one-line summary. The server checks every value again; the sentences here are the ones
 * the contract words (the card holds the text), plus the server's own for a middle ring with no group.
 */

export const MIN_RINGS = 2;
export const MAX_RINGS = 4;
export const NAME_MAX = 40;
export const CANARY_NAME = 'Canary';
export const LAST_RING_NAME = 'Everyone else';

/** What can be wrong with a ring; the card words each code (RINGS_PROBLEM_TEXT in RingsSettings.tsx). */
export type ProblemCode = 'canaryGroup' | 'middleGroup' | 'name' | 'unique' | 'soak' | 'failPct' | 'minSample';

export const NOT_SET_SUMMARY = 'No rings set up yet · Canary needs a group before a rollout can start';

export interface DraftRing {
    /** The saved key; empty for a ring added in this form (the server gives it one). */
    key: string;
    name: string;
    groupIds: string[];
    soak: string;
    failPct: string;
    minSample: string;
}

export interface RingProblems {
    name?: ProblemCode;
    groups?: ProblemCode;
    soak?: ProblemCode;
    failPct?: ProblemCode;
    minSample?: ProblemCode;
}

const draftOf = (r: RingSettingView): DraftRing => ({
    key: r.key, name: r.name, groupIds: [...r.groupIds],
    soak: String(r.soakHours), failPct: String(r.failPct), minSample: String(r.minSample),
});

/** The saved rings as a form; with fewer than two saved, the starting point is the Canary ring and a last ring. */
export function ringsToDraft(saved: RingsSettings | null): DraftRing[] {
    if (saved && saved.rings.length >= MIN_RINGS) return saved.rings.map(draftOf);
    const blank = { groupIds: [], soak: '24', failPct: '10', minSample: '10' };
    return [{ key: 'canary', name: CANARY_NAME, ...blank }, { key: '', name: LAST_RING_NAME, ...blank }];
}

/** A new ring for the end of the list, named so it does not repeat an existing name. */
export function newRing(rings: DraftRing[]): DraftRing {
    const taken = new Set(rings.map(r => r.name.trim().toLowerCase()));
    let n = rings.length + 1;
    while (taken.has(`ring ${n}`)) n += 1;
    return { key: '', name: `Ring ${n}`, groupIds: [], soak: '24', failPct: '10', minSample: '10' };
}

const WHOLE = /^\d+$/;
const DECIMAL = /^\d+(\.\d+)?$/;
const inRange = (text: string, pattern: RegExp, low: number, high: number) => {
    const value = text.trim();
    return pattern.test(value) && Number(value) >= low && Number(value) <= high;
};

/** What is wrong with each ring, in order; an empty object is a ring that can be saved. */
export function validateRings(rings: DraftRing[]): RingProblems[] {
    const firstSeen = new Map<string, number>();
    return rings.map((ring, index) => {
        const problems: RingProblems = {};
        const name = ring.name.trim();
        if (index > 0) {
            if (!name) problems.name = 'name';
            else if (firstSeen.has(name.toLowerCase())) problems.name = 'unique';
        }
        if (name && !firstSeen.has(name.toLowerCase())) firstSeen.set(name.toLowerCase(), index);
        if (ring.groupIds.length === 0) {
            if (index === 0) problems.groups = 'canaryGroup';
            else if (index < rings.length - 1) problems.groups = 'middleGroup';
        }
        if (!inRange(ring.soak, DECIMAL, 1, 168)) problems.soak = 'soak';
        if (index > 0) {
            if (!inRange(ring.failPct, WHOLE, 1, 50)) problems.failPct = 'failPct';
            if (!inRange(ring.minSample, WHOLE, 1, 100)) problems.minSample = 'minSample';
        }
        return problems;
    });
}

export const hasProblems = (problems: RingProblems[]) => problems.some(p => Object.keys(p).length > 0);

/** The rings as the PUT sends them. Only call this for a form with no problems. */
export function toInput(rings: DraftRing[]): RingInput[] {
    return rings.map((r, index) => ({
        ...(r.key ? { key: r.key } : {}),
        name: index === 0 ? CANARY_NAME : r.name.trim(),
        groupIds: r.groupIds,
        soakHours: Number(r.soak),
        failPct: Number(r.failPct),
        minSample: Number(r.minSample),
    }));
}

/** True when the form differs from the saved rings (group order and surrounding spaces do not count). */
export function isDirty(rings: DraftRing[], baseline: DraftRing[]): boolean {
    const plain = (list: DraftRing[]) => JSON.stringify(list.map(r => [
        r.key, r.name.trim(), [...r.groupIds].sort(), r.soak.trim(), r.failPct.trim(), r.minSample.trim(),
    ]));
    return plain(rings) !== plain(baseline);
}

/** `Canary (Canary) -> Pilot (Servers) -> Everyone else · 24-hour soak`, the same line the server writes. */
export function ringsSummary(saved: RingsSettings): string {
    if (saved.rings.length < MIN_RINGS) return NOT_SET_SUMMARY;
    const names = new Map(saved.groups.map(g => [g.id, g.name]));
    const parts = saved.rings.map((ring, index) => {
        const shown = ring.groupIds.map(id => names.get(id)).filter((n): n is string => !!n);
        if (shown.length > 0) return `${ring.name} (${shown.join(', ')})`;
        return index === saved.rings.length - 1 ? LAST_RING_NAME : ring.name;
    });
    const soaks = Array.from(new Set(saved.rings.map(r => r.soakHours))).sort((a, b) => a - b);
    const soak = soaks.length === 1 ? `${soaks[0]}-hour soak` : `${soaks[0]} to ${soaks[soaks.length - 1]}-hour soaks`;
    return `${parts.join(' -> ')} · ${soak}`;
}
