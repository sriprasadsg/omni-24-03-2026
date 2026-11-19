/**
 * Mobile Device Management, Jamf Pro card (Apple devices): connecting sends the address, client ID and secret then
 * syncs; a connected card shows the address, devices and the last error, and a blank secret keeps the saved one.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { JamfConnectorCard } from '../../components/JamfConnectorCard';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const puts = () => authFetch.mock.calls.filter(([, i]) => i?.method === 'PUT');
const CLIENT = '0f6c3a52-8d1e-4b7a-9c2d-5e4f3a2b1c0d';

beforeEach(() => { authFetch.mockReset(); });

describe('Jamf Pro connector card', () => {
  it('connects with the address, client ID and secret, then syncs and shows the devices', async () => {
    let connected = false;
    authFetch.mockImplementation(async (url: string, init?: { method?: string }) => {
      if (init?.method === 'PUT') { connected = true; return ok({ connected: true }); }
      if (init?.method === 'POST') return ok({ devices: 3, removed: 0 });
      return ok(connected ? { connected: true, baseUrl: 'https://acme.jamfcloud.com', clientId: CLIENT, devices: 3, lastSyncAt: '2026-11-19T10:00:00Z', lastError: null } : { connected: false });
    });
    const onSynced = vi.fn();
    render(<JamfConnectorCard onSynced={onSynced} />);
    expect(await screen.findByText(/manage Macs, iPhones and iPads without Intune/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Connect Jamf Pro' }));
    expect((screen.getByRole('button', { name: 'Save and sync' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Jamf Pro address'), { target: { value: ' https://acme.jamfcloud.com ' } });
    fireEvent.change(screen.getByLabelText('Client ID'), { target: { value: CLIENT } });
    fireEvent.change(screen.getByLabelText('Client secret'), { target: { value: 'sekret-0123456789' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save and sync' }));
    await waitFor(() => expect(onSynced).toHaveBeenCalled());
    expect(JSON.parse(puts()[0][1].body)).toEqual({ baseUrl: 'https://acme.jamfcloud.com', clientId: CLIENT, clientSecret: 'sekret-0123456789' });
    expect(authFetch.mock.calls.some(([u, i]) => u === '/api/mdm/jamf/sync' && i?.method === 'POST')).toBe(true);
    expect(await screen.findByText(/Connected to https:\/\/acme\.jamfcloud\.com · 3 devices/)).toBeTruthy();
  });

  it('shows the last error and keeps the saved secret when the field is left blank', async () => {
    authFetch.mockImplementation(async (url: string, init?: { method?: string }) =>
      (init?.method ? ok({ connected: true }) : ok({ connected: true, baseUrl: 'https://acme.jamfcloud.com', clientId: CLIENT, devices: 0, lastError: 'Jamf Pro refused (HTTP 403): give the API client\'s role Read Computers' })));
    render(<JamfConnectorCard />);
    expect((await screen.findByRole('alert')).textContent).toMatch(/Jamf Pro refused \(HTTP 403\)/);
    fireEvent.click(screen.getByRole('button', { name: 'Change' }));
    expect(screen.getByLabelText('Client secret').getAttribute('placeholder')).toMatch(/keep the saved secret/);
    fireEvent.click(screen.getByRole('button', { name: 'Save and sync' }));
    await waitFor(() => expect(puts()).toHaveLength(1));
    expect(JSON.parse(puts()[0][1].body)).toEqual({ baseUrl: 'https://acme.jamfcloud.com', clientId: CLIENT });
  });
});
