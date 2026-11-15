/**
 * AI Anomaly screen, 88.1 stage 1 (R4): its network tiles read a fake NDR route that no longer exists, so they
 * are gone. The screen must not ask for NDR data or claim network monitoring.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

const authFetch = vi.fn();

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: (...args: unknown[]) => authFetch(...args),
}));

import { AIAnomalyDashboard } from '../../components/AIAnomalyDashboard';

describe('AIAnomalyDashboard', () => {
  beforeEach(() => authFetch.mockReset());

  it('shows UEBA scores and makes no NDR request or network claim', async () => {
    authFetch.mockResolvedValue({ ok: true, json: async () => ({ results: [
      { userId: 'u1', userName: 'Asha Rao', userEmail: 'asha@example.com', score: 60, ruleScore: 40, mlScore: 70,
        reasons: [], lastCalculated: '2026-11-14T12:00:00Z' },
    ] }) });
    render(<AIAnomalyDashboard />);

    expect(await screen.findByText('Asha Rao')).toBeTruthy();
    expect(authFetch.mock.calls.map(call => call[0])).toEqual(['/api/ueba/risk-scores']);
    expect(screen.queryByText(/Network Anomalies/i)).toBeNull();
    expect(screen.queryByText(/Critical Network/i)).toBeNull();
    expect(screen.queryByText(/NDR/)).toBeNull();
  });
});
