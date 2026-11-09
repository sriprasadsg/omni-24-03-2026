/**
 * Phase 85 / DESK-01 (85-20): the ticket screen's desk additions of 85-UI-SPEC section 3. The Reply to requester choice,
 * the marks on comments, the Waiting on customer status (R2), the Draft waiting chip and the two panels mounted above
 * the tab bar. The whole screen is rendered with mocked services; nothing here reaches a real API.
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
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', ...api }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));
vi.mock('../../contexts/UserContext', () => ({ useUser: () => ({ currentUser: { name: 'Sam Rivera', email: 'sam@acme.test' } }) }));
vi.mock('../../components/TicketReportsDashboard', () => ({ default: () => null }));

import InternalTicketsDashboard from '../../components/InternalTicketsDashboard';
import { ReplyVisibilityPicker, CommentMarks, CommentBody } from '../../components/serviceDesk/ReplyVisibilityPicker';
import { REPLY_PICKER } from '../../components/serviceDesk/serviceDeskCopy';

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

// ------------------------------------------------------------------------------------------ the picker alone

describe('ReplyVisibilityPicker', () => {
  const picker = (over: Record<string, unknown> = {}) => {
    const onChange = vi.fn();
    const out = render(<ReplyVisibilityPicker value="staff" onChange={onChange} canReplyToRequester reporter="Dana Lee" {...over} />);
    return { ...out, onChange };
  };

  it('is a radiogroup named Who can see this comment with Staff only chosen', () => {
    picker();
    const group = screen.getByRole('radiogroup', { name: 'Who can see this comment' });
    expect(within(group).getAllByRole('radio')).toHaveLength(2);
    expect(screen.getByRole('radio', { name: 'Staff only' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Reply to requester' })).not.toBeChecked();
    expect(screen.queryByText(/will see this reply/)).toBeNull();
  });

  it('chooses Reply to requester and then names who will see it', () => {
    const { onChange, rerender } = picker();
    fireEvent.click(screen.getByRole('radio', { name: 'Reply to requester' }));
    expect(onChange).toHaveBeenCalledWith('requester');
    rerender(<ReplyVisibilityPicker value="requester" onChange={onChange} canReplyToRequester reporter="Dana Lee" />);
    expect(screen.getByRole('radio', { name: 'Reply to requester' })).toBeChecked();
    expect(screen.getByText("Dana Lee will see this reply in their ticket and get a notice. Don't include anything staff-only.")).toBeInTheDocument();
  });

  it('turns Reply to requester off with its reason when the server says there is no requester', () => {
    const { onChange } = picker({ canReplyToRequester: false });
    const reply = screen.getByRole('radio', { name: 'Reply to requester' });
    expect(reply).toBeDisabled();
    expect(reply).toHaveAccessibleDescription('This ticket was raised by an automated source, so there is no requester to reply to.');
    fireEvent.click(reply);
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('radio', { name: 'Staff only' })).toBeChecked();
  });

  it('keeps the choice off without a reason while the server flag is unknown', () => {
    picker({ unknown: true, canReplyToRequester: false });
    expect(screen.getByRole('radio', { name: 'Reply to requester' })).toBeDisabled();
    expect(screen.queryByText(/automated source/)).toBeNull();
  });
});

// ------------------------------------------------------------------------------------------ the comment marks

describe('CommentMarks and CommentBody', () => {
  it('leaves a plain staff comment without any mark', () => {
    const { container } = render(<CommentMarks comment={{ text: 'note' }} />);
    expect(container.firstChild).toBeNull();
    const staff = render(<CommentMarks comment={{ text: 'note', visibility: 'staff' }} />);
    expect(staff.container.firstChild).toBeNull();
  });

  it('marks a requester-visible reply Sent to requester', () => {
    render(<CommentMarks comment={{ text: 'hi', visibility: 'requester' }} />);
    expect(screen.getByText('Sent to requester')).toBeInTheDocument();
  });

  it('does not mark the requester\'s own note as sent to the requester', () => {
    const { container } = render(<CommentMarks comment={{ text: 'hi', visibility: 'requester', kind: 'requester_reply' }} />);
    expect(container.firstChild).toBeNull();
  });

  it('marks an answer a person sent AI-assisted with Sent by {name}', () => {
    render(<CommentMarks comment={{ text: 'a', kind: 'ai_answer', visibility: 'requester', ai: { state: 'sent', sentBy: { id: 'sam@acme.test', name: 'Sam Rivera' } } }} />);
    expect(screen.getByText('AI-assisted')).toBeInTheDocument();
    expect(screen.getByText('Sent by Sam Rivera')).toBeInTheDocument();
    expect(screen.queryByText('Posted automatically')).toBeNull();
  });

  it('marks an answer posted by the desk AI-assisted and Posted automatically', () => {
    render(<CommentMarks comment={{ text: 'a', kind: 'ai_answer', visibility: 'requester', ai: { state: 'posted' } }} />);
    expect(screen.getByText('AI-assisted')).toBeInTheDocument();
    expect(screen.getByText('Posted automatically')).toBeInTheDocument();
  });

  it('marks a draft Draft', () => {
    render(<CommentMarks comment={{ text: 'a', kind: 'ai_draft', ai: { state: 'draft' } }} />);
    expect(screen.getByText('Draft')).toBeInTheDocument();
  });

  it('shows a withdrawn answer as withdrawn and keeps the original behind Show original', () => {
    const comment = { text: 'the original wording', kind: 'ai_answer', visibility: 'requester', ai: { state: 'withdrawn' } };
    render(<><CommentMarks comment={comment} /><CommentBody comment={comment} /></>);
    expect(screen.getByText('Withdrawn')).toBeInTheDocument();
    expect(screen.getByText('AI-assisted')).toBeInTheDocument();
    expect(screen.getByText('This answer was withdrawn.')).toBeInTheDocument();
    expect(screen.queryByText('the original wording')).toBeNull();
    const toggle = screen.getByRole('button', { name: 'Show original' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('the original wording')).toBeInTheDocument();
  });

  it('shows the text of an ordinary comment as it is', () => {
    render(<CommentBody comment={{ text: 'plain words' }} />);
    expect(screen.getByText('plain words')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Show original' })).toBeNull();
  });
});

// ------------------------------------------------------------------------------------------ the whole ticket screen

const ticket = (over: Record<string, unknown> = {}) => ({
  id: 't-1', ticket_number: 'TKT-0042', title: 'Cannot reset password', description: '', type: 'task', priority: 'medium',
  status: 'open', assignee: '', assignee_group: '', watchers: [], reporter: 'dana@acme.test', tags: [],
  escalated: false, escalation_level: 0, approval_required: false, approval_status: '', custom_fields: {},
  links: [], attachments: [], comments: [], work_logs: [], created_at: '2026-11-09T09:00:00Z', updated_at: '2026-11-09T09:00:00Z',
  ...over,
});

const desk = (over: Record<string, unknown> = {}) => ({
  ticketId: 't-1', ticketNumber: 'TKT-0042', status: 'open', isRequester: false, requester: null, draft: null,
  canReplyToRequester: true, draftWaiting: false, ...over,
});

const waitingDraft = () => ({
  commentId: 'd-1', actionId: 'a-1', answer: 'Open Settings and choose Reset.', citations: [{ articleId: 'k-1', title: 'Reset your password' }],
  createdAt: new Date(Date.now() - 600000).toISOString(), articleCount: 1, draftReason: null, draftReasonText: null,
  maxAnswerLength: 900, canActOnDraft: true, blockedReason: null, blockedText: null, reporter: 'dana@acme.test',
});

let deskReply: () => Response = () => jsonRes(desk());
const deskPosts: Array<{ url: string; body: string }> = [];

function setup(tickets: unknown[], opts: { desk?: () => Response } = {}) {
  deskReply = opts.desk ?? (() => jsonRes(desk()));
  deskPosts.length = 0;
  api.fetchTickets.mockResolvedValue({ tickets });
  api.fetchTicketStats.mockResolvedValue({ total: tickets.length, by_status: {}, by_priority: {} });
  api.fetchTicketTemplates.mockResolvedValue([]);
  api.fetchTicketFieldSchema.mockResolvedValue({ fields: [] });
  api.fetchTicketHistory.mockResolvedValue([]);
  api.fetchAgents.mockResolvedValue([]);
  api.authFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') deskPosts.push({ url, body: String(init.body ?? '') });
    if (url.endsWith('/service-desk') && !init?.method) return deskReply();
    if (init?.method === 'POST' && url.endsWith('/comments')) return jsonRes(ticket()); // the updated ticket
    return jsonRes({});
  });
  return render(<InternalTicketsDashboard currentUserEmail="sam@acme.test" />);
}

const open = async (title = 'Cannot reset password') => {
  fireEvent.click(await screen.findByText(title));
  return screen.findByRole('button', { name: 'Comments' });
};

beforeEach(() => {
  Object.values(api).forEach(m => m.mockReset());
  Element.prototype.scrollIntoView = vi.fn(); // jsdom has none; the Comments tab scrolls to its newest comment
});

describe('Waiting on customer (R2)', () => {
  it('labels a pending_customer ticket Waiting on customer and never Open', async () => {
    setup([ticket({ status: 'pending_customer' })]);
    const row = (await screen.findByText('Cannot reset password')).closest('tr')!;
    expect(within(row).getByText('Waiting on customer')).toBeInTheDocument();
    expect(within(row).queryByText('Open')).toBeNull();
  });

  it('offers it in the status filter and as a board column', async () => {
    setup([ticket({ status: 'pending_customer' })]);
    await screen.findByText('Cannot reset password');
    expect(screen.getByRole('option', { name: 'Waiting on customer' })).toHaveValue('pending_customer');
    expect(screen.getAllByText('Waiting on customer')).toHaveLength(2); // the option and the row's badge
    fireEvent.click(screen.getByTitle('Kanban view'));
    await screen.findByText('Cannot reset password');
    const columns = ['Open', 'In Progress', 'Waiting on customer', 'Resolved', 'Closed'];
    columns.forEach(label => expect(screen.getAllByText(label).length).toBeGreaterThan(0));
  });
});

describe('the draft panel and the Draft waiting chip', () => {
  it('shows Draft waiting in the list row when the ticket says so', async () => {
    setup([ticket({ desk: { draftWaiting: true } }), ticket({ id: 't-2', ticket_number: 'TKT-0043', title: 'Printer', desk: { draftWaiting: false } })]);
    const row = (await screen.findByText('Cannot reset password')).closest('tr')!;
    expect(within(row).getByText('Draft waiting')).toBeInTheDocument();
    expect(within((await screen.findByText('Printer')).closest('tr')!).queryByText('Draft waiting')).toBeNull();
  });

  it('does not show the chip to the person who raised the ticket', async () => {
    setup([ticket({ reporter: 'Sam@Acme.test', desk: { draftWaiting: true } })]);
    const row = (await screen.findByText('Cannot reset password')).closest('tr')!;
    expect(within(row).queryByText('Draft waiting')).toBeNull();
  });

  it('mounts the draft panel above the tab bar, on every tab, and the chip in the header', async () => {
    setup([ticket()], { desk: () => jsonRes(desk({ draft: waitingDraft(), draftWaiting: true })) });
    const commentsTab = await open();
    const panel = await screen.findByRole('heading', { name: 'Draft answer' });
    const section = document.getElementById('service-desk-draft')!;
    expect(section.contains(panel)).toBe(true);
    expect(screen.getAllByText('Draft waiting').length).toBeGreaterThan(0);
    expect(section.compareDocumentPosition(commentsTab) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click(commentsTab);
    expect(screen.getByRole('heading', { name: 'Draft answer' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'History' }));
    expect(screen.getByRole('heading', { name: 'Draft answer' })).toBeInTheDocument();
  });

  it('sends the draft from the ticket and reads the ticket and the desk view again', async () => {
    let calls = 0;
    api.fetchTicket.mockResolvedValue(ticket({ status: 'pending_customer' }));
    setup([ticket()], {
      desk: () => (calls++ === 0 ? jsonRes(desk({ draft: waitingDraft(), draftWaiting: true })) : jsonRes(desk({ status: 'pending_customer' }))),
    });
    await open();
    fireEvent.click(await screen.findByRole('button', { name: 'Send as is' }));
    expect(await screen.findByText(/^Sent to dana@acme\.test by Sam Rivera at \d\d:\d\d/)).toBeInTheDocument();
    expect(deskPosts.map(p => p.url)).toContain('/api/tickets/t-1/service-desk/drafts/d-1/send');
    await waitFor(() => expect(api.fetchTicket).toHaveBeenCalledWith('t-1'));
    await waitFor(() => expect(calls).toBe(2));
  });

  it('shows no panel and no empty gap when nothing applies', async () => {
    setup([ticket()]);
    await open();
    await waitFor(() => expect(api.authFetch).toHaveBeenCalled());
    expect(screen.queryByRole('heading', { name: 'Draft answer' })).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Answer from IT support' })).toBeNull();
  });

  it('shows no panel when the desk view cannot be read', async () => {
    setup([ticket()], { desk: () => jsonRes({ detail: 'nope' }, 403) });
    await open();
    await waitFor(() => expect(api.authFetch).toHaveBeenCalled());
    expect(screen.queryByRole('heading', { name: 'Draft answer' })).toBeNull();
  });
});

describe('the requester panel on the ticket', () => {
  it('mounts the answer panel for the person who raised the ticket and hides drafts and the picker', async () => {
    const view = desk({
      isRequester: true, canReplyToRequester: false,
      requester: {
        items: [{ id: 'c-1', kind: 'ai_answer', at: '2026-11-09T10:00:00Z', author: null, text: 'Open Settings and choose Reset.', citations: [] }],
        canSee: true, canConfirm: true, returnAt: null, notice: null, confirmedAt: null,
      },
    });
    setup([ticket({
      status: 'pending_customer',
      comments: [
        { id: 'c-1', author: 'service-desk', text: 'Open Settings and choose Reset.', created_at: '2026-11-09T10:00:00Z', kind: 'ai_answer', visibility: 'requester', ai: { state: 'posted' } },
        { id: 'd-9', author: 'service-desk', text: 'a staff-only draft text', created_at: '2026-11-09T10:01:00Z', kind: 'ai_draft', ai: { state: 'draft' } },
      ],
    })], { desk: () => jsonRes(view) });
    const commentsTab = await open();
    expect(await screen.findByRole('heading', { name: 'Answer from IT support' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'This fixed it' })).toBeInTheDocument();
    fireEvent.click(commentsTab);
    expect(screen.queryByText('a staff-only draft text')).toBeNull();
    expect(screen.queryByRole('radiogroup', { name: 'Who can see this comment' })).toBeNull();
  });
});

describe('Reply to requester in the comment composer', () => {
  const withComments = () => ticket({
    comments: [
      { id: 'c-1', author: 'sam@acme.test', text: 'a staff note', created_at: '2026-11-09T10:00:00Z' },
      { id: 'c-2', author: 'sam@acme.test', text: 'a reply for Dana', created_at: '2026-11-09T10:05:00Z', visibility: 'requester' },
      { id: 'c-3', author: 'service-desk', text: 'the answer', created_at: '2026-11-09T10:06:00Z', kind: 'ai_answer', visibility: 'requester', ai: { state: 'sent', sentBy: { id: 'sam@acme.test', name: 'Sam Rivera' } } },
    ],
  });

  const comments = async (over: Record<string, unknown> = {}) => {
    setup([withComments()], { desk: () => jsonRes(desk(over)) });
    fireEvent.click(await open());
    await screen.findByRole('radiogroup', { name: 'Who can see this comment' });
    await waitFor(() => expect(screen.getByRole('radio', { name: 'Reply to requester' })).toBeEnabled());
  };

  it('shows the explanatory line and marks only what the requester can see', async () => {
    await comments();
    expect(screen.getByText('Comments are visible to staff only unless marked "Sent to requester".')).toBeInTheDocument();
    const note = screen.getByText('a staff note').closest('div')!;
    expect(within(note).queryByText('Sent to requester')).toBeNull();
    expect(within(screen.getByText('a reply for Dana').closest('div')!).getByText('Sent to requester')).toBeInTheDocument();
    const answer = screen.getByText('the answer').closest('div')!;
    expect(within(answer).getByText('AI-assisted')).toBeInTheDocument();
    expect(within(answer).getByText('Sent by Sam Rivera')).toBeInTheDocument();
  });

  it('starts at Staff only and posts a staff comment as before (addTicketComment, no visibility)', async () => {
    api.addTicketComment.mockResolvedValue(withComments());
    await comments();
    expect(screen.getByRole('radio', { name: 'Staff only' })).toBeChecked();
    fireEvent.change(screen.getByPlaceholderText(/Add a comment/), { target: { value: 'just us' } });
    fireEvent.click(screen.getAllByRole('button').find(b => b.querySelector('svg.lucide-send'))!);
    await waitFor(() => expect(api.addTicketComment).toHaveBeenCalledWith('t-1', 'just us'));
    expect(deskPosts.filter(p => p.url.endsWith('/comments'))).toHaveLength(0);
  });

  it('posts {text, visibility: requester} for Reply to requester, then returns to Staff only', async () => {
    await comments();
    fireEvent.click(screen.getByRole('radio', { name: 'Reply to requester' }));
    expect(screen.getByText(/dana@acme\.test will see this reply in their ticket/)).toBeInTheDocument();
    const box = screen.getByPlaceholderText('Write a reply to the requester...');
    fireEvent.change(box, { target: { value: 'Try again now' } });
    const send = screen.getByRole('button', { name: 'Send reply to requester' });
    expect(send).toHaveAttribute('title', 'Send reply to requester');
    fireEvent.click(send);
    await waitFor(() => expect(deskPosts.some(p => p.url === '/api/tickets/t-1/comments')).toBe(true));
    const posted = deskPosts.find(p => p.url === '/api/tickets/t-1/comments')!;
    expect(JSON.parse(posted.body)).toEqual({ text: 'Try again now', visibility: 'requester' });
    await waitFor(() => expect(screen.getByRole('radio', { name: 'Staff only' })).toBeChecked());
    expect(screen.queryByPlaceholderText('Write a reply to the requester...')).toBeNull();
    expect(api.addTicketComment).not.toHaveBeenCalled();
  });

  it('keeps the choice and says why when the server refuses the reply (no requester to reply to)', async () => {
    await comments();
    api.authFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && url.endsWith('/comments')) {
        return jsonRes({ detail: 'This ticket was raised by an automated source, so there is no requester to reply to.' }, 400);
      }
      return jsonRes(desk());
    });
    fireEvent.click(screen.getByRole('radio', { name: 'Reply to requester' }));
    fireEvent.change(screen.getByPlaceholderText('Write a reply to the requester...'), { target: { value: 'hello' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send reply to requester' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('This ticket was raised by an automated source, so there is no requester to reply to.');
    expect(screen.getByRole('radio', { name: 'Reply to requester' })).toBeChecked();
    expect(screen.getByPlaceholderText('Write a reply to the requester...')).toHaveValue('hello');
  });

  it('uses the fallback copy when a reply fails without a server message', async () => {
    await comments();
    api.authFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && url.endsWith('/comments')) throw new Error('offline');
      return jsonRes(desk());
    });
    fireEvent.click(screen.getByRole('radio', { name: 'Reply to requester' }));
    fireEvent.change(screen.getByPlaceholderText('Write a reply to the requester...'), { target: { value: 'hello' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send reply to requester' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't send the reply. Check your connection and try again.");
  });

  it('disables Reply to requester for a ticket with no requester and keeps comments staff only', async () => {
    setup([withComments()], { desk: () => jsonRes(desk({ canReplyToRequester: false })) });
    fireEvent.click(await open());
    expect(await screen.findByText('This ticket was raised by an automated source, so there is no requester to reply to.')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Reply to requester' })).toBeDisabled();
    expect(screen.getByRole('radio', { name: 'Staff only' })).toBeChecked();
  });

  it('resets the choice to Staff only when another ticket opens', async () => {
    setup([withComments(), ticket({ id: 't-2', ticket_number: 'TKT-0043', title: 'Printer' })], {
      desk: () => jsonRes(desk()),
    });
    fireEvent.click(await open());
    await waitFor(() => expect(screen.getByRole('radio', { name: 'Reply to requester' })).toBeEnabled());
    fireEvent.click(screen.getByRole('radio', { name: 'Reply to requester' }));
    expect(screen.getByRole('radio', { name: 'Reply to requester' })).toBeChecked();
    fireEvent.click(screen.getByText('Printer'));
    fireEvent.click(await screen.findByRole('button', { name: 'Comments' }));
    await waitFor(() => expect(screen.getByRole('radio', { name: 'Reply to requester' })).toBeEnabled());
    expect(screen.getByRole('radio', { name: 'Staff only' })).toBeChecked();
  });
});

describe('the copy this file asserts is the copy of the module', () => {
  it('uses the labels of serviceDeskCopy', () => {
    expect(REPLY_PICKER.statusWaiting).toBe('Waiting on customer');
    expect(REPLY_PICKER.label).toBe('Who can see this comment');
  });
});
