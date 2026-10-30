/**
 * Phase 82 / HEAL-02..04, D-13, D-14, D-21: the certificate, disk and on-call cards of the Platform health
 * section, and Send test alert with its state machine. authFetch is mocked; the document follows
 * GET /api/platform/autonomous-ops/health (82-08).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, within, act, fireEvent } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { AutonomousOpsPlatformHealth } from '../../components/AutonomousOpsPlatformHealth';
import { CertificatesCard, DiskCard, OnCallCard } from '../../components/AutonomousOpsHealthCards';
import {
  mockAuthFetch, jsonRes, healthDoc, notInstalledDoc, cert, disk, testAlert, gb, clock, AT_1402,
  healthCalls, testAlertCalls,
} from './_platformHealthHarness';

const CHECKLIST = { path: 'deploy/omni-watchdog/INSTALL.md', url: null };
const NOTE = 'Agents pin the nginx certificate. Replacing it needs an agent update first, so plan the swap before it expires. The platform never renews certificates.';
const DISK_NOTE = 'Nothing is deleted automatically to free space. Free space yourself.';

const entries = (container: HTMLElement) => Array.from(container.querySelectorAll('li')) as HTMLElement[];
const headerOf = (name: string) => screen.getByRole('heading', { name }).parentElement as HTMLElement;

beforeEach(() => { mockAuthFetch.mockReset(); });
afterEach(() => { vi.useRealTimers(); });

// ── certificates ────────────────────────────────────────────────────────────

describe('CertificatesCard', () => {
  const soon = cert({ path: '/etc/ssl/soon.pem', notAfter: '2026-11-02T12:00:00Z', daysLeft: 3.4, rung: 2, pinned: false });
  const month = cert({ path: '/etc/ssl/month.pem', notAfter: '2026-11-19T12:00:00Z', daysLeft: 20, rung: 1, pinned: false });
  const nginx = cert({ notAfter: '2029-01-15T12:00:00Z', daysLeft: 800.2, rung: 0 });

  it('lists soonest expiry first with the path in mono, the date, the days left and the ladder chip', () => {
    const { container } = render(<CertificatesCard certs={[nginx, month, soon]} stale={false} />);
    const rows = entries(container);
    expect(rows.map(r => r.querySelector('.font-mono')!.textContent)).toEqual(['/etc/ssl/soon.pem', '/etc/ssl/month.pem', '/etc/nginx/ssl/omni.crt']);
    expect(rows[0].querySelector('.font-mono')!.className).toContain('break-all');
    expect(within(rows[0]).getByText('in 3 days')).toBeInTheDocument();
    expect(within(rows[0]).getByText('Warning')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Notice')).toBeInTheDocument();
    expect(within(rows[2]).getByText('Jan 15, 2029')).toBeInTheDocument();
    expect(within(rows[2]).getByText('in 800 days')).toBeInTheDocument();
    expect(within(rows[2]).getByText('OK')).toBeInTheDocument();
    expect(container.querySelector('ul')!.className).toContain('divide-y');
    expect(container.innerHTML).not.toContain('truncate');
  });

  it('only the nginx certificate carries Pinned by agents, and the header shows the worst rung', () => {
    const { container } = render(<CertificatesCard certs={[nginx, soon]} stale={false} />);
    const rows = entries(container);
    expect(within(rows[0]).queryByText('Pinned by agents')).toBeNull();
    expect(within(rows[1]).getByText('Pinned by agents')).toBeInTheDocument();
    expect(within(headerOf('Certificates')).getByText('Warning')).toBeInTheDocument();
  });

  it.each([
    [5.9, 'in 5 days'], [1.2, 'expires tomorrow'], [0.4, 'expires today'], [-2.5, 'expired 3 days ago'], [-0.5, 'expired 1 day ago'],
  ])('says %s days left as "%s"', (daysLeft, text) => {
    render(<CertificatesCard certs={[cert({ daysLeft, rung: 3 })]} stale={false} />);
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it('an unreadable file shows an amber Warning and says so, while the other entries render normally', () => {
    const unreadable = cert({ path: '/etc/ssl/bad.pem', notAfter: null, daysLeft: null, rung: null, error: 'unreadable', pinned: false });
    const { container } = render(<CertificatesCard certs={[unreadable, nginx]} stale={false} />);
    const rows = entries(container);
    expect(within(rows[0]).getByText('Warning').className).toContain('bg-amber-50');
    expect(within(rows[0]).getByText("Can't read this file.")).toBeInTheDocument();
    expect(within(rows[1]).getByText('Jan 15, 2029')).toBeInTheDocument();
    expect(within(headerOf('Certificates')).getByText('Warning')).toBeInTheDocument();
  });

  it('the pinned-certificate note is always shown, and an empty list says nothing is watched', () => {
    const { container, rerender } = render(<CertificatesCard certs={[nginx]} stale={false} />);
    expect(screen.getByText(NOTE)).toBeInTheDocument();
    rerender(<CertificatesCard certs={[]} stale={false} />);
    expect(screen.getByText('No certificates are being watched.')).toBeInTheDocument();
    expect(screen.getByText(NOTE)).toBeInTheDocument();
    expect(entries(container)).toHaveLength(0);
  });

  it('while the watchdog is silent or not installed, entries read Unknown with the last known expiry or no reading', () => {
    const { container } = render(
      <CertificatesCard certs={[nginx, cert({ path: '/etc/ssl/new.pem', notAfter: null, daysLeft: null, rung: null, pinned: false })]} stale updatedAt={AT_1402} />,
    );
    const rows = entries(container); // an entry with no expiry sorts first, as on the server
    expect(within(rows[0]).getByText('Unknown')).toBeInTheDocument();
    expect(within(rows[0]).getByText('No reading yet.')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Unknown')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Last known expiry Jan 15, 2029.')).toBeInTheDocument();
    expect(within(headerOf('Certificates')).getByText('Unknown')).toBeInTheDocument();
  });

  it('renders a hostile path as text, never as markup', () => {
    const hostile = '<img src=x onerror=alert(1)>';
    const { container } = render(<CertificatesCard certs={[cert({ path: hostile })]} stale={false} />);
    expect(screen.getByText(hostile)).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
  });
});

// ── disk ────────────────────────────────────────────────────────────────────

describe('DiskCard', () => {
  it('shows the mount, the percent, free of total, the meter with ticks and the ladder chip', () => {
    const { container } = render(<DiskCard disks={[disk({ usedPct: 91.2, freeBytes: gb(4.4), totalBytes: gb(50), rung: 2 })]} stale={false} />);
    const row = entries(container)[0];
    expect(within(row).getByText('/', { selector: '.font-mono' })).toBeInTheDocument();
    expect(within(row).getByText('91% used')).toBeInTheDocument();
    expect(within(row).getByText('4.4 GB free of 50.0 GB')).toBeInTheDocument();
    expect(within(row).getByText('Warning')).toBeInTheDocument();
    const meter = within(row).getByRole('meter', { name: 'Disk used' });
    expect(meter).toHaveAttribute('aria-valuemin', '0');
    expect(meter).toHaveAttribute('aria-valuemax', '100');
    expect(meter).toHaveAttribute('aria-valuenow', '91');
    expect(meter.querySelector('[data-fill]')!.className).toContain('bg-amber-500');
    const ticks = Array.from(meter.querySelectorAll('[aria-hidden="true"]:not([data-fill])')) as HTMLElement[];
    expect(ticks.map(t => t.style.left)).toEqual(['80%', '90%', '95%']);
    expect(within(headerOf('Disk')).getByText('Warning')).toBeInTheDocument();
  });

  it.each([[0, 'bg-green-600'], [1, 'bg-blue-600'], [2, 'bg-amber-500'], [3, 'bg-red-600']])(
    'fills the meter for rung %s with %s', (rung, fill) => {
      render(<DiskCard disks={[disk({ rung })]} stale={false} />);
      expect(screen.getByRole('meter').querySelector('[data-fill]')!.className).toContain(fill);
    },
  );

  it('forecast: a growth forecast with its own chip, flat usage and too few readings', () => {
    const { container, rerender } = render(<DiskCard disks={[disk({ forecast: { state: 'ok', days: 9.5, rung: 1 } })]} stale={false} />);
    const line = container.querySelector('[data-slot="disk-forecast"]') as HTMLElement;
    expect(within(line).getByText('Forecast: full in about 10 days at the last 7 days of growth.')).toBeInTheDocument();
    expect(within(line).getByText('Notice')).toBeInTheDocument();

    rerender(<DiskCard disks={[disk({ forecast: { state: 'flat', days: null, rung: 0 } })]} stale={false} />);
    const flat = container.querySelector('[data-slot="disk-forecast"]') as HTMLElement;
    expect(within(flat).getByText('Usage is not growing. No forecast.')).toBeInTheDocument();
    expect(flat.querySelector('span.rounded-full')).toBeNull();

    rerender(<DiskCard disks={[disk({ forecast: { state: 'insufficient', days: null, rung: 0 } })]} stale={false} />);
    const few = container.querySelector('[data-slot="disk-forecast"]') as HTMLElement;
    expect(within(few).getByText('Not enough readings for a forecast yet.')).toBeInTheDocument();
    expect(few.querySelector('span.rounded-full')).toBeNull();
  });

  it('one filesystem holding / and the data directory is one entry listing both paths; two filesystems are two entries', () => {
    const { container, rerender } = render(<DiskCard disks={[disk()]} stale={false} />);
    expect(entries(container)).toHaveLength(1);
    expect(screen.getByText('/var/lib/mongodb')).toBeInTheDocument();
    rerender(<DiskCard disks={[disk(), disk({ mount: '/data', paths: ['/data'] })]} stale={false} />);
    expect(entries(container)).toHaveLength(2);
  });

  it('shows the free-space note once and wraps long mount points', () => {
    const { container } = render(<DiskCard disks={[disk(), disk({ mount: '/data', paths: ['/data'] })]} stale={false} />);
    expect(screen.getAllByText(DISK_NOTE)).toHaveLength(1);
    expect(container.querySelector('li .font-mono')!.className).toContain('break-all');
    expect(container.innerHTML).not.toContain('truncate');
  });

  it('with no readings there is still one entry for / reading Unknown', () => {
    const { container } = render(<DiskCard disks={[]} stale />);
    const rows = entries(container);
    expect(rows).toHaveLength(1);
    expect(within(rows[0]).getByText('Unknown')).toBeInTheDocument();
    expect(within(rows[0]).getByText('No reading yet.')).toBeInTheDocument();
    expect(screen.queryByRole('meter')).toBeNull();
  });

  it('while the watchdog is silent the entry reads Unknown with the last known percent', () => {
    const { container } = render(<DiskCard disks={[disk({ usedPct: 62.4 })]} stale updatedAt={AT_1402} />);
    const row = entries(container)[0];
    expect(within(row).getByText('Unknown')).toBeInTheDocument();
    expect(within(row).getByText(`Last known: 62% used at ${clock(AT_1402)}.`)).toBeInTheDocument();
    expect(screen.queryByRole('meter')).toBeNull();
  });
});

// ── on-call ─────────────────────────────────────────────────────────────────

describe('OnCallCard', () => {
  const onCall = (over: Record<string, unknown> = {}) =>
    ({ type: 'pagerduty', heartbeatConfigured: true, status: 'working', last: { at: AT_1402, ok: true, error: null }, ...over }) as any;
  const card = (oncall: any, extra: Record<string, unknown> = {}) => (
    <OnCallCard oncall={oncall} testAlert={null} watchdogState="running" installChecklist={CHECKLIST} noAnswer={false} onTestRequested={() => {}} {...extra} />
  );
  const cell = (label: string) => screen.getByText(label, { selector: 'dt' }).parentElement as HTMLElement;

  it('shows the channel type, a working status and a configured heartbeat', () => {
    const { container } = render(card(onCall()));
    expect(screen.getByRole('heading', { name: 'On-call alerting' })).toBeInTheDocument();
    expect(within(cell('Channel')).getByText('PagerDuty')).toBeInTheDocument();
    expect(within(cell('Channel')).getByText('Held on the server. The platform never sees the key.')).toBeInTheDocument();
    expect(within(cell('Status')).getByText('Working')).toBeInTheDocument();
    expect(within(cell('Status')).getByText(`Last delivered ${clock(AT_1402)}.`)).toBeInTheDocument();
    expect(within(cell('External heartbeat')).getByText('Configured')).toBeInTheDocument();
    expect(container.querySelector('dl')!.className).toContain('grid-cols-1 sm:grid-cols-3');
  });

  it('a webhook that failed shows Not working with the error and no heartbeat advice', () => {
    render(card(onCall({
      type: 'webhook', heartbeatConfigured: false, status: 'not_working',
      last: { at: AT_1402, ok: false, error: 'The receiver answered 500' },
    })));
    expect(within(cell('Channel')).getByText('Webhook')).toBeInTheDocument();
    expect(within(cell('Status')).getByText('Not working')).toBeInTheDocument();
    expect(within(cell('Status')).getByText(`Last attempt ${clock(AT_1402)}: The receiver answered 500`)).toBeInTheDocument();
    expect(within(cell('External heartbeat')).getByText('Not configured')).toBeInTheDocument();
    expect(within(cell('External heartbeat')).getByText(
      'Without it, nobody is paged if the watchdog or the whole server goes down. The install checklist recommends setting it up.',
    )).toBeInTheDocument();
  });

  it('no channel shows Not set up with the on-call file advice and the install checklist', () => {
    render(card(onCall({ type: 'none', status: 'not_set_up', last: null, heartbeatConfigured: false })));
    expect(within(cell('Channel')).getByText('Not set up')).toBeInTheDocument();
    expect(within(cell('Channel')).getByText('Set up a channel in the on-call file on the server, then send a test alert.')).toBeInTheDocument();
    expect(within(cell('Channel')).getByText('View install checklist')).toBeInTheDocument();
  });

  it('a channel never tested shows Not tested and asks for a test alert', () => {
    render(card(onCall({ status: 'not_tested', last: null })));
    expect(within(cell('Status')).getByText('Not tested')).toBeInTheDocument();
    expect(within(cell('Status')).getByText('No alert has been sent yet. Send a test alert.')).toBeInTheDocument();
  });

  it('never renders a key, a routing key, a webhook url or a heartbeat url, even if the payload carried one', () => {
    const secrets = {
      key: 'S3CRET-KEY', routingKey: 'R0UTING-KEY', webhookUrl: 'https://hooks.example.com/secret', heartbeatUrl: 'https://hc.example.com/ping/abc',
    };
    const { container } = render(card(onCall(secrets)));
    for (const value of Object.values(secrets)) expect(container.textContent).not.toContain(value);
    expect(container.textContent).not.toMatch(/https?:\/\//);
    expect(container.querySelector('input')).toBeNull();
    expect(container.querySelector('a[href]')).toBeNull();
  });

  it('wraps a long delivery error', () => {
    render(card(onCall({ status: 'not_working', last: { at: AT_1402, ok: false, error: 'x'.repeat(300) } })));
    expect(within(cell('Status')).getByText(/Last attempt/).className).toContain('break-words');
  });
});

// ── Send test alert, through the section ────────────────────────────────────

const HEALTH = '/api/platform/autonomous-ops/health';
const TEST_ALERT = '/api/platform/autonomous-ops/health/test-alert';
const tick = async (ms = 0) => { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); };
const button = () => screen.getByRole('button', { name: /Send test alert|Requesting\.\.\.|Waiting for the watchdog\.\.\./ }) as HTMLButtonElement;

/** The health document and the POST answer are variables, so a test can change what the next poll sees. */
function serve(initial: Record<string, unknown>, post: () => Response | Promise<Response> = () => jsonRes({ testAlert: testAlert() })) {
  const state = { doc: healthDoc(initial) as Record<string, unknown> };
  mockAuthFetch.mockImplementation(async (url: string, init: RequestInit = {}) => {
    const path = url.split('?')[0];
    if (path === TEST_ALERT && init.method === 'POST') return post();
    if (path === HEALTH) return jsonRes(state.doc);
    throw new Error(`unexpected request ${url}`);
  });
  return state;
}

async function mountSection() {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 9, 30, 14, 2, 0));
  const view = render(<AutonomousOpsPlatformHealth />);
  await tick();
  return view;
}

describe('Send test alert', () => {
  it('idle: an enabled secondary button, the helper under it and no result line', async () => {
    serve({});
    await mountSection();
    expect(button()).toBeEnabled();
    expect(button().className).toContain('min-h-10');
    expect(screen.getByText('The watchdog sends it within about a minute.')).toBeInTheDocument();
    expect(screen.getByRole('status').textContent).toBe('');
    expect(button().getAttribute('aria-describedby')).toBeTruthy();
  });

  it('requesting: the POST in flight disables the button, and repeated clicks send one request', async () => {
    let release: (r: Response) => void = () => {};
    serve({}, () => new Promise<Response>(resolve => { release = resolve; }));
    await mountSection();
    fireEvent.click(button());
    fireEvent.click(button());
    fireEvent.click(button());
    expect(button().textContent).toContain('Requesting...');
    expect(button()).toBeDisabled();
    expect(testAlertCalls().length).toBe(1);
    await act(async () => { release(jsonRes({ testAlert: testAlert({ requestedAt: new Date().toISOString() }) })); });
    expect(testAlertCalls().length).toBe(1);
  });

  it('waiting: Waiting for the watchdog with a spinner, the requested line, and a poll every 5 s that does not re-announce', async () => {
    const state = serve({});
    const { container } = await mountSection();
    const before = healthCalls().length;
    fireEvent.click(button());
    await tick();
    state.doc = healthDoc({ testAlert: testAlert({ requestedAt: new Date().toISOString() }) });

    expect(button().textContent).toContain('Waiting for the watchdog...');
    expect(button()).toBeDisabled();
    expect(button().querySelector('svg.animate-spin')).not.toBeNull();
    const line = within(screen.getByRole('status')).getByText(`Test requested at ${clock(new Date().toISOString())}. The watchdog sends it within about a minute.`);

    await tick(5_000);
    expect(healthCalls().length).toBe(before + 1);
    await tick(5_000);
    expect(healthCalls().length).toBe(before + 2);
    const again = within(screen.getByRole('status')).getByText(/Test requested at/);
    expect(again).toBe(line);
    expect(container.querySelector('section')).not.toHaveAttribute('aria-busy', 'true');
  });

  it('delivered: the green line, the button back, and the 5 s polling stops', async () => {
    const state = serve({});
    await mountSection();
    fireEvent.click(button());
    await tick();
    state.doc = healthDoc({ testAlert: testAlert({ state: 'delivered', sentAt: AT_1402 }) });
    await tick(5_000);
    expect(within(screen.getByRole('status')).getByText(`Sent at ${clock(AT_1402)}, delivered.`)).toBeInTheDocument();
    expect(button()).toBeEnabled();
    expect(button().textContent).toContain('Send test alert');
    const calls = healthCalls().length;
    await tick(15_000);
    expect(healthCalls().length).toBe(calls);
  });

  it('failed: the red alert line with the error', async () => {
    const state = serve({});
    await mountSection();
    fireEvent.click(button());
    await tick();
    state.doc = healthDoc({ testAlert: testAlert({ state: 'failed', sentAt: AT_1402, error: 'The pager service answered 500' }) });
    await tick(5_000);
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain(`Sent at ${clock(AT_1402)}, not delivered: The pager service answered 500`);
    expect(button()).toBeEnabled();
  });

  it('no answer after 90 s: the amber line, the button back and the fast polling stops', async () => {
    const state = serve({});
    await mountSection();
    fireEvent.click(button());
    await tick();
    state.doc = healthDoc({ testAlert: testAlert({ requestedAt: new Date().toISOString() }) });
    await tick(89_000);
    expect(button()).toBeDisabled();
    await tick(2_000);
    expect(within(screen.getByRole('status')).getByText("The watchdog hasn't picked up the test request yet. Check that it is running.")).toBeInTheDocument();
    expect(button()).toBeEnabled();
    const calls = healthCalls().length;
    await tick(19_000);
    expect(healthCalls().length).toBe(calls);
  });

  it('a pending test that survived a reload shows the waiting state at once', async () => {
    serve({ testAlert: testAlert({ requestedAt: new Date().toISOString() }) });
    await mountSection();
    expect(button().textContent).toContain('Waiting for the watchdog...');
    expect(button()).toBeDisabled();
  });

  it('a failed request shows the server message, and the button works again', async () => {
    serve({}, () => jsonRes({ detail: 'Another test is already waiting' }, 409));
    await mountSection();
    fireEvent.click(button());
    await tick();
    expect(screen.getByRole('alert').textContent).toBe("Couldn't request a test alert: Another test is already waiting. Try again.");
    expect(button()).toBeEnabled();
  });

  it('a request that never reached the server shows the connection fallback', async () => {
    serve({}, () => { throw new Error('network down'); });
    await mountSection();
    fireEvent.click(button());
    await tick();
    expect(screen.getByRole('alert').textContent).toBe("Couldn't request a test alert. Check your connection and try again.");
  });

  it('watchdog not installed: the button is disabled and the helper asks to install it first', async () => {
    mockAuthFetch.mockImplementation(async () => jsonRes(notInstalledDoc()));
    await mountSection();
    expect(button()).toBeDisabled();
    expect(screen.getByText('Install the watchdog first.')).toBeInTheDocument();
    expect(screen.queryByText('The watchdog sends it within about a minute.')).toBeNull();
  });

  it('watchdog silent: the button is disabled and a blue line says a test cannot be sent', async () => {
    serve({ watchdog: { state: 'silent', lastSeenAt: AT_1402, firstSeenAt: AT_1402, cadenceSeconds: 60, silentAfterSeconds: 300 } });
    await mountSection();
    expect(button()).toBeDisabled();
    expect(within(screen.getByRole('status')).getByText("The watchdog is silent, so a test can't be sent until it reports again.")).toBeInTheDocument();
  });
});

describe('Platform health section: card layout', () => {
  it('places the certificate and disk cards in one grid, one column below xl and two from xl, before the on-call card', async () => {
    serve({});
    const { container } = await mountSection();
    const grid = container.querySelector('.grid.xl\\:grid-cols-2') as HTMLElement;
    expect(grid.className).toContain('grid-cols-1');
    expect(within(grid).getByRole('heading', { name: 'Certificates' })).toBeInTheDocument();
    expect(within(grid).getByRole('heading', { name: 'Disk' })).toBeInTheDocument();
    const onCall = screen.getByRole('heading', { name: 'On-call alerting' });
    expect(grid.compareDocumentPosition(onCall) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
