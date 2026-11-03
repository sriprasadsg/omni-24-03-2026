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
vi.mock('../../components/NotificationCenter', () => ({ default: () => <div>NOTIFICATION CENTRE</div> }));
vi.mock('../../components/AcceptInvitePage', () => ({ default: () => <div>ACCEPT INVITE PAGE</div> }));
vi.mock('../../components/TenantManagementDashboard', () => ({
  TenantManagementDashboard: (p: { tenants: { name: string }[] }) => (
    <div data-testid="tenant-list">{p.tenants.map(t => t.name).join('|')}</div>
  ),
}));

import App from '../../App';
import { Header } from '../../components/Header';
import { Sidebar } from '../../components/Sidebar';
import { ThemeProvider } from '../../contexts/ThemeProvider';
import { TimeZoneProvider } from '../../contexts/TimeZoneContext';
import { UserContext } from '../../contexts/UserContext';

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

const PARTNER_VIEWER = { ...PARTNER_ADMIN, id: 'u-pv', role: 'partner_viewer', permissions: ['view:partner_portal'] };

function renderHeader(user: object, restricted?: boolean) {
  const onOpenSearch = vi.fn();
  render(
    <TimeZoneProvider>
      <ThemeProvider>
        <UserContext.Provider value={{ currentUser: user, hasPermission: () => false, logout: vi.fn() } as never}>
          <Header
            allUsers={[]}
            onToggleSidebar={() => {}}
            onOpenCommandBar={() => {}}
            onOpenSearch={onOpenSearch}
            setCurrentView={() => {}}
            onStartTour={() => {}}
            currentView="partnerPortal"
            restricted={restricted}
          />
        </UserContext.Provider>
      </ThemeProvider>
    </TimeZoneProvider>,
  );
}

function renderSidebar(user: any, has: (p: string) => boolean) {
  return render(
    <UserContext.Provider value={{ currentUser: user, hasPermission: has } as never}>
      <Sidebar
        isOpen
        currentView="partnerPortal"
        setCurrentView={() => {}}
        isViewingTenant={false}
        onBackToTenants={() => {}}
      />
    </UserContext.Provider>,
  );
}

const navLabels = (c: HTMLElement) =>
  Array.from(c.querySelectorAll('nav button')).map(b => b.textContent?.trim() ?? '').filter(Boolean);

describe('Header for a partner user (PART-05, T-87-42)', () => {
  it('shows the theme toggle and the account menu and none of the customer-facing widgets', () => {
    stubFetch(null);
    renderHeader(PARTNER_ADMIN, true);
    expect(screen.getByRole('button', { name: 'Toggle dark mode' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Account and appearance' })).toBeTruthy();
    expect(screen.queryAllByRole('button', { name: 'Open command palette' })).toEqual([]);
    expect(screen.queryByRole('button', { name: 'Open Global Search' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Start guided tour' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Feature help' })).toBeNull();
    expect(screen.queryByText('NOTIFICATION CENTRE')).toBeNull();
  });

  it('keeps every widget for everyone else', () => {
    stubFetch(null);
    renderHeader(SUPER_ADMIN);
    expect(screen.getAllByRole('button', { name: 'Open command palette' }).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Open Global Search' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Start guided tour' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Feature help' })).toBeTruthy();
    expect(screen.getByText('NOTIFICATION CENTRE')).toBeTruthy();
  });
});

describe('Sidebar for partner users and the Super Admin (PART-05, R1)', () => {
  it('gives a partner viewer exactly one entry and no group heading', () => {
    stubFetch(null);
    const { container } = renderSidebar(PARTNER_VIEWER, p => PARTNER_VIEWER.permissions.includes(p));
    expect(navLabels(container)).toEqual(['Partner portal']);
    expect(container.querySelectorAll('button[aria-expanded]').length).toBe(0);
    expect(screen.queryByText('Management & Settings')).toBeNull();
  });

  it('keeps the single entry visible without opening an accordion', () => {
    stubFetch(null);
    const { container } = renderSidebar(PARTNER_ADMIN, p => PARTNER_ADMIN.permissions.includes(p));
    const link = Array.from(container.querySelectorAll('nav button')).find(b => b.textContent?.includes('Partner portal')) as HTMLElement;
    expect(link).toBeTruthy();
    let el: HTMLElement | null = link;
    while (el && el.tagName !== 'NAV') {
      expect(el.style.maxHeight === '0px').toBe(false);
      el = el.parentElement;
    }
  });

  it('does not poll the support unread count for a partner user', async () => {
    stubFetch(null);
    renderSidebar(PARTNER_VIEWER, p => PARTNER_VIEWER.permissions.includes(p));
    await act(async () => { await new Promise(r => setTimeout(r, 30)); });
    expect(calls.filter(c => !ALLOWED.test(c))).toEqual([]);
  });

  it('shows the Super Admin Partners right after Tenants and never Partner portal', () => {
    stubFetch(null);
    const { container } = renderSidebar(SUPER_ADMIN, () => true);
    const labels = navLabels(container);
    expect(labels).not.toContain('Partner portal');
    expect(labels[labels.indexOf('Tenants') + 1]).toBe('Partners');
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
