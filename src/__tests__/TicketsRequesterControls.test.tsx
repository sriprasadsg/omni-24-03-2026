/**
 * Phase 85 / DESK-01 (85-40, G-85-4b screen half, IN-604): the Tickets screen asks hasPermission('manage:tickets') and
 * hides every staff-only control from a requester. The server refuses those actions since 85-34; the screen now
 * matches. Ticket staff keep every control. The whole screen is rendered with mocked services.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const api = vi.hoisted(() => {
  const fn = () => vi.fn();
  return {
    fetchTickets: fn(), fetchTicketStats: fn(), createTicket: fn(), updateTicket: fn(), deleteTicket: fn(),
    addTicketComment: fn(), fetchTicketHistory: fn(), uploadTicketAttachment: fn(), deleteTicketAttachment: fn(),
    downloadTicketAttachment: fn(), linkTickets: fn(), unlinkTickets: fn(), logTicketWork: fn(), escalateTicket: fn(),
    approveTicket: fn(), rejectTicket: fn(), addTicketWatcher: fn(), removeTicketWatcher: fn(), bulkUpdateTickets: fn(),
    fetchTicketTemplates: fn(), fetchTicketFieldSchema: fn(), fetchAgents: fn(), authFetch: fn(), fetchTicket: fn(),
  };
});
const perms = vi.hoisted(() => new Set<string>());
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', ...api }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));
vi.mock('../../contexts/UserContext', () => ({
  useUser: () => ({ currentUser: { name: 'Nobody', email: '' }, hasPermission: (p: string) => perms.has(p) }),
}));
vi.mock('../../components/TicketReportsDashboard', () => ({ default: () => null }));

import InternalTicketsDashboard from '../../components/InternalTicketsDashboard';

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

const ticket = (over: Record<string, unknown> = {}) => ({
  id: 't-1', ticket_number: 'TKT-0042', title: 'Cannot reset password', description: '', type: 'task', priority: 'medium',
  status: 'open', assignee: '', assignee_group: '', watchers: [], reporter: 'dana@acme.test', tags: [],
  escalated: false, escalation_level: 0, approval_required: false, approval_status: '', custom_fields: {},
  links: [], attachments: [{ id: 'a-1', filename: 'notes.txt', size: 12, uploaded_by: 'dana@acme.test', created_at: '2026-11-09T09:30:00Z' }],
  comments: [], work_logs: [], created_at: '2026-11-09T09:00:00Z', updated_at: '2026-11-09T09:00:00Z',
  ...over,
});

const desk = (over: Record<string, unknown> = {}) => ({
  ticketId: 't-1', ticketNumber: 'TKT-0042', status: 'open', isRequester: false, requester: null, draft: null,
  canReplyToRequester: true, draftWaiting: false, ...over,
});

function setup(viewer: 'dana@acme.test' | 'sam@acme.test', tickets: unknown[], granted: string[] = []) {
  perms.clear();
  granted.forEach(p => perms.add(p));
  api.fetchTickets.mockResolvedValue({ tickets });
  api.fetchTicketStats.mockResolvedValue({ total: tickets.length, by_status: {}, by_priority: {} });
  api.fetchTicketTemplates.mockResolvedValue([]);
  api.fetchTicketFieldSchema.mockResolvedValue({ fields: [] });
  api.fetchTicketHistory.mockResolvedValue([]);
  api.fetchAgents.mockResolvedValue([]);
  api.authFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/service-desk') && !init?.method) return jsonRes(desk({ isRequester: viewer === 'dana@acme.test' }));
    return jsonRes({});
  });
  return render(<InternalTicketsDashboard currentUserEmail={viewer} />);
}

const asRequester = (tickets: unknown[] = [ticket()]) => setup('dana@acme.test', tickets);
const asStaff = (tickets: unknown[] = [ticket()], extra: string[] = []) => setup('sam@acme.test', tickets, ['manage:tickets', ...extra]);

const openTicket = async (title = 'Cannot reset password') => {
  fireEvent.click(await screen.findByText(title));
  await screen.findByRole('button', { name: 'Details' });
};
const tab = (name: string) => screen.queryByRole('button', { name });
const STATUS_BUTTONS = ['→ in progress', '→ resolved', '→ closed'];

beforeEach(() => {
  Object.values(api).forEach(m => m.mockReset());
  Element.prototype.scrollIntoView = vi.fn(); // jsdom has none; the Comments tab scrolls to its newest comment
});

// ------------------------------------------------------------------------------------------------- the ticket panel

describe('a requester opening their own ticket (G-85-4b)', () => {
  it('sees no status button, no Escalate, no Merge and no Watchers block', async () => {
    asRequester();
    await openTicket();
    STATUS_BUTTONS.forEach(n => expect(screen.queryByRole('button', { name: n })).toBeNull());
    expect(screen.queryByText('Escalate')).toBeNull();
    expect(screen.queryByText('Merge into another ticket')).toBeNull();
    expect(screen.queryByText('Watchers')).toBeNull();
    expect(screen.queryByPlaceholderText('Add watcher email…')).toBeNull();
  });

  it('keeps the Details, Comments, History and Files tabs and loses Work Log and Links', async () => {
    asRequester();
    await openTicket();
    ['Details', 'Comments', 'History', 'Files'].forEach(n => expect(tab(n)).not.toBeNull());
    expect(tab('Work Log')).toBeNull();
    expect(tab('Links')).toBeNull();
  });

  it('sees no staff hint on the Comments tab', async () => {
    asRequester();
    await openTicket();
    fireEvent.click(screen.getByRole('button', { name: 'Comments' }));
    await waitFor(() => expect(screen.getByText('No comments yet.')).toBeInTheDocument());
    expect(screen.queryByText(/Comments are visible to staff only/)).toBeNull();
  });

  it('can download a file but not delete it', async () => {
    asRequester();
    await openTicket();
    fireEvent.click(screen.getByRole('button', { name: 'Files' }));
    expect(await screen.findByText('notes.txt')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Upload File/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete notes.txt' })).toBeNull();
  });

  it('sees the Pending Approval heading but no Approve button and no rejection box', async () => {
    asRequester([ticket({ approval_required: true, approval_status: 'pending' })]);
    await openTicket();
    expect(screen.getByText('Pending Approval')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /approve/i })).toBeNull();
    expect(screen.queryByPlaceholderText('Rejection reason (required)')).toBeNull();
    expect(screen.queryByPlaceholderText('Optional comment…')).toBeNull();
  });

  it('sees the read-only install line and no Approve Install or deny control', async () => {
    asRequester([ticket({ tags: ['install-software'], approval_status: 'approved' })]);
    await openTicket();
    expect(screen.getByText(/Install approved/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Approve Install/ })).toBeNull();
  });

  it('cannot start the title edit, a PATCH only staff may send', async () => {
    asRequester();
    await openTicket();
    const heading = screen.getByRole('heading', { name: 'Cannot reset password' });
    fireEvent.click(heading);
    expect(screen.queryByDisplayValue('Cannot reset password')).toBeNull();
  });
});

describe('ticket staff (manage:tickets) on the same ticket', () => {
  it('see every control they saw before', async () => {
    asStaff();
    await openTicket();
    STATUS_BUTTONS.forEach(n => expect(screen.getByRole('button', { name: n })).toBeInTheDocument());
    expect(screen.getByText('Escalate', { selector: 'p' })).toBeInTheDocument();
    expect(screen.getByText('Merge into another ticket')).toBeInTheDocument();
    expect(screen.getByText('Watchers')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Add watcher email…')).toBeInTheDocument();
    ['Details', 'Comments', 'History', 'Files', 'Work Log', 'Links'].forEach(n => expect(tab(n)).not.toBeNull());
  });

  it('see the staff hint and the delete button for a file', async () => {
    asStaff();
    await openTicket();
    fireEvent.click(screen.getByRole('button', { name: 'Comments' }));
    expect(await screen.findByText(/Comments are visible to staff only/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Files' }));
    expect(await screen.findByRole('button', { name: 'Delete notes.txt' })).toBeInTheDocument();
  });

  it('see Approve and the rejection box on a ticket pending approval', async () => {
    asStaff([ticket({ approval_required: true, approval_status: 'pending' })]);
    await openTicket();
    expect(screen.getByText('Pending Approval')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Rejection reason (required)')).toBeInTheDocument();
  });

  it('can start the title edit', async () => {
    asStaff();
    await openTicket();
    fireEvent.click(screen.getByRole('heading', { name: 'Cannot reset password' }));
    expect(screen.getByDisplayValue('Cannot reset password')).toBeInTheDocument();
  });

  it('see the Approve Install button on an install request', async () => {
    asStaff([ticket({ tags: ['install-software'] })]);
    await openTicket();
    expect(screen.getByRole('button', { name: /Approve Install/ })).toBeInTheDocument();
    expect(screen.getByText(/Software Install Request/)).toBeInTheDocument();
  });
});
