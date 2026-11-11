/**
 * Phase 88 (LIC-02, LIC-03; D-13, D-15, D-22; 88-UI-SPEC S10): the partner admin's Plan and trial modal.
 * The API client is mocked; every refusal is asserted in the contract's own words. The server enforces the
 * ceiling, ownership and the trial rules; the modal only shows them.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('../../services/partnerApi', async () => {
  const actual = await vi.importActual<typeof import('../../services/partnerApi')>('../../services/partnerApi');
  return { ...actual, changeCustomerPlan: vi.fn(), extendCustomerTrial: vi.fn() };
});
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import * as api from '../../services/partnerApi';
import { PartnerApiError, type PartnerCustomerRow } from '../../services/partnerApi';
import { showToast } from '../../utils/toast';
import { PartnerPlanModal } from '../../components/PartnerPlanModal';

const changeCustomerPlan = api.changeCustomerPlan as ReturnType<typeof vi.fn>;
const extendCustomerTrial = api.extendCustomerTrial as ReturnType<typeof vi.fn>;
const toast = showToast as ReturnType<typeof vi.fn>;

const DAY = 24 * 60 * 60 * 1000;
const inDays = (n: number) => new Date(Date.now() + n * DAY).toISOString();

const customer = (over: Partial<PartnerCustomerRow> = {}): PartnerCustomerRow => ({
  id: 'c1',
  name: 'Globex',
  seatsAssigned: 10,
  seatsUsed: 4,
  agentsOnline: 1,
  agentsTotal: 3,
  licenseExpiresAt: null,
  plan: 'Free',
  trialEndsAt: inDays(10),
  ...over,
});

const mount = (over: Partial<React.ComponentProps<typeof PartnerPlanModal>> = {}) => {
  const props = { customer: customer(), planCeiling: ['Free', 'Pro'], onClose: vi.fn(), onRefetch: vi.fn(), ...over };
  const view = render(<PartnerPlanModal {...props} />);
  return { ...props, rerender: (next: Partial<typeof props>) => view.rerender(<PartnerPlanModal {...props} {...next} />) };
};

const dialog = () => screen.getByRole('dialog');
const select = () => within(dialog()).getByLabelText('Plan') as HTMLSelectElement;
const optionTexts = () => Array.from(select().options).map(o => o.textContent);
const click = (name: string | RegExp) => fireEvent.click(within(dialog()).getByRole('button', { name }));

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(cleanup);

describe('PartnerPlanModal, plan (D-13)', () => {
  it('titles the modal with the customer and lists the current plan first, then the rest of the ceiling', () => {
    mount();
    expect(screen.getByRole('heading', { name: 'Plan for Globex' })).toBeTruthy();
    expect(optionTexts()).toEqual(['Free (current)', 'Pro']);
    expect(select().value).toBe('Free');
    expect(within(dialog()).getByText(/Seats stay as you assigned them\. Screens the customer already has stay on/)).toBeTruthy();
    expect(within(dialog()).getByText(/moving back to Free after a paid plan gives no new trial\./)).toBeTruthy();
    expect((within(dialog()).getByRole('button', { name: 'Save plan' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('changes the plan inside the ceiling, toasts, refetches and closes', async () => {
    changeCustomerPlan.mockResolvedValue(customer({ plan: 'Pro', trialEndsAt: null }));
    const props = mount();
    fireEvent.change(select(), { target: { value: 'Pro' } });
    expect((within(dialog()).getByRole('button', { name: 'Save plan' }) as HTMLButtonElement).disabled).toBe(false);
    click('Save plan');
    expect(within(dialog()).getByRole('button', { name: 'Saving...' })).toBeTruthy();
    await waitFor(() => expect(props.onClose).toHaveBeenCalled());
    expect(changeCustomerPlan).toHaveBeenCalledWith('c1', 'Pro');
    expect(toast).toHaveBeenCalledWith('Globex is now on the Pro plan.', 'success');
    expect(props.onRefetch).toHaveBeenCalled();
  });

  it('always lists and selects the current plan even when it is outside the ceiling', () => {
    mount({ customer: customer({ plan: 'Enterprise', trialEndsAt: null }), planCeiling: ['Free', 'Pro'] });
    expect(optionTexts()).toEqual(['Enterprise (current)', 'Free', 'Pro']);
    expect(select().value).toBe('Enterprise');
  });

  it('with an empty ceiling shows only the current plan and says so', () => {
    mount({ customer: customer({ plan: 'Pro', trialEndsAt: null }), planCeiling: [] });
    expect(optionTexts()).toEqual(['Pro (current)']);
    expect(within(dialog()).getByText("Your platform administrator hasn't chosen any plans you can sell.")).toBeTruthy();
    expect((within(dialog()).getByRole('button', { name: 'Save plan' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows plan_outside_ceiling in the contract wording, refetches and stays open', async () => {
    changeCustomerPlan.mockRejectedValue(new PartnerApiError('Plan not allowed', 422, 'plan_outside_ceiling'));
    const props = mount();
    fireEvent.change(select(), { target: { value: 'Pro' } });
    click('Save plan');
    const alert = await within(dialog()).findByRole('alert');
    expect(alert.textContent).toBe('Pro is not one of the plans you can sell.');
    expect(props.onRefetch).toHaveBeenCalled();
    expect(props.onClose).not.toHaveBeenCalled();
  });

  it('shows unknown_plan as the stale-page sentence', async () => {
    changeCustomerPlan.mockRejectedValue(new PartnerApiError('Unknown plan', 422, 'unknown_plan'));
    mount();
    fireEvent.change(select(), { target: { value: 'Pro' } });
    click('Save plan');
    expect((await within(dialog()).findByRole('alert')).textContent).toBe("That plan isn't available. Reload the page and try again.");
  });

  it('on plan_changed shows the message, refetches and resets the select to the new current plan', async () => {
    changeCustomerPlan.mockRejectedValue(new PartnerApiError('The plan changed while you were saving. Try again.', 409, 'plan_changed'));
    const props = mount();
    fireEvent.change(select(), { target: { value: 'Pro' } });
    click('Save plan');
    const alert = await within(dialog()).findByRole('alert');
    expect(alert.textContent).toBe("This customer's plan changed while you were saving. Check the plan and try again.");
    expect(props.onRefetch).toHaveBeenCalled();
    // The portal refetched: the live row now carries the plan someone else set.
    props.rerender({ customer: customer({ plan: 'Pro', trialEndsAt: null }) });
    expect(select().value).toBe('Pro');
    expect(optionTexts()).toEqual(['Pro (current)', 'Free']);
    expect(within(dialog()).getByRole('alert').textContent).toContain('changed while you were saving');
  });

  it('wraps other failures through partnerFailureText and disables everything while saving', async () => {
    let reject: (e: unknown) => void = () => {};
    changeCustomerPlan.mockReturnValue(new Promise((_r, j) => { reject = j; }));
    mount();
    fireEvent.change(select(), { target: { value: 'Pro' } });
    click('Save plan');
    expect(select().disabled).toBe(true);
    expect((within(dialog()).getByRole('button', { name: 'Extend trial' }) as HTMLButtonElement).disabled).toBe(true);
    reject(new PartnerApiError('Server said no.', 500));
    expect((await within(dialog()).findByRole('alert')).textContent).toBe("Couldn't save the plan: Server said no. Try again.");
    expect(select().disabled).toBe(false);
  });
});

describe('PartnerPlanModal, trial (D-15)', () => {
  it('shows the open trial end and days left on a Free customer, with the extension field at 7', () => {
    mount();
    expect(within(dialog()).getByText(/^Trial ends [A-Z][a-z]{2} \d{1,2}, \d{4}: 10 days left$/)).toBeTruthy();
    expect((within(dialog()).getByLabelText('Extend trial by (days)') as HTMLInputElement).value).toBe('7');
  });

  it('says 1 day left at one day', () => {
    mount({ customer: customer({ trialEndsAt: inDays(1) }) });
    expect(within(dialog()).getByText(/: 1 day left$/)).toBeTruthy();
  });

  it('shows an ended trial as ended, still offering the extension', () => {
    mount({ customer: customer({ trialEndsAt: '2020-01-05T23:59:59Z' }) });
    expect(within(dialog()).getByText('Trial ended Jan 5, 2020')).toBeTruthy();
    expect((within(dialog()).getByRole('button', { name: 'Extend trial' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('extends by 7 days, toasts the new end date, refetches and stays open', async () => {
    extendCustomerTrial.mockResolvedValue(customer({ trialEndsAt: '2099-01-05T23:59:59Z' }));
    const props = mount();
    click('Extend trial');
    expect(within(dialog()).getByRole('button', { name: 'Extending...' })).toBeTruthy();
    await waitFor(() => expect(props.onRefetch).toHaveBeenCalled());
    expect(extendCustomerTrial).toHaveBeenCalledWith('c1', 7);
    expect(toast).toHaveBeenCalledWith("Trial extended. Globex's trial now ends Jan 5, 2099.", 'success');
    expect(props.onClose).not.toHaveBeenCalled();
    expect((within(dialog()).getByRole('button', { name: 'Extend trial' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it.each(['0', '366', '2.5', '', 'abc'])('disables Extend trial and says why for %j days', value => {
    mount();
    fireEvent.change(within(dialog()).getByLabelText('Extend trial by (days)'), { target: { value } });
    expect((within(dialog()).getByRole('button', { name: 'Extend trial' }) as HTMLButtonElement).disabled).toBe(true);
    expect(within(dialog()).getByText('Enter a whole number of days from 1 to 365.')).toBeTruthy();
  });

  it.each(['1', '365'])('accepts %s days', async value => {
    extendCustomerTrial.mockResolvedValue(customer());
    mount();
    fireEvent.change(within(dialog()).getByLabelText('Extend trial by (days)'), { target: { value } });
    click('Extend trial');
    await waitFor(() => expect(extendCustomerTrial).toHaveBeenCalledWith('c1', Number(value)));
  });

  it('explains on a paid plan that only a Free trial can be extended, with no extension control', () => {
    mount({ customer: customer({ plan: 'Pro', trialEndsAt: null }) });
    expect(within(dialog()).getByText('Only a Free trial can be extended.')).toBeTruthy();
    expect(within(dialog()).queryByRole('button', { name: 'Extend trial' })).toBeNull();
    expect(within(dialog()).queryByLabelText('Extend trial by (days)')).toBeNull();
  });

  it('shows not_on_trial and trial_changed verbatim; trial_changed refetches', async () => {
    extendCustomerTrial.mockRejectedValueOnce(new PartnerApiError('Only a Free trial can be extended.', 422, 'not_on_trial'));
    const props = mount();
    click('Extend trial');
    expect((await within(dialog()).findByRole('alert')).textContent).toBe('Only a Free trial can be extended.');
    extendCustomerTrial.mockRejectedValueOnce(new PartnerApiError('The trial changed while you were saving. Try again.', 409, 'trial_changed'));
    click('Extend trial');
    await waitFor(() => expect(within(dialog()).getByRole('alert').textContent).toBe('The trial changed while you were saving. Try again.'));
    expect(props.onRefetch).toHaveBeenCalled();
  });

  it('shows invalid_days in the contract wording', async () => {
    extendCustomerTrial.mockRejectedValue(new PartnerApiError('days must be between 1 and 365', 422, 'invalid_days'));
    mount();
    click('Extend trial');
    expect((await within(dialog()).findByRole('alert')).textContent).toBe('Enter a whole number of days from 1 to 365.');
  });
});
