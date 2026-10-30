/**
 * Phase 82 / HEAL-06, D-18..D-20: the Scheduled data retention card of the Platform health section and its
 * Confirm deletion dialog (82-UI-SPEC sections 6 and 7). authFetch and the toast are mocked; the review
 * payload follows GET /api/platform/autonomous-ops/retention/review (82-10).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { UserContext } from '../../contexts/UserContext';
import { showToast } from '../../utils/toast';
import { AutonomousOpsRetentionReview } from '../../components/AutonomousOpsRetentionReview';
import {
  mockAuthFetch, jsonRes, retentionReview, reviewCalls, confirmCalls, REVIEW_PATH, CONFIRM_PATH,
} from './_platformHealthHarness';

const mockToast = showToast as unknown as ReturnType<typeof vi.fn>;

const PLATFORM_CONTROL = 'control:platform_autonomous_ops';
const SUPER = ['view:autonomous_ops', 'control:autonomous_ops', 'manage:autonomous_ops', PLATFORM_CONTROL];

function withUser(permissions: string[], ui: React.ReactElement) {
  return (
    <UserContext.Provider value={{
      currentUser: { id: 'u1', name: 'Pat', email: 'pat@example.com', role: 'Super Admin', tenantId: 'tenant-a', permissions } as any,
      login: async () => false, logout: () => {}, signup: async () => false, registerTenant: async () => false,
      hasPermission: (p: any) => permissions.includes(p), enabledFeatures: [], serverLockedFeatures: {},
    }}>
      {ui}
    </UserContext.Provider>
  );
}

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;

/** Route authFetch by path; an unknown path fails loudly so a stray request shows up in the test. */
function route(opts: { review?: Handler; confirm?: Handler } = {}) {
  mockAuthFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = url.split('?')[0];
    if (path === REVIEW_PATH) return (opts.review ?? (() => jsonRes(retentionReview())))(url, init);
    if (path === CONFIRM_PATH) return (opts.confirm ?? (() => jsonRes({ confirmed: { rows: 2, records: 4, tenants: 2 } })))(url, init);
    throw new Error(`unexpected request ${url}`);
  });
}

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
    const confirm = vi.fn<Handler>(() => new Promise<Response>(resolve => { finish = resolve; }));
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
