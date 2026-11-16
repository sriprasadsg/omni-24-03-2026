/**
 * Framework Evaluator: a framework with no evidence reads "Not assessed", and every score says how much it covers.
 *  1. A framework card with nothing assessed shows "Not assessed" instead of a 0% ring.
 *  2. Every card shows "N of M assessed".
 *  3. A control without evidence carries the "Not assessed" badge, and the detail offers a Not assessed filter.
 *  4. A server without the counts (before 2026-11-16) still renders the old way.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

const authFetch = vi.fn();

vi.mock('../../services/apiService', () => ({
  authFetch: (...args: unknown[]) => authFetch(...args),
}));
vi.mock('../../contexts/UserContext', () => ({
  useUser: () => ({ currentUser: { role: 'Tenant Admin', name: 'Test User' } }),
}));

import { ComplianceFrameworksDashboard } from '../../components/ComplianceFrameworksDashboard';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });

const SUMMARY = {
  soc1_type2: { name: 'SOC 1 Type II', score: 0, passed: 0, partial: 0, failed: 0, not_applicable: 0,
                not_assessed: 2, assessed: 0, total: 2 },
  soc2: { name: 'SOC 2', score: 50, passed: 1, partial: 0, failed: 1, not_applicable: 0,
          not_assessed: 0, assessed: 2, total: 2 },
};
const DETAIL = {
  framework_id: 'soc1_type2', framework_name: 'SOC 1 Type II', version: '2', score: 0, passed: 0, partial: 0,
  failed: 0, not_applicable: 0, not_assessed: 2, assessed: 0, total: 2, evaluated_at: new Date().toISOString(),
  controls: [
    { id: 'CC1.1', title: 'Control environment', description: '', status: 'not_assessed', evidence: '',
      evaluated_at: '', theme: 'Control Environment' },
    { id: 'CC1.2', title: 'Board oversight', description: '', status: 'not_assessed', evidence: '',
      evaluated_at: '', theme: 'Control Environment' },
  ],
};

function serve(summary: unknown, detail: unknown) {
  authFetch.mockImplementation(async (url: string) => (url.endsWith('/summary') ? ok(summary) : ok(detail)));
}

describe('ComplianceFrameworksDashboard coverage', () => {
  beforeEach(() => { authFetch.mockReset(); });

  it('shows Not assessed instead of a 0% ring for a framework with no evidence', async () => {
    serve(SUMMARY, DETAIL);
    render(<ComplianceFrameworksDashboard />);
    expect((await screen.findAllByText('Not assessed')).length).toBeGreaterThan(0);
    expect(screen.queryByText('0%')).toBeNull();
    expect(screen.getByText('50%')).toBeTruthy();
  });

  it('says how many controls each framework score covers', async () => {
    serve(SUMMARY, DETAIL);
    render(<ComplianceFrameworksDashboard />);
    expect(await screen.findByText('0 of 2 assessed')).toBeTruthy();
    expect(screen.getByText('2 of 2 assessed')).toBeTruthy();
  });

  it('badges controls without evidence and offers a Not assessed filter', async () => {
    serve(SUMMARY, DETAIL);
    render(<ComplianceFrameworksDashboard />);
    const filter = await screen.findByRole('button', { name: 'Not assessed (2)' });
    fireEvent.click(screen.getByText('Control Environment'));
    expect(screen.getByText('Control environment')).toBeTruthy();
    fireEvent.click(filter);
    expect(screen.getByText('Board oversight')).toBeTruthy();
  });

  it('renders a server without the counts the old way', async () => {
    const strip = ({ not_assessed: _n, assessed: _a, ...rest }: Record<string, unknown>) => rest;
    serve({ soc2: strip(SUMMARY.soc2) }, { ...strip(DETAIL), framework_id: 'soc2', controls: [] });
    render(<ComplianceFrameworksDashboard />);
    expect(await screen.findByText('50%')).toBeTruthy();
    expect(screen.queryByText(/ assessed$/)).toBeNull();
    expect(screen.queryByRole('button', { name: /Not assessed/ })).toBeNull();
  });
});
