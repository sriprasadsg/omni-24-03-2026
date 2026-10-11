/**
 * Regression tests for the 2026-10-11 sidebar audit: options that couldn't be
 * clicked, pages that never got data, and figures that were hard-coded instead
 * of measured.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({
  authFetch: (...args: unknown[]) => authFetch(...args),
  fetchSupportUnreadCount: () => Promise.resolve(0),
  fetchAgents: () => Promise.resolve([]),
  getJobs: () => Promise.resolve([]),
  fetchCryptoInventory: () => Promise.resolve([]),
}));
vi.mock('../../services/socketService', () => ({ socketService: { on: vi.fn(), off: vi.fn() } }));

import { Sidebar } from '../../components/Sidebar';
import { UserContext } from '../../contexts/UserContext';
import AttackTimelineDashboard from '../../components/AttackTimelineDashboard';
import { RuntimeSecurityPage } from '../../components/RuntimeSecurityPage';
import { meshErrorRate } from '../../components/ServiceMeshDashboard';
import { fleetHealthIndex } from '../../components/PredictiveHealthDashboard';
import { integrationHubStats } from '../../components/IntegrationsHub';
import { alertsPerDay, assetsByOsFamily, threatTrendDirection } from '../../components/CXODashboard';
import { hadrSummary } from '../../components/HADRDashboard';
import { infraAlerts } from '../../components/SystemHealthDashboard';
import { simulationCoverage, SIM_TECHNIQUES } from '../../components/SecuritySimulation';
import { etlRunsByDay } from '../../components/DataWarehouseDashboard';
import { shareLink } from '../../components/SecureFileShare';
import { opsSummary } from '../../components/FutureOpsDashboard';
import { horizonSummary } from '../../components/FutureTechDashboard';
import { describeRouteProblem } from '../../components/ApiStatusDashboard';
import { toQuizPayload } from '../../components/TrainingAdminPanel';

const json = (body: unknown, status = 200) =>
  ({ ok: status >= 200 && status < 300, status, json: async () => body }) as Response;

describe('Sidebar', () => {
  it('opens a long group tall enough to show every option (Security has 49)', () => {
    const user = { id: 'u', name: 'S', email: 's@x', role: 'Super Admin', tenantId: 'platform-admin' } as any;
    render(
      <UserContext.Provider value={{ currentUser: user, hasPermission: () => true } as any}>
        <Sidebar isOpen currentView="dashboard" setCurrentView={() => {}} isViewingTenant={false} onBackToTenants={() => {}} />
      </UserContext.Provider>,
    );
    const header = screen.getByText('Security (SecOps)').closest('button')!;
    fireEvent.click(header);
    const content = header.nextElementSibling as HTMLElement;
    const items = content.querySelectorAll('button').length;
    expect(items).toBeGreaterThan(40);
    // each option is ~38px tall; the old fixed 1000px cap hid the bottom half
    expect(parseInt(content.style.maxHeight, 10)).toBeGreaterThanOrEqual(items * 38);
  });
});

describe('AttackTimelineDashboard', () => {
  beforeEach(() => authFetch.mockReset());

  it('shows an empty state instead of sample attacks when there are no events', async () => {
    authFetch.mockResolvedValue(json([]));
    render(<AttackTimelineDashboard />);
    expect(await screen.findByText(/No security events in this time range/)).toBeTruthy();
    expect(screen.queryByText(/WIN-DC01/)).toBeNull();
  });
});

describe('RuntimeSecurityPage', () => {
  it('shows the selected agent’s runtime data', () => {
    const agents = [
      { id: 'a1', hostname: 'host-1', meta: {} },
      { id: 'a2', hostname: 'host-2', meta: { runtime_security: { processes: [{ pid: 7, name: 'sshd', user: 'root', cpu_percent: 1, memory_percent: 1 }], connections: [], suspicious_activities: [], process_count: 1, connection_count: 0 } } },
    ] as any;
    render(<RuntimeSecurityPage agents={agents} />);
    expect(screen.getByLabelText('Agent')).toHaveValue('a2');
    expect(screen.queryByText('No runtime security data available')).toBeNull();
  });
});

describe('measured figures', () => {
  it('derives KPIs from data and returns "no data" when there is none', () => {
    expect(meshErrorRate([])).toBeNull();
    expect(meshErrorRate([{ requestCount: 200, errorCount: 2 }])).toBeCloseTo(1);
    expect(fleetHealthIndex([])).toBeNull();
    expect(fleetHealthIndex([{ failure_probability: 0.2 }, { failure_probability: 0.4 }])).toBe('70.0');
    expect(integrationHubStats([{ isEnabled: true, status: 'error' }, { isEnabled: false }] as any))
      .toEqual({ enabled: 1, errors: 1, events: null });
    expect(simulationCoverage([{ technique: 'memory_write' }, { technique: 'memory_write' }]).exercised).toBe(1);
    expect(SIM_TECHNIQUES).toHaveLength(3);
    expect(opsSummary([{ status: 'running' }], [{ status: 'Online' }, { status: 'Offline' }]))
      .toMatchObject({ active: 1, endpoints: 2, onlinePct: 50 });
    expect(horizonSummary([{ quantumVulnerable: true }, { quantumVulnerable: false }] as any, []))
      .toMatchObject({ cryptoAssets: 2, quantumVulnerable: 1, agentsTotal: 0 });
  });

  it('builds the CXO threat trend from alert timestamps', () => {
    const now = new Date('2026-10-11T12:00:00Z');
    const days = alertsPerDay([
      { severity: 'Critical', timestamp: '2026-10-11T08:00:00Z' },
      { severity: 'High', timestamp: '2026-10-05T08:00:00Z' },
      { severity: 'Low', timestamp: '2026-10-11T08:00:00Z' },
    ], now);
    expect(days).toHaveLength(7);
    expect(days[6].critical).toBe(1);
    expect(days.reduce((n, d) => n + d.critical + d.high + d.medium, 0)).toBe(2);
    expect(threatTrendDirection(days.map(() => ({ critical: 0, high: 0, medium: 0 }))).label).toBe('No alerts');
    expect(assetsByOsFamily([{ osName: 'Windows 11' }, { osName: 'Ubuntu 24.04' }, { osName: 'Windows Server' }]))
      .toEqual(expect.arrayContaining([{ name: 'Windows', value: 2, color: expect.any(String) }]));
  });

  it('summarises HA/DR from backups and tests, with nothing invented', () => {
    const empty = hadrSummary([], null, null, []);
    expect(empty.latestBackupAgo).toBeNull();
    expect(empty.drState.label).toBe('NOT TESTED YET');
    expect(empty.tiles.every(t => t.ok === null)).toBe(true);
    const s = hadrSummary(
      [{ id: '1', backup_id: 'b', backup_type: 'full', status: 'completed', started_at: '2026-10-11T10:00:00Z', completed_at: '2026-10-11T10:30:00Z', size_bytes: 2048, encrypted: true }],
      { status_counts: {}, total_size_bytes: 2048, total_size_gb: 0, rpo_compliant: true, rpo_hours: 1, rto_minutes: 15, latest_backup_time: '2026-10-11T11:30:00Z' },
      null, [], Date.parse('2026-10-11T12:00:00Z'),
    );
    expect(s.latestBackupAgo).toBe('30m 0s');
    expect(s.rpoPct).toBeCloseTo(50);
    expect(s.byType).toEqual([{ type: 'full', count: 1, bytes: 2048, pct: 100 }]);
  });

  it('raises System Health alerts only from the live snapshot', () => {
    const healthy = {
      status: 'ok', uptime: '1h',
      resources: { cpu_percent: 10, memory_percent: 20, memory_used_gb: 1, memory_total_gb: 8, disk_percent: 30, available: true },
      database: { connected: true },
      queues: { alert_queue: 0, open_alerts: 0, deployment_tasks: 0, running_playbooks: 0 },
      agent_fleet: { total: 1, online: 1, offline: 0, stale: 0, health_pct: 100 },
      background_tasks: [{ name: 'NVD CVE Sync', interval: '6h', status: 'running' }],
    };
    expect(infraAlerts(healthy as any).map(a => a.title)).toEqual(['All Checks Passing']);
    const sick = { ...healthy, database: { connected: false }, background_tasks: [{ name: 'NVD CVE Sync', interval: '6h', status: 'not running' }] };
    expect(infraAlerts(sick as any).map(a => a.title)).toEqual(['Database Disconnected', 'Background Tasks Not Running']);
  });

  it('charts real ETL runs, links shares to the recipient page, and builds quizzes', () => {
    const runs = etlRunsByDay([{ start_time: '2026-10-11T09:00:00' }, { start_time: '2026-10-11T10:00:00' }], new Date('2026-10-11T12:00:00'));
    expect(runs[6].runs).toBe(2);
    expect(runs.slice(0, 6).every(d => d.runs === 0)).toBe(true);
    expect(shareLink('a b')).toBe(`${window.location.origin}/static/shared.html#a%20b`);
    expect(describeRouteProblem({ path: '/api/x', name: 'x', methods: ['GET'], status: 'Unregistered' }))
      .toContain('no handler bound');
    expect(toQuizPayload([{ question: ' Q ', options: 'a\n b \n', correct_answer: 'b' }, { question: '', options: '', correct_answer: '' }]))
      .toEqual([{ question: 'Q', options: ['a', 'b'], correct_answer: 'b' }]);
  });
});
