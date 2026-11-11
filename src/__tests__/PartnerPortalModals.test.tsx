/**
 * Phase 87 (PART-02, PART-04, PART-06; 87-UI-SPEC section 2): the Partner portal's Create customer, Change
 * seats and Choose screens modals, and (Task 3) the Team section. The API client is mocked; every floor,
 * ceiling and refusal is asserted in the contract's own words.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('../../services/partnerApi', async () => {
  const actual = await vi.importActual<typeof import('../../services/partnerApi')>('../../services/partnerApi');
  return {
    ...actual,
    fetchPartnerOverview: vi.fn(),
    fetchPartnerTeam: vi.fn(),
    createPartnerCustomer: vi.fn(),
    changeCustomerSeats: vi.fn(),
    changeCustomerPlan: vi.fn(),
    extendCustomerTrial: vi.fn(),
    fetchCustomerFeatures: vi.fn(),
    saveCustomerFeatures: vi.fn(),
    inviteColleague: vi.fn(),
    resendColleagueInvite: vi.fn(),
  };
});
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import * as api from '../../services/partnerApi';
import { PartnerApiError, type CustomerFeatures, type PartnerCustomerRow, type PartnerOverview, type PartnerTeamMember } from '../../services/partnerApi';
import { showToast } from '../../utils/toast';
import { ChangeSeatsModal, ChooseScreensModal, CreateCustomerModal } from '../../components/PartnerCustomerModals';
import { PartnerPortal } from '../../components/PartnerPortal';
import { InviteColleagueModal, PartnerTeamPanel } from '../../components/PartnerTeamPanel';

const createPartnerCustomer = api.createPartnerCustomer as ReturnType<typeof vi.fn>;
const changeCustomerSeats = api.changeCustomerSeats as ReturnType<typeof vi.fn>;
const fetchCustomerFeatures = api.fetchCustomerFeatures as ReturnType<typeof vi.fn>;
const saveCustomerFeatures = api.saveCustomerFeatures as ReturnType<typeof vi.fn>;
const fetchPartnerOverview = api.fetchPartnerOverview as ReturnType<typeof vi.fn>;
const fetchPartnerTeam = api.fetchPartnerTeam as ReturnType<typeof vi.fn>;
const toast = showToast as ReturnType<typeof vi.fn>;
const inviteColleague = api.inviteColleague as ReturnType<typeof vi.fn>;
const resendColleagueInvite = api.resendColleagueInvite as ReturnType<typeof vi.fn>;

const customer = (over: Partial<PartnerCustomerRow> = {}): PartnerCustomerRow => ({
  id: 'c1',
  name: 'Globex',
  seatsAssigned: 10,
  seatsUsed: 4,
  agentsOnline: 1,
  agentsTotal: 3,
  licenseExpiresAt: null,
  ...over,
});

const CEILING = ['screen:customDashboards', 'screen:digitalTwin'];

const features = (over: Partial<CustomerFeatures> = {}): CustomerFeatures => ({
  enabledFeatures: ['screen:dashboard'],
  ceiling: CEILING,
  unrestricted: false,
  kept: [],
  ...over,
});

const overview = (over: Partial<PartnerOverview> = {}): PartnerOverview => ({
  partner: { name: 'Acme Retail' },
  role: 'admin',
  pool: { size: 100, handedOut: 40, free: 60, expiresAt: null, expired: false },
  ceiling: CEILING,
  unrestricted: false,
  customers: [customer()],
  ...over,
});

const dialog = () => screen.getByRole('dialog');
const type = (label: string, value: string) =>
  fireEvent.change(within(dialog()).getByLabelText(label), { target: { value } });
const click = (name: string | RegExp) => fireEvent.click(within(dialog()).getByRole('button', { name }));

beforeEach(() => {
  vi.clearAllMocks();
  fetchPartnerTeam.mockResolvedValue([]);
});
afterEach(cleanup);

describe('CreateCustomerModal (PART-02, D-09)', () => {
  const mount = (over: Partial<React.ComponentProps<typeof CreateCustomerModal>> = {}) => {
    const props = { free: 60, ceiling: CEILING, unrestricted: false, onClose: vi.fn(), onRefetch: vi.fn(), ...over };
    render(<CreateCustomerModal {...props} />);
    return props;
  };
  const fill = (name = 'Globex', seats = '5', adminName = 'Ada Lovelace', email = 'ada@globex.example') => {
    type('Customer name', name);
    type('Seats', seats);
    type('Name', adminName);
    type('Email address', email);
  };

  it('collects the customer, seats, first administrator and optional screens with the D-09 helper lines', () => {
    mount();
    expect(screen.getByRole('heading', { name: 'Create a customer' })).toBeTruthy();
    expect(within(dialog()).getByText('Taken from your pool. You have 60 seats free.')).toBeTruthy();
    expect(within(dialog()).getByText(/We email this person a link to set a password\. The link works for 7 days\. They then run the organization\./)).toBeTruthy();
    expect(within(dialog()).getByText('They get the same rights as the administrator of any organization on the platform.')).toBeTruthy();
    expect(within(dialog()).getByText('Dashboard only. You can add more later.')).toBeTruthy();
    expect(within(dialog()).queryByText('Digital Twin')).toBeNull();
    expect((within(dialog()).getByRole('button', { name: 'Create customer' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('says 1 seat in the helper at one free seat', () => {
    mount({ free: 1 });
    expect(within(dialog()).getByText('Taken from your pool. You have 1 seat free.')).toBeTruthy();
  });

  it('shows the validation messages verbatim after a field is left', () => {
    mount();
    for (const label of ['Customer name', 'Seats', 'Name', 'Email address']) fireEvent.blur(within(dialog()).getByLabelText(label));
    expect(within(dialog()).getByText('Enter a customer name.')).toBeTruthy();
    expect(within(dialog()).getByText('Enter a whole number of seats between 1 and 60.')).toBeTruthy();
    expect(within(dialog()).getByText('Enter a name for the administrator.')).toBeTruthy();
    expect(within(dialog()).getByText('Enter a valid email address.')).toBeTruthy();
    type('Seats', '61');
    expect(within(dialog()).getByText('Enter a whole number of seats between 1 and 60.')).toBeTruthy();
    type('Seats', '2.5');
    expect(within(dialog()).getByText('Enter a whole number of seats between 1 and 60.')).toBeTruthy();
    type('Email address', 'nope');
    expect(within(dialog()).getByText('Enter a valid email address.')).toBeTruthy();
  });

  it('creates the customer, toasts, refetches and closes; screens default to Dashboard only (none sent)', async () => {
    createPartnerCustomer.mockResolvedValue({ customer: customer({ name: 'Globex' }), emailSent: true });
    const props = mount();
    fill();
    click('Create customer');
    expect(within(dialog()).getByRole('button', { name: 'Creating...' })).toBeTruthy();
    await waitFor(() => expect(props.onClose).toHaveBeenCalled());
    expect(createPartnerCustomer).toHaveBeenCalledWith({ name: 'Globex', seats: 5, plan: 'Free', adminName: 'Ada Lovelace', adminEmail: 'ada@globex.example' });
    expect(toast).toHaveBeenCalledWith('Globex was created. An invite was sent to ada@globex.example.', 'success');
    expect(props.onRefetch).toHaveBeenCalled();
  });

  it('sends the screens ticked in the collapsed Choose screens group', async () => {
    createPartnerCustomer.mockResolvedValue({ customer: customer(), emailSent: true });
    mount();
    fill();
    const toggle = within(dialog()).getByRole('button', { name: /Choose screens/ });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(within(dialog()).getByLabelText('Digital Twin'));
    expect(within(dialog()).getByText('1 screen selected')).toBeTruthy();
    click('Create customer');
    await waitFor(() => expect(createPartnerCustomer).toHaveBeenCalled());
    expect(createPartnerCustomer.mock.calls[0][0].enabledFeatures).toEqual(['screen:digitalTwin']);
  });

  it('offers the partner\'s plans with Free selected, explains Free and sends the plan (D-23)', async () => {
    createPartnerCustomer.mockResolvedValue({ customer: customer(), emailSent: true });
    const props = mount({ planCeiling: ['Free', 'Pro'] });
    const plan = within(dialog()).getByLabelText('Plan') as HTMLSelectElement;
    expect(Array.from(plan.options).map(o => o.textContent)).toEqual(['Free', 'Pro']);
    expect(plan.value).toBe('Free');
    expect(within(dialog()).getByText('Free starts a free trial today. The plan decides which screens this customer can have; seats are the number you assign.')).toBeTruthy();
    fill();
    fireEvent.change(plan, { target: { value: 'Pro' } });
    click('Create customer');
    await waitFor(() => expect(props.onClose).toHaveBeenCalled());
    expect(createPartnerCustomer.mock.calls[0][0].plan).toBe('Pro');
  });

  it('defaults the plan to Free when the overview carries no planCeiling', async () => {
    createPartnerCustomer.mockResolvedValue({ customer: customer(), emailSent: true });
    const props = mount();
    expect(Array.from((within(dialog()).getByLabelText('Plan') as HTMLSelectElement).options).map(o => o.textContent)).toEqual(['Free']);
    fill();
    click('Create customer');
    await waitFor(() => expect(props.onClose).toHaveBeenCalled());
    expect(createPartnerCustomer.mock.calls[0][0].plan).toBe('Free');
  });

  it('selects the first plan of the ceiling when Free is not in it', () => {
    mount({ planCeiling: ['Enterprise', 'Pro'] });
    const plan = within(dialog()).getByLabelText('Plan') as HTMLSelectElement;
    expect(Array.from(plan.options).map(o => o.textContent)).toEqual(['Pro', 'Enterprise']);
    expect(plan.value).toBe('Pro');
  });

  it('with no plan to sell replaces the select with a message and disables Create customer', () => {
    mount({ planCeiling: [] });
    expect(within(dialog()).queryByLabelText('Plan')).toBeNull();
    expect(within(dialog()).getByText("Your platform administrator hasn't chosen any plans you can sell. Ask them to set your plans.")).toBeTruthy();
    fill();
    expect((within(dialog()).getByRole('button', { name: 'Create customer' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('says screens outside the chosen plan are refused once Choose screens is opened', () => {
    mount();
    fireEvent.click(within(dialog()).getByRole('button', { name: /Choose screens/ }));
    expect(within(dialog()).getByText('Screens outside the chosen plan are refused.')).toBeTruthy();
  });

  it('shows an empty ceiling message instead of a list', () => {
    mount({ ceiling: [], unrestricted: false });
    fireEvent.click(within(dialog()).getByRole('button', { name: /Choose screens/ }));
    expect(within(dialog()).getByText("Your platform administrator hasn't made any screens available to sell yet. Ask them to set your screen list.")).toBeTruthy();
  });

  it('stays on a result view when the email was not sent, never showing a link, token or registration key', async () => {
    createPartnerCustomer.mockResolvedValue({
      customer: customer(), emailSent: false,
      inviteLink: 'https://x.example/accept?token=SECRET', token: 'SECRET', registrationKey: 'REGKEY',
    });
    const props = mount();
    fill();
    click('Create customer');
    await screen.findByText('Globex was created with 5 seats.');
    expect(within(dialog()).getByText("The invite email couldn't be sent. Ask your platform administrator to share sign-in details with ada@globex.example.")).toBeTruthy();
    expect(props.onClose).not.toHaveBeenCalled();
    expect(props.onRefetch).toHaveBeenCalled();
    expect(dialog().textContent).not.toMatch(/SECRET|REGKEY|token|http/i);
    expect(toast).not.toHaveBeenCalled();
    click('Done');
    expect(props.onClose).toHaveBeenCalled();
  });

  it.each([
    ['name', "That name isn't available."],
    ['email', "That email address can't be used. Use a different one."],
    ['pool full', 'Only 3 seats are free in your pool.'],
    ['expired', "Your seat pool has expired. You can't create customers."],
  ])('shows the %s refusal verbatim, keeps the modal open and refetches', async (_n, message) => {
    createPartnerCustomer.mockRejectedValue(new PartnerApiError(message, 409, 'x'));
    const props = mount();
    fill();
    click('Create customer');
    const alert = await within(dialog()).findByRole('alert');
    expect(alert.textContent).toBe(message);
    expect(props.onClose).not.toHaveBeenCalled();
    expect(props.onRefetch).toHaveBeenCalled();
    expect((within(dialog()).getByRole('button', { name: 'Create customer' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('wraps other server messages and falls back for a network failure', async () => {
    createPartnerCustomer.mockRejectedValueOnce(new PartnerApiError('Server said no.', 500));
    mount();
    fill();
    click('Create customer');
    expect((await within(dialog()).findByRole('alert')).textContent).toBe("Couldn't create this customer: Server said no. Try again.");
    createPartnerCustomer.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    click('Create customer');
    await waitFor(() =>
      expect(within(dialog()).getByRole('alert').textContent).toBe("Couldn't create this customer. Check your connection and try again."));
  });

  it('sends one request for a double click', async () => {
    let resolve: (v: unknown) => void = () => {};
    createPartnerCustomer.mockReturnValue(new Promise(r => { resolve = r; }));
    mount();
    fill();
    const submit = within(dialog()).getByRole('button', { name: 'Create customer' });
    fireEvent.click(submit);
    fireEvent.click(submit);
    expect(createPartnerCustomer).toHaveBeenCalledTimes(1);
    await act(async () => { resolve({ customer: customer(), emailSent: true }); });
  });
});

describe('ChangeSeatsModal (PART-02, PART-04)', () => {
  const mount = (over: Partial<React.ComponentProps<typeof ChangeSeatsModal>> = {}) => {
    const props = { customer: customer(), free: 6, expired: false, onClose: vi.fn(), onRefetch: vi.fn(), ...over };
    render(<ChangeSeatsModal {...props} />);
    return props;
  };

  it('titles the modal for the customer and states used, free and assigned with the range helper', () => {
    mount();
    expect(screen.getByRole('heading', { name: 'Change seats for Globex' })).toBeTruthy();
    expect(within(dialog()).getByText('4 seats in use')).toBeTruthy();
    expect(within(dialog()).getByText('6 free in your pool')).toBeTruthy();
    expect(within(dialog()).getByText('10 assigned now')).toBeTruthy();
    expect(within(dialog()).getByText("You can set between 4 and 16 seats. 4 seats are in use, so this customer can't go below that. Running agents are never cut off.")).toBeTruthy();
    const field = within(dialog()).getByLabelText('Seats') as HTMLInputElement;
    expect(field.value).toBe('10');
    expect(field.min).toBe('4');
    expect(field.max).toBe('16');
    expect((within(dialog()).getByRole('button', { name: 'Save seats' }) as HTMLButtonElement).disabled).toBe(true);
    expect(within(dialog()).getByText('No change.')).toBeTruthy();
  });

  it('refuses below the used floor and above the free ceiling in the contract words', () => {
    mount();
    type('Seats', '3');
    expect(within(dialog()).getByRole('alert').textContent).toBe("Globex uses 4 seats now. You can't set fewer.");
    expect((within(dialog()).getByRole('button', { name: 'Save seats' }) as HTMLButtonElement).disabled).toBe(true);
    type('Seats', '17');
    expect(within(dialog()).getByRole('alert').textContent).toBe('Your pool has 6 seats free, so the most you can set is 16.');
    type('Seats', '2.5');
    expect(within(dialog()).getByRole('alert').textContent).toBe('Enter a whole number of seats.');
    type('Seats', '');
    expect(within(dialog()).getByRole('alert').textContent).toBe('Enter a whole number of seats.');
  });

  it('states the change in plain words, pluralising one seat', () => {
    mount();
    type('Seats', '12');
    expect(within(dialog()).getByText('Takes 2 more seats from your pool.')).toBeTruthy();
    type('Seats', '8');
    expect(within(dialog()).getByText('Returns 2 seats to your pool.')).toBeTruthy();
    type('Seats', '11');
    expect(within(dialog()).getByText('Takes 1 more seat from your pool.')).toBeTruthy();
    type('Seats', '9');
    expect(within(dialog()).getByText('Returns 1 seat to your pool.')).toBeTruthy();
  });

  it('saves, toasts, refetches and closes', async () => {
    changeCustomerSeats.mockResolvedValue(customer({ seatsAssigned: 12 }));
    const props = mount();
    type('Seats', '12');
    click('Save seats');
    expect(within(dialog()).getByRole('button', { name: 'Saving...' })).toBeTruthy();
    await waitFor(() => expect(props.onClose).toHaveBeenCalled());
    expect(changeCustomerSeats).toHaveBeenCalledWith('c1', 12);
    expect(toast).toHaveBeenCalledWith('Seats saved. Globex now has 12 seats.', 'success');
    expect(props.onRefetch).toHaveBeenCalled();
  });

  it.each([
    ['Only 2 seats are free in your pool.'],
    ['Your seat pool has expired. You can\'t hand out seats.'],
  ])('shows the refusal "%s" verbatim and refetches the row', async message => {
    changeCustomerSeats.mockRejectedValue(new PartnerApiError(message, 409, 'x'));
    const props = mount();
    type('Seats', '12');
    click('Save seats');
    expect((await within(dialog()).findByRole('alert')).textContent).toBe(message);
    expect(props.onRefetch).toHaveBeenCalled();
    expect(props.onClose).not.toHaveBeenCalled();
  });

  it('wraps an unnamed failure with the server message', async () => {
    changeCustomerSeats.mockRejectedValue(new PartnerApiError('Customer not found', 404));
    mount();
    type('Seats', '12');
    click('Save seats');
    expect((await within(dialog()).findByRole('alert')).textContent).toBe("Couldn't save seats: Customer not found. Try again.");
  });

  it('disables the field and submit with the amber line when the pool has expired', () => {
    mount({ expired: true });
    expect((within(dialog()).getByLabelText('Seats') as HTMLInputElement).disabled).toBe(true);
    expect((within(dialog()).getByRole('button', { name: 'Save seats' }) as HTMLButtonElement).disabled).toBe(true);
    expect(within(dialog()).getByText("Your seat pool has expired, so seats can't be changed.")).toBeTruthy();
  });

  it('wraps a long customer name in the title', () => {
    mount({ customer: customer({ name: 'L'.repeat(100) }) });
    expect(screen.getByRole('heading').querySelector('.break-words')).toBeTruthy();
  });

  it('says 1 seat is in use for a customer using a single seat', () => {
    mount({ customer: customer({ seatsUsed: 1, seatsAssigned: 1 }), free: 0 });
    expect(within(dialog()).getByText('1 seat in use')).toBeTruthy();
    expect(within(dialog()).getByText("You can set between 1 and 1 seats. 1 seat is in use, so this customer can't go below that. Running agents are never cut off.")).toBeTruthy();
  });
});

describe('ChooseScreensModal (PART-06, D-10, D-19)', () => {
  const mount = () => {
    const props = { customer: customer(), onClose: vi.fn(), onRefetch: vi.fn() };
    render(<ChooseScreensModal {...props} />);
    return props;
  };

  it('shows a skeleton list while the ceiling loads, then the picker in customer mode', async () => {
    fetchCustomerFeatures.mockResolvedValue(features());
    mount();
    expect(screen.getByRole('heading', { name: 'Screens for Globex' })).toBeTruthy();
    expect(dialog().querySelector('[data-skeleton]')).toBeTruthy();
    expect(await within(dialog()).findByLabelText('Digital Twin')).toBeTruthy();
    expect(within(dialog()).queryByLabelText('Log Explorer')).toBeNull();
    expect(within(dialog()).getByText('Always included')).toBeTruthy();
  });

  it('saves the full list, toasts, refetches and closes; Save screens is disabled until something changed', async () => {
    fetchCustomerFeatures.mockResolvedValue(features());
    saveCustomerFeatures.mockResolvedValue(features({ enabledFeatures: ['screen:dashboard', 'screen:digitalTwin'] }));
    const props = mount();
    await within(dialog()).findByLabelText('Digital Twin');
    const save = within(dialog()).getByRole('button', { name: 'Save screens' }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.click(within(dialog()).getByLabelText('Digital Twin'));
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    expect(within(dialog()).getByRole('button', { name: 'Saving...' })).toBeTruthy();
    await waitFor(() => expect(props.onClose).toHaveBeenCalled());
    expect(saveCustomerFeatures).toHaveBeenCalledWith('c1', expect.arrayContaining(['screen:dashboard', 'screen:digitalTwin']));
    expect(toast).toHaveBeenCalledWith('Screens saved for Globex.', 'success');
    expect(props.onRefetch).toHaveBeenCalled();
  });

  it('shows a kept screen outside the ceiling locked with the kept sentence and still sends it', async () => {
    fetchCustomerFeatures.mockResolvedValue(features({ enabledFeatures: ['screen:dashboard', 'view:tracing'], kept: ['view:tracing'] }));
    saveCustomerFeatures.mockResolvedValue(features());
    mount();
    const kept = (await within(dialog()).findByLabelText('Tracing & APM')) as HTMLInputElement;
    expect(kept.checked).toBe(true);
    expect(kept.disabled).toBe(true);
    expect(within(dialog()).getByText("Kept from before. You can't add it again.")).toBeTruthy();
    fireEvent.click(within(dialog()).getByLabelText('Digital Twin'));
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Save screens' }));
    await waitFor(() => expect(saveCustomerFeatures).toHaveBeenCalled());
    expect(saveCustomerFeatures.mock.calls[0][1]).toContain('view:tracing');
  });

  it('shows the empty-ceiling message with the submit disabled', async () => {
    fetchCustomerFeatures.mockResolvedValue(features({ ceiling: [] }));
    mount();
    expect(await within(dialog()).findByText("Your platform administrator hasn't made any screens available to sell yet. Ask them to set your screen list.")).toBeTruthy();
    expect((within(dialog()).getByRole('button', { name: 'Save screens' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows the ceiling refusal verbatim and refetches the features and the row', async () => {
    fetchCustomerFeatures.mockResolvedValue(features());
    const refusal = 'Log Explorer is not one of the screens you can sell.';
    saveCustomerFeatures.mockRejectedValue(new PartnerApiError(refusal, 422, 'screen_outside_ceiling'));
    const props = mount();
    fireEvent.click(await within(dialog()).findByLabelText('Digital Twin'));
    click('Save screens');
    expect((await within(dialog()).findByRole('alert')).textContent).toBe(refusal);
    await waitFor(() => expect(fetchCustomerFeatures).toHaveBeenCalledTimes(2));
    expect(props.onRefetch).toHaveBeenCalled();
    expect(props.onClose).not.toHaveBeenCalled();
  });

  it('wraps an unnamed save failure', async () => {
    fetchCustomerFeatures.mockResolvedValue(features());
    saveCustomerFeatures.mockRejectedValue(new PartnerApiError('Customer not found', 404));
    mount();
    fireEvent.click(await within(dialog()).findByLabelText('Digital Twin'));
    click('Save screens');
    expect((await within(dialog()).findByRole('alert')).textContent).toBe("Couldn't save screens: Customer not found. Try again.");
  });

  it('shows a load error with Try again', async () => {
    fetchCustomerFeatures.mockRejectedValueOnce(new Error('down'));
    mount();
    expect((await within(dialog()).findByRole('alert')).textContent).toContain("Couldn't load the screens. Check your connection and try again.");
    fetchCustomerFeatures.mockResolvedValue(features());
    click('Try again');
    expect(await within(dialog()).findByLabelText('Digital Twin')).toBeTruthy();
  });
});

describe('PartnerPortal wiring of the customer modals', () => {
  const portal = async (data = overview()) => {
    fetchPartnerOverview.mockResolvedValue(data);
    render(<PartnerPortal />);
    await screen.findByText('Seat pool');
    await waitFor(() => expect(document.querySelector('[data-skeleton]')).toBeNull());
  };

  it('opens Create customer from the header, then refetches the overview after a success', async () => {
    createPartnerCustomer.mockResolvedValue({ customer: customer(), emailSent: true });
    await portal();
    fireEvent.click(screen.getByRole('button', { name: 'Create customer' }));
    expect(screen.getByRole('heading', { name: 'Create a customer' })).toBeTruthy();
    type('Customer name', 'Newco');
    type('Seats', '5');
    type('Name', 'Ada');
    type('Email address', 'ada@newco.example');
    fetchPartnerOverview.mockClear();
    click('Create customer');
    await waitFor(() => expect(fetchPartnerOverview).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('opens Change seats and Choose screens for the row with the pool figures', async () => {
    fetchCustomerFeatures.mockResolvedValue(features());
    await portal();
    fireEvent.click(screen.getByRole('button', { name: 'Change seats for Globex' }));
    expect(within(dialog()).getByText('60 free in your pool')).toBeTruthy();
    expect(within(dialog()).getByText(/You can set between 4 and 70 seats\./)).toBeTruthy();
    click('Cancel');
    expect(screen.queryByRole('dialog')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Choose screens for Globex' }));
    expect(screen.getByRole('heading', { name: 'Screens for Globex' })).toBeTruthy();
    await within(dialog()).findByLabelText('Digital Twin');
  });

  it('disables only the open row\'s actions', async () => {
    fetchCustomerFeatures.mockResolvedValue(features());
    await portal(overview({ customers: [customer(), customer({ id: 'c2', name: 'Initech' })] }));
    fireEvent.click(screen.getByRole('button', { name: 'Change seats for Globex' }));
    expect((screen.getByRole('button', { name: 'Change seats for Globex', hidden: true }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: 'Change seats for Initech', hidden: true }) as HTMLButtonElement).disabled).toBe(false);
  });
});

const member = (over: Partial<PartnerTeamMember> = {}): PartnerTeamMember => ({
  id: 'u1', name: 'Ada Admin', email: 'ada@acme.example', role: 'partner_admin', status: 'active', ...over,
});

describe('PartnerTeamPanel (PART-02, D-17; S7)', () => {
  it('shows skeleton rows while loading, then name, email, role and status chip per row', async () => {
    fetchPartnerTeam.mockResolvedValue([
      member(),
      member({ id: 'u2', name: 'Vic Viewer', email: 'vic@acme.example', role: 'partner_viewer', status: 'invited' }),
    ]);
    const { container } = render(<PartnerTeamPanel />);
    expect(screen.getByRole('heading', { name: 'Team' })).toBeTruthy();
    expect(container.querySelectorAll('tr[data-skeleton]').length).toBeGreaterThan(0);
    await screen.findByText('Ada Admin');
    expect(screen.getByText('Partner administrators create customers and change seats. Partner viewers can only look.')).toBeTruthy();
    const vic = screen.getByText('Vic Viewer').closest('tr') as HTMLElement;
    expect(within(vic).getByText('Partner viewer')).toBeTruthy();
    expect(within(vic).getByText('Invited')).toBeTruthy();
    const ada = screen.getByText('Ada Admin').closest('tr') as HTMLElement;
    expect(within(ada).getByText('Partner administrator')).toBeTruthy();
    expect(within(ada).getByText('Active')).toBeTruthy();
    expect(screen.getByText('vic@acme.example').className).toContain('break-all');
  });

  it('offers Resend invite only for Invited and Invite expired', async () => {
    fetchPartnerTeam.mockResolvedValue([
      member(),
      member({ id: 'u2', name: 'Inv', email: 'inv@acme.example', status: 'invited' }),
      member({ id: 'u3', name: 'Exp', email: 'exp@acme.example', status: 'invite_expired' }),
    ]);
    render(<PartnerTeamPanel />);
    await screen.findByText('Inv');
    expect(screen.getByRole('button', { name: 'Resend invite to inv@acme.example' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Resend invite to exp@acme.example' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Resend invite to ada@acme.example' })).toBeNull();
    expect(screen.getByText('Invite expired')).toBeTruthy();
  });

  it('Resend invite shows Sending... then toasts and recovers', async () => {
    fetchPartnerTeam.mockResolvedValue([member({ id: 'u2', name: 'Inv', email: 'inv@acme.example', status: 'invited' })]);
    let resolve: (v: unknown) => void = () => {};
    resendColleagueInvite.mockReturnValue(new Promise(r => { resolve = r; }));
    render(<PartnerTeamPanel />);
    fireEvent.click(await screen.findByRole('button', { name: 'Resend invite to inv@acme.example' }));
    const busy = screen.getByRole('button', { name: 'Resend invite to inv@acme.example' }) as HTMLButtonElement;
    expect(busy.textContent).toBe('Sending...');
    expect(busy.disabled).toBe(true);
    await act(async () => { resolve({ emailSent: true }); });
    expect(resendColleagueInvite).toHaveBeenCalledWith('u2');
    expect(toast).toHaveBeenCalledWith('Invite sent to inv@acme.example.', 'success');
    expect((screen.getByRole('button', { name: 'Resend invite to inv@acme.example' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('Resend invite failure toasts an error and does not claim success', async () => {
    fetchPartnerTeam.mockResolvedValue([member({ id: 'u2', email: 'inv@acme.example', status: 'invited' })]);
    resendColleagueInvite.mockRejectedValue(new PartnerApiError('Nope', 500));
    render(<PartnerTeamPanel />);
    fireEvent.click(await screen.findByRole('button', { name: 'Resend invite to inv@acme.example' }));
    await waitFor(() => expect(toast).toHaveBeenCalled());
    expect(toast.mock.calls[0][1]).toBe('error');
    expect(toast.mock.calls[0][0]).not.toMatch(/^Invite sent/);
  });

  it('shows a red inline block with Try again when the load fails', async () => {
    fetchPartnerTeam.mockRejectedValueOnce(new Error('down'));
    render(<PartnerTeamPanel />);
    expect((await screen.findByRole('alert')).textContent).toContain("Couldn't load your team. Check your connection and try again.");
    fetchPartnerTeam.mockResolvedValue([member()]);
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await screen.findByText('Ada Admin');
  });

  it('opens Invite colleague, and reloads the list after a successful invite', async () => {
    fetchPartnerTeam.mockResolvedValue([member()]);
    inviteColleague.mockResolvedValue({ member: member({ id: 'u9' }), emailSent: true });
    render(<PartnerTeamPanel />);
    await screen.findByText('Ada Admin');
    fireEvent.click(screen.getByRole('button', { name: /Invite colleague/ }));
    type('Name', 'New Person');
    type('Email address', 'new@acme.example');
    fetchPartnerTeam.mockClear();
    click('Send invite');
    await waitFor(() => expect(fetchPartnerTeam).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});

describe('InviteColleagueModal (PART-02, D-17)', () => {
  const mount = () => {
    const props = { onClose: vi.fn(), onInvited: vi.fn() };
    render(<InviteColleagueModal {...props} />);
    return props;
  };

  it('offers the two roles and changes the helper with the value', () => {
    mount();
    expect(screen.getByRole('heading', { name: 'Invite a colleague' })).toBeTruthy();
    const role = within(dialog()).getByLabelText('Role') as HTMLSelectElement;
    expect(Array.from(role.options).map(o => o.textContent)).toEqual(['Partner administrator', 'Partner viewer']);
    expect(within(dialog()).getByText('Can create customers, change seats and invite colleagues. Must set up two-step verification.')).toBeTruthy();
    fireEvent.change(role, { target: { value: 'partner_viewer' } });
    expect(within(dialog()).getByText("Can look at the pool, customers and usage. Can't change anything.")).toBeTruthy();
    expect(within(dialog()).queryByText(/Must set up two-step/)).toBeNull();
  });

  it('validates name and email, with Send invite disabled until valid', () => {
    mount();
    const send = within(dialog()).getByRole('button', { name: 'Send invite' }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    fireEvent.blur(within(dialog()).getByLabelText('Name'));
    fireEvent.blur(within(dialog()).getByLabelText('Email address'));
    expect(within(dialog()).getByText('Enter a name for your colleague.')).toBeTruthy();
    expect(within(dialog()).getByText('Enter a valid email address.')).toBeTruthy();
    type('Name', 'Vic');
    type('Email address', 'vic@acme.example');
    expect(send.disabled).toBe(false);
  });

  it('sends the role, toasts with the 7 day line and closes', async () => {
    inviteColleague.mockResolvedValue({ member: member(), emailSent: true });
    const props = mount();
    type('Name', 'Vic');
    type('Email address', 'vic@acme.example');
    fireEvent.change(within(dialog()).getByLabelText('Role'), { target: { value: 'partner_viewer' } });
    click('Send invite');
    expect(within(dialog()).getByRole('button', { name: 'Sending...' })).toBeTruthy();
    await waitFor(() => expect(props.onClose).toHaveBeenCalled());
    expect(inviteColleague).toHaveBeenCalledWith({ name: 'Vic', email: 'vic@acme.example', role: 'partner_viewer' });
    expect(toast).toHaveBeenCalledWith('Invite sent to vic@acme.example. The link works for 7 days.', 'success');
    expect(props.onInvited).toHaveBeenCalled();
  });

  it('shows the amber block and stays open when the email was not sent, never a link or token', async () => {
    inviteColleague.mockResolvedValue({ member: member(), emailSent: false, inviteLink: 'https://x/a?token=SECRET', token: 'SECRET' });
    const props = mount();
    type('Name', 'Vic');
    type('Email address', 'vic@acme.example');
    click('Send invite');
    expect(await within(dialog()).findByText("The invite email couldn't be sent. Ask your platform administrator for help.")).toBeTruthy();
    expect(dialog().textContent).not.toMatch(/SECRET|token|http/i);
    expect(props.onClose).not.toHaveBeenCalled();
    expect(props.onInvited).toHaveBeenCalled();
  });

  it('shows the generic email refusal verbatim and keeps the modal open', async () => {
    inviteColleague.mockRejectedValue(new PartnerApiError("That email address can't be used. Use a different one.", 409, 'email_unavailable'));
    const props = mount();
    type('Name', 'Vic');
    type('Email address', 'vic@acme.example');
    click('Send invite');
    expect((await within(dialog()).findByRole('alert')).textContent).toBe("That email address can't be used. Use a different one.");
    expect(props.onClose).not.toHaveBeenCalled();
  });

  it('falls back for a network failure', async () => {
    inviteColleague.mockRejectedValue(new TypeError('Failed to fetch'));
    mount();
    type('Name', 'Vic');
    type('Email address', 'vic@acme.example');
    click('Send invite');
    expect((await within(dialog()).findByRole('alert')).textContent).toBe("Couldn't send this invite. Check your connection and try again.");
  });
});

describe('PartnerPortal Team section (admin only)', () => {
  it('mounts the Team panel for an admin, which loads the team itself', async () => {
    fetchPartnerOverview.mockResolvedValue(overview());
    fetchPartnerTeam.mockResolvedValue([member()]);
    render(<PartnerPortal />);
    expect(await screen.findByRole('heading', { name: 'Team' })).toBeTruthy();
    await screen.findByText('Ada Admin');
    expect(fetchPartnerTeam).toHaveBeenCalledTimes(1);
  });

  it('does not mount the Team panel or call fetchPartnerTeam for a viewer', async () => {
    fetchPartnerOverview.mockResolvedValue(overview({ role: 'viewer' }));
    render(<PartnerPortal />);
    await screen.findByText('Seat pool');
    expect(screen.queryByRole('heading', { name: 'Team' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Invite colleague/ })).toBeNull();
    expect(fetchPartnerTeam).not.toHaveBeenCalled();
  });
});
