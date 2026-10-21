/**
 * Agents screen:
 *  - The fleet summary answers totalAgents / onlineAgents; the screen read total_agents / online_agents, so
 *    a fleet larger than the first page of /api/agents (50) showed the page count as the fleet size.
 *  - An agent reported Online whose heartbeat is stale shows Offline; the status filter and the counts now
 *    agree with the card.
 *  - "Restart" only wrote to the console (no restart path exists), so it is gone.
 *  - A filter with no matches no longer says "No agents registered yet"; versions sort numerically;
 *    status filters set by a command are applied.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { AgentsDashboard } from '../../components/AgentsDashboard';
import { UserContext } from '../../contexts/UserContext';
import { TimeZoneProvider } from '../../contexts/TimeZoneContext';
import type { Agent, Filter } from '../../types';

const json = (body: unknown, status = 200) =>
  ({ ok: status >= 200 && status < 300, status, headers: new Headers(), json: async () => body }) as Response;

const secsAgo = (s: number) => new Date(Date.now() - s * 1000).toISOString();
const agent = (id: string, hostname: string, status: Agent['status'], lastSeen: string, version = '2.1.14') =>
  ({ id, hostname, status, lastSeen, version, platform: 'Linux', tenantId: 't1', ipAddress: '10.0.0.1', assetId: `a-${id}`, capabilities: [], health: {} }) as unknown as Agent;

const fresh = agent('ag1', 'WKS-101', 'Online', secsAgo(10), '2.1.9');
const stale = agent('ag2', 'WKS-102', 'Online', secsAgo(900), '2.1.10');

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  sessionStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

function renderScreen(agents: Agent[], { summary, filters = [] }: { summary?: Record<string, number>; filters?: Filter[] } = {}) {
  fetchMock.mockImplementation(async (url: string) => {
    const u = String(url);
    if (u.includes('/api/kpi/summary')) return json(summary ?? {});
    if (u.includes('/api/agents/pending')) return json({ agents: [] });
    return json([]);
  });
  const user = { id: 'u', name: 'Ava', email: 'ava@x.test', role: 'Tenant Admin', tenantId: 't1' } as any;
  return render(
    <TimeZoneProvider>
      <UserContext.Provider value={{ currentUser: user, hasPermission: () => true } as any}>
        <AgentsDashboard agents={agents} assets={[]} logs={[]} registrationKey={null} onRegisterAgent={vi.fn()} onUpdateAgent={vi.fn()}
          agentUpgradeJobs={[]} onScheduleUpgrade={vi.fn()} filters={filters} onClearFilters={vi.fn()} activeTenantId="t1" subscriptionTier="Enterprise" />
      </UserContext.Provider>
    </TimeZoneProvider>,
  );
}

const cards = () => screen.getAllByRole('checkbox', { name: /^Select agent / }).map(c => c.getAttribute('aria-label'));

describe('Agents screen', () => {
  it('uses the fleet summary when the list is only the first page', async () => {
    renderScreen([fresh], { summary: { totalAgents: 120, onlineAgents: 80, totalAssets: 130 } });
    expect(await screen.findByText('Showing the first 1 of 120')).toBeTruthy();
    expect(screen.getAllByText('120').length).toBeGreaterThan(0);
    expect(screen.getAllByText('80').length).toBeGreaterThan(0);
  });

  it('counts from the live list when it is the whole fleet', async () => {
    renderScreen([fresh, stale], { summary: { totalAgents: 2, onlineAgents: 2 } });
    await screen.findAllByText('WKS-101');
    expect(screen.queryByText(/Showing the first/)).toBeNull();
  });

  it('a stale "Online" agent shows, filters and counts as Offline', async () => {
    renderScreen([fresh, stale]);
    const filter = await screen.findByRole('group', { name: 'Filter by status' }).catch(() => null);
    if (filter) {
      fireEvent.click(within(filter).getByRole('button', { name: /^Offline/ }));
    } else {
      fireEvent.change(screen.getByDisplayValue('All Statuses'), { target: { value: 'Offline' } });
    }
    expect(cards()).toEqual(['Select agent WKS-102']);
  });

  it('has no Restart button', () => {
    renderScreen([fresh]);
    expect(screen.queryByTitle('Restart Agent')).toBeNull();
    expect(screen.queryByRole('button', { name: /Restart/ })).toBeNull();
  });

  it('a filter with no matches says so and can be cleared', async () => {
    renderScreen([fresh]);
    const filter = await screen.findByRole('group', { name: 'Filter by status' }).catch(() => null);
    if (filter) {
      fireEvent.click(within(filter).getByRole('button', { name: /^Error/ }));
    } else {
      fireEvent.change(screen.getByDisplayValue('All Statuses'), { target: { value: 'Error' } });
    }
    expect(screen.getByText('No agents match these filters')).toBeTruthy();
    expect(screen.queryByText('No agents registered yet')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show all agents' }));
    expect(cards()).toEqual(['Select agent WKS-101']);
  });

  it('sorts versions numerically', () => {
    renderScreen([stale, fresh]);
    const sortVersion = screen.getByRole('button', { name: /^Version/ });
    fireEvent.click(sortVersion);
    expect(cards()).toEqual(['Select agent WKS-101', 'Select agent WKS-102']);
  });

  it('applies a status filter set by a command', () => {
    renderScreen([fresh, agent('ag3', 'SRV-ERR', 'Error', secsAgo(5))], { filters: [{ type: 'status', value: 'error' }] });
    expect(cards()).toEqual(['Select agent SRV-ERR']);
  });
});
