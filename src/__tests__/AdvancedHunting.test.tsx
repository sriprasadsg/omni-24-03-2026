/**
 * Advanced Hunting: the KQL editor shows the server's columns, every row, and the server's reason for a bad query.
 *
 * Value: protects=a refused query says why instead of showing nothing, every returned column is shown in the
 * server's order, and a capped result says so; fails_when=a 400 is shown as an empty result, columns are cut to six
 * or taken from the first row only, or the row-limit note is missing; no_claim=the query engine
 * (backend/tests/test_kql_hunt.py).
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AdvancedHuntingDashboard from '../../components/AdvancedHuntingDashboard';

const res = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

function runQuery(text: string) {
  fireEvent.change(screen.getByRole('textbox'), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: /Run Hunt/ }));
}

afterEach(() => { vi.unstubAllGlobals(); });

describe('AdvancedHuntingDashboard', () => {
  it('shows every server column in order, all rows and the row-limit note', async () => {
    const columns = ['Account', 'Computer', 'Failures', 'SourceIP', 'LogonType', 'EventID', 'Message'];
    const row = Object.fromEntries(columns.map(c => [c, `${c}-v`]));
    vi.stubGlobal('fetch', vi.fn(async () => res({ results: [row, { ...row, Account: 'bob' }], columns,
      total: 2, truncated: true, elapsed_ms: 12 })));
    render(<AdvancedHuntingDashboard />);
    runQuery('SecurityEvent | take 2');
    expect(await screen.findByText('2 results')).toBeTruthy();
    expect(screen.getAllByRole('columnheader').map(h => h.textContent)).toEqual(columns);
    expect(screen.getByText('bob')).toBeTruthy();
    expect(screen.getByText(/Row limit reached/)).toBeTruthy();
  });

  it('shows the reason when the server refuses a query', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => res({ detail: 'Unknown column password; columns here: Account' }, 400)));
    render(<AdvancedHuntingDashboard />);
    runQuery("SecurityEvent | where password == 'x'");
    expect(await screen.findByText('Unknown column password; columns here: Account')).toBeTruthy();
    expect(screen.queryByRole('table')).toBeNull();
  });
});
