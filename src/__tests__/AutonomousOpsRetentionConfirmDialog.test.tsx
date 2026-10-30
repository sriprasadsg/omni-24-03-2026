/**
 * Phase 82 / HEAL-06, T-82-42, T-82-43: the Confirm deletion dialog of the retention card (82-UI-SPEC section 7):
 * pending, stale counts (409), not allowed (403), failures, uncountable rows and the keyboard and backdrop rules.
 * authFetch and the toast are mocked; nothing here reaches a real API or database.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within, fireEvent, act } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { showToast } from '../../utils/toast';
import { AutonomousOpsRetentionReview } from '../../components/AutonomousOpsRetentionReview';
import {
  mockAuthFetch, jsonRes, retentionReview, reviewCalls, confirmCalls, withUser, routeRetention, SUPER_PERMISSIONS,
  AT_1402, clock,
} from './_platformHealthHarness';
import type { RetentionHandler } from './_platformHealthHarness';

const mockToast = showToast as unknown as ReturnType<typeof vi.fn>;
const OK = () => jsonRes({ confirmed: { rows: 2, records: 4, tenants: 2 } });

beforeEach(() => { mockAuthFetch.mockReset(); mockToast.mockReset(); });

/** Show the card, wait for the rows, open the dialog and wait for focus to land on the review checkbox. */
async function openDialog(opts: { review?: RetentionHandler; confirm?: RetentionHandler } = {}) {
  routeRetention(opts);
  const view = render(withUser(SUPER_PERMISSIONS, <AutonomousOpsRetentionReview />));
  await screen.findByRole('table', { name: 'Retention counts waiting for confirmation' });
  fireEvent.click(screen.getByRole('button', { name: 'Confirm deletion' }));
  const dialog = await screen.findByRole('dialog');
  const checkbox = within(dialog).getByRole('checkbox', { name: 'I have reviewed the counts for every organization listed.' });
  await waitFor(() => expect(checkbox).toHaveFocus());
  return { view, dialog, checkbox };
}
const confirmIn = (dialog: HTMLElement) => within(dialog).getByRole('button', { name: /^(Confirm deletion|Confirming\.\.\.)$/ });

describe('Confirm deletion dialog: content', () => {
  it('shows the body, the summary with the count time, the safeguard line and Keep waiting', async () => {
    const { dialog } = await openDialog({ review: () => jsonRes(retentionReview({ countedAt: AT_1402 })) });
    expect(within(dialog).getByText("From the next nightly run at 02:00 UTC, records older than each organization's retention period will be deleted. Deleted records can't be restored.")).toBeInTheDocument();
    expect(within(dialog).getByText(`4 records across 2 organizations, counted ${clock(AT_1402)}.`)).toBeInTheDocument();
    expect(within(dialog).getByText('Audit logs, the audit ledger, decision records and compliance evidence are never deleted.')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Keep waiting' })).toBeEnabled();
    expect(within(dialog).queryByRole('button', { name: 'Close dialog' })).toBeNull();
  });

  it('with uncountable rows the summary adds how many stay waiting', async () => {
    const { dialog } = await openDialog({ review: () => jsonRes(retentionReview({
      totals: { records: 4, tenants: 2, rows: 4, uncountable: 2 },
    })) });
    expect(within(dialog).getByText('2 rows could not be counted and stay waiting.')).toBeInTheDocument();
  });

  it('with one uncountable row the line reads in the singular', async () => {
    const { dialog } = await openDialog({ review: () => jsonRes(retentionReview({
      totals: { records: 4, tenants: 2, rows: 3, uncountable: 1 },
    })) });
    expect(within(dialog).getByText('1 row could not be counted and stays waiting.')).toBeInTheDocument();
  });

  it('without uncountable rows there is no such line', async () => {
    const { dialog } = await openDialog();
    expect(within(dialog).queryByText(/could not be counted/)).toBeNull();
  });
});

describe('Confirm deletion dialog: pending, closing and keyboard', () => {
  it('while confirming the button reads Confirming... and is disabled, Keep waiting stays enabled, one click sends one request', async () => {
    const confirm = vi.fn<RetentionHandler>(() => new Promise<Response>(() => {}));
    const { dialog, checkbox } = await openDialog({ confirm });
    fireEvent.click(checkbox);
    fireEvent.click(confirmIn(dialog));
    await waitFor(() => expect(confirmIn(dialog)).toHaveTextContent('Confirming...'));
    expect(confirmIn(dialog)).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Keep waiting' })).toBeEnabled();
    fireEvent.click(confirmIn(dialog));
    expect(confirmCalls()).toHaveLength(1);
  });

  it('Keep waiting closes the dialog and deletes nothing; reopening starts with the box unchecked', async () => {
    const { dialog, checkbox } = await openDialog();
    fireEvent.click(checkbox);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Keep waiting' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(confirmCalls()).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: 'Confirm deletion' }));
    const again = await screen.findByRole('dialog');
    expect(within(again).getByRole('checkbox')).not.toBeChecked();
    expect(confirmIn(again)).toBeDisabled();
  });

  it('Esc closes; a click on the backdrop does not; Enter and Ctrl+Enter submit nothing', async () => {
    const { dialog, checkbox } = await openDialog();
    fireEvent.click(checkbox);
    fireEvent.keyDown(checkbox, { key: 'Enter' });
    fireEvent.keyDown(dialog, { key: 'Enter' });
    fireEvent.keyDown(dialog, { key: 'Enter', ctrlKey: true });
    fireEvent.keyDown(dialog, { key: 'Enter', metaKey: true });
    fireEvent.mouseDown(dialog);
    fireEvent.click(dialog);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(confirmCalls()).toHaveLength(0);

    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(confirmCalls()).toHaveLength(0);
  });

  it('confirms the counts that were on screen when the dialog opened, not a later refresh', async () => {
    let token = 'abc';
    const { view, dialog, checkbox } = await openDialog({ review: () => jsonRes(retentionReview({ reviewToken: token })) });
    token = 'def';
    view.rerender(withUser(SUPER_PERMISSIONS, <AutonomousOpsRetentionReview refreshSignal={1} />));
    await waitFor(() => expect(reviewCalls()).toHaveLength(2));
    fireEvent.click(checkbox);
    fireEvent.click(confirmIn(dialog));
    await waitFor(() => expect(confirmCalls()).toHaveLength(1));
    expect(JSON.parse(String(confirmCalls()[0][1].body))).toEqual({ reviewToken: 'abc' });
  });
});

describe('Confirm deletion dialog: errors', () => {
  it('409: the stale-counts alert, the checkbox resets, and Reload review replaces the confirm button for good', async () => {
    const { dialog, checkbox } = await openDialog({ confirm: () => jsonRes({ detail: 'The counts changed.' }, 409) });
    fireEvent.click(checkbox);
    fireEvent.click(confirmIn(dialog));

    const alert = await within(dialog).findByRole('alert');
    expect(within(alert).getByText('The counts changed since you opened this review. Reload the review and check the new counts before confirming.')).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: /Confirm deletion|Confirming/ })).toBeNull();
    expect(within(dialog).getByRole('checkbox')).not.toBeChecked();
    expect(confirmCalls()).toHaveLength(1);

    const reviews = reviewCalls().length;
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reload review' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await waitFor(() => expect(reviewCalls().length).toBe(reviews + 1));
    expect(confirmCalls()).toHaveLength(1);
  });

  it('403: the dialog closes, the error toast says who can confirm, and the review is fetched again', async () => {
    const { dialog, checkbox } = await openDialog({ confirm: () => jsonRes({ detail: 'Forbidden' }, 403) });
    fireEvent.click(checkbox);
    fireEvent.click(confirmIn(dialog));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(mockToast).toHaveBeenCalledWith('Only a platform administrator can confirm deletion.', 'error');
    await waitFor(() => expect(reviewCalls()).toHaveLength(2));
  });

  it('another failure with a server message: the dialog stays open with the message, and a retry can succeed', async () => {
    let calls = 0;
    const { dialog, checkbox } = await openDialog({
      confirm: () => { calls += 1; return calls === 1 ? jsonRes({ detail: 'The database is busy.' }, 500) : OK(); },
    });
    fireEvent.click(checkbox);
    fireEvent.click(confirmIn(dialog));
    const alert = await within(dialog).findByRole('alert');
    expect(within(alert).getByText("Couldn't confirm deletion: The database is busy. Try again.")).toBeInTheDocument();
    expect(alert.className).toContain('break-words');
    expect(confirmIn(dialog)).toBeEnabled();

    fireEvent.click(confirmIn(dialog));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(confirmCalls()).toHaveLength(2);
    expect(mockToast).toHaveBeenCalledWith('Retention confirmed. Old records will be deleted from the next nightly run.', 'success');
  });

  it('a failure without a server message uses the fallback copy', async () => {
    const { dialog, checkbox } = await openDialog({ confirm: () => jsonRes({}, 502) });
    fireEvent.click(checkbox);
    fireEvent.click(confirmIn(dialog));
    expect(await within(dialog).findByText("Couldn't confirm deletion. Check your connection and try again.")).toBeInTheDocument();
  });

  it('a network error uses the fallback copy too', async () => {
    const { dialog, checkbox } = await openDialog({ confirm: () => { throw new TypeError('Failed to fetch'); } });
    fireEvent.click(checkbox);
    await act(async () => { fireEvent.click(confirmIn(dialog)); });
    expect(await within(dialog).findByText("Couldn't confirm deletion. Check your connection and try again.")).toBeInTheDocument();
  });
});
