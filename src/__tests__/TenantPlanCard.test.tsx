/**
 * Tenant admin's licence card on the Agents screen (88-13, LIC-07, D-19, D-21).
 * protects=the card shows plan, seats used of the limit (override and partner marks), the days left on a
 * Free trial, the trial-ended wording and the allowed networks with their source; it renders nothing for an
 * exempt organization or a refused read; it offers no control that edits anything.
 * fails_when=a mark or the trial wording is dropped, the card shows for a refused read, or an input or button
 * appears; no_claim=the backend (authFetch is mocked) and styling.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const authFetch = vi.fn();

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: (...args: unknown[]) => authFetch(...args),
}));

import { TenantPlanCard } from '../../components/TenantPlanCard';

const VIEW = {
  tenantId: 't1', maxAgents: 5, seatsUsed: 3, seatsAvailable: 2, overBy: 0, inactiveReclaimDays: 30,
  allowlistMode: 'off', subLimits: [], expiresAt: null, plan: 'Free', planSeats: 5, seatOverride: null,
  partnerManaged: false, exempt: false,
  trial: { startedAt: '2026-11-01T00:00:00Z', endsAt: '2026-11-20T00:00:00Z', consumed: false, ended: false, daysLeft: 9 },
  allowedNetworks: [{ cidr: '203.0.113.7/32', source: 'learned', addedAt: '2026-11-02T00:00:00Z' }],
};
const answer = (body: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body });

describe('TenantPlanCard', () => {
  beforeEach(() => authFetch.mockReset());

  it('shows the plan, seats, trial days and the learned network', async () => {
    authFetch.mockResolvedValue(answer(VIEW));
    render(<TenantPlanCard tenantId="t1" />);
    await waitFor(() => screen.getByText('Free'));
    expect(authFetch.mock.calls[0][0]).toBe('/api/tenants/t1/license');
    expect(screen.getByText('Your plan')).toBeTruthy();
    expect(screen.getByText(/3 of 5 seats used/)).toBeTruthy();
    expect(screen.getByText('9 days left in your free trial')).toBeTruthy();
    expect(screen.getByText('203.0.113.7 (learned)')).toBeTruthy();
    expect(screen.queryByText(/override/)).toBeNull();
  });

  it('marks an override and a partner-set limit', async () => {
    authFetch.mockResolvedValue(answer({ ...VIEW, plan: 'Pro', maxAgents: 12, seatOverride: 12, trial: null }));
    const { unmount } = render(<TenantPlanCard tenantId="t1" />);
    await waitFor(() => screen.getByText('Pro'));
    expect(screen.getByText(/3 of 12 seats used/).textContent).toContain('override');
    unmount();

    authFetch.mockResolvedValue(answer({ ...VIEW, plan: 'Pro', partnerManaged: true, trial: null }));
    render(<TenantPlanCard tenantId="t1" />);
    await waitFor(() => screen.getByText('Pro'));
    expect(screen.getByText(/3 of 5 seats used/).textContent).toContain('set by your partner');
  });

  it('says the trial has ended and that running agents keep working', async () => {
    authFetch.mockResolvedValue(answer({ ...VIEW, trial: { ...VIEW.trial, ended: true, daysLeft: 0 } }));
    render(<TenantPlanCard tenantId="t1" />);
    await waitFor(() => screen.getByText(/Your free trial has ended/));
    expect(screen.getByText(/New computers wait for approval; running agents and screens keep working\./)).toBeTruthy();
    expect(screen.queryByText(/days left in your free trial/)).toBeNull();
  });

  it('explains an empty network list', async () => {
    authFetch.mockResolvedValue(answer({ ...VIEW, allowedNetworks: [] }));
    render(<TenantPlanCard tenantId="t1" />);
    await waitFor(() => screen.getByText(/No network learned yet/));
    expect(screen.getByText(/the first computer you enroll sets it/)).toBeTruthy();
  });

  it('renders nothing for an exempt organization', async () => {
    authFetch.mockResolvedValue(answer({ ...VIEW, exempt: true, maxAgents: null }));
    const { container } = render(<TenantPlanCard tenantId="platform" />);
    await waitFor(() => expect(authFetch).toHaveBeenCalled());
    await Promise.resolve();
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when the licence read is refused', async () => {
    authFetch.mockResolvedValue(answer({ error: 'forbidden' }, 403));
    const { container } = render(<TenantPlanCard tenantId="t1" />);
    await waitFor(() => expect(authFetch).toHaveBeenCalled());
    await Promise.resolve();
    expect(container.innerHTML).toBe('');
  });

  it('offers no control that edits anything', async () => {
    authFetch.mockResolvedValue(answer(VIEW));
    const { container } = render(<TenantPlanCard tenantId="t1" />);
    await waitFor(() => screen.getByText('Free'));
    expect(container.querySelectorAll('input, button, select, textarea').length).toBe(0);
  });
});
