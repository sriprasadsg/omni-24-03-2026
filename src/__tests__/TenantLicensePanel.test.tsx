/**
 * Super Admin licence panel in Manage Tenant (88-13, LIC-01, LIC-03, LIC-05, D-09, D-15, D-19).
 * protects=the panel shows the plan's seat number beside the tenant's limit, marks an override and returns
 * to the plan number through PATCH {clearSeatOverride: true} (direct tenants only); shows the Free trial end
 * and extends it by 1..365 days through PATCH {trialExtendDays}; lists the allowed networks read-only; and
 * still saves the existing fields with the same PATCH body.
 * fails_when=Use plan number shows for a partner customer or without an override, an out-of-range extension
 * can be sent, the networks become editable, or the old save body changes; no_claim=the backend (authFetch is mocked).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const authFetch = vi.fn();

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: (...args: unknown[]) => authFetch(...args),
}));

import { TenantLicensePanel } from '../../components/TenantLicensePanel';

const VIEW = {
  tenantId: 't1', maxAgents: 12, seatsUsed: 4, seatsAvailable: 8, overBy: 0, inactiveReclaimDays: 30,
  allowlistMode: 'off', subLimits: [], expiresAt: null, plan: 'Free', planSeats: 5, seatOverride: 12,
  partnerManaged: false, exempt: false,
  trial: { startedAt: '2026-11-01T00:00:00Z', endsAt: '2026-11-20T00:00:00Z', consumed: false, ended: false, daysLeft: 9 },
  allowedNetworks: [
    { cidr: '203.0.113.7/32', source: 'learned', addedAt: '2026-11-02T00:00:00Z' },
    { cidr: '10.1.0.0/16', source: 'approved', addedAt: '2026-11-03T00:00:00Z' },
  ],
};
const answer = (body: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
const patches = () => authFetch.mock.calls.filter(c => c[1]?.method === 'PATCH');
const sentBody = (i = 0) => JSON.parse(patches()[i][1].body);

const mockServer = (view: unknown, afterPatch?: unknown) => {
  authFetch.mockImplementation(async (_url: string, init?: { method?: string }) =>
    init?.method === 'PATCH' ? answer(afterPatch ?? view) : answer(view));
};

describe('TenantLicensePanel plan, override and trial', () => {
  beforeEach(() => authFetch.mockReset());

  it('shows the plan number beside the limit, marks the override and returns to the plan number', async () => {
    mockServer(VIEW, { ...VIEW, maxAgents: 5, seatOverride: null });
    render(<TenantLicensePanel tenantId="t1" />);
    await waitFor(() => screen.getByText('Plan Free: 5 seats'));
    expect(authFetch.mock.calls[0][0]).toBe('/api/tenants/t1/license');
    expect(screen.getByText('Limit 12 (override)')).toBeTruthy();

    fireEvent.click(screen.getByText('Use plan number'));
    await waitFor(() => expect(patches().length).toBe(1));
    expect(sentBody()).toEqual({ clearSeatOverride: true });
    await waitFor(() => screen.getByText('Limit 5'));
    expect(screen.queryByText('Use plan number')).toBeNull();
    expect((screen.getByLabelText('Max agents') as HTMLInputElement).value).toBe('5');
  });

  it('has no Use plan number without an override, and none for a partner customer', async () => {
    mockServer({ ...VIEW, maxAgents: 5, seatOverride: null });
    const { unmount } = render(<TenantLicensePanel tenantId="t1" />);
    await waitFor(() => screen.getByText('Limit 5'));
    expect(screen.queryByText('Use plan number')).toBeNull();
    unmount();

    mockServer({ ...VIEW, partnerManaged: true });
    render(<TenantLicensePanel tenantId="t1" />);
    await waitFor(() => screen.getByText(/partner's allotment sets the seats/));
    expect(screen.queryByText('Use plan number')).toBeNull();
  });

  it('shows the trial end and days left on Free and extends it', async () => {
    mockServer(VIEW, { ...VIEW, trial: { ...VIEW.trial, endsAt: '2026-11-27T00:00:00Z', daysLeft: 16 } });
    render(<TenantLicensePanel tenantId="t1" />);
    await waitFor(() => screen.getByText('9 days left'));
    expect(screen.getByText('Nov 20, 2026').getAttribute('title')).toBe('2026-11-20');

    const days = screen.getByLabelText(/Extend trial by/) as HTMLInputElement;
    const extend = screen.getByText('Extend') as HTMLButtonElement;
    for (const bad of ['0', '366', '2.5', '']) {
      fireEvent.change(days, { target: { value: bad } });
      expect(extend.disabled).toBe(true);
    }
    fireEvent.change(days, { target: { value: '7' } });
    expect(extend.disabled).toBe(false);
    fireEvent.click(extend);
    await waitFor(() => expect(patches().length).toBe(1));
    expect(sentBody()).toEqual({ trialExtendDays: 7 });
    await waitFor(() => screen.getByText('16 days left'));
  });

  it('UI-SPEC S5: Use plan number is a neutral underlined 14/600 text button of 32px, and says what happened (G-07, G-20)', async () => {
    mockServer(VIEW, { ...VIEW, maxAgents: 5, seatOverride: null });
    render(<TenantLicensePanel tenantId="t1" />);
    await waitFor(() => screen.getByText('Use plan number'));
    const button = screen.getByText('Use plan number');
    expect(button.className).not.toMatch(/primary/);
    expect(button.className).toMatch(/min-h-8/);
    expect(button.className).toMatch(/text-sm/);
    expect(button.className).toMatch(/font-semibold/);
    expect(button.className).toMatch(/underline/);
    fireEvent.click(button);
    const status = await waitFor(() => screen.getByRole('status'));
    expect(status.textContent).toBe("Seat limit is the plan's number again (5).");
  });

  it('UI-SPEC S5: Extend says the new end date, points at its effect line and has no half-step padding (G-20, G-22, G-04, G-02)', async () => {
    mockServer(VIEW, { ...VIEW, trial: { ...VIEW.trial, endsAt: '2026-11-27T00:00:00Z', daysLeft: 16 } });
    render(<TenantLicensePanel tenantId="t1" />);
    await waitFor(() => screen.getByText('9 days left'));
    const extend = screen.getByText('Extend');
    expect(extend.className).toMatch(/min-h-10/);
    expect(extend.className).not.toMatch(/py-1(\.5)?\b/);
    const effect = screen.getByText('Counts from today if the trial has ended. Recorded in the audit log.');
    expect(extend.getAttribute('aria-describedby')).toBe(effect.id);
    expect(screen.getByText(/Extend trial by/).className).not.toMatch(/font-medium/);
    fireEvent.click(extend);
    const status = await waitFor(() => screen.getByRole('status'));
    expect(status.textContent).toBe('Trial now ends Nov 27, 2026.');
  });

  it('clears the status line when a field is edited (G-20)', async () => {
    mockServer(VIEW, { ...VIEW, maxAgents: 5, seatOverride: null });
    render(<TenantLicensePanel tenantId="t1" />);
    await waitFor(() => screen.getByText('Use plan number'));
    fireEvent.click(screen.getByText('Use plan number'));
    await waitFor(() => screen.getByRole('status'));
    fireEvent.change(screen.getByLabelText('Max agents'), { target: { value: '9' } });
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('shows no trial row on a paid plan', async () => {
    mockServer({ ...VIEW, plan: 'Pro', planSeats: 25, trial: null });
    render(<TenantLicensePanel tenantId="t1" />);
    await waitFor(() => screen.getByText('Plan Pro: 25 seats'));
    expect(screen.queryByLabelText(/Extend trial by/)).toBeNull();
  });

  it('lists the allowed networks with their source and no way to edit them', async () => {
    mockServer(VIEW);
    render(<TenantLicensePanel tenantId="t1" />);
    await waitFor(() => screen.getByText('203.0.113.7/32 (learned)'));
    expect(screen.getByText('10.1.0.0/16 (approved)')).toBeTruthy();
    const list = screen.getByText('Allowed networks').parentElement!;
    expect(list.querySelectorAll('input, button, select').length).toBe(0);
  });

  it('still saves the existing fields with the same PATCH body', async () => {
    mockServer({ ...VIEW, seatOverride: null, maxAgents: 5 }, { ...VIEW, maxAgents: 8, seatOverride: 8 });
    render(<TenantLicensePanel tenantId="t1" />);
    await waitFor(() => screen.getByText('Limit 5'));
    fireEvent.change(screen.getByLabelText('Max agents'), { target: { value: '8' } });
    fireEvent.click(screen.getByText('Save license'));
    await waitFor(() => expect(patches().length).toBe(1));
    expect(sentBody()).toEqual({ maxAgents: 8, inactiveReclaimDays: 30, allowlistMode: 'off', subLimits: [] });
  });

  it('shows a refusal from the server and keeps the panel usable', async () => {
    authFetch.mockImplementation(async (_url: string, init?: { method?: string }) =>
      init?.method === 'PATCH' ? answer({ error: 'trialExtendDays must be 1..365' }, 400) : answer(VIEW));
    render(<TenantLicensePanel tenantId="t1" />);
    await waitFor(() => screen.getByText('9 days left'));
    fireEvent.change(screen.getByLabelText(/Extend trial by/), { target: { value: '7' } });
    fireEvent.click(screen.getByText('Extend'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('trialExtendDays must be 1..365'));
  });
});
