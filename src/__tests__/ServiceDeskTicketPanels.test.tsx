/**
 * Phase 85 / DESK-01 (85-20): the cited-article list and the requester's answer panel of 85-UI-SPEC section 4, and the
 * staff draft panel of section 3. authFetch and the toast are mocked; the payloads follow 85-14-SUMMARY.md (the server
 * sends the STORED comment kind, the API layer maps it). Nothing here reaches a real API.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: vi.fn() }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { authFetch } from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { CitedArticles } from '../../components/serviceDesk/CitedArticles';
import { RequesterAnswerPanel } from '../../components/serviceDesk/RequesterAnswerPanel';
import { fetchTicketDesk, mapRequesterKind } from '../../services/serviceDesk/ticketApi';
import { FOOTER, HANDOFF_NOTICE, MARK, WITHDRAWN_NOTICE } from '../../components/serviceDesk/serviceDeskCopy';

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
