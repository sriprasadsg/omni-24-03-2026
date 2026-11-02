/**
 * Phase 87 (PART-01, PART-05): the partner client, the role gate that keeps the Partner portal for
 * partner users only, and the suspended-partner exit.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { canReadView, evaluateViewAccess, landingView, PARTNER_ONLY_VIEWS } from '../../utils/viewAccess';
import { derivePermissionState, isPartnerAdminRoleName, isPartnerRoleName, partnerRoleLabel, platformTier } from '../../utils/permissions';
import {
  PartnerApiError,
  acceptInvite,
  fetchInviteStatus,
  fetchPartnerOverview,
  inviteColleague,
  moveCustomer,
} from '../../services/partnerApi';
import { LoginPage } from '../../components/LoginPage';
import type { User } from '../../types';

vi.mock('@simplewebauthn/browser', () => ({ startAuthentication: vi.fn() }));

const mk = (role: string, permissions?: string[]): User =>
  ({ id: 'u1', name: 'U', email: 'u@x.test', role, tenantId: 't1', permissions }) as unknown as User;

const has = (user: User) => derivePermissionState(user).hasPermission;
const evaluate = (view: string, user: User) => evaluateViewAccess(view as never, user, has(user));

const partnerAdmin = mk('partner_admin', ['view:partner_portal', 'manage:partner_customers']);
const partnerViewer = mk('partner_viewer', ['view:partner_portal']);
const superAdmin = mk('Super Admin', []);

const reply = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });

describe('partner role names', () => {
  it.each(['partner_admin', 'Partner Admin', 'partner-viewer', ' PARTNER_VIEWER '])('recognises %s as a partner role', role => {
    expect(isPartnerRoleName(role)).toBe(true);
    expect(platformTier(role)).toBeNull();
  });

  it.each(['Super Admin', 'Tenant Admin', 'platform_support', '', null, undefined])('does not treat %s as a partner role', role => {
    expect(isPartnerRoleName(role as never)).toBe(false);
  });

  it('labels the two roles for people', () => {
    expect(isPartnerAdminRoleName('Partner Admin')).toBe(true);
    expect(isPartnerAdminRoleName('partner_viewer')).toBe(false);
    expect(partnerRoleLabel('partner_admin')).toBe('Partner administrator');
    expect(partnerRoleLabel('partner_viewer')).toBe('Partner viewer');
  });
});

describe('the Partner portal belongs to partner users only (PART-05, R1)', () => {
  it('lists partnerPortal as the one partner-only view', () => {
    expect([...PARTNER_ONLY_VIEWS]).toEqual(['partnerPortal']);
  });

  it('denies partnerPortal to a Super Admin even though the owner passes every permission check', () => {
    expect(evaluate('partnerPortal', superAdmin)).toMatchObject({ allowed: false, reason: 'role' });
    expect(canReadView('partnerPortal' as never, superAdmin, has(superAdmin))).toBe(false);
  });

  it('denies partnerPortal to a user holding every permission through the star', () => {
    const everything = mk('Tenant Admin', ['*']);
    expect(evaluate('partnerPortal', everything)).toMatchObject({ allowed: false, reason: 'role' });
  });

  it.each(['Tenant Admin', 'itam_user', 'platform_support', 'platform_billing'])('denies partnerPortal to %s', role => {
    const user = mk(role, ['view:partner_portal', 'view:dashboard']);
    expect(evaluate('partnerPortal', user)).toMatchObject({ allowed: false, reason: 'role' });
  });

  it('allows partnerPortal to a partner admin and a partner viewer holding view:partner_portal', () => {
    expect(evaluate('partnerPortal', partnerAdmin)).toEqual({ allowed: true });
    expect(evaluate('partnerPortal', partnerViewer)).toEqual({ allowed: true });
    expect(canReadView('partnerPortal' as never, partnerViewer, has(partnerViewer))).toBe(true);
  });

  it('still requires the permission for a partner user', () => {
    expect(evaluate('partnerPortal', mk('partner_viewer', []))).toMatchObject({ allowed: false, reason: 'role' });
  });

  it('allows the Partners page to the Super Admin and refuses it to a partner admin', () => {
    expect(evaluate('partners', superAdmin)).toEqual({ allowed: true });
    expect(evaluate('partners', partnerAdmin)).toMatchObject({ allowed: false, reason: 'role' });
  });

  it('lands a partner user on the portal and leaves the Super Admin landing view unchanged', () => {
    expect(landingView(partnerViewer, has(partnerViewer))).toBe('partnerPortal');
    expect(landingView(superAdmin, has(superAdmin))).toBe('dashboard');
  });
});

describe('partner API client', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    sessionStorage.clear();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('resolves the parsed body of a successful overview call', async () => {
    const overview = { partner: { name: 'Acme' }, role: 'admin', pool: { size: 10 }, ceiling: [], unrestricted: false, customers: [] };
    fetchMock.mockResolvedValueOnce(reply(200, overview));
    await expect(fetchPartnerOverview()).resolves.toEqual(overview);
    expect(fetchMock.mock.calls[0][0]).toBe('/api/partner/overview');
  });

  it('throws PartnerApiError with the server text, code, status and numbers on a refusal', async () => {
    fetchMock.mockResolvedValueOnce(reply(409, { error: 'Only 4 seats are free in your pool.', code: 'pool_full', free: 4 }));
    const err = await fetchPartnerOverview().catch(e => e);
    expect(err).toBeInstanceOf(PartnerApiError);
    expect(err.message).toBe('Only 4 seats are free in your pool.');
    expect(err.code).toBe('pool_full');
    expect(err.status).toBe(409);
    expect(err.data.free).toBe(4);
  });

  it('falls back to body.detail, then to a plain sentence', async () => {
    fetchMock.mockResolvedValueOnce(reply(403, { detail: 'Only a partner admin can change the partner\'s customers' }));
    await expect(inviteColleague({ name: 'A', email: 'a@x.test', role: 'partner_viewer' }))
      .rejects.toMatchObject({ message: "Only a partner admin can change the partner's customers", status: 403 });
    fetchMock.mockResolvedValueOnce(reply(500, 'not json'));
    await expect(moveCustomer('c1', null)).rejects.toMatchObject({ message: 'Could not move the customer.', status: 500 });
  });

  it('sends the move target in the body, null meaning direct', async () => {
    fetchMock.mockResolvedValueOnce(reply(200, {}));
    await moveCustomer('c 1', null);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/platform/partners/customers/c%201/move');
    expect(JSON.parse(init.body)).toEqual({ targetPartnerId: null });
  });

  it('sends the session token on signed-in calls', async () => {
    sessionStorage.setItem('token', 'header.eyJleHAiOjk5OTk5OTk5OTl9.sig');
    fetchMock.mockResolvedValueOnce(reply(200, { members: [] }));
    await inviteColleague({ name: 'A', email: 'a@x.test', role: 'partner_viewer' }).catch(() => undefined);
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toMatch(/^Bearer /);
  });

  it('checks an invite and accepts it with plain fetch and no Authorization header', async () => {
    sessionStorage.setItem('token', 'should-not-be-sent');
    fetchMock.mockResolvedValueOnce(reply(200, { state: 'valid', organizationName: 'Acme', email: 'a@x.test', roleKind: 'partner_admin' }));
    await expect(fetchInviteStatus('tok')).resolves.toMatchObject({ state: 'valid', organizationName: 'Acme' });
    fetchMock.mockResolvedValueOnce(reply(200, {}));
    await acceptInvite('tok', 'a-long-enough-password');

    const [statusCall, acceptCall] = fetchMock.mock.calls;
    expect(statusCall[0]).toBe('/api/auth/invite/status');
    expect(JSON.parse(statusCall[1].body)).toEqual({ token: 'tok' });
    expect(acceptCall[0]).toBe('/api/auth/reset-password/confirm');
    expect(JSON.parse(acceptCall[1].body)).toEqual({ token: 'tok', new_password: 'a-long-enough-password' });
    for (const [, init] of fetchMock.mock.calls) {
      expect(Object.keys(init.headers).map(k => k.toLowerCase())).not.toContain('authorization');
    }
  });

  it('surfaces the server text when an invite cannot be accepted', async () => {
    fetchMock.mockResolvedValueOnce(reply(400, { detail: 'Password is too short' }));
    await expect(acceptInvite('tok', 'x')).rejects.toMatchObject({ message: 'Password is too short', status: 400 });
  });
});

const SUSPENDED_MESSAGE = 'This partner account is suspended. Contact your platform administrator to restore access.';
const LIVE_TOKEN = 'header.eyJleHAiOjk5OTk5OTk5OTl9.sig';

describe('a suspended partner session ends on the sign-in page (PART-01, T-87-21)', () => {
  const realLocation = window.location;
  const fetchMock = vi.fn();
  let api: typeof import('../../services/apiService');

  beforeEach(async () => {
    // _sessionEnding is module state: each test gets its own copy of apiService.
    vi.resetModules();
    api = await import('../../services/apiService');
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    sessionStorage.clear();
    sessionStorage.setItem('token', LIVE_TOKEN);
    sessionStorage.setItem('refresh_token', 'refresh');
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { href: 'http://localhost/#partnerPortal', hash: '#partnerPortal', search: '', pathname: '/' },
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    Object.defineProperty(window, 'location', { configurable: true, value: realLocation });
  });

  it('clears the tokens, goes to the sign-in page with the reason, and throws on a 403 carrying X-Partner-Suspended', async () => {
    fetchMock.mockResolvedValueOnce(reply(403, { detail: SUSPENDED_MESSAGE }, { 'X-Partner-Suspended': '1' }));
    await expect(api.authFetch('/api/partner/overview')).rejects.toThrow('Partner suspended');
    expect(sessionStorage.getItem('token')).toBeNull();
    expect(sessionStorage.getItem('refresh_token')).toBeNull();
    expect(window.location.href).toBe('/login?error=partner_suspended');
    // The generic "session ended" notice would contradict the one message the contract allows.
    expect(sessionStorage.getItem(api.SESSION_ENDED_KEY)).toBeNull();
  });

  it('leaves a 403 without that header exactly as before', async () => {
    fetchMock.mockResolvedValueOnce(reply(403, { detail: 'Not allowed' }));
    const res = await api.authFetch('/api/partner/overview');
    expect(res.status).toBe(403);
    expect(sessionStorage.getItem('token')).toBe(LIVE_TOKEN);
    expect(window.location.href).toBe('http://localhost/#partnerPortal');
  });

  it('refuses every later call once the session has ended', async () => {
    fetchMock.mockResolvedValueOnce(reply(403, {}, { 'X-Partner-Suspended': '1' }));
    await api.authFetch('/api/partner/overview').catch(() => undefined);
    await expect(api.authFetch('/api/partner/team')).rejects.toThrow('Session ended');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('shows the server wording when sign-in answers 403 with body.error', async () => {
    fetchMock.mockResolvedValueOnce(reply(403, { error: SUSPENDED_MESSAGE }));
    const err = await api.login('p@x.test', 'pw').catch(e => e);
    expect(err).toBeInstanceOf(api.LoginError);
    expect(err.message).toBe(SUSPENDED_MESSAGE);
  });

  it('still shows body.detail, then the disabled-account fallback, for other 403s', async () => {
    fetchMock.mockResolvedValueOnce(reply(403, { detail: 'Account locked' }));
    await expect(api.login('a@x.test', 'pw')).rejects.toThrow('Account locked');
    fetchMock.mockResolvedValueOnce(reply(403, {}));
    await expect(api.login('a@x.test', 'pw')).rejects.toThrow('This account is disabled. Contact your administrator.');
  });
});

describe('LoginPage explains a suspended partner', () => {
  beforeEach(() => {
    sessionStorage.clear();
    // LoginPage asks the server for SSO providers on mount.
    vi.stubGlobal('fetch', vi.fn(async () => reply(200, { providers: [] })));
    (window as any).matchMedia ??= () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    (window as any).IntersectionObserver ??= class { observe() {} unobserve() {} disconnect() {} };
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    window.history.replaceState(null, '', '/');
  });

  it('shows the suspended message for ?error=partner_suspended', () => {
    window.history.replaceState(null, '', '/login?error=partner_suspended');
    render(React.createElement(LoginPage, { users: [] }));
    expect(screen.getByText(SUSPENDED_MESSAGE)).toBeTruthy();
  });

  it('shows no error on an ordinary visit', () => {
    render(React.createElement(LoginPage, { users: [] }));
    expect(screen.queryByText(SUSPENDED_MESSAGE)).toBeNull();
  });
});
