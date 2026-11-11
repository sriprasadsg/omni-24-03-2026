/**
 * The live Add New Tenant wizard (UI-SPEC S3, G-24): plan options Free, Pro, Enterprise and Custom, Free by
 * default (D-24), a required Seats number for Custom sent as maxAgents, and a refused create that keeps the
 * wizard on its step with the typed values and the server sentence.
 * no_claim=the backend (apiService is mocked) and the admin-user and API-key steps.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

const addTenant = vi.fn();
vi.mock('../../services/apiService', () => ({
  addTenant: (...args: unknown[]) => addTenant(...args),
  addUser: vi.fn(),
  generateApiKey: vi.fn(),
}));

import { TenantOnboardingWizard } from '../../components/TenantOnboardingWizard';

const open = (props: Partial<React.ComponentProps<typeof TenantOnboardingWizard>> = {}) =>
  render(<TenantOnboardingWizard isOpen onClose={() => {}} onComplete={() => {}} {...props} />);
const fillName = (name: string) => fireEvent.change(screen.getByPlaceholderText('Acme Corp'), { target: { value: name } });
const plan = (name: string) => screen.getByRole('button', { name }) as HTMLButtonElement;
const create = () => fireEvent.click(screen.getByRole('button', { name: /Create Organization/ }));

beforeEach(() => addTenant.mockReset());
afterEach(cleanup);

describe('TenantOnboardingWizard plan step (UI-SPEC S3)', () => {
  it('offers Free, Pro, Enterprise and Custom (no Starter), opens on Free, and calls the field Plan', () => {
    open();
    const names = ['Free', 'Pro', 'Enterprise', 'Custom'];
    for (const n of names) expect(plan(n)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Starter' })).toBeNull();
    expect(plan('Free').getAttribute('aria-pressed')).toBe('true');
    for (const n of ['Pro', 'Enterprise', 'Custom']) expect(plan(n).getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByText('Plan')).toBeTruthy();
    expect(screen.queryByText('Subscription Tier')).toBeNull();
  });

  it('explains each plan, and Custom asks for seats with their helper', () => {
    open();
    expect(screen.getByText('Starts a free trial today. Seats and screens follow the Free plan.')).toBeTruthy();
    fireEvent.click(plan('Pro'));
    expect(screen.getByText('Seats and screens follow the Pro plan. Tick screens one by one in Manage Tenant.')).toBeTruthy();
    fireEvent.click(plan('Enterprise'));
    expect(screen.getByText('Seats and screens follow the Enterprise plan. Tick screens one by one in Manage Tenant.')).toBeTruthy();
    expect(screen.queryByLabelText(/Seats/)).toBeNull();
    fireEvent.click(plan('Custom'));
    expect(screen.getByText('Set per tenant by contract. Tick screens one by one in Manage Tenant.')).toBeTruthy();
    expect(screen.getByLabelText(/Seats/)).toBeTruthy();
    expect(screen.getByText('The seat limit from the contract. 0 means no computer can enroll.')).toBeTruthy();
  });

  it('creates a Free tenant by default with no seat count', async () => {
    addTenant.mockResolvedValue({ id: 't1', name: 'Acme' });
    open();
    fillName('Acme');
    create();
    await waitFor(() => expect(addTenant).toHaveBeenCalled());
    expect(addTenant.mock.calls[0][0]).toEqual({ name: 'Acme', subscriptionTier: 'Free' });
    await waitFor(() => screen.getByText(/Add a first admin user/));
  });

  it('Custom refuses a missing or non-whole seat count and sends nothing', () => {
    open();
    fillName('Globex');
    fireEvent.click(plan('Custom'));
    create();
    expect(screen.getByText('Seats must be a whole number from 0 to 1,000,000.')).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Seats/), { target: { value: '2.5' } });
    create();
    expect(screen.getByText('Seats must be a whole number from 0 to 1,000,000.')).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Seats/), { target: { value: '1000001' } });
    create();
    expect(addTenant).not.toHaveBeenCalled();
  });

  it('Custom sends the seats as maxAgents', async () => {
    addTenant.mockResolvedValue({ id: 't2', name: 'Globex' });
    open();
    fillName('Globex');
    fireEvent.click(plan('Custom'));
    fireEvent.change(screen.getByLabelText(/Seats/), { target: { value: '40' } });
    create();
    await waitFor(() => expect(addTenant).toHaveBeenCalled());
    expect(addTenant.mock.calls[0][0]).toEqual({ name: 'Globex', subscriptionTier: 'Custom', maxAgents: 40 });
  });

  it('a refused create stays on the step with the typed values and the server sentence', async () => {
    addTenant.mockRejectedValue(new Error('unknown_plan: That plan is not available.'));
    open();
    fillName('Acme');
    fireEvent.click(plan('Custom'));
    fireEvent.change(screen.getByLabelText(/Seats/), { target: { value: '40' } });
    create();
    await waitFor(() => screen.getByText('unknown_plan: That plan is not available.'));
    expect((screen.getByPlaceholderText('Acme Corp') as HTMLInputElement).value).toBe('Acme');
    expect(plan('Custom').getAttribute('aria-pressed')).toBe('true');
    expect((screen.getByLabelText(/Seats/) as HTMLInputElement).value).toBe('40');
    expect(screen.queryByText(/Add a first admin user/)).toBeNull();
    expect((screen.getByRole('button', { name: /Create Organization/ }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('closing resets the plan to Free', () => {
    const onClose = vi.fn();
    const { container } = open({ onClose });
    fireEvent.click(plan('Pro'));
    expect(plan('Pro').getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(container.firstChild as HTMLElement);
    expect(onClose).toHaveBeenCalled();
    expect(plan('Free').getAttribute('aria-pressed')).toBe('true');
  });
});
