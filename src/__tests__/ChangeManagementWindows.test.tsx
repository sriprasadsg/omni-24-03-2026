/**
 * Phase 84 / PTCH-05, D-01 (84-12 task 3): the read-only windows list in Change Management and the ring chip on
 * Agent Groups. authFetch (and fetch for Agent Groups) are mocked with the 84-05 and 84-06 payloads.
 *
 * Value: protects=anyone on Change Management sees the windows rollouts obey without being able to change them,
 * a failed windows read never hides the changes table, and a group shows the ring it feeds; fails_when=a create,
 * edit or delete control appears in the list, more than 5 windows are shown at once, Manage in Settings is a link
 * when the viewer cannot open Settings, or the ring chip is missing, a link, or cut off; no_claim=the server
 * routes (backend/tests/test_maintenance_windows.py) and the Settings panel (MaintenanceWindows.test.tsx).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));

import { authFetch } from '../../services/apiService';
import { ChangeManagementWindows } from '../../components/patchRollouts/ChangeManagementWindows';
import ChangeManagementDashboard from '../../components/ChangeManagementDashboard';
import AgentGroupsDashboard from '../../components/AgentGroupsDashboard';
import type { ChangeWindowRow } from '../../services/patchRollouts/types';

const mockFetch = authFetch as unknown as ReturnType<typeof vi.fn>;

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

const row = (n: number, over: Partial<ChangeWindowRow> = {}): ChangeWindowRow => ({
  id: `w${n}`, name: `Window ${n}`,
  scheduleText: 'Weekly, Sat and Sun, 22:00 to 02:00 the next day (Asia/Kolkata)',
  openNow: false, nextText: 'Next: Sat 7 Nov, 22:00', ...over,
});

beforeEach(() => { mockFetch.mockReset(); });

describe('ChangeManagementWindows', () => {
  it('shows one h-16 busy skeleton while loading', () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    const { container } = render(<ChangeManagementWindows />);
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(container.querySelectorAll('.h-16')).toHaveLength(1);
    expect(screen.getByRole('heading', { name: 'Maintenance windows' })).toBeInTheDocument();
  });

  it('no windows: says rollouts cannot start, with Manage in Settings as plain text without Settings access', async () => {
    mockFetch.mockResolvedValue(jsonRes([]));
    render(<ChangeManagementWindows />);
    expect(await screen.findByText("No maintenance windows. Rollouts can't start until one is added.")).toBeInTheDocument();
    expect(screen.getByText('Manage in Settings')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Manage in Settings' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Manage in Settings' })).toBeNull();
  });

  it('Manage in Settings is a button only when the viewer can open Settings', async () => {
    mockFetch.mockResolvedValue(jsonRes([row(1)]));
    const onOpenSettings = vi.fn();
    render(<ChangeManagementWindows onOpenSettings={onOpenSettings} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Manage in Settings' }));
    expect(onOpenSettings).toHaveBeenCalledTimes(1);
  });

  it('one window renders one row with its schedule line and the Next chip, and no Show more', async () => {
    mockFetch.mockResolvedValue(jsonRes([row(1)]));
    render(<ChangeManagementWindows />);
    expect(await screen.findByText('Window 1')).toBeInTheDocument();
    expect(screen.getByText('Weekly, Sat and Sun, 22:00 to 02:00 the next day (Asia/Kolkata)')).toBeInTheDocument();
    expect(screen.getByText('Next: Sat 7 Nov, 22:00')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    expect(screen.queryByRole('button', { name: /Show/ })).toBeNull();
    expect(mockFetch.mock.calls[0][0]).toBe('/api/changes/maintenance-windows');
  });

  it('an open window reads Open now', async () => {
    mockFetch.mockResolvedValue(jsonRes([row(1, { openNow: true })]));
    render(<ChangeManagementWindows />);
    expect(await screen.findByText('Open now')).toBeInTheDocument();
    expect(screen.queryByText(/^Next:/)).toBeNull();
  });

  it('7 windows show the first 5 and Show 2 more reveals the rest', async () => {
    mockFetch.mockResolvedValue(jsonRes([1, 2, 3, 4, 5, 6, 7].map(n => row(n))));
    render(<ChangeManagementWindows />);
    await screen.findByText('Window 1');
    expect(screen.getAllByRole('listitem')).toHaveLength(5);
    expect(screen.queryByText('Window 6')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show 2 more' }));
    expect(screen.getAllByRole('listitem')).toHaveLength(7);
    expect(screen.queryByRole('button', { name: /Show/ })).toBeNull();
  });

  it('exactly 5 windows show no Show more', async () => {
    mockFetch.mockResolvedValue(jsonRes([1, 2, 3, 4, 5].map(n => row(n))));
    render(<ChangeManagementWindows />);
    await screen.findByText('Window 5');
    expect(screen.queryByRole('button', { name: /Show/ })).toBeNull();
  });

  it('has no create, edit or delete control', async () => {
    mockFetch.mockResolvedValue(jsonRes([row(1), row(2)]));
    render(<ChangeManagementWindows />);
    await screen.findByText('Window 1');
    expect(screen.queryByRole('button', { name: /add|edit|delete|save|create/i })).toBeNull();
    expect(screen.queryAllByRole('textbox')).toHaveLength(0);
  });

  it('a long name and schedule line wrap', async () => {
    mockFetch.mockResolvedValue(jsonRes([row(1, { name: 'A very long maintenance window name for the finance servers and every database' })]));
    render(<ChangeManagementWindows />);
    const name = await screen.findByText(/A very long maintenance window name/);
    expect(name.className).toContain('break-words');
    expect(screen.getByText(/Weekly, Sat and Sun/).className).toContain('break-words');
  });

  it('a failed read shows the alert with Try again, which reads again', async () => {
    mockFetch.mockRejectedValueOnce(new Error('offline'));
    render(<ChangeManagementWindows />);
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain("Couldn't load maintenance windows.");
    mockFetch.mockResolvedValue(jsonRes([row(1)]));
    fireEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Window 1')).toBeInTheDocument();
  });

  it('is mounted above the filters of Change Management, and a failed read leaves the changes table alone', async () => {
    mockFetch.mockImplementation(async (url: string) => {
      if (url === '/api/changes/maintenance-windows') throw new Error('offline');
      if (url === '/api/changes') {
        return jsonRes([{
          id: 'c1', title: 'Upgrade the firewall', change_type: 'normal', status: 'draft', risk_level: 'low',
          impact_level: 'low', risk_assessment: '', rollback_plan: '', implementation_plan: '', cab_votes: [],
          required_approvals: 1, scheduled_start: '', scheduled_end: '', assignee: '', reporter: 'Pat',
          created_at: '2026-11-01T00:00:00Z',
        }]);
      }
      return jsonRes([]);
    });
    render(<ChangeManagementDashboard />);
    expect(await screen.findByText('Upgrade the firewall')).toBeInTheDocument();
    expect(await screen.findByText("Couldn't load maintenance windows.")).toBeInTheDocument();
    const heading = screen.getByRole('heading', { name: 'Maintenance windows' });
    const filter = screen.getAllByRole('combobox')[0];
    expect(heading.compareDocumentPosition(filter) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe('Agent Groups ring chip', () => {
  const groups = [
    { id: 'g1', name: 'Pilot machines', description: '', color: '#3b82f6', tags: [], member_count: 3, created_at: '2026-11-01T00:00:00Z', ringName: 'Pilot' },
    { id: 'g2', name: 'Everything else', description: '', color: '#10b981', tags: [], member_count: 9, created_at: '2026-11-01T00:00:00Z', ringName: null },
    { id: 'g3', name: 'Finance', description: '', color: '#f59e0b', tags: [], member_count: 2, created_at: '2026-11-01T00:00:00Z' },
    { id: 'g4', name: 'Datacentre', description: '', color: '#ef4444', tags: [], member_count: 1, created_at: '2026-11-01T00:00:00Z', ringName: 'Production datacentre ring number four' },
  ];

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonRes(groups)));
  });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('a group with a ring shows Ring: name, a group without one shows nothing, and the chip is not a link', async () => {
    render(<AgentGroupsDashboard />);
    await screen.findByText('Pilot machines');
    const chip = screen.getByText('Ring: Pilot');
    expect(chip.closest('a')).toBeNull();
    expect(chip.querySelector('svg')).not.toBeNull();
    expect(screen.getAllByText(/^Ring:/)).toHaveLength(2);
    const card = screen.getByText('Everything else').closest('div.cursor-pointer') as HTMLElement;
    expect(within(card).queryByText(/Ring:/)).toBeNull();
    const finance = screen.getByText('Finance').closest('div.cursor-pointer') as HTMLElement;
    expect(within(finance).queryByText(/Ring:/)).toBeNull();
  });

  it('a long ring name wraps inside the chip and is never truncated', async () => {
    render(<AgentGroupsDashboard />);
    await waitFor(() => expect(screen.getByText('Ring: Production datacentre ring number four')).toBeInTheDocument());
    const chip = screen.getByText('Ring: Production datacentre ring number four');
    expect(chip.className).toContain('break-words');
    expect(chip.className).not.toContain('truncate');
  });
});
