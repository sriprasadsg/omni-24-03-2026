/**
 * Phase 85 / DESK-01 (85-41, G-85-4b error half, PROH-85-35, T-85-140): a staff action on the Tickets screen that
 * fails shows an error toast with the error's message instead of failing silently. The whole screen is rendered
 * with mocked services; a rejecting helper stands for a refused (403), failed (500) or unreachable call.
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
import { showToast } from '../../utils/toast';

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

const ticket = (over: Record<string, unknown> = {}) => ({
  id: 't-1', ticket_number: 'TKT-0042', title: 'Cannot reset password', description: '', type: 'task', priority: 'medium',
  status: 'open', assignee: '', assignee_group: '', watchers: ['old@acme.test'], reporter: 'dana@acme.test', tags: [],
  escalated: false, escalation_level: 0, approval_required: false, approval_status: '', custom_fields: {},
  links: [], attachments: [{ id: 'a-1', filename: 'notes.txt', size: 12, uploaded_by: 'dana@acme.test', created_at: '2026-11-09T09:30:00Z' }],
  comments: [], work_logs: [], created_at: '2026-11-09T09:00:00Z', updated_at: '2026-11-09T09:00:00Z',
  ...over,
});

const desk = () => ({
  ticketId: 't-1', ticketNumber: 'TKT-0042', status: 'open', isRequester: false, requester: null, draft: null,
  canReplyToRequester: true, draftWaiting: false,
});

function asStaff(tickets: unknown[] = [ticket()], extra: string[] = []) {
  perms.clear();
  ['manage:tickets', ...extra].forEach(p => perms.add(p));
  api.fetchTickets.mockResolvedValue({ tickets });
  api.fetchTicketStats.mockResolvedValue({ total: tickets.length, by_status: {}, by_priority: {} });
  api.fetchTicketTemplates.mockResolvedValue([]);
  api.fetchTicketFieldSchema.mockResolvedValue({ fields: [] });
  api.fetchTicketHistory.mockResolvedValue([]);
  api.fetchAgents.mockResolvedValue([]);
  api.authFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/service-desk') && !init?.method) return jsonRes(desk());
    return jsonRes({});
  });
  return render(<InternalTicketsDashboard currentUserEmail="sam@acme.test" />);
}

const openTicket = async (title = 'Cannot reset password') => {
  fireEvent.click(await screen.findByText(title));
  await screen.findByRole('button', { name: 'Details' });
};
const toast = showToast as unknown as ReturnType<typeof vi.fn>;
const expectToast = async (message: string) =>
  waitFor(() => expect(toast).toHaveBeenCalledWith(message, 'error'));

beforeEach(() => {
  Object.values(api).forEach(m => m.mockReset());
  toast.mockClear();
  Element.prototype.scrollIntoView = vi.fn(); // jsdom has none; the Comments tab scrolls to its newest comment
});

// ------------------------------------------------------------------------------------ the three UAT silent failures

describe('the actions UAT round 3 saw fail silently', () => {
  it('a refused status change shows the error and leaves the status as it was', async () => {
    api.updateTicket.mockRejectedValue(new Error('Failed to update ticket'));
    asStaff();
    await openTicket();
    fireEvent.click(screen.getByRole('button', { name: '→ resolved' }));
    await expectToast('Failed to update ticket');
    expect(api.updateTicket).toHaveBeenCalledWith('t-1', { status: 'resolved' });
    expect(screen.getByRole('button', { name: '→ resolved' })).toBeInTheDocument();
  });

  it('a refused escalate shows the error', async () => {
    api.escalateTicket.mockRejectedValue(new Error('Escalation refused'));
    asStaff();
    await openTicket();
    fireEvent.click(screen.getByRole('button', { name: /Escalate/ }));
    await expectToast('Escalation refused');
  });

  it('a refused watcher add shows the error', async () => {
    api.addTicketWatcher.mockRejectedValue(new Error('Failed to add watcher'));
    asStaff();
    await openTicket();
    fireEvent.change(screen.getByPlaceholderText('Add watcher email…'), { target: { value: 'lead@acme.test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add watcher' }));
    await expectToast('Failed to add watcher');
  });

  it('a refused watcher add by the Enter key shows the error', async () => {
    api.addTicketWatcher.mockRejectedValue(new Error('Failed to add watcher'));
    asStaff();
    await openTicket();
    const box = screen.getByPlaceholderText('Add watcher email…');
    fireEvent.change(box, { target: { value: 'lead@acme.test' } });
    fireEvent.keyDown(box, { key: 'Enter' });
    await expectToast('Failed to add watcher');
  });

  it('a refused watcher removal shows the error and keeps the watcher', async () => {
    api.removeTicketWatcher.mockRejectedValue(new Error('Failed to remove watcher'));
    asStaff();
    await openTicket();
    fireEvent.click(screen.getByRole('button', { name: 'Remove watcher old@acme.test' }));
    await expectToast('Failed to remove watcher');
    expect(screen.getByText('old@acme.test')).toBeInTheDocument();
  });
});

describe('a successful watcher change', () => {
  it('shows the returned watcher list on the open ticket after an add', async () => {
    api.addTicketWatcher.mockResolvedValue(ticket({ watchers: ['old@acme.test', 'lead@acme.test'] }));
    asStaff();
    await openTicket();
    fireEvent.change(screen.getByPlaceholderText('Add watcher email…'), { target: { value: 'lead@acme.test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add watcher' }));
    expect(await screen.findByText('lead@acme.test')).toBeInTheDocument();
    expect(api.addTicketWatcher).toHaveBeenCalledWith('t-1', 'lead@acme.test');
    expect(screen.getByPlaceholderText('Add watcher email…')).toHaveValue('');
    expect(toast).not.toHaveBeenCalled();
  });

  it('drops the watcher from the open ticket after a removal', async () => {
    api.removeTicketWatcher.mockResolvedValue(ticket({ watchers: [] }));
    asStaff();
    await openTicket();
    fireEvent.click(screen.getByRole('button', { name: 'Remove watcher old@acme.test' }));
    await waitFor(() => expect(screen.queryByText('old@acme.test')).toBeNull());
    expect(toast).not.toHaveBeenCalled();
  });
});

describe('an error that carries no message', () => {
  it('shows the fallback sentence of the handler', async () => {
    api.updateTicket.mockRejectedValue('nope');
    asStaff();
    await openTicket();
    fireEvent.click(screen.getByRole('button', { name: '→ resolved' }));
    await expectToast('Failed to update ticket');
  });

  it('shows the fallback when an Error has an empty message', async () => {
    api.escalateTicket.mockRejectedValue(new Error(''));
    asStaff();
    await openTicket();
    fireEvent.click(screen.getByRole('button', { name: /Escalate/ }));
    await expectToast('Failed to escalate ticket');
  });
});
