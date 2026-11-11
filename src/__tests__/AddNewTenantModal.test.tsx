/**
 * Phase 88 (LIC-02, D-24): a new organization starts on Free; Custom asks for a seat number and sends it
 * as maxAgents; apiService.addTenant posts Free when no plan is given and forwards maxAgents.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AddNewTenantModal } from '../../components/AddNewTenantModal';
import { addTenant } from '../../services/apiService';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const fillName = (name: string) => fireEvent.change(screen.getByLabelText('Company Name'), { target: { value: name } });

describe('AddNewTenantModal plan choice', () => {
  it('opens on Free and offers the four plans', () => {
    render(<AddNewTenantModal isOpen onClose={() => {}} onSave={() => {}} />);
    const select = screen.getByLabelText('Plan') as HTMLSelectElement;
    expect(select.value).toBe('Free');
    expect([...select.options].map(o => o.value)).toEqual(['Free', 'Pro', 'Enterprise', 'Custom']);
    expect(screen.queryByLabelText(/Seats/)).toBeNull();
  });

  it('saves a Free tenant with no seat count', async () => {
    const onSave = vi.fn();
    render(<AddNewTenantModal isOpen onClose={() => {}} onSave={onSave} />);
    fillName('Acme');
    fireEvent.click(screen.getByText('Create Tenant'));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(onSave.mock.calls[0][0]).toEqual({ name: 'Acme', subscriptionTier: 'Free' });
    expect('maxAgents' in onSave.mock.calls[0][0]).toBe(false);
  });

  it('Custom asks for seats and sends them as maxAgents', async () => {
    const onSave = vi.fn();
    render(<AddNewTenantModal isOpen onClose={() => {}} onSave={onSave} />);
    fillName('Globex');
    fireEvent.change(screen.getByLabelText('Plan'), { target: { value: 'Custom' } });
    fireEvent.change(screen.getByLabelText(/Seats/), { target: { value: '40' } });
    fireEvent.click(screen.getByText('Create Tenant'));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(onSave.mock.calls[0][0]).toEqual({ name: 'Globex', subscriptionTier: 'Custom', maxAgents: 40 });
  });

  it('Custom refuses a missing or non-whole seat count and sends nothing', () => {
    const onSave = vi.fn();
    render(<AddNewTenantModal isOpen onClose={() => {}} onSave={onSave} />);
    fillName('Globex');
    fireEvent.change(screen.getByLabelText('Plan'), { target: { value: 'Custom' } });
    fireEvent.change(screen.getByLabelText(/Seats/), { target: { value: '2.5' } });
    fireEvent.submit(document.getElementById('add-tenant-form')!);
    expect(screen.getByText('Seats must be a whole number from 0 to 1,000,000.')).toBeTruthy();
    expect(onSave).not.toHaveBeenCalled();
  });
});

describe('AddNewTenantModal UI-SPEC S3 (G-13, G-17, G-18)', () => {
  it('labels the select Plan and explains what each plan means', () => {
    render(<AddNewTenantModal isOpen onClose={() => {}} onSave={() => {}} />);
    expect(screen.queryByText('Subscription Tier')).toBeNull();
    expect(screen.getByText('Starts a free trial today. Seats and screens follow the Free plan.')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Plan'), { target: { value: 'Pro' } });
    expect(screen.getByText('Seats and screens follow the Pro plan. Tick screens one by one in Manage Tenant.')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Plan'), { target: { value: 'Enterprise' } });
    expect(screen.getByText('Seats and screens follow the Enterprise plan. Tick screens one by one in Manage Tenant.')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Plan'), { target: { value: 'Custom' } });
    expect(screen.getByText('Set per tenant by contract. Tick screens one by one in Manage Tenant.')).toBeTruthy();
    expect(screen.getByText('The seat limit from the contract. 0 means no computer can enroll.')).toBeTruthy();
  });

  it('a refused create keeps the modal open with the typed values and shows the server sentence', async () => {
    const onClose = vi.fn();
    const onSave = vi.fn().mockRejectedValue(new Error('A tenant named "Acme" already exists.'));
    render(<AddNewTenantModal isOpen onClose={onClose} onSave={onSave} />);
    fillName('Acme');
    fireEvent.change(screen.getByLabelText('Plan'), { target: { value: 'Custom' } });
    fireEvent.change(screen.getByLabelText(/Seats/), { target: { value: '40' } });
    fireEvent.click(screen.getByText('Create Tenant'));
    const alert = await waitFor(() => screen.getByText('A tenant named "Acme" already exists.'));
    expect(alert.closest('[role="alert"]')).toBeTruthy();
    expect(onClose).not.toHaveBeenCalled();
    expect((screen.getByLabelText('Company Name') as HTMLInputElement).value).toBe('Acme');
    expect((screen.getByLabelText('Plan') as HTMLSelectElement).value).toBe('Custom');
    expect((screen.getByLabelText(/Seats/) as HTMLInputElement).value).toBe('40');
    expect((screen.getByText('Create Tenant') as HTMLButtonElement).disabled).toBe(false);
  });

  it('clears the refusal on the next attempt and closes when it succeeds', async () => {
    const onClose = vi.fn();
    const onSave = vi.fn().mockRejectedValueOnce(new Error('Nope.')).mockResolvedValueOnce(undefined);
    render(<AddNewTenantModal isOpen onClose={onClose} onSave={onSave} />);
    fillName('Acme');
    fireEvent.click(screen.getByText('Create Tenant'));
    await waitFor(() => screen.getByText('Nope.'));
    fireEvent.click(screen.getByText('Create Tenant'));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('Nope.')).toBeNull();
  });
});

describe('apiService.addTenant (D-24)', () => {
  const stubFetch = () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ id: 't9', name: 'X' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
  };

  it('posts subscriptionTier Free when none is given', async () => {
    const fetchMock = stubFetch();
    await addTenant({ name: 'X' });
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({ name: 'X', subscriptionTier: 'Free' });
  });

  it('forwards maxAgents when given', async () => {
    const fetchMock = stubFetch();
    await addTenant({ name: 'X', subscriptionTier: 'Custom', maxAgents: 40 });
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({ name: 'X', subscriptionTier: 'Custom', maxAgents: 40 });
  });
});
