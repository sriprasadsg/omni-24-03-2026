/**
 * Phase 86 / GATE-09, D-23 (plan 86-15): the go-live test organization on the Going live card.
 * The go-live service is mocked; payloads follow the 86-14 route contract (GET /golive adds testOrganization and a
 * per-row testOrganization, POST and DELETE /golive/test-organization answer 409 or 422 with a plain sentence).
 * The card never decides on its own: it renders what the server says and shows the server's refusal sentences.
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
  markTestOrganization: vi.fn(),
  clearTestOrganization: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import {
  fetchGoLive, setOrganizationShadow, markTestOrganization, clearTestOrganization,
} from '../../services/autonomousOpsGoLive';
import { showToast } from '../../utils/toast';
import { GoLiveCard } from '../../components/autonomousOpsGoLive/GoLiveCard';

const fetchOverview = fetchGoLive as unknown as ReturnType<typeof vi.fn>;
const setShadow = setOrganizationShadow as unknown as ReturnType<typeof vi.fn>;
const mark = markTestOrganization as unknown as ReturnType<typeof vi.fn>;
const clear = clearTestOrganization as unknown as ReturnType<typeof vi.fn>;
const toast = showToast as unknown as ReturnType<typeof vi.fn>;

const IDS = ['firewall_round_trip', 'reboot_gate', 'watchdog_stop_start', 'alert_delivery', 'live_stop_drill'] as const;
const checks = (recordedAll = false) => IDS.map(id => ({
  id, recorded: recordedAll,
  recordedBy: recordedAll ? { username: 'pat', display: 'Pat' } : null,
  recordedAt: recordedAll ? '2026-11-12T14:02:00' : null,
  note: recordedAll ? 'Blocked our test address and undid it afterwards.' : null,
}));

interface Mark { id: string; name: string; markedBy: string; markedAt: string }
const overview = (organizations: unknown[], testOrganization: Mark | null = null) => ({
  checks: checks(), recordedCount: 0, organizations, masterShadow: false, testOrganization,
});

const ACME = {
  id: 'acme-id', name: 'Acme', shadow: true, daysObserved: 5, wouldHaveDone: 18, canLift: false, testOrganization: false,
  reasons: [{ code: 'checks_missing', recorded: 0 }, { code: 'days_short', days: 5 }],
};
const BOLT = { id: 'bolt-id', name: 'Bolt', shadow: true, daysObserved: 0, wouldHaveDone: 0, canLift: false, testOrganization: false, reasons: [{ code: 'no_shadow_records' }] };
const SANDBOX_ON = { id: 'sandbox-id', name: 'Sandbox', shadow: true, daysObserved: null, wouldHaveDone: 0, canLift: true, testOrganization: true, reasons: [] };
const SANDBOX_OFF = { ...SANDBOX_ON, shadow: false };
const SANDBOX_MARK: Mark = { id: 'sandbox-id', name: 'Sandbox', markedBy: 'Pat', markedAt: '2026-11-13T09:00:00' };

const apiError = (status: number, detail = '') => Object.assign(new Error(detail || `failed ${status}`), { status, detail, by: null });
const deferred = <T,>() => {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
};
const describedBy = (el: HTMLElement) =>
  (el.getAttribute('aria-describedby') ?? '').split(' ').filter(Boolean).map(id => document.getElementById(id)?.textContent);

const renderExpanded = async (organizations: unknown[], testOrganization: Mark | null = null) => {
  fetchOverview.mockResolvedValue(overview(organizations, testOrganization));
  render(<GoLiveCard />);
  fireEvent.click(await screen.findByRole('button', { name: /Going live/ }));
  await screen.findByRole('heading', { level: 3, name: 'Organizations' });
};
const orgTable = () => screen.getByRole('table', { name: 'Shadow mode by organization' });
const orgRow = (name: string) => {
  const row = within(orgTable()).getAllByRole('row').find(r => within(r).queryByText(name));
  if (!row) throw new Error(`no row for ${name}`);
  return row;
};

beforeEach(() => {
  fetchOverview.mockReset();
  setShadow.mockReset();
  mark.mockReset();
  clear.mockReset();
  toast.mockReset();
});

describe('marking offers, with no test organization marked', () => {
  it('shows Use as test organization on every row and no label or Clear test mark anywhere', async () => {
    await renderExpanded([ACME, BOLT]);
    expect(within(orgRow('Acme')).getByRole('button', { name: 'Use as test organization' })).toBeEnabled();
    expect(within(orgRow('Bolt')).getByRole('button', { name: 'Use as test organization' })).toBeEnabled();
    expect(screen.queryByText('Test organization')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Clear test mark' })).toBeNull();
  });
});

describe('a marked test organization', () => {
  it('shows the Test organization label as text on that row only and offers marking on no row', async () => {
    await renderExpanded([ACME, SANDBOX_ON], SANDBOX_MARK);
    const sandbox = orgRow('Sandbox');
    expect(within(sandbox).getByText('Test organization')).toBeInTheDocument();
    expect(within(sandbox).getByRole('button', { name: 'Clear test mark' })).toBeEnabled();
    expect(within(orgRow('Acme')).queryByText('Test organization')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Use as test organization' })).toBeNull();
  });

  it('keeps the server canLift: the marked row can be lifted because the server says so, a customer row stays disabled', async () => {
    await renderExpanded([ACME, SANDBOX_ON], SANDBOX_MARK);
    expect(within(orgRow('Sandbox')).getByRole('button', { name: 'Lift shadow mode' })).toBeEnabled();
    expect(within(orgRow('Acme')).getByRole('button', { name: 'Lift shadow mode' })).toBeDisabled();
  });

  it('disables Clear test mark with the visible reason while shadow mode is off, pointed to by aria-describedby', async () => {
    await renderExpanded([SANDBOX_OFF], SANDBOX_MARK);
    const sandbox = orgRow('Sandbox');
    const button = within(sandbox).getByRole('button', { name: 'Clear test mark' });
    expect(button).toBeDisabled();
    expect(within(sandbox).getByText('Turn shadow mode back on first.')).toBeInTheDocument();
    expect(describedBy(button)).toContain('Turn shadow mode back on first.');
    expect(within(sandbox).getByRole('button', { name: 'Turn shadow mode back on' })).toBeEnabled();
  });

  it('shows the label also from the per-row flag when the top-level mark is missing', async () => {
    await renderExpanded([ACME, SANDBOX_ON], null);
    expect(within(orgRow('Sandbox')).getByText('Test organization')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Use as test organization' })).toBeNull();
  });
});

const openMark = async () => {
  await renderExpanded([ACME, BOLT]);
  fireEvent.click(within(orgRow('Acme')).getByRole('button', { name: 'Use as test organization' }));
  const dialog = await screen.findByRole('dialog', { name: 'Use Acme as the go-live test organization?' });
  const input = within(dialog).getByLabelText('Type Acme to confirm');
  return { dialog, input, confirm: within(dialog).getByRole('button', { name: 'Use as test organization' }) };
};

describe('the Mark dialog', () => {
  it('explains the exemption, focuses the typed-name input and keeps the confirm disabled with its reason', async () => {
    const { dialog, input, confirm } = await openMark();
    expect(input).toHaveFocus();
    expect(within(dialog).getByText(
      "This organization can leave shadow mode before the five checks are recorded and without the seven days of shadow records, so you can walk checks 1, 2 and 5. Use a dedicated test organization, never a customer's. Only one organization can be marked. This is recorded in the platform audit log.",
    )).toBeInTheDocument();
    expect(confirm).toBeDisabled();
    expect(describedBy(confirm)).toContain('Type the name to continue.');
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });

  it('stays disabled for a different or partly typed name and enables for the exact name after trimming', async () => {
    const { input, confirm } = await openMark();
    fireEvent.change(input, { target: { value: 'acme' } });
    expect(confirm).toBeDisabled();
    fireEvent.change(input, { target: { value: 'Acm' } });
    expect(confirm).toBeDisabled();
    fireEvent.change(input, { target: { value: ' Acme ' } });
    expect(confirm).toBeEnabled();
  });

  it('marks once, shows Marking..., then toasts, closes and reloads the card', async () => {
    const { dialog, input, confirm } = await openMark();
    const pending = deferred<unknown>();
    mark.mockReturnValueOnce(pending.promise);
    fireEvent.change(input, { target: { value: 'Acme' } });
    fireEvent.click(confirm);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Marking...' }));
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(screen.getByRole('dialog', { name: 'Use Acme as the go-live test organization?' })).toBeInTheDocument();
    expect(mark).toHaveBeenCalledTimes(1);
    expect(mark).toHaveBeenCalledWith('acme-id', 'Acme');
    const before = fetchOverview.mock.calls.length;
    await act(async () => { pending.resolve({}); await Promise.resolve(); });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(toast).toHaveBeenCalledWith('Acme is now the test organization.', 'success');
    expect(fetchOverview.mock.calls.length).toBeGreaterThan(before);
  });

  it('sends the typed text with the surrounding spaces the person typed removed', async () => {
    const { input, confirm } = await openMark();
    mark.mockResolvedValueOnce({});
    fireEvent.change(input, { target: { value: '  Acme ' } });
    fireEvent.click(confirm);
    await waitFor(() => expect(mark).toHaveBeenCalledWith('acme-id', 'Acme'));
  });

  it.each([
    [409, 'Sandbox is already the test organization. Clear that mark first.'],
    [422, "Type the organization's name exactly to confirm."],
    [404, 'Organization not found'],
  ])('shows the server sentence for a %s in an alert, keeps the input and does not toast', async (status, sentence) => {
    const { dialog, input, confirm } = await openMark();
    mark.mockRejectedValueOnce(apiError(status, sentence));
    fireEvent.change(input, { target: { value: 'Acme' } });
    fireEvent.click(confirm);
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(sentence);
    expect(input).toHaveValue('Acme');
    expect(toast).not.toHaveBeenCalled();
    expect(within(dialog).getByRole('button', { name: 'Use as test organization' })).toBeEnabled();
  });

  it('shows a fallback sentence for a network failure and closes on Cancel without writing', async () => {
    const { dialog, input, confirm } = await openMark();
    mark.mockRejectedValueOnce(apiError(500, ''));
    fireEvent.change(input, { target: { value: 'Acme' } });
    fireEvent.click(confirm);
    expect(await within(dialog).findByRole('alert')).toHaveTextContent("Couldn't mark the test organization. Check your connection and try again.");
    mark.mockClear();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(mark).not.toHaveBeenCalled();
  });

  it('renders a hostile organization name and server sentence as plain text', async () => {
    const hostile = { ...ACME, id: 'x-id', name: '<img src=x onerror=alert(1)>' };
    await renderExpanded([hostile]);
    fireEvent.click(within(orgRow(hostile.name)).getByRole('button', { name: 'Use as test organization' }));
    const dialog = await screen.findByRole('dialog');
    mark.mockRejectedValueOnce(apiError(409, '<b>bold</b> is already the test organization. Clear that mark first.'));
    fireEvent.change(within(dialog).getByLabelText(`Type ${hostile.name} to confirm`), { target: { value: hostile.name } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Use as test organization' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('<b>bold</b> is already the test organization.');
    expect(dialog.querySelector('img')).toBeNull();
    expect(dialog.querySelector('b')).toBeNull();
  });
});

const openClear = async (row = SANDBOX_ON) => {
  await renderExpanded([ACME, row], SANDBOX_MARK);
  fireEvent.click(within(orgRow('Sandbox')).getByRole('button', { name: 'Clear test mark' }));
  const dialog = await screen.findByRole('dialog', { name: 'Clear the test mark on Sandbox?' });
  return { dialog, confirm: within(dialog).getByRole('button', { name: 'Clear test mark' }) };
};

describe('the Clear test mark dialog', () => {
  it('opens only while shadow mode is on, with the customer-rules sentence', async () => {
    const { dialog, confirm } = await openClear(SANDBOX_ON);
    expect(within(dialog).getByText(
      'Customer rules apply to it again: it needs the five checks and seven days before it can leave shadow mode.',
    )).toBeInTheDocument();
    expect(confirm).toBeEnabled();
    expect(within(dialog).queryByRole('textbox')).toBeNull();
  });

  it('clears once, shows Clearing..., then toasts, closes and reloads the card', async () => {
    const { dialog, confirm } = await openClear(SANDBOX_ON);
    const pending = deferred<unknown>();
    clear.mockReturnValueOnce(pending.promise);
    fireEvent.click(confirm);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Clearing...' }));
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(clear).toHaveBeenCalledTimes(1);
    expect(clear).toHaveBeenCalledWith('sandbox-id');
    const before = fetchOverview.mock.calls.length;
    await act(async () => { pending.resolve({}); await Promise.resolve(); });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(toast).toHaveBeenCalledWith('The test mark on Sandbox is cleared.', 'success');
    expect(fetchOverview.mock.calls.length).toBeGreaterThan(before);
  });

  it('shows the server sentence for a 409 in an alert and keeps the dialog open', async () => {
    const { dialog, confirm } = await openClear(SANDBOX_ON);
    clear.mockRejectedValueOnce(apiError(409, 'Turn shadow mode back on for Sandbox first.'));
    fireEvent.click(confirm);
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Turn shadow mode back on for Sandbox first.');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(toast).not.toHaveBeenCalled();
  });

  it('closes on Keep test mark without writing', async () => {
    const { dialog } = await openClear(SANDBOX_ON);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Keep test mark' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(clear).not.toHaveBeenCalled();
  });
});

const TEST_ORG_NOTE =
  'Test organization: the five checks and the seven days are not required. The lift is recorded as a test-organization lift.';
const ACME_READY = { ...ACME, daysObserved: 7, canLift: true, reasons: [] };

const openLift = async (name: string, organizations: unknown[], testOrganization: Mark | null) => {
  await renderExpanded(organizations, testOrganization);
  fireEvent.click(within(orgRow(name)).getByRole('button', { name: 'Lift shadow mode' }));
  const dialog = await screen.findByRole('dialog', { name: `Lift shadow mode for ${name}?` });
  const input = within(dialog).getByLabelText('Type the organization name to confirm');
  return { dialog, input, confirm: within(dialog).getByRole('button', { name: 'Lift shadow mode' }) };
};

describe('the Lift dialog for the test organization', () => {
  it('says the checks and the seven days are not required, above the typed-name confirmation', async () => {
    const { dialog, input } = await openLift('Sandbox', [ACME, SANDBOX_ON], SANDBOX_MARK);
    const note = within(dialog).getByText(TEST_ORG_NOTE);
    expect(note.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('does not claim the five checks are recorded, because they are not required for it', async () => {
    const { dialog } = await openLift('Sandbox', [SANDBOX_ON], SANDBOX_MARK);
    expect(within(dialog).queryByText(/All 5 go-live checks are recorded\./)).toBeNull();
  });

  it('keeps the typed-name confirmation: disabled until the exact name, then lifts once through the server', async () => {
    const { dialog, input, confirm } = await openLift('Sandbox', [SANDBOX_ON], SANDBOX_MARK);
    expect(confirm).toBeDisabled();
    expect(within(dialog).getByText('Type the name to continue.')).toBeInTheDocument();
    fireEvent.change(input, { target: { value: 'sandbox' } });
    expect(confirm).toBeDisabled();
    setShadow.mockResolvedValueOnce({});
    fireEvent.change(input, { target: { value: 'Sandbox' } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(setShadow).toHaveBeenCalledWith('sandbox-id', false));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(setShadow).toHaveBeenCalledTimes(1);
  });

  it('shows the server sentence for a refused lift and refetches', async () => {
    const { dialog, input, confirm } = await openLift('Sandbox', [SANDBOX_ON], SANDBOX_MARK);
    setShadow.mockRejectedValueOnce(apiError(409, 'Record all 5 go-live checks first (0 of 5 recorded).'));
    fireEvent.change(input, { target: { value: 'Sandbox' } });
    const before = fetchOverview.mock.calls.length;
    fireEvent.click(confirm);
    expect(await within(dialog).findByRole('alert')).toHaveTextContent("Shadow mode can't be lifted yet: Record all 5 go-live checks first (0 of 5 recorded).");
    await waitFor(() => expect(fetchOverview.mock.calls.length).toBeGreaterThan(before));
  });

  it('leaves the dialog unchanged for any other organization: evidence line, no test-organization note', async () => {
    const { dialog } = await openLift('Acme', [ACME_READY, SANDBOX_ON], SANDBOX_MARK);
    expect(within(dialog).queryByText(TEST_ORG_NOTE)).toBeNull();
    expect(within(dialog).getByText('7 days of shadow records. 18 actions would have been done. All 5 go-live checks are recorded.')).toBeInTheDocument();
  });
});
