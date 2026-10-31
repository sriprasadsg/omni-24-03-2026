/**
 * Phase 82 / HEAL-06, D-16, D-17, D-19, D-25, D-26: the tenant Retention Policy screen tells the truth about
 * the nightly count-only gate. authFetch is mocked; payloads follow GET /api/retention/policies (82-10).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));

vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { authFetch } from '../../services/apiService';
import { showToast } from '../../utils/toast';
import RetentionPolicyDashboard from '../../components/RetentionPolicyDashboard';

const mockAuthFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
const mockToast = showToast as unknown as ReturnType<typeof vi.fn>;
const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

const NOT_WAITING = { waiting: false, reason: null };

function policy(collection: string, days: number, over: Record<string, unknown> = {}) {
  return {
    collection, retention_days: days, description: `${collection} description`,
    gate: NOT_WAITING, editable: true, ...over,
  };
}

const AUDIT = policy('audit_logs', 365, { managedBy: 'audit_ledger', editable: false });

interface Opts {
  policies?: unknown[];
  save?: (collection: string, body: any) => Response;
  run?: () => Response;
}

function route(opts: Opts = {}) {
  const policies = opts.policies ?? [AUDIT, policy('metrics', 30), policy('notifications', 60)];
  mockAuthFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = url.split('?')[0];
    if (path === '/api/retention/policies' && !init?.method) return jsonRes({ policies });
    if (path === '/api/retention/stats') return jsonRes({ policies: policies.length, collections: [], last_cleanup: null });
    if (path === '/api/retention/run') return (opts.run ?? (() => jsonRes({ status: 'completed', ran_at: new Date().toISOString(), result: {} })))();
    if (path.startsWith('/api/retention/policies/')) {
      const collection = path.split('/').pop() as string;
      return (opts.save ?? (() => jsonRes({ updated: true, countOnlyUntilConfirmed: false })))(collection, JSON.parse(String(init?.body)));
    }
    throw new Error(`unexpected request ${url}`);
  });
}

const cardOf = (heading: string) =>
  screen.getByRole('heading', { level: 3, name: heading }).closest('div.rounded-xl') as HTMLElement;

async function loaded() {
  await screen.findByRole('heading', { level: 3, name: 'metrics' });
}

const D19 =
  'Saved. Because this shortens the period, the next cleanup run, nightly or manual, only counts what would be deleted. ' +
  'A platform administrator confirms before anything is removed.';
const WAITING =
  'Waiting for a platform administrator to confirm before old records are deleted. ' +
  'Until then, the nightly run and Run Cleanup Now only count them.';
const D25 = "Audit logs are kept by the audit ledger's own schedule, not by this cleanup.";
const D26 =
  "Run data retention cleanup now? This permanently deletes data older than each policy threshold, except data types still waiting for a platform administrator's confirmation, which are only counted. Audit logs are not affected.";

let confirmSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  mockAuthFetch.mockReset();
  mockToast.mockReset();
  confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
});
afterEach(() => { confirmSpy.mockRestore(); });

describe('audit_logs card (D-25)', () => {
  it('keeps its row, has no Edit button and states who keeps audit logs', async () => {
    route();
    render(<RetentionPolicyDashboard />);
    await loaded();
    const audit = cardOf('audit logs');
    expect(audit).toBeInTheDocument();
    expect(within(audit).queryByRole('button', { name: 'Edit' })).toBeNull();
    expect(within(audit).getByText(D25)).toBeInTheDocument();
  });

  it('the other cards keep Edit and do not show the note', async () => {
    route();
    render(<RetentionPolicyDashboard />);
    await loaded();
    expect(within(cardOf('metrics')).getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(within(cardOf('notifications')).getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(screen.getAllByText(D25).length).toBe(1);
  });

  it('a server that marks another card not editable also hides its Edit button', async () => {
    route({ policies: [policy('metrics', 30, { editable: false })] });
    render(<RetentionPolicyDashboard />);
    await loaded();
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
  });
});

describe('guidelines (D-17)', () => {
  it('shows the 02:00 UTC schedule, no 3:00 AM text, and keeps every other bullet', async () => {
    route();
    const { container } = render(<RetentionPolicyDashboard />);
    await loaded();
    expect(screen.getByText('Cleanup runs automatically every night at 02:00 UTC.')).toBeInTheDocument();
    expect(container.textContent).not.toContain('3:00 AM');
    expect(screen.getByText('Audit logs must be retained for at least 90 days per SOC 2 requirements')).toBeInTheDocument();
    expect(screen.getByText('Security events retention of 365+ days recommended for forensic investigations')).toBeInTheDocument();
    expect(screen.getByText('GDPR Article 5(1)(e) requires data not be kept longer than necessary')).toBeInTheDocument();
  });
});

describe('Run Cleanup Now confirmation (D-26)', () => {
  it('asks with the exact count-only wording', async () => {
    route();
    render(<RetentionPolicyDashboard />);
    await loaded();
    fireEvent.click(screen.getByRole('button', { name: /Run Cleanup Now/ }));
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(confirmSpy).toHaveBeenCalledWith(D26);
  });

  it('declining runs nothing', async () => {
    route();
    render(<RetentionPolicyDashboard />);
    await loaded();
    fireEvent.click(screen.getByRole('button', { name: /Run Cleanup Now/ }));
    expect(mockAuthFetch.mock.calls.some(c => String(c[0]) === '/api/retention/run')).toBe(false);
  });
});

describe('Run Cleanup Now outcomes (WR-05, T-82-55)', () => {
  const FALLBACK = "Couldn't run cleanup.";
  async function run() {
    confirmSpy.mockReturnValue(true);
    render(<RetentionPolicyDashboard />);
    await loaded();
    fireEvent.click(screen.getByRole('button', { name: /Run Cleanup Now/ }));
  }
  const unreadable = () => ({ ok: false, status: 502, json: () => Promise.reject(new SyntaxError('bad json')) }) as unknown as Response;
  const failures: Array<[string, () => Response, string]> = [
    ['a 409 busy lock', () => jsonRes({ detail: 'A retention run is in progress. Try again when it finishes.' }, 409), 'A retention run is in progress. Try again when it finishes.'],
    ['a 403 for a viewer', () => jsonRes({ detail: 'Admin role required' }, 403), 'Admin role required'],
    ['a 400 without a tenant', () => jsonRes({ detail: 'A tenant is required to run retention' }, 400), 'A tenant is required to run retention'],
    ['a 422 whose detail is a list', () => jsonRes({ detail: [{ msg: 'bad' }] }, 422), FALLBACK],
    ['a 502 with an unreadable body', unreadable, FALLBACK],
    ['a 200 with no readable ran_at', () => jsonRes({ status: 'completed', result: {} }), FALLBACK],
  ];

  it.each(failures)('%s shows an error toast and never the completed card', async (_name, answer, message) => {
    route({ run: answer });
    await run();
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith(message, 'error'));
    expect(screen.queryByText(/Cleanup completed/)).toBeNull();
    expect(screen.getByRole('button', { name: /Run Cleanup Now/ })).toBeEnabled();
  });

  it('a network error does not throw, shows the fallback toast and no card', async () => {
    route({ run: () => { throw new TypeError('Failed to fetch'); } });
    await run();
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith(FALLBACK, 'error'));
    expect(screen.queryByText(/Cleanup completed/)).toBeNull();
    expect(screen.getByRole('button', { name: /Run Cleanup Now/ })).toBeEnabled();
  });

  it('a successful run still shows the green Cleanup completed card with its tiles and no toast', async () => {
    route({ run: () => jsonRes({ status: 'completed', ran_at: '2026-10-31T01:00:00+00:00', result: { logs: 7 } }) });
    await run();
    expect(await screen.findByText(/Cleanup completed at/)).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(mockToast).not.toHaveBeenCalled();
  });
});

describe('shortened period (D-19)', () => {
  async function save(card: string, days: number) {
    fireEvent.click(within(cardOf(card)).getByRole('button', { name: 'Edit' }));
    fireEvent.change(within(cardOf(card)).getByRole('spinbutton'), { target: { value: String(days) } });
    fireEvent.click(within(cardOf(card)).getByRole('button', { name: 'Save' }));
  }

  it('saving a lower value that the server holds for confirmation shows the yellow block on that card only', async () => {
    route({ save: () => jsonRes({ updated: true, countOnlyUntilConfirmed: true }) });
    render(<RetentionPolicyDashboard />);
    await loaded();
    await save('metrics', 20);
    await waitFor(() => expect(within(cardOf('metrics')).getByText(D19)).toBeInTheDocument());
    expect(within(cardOf('notifications')).queryByText(D19)).toBeNull();
    const block = within(cardOf('metrics')).getByText(D19).closest('div') as HTMLElement;
    expect(block.className).toContain('bg-yellow-100');
  });

  it('saving a longer value shows no block, even if the server still counts only', async () => {
    route({ save: () => jsonRes({ updated: true, countOnlyUntilConfirmed: true }) });
    render(<RetentionPolicyDashboard />);
    await loaded();
    await save('metrics', 60);
    await waitFor(() => expect(mockAuthFetch.mock.calls.some(c => String(c[0]) === '/api/retention/policies/metrics')).toBe(true));
    await waitFor(() => expect(within(cardOf('metrics')).queryByRole('button', { name: 'Save' })).toBeNull());
    expect(screen.queryByText(D19)).toBeNull();
  });

  it('saving a lower value the server does not hold shows no block', async () => {
    route({ save: () => jsonRes({ updated: true, countOnlyUntilConfirmed: false }) });
    render(<RetentionPolicyDashboard />);
    await loaded();
    await save('metrics', 20);
    await waitFor(() => expect(within(cardOf('metrics')).queryByRole('button', { name: 'Save' })).toBeNull());
    expect(screen.queryByText(D19)).toBeNull();
  });

  it('a refused save (non-OK answer) shows no block', async () => {
    route({ save: () => jsonRes({ detail: 'Admin role required' }, 403) });
    render(<RetentionPolicyDashboard />);
    await loaded();
    await save('metrics', 20);
    await waitFor(() => expect(within(cardOf('metrics')).queryByRole('button', { name: 'Save' })).toBeNull());
    expect(screen.queryByText(D19)).toBeNull();
  });
});

describe('waiting state (D-19, T-82-45)', () => {
  it('a policy whose gate is waiting shows the waiting line, with no numbers; others do not', async () => {
    route({ policies: [
      AUDIT,
      policy('metrics', 30, { gate: { waiting: true, reason: 'shortened' } }),
      policy('notifications', 60),
    ] });
    render(<RetentionPolicyDashboard />);
    await loaded();
    const waiting = within(cardOf('metrics')).getByText(WAITING);
    expect(waiting.className).toContain('text-xs');
    expect(within(cardOf('notifications')).queryByText(WAITING)).toBeNull();
    expect(within(cardOf('audit logs')).queryByText(WAITING)).toBeNull();
    expect(screen.getAllByText(WAITING).length).toBe(1);
    expect(waiting.textContent).not.toMatch(/\d/);
  });

  it('nothing is shown when no policy is waiting', async () => {
    route();
    render(<RetentionPolicyDashboard />);
    await loaded();
    expect(screen.queryByText(WAITING)).toBeNull();
  });
});
