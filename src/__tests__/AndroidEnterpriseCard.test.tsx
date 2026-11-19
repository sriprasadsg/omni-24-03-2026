/**
 * Mobile Device Management, Android Enterprise card: connecting sends the key and enterprise then syncs, a connected
 * enterprise offers an enrollment QR code and work-profile link, and Google's sign-up return is completed on load.
 *
 * Value: protects=the key is sent once and the card never shows it, an enrollment code shows its QR and link, the
 * enterprise token from Google's return address is posted and removed from the address bar; fails_when=the sign-up
 * return is ignored, or the token stays in the address bar; no_claim=the server calls (test_android_mdm.py).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { AndroidEnterpriseCard } from '../../components/AndroidEnterpriseCard';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const ENT = 'enterprises/LC01abcdef';
const CONNECTED = { connected: true, enterprise: ENT, enterpriseName: 'Contoso', devices: 2, lastSyncAt: '2026-11-19T10:00:00Z' };

beforeEach(() => { authFetch.mockReset(); });
afterEach(() => { window.history.replaceState(null, '', '/'); });

describe('Android Enterprise card', () => {
  it('connects with the key and enterprise, then syncs, and never shows the key', async () => {
    let connected = false;
    authFetch.mockImplementation(async (url: string, init?: { method?: string }) => {
      if (init?.method === 'PUT') { connected = true; return ok({ connected: true }); }
      if (init?.method === 'POST') return ok({ devices: 2, removed: 0 });
      return ok(connected ? CONNECTED : { connected: false });
    });
    render(<AndroidEnterpriseCard />);
    fireEvent.click(await screen.findByRole('button', { name: 'Connect Android' }));
    fireEvent.change(screen.getByLabelText('Service account key (JSON)'), { target: { value: '{"type":"service_account"}' } });
    fireEvent.change(screen.getByLabelText('Enterprise'), { target: { value: ENT } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText(/Connected · Contoso · 2 devices/)).toBeTruthy();
    const put = authFetch.mock.calls.find(([, i]) => i?.method === 'PUT');
    expect(JSON.parse(put![1].body)).toEqual({ serviceAccountKey: '{"type":"service_account"}', enterprise: ENT });
    expect(authFetch.mock.calls.some(([u, i]) => u === '/api/mdm/android/sync' && i?.method === 'POST')).toBe(true);
    expect(screen.queryByText(/service_account/)).toBeNull();
  });

  it('shows an enrollment QR code and work-profile link', async () => {
    authFetch.mockImplementation(async (url: string) => url.endsWith('/enrollment-token')
      ? ok({ value: 'ABCDEFGHIJ', link: 'https://enterprise.google.com/android/enroll?et=ABCDEFGHIJ', qrPng: 'iVBORw0', hours: 24 })
      : ok(CONNECTED));
    render(<AndroidEnterpriseCard />);
    fireEvent.click(await screen.findByRole('button', { name: 'Enroll a device' }));
    expect(await screen.findByAltText('Android enrollment QR code')).toBeTruthy();
    expect(screen.getByRole('link', { name: /enroll\?et=ABCDEFGHIJ/ })).toBeTruthy();
    expect(screen.getByText(/valid for 24 hours/)).toBeTruthy();
  });

  it("completes Google's sign-up from the return address and clears the token", async () => {
    window.history.replaceState(null, '', '/?enterpriseToken=EnterpriseToken_0123');
    authFetch.mockImplementation(async () => ok(CONNECTED));
    render(<AndroidEnterpriseCard />);
    await waitFor(() => expect(authFetch.mock.calls.some(([u]) => u === '/api/mdm/android/enterprise')).toBe(true));
    const post = authFetch.mock.calls.find(([u]) => u === '/api/mdm/android/enterprise');
    expect(JSON.parse(post![1].body)).toEqual({ enterpriseToken: 'EnterpriseToken_0123' });
    expect(window.location.search).toBe('');
  });
});
