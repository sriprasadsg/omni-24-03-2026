/**
 * Phase 81 / ACTV-01, GATE-06, D-11, D-14, D-22, D-25: the Autonomous Ops status card, the Resume
 * dialog and the Super Admin platform-wide controls. authFetch is mocked; payloads follow 81-09.
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
import { AutonomousOpsStatusCard } from '../../components/AutonomousOpsStatusCard';

const mockAuthFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
const mockToast = showToast as unknown as ReturnType<typeof vi.fn>;

// ── fixtures ────────────────────────────────────────────────────────────────

const AT = '2026-10-25T14:32:00Z';
const stopView = (over: Record<string, unknown> = {}) =>
  ({ scope: 'tenant', by: 'Dana Admin', at: AT, reason: 'Investigating a bad rule', ...over });
const platformStopView = (over: Record<string, unknown> = {}) =>
  stopView({ scope: 'platform', by: 'Platform administrator', reason: null, ...over });

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

function platformStatusPayload(over: Record<string, unknown> = {}) {
  return {
    scope: 'platform', stop: { platform: null }, tenantStopsCount: 2,
    canStopPlatform: true, canResumePlatform: false, ...over,
  };
}

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

const TENANT_ADMIN = ['view:autonomous_ops', 'control:autonomous_ops', 'manage:autonomous_ops'];
const SECURITY_ANALYST = ['view:autonomous_ops', 'control:autonomous_ops'];
const ANALYST = ['view:autonomous_ops'];
const SUPER = [...TENANT_ADMIN, 'control:platform_autonomous_ops'];

type Handler = (init: RequestInit) => Response | Promise<Response>;
interface Routes {
  status?: Handler; platformStatus?: Handler;
  stop?: Handler; resume?: Handler; platformStop?: Handler; platformResume?: Handler;
}

function route(r: Routes) {
  const ok = (h: Handler | undefined, fallback: () => Response) => (init: RequestInit) => (h ? h(init) : fallback());
  mockAuthFetch.mockImplementation(async (url: string, init: RequestInit = {}) => {
    const path = url.split('?')[0];
    switch (path) {
      case '/api/autonomous-ops/status': return ok(r.status, () => jsonRes(statusPayload()))(init);
      case '/api/platform/autonomous-ops/status': return ok(r.platformStatus, () => jsonRes(platformStatusPayload()))(init);
      case '/api/autonomous-ops/stop': return ok(r.stop, () => jsonRes(statusPayload()))(init);
      case '/api/autonomous-ops/resume': return ok(r.resume, () => jsonRes(statusPayload()))(init);
      case '/api/platform/autonomous-ops/stop': return ok(r.platformStop, () => jsonRes(platformStatusPayload()))(init);
      case '/api/platform/autonomous-ops/resume': return ok(r.platformResume, () => jsonRes(platformStatusPayload()))(init);
      default: throw new Error(`unexpected request ${url}`);
    }
  });
}

const posts = (path: string) =>
  mockAuthFetch.mock.calls.filter(c => (c[1] as RequestInit | undefined)?.method === 'POST' && (c[0] as string).split('?')[0] === path);

function card(permissions: string[], opts: { role?: string; tenantId?: string | null; enabled?: boolean } = {}) {
  const { role = 'Tenant Admin', tenantId = null, enabled = true } = opts;
  return (
    <UserContext.Provider value={{
      currentUser: { id: 'u1', name: 'Pat', email: 'p@example.com', role, tenantId: 'tenant-a', permissions } as any,
      login: async () => false, logout: () => {}, signup: async () => false,
      registerTenant: async () => false,
      hasPermission: (p: any) => permissions.includes(p),
      enabledFeatures: [], serverLockedFeatures: {},
    }}>
      <AutonomousOpsStatusProvider tenantId={tenantId} enabled={enabled}>
        <AutonomousOpsStatusCard tenantId={tenantId} />
      </AutonomousOpsStatusProvider>
    </UserContext.Provider>
  );
}

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockToast.mockReset();
});

const stoppedTenant = (over: Record<string, unknown> = {}) =>
  statusPayload({ stop: { tenant: stopView(), platform: null }, canResume: true, ...over });

// ── readout and notices ─────────────────────────────────────────────────────

describe('status card readout', () => {
  it('shows the four cells with their labels, values and helper lines', async () => {
    route({});
    const { container } = render(card(TENANT_ADMIN));
    await screen.findByText('Current level');
    expect(screen.getByText('Highest level allowed')).toBeInTheDocument();
    expect(screen.getByText('Shadow mode')).toBeInTheDocument();
    expect(container.querySelectorAll('dt')).toHaveLength(4);
    expect(screen.getAllByText('Automatic within limits')).toHaveLength(2);
    expect(screen.getByText(
      'Low-risk actions run on their own and can be undone. Riskier actions need your approval.',
    )).toBeInTheDocument();
    expect(screen.getByText('Set by a platform administrator.')).toBeInTheDocument();
    expect(screen.getByText('Off: actions are live')).toBeInTheDocument();
    expect(screen.getByText('Actions allowed by the level above are carried out.')).toBeInTheDocument();
    expect(screen.getByText('Not stopped')).toBeInTheDocument();
  });

  it('labels Off and Suggest only with their helper lines', async () => {
    route({ status: () => jsonRes(statusPayload({ level: 'suggest', maxLevel: 'off' })) });
    render(card(ANALYST));
    expect(await screen.findByText('Suggest only')).toBeInTheDocument();
    expect(screen.getByText('Off')).toBeInTheDocument();
    expect(screen.getByText('Autonomous Ops suggests actions. Every action needs your approval.')).toBeInTheDocument();
    expect(screen.getByText('Nothing is decided or recorded.')).toBeInTheDocument();
  });

  it('shows shadow mode as a simulation, saying whether it is set for the deployment or the organization', async () => {
    route({ status: () => jsonRes(statusPayload({ shadow: { effective: true, source: 'deployment' } })) });
    const first = render(card(ANALYST));
    const chip = await screen.findByText('On: simulation only');
    expect(chip.closest('span')?.className).toContain('border-dashed');
    expect(screen.getByText(/Autonomous Ops records what it would have done. Nothing is carried out./)).toBeInTheDocument();
    expect(screen.getByText(/Set for the whole deployment\./)).toBeInTheDocument();
    first.unmount();

    route({ status: () => jsonRes(statusPayload({ shadow: { effective: true, source: 'tenant' } })) });
    render(card(ANALYST));
    expect(await screen.findByText(/Set for this organization\./)).toBeInTheDocument();
    expect(screen.queryByText(/Set for the whole deployment\./)).toBeNull();
  });

  it('shows the circuit-breaker notice with the level it was lowered from', async () => {
    route({ status: () => jsonRes(statusPayload({ level: 'suggest', previousLevel: 'undoable_auto' })) });
    render(card(ANALYST));
    expect(await screen.findByText(
      'Lowered from Automatic within limits after several automatic actions in a row were undone or failed. A person with manage access can restore it.',
    )).toBeInTheDocument();
  });

  it('shows the Suggest-only notice when the setting could not be read', async () => {
    route({ status: () => jsonRes(statusPayload({ level: 'suggest', levelReadable: false })) });
    render(card(ANALYST));
    expect(await screen.findByText(
      "This organization's setting couldn't be read, so it is treated as Suggest only. Every action needs approval.",
    )).toBeInTheDocument();
  });

  it('shows the platform organization as Off with no controls', async () => {
    route({
      status: () => jsonRes(statusPayload({
        platformTenant: true, eligible: false, level: 'off', maxLevel: 'off', canStop: false,
      })),
    });
    render(card(TENANT_ADMIN));
    expect(await screen.findByText('Autonomous Ops is not available for the platform organization.')).toBeInTheDocument();
    expect(screen.getAllByText('Off')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /Stop automatic actions|Resume automatic actions/ })).toBeNull();
  });

  it('says the screen is not switched on for an organization that is not eligible', async () => {
    route({ status: () => jsonRes(statusPayload({ eligible: false })) });
    render(card(ANALYST));
    expect(await screen.findByText(
      "This screen isn't switched on for this organization, so nothing is decided or recorded for it.",
    )).toBeInTheDocument();
  });

  it('lays the readout out as 1, 2 and 4 columns', async () => {
    route({});
    const { container } = render(card(ANALYST));
    await screen.findByText('Current level');
    const grid = container.querySelector('dl') as HTMLElement;
    expect(grid.className).toContain('grid-cols-1');
    expect(grid.className).toContain('sm:grid-cols-2');
    expect(grid.className).toContain('xl:grid-cols-4');
  });
});

// ── controls ────────────────────────────────────────────────────────────────

describe('stop and resume controls', () => {
  it('renders Resume (and no Stop) when the server says canResume', async () => {
    route({ status: () => jsonRes(stoppedTenant()) });
    render(card(TENANT_ADMIN));
    expect(await screen.findByRole('button', { name: /Resume automatic actions/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Stop automatic actions/ })).toBeNull();
    expect(screen.getByText('Stopped')).toBeInTheDocument();
    expect(screen.getByText(/Stopped by Dana Admin on Oct 25, 2026/)).toBeInTheDocument();
    expect(screen.getByText(/Reason: Investigating a bad rule/)).toBeInTheDocument();
  });

  it('explains who can resume when the viewer cannot', async () => {
    route({ status: () => jsonRes(statusPayload({ stop: { tenant: stopView(), platform: null }, canResume: false })) });
    const a = render(card(SECURITY_ANALYST));
    expect(await screen.findByText('Only an administrator with manage access can resume this.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Resume automatic actions|Stop automatic actions/ })).toBeNull();
    a.unmount();

    // a tenant admin looking at a stop a Super Admin pressed, and at a platform-wide stop
    const b = render(card(TENANT_ADMIN));
    expect(await screen.findByText('Only a platform administrator can resume this.')).toBeInTheDocument();
    b.unmount();

    route({ status: () => jsonRes(statusPayload({ stop: { tenant: null, platform: platformStopView() }, canResume: false })) });
    render(card(SECURITY_ANALYST));
    expect(await screen.findByText('Only a platform administrator can resume this.')).toBeInTheDocument();
    expect(screen.getByText(/Stopped by Platform administrator on/)).toBeInTheDocument();
  });

  it('gives an analyst with no control access no controls and no helper line', async () => {
    route({ status: () => jsonRes(statusPayload({ stop: { tenant: stopView(), platform: null }, canStop: false })) });
    render(card(ANALYST));
    await screen.findByText('Stopped');
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByText(/can resume this/)).toBeNull();
  });

  it('gives Platform Support no controls even if the permission list names them', async () => {
    route({ status: () => jsonRes(statusPayload({ canStop: false })) });
    render(card(SUPER, { role: 'Platform Support', tenantId: 'tenant-a' }));
    await screen.findByText('Current level');
    expect(screen.queryByRole('button')).toBeNull();
  });
});

// ── Resume dialog ───────────────────────────────────────────────────────────

describe('Resume dialog', () => {
  async function openResume(statusOver: Record<string, unknown> = {}) {
    route({ status: () => jsonRes(stoppedTenant(statusOver)) });
    render(card(TENANT_ADMIN));
    fireEvent.click(await screen.findByRole('button', { name: /Resume automatic actions/ }));
    return await screen.findByRole('dialog');
  }

  it('shows who stopped it, requires a typed reason and never submits from the keyboard', async () => {
    const dialog = await openResume();
    expect(within(dialog).getByText('Resume automatic actions?')).toBeInTheDocument();
    expect(dialog.textContent).toContain('Stopped by Dana Admin on Oct 25, 2026');
    expect(dialog.textContent).toContain('Reason: Investigating a bad rule');
    expect(dialog.textContent).toContain(
      'Actions that were held back during the stop were cancelled and will not run. New decisions can start again.',
    );
    const field = within(dialog).getByLabelText('Reason for resuming') as HTMLTextAreaElement;
    expect(field.getAttribute('aria-required')).toBe('true');
    expect(field.maxLength).toBe(500);
    await waitFor(() => expect(document.activeElement).toBe(field));

    const confirm = within(dialog).getByRole('button', { name: 'Resume automatic actions' });
    expect(confirm).toBeDisabled();

    // Enter on an empty field shows the validation message
    fireEvent.keyDown(field, { key: 'Enter' });
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Enter a reason to resume.');

    // whitespace only counts as empty
    fireEvent.change(field, { target: { value: '   ' } });
    expect(confirm).toBeDisabled();
    fireEvent.keyDown(field, { key: 'Enter' });
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Enter a reason to resume.');

    // no shortcut submit, even with text
    fireEvent.change(field, { target: { value: 'Rule fixed' } });
    expect(confirm).toBeEnabled();
    fireEvent.keyDown(field, { key: 'Enter', ctrlKey: true });
    fireEvent.keyDown(field, { key: 'Enter', metaKey: true });
    expect(posts('/api/autonomous-ops/resume')).toHaveLength(0);
    expect(within(dialog).getByText('10/500')).toBeInTheDocument();
  });

  it('resumes with the trimmed reason once, closes, toasts and refetches the status', async () => {
    let release: (r: Response) => void = () => {};
    const dialog = await openResume();
    route({
      status: () => jsonRes(statusPayload()),
      resume: () => new Promise<Response>(r => { release = r; }),
    });
    const field = within(dialog).getByLabelText('Reason for resuming');
    fireEvent.change(field, { target: { value: '  Rule fixed  ' } });
    const confirm = within(dialog).getByRole('button', { name: 'Resume automatic actions' });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Resuming...' })).toBeDisabled());
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeEnabled();
    expect(posts('/api/autonomous-ops/resume')).toHaveLength(1);
    expect(JSON.parse((posts('/api/autonomous-ops/resume')[0][1] as RequestInit).body as string)).toEqual({ reason: 'Rule fixed' });

    await act(async () => { release(jsonRes(statusPayload())); });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(mockToast).toHaveBeenCalledWith('Automatic actions resumed.', 'success');
    await waitFor(() => expect(screen.getByText('Not stopped')).toBeInTheDocument());
  });

  it('adds the shadow clause when shadow mode is on', async () => {
    const dialog = await openResume({ shadow: { effective: true, source: 'tenant' } });
    expect(dialog.textContent).toContain('New decisions can start again in shadow mode, so nothing is carried out.');
  });

  it('closes with an error toast when a platform administrator pressed the stop meanwhile (403)', async () => {
    const dialog = await openResume();
    route({
      status: () => jsonRes(stoppedTenant({ canResume: false })),
      resume: () => jsonRes({ detail: 'Forbidden' }, 403),
    });
    fireEvent.change(within(dialog).getByLabelText('Reason for resuming'), { target: { value: 'Rule fixed' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Resume automatic actions' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(mockToast).toHaveBeenCalledWith('Only a platform administrator can resume this stop.', 'error');
  });

  it('keeps the dialog open with the typed reason and the server message on any other failure', async () => {
    const dialog = await openResume();
    route({
      status: () => jsonRes(stoppedTenant()),
      resume: () => jsonRes({ detail: 'Storage is busy.' }, 503),
    });
    const field = within(dialog).getByLabelText('Reason for resuming') as HTMLTextAreaElement;
    fireEvent.change(field, { target: { value: 'Rule fixed' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Resume automatic actions' }));
    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't resume automatic actions: Storage is busy. Try again.");
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(field.value).toBe('Rule fixed');
    expect(within(dialog).getByRole('button', { name: 'Resume automatic actions' })).toBeEnabled();
  });

  it('falls back to the connection message when the server sent none', async () => {
    const dialog = await openResume();
    mockAuthFetch.mockImplementation(async (url: string) => {
      if (url.split('?')[0] === '/api/autonomous-ops/resume') throw new Error('network down');
      return jsonRes(stoppedTenant());
    });
    fireEvent.change(within(dialog).getByLabelText('Reason for resuming'), { target: { value: 'Rule fixed' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Resume automatic actions' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      "Couldn't resume automatic actions. Check your connection and try again.",
    );
  });
});

// ── Stop dialog failures ────────────────────────────────────────────────────

describe('Stop dialog failures', () => {
  it('a 409 closes the dialog with an info toast naming who stopped it', async () => {
    route({ stop: () => jsonRes({ detail: 'Already stopped.', by: 'Sam Responder' }, 409) });
    render(card(SECURITY_ANALYST));
    fireEvent.click(await screen.findByRole('button', { name: /Stop automatic actions/ }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Stop automatic actions' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(mockToast).toHaveBeenCalledWith('Automatic actions were already stopped by Sam Responder.', 'info');
  });

  it('keeps the dialog open with the typed reason and the server message on failure', async () => {
    route({ stop: () => jsonRes({ detail: 'Storage is busy.' }, 503) });
    render(card(SECURITY_ANALYST));
    fireEvent.click(await screen.findByRole('button', { name: /Stop automatic actions/ }));
    const dialog = await screen.findByRole('dialog');
    const field = within(dialog).getByLabelText('Reason (optional)') as HTMLTextAreaElement;
    fireEvent.change(field, { target: { value: 'Looks wrong' } });
    fireEvent.keyDown(field, { key: 'Enter', ctrlKey: true });
    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent(
      "Couldn't stop automatic actions: Storage is busy. Try again. If it keeps failing, ask a platform administrator to use the platform-wide stop.",
    );
    expect(field.value).toBe('Looks wrong');
    expect(field.maxLength).toBe(500);
    expect(within(dialog).getByText('11/500')).toBeInTheDocument();
  });
});

// ── platform-wide controls ──────────────────────────────────────────────────

describe('platform-wide stop (Super Admin)', () => {
  it('is not shown to a tenant admin', async () => {
    route({ status: () => jsonRes(statusPayload({ canStopPlatform: false })) });
    render(card(TENANT_ADMIN));
    await screen.findByText('Current level');
    expect(screen.queryByText('Platform-wide stop')).toBeNull();
    expect(screen.queryByRole('button', { name: /all organizations/ })).toBeNull();
  });

  it('presses Stop all organizations from inside a tenant and toasts', async () => {
    route({ status: () => jsonRes(statusPayload({ canStopPlatform: true })) });
    render(card(SUPER, { role: 'Super Admin', tenantId: 'tenant-a' }));
    expect(await screen.findByText('Platform-wide stop')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Stop all organizations' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Stop automatic actions for every organization?')).toBeInTheDocument();
    expect(dialog.textContent).toContain(
      'This halts new automatic decisions across the whole platform and holds back queued automatic instructions for all organizations. Only a platform administrator can resume it.',
    );
    fireEvent.change(within(dialog).getByLabelText('Reason (optional)'), { target: { value: 'Incident 42' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Stop all organizations' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(posts('/api/platform/autonomous-ops/stop')).toHaveLength(1);
    expect(JSON.parse((posts('/api/platform/autonomous-ops/stop')[0][1] as RequestInit).body as string)).toEqual({ reason: 'Incident 42' });
    expect(mockToast).toHaveBeenCalledWith('Automatic actions stopped for every organization.', 'success');
  });

  it('resumes all organizations only with a typed reason, using the server canResumePlatform flag', async () => {
    route({
      status: () => jsonRes(statusPayload({
        canStopPlatform: true, canResumePlatform: true,
        stop: { tenant: null, platform: platformStopView({ by: 'Root Admin' }) },
      })),
    });
    render(card(SUPER, { role: 'Super Admin', tenantId: 'tenant-a' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Resume all organizations' }));
    expect(screen.queryByRole('button', { name: 'Stop all organizations' })).toBeNull();
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Resume automatic actions for every organization?')).toBeInTheDocument();
    const confirm = within(dialog).getByRole('button', { name: 'Resume all organizations' });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText('Reason for resuming'), { target: { value: 'Incident closed' } });
    fireEvent.click(confirm);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(JSON.parse((posts('/api/platform/autonomous-ops/resume')[0][1] as RequestInit).body as string)).toEqual({ reason: 'Incident closed' });
    expect(mockToast).toHaveBeenCalledWith('Automatic actions resumed for every organization.', 'success');
  });

  it('in platform scope replaces the readout with the platform stop and the tenant stop count', async () => {
    route({});
    const { container } = render(card(SUPER, { role: 'Super Admin' }));
    expect(await screen.findByText('2 organizations stopped')).toBeInTheDocument();
    expect(screen.getByText('Each organization can also be stopped on its own.')).toBeInTheDocument();
    expect(screen.queryByText('Current level')).toBeNull();
    expect(container.querySelectorAll('dt')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Stop all organizations' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Stop automatic actions' })).toBeNull();
  });
});

// ── card states ─────────────────────────────────────────────────────────────

describe('card states', () => {
  const FORBIDDEN = ['truncate', 'font-medium', 'font-bold'];
  const noForbidden = (container: HTMLElement) => {
    for (const cls of FORBIDDEN) expect(container.querySelector(`.${cls}`)).toBeNull();
  };

  it('loading: four h-16 skeletons, one h-10 w-56 skeleton and aria-busy', async () => {
    route({ status: () => new Promise<Response>(() => {}) });
    const { container } = render(card(TENANT_ADMIN));
    await waitFor(() => expect(container.querySelector('[aria-busy="true"]')).not.toBeNull());
    expect(container.querySelectorAll('.h-16')).toHaveLength(4);
    expect(container.querySelectorAll('.h-10.w-56')).toHaveLength(1);
    expect(container.querySelector('.card')?.getAttribute('aria-busy')).toBe('true');
    noForbidden(container);
  });

  it('error: a role=alert block with Try again, Stop still available and Resume disabled', async () => {
    let fail = true;
    route({ status: () => (fail ? jsonRes({ detail: 'down' }, 503) : jsonRes(statusPayload())) });
    const { container } = render(card(TENANT_ADMIN));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't load the current status. Stop is still available.");
    expect(screen.getByRole('button', { name: /Stop automatic actions/ })).toBeEnabled();
    expect(screen.getByRole('button', { name: /Resume automatic actions/ })).toBeDisabled();
    noForbidden(container);

    fail = false;
    fireEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Current level')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('error: an analyst without the stop permission sees no Stop hint and no controls', async () => {
    route({ status: () => jsonRes({ detail: 'down' }, 503) });
    render(card(ANALYST));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't load the current status.");
    expect(alert.textContent).not.toContain('Stop is still available');
    expect(screen.queryByRole('button', { name: /Stop automatic actions|Resume automatic actions/ })).toBeNull();
  });

  it('makes no request and renders nothing when disabled', async () => {
    route({});
    const { container } = render(card(ANALYST, { enabled: false }));
    await act(async () => { await Promise.resolve(); });
    expect(mockAuthFetch).not.toHaveBeenCalled();
    expect(container.querySelector('.card')).toBeNull();
  });

  it('populated: wraps long reasons and names, nothing truncated or in a forbidden weight', async () => {
    const long = 'y'.repeat(450);
    route({ status: () => jsonRes(stoppedTenant({ tenantName: 'T'.repeat(120), stop: { tenant: stopView({ reason: long }), platform: null } })) });
    const { container } = render(card(TENANT_ADMIN));
    const line = await screen.findByText(new RegExp(`Reason: ${long}`));
    expect(line.className).toContain('break-words');
    noForbidden(container);
  });

  it('uses the divider and a 40 px control row for the controls', async () => {
    route({});
    const { container } = render(card(TENANT_ADMIN));
    const stop = await screen.findByRole('button', { name: /Stop automatic actions/ });
    expect(stop.className).toContain('min-h-10');
    expect(stop.className).toContain('px-4');
    expect(stop.className).toContain('bg-red-600');
    expect(container.querySelector('.border-t.pt-6')).not.toBeNull();
  });

  it('renders the Resume button with the accent classes', async () => {
    route({ status: () => jsonRes(stoppedTenant()) });
    render(card(TENANT_ADMIN));
    const resume = await screen.findByRole('button', { name: /Resume automatic actions/ });
    expect(resume.className).toContain('bg-primary-600');
    expect(resume.className).toContain('min-h-10');
  });
});
