/**
 * Platform health, Certificate change card: says which step the change is at and how many active agents are
 * ready, and lists the others with what each still needs.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));

import { PlatformCertificateChangeCard } from '../../components/PlatformCertificateChangeCard';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const served = { fingerprint: 'ab'.repeat(32), subject: 'CN=135.237.98.107', notAfter: '2029-11-09T14:26:58+00:00' };

beforeEach(() => { authFetch.mockReset(); });

describe('Certificate change card', () => {
  it('without a change, it shows the served certificate and how to start one', async () => {
    authFetch.mockResolvedValue(ok({ phase: 'none', served, next: [], probePort: null, counts: {}, notReady: [] }));
    render(<PlatformCertificateChangeCard />);
    expect(await screen.findByText(/No certificate change in progress/)).toBeTruthy();
    expect(screen.getByText(/abababababab…/)).toBeTruthy();
    expect(authFetch).toHaveBeenCalledWith('/api/platform/autonomous-ops/health/tls-rollover');
  });

  it('while prepared, it counts ready agents and lists what the others need', async () => {
    authFetch.mockResolvedValue(ok({
      phase: 'prepared', served, next: ['cd'.repeat(32)], probePort: 8443, counts: { active: 3, ready: 1, update_agent: 1, probe_failed: 1 },
      notReady: [
        { hostname: 'EILT0197', platform: 'Windows', version: '2.1.21', status: 'update_agent', detail: 'This agent version cannot take a certificate change; update it' },
        { hostname: 'mac-01', platform: 'macOS', version: '2.1.22', status: 'probe_failed', detail: 'could not connect: timed out' },
      ],
    }));
    render(<PlatformCertificateChangeCard />);
    expect(await screen.findByText(/1 of 3 active agents are ready\. Switch with sudo scripts\/tls_rollover\.sh switch once all are\./)).toBeTruthy();
    const rows = within(screen.getByRole('table', { name: 'Agents not ready for the certificate change' })).getAllByRole('row');
    expect(rows).toHaveLength(3);
    expect(rows[1].textContent).toContain('Update the agent');
    expect(rows[2].textContent).toContain('could not connect: timed out');
  });

  it('a failed load is a plain note', async () => {
    authFetch.mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: 'Super Admin only' }) });
    render(<PlatformCertificateChangeCard />);
    expect(await screen.findByText('The certificate change status could not be loaded (Super Admin only).')).toBeTruthy();
  });
});
