/**
 * Phase 83 / RESP-04, RESP-08, ACTV-02 (83-13 Task 2): Response settings for every organization (83-UI-SPEC sections 6 and 7,
 * R10). authFetch and the toast are mocked; the payloads follow 83-07-SUMMARY.md. Nothing here reaches a real API.
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
import { PlatformResponseSettings } from '../../components/AutonomousOpsResponseSettingsPlatform';

const mockAuthFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
const mockToast = showToast as unknown as ReturnType<typeof vi.fn>;

type Json = Record<string, unknown>;
type Reply = Response | Promise<Response>;

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

const URL_GET = '/api/platform/autonomous-ops/response-settings';
const URL_BULK = '/api/platform/autonomous-ops/response-settings/bulk';
const dist = (over: Json = {}) => ({
  organizations: 4, twoSignal: { on: 3, off: 1 }, blockHours: { '12': 1, '24': 3 }, unreadable: 0, ...over,
});

function routePlatform(opts: { get?: () => Reply; bulk?: (body: Json) => Reply } = {}) {
  mockAuthFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url === URL_GET && !init?.method) return (opts.get ?? (() => jsonRes(dist())))();
    if (url === URL_BULK && init?.method === 'PUT') {
      const body = JSON.parse(init.body as string) as Json;
      return (opts.bulk ?? (() => jsonRes({ changed: ['t1', 't2', 't3', 't4'], failures: [] })))(body);
    }
    throw new Error(`unexpected request ${url}`);
  });
}
const bulks = () => mockAuthFetch.mock.calls.filter(c => c[0] === URL_BULK);
const bulkBodies = () => bulks().map(c => JSON.parse((c[1] as RequestInit).body as string));
const gets = () => mockAuthFetch.mock.calls.filter(c => c[0] === URL_GET);

beforeEach(() => { mockAuthFetch.mockReset(); mockToast.mockReset(); });

const TITLE = 'Response settings for every organization';
const header = () => screen.getByRole('button', { name: TITLE });
const boxes = () => screen.getAllByRole('checkbox', { name: 'Change this setting for every organization' });
const apply = () => screen.getByRole('button', { name: 'Apply to every organization' });
const blockInput = () => screen.getByLabelText('Block length') as HTMLInputElement;
const SWITCH_NAME = 'Require two sources before blocking or quarantining';

async function openForm(opts: Parameters<typeof routePlatform>[0] = {}) {
  routePlatform(opts);
  const view = render(<PlatformResponseSettings />);
  await screen.findByText(/^Two-source rule on in/);
  fireEvent.click(header());
  await screen.findByRole('switch', { name: SWITCH_NAME });
  return view;
}
async function openDialog(setup: () => void, opts: Parameters<typeof routePlatform>[0] = {}) {
  await openForm(opts);
  setup();
  fireEvent.click(apply());
  return screen.findByRole('dialog');
}
const tickRuleOff = () => { fireEvent.click(boxes()[0]); fireEvent.click(screen.getByRole('switch', { name: SWITCH_NAME })); };
const tickBlock = (hours: string) => { fireEvent.click(boxes()[1]); fireEvent.change(blockInput(), { target: { value: hours } }); };

describe('Response settings for every organization: summary and form', () => {
  it('reads how many organizations have the rule on and that the block length differs', async () => {
    routePlatform();
    render(<PlatformResponseSettings />);
    expect(await screen.findByText(
      'Two-source rule on in 3 organizations, off in 1 · Block length differs across organizations',
    )).toBeInTheDocument();
    expect(header()).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('switch')).toBeNull();
    expect(gets()[0][0]).toBe(URL_GET);
  });

  it('reads the one block length when every organization has the same', async () => {
    routePlatform({ get: () => jsonRes(dist({ twoSignal: { on: 4, off: 0 }, blockHours: { '48': 4 } })) });
    render(<PlatformResponseSettings />);
    expect(await screen.findByText(
      'Two-source rule on in 4 organizations, off in 0 · Blocks last 2 days in every organization',
    )).toBeInTheDocument();
  });

  it('shows a skeleton line while loading and a red alert with Try again when it fails', async () => {
    mockAuthFetch.mockImplementation(() => new Promise(() => {}));
    const first = render(<PlatformResponseSettings />);
    expect(first.container.querySelector('.h-4.w-64')).not.toBeNull();
    first.unmount();
    routePlatform({ get: () => jsonRes({ detail: 'x' }, 500) });
    render(<PlatformResponseSettings />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't load response settings. Check your connection and try again.");
    routePlatform();
    fireEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText(/^Two-source rule on in/)).toBeInTheDocument();
  });

  it('offers two groups only, each behind its own checkbox, with No change and disabled controls', async () => {
    await openForm();
    expect(boxes()).toHaveLength(2);
    expect(boxes()[0]).not.toBeChecked();
    expect(screen.getAllByText('No change')).toHaveLength(2);
    expect(screen.getByRole('switch', { name: SWITCH_NAME })).toBeDisabled();
    expect(blockInput()).toBeDisabled();
    expect(screen.getByLabelText('Block length unit')).toBeDisabled();
    expect(apply()).toBeDisabled();
    expect(screen.queryByLabelText('Service name')).toBeNull();
    expect(screen.getByText('Watched services are set for each organization on its own screen.')).toBeInTheDocument();
  });

  it('a ticked box enables its control and Apply; an invalid length disables Apply again', async () => {
    await openForm();
    fireEvent.click(boxes()[1]);
    expect(blockInput()).toBeEnabled();
    expect(screen.getAllByText('No change')).toHaveLength(1);
    expect(apply()).toBeEnabled();
    fireEvent.change(blockInput(), { target: { value: '0' } });
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a block length between 1 hour and 7 days.');
    expect(apply()).toBeDisabled();
    fireEvent.change(blockInput(), { target: { value: '12' } });
    expect(apply()).toBeEnabled();
    fireEvent.click(boxes()[1]);
    expect(apply()).toBeDisabled();
  });
});

describe('Apply to every organization? dialog', () => {
  it('changing only the block length has the body, the summary and no checkbox', async () => {
    const dialog = await openDialog(() => tickBlock('12'));
    expect(within(dialog).getByRole('heading', { name: 'Apply to every organization?' })).toBeInTheDocument();
    expect(within(dialog).getByText(
      "This writes the setting to each organization on its own. An organization's administrator can change it back afterwards. The platform organization is not changed.",
    )).toBeInTheDocument();
    expect(within(dialog).getByText('Block length: 12 hours')).toBeInTheDocument();
    expect(within(dialog).getByText('4 organizations will be changed.')).toBeInTheDocument();
    expect(within(dialog).queryByRole('checkbox')).toBeNull();
    expect(within(dialog).queryByRole('status')).toBeNull();
    expect(within(dialog).queryByRole('button', { name: 'Close dialog' })).toBeNull();
    expect(bulks()).toHaveLength(0);
  });

  it('turning the rule on has no checkbox either', async () => {
    const dialog = await openDialog(() => fireEvent.click(boxes()[0]));
    expect(within(dialog).getByText('Two-source rule: on')).toBeInTheDocument();
    expect(within(dialog).queryByRole('checkbox')).toBeNull();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply to every organization' }));
    await waitFor(() => expect(bulkBodies()).toEqual([{ twoSignal: true }]));
  });

  it('turning the rule off shows the amber block and a required checkbox that is first and gates the confirm', async () => {
    const dialog = await openDialog(tickRuleOff);
    expect(within(dialog).getByText('Two-source rule: off')).toBeInTheDocument();
    expect(within(dialog).getByRole('status')).toHaveTextContent(
      'Turning the rule off lets one source block an IP address or quarantine a file on its own in every organization. Every other limit still applies.',
    );
    const ack = within(dialog).getByRole('checkbox', { name: 'I understand this changes every organization.' });
    expect(ack).toHaveAttribute('aria-required', 'true');
    expect(ack).not.toBeChecked();
    await waitFor(() => expect(ack).toHaveFocus());
    const confirm = within(dialog).getByRole('button', { name: 'Apply to every organization' });
    expect(confirm).toBeDisabled();
    fireEvent.click(confirm);
    expect(bulks()).toHaveLength(0);
    fireEvent.click(ack);
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(bulkBodies()).toEqual([{ twoSignal: false }]));
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith('Settings applied to 4 organizations.', 'success'));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await waitFor(() => expect(gets().length).toBe(2));
  });

  it('both settings together list both lines and send both values', async () => {
    const dialog = await openDialog(() => { tickRuleOff(); tickBlock('3'); fireEvent.change(screen.getByLabelText('Block length unit'), { target: { value: 'days' } }); });
    expect(within(dialog).getByText('Two-source rule: off')).toBeInTheDocument();
    expect(within(dialog).getByText('Block length: 72 hours')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('checkbox'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply to every organization' }));
    await waitFor(() => expect(bulkBodies()).toEqual([{ twoSignal: false, blockHours: 72 }]));
  });

  it('Cancel and Esc write nothing, and Esc is ignored while the request is in flight', async () => {
    let release: (r: Response) => void = () => {};
    const dialog = await openDialog(() => tickBlock('12'), { bulk: () => new Promise<Response>(r => { release = r; }) });
    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(bulks()).toHaveLength(0);
    fireEvent.click(apply());
    const again = await screen.findByRole('dialog');
    fireEvent.click(within(again).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    fireEvent.click(apply());
    const third = await screen.findByRole('dialog');
    fireEvent.click(within(third).getByRole('button', { name: 'Apply to every organization' }));
    const busy = await within(third).findByRole('button', { name: 'Applying...' });
    expect(busy).toBeDisabled();
    fireEvent.keyDown(third, { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(within(third).getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expect(bulks()).toHaveLength(1);
    await act(async () => { release(jsonRes({ changed: ['t1'], failures: [] })); });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('a partial failure keeps the dialog, names the counts, and the retry sends only the failed organizations', async () => {
    let call = 0;
    const dialog = await openDialog(() => tickBlock('12'), {
      bulk: () => {
        call += 1;
        return call === 1
          ? jsonRes({ changed: ['t1', 't2'], failures: [
            { tenantId: 't3', name: 'Three', detail: 'The settings could not be saved for this organization.' },
            { tenantId: 't4', name: 'Four', detail: 'The settings could not be saved for this organization.' }] })
          : jsonRes({ changed: ['t3', 't4'], failures: [] });
      },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply to every organization' }));
    expect(await within(dialog).findByText(
      "Couldn't change 2 of 4 organizations: The settings could not be saved for this organization. The others were changed. Try again to retry the rest.",
    )).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(within(dialog).getByText('2 organizations will be changed.')).toBeInTheDocument();
    expect(mockToast).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply to every organization' }));
    await waitFor(() => expect(bulkBodies()).toEqual([{ blockHours: 12 }, { blockHours: 12, onlyTenants: ['t3', 't4'] }]));
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith('Settings applied to 4 organizations.', 'success'));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('when every organization failed the message still states the counts', async () => {
    const dialog = await openDialog(() => tickBlock('12'), {
      bulk: () => jsonRes({ changed: [], failures: [{ tenantId: 't1', name: 'One', detail: 'This organization no longer exists.' }] }),
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply to every organization' }));
    expect(await within(dialog).findByText(
      "Couldn't change 1 of 1 organization: This organization no longer exists. Try again.",
    )).toBeInTheDocument();
  });

  it('a refused request keeps the dialog open with the server message, or the connection fallback', async () => {
    const dialog = await openDialog(() => tickBlock('12'), { bulk: () => jsonRes({ detail: 'Choose at least one setting to change.' }, 422) });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply to every organization' }));
    expect(await within(dialog).findByText(
      "Couldn't save response settings: Choose at least one setting to change. Try again.",
    )).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Apply to every organization' })).toBeEnabled();
    routePlatform({ bulk: () => { throw new Error('offline'); } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply to every organization' }));
    expect(await within(dialog).findByText("Couldn't save response settings. Check your connection and try again.")).toBeInTheDocument();
  });

  it('a 403 closes the form with the permission toast', async () => {
    const dialog = await openDialog(() => tickBlock('12'), { bulk: () => jsonRes({ detail: 'no' }, 403) });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply to every organization' }));
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith("You don't have permission to change these settings.", 'error'));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(header()).toHaveAttribute('aria-expanded', 'false');
  });

  it('wraps a long failure message and never truncates', async () => {
    const long = 'x'.repeat(300);
    const dialog = await openDialog(() => tickBlock('12'), { bulk: () => jsonRes({ detail: long }, 500) });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply to every organization' }));
    const message = await within(dialog).findByText(new RegExp(long));
    expect(message.closest('[role="alert"]')).toHaveClass('break-words');
    // The dialog body and the card carry no clamp; the shared Modal title is a fixed string and is not data.
    expect(dialog.querySelector('[role="alert"]')?.outerHTML).not.toContain('truncate');
    expect(screen.getByRole('button', { name: TITLE }).closest('section')?.outerHTML).not.toContain('truncate');
  });
});

// ── who sees the card ───────────────────────────────────────────────────────

function screenFor(role: string, perms: string[], tenantId: string | null = null) {
  mockAuthFetch.mockImplementation(async (url: string) => {
    const path = url.split('?')[0];
    if (path === '/api/autonomous-ops/status') {
      return jsonRes({
        tenantId: 'tenant-a', tenantName: 'Acme Corp', scope: 'tenant', platformTenant: false, eligible: true, levelReadable: true,
        level: 'undoable_auto', maxLevel: 'undoable_auto', previousLevel: null, shadow: { effective: false, source: null },
        stop: { tenant: null, platform: null }, canStop: true, canResume: true, canStopPlatform: false, canResumePlatform: false,
      });
    }
    if (path === '/api/platform/autonomous-ops/status') {
      return jsonRes({ scope: 'platform', stop: { platform: null }, tenantStopsCount: 0, canStopPlatform: true, canResumePlatform: true });
    }
    if (path.endsWith('/autonomous-ops/actions')) return jsonRes({ items: [], nextCursor: null });
    if (path === '/api/autonomous-ops/response-settings') {
      return jsonRes({ twoSignal: true, blockHours: 24, watchedServices: [], readable: true, restartAvailable: true });
    }
    if (path === URL_GET) return jsonRes(dist());
    // The platform health and retention cards read their own routes; this test is about the settings card.
    return jsonRes({}, 500);
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

describe('Response settings for every organization: who sees it', () => {
  it('a Super Admin in platform scope sees it between Platform health and Activity', async () => {
    render(screenFor('Super Admin', ['*']));
    const card = await screen.findByRole('button', { name: TITLE });
    const activity = screen.getByRole('heading', { name: 'Activity' });
    expect(card.compareDocumentPosition(activity) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Response settings' })).toBeNull();
    expect(await screen.findByText(/^Two-source rule on in 3 organizations/)).toBeInTheDocument();
  });

  it('a Super Admin inside one organization gets the normal panel, not this card', async () => {
    render(screenFor('Super Admin', ['*'], 'tenant-a'));
    await screen.findByRole('button', { name: 'Response settings' });
    expect(screen.queryByRole('button', { name: TITLE })).toBeNull();
    expect(gets()).toHaveLength(0);
  });

  it('a Tenant Admin never sees it and no platform settings request is made', async () => {
    render(screenFor('Tenant Admin', ['view:autonomous_ops', 'manage:autonomous_ops']));
    await screen.findByRole('button', { name: 'Response settings' });
    expect(screen.queryByRole('button', { name: TITLE })).toBeNull();
    expect(gets()).toHaveLength(0);
  });
});
