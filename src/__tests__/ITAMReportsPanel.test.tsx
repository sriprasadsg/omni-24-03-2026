/**
 * Phase 72 (plan 72-01, Task 2) ReportsPanel behavior — UI-SPEC E4 states:
 *  1. Pre-built report list renders on mount without a full-page skeleton.
 *  2. A run returning rows renders a table whose header cells equal the response columns.
 *  3. A run returning zero rows renders the "No matching assets" empty state.
 *  4. An in-flight run shows the existing "Loading…" convention.
 *  5. A rejected run routes through showToast('error') and keeps the prior table intact.
 *  6. A null cell value renders an em dash, never blank or "undefined".
 *  7. A single-row response renders exactly one table body row.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const fetchItamPrebuiltReports = vi.fn();
const runItamPrebuiltReport = vi.fn();
const generateItamReport = vi.fn();
const downloadItamReport = vi.fn();

vi.mock('../../services/apiService', () => ({
  fetchItamPrebuiltReports: (...args: unknown[]) => fetchItamPrebuiltReports(...args),
  runItamPrebuiltReport: (...args: unknown[]) => runItamPrebuiltReport(...args),
  generateItamReport: (...args: unknown[]) => generateItamReport(...args),
  downloadItamReport: (...args: unknown[]) => downloadItamReport(...args),
}));

const showToast = vi.fn();
vi.mock('../../utils/toast', () => ({ showToast: (...args: unknown[]) => showToast(...args) }));

import { ReportsPanel } from '../../components/itam/ReportsPanel';

const REPORT_COLUMNS = ['Asset Tag', 'Name', 'Lifecycle Status', 'Warranty Expires', 'Days To Expiry', 'Status'];

const REPORT_META = [{
  key: 'warranty_expiring',
  title: 'Warranty Expiring',
  description: "Assets whose warranty falls inside the tenant's alert window.",
  columns: REPORT_COLUMNS,
  defaultSort: 'Ascending by warranty expiry date',
}];

function runResult(rows: Record<string, unknown>[]) {
  return {
    key: 'warranty_expiring',
    title: 'Warranty Expiring',
    columns: REPORT_COLUMNS,
    rows,
    rowCount: rows.length,
    page: 1,
    pageSize: 50,
    totalPages: 1,
    truncated: false,
  };
}

async function renderAndOpenReport() {
  render(<ReportsPanel />);
  await waitFor(() => expect(screen.getByText('Warranty Expiring')).toBeInTheDocument());
}

describe('ReportsPanel', () => {
  beforeEach(() => {
    fetchItamPrebuiltReports.mockReset();
    runItamPrebuiltReport.mockReset();
    generateItamReport.mockReset();
    downloadItamReport.mockReset();
    showToast.mockReset();
    fetchItamPrebuiltReports.mockResolvedValue(REPORT_META);
  });

  it('renders the pre-built report list on mount without a full-page skeleton', async () => {
    render(<ReportsPanel />);
    await waitFor(() => expect(screen.getByText('Warranty Expiring')).toBeInTheDocument());
    expect(screen.getByText('Run Report')).toBeInTheDocument();
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument();
  });

  it('a run returning rows renders a table whose header cells equal the response columns', async () => {
    runItamPrebuiltReport.mockResolvedValue(runResult([
      { 'Asset Tag': 'IT-0001', Name: 'Laptop X1', 'Lifecycle Status': 'deployed', 'Warranty Expires': '2026-09-01', 'Days To Expiry': 10, Status: 'expiring' },
    ]));
    await renderAndOpenReport();
    fireEvent.click(screen.getByText('Run Report'));
    await waitFor(() => expect(screen.getByText('IT-0001')).toBeInTheDocument());
    for (const col of REPORT_COLUMNS) {
      expect(screen.getByText(col)).toBeInTheDocument();
    }
  });

  it('a run returning zero rows renders the "No matching assets" empty state', async () => {
    runItamPrebuiltReport.mockResolvedValue(runResult([]));
    await renderAndOpenReport();
    fireEvent.click(screen.getByText('Run Report'));
    await waitFor(() => expect(screen.getByText('No matching assets')).toBeInTheDocument());
    expect(screen.getByText('Adjust your filters and run the report again.')).toBeInTheDocument();
  });

  it('an in-flight run shows the existing Loading… convention', async () => {
    let resolveRun: (value: unknown) => void = () => {};
    runItamPrebuiltReport.mockReturnValue(new Promise((resolve) => { resolveRun = resolve; }));
    await renderAndOpenReport();
    fireEvent.click(screen.getByText('Run Report'));
    await waitFor(() => expect(screen.getByText('Loading…')).toBeInTheDocument());
    resolveRun(runResult([]));
    await waitFor(() => expect(screen.getByText('No matching assets')).toBeInTheDocument());
  });

  it('a rejected run calls showToast with the error variant and leaves the previous table state intact', async () => {
    runItamPrebuiltReport.mockResolvedValueOnce(runResult([
      { 'Asset Tag': 'IT-0001', Name: 'Laptop X1', 'Lifecycle Status': 'deployed', 'Warranty Expires': '2026-09-01', 'Days To Expiry': 10, Status: 'expiring' },
    ]));
    await renderAndOpenReport();
    fireEvent.click(screen.getByText('Run Report'));
    await waitFor(() => expect(screen.getByText('IT-0001')).toBeInTheDocument());

    runItamPrebuiltReport.mockRejectedValueOnce(new Error('boom'));
    fireEvent.click(screen.getByText('Run Report'));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('boom', 'error'));
    // The panel is not replaced with an error page — the prior table stays visible.
    expect(screen.getByText('IT-0001')).toBeInTheDocument();
  });

  it('a null cell value renders an em dash, never blank or "undefined"', async () => {
    runItamPrebuiltReport.mockResolvedValue(runResult([
      { 'Asset Tag': 'IT-0002', Name: null, 'Lifecycle Status': 'deployed', 'Warranty Expires': '2026-09-01', 'Days To Expiry': 5, Status: 'expiring' },
    ]));
    await renderAndOpenReport();
    fireEvent.click(screen.getByText('Run Report'));
    await waitFor(() => expect(screen.getByText('IT-0002')).toBeInTheDocument());
    expect(screen.queryByText('undefined')).not.toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('a single-row response renders exactly one table body row', async () => {
    runItamPrebuiltReport.mockResolvedValue(runResult([
      { 'Asset Tag': 'IT-0003', Name: 'Laptop', 'Lifecycle Status': 'deployed', 'Warranty Expires': '2026-09-01', 'Days To Expiry': 5, Status: 'expiring' },
    ]));
    await renderAndOpenReport();
    fireEvent.click(screen.getByText('Run Report'));
    await waitFor(() => expect(screen.getByText('IT-0003')).toBeInTheDocument());
    // 1 header row + 1 data row.
    expect(screen.getAllByRole('row').length).toBe(2);
  });
});
