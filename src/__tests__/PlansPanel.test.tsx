/**
 * Phase 88 (LIC-07, D-14, D-17, D-28): the Super Admin Plans screen opened from Tenant Management.
 * The plans API client is mocked; the server enforces every rule, so these cases cover what the
 * screen shows, what it sends and how it reports the answer.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('../../services/plansApi', async () => {
  const actual = await vi.importActual<typeof import('../../services/plansApi')>('../../services/plansApi');
  return { ...actual, fetchPlans: vi.fn(), savePlan: vi.fn() };
});

import * as api from '../../services/plansApi';
import type { Plan } from '../../services/plansApi';
import { PlansPanel } from '../../components/PlansPanel';

const fetchPlans = api.fetchPlans as ReturnType<typeof vi.fn>;
const savePlan = api.savePlan as ReturnType<typeof vi.fn>;

const plans: Plan[] = [
  { key: 'Free', seats: 5, trialDays: 14, screens: ['screen:dashboard', 'view:agents'], tenantCount: 3 },
  { key: 'Pro', seats: 50, trialDays: null, screens: ['screen:dashboard', 'view:agents', 'view:logs'], tenantCount: 2 },
  { key: 'Enterprise', seats: 500, trialDays: null, screens: ['screen:dashboard'], tenantCount: 1 },
  { key: 'Custom', seats: null, trialDays: null, screens: 'all', tenantCount: 4 },
];

const section = (key: string) => screen.getByRole('region', { name: `${key} plan` });
const box = (key: string, label: string) =>
  within(within(section(key)).getByText(label).closest('label') as HTMLElement).getByRole('checkbox') as HTMLInputElement;

async function open() {
  render(<PlansPanel isOpen onClose={() => {}} />);
  await waitFor(() => expect(screen.getByRole('region', { name: 'Free plan' })).toBeTruthy());
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchPlans.mockResolvedValue(plans);
});
afterEach(cleanup);

describe('PlansPanel (LIC-07)', () => {
  it('lists Free, Pro, Enterprise and Custom with seats and tenant counts', async () => {
    await open();
    for (const key of ['Free', 'Pro', 'Enterprise', 'Custom']) expect(section(key)).toBeTruthy();
    expect((within(section('Pro')).getByLabelText('Pro seats') as HTMLInputElement).value).toBe('50');
    expect(within(section('Pro')).getByText('2 tenants')).toBeTruthy();
    expect(within(section('Enterprise')).getByText('1 tenant')).toBeTruthy();
  });

  it('saving Pro seats sends PUT with only the seats and reports the tenants updated', async () => {
    savePlan.mockResolvedValue({ plan: { ...plans[1], seats: 60 }, tenantsUpdated: 2 });
    await open();
    fireEvent.change(within(section('Pro')).getByLabelText('Pro seats'), { target: { value: '60' } });
    fireEvent.click(within(section('Pro')).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(within(section('Pro')).getByText('Saved. 2 tenants updated.')).toBeTruthy());
    expect(savePlan).toHaveBeenCalledWith('Pro', { seats: 60 });
  });

  it('trial days exist on Free only, and Custom is read-only "Set per tenant by contract" (D-17)', async () => {
    await open();
    expect(within(section('Free')).getByLabelText('Free trial days')).toBeTruthy();
    expect(screen.getAllByLabelText(/trial days/i)).toHaveLength(1);
    const custom = within(section('Custom'));
    expect(custom.getByText('Set per tenant by contract')).toBeTruthy();
    expect(custom.queryAllByRole('spinbutton')).toHaveLength(0);
    expect(custom.queryByRole('button', { name: 'Save' })).toBeNull();
  });

  it('unticking a screen on Free and saving sends the list without it', async () => {
    savePlan.mockResolvedValue({ plan: plans[0], tenantsUpdated: 0 });
    await open();
    expect(box('Free', 'Overview').checked).toBe(true);
    fireEvent.click(box('Free', 'Agent Fleet Management'));
    fireEvent.click(within(section('Free')).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(savePlan).toHaveBeenCalled());
    expect(savePlan).toHaveBeenCalledWith('Free', { screens: ['screen:dashboard'] });
  });

  it('explains when each kind of change takes effect (D-28)', async () => {
    await open();
    expect(screen.getByText(/Seat changes apply at once to every tenant on the plan without an override/)).toBeTruthy();
    expect(screen.getByText(/Screen changes only limit what can be ticked from now on/)).toBeTruthy();
    expect(screen.getByText(/Trial-day changes apply to trials that start afterwards/)).toBeTruthy();
  });

  it('shows a 422 answer and keeps the edits', async () => {
    savePlan.mockRejectedValue(new Error('seats must be a whole number from 0 to 1,000,000'));
    await open();
    const seats = within(section('Pro')).getByLabelText('Pro seats') as HTMLInputElement;
    fireEvent.change(seats, { target: { value: '70' } });
    fireEvent.click(within(section('Pro')).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(within(section('Pro')).getByText('seats must be a whole number from 0 to 1,000,000')).toBeTruthy());
    expect((within(section('Pro')).getByLabelText('Pro seats') as HTMLInputElement).value).toBe('70');
  });

  it('does not send a seat count that is not a whole number', async () => {
    await open();
    fireEvent.change(within(section('Pro')).getByLabelText('Pro seats'), { target: { value: '1.5' } });
    fireEvent.click(within(section('Pro')).getByRole('button', { name: 'Save' }));
    expect(within(section('Pro')).getByText('Seats must be a whole number from 0 to 1,000,000.')).toBeTruthy();
    expect(savePlan).not.toHaveBeenCalled();
  });

  it('shows why the plans could not be loaded', async () => {
    fetchPlans.mockRejectedValue(new Error('HTTP 403'));
    render(<PlansPanel isOpen onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText('HTTP 403')).toBeTruthy());
  });
});
