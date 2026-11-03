/**
 * Phase 87 (87-14): the partner screens in the application shell.
 * PART-01 views partners / partnerPortal, PART-02 public /accept-invite, PART-05 a partner user's shell
 * calls nothing but its own routes (T-87-42).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';

vi.mock('../../services/socketService', () => ({
  socketService: { on: vi.fn(), off: vi.fn(), connect: vi.fn(), disconnect: vi.fn(), emit: vi.fn() },
}));
vi.mock('../../services/geminiService', () => ({ getCommandFromQuery: vi.fn() }));
vi.mock('../../components/PartnerPortal', () => ({ default: () => <div>PARTNER PORTAL SCREEN</div> }));
vi.mock('../../components/PartnersDashboard', () => {
  const Screen = () => <div>PARTNERS SCREEN</div>;
  return { PartnersDashboard: Screen, default: Screen };
});
vi.mock('../../components/AcceptInvitePage', () => ({ default: () => <div>ACCEPT INVITE PAGE</div> }));
vi.mock('../../components/TenantManagementDashboard', () => ({
  TenantManagementDashboard: (p: { tenants: { name: string }[] }) => (
    <div data-testid="tenant-list">{p.tenants.map(t => t.name).join('|')}</div>
  ),
}));

import App from '../../App';

const jwt = (role: string) => `h.${btoa(JSON.stringify({ role }))}.s`;

const PARTNER_ADMIN = {
  id: 'u-pa', name: 'Pat Partner', email: 'pat@retailer.test', role: 'partner_admin', tenantId: 'org-retail',
  tenantName: 'Retailer', permissions: ['view:partner_portal', 'manage:partner_customers'],
};
const SUPER_ADMIN = {
  id: 'u-sa', name: 'Root', email: 'root@omni.test', role: 'Super Admin', tenantId: 'platform-admin',
  permissions: ['*'],
};
const TENANTS = [
  { id: 't-acme', name: 'Acme Customer', type: 'customer' },
  { id: 'org-retail', name: 'Retailer Partner Org', type: 'partner' },
];

const ALLOWED = /^\/api\/(partner|auth|mfa|passkey)(\/|$)|^\/api\/platform\/features$|^\/api\/health$/;

let calls: string[] = [];

function stubFetch(me: object | null) {
  calls = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const path = new URL(raw, 'http://localhost').pathname;
    calls.push(path);
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
    if (path === '/api/auth/me') return me ? json(me) : json({}, 401);
    if (path === '/api/health') return json({ status: 'ok' });
    if (path === '/api/tenants') return json(TENANTS);
    if (path === '/api/platform/features') return json({ tier: 'Free', enabled: [], locked: {}, tier_order: {} });
    return json({}, 404);
  }));
}

function signIn(role: string) {
  sessionStorage.setItem('token', jwt(role));
}

beforeEach(() => {
  // jsdom has none of these browser APIs; the shell touches them on mount.
  window.matchMedia = ((query: string) => ({
    matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
  class Observer { observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } }
  vi.stubGlobal('ResizeObserver', Observer);
  vi.stubGlobal('IntersectionObserver', Observer);
  window.HTMLElement.prototype.scrollIntoView = () => {};
  sessionStorage.clear();
  localStorage.clear();
  window.history.replaceState(null, '', '/');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('public /accept-invite route (PART-02)', () => {
  it('renders the Accept invite page without a session, not the sign-in page', async () => {
    stubFetch(null);
    window.history.replaceState(null, '', '/accept-invite?token=abc');
    render(<App />);
    expect(await screen.findByText('ACCEPT INVITE PAGE')).toBeTruthy();
    expect(screen.queryByText(/sign in to/i)).toBeNull();
    expect(screen.queryByLabelText(/password/i)).toBeNull();
  });
});

describe('Super Admin views (PART-01)', () => {
  it('renders PartnersDashboard for the partners view', async () => {
    stubFetch(SUPER_ADMIN);
    signIn('Super Admin');
    window.history.replaceState(null, '', '/#partners');
    render(<App />);
    expect(await screen.findByText('PARTNERS SCREEN')).toBeTruthy();
  });

  it('lists no partner organization on the Tenants screen', async () => {
    stubFetch(SUPER_ADMIN);
    signIn('Super Admin');
    window.history.replaceState(null, '', '/#tenantmanagement');
    render(<App />);
    const list = await screen.findByTestId('tenant-list');
    await waitFor(() => expect(list.textContent).toContain('Acme Customer'));
    expect(list.textContent).not.toContain('Retailer Partner Org');
  });
});

describe('partner user shell (PART-05, T-87-42)', () => {
  it('lands on the Partner portal', async () => {
    stubFetch(PARTNER_ADMIN);
    signIn('partner_admin');
    render(<App />);
    expect(await screen.findByText('PARTNER PORTAL SCREEN')).toBeTruthy();
  });

  it('makes no request outside the partner, auth, mfa, passkey and features routes', async () => {
    stubFetch(PARTNER_ADMIN);
    signIn('partner_admin');
    render(<App />);
    await screen.findByText('PARTNER PORTAL SCREEN');
    await act(async () => { await new Promise(r => setTimeout(r, 100)); });
    const outside = calls.filter(p => !ALLOWED.test(p));
    expect(outside).toEqual([]);
  });

  it('ignores the command palette and search keys', async () => {
    stubFetch(PARTNER_ADMIN);
    signIn('partner_admin');
    render(<App />);
    await screen.findByText('PARTNER PORTAL SCREEN');
    await act(async () => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }));
      window.dispatchEvent(new KeyboardEvent('keydown', { key: '/', ctrlKey: true, bubbles: true }));
    });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByPlaceholderText(/search/i)).toBeNull();
  });
});

// Last on purpose: holding a session for MFA is module state in apiService and lasts for the file.
describe('public /accept-invite route and the MFA gate (PART-02)', () => {
  it('renders it before the MFA gate, even when a held session would ask for MFA', async () => {
    stubFetch({ ...PARTNER_ADMIN, mfa_action: 'enroll' });
    signIn('partner_admin');
    window.history.replaceState(null, '', '/accept-invite?token=abc');
    render(<App />);
    expect(await screen.findByText('ACCEPT INVITE PAGE')).toBeTruthy();
    await act(async () => { await new Promise(r => setTimeout(r, 30)); });
    expect(screen.getByText('ACCEPT INVITE PAGE')).toBeTruthy();
  });
});
