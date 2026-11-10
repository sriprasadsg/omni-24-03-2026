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

// ------------------------------------------------------------------------------------- every other staff action

const openTab = async (name: string) => {
  fireEvent.click(screen.getByRole('button', { name }));
};
const pendingApproval = () => ticket({ approval_required: true, approval_status: 'pending' });
const rejectButton = () => screen.getByPlaceholderText('Rejection reason (required)').nextElementSibling as HTMLElement;

describe('the ticket panel actions', () => {
  it('a failed work log shows the error and keeps the typed hours', async () => {
    api.logTicketWork.mockRejectedValue(new Error('Failed to log work'));
    asStaff();
    await openTicket();
    await openTab('Work Log');
    fireEvent.change(screen.getByPlaceholderText('Hours'), { target: { value: '1.5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Log' }));
    await expectToast('Failed to log work');
    expect(api.logTicketWork).toHaveBeenCalledWith('t-1', 1.5, '');
    expect(screen.getByPlaceholderText('Hours')).toHaveValue(1.5);
  });

  it('a failed link shows the error', async () => {
    api.linkTickets.mockRejectedValue(new Error('Linked ticket not found'));
    asStaff();
    await openTicket();
    await openTab('Links');
    fireEvent.change(screen.getByPlaceholderText('Ticket ID (e.g. TKT-0012)…'), { target: { value: 'TKT-0099' } });
    fireEvent.click(screen.getByRole('button', { name: 'Link' }));
    await expectToast('Linked ticket not found');
  });

  it('a failed unlink shows the error and keeps the link', async () => {
    api.unlinkTickets.mockRejectedValue(new Error('Failed to remove link'));
    asStaff([ticket({ links: [{ linked_id: 'TKT-0099', type: 'relates_to' }] })]);
    await openTicket();
    await openTab('Links');
    fireEvent.click(screen.getByRole('button', { name: 'Remove link TKT-0099' }));
    await expectToast('Failed to remove link');
    expect(screen.getByText('TKT-0099')).toBeInTheDocument();
  });

  it('a failed approval shows the error', async () => {
    api.approveTicket.mockRejectedValue(new Error('Approval refused'));
    asStaff([pendingApproval()]);
    await openTicket();
    fireEvent.click(screen.getByRole('button', { name: /^Approve$/ }));
    await expectToast('Approval refused');
  });

  it('a failed rejection shows the error', async () => {
    api.rejectTicket.mockRejectedValue(new Error('Rejection refused'));
    asStaff([pendingApproval()]);
    await openTicket();
    fireEvent.change(screen.getByPlaceholderText('Rejection reason (required)'), { target: { value: 'Not needed' } });
    fireEvent.click(rejectButton());
    await expectToast('Rejection refused');
    expect(api.rejectTicket).toHaveBeenCalledWith('t-1', 'Not needed');
  });

  it('a failed attachment delete shows the error and keeps the file', async () => {
    api.deleteTicketAttachment.mockRejectedValue(new Error('Failed to delete attachment'));
    asStaff();
    await openTicket();
    await openTab('Files');
    fireEvent.click(await screen.findByRole('button', { name: 'Delete notes.txt' }));
    await expectToast('Failed to delete attachment');
    expect(screen.getByText('notes.txt')).toBeInTheDocument();
  });

  it('a merge whose request throws shows the error', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    asStaff();
    api.authFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/service-desk') && !init?.method) return jsonRes(desk());
      if (url.endsWith('/merge')) throw new Error('Network down');
      return jsonRes({});
    });
    await openTicket();
    fireEvent.change(screen.getByPlaceholderText('Target ticket ID (e.g. abc-123)…'), { target: { value: 't-2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Merge' }));
    await expectToast('Network down');
    confirmSpy.mockRestore();
  });

  it('a merge answered not-ok keeps its own message', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    asStaff();
    api.authFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/service-desk') && !init?.method) return jsonRes(desk());
      if (url.endsWith('/merge')) return jsonRes({}, 404);
      return jsonRes({});
    });
    await openTicket();
    fireEvent.change(screen.getByPlaceholderText('Target ticket ID (e.g. abc-123)…'), { target: { value: 't-2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Merge' }));
    await expectToast('Merge failed — check the target ticket ID');
    confirmSpy.mockRestore();
  });
});

describe('the list, the bulk bar and the board', () => {
  it('a failed ticket delete from its row shows the error and keeps the row', async () => {
    api.deleteTicket.mockRejectedValue(new Error('Failed to delete ticket'));
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    asStaff([ticket()], ['manage:settings']);
    fireEvent.click(await screen.findByRole('button', { name: 'Delete TKT-0042' }));
    await expectToast('Failed to delete ticket');
    expect(screen.getByText('Cannot reset password')).toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  it('a failed bulk status change shows the error and keeps the selection', async () => {
    api.bulkUpdateTickets.mockRejectedValue(new Error('Failed to update tickets'));
    asStaff();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Select TKT-0042' }));
    fireEvent.change(await screen.findByDisplayValue('Bulk action…'), { target: { value: 'status:resolved' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    await expectToast('Failed to update tickets');
    expect(api.bulkUpdateTickets).toHaveBeenCalledWith(['t-1'], { status: 'resolved' });
    expect(screen.getByText('1 selected')).toBeInTheDocument();
  });

  it('a successful bulk status change clears the selection and reloads the list', async () => {
    api.bulkUpdateTickets.mockResolvedValue({});
    asStaff();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Select TKT-0042' }));
    const loadsBefore = api.fetchTickets.mock.calls.length;
    fireEvent.change(await screen.findByDisplayValue('Bulk action…'), { target: { value: 'status:resolved' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    await waitFor(() => expect(screen.queryByText('1 selected')).toBeNull());
    expect(api.fetchTickets.mock.calls.length).toBeGreaterThan(loadsBefore);
    expect(toast).not.toHaveBeenCalled();
  });

  it('a failed bulk delete shows the error', async () => {
    api.deleteTicket.mockRejectedValue(new Error('Failed to delete tickets'));
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    asStaff([ticket()], ['manage:settings']);
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Select TKT-0042' }));
    fireEvent.change(await screen.findByDisplayValue('Bulk action…'), { target: { value: 'delete' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    await expectToast('Failed to delete tickets');
    confirmSpy.mockRestore();
  });

  it('a board drop whose update fails shows the error', async () => {
    api.updateTicket.mockRejectedValue(new Error('Failed to update ticket'));
    asStaff();
    await screen.findByText('Cannot reset password');
    fireEvent.click(screen.getByTitle('Kanban view'));
    await screen.findByText('Cannot reset password');
    const column = screen.getByText('In Progress').closest('div[class*="w-72"]')!;
    fireEvent.drop(column, { dataTransfer: { getData: () => 't-1' } });
    await expectToast('Failed to update ticket');
    expect(api.updateTicket).toHaveBeenCalledWith('t-1', { status: 'in_progress' });
  });
});

describe('the successful paths stay as they were', () => {
  it('a logged piece of work shows the returned ticket', async () => {
    api.logTicketWork.mockResolvedValue(ticket({ total_hours_logged: 2, work_logs: [{ id: 'w-1', hours: 2, description: 'Reset it', author: 'sam@acme.test', created_at: '2026-11-10T09:00:00Z' }] }));
    asStaff();
    await openTicket();
    await openTab('Work Log');
    fireEvent.change(screen.getByPlaceholderText('Hours'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Log' }));
    expect(await screen.findByText('Reset it')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Hours')).toHaveValue(null);
    expect(toast).not.toHaveBeenCalled();
  });

  it('an approval clears the pending panel', async () => {
    api.approveTicket.mockResolvedValue(ticket({ approval_required: true, approval_status: 'approved' }));
    asStaff([pendingApproval()]);
    await openTicket();
    fireEvent.click(screen.getByRole('button', { name: /^Approve$/ }));
    await waitFor(() => expect(screen.queryByRole('button', { name: /^Approve$/ })).toBeNull());
    expect(toast).not.toHaveBeenCalled();
  });
});

// ------------------------------------------------------------- the paths the third-round review found silent (WR-701)

describe('the staff paths the review found silent (WR-701)', () => {
  it('a refused rename by the Enter key shows the error', async () => {
    api.updateTicket.mockRejectedValue(new Error('Rename refused'));
    asStaff();
    await openTicket();
    fireEvent.click(screen.getByTitle('Click to edit'));
    const box = screen.getByDisplayValue('Cannot reset password');
    fireEvent.change(box, { target: { value: 'Password reset link expired' } });
    fireEvent.keyDown(box, { key: 'Enter' });
    await expectToast('Rename refused');
    expect(api.updateTicket).toHaveBeenCalledWith('t-1', { title: 'Password reset link expired' });
  });

  it('a refused rename on leaving the box shows the error', async () => {
    api.updateTicket.mockRejectedValue('nope');
    asStaff();
    await openTicket();
    fireEvent.click(screen.getByTitle('Click to edit'));
    fireEvent.blur(screen.getByDisplayValue('Cannot reset password'));
    await expectToast('Failed to update ticket');
  });

  it('a refused Start Remediation on a security finding shows the error', async () => {
    api.updateTicket.mockRejectedValue(new Error('Failed to update ticket'));
    asStaff([ticket({ type: 'security' })]);
    await openTicket();
    fireEvent.click(screen.getByRole('button', { name: 'Start Remediation' }));
    await expectToast('Failed to update ticket');
    expect(api.updateTicket).toHaveBeenCalledWith('t-1', { status: 'in_progress' });
  });

  it('a refused staff note shows the error and keeps the typed note', async () => {
    api.addTicketComment.mockRejectedValue(new Error('Failed to add comment'));
    asStaff();
    await openTicket();
    await openTab('Comments');
    const box = await screen.findByPlaceholderText('Add a comment… (Enter to send, @ to mention)');
    fireEvent.change(box, { target: { value: 'Checked the AD account' } });
    fireEvent.keyDown(box, { key: 'Enter' });
    await expectToast('Failed to add comment');
    expect(api.addTicketComment).toHaveBeenCalledWith('t-1', 'Checked the AD account');
    expect(box).toHaveValue('Checked the AD account');
  });

  it('a refused upload shows the error', async () => {
    api.uploadTicketAttachment.mockRejectedValue(new Error('File too large'));
    const { container } = asStaff();
    await openTicket();
    await openTab('Files');
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'log.txt', { type: 'text/plain' })] } });
    await expectToast('File too large');
    expect(api.uploadTicketAttachment).toHaveBeenCalledWith('t-1', expect.any(File));
  });
});

// ------------------------------------------------------------------------- a bulk delete that fails part-way (WR-702)

describe('a bulk delete that fails part-way (WR-702)', () => {
  it('drops only the deleted tickets, keeps the refused one selected and reloads the list', async () => {
    const second = ticket({ id: 't-2', ticket_number: 'TKT-0043', title: 'VPN drops every hour' });
    api.deleteTicket.mockImplementation(async (id: string) => {
      if (id === 't-2') throw new Error('Failed to delete ticket');
      return {};
    });
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    asStaff([ticket(), second], ['manage:settings']);
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Select all tickets' }));
    api.fetchTickets.mockResolvedValue({ tickets: [second] }); // what the server holds after the partial delete
    const loadsBefore = api.fetchTickets.mock.calls.length;
    fireEvent.change(await screen.findByDisplayValue('Bulk action…'), { target: { value: 'delete' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    await expectToast('Failed to delete ticket');
    expect(api.deleteTicket).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(screen.queryByText('Cannot reset password')).toBeNull());
    expect(screen.getByText('VPN drops every hour')).toBeInTheDocument();
    expect(screen.getByText('1 selected')).toBeInTheDocument();
    expect(api.fetchTickets.mock.calls.length).toBeGreaterThan(loadsBefore);
    confirmSpy.mockRestore();
  });

  it('a failed bulk status change reloads the list', async () => {
    api.bulkUpdateTickets.mockRejectedValue(new Error('Failed to update tickets'));
    asStaff();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Select TKT-0042' }));
    const loadsBefore = api.fetchTickets.mock.calls.length;
    fireEvent.change(await screen.findByDisplayValue('Bulk action…'), { target: { value: 'status:resolved' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    await expectToast('Failed to update tickets');
    await waitFor(() => expect(api.fetchTickets.mock.calls.length).toBeGreaterThan(loadsBefore));
  });
});
