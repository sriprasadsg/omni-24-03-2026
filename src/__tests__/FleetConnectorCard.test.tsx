/**
 * Mobile Device Management, Fleet card (open source): connecting sends the address and token then syncs; a connected
 * card shows the address, devices and the last error, and a blank token keeps the saved one.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { FleetConnectorCard } from '../../components/FleetConnectorCard';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const puts = () => authFetch.mock.calls.filter(([, i]) => i?.method === 'PUT');

beforeEach(() => { authFetch.mockReset(); });

describe('Fleet connector card', () => {
  it('connects with the address and token, then syncs and shows the hosts', async () => {
    let connected = false;
    authFetch.mockImplementation(async (url: string, init?: { method?: string }) => {
      if (init?.method === 'PUT') { connected = true; return ok({ connected: true }); }
      if (init?.method === 'POST') return ok({ devices: 1, removed: 0 });
      return ok(connected ? { connected: true, baseUrl: 'https://localhost:8412', devices: 1, lastSyncAt: '2026-11-19T10:00:00Z', lastError: null } : { connected: false });
    });
    const onSynced = vi.fn();
    render(<FleetConnectorCard onSynced={onSynced} />);
    expect(await screen.findByText(/Fleet is open-source device management/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Connect Fleet' }));
    fireEvent.change(screen.getByLabelText('Fleet address'), { target: { value: ' https://localhost:8412 ' } });
    fireEvent.change(screen.getByLabelText('API token'), { target: { value: 'tok123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save and sync' }));
    await waitFor(() => expect(onSynced).toHaveBeenCalled());
    expect(JSON.parse(puts()[0][1].body)).toEqual({ baseUrl: 'https://localhost:8412', apiToken: 'tok123' });
    expect(authFetch.mock.calls.some(([u, i]) => u === '/api/mdm/fleet/sync' && i?.method === 'POST')).toBe(true);
    expect(await screen.findByText(/Connected to https:\/\/localhost:8412 · 1 devices/)).toBeTruthy();
  });

  it('shows the last error and keeps the saved token when the field is left blank', async () => {
    authFetch.mockImplementation(async (url: string, init?: { method?: string }) =>
      (init?.method ? ok({ connected: true }) : ok({ connected: true, baseUrl: 'https://fleet.example.com', devices: 0, lastError: 'Fleet refused the API token (HTTP 401)' })));
    render(<FleetConnectorCard />);
    expect((await screen.findByRole('alert')).textContent).toMatch(/Fleet refused the API token \(HTTP 401\)/);
    fireEvent.click(screen.getByRole('button', { name: 'Change' }));
    expect(screen.getByLabelText('API token').getAttribute('placeholder')).toMatch(/keep the saved token/);
    fireEvent.click(screen.getByRole('button', { name: 'Save and sync' }));
    await waitFor(() => expect(puts()).toHaveLength(1));
    expect(JSON.parse(puts()[0][1].body)).toEqual({ baseUrl: 'https://fleet.example.com' });
  });
});
