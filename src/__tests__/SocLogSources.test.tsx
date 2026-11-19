/**
 * SOC console, Cloud log sources: each source shows whether it is connected, its last success and events, and a
 * failed pull's reason; connecting sends only that provider's fields (a blank secret keeps the saved one); Pull now
 * reports new events and rule hits.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));
const showToast = vi.fn();
vi.mock('../../utils/toast', () => ({ showToast: (...a: unknown[]) => showToast(...a) }));

import { LogSourcesPanel } from '../../components/security/soc/LogSourcesPanel';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const sent = (method: string) => authFetch.mock.calls.filter(([, init]) => (init?.method ?? 'GET') === method);
const list = {
    entra: { name: 'Microsoft Entra ID', connected: true, enabled: true, azureTenantId: '11111111-2222-3333-4444-555555555555', clientId: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
        lastSuccessAt: '2026-11-19T11:00:00Z', lastRunAt: '2026-11-19T11:05:00Z', lastError: 'Microsoft Graph answered HTTP 403: the app lacks a permission or licence', totalEvents: 42 },
    m365: { name: 'Microsoft 365', connected: false },
    aws: { name: 'AWS CloudTrail', connected: false },
    google: { name: 'Google Workspace', connected: false },
};

describe('LogSourcesPanel', () => {
    beforeEach(() => { authFetch.mockReset(); showToast.mockReset(); });

    it('shows each source, a failed pull, and pulls now', async () => {
        authFetch.mockImplementation(async (url: string) => (url.endsWith('/pull') ? ok({ ok: true, read: 9, new: 7, hits: 2 }) : ok(list)));
        render(<LogSourcesPanel />);
        expect(await screen.findByText(/42 events/)).toBeTruthy();
        expect(screen.getAllByText('Not connected')).toHaveLength(3);
        expect(screen.getByRole('status').textContent).toMatch(/failed: Microsoft Graph answered HTTP 403/);
        fireEvent.click(screen.getByRole('button', { name: 'Pull now' }));
        await waitFor(() => expect(showToast).toHaveBeenCalledWith('Microsoft Entra ID: 7 new events, 2 rule hits', 'success'));
        expect(sent('POST')[0][0]).toBe('/api/security/soc/log-sources/entra/pull');
    });

    it('connects AWS with its own fields and keeps a saved secret when the field is blank', async () => {
        authFetch.mockImplementation(async (url: string, init?: { method?: string }) =>
            (init?.method === 'PUT' ? ok({ ...list.aws, connected: true, enabled: true, accessKeyId: 'AKIAIOSFODNN7EXAMPLE', regions: ['eu-west-1', 'us-east-1'] }) : ok(list)));
        render(<LogSourcesPanel />);
        const connect = await screen.findAllByRole('button', { name: 'Connect' });
        fireEvent.click(connect[1]);  // m365, entra (Edit), aws: the second Connect
        fireEvent.change(screen.getByLabelText('Access key id'), { target: { value: ' AKIAIOSFODNN7EXAMPLE ' } });
        fireEvent.change(screen.getByLabelText('Secret access key'), { target: { value: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY' } });
        fireEvent.change(screen.getByLabelText('Regions (comma-separated)'), { target: { value: 'eu-west-1, us-east-1,' } });
        fireEvent.click(screen.getByRole('button', { name: 'Save AWS CloudTrail' }));
        await waitFor(() => expect(sent('PUT')).toHaveLength(1));
        expect(sent('PUT')[0][0]).toBe('/api/security/soc/log-sources/aws');
        expect(JSON.parse(sent('PUT')[0][1].body)).toEqual({ accessKeyId: 'AKIAIOSFODNN7EXAMPLE', regions: ['eu-west-1', 'us-east-1'], enabled: true,
            secret: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY' });
        fireEvent.click(screen.getAllByRole('button', { name: 'Edit' })[0]);  // entra (AWS now shows Edit too)
        expect(screen.getByLabelText('Client secret').getAttribute('placeholder')).toMatch(/leave blank to keep/);
        fireEvent.click(screen.getByRole('button', { name: 'Save Microsoft Entra ID' }));
        await waitFor(() => expect(sent('PUT')).toHaveLength(2));
        const entra = JSON.parse(sent('PUT')[1][1].body);
        expect(entra).toMatchObject({ azureTenantId: list.entra.azureTenantId, clientId: list.entra.clientId });
        expect('secret' in entra).toBe(false);
    });

    it('lists authentik when the platform has it, sends its address and token, and still lists the cloud four without it', async () => {
        const withAk = { ...list, authentik: { name: 'authentik', connected: false } };
        authFetch.mockImplementation(async (url: string, init?: { method?: string }) =>
            (init?.method === 'PUT' ? ok({ name: 'authentik', connected: true, enabled: true, baseUrl: 'http://127.0.0.1:9000' }) : ok(withAk)));
        const { unmount } = render(<LogSourcesPanel />);
        expect(await screen.findByText('authentik')).toBeTruthy();
        const connect = screen.getAllByRole('button', { name: 'Connect' });
        fireEvent.click(connect[connect.length - 1]);
        fireEvent.change(screen.getByLabelText('authentik address'), { target: { value: ' http://127.0.0.1:9000 ' } });
        fireEvent.change(screen.getByLabelText('API token'), { target: { value: 'Ak'.repeat(30) } });
        fireEvent.click(screen.getByRole('button', { name: 'Save authentik' }));
        await waitFor(() => expect(sent('PUT')).toHaveLength(1));
        expect(sent('PUT')[0][0]).toBe('/api/security/soc/log-sources/authentik');
        expect(JSON.parse(sent('PUT')[0][1].body)).toEqual({ baseUrl: 'http://127.0.0.1:9000', enabled: true, secret: 'Ak'.repeat(30) });
        unmount();
        authFetch.mockReset();
        authFetch.mockImplementation(async () => ok(list));
        render(<LogSourcesPanel />);
        expect(await screen.findByText('Google Workspace')).toBeTruthy();
        expect(screen.queryByText('authentik')).toBeNull();
    });
});
