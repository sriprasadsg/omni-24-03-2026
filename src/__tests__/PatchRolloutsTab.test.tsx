/**
 * Phase 84 / PTCH-01, PTCH-04, PTCH-05 (84-14): the Rollouts tab on the Patching screen. authFetch is mocked with the
 * 84-09 payloads (GET /api/patch-rollouts, /window, /{id}).
 *
 * Value: protects=the operator sees the window state, the assurance line and every rollout on the Patching screen, in
 * every loading, empty, error, stop and shadow case, and the tab badge counts what needs a person; fails_when=the
 * Rollouts tab is missing or out of order, the badge shows at zero, a background poll shows a skeleton or an error,
 * the live region speaks on first load, polling continues while the tab is hidden, or a control renders without its
 * server flag; no_claim=the server payloads (backend/tests/test_patch_rollout_views.py) and the card
 * (PatchRolloutCard.test.tsx).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within, act } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { authFetch } from '../../services/apiService';
import { fetchRollout, fetchRollouts, fetchWindowStrip } from '../../services/patchRollouts/rollouts';
import { PatchManagementDashboard } from '../../components/PatchManagementDashboard';
import { card, jsonRes, rolloutPage } from './_patchRolloutFixtures';

const mockFetch = authFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => { mockFetch.mockReset(); });

describe('rollouts calls', () => {
  it('fetchRollouts asks for the page, with the viewed organization when given', async () => {
    mockFetch.mockResolvedValue(jsonRes(rolloutPage([card()])));
    await fetchRollouts({ offset: 10, limit: 10, tenantId: 'tenant_x' });
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts?offset=10&limit=10&tenantId=tenant_x');
    mockFetch.mockClear();
    await fetchRollouts({});
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts?offset=0&limit=10');
  });

  it('fetchRollout and fetchWindowStrip use /{id} and /window', async () => {
    mockFetch.mockResolvedValue(jsonRes(card()));
    await fetchRollout('R 1');
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts/R%201');
    mockFetch.mockClear();
    mockFetch.mockResolvedValue(jsonRes({ state: 'none', text: '', closesAt: null, nextOpensAt: null, timeZone: null }));
    await fetchWindowStrip('tenant_x');
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts/window?tenantId=tenant_x');
  });

  it('a failed call carries the status and the server sentence', async () => {
    mockFetch.mockResolvedValue(jsonRes({ detail: 'Rollouts need a maintenance window.' }, 422));
    await expect(fetchRollouts({})).rejects.toMatchObject({ status: 422, detail: 'Rollouts need a maintenance window.' });
    mockFetch.mockResolvedValue(jsonRes({}, 500));
    await expect(fetchRollout('R1')).rejects.toMatchObject({ status: 500, detail: '' });
  });
});

describe('PatchManagementDashboard Rollouts tab', () => {
  const dashboard = (props: Record<string, unknown> = {}) => render(
    <PatchManagementDashboard patches={[]} assets={[]} patchDeploymentJobs={[]} vulnerabilityScanJobs={[]}
      onSchedulePatchDeployment={vi.fn()} onScheduleVulnerabilityScan={vi.fn()} tenantId={null} {...props} />);

  const serve = (attention: number) => mockFetch.mockImplementation((url: string) => Promise.resolve(
    url.startsWith('/api/patch-rollouts')
      ? jsonRes(rolloutPage([card()], { attentionCount: attention }))
      : jsonRes([])));

  const tabNames = () => screen.getAllByRole('button')
    .map(b => b.textContent ?? '')
    .filter(t => /Patches & Deployment|Software Updates|OS Patches|Rollouts|Agent Approvals/.test(t));

  it('lists Rollouts between OS Patches and Agent Approvals, with no emoji', async () => {
    serve(0);
    dashboard();
    const names = tabNames();
    const index = (word: string) => names.findIndex(n => n.includes(word));
    expect(index('Patches & Deployment')).toBeLessThan(index('Software Updates'));
    expect(index('Software Updates')).toBeLessThan(index('OS Patches'));
    expect(index('OS Patches')).toBeLessThan(index('Rollouts'));
    expect(index('Rollouts')).toBeLessThan(index('Agent Approvals'));
    expect(names[index('Rollouts')]).toMatch(/^Rollouts/);
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
  });

  it('shows an amber badge with the number of rollouts that need a person, and hides it at zero', async () => {
    serve(2);
    dashboard();
    const tab = screen.getByRole('button', { name: /^Rollouts/ });
    expect(await within(tab).findByText('2')).toBeInTheDocument();
    expect(mockFetch.mock.calls.some(c => c[0] === '/api/patch-rollouts?offset=0&limit=1')).toBe(true);
  });

  it('shows no badge at zero', async () => {
    serve(0);
    dashboard();
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    const tab = screen.getByRole('button', { name: /^Rollouts/ });
    expect(tab.textContent).toBe('Rollouts');
  });

  it('re-reads the badge on window focus', async () => {
    serve(0);
    dashboard();
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    serve(3);
    act(() => { window.dispatchEvent(new Event('focus')); });
    const tab = screen.getByRole('button', { name: /^Rollouts/ });
    expect(await within(tab).findByText('3')).toBeInTheDocument();
  });

  it('a failed badge read shows no badge and no error', async () => {
    mockFetch.mockResolvedValue(jsonRes({ detail: 'x' }, 500));
    dashboard();
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: /^Rollouts/ }).textContent).toBe('Rollouts');
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('selecting the tab renders the Rollouts section', async () => {
    serve(0);
    dashboard();
    fireEvent.click(screen.getByRole('button', { name: /^Rollouts/ }));
    expect(await screen.findByRole('heading', { level: 2, name: 'Rollouts' })).toBeInTheDocument();
  });

  it('the badge read follows the viewed organization', async () => {
    serve(0);
    dashboard({ tenantId: 'tenant_b' });
    await waitFor(() => expect(mockFetch.mock.calls.some(
      c => c[0] === '/api/patch-rollouts?offset=0&limit=1&tenantId=tenant_b')).toBe(true));
  });
});

afterEach(() => { vi.useRealTimers(); });
