/**
 * Phase 86 / GATE-09, D-14, D-15, D-16: the Going live card on the platform-scope Autonomous Ops screen.
 * The go-live service is mocked; payloads follow the 86-07 route contract (GET /golive, POST /golive/checks/{id},
 * PUT /tenants/{id}/shadow with a 409 {detail, reasons} on a refused lift).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../services/autonomousOpsGoLive', () => ({
  fetchGoLive: vi.fn(),
  recordGoLiveCheck: vi.fn(),
  setOrganizationShadow: vi.fn(),
}));
vi.mock('../../services/autonomousOpsReporting', () => ({
  fetchAutonomousOpsStatistics: vi.fn(),
  downloadAutonomousOpsExport: vi.fn(),
  downloadAutonomousOpsReport: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { authFetch } from '../../services/apiService';
import { fetchGoLive, recordGoLiveCheck, setOrganizationShadow } from '../../services/autonomousOpsGoLive';
import { fetchAutonomousOpsStatistics } from '../../services/autonomousOpsReporting';
import { showToast } from '../../utils/toast';
import { UserContext } from '../../contexts/UserContext';
import { AutonomousOpsStatusProvider } from '../../contexts/AutonomousOpsStatusContext';
import { AutonomousOpsActivity } from '../../components/AutonomousOpsActivity';
import { GoLiveCard } from '../../components/autonomousOpsGoLive/GoLiveCard';

const mockAuthFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
const fetchOverview = fetchGoLive as unknown as ReturnType<typeof vi.fn>;
const record = recordGoLiveCheck as unknown as ReturnType<typeof vi.fn>;
const setShadow = setOrganizationShadow as unknown as ReturnType<typeof vi.fn>;
const fetchStats = fetchAutonomousOpsStatistics as unknown as ReturnType<typeof vi.fn>;
const toast = showToast as unknown as ReturnType<typeof vi.fn>;

const IDS = ['firewall_round_trip', 'reboot_gate', 'watchdog_stop_start', 'alert_delivery', 'live_stop_drill'] as const;
const TITLES = ['Firewall round-trip', 'Reboot gate', 'Watchdog stop and start', 'Alert delivery', 'Live stop drill'];
const SUMMARY_LINES = [
  'Block a test address with Autonomous Ops, confirm the firewall refuses it, then undo the block and confirm the address works again.',
  'Confirm a patch that needs a reboot waits for approval on its card, and the machine does not restart on its own.',
  'Stop the watchdog timer on the server, confirm Platform health shows Silent, start it again and confirm it shows Running.',
  'Send a test alert from Platform health and confirm it reaches the on-call channel.',
  'Use Stop all organizations and confirm new decisions halt, queued instructions are held back, approvals and rollouts freeze and AI ticket replies pause. Then resume.',
];

interface RecordedFixture { by: string; at: string; note: string }
const checksFor = (recorded: Record<number, RecordedFixture> = {}) => IDS.map((id, i) => {
  const r = recorded[i];
  return {
    id, recorded: !!r, recordedBy: r ? { username: 'pat', display: r.by } : null,
    recordedAt: r ? r.at : null, note: r ? r.note : null,
  };
});
const REC = (by = 'Pat', note = 'Blocked our test address and undid it afterwards.'): RecordedFixture =>
  ({ by, at: '2026-11-12T14:02:00', note });

const overview = (recordedIdx: number[] = [], organizations: unknown[] = [], masterShadow = false) => ({
  checks: checksFor(Object.fromEntries(recordedIdx.map(i => [i, REC()]))),
  recordedCount: recordedIdx.length,
  organizations,
  masterShadow,
});

const apiError = (status: number, detail = '') => Object.assign(new Error(detail || `failed ${status}`), { status, detail, by: null });
const deferred = <T,>() => {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
};

const expand = async () => {
  const toggle = await screen.findByRole('button', { name: /Going live/ });
  fireEvent.click(toggle);
  return toggle;
};

beforeEach(() => {
  mockAuthFetch.mockReset();
  fetchOverview.mockReset();
  record.mockReset();
  setShadow.mockReset();
  fetchStats.mockReset();
  toast.mockReset();
});

// ── mounting and permissions ───────────────────────────────────────────────────────────────────────────

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

function routeFetch() {
  mockAuthFetch.mockImplementation(async (url: string) => {
    const path = url.split('?')[0];
    if (path === '/api/autonomous-ops/status') {
      return jsonRes({
        tenantId: 'tenant-a', tenantName: 'Acme Corp', scope: 'tenant', platformTenant: false, eligible: true,
        levelReadable: true, level: 'undoable_auto', maxLevel: 'undoable_auto', previousLevel: null,
        shadow: { effective: false, source: null }, stop: { tenant: null, platform: null },
        canStop: true, canResume: true, canStopPlatform: false, canResumePlatform: false,
      });
    }
    if (path === '/api/autonomous-ops/actions' || path === '/api/platform/autonomous-ops/actions') return jsonRes({ items: [], nextCursor: null });
    if (path === '/api/autonomous-ops/incidents' || path === '/api/autonomous-ops/rollout-cards') {
      return jsonRes({ items: [], total: 0, offset: 0, limit: 10, stopped: null });
    }
    if (path === '/api/platform/autonomous-ops/status') {
      return jsonRes({ scope: 'platform', stop: { platform: null }, tenantStopsCount: 0, canStopPlatform: true, canResumePlatform: true });
    }
    return jsonRes({}, 404);
  });
}

function screenFor(role: string, opts: { tenantId?: string | null; allowed?: boolean } = {}) {
  const { tenantId = null, allowed = true } = opts;
  return (
    <UserContext.Provider value={{
      currentUser: { id: 'u1', name: 'Pat', email: 'pat@example.com', role, tenantId: 'tenant-a', permissions: ['view:autonomous_ops'] } as any,
      login: async () => false, logout: () => {}, signup: async () => false,
      registerTenant: async () => false, hasPermission: () => allowed,
      enabledFeatures: [], serverLockedFeatures: {},
    }}>
      <AutonomousOpsStatusProvider tenantId={tenantId} enabled>
        <AutonomousOpsActivity tenantId={tenantId} />
      </AutonomousOpsStatusProvider>
    </UserContext.Provider>
  );
}

describe('where the Going live card appears', () => {
  it('shows for a Super Admin in platform scope, after the response settings and before Activity', async () => {
    routeFetch();
    fetchOverview.mockResolvedValue(overview());
    render(screenFor('Super Admin'));
    const toggle = await screen.findByRole('button', { name: /Going live/ });
    const settings = await screen.findByRole('button', { name: /Response settings for every organization/ });
    const activity = screen.getByRole('heading', { level: 2, name: 'Activity' });
    expect(settings.compareDocumentPosition(toggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(toggle.compareDocumentPosition(activity) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('is not rendered for a tenant admin', async () => {
    routeFetch();
    fetchStats.mockResolvedValue({
      tenantId: 'tenant-a', days: 30, generatedAt: '2026-11-13T09:00:00Z', shadowOnly: false, canExport: false, rules: [],
      totals: { fired: 0, done: 0, approved: 0, denied: 0, undone: 0, failed: 0, refused: 0, wouldHaveDone: 0 },
      timeSaved: { minutes: 0, estimate: true, perKind: [] },
    });
    render(screenFor('Tenant Admin'));
    await screen.findByRole('heading', { level: 2, name: 'Activity' });
    expect(screen.queryByRole('button', { name: /Going live/ })).toBeNull();
    expect(fetchOverview).not.toHaveBeenCalled();
  });

  it('is not rendered for a Super Admin viewing one organization', async () => {
    routeFetch();
    fetchStats.mockResolvedValue({
      tenantId: 'tenant-a', days: 30, generatedAt: '2026-11-13T09:00:00Z', shadowOnly: false, canExport: false, rules: [],
      totals: { fired: 0, done: 0, approved: 0, denied: 0, undone: 0, failed: 0, refused: 0, wouldHaveDone: 0 },
      timeSaved: { minutes: 0, estimate: true, perKind: [] },
    });
    render(screenFor('Super Admin', { tenantId: 'tenant-a' }));
    await screen.findByRole('heading', { level: 2, name: 'Activity' });
    expect(screen.queryByRole('button', { name: /Going live/ })).toBeNull();
    expect(fetchOverview).not.toHaveBeenCalled();
  });

  it('is not rendered without the platform owner permission', async () => {
    routeFetch();
    render(screenFor('Super Admin', { allowed: false }));
    await screen.findByRole('heading', { level: 2, name: 'Activity' });
    expect(screen.queryByRole('button', { name: /Going live/ })).toBeNull();
    expect(fetchOverview).not.toHaveBeenCalled();
  });
});

// ── the collapsed summary ─────────────────────────────────────────────────────────────────────────────

describe('the collapsed summary', () => {
  it('reads 3 of 5 checks and one organization out of shadow mode', async () => {
    fetchOverview.mockResolvedValue(overview([0, 1, 2], [
      { id: 'o1', name: 'Acme', shadow: false, daysObserved: 9, wouldHaveDone: 3, canLift: false, reasons: [] },
      { id: 'o2', name: 'Bolt', shadow: true, daysObserved: 2, wouldHaveDone: 1, canLift: false, reasons: [{ code: 'days_short', days: 2 }] },
    ]));
    render(<GoLiveCard />);
    expect(await screen.findByText('3 of 5 checks recorded · 1 organization out of shadow mode')).toBeInTheDocument();
  });

  it('reads All 5 checks recorded when every check has a record', async () => {
    fetchOverview.mockResolvedValue(overview([0, 1, 2, 3, 4]));
    render(<GoLiveCard />);
    expect(await screen.findByText('All 5 checks recorded')).toBeInTheDocument();
  });

  it('reads 0 of 5 checks and that no organization is out of shadow mode', async () => {
    fetchOverview.mockResolvedValue(overview());
    render(<GoLiveCard />);
    expect(await screen.findByText('0 of 5 checks recorded · No organization is out of shadow mode')).toBeInTheDocument();
  });

  it('uses the plural for several organizations', async () => {
    fetchOverview.mockResolvedValue(overview([0], [
      { id: 'o1', name: 'Acme', shadow: false, daysObserved: 9, wouldHaveDone: 3, canLift: false, reasons: [] },
      { id: 'o2', name: 'Bolt', shadow: false, daysObserved: 9, wouldHaveDone: 3, canLift: false, reasons: [] },
    ]));
    render(<GoLiveCard />);
    expect(await screen.findByText('1 of 5 checks recorded · 2 organizations out of shadow mode')).toBeInTheDocument();
  });

  it('shows a skeleton while loading and the failure summary with a red notice when the load fails', async () => {
    const pending = deferred<never>();
    fetchOverview.mockReturnValueOnce(pending.promise);
    const { container } = render(<GoLiveCard />);
    expect(container.querySelector('.h-4.w-72')).not.toBeNull();
    await act(async () => { pending.reject(apiError(500)); await Promise.resolve(); });
    expect(await screen.findByText("Go-live checks couldn't be loaded")).toBeInTheDocument();
    await expand();
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText("Couldn't load the go-live checks. Check your connection and try again.")).toBeInTheDocument();
    fetchOverview.mockResolvedValue(overview());
    fireEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('0 of 5 checks recorded · No organization is out of shadow mode')).toBeInTheDocument();
  });
});

// ── the expanded body ─────────────────────────────────────────────────────────────────────────────────

describe('the expanded checklist', () => {
  it('names the document and lists the five checks with the document sentences', async () => {
    fetchOverview.mockResolvedValue(overview());
    render(<GoLiveCard />);
    await expand();
    expect(await screen.findByText(/docs\/autonomous-ops-go-live\.md/)).toBeInTheDocument();
    const list = await screen.findByRole('list', { name: 'Go-live checks' });
    const rows = within(list).getAllByRole('listitem');
    expect(rows).toHaveLength(5);
    rows.forEach((row, i) => {
      expect(within(row).getByText(TITLES[i])).toBeInTheDocument();
      expect(within(row).getByText(SUMMARY_LINES[i])).toBeInTheDocument();
      expect(within(row).getByText('Not recorded')).toBeInTheDocument();
      expect(within(row).getByRole('button', { name: 'Record this check' })).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /Going live/ })).toHaveAttribute('aria-expanded', 'true');
  });

  it('shows five check skeletons with aria-busy while the first load is in flight', async () => {
    const pending = deferred<never>();
    fetchOverview.mockReturnValueOnce(pending.promise);
    const { container } = render(<GoLiveCard />);
    await expand();
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(container.querySelectorAll('.h-24')).toHaveLength(5);
  });

  it('refetches when the card is expanded', async () => {
    fetchOverview.mockResolvedValue(overview());
    render(<GoLiveCard />);
    await screen.findByText('0 of 5 checks recorded · No organization is out of shadow mode');
    expect(fetchOverview).toHaveBeenCalledTimes(1);
    await expand();
    await waitFor(() => expect(fetchOverview).toHaveBeenCalledTimes(2));
  });

  it('shows who recorded a check, when, the full note, Record again and the audit line', async () => {
    const note = 'Blocked our test address, the firewall refused it at 14:02, undone at 14:05.\nSecond line stays.';
    fetchOverview.mockResolvedValue({ ...overview([0]), checks: checksFor({ 0: { by: 'Pat', at: '2026-11-12T14:02:00', note } }) });
    render(<GoLiveCard />);
    await expand();
    const rows = within(await screen.findByRole('list', { name: 'Go-live checks' })).getAllByRole('listitem');
    expect(within(rows[0]).getByText('Recorded')).toBeInTheDocument();
    expect(within(rows[0]).getByText('Recorded by Pat on 12 Nov 2026 at 14:02')).toBeInTheDocument();
    const shownNote = within(rows[0]).getByText(/Blocked our test address/);
    expect(shownNote.textContent).toBe(note);
    expect(shownNote.className).toContain('whitespace-pre-wrap');
    expect(shownNote.className).toContain('break-words');
    expect(within(rows[0]).getByRole('button', { name: 'Record again' })).toBeInTheDocument();
    expect(within(rows[0]).getByText('Earlier records stay in the audit log.')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Not recorded')).toBeInTheDocument();
  });

  it('renders a hostile note and recorder name as text only', async () => {
    const hostile = '<img src=x onerror=alert(1)>';
    fetchOverview.mockResolvedValue({ ...overview([0]), checks: checksFor({ 0: { by: '<b>Eve</b>', at: '2026-11-12T14:02:00', note: hostile } }) });
    const { container } = render(<GoLiveCard />);
    await expand();
    expect(await screen.findByText(hostile)).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('b')).toBeNull();
  });
});

// ── recording a check ─────────────────────────────────────────────────────────────────────────────────

const openForm = async (index = 1) => {
  fetchOverview.mockResolvedValue(overview());
  render(<GoLiveCard />);
  await expand();
  const rows = within(await screen.findByRole('list', { name: 'Go-live checks' })).getAllByRole('listitem');
  const button = within(rows[index]).getByRole('button', { name: 'Record this check' });
  fireEvent.click(button);
  const field = await screen.findByLabelText('Note (required)');
  return { rows, button, field };
};

describe('the inline record form', () => {
  it('opens under the row with the textarea focused, the helper and a 0/500 counter', async () => {
    const { field } = await openForm();
    expect(field).toHaveFocus();
    expect(field).toHaveAttribute('maxlength', '500');
    expect(screen.getByText('0/500')).toBeInTheDocument();
    expect(screen.getByText(/Say what you did and what you saw, for example: Blocked our test address, the firewall refused it at 14:02, undone at 14:05\./)).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('keeps Record check disabled with its reason until the trimmed note has 10 characters', async () => {
    const { field } = await openForm();
    const submit = screen.getByRole('button', { name: 'Record check' });
    expect(submit).toBeDisabled();
    const reason = screen.getByText('Add a note of at least 10 characters.');
    expect(submit).toHaveAttribute('aria-describedby', expect.stringContaining(reason.id));
    fireEvent.change(field, { target: { value: '   short   ' } });
    expect(screen.getByText('11/500')).toBeInTheDocument();
    expect(submit).toBeDisabled();
    fireEvent.change(field, { target: { value: 'Long enough note.' } });
    expect(submit).toBeEnabled();
    expect(screen.queryByText('Add a note of at least 10 characters.')).toBeNull();
  });

  it('posts once, shows Recording..., then toasts and shows the new record in the row', async () => {
    const { field } = await openForm();
    const pending = deferred<unknown>();
    record.mockReturnValueOnce(pending.promise);
    fireEvent.change(field, { target: { value: '  Held the reboot until approval.  ' } });
    const submit = screen.getByRole('button', { name: 'Record check' });
    fireEvent.click(submit);
    fireEvent.click(screen.getByRole('button', { name: 'Recording...' }));
    expect(record).toHaveBeenCalledTimes(1);
    expect(record).toHaveBeenCalledWith('reboot_gate', 'Held the reboot until approval.');
    fetchOverview.mockResolvedValue({
      ...overview([1]),
      checks: checksFor({ 1: { by: 'Pat', at: '2026-11-12T14:02:00', note: 'Held the reboot until approval.' } }),
    });
    await act(async () => { pending.resolve({ id: 'GL-1' }); await Promise.resolve(); });
    await waitFor(() => expect(toast).toHaveBeenCalledWith('Check recorded: Reboot gate.', 'success'));
    expect(await screen.findByText('Recorded by Pat on 12 Nov 2026 at 14:02')).toBeInTheDocument();
    expect(screen.getByText('Held the reboot until approval.')).toBeInTheDocument();
    expect(screen.queryByLabelText('Note (required)')).toBeNull();
    expect(await screen.findByText('1 of 5 checks recorded · No organization is out of shadow mode')).toBeInTheDocument();
  });

  it('shows the platform administrator sentence for a 403 and keeps the note', async () => {
    const { field } = await openForm();
    record.mockRejectedValueOnce(apiError(403, 'Forbidden'));
    fireEvent.change(field, { target: { value: 'A note that stays put.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record check' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Only a platform administrator can record these checks.');
    expect(screen.getByLabelText('Note (required)')).toHaveValue('A note that stays put.');
    expect(toast).not.toHaveBeenCalled();
  });

  it('shows the fallback sentence for a server failure and keeps the note', async () => {
    const { field } = await openForm();
    record.mockRejectedValueOnce(apiError(500));
    fireEvent.change(field, { target: { value: 'A note that stays put.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record check' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't record the check. Check your connection and try again.");
    expect(screen.getByLabelText('Note (required)')).toHaveValue('A note that stays put.');
    expect(screen.getByRole('button', { name: 'Record check' })).toBeEnabled();
  });

  it('shows the server message for a refused record', async () => {
    const { field } = await openForm();
    record.mockRejectedValueOnce(apiError(422, 'the note must be 10 to 500 characters.'));
    fireEvent.change(field, { target: { value: 'A note that stays put.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record check' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't record the check: the note must be 10 to 500 characters. Try again.");
  });

  it('closes an empty form on Esc without asking', async () => {
    const { field, button } = await openForm();
    fireEvent.keyDown(field, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByLabelText('Note (required)')).toBeNull());
    expect(screen.queryByText('Discard this note?')).toBeNull();
    expect(button).toHaveFocus();
  });

  it('asks before discarding typed text: Keep editing keeps it, Discard note closes and returns focus', async () => {
    const { field, button } = await openForm();
    fireEvent.change(field, { target: { value: 'Half a note' } });
    fireEvent.keyDown(field, { key: 'Escape' });
    expect(await screen.findByText('Discard this note?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Keep editing' }));
    expect(screen.queryByText('Discard this note?')).toBeNull();
    expect(screen.getByLabelText('Note (required)')).toHaveValue('Half a note');
    fireEvent.click(screen.getByRole('button', { name: 'Close form' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Discard note' }));
    await waitFor(() => expect(screen.queryByLabelText('Note (required)')).toBeNull());
    expect(button).toHaveFocus();
  });

  it('opens one form at a time', async () => {
    const { rows } = await openForm(0);
    fireEvent.click(within(rows[2]).getByRole('button', { name: 'Record this check' }));
    await waitFor(() => expect(screen.getAllByLabelText('Note (required)')).toHaveLength(1));
    expect(within(rows[2]).getByLabelText('Note (required)')).toBeInTheDocument();
  });
});
