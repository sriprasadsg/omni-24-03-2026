/**
 * SOC console, ATT&CK coverage: detected / rule-only / not covered are told apart with words and icons, the SIEM
 * state is explained, the console's range is used and a table view holds the same techniques.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { CoverageTab } from '../../components/security/soc/CoverageTab';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const calls = (method: string, path: string) =>
    authFetch.mock.calls.filter(([url, init]) => (init?.method ?? 'GET') === method && String(url).startsWith(path));

const tech = (id: string, name: string, level: string, extra: Record<string, unknown> = {}) => ({
    id, name, level, seen: 0, active: 0, ruleCount: 0, subTechniques: [], detections: [], rules: [], ...extra,
});
const coverage = {
    generatedAt: '2026-11-18T12:00:00Z', range: '7d', endpoints: 2, siemLogs: 0, siemLogDays: 7,
    tactics: [
        { id: 'TA0003', name: 'Persistence', techniques: [
            tech('T1053', 'Scheduled Task/Job', 'detected', { seen: 4, active: 1, subTechniques: ['T1053.005'],
                detections: [{ type: 'persistence_mechanism', label: 'Suspicious persistence', check: 'persistence_detection', technique: 'T1053.005', what: 'Windows scheduled tasks', endpoints: 2 }] }),
            tech('T1098', 'Account Manipulation', 'rule', { ruleCount: 1, rules: [{ name: 'New credential on a service principal', technique: 'T1098.001', library: true }] }),
        ] },
        { id: 'TA0006', name: 'Credential Access', techniques: [tech('T1110', 'Brute Force', 'none')] },
    ],
    totals: { techniques: 3, detected: 1, ruleOnly: 1, none: 1, seen: 1 },
    checks: [{ type: 'shadow_ai_process', label: 'Unapproved AI process', check: 'shadow_ai', endpoints: 1, techniques: [] }],
};

beforeEach(() => { authFetch.mockReset(); authFetch.mockImplementation(async () => ok(coverage)); });

describe('ATT&CK coverage', () => {
    it('separates detected, rule-only and uncovered techniques and explains each', async () => {
        render(<CoverageTab range="7d" rangeLabel="7 days" />);
        expect(await screen.findByText(/techniques are detected on your 2 endpoints/)).toBeTruthy();
        expect(calls('GET', '/api/security/soc/mitre-coverage?range=7d')).toHaveLength(1);
        const legend = screen.getByRole('list', { name: 'Legend' });
        expect(within(legend).getByText('Detected on your endpoints')).toBeTruthy();
        expect(within(legend).getByText('SIEM rule written, not covered')).toBeTruthy();
        expect(screen.getByRole('group', { name: 'Persistence: 1 of 2 detected' })).toBeTruthy();

        fireEvent.click(screen.getByRole('button', { name: 'T1053 Scheduled Task/Job: Detected on your endpoints, 4 alerts' }));
        const detail = screen.getByRole('complementary', { name: 'Technique details' });
        expect(within(detail).getByText(/Windows scheduled tasks/)).toBeTruthy();
        expect(within(detail).getByText('Runs on 2 endpoints')).toBeTruthy();
        expect(within(detail).getByText('4 alerts, 1 still active')).toBeTruthy();

        fireEvent.click(screen.getByRole('button', { name: 'T1098 Account Manipulation: SIEM rule written, not covered' }));
        expect(within(detail).getByText(/no logs from you in the last 7 days, so these rules cannot fire yet/)).toBeTruthy();
        expect(screen.getByText(/not an ATT&CK technique/)).toBeTruthy();

        fireEvent.click(screen.getByRole('button', { name: 'Table' }));
        const table = screen.getByRole('table');
        expect(within(table).getAllByRole('row')).toHaveLength(4);
        expect(within(table).getByText('Not covered')).toBeTruthy();
    });
});
