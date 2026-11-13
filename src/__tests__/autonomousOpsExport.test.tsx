/**
 * Phase 86 / ACTV-06, D-09, D-10, D-12: the Export activity button and dialog on the Autonomous Ops screen
 * and the Autonomous Ops Activity card on the Reporting screen. The reporting service is mocked; payloads
 * follow the 86-08 route contract (X-Export-Rows, X-Export-Total, X-Export-Truncated, 204 for nothing).
 */
import React from 'react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../services/autonomousOpsReporting', () => ({
  fetchAutonomousOpsStatistics: vi.fn(),
  downloadAutonomousOpsExport: vi.fn(),
  downloadAutonomousOpsReport: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { authFetch } from '../../services/apiService';
import {
  fetchAutonomousOpsStatistics, downloadAutonomousOpsExport, downloadAutonomousOpsReport,
} from '../../services/autonomousOpsReporting';
import { showToast } from '../../utils/toast';
import { UserContext } from '../../contexts/UserContext';
import { AutonomousOpsStatusProvider } from '../../contexts/AutonomousOpsStatusContext';
import { AutonomousOpsActivity } from '../../components/AutonomousOpsActivity';
import { ExportDialog } from '../../components/autonomousOpsStats/ExportDialog';
import { EmptyStateCard as FromList } from '../../components/AutonomousOpsActivityList';
import { EmptyStateCard as FromOwnFile } from '../../components/AutonomousOpsEmptyStateCard';
import { ReportExportCard } from '../../components/autonomousOpsStats/ReportExportCard';

const mockAuthFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
const fetchStats = fetchAutonomousOpsStatistics as unknown as ReturnType<typeof vi.fn>;
const download = downloadAutonomousOpsExport as unknown as ReturnType<typeof vi.fn>;
const downloadReport = downloadAutonomousOpsReport as unknown as ReturnType<typeof vi.fn>;
const toast = showToast as unknown as ReturnType<typeof vi.fn>;

const ZERO = { fired: 0, done: 0, approved: 0, denied: 0, undone: 0, failed: 0, refused: 0, wouldHaveDone: 0 };
const statsPayload = (canExport: boolean) => ({
  tenantId: 'tenant-a', days: 30, generatedAt: '2026-11-13T09:00:00Z', shadowOnly: false, canExport, rules: [],
  totals: ZERO, timeSaved: { minutes: 0, estimate: true, perKind: [] },
});

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

function routeFetch() {
  mockAuthFetch.mockImplementation(async (url: string) => {
    const path = url.split('?')[0];
    if (path === '/api/autonomous-ops/status') {
      return jsonRes({
        tenantId: 'tenant-a', tenantName: 'Acme Corp', scope: 'tenant', platformTenant: false, eligible: true,
        levelReadable: true, level: 'undoable_auto', maxLevel: 'undoable_auto', previousLevel: null,
        shadow: { effective: false, source: null }, stop: { tenant: null, platform: null },
        canStop: true, canResume: true, canStopPlatform: false, canResumePlatform: false,
      });
    }
    if (path === '/api/autonomous-ops/actions') return jsonRes({ items: [], nextCursor: null });
    if (path === '/api/autonomous-ops/incidents' || path === '/api/autonomous-ops/rollout-cards') {
      return jsonRes({ items: [], total: 0, offset: 0, limit: 10, stopped: null });
    }
    if (path === '/api/platform/autonomous-ops/status') {
      return jsonRes({ scope: 'platform', stop: { platform: null }, tenantStopsCount: 0, canStopPlatform: true, canResumePlatform: true });
    }
    if (path === '/api/platform/autonomous-ops/actions') return jsonRes({ items: [], nextCursor: null });
    return jsonRes({}, 404);
  });
}

function screenFor(role: string) {
  return (
    <UserContext.Provider value={{
      currentUser: { id: 'u1', name: 'Pat', email: 'pat@example.com', role, tenantId: 'tenant-a', permissions: ['view:autonomous_ops'] } as any,
      login: async () => false, logout: () => {}, signup: async () => false,
      registerTenant: async () => false, hasPermission: () => true,
      enabledFeatures: [], serverLockedFeatures: {},
    }}>
      <AutonomousOpsStatusProvider tenantId={null} enabled>
        <AutonomousOpsActivity tenantId={null} />
      </AutonomousOpsStatusProvider>
    </UserContext.Provider>
  );
}

beforeEach(() => {
  mockAuthFetch.mockReset();
  fetchStats.mockReset();
  download.mockReset();
  downloadReport.mockReset();
  toast.mockReset();
});

// ── Task 1: the button on the Activity header ─────────────────────────────────────────────────────────

describe('the Export activity button', () => {
  it('shows beside Newest first in tenant scope when the statistics say canExport', async () => {
    routeFetch();
    fetchStats.mockResolvedValue(statsPayload(true));
    render(screenFor('Tenant Admin'));
    expect(await screen.findByRole('button', { name: 'Export activity' })).toBeInTheDocument();
    expect(screen.getByText('Newest first')).toBeInTheDocument();
  });

  it('is absent when canExport is false', async () => {
    routeFetch();
    fetchStats.mockResolvedValue(statsPayload(false));
    render(screenFor('Tenant Admin'));
    await screen.findByText('Last 30 days · No decisions yet');
    expect(screen.queryByRole('button', { name: 'Export activity' })).toBeNull();
  });

  it('is never rendered in platform scope', async () => {
    routeFetch();
    fetchStats.mockResolvedValue(statsPayload(true));
    render(screenFor('Super Admin'));
    expect(await screen.findByRole('heading', { level: 1, name: 'Autonomous Ops' })).toBeInTheDocument();
    await screen.findByText('Newest first');
    expect(screen.queryByRole('button', { name: 'Export activity' })).toBeNull();
    expect(fetchStats).not.toHaveBeenCalled();
  });

  it('opens a dialog that exports the state pill the list shows', async () => {
    routeFetch();
    fetchStats.mockResolvedValue(statsPayload(true));
    render(screenFor('Tenant Admin'));
    fireEvent.click(await screen.findByRole('button', { name: /^Done/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Export activity' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Activity: Done. Period: Last 30 days. Newest first, up to 5,000 rows.')).toBeInTheDocument();
  });
});

// ── Task 1: the dialog ───────────────────────────────────────────────────────────────────────────────

const WHOLE = { status: 'downloaded', fileName: 'autonomous_ops_activity.csv', rows: 3, total: 3, truncated: false } as const;

const open = (props: Partial<React.ComponentProps<typeof ExportDialog>> = {}) => {
  const onClose = vi.fn();
  render(<ExportDialog bucket="done" defaultDays={30} tenantId="tenant-a" onClose={onClose} {...props} />);
  return onClose;
};

describe('the Export activity dialog', () => {
  it('opens filled: CSV, the Statistics period, the included line, the audit sentence and first focus on Close', async () => {
    open();
    expect(screen.getByRole('dialog', { name: 'Export activity' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /CSV/ })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Last 30 days' })).toBeChecked();
    expect(screen.getByRole('status')).toHaveTextContent('Activity: Done. Period: Last 30 days. Newest first, up to 5,000 rows.');
    expect(screen.getByText('Each export is recorded in the audit log with who exported, the filter, the number of rows and the format.')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus());
  });

  it('follows the period and format choices', () => {
    open({ defaultDays: 90 });
    expect(screen.getByRole('radio', { name: 'Last 90 days' })).toBeChecked();
    fireEvent.click(screen.getByRole('radio', { name: 'All time' }));
    fireEvent.click(screen.getByRole('radio', { name: /PDF/ }));
    expect(screen.getByRole('status')).toHaveTextContent('Activity: Done. Period: All time. Newest first, up to 5,000 rows.');
    expect(screen.getByRole('button', { name: 'Download PDF' })).toBeInTheDocument();
  });

  it('sends one request however often Download CSV is clicked, shows Preparing, keeps Close and ignores Esc', async () => {
    let finish: (v: unknown) => void = () => {};
    download.mockReturnValue(new Promise(res => { finish = res; }));
    const onClose = open();
    const button = screen.getByRole('button', { name: 'Download CSV' });
    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);
    expect(download).toHaveBeenCalledTimes(1);
    expect(download).toHaveBeenCalledWith({ format: 'csv', bucket: 'done', days: '30', tenantId: 'tenant-a' });
    expect(await screen.findByRole('button', { name: 'Preparing...' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Close' })).toBeEnabled();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
    await act(async () => { finish(WHOLE); });
  });

  it('closes with a toast after a whole download', async () => {
    download.mockResolvedValue(WHOLE);
    const onClose = open();
    fireEvent.click(screen.getByRole('button', { name: 'Download CSV' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(toast).toHaveBeenCalledWith('Export downloaded. 3 rows.', 'success');
  });

  it('keeps the dialog open with the amber cap note and the true total when the file was cut', async () => {
    download.mockResolvedValue({ status: 'downloaded', fileName: 'autonomous_ops_activity_2026-11-13.csv', rows: 5000, total: 6200, truncated: true });
    const onClose = open();
    fireEvent.click(screen.getByRole('button', { name: 'Download CSV' }));
    const note = await screen.findByText(
      'Downloaded autonomous_ops_activity_2026-11-13.csv: the newest 5,000 of 6,200 rows. Rows older than that were left out. Pick a shorter period or a single state to get the rest.');
    expect(note.closest('[role="status"]')).not.toBeNull();
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('says nothing was downloaded for a 204', async () => {
    download.mockResolvedValue({ status: 'empty' });
    const onClose = open();
    fireEvent.click(screen.getByRole('button', { name: 'Download CSV' }));
    expect(await screen.findByText('There are no rows for this filter, so nothing was downloaded.')).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(toast).not.toHaveBeenCalled();
  });

  it('shows a red alert and keeps the choices after a failure', async () => {
    download.mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }));
    open();
    fireEvent.click(screen.getByRole('radio', { name: /PDF/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Download PDF' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't create the export. Check your connection and try again.");
    expect(screen.getByRole('radio', { name: /PDF/ })).toBeChecked();
    expect(screen.getByRole('button', { name: 'Download PDF' })).toBeEnabled();
  });

  it('explains a 403 in its own sentence', async () => {
    download.mockRejectedValue(Object.assign(new Error('no'), { status: 403 }));
    open();
    fireEvent.click(screen.getByRole('button', { name: 'Download CSV' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      "You don't have permission to export this. It needs the right to export reports and to view Autonomous Ops.");
  });

  it('renders a hostile file name as text', async () => {
    const hostile = '<img src=x onerror=alert(1)>.csv';
    download.mockResolvedValue({ status: 'downloaded', fileName: hostile, rows: 5000, total: 9000, truncated: true });
    open();
    fireEvent.click(screen.getByRole('button', { name: 'Download CSV' }));
    await screen.findByText(/Downloaded <img src=x/);
    expect(document.body.querySelector('img')).toBeNull();
  });
});

describe('the moved EmptyStateCard', () => {
  it('is the same component from its own file and from the list file', () => {
    expect(FromList).toBe(FromOwnFile);
  });

  it('leaves the list file under 500 lines', () => {
    const text = readFileSync(resolve(__dirname, '../../components/AutonomousOpsActivityList.tsx'), 'utf8');
    expect(text.split('\n').length).toBeLessThan(500);
  });
});

// ── Task 2: the Reporting screen card ─────────────────────────────────────────────────────────────────

function cardFor(role: string, granted: string[]) {
  return render(
    <UserContext.Provider value={{
      currentUser: { id: 'u1', name: 'Pat', email: 'pat@example.com', role, tenantId: 'tenant-a', permissions: granted } as any,
      login: async () => false, logout: () => {}, signup: async () => false,
      registerTenant: async () => false, hasPermission: (p: string) => granted.includes(p),
      enabledFeatures: [], serverLockedFeatures: {},
    }}>
      <ReportExportCard />
    </UserContext.Provider>,
  );
}

const BOTH = ['export:reports', 'view:autonomous_ops'];

describe('the Autonomous Ops Activity card on the Reporting screen', () => {
  it('shows the title, the note and no reason line for a tenant admin with both rights', () => {
    cardFor('Tenant Admin', BOTH);
    expect(screen.getByText('Autonomous Ops Activity')).toBeInTheDocument();
    expect(screen.getByText('All states, last 30 days, newest 5,000 rows.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'CSV' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'PDF' })).toBeEnabled();
    expect(screen.queryByText(/^Needs permission/)).toBeNull();
  });

  it('downloads CSV and spins on that button only', async () => {
    let finish: (v: unknown) => void = () => {};
    downloadReport.mockReturnValue(new Promise(res => { finish = res; }));
    cardFor('Tenant Admin', BOTH);
    fireEvent.click(screen.getByRole('button', { name: 'CSV' }));
    expect(downloadReport).toHaveBeenCalledWith('csv');
    expect(screen.getByRole('button', { name: 'CSV' }).querySelector('svg.animate-spin')).not.toBeNull();
    expect(screen.getByRole('button', { name: 'PDF' }).querySelector('svg.animate-spin')).toBeNull();
    await act(async () => { finish({ fileName: 'a.csv', rows: 2, truncated: false }); });
    await waitFor(() => expect(screen.getByRole('button', { name: 'CSV' }).querySelector('svg.animate-spin')).toBeNull());
    expect(toast).not.toHaveBeenCalled();
  });

  it('says only the newest 5,000 rows are included when the download was cut', async () => {
    downloadReport.mockResolvedValue({ fileName: 'a.pdf', rows: 5000, truncated: true });
    cardFor('Tenant Admin', BOTH);
    fireEvent.click(screen.getByRole('button', { name: 'PDF' }));
    await waitFor(() => expect(toast).toHaveBeenCalledWith('Export downloaded. Only the newest 5,000 rows are included.', 'success'));
    expect(downloadReport).toHaveBeenCalledWith('pdf');
  });

  it('shows the failure toast when the download is rejected', async () => {
    downloadReport.mockRejectedValue(new Error('nope'));
    cardFor('Tenant Admin', BOTH);
    fireEvent.click(screen.getByRole('button', { name: 'CSV' }));
    await waitFor(() => expect(toast).toHaveBeenCalledWith('Failed to export Autonomous Ops Activity.', 'error'));
  });

  it.each([
    ['without export:reports', 'Tenant Admin', ['view:autonomous_ops'], 'Needs permission to export reports.'],
    ['without view:autonomous_ops', 'Tenant Admin', ['export:reports'], 'Needs permission to view Autonomous Ops.'],
    ['for a Super Admin', 'Super Admin', BOTH, 'Open an organization in Tenants, then export from its Autonomous Ops screen.'],
    ['for Platform Support with no rights', 'Platform Support', [], 'Open an organization in Tenants, then export from its Autonomous Ops screen.'],
  ])('disables both buttons with a visible, described reason %s', (_label, role, granted, reason) => {
    cardFor(role, granted);
    const csv = screen.getByRole('button', { name: 'CSV' });
    const pdf = screen.getByRole('button', { name: 'PDF' });
    expect(csv).toBeDisabled();
    expect(pdf).toBeDisabled();
    const line = screen.getByText(reason);
    expect(line.id).not.toBe('');
    expect(csv.getAttribute('aria-describedby')).toBe(line.id);
    expect(pdf.getAttribute('aria-describedby')).toBe(line.id);
    fireEvent.click(csv);
    expect(downloadReport).not.toHaveBeenCalled();
  });

  it('sits in the IT Operations group right after Agent Health on the Reporting screen', () => {
    const text = readFileSync(resolve(__dirname, '../../components/ReportingDashboard.tsx'), 'utf8');
    const agent = text.indexOf('<ExportCard title="Agent Health"');
    const mine = text.indexOf('<ReportExportCard />');
    const next = text.indexOf('Chat & Support');
    expect(agent).toBeGreaterThan(0);
    expect(mine).toBeGreaterThan(agent);
    expect(mine).toBeLessThan(next);
    // one import line and one mount line, nothing else
    expect(text.split('\n').filter(l => l.includes('ReportExportCard'))).toHaveLength(2);
  });
});
