/**
 * Phase 82 / HEAL-06, D-18..D-20: the Scheduled data retention card of the Platform health section and its
 * Confirm deletion dialog (82-UI-SPEC sections 6 and 7). authFetch and the toast are mocked; the review
 * payload follows GET /api/platform/autonomous-ops/retention/review (82-10).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within, fireEvent, act } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { showToast } from '../../utils/toast';
import { AutonomousOpsRetentionReview } from '../../components/AutonomousOpsRetentionReview';
import { AutonomousOpsPlatformHealth } from '../../components/AutonomousOpsPlatformHealth';
import {
  mockAuthFetch, jsonRes, retentionReview, retentionItem, reviewCalls, confirmCalls, REVIEW_PATH,
  notInstalledDoc, minutesAgo, withUser, routeRetention, SUPER_PERMISSIONS,
} from './_platformHealthHarness';
import type { RetentionHandler } from './_platformHealthHarness';

const mockToast = showToast as unknown as ReturnType<typeof vi.fn>;

const SUPER = SUPER_PERMISSIONS;
const route = routeRetention;

const renderCard = (permissions: string[] = SUPER, props: { refreshSignal?: number } = {}) =>
  render(withUser(permissions, <AutonomousOpsRetentionReview {...props} />));

/** Wait for the first review to be on screen before acting on it. */
async function ready() {
  return screen.findByRole('table', { name: 'Retention counts waiting for confirmation' });
}

beforeEach(() => { mockAuthFetch.mockReset(); mockToast.mockReset(); });
afterEach(() => { vi.useRealTimers(); });

describe('Retention card (tracer)', () => {
  it('shows what is waiting: heading, totals, both rows and the Confirm deletion button', async () => {
    route();
    renderCard();

    const table = await ready();
    expect(screen.getByText('Scheduled data retention')).toBeInTheDocument();
    expect(screen.getByText('Waiting for your confirmation')).toBeInTheDocument();
    expect(screen.getByText('4 records across 2 organizations would be deleted.')).toBeInTheDocument();
    expect(within(table).getByText('Acme Corp')).toBeInTheDocument();
    expect(within(table).getByText('Agent metrics')).toBeInTheDocument();
    expect(within(table).getByText('Beta Ltd')).toBeInTheDocument();
    expect(within(table).getByText('Logs')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm deletion' })).toBeEnabled();
  });

  it('confirms once: focus lands on the review checkbox, the button waits for it, a double click sends one POST with the review token, then toast and refetch', async () => {
    let finish: (r: Response) => void = () => {};
    const confirm = vi.fn<RetentionHandler>(() => new Promise<Response>(resolve => { finish = resolve; }));
    route({ confirm });
    renderCard();
    await ready();
    expect(reviewCalls()).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'Confirm deletion' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: 'Confirm deletion of old records?' })).toBeInTheDocument();
    const checkbox = within(dialog).getByRole('checkbox', { name: 'I have reviewed the counts for every organization listed.' });
    await waitFor(() => expect(checkbox).toHaveFocus());

    const confirmButton = within(dialog).getByRole('button', { name: 'Confirm deletion' });
    expect(confirmButton).toBeDisabled();
    fireEvent.click(confirmButton);
    expect(confirm).not.toHaveBeenCalled();

    fireEvent.click(checkbox);
    expect(confirmButton).toBeEnabled();
    fireEvent.click(confirmButton);
    fireEvent.click(confirmButton);
    await waitFor(() => expect(confirmCalls()).toHaveLength(1));
    expect(JSON.parse(String(confirmCalls()[0][1].body))).toEqual({ reviewToken: 'abc' });

    finish(jsonRes({ confirmed: { rows: 2, records: 4, tenants: 2 } }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(mockToast).toHaveBeenCalledWith('Retention confirmed. Old records will be deleted from the next nightly run.', 'success');
    await waitFor(() => expect(reviewCalls()).toHaveLength(2));
    expect(confirmCalls()).toHaveLength(1);
  });
});

// ── Task 2: every state, the responsive table, paging ───────────────────────

const TABLE_NAME = 'Retention counts waiting for confirmation';
const offsetOf = (url: string) => Number(new URL(url, 'http://x').searchParams.get('offset'));
const confirmButton = () => screen.getByRole('button', { name: 'Confirm deletion' });

/** `n` rows named Org 01..Org n, largest count first the way the server sends them. */
function manyItems(n: number) {
  return Array.from({ length: n }, (_, i) => retentionItem({
    tenantId: `t${i + 1}`, tenantName: `Org ${String(i + 1).padStart(2, '0')}`, count: 100 - i,
  }));
}
const pageOf = (all: unknown[], offset: number) => all.slice(offset, offset + 25);

describe('Retention card: header and the states of the card body', () => {
  it('shows the mode, the next run in UTC with the local time in the title, the last run and the scope note', async () => {
    route();
    renderCard();
    await ready();

    expect(screen.getByText('Counting only')).toBeInTheDocument();
    expect(screen.getByText('Nothing is deleted yet. Counts are listed below for review.')).toBeInTheDocument();
    const next = screen.getByText('Oct 31, 2026, 02:00 UTC');
    expect(next.tagName).toBe('TIME');
    expect(next).toHaveAttribute('title', new Date('2026-10-31T02:00:00+00:00').toLocaleString());
    expect(screen.getByText('Runs organization by organization in small batches.')).toBeInTheDocument();
    expect(screen.getByText('10 hr ago')).toBeInTheDocument();
    expect(screen.getByText('Counted 4 records across 2 organizations. Deleted nothing.')).toBeInTheDocument();
    expect(screen.getByText('Audit logs, the audit ledger, decision records and compliance evidence are never deleted by this job.')).toBeInTheDocument();
  });

  it('a run that deleted records says so', async () => {
    route({ review: () => jsonRes(retentionReview({
      mode: 'deleting_nightly', items: [], totals: { records: 0, tenants: 0, rows: 0, uncountable: 0 },
      lastRun: { at: minutesAgo(30), trigger: 'scheduled', counted: 1200, deleted: 1200, tenants: 3, error: null, stoppedEarly: false },
    })) });
    renderCard();
    expect(await screen.findByText('Deleted 1,200 records across 3 organizations.')).toBeInTheDocument();
    expect(screen.getByText('Deleting nightly')).toBeInTheDocument();
    expect(screen.getByText("Records older than each organization's retention period are deleted every night.")).toBeInTheDocument();
  });

  it('before the first count: the blue block names the date, no table and no Confirm, Last run reads Never', async () => {
    route({ review: () => jsonRes(retentionReview({
      notCountedYet: true, items: [], lastRun: null, countedAt: null, total: 0,
      totals: { records: 0, tenants: 0, rows: 0, uncountable: 0 },
    })) });
    renderCard();
    expect(await screen.findByText('The first run only counts what would be deleted. It runs at 02:00 UTC on Oct 31, 2026, and you confirm the counts here before anything is removed.')).toBeInTheDocument();
    expect(screen.getByText('Counting only')).toBeInTheDocument();
    expect(screen.getByText('Never')).toBeInTheDocument();
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Confirm deletion' })).toBeNull();
  });

  it('nothing waiting: the muted line, no table and no Confirm', async () => {
    route({ review: () => jsonRes(retentionReview({
      mode: 'deleting_nightly', items: [], total: 0, totals: { records: 0, tenants: 0, rows: 0, uncountable: 0 },
    })) });
    renderCard();
    expect(await screen.findByText('Nothing is waiting for confirmation. If an organization shortens a retention period, its next run only counts until you confirm it again.')).toBeInTheDocument();
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Confirm deletion' })).toBeNull();
  });

  it('a run in progress: Running now, and Confirm deletion is disabled with the reason', async () => {
    route({ review: () => jsonRes(retentionReview({ mode: 'running' })) });
    renderCard();
    await ready();
    expect(screen.getByText('Running now')).toBeInTheDocument();
    expect(confirmButton()).toBeDisabled();
    expect(screen.getByText('A run is in progress. Confirm after it finishes.')).toBeInTheDocument();
  });

  it('a failed last run: a red alert with the error, the rest of the card unchanged', async () => {
    route({ review: () => jsonRes(retentionReview({
      lastRun: { at: minutesAgo(60), trigger: 'scheduled', counted: 0, deleted: 0, tenants: 0, error: 'Database timed out.', stoppedEarly: false },
    })) });
    renderCard();
    await ready();
    const alert = screen.getByRole('alert');
    expect(within(alert).getByText('Failed: Database timed out. It tries again at the next run.')).toBeInTheDocument();
    expect(confirmButton()).toBeEnabled();
  });

  it('without the platform permission the rows show and there is no Confirm deletion', async () => {
    route();
    renderCard(['view:autonomous_ops', 'control:autonomous_ops']);
    await ready();
    expect(screen.queryByRole('button', { name: 'Confirm deletion' })).toBeNull();
  });
});

describe('Retention card: loading and load failure', () => {
  it('first load: three h-16 cells and an h-40 table skeleton under aria-busy, then the content', async () => {
    let release: (r: Response) => void = () => {};
    route({ review: () => new Promise<Response>(resolve => { release = resolve; }) });
    const { container } = renderCard();
    const busy = container.querySelector('[aria-busy="true"]') as HTMLElement;
    expect(busy).not.toBeNull();
    expect(busy.querySelectorAll('.h-16.animate-pulse')).toHaveLength(3);
    expect(busy.querySelectorAll('.h-40.animate-pulse')).toHaveLength(1);

    await act(async () => { release(jsonRes(retentionReview())); });
    await ready();
    expect(container.querySelector('[aria-busy="true"]')).toBeNull();
    expect(container.querySelector('.animate-pulse')).toBeNull();
  });

  it('a first-load failure: a red alert with Reload retention review, which fetches again', async () => {
    let calls = 0;
    route({ review: () => { calls += 1; return calls === 1 ? jsonRes({ detail: 'down' }, 503) : jsonRes(retentionReview()); } });
    renderCard();
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText("Couldn't load the retention review. Check your connection and try again.")).toBeInTheDocument();
    expect(screen.getByText('Scheduled data retention')).toBeInTheDocument();
    fireEvent.click(within(alert).getByRole('button', { name: 'Reload retention review' }));
    await ready();
    expect(calls).toBe(2);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('the card renders on its own fetch when the health document failed and when the watchdog is not installed', async () => {
    mockAuthFetch.mockImplementation(async (url: string) => {
      const path = url.split('?')[0];
      if (path === REVIEW_PATH) return jsonRes(retentionReview());
      return jsonRes({ detail: 'down' }, 503);
    });
    const failed = render(withUser(SUPER, <AutonomousOpsPlatformHealth />));
    await ready();
    expect(screen.getByText("Couldn't load platform health. Check your connection and try again.")).toBeInTheDocument();
    failed.unmount();

    mockAuthFetch.mockImplementation(async (url: string) => (url.split('?')[0] === REVIEW_PATH
      ? jsonRes(retentionReview()) : jsonRes(notInstalledDoc())));
    render(withUser(SUPER, <AutonomousOpsPlatformHealth />));
    await screen.findByText('Not installed');
    await ready();
    const section = document.getElementById('platform-health') as HTMLElement;
    expect(section.lastElementChild).toContainElement(screen.getByText('Scheduled data retention'));
  });

  it('refetches when the page Refresh counter changes and every 30 s while visible', async () => {
    route();
    const view = renderCard(SUPER, { refreshSignal: 0 });
    await ready();
    expect(reviewCalls()).toHaveLength(1);

    view.rerender(withUser(SUPER, <AutonomousOpsRetentionReview refreshSignal={1} />));
    await waitFor(() => expect(reviewCalls()).toHaveLength(2));

    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    view.rerender(withUser(SUPER, <AutonomousOpsRetentionReview refreshSignal={1} key="again" />));
    await waitFor(() => expect(reviewCalls()).toHaveLength(3));
    await act(async () => { vi.advanceTimersByTime(30_000); });
    await waitFor(() => expect(reviewCalls()).toHaveLength(4));
  });
});

describe('Retention card: the review table', () => {
  it('is a real table at xl: sr-only caption, five scope=col headers, no truncation, rows in the server order', async () => {
    const items = [
      retentionItem({ tenantName: 'Zeta Corp', count: 50 }),
      retentionItem({ tenantId: 't2', tenantName: 'Alpha Ltd', count: 5 }),
      retentionItem({ tenantId: 't3', tenantName: 'Beta Ltd', count: 5 }),
    ];
    route({ review: () => jsonRes(retentionReview({ items, totals: { records: 60, tenants: 3, rows: 3, uncountable: 0 } })) });
    const { container } = renderCard();
    const table = await ready();

    expect(table.className).toContain('hidden');
    expect(table.className).toContain('xl:table');
    const headers = within(table).getAllByRole('columnheader');
    expect(headers.map(h => h.textContent)).toEqual(['Organization', 'Data type', 'Keeps', 'Would be deleted', 'Why it waits']);
    headers.forEach(h => expect(h).toHaveAttribute('scope', 'col'));
    const names = within(table).getAllByRole('row').slice(1).map(r => within(r).getAllByRole('cell')[0].textContent);
    expect(names).toEqual(['Zeta Corp', 'Alpha Ltd', 'Beta Ltd']);
    expect(within(table).getAllByText('Waiting for confirmation')).toHaveLength(3);
    expect(container.innerHTML).not.toContain('truncate');
  });

  it('below xl the rows are stacked cards with the Data type, Keeps, Would be deleted and Why labels, and break-words names', async () => {
    route();
    renderCard();
    await ready();
    const cards = screen.getByRole('list', { name: 'Retention rows waiting for confirmation, card view' });
    expect(cards.className).toContain('xl:hidden');
    const first = within(cards).getAllByRole('listitem')[0];
    ['Data type', 'Keeps', 'Would be deleted', 'Why'].forEach(label => expect(within(first).getByText(label)).toBeInTheDocument());
    expect(within(first).getByText('Acme Corp').className).toContain('break-words');
    expect(within(first).getByText('3 records')).toBeInTheDocument();
    expect(within(first).getByText('First run')).toBeInTheDocument();
  });

  it('a shortened period shows the new and the old days and why it waits; a first-run row says First run', async () => {
    const items = [
      retentionItem({ tenantName: 'Zeta Corp', days: 20, previousDays: 30, reason: 'shortened', count: 9 }),
      retentionItem({ tenantId: 't2', tenantName: 'Beta Ltd', type: 'logs', label: 'Logs', collection: 'logs', days: 90, count: 1 }),
    ];
    route({ review: () => jsonRes(retentionReview({ items, totals: { records: 10, tenants: 2, rows: 2, uncountable: 0 } })) });
    renderCard();
    const table = await ready();
    expect(within(table).getByText('20 days')).toBeInTheDocument();
    expect(within(table).getByText('was 30 days')).toBeInTheDocument();
    expect(within(table).getByText('Retention period shortened from 30 to 20 days')).toBeInTheDocument();
    expect(within(table).getByText('90 days')).toBeInTheDocument();
    expect(within(table).getByText('First run')).toBeInTheDocument();
    expect(within(table).getByText('agent_metrics')).toBeInTheDocument();
  });

  it('a row that could not be counted says so in red, stays listed and is left out of the totals', async () => {
    const items = [
      retentionItem({ tenantName: 'Zeta Corp', count: 3 }),
      retentionItem({ tenantId: 't2', tenantName: 'Beta Ltd', type: 'logs', label: 'Logs', collection: 'logs', count: null, countError: 'timeout' }),
    ];
    route({ review: () => jsonRes(retentionReview({ items, totals: { records: 3, tenants: 1, rows: 2, uncountable: 1 } })) });
    renderCard();
    const table = await ready();
    const bad = within(table).getByText("Couldn't count");
    expect(bad.className).toContain('text-red');
    expect(within(table).getByText('Beta Ltd')).toBeInTheDocument();
    expect(screen.getByText('3 records across 1 organization would be deleted.')).toBeInTheDocument();
    expect(confirmButton()).toBeEnabled();
  });

  it('with only uncountable rows Confirm deletion is disabled', async () => {
    const items = [retentionItem({ count: null, countError: 'timeout' })];
    route({ review: () => jsonRes(retentionReview({ items, totals: { records: 0, tenants: 0, rows: 1, uncountable: 1 } })) });
    renderCard();
    await ready();
    expect(screen.getByText('0 records across 0 organizations would be deleted.')).toBeInTheDocument();
    expect(confirmButton()).toBeDisabled();
  });

  it('one row reads in the singular: 1 record, 1 organization, Showing 1 row', async () => {
    const items = [retentionItem({ count: 1 })];
    route({ review: () => jsonRes(retentionReview({ items, totals: { records: 1, tenants: 1, rows: 1, uncountable: 0 } })) });
    renderCard();
    await ready();
    expect(screen.getByText('1 record across 1 organization would be deleted.')).toBeInTheDocument();
    expect(screen.getByText('Showing 1 row')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Load more rows' })).toBeNull();
  });

  it('counts are formatted with thousands separators', async () => {
    const items = [retentionItem({ count: 1234567 })];
    route({ review: () => jsonRes(retentionReview({ items, totals: { records: 1234567, tenants: 1, rows: 1, uncountable: 0 } })) });
    renderCard();
    const table = await ready();
    expect(within(table).getByText('1,234,567 records')).toBeInTheDocument();
    expect(screen.getByText('1,234,567 records across 1 organization would be deleted.')).toBeInTheDocument();
  });
});

describe('Retention card: paging', () => {
  const all = manyItems(30);
  const totals = { records: 3000, tenants: 30, rows: 30, uncountable: 0 };
  const serve = (over: (offset: number) => Response | Promise<Response> | null = () => null) => route({
    review: url => over(offsetOf(url)) ?? jsonRes(retentionReview({
      items: pageOf(all, offsetOf(url)), total: 30, totals, nextOffset: offsetOf(url) + 25 < 30 ? offsetOf(url) + 25 : null,
    })),
  });

  it('25 rows first, Showing 25 of 30 rows, and Load more rows fetches offset 25 and shows Loading... meanwhile', async () => {
    let release: (r: Response) => void = () => {};
    serve(offset => (offset === 25 ? new Promise<Response>(resolve => { release = resolve; }) : null));
    renderCard();
    const table = await ready();
    expect(within(table).getAllByRole('row')).toHaveLength(26);
    expect(screen.getByText('Showing 25 of 30 rows')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Load more rows' }));
    const loading = await screen.findByRole('button', { name: 'Loading...' });
    expect(loading).toBeDisabled();
    expect(reviewCalls().map(c => offsetOf(c[0] as string))).toEqual([0, 25]);

    await act(async () => { release(jsonRes(retentionReview({ items: pageOf(all, 25), total: 30, totals, nextOffset: null }))); });
    await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(31));
    expect(screen.getByText('Showing 30 of 30 rows')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Load more rows|Loading/ })).toBeNull();
    expect(screen.getByText('3,000 records across 30 organizations would be deleted.')).toBeInTheDocument();
  });

  it('a failed page keeps the loaded rows, says Couldn\'t load more rows. and Load more rows retries', async () => {
    let failures = 1;
    serve(offset => (offset === 25 && failures-- > 0 ? jsonRes({ detail: 'down' }, 503) : null));
    renderCard();
    const table = await ready();

    fireEvent.click(screen.getByRole('button', { name: 'Load more rows' }));
    expect(await screen.findByText("Couldn't load more rows.")).toBeInTheDocument();
    expect(within(table).getAllByRole('row')).toHaveLength(26);

    fireEvent.click(screen.getByRole('button', { name: 'Load more rows' }));
    await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(31));
    expect(screen.queryByText("Couldn't load more rows.")).toBeNull();
  });

  it('a background refresh with the same token keeps the rows already loaded', async () => {
    serve();
    const view = renderCard();
    const table = await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Load more rows' }));
    await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(31));

    view.rerender(withUser(SUPER, <AutonomousOpsRetentionReview refreshSignal={1} />));
    await waitFor(() => expect(reviewCalls()).toHaveLength(3));
    expect(within(table).getAllByRole('row')).toHaveLength(31);
  });

  it('Confirm deletion waits for the last page: disabled on page 1 with the Load all line, enabled once every row is loaded, disabled again after a recount', async () => {
    let token = 'one';
    route({ review: url => jsonRes(retentionReview({
      items: pageOf(all, offsetOf(url)), total: 30, totals, reviewToken: token, nextOffset: offsetOf(url) + 25 < 30 ? offsetOf(url) + 25 : null,
    })) });
    const view = renderCard();
    const table = await ready();
    expect(confirmButton()).toBeDisabled();
    expect(screen.getByText('Load all 30 rows before confirming.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Load more rows' }));
    await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(31));
    expect(confirmButton()).toBeEnabled();
    expect(screen.queryByText(/Load all 30 rows/)).toBeNull();

    token = 'two'; // a recount: the new token takes the fresh first page
    view.rerender(withUser(SUPER, <AutonomousOpsRetentionReview refreshSignal={1} />));
    await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(26));
    expect(confirmButton()).toBeDisabled();
    expect(screen.getByText('Load all 30 rows before confirming.')).toBeInTheDocument();
  });
});

// ── 82-17: the helper line and the incomplete notice ──
const NEXT_RUN = 'You can confirm after the next run.';
const unloaded = { total: 1234, nextOffset: 25 };
const noCountable = { totals: { records: 0, tenants: 0, rows: 1, uncountable: 1 } };
const INCOMPLETE_HELPER = 'Confirm after the next run has counted every organization.';
const NO_COUNTABLE = 'No row could be counted, so there is nothing to confirm yet.';
const RUN_LINE = 'A run is in progress. Confirm after it finishes.';
describe('Retention card: helper line precedence', () => {
  const gap = { reason: 'tenant_failed', tenants: 1 };
  it.each([
    ['run in progress beats everything', { mode: 'running', incomplete: gap, ...noCountable, ...unloaded }, RUN_LINE],
    ['incomplete beats no countable rows and unloaded rows', { incomplete: gap, ...noCountable, ...unloaded }, INCOMPLETE_HELPER],
    ['no countable rows beats unloaded rows', { ...noCountable, ...unloaded }, NO_COUNTABLE],
    ['unloaded rows alone read with a thousands separator', { ...unloaded }, 'Load all 1,234 rows before confirming.'],
    ['none of these reads the default line', {}, "One confirmation covers every row listed. Deleted records can't be restored."],
  ])('%s', async (_name, over, line) => {
    route({ review: () => jsonRes(retentionReview(over)) });
    renderCard();
    await ready();
    expect(screen.getByText(line)).toBeInTheDocument();
    const others = [RUN_LINE, INCOMPLETE_HELPER, NO_COUNTABLE, /^Load all /].filter(o => (o instanceof RegExp ? !line.startsWith('Load all') : o !== line));
    others.forEach(o => expect(screen.queryByText(o)).toBeNull());
    if (line.startsWith('One confirmation')) expect(confirmButton()).toBeEnabled(); else expect(confirmButton()).toBeDisabled();
  });
});

describe('Retention card: the review is incomplete', () => {
  it.each([
    [{ reason: 'stopped_early', tenants: 3 }, `The last run stopped early, so 3 organizations weren't counted. ${NEXT_RUN}`],
    [{ reason: 'stopped_early', tenants: 1 }, `The last run stopped early, so 1 organization wasn't counted. ${NEXT_RUN}`],
    [{ reason: 'stopped_early', tenants: 0 }, `The last run stopped early. ${NEXT_RUN}`],
    [{ reason: 'tenant_failed', tenants: 2 }, `The last run failed for 2 organizations. ${NEXT_RUN}`],
    [{ reason: 'tenant_failed', tenants: 1 }, `The last run failed for 1 organization. ${NEXT_RUN}`],
    [{ reason: 'not_reached', tenants: 4 }, `4 organizations haven't been counted yet. ${NEXT_RUN}`],
    [{ reason: 'not_reached', tenants: 1 }, `1 organization hasn't been counted yet. ${NEXT_RUN}`],
    [{ reason: 'something_new', tenants: 2 }, `Not every organization has been counted yet. ${NEXT_RUN}`],
  ])('%j reads as an amber status notice and disables Confirm deletion', async (incomplete, copy) => {
    route({ review: () => jsonRes(retentionReview({ incomplete })) });
    renderCard();
    await ready();
    const notice = screen.getByRole('status');
    expect(within(notice).getByText(copy)).toBeInTheDocument();
    expect(notice.className).toContain('amber');
    expect(confirmButton()).toBeDisabled();
    expect(screen.getByText(INCOMPLETE_HELPER)).toBeInTheDocument();
  });

  it('incomplete null, and a response with no incomplete key, show no notice and leave the button enabled', async () => {
    route({ review: () => jsonRes(retentionReview({ incomplete: null })) });
    const first = renderCard();
    await ready();
    expect(screen.queryByRole('status')).toBeNull();
    expect(confirmButton()).toBeEnabled();
    first.unmount();
    route({ review: () => jsonRes(Object.fromEntries(Object.entries(retentionReview()).filter(([k]) => k !== 'incomplete'))) });
    renderCard();
    await ready();
    expect(screen.queryByRole('status')).toBeNull();
    expect(confirmButton()).toBeEnabled();
  });

  it('with no rows listed there is no notice: the blue block and the muted line stand alone', async () => {
    const empty = { items: [], total: 0, totals: { records: 0, tenants: 0, rows: 0, uncountable: 0 }, incomplete: { reason: 'not_reached', tenants: 2 } };
    route({ review: () => jsonRes(retentionReview({ ...empty, notCountedYet: true })) });
    const first = renderCard();
    expect(await screen.findByText(/^The first run only counts what would be deleted\./)).toBeInTheDocument();
    expect(screen.queryByText(/haven't been counted yet/)).toBeNull();
    first.unmount();

    route({ review: () => jsonRes(retentionReview(empty)) });
    renderCard();
    expect(await screen.findByText(/^Nothing is waiting for confirmation\./)).toBeInTheDocument();
    expect(screen.queryByText(/haven't been counted yet/)).toBeNull();
  });
});
