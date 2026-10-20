/** Sign-up requests in Tenant Management (approval-gated sign-up, 2026-10-20). */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ authFetch: (...args: unknown[]) => authFetch(...args) }));

import { PendingSignupsPanel } from '../../components/PendingSignupsPanel';

const ok = (body: unknown) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
const PENDING = { signups: [{ id: 'tp', name: 'ABC', adminEmail: 'p@abc.test', adminName: 'Pat', requestedAt: '2026-10-20T02:34:23Z' }] };

beforeEach(() => authFetch.mockReset());

describe('PendingSignupsPanel', () => {
  it('stays hidden when nothing waits', async () => {
    authFetch.mockImplementation(() => ok({ signups: [] }));
    const { container } = render(<PendingSignupsPanel />);
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/tenants/signups/pending'));
    expect(container.textContent).toBe('');
  });

  it('approves a request and says what the new admin will see', async () => {
    authFetch.mockImplementation((url: string = '') => ok(String(url).endsWith('/pending') ? PENDING : { approved: 'tp' }));
    const onChanged = vi.fn();
    render(<PendingSignupsPanel onChanged={onChanged} />);
    expect(await screen.findByText('ABC')).toBeTruthy();
    expect(screen.getByText(/Pat · p@abc.test/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    expect(await screen.findByText(/ABC approved/)).toBeTruthy();
    expect(authFetch).toHaveBeenCalledWith('/api/tenants/signups/tp/approve', { method: 'POST' });
    expect(onChanged).toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
  });

  it('asks before rejecting and shows the server refusal', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    authFetch.mockImplementation((url: string = '') => String(url).endsWith('/pending') ? ok(PENDING)
      : Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ detail: 'No pending sign-up for this tenant' }) }));
    render(<PendingSignupsPanel />);
    fireEvent.click(await screen.findByRole('button', { name: 'Reject' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No pending sign-up for this tenant');
    expect(window.confirm).toHaveBeenCalled();
  });
});
