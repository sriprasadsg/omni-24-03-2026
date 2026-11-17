/**
 * Phase 78 plan 11: ReportsPanel stale-response and request-sequence behaviour
 * (UI-SPEC R3, threat T-78-27). Only the latest request may own the result:
 *  - a run or builder preview issued before a tenant switch renders nothing when it resolves after;
 *  - switching to no tenant mid-run clears the Loading line at once;
 *  - two runs in one tenant that resolve out of order end on the later-issued run;
 *  - a superseded failure raises no toast;
 *  - the unsaved builder preview still renders (Phase 72 D-02) and offers no export;
 *  - a rerender with the same tenant keeps the shown result.
 */
import type { ComponentProps } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';

const fetchItamPrebuiltReports = vi.fn();
const runItamPrebuiltReport = vi.fn();
const generateItamReport = vi.fn();
const downloadItamReport = vi.fn();
const fetchItamReportFields = vi.fn();
const listItamCustomReports = vi.fn();
const saveItamCustomReport = vi.fn();
const deleteItamCustomReport = vi.fn();
const previewItamCustomReport = vi.fn();
const runItamCustomReport = vi.fn();

vi.mock('../../services/apiService', () => ({
  fetchItamPrebuiltReports: (...args: unknown[]) => fetchItamPrebuiltReports(...args),
  runItamPrebuiltReport: (...args: unknown[]) => runItamPrebuiltReport(...args),
  generateItamReport: (...args: unknown[]) => generateItamReport(...args),
  downloadItamReport: (...args: unknown[]) => downloadItamReport(...args),
  fetchItamReportFields: (...args: unknown[]) => fetchItamReportFields(...args),
  listItamCustomReports: (...args: unknown[]) => listItamCustomReports(...args),
  saveItamCustomReport: (...args: unknown[]) => saveItamCustomReport(...args),
  deleteItamCustomReport: (...args: unknown[]) => deleteItamCustomReport(...args),
  previewItamCustomReport: (...args: unknown[]) => previewItamCustomReport(...args),
  runItamCustomReport: (...args: unknown[]) => runItamCustomReport(...args),
}));

const showToast = vi.fn();
vi.mock('../../utils/toast', () => ({ showToast: (...args: unknown[]) => showToast(...args) }));

import { ReportsPanel } from '../../components/itam/ReportsPanel';

const PREBUILT_METAS = [
  { key: 'asset_value', title: 'Asset Value', description: 'Book value per asset' },
  { key: 'warranty_expiring', title: 'Warranty Expiring', description: 'Warranties inside the alert window' },
];
const SAVED_REPORT = {
  id: 'c-1', name: 'My report', columns: ['asset.assetTag'], filters: [],
  createdAt: '2026-11-17T00:00:00.000Z', createdBy: 'admin',
};
const FIELD_CATALOG = [{ key: 'asset.assetTag', label: 'Asset Tag', entity: 'asset', type: 'text' }];

function resultFor(title: string, value: string) {
  return {
    key: 'k', title, columns: ['Asset Tag'], rows: [{ 'Asset Tag': value }],
    rowCount: 1, page: 1, pageSize: 50, totalPages: 1, truncated: false,
  };
}

function deferred<T = unknown>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

// Runs fn, then lets React flush whatever a late response writes before absence is asserted.
async function settle(fn: () => void) {
  await act(async () => {
    fn();
    await new Promise((r) => setTimeout(r, 20));
  });
}

type PanelProps = ComponentProps<typeof ReportsPanel>;

async function renderPanel(props: PanelProps) {
  const view = render(<ReportsPanel {...props} />);
  await screen.findByText('Pre-built Reports');
  await waitFor(() => expect(
    screen.queryByText('No custom reports yet') || screen.queryByRole('button', { name: 'Run My report' }),
  ).toBeInTheDocument());
  return view;
}

describe('ReportsPanel stale responses (Phase 78 plan 11)', () => {
  beforeEach(() => {
    [fetchItamPrebuiltReports, runItamPrebuiltReport, generateItamReport, downloadItamReport,
      fetchItamReportFields, listItamCustomReports, saveItamCustomReport, deleteItamCustomReport,
      previewItamCustomReport, runItamCustomReport, showToast].forEach((fn) => fn.mockReset());
    fetchItamPrebuiltReports.mockResolvedValue(PREBUILT_METAS);
    listItamCustomReports.mockResolvedValue([]);
    fetchItamReportFields.mockResolvedValue(FIELD_CATALOG);
  });

  it('a saved custom run issued before a tenant switch renders nothing when it resolves after', async () => {
    listItamCustomReports.mockResolvedValue([SAVED_REPORT]);
    const held = deferred();
    runItamCustomReport.mockReturnValueOnce(held.promise);
    const { rerender } = await renderPanel({ tenantId: 't-1' });

    fireEvent.click(screen.getByRole('button', { name: 'Run My report' }));
    await waitFor(() => expect(runItamCustomReport).toHaveBeenCalledWith('c-1', 1, 50));
    rerender(<ReportsPanel tenantId="t-2" />);
    await settle(() => held.resolve(resultFor('My report', 'IT-OLD')));

    expect(screen.queryByText('IT-OLD')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'My report', level: 3 })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Export CSV/ })).not.toBeInTheDocument();
  });

  it('switching to no tenant while a run is in flight clears Loading at once and the late response renders nothing', async () => {
    const held = deferred();
    runItamPrebuiltReport.mockReturnValueOnce(held.promise);
    const { rerender } = await renderPanel({ tenantId: 't-1' });

    fireEvent.click(screen.getAllByRole('button', { name: 'Run Report' })[0]);
    expect(await screen.findByText('Loading…')).toBeInTheDocument();

    rerender(<ReportsPanel needsTenant />);
    await waitFor(() => expect(screen.queryByText('Loading…')).not.toBeInTheDocument());
    await settle(() => held.resolve(resultFor('Asset Value', 'IT-LATE')));

    expect(screen.queryByText('IT-LATE')).not.toBeInTheDocument();
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument();
    expect(showToast).not.toHaveBeenCalled();
  });

  it('two runs in one tenant resolving out of order end on the later-issued run', async () => {
    const first = deferred();
    const second = deferred();
    runItamPrebuiltReport.mockImplementation((key: string) => (key === 'asset_value' ? first.promise : second.promise));
    await renderPanel({ tenantId: 't-1' });

    const runButtons = screen.getAllByRole('button', { name: 'Run Report' });
    fireEvent.click(runButtons[0]);
    fireEvent.click(runButtons[1]);
    await waitFor(() => expect(runItamPrebuiltReport).toHaveBeenCalledTimes(2));

    await settle(() => first.resolve(resultFor('Asset Value', 'IT-A')));
    expect(screen.getByText('Loading…')).toBeInTheDocument();
    expect(screen.queryByText('IT-A')).not.toBeInTheDocument();

    await settle(() => second.resolve(resultFor('Warranty Expiring', 'IT-W')));
    expect(screen.getByText('IT-W')).toBeInTheDocument();
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument();
    expect(screen.queryByText('IT-A')).not.toBeInTheDocument();
  });

  it('a pre-built run that fails after the switch raises no toast', async () => {
    const held = deferred();
    runItamPrebuiltReport.mockReturnValueOnce(held.promise);
    const { rerender } = await renderPanel({ tenantId: 't-1' });

    fireEvent.click(screen.getAllByRole('button', { name: 'Run Report' })[0]);
    await waitFor(() => expect(runItamPrebuiltReport).toHaveBeenCalledTimes(1));
    rerender(<ReportsPanel tenantId="t-2" />);
    await settle(() => held.reject(new Error('boom')));

    expect(showToast).not.toHaveBeenCalled();
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument();
  });

  async function runPreview() {
    fireEvent.click(screen.getByRole('button', { name: /Create Custom Report/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Asset Tag' }));
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
  }

  it('the unsaved builder preview still renders its rows and offers no export', async () => {
    previewItamCustomReport.mockResolvedValue(resultFor('Custom Report', 'IT-PREVIEW'));
    await renderPanel({ tenantId: 't-1' });

    await runPreview();

    expect(await screen.findByText('IT-PREVIEW')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Export CSV/ })).not.toBeInTheDocument();
  });

  it('a builder preview that resolves after the tenant switch renders nothing', async () => {
    const held = deferred();
    previewItamCustomReport.mockReturnValueOnce(held.promise);
    const { rerender } = await renderPanel({ tenantId: 't-1' });

    await runPreview();
    await waitFor(() => expect(previewItamCustomReport).toHaveBeenCalledTimes(1));
    rerender(<ReportsPanel tenantId="t-2" />);
    await settle(() => held.resolve(resultFor('Custom Report', 'IT-PREVIEW')));

    expect(screen.queryByText('IT-PREVIEW')).not.toBeInTheDocument();
  });

  it('a rerender with the same tenant keeps the shown result and its export buttons', async () => {
    runItamPrebuiltReport.mockResolvedValue(resultFor('Asset Value', 'IT-KEEP'));
    const { rerender } = await renderPanel({ tenantId: 't-1' });

    fireEvent.click(screen.getAllByRole('button', { name: 'Run Report' })[0]);
    expect(await screen.findByText('IT-KEEP')).toBeInTheDocument();

    rerender(<ReportsPanel tenantId="t-1" />);
    await settle(() => undefined);

    expect(screen.getByText('IT-KEEP')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Export CSV/ })).toBeInTheDocument();
  });

  it("a failed run after a successful one keeps the earlier report's title, rows and export target", async () => {
    runItamPrebuiltReport
      .mockResolvedValueOnce(resultFor('Asset Value', 'IT-A'))
      .mockRejectedValueOnce(new Error('boom'));
    generateItamReport.mockResolvedValue({ filename: 'a.csv' });
    downloadItamReport.mockResolvedValue(undefined);
    await renderPanel({ tenantId: 't-1' });

    const runButtons = screen.getAllByRole('button', { name: 'Run Report' });
    fireEvent.click(runButtons[0]);
    expect(await screen.findByText('IT-A')).toBeInTheDocument();
    fireEvent.click(runButtons[1]);
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('boom', 'error'));

    expect(screen.getByRole('heading', { name: 'Asset Value', level: 3 })).toBeInTheDocument();
    expect(screen.getByText('IT-A')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Export CSV/ }));
    await waitFor(() => expect(downloadItamReport).toHaveBeenCalledWith('a.csv'));
    expect(generateItamReport).toHaveBeenLastCalledWith('prebuilt', 'asset_value', 'csv', 't-1');
  });
});
