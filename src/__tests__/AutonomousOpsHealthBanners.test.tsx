/**
 * Phase 82 / HEAL-05, D-05, D-22, D-24: the two app-wide platform health banners.
 * authFetch is mocked; payloads follow the 82-08 status.health summary
 * {watchdog, lastSeenAt, channel, channelError}.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act, fireEvent, within, waitFor } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { authFetch } from '../../services/apiService';
import { UserContext } from '../../contexts/UserContext';
import { AutonomousOpsStatusProvider } from '../../contexts/AutonomousOpsStatusContext';
import { AutonomousOpsStopBanner } from '../../components/AutonomousOpsStopBanner';

const mockAuthFetch = authFetch as unknown as ReturnType<typeof vi.fn>;

const PLATFORM_CONTROL = 'control:platform_autonomous_ops';
const SILENT_TITLE = 'The watchdog has gone silent.';
const CHANNEL_TITLE = 'No working on-call channel.';

/** 14:02 on the viewer's own clock, so the expected HH:MM does not depend on the time zone of the test run. */
const LAST_SEEN = new Date(2026, 9, 30, 14, 2, 0).toISOString();

function tenantStatus(over: Record<string, unknown> = {}) {
  return {
    tenantId: 't1', tenantName: 'Acme Corp', scope: 'tenant', platformTenant: false,
    eligible: true, levelReadable: true, level: 'undoable_auto', maxLevel: 'undoable_auto',
    previousLevel: null, shadow: { effective: false, source: null },
    stop: { tenant: null, platform: null },
    canStop: true, canResume: false, canStopPlatform: false, canResumePlatform: false,
    ...over,
  };
}

function health(over: Record<string, unknown> = {}) {
  return { watchdog: 'running', lastSeenAt: LAST_SEEN, channel: 'working', channelError: null, ...over };
}

function platformStatus(h: unknown, over: Record<string, unknown> = {}) {
  return {
    scope: 'platform', stop: { platform: null }, tenantStopsCount: 0,
    canStopPlatform: true, canResumePlatform: false, health: h, ...over,
  };
}

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

function userWith(permissions: string[], role: string) {
  return { id: 'u1', name: 'Pat', email: 'pat@example.com', role, tenantId: 't1', permissions } as any;
}

function withUser(permissions: string[], role: string, ui: React.ReactElement) {
  return (
    <UserContext.Provider value={{
      currentUser: userWith(permissions, role),
      login: async () => false, logout: () => {}, signup: async () => false,
      registerTenant: async () => false,
      hasPermission: (p: any) => permissions.includes(p),
      enabledFeatures: [], serverLockedFeatures: {},
    }}>
      {ui}
    </UserContext.Provider>
  );
}

type Handler = () => Response | Promise<Response>;

function route(handlers: { tenant?: Handler; platform?: Handler }) {
  mockAuthFetch.mockImplementation(async (url: string) => {
    const path = url.split('?')[0];
    if (path === '/api/autonomous-ops/status') return (handlers.tenant ?? (() => jsonRes(tenantStatus())))();
    if (path === '/api/platform/autonomous-ops/status') return (handlers.platform ?? (() => jsonRes(platformStatus(health())))) ();
    throw new Error(`unexpected request ${url}`);
  });
}

const platformCalls = () =>
  mockAuthFetch.mock.calls.filter(c => String(c[0]).split('?')[0] === '/api/platform/autonomous-ops/status');

/** Waits for a region by role. A missing region fails with a one-line message. */
async function findRegion(role: 'alert' | 'status'): Promise<HTMLElement> {
  await waitFor(() => expect(screen.queryByRole(role)).not.toBeNull(),
    { onTimeout: () => new Error(`no ${role} region was rendered`) });
  return screen.getByRole(role);
}

async function findViewDetails(): Promise<HTMLElement> {
  await waitFor(() => expect(screen.queryByRole('button', { name: 'View details' })).not.toBeNull(),
    { onTimeout: () => new Error('no View details button was rendered') });
  return screen.getByRole('button', { name: 'View details' });
}

const ADMIN = [PLATFORM_CONTROL, 'view:autonomous_ops'];

interface BannerOpts {
  view?: string;
  inPlatformScope?: boolean;
  onViewPlatformHealth?: () => void;
}

function banner(o: BannerOpts = {}) {
  return (
    <AutonomousOpsStopBanner
      currentView={o.view ?? 'agents'}
      onViewDetails={() => {}}
      inPlatformScope={o.inPlatformScope ?? false}
      onViewPlatformHealth={o.onViewPlatformHealth ?? (() => {})}
    />
  );
}

/** A Super Admin who has entered tenant t1 (tenant scope). */
function superAdminInTenant(o: BannerOpts = {}) {
  return withUser(ADMIN, 'Super Admin',
    <AutonomousOpsStatusProvider tenantId="t1" enabled>{banner(o)}</AutonomousOpsStatusProvider>);
}

/** A Super Admin with no tenant selected (platform scope). */
function superAdminOnPlatform(o: BannerOpts = {}) {
  return withUser(ADMIN, 'Super Admin',
    <AutonomousOpsStatusProvider tenantId={null} enabled>
      {banner({ inPlatformScope: true, ...o })}
    </AutonomousOpsStatusProvider>);
}

beforeEach(() => {
  mockAuthFetch.mockReset();
});

describe('platform health banner: the silent watchdog reaches a Super Admin inside a tenant', () => {
  it('fetches the platform status in tenant scope and shows the red silent banner with the last seen time', async () => {
    route({ platform: () => jsonRes(platformStatus(health({ watchdog: 'silent' }))) });
    render(superAdminInTenant());

    const alert = await findRegion('alert');
    expect(within(alert).getByText(SILENT_TITLE)).toBeInTheDocument();
    expect(alert.textContent).toContain(
      'Last seen 14:02. Services are not being checked or restarted, and no on-call pages can be sent, until it reports again.');
    expect(alert.className).toContain('red');
    expect(platformCalls().length).toBeGreaterThanOrEqual(1);
    expect(mockAuthFetch.mock.calls.some(c => String(c[0]).split('?')[0] === '/api/autonomous-ops/status')).toBe(true);
  });

  it('makes no platform request and shows no health banner for a tenant admin', async () => {
    route({ platform: () => jsonRes(platformStatus(health({ watchdog: 'silent' }))) });
    render(withUser(['view:autonomous_ops'], 'Tenant Admin',
      <AutonomousOpsStatusProvider enabled>{banner()}</AutonomousOpsStatusProvider>));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });

    expect(platformCalls()).toHaveLength(0);
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByText(SILENT_TITLE)).toBeNull();
    expect(screen.queryByText(CHANNEL_TITLE)).toBeNull();
  });
});
