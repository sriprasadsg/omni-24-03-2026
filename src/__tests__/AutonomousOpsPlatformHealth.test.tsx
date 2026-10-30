/**
 * Phase 82 / HEAL-01..05, D-20: the Platform health section on the Autonomous Ops screen.
 * authFetch is mocked; the health payload follows GET /api/platform/autonomous-ops/health (82-08).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within, act, fireEvent } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { UserContext } from '../../contexts/UserContext';
import { AutonomousOpsStatusProvider } from '../../contexts/AutonomousOpsStatusContext';
import { AutonomousOpsActivity } from '../../components/AutonomousOpsActivity';
import { AutonomousOpsPlatformHealth } from '../../components/AutonomousOpsPlatformHealth';
import { requestPlatformHealthFocus } from '../../components/AutonomousOpsHealthBanners';
import {
  mockAuthFetch, jsonRes, healthDoc, notInstalledDoc, services, healthCalls, retentionReview, REVIEW_PATH,
  clock, minutesAgo, minutesAhead, AT_1402, AT_0915,
} from './_platformHealthHarness';

const PLATFORM_CONTROL = 'control:platform_autonomous_ops';
const TENANT_ADMIN = ['view:autonomous_ops', 'control:autonomous_ops', 'manage:autonomous_ops'];
const SUPER = [...TENANT_ADMIN, PLATFORM_CONTROL];

function tenantStatus() {
  return {
    tenantId: 'tenant-a', tenantName: 'Acme Corp', scope: 'tenant', platformTenant: false,
    eligible: true, levelReadable: true, level: 'undoable_auto', maxLevel: 'undoable_auto',
    previousLevel: null, shadow: { effective: false, source: null },
    stop: { tenant: null, platform: null },
    canStop: true, canResume: true, canStopPlatform: false, canResumePlatform: false,
  };
}
const platformStatus = () => ({
  scope: 'platform', stop: { platform: null }, tenantStopsCount: 0, canStopPlatform: true, canResumePlatform: true,
});

/** Route authFetch by path; an unknown path fails loudly so a stray request shows up in the test. */
function route(health: () => Response | Promise<Response> = () => jsonRes(healthDoc())) {
  mockAuthFetch.mockImplementation(async (url: string) => {
    const path = url.split('?')[0];
    if (path === '/api/autonomous-ops/status') return jsonRes(tenantStatus());
    if (path === '/api/platform/autonomous-ops/status') return jsonRes(platformStatus());
    if (path === '/api/autonomous-ops/actions' || path === '/api/platform/autonomous-ops/actions') {
      return jsonRes({ items: [], nextCursor: null });
    }
    if (path === '/api/platform/autonomous-ops/health') return health();
    if (path === REVIEW_PATH) return jsonRes(retentionReview()); // the retention card has its own fetch (82-13)
    throw new Error(`unexpected request ${url}`);
  });
}

function screenFor(role: string, permissions: string[], tenantId: string | null = null) {
  return (
    <UserContext.Provider value={{
      currentUser: { id: 'u1', name: 'Pat', email: 'pat@example.com', role, tenantId: 'tenant-a', permissions } as any,
      login: async () => false, logout: () => {}, signup: async () => false,
      registerTenant: async () => false,
      hasPermission: (p: any) => permissions.includes(p),
      enabledFeatures: [], serverLockedFeatures: {},
    }}>
      <AutonomousOpsStatusProvider tenantId={tenantId} enabled>
        <AutonomousOpsActivity tenantId={tenantId} />
      </AutonomousOpsStatusProvider>
    </UserContext.Provider>
  );
}

beforeEach(() => { mockAuthFetch.mockReset(); });
afterEach(() => { vi.useRealTimers(); });

describe('Platform health section (tracer)', () => {
  it('Super Admin in platform scope: one health request, the section between the status card and Activity, the watchdog Running and the four services in order', async () => {
    route();
    const { container } = render(screenFor('Super Admin', SUPER));

    const heading = await screen.findByRole('heading', { level: 2, name: 'Platform health' });
    expect(heading).toHaveAttribute('id', 'platform-health-title');
    expect(healthCalls().length).toBe(1);

    const section = container.querySelector('#platform-health') as HTMLElement;
    expect(section).not.toBeNull();
    expect(section).toHaveAttribute('aria-labelledby', 'platform-health-title');
    const status = container.querySelector('[data-slot="autonomous-ops-status"]') as HTMLElement;
    const activity = screen.getByRole('heading', { level: 2, name: 'Activity' });
    expect(status.compareDocumentPosition(section) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(section.compareDocumentPosition(activity) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    await waitFor(() => expect(within(section).getByText('Running')).toBeInTheDocument());
    const cells = Array.from(section.querySelectorAll('dl.grid > div')).filter(c => c.querySelector('dt .font-mono'));
    expect(cells.map(c => c.querySelector('dt .font-mono')!.textContent)).toEqual(['mongod', 'omni-backend', 'nginx', 'ollama']);
    expect(cells.map(c => c.querySelector('dt')!.textContent)).toEqual(
      ['MongoDBmongod', 'Backendomni-backend', 'nginxnginx', 'Ollamaollama'],
    );
    expect(within(cells[0] as HTMLElement).getByText('Healthy')).toBeInTheDocument();
    expect(within(cells[3] as HTMLElement).getByText('Expected off')).toBeInTheDocument();
  });

  it('Super Admin viewing a tenant: no health request and no section', async () => {
    route();
    render(screenFor('Super Admin', SUPER, 'tenant-a'));
    await screen.findByRole('heading', { level: 2, name: 'Activity' });
    expect(screen.queryByRole('heading', { name: 'Platform health' })).toBeNull();
    expect(healthCalls().length).toBe(0);
  });

  it('a tenant admin: no health request and no section', async () => {
    route();
    render(screenFor('Tenant Admin', TENANT_ADMIN));
    await screen.findByRole('heading', { level: 2, name: 'Activity' });
    expect(screen.queryByRole('heading', { name: 'Platform health' })).toBeNull();
    expect(healthCalls().length).toBe(0);
  });
});

// ── Task 2: states of the section ───────────────────────────────────────────

const HEALTH_PATH = '/api/platform/autonomous-ops/health';

function serve(doc: unknown) {
  mockAuthFetch.mockImplementation(async (url: string) => {
    if (url.split('?')[0] === HEALTH_PATH) return jsonRes(doc);
    if (url.split('?')[0] === REVIEW_PATH) return jsonRes(retentionReview()); // the retention card has its own fetch (82-13)
    throw new Error(`unexpected request ${url}`);
  });
}

async function renderSection(doc: unknown, props: { refreshSignal?: number } = {}) {
  serve(doc);
  const view = render(<AutonomousOpsPlatformHealth {...props} />);
  await screen.findByText('Watchdog');
  return view;
}

/** The four service cells of the grid, in document order. */
const serviceCells = (container: HTMLElement) =>
  Array.from(container.querySelectorAll('dl.grid > div')).filter(c => c.querySelector('dt .font-mono')) as HTMLElement[];
const [MONGO, BACKEND, NGINX, OLLAMA] = [0, 1, 2, 3];

const INSTALL_TEXT =
  'Watchdog not installed. Service, certificate, disk and alert-channel status appear here once it is installed and reports. Installing it is a step on the server.';
const STOP_DATABASE =
  'Restarts are paused because automatic actions are stopped for the whole platform. Checks, warnings and pages continue.';

describe('Platform health section: header', () => {
  it('shows the title, the subtitle and the time of the last successful read', async () => {
    const { container } = await renderSection(healthDoc());
    expect(screen.getByRole('heading', { level: 2, name: 'Platform health' })).toHaveAttribute('tabindex', '-1');
    expect(screen.getByText(
      'Services, certificates, disk and alerting for the platform server, checked every minute by the watchdog.',
    )).toBeInTheDocument();
    const updated = container.querySelector('time') as HTMLElement;
    expect(updated.textContent).toMatch(/^Updated \d{2}:\d{2}$/);
    expect(updated).toHaveAttribute('datetime');
    expect(updated.getAttribute('title')).toBeTruthy();
  });
});

describe('Platform health section: services table', () => {
  it('Healthy shows when it was checked and the restart budget only when some was used', async () => {
    const { container } = await renderSection(healthDoc({
      services: services({ mongod: { restartsInWindow: 2, budgetReturnsAt: minutesAhead(45) } }),
    }));
    const [mongo, backend] = serviceCells(container);
    expect(within(mongo).getByText('Healthy')).toBeInTheDocument();
    expect(within(mongo).getByText('Checked 1 min ago.')).toBeInTheDocument();
    expect(within(mongo).getByText('Restarts used: 2 of 3 in the last 30 minutes. Restart budget back in 45 min.')).toBeInTheDocument();
    expect(within(backend).getByText('Checked 1 min ago.')).toBeInTheDocument();
    expect(within(backend).queryByText(/Restarts used/)).toBeNull();
  });

  it('Failed one check shows Checking and counts as down after two', async () => {
    const { container } = await renderSection(healthDoc({ services: services({ nginx: { state: 'checking', failedChecks: 1 } }) }));
    const cell = serviceCells(container)[NGINX];
    expect(within(cell).getByText('Checking')).toBeInTheDocument();
    expect(within(cell).getByText('1 failed check. Counted as down after 2 in a row.')).toBeInTheDocument();
  });

  it('Down shows since when, which restart is next and the minutes to wait', async () => {
    const { container } = await renderSection(healthDoc({
      services: services({ 'omni-backend': { state: 'down', since: AT_0915, restartsInWindow: 1, nextRestartAt: minutesAhead(3) } }),
    }));
    const cell = serviceCells(container)[BACKEND];
    expect(within(cell).getByText('Down')).toBeInTheDocument();
    expect(within(cell).getByText(`Down since ${clock(AT_0915)}. Restart 2 of 3 waiting 3 min.`)).toBeInTheDocument();
    expect(within(cell).getByText('Restarts used: 1 of 3 in the last 30 minutes.')).toBeInTheDocument();
  });

  it('Restarting shows which restart started and when', async () => {
    const { container } = await renderSection(healthDoc({
      services: services({ mongod: { state: 'restarting', since: AT_1402, restartsInWindow: 2 } }),
    }));
    const cell = serviceCells(container)[MONGO];
    expect(within(cell).getByText('Restarting')).toBeInTheDocument();
    expect(within(cell).getByText(`Restart 2 of 3 started ${clock(AT_1402)}.`)).toBeInTheDocument();
  });

  it('Gave up shows when on-call was paged and that the budget returns after an hour healthy', async () => {
    const { container } = await renderSection(healthDoc({
      services: services({ mongod: { state: 'gave_up', restartsInWindow: 3, pagedAt: AT_1402 } }),
    }));
    const cell = serviceCells(container)[MONGO];
    expect(within(cell).getByText('Gave up')).toBeInTheDocument();
    expect(within(cell).getByText(`Restarted 3 times in 30 minutes. Not restarting again. On-call was paged at ${clock(AT_1402)}.`)).toBeInTheDocument();
    expect(within(cell).getByText('Restart budget returns after 1 hour healthy.')).toBeInTheDocument();
  });

  it('a stop keeps the state chip and says restarts are paused', async () => {
    const { container } = await renderSection(healthDoc({
      stop: { effective: true, source: 'database' },
      services: services({ nginx: { state: 'down', since: AT_1402 } }),
    }));
    const cell = serviceCells(container)[NGINX];
    expect(within(cell).getByText('Down')).toBeInTheDocument();
    expect(within(cell).getByText('Restarts paused: automatic actions are stopped.')).toBeInTheDocument();
  });

  it('the backend waits for MongoDB while MongoDB is not healthy', async () => {
    const { container } = await renderSection(healthDoc({
      services: services({ mongod: { state: 'down', since: AT_1402 }, 'omni-backend': { state: 'down', since: AT_1402, waitingOn: 'mongod' } }),
    }));
    const cell = serviceCells(container)[BACKEND];
    expect(within(cell).getByText('Down')).toBeInTheDocument();
    expect(within(cell).getByText('Waiting for MongoDB to be healthy first.')).toBeInTheDocument();
  });

  it('Ollama is Expected off, or Running in the Notice tone when it runs where it is not expected', async () => {
    const off = await renderSection(healthDoc());
    const offCell = serviceCells(off.container)[OLLAMA];
    expect(within(offCell).getByText('Expected off')).toBeInTheDocument();
    expect(within(offCell).getByText('Not installed on this server. The watchdog never starts it.')).toBeInTheDocument();
    expect(within(offCell).queryByText(/Restarts used/)).toBeNull();
    off.unmount();

    const on = await renderSection(healthDoc({ services: services({ ollama: { state: 'unexpected_running' } }) }));
    const onCell = serviceCells(on.container)[OLLAMA];
    const chip = within(onCell).getByText('Running');
    expect(chip.className).toContain('bg-blue-50');
    expect(within(onCell).getByText('Running, but not expected on this server. Not managed.')).toBeInTheDocument();
  });

  it('a missing field renders an em dash', async () => {
    const { container } = await renderSection(healthDoc({ services: services({ nginx: { state: 'down', since: null } }) }));
    expect(within(serviceCells(container)[NGINX]).getByText('Down since —.')).toBeInTheDocument();
  });

  it('always shows four cells in the fixed order, in the responsive grid, with unit names and no truncation', async () => {
    const { container } = await renderSection(healthDoc({ services: services().reverse() }));
    const cells = serviceCells(container);
    expect(cells.map(c => c.querySelector('dt')!.textContent)).toEqual(['MongoDBmongod', 'Backendomni-backend', 'nginxnginx', 'Ollamaollama']);
    expect(container.querySelector('dl.grid')!.className).toContain('grid-cols-1 sm:grid-cols-2 xl:grid-cols-4');
    expect(container.innerHTML).not.toContain('truncate');
  });

  it('renders a hostile unit name as text, never as markup', async () => {
    const hostile = '<img src=x onerror=alert(1)>';
    const { container } = await renderSection(healthDoc({ services: services({ mongod: { unit: hostile } }) }));
    expect(screen.getByText(hostile)).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
  });
});

describe('Platform health section: watchdog row', () => {
  it('Running shows the chip, when it was last seen and the check cadence', async () => {
    await renderSection(healthDoc());
    expect(screen.getAllByText('Running').length).toBeGreaterThan(0);
    expect(screen.getByText('Last seen 1 min ago.')).toBeInTheDocument();
    expect(screen.getByText('Checks run every minute.')).toBeInTheDocument();
    expect(screen.queryByText(INSTALL_TEXT)).toBeNull();
  });

  it('Silent shows the red block with the timer name, and every service reads Unknown with its last known state', async () => {
    const seen = minutesAgo(7);
    const { container } = await renderSection(healthDoc({
      updatedAt: AT_1402,
      watchdog: { state: 'silent', lastSeenAt: seen, firstSeenAt: minutesAgo(5000), cadenceSeconds: 60, silentAfterSeconds: 300 },
    }));
    expect(screen.getByText('Silent')).toBeInTheDocument();
    expect(screen.getByText('Last seen 7 min ago.')).toBeInTheDocument();
    const alert = screen.getByRole('alert');
    expect(within(alert).getByText(
      `The watchdog has not reported since ${clock(seen)}. Services are not being checked or restarted, and no on-call pages can be sent. Check the timer on the server:`,
    )).toBeInTheDocument();
    expect(within(alert).getByText('omni-watchdog.timer').className).toContain('font-mono');
    const cells = serviceCells(container);
    expect(cells.map(c => within(c).getByText('Unknown') && true)).toEqual([true, true, true, true]);
    expect(within(cells[MONGO]).getByText(`Last known: Healthy at ${clock(AT_1402)}.`)).toBeInTheDocument();
    expect(within(cells[OLLAMA]).getByText(`Last known: Expected off at ${clock(AT_1402)}.`)).toBeInTheDocument();
  });

  it('Not installed shows the chip, the info block and Unknown cells with no reading yet', async () => {
    const { container } = await renderSection(notInstalledDoc());
    expect(screen.getByText('Not installed')).toBeInTheDocument();
    expect(screen.getByText('The watchdog has never reported on this server.')).toBeInTheDocument();
    expect(screen.getByText(INSTALL_TEXT)).toBeInTheDocument();
    const cells = serviceCells(container);
    expect(cells).toHaveLength(4);
    for (const cell of cells) {
      expect(within(cell).getByText('Unknown')).toBeInTheDocument();
      expect(within(cell).getByText('No reading yet.')).toBeInTheDocument();
    }
  });

  it('the install checklist is text plus the path in mono when the server sends no url', async () => {
    await renderSection(notInstalledDoc());
    expect(screen.queryByRole('link', { name: /install checklist/i })).toBeNull();
    expect(screen.getAllByText('View install checklist').length).toBeGreaterThan(0);
    expect(screen.getAllByText('deploy/omni-watchdog/INSTALL.md')[0].className).toContain('font-mono');
  });

  it('the install checklist is a new-tab link for an https url and for a same-origin path', async () => {
    const https = await renderSection(notInstalledDoc({ installChecklist: { path: 'deploy/omni-watchdog/INSTALL.md', url: 'https://docs.example.com/install' } }));
    const link = screen.getAllByRole('link', { name: /View install checklist/ })[0];
    expect(link).toHaveAttribute('href', 'https://docs.example.com/install');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
    https.unmount();

    await renderSection(notInstalledDoc({ installChecklist: { path: 'deploy/omni-watchdog/INSTALL.md', url: '/docs/install' } }));
    expect(screen.getAllByRole('link', { name: /View install checklist/ })[0]).toHaveAttribute('href', '/docs/install');
  });

  it.each(['http://elsewhere.example.com/install', 'javascript:alert(1)', 'data:text/html,hi'])(
    'a %s checklist url is never made a link', async (url) => {
      await renderSection(notInstalledDoc({ installChecklist: { path: 'deploy/omni-watchdog/INSTALL.md', url } }));
      expect(screen.queryByRole('link')).toBeNull();
      expect(screen.getAllByText('deploy/omni-watchdog/INSTALL.md').length).toBeGreaterThan(0);
    },
  );
});

describe('Platform health section: stop notice (D-11)', () => {
  it('the database source says restarts are paused for the whole platform', async () => {
    await renderSection(healthDoc({ stop: { effective: true, source: 'database' } }));
    expect(screen.getByText(STOP_DATABASE)).toBeInTheDocument();
  });

  it('the cache source adds that the last stop state seen is being used', async () => {
    await renderSection(healthDoc({ stop: { effective: true, source: 'cache' } }));
    expect(screen.getByText(`${STOP_DATABASE} The database can't be reached, so the watchdog is using the last stop state it saw.`)).toBeInTheDocument();
  });

  it('the file source names the STOP file', async () => {
    await renderSection(healthDoc({ stop: { effective: true, source: 'file' } }));
    expect(screen.getByText('Restarts are paused by a STOP file on the server. Checks, warnings and pages continue.')).toBeInTheDocument();
    expect(screen.queryByText(STOP_DATABASE)).toBeNull();
  });

  it('no stop, no notice', async () => {
    await renderSection(healthDoc());
    expect(screen.queryByText(/Restarts are paused/)).toBeNull();
  });
});

describe('Platform health section: loading and error', () => {
  it('first load shows one skeleton card per block with aria-busy, then the content', async () => {
    let release: (r: Response) => void = () => {};
    mockAuthFetch.mockImplementation((url: string) => (url.split('?')[0] === REVIEW_PATH
      ? Promise.resolve(jsonRes(retentionReview()))
      : new Promise<Response>(resolve => { release = resolve; })));
    const { container } = render(<AutonomousOpsPlatformHealth />);
    const section = container.querySelector('section') as HTMLElement;
    expect(section).toHaveAttribute('aria-busy', 'true');
    expect(section.querySelectorAll('.card.p-6 .animate-pulse').length).toBeGreaterThanOrEqual(4);
    // four health skeleton cards plus the retention card, which has its own fetch
    expect(section.querySelectorAll('.card.p-6')).toHaveLength(5);
    await act(async () => { release(jsonRes(healthDoc())); });
    await screen.findByText('Watchdog');
    await screen.findByRole('table', { name: 'Retention counts waiting for confirmation' });
    expect(section).not.toHaveAttribute('aria-busy', 'true');
    expect(section.querySelector('.animate-pulse')).toBeNull();
  });

  it('a first-load failure shows one red alert card, and Reload platform health fetches again', async () => {
    let calls = 0;
    mockAuthFetch.mockImplementation(async (url: string) => {
      if (url.split('?')[0] === REVIEW_PATH) return jsonRes(retentionReview());
      calls += 1;
      return calls === 1 ? jsonRes({ detail: 'nope' }, 500) : jsonRes(healthDoc());
    });
    render(<AutonomousOpsPlatformHealth />);
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText("Couldn't load platform health. Check your connection and try again.")).toBeInTheDocument();
    fireEvent.click(within(alert).getByRole('button', { name: 'Reload platform health' }));
    await screen.findByText('Watchdog');
    expect(calls).toBe(2);
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('Platform health section: refresh cadence', () => {
  const tick = async (ms = 0) => { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); };

  it('refetches every 30 s, on window focus and when refreshSignal changes, without a skeleton', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 9, 30, 14, 2, 0));
    serve(healthDoc());
    const { container, rerender } = render(<AutonomousOpsPlatformHealth refreshSignal={0} />);
    await tick();
    expect(healthCalls().length).toBe(1);

    const section = container.querySelector('section') as HTMLElement;
    const quiet = () => {
      expect(section).not.toHaveAttribute('aria-busy', 'true');
      expect(section.querySelector('.animate-pulse')).toBeNull();
    };
    await tick(30_000);
    expect(healthCalls().length).toBe(2);
    quiet();

    await act(async () => { window.dispatchEvent(new Event('focus')); });
    await tick();
    expect(healthCalls().length).toBe(3);
    quiet();

    rerender(<AutonomousOpsPlatformHealth refreshSignal={1} />);
    await tick();
    expect(healthCalls().length).toBe(4);
    quiet();
  });

  it('a failed background poll keeps the last data and the Updated time stops advancing', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 9, 30, 14, 2, 0));
    let calls = 0;
    mockAuthFetch.mockImplementation(async (url: string) => {
      if (url.split('?')[0] === REVIEW_PATH) return jsonRes(retentionReview());
      calls += 1;
      return calls === 2 || calls === 3 ? jsonRes({ detail: 'down' }, 503) : jsonRes(healthDoc());
    });
    const { container } = render(<AutonomousOpsPlatformHealth />);
    await tick();
    const updated = () => container.querySelector('time')!.textContent;
    expect(updated()).toBe('Updated 14:02');

    await tick(30_000);
    await tick(30_000);
    expect(calls).toBe(3);
    expect(updated()).toBe('Updated 14:02');
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByText('Watchdog')).toBeInTheDocument();

    await tick(30_000);
    expect(calls).toBe(4);
    expect(updated()).toBe('Updated 14:03');
  });
});

describe('Platform health section: focus', () => {
  it('moves focus to the heading on mount when a banner asked for it, once', async () => {
    requestPlatformHealthFocus();
    const first = await renderSection(healthDoc());
    expect(screen.getByRole('heading', { name: 'Platform health' })).toHaveFocus();
    first.unmount();

    await renderSection(healthDoc());
    expect(screen.getByRole('heading', { name: 'Platform health' })).not.toHaveFocus();
  });
});
