/**
 * SOC console, case work: the standard steps are added, a skipped task needs a reason, alert indicators become
 * evidence and evidence is excluded with a reason (never deleted); without edit rights nothing can be changed.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { CaseWork } from '../../components/security/soc/CaseWork';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const calls = (method: string, path: string) =>
    authFetch.mock.calls.filter(([url, init]) => (init?.method ?? 'GET') === method && String(url).startsWith(path));

let canEdit = true;
const work = () => ({
    caseId: 'case-1', canEdit,
    tasks: [{ id: 'task-1', title: 'Remove the cause', status: 'todo', createdBy: 'ana', createdAt: '2026-11-18T08:00:00Z' }],
    evidence: [{ id: 'ev-1', kind: 'file', value: 'evil.exe', size: 2048, sha256: 'ab'.repeat(32), addedBy: 'ana', addedAt: '2026-11-18T08:00:00Z',
                 excluded: false, custody: [{ action: 'added', by: 'ana', at: '2026-11-18T08:00:00Z' }] }],
    standardSteps: ['Confirm the alerts are real, not a false positive', 'Remove the cause'],
    alertIndicators: [{ indicatorKind: 'ip', key: '45.33.32.156', value: '45.33.32.156', alertIds: ['a1'] }],
});

function route(url: string, init?: RequestInit) {
    if (new URL(url, 'http://x').pathname.endsWith('/work')) return ok(work());
    if (init?.method === 'PATCH') return ok({ id: 'x', ...JSON.parse(String(init.body)) });
    return ok({ added: 1 });
}

beforeEach(() => { canEdit = true; authFetch.mockReset(); authFetch.mockImplementation(async (url: string, init?: RequestInit) => route(url, init)); });

describe('Case work', () => {
    it('adds the standard steps, asks why a task is skipped and keeps excluded evidence', async () => {
        render(<CaseWork caseId="case-1" />);
        fireEvent.click(await screen.findByRole('button', { name: 'Add the standard steps (2)' }));
        await waitFor(() => expect(calls('POST', '/api/security/soc/cases/case-1/tasks/standard')).toHaveLength(1));

        fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
        const skip = screen.getByRole('button', { name: 'Skip task' });
        expect((skip as HTMLButtonElement).disabled).toBe(true);
        fireEvent.change(screen.getByPlaceholderText('Why it does not apply'), { target: { value: 'host rebuilt' } });
        fireEvent.click(skip);
        await waitFor(() => expect(calls('PATCH', '/api/security/soc/cases/case-1/tasks/task-1')).toHaveLength(1));
        expect(JSON.parse(String(calls('PATCH', '/api/security/soc/cases/case-1/tasks/task-1')[0][1].body))).toEqual({ status: 'skipped', note: 'host rebuilt' });

        fireEvent.click(screen.getByRole('button', { name: 'Add 1 indicator from the alerts' }));
        await waitFor(() => expect(calls('POST', '/api/security/soc/cases/case-1/evidence/from-alerts')).toHaveLength(1));

        expect(screen.getByText(`SHA-256 ${'ab'.repeat(32)}`)).toBeTruthy();
        fireEvent.click(screen.getByRole('button', { name: 'Exclude' }));
        fireEvent.change(screen.getByPlaceholderText('Why it does not matter'), { target: { value: 'not related' } });
        fireEvent.click(screen.getAllByRole('button', { name: 'Exclude' }).at(-1)!);
        await waitFor(() => expect(calls('PATCH', '/api/security/soc/cases/case-1/evidence/ev-1')).toHaveLength(1));
        expect(JSON.parse(String(calls('PATCH', '/api/security/soc/cases/case-1/evidence/ev-1')[0][1].body))).toEqual({ excluded: true, reason: 'not related' });
        expect(calls('DELETE', '/api/security/soc/cases')).toHaveLength(0);
    });

    it('offers no changes without edit rights but still allows the download', async () => {
        canEdit = false;
        render(<CaseWork caseId="case-1" />);
        expect(await screen.findByText('Remove the cause')).toBeTruthy();
        expect(screen.queryByRole('button', { name: /standard steps/ })).toBeNull();
        expect(screen.queryByRole('button', { name: 'Exclude' })).toBeNull();
        expect(screen.queryByPlaceholderText('Add a task')).toBeNull();
        expect((screen.getByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
        expect(screen.getByRole('button', { name: 'Download evil.exe' })).toBeTruthy();
    });
});
