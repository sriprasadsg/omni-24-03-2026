/**
 * Phase 87 (PART-02, D-09, D-17, D-20; 87-UI-SPEC section 3): the public Accept invite page. The API client is
 * mocked; the token must leave the address bar before any request, every state shows its contract words, and
 * the page never builds MFA UI of its own.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

vi.mock('../../services/partnerApi', async () => {
  const actual = await vi.importActual<typeof import('../../services/partnerApi')>('../../services/partnerApi');
  return { ...actual, fetchInviteStatus: vi.fn(), acceptInvite: vi.fn() };
});

import * as api from '../../services/partnerApi';
import type { InviteStatus } from '../../services/partnerApi';
import AcceptInvitePage from '../../components/AcceptInvitePage';

const fetchInviteStatus = api.fetchInviteStatus as ReturnType<typeof vi.fn>;

const validStatus: InviteStatus = {
  state: 'valid',
  organizationName: 'Northwind Traders',
  email: 'jo@northwind.example',
  roleKind: 'partner_admin',
};

const originalLocation = window.location;
let replaceState: ReturnType<typeof vi.spyOn>;

function openLink(search = '?token=abc123') {
  window.history.pushState({}, '', `/accept-invite${search}`);
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...originalLocation, search, pathname: '/accept-invite', replace: vi.fn(), assign: vi.fn() },
  });
}

beforeEach(() => {
  fetchInviteStatus.mockReset();
  replaceState = vi.spyOn(window.history, 'replaceState');
  openLink();
});

afterEach(() => {
  cleanup();
  replaceState.mockRestore();
  Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
});

describe('AcceptInvitePage link check (PART-02, D-17)', () => {
  it('removes the token from the address bar before the status request is made', async () => {
    const order: string[] = [];
    replaceState.mockImplementation(() => { order.push('replaceState'); });
    fetchInviteStatus.mockImplementation(async () => { order.push('status'); return validStatus; });
    render(<AcceptInvitePage />);
    await screen.findByRole('heading', { name: 'Set your password' });
    expect(order).toEqual(['replaceState', 'status']);
    expect(replaceState).toHaveBeenCalledWith({}, '', '/accept-invite');
    expect(fetchInviteStatus).toHaveBeenCalledWith('abc123');
  });

  it('shows Checking your invite... with a busy skeleton while the status call is in flight', async () => {
    fetchInviteStatus.mockReturnValue(new Promise(() => {}));
    const { container } = render(<AcceptInvitePage />);
    expect(screen.getByRole('heading', { level: 1, name: 'Checking your invite...' })).toBeTruthy();
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(container.querySelector('.h-4.w-48')).not.toBeNull();
  });

  it('shows the welcome line with the organization name and the read-only email for a valid invite', async () => {
    fetchInviteStatus.mockResolvedValue(validStatus);
    render(<AcceptInvitePage />);
    await screen.findByRole('heading', { name: 'Set your password' });
    expect(screen.getByText('Welcome to Northwind Traders. Choose a password to finish setting up your account.')).toBeTruthy();
    expect(screen.getByText('Email address')).toBeTruthy();
    expect(screen.getByText('jo@northwind.example')).toBeTruthy();
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('shows the Expired state with a secondary Go to sign in and no form', async () => {
    fetchInviteStatus.mockResolvedValue({ state: 'expired' });
    render(<AcceptInvitePage />);
    await screen.findByRole('heading', { name: 'This invite has expired' });
    expect(screen.getByText('Invite links work for 7 days. Ask the person who invited you to send a new one.')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Go to sign in' }).getAttribute('href')).toBe('/login');
    expect(screen.queryByLabelText('New password')).toBeNull();
  });

  it('shows the Used state', async () => {
    fetchInviteStatus.mockResolvedValue({ state: 'used' });
    render(<AcceptInvitePage />);
    await screen.findByRole('heading', { name: 'This invite was already used' });
    expect(
      screen.getByText('If you have set your password, sign in below. If you did not, ask the person who invited you to send a new link.'),
    ).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Go to sign in' }).getAttribute('href')).toBe('/login');
  });

  it('shows the Invalid state for the invalid answer and for a state it cannot classify', async () => {
    fetchInviteStatus.mockResolvedValue({ state: 'invalid' });
    const first = render(<AcceptInvitePage />);
    await screen.findByRole('heading', { name: "This invite link isn't valid" });
    expect(
      screen.getByText('Check that you opened the whole link from your email, or ask the person who invited you to send a new one.'),
    ).toBeTruthy();
    first.unmount();

    openLink();
    fetchInviteStatus.mockResolvedValue({ state: 'something-new' });
    render(<AcceptInvitePage />);
    await screen.findByRole('heading', { name: "This invite link isn't valid" });
    expect(screen.queryByLabelText('New password')).toBeNull();
  });

  it('shows Invalid and makes no status request when there is no token', async () => {
    openLink('');
    render(<AcceptInvitePage />);
    await screen.findByRole('heading', { name: "This invite link isn't valid" });
    expect(fetchInviteStatus).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('New password')).toBeNull();
  });

  it('shows the network error block when the status request fails', async () => {
    fetchInviteStatus.mockRejectedValue(new TypeError('Failed to fetch'));
    render(<AcceptInvitePage />);
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain("Couldn't reach the platform. Check your connection and try again.");
  });

  it('moves focus to the state heading when the state changes', async () => {
    fetchInviteStatus.mockResolvedValue({ state: 'expired' });
    render(<AcceptInvitePage />);
    const heading = await screen.findByRole('heading', { level: 1, name: 'This invite has expired' });
    await waitFor(() => expect(document.activeElement).toBe(heading));
  });

  it('renders a long organization name and email as wrapping text, never as markup', async () => {
    const organizationName = `<b>${'Acme'.repeat(25)}</b>`;
    const email = `${'a'.repeat(80)}@${'b'.repeat(60)}.example`;
    fetchInviteStatus.mockResolvedValue({ ...validStatus, organizationName, email });
    render(<AcceptInvitePage />);
    await screen.findByRole('heading', { name: 'Set your password' });
    const welcome = screen.getByText(new RegExp('^Welcome to <b>Acme'));
    expect(welcome.className).toContain('break-words');
    expect(welcome.querySelector('b')).toBeNull();
    expect(screen.getByText(email).className).toContain('break-all');
  });
});
