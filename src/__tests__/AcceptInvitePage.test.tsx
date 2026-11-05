/**
 * Phase 87 (PART-02, D-09, D-17, D-20; 87-UI-SPEC section 3): the public Accept invite page. The API client is
 * mocked; the token must leave the address bar before any request, every state shows its contract words, and
 * the page never builds MFA UI of its own.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('../../services/partnerApi', async () => {
  const actual = await vi.importActual<typeof import('../../services/partnerApi')>('../../services/partnerApi');
  return { ...actual, fetchInviteStatus: vi.fn(), acceptInvite: vi.fn() };
});

vi.mock('../../services/apiService', async () => {
  const actual = await vi.importActual<typeof import('../../services/apiService')>('../../services/apiService');
  return { ...actual, login: vi.fn() };
});

import * as api from '../../services/partnerApi';
import * as apiService from '../../services/apiService';
import { PartnerApiError, type InviteStatus } from '../../services/partnerApi';
import AcceptInvitePage from '../../components/AcceptInvitePage';

const fetchInviteStatus = api.fetchInviteStatus as ReturnType<typeof vi.fn>;
const acceptInvite = api.acceptInvite as ReturnType<typeof vi.fn>;
const login = apiService.login as ReturnType<typeof vi.fn>;
const GOOD = 'Str0ng!pass';

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
  acceptInvite.mockReset();
  login.mockReset();
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

  it('Try again after a network failure asks the status again with the token kept in memory', async () => {
    fetchInviteStatus.mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(validStatus);
    render(<AcceptInvitePage />);
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await screen.findByRole('heading', { name: 'Set your password' });
    expect(fetchInviteStatus).toHaveBeenCalledTimes(2);
    expect(fetchInviteStatus).toHaveBeenLastCalledWith('abc123');
    expect(replaceState).toHaveBeenCalledTimes(1);
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

async function openForm(status: InviteStatus = validStatus) {
  fetchInviteStatus.mockResolvedValue(status);
  render(<AcceptInvitePage />);
  await screen.findByRole('heading', { name: 'Set your password' });
}

const newPassword = () => screen.getByLabelText('New password') as HTMLInputElement;
const confirmPassword = () => screen.getByLabelText('Confirm password') as HTMLInputElement;
const submit = () => screen.getByRole('button', { name: /^Set password$|^Setting password\.\.\.$/ }) as HTMLButtonElement;

function fill(password: string, confirm = password) {
  fireEvent.change(newPassword(), { target: { value: password } });
  fireEvent.change(confirmPassword(), { target: { value: confirm } });
}

describe('AcceptInvitePage password form (PART-02, D-20)', () => {
  it('has two new-password fields, a visible label for each, and focus starts on the heading', async () => {
    await openForm();
    expect(newPassword().type).toBe('password');
    expect(newPassword().getAttribute('autocomplete')).toBe('new-password');
    expect(confirmPassword().type).toBe('password');
    expect(confirmPassword().getAttribute('autocomplete')).toBe('new-password');
    expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1 }));
  });

  it('shows the five rules, each meeting live as the password is typed', async () => {
    await openForm();
    const rules = ['At least 8 characters', 'An uppercase letter', 'A lowercase letter', 'A digit', 'A special character'];
    const list = screen.getByRole('list', { name: 'Password rules' });
    expect(within(list).getAllByRole('listitem').map(li => li.textContent)).toEqual(rules);
    const met = (label: string) => screen.getByText(label).closest('li')!.getAttribute('data-met');
    expect(rules.map(met)).toEqual(['false', 'false', 'false', 'false', 'false']);
    fireEvent.change(newPassword(), { target: { value: 'abcdefgh' } });
    expect(rules.map(met)).toEqual(['true', 'false', 'true', 'false', 'false']);
    fireEvent.change(newPassword(), { target: { value: GOOD } });
    expect(rules.map(met)).toEqual(['true', 'true', 'true', 'true', 'true']);
  });

  it('announces rule changes politely only after the field was touched', async () => {
    await openForm();
    const list = screen.getByRole('list', { name: 'Password rules' });
    expect(list.getAttribute('aria-live')).toBeNull();
    fireEvent.change(newPassword(), { target: { value: 'a' } });
    expect(list.getAttribute('aria-live')).toBe('polite');
  });

  it('keeps Set password disabled until every rule is met and both fields match', async () => {
    await openForm();
    expect(submit().disabled).toBe(true);
    fill('abcdefgh');
    expect(submit().disabled).toBe(true);
    fill(GOOD, 'Different1!');
    expect(submit().disabled).toBe(true);
    expect(screen.getByText("The passwords don't match.")).toBeTruthy();
    fill(GOOD);
    expect(submit().disabled).toBe(false);
    expect(screen.queryByText("The passwords don't match.")).toBeNull();
  });

  it('does not show the mismatch message before the confirm field has something in it', async () => {
    await openForm();
    fireEvent.change(newPassword(), { target: { value: GOOD } });
    expect(screen.queryByText("The passwords don't match.")).toBeNull();
  });

  it('each field has a show/hide toggle with aria-pressed', async () => {
    await openForm();
    const toggles = screen.getAllByRole('button', { name: 'Show password' });
    expect(toggles).toHaveLength(2);
    expect(toggles[0].getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(toggles[0]);
    expect(newPassword().type).toBe('text');
    expect(confirmPassword().type).toBe('password');
    const hide = screen.getByRole('button', { name: 'Hide password' });
    expect(hide.getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(hide);
    expect(newPassword().type).toBe('password');
  });

  it('allows paste into both fields', async () => {
    await openForm();
    expect(fireEvent.paste(newPassword(), { clipboardData: { getData: () => GOOD } })).toBe(true);
    expect(fireEvent.paste(confirmPassword(), { clipboardData: { getData: () => GOOD } })).toBe(true);
  });
});

describe('AcceptInvitePage submit and sign-in (D-20)', () => {
  it('sets the password, shows Signing you in, signs in once with the email and password, then loads the app shell', async () => {
    let finishAccept: () => void = () => {};
    acceptInvite.mockReturnValue(new Promise<void>(resolve => { finishAccept = resolve; }));
    login.mockResolvedValue({ access_token: 'session-token' });
    await openForm();
    fill(GOOD);
    fireEvent.click(submit());

    expect(submit().textContent).toBe('Setting password...');
    expect(submit().disabled).toBe(true);
    expect(newPassword().disabled).toBe(true);
    expect(confirmPassword().disabled).toBe(true);
    expect(acceptInvite).toHaveBeenCalledTimes(1);
    expect(acceptInvite).toHaveBeenCalledWith('abc123', GOOD);

    await act(async () => { finishAccept(); });
    await waitFor(() => expect(login).toHaveBeenCalledTimes(1));
    expect(login).toHaveBeenCalledWith('jo@northwind.example', GOOD);
    await waitFor(() => expect((window.location.replace as ReturnType<typeof vi.fn>)).toHaveBeenCalledWith('/'));
    expect(screen.getByRole('heading', { name: 'Password set' })).toBeTruthy();
  });

  it('shows Password set with a Signing you in... status spinner while the sign-in is in flight', async () => {
    acceptInvite.mockResolvedValue(undefined);
    login.mockReturnValue(new Promise(() => {}));
    await openForm();
    fill(GOOD);
    fireEvent.click(submit());
    await screen.findByRole('heading', { name: 'Password set' });
    const status = screen.getByRole('status');
    expect(status.textContent).toContain('Signing you in...');
    expect(status.querySelector('.animate-spin')).not.toBeNull();
    expect(screen.queryByLabelText('New password')).toBeNull();
  });

  it('sends one request for a double click', async () => {
    acceptInvite.mockReturnValue(new Promise(() => {}));
    await openForm();
    fill(GOOD);
    fireEvent.click(submit());
    fireEvent.click(submit());
    fireEvent.submit(submit().closest('form')!);
    expect(acceptInvite).toHaveBeenCalledTimes(1);
  });

  it('falls back to Password set with Go to sign in when the sign-in is refused', async () => {
    acceptInvite.mockResolvedValue(undefined);
    login.mockRejectedValue(new Error('Invalid credentials'));
    await openForm();
    fill(GOOD);
    fireEvent.click(submit());
    await screen.findByText('Your password is set. Sign in to continue.');
    expect(screen.getByRole('heading', { name: 'Password set' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Go to sign in' }).getAttribute('href')).toBe('/login');
    expect(window.location.replace).not.toHaveBeenCalled();
  });

  it('falls back when the sign-in answer has no access_token (for example a required challenge)', async () => {
    acceptInvite.mockResolvedValue(undefined);
    login.mockResolvedValue({ mfa_required: true });
    await openForm();
    fill(GOOD);
    fireEvent.click(submit());
    await screen.findByText('Your password is set. Sign in to continue.');
    expect(window.location.replace).not.toHaveBeenCalled();
  });

  it('falls back when the status gave no email to sign in with', async () => {
    acceptInvite.mockResolvedValue(undefined);
    await openForm({ state: 'valid', organizationName: 'Northwind Traders' });
    fill(GOOD);
    fireEvent.click(submit());
    await screen.findByText('Your password is set. Sign in to continue.');
    expect(login).not.toHaveBeenCalled();
  });

  it('re-asks the status after a 400 and moves to Used', async () => {
    acceptInvite.mockRejectedValue(new PartnerApiError('Reset token has already been used', 400));
    await openForm();
    fetchInviteStatus.mockResolvedValue({ state: 'used' });
    fill(GOOD);
    fireEvent.click(submit());
    await screen.findByRole('heading', { name: 'This invite was already used' });
    expect(fetchInviteStatus).toHaveBeenCalledTimes(2);
    expect(login).not.toHaveBeenCalled();
  });

  it('re-asks the status after a 400 and moves to Expired', async () => {
    acceptInvite.mockRejectedValue(new PartnerApiError('Reset token has expired', 400));
    await openForm();
    fetchInviteStatus.mockResolvedValue({ state: 'expired' });
    fill(GOOD);
    fireEvent.click(submit());
    await screen.findByRole('heading', { name: 'This invite has expired' });
  });

  it('shows a complexity refusal verbatim above the button and keeps the typed values', async () => {
    acceptInvite.mockRejectedValue(new PartnerApiError('Password must contain at least one special character', 400));
    await openForm();
    fetchInviteStatus.mockResolvedValue(validStatus);
    fill(GOOD);
    fireEvent.click(submit());
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toBe('Password must contain at least one special character');
    expect(alert.compareDocumentPosition(submit()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(newPassword().value).toBe(GOOD);
    expect(newPassword().disabled).toBe(false);
  });

  it('words any other server refusal as Could not set your password', async () => {
    acceptInvite.mockRejectedValue(new PartnerApiError('Too many requests.', 429));
    await openForm();
    fill(GOOD);
    fireEvent.click(submit());
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toBe("Couldn't set your password: Too many requests. Try again.");
    expect(fetchInviteStatus).toHaveBeenCalledTimes(1);
  });

  it('keeps the typed values and shows the red block on a network failure', async () => {
    acceptInvite.mockRejectedValue(new TypeError('Failed to fetch'));
    await openForm();
    fill(GOOD);
    fireEvent.click(submit());
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toBe("Couldn't set your password. Check your connection and try again.");
    expect(newPassword().value).toBe(GOOD);
    expect(confirmPassword().value).toBe(GOOD);
    expect(submit().disabled).toBe(false);
  });

  it('never logs, stores or puts the password or token in the address bar', async () => {
    const log = vi.spyOn(console, 'log').mockImplementation(() => {});
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    acceptInvite.mockResolvedValue(undefined);
    login.mockResolvedValue({ access_token: 'session-token' });
    await openForm();
    fill(GOOD);
    fireEvent.click(submit());
    await waitFor(() => expect(window.location.replace).toHaveBeenCalled());
    const everything = JSON.stringify([log.mock.calls, err.mock.calls, setItem.mock.calls, replaceState.mock.calls, originalLocation.href]);
    expect(everything).not.toContain(GOOD);
    expect(everything).not.toContain('abc123');
    expect(document.body.innerHTML).not.toContain('abc123');
    log.mockRestore();
    err.mockRestore();
    setItem.mockRestore();
  });
});

describe('AcceptInvitePage reset purpose (the /reset-password link of a reset email)', () => {
  it('opens the form at once, asks no invite status and takes the token out of the address bar', async () => {
    render(<AcceptInvitePage purpose="reset" />);
    await screen.findByRole('heading', { name: 'Choose a new password' });
    expect(replaceState).toHaveBeenCalledWith({}, '', '/reset-password');
    expect(fetchInviteStatus).not.toHaveBeenCalled();
    expect(screen.queryByText(/Welcome to/)).toBeNull();
  });

  it('sets the password and ends on Password set with Go to sign in, without signing in', async () => {
    acceptInvite.mockResolvedValue(undefined);
    render(<AcceptInvitePage purpose="reset" />);
    await screen.findByRole('heading', { name: 'Choose a new password' });
    fill(GOOD);
    fireEvent.click(submit());
    await screen.findByRole('heading', { name: 'Password set' });
    expect(acceptInvite).toHaveBeenCalledWith('abc123', GOOD);
    expect(screen.getByText('Your new password is set. Sign in with it.')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Go to sign in' })).toBeTruthy();
    expect(login).not.toHaveBeenCalled();
  });

  it('shows the reset Invalid state when the server refuses the link', async () => {
    acceptInvite.mockRejectedValue(new PartnerApiError('Reset token has expired', 400));
    render(<AcceptInvitePage purpose="reset" />);
    await screen.findByRole('heading', { name: 'Choose a new password' });
    fill(GOOD);
    fireEvent.click(submit());
    await screen.findByRole('heading', { name: "This reset link isn't valid" });
    expect(screen.queryByLabelText('New password')).toBeNull();
    expect(fetchInviteStatus).not.toHaveBeenCalled();
  });

  it('keeps the form and shows a password-rule refusal as it is', async () => {
    acceptInvite.mockRejectedValue(new PartnerApiError('Password must contain at least one special character', 400));
    render(<AcceptInvitePage purpose="reset" />);
    await screen.findByRole('heading', { name: 'Choose a new password' });
    fill(GOOD);
    fireEvent.click(submit());
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toBe('Password must contain at least one special character');
    expect(newPassword().value).toBe(GOOD);
  });

  it('shows the reset Invalid state for a link without a token', async () => {
    openLink('');
    render(<AcceptInvitePage purpose="reset" />);
    await screen.findByRole('heading', { name: "This reset link isn't valid" });
    expect(acceptInvite).not.toHaveBeenCalled();
  });

  it('is what App renders for /reset-password', async () => {
    const { readFileSync } = await import('node:fs');
    const { resolve } = await import('node:path');
    const app = readFileSync(resolve(__dirname, '../../App.tsx'), 'utf8');
    expect(app).toContain("window.location.pathname === '/accept-invite' || window.location.pathname === '/reset-password'");
    expect(app).toContain("<AcceptInvitePage purpose={window.location.pathname === '/reset-password' ? 'reset' : 'invite'} />");
  });
});
