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
import { PartnerApiError, type PartnerSummary } from '../../services/partnerApi';
import { showToast } from '../../utils/toast';
import { PartnerFormModal } from '../../components/PartnerFormModal';

const appointPartner = api.appointPartner as ReturnType<typeof vi.fn>;
const updatePartner = api.updatePartner as ReturnType<typeof vi.fn>;
const toast = showToast as ReturnType<typeof vi.fn>;

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
});
