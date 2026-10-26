/**
 * Phase 81 / GATE-06, D-15: pressing Stop on the status card and the app-wide stop banner.
 * authFetch is mocked, so the payloads follow the 81-09 contract (status, stop, 409 body).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { authFetch } from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { UserContext } from '../../contexts/UserContext';
import { AutonomousOpsStatusProvider } from '../../contexts/AutonomousOpsStatusContext';
import { AutonomousOpsActivity } from '../../components/AutonomousOpsActivity';
import { AutonomousOpsStopBanner } from '../../components/AutonomousOpsStopBanner';

const mockAuthFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
const mockToast = showToast as unknown as ReturnType<typeof vi.fn>;

const STOPPED_AT = '2026-10-25T14:32:00Z';

function stopView(over: Record<string, unknown> = {}) {
  return { scope: 'tenant', by: 'Dana Admin', at: STOPPED_AT, reason: 'Investigating a bad rule', ...over };
}

function statusPayload(over: Record<string, unknown> = {}) {
  return {
    tenantId: 'tenant-a', tenantName: 'Acme Corp', scope: 'tenant', platformTenant: false,
    eligible: true, levelReadable: true, level: 'undoable_auto', maxLevel: 'undoable_auto',
    previousLevel: null, shadow: { effective: false, source: null },
    stop: { tenant: null, platform: null },
    canStop: true, canResume: false, canStopPlatform: false, canResumePlatform: false,
    ...over,
  };
}

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

function userWith(permissions: string[], role = 'Tenant Admin') {
  return {
    id: 'u1', name: 'Pat', email: 'pat@example.com', role, tenantId: 'tenant-a', permissions,
  } as any;
}

function withUser(permissions: string[], ui: React.ReactElement, role = 'Tenant Admin') {
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

function route(handlers: {
  status?: () => Response | Promise<Response>;
  stop?: (init: RequestInit) => Response | Promise<Response>;
}) {
  mockAuthFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = url.split('?')[0];
    if (path === '/api/autonomous-ops/status') return (handlers.status ?? (() => jsonRes(statusPayload())))();
    if (path === '/api/autonomous-ops/actions') return jsonRes({ items: [], nextCursor: null });
    if (path === '/api/autonomous-ops/stop') return (handlers.stop ?? (() => jsonRes(statusPayload())))(init ?? {});
    throw new Error(`unexpected request ${url}`);
  });
}

const posts = () => mockAuthFetch.mock.calls.filter(c => (c[1] as RequestInit | undefined)?.method === 'POST');

function banner(view = 'agents', onViewDetails: () => void = () => {}) {
  return <AutonomousOpsStopBanner currentView={view} onViewDetails={onViewDetails} />;
}

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockToast.mockReset();
});

describe('Autonomous Ops stop banner', () => {
  it('shows nothing until the first poll succeeds, then the amber status banner with the stop details', async () => {
    let release: (r: Response) => void = () => {};
    route({ status: () => new Promise<Response>(r => { release = r; }) });
    render(withUser(['view:autonomous_ops'],
      <AutonomousOpsStatusProvider enabled>{banner()}</AutonomousOpsStatusProvider>));

    expect(screen.queryByRole('status')).toBeNull();
    await act(async () => {
      release(jsonRes(statusPayload({ stop: { tenant: stopView(), platform: null } })));
    });

    const region = await screen.findByRole('status');
    expect(within(region).getByText('Automatic actions are stopped for Acme Corp.')).toBeInTheDocument();
    expect(region.textContent).toContain('Stopped by Dana Admin on');
    expect(region.textContent).toContain('Oct 25, 2026');
    expect(region.textContent).toContain('Reason: Investigating a bad rule');
    expect(region.className).toContain('amber');
  });

  it('says "No reason was given." when the stop carries none', async () => {
    route({ status: () => jsonRes(statusPayload({ stop: { tenant: stopView({ reason: null }), platform: null } })) });
    render(withUser(['view:autonomous_ops'],
      <AutonomousOpsStatusProvider enabled>{banner()}</AutonomousOpsStatusProvider>));
    const region = await screen.findByRole('status');
    expect(region.textContent).toContain('No reason was given.');
    expect(region.textContent).not.toContain('Reason:');
  });

  it('cannot be dismissed: the only button inside the banner is View details', async () => {
    route({ status: () => jsonRes(statusPayload({ stop: { tenant: stopView(), platform: null } })) });
    render(withUser(['view:autonomous_ops'],
      <AutonomousOpsStatusProvider enabled>{banner()}</AutonomousOpsStatusProvider>));
    const region = await screen.findByRole('status');
    const buttons = within(region).getAllByRole('button');
    expect(buttons).toHaveLength(1);
    expect(buttons[0]).toHaveTextContent('View details');
    expect(region.querySelector('[aria-label*="lose"], [aria-label*="ismiss"]')).toBeNull();
  });

  it('renders nothing and makes no request for a user without view:autonomous_ops', async () => {
    route({ status: () => jsonRes(statusPayload({ stop: { tenant: stopView(), platform: null } })) });
    const { container } = render(withUser([],
      <AutonomousOpsStatusProvider enabled={false}>{banner()}</AutonomousOpsStatusProvider>));
    await act(async () => { await Promise.resolve(); });
    expect(container.querySelector('[role="status"]')).toBeNull();
    expect(mockAuthFetch).not.toHaveBeenCalled();
  });

  it('renders no banner when the first load fails, and keeps the last banner when a later poll fails', async () => {
    let fail = true;
    route({
      status: () => (fail
        ? jsonRes({ detail: 'down' }, 503)
        : jsonRes(statusPayload({ stop: { tenant: stopView(), platform: null } }))),
    });
    render(withUser(['view:autonomous_ops'],
      <AutonomousOpsStatusProvider enabled>{banner()}</AutonomousOpsStatusProvider>));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();

    fail = false;
    await act(async () => { window.dispatchEvent(new Event('focus')); });
    await screen.findByRole('status');

    fail = true;
    await act(async () => { window.dispatchEvent(new Event('focus')); });
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('stacks the platform banner above the organization banner', async () => {
    route({
      status: () => jsonRes(statusPayload({
        stop: {
          tenant: stopView(),
          platform: stopView({ scope: 'platform', by: 'Platform administrator', reason: null }),
        },
      })),
    });
    render(withUser(['view:autonomous_ops'],
      <AutonomousOpsStatusProvider enabled>{banner()}</AutonomousOpsStatusProvider>));
    await waitFor(() => expect(screen.getAllByRole('status')).toHaveLength(2));
    const [first, second] = screen.getAllByRole('status');
    expect(first.textContent).toContain('Automatic actions are stopped for the whole platform.');
    expect(first.textContent).toContain('Stopped by Platform administrator on');
    expect(second.textContent).toContain('Automatic actions are stopped for Acme Corp.');
  });

  it('shows View details everywhere except on the Autonomous Ops screen, and navigates on click', async () => {
    route({ status: () => jsonRes(statusPayload({ stop: { tenant: stopView(), platform: null } })) });
    const go = vi.fn();
    const { rerender } = render(withUser(['view:autonomous_ops'],
      <AutonomousOpsStatusProvider enabled>{banner('agents', go)}</AutonomousOpsStatusProvider>));
    const button = await screen.findByRole('button', { name: 'View details' });
    fireEvent.click(button);
    expect(go).toHaveBeenCalledTimes(1);

    rerender(withUser(['view:autonomous_ops'],
      <AutonomousOpsStatusProvider enabled>{banner('autonomousOps', go)}</AutonomousOpsStatusProvider>));
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'View details' })).toBeNull();
  });

  it('wraps long text and clamps the detail to two lines with the full text in title', async () => {
    const reason = 'x'.repeat(480);
    route({ status: () => jsonRes(statusPayload({ stop: { tenant: stopView({ reason }), platform: null } })) });
    render(withUser(['view:autonomous_ops'],
      <AutonomousOpsStatusProvider enabled>{banner()}</AutonomousOpsStatusProvider>));
    const region = await screen.findByRole('status');
    const detail = region.querySelector('.line-clamp-2') as HTMLElement;
    expect(detail).not.toBeNull();
    expect(detail.className).toContain('break-words');
    expect(detail.getAttribute('title')).toContain(reason);
  });

  it('never uses truncate, font-medium or font-bold', async () => {
    route({ status: () => jsonRes(statusPayload({ stop: { tenant: stopView(), platform: null } })) });
    const { container } = render(withUser(['view:autonomous_ops'],
      <AutonomousOpsStatusProvider enabled>{banner()}</AutonomousOpsStatusProvider>));
    await screen.findByRole('status');
    for (const cls of ['truncate', 'font-medium', 'font-bold']) {
      expect(container.querySelector(`.${cls}`)).toBeNull();
    }
  });
});

describe('Stop on the status card (tracer)', () => {
  function screenWithBanner(permissions: string[]) {
    return withUser(
      permissions,
      <AutonomousOpsStatusProvider enabled>
        {banner('autonomousOps')}
        <AutonomousOpsActivity />
      </AutonomousOpsStatusProvider>,
    );
  }

  it('one confirmation presses Stop, closes the dialog, toasts, and the banner appears', async () => {
    let stopped = false;
    let releaseStop: (r: Response) => void = () => {};
    route({
      status: () => jsonRes(statusPayload(stopped ? { stop: { tenant: stopView(), platform: null }, canResume: true } : {})),
      stop: () => new Promise<Response>(r => { releaseStop = r; }),
    });
    render(screenWithBanner(['view:autonomous_ops', 'control:autonomous_ops']));

    const stopButton = await screen.findByRole('button', { name: /Stop automatic actions/ });
    expect(screen.getByText('Takes effect right away. Undo still works.')).toBeInTheDocument();
    expect(screen.queryByRole('status')).toBeNull();

    fireEvent.click(stopButton);
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Stop automatic actions?')).toBeInTheDocument();
    const reason = within(dialog).getByLabelText('Reason (optional)') as HTMLTextAreaElement;
    await waitFor(() => expect(document.activeElement).toBe(reason));
    fireEvent.change(reason, { target: { value: 'Investigating a bad rule' } });

    const confirm = within(dialog).getByRole('button', { name: 'Stop automatic actions' });
    fireEvent.click(confirm);
    fireEvent.click(confirm); // a second click is ignored
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Stopping...' })).toBeDisabled());
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeEnabled();

    expect(posts()).toHaveLength(1);
    const [url, init] = posts()[0];
    expect(url).toBe('/api/autonomous-ops/stop');
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ reason: 'Investigating a bad rule' });

    stopped = true;
    await act(async () => { releaseStop(jsonRes(statusPayload({ stop: { tenant: stopView(), platform: null } }))); });

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(mockToast).toHaveBeenCalledWith('Automatic actions stopped.', 'success');
    const region = await screen.findByRole('status');
    expect(region.textContent).toContain('Automatic actions are stopped for Acme Corp.');
  });

  it('sends no reason when the field is empty', async () => {
    route({});
    render(screenWithBanner(['view:autonomous_ops', 'control:autonomous_ops']));
    fireEvent.click(await screen.findByRole('button', { name: /Stop automatic actions/ }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Stop automatic actions' }));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(JSON.parse((posts()[0][1] as RequestInit).body as string)).toEqual({});
  });

  it('renders no Stop button for a viewer without control:autonomous_ops', async () => {
    route({});
    render(screenWithBanner(['view:autonomous_ops']));
    await screen.findByText('Not stopped');
    expect(screen.queryByRole('button', { name: /Stop automatic actions/ })).toBeNull();
  });
});
