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
    fireEvent.click(within(section('Pro')).getByRole('button', { name: 'Save Pro plan' }));
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
    expect(custom.queryByRole('button', { name: /^Save/ })).toBeNull();
  });

  it('unticking a screen on Free and saving sends the list without it', async () => {
    savePlan.mockResolvedValue({ plan: plans[0], tenantsUpdated: 0 });
    await open();
    expect(box('Free', 'Overview').checked).toBe(true);
    fireEvent.click(box('Free', 'Agent Fleet Management'));
    fireEvent.click(within(section('Free')).getByRole('button', { name: 'Save Free plan' }));
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
    fireEvent.click(within(section('Pro')).getByRole('button', { name: 'Save Pro plan' }));
    await waitFor(() => expect(within(section('Pro')).getByText('seats must be a whole number from 0 to 1,000,000')).toBeTruthy());
    expect((within(section('Pro')).getByLabelText('Pro seats') as HTMLInputElement).value).toBe('70');
  });

  it('does not send a seat count that is not a whole number', async () => {
    await open();
    fireEvent.change(within(section('Pro')).getByLabelText('Pro seats'), { target: { value: '1.5' } });
    fireEvent.click(within(section('Pro')).getByRole('button', { name: 'Save Pro plan' }));
    expect(within(section('Pro')).getByText('Seats must be a whole number from 0 to 1,000,000.')).toBeTruthy();
    expect(savePlan).not.toHaveBeenCalled();
  });

  it('says the plans could not be loaded, shows no stale sections and retries on Try again (G-12)', async () => {
    fetchPlans.mockRejectedValueOnce(new Error('HTTP 403'));
    render(<PlansPanel isOpen onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("Couldn't load the plans. Check your connection and try again.")).toBeTruthy());
    expect(screen.queryByRole('region')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByRole('region', { name: 'Free plan' })).toBeTruthy());
    expect(fetchPlans).toHaveBeenCalledTimes(2);
    expect(screen.queryByText(/Couldn't load the plans/)).toBeNull();
  });

  it('says so when no plans come back, with Try again (G-12)', async () => {
    fetchPlans.mockResolvedValue([]);
    render(<PlansPanel isOpen onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText(/No plans were found\./)).toBeTruthy());
    expect(screen.getByText(/ask whoever runs the platform to check the plan migration\./)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy();
  });
});

describe('PlansPanel UI-SPEC S1 conformance', () => {
  it('names each section button after its plan, and shows Saving... while pending (G-23)', async () => {
    let finish: (v: unknown) => void = () => {};
    savePlan.mockReturnValue(new Promise(r => { finish = r; }));
    await open();
    for (const key of ['Free', 'Pro', 'Enterprise']) {
      expect(within(section(key)).getByRole('button', { name: `Save ${key} plan` })).toBeTruthy();
    }
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull();
    fireEvent.change(within(section('Pro')).getByLabelText('Pro seats'), { target: { value: '60' } });
    fireEvent.click(within(section('Pro')).getByRole('button', { name: 'Save Pro plan' }));
    await waitFor(() => expect(within(section('Pro')).getByRole('button', { name: 'Saving...' })).toBeTruthy());
    expect((within(section('Pro')).getByLabelText('Pro seats') as HTMLInputElement).disabled).toBe(true);
    expect((within(section('Free')).getByLabelText('Free seats') as HTMLInputElement).disabled).toBe(false);
    finish({ plan: { ...plans[1], seats: 60 }, tenantsUpdated: 2 });
    await waitFor(() => within(section('Pro')).getByText('Saved. 2 tenants updated.'));
  });

  it('does not close on a backdrop click, so edits are not lost (G-10)', async () => {
    const onClose = vi.fn();
    render(<PlansPanel isOpen onClose={onClose} />);
    await waitFor(() => expect(screen.getByRole('region', { name: 'Free plan' })).toBeTruthy());
    fireEvent.mouseDown(screen.getByRole('dialog'));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('uses the shared screen checklist: parent rule, Overview always included, select and clear all (G-09)', async () => {
    savePlan.mockResolvedValue({ plan: plans[0], tenantsUpdated: 0 });
    await open();
    const free = within(section('Free'));
    expect(box('Free', 'Overview')).toMatchObject({ checked: true, disabled: true });
    expect(free.getByText('Always included')).toBeTruthy();

    expect(box('Free', 'Patch Management').checked).toBe(false);
    fireEvent.click(box('Free', 'Deploy Patches'));
    expect(box('Free', 'Patch Management').checked).toBe(true);
    expect(box('Free', 'Deploy Patches').checked).toBe(true);
    fireEvent.click(free.getByRole('button', { name: 'Save Free plan' }));
    await waitFor(() => expect(savePlan).toHaveBeenCalled());
    expect(savePlan.mock.calls[0][1].screens).toEqual(expect.arrayContaining(['screen:dashboard', 'view:agents', 'view:patching', 'manage:patches']));

    fireEvent.click(free.getByRole('button', { name: 'Select all screens' }));
    expect(free.getByText(/^207 of 207 selected$/)).toBeTruthy();
    fireEvent.click(free.getByRole('button', { name: 'Clear all screens' }));
    expect(free.getByText(/^0 of 207 selected$/)).toBeTruthy();
    expect(box('Free', 'Overview').checked).toBe(true);
  });

  it('shows the live effect line under a changed field only (G-11)', async () => {
    await open();
    const pro = within(section('Pro'));
    expect(pro.queryByText(/Applies at once to every tenant on Pro/)).toBeNull();
    const seats = pro.getByLabelText('Pro seats');
    fireEvent.change(seats, { target: { value: '60' } });
    const line = pro.getByText('Applies at once to every tenant on Pro that has no seat override (2 on this plan). Running agents are never cut off; computers over the new limit wait for approval.');
    expect(line.getAttribute('aria-live')).toBe('polite');
    expect(seats.getAttribute('aria-describedby')).toBe(line.id);
    fireEvent.change(seats, { target: { value: '50' } });
    expect(pro.queryByText(/Applies at once to every tenant on Pro/)).toBeNull();

    const free = within(section('Free'));
    fireEvent.change(free.getByLabelText('Free trial days'), { target: { value: '30' } });
    expect(free.getByText('Applies to trials that start afterwards.')).toBeTruthy();
    expect(free.queryByText('Only limits what can be ticked from now on; screens already on stay on.')).toBeNull();
    fireEvent.click(box('Free', 'Agent Fleet Management'));
    expect(free.getByText('Only limits what can be ticked from now on; screens already on stay on.')).toBeTruthy();
  });

  it('uses the contract type scale and control sizes (G-01, G-02, G-03, G-04) and explains Custom', async () => {
    await open();
    expect(screen.getByRole('heading', { name: 'Free' }).className).toMatch(/text-lg/);
    expect(screen.getByRole('heading', { name: 'Free' }).className).not.toMatch(/text-base/);
    const html = screen.getByRole('dialog').innerHTML;
    expect(html).not.toMatch(/font-medium/);
    expect(html).not.toMatch(/\bpy-1(\.5)?\b/);
    expect(html).not.toMatch(/uppercase/);
    expect(within(section('Pro')).getByRole('button', { name: 'Save Pro plan' }).className).toMatch(/min-h-10/);
    expect(within(section('Custom')).getByText('Choose the seats and screens for each Custom tenant in Manage Tenant.')).toBeTruthy();
  });
});
