/**
 * Phase 85 / DESK-01 (85-20): the cited-article list and the requester's answer panel of 85-UI-SPEC section 4, and the
 * staff draft panel of section 3. authFetch and the toast are mocked; the payloads follow 85-14-SUMMARY.md (the server
 * sends the STORED comment kind, the API layer maps it). Nothing here reaches a real API.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within, act } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: vi.fn() }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { authFetch } from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { CitedArticles } from '../../components/serviceDesk/CitedArticles';
import { RequesterAnswerPanel } from '../../components/serviceDesk/RequesterAnswerPanel';
import { TicketDraftPanel } from '../../components/serviceDesk/TicketDraftPanel';
import { fetchTicketDesk, mapRequesterKind } from '../../services/serviceDesk/ticketApi';
import { DRAFT_PANEL, FOOTER, HANDOFF_NOTICE, MARK, REQUESTER, WITHDRAWN_NOTICE, fill } from '../../components/serviceDesk/serviceDeskCopy';

const mockFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

const TICKET = 't-1';
const CITES = [{ articleId: 'a-1', title: 'Reset your password' }, { articleId: 'a-2', title: 'VPN setup' }];

beforeEach(() => { mockFetch.mockReset(); vi.mocked(showToast).mockReset(); });

// ------------------------------------------------------------------------------------------ fixtures

const item = (over: Record<string, unknown> = {}) => ({
  id: 'c-1', kind: 'answer', at: '2026-11-09T10:00:00Z', author: null, text: 'Open Settings and choose Reset.', citations: CITES, ...over,
});

const requesterView = (over: Record<string, unknown> = {}, items: unknown[] = [item()]) => ({
  ticketId: TICKET, ticketNumber: 'TKT-0042', status: 'pending_customer', isRequester: true,
  requester: { items, canSee: true, canConfirm: true, returnAt: '2026-11-12T10:00:00Z', notice: null, confirmedAt: null, ...over },
  draft: null, canReplyToRequester: false, draftWaiting: false,
}) as any;

const rendered = (view: any, onChanged = vi.fn()) => {
  const out = render(<RequesterAnswerPanel ticketId={TICKET} view={view} onChanged={onChanged} />);
  return { ...out, onChanged };
};

// ------------------------------------------------------------------------------------------ the kind mapping

describe('the server comment kinds become the client kinds in one place', () => {
  it.each([
    ['ai_answer', 'answer'], ['requester_reply', 'you'], ['withdrawn_notice', 'withdrawn'],
    ['handoff_notice', 'notice'], [null, 'reply'], [undefined, 'reply'], ['something_new', 'notice'],
  ])('maps %s to %s', (stored, client) => {
    expect(mapRequesterKind(stored as any)).toBe(client);
  });

  it('maps every requester item of the GET answer and leaves the rest of the view alone', async () => {
    mockFetch.mockResolvedValue(jsonRes({
      ...requesterView({}, [
        item({ id: 'c-1', kind: 'ai_answer' }), item({ id: 'c-2', kind: null, author: 'Sam' }),
        item({ id: 'c-3', kind: 'requester_reply', citations: [] }), item({ id: 'c-4', kind: 'handoff_notice', citations: [] }),
      ]),
    }));
    const desk = await fetchTicketDesk(TICKET);
    expect(mockFetch).toHaveBeenCalledWith('/api/tickets/t-1/service-desk');
    expect(desk.requester!.items.map(i => i.kind)).toEqual(['answer', 'reply', 'you', 'notice']);
    expect(desk.requester!.canConfirm).toBe(true);
    expect(desk.requester!.items[1].author).toBe('Sam');
  });

  it('gives a staff view no requester block', async () => {
    mockFetch.mockResolvedValue(jsonRes({ ticketId: TICKET, isRequester: false, requester: null, draft: null, draftWaiting: false }));
    expect((await fetchTicketDesk(TICKET)).requester).toBeNull();
  });
});

// ------------------------------------------------------------------------------------------ cited articles

describe('CitedArticles', () => {
  const article = (over: Record<string, unknown> = {}) => ({ articleId: 'a-1', title: 'Reset your password', content: 'Step 1\nStep 2', available: true, ...over });

  it('lists each citation as a collapsed disclosure button and reads nothing until one opens', () => {
    render(<CitedArticles ticketId={TICKET} citations={CITES} />);
    const buttons = screen.getAllByRole('button');
    expect(buttons.map(b => b.textContent)).toEqual(['Reset your password', 'VPN setup']);
    buttons.forEach(b => expect(b).toHaveAttribute('aria-expanded', 'false'));
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('shows Loading article... then the read-only text, and reads each article only once', async () => {
    let release: (r: Response) => void = () => {};
    mockFetch.mockImplementation(() => new Promise<Response>(resolve => { release = resolve; }));
    render(<CitedArticles ticketId={TICKET} citations={CITES} />);
    const button = screen.getByRole('button', { name: 'Reset your password' });
    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'true');
    expect(await screen.findByText('Loading article...')).toBeInTheDocument();
    await act(async () => { release(jsonRes(article())); });
    expect(await screen.findByText(/Step 1/)).toBeInTheDocument();
    expect(screen.getByText(/Read-only\. This is the article the answer was based on\./)).toBeInTheDocument();
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0][0]).toBe('/api/tickets/t-1/service-desk/articles/a-1');
    fireEvent.click(button);
    fireEvent.click(button);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('wraps long text and scrolls the expanded region inside max-h-64', async () => {
    mockFetch.mockResolvedValue(jsonRes(article({ content: 'x'.repeat(5000) })));
    render(<CitedArticles ticketId={TICKET} citations={CITES} />);
    fireEvent.click(screen.getByRole('button', { name: 'Reset your password' }));
    const text = await screen.findByText('x'.repeat(5000));
    expect(text.className).toContain('whitespace-pre-wrap');
    expect(text.className).toContain('break-words');
    const region = document.getElementById(screen.getByRole('button', { name: 'Reset your password' }).getAttribute('aria-controls')!)!;
    expect(region.className).toContain('max-h-64');
    expect(region.className).toContain('overflow-y-auto');
    expect(region.className).toContain('p-4');
  });

  it('says it could not load the article and loads it again with Try again', async () => {
    mockFetch.mockResolvedValueOnce(jsonRes({ detail: 'x' }, 500)).mockResolvedValueOnce(jsonRes(article()));
    render(<CitedArticles ticketId={TICKET} citations={CITES} />);
    fireEvent.click(screen.getByRole('button', { name: 'Reset your password' }));
    expect(await screen.findByText("Couldn't load this article. Try again.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText(/Step 1/)).toBeInTheDocument();
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('keeps the title of a deleted article and says it is no longer available', async () => {
    mockFetch.mockResolvedValue(jsonRes(article({ content: '', available: false })));
    render(<CitedArticles ticketId={TICKET} citations={CITES} />);
    fireEvent.click(screen.getByRole('button', { name: 'Reset your password' }));
    expect(await screen.findByText('This article is no longer available.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reset your password' })).toBeInTheDocument();
  });

  it('renders an article text as text, never as markup', async () => {
    mockFetch.mockResolvedValue(jsonRes(article({ content: '<img src=x onerror=alert(1)> **bold**' })));
    const { container } = render(<CitedArticles ticketId={TICKET} citations={CITES} />);
    fireEvent.click(screen.getByRole('button', { name: 'Reset your password' }));
    await screen.findByText(/onerror/);
    expect(container.querySelector('img')).toBeNull();
  });
});

// ------------------------------------------------------------------------------------------ the requester's panel

describe('RequesterAnswerPanel: states', () => {
  it('shows the mark, the answer, the cited articles, the footer, the return date and both buttons while an answer waits', () => {
    rendered(requesterView());
    const panel = document.getElementById('service-desk-answer')!;
    expect(panel).toHaveAttribute('tabindex', '-1');
    expect(screen.getByRole('heading', { name: 'Answer from IT support' })).toBeInTheDocument();
    expect(screen.getByText(MARK)).toBeInTheDocument();
    expect(screen.getByText('Open Settings and choose Reset.')).toBeInTheDocument();
    expect(screen.getByText('Based on')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'VPN setup' })).toBeInTheDocument();
    expect(screen.getByText(FOOTER)).toBeInTheDocument();
    expect(screen.getByText(/^If we don't hear back by \w{3} \d{1,2} \w{3}, a person from IT will pick this up\.$/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'This fixed it' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'I still need help' })).toBeEnabled();
    expect(screen.getByText('Marks your ticket resolved.')).toBeInTheDocument();
  });

  it('leaves out the return date when the server sends none', () => {
    rendered(requesterView({ returnAt: null }));
    expect(screen.queryByText(/If we don't hear back/)).toBeNull();
  });

  it('wraps a long answer and never truncates it', () => {
    const long = 'word '.repeat(600).trim();
    rendered(requesterView({}, [item({ text: long })]));
    const text = screen.getByText(long);
    expect(text.className).toContain('whitespace-pre-wrap');
    expect(text.className).toContain('break-words');
  });

  it('shows the confirmed notice with the time and removes the buttons', () => {
    rendered(requesterView({ canConfirm: false, notice: 'confirmed', confirmedAt: '2026-11-09T14:30:00Z' }));
    expect(screen.getByRole('status')).toHaveTextContent(/^You confirmed this fixed it on \w{3} \d{1,2} \w{3}, \d\d:\d\d\. The ticket is resolved\.$/);
    expect(screen.queryByRole('button', { name: 'This fixed it' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'I still need help' })).toBeNull();
  });

  it('shows Sent to IT after a help request, with the buttons gone', () => {
    rendered(requesterView({ canConfirm: false, notice: 'helped' }));
    expect(screen.getByRole('status')).toHaveTextContent('Sent to IT. A person will take over.');
    expect(screen.queryByRole('button', { name: 'This fixed it' })).toBeNull();
  });

  it('shows the hand-off notice for a ticket a person now has, with and without an answer', () => {
    const { unmount } = rendered(requesterView({ canConfirm: false, notice: 'handed_off' }));
    expect(screen.getByRole('status')).toHaveTextContent(HANDOFF_NOTICE);
    expect(screen.getByText(MARK)).toBeInTheDocument();
    unmount();
    rendered(requesterView({ canConfirm: false, notice: 'handed_off' }, []));
    expect(screen.getByRole('status')).toHaveTextContent(HANDOFF_NOTICE);
    expect(screen.queryByText(MARK)).toBeNull();
  });

  it('shows the no-reply-in-3-days case as the same hand-off notice and never a reason', () => {
    rendered(requesterView({ canConfirm: false, notice: 'handed_off' }));
    expect(screen.getByRole('status').textContent).toBe(HANDOFF_NOTICE);
    expect(screen.queryByText(/no reply/i)).toBeNull();
  });

  it('hides the text of a withdrawn answer and says a person will follow up', () => {
    rendered(requesterView({ canConfirm: false, notice: 'withdrawn' }));
    expect(screen.getByRole('status')).toHaveTextContent(WITHDRAWN_NOTICE);
    expect(screen.queryByText('Open Settings and choose Reset.')).toBeNull();
    expect(screen.queryByRole('button', { name: 'This fixed it' })).toBeNull();
  });

  it('lists replies from IT with the staff name, or IT when there is none, and keeps the buttons while canConfirm', () => {
    rendered(requesterView({}, [
      item(),
      item({ id: 'c-2', kind: 'reply', author: 'Sam Rivera', text: 'Try the second step again.', at: '2026-11-09T11:00:00Z', citations: [] }),
      item({ id: 'c-3', kind: 'reply', author: null, text: 'Any news?', at: '2026-11-09T12:00:00Z', citations: [] }),
    ]));
    expect(screen.getByText(/^Sam Rivera · /)).toBeInTheDocument();
    expect(screen.getByText(/^IT · /)).toBeInTheDocument();
    expect(screen.getByText('Try the second step again.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'This fixed it' })).toBeInTheDocument();
  });

  it('removes the buttons when the server says the requester cannot answer (staff resolved it) and adds no notice', () => {
    rendered(requesterView({ canConfirm: false }));
    expect(screen.queryByRole('button', { name: 'This fixed it' })).toBeNull();
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.getByText('Open Settings and choose Reset.')).toBeInTheDocument();
  });

  it('renders nothing when nothing is visible to the requester', () => {
    const { container } = rendered(requesterView({ canConfirm: false }, []));
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for staff, who get no requester block, and never shows a draft', () => {
    const view = { ...requesterView(), isRequester: false, requester: null };
    const { container } = rendered(view);
    expect(container.firstChild).toBeNull();
  });

  it('ignores the requester\'s own notes and system notices in the list of answers', () => {
    rendered(requesterView({}, [item(), item({ id: 'c-2', kind: 'you', text: 'my own note text', citations: [] })]));
    expect(screen.queryByText('my own note text')).toBeNull();
  });
});

describe('RequesterAnswerPanel: This fixed it and I still need help', () => {
  it('posts confirm once, shows Saving... with both buttons disabled, then the confirmed notice and refetches', async () => {
    let release: (r: Response) => void = () => {};
    mockFetch.mockImplementation(() => new Promise<Response>(resolve => { release = resolve; }));
    const { onChanged } = rendered(requesterView());
    const fixed = screen.getByRole('button', { name: 'This fixed it' });
    fireEvent.click(fixed);
    fireEvent.click(fixed);
    expect(await screen.findByRole('button', { name: 'Saving...' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'I still need help' })).toBeDisabled();
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith('/api/tickets/t-1/service-desk/confirm', { method: 'POST', body: '{}' });
    await act(async () => { release(jsonRes({ status: 'confirmed' })); });
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    const notice = await screen.findByRole('status');
    expect(notice).toHaveTextContent(/^You confirmed this fixed it on /);
    await waitFor(() => expect(notice.parentElement).toBe(document.activeElement));
    expect(screen.queryByRole('button', { name: 'This fixed it' })).toBeNull();
  });

  it('shows the failure with the server message and re-enables both buttons', async () => {
    mockFetch.mockResolvedValue(jsonRes({ detail: 'This ticket has no answer waiting for your reply.' }, 422));
    rendered(requesterView());
    fireEvent.click(screen.getByRole('button', { name: 'This fixed it' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't save your answer: This ticket has no answer waiting for your reply. Try again.");
    expect(screen.getByRole('button', { name: 'This fixed it' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'I still need help' })).toBeEnabled();
  });

  it('uses the fallback copy when the request never gets an answer', async () => {
    mockFetch.mockRejectedValue(new Error('network down'));
    rendered(requesterView());
    fireEvent.click(screen.getByRole('button', { name: 'This fixed it' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't save your answer. Check your connection and try again.");
  });

  it('shows the server text of a 409 and reads the ticket again', async () => {
    mockFetch.mockResolvedValue(jsonRes({ detail: 'This ticket has no answer waiting for your reply.' }, 409));
    const { onChanged } = rendered(requesterView());
    fireEvent.click(screen.getByRole('button', { name: 'This fixed it' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('This ticket has no answer waiting for your reply');
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  });

  it('reveals the labelled note box with a 1,000 counter, and Back to answer hides it', async () => {
    rendered(requesterView());
    fireEvent.click(screen.getByRole('button', { name: 'I still need help' }));
    const box = await screen.findByLabelText("Tell IT what's still wrong (optional)");
    expect(box).toHaveAttribute('maxlength', '1000');
    await waitFor(() => expect(box).toHaveFocus());
    expect(screen.getByText('0/1000')).toBeInTheDocument();
    fireEvent.change(box, { target: { value: 'still broken' } });
    expect(screen.getByText('12/1000')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Back to answer' }));
    expect(screen.queryByLabelText("Tell IT what's still wrong (optional)")).toBeNull();
    expect(screen.getByRole('button', { name: 'I still need help' })).toBeInTheDocument();
  });

  it('caps the note at 1,000 characters', async () => {
    rendered(requesterView());
    fireEvent.click(screen.getByRole('button', { name: 'I still need help' }));
    const box = await screen.findByLabelText("Tell IT what's still wrong (optional)");
    fireEvent.change(box, { target: { value: 'n'.repeat(1200) } });
    expect(screen.getByText('1000/1000')).toBeInTheDocument();
  });

  it('posts the note to help, shows Sending... while pending, then the Sent to IT notice', async () => {
    let release: (r: Response) => void = () => {};
    mockFetch.mockImplementation(() => new Promise<Response>(resolve => { release = resolve; }));
    const { onChanged } = rendered(requesterView());
    fireEvent.click(screen.getByRole('button', { name: 'I still need help' }));
    fireEvent.change(await screen.findByLabelText("Tell IT what's still wrong (optional)"), { target: { value: 'still broken' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send to IT' }));
    expect(await screen.findByRole('button', { name: 'Sending...' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'This fixed it' })).toBeDisabled();
    expect(mockFetch).toHaveBeenCalledWith('/api/tickets/t-1/service-desk/help', { method: 'POST', body: JSON.stringify({ text: 'still broken' }) });
    await act(async () => { release(jsonRes({ status: 'helped' })); });
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole('status')).toHaveTextContent('Sent to IT. A person will take over.');
  });

  it('sends an empty body when no note was written', async () => {
    mockFetch.mockResolvedValue(jsonRes({ status: 'helped' }));
    rendered(requesterView());
    fireEvent.click(screen.getByRole('button', { name: 'I still need help' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Send to IT' }));
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(mockFetch).toHaveBeenCalledWith('/api/tickets/t-1/service-desk/help', { method: 'POST', body: '{}' });
  });

  it('shows the failure of a help request and keeps the note box open', async () => {
    mockFetch.mockResolvedValue(jsonRes({ detail: 'Use up to 1000 characters.' }, 422));
    rendered(requesterView());
    fireEvent.click(screen.getByRole('button', { name: 'I still need help' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Send to IT' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't save your answer: Use up to 1000 characters. Try again.");
    expect(screen.getByLabelText("Tell IT what's still wrong (optional)")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send to IT' })).toBeEnabled();
  });
});

// ------------------------------------------------------------------------------------------ the staff draft panel

const draft = (over: Record<string, unknown> = {}) => ({
  commentId: 'd-1', actionId: 'act-1', answer: 'Open Settings and choose Reset.', citations: CITES,
  createdAt: new Date(Date.now() - 2 * 3600 * 1000).toISOString(), articleCount: 2,
  draftReason: 'mode_drafts', draftReasonText: 'Kept as a draft because the service desk is set to Drafts only.',
  maxAnswerLength: 900, canActOnDraft: true, blockedReason: null, blockedText: null, reporter: 'Dana Lee', ...over,
});

const staffView = (over: Record<string, unknown> = {}) => ({
  ticketId: TICKET, ticketNumber: 'TKT-0042', status: 'open', isRequester: false, requester: null,
  draft: draft(over), canReplyToRequester: true, draftWaiting: true,
}) as any;

const panel = (view: any, onChanged = vi.fn()) => {
  const out = render(<TicketDraftPanel ticketId={TICKET} view={view} actorName="Sam Rivera" onChanged={onChanged} />);
  return { ...out, onChanged };
};

describe('TicketDraftPanel: the five zones', () => {
  it('shows the header, the reason, the answer box, the consequence line and the three buttons', () => {
    panel(staffView());
    const section = document.getElementById('service-desk-draft')!;
    expect(section).toHaveAttribute('tabindex', '-1');
    expect(screen.getByRole('heading', { name: 'Draft answer' })).toBeInTheDocument();
    expect(screen.getByText(/^Written by the service desk 2 hours ago from 2 articles\. Only staff can see this\.$/)).toBeInTheDocument();
    expect(screen.getByText('Draft')).toBeInTheDocument();
    expect(screen.getByText('Kept as a draft because the service desk is set to Drafts only.')).toBeInTheDocument();
    expect(screen.getByText('What the requester will see')).toBeInTheDocument();
    expect(screen.getByText(MARK)).toBeInTheDocument();
    expect(screen.getByText('Open Settings and choose Reset.')).toBeInTheDocument();
    expect(screen.getByText('Based on')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reset your password' })).toBeInTheDocument();
    expect(screen.getByText(FOOTER)).toBeInTheDocument();
    const consequence = screen.getByText(fill(DRAFT_PANEL.consequence, { reporter: 'Dana Lee' }));
    expect(screen.getByRole('button', { name: 'Send as is' })).toHaveAttribute('aria-describedby', consequence.id);
    expect(screen.getByRole('button', { name: 'Edit and send' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Discard draft' })).toBeEnabled();
  });

  it('leaves the reason line out when the server supplies none', () => {
    panel(staffView({ draftReason: null, draftReasonText: null }));
    expect(screen.queryByText(/^Kept as a draft/)).toBeNull();
  });

  it('wraps a long answer and scrolls nothing away', () => {
    const long = 'line '.repeat(400).trim();
    panel(staffView({ answer: long }));
    const text = screen.getByText(long);
    expect(text.className).toContain('whitespace-pre-wrap');
    expect(text.className).toContain('break-words');
  });

  it('renders nothing when no draft is waiting', () => {
    const { container } = panel({ ...staffView(), draft: null, draftWaiting: false });
    expect(container.firstChild).toBeNull();
  });
});

describe('TicketDraftPanel: Send as is', () => {
  it('posts send once, shows Sending... with all three disabled, then the result line with focus and refetches', async () => {
    let release: (r: Response) => void = () => {};
    mockFetch.mockImplementation(() => new Promise<Response>(resolve => { release = resolve; }));
    const { onChanged } = panel(staffView());
    const send = screen.getByRole('button', { name: 'Send as is' });
    fireEvent.click(send);
    fireEvent.click(send);
    expect(await screen.findByRole('button', { name: 'Sending...' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Edit and send' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Discard draft' })).toBeDisabled();
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith('/api/tickets/t-1/service-desk/drafts/d-1/send', { method: 'POST', body: '{}' });
    await act(async () => { release(jsonRes({ status: 'sent', commentId: 'd-1', edited: false })); });
    const result = await screen.findByRole('status');
    expect(result).toHaveTextContent(/^Sent to Dana Lee by Sam Rivera at \d\d:\d\d\. The ticket is waiting on the customer\.$/);
    await waitFor(() => expect(result).toHaveFocus());
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: 'Send as is' })).toBeNull();
  });

  it('shows the failure with the server message and re-enables the buttons', async () => {
    mockFetch.mockResolvedValue(jsonRes({ detail: 'A person already replied, so this draft can not be sent' }, 500));
    panel(staffView());
    fireEvent.click(screen.getByRole('button', { name: 'Send as is' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't send the answer: A person already replied, so this draft can not be sent. Try again.");
    expect(screen.getByRole('button', { name: 'Send as is' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Edit and send' })).toBeEnabled();
  });

  it('uses the fallback copy on a network failure', async () => {
    mockFetch.mockRejectedValue(new Error('offline'));
    panel(staffView());
    fireEvent.click(screen.getByRole('button', { name: 'Send as is' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't send the answer. Check your connection and try again.");
  });

  it('replaces the buttons with the server text on a 409 already handled and refetches', async () => {
    mockFetch.mockResolvedValue(jsonRes({ detail: 'This draft was already handled.' }, 409));
    const { onChanged } = panel(staffView());
    fireEvent.click(screen.getByRole('button', { name: 'Send as is' }));
    expect(await screen.findByText('This draft was already handled.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send as is' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Discard draft' })).toBeNull();
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  });
});

describe('TicketDraftPanel: Edit and send', () => {
  const open = async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Edit and send' }));
    return screen.findByLabelText('Edit the answer') as Promise<HTMLTextAreaElement>;
  };

  it('swaps in the textarea with the counter from the server limit, and Send edit starts disabled with the reason', async () => {
    panel(staffView());
    const box = await open();
    expect(box).toHaveValue('Open Settings and choose Reset.');
    expect(screen.getByText('31/900')).toBeInTheDocument();
    expect(screen.getByText(DRAFT_PANEL.editHelper)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send edit' })).toBeDisabled();
    expect(screen.getByText('Change the text, or use Send as is.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send as is' })).toBeNull();
  });

  it('enables Send edit for a changed text and posts it to edit', async () => {
    mockFetch.mockResolvedValue(jsonRes({ status: 'sent', commentId: 'd-1', edited: true }));
    const { onChanged } = panel(staffView());
    const box = await open();
    fireEvent.change(box, { target: { value: 'Open Settings, then choose Reset.' } });
    expect(screen.queryByText('Change the text, or use Send as is.')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Send edit' }));
    expect(await screen.findByRole('status')).toHaveTextContent(/^Sent to Dana Lee by Sam Rivera at /);
    expect(mockFetch).toHaveBeenCalledWith('/api/tickets/t-1/service-desk/drafts/d-1/edit',
      { method: 'POST', body: JSON.stringify({ text: 'Open Settings, then choose Reset.' }) });
    expect(onChanged).toHaveBeenCalled();
  });

  it('disables Send edit for empty text and for text over the server limit', async () => {
    panel(staffView({ maxAnswerLength: 40 }));
    const box = await open();
    fireEvent.change(box, { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: 'Send edit' })).toBeDisabled();
    fireEvent.change(box, { target: { value: 'x'.repeat(41) } });
    expect(screen.getByText('41/40')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send edit' })).toBeDisabled();
    fireEvent.change(box, { target: { value: 'x'.repeat(40) } });
    expect(screen.getByRole('button', { name: 'Send edit' })).toBeEnabled();
  });

  it('restores the original text with Back to draft', async () => {
    panel(staffView());
    const box = await open();
    fireEvent.change(box, { target: { value: 'something else' } });
    fireEvent.click(screen.getByRole('button', { name: 'Back to draft' }));
    expect(screen.queryByLabelText('Edit the answer')).toBeNull();
    expect(screen.getByText('Open Settings and choose Reset.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Edit and send' }));
    expect(await screen.findByLabelText('Edit the answer')).toHaveValue('Open Settings and choose Reset.');
  });

  it('asks Discard your edits? on Esc with edits and leaves quietly without them', async () => {
    panel(staffView());
    let box = await open();
    fireEvent.keyDown(box, { key: 'Escape' });
    expect(screen.queryByLabelText('Edit the answer')).toBeNull();
    box = await open();
    fireEvent.change(box, { target: { value: 'changed' } });
    fireEvent.keyDown(box, { key: 'Escape' });
    expect(screen.getByText('Discard your edits?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Keep editing' }));
    expect(screen.getByLabelText('Edit the answer')).toHaveValue('changed');
    fireEvent.keyDown(screen.getByLabelText('Edit the answer'), { key: 'Escape' });
    fireEvent.click(screen.getByRole('button', { name: 'Discard edits' }));
    expect(screen.queryByLabelText('Edit the answer')).toBeNull();
    expect(screen.getByText('Open Settings and choose Reset.')).toBeInTheDocument();
  });

  it('shows the server refusal of an edit as the failure line and keeps the text', async () => {
    mockFetch.mockResolvedValue(jsonRes({ detail: 'The answer is over 900 characters. Shorten it.' }, 422));
    panel(staffView());
    const box = await open();
    fireEvent.change(box, { target: { value: 'a different answer' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send edit' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't send the answer: The answer is over 900 characters. Shorten it. Try again.");
    expect(screen.getByLabelText('Edit the answer')).toHaveValue('a different answer');
  });
});

describe('TicketDraftPanel: Discard draft', () => {
  it('opens Discard this draft? with Keep draft first, and Keep draft closes it without a request', async () => {
    panel(staffView());
    fireEvent.click(screen.getByRole('button', { name: 'Discard draft' }));
    const dialog = await screen.findByRole('dialog', { name: 'Discard this draft?' });
    expect(within(dialog).getByText(/^The requester never sees it\./)).toBeInTheDocument();
    const buttons = within(dialog).getAllByRole('button');
    expect(buttons.map(b => b.textContent)).toEqual(['Keep draft', 'Discard draft']);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Keep draft' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('posts discard from the red confirm, toasts Draft discarded. and shows the result line', async () => {
    mockFetch.mockResolvedValue(jsonRes({ status: 'discarded', commentId: 'd-1' }));
    const { onChanged } = panel(staffView());
    fireEvent.click(screen.getByRole('button', { name: 'Discard draft' }));
    const dialog = await screen.findByRole('dialog', { name: 'Discard this draft?' });
    const confirm = within(dialog).getByRole('button', { name: 'Discard draft' });
    expect(confirm.className).toContain('bg-red-600');
    fireEvent.click(confirm);
    expect(await screen.findByRole('status')).toHaveTextContent(/^Draft discarded by Sam Rivera at \d\d:\d\d\.$/);
    expect(mockFetch).toHaveBeenCalledWith('/api/tickets/t-1/service-desk/drafts/d-1/discard', { method: 'POST', body: '{}' });
    expect(showToast).toHaveBeenCalledWith('Draft discarded.', 'success');
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it('shows Discarding... while pending and the discard failure inside the dialog', async () => {
    let release: (r: Response) => void = () => {};
    mockFetch.mockImplementation(() => new Promise<Response>(resolve => { release = resolve; }));
    panel(staffView());
    fireEvent.click(screen.getByRole('button', { name: 'Discard draft' }));
    const dialog = await screen.findByRole('dialog', { name: 'Discard this draft?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Discard draft' }));
    expect(await within(dialog).findByRole('button', { name: 'Discarding...' })).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Keep draft' })).toBeDisabled();
    await act(async () => { release(jsonRes({ detail: 'This draft was already handled.' }, 500)); });
    expect(await within(dialog).findByRole('alert')).toHaveTextContent("Couldn't discard the draft: This draft was already handled. Try again.");
    expect(within(dialog).getByRole('button', { name: 'Discard draft' })).toBeEnabled();
  });
});

describe('TicketDraftPanel: blocked states', () => {
  it('disables send and edit on a resolved ticket with the server text and keeps Discard draft', () => {
    panel(staffView({
      canActOnDraft: false, blockedReason: 'ticket_closed',
      blockedText: "This ticket is resolved, so the draft can't be sent. You can still discard it.",
    }));
    expect(screen.getByText("This ticket is resolved, so the draft can't be sent. You can still discard it.")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send as is' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Edit and send' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Discard draft' })).toBeEnabled();
  });

  it('disables send and edit once a person already replied and keeps Discard draft', () => {
    panel(staffView({
      canActOnDraft: false, blockedReason: 'person_replied',
      blockedText: "A person already replied, so this draft can't be sent. You can still discard it.",
    }));
    expect(screen.getByText(DRAFT_PANEL.personReplied)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send as is' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Discard draft' })).toBeEnabled();
  });

  it('replaces the actions with the no-requester text and leaves Discard draft only', () => {
    panel(staffView({
      canActOnDraft: false, blockedReason: 'no_requester',
      blockedText: "This ticket has no requester who can see an answer, so the draft can't be sent.",
    }));
    expect(screen.getByText(DRAFT_PANEL.noRequester)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send as is' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Edit and send' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Discard draft' })).toBeEnabled();
  });

  it('falls back to the copy text for the blocked reason when the server sends none', () => {
    panel(staffView({ canActOnDraft: false, blockedReason: 'ticket_closed', blockedText: null }));
    expect(screen.getByText(fill(DRAFT_PANEL.closedBlocked, { state: 'open' }))).toBeInTheDocument();
  });
});
