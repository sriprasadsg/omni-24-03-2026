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
    const select = screen.getByLabelText('Subscription Tier') as HTMLSelectElement;
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
    fireEvent.change(screen.getByLabelText('Subscription Tier'), { target: { value: 'Custom' } });
    fireEvent.change(screen.getByLabelText(/Seats/), { target: { value: '40' } });
    fireEvent.click(screen.getByText('Create Tenant'));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(onSave.mock.calls[0][0]).toEqual({ name: 'Globex', subscriptionTier: 'Custom', maxAgents: 40 });
  });

  it('Custom refuses a missing or non-whole seat count and sends nothing', () => {
    const onSave = vi.fn();
    render(<AddNewTenantModal isOpen onClose={() => {}} onSave={onSave} />);
    fillName('Globex');
    fireEvent.change(screen.getByLabelText('Subscription Tier'), { target: { value: 'Custom' } });
    fireEvent.change(screen.getByLabelText(/Seats/), { target: { value: '2.5' } });
    fireEvent.submit(document.getElementById('add-tenant-form')!);
    expect(screen.getByText('Seats must be a whole number from 0 to 1,000,000.')).toBeTruthy();
    expect(onSave).not.toHaveBeenCalled();
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
