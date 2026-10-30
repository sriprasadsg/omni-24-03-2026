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
import * as Banners from '../../components/AutonomousOpsHealthBanners';
import { HealthChip, ladderChip, type HealthChipKind } from '../../components/AutonomousOpsHealthChips';

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

describe('platform health banner: priority, arming and the failing-channel text', () => {
  it('silent plus a failing channel shows only the silent banner', async () => {
    route({ platform: () => jsonRes(platformStatus(health({ watchdog: 'silent', channel: 'failing', channelError: 'HTTP 400' }))) });
    render(superAdminInTenant());
    await findRegion('alert');
    expect(screen.queryByText(CHANNEL_TITLE)).toBeNull();
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('running with no channel shows the amber status banner with the none detail', async () => {
    route({ platform: () => jsonRes(platformStatus(health({ channel: 'none' }))) });
    render(superAdminInTenant());
    const region = await findRegion('status');
    expect(within(region).getByText(CHANNEL_TITLE)).toBeInTheDocument();
    expect(region.textContent).toContain(
      'Nobody will be paged if a service fails. Set up a channel on the server, then send a test alert.');
    expect(region.className).toContain('amber');
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('running with a failing channel shows the error, wrapped, clamped to two lines, with the full text in title', async () => {
    route({ platform: () => jsonRes(platformStatus(health({ channel: 'failing', channelError: 'HTTP 400' }))) });
    render(superAdminInTenant());
    const region = await findRegion('status');
    const detail = region.querySelector('p.line-clamp-2') as HTMLElement;
    expect(detail).not.toBeNull();
    expect(detail.textContent).toBe(
      "The last alert couldn't be delivered: HTTP 400. Nobody will be paged until a test alert succeeds.");
    expect(detail.className).toContain('break-words');
    expect(detail.getAttribute('title')).toBe(detail.textContent);
  });

  it.each([['untested'], ['working'], [null]])('shows no banner when the channel is %s', async (channel) => {
    route({ platform: () => jsonRes(platformStatus(health({ channel }))) });
    render(superAdminInTenant());
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(platformCalls().length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('shows no banner while the watchdog is not installed, even with no channel', async () => {
    route({ platform: () => jsonRes(platformStatus(health({ watchdog: 'not_installed', lastSeenAt: null, channel: 'none' }))) });
    render(superAdminInTenant());
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(platformCalls().length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('shows no banner when health is null', async () => {
    route({ platform: () => jsonRes(platformStatus(null)) });
    render(superAdminInTenant());
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(platformCalls().length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('shows nothing before the first poll succeeds, and keeps the silent banner when a later poll fails', async () => {
    let release: (r: Response) => void = () => {};
    let fail = false;
    route({
      platform: () => (fail
        ? jsonRes({ detail: 'down' }, 503)
        : new Promise<Response>(r => { release = r; })),
    });
    render(superAdminInTenant());
    expect(screen.queryByRole('alert')).toBeNull();

    await act(async () => { release(jsonRes(platformStatus(health({ watchdog: 'silent' })))); });
    await findRegion('alert');

    fail = true;
    await act(async () => { window.dispatchEvent(new Event('focus')); });
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getAllByRole('alert')).toHaveLength(1);
  });

  it('stacks the health banner beneath the stop banner', async () => {
    route({
      tenant: () => jsonRes(tenantStatus({ stop: { tenant: { scope: 'tenant', by: 'Dana Admin', at: LAST_SEEN, reason: null }, platform: null } })),
      platform: () => jsonRes(platformStatus(health({ channel: 'none' }))),
    });
    render(superAdminInTenant());
    await waitFor(() => expect(screen.queryByText(CHANNEL_TITLE)).not.toBeNull(),
      { onTimeout: () => new Error('the channel banner was not rendered') });
    const regions = screen.getAllByRole('status');
    expect(regions).toHaveLength(2);
    expect(regions[0].textContent).toContain('Automatic actions are stopped for Acme Corp.');
    expect(regions[1].textContent).toContain(CHANNEL_TITLE);
  });
});

describe('platform health banner: View details', () => {
  it('is absent on the Autonomous Ops screen in platform scope', async () => {
    route({ platform: () => jsonRes(platformStatus(health({ watchdog: 'silent' }))) });
    render(superAdminOnPlatform({ view: 'autonomousOps' }));
    await findRegion('alert');
    expect(screen.queryByRole('button', { name: 'View details' })).toBeNull();
  });

  it('in tenant scope on the Autonomous Ops screen it is shown, navigates and requests focus once', async () => {
    route({ platform: () => jsonRes(platformStatus(health({ watchdog: 'silent' }))) });
    const go = vi.fn();
    render(superAdminInTenant({ view: 'autonomousOps', onViewPlatformHealth: go }));
    const button = await findViewDetails();

    expect(Banners.consumePlatformHealthFocus).toBeTypeOf('function');
    expect(Banners.requestPlatformHealthFocus).toBeTypeOf('function');
    expect(Banners.consumePlatformHealthFocus()).toBe(false);

    fireEvent.click(button);
    expect(go).toHaveBeenCalledTimes(1);
    expect(Banners.consumePlatformHealthFocus()).toBe(true);
    expect(Banners.consumePlatformHealthFocus()).toBe(false);
  });

  it('wraps below the text under 640px: full-width basis that relaxes from the sm breakpoint', async () => {
    route({ platform: () => jsonRes(platformStatus(health({ watchdog: 'silent' }))) });
    render(superAdminInTenant());
    const button = await findViewDetails();
    expect(button.className).toContain('basis-full');
    expect(button.className).toContain('sm:basis-auto');
  });

  it('is shown on another screen in platform scope', async () => {
    route({ platform: () => jsonRes(platformStatus(health({ watchdog: 'silent' }))) });
    render(superAdminOnPlatform({ view: 'agents' }));
    expect(await findViewDetails()).toBeInTheDocument();
  });
});

describe('platform health banner: one poller', () => {
  it('a Super Admin in tenant scope polls both statuses on the 30 second interval and starts no second timer', async () => {
    vi.useFakeTimers();
    try {
      route({ platform: () => jsonRes(platformStatus(health({ channel: 'none' }))) });
      const spy = vi.spyOn(globalThis, 'setInterval');
      render(superAdminInTenant());
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      const intervals = spy.mock.calls.filter(c => c[1] === 30_000);
      expect(intervals).toHaveLength(1);
      const before = platformCalls().length;
      await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
      expect(platformCalls().length).toBe(before + 1);
      spy.mockRestore();
    } finally {
      vi.useRealTimers();
    }
  });
});

const CHIPS: Array<[HealthChipKind, string, string]> = [
  ['healthy', 'Healthy', 'bg-green-50'],
  ['checking', 'Checking', 'bg-amber-50'],
  ['restarting', 'Restarting', 'bg-amber-50'],
  ['down', 'Down', 'bg-red-50'],
  ['gave_up', 'Gave up', 'bg-red-50'],
  ['expected_off', 'Expected off', 'bg-transparent'],
  ['unknown', 'Unknown', 'bg-transparent'],
  ['running', 'Running', 'bg-green-50'],
  ['silent', 'Silent', 'bg-red-50'],
  ['not_installed', 'Not installed', 'bg-transparent'],
  ['ok', 'OK', 'bg-green-50'],
  ['notice', 'Notice', 'bg-blue-50'],
  ['warning', 'Warning', 'bg-amber-50'],
  ['critical', 'Critical', 'bg-red-50'],
  ['pinned', 'Pinned by agents', 'bg-transparent'],
  ['working', 'Working', 'bg-green-50'],
  ['not_working', 'Not working', 'bg-red-50'],
  ['not_set_up', 'Not set up', 'bg-amber-50'],
  ['not_tested', 'Not tested', 'bg-gray-100'],
  ['counting_only', 'Counting only', 'bg-amber-50'],
  ['deleting_nightly', 'Deleting nightly', 'bg-green-50'],
  ['waiting', 'Waiting for confirmation', 'bg-amber-50'],
  ['running_now', 'Running now', 'bg-amber-50'],
  ['paged', 'Paged', 'bg-gray-100'],
  ['skipped', 'Skipped', 'bg-transparent'],
];

describe('HealthChip', () => {
  it.each(CHIPS)('%s renders "%s" with an aria-hidden icon in the 81 anatomy and its tone, light and dark', (kind, text, tone) => {
    const { container } = render(<HealthChip kind={kind} />);
    const chip = container.firstElementChild as HTMLElement;
    expect(chip).not.toBeNull();
    expect(chip.textContent).toBe(text);
    expect(chip.className).toContain('inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold border');
    expect(chip.className).toContain(tone);
    expect(chip.className).toContain('dark:');
    const icon = chip.querySelector('svg');
    expect(icon).not.toBeNull();
    expect(icon!.getAttribute('aria-hidden')).toBe('true');
  });

  it('covers all 25 UI-SPEC chips', () => {
    expect(new Set(CHIPS.map(c => c[0])).size).toBe(25);
  });

  it('ladderChip maps the severity rungs 0..3 to OK, Notice, Warning and Critical', () => {
    expect([0, 1, 2, 3].map(r => ladderChip(r))).toEqual(['ok', 'notice', 'warning', 'critical']);
  });

  it('ladderChip clamps out-of-range rungs and shows Unknown for a rung it cannot read', () => {
    expect(ladderChip(7)).toBe('critical');
    expect(ladderChip(-1)).toBe('ok');
    expect(ladderChip(null)).toBe('unknown');
  });
});
