/**
 * Phase 85 / DESK-01 (85-26, CR-401 UI half, D-11): the Tickets screen shows the person who raised a ticket only the
 * comments they may read, on the first paint, after a failed desk read and in the list count; staff see everything.
 * requesterMayRead is pinned to the case table the backend test reads (shared/service-desk-requester-comments.json).
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
vi.mock('../../contexts/UserContext', () => ({ useUser: () => ({ currentUser: { name: 'Nobody', email: '' } }) }));
vi.mock('../../components/TicketReportsDashboard', () => ({ default: () => null }));

import InternalTicketsDashboard from '../../components/InternalTicketsDashboard';
import { requesterMayRead, sameUser, viewerIsReporter, visibleComments } from '../../components/serviceDesk/requesterComments';
import table from '../../shared/service-desk-requester-comments.json';

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

// ----------------------------------------------------------------------------------------------------- the rule itself

describe('requesterMayRead agrees with the shared case table', () => {
  it.each(table.cases.map(c => [c.id, c] as const))('%s', (_id, c) => {
    expect(requesterMayRead({ reporter: table.reporter }, c.comment)).toBe(c.readable);
  });

  it('has the same reader as the server for every case (the table is not empty)', () => {
    expect(table.cases.length).toBeGreaterThanOrEqual(16);
  });
});

describe('sameUser', () => {
  it('ignores case and surrounding spaces and never matches an empty name', () => {
    expect(sameUser('dana@acme.test', '  DANA@acme.test ')).toBe(true);
    expect(sameUser('', '')).toBe(false);
    expect(sameUser('dana@acme.test', 'dana@acme.test.evil')).toBe(false);
    expect(sameUser(undefined, 'dana@acme.test')).toBe(false);
  });
});

describe('viewerIsReporter', () => {
  const t = { reporter: 'dana@acme.test' };

  it('decides from the ticket while the desk view is not there', () => {
    expect(viewerIsReporter(t, ' Dana@Acme.test', null)).toBe(true);
    expect(viewerIsReporter(t, 'sam@acme.test', null)).toBe(false);
    expect(viewerIsReporter(t, 'sam@acme.test', undefined)).toBe(false);
  });

  it('treats an unknown viewer as the reporter while the desk view is not there', () => {
    expect(viewerIsReporter(t, '', null)).toBe(true);
    expect(viewerIsReporter(t, '   ', undefined)).toBe(true);
    expect(viewerIsReporter(t, undefined, null)).toBe(true);
  });

  it('follows the desk view when it answers', () => {
    expect(viewerIsReporter(t, 'other@acme.test', { isRequester: true })).toBe(true);
    expect(viewerIsReporter(t, 'sam@acme.test', { isRequester: false })).toBe(false);
    expect(viewerIsReporter(t, '', { isRequester: false })).toBe(false);
  });
});

describe('visibleComments', () => {
  const comments = table.cases.map(c => c.comment).filter(c => typeof c === 'object');

  it('keeps every comment for staff and filters for the reporter', () => {
    const ticket = { reporter: table.reporter, comments: comments as any[] };
    expect(visibleComments(ticket, 'sam@acme.test', { isRequester: false })).toHaveLength(comments.length);
    const readable = table.cases.filter(c => c.readable).length;
    expect(visibleComments(ticket, table.reporter, null)).toHaveLength(readable);
  });

  it('gives an empty list for a ticket without comments', () => {
    expect(visibleComments({ reporter: 'dana@acme.test' }, 'dana@acme.test', null)).toEqual([]);
    expect(visibleComments({ reporter: 'dana@acme.test', comments: null }, 'sam@acme.test', null)).toEqual([]);
  });
});

// ------------------------------------------------------------------------------------------ the whole ticket screen

const TEXT = {
  staffOnly: 'Staff-only remark about the cable',
  noFlag: 'Older note without a flag',
  draft: 'Draft answer nobody has sent',
  withdrawn: 'Answer that was taken back',
  staffReply: 'Please restart the laptop',
  own: 'It still shows a black screen',
  posted: 'Hold the power button for ten seconds',
  reply: 'I still need help with this',
};
const HIDDEN = [TEXT.staffOnly, TEXT.noFlag, TEXT.draft, TEXT.withdrawn];
const READABLE = [TEXT.staffReply, TEXT.own, TEXT.posted, TEXT.reply];

const at = (n: number) => `2026-11-09T10:0${n}:00Z`;
const eightComments = () => [
  { id: 'c1', author: 'bob@acme.test', text: TEXT.staffOnly, created_at: at(1), visibility: 'staff' },
  { id: 'c2', author: 'bob@acme.test', text: TEXT.noFlag, created_at: at(2) },
  { id: 'c3', author: 'service-desk', text: TEXT.draft, created_at: at(3), visibility: 'staff', kind: 'ai_draft', ai: { state: 'draft' } },
  { id: 'c4', author: 'service-desk', text: TEXT.withdrawn, created_at: at(4), visibility: 'requester', kind: 'ai_answer', ai: { state: 'withdrawn' } },
  { id: 'c5', author: 'bob@acme.test', text: TEXT.staffReply, created_at: at(5), visibility: 'requester' },
  { id: 'c6', author: 'dana@acme.test', text: TEXT.own, created_at: at(6), visibility: 'staff' },
  { id: 'c7', author: 'service-desk', text: TEXT.posted, created_at: at(7), visibility: 'requester', kind: 'ai_answer', ai: { state: 'posted' } },
  { id: 'c8', author: 'dana@acme.test', text: TEXT.reply, created_at: at(8), visibility: 'requester', kind: 'requester_reply' },
];

const ticket = (over: Record<string, unknown> = {}) => ({
  id: 't-1', ticket_number: 'TKT-0042', title: 'Cannot reset password', description: '', type: 'task', priority: 'medium',
  status: 'open', assignee: '', assignee_group: '', watchers: [], reporter: 'dana@acme.test', tags: [],
  escalated: false, escalation_level: 0, approval_required: false, approval_status: '', custom_fields: {},
  links: [], attachments: [], comments: eightComments(), work_logs: [], created_at: '2026-11-09T09:00:00Z', updated_at: '2026-11-09T09:00:00Z',
  ...over,
});

const desk = (over: Record<string, unknown> = {}) => ({
  ticketId: 't-1', ticketNumber: 'TKT-0042', status: 'open', isRequester: false, requester: null, draft: null,
  canReplyToRequester: true, draftWaiting: false, ...over,
});

let deskReply: () => Response | Promise<Response> = () => jsonRes(desk());
let deskReads = 0;
const never = () => new Promise<Response>(() => {});

function setup(viewer: string, tickets: unknown[], reply: () => Response | Promise<Response>) {
  deskReply = reply;
  deskReads = 0;
  api.fetchTickets.mockResolvedValue({ tickets });
  api.fetchTicketStats.mockResolvedValue({ total: tickets.length, by_status: {}, by_priority: {} });
  api.fetchTicketTemplates.mockResolvedValue([]);
  api.fetchTicketFieldSchema.mockResolvedValue({ fields: [] });
  api.fetchTicketHistory.mockResolvedValue([]);
  api.fetchAgents.mockResolvedValue([]);
  api.authFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/service-desk') && !init?.method) { deskReads += 1; return deskReply(); }
    return jsonRes({});
  });
  return render(<InternalTicketsDashboard currentUserEmail={viewer} />);
}

const openComments = async (title = 'Cannot reset password') => {
  fireEvent.click(await screen.findByText(title));
  fireEvent.click(await screen.findByRole('button', { name: 'Comments' }));
};

const expectShown = (texts: string[]) => texts.forEach(t => expect(screen.getByText(t)).toBeInTheDocument());
const expectAbsent = (texts: string[]) => texts.forEach(t => expect(screen.queryByText(t)).toBeNull());

beforeEach(() => {
  Object.values(api).forEach(m => m.mockReset());
  Element.prototype.scrollIntoView = vi.fn(); // jsdom has none; the Comments tab scrolls to its newest comment
});

describe('the reporter on the first paint of the Comments tab', () => {
  it('sees no staff-only comment, draft or withdrawn answer while the desk view is still loading', async () => {
    setup('dana@acme.test', [ticket()], never);
    await openComments();
    await waitFor(() => expect(deskReads).toBe(1));
    expectAbsent(HIDDEN);
    expectShown(READABLE);
    expect(screen.getByText('Comments are visible to staff only unless marked "Sent to requester".')).toBeInTheDocument();
  });
});

describe('the reporter after a failed or different desk read', () => {
  it('sees no hidden comment when the desk read fails', async () => {
    setup('dana@acme.test', [ticket()], () => jsonRes({}, 500));
    await openComments();
    await waitFor(() => expect(deskReads).toBe(1));
    await waitFor(() => expectShown(READABLE));
    expectAbsent(HIDDEN);
  });

  it('sees no hidden comment when the signed-in email differs only in case and the desk view says requester', async () => {
    setup('DANA@acme.test', [ticket()], () => jsonRes(desk({ isRequester: true, canReplyToRequester: false })));
    await openComments();
    await waitFor(() => expect(deskReads).toBe(1));
    await waitFor(() => expectShown(READABLE));
    expectAbsent(HIDDEN);
  });

  it('sees no hidden comment when the desk view says requester for a different email', async () => {
    setup('someone.else@acme.test', [ticket()], () => jsonRes(desk({ isRequester: true, canReplyToRequester: false })));
    await openComments();
    await waitFor(() => expect(deskReads).toBe(1));
    await waitFor(() => expectAbsent(HIDDEN));
    expectShown(READABLE);
  });

  it('shows "No comments yet." and keeps the note when only staff-only comments exist', async () => {
    const staffOnly = [
      { id: 'c1', author: 'bob@acme.test', text: TEXT.staffOnly, created_at: at(1), visibility: 'staff' },
      { id: 'c3', author: 'service-desk', text: TEXT.draft, created_at: at(3), visibility: 'staff', kind: 'ai_draft', ai: { state: 'draft' } },
    ];
    setup('dana@acme.test', [ticket({ comments: staffOnly })], never);
    await openComments();
    await waitFor(() => expect(deskReads).toBe(1));
    expect(screen.getByText('No comments yet.')).toBeInTheDocument();
    expect(screen.getByText('Comments are visible to staff only unless marked "Sent to requester".')).toBeInTheDocument();
    expectAbsent([TEXT.staffOnly, TEXT.draft]);
  });
});

describe('staff keep the full view (D-11)', () => {
  it('sees every comment before the desk view loads', async () => {
    setup('sam@acme.test', [ticket()], never);
    await openComments();
    await waitFor(() => expect(deskReads).toBe(1));
    expectShown([TEXT.staffOnly, TEXT.noFlag, TEXT.draft, ...READABLE]);
    expect(screen.getByText('This answer was withdrawn.')).toBeInTheDocument();
  });

  it('still sees every comment after the desk view answers isRequester false', async () => {
    setup('sam@acme.test', [ticket()], () => jsonRes(desk({ isRequester: false })));
    await openComments();
    await waitFor(() => expect(deskReads).toBe(1));
    await waitFor(() => expect(screen.getByRole('radio', { name: 'Reply to requester' })).toBeEnabled());
    expectShown([TEXT.staffOnly, TEXT.noFlag, TEXT.draft, ...READABLE]);
    expect(screen.getByText('This answer was withdrawn.')).toBeInTheDocument();
  });
});

describe('the comment count of the ticket list row', () => {
  const countOf = async () => {
    const row = (await screen.findByText('Cannot reset password')).closest('tr')!;
    return row.querySelector('svg.lucide-message-square')?.parentElement?.textContent ?? null;
  };

  it('counts only the comments the reporter may read', async () => {
    setup('dana@acme.test', [ticket()], never);
    expect(await countOf()).toBe('4');
  });

  it('counts every comment for staff', async () => {
    setup('sam@acme.test', [ticket()], never);
    expect(await countOf()).toBe('8');
  });

  it('shows no count for the reporter when nothing is readable', async () => {
    setup('dana@acme.test', [ticket({ comments: [eightComments()[0]] })], never);
    expect(await countOf()).toBeNull();
  });
});
