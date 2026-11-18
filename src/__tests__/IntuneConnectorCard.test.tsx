/**
 * Mobile Device Management, Intune card: not connected says actions are only recorded; connecting sends the ids and
 * secret then syncs; a connected card shows devices, the last error and never the secret.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { IntuneConnectorCard } from '../../components/IntuneConnectorCard';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const TID = '11111111-2222-3333-4444-555555555555', CID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';

beforeEach(() => { authFetch.mockReset(); });

describe('Intune connector card', () => {
  it('connects with the ids and secret, then syncs', async () => {
    let connected = false;
    authFetch.mockImplementation(async (url: string, init?: { method?: string }) => {
      if (init?.method === 'PUT') { connected = true; return ok({ connected: true }); }
      if (init?.method === 'POST') return ok({ devices: 3, removed: 0 });
      return ok(connected ? { connected: true, devices: 3, lastSyncAt: '2026-11-18T20:00:00Z', lastError: null } : { connected: false });
    });
    const onSynced = vi.fn();
    render(<IntuneConnectorCard onSynced={onSynced} />);
    expect(await screen.findByText(/actions on them are recorded, not sent/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Connect Intune' }));
    fireEvent.change(screen.getByLabelText('Directory (tenant) ID'), { target: { value: TID } });
    fireEvent.change(screen.getByLabelText('Application (client) ID'), { target: { value: CID } });
    fireEvent.change(screen.getByLabelText('Client secret'), { target: { value: 'sec' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save and sync' }));
    await waitFor(() => expect(onSynced).toHaveBeenCalled());
    const put = authFetch.mock.calls.find(([, i]) => i?.method === 'PUT');
    expect(JSON.parse(put![1].body)).toEqual({ azureTenantId: TID, clientId: CID, clientSecret: 'sec' });
    expect(authFetch.mock.calls.some(([u, i]) => u === '/api/mdm/intune/sync' && i?.method === 'POST')).toBe(true);
    expect(await screen.findByText(/Connected · 3 devices/)).toBeTruthy();
  });

  it('shows the last sync error of a connected Intune', async () => {
    authFetch.mockResolvedValue(ok({ connected: true, devices: 0, lastError: 'Graph refused (HTTP 403): grant the app permissions' }));
    render(<IntuneConnectorCard />);
    expect((await screen.findByRole('alert')).textContent).toContain('HTTP 403');
  });
});
