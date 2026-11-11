/**
 * Phase 87 (PART-01, PART-03, PART-07; 87-UI-SPEC section 1): the Super Admin's Appoint and Edit partner
 * form, the Suspend and Reinstate confirmations and the Move customer dialog. The API client is mocked.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('../../services/partnerApi', async () => {
  const actual = await vi.importActual<typeof import('../../services/partnerApi')>('../../services/partnerApi');
  return {
    ...actual,
    appointPartner: vi.fn(),
    updatePartner: vi.fn(),
    suspendPartner: vi.fn(),
    reinstatePartner: vi.fn(),
    moveCustomer: vi.fn(),
    fetchDirectCustomers: vi.fn(),
  };
});
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import * as api from '../../services/partnerApi';
import { PartnerApiError, type PartnerCustomerRow, type PartnerSummary } from '../../services/partnerApi';
import { showToast } from '../../utils/toast';
import { PartnerFormModal } from '../../components/PartnerFormModal';
import { ReinstatePartnerDialog, SuspendPartnerDialog } from '../../components/PartnerStatusDialogs';
import { PartnerMoveCustomerModal } from '../../components/PartnerMoveCustomerModal';

const appointPartner = api.appointPartner as ReturnType<typeof vi.fn>;
const updatePartner = api.updatePartner as ReturnType<typeof vi.fn>;
const toast = showToast as ReturnType<typeof vi.fn>;
const suspendPartner = api.suspendPartner as ReturnType<typeof vi.fn>;
const reinstatePartner = api.reinstatePartner as ReturnType<typeof vi.fn>;
const moveCustomer = api.moveCustomer as ReturnType<typeof vi.fn>;
const fetchDirectCustomers = api.fetchDirectCustomers as ReturnType<typeof vi.fn>;

const partner = (over: Partial<PartnerSummary> = {}): PartnerSummary => ({
  id: 'p1',
  name: 'Acme Resale',
  poolSize: 100,
  allocated: 40,
  free: 60,
  expiresAt: '2027-03-31T23:59:59Z',
  expired: false,
  screenCeiling: ['view:cxo_dashboard'],
  unrestricted: false,
  status: 'active',
  customerCount: 2,
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(cleanup);

const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
const submitButton = (name: string) => screen.getByRole('button', { name }) as HTMLButtonElement;

describe('PartnerFormModal, appoint mode', () => {
  const open = () => {
    const onClose = vi.fn();
    const onSaved = vi.fn();
    render(<PartnerFormModal mode="appoint" onClose={onClose} onSaved={onSaved} />);
    return { onClose, onSaved };
  };
  const fillValid = () => {
    type('Partner name', 'Northwind Channel');
    type('Seat pool', '250');
    type('Name', 'Pat Admin');
    type('Email address', 'pat@northwind.example');
  };

  it('opens with the title, helpers, an empty pool, 0 selected screens and a disabled submit', () => {
    open();
    expect(screen.getByRole('heading', { name: 'Appoint a partner' })).toBeTruthy();
    expect(screen.getByText('The name staff and customers recognise.')).toBeTruthy();
    expect(screen.getByText('How many agent seats this partner can hand out in total.')).toBeTruthy();
    expect(screen.getByText(/Leave empty for no expiry\. After this date the partner can't create customers/)).toBeTruthy();
    expect(screen.getByText(/We email this person a link to set a password\. The link works for 7 days\./)).toBeTruthy();
    expect(screen.getByText(/^0 of \d+ selected$/)).toBeTruthy();
    expect(screen.getByText('Always included')).toBeTruthy();
    expect((screen.getByLabelText('Seat pool') as HTMLInputElement).value).toBe('');
    expect(submitButton('Appoint partner').disabled).toBe(true);
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeTruthy();
  });

  it('shows each validation message on blur', () => {
    open();
    fireEvent.blur(screen.getByLabelText('Partner name'));
    expect(screen.getByText('Enter a partner name.')).toBeTruthy();
    type('Seat pool', '0');
    fireEvent.blur(screen.getByLabelText('Seat pool'));
    expect(screen.getByText('Enter a pool between 1 and 1,000,000 seats.')).toBeTruthy();
    type('Seat pool', '1000001');
    expect(screen.getByText('Enter a pool between 1 and 1,000,000 seats.')).toBeTruthy();
    type('Email address', 'nope');
    fireEvent.blur(screen.getByLabelText('Email address'));
    expect(screen.getByText('Enter a valid email address.')).toBeTruthy();
    fireEvent.blur(screen.getByLabelText('Name'));
    expect(screen.getByText('Enter a name for the administrator.')).toBeTruthy();
    expect(screen.getAllByRole('alert').length).toBeGreaterThanOrEqual(4);
  });

  it('enables submit once valid and sends the form, with the expiry at the end of the day', async () => {
    appointPartner.mockResolvedValue({ partner: partner(), emailSent: true });
    const { onClose, onSaved } = open();
    fillValid();
    type('Pool expires on', '2027-01-31');
    fireEvent.click(screen.getByRole('checkbox', { name: 'CXO Insights' }));
    expect(screen.getByText(/^1 of \d+ selected$/)).toBeTruthy();
    fireEvent.click(submitButton('Appoint partner'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(appointPartner).toHaveBeenCalledWith({
      name: 'Northwind Channel',
      poolSize: 250,
      expiresAt: '2027-01-31T23:59:59Z',
      screenCeiling: ['view:cxo_dashboard'],
      planCeiling: ['Free'],
      adminName: 'Pat Admin',
      adminEmail: 'pat@northwind.example',
    });
    expect(onSaved).toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith('Partner appointed. An invite was sent to pat@northwind.example.', 'success');
  });

  it('sends ["all"] when every screen is ticked and no expiry when the date is empty', async () => {
    appointPartner.mockResolvedValue({ partner: partner(), emailSent: true });
    const { onClose } = open();
    fillValid();
    fireEvent.click(screen.getByRole('button', { name: 'Select all screens' }));
    fireEvent.click(submitButton('Appoint partner'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const sent = appointPartner.mock.calls[0][0];
    expect(sent.screenCeiling).toEqual(['all']);
    expect(sent.expiresAt ?? null).toBeNull();
  });

  it('stays open on a result view naming User Management when the email was not sent', async () => {
    appointPartner.mockResolvedValue({ partner: partner(), emailSent: false });
    const { onClose, onSaved } = open();
    fillValid();
    fireEvent.click(submitButton('Appoint partner'));
    expect(await screen.findByText('Northwind Channel was appointed.')).toBeTruthy();
    expect(
      screen.getByText(
        "The invite email couldn't be sent. Email is not configured on this platform. Set a password for pat@northwind.example in User Management, then share it with them directly.",
      ),
    ).toBeTruthy();
    expect(onSaved).toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(toast).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onClose).toHaveBeenCalled();
  });

  it('wraps a server message and keeps the modal open with the typed values', async () => {
    appointPartner.mockRejectedValue(new PartnerApiError('Enter a name.', 422, 'invalid_name'));
    const { onClose } = open();
    fillValid();
    fireEvent.click(submitButton('Appoint partner'));
    const alert = await screen.findByText("Couldn't appoint this partner: Enter a name. Try again.");
    expect(alert.closest('[role="alert"]')).toBeTruthy();
    expect(onClose).not.toHaveBeenCalled();
    expect((screen.getByLabelText('Partner name') as HTMLInputElement).value).toBe('Northwind Channel');
  });

  it('shows a 409 refusal verbatim', async () => {
    appointPartner.mockRejectedValue(new PartnerApiError("That name isn't available.", 409, 'name_unavailable'));
    open();
    fillValid();
    fireEvent.click(submitButton('Appoint partner'));
    expect(await screen.findByText("That name isn't available.")).toBeTruthy();
  });

  it('falls back to the connection message for a network failure', async () => {
    appointPartner.mockRejectedValue(new TypeError('Failed to fetch'));
    open();
    fillValid();
    fireEvent.click(submitButton('Appoint partner'));
    expect(await screen.findByText("Couldn't appoint this partner. Check your connection and try again.")).toBeTruthy();
  });

  it('disables the fields and ignores Esc and the backdrop while the request is in flight', async () => {
    appointPartner.mockReturnValue(new Promise(() => {}));
    const { onClose } = open();
    fillValid();
    fireEvent.click(submitButton('Appoint partner'));
    expect(await screen.findByRole('button', { name: 'Appointing...' })).toBeTruthy();
    expect((screen.getByLabelText('Partner name') as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText('Email address') as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: 'Cancel' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    fireEvent.mouseDown(screen.getByRole('dialog'));
    expect(onClose).not.toHaveBeenCalled();
  });

  it('closes on Esc when idle, but not on a backdrop click', () => {
    const { onClose } = open();
    fireEvent.mouseDown(screen.getByRole('dialog'));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('lets a 100-character name and a long email wrap in the summary', async () => {
    appointPartner.mockResolvedValue({ partner: partner(), emailSent: false });
    open();
    const longName = 'N'.repeat(100);
    type('Partner name', longName);
    type('Seat pool', '10');
    type('Name', 'Pat');
    type('Email address', `${'a'.repeat(60)}@example.com`);
    fireEvent.click(submitButton('Appoint partner'));
    const line = await screen.findByText(`${longName} was appointed.`);
    expect(line.className).toContain('break-words');
  });

  it('offers Plans this partner can sell with only Free ticked, and sends the plans ticked (LIC-02, D-13)', async () => {
    appointPartner.mockResolvedValue({ partner: partner(), emailSent: true });
    const { onClose } = open();
    expect(screen.getByText('Plans this partner can sell')).toBeTruthy();
    expect(screen.getByText('A partner can only set these plans on its customers. Customers already on another plan stay on it.')).toBeTruthy();
    const box = (n: string) => screen.getByRole('checkbox', { name: n }) as HTMLInputElement;
    expect(['Free', 'Pro', 'Enterprise', 'Custom'].map(n => box(n).checked)).toEqual([true, false, false, false]);
    fillValid();
    fireEvent.click(box('Pro'));
    fireEvent.click(submitButton('Appoint partner'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(appointPartner.mock.calls[0][0].planCeiling).toEqual(['Free', 'Pro']);
  });

  it('shows an amber status, and still saves, when no plan is ticked', async () => {
    appointPartner.mockResolvedValue({ partner: partner(), emailSent: true });
    const { onClose } = open();
    expect(screen.queryByText("No plan ticked: this partner can't create customers or change plans.")).toBeNull();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Free' }));
    const note = screen.getByText("No plan ticked: this partner can't create customers or change plans.");
    expect(note.closest('[role="status"]')).toBeTruthy();
    fillValid();
    fireEvent.click(submitButton('Appoint partner'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(appointPartner.mock.calls[0][0].planCeiling).toEqual([]);
  });

  it('shows the invalid_plan refusal as the stale-page sentence in the red block and keeps the ticks', async () => {
    appointPartner.mockRejectedValue(new PartnerApiError('Unknown plan', 422, 'invalid_plan'));
    const { onClose } = open();
    fillValid();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Enterprise' }));
    fireEvent.click(submitButton('Appoint partner'));
    const block = await screen.findByText("That plan isn't available. Reload the page and try again.");
    expect(block.closest('[role="alert"]')).toBeTruthy();
    expect((screen.getByRole('checkbox', { name: 'Enterprise' }) as HTMLInputElement).checked).toBe(true);
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe('PartnerFormModal, edit mode', () => {
  const open = (over: Partial<PartnerSummary> = {}) => {
    const onClose = vi.fn();
    const onSaved = vi.fn();
    render(<PartnerFormModal mode="edit" partner={partner(over)} onClose={onClose} onSaved={onSaved} />);
    return { onClose, onSaved };
  };

  it('shows the title, the handed-out floor, the saved values and no administrator fields', () => {
    open();
    expect(screen.getByRole('heading', { name: 'Edit Acme Resale' })).toBeTruthy();
    expect((screen.getByLabelText('Partner name') as HTMLInputElement).value).toBe('Acme Resale');
    expect((screen.getByLabelText('Seat pool') as HTMLInputElement).value).toBe('100');
    expect((screen.getByLabelText('Seat pool') as HTMLInputElement).min).toBe('40');
    expect((screen.getByLabelText('Pool expires on') as HTMLInputElement).value).toBe('2027-03-31');
    expect(screen.getByText("40 seats are handed out, so the pool can't go below 40.")).toBeTruthy();
    expect(screen.queryByLabelText('Email address')).toBeNull();
    expect(screen.queryByText('First partner administrator')).toBeNull();
    expect((screen.getByRole('checkbox', { name: 'CXO Insights' }) as HTMLInputElement).checked).toBe(true);
    expect(submitButton('Save partner').disabled).toBe(true);
  });

  it('enables Save partner on a change and sends only what changed', async () => {
    updatePartner.mockResolvedValue(partner({ poolSize: 120 }));
    const { onClose, onSaved } = open();
    type('Seat pool', '120');
    expect(submitButton('Save partner').disabled).toBe(false);
    fireEvent.click(submitButton('Save partner'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(updatePartner).toHaveBeenCalledWith('p1', { poolSize: 120 });
    expect(onSaved).toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith('Partner saved.', 'success');
  });

  it('keeps Save partner disabled again once the change is reverted', () => {
    open();
    type('Seat pool', '120');
    type('Seat pool', '100');
    expect(submitButton('Save partner').disabled).toBe(true);
  });

  it('refuses a pool below the handed-out floor inline and disables submit', () => {
    open();
    type('Seat pool', '30');
    fireEvent.blur(screen.getByLabelText('Seat pool'));
    expect(
      screen.getByText("The pool can't be smaller than the 40 seats already handed out. Ask the partner to take seats back first."),
    ).toBeTruthy();
    expect(submitButton('Save partner').disabled).toBe(true);
  });

  it('sends expiresAt null when the date is cleared, and the end-of-day time when it is changed', async () => {
    updatePartner.mockResolvedValue(partner({ expiresAt: null }));
    const first = open();
    type('Pool expires on', '');
    fireEvent.click(submitButton('Save partner'));
    await waitFor(() => expect(first.onClose).toHaveBeenCalled());
    expect(updatePartner).toHaveBeenLastCalledWith('p1', { expiresAt: null });
    cleanup();
    const second = open();
    type('Pool expires on', '2027-06-30');
    fireEvent.click(submitButton('Save partner'));
    await waitFor(() => expect(second.onClose).toHaveBeenCalled());
    expect(updatePartner).toHaveBeenLastCalledWith('p1', { expiresAt: '2027-06-30T23:59:59Z' });
  });

  it('sends the screen ceiling only when it changed', async () => {
    updatePartner.mockResolvedValue(partner());
    const { onClose } = open();
    fireEvent.click(screen.getByRole('checkbox', { name: 'CXO Insights' }));
    fireEvent.click(submitButton('Save partner'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(updatePartner).toHaveBeenCalledWith('p1', { screenCeiling: [] });
  });

  it('treats an unrestricted partner as every screen ticked and unchanged until edited', () => {
    open({ unrestricted: true, screenCeiling: ['all'] });
    expect(screen.queryByText(/^0 of \d+ selected$/)).toBeNull();
    expect(submitButton('Save partner').disabled).toBe(true);
  });

  it('shows the server 409 about the handed-out floor verbatim in the red block', async () => {
    const refusal = "The pool can't be smaller than the 45 seats already handed out. Ask the partner to take seats back first.";
    updatePartner.mockRejectedValue(new PartnerApiError(refusal, 409, 'pool_below_allocated', { handedOut: 45 }));
    const { onClose } = open();
    type('Seat pool', '50');
    fireEvent.click(submitButton('Save partner'));
    const block = await screen.findByText(refusal);
    expect(block.closest('[role="alert"]')).toBeTruthy();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('wraps other failures as Couldn\'t save this partner', async () => {
    updatePartner.mockRejectedValue(new PartnerApiError('Partner not found', 404));
    open();
    type('Partner name', 'Acme Resale Ltd');
    fireEvent.click(submitButton('Save partner'));
    expect(await screen.findByText("Couldn't save this partner: Partner not found. Try again.")).toBeTruthy();
  });

  it('shows Saving... and blocks Esc while the request is in flight', async () => {
    updatePartner.mockReturnValue(new Promise(() => {}));
    const { onClose } = open();
    type('Seat pool', '120');
    await act(async () => { fireEvent.click(submitButton('Save partner')); });
    expect(screen.getByRole('button', { name: 'Saving...' })).toBeTruthy();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('shows the saved planCeiling ticked and sends only planCeiling when a plan is unticked (LIC-02, D-13)', async () => {
    updatePartner.mockResolvedValue(partner({ planCeiling: ['Free'] }));
    const { onClose } = open({ planCeiling: ['Free', 'Pro'] });
    const box = (n: string) => screen.getByRole('checkbox', { name: n }) as HTMLInputElement;
    expect(['Free', 'Pro', 'Enterprise', 'Custom'].map(n => box(n).checked)).toEqual([true, true, false, false]);
    expect(submitButton('Save partner').disabled).toBe(true);
    fireEvent.click(box('Pro'));
    expect(submitButton('Save partner').disabled).toBe(false);
    fireEvent.click(submitButton('Save partner'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(updatePartner).toHaveBeenCalledWith('p1', { planCeiling: ['Free'] });
  });

  it('reads a partner summary without planCeiling as Free ticked and unchanged', () => {
    open();
    const box = (n: string) => screen.getByRole('checkbox', { name: n }) as HTMLInputElement;
    expect(['Free', 'Pro', 'Enterprise', 'Custom'].map(n => box(n).checked)).toEqual([true, false, false, false]);
    expect(submitButton('Save partner').disabled).toBe(true);
  });
});

describe('Suspend and Reinstate dialogs (D-15)', () => {
  const openSuspend = () => {
    const onClose = vi.fn();
    const onDone = vi.fn();
    render(<SuspendPartnerDialog partner={partner()} onClose={onClose} onDone={onDone} />);
    return { onClose, onDone };
  };
  const openReinstate = () => {
    const onClose = vi.fn();
    const onDone = vi.fn();
    render(<ReinstatePartnerDialog partner={partner({ status: 'suspended' })} onClose={onClose} onDone={onDone} />);
    return { onClose, onDone };
  };

  it('asks Suspend {name}? with the body, the amber audit line and a red confirm', () => {
    openSuspend();
    expect(screen.getByRole('heading', { name: 'Suspend Acme Resale?' })).toBeTruthy();
    expect(
      screen.getByText(
        "Everyone at this partner is signed out now and can't sign in until you reinstate it. Its customers are not affected: they keep their seats and keep running.",
      ),
    ).toBeTruthy();
    const audit = screen.getByText('This is recorded in the audit log with your name.');
    expect(audit.closest('[role="status"]')).toBeTruthy();
    expect(submitButton('Suspend partner').className).toContain('bg-red-600');
    expect(screen.queryByRole('button', { name: 'Close dialog' })).toBeNull();
  });

  it('suspends, toasts, refreshes and closes', async () => {
    suspendPartner.mockResolvedValue(partner({ status: 'suspended' }));
    const { onClose, onDone } = openSuspend();
    fireEvent.click(submitButton('Suspend partner'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(suspendPartner).toHaveBeenCalledWith('p1');
    expect(onDone).toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith('Acme Resale is suspended.', 'success');
  });

  it('shows Suspending..., disables both buttons and ignores Esc and the backdrop in flight', async () => {
    suspendPartner.mockReturnValue(new Promise(() => {}));
    const { onClose } = openSuspend();
    fireEvent.click(submitButton('Suspend partner'));
    const pending = await screen.findByRole('button', { name: 'Suspending...' });
    expect((pending as HTMLButtonElement).disabled).toBe(true);
    expect(submitButton('Cancel').disabled).toBe(true);
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    fireEvent.mouseDown(screen.getByRole('dialog'));
    expect(onClose).not.toHaveBeenCalled();
  });

  it('keeps the dialog open with the server message when suspending fails', async () => {
    suspendPartner.mockRejectedValue(new PartnerApiError("Couldn't sign this partner's users out", 500));
    const { onClose } = openSuspend();
    fireEvent.click(submitButton('Suspend partner'));
    const block = await screen.findByText("Couldn't suspend this partner: Couldn't sign this partner's users out. Try again.");
    expect(block.closest('[role="alert"]')).toBeTruthy();
    expect(onClose).not.toHaveBeenCalled();
    expect(submitButton('Suspend partner').disabled).toBe(false);
  });

  it('falls back to the connection message when there is no server message', async () => {
    suspendPartner.mockRejectedValue(new TypeError('Failed to fetch'));
    openSuspend();
    fireEvent.click(submitButton('Suspend partner'));
    expect(await screen.findByText("Couldn't suspend this partner. Check your connection and try again.")).toBeTruthy();
  });

  it('asks Reinstate {name}? with an accent confirm and reinstates', async () => {
    reinstatePartner.mockResolvedValue(partner());
    const { onClose, onDone } = openReinstate();
    expect(screen.getByRole('heading', { name: 'Reinstate Acme Resale?' })).toBeTruthy();
    expect(screen.getByText('Its staff can sign in again. Seats, customers and the pool are unchanged.')).toBeTruthy();
    expect(submitButton('Reinstate partner').className).toContain('bg-primary-600');
    expect(submitButton('Reinstate partner').className).not.toContain('bg-red-600');
    fireEvent.click(submitButton('Reinstate partner'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(reinstatePartner).toHaveBeenCalledWith('p1');
    expect(onDone).toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith('Acme Resale is reinstated.', 'success');
  });

  it('shows Reinstating... in flight and the failure wording on error', async () => {
    reinstatePartner.mockReturnValueOnce(new Promise(() => {}));
    openReinstate();
    fireEvent.click(submitButton('Reinstate partner'));
    expect(await screen.findByRole('button', { name: 'Reinstating...' })).toBeTruthy();
    cleanup();
    reinstatePartner.mockRejectedValueOnce(new PartnerApiError('Partner not found', 404));
    openReinstate();
    fireEvent.click(submitButton('Reinstate partner'));
    expect(await screen.findByText("Couldn't reinstate this partner: Partner not found. Try again.")).toBeTruthy();
  });

  it('wraps a long partner name in the title and body', () => {
    const long = 'L'.repeat(120);
    render(<SuspendPartnerDialog partner={partner({ name: long })} onClose={vi.fn()} onDone={vi.fn()} />);
    const heading = screen.getByRole('heading', { name: `Suspend ${long}?` });
    expect(heading.querySelector('.break-words')).toBeTruthy();
  });
});

describe('PartnerMoveCustomerModal, move mode (D-11, D-18, D-19)', () => {
  const globex: PartnerCustomerRow = {
    id: 'c1', name: 'Globex', seatsAssigned: 25, seatsUsed: 10, agentsOnline: 4, agentsTotal: 9, licenseExpiresAt: null,
  };
  const partners = [
    partner({ id: 'p1', name: 'Acme Resale', free: 60 }),
    partner({ id: 'p2', name: 'Beta', free: 30 }),
    partner({ id: 'p3', name: 'Gamma', free: 5 }),
    partner({ id: 'p4', name: 'Dormant', free: 100, status: 'suspended' }),
  ];
  const open = () => {
    const onClose = vi.fn();
    const onMoved = vi.fn();
    render(
      <PartnerMoveCustomerModal mode="move" partner={partners[0]} customer={globex} partners={partners} onClose={onClose} onMoved={onMoved} />,
    );
    return { onClose, onMoved };
  };
  const choose = (value: string) => fireEvent.change(screen.getByLabelText('Move to'), { target: { value } });

  it('shows the summary, the audit and D-19 block, and every other active partner then No partner', () => {
    open();
    expect(screen.getByRole('heading', { name: 'Move Globex' })).toBeTruthy();
    expect(screen.getByText('Currently with Acme Resale')).toBeTruthy();
    expect(screen.getByText('25 seats assigned, 10 in use')).toBeTruthy();
    expect(
      screen.getByText(
        'This is recorded in the audit log with your name. Screens the customer already has stay on, even if this partner may not sell them.',
      ),
    ).toBeTruthy();
    const labels = Array.from((screen.getByLabelText('Move to') as HTMLSelectElement).options).map(o => o.textContent);
    expect(labels).toContain('Beta (30 free)');
    expect(labels).toContain('Gamma (5 free)');
    expect(labels[labels.length - 1]).toBe('No partner (direct customer)');
    expect(labels.some(l => l?.startsWith('Acme Resale'))).toBe(false);
    expect(labels.some(l => l?.startsWith('Dormant'))).toBe(false);
    expect(submitButton('Move customer').disabled).toBe(true);
    expect(submitButton('Move customer').className).not.toContain('bg-red-600');
  });

  it('states the seat consequence for a partner that can take the seats, then moves', async () => {
    moveCustomer.mockResolvedValue({});
    const { onClose, onMoved } = open();
    choose('p2');
    expect(
      screen.getByText("Globex keeps its 25 seats. They are taken from Beta's pool (30 free) and returned to Acme Resale's pool."),
    ).toBeTruthy();
    expect(submitButton('Move customer').disabled).toBe(false);
    fireEvent.click(submitButton('Move customer'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(moveCustomer).toHaveBeenCalledWith('c1', 'p2');
    expect(onMoved).toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith('Globex moved to Beta.', 'success');
  });

  it('refuses a target that cannot fit the seats and disables submit', () => {
    open();
    choose('p3');
    const alert = screen.getByText("Gamma has 5 seats free and Globex needs 25. Increase Gamma's pool first.");
    expect(alert.closest('[role="alert"]')).toBeTruthy();
    expect(submitButton('Move customer').disabled).toBe(true);
  });

  it('turns the customer into a direct one with the direct consequence line', async () => {
    moveCustomer.mockResolvedValue({});
    const { onClose } = open();
    choose('__direct__');
    expect(
      screen.getByText("Globex becomes a direct customer and keeps its 25 seats as its own licence. The seats return to Acme Resale's pool."),
    ).toBeTruthy();
    fireEvent.click(submitButton('Move customer'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(moveCustomer).toHaveBeenCalledWith('c1', null);
    expect(toast).toHaveBeenCalledWith('Globex is now a direct customer.', 'success');
  });

  it('shows the server 409 verbatim when the seat race is lost, and stays open', async () => {
    const refusal = "Beta has 3 seats free and Globex needs 25. Increase Beta's pool first.";
    moveCustomer.mockRejectedValue(new PartnerApiError(refusal, 409, 'pool_full', { free: 3 }));
    const { onClose } = open();
    choose('p2');
    fireEvent.click(submitButton('Move customer'));
    const block = await screen.findByText(refusal);
    expect(block.closest('[role="alert"]')).toBeTruthy();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('wraps other failures and falls back for a network error', async () => {
    moveCustomer.mockRejectedValueOnce(new PartnerApiError('Customer not found', 404));
    open();
    choose('p2');
    fireEvent.click(submitButton('Move customer'));
    expect(await screen.findByText("Couldn't move this customer: Customer not found. Try again.")).toBeTruthy();
    moveCustomer.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    fireEvent.click(submitButton('Move customer'));
    await waitFor(() => expect(screen.getByText("Couldn't move this customer. Check your connection and try again.")).toBeTruthy());
  });

  it('shows Moving..., disables the fields and both buttons, and ignores Esc in flight', async () => {
    moveCustomer.mockReturnValue(new Promise(() => {}));
    const { onClose } = open();
    choose('p2');
    fireEvent.click(submitButton('Move customer'));
    expect(await screen.findByRole('button', { name: 'Moving...' })).toBeTruthy();
    expect((screen.getByLabelText('Move to') as HTMLSelectElement).disabled).toBe(true);
    expect(submitButton('Cancel').disabled).toBe(true);
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe('PartnerMoveCustomerModal, add mode (D-19 Add an existing organization)', () => {
  const beta = partner({ id: 'p2', name: 'Beta', free: 30 });
  const open = () => {
    const onClose = vi.fn();
    const onMoved = vi.fn();
    render(<PartnerMoveCustomerModal mode="add" partner={beta} partners={[beta]} onClose={onClose} onMoved={onMoved} />);
    return { onClose, onMoved };
  };

  it('lists direct customers only, checks the fit against the partner and adds the organization', async () => {
    fetchDirectCustomers.mockResolvedValue([
      { id: 'd1', name: 'Direct One', seatsAssigned: 12 },
      { id: 'd2', name: 'Direct Two', seatsAssigned: 40 },
    ]);
    moveCustomer.mockResolvedValue({});
    const { onClose, onMoved } = open();
    expect(screen.getByRole('heading', { name: 'Add an organization to Beta' })).toBeTruthy();
    const select = (await screen.findByLabelText('Organization')) as HTMLSelectElement;
    await waitFor(() => expect(Array.from(select.options).map(o => o.textContent)).toContain('Direct One (12 seats)'));
    expect(Array.from(select.options).map(o => o.textContent)).toContain('Direct Two (40 seats)');
    fireEvent.change(select, { target: { value: 'd2' } });
    expect(screen.getByText("Beta has 30 seats free and Direct Two needs 40. Increase Beta's pool first.")).toBeTruthy();
    expect(submitButton('Move customer').disabled).toBe(true);
    fireEvent.change(select, { target: { value: 'd1' } });
    expect(submitButton('Move customer').disabled).toBe(false);
    fireEvent.click(submitButton('Move customer'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(moveCustomer).toHaveBeenCalledWith('d1', 'p2');
    expect(onMoved).toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith('Direct One moved to Beta.', 'success');
  });

  it('says Every organization already has a partner. when there are no direct customers', async () => {
    fetchDirectCustomers.mockResolvedValue([]);
    open();
    expect(await screen.findByText('Every organization already has a partner.')).toBeTruthy();
    expect(submitButton('Move customer').disabled).toBe(true);
  });

  it('adds a text filter above 20 entries', async () => {
    fetchDirectCustomers.mockResolvedValue(
      Array.from({ length: 21 }, (_, i) => ({ id: `d${i}`, name: `Org ${String(i).padStart(2, '0')}`, seatsAssigned: 1 })),
    );
    open();
    const filter = await screen.findByLabelText('Filter organizations');
    fireEvent.change(filter, { target: { value: 'org 07' } });
    const select = screen.getByLabelText('Organization') as HTMLSelectElement;
    const labels = Array.from(select.options).map(o => o.textContent);
    expect(labels).toContain('Org 07 (1 seat)');
    expect(labels).not.toContain('Org 00 (1 seat)');
  });

  it('shows no filter at 20 entries or fewer', async () => {
    fetchDirectCustomers.mockResolvedValue(
      Array.from({ length: 20 }, (_, i) => ({ id: `d${i}`, name: `Org ${i}`, seatsAssigned: 1 })),
    );
    open();
    await screen.findByLabelText('Organization');
    await waitFor(() => expect(screen.getByLabelText('Organization')).toBeTruthy());
    expect(screen.queryByLabelText('Filter organizations')).toBeNull();
  });

  it('shows a red block when the direct customers cannot be loaded', async () => {
    fetchDirectCustomers.mockRejectedValue(new Error('down'));
    open();
    expect(await screen.findByText("Couldn't load the organizations. Check your connection and try again.")).toBeTruthy();
  });
});
