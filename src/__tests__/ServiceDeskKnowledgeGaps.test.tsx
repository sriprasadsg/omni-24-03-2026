/**
 * Phase 85 / DESK-06 (85-21): the Knowledge gaps tab of the Knowledge Base screen (85-UI-SPEC section 6, D-26, D-27).
 * authFetch and the toast are mocked; the payloads follow 85-15-SUMMARY.md (GapsView). Nothing here reaches a real API.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: vi.fn() }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { showToast } from '../../utils/toast';
import { GAPS, KB, TOASTS, fill } from '../../components/serviceDesk/serviceDeskCopy';
import {
  bodyOf, calls, deferred, docList, jsonRes, kbDoc, kbFlags, mockFetch, renderKb, serve, type Json,
} from './_serviceDeskKnowledgeHarness';

const LIST = '/api/knowledge/docs';
const COUNT = '/api/knowledge/helpdesk/gaps';
const FULL = '/api/knowledge/helpdesk/gaps?dismissed=true';

const tickets = (n: number, from = 40) => Array.from({ length: n }, (_, i) => ({ id: `t-${from + i}`, number: `TKT-${String(from + i).padStart(4, '0')}` }));
const group = (over: Json = {}): Json => ({
  id: 'g-1', question: 'How do I reset my VPN?', count: 2, lastAskedAt: new Date(Date.now() - 2 * 3600 * 1000).toISOString(),
  tickets: tickets(2), status: 'open', ...over,
});
const view = (groups: Json[], over: Json = {}): Json => ({ groups, otherLanguageCount: 0, dismissedCount: 0, deskOff: false, ...over });

const canSee = () => docList([kbDoc()], kbFlags({ canSeeGaps: true, helpdeskCount: 1 }));

/** Opens the screen with gaps allowed and goes to the tab. `full` answers the tab's own read, `count` the count read. */
async function openTab(full: Json, count: Json = full, extra: Record<string, any> = {}) {
  serve({
    [`GET ${LIST}`]: () => canSee(),
    [`GET ${COUNT}`]: () => jsonRes(count),
    [`GET ${FULL}`]: () => jsonRes(full),
    ...extra,
  });
  const out = await renderKb();
  fireEvent.click(await screen.findByRole('button', { name: /^Knowledge gaps/ }));
  return out;
}

beforeEach(() => { mockFetch.mockReset(); vi.mocked(showToast).mockReset(); });

describe('the tab itself', () => {
  it('is not there, and asks nothing, without canSeeGaps', async () => {
    serve({ [`GET ${LIST}`]: docList([kbDoc()], kbFlags({ canSeeGaps: false })) });
    await renderKb();
    await screen.findByText('Printer fix');
    expect(screen.queryByRole('button', { name: /Knowledge gaps/ })).toBeNull();
    expect(calls('GET', COUNT)).toHaveLength(0);
  });

  it('reads the count once on mount and shows it in amber when there are open groups', async () => {
    serve({ [`GET ${LIST}`]: () => canSee(), [`GET ${COUNT}`]: () => jsonRes(view([group(), group({ id: 'g-2' })])) });
    await renderKb();
    const tab = await screen.findByRole('button', { name: fill(GAPS.tab, { n: 2 }) });
    expect(tab.className).toContain('amber');
    expect(calls('GET', COUNT)).toHaveLength(1);
  });

  it('is not amber when nothing is open, and does not read again while another tab is shown', async () => {
    serve({ [`GET ${LIST}`]: () => canSee(), [`GET ${COUNT}`]: () => jsonRes(view([])) });
    await renderKb();
    const tab = await screen.findByRole('button', { name: fill(GAPS.tab, { n: 0 }) });
    expect(tab.className).not.toContain('amber');
    fireEvent.click(screen.getByRole('button', { name: fill(KB.filterAll, { total: 1 }) }));
    expect(calls('GET', COUNT)).toHaveLength(1);
    expect(calls('GET', FULL)).toHaveLength(0);
  });
});

describe('the groups', () => {
  it('lists them in the server order with the question, the count words and the ticket numbers', async () => {
    await openTab(view([
      group({ id: 'g-1', question: 'Printer is jammed', count: 1, tickets: tickets(1, 7) }),
      group({ id: 'g-2', question: 'VPN keeps dropping', count: 3, tickets: tickets(3, 20) }),
    ]));
    const list = await screen.findByRole('list', { name: GAPS.listLabel });
    const cards = within(list).getAllByRole('listitem');
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).getByText('Printer is jammed')).toBeInTheDocument();
    expect(within(cards[0]).getByText(/^1 ticket · Last asked /)).toBeInTheDocument();
    expect(within(cards[1]).getByText(/^3 tickets · Last asked 2 hours ago$/)).toBeInTheDocument();
    expect(within(cards[1]).getByText('TKT-0020').className).toContain('font-mono');
    expect(screen.getByRole('heading', { name: GAPS.heading })).toBeInTheDocument();
    expect(screen.getByText(GAPS.intro)).toBeInTheDocument();
    expect(calls('GET', FULL)).toHaveLength(1);
  });

  it('shows the first three tickets, then all of them in place on Show all', async () => {
    await openTab(view([group({ count: 5, tickets: tickets(5, 10) })]));
    const card = (await screen.findAllByRole('listitem'))[0];
    expect(within(card).getAllByText(/^TKT-/)).toHaveLength(3);
    const more = within(card).getByRole('button', { name: fill(GAPS.showAllTickets, { n: 5 }) });
    expect(more).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(more);
    expect(within(card).getAllByText(/^TKT-/)).toHaveLength(5);
    expect(within(card).getByRole('button', { name: fill(GAPS.showAllTickets, { n: 5 }) })).toHaveAttribute('aria-expanded', 'true');
  });

  it('wraps a long question instead of cutting it off', async () => {
    const long = 'Why does the shared drive on the third floor disconnect every time '.repeat(3).trim();
    await openTab(view([group({ question: long })]));
    expect((await screen.findByText(long)).className).toContain('break-words');
  });

  it('shows ten groups, then ten more on Show more gaps', async () => {
    const twelve = Array.from({ length: 12 }, (_, i) => group({ id: `g-${i}`, question: `Question ${i}`, count: 12 - i }));
    await openTab(view(twelve));
    await screen.findByText('Question 0');
    expect(screen.getAllByRole('listitem')).toHaveLength(10);
    fireEvent.click(screen.getByRole('button', { name: GAPS.showMore }));
    expect(screen.getAllByRole('listitem')).toHaveLength(12);
    expect(screen.queryByRole('button', { name: GAPS.showMore })).toBeNull();
  });

  it('counts other-language tickets in one line, singular and plural, and always shows the footnote', async () => {
    const first = await openTab(view([group()], { otherLanguageCount: 3 }));
    expect(await screen.findByText(fill(GAPS.otherLanguage, { n: 3 }))).toBeInTheDocument();
    expect(screen.getByText(GAPS.footnote)).toBeInTheDocument();
    first.unmount();
    mockFetch.mockReset();
    await openTab(view([group()], { otherLanguageCount: 1 }));
    expect(await screen.findByText(GAPS.otherLanguageOne)).toBeInTheDocument();
  });
});

describe('Dismiss gap and Restore gap', () => {
  it('dismisses with one request, says Dismissing... meanwhile, toasts, removes the group and lowers the count', async () => {
    const answer = deferred<Response>();
    const data = view([group({ id: 'g-1', question: 'First' }), group({ id: 'g-2', question: 'Second' })]);
    await openTab(data, data, { 'POST /api/knowledge/helpdesk/gaps/g-1/dismiss': () => answer.promise });
    const first = (await screen.findAllByRole('listitem'))[0];
    fireEvent.click(within(first).getByRole('button', { name: new RegExp(`^${GAPS.dismiss}`) }));
    const busy = await within(first).findByRole('button', { name: GAPS.dismissing });
    expect(busy).toBeDisabled();
    answer.resolve(jsonRes({ status: 'dismissed', changed: 2 }));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith(TOASTS.gapDismissed, 'success'));
    expect(calls('POST', '/api/knowledge/helpdesk/gaps/g-1/dismiss')).toHaveLength(1);
    await waitFor(() => expect(screen.queryByText('First')).toBeNull());
    expect(screen.getByText('Second')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: fill(GAPS.tab, { n: 1 }) })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: fill(GAPS.showDismissed, { d: 1 }) })).toBeInTheDocument();
  });

  it('keeps the group and says why when dismissing fails', async () => {
    await openTab(view([group()]), view([group()]), {
      'POST /api/knowledge/helpdesk/gaps/g-1/dismiss': jsonRes({ detail: 'Group not found.' }, 404),
    });
    fireEvent.click(await screen.findByRole('button', { name: new RegExp(`^${GAPS.dismiss}`) }));
    expect(await screen.findByRole('alert')).toHaveTextContent(fill(GAPS.actionFailed, { message: 'Group not found' }));
    expect(screen.getByText('How do I reset my VPN?')).toBeInTheDocument();
    expect(showToast).not.toHaveBeenCalled();
  });

  it('shows dismissed groups only on request, with Restore gap instead of the two actions, and restores with one request', async () => {
    const data = view([
      group({ id: 'g-1', question: 'Open one' }), group({ id: 'g-2', question: 'Set aside', status: 'dismissed' }),
    ], { dismissedCount: 1 });
    await openTab(data, view([group({ id: 'g-1' })], { dismissedCount: 1 }), {
      'POST /api/knowledge/helpdesk/gaps/g-2/restore': jsonRes({ status: 'open', changed: 2 }),
    });
    await screen.findByText('Open one');
    expect(screen.queryByText('Set aside')).toBeNull();
    const toggle = screen.getByRole('button', { name: fill(GAPS.showDismissed, { d: 1 }) });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(toggle);
    const set = screen.getByText('Set aside').closest('li') as HTMLElement;
    expect(within(set).getByText(GAPS.chipDismissed)).toBeInTheDocument();
    expect(within(set).queryByRole('button', { name: new RegExp(`^${GAPS.dismiss}`) })).toBeNull();
    expect(within(set).queryByRole('button', { name: new RegExp(`^${GAPS.writeArticle}`) })).toBeNull();
    expect(screen.getByRole('button', { name: GAPS.hideDismissed })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(within(set).getByRole('button', { name: new RegExp(`^${GAPS.restore}`) }));
    await waitFor(() => expect(within(set).queryByText(GAPS.chipDismissed)).toBeNull());
    expect(calls('POST', '/api/knowledge/helpdesk/gaps/g-2/restore')).toHaveLength(1);
    expect(screen.queryByRole('button', { name: GAPS.hideDismissed })).toBeNull();
  });
});

describe('Write article from a gap', () => {
  it('opens the article dialog with the question as the title and Help desk ticked, then closes the gap on save', async () => {
    let served = 0;
    serve({
      [`GET ${LIST}`]: () => canSee(),
      [`GET ${COUNT}`]: () => jsonRes(view([group()])),
      [`GET ${FULL}`]: () => jsonRes(served++ === 0 ? view([group()]) : view([])),
      'POST /api/knowledge/helpdesk/articles': jsonRes({ id: 'kb-9', title: 'x', helpdesk: true, gapsWritten: 2 }),
    });
    await renderKb();
    fireEvent.click(await screen.findByRole('button', { name: /^Knowledge gaps/ }));
    fireEvent.click(await screen.findByRole('button', { name: new RegExp(`^${GAPS.writeArticle}`) }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: KB.articleDialogWrite })).toBeInTheDocument();
    expect((within(dialog).getByLabelText(KB.fieldTitle) as HTMLInputElement).value).toBe('How do I reset my VPN?');
    expect(within(dialog).getByRole('checkbox', { name: KB.helpdeskCheckbox })).toBeChecked();
    fireEvent.change(within(dialog).getByLabelText(KB.fieldContent), { target: { value: 'Open the VPN app and choose Reset.' } });
    fireEvent.click(within(dialog).getByRole('button', { name: KB.saveArticle }));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith(TOASTS.articleSavedGap, 'success'));
    expect(bodyOf(calls('POST', '/api/knowledge/helpdesk/articles')[0])).toMatchObject({ gapGroupId: 'g-1', helpdesk: true });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await screen.findByText(GAPS.emptyHeading)).toBeInTheDocument();
    expect(calls('GET', LIST)).toHaveLength(2);
    expect(screen.getByRole('button', { name: fill(GAPS.tab, { n: 0 }) })).toBeInTheDocument();
  });
});

describe('the states', () => {
  it('shows three busy skeleton cards while the first read runs', async () => {
    const answer = deferred<Response>();
    serve({ [`GET ${LIST}`]: () => canSee(), [`GET ${COUNT}`]: () => jsonRes(view([])), [`GET ${FULL}`]: () => answer.promise });
    await renderKb();
    fireEvent.click(await screen.findByRole('button', { name: /^Knowledge gaps/ }));
    const busy = await screen.findByTestId('gaps-loading');
    expect(busy).toHaveAttribute('aria-busy', 'true');
    expect(busy.children).toHaveLength(3);
    answer.resolve(jsonRes(view([])));
    await waitFor(() => expect(screen.queryByTestId('gaps-loading')).toBeNull());
  });

  it('says there are no knowledge gaps when the desk is on and nothing is open', async () => {
    await openTab(view([]));
    expect(await screen.findByRole('heading', { name: GAPS.emptyHeading })).toBeInTheDocument();
    expect(screen.getByText(GAPS.emptyBody)).toBeInTheDocument();
  });

  it('says the service desk is off when it is, in place of the first empty card', async () => {
    await openTab(view([], { deskOff: true }));
    expect(await screen.findByRole('heading', { name: GAPS.emptyOffHeading })).toBeInTheDocument();
    expect(screen.getByText(GAPS.emptyOffBody)).toBeInTheDocument();
    expect(screen.queryByText(GAPS.emptyHeading)).toBeNull();
  });

  it('shows a red alert with Try again when the read fails, and reads again on Try again', async () => {
    let n = 0;
    serve({
      [`GET ${LIST}`]: () => canSee(), [`GET ${COUNT}`]: () => jsonRes(view([])),
      [`GET ${FULL}`]: () => (n++ === 0 ? jsonRes({ detail: 'x' }, 500) : jsonRes(view([group()]))),
    });
    await renderKb();
    fireEvent.click(await screen.findByRole('button', { name: /^Knowledge gaps/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent(GAPS.loadFailed);
    fireEvent.click(screen.getByRole('button', { name: GAPS.tryAgain }));
    expect(await screen.findByText('How do I reset my VPN?')).toBeInTheDocument();
  });
});
