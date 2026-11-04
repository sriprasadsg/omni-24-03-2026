/**
 * Phase 83 / RESP-04, RESP-08, ACTV-02 (83-13): the Response settings panel (83-UI-SPEC sections 6 and 7).
 * authFetch and the toast are mocked; the payloads follow 83-07-SUMMARY.md. Nothing here reaches a real API.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within, act } from '@testing-library/react';

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
import { AutonomousOpsResponseSettings } from '../../components/AutonomousOpsResponseSettings';

const mockAuthFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
const mockToast = showToast as unknown as ReturnType<typeof vi.fn>;

type Json = Record<string, unknown>;
type Reply = Response | Promise<Response>;

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

const SETTINGS_URL = '/api/autonomous-ops/response-settings';
let stored: Json;
const settings = (over: Json = {}): Json => ({
  twoSignal: true, blockHours: 24, watchedServices: [], readable: true, restartAvailable: true, ...over,
});

/** GET returns what is stored; PUT merges the body into it, unless the test supplies its own reply. */
function routeSettings(opts: { get?: () => Reply; put?: (body: Json) => Reply } = {}) {
  mockAuthFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = url.split('?')[0];
    if (path === SETTINGS_URL && !init?.method) return (opts.get ?? (() => jsonRes(stored)))();
    if (path === SETTINGS_URL && init?.method === 'PUT') {
      const body = JSON.parse(init.body as string) as Json;
      return (opts.put ?? ((b: Json) => { stored = { ...stored, ...b }; return jsonRes(stored); }))(body);
    }
    throw new Error(`unexpected request ${url}`);
  });
}
const puts = () => mockAuthFetch.mock.calls.filter(c => (c[1] as RequestInit | undefined)?.method === 'PUT');
const putBodies = () => puts().map(c => JSON.parse((c[1] as RequestInit).body as string));
const gets = () => mockAuthFetch.mock.calls.filter(c => !(c[1] as RequestInit | undefined)?.method);

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockToast.mockReset();
  stored = settings();
});

const header = () => screen.getByRole('button', { name: 'Response settings' });
const SWITCH_NAME = 'Require two sources before blocking or quarantining';

async function openPanel(over: Json = {}, opts: Parameters<typeof routeSettings>[0] = {}) {
  stored = settings(over);
  routeSettings(opts);
  const view = render(<AutonomousOpsResponseSettings tenantName="Acme Corp" tenantId={null} />);
  await waitFor(() => expect(view.container.querySelector('.h-4.w-64')).toBeNull());
  fireEvent.click(header());
  await screen.findByRole('switch', { name: SWITCH_NAME });
  return view;
}
const addService = (name: string) => {
  fireEvent.change(screen.getByLabelText('Service name'), { target: { value: name } });
  fireEvent.click(screen.getByRole('button', { name: 'Add' }));
};
const save = () => screen.getByRole('button', { name: /^(Save settings|Saving\.\.\.)$/ });
const blockInput = () => screen.getByLabelText('Block length') as HTMLInputElement;

describe('Response settings: collapsed summary and loading', () => {
  it('reads the stored values in one line and renders no form while collapsed', async () => {
    stored = settings();
    routeSettings();
    render(<AutonomousOpsResponseSettings tenantName="Acme Corp" tenantId={null} />);
    expect(await screen.findByText(
      'Two-source rule on · Blocks last 24 hours · 0 services watched · Nothing restarts until you add a service',
    )).toBeInTheDocument();
    expect(header()).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('switch')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Save settings' })).toBeNull();
    expect(gets()[0][0]).toBe(SETTINGS_URL);
  });

  it('keeps the dormant fact out of the line once a service is watched, and counts them', async () => {
    stored = settings({ watchedServices: ['nginx'], twoSignal: false, blockHours: 48 });
    routeSettings();
    const { rerender } = render(<AutonomousOpsResponseSettings tenantName="Acme Corp" tenantId={null} />);
    expect(await screen.findByText('Two-source rule off · Blocks last 2 days · 1 service watched')).toBeInTheDocument();
    stored = settings({ watchedServices: ['a', 'b', 'c'], blockHours: 1 });
    rerender(<AutonomousOpsResponseSettings key="again" tenantName="Acme Corp" tenantId={null} />);
    expect(await screen.findByText('Two-source rule on · Blocks last 1 hour · 3 services watched')).toBeInTheDocument();
  });

  it('shows a skeleton line while loading and three skeleton groups, aria-busy, when expanded', async () => {
    mockAuthFetch.mockImplementation(() => new Promise(() => {}));
    const { container } = render(<AutonomousOpsResponseSettings tenantName="Acme Corp" tenantId={null} />);
    expect(container.querySelector('.h-4.w-64')).not.toBeNull();
    fireEvent.click(header());
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(container.querySelectorAll('[aria-busy="true"] .h-16')).toHaveLength(3);
    expect(screen.queryByRole('switch')).toBeNull();
  });

  it('a load failure shows a red alert with Try again and keeps the header', async () => {
    routeSettings({ get: () => jsonRes({ detail: 'x' }, 500) });
    render(<AutonomousOpsResponseSettings tenantName="Acme Corp" tenantId={null} />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't load response settings. Check your connection and try again.");
    expect(header()).toBeInTheDocument();
    stored = settings();
    routeSettings();
    fireEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText(/^Two-source rule on/)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('Response settings: the form', () => {
  it('shows the switch on, 24 hours in the number input and unit, and 48 hours as 2 days', async () => {
    await openPanel();
    const sw = screen.getByRole('switch', { name: SWITCH_NAME });
    expect(sw).toHaveAttribute('aria-checked', 'true');
    expect(screen.getAllByText('On').length).toBeGreaterThan(0);
    expect(blockInput()).toHaveValue(24);
    expect(screen.getByLabelText('Block length unit')).toHaveValue('hours');
    expect(save()).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Discard changes' })).toBeNull();
  });

  it('shows a whole number of days above one day in days', async () => {
    await openPanel({ blockHours: 48 });
    expect(blockInput()).toHaveValue(2);
    expect(screen.getByLabelText('Block length unit')).toHaveValue('days');
  });

  it('an invalid block length shows the inline alert and disables Save', async () => {
    await openPanel();
    fireEvent.change(blockInput(), { target: { value: '0' } });
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a block length between 1 hour and 7 days.');
    expect(save()).toBeDisabled();
    fireEvent.change(blockInput(), { target: { value: '169' } });
    expect(screen.getByRole('alert')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Block length unit'), { target: { value: 'days' } });
    fireEvent.change(blockInput(), { target: { value: '8' } });
    expect(screen.getByRole('alert')).toBeInTheDocument();
    fireEvent.change(blockInput(), { target: { value: '7' } });
    expect(screen.queryByRole('alert')).toBeNull();
    expect(save()).toBeEnabled();
  });

  it('refuses each invalid service name with its own message and adds on Enter', async () => {
    await openPanel({ watchedServices: ['nginx'] });
    addService('   ');
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a service name.');
    addService('NGINX');
    expect(screen.getByRole('alert')).toHaveTextContent('NGINX is already on the list.');
    addService('bad name!');
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Use only letters, numbers, dots, hyphens and underscores, starting with a letter or number.',
    );
    addService('-leading');
    expect(screen.getByRole('alert')).toHaveTextContent('Use only letters');
    const input = screen.getByLabelText('Service name');
    fireEvent.change(input, { target: { value: 'Spooler' } });
    expect(screen.queryByRole('alert')).toBeNull();
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(screen.getByRole('button', { name: 'Remove Spooler' })).toBeInTheDocument();
    expect(screen.getByText('2/50 services')).toBeInTheDocument();
    expect(input).toHaveValue('');
  });

  it('refuses a 51st service and refuses a name longer than 128 characters', async () => {
    await openPanel({ watchedServices: Array.from({ length: 50 }, (_, i) => `svc${i}`) });
    addService('one-more');
    expect(screen.getByRole('alert')).toHaveTextContent('You can watch up to 50 services.');
    expect(screen.getByText('50/50 services')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Remove svc0' }));
    addService('a'.repeat(129));
    expect(screen.getByRole('alert')).toHaveTextContent('Use only letters');
  });

  it('shows the empty-list line, and removes a chip', async () => {
    await openPanel();
    expect(screen.getByText('No services are watched yet, so nothing restarts on its own.')).toBeInTheDocument();
    expect(screen.getByText('0/50 services')).toBeInTheDocument();
    addService('nginx');
    expect(screen.queryByText('No services are watched yet, so nothing restarts on its own.')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Remove nginx' }));
    expect(screen.queryByRole('button', { name: 'Remove nginx' })).toBeNull();
  });

  it('writes nothing until Save, and Discard changes restores the stored values', async () => {
    await openPanel();
    addService('nginx');
    fireEvent.change(blockInput(), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('switch', { name: SWITCH_NAME }));
    expect(puts()).toHaveLength(0);
    expect(save()).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }));
    expect(screen.getByRole('switch', { name: SWITCH_NAME })).toHaveAttribute('aria-checked', 'true');
    expect(blockInput()).toHaveValue(24);
    expect(screen.queryByRole('button', { name: 'Remove nginx' })).toBeNull();
    expect(puts()).toHaveLength(0);
    expect(save()).toBeDisabled();
  });

  it('saves other changes with no dialog, sending only what changed, then toasts and refetches', async () => {
    await openPanel();
    addService('nginx');
    fireEvent.change(blockInput(), { target: { value: '12' } });
    fireEvent.click(save());
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith('Response settings saved.', 'success'));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(putBodies()).toEqual([{ blockHours: 12, watchedServices: ['nginx'] }]);
    await waitFor(() => expect(gets().length).toBe(2));
    expect(save()).toBeDisabled();
  });

  it('locks every field while saving and keeps the saved answer, with no second read (WR-28)', async () => {
    let release: (r: Response) => void = () => {};
    await openPanel({ watchedServices: ['sshd'] }, { put: () => new Promise<Response>(r => { release = r; }) });
    fireEvent.change(blockInput(), { target: { value: '12' } });
    fireEvent.click(save());
    await waitFor(() => expect(puts()).toHaveLength(1));
    for (const field of [screen.getByRole('switch', { name: SWITCH_NAME }), blockInput(), screen.getByLabelText('Service name'),
      screen.getByRole('button', { name: 'Add' }), screen.getByRole('button', { name: 'Remove sshd' })]) expect(field).toBeDisabled();
    await act(async () => { release(jsonRes(settings({ blockHours: 12, watchedServices: ['sshd'] }))); });
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith('Response settings saved.', 'success'));
    expect(gets()).toHaveLength(1);
    expect(blockInput()).toHaveValue(12);
  });

  it('a services save applies only the person\'s adds and removes to the list read just before it (WR-28)', async () => {
    await openPanel({ watchedServices: ['sshd'] });
    stored = { ...stored, watchedServices: ['sshd', 'cron'] }; // another administrator added cron meanwhile
    fireEvent.click(screen.getByRole('button', { name: 'Remove sshd' }));
    addService('nginx');
    fireEvent.click(save());
    await waitFor(() => expect(putBodies()).toEqual([{ watchedServices: ['cron', 'nginx'] }]));
  });

  it('sends a block length chosen in days as hours', async () => {
    await openPanel();
    fireEvent.change(screen.getByLabelText('Block length unit'), { target: { value: 'days' } });
    fireEvent.change(blockInput(), { target: { value: '3' } });
    fireEvent.click(save());
    await waitFor(() => expect(putBodies()).toEqual([{ blockHours: 72 }]));
  });

  it('a failed save shows the server message above the footer and keeps the staged values', async () => {
    await openPanel({}, { put: () => jsonRes({ detail: 'nginx is a system service, so it is never restarted automatically.' }, 422) });
    addService('nginx');
    fireEvent.click(save());
    expect(await screen.findByText(
      "Couldn't save response settings: nginx is a system service, so it is never restarted automatically. Try again.",
    )).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove nginx' })).toBeInTheDocument();
    expect(save()).toBeEnabled();
  });

  it('a failed save with no message shows the connection fallback', async () => {
    await openPanel({}, { put: () => { throw new Error('offline'); } });
    addService('nginx');
    fireEvent.click(save());
    expect(await screen.findByText("Couldn't save response settings. Check your connection and try again.")).toBeInTheDocument();
  });

  it('a 403 on save closes the form with the permission toast and fetches again', async () => {
    await openPanel({}, { put: () => jsonRes({ detail: 'no' }, 403) });
    addService('nginx');
    fireEvent.click(save());
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith("You don't have permission to change these settings.", 'error'));
    expect(screen.queryByRole('switch')).toBeNull();
    expect(header()).toHaveAttribute('aria-expanded', 'false');
    // On mount, just before the services save (WR-28) and again after the 403.
    await waitFor(() => expect(gets().length).toBe(3));
  });

  it('restartAvailable false shows the blue block and the list can still be built', async () => {
    await openPanel({ restartAvailable: false });
    expect(screen.getByText(
      'Restarting services needs remediation to be switched on for this organization. Ask a platform administrator. You can still build the list now.',
    )).toBeInTheDocument();
    addService('nginx');
    expect(screen.getByRole('button', { name: 'Remove nginx' })).toBeInTheDocument();
  });

  it('does not show that block when restart is available', async () => {
    await openPanel();
    expect(screen.queryByText(/Restarting services needs remediation/)).toBeNull();
  });

  it('unreadable settings show the safe defaults in a blue block and Save waits for a change', async () => {
    await openPanel({ readable: false });
    expect(screen.getByText(
      "This organization's response settings couldn't be read, so the safe defaults apply: two sources required, 24-hour blocks, no services watched.",
    )).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: SWITCH_NAME })).toHaveAttribute('aria-checked', 'true');
    expect(save()).toBeDisabled();
    addService('nginx');
    expect(save()).toBeEnabled();
  });

  it('wraps long service names and never truncates', async () => {
    const long = 'a'.repeat(128);
    const { container } = await openPanel({ watchedServices: [long] });
    expect(screen.getByText(long)).toHaveClass('break-all');
    expect(container.innerHTML).not.toContain('truncate');
  });
});

describe('Response settings: turning the two-source rule off', () => {
  async function stage(over: Json = {}, opts: Parameters<typeof routeSettings>[0] = {}) {
    await openPanel(over, opts);
    fireEvent.click(screen.getByRole('switch', { name: SWITCH_NAME }));
    expect(screen.getByRole('switch', { name: SWITCH_NAME })).toHaveAttribute('aria-checked', 'false');
    expect(screen.getAllByText('Off').length).toBeGreaterThan(0);
    fireEvent.click(save());
    return screen.findByRole('dialog');
  }

  it('opens the confirmation before anything is written, with the tenant name and the record notice', async () => {
    const dialog = await stage();
    expect(within(dialog).getByRole('heading', { name: 'Turn off the two-source rule?' })).toBeInTheDocument();
    expect(within(dialog).getByText(
      'With the rule off, one source is enough for Autonomous Ops to block an IP address or quarantine a file on its own for Acme Corp. Blocks and quarantines can still be undone, and every other limit still applies: the never-touch list, 20 automatic actions an hour, and the circuit breaker.',
    )).toBeInTheDocument();
    expect(within(dialog).getByRole('status')).toHaveTextContent(
      'This change is recorded in the activity list and the audit log with your name.',
    );
    expect(within(dialog).queryByText(/Also saving/)).toBeNull();
    expect(within(dialog).queryByRole('button', { name: 'Close dialog' })).toBeNull();
    expect(puts()).toHaveLength(0);
  });

  it('Cancel writes nothing and keeps the staged form', async () => {
    const dialog = await stage();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(puts()).toHaveLength(0);
    expect(screen.getByRole('switch', { name: SWITCH_NAME })).toHaveAttribute('aria-checked', 'false');
  });

  it('lists the other changes that save with it', async () => {
    await openPanel();
    fireEvent.click(screen.getByRole('switch', { name: SWITCH_NAME }));
    fireEvent.change(blockInput(), { target: { value: '12' } });
    addService('nginx');
    addService('Spooler');
    fireEvent.click(save());
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Also saving: block length 12 hours; 2 services watched.')).toBeInTheDocument();
  });

  it('Turn off the rule saves, toasts its own message and closes', async () => {
    const dialog = await stage();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Turn off the rule' }));
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith('Response settings saved. The two-source rule is off.', 'success'));
    expect(putBodies()).toEqual([{ twoSignal: false }]);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(gets().length).toBe(1); // the PUT answer is the saved state: no second read (WR-28)
  });

  it('shows Saving..., ignores a second click and does not close on Esc while the request is in flight', async () => {
    let release: (r: Response) => void = () => {};
    const dialog = await stage({}, { put: () => new Promise<Response>(r => { release = r; }) });
    const confirm = within(dialog).getByRole('button', { name: 'Turn off the rule' });
    fireEvent.click(confirm);
    const pending = await within(dialog).findByRole('button', { name: 'Saving...' });
    expect(pending).toBeDisabled();
    fireEvent.click(pending);
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expect(puts()).toHaveLength(1);
    await act(async () => { release(jsonRes(settings({ twoSignal: false }))); });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('Esc closes the dialog when nothing is in flight', async () => {
    const dialog = await stage();
    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(puts()).toHaveLength(0);
  });

  it('a failed save keeps the dialog open with the server message', async () => {
    const dialog = await stage({}, { put: () => jsonRes({ detail: 'The change could not be recorded.' }, 500) });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Turn off the rule' }));
    expect(await within(dialog).findByText(
      "Couldn't save response settings: The change could not be recorded. Try again.",
    )).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Turn off the rule' })).toBeEnabled();
  });

  it('turning the rule on needs no dialog', async () => {
    await openPanel({ twoSignal: false });
    fireEvent.click(screen.getByRole('switch', { name: SWITCH_NAME }));
    fireEvent.click(save());
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith('Response settings saved.', 'success'));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(putBodies()).toEqual([{ twoSignal: true }]);
  });
});

// ── who sees the panel ──────────────────────────────────────────────────────

function screenFor(role: string, perms: string[], opts: { tenantId?: string | null; platformTenant?: boolean } = {}) {
  const { tenantId = null, platformTenant = false } = opts;
  mockAuthFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = url.split('?')[0];
    if (path === '/api/autonomous-ops/status') {
      return jsonRes({
        tenantId: 'tenant-a', tenantName: 'Acme Corp', scope: 'tenant', platformTenant, eligible: true, levelReadable: true,
        level: 'undoable_auto', maxLevel: 'undoable_auto', previousLevel: null, shadow: { effective: false, source: null },
        stop: { tenant: null, platform: null }, canStop: true, canResume: true, canStopPlatform: false, canResumePlatform: false,
      });
    }
    if (path === '/api/platform/autonomous-ops/status') {
      return jsonRes({ scope: 'platform', stop: { platform: null }, tenantStopsCount: 0, canStopPlatform: true, canResumePlatform: true });
    }
    if (path.endsWith('/autonomous-ops/actions')) return jsonRes({ items: [], nextCursor: null });
    if (path === SETTINGS_URL && !init?.method) return jsonRes(settings());
    throw new Error(`unexpected request ${url}`);
  });
  return (
    <UserContext.Provider value={{
      currentUser: { id: 'u1', name: 'Pat', email: 'pat@example.com', role, tenantId: 'tenant-a', permissions: perms } as any,
      login: async () => false, logout: () => {}, signup: async () => false, registerTenant: async () => false,
      hasPermission: ((p: string) => perms.includes('*') || perms.includes(p)) as any, enabledFeatures: [], serverLockedFeatures: {},
    }}>
      <AutonomousOpsStatusProvider tenantId={tenantId} enabled>
        <AutonomousOpsActivity tenantId={tenantId} />
      </AutonomousOpsStatusProvider>
    </UserContext.Provider>
  );
}
const settingsGets = () => mockAuthFetch.mock.calls.filter(c => String(c[0]).includes('response-settings'));

describe('Response settings: who sees the panel', () => {
  it('a Tenant Admin with manage sees it between the status card and Activity', async () => {
    render(screenFor('Tenant Admin', ['view:autonomous_ops', 'manage:autonomous_ops']));
    const panel = await screen.findByRole('button', { name: 'Response settings' });
    const activity = screen.getByRole('heading', { name: 'Activity' });
    expect(panel.compareDocumentPosition(activity) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(await screen.findByText(/^Two-source rule on/)).toBeInTheDocument();
  });

  it('a viewer without manage does not see it and no settings request is made', async () => {
    render(screenFor('Security Analyst', ['view:autonomous_ops', 'control:autonomous_ops']));
    await screen.findByRole('heading', { name: 'Activity' });
    expect(screen.queryByRole('button', { name: 'Response settings' })).toBeNull();
    expect(settingsGets()).toHaveLength(0);
  });

  it('Platform Support never sees it, even in an organization it entered', async () => {
    render(screenFor('Platform Support', ['view:autonomous_ops', 'manage:autonomous_ops'], { tenantId: 'tenant-a' }));
    await screen.findByRole('heading', { name: 'Activity' });
    expect(screen.queryByRole('button', { name: 'Response settings' })).toBeNull();
    expect(settingsGets()).toHaveLength(0);
  });

  it('the platform organization never gets it', async () => {
    render(screenFor('Tenant Admin', ['view:autonomous_ops', 'manage:autonomous_ops'], { platformTenant: true }));
    await screen.findByRole('heading', { name: 'Activity' });
    await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: 'Response settings' })).toBeNull();
    expect(settingsGets()).toHaveLength(0);
  });

  it('a Super Admin inside an organization uses the normal panel for that organization', async () => {
    render(screenFor('Super Admin', ['*'], { tenantId: 'tenant-a' }));
    await screen.findByRole('button', { name: 'Response settings' });
    await waitFor(() => expect(settingsGets().length).toBeGreaterThan(0));
    expect(settingsGets()[0][0]).toBe(`${SETTINGS_URL}?tenantId=tenant-a`);
    expect(screen.queryByRole('button', { name: 'Response settings for every organization' })).toBeNull();
  });
});
