/**
 * Phase 85 / DESK-01 (85-40, G-85-4b screen half, IN-604): the Tickets screen asks hasPermission('manage:tickets') and
 * hides every staff-only control from a requester. The server refuses those actions since 85-34; the screen now
 * matches. Ticket staff keep every control. The whole screen is rendered with mocked services.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';

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

// ------------------------------------------------------------------------------------ the list, the board and the form

const listCheckboxes = async () => {
  const table = (await screen.findByText('Cannot reset password')).closest('table')!;
  return within(table).queryAllByRole('checkbox');
};
const FORM_LABELS = ['Assignee (email)', 'Team / Group', 'Due Date', 'SLA Hours (override)', 'Requires approval before processing'];
const openForm = async () => {
  await screen.findByText('Cannot reset password');
  fireEvent.click(screen.getByRole('button', { name: /New Ticket/ }));
  return screen.findByPlaceholderText('Brief summary of the issue');
};

describe('the list and the bulk bar', () => {
  it('give a requester no row checkbox, no bulk bar and no delete button', async () => {
    asRequester();
    expect(await listCheckboxes()).toHaveLength(0);
    expect(screen.queryByText(/selected$/)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Delete TKT-0042' })).toBeNull();
    fireEvent.click(document.querySelector('button svg[class*="lucide-filter"], button svg[class*="lucide-funnel"]')!.closest('button')!);
    expect(await screen.findByRole('checkbox', { name: /Overdue only/ })).toBeInTheDocument(); // the filter boxes stay
    expect(screen.getByRole('checkbox', { name: /My tickets/ })).toBeInTheDocument();
  });

  it('give ticket staff the checkboxes and the bulk bar but no delete without manage:settings', async () => {
    asStaff();
    const boxes = await listCheckboxes();
    expect(boxes).toHaveLength(2);
    fireEvent.click(boxes[1]);
    expect(await screen.findByText('1 selected')).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Delete selected' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Delete TKT-0042' })).toBeNull();
  });

  it('give staff with manage:settings the row delete button and the Delete selected option', async () => {
    asStaff([ticket()], ['manage:settings']);
    const boxes = await listCheckboxes();
    fireEvent.click(boxes[1]);
    expect(await screen.findByRole('option', { name: 'Delete selected' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete TKT-0042' })).toBeInTheDocument();
  });
});

describe('the board', () => {
  const cards = async () => {
    await screen.findByText('Cannot reset password');
    fireEvent.click(screen.getByTitle('Kanban view'));
    return (await screen.findByText('Cannot reset password')).closest('[draggable]') as HTMLElement | null;
  };

  it('makes no card draggable for a requester', async () => {
    asRequester();
    const card = await cards();
    expect(card === null || card.getAttribute('draggable') !== 'true').toBe(true);
  });

  it('makes cards draggable for ticket staff', async () => {
    asStaff();
    const card = await cards();
    expect(card?.getAttribute('draggable')).toBe('true');
  });

  it('does not move a ticket when a requester drops one on a column', async () => {
    asRequester();
    await cards();
    const column = screen.getByText('In Progress').closest('div[class*="w-72"]')!;
    fireEvent.drop(column, { dataTransfer: { getData: () => 't-1' } });
    expect(api.updateTicket).not.toHaveBeenCalled();
  });
});

describe('the New Ticket form', () => {
  it('shows a requester no staff-only input', async () => {
    asRequester();
    await openForm();
    FORM_LABELS.forEach(l => expect(screen.queryByText(l)).toBeNull());
    expect(screen.getByText('Title *')).toBeInTheDocument();
  });

  it('shows ticket staff all five inputs', async () => {
    asStaff();
    await openForm();
    FORM_LABELS.forEach(l => expect(screen.getByText(l)).toBeInTheDocument());
  });

  it('sends a requester payload without any staff-only key', async () => {
    api.createTicket.mockResolvedValue(ticket({ ticket_number: 'TKT-0043' }));
    asRequester();
    const title = await openForm();
    fireEvent.change(title, { target: { value: 'Printer jam' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Ticket' }));
    await waitFor(() => expect(api.createTicket).toHaveBeenCalledTimes(1));
    const payload = api.createTicket.mock.calls[0][0];
    ['assignee', 'assignee_group', 'watchers', 'approval_required', 'sla_hours', 'due_date'].forEach(k => expect(payload).not.toHaveProperty(k));
    expect(payload.title).toBe('Printer jam');
  });

  it('keeps the staff-only keys in the payload of ticket staff', async () => {
    api.createTicket.mockResolvedValue(ticket({ ticket_number: 'TKT-0044' }));
    asStaff();
    const title = await openForm();
    fireEvent.change(title, { target: { value: 'Rack swap' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Ticket' }));
    await waitFor(() => expect(api.createTicket).toHaveBeenCalledTimes(1));
    expect(api.createTicket.mock.calls[0][0]).toHaveProperty('assignee');
    expect(api.createTicket.mock.calls[0][0]).toHaveProperty('approval_required');
  });
});
