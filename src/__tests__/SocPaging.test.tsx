/**
 * SOC console, Paging: the saved provider is shown without its key, a blank key keeps the saved one, on-call hours
 * are sent as a weekly window, the test page says how to resolve it, and recent pages list why and how they ended.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));
const showToast = vi.fn();
vi.mock('../../utils/toast', () => ({ showToast: (...a: unknown[]) => showToast(...a) }));

import { PagingPanel, type PagingConfig } from '../../components/security/soc/PagingPanel';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const bad = (status: number, detail: string) => ({ ok: false, status, json: async () => ({ detail }) });
const sent = (method: string) => authFetch.mock.calls.filter(([, init]) => (init?.method ?? 'GET') === method);

const saved: PagingConfig = {
    configured: true, provider: 'pagerduty', enabled: true, minSeverity: 'critical', breachSeverity: 'high', pageBreaches: true,
    region: 'us', onCall: { always: true }, lastResult: { at: '2026-11-19T09:00:00Z', ok: false, error: 'PagerDuty answered HTTP 401: the key was refused' },
    recentPages: [
        { id: 'p1', alertId: 'a1', title: 'mimikatz.exe started', reason: 'new', status: 'resolved', sentAt: '2026-11-19T08:00:00Z' },
        { id: 'p2', alertId: 'a2', title: 'Brute force', reason: 'ack_breach', status: 'failed', sentAt: '2026-11-19T09:00:00Z', error: 'PagerDuty answered HTTP 401: the key was refused' },
    ],
};

describe('PagingPanel', () => {
    beforeEach(() => { authFetch.mockReset(); showToast.mockReset(); });

    it('shows the saved provider, keeps the key when the field is left blank, and lists recent pages', async () => {
        authFetch.mockImplementation(async (url: string, init?: { method?: string; body?: string }) =>
            (init?.method === 'PUT' ? ok({ ...saved, minSeverity: 'high' }) : ok(saved)));
        render(<PagingPanel />);
        const key = await screen.findByLabelText(/Routing key/);
        expect((key as HTMLInputElement).value).toBe('');
        expect(key.getAttribute('placeholder')).toMatch(/leave blank to keep/);
        expect(screen.getByText('Not acknowledged in time')).toBeTruthy();
        expect(screen.getByText(/Failed: PagerDuty answered HTTP 401/)).toBeTruthy();
        expect(screen.getByRole('status').textContent).toMatch(/the key was refused/);
        fireEvent.change(screen.getByLabelText('Page new alerts that are'), { target: { value: 'high' } });
        fireEvent.click(screen.getByRole('button', { name: 'Save paging' }));
        await waitFor(() => expect(sent('PUT')).toHaveLength(1));
        const body = JSON.parse(sent('PUT')[0][1].body);
        expect(body).toMatchObject({ provider: 'pagerduty', minSeverity: 'high', onCall: { always: true } });
        expect('secret' in body).toBe(false);
    });

    it('sends a new provider with its webhook and on-call hours as a weekly window', async () => {
        authFetch.mockImplementation(async (url: string, init?: { method?: string }) =>
            (init?.method === 'PUT' ? bad(400, 'Webhook URL refused: private address') : ok({ configured: false })));
        render(<PagingPanel />);
        fireEvent.change(await screen.findByLabelText('Send pages to'), { target: { value: 'teams' } });
        fireEvent.change(screen.getByLabelText('Workflow webhook URL'), { target: { value: ' https://x.webhook.office.com/a ' } });
        fireEvent.click(screen.getByLabelText('Any time'));
        fireEvent.click(screen.getByLabelText('Fri'));
        fireEvent.change(screen.getByLabelText('On-call from'), { target: { value: '22:00' } });
        fireEvent.change(screen.getByLabelText('On-call until'), { target: { value: '06:00' } });
        fireEvent.change(screen.getByLabelText('Time zone'), { target: { value: 'Europe/London' } });
        expect(screen.queryByRole('button', { name: 'Send test page' })).toBeNull();
        fireEvent.click(screen.getByRole('button', { name: 'Save paging' }));
        await waitFor(() => expect(showToast).toHaveBeenCalledWith('Webhook URL refused: private address', 'error'));
        expect(JSON.parse(sent('PUT')[0][1].body)).toMatchObject({ provider: 'teams', secret: 'https://x.webhook.office.com/a',
            onCall: { always: false, timezone: 'Europe/London', days: [0, 1, 2, 3], start: '22:00', end: '06:00' } });
    });

    it('says how to resolve a test page, and why one was not sent', async () => {
        let answer = { alertId: 'a9', paged: true };
        authFetch.mockImplementation(async (url: string) => (url.endsWith('/test') ? ok(answer) : ok(saved)));
        render(<PagingPanel />);
        fireEvent.click(await screen.findByRole('button', { name: 'Send test page' }));
        await waitFor(() => expect(showToast).toHaveBeenCalledWith(expect.stringMatching(/Close the "Paging test" alert/), 'success'));
        answer = { alertId: 'a10', paged: false, error: 'PagerDuty answered HTTP 401: the key was refused' } as typeof answer;
        fireEvent.click(screen.getByRole('button', { name: 'Send test page' }));
        await waitFor(() => expect(showToast).toHaveBeenCalledWith('Test page not sent: PagerDuty answered HTTP 401: the key was refused', 'error'));
    });
});
