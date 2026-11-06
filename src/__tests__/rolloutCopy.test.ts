/**
 * Staged patch rollouts, plan 84-02: the shared UI copy module.
 *
 * Value: protects=PTCH-04: the assurance line is the exact UI-SPEC sentence, every chip map entry names its
 * label, tone and an icon that exists in components/icons.tsx, a count never reads "1 computers", and the
 * state maps cover every value the payload types allow; fails_when=a chip entry loses its tone or icon, an icon
 * name drifts from icons.tsx, or the assurance line changes; no_claim=the components that render the chips
 * (84-14 and later) or the server sentences (backend rollout/messages.py).
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
    ASSURANCE_LINE, HOST_STATE_CHIP, LINK_LABELS, RING_STATE_CHIP, ROLLOUT_STATUS_CHIP, SIGNAL_CHIP, SIMULATION_CHIP,
    plural,
} from '../../components/patchRollouts/rolloutCopy';
import type { ChipSpec } from '../../components/patchRollouts/rolloutCopy';

const ROOT = resolve(__dirname, '../..');
const ICONS = readFileSync(resolve(ROOT, 'components/icons.tsx'), 'utf-8');
const TONES = ['amber', 'blue', 'green', 'red', 'neutral', 'outline', 'dashed'];

const MAPS: Record<string, Record<string, ChipSpec>> = {
    ROLLOUT_STATUS_CHIP, RING_STATE_CHIP, HOST_STATE_CHIP, SIGNAL_CHIP,
};

describe('rollout copy', () => {
    it('the assurance line is the exact UI-SPEC sentence', () => {
        expect(ASSURANCE_LINE).toBe(
            'A rollout halts on failure; reverts where supported. Nothing is installed outside your maintenance window.');
        expect(ASSURANCE_LINE).toContain('reverts where supported');
    });

    it('plural(1, ...) is singular and anything else is plural', () => {
        expect(plural(1, 'computer', 'computers')).toBe('1 computer');
        expect(plural(0, 'computer', 'computers')).toBe('0 computers');
        expect(plural(3, 'patch', 'patches')).toBe('3 patches');
    });

    for (const [name, map] of Object.entries(MAPS)) {
        it(`${name}: every entry has a label, a known tone and an icon that exists`, () => {
            expect(Object.keys(map).length).toBeGreaterThan(0);
            for (const [key, chip] of Object.entries(map)) {
                expect(chip.label, `${name}.${key}`).not.toBe('');
                expect(TONES, `${name}.${key}`).toContain(chip.tone);
                expect(ICONS, `${name}.${key}`).toMatch(new RegExp(`export const ${chip.icon}\\b`));
            }
        });
    }

    it('the state maps cover the values the payload types allow', () => {
        expect(Object.keys(ROLLOUT_STATUS_CHIP).sort()).toEqual(
            ['cancelled', 'completed', 'halted', 'running', 'waiting_for_approval', 'waiting_for_window']);
        expect(Object.keys(RING_STATE_CHIP).sort()).toEqual(
            ['cancelled', 'checking_health', 'halted', 'installing', 'not_started', 'passed', 'restarting', 'reverted',
                'soaking', 'waiting_for_approval', 'waiting_for_window']);
        expect(Object.keys(HOST_STATE_CHIP).sort()).toEqual(
            ['failed', 'healthy', 'installed', 'installing', 'left_out', 'not_reached', 'not_reverted', 'restarting',
                'reverted', 'reverting', 'waiting', 'would_install', 'would_restart']);
        expect(Object.keys(SIGNAL_CHIP).sort()).toEqual(
            ['agent_only', 'failed', 'no_data', 'not_checked', 'passed', 'waiting']);
    });

    it('follows the UI-SPEC colour table', () => {
        expect(ROLLOUT_STATUS_CHIP.running).toMatchObject({ tone: 'blue', icon: 'RefreshCwIcon' });
        expect(ROLLOUT_STATUS_CHIP.halted).toMatchObject({ tone: 'red', icon: 'AlertOctagonIcon' });
        expect(RING_STATE_CHIP.halted).toMatchObject({ tone: 'red', icon: 'XCircleIcon' });
        expect(RING_STATE_CHIP.passed.tone).toBe('green');
        expect(HOST_STATE_CHIP.reverted).toMatchObject({ tone: 'neutral', icon: 'RefreshCcwIcon' });
        expect(HOST_STATE_CHIP.not_reverted).toMatchObject({ tone: 'outline', icon: 'ShieldLockIcon' });
        expect(HOST_STATE_CHIP.left_out).toMatchObject({ tone: 'outline', icon: 'InfoIcon' });
        expect(SIMULATION_CHIP).toMatchObject({ label: 'Simulation', tone: 'dashed', icon: 'FlaskConicalIcon' });
    });

    it('DEV-2: a computer whose agent cannot report services is Not checked, never Passed', () => {
        expect(SIGNAL_CHIP.not_checked).toEqual({ label: 'Not checked', tone: 'outline', icon: 'InfoIcon' });
        expect(SIGNAL_CHIP.no_data).toMatchObject({ label: 'No data', tone: 'red' });
    });

    it('link labels are the UI-SPEC ones', () => {
        expect(LINK_LABELS.maintenance).toBe('Open maintenance windows');
        expect(LINK_LABELS.rings).toBe('Open rollout rings');
        expect(LINK_LABELS.agentGroups).toBe('Open agent groups');
        expect(LINK_LABELS.reviewDecisions).toBe('Review in Needs your decision');
    });
});
