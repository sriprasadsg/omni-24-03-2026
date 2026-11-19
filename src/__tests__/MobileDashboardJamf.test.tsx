/**
 * Mobile screen, Jamf Pro devices: locking a Mac asks for the 6-digit PIN Jamf needs and sends it, wiping asks for
 * the typed device name (and a Mac also for the PIN), and an iPhone lock needs no PIN. Connector devices carry no
 * udid, so the table shows the serial number instead of crashing.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import MobileDashboard from '../../components/MobileDashboard';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const DEVICES = [
  { id: 'mdm-mac', name: 'mac-01', source: 'jamf', serial_number: 'C02X1', platform: 'macos', os_version: '15.6', enrollment_status: 'enrolled', compliance_status: 'unknown' },
  { id: 'mdm-phone', name: 'iphone-01', source: 'jamf', platform: 'ios', os_version: '18.6', enrollment_status: 'enrolled', compliance_status: 'unknown' },
];
const actions = () => authFetch.mock.calls.filter(([u]) => String(u).endsWith('/action')).map(([u, i]) => [u, JSON.parse(i.body)]);
const row = async (name: string) => (await screen.findByText(name)).closest('tr') as HTMLElement;

beforeEach(() => {
  authFetch.mockReset();
  authFetch.mockImplementation(async (url: string) => {
    if (url.endsWith('/action')) return ok({ status: 'sent' });
    if (url === '/api/mdm/devices') return ok({ devices: DEVICES });
    if (url === '/api/mdm/policies') return ok({ policies: [] });
    if (url === '/api/mdm/summary') return ok({ total: 2, enrolled: 2, non_compliant: 0, ios: 1, android: 0, other: 1 });
    return ok({ connected: false });
  });
});
afterEach(() => { vi.restoreAllMocks(); });

describe('Mobile screen, Jamf Pro actions', () => {
  it('a Mac lock sends the PIN typed and a cancelled PIN sends nothing', async () => {
    const prompt = vi.spyOn(window, 'prompt').mockReturnValueOnce(null).mockReturnValueOnce(' 482916 ');
    const confirm = vi.spyOn(window, 'confirm');
    render(<MobileDashboard />);
    const mac = await row('mac-01');
    expect(within(mac).getByText('C02X1')).toBeTruthy();
    fireEvent.click(within(mac).getByRole('button', { name: 'Lock' }));
    await waitFor(() => expect(prompt).toHaveBeenCalledTimes(1));
    expect(actions()).toHaveLength(0);
    fireEvent.click(within(mac).getByRole('button', { name: 'Lock' }));
    await waitFor(() => expect(actions()).toHaveLength(1));
    expect(actions()[0]).toEqual(['/api/mdm/devices/mdm-mac/action', { action: 'lock', pin: '482916' }]);
    expect(prompt.mock.calls[1][0]).toMatch(/6-digit PIN for "mac-01"/);
    expect(confirm).not.toHaveBeenCalled();
  });

  it('a Mac wipe asks for the name, then the PIN; an iPhone lock asks only to confirm', async () => {
    vi.spyOn(window, 'prompt').mockReturnValueOnce('mac-01').mockReturnValueOnce('135790');
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<MobileDashboard />);
    fireEvent.click(within(await row('mac-01')).getByRole('button', { name: 'Wipe' }));
    await waitFor(() => expect(actions()).toHaveLength(1));
    expect(actions()[0][1]).toEqual({ action: 'wipe', confirm: 'mac-01', pin: '135790' });
    fireEvent.click(within(await row('iphone-01')).getByRole('button', { name: 'Lock' }));
    await waitFor(() => expect(actions()).toHaveLength(2));
    expect(actions()[1]).toEqual(['/api/mdm/devices/mdm-phone/action', { action: 'lock' }]);
  });
});
