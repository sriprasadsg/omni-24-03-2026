/**
 * Platform health, Integrations card: configured integrations get a Test button and show the result built by the
 * server; unconfigured ones say which variable to set; nothing on the card is ever a key value.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));

import { PlatformIntegrationsCard } from '../../components/PlatformIntegrationsCard';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const items = [
  { name: 'virustotal', label: 'VirusTotal', use: 'File and hash scanning', envVars: ['VIRUSTOTAL_API_KEY'], configured: true, missing: [] },
  { name: 'stripe', label: 'Stripe', use: 'Payments', envVars: ['STRIPE_SECRET_KEY'], configured: false, missing: ['STRIPE_SECRET_KEY'] },
];

beforeEach(() => { authFetch.mockReset(); });

describe('Platform integrations card', () => {
  it('lists what is configured, tests one, and says what to set for the rest', async () => {
    authFetch.mockImplementation(async (url: string, init?: { method?: string }) =>
      ok(init?.method === 'POST' ? { ok: false, detail: 'HTTP 401: the key was refused' } : { items }));
    render(<PlatformIntegrationsCard />);
    expect(await screen.findByText(/1 of 2 configured/)).toBeTruthy();
    expect(screen.getByText(/Not configured: set STRIPE_SECRET_KEY/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Test Stripe' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Test VirusTotal' }));
    await waitFor(() => expect(screen.getByRole('status').textContent).toBe('Test failed: HTTP 401: the key was refused'));
    expect(authFetch).toHaveBeenCalledWith('/api/platform/autonomous-ops/health/integrations/virustotal/test', { method: 'POST' });
  });
});
