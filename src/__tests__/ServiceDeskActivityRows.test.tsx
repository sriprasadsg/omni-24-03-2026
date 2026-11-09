/**
 * Phase 85 / DESK-01, DESK-04 (85-16): service desk rows in the Autonomous Ops Activity list (85-UI-SPEC section 5):
 * the ticket link, no Approve or Deny, Undo only where the server sends canUndo, and the desk's own toasts.
 * authFetch and the toast are mocked; the row fields follow 85-04-SUMMARY.md. Nothing here reaches a real API.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within, act } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: vi.fn() }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { authFetch } from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { UserContext } from '../../contexts/UserContext';
import { AutonomousOpsStatusProvider } from '../../contexts/AutonomousOpsStatusContext';
import { AutonomousOpsActivityList } from '../../components/AutonomousOpsActivityList';
import { buildOpenViewHandlers } from '../../components/AutonomousOpsRowActions';
import { DESK_SETTINGS_CHANGED } from '../../services/serviceDesk/settingsApi';

const mockAuthFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
const toast = showToast as unknown as ReturnType<typeof vi.fn>;

const NOW = Date.now();
const minutesAgo = (m: number) => new Date(NOW - m * 60_000).toISOString();

function row(over: Record<string, unknown> = {}) {
  return {
    id: 'r1', bucket: 'done', state: 'verified', createdAt: minutesAgo(12),
    actionLabel: 'Block IP address', classLine: 'Automatic',
    reasonText: 'Two sources agree: OTX and VirusTotal.', ruleId: 'sweep:block_ip',
    host: 'web-01.example.com', target: '45.33.32.156', resultText: 'Blocked.', controlEvent: null,
    canUndo: false, undoHint: null, incidentId: null, blockedUntil: null, suggestion: null,
    ticketId: null, ticketNumber: null,
    ...over,
  };
}

/** A posted answer: Done, with Undo, as 85-04 delivers it. */
const POSTED = row({
  id: 'd1', actionLabel: 'Post ticket answer', ruleId: null, host: null, target: null,
  reasonText: 'Ticket TKT-0042: "VPN will not connect" matched 2 Help desk articles.',
  resultText: 'Posted to the requester with 2 cited articles. Waiting for their reply.',
  canUndo: true, undoHint: 'Hides the answer from the requester and sends the ticket to a person.',
  ticketId: 'tk-42', ticketNumber: 'TKT-0042',
});
const DRAFT = row({
  id: 'd2', bucket: 'suggested', state: 'suggested', actionLabel: 'Draft ticket answer', classLine: 'Needs a person',
  ruleId: null, host: null, target: null, reasonText: 'Ticket TKT-0043: "Printer is offline" matched 1 Help desk article.',
  resultText: 'Draft kept for your team. Open the ticket to send, edit or discard it.',
  ticketId: 'tk-43', ticketNumber: 'TKT-0043',
});

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

const status = () => ({
  tenantId: 'tenant-a', tenantName: 'Acme Corp', scope: 'tenant', platformTenant: false,
  eligible: true, levelReadable: true, level: 'undoable_auto', maxLevel: 'undoable_auto', previousLevel: null,
  shadow: { effective: false, source: null }, stop: { tenant: null, platform: null },
  canStop: true, canResume: false, canStopPlatform: false, canResumePlatform: false,
});

type Undo = (url: string, init: RequestInit) => Response | Promise<Response>;

function route(opts: { rows?: unknown[]; undo?: Undo } = {}) {
  mockAuthFetch.mockImplementation(async (url: string, init: RequestInit = {}) => {
    const path = url.split('?')[0];
    if (path === '/api/autonomous-ops/status') return jsonRes(status());
    if (path === '/api/autonomous-ops/actions') return jsonRes({ items: opts.rows ?? [], nextCursor: null });
    if (/^\/api\/autonomous-ops\/actions\/[^/]+\/undo$/.test(path)) {
      return (opts.undo ?? (() => jsonRes({ status: 'undone', action: row({ id: 'd1', state: 'undone', bucket: 'undone', ticketNumber: 'TKT-0042' }), breakerTripped: false })))(url, init);
    }
    throw new Error(`unexpected request ${url}`);
  });
}

const undoPosts = () => mockAuthFetch.mock.calls.filter(c =>
  (c[1] as RequestInit | undefined)?.method === 'POST' && /\/undo$/.test((c[0] as string).split('?')[0]));

function shell(ui: React.ReactElement) {
  return (
    <UserContext.Provider value={{
      currentUser: { id: 'u1', name: 'Pat', email: 'p@example.com', role: 'Tenant Admin', tenantId: 'tenant-a', permissions: [] } as any,
      login: async () => false, logout: () => {}, signup: async () => false, registerTenant: async () => false,
      hasPermission: (() => true) as any, enabledFeatures: [], serverLockedFeatures: {},
    }}>
      <AutonomousOpsStatusProvider tenantId={null} enabled>{ui}</AutonomousOpsStatusProvider>
    </UserContext.Provider>
  );
}

const list = (props: Partial<React.ComponentProps<typeof AutonomousOpsActivityList>> = {}) => (
  <AutonomousOpsActivityList scope={{ kind: 'tenant', tenantId: null }} {...props} />
);

beforeEach(() => { mockAuthFetch.mockReset(); toast.mockReset(); });

const UNDO = 'Undo: Post ticket answer on TKT-0042';
const undoButton = async () => (await screen.findAllByRole('button', { name: UNDO }))[0];

describe('Desk rows: the ticket link', () => {
  it('shows "Open ticket TKT-0042" as a link that hands the ticket id to the Tickets opener', async () => {
    route({ rows: [POSTED] });
    const internalTickets = vi.fn();
    render(shell(list({ onOpenView: { internalTickets } })));
    const [link] = await screen.findAllByRole('button', { name: 'Open ticket TKT-0042' });
    expect(link.className).toContain('underline');
    expect(link.className).toContain('font-semibold');
    expect(link.querySelector('svg')).toHaveAttribute('width', '12');
    fireEvent.click(link);
    expect(internalTickets).toHaveBeenCalledWith('tk-42');
  });

  it('is plain text when the viewer cannot open Tickets', async () => {
    route({ rows: [POSTED] });
    render(shell(list({ onOpenView: {} })));
    expect((await screen.findAllByText('Open ticket TKT-0042')).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: 'Open ticket TKT-0042' })).toBeNull();
  });

  it('is plain text when the screen cannot navigate at all', async () => {
    route({ rows: [POSTED] });
    render(shell(list()));
    expect((await screen.findAllByText('Open ticket TKT-0042')).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /^Open ticket/ })).toBeNull();
  });

  it('appears on no other row', async () => {
    route({ rows: [row()] });
    render(shell(list({ onOpenView: { internalTickets: vi.fn() } })));
    await screen.findAllByText('Blocked.');
    expect(screen.queryByText(/Open ticket/)).toBeNull();
  });

  it('buildOpenViewHandlers offers the Tickets opener only to a viewer who may open Tickets', () => {
    const go = vi.fn();
    const can = { canPatch: false, canFim: false, canDraft: false };
    expect(buildOpenViewHandlers(go, { ...can, canTickets: false })?.internalTickets).toBeUndefined();
    expect(buildOpenViewHandlers(go, can)?.internalTickets).toBeUndefined();
    const handlers = buildOpenViewHandlers(go, { ...can, canTickets: true });
    handlers?.internalTickets?.('tk-42');
    expect(go).toHaveBeenCalledWith('internalTickets');
  });
});

describe('Desk rows: no Approve, no Deny', () => {
  it('a draft in the suggested bucket has the link and no decision control', async () => {
    route({ rows: [DRAFT] });
    render(shell(list({ onOpenView: { internalTickets: vi.fn() } })));
    await screen.findAllByRole('button', { name: 'Open ticket TKT-0043' });
    expect(screen.queryByRole('button', { name: /approve|deny/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Undo:/ })).toBeNull();
    expect(screen.getAllByText('Draft kept for your team. Open the ticket to send, edit or discard it.').length).toBeGreaterThan(0);
  });

  it('never links a desk row to a Needs your decision card, even if an incident id came with it', async () => {
    route({ rows: [{ ...DRAFT, bucket: 'pending', state: 'pending', incidentId: 'inc-1' }] });
    render(shell(list({ decisionIds: new Set(['inc-1']), onOpenView: {} })));
    await screen.findAllByText('Open ticket TKT-0043');
    expect(screen.queryByRole('button', { name: 'Review in Needs your decision' })).toBeNull();
  });
});

describe('Desk rows: Undo', () => {
  it('renders Undo with the desk aria-label and the server hint when the server says canUndo', async () => {
    route({ rows: [POSTED] });
    render(shell(list()));
    const button = await undoButton();
    expect(within(button).getByText('Undo')).toBeInTheDocument();
    expect(screen.getAllByText('Hides the answer from the requester and sends the ticket to a person.').length).toBeGreaterThan(0);
  });

  it('shows Undoing... while pending and sends one request for two clicks', async () => {
    let release: (r: Response) => void = () => {};
    route({ rows: [POSTED], undo: () => new Promise<Response>(res => { release = res; }) });
    render(shell(list()));
    const button = await undoButton();
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => expect(button).toBeDisabled());
    expect(within(button).getByText('Undoing...')).toBeInTheDocument();
    expect(undoPosts()).toHaveLength(1);
    expect(undoPosts()[0][0]).toBe('/api/autonomous-ops/actions/d1/undo');
    await act(async () => { release(jsonRes({ status: 'undone', action: row({ id: 'd1', bucket: 'undone', ticketNumber: 'TKT-0042' }), breakerTripped: false })); });
  });

  it('on success toasts that the ticket went to a person, and leaves the desk card alone', async () => {
    const changed = vi.fn();
    window.addEventListener(DESK_SETTINGS_CHANGED, changed);
    route({ rows: [POSTED] });
    render(shell(list()));
    fireEvent.click(await undoButton());
    await waitFor(() => expect(toast).toHaveBeenCalledWith('Answer withdrawn. Ticket TKT-0042 went to a person.', 'success'));
    expect(changed).not.toHaveBeenCalled();
    window.removeEventListener(DESK_SETTINGS_CHANGED, changed);
  });

  it('when the withdrawal dropped the desk to Drafts only, toasts the info text and tells the Service desk card to read again', async () => {
    const changed = vi.fn();
    window.addEventListener(DESK_SETTINGS_CHANGED, changed);
    route({
      rows: [POSTED],
      undo: () => jsonRes({ status: 'undone', action: row({ id: 'd1', bucket: 'undone', ticketNumber: 'TKT-0042' }), breakerTripped: false, deskBreakerTripped: true }),
    });
    render(shell(list()));
    fireEvent.click(await undoButton());
    await waitFor(() => expect(toast).toHaveBeenCalledWith(
      'Answer withdrawn. 3 answers were withdrawn within 24 hours, so the service desk dropped to Drafts only. A person with manage access can restore it.',
      'info',
    ));
    expect(changed).toHaveBeenCalledTimes(1);
    window.removeEventListener(DESK_SETTINGS_CHANGED, changed);
  });

  it('a security breaker flag on a desk row never produces the security wording', async () => {
    route({
      rows: [POSTED],
      undo: () => jsonRes({ status: 'undone', action: row({ id: 'd1', bucket: 'undone', ticketNumber: 'TKT-0042' }), breakerTripped: true, deskBreakerTripped: false }),
    });
    render(shell(list()));
    fireEvent.click(await undoButton());
    await waitFor(() => expect(toast).toHaveBeenCalledTimes(1));
    expect(toast).toHaveBeenCalledWith('Answer withdrawn. Ticket TKT-0042 went to a person.', 'success');
  });

  it('a refusal shows the server words under the button and Undo stays', async () => {
    route({ rows: [POSTED], undo: () => jsonRes({ detail: 'This action cannot be undone.' }, 409) });
    render(shell(list()));
    fireEvent.click(await undoButton());
    const alerts = await screen.findAllByRole('alert');
    expect(alerts[0]).toHaveTextContent("Couldn't undo this action: This action cannot be undone. Try again.");
    expect(alerts[0].className).toContain('break-words');
    expect(screen.getAllByRole('button', { name: UNDO }).length).toBeGreaterThan(0);
  });

  it('with canUndo false there is no Undo and the server result text is shown as sent', async () => {
    const confirmed = row({
      id: 'd3', actionLabel: 'Post ticket answer', ticketId: 'tk-44', ticketNumber: 'TKT-0044',
      resultText: 'A person replied after this answer. Undo is no longer available.', canUndo: false, undoHint: null,
    });
    route({ rows: [confirmed] });
    render(shell(list({ onOpenView: {} })));
    expect((await screen.findAllByText('A person replied after this answer. Undo is no longer available.')).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /^Undo:/ })).toBeNull();
  });

  it('a security row keeps its own aria-label and toast', async () => {
    route({
      rows: [row({ canUndo: true, undoHint: 'Removes the block on 45.33.32.156.' })],
      undo: () => jsonRes({ status: 'undone', action: row({ bucket: 'undone' }), breakerTripped: false }),
    });
    render(shell(list()));
    fireEvent.click((await screen.findAllByRole('button', { name: 'Undo: Block IP address on web-01.example.com' }))[0]);
    await waitFor(() => expect(toast).toHaveBeenCalledWith('Undo sent to web-01.example.com.', 'success'));
  });
});

describe('Desk rows: long text', () => {
  it('a 200-character ticket title in the Why cell wraps inside the row', async () => {
    const title = 'T'.repeat(200);
    route({ rows: [{ ...POSTED, reasonText: `Ticket TKT-0042: "${title}" matched 1 Help desk article.` }] });
    render(shell(list()));
    const [cell] = await screen.findAllByText(new RegExp(`"${title}"`));
    expect(cell.className).toContain('break-words');
  });
});
