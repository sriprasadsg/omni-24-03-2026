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
import { ReportBuilderForm } from '../../components/itam/ReportBuilderForm';

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
    listItamCustomReports.mockReset();
    saveItamCustomReport.mockReset();
    deleteItamCustomReport.mockReset();
    previewItamCustomReport.mockReset();
    runItamCustomReport.mockReset();
    showToast.mockReset();
    fetchItamPrebuiltReports.mockResolvedValue(REPORT_META);
    listItamCustomReports.mockResolvedValue([]);
  });

  it('renders the pre-built report list on mount without a full-page skeleton', async () => {
    render(<ReportsPanel />);
    await waitFor(() => expect(screen.getByText('Warranty Expiring')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('No custom reports yet')).toBeInTheDocument());
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

/**
 * Phase 72 (plan 72-06, Task 1) ReportBuilderForm behavior — the field +
 * filter picker (D-02/D-03).
 */
const FIELD_CATALOG = [
  { key: 'asset.assetTag', label: 'Asset Tag', entity: 'asset', type: 'text' },
  { key: 'asset.purchaseDate', label: 'Purchase Date', entity: 'asset', type: 'date' },
  { key: 'asset.purchaseCostCents', label: 'Purchase Cost (cents)', entity: 'asset', type: 'number' },
];

describe('ReportBuilderForm', () => {
  let onPreview: ReturnType<typeof vi.fn>;
  let onSave: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchItamReportFields.mockReset();
    fetchItamReportFields.mockResolvedValue(FIELD_CATALOG);
    showToast.mockReset();
    onPreview = vi.fn().mockResolvedValue(undefined);
    onSave = vi.fn().mockResolvedValue(undefined);
  });

  async function renderForm(busy = false) {
    render(<ReportBuilderForm onPreview={onPreview} onSave={onSave} busy={busy} />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Asset Tag' })).toBeInTheDocument());
  }

  it('fetches the field catalogue on mount and lists selectable columns as toggleable chips', async () => {
    await renderForm();
    expect(screen.getByRole('button', { name: 'Asset Tag' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Purchase Date' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Purchase Cost (cents)' })).toBeInTheDocument();
    const chip = screen.getByRole('button', { name: 'Asset Tag' });
    expect(chip).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(chip);
    expect(chip).toHaveAttribute('aria-pressed', 'true');
  });

  it('a text field offers exactly equals/contains and a date field offers exactly three operators', async () => {
    await renderForm();
    fireEvent.change(screen.getByLabelText('Filter field'), { target: { value: 'asset.assetTag' } });
    expect(screen.getByLabelText('Filter operator').querySelectorAll('option').length).toBe(2);

    fireEvent.change(screen.getByLabelText('Filter field'), { target: { value: 'asset.purchaseDate' } });
    expect(screen.getByLabelText('Filter operator').querySelectorAll('option').length).toBe(3);
  });

  it('choosing the between operator reveals a second value input', async () => {
    await renderForm();
    fireEvent.change(screen.getByLabelText('Filter field'), { target: { value: 'asset.purchaseCostCents' } });
    expect(screen.queryByLabelText('Filter value 2')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Filter operator'), { target: { value: 'between' } });
    expect(screen.getByLabelText('Filter value 2')).toBeInTheDocument();
  });

  it('an added filter appears as a removable row and removing it drops it from the definition', async () => {
    await renderForm();
    fireEvent.change(screen.getByLabelText('Filter field'), { target: { value: 'asset.assetTag' } });
    fireEvent.change(screen.getByLabelText('Filter value'), { target: { value: 'IT-0001' } });
    fireEvent.click(screen.getByLabelText('Add filter'));
    expect(screen.getByTitle('Asset Tag equals IT-0001')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/Remove filter/));
    await waitFor(() => expect(screen.queryByTitle('Asset Tag equals IT-0001')).not.toBeInTheDocument());
  });

  it('running with zero filters submits an empty filter list and still returns rows', async () => {
    await renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Asset Tag' }));
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    await waitFor(() => expect(onPreview).toHaveBeenCalledWith(
      expect.objectContaining({ columns: ['asset.assetTag'], filters: [] }), 1,
    ));
  });

  it('Run is disabled until at least one column is selected', async () => {
    await renderForm();
    expect(screen.getByRole('button', { name: 'Run' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Asset Tag' }));
    expect(screen.getByRole('button', { name: 'Run' })).not.toBeDisabled();
  });

  it('a rejected run calls showToast with the error variant and the run error sentence', async () => {
    onPreview.mockRejectedValueOnce(new Error("Couldn't run report. Try adjusting your filters or contact an administrator."));
    await renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Asset Tag' }));
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith(
      "Couldn't run report. Try adjusting your filters or contact an administrator.", 'error',
    ));
  });

  it('a rejected save calls showToast with the save error sentence', async () => {
    onSave.mockRejectedValueOnce(new Error("Couldn't save report. Give it a name and try again."));
    await renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Asset Tag' }));
    fireEvent.change(screen.getByLabelText('Report Name'), { target: { value: 'My Report' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Report' }));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith(
      "Couldn't save report. Give it a name and try again.", 'error',
    ));
  });

  it('the column and filter area is inside a max-height scroll container', async () => {
    await renderForm();
    const columnChip = screen.getByRole('button', { name: 'Asset Tag' });
    const scrollContainer = columnChip.closest('.max-h-64');
    expect(scrollContainer).not.toBeNull();
    expect(scrollContainer).toHaveClass('overflow-y-auto');
  });
});

/**
 * Phase 72 (plan 72-06, Task 2) ReportsPanel two-section layout — pre-built
 * grid, saved custom-report list, delete modal, three export buttons.
 */
const SIX_PREBUILT_REPORTS = [
  { key: 'warranty_expiring', title: 'Warranty Expiring', description: '', columns: [], defaultSort: '' },
  { key: 'asset_value', title: 'Asset Value & Depreciation', description: '', columns: [], defaultSort: '' },
  { key: 'checkout_activity', title: 'Check-Out / Check-In Activity', description: '', columns: [], defaultSort: '' },
  { key: 'overdue_audits', title: 'Overdue Physical Audits', description: '', columns: [], defaultSort: '' },
  { key: 'license_utilization', title: 'License Seat Utilization', description: '', columns: [], defaultSort: '' },
  { key: 'low_stock_consumables', title: 'Low-Stock Consumables', description: '', columns: [], defaultSort: '' },
];

const SAVED_REPORTS = [{
  id: 'rpt-abc123',
  name: 'My Custom Report',
  columns: ['asset.assetTag'],
  filters: [],
  createdAt: '2026-08-17T00:00:00.000Z',
  createdBy: 'admin',
}];

function savedReportRunResult() {
  return {
    key: 'rpt-abc123', title: 'My Custom Report', columns: ['Asset Tag'],
    rows: [{ 'Asset Tag': 'IT-9001' }], rowCount: 1, page: 1, pageSize: 50, totalPages: 1, truncated: false,
  };
}

describe('ReportsPanel — two-section layout', () => {
  beforeEach(() => {
    fetchItamPrebuiltReports.mockReset();
    runItamPrebuiltReport.mockReset();
    generateItamReport.mockReset();
    downloadItamReport.mockReset();
    fetchItamReportFields.mockReset();
    listItamCustomReports.mockReset();
    saveItamCustomReport.mockReset();
    deleteItamCustomReport.mockReset();
    previewItamCustomReport.mockReset();
    runItamCustomReport.mockReset();
    showToast.mockReset();
    fetchItamPrebuiltReports.mockResolvedValue(REPORT_META);
    fetchItamReportFields.mockResolvedValue([]);
    listItamCustomReports.mockResolvedValue([]);
  });

  it('renders all six pre-built report titles in the pre-built section', async () => {
    fetchItamPrebuiltReports.mockResolvedValue(SIX_PREBUILT_REPORTS);
    render(<ReportsPanel />);
    await waitFor(() => {
      SIX_PREBUILT_REPORTS.forEach((r) => expect(screen.getByText(r.title)).toBeInTheDocument());
    });
  });

  it('the Create Custom Report control reveals the builder form', async () => {
    render(<ReportsPanel />);
    await waitFor(() => expect(screen.getByText('Custom Reports')).toBeInTheDocument());
    expect(screen.queryByLabelText('Report Name')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Create Custom Report/ }));
    await waitFor(() => expect(screen.getByLabelText('Report Name')).toBeInTheDocument());
  });

  it('renders the "No custom reports yet" empty state with no saved reports', async () => {
    render(<ReportsPanel />);
    await waitFor(() => expect(screen.getByText('No custom reports yet')).toBeInTheDocument());
    expect(screen.getByText('Build a report by picking fields and filters, then save it to reuse anytime.')).toBeInTheDocument();
  });

  it('renders one row per saved report with truncated name, run and delete controls', async () => {
    listItamCustomReports.mockResolvedValue(SAVED_REPORTS);
    render(<ReportsPanel />);
    await waitFor(() => expect(screen.getByText('My Custom Report')).toBeInTheDocument());
    expect(screen.getByText('My Custom Report')).toHaveAttribute('title', 'My Custom Report');
    expect(screen.getByRole('button', { name: 'Run My Custom Report' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete My Custom Report' })).toBeInTheDocument();
  });

  it('clicking delete opens the shared Modal and only calls deleteItamCustomReport after the confirm control is used', async () => {
    listItamCustomReports.mockResolvedValue(SAVED_REPORTS);
    render(<ReportsPanel />);
    await waitFor(() => expect(screen.getByText('My Custom Report')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Delete My Custom Report' }));
    await waitFor(() => expect(screen.getByText('Delete report?')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(deleteItamCustomReport).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByText('Delete report?')).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Delete My Custom Report' }));
    await waitFor(() => expect(screen.getByText('Delete report?')).toBeInTheDocument());
    deleteItamCustomReport.mockResolvedValue(undefined);
    listItamCustomReports.mockResolvedValue([]);
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(deleteItamCustomReport).toHaveBeenCalledWith('rpt-abc123'));
  });

  it('running a saved report renders its rows in the shared preview table', async () => {
    listItamCustomReports.mockResolvedValue(SAVED_REPORTS);
    runItamCustomReport.mockResolvedValue(savedReportRunResult());
    render(<ReportsPanel />);
    await waitFor(() => expect(screen.getByText('My Custom Report')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Run My Custom Report' }));
    await waitFor(() => expect(screen.getByText('IT-9001')).toBeInTheDocument());
  });

  it('the three export buttons appear labelled once a report has run', async () => {
    listItamCustomReports.mockResolvedValue(SAVED_REPORTS);
    runItamCustomReport.mockResolvedValue(savedReportRunResult());
    render(<ReportsPanel />);
    await waitFor(() => expect(screen.getByText('My Custom Report')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Run My Custom Report' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Export PDF' })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Export Excel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument();
  });

  it('clicking an export button calls generateItamReport with the running report kind/key, then downloadItamReport', async () => {
    listItamCustomReports.mockResolvedValue(SAVED_REPORTS);
    runItamCustomReport.mockResolvedValue(savedReportRunResult());
    generateItamReport.mockResolvedValue({ filename: 'custom_report.csv', url: '/x', generatedAt: 'now', rowCount: 1, truncated: false });
    render(<ReportsPanel />);
    await waitFor(() => expect(screen.getByText('My Custom Report')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Run My Custom Report' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    await waitFor(() => expect(generateItamReport).toHaveBeenCalledWith('custom', 'rpt-abc123', 'csv'));
    await waitFor(() => expect(downloadItamReport).toHaveBeenCalledWith('custom_report.csv'));
  });

  it('export buttons are disabled and show the loading convention while generation is in flight', async () => {
    listItamCustomReports.mockResolvedValue(SAVED_REPORTS);
    runItamCustomReport.mockResolvedValue(savedReportRunResult());
    let resolveExport: (v: unknown) => void = () => {};
    generateItamReport.mockReturnValue(new Promise((resolve) => { resolveExport = resolve; }));
    render(<ReportsPanel />);
    await waitFor(() => expect(screen.getByText('My Custom Report')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Run My Custom Report' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Exporting…' })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Export PDF' })).toBeDisabled();
    resolveExport({ filename: 'x.csv', url: '/x', generatedAt: 'now', rowCount: 1, truncated: false });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument());
  });

  it('a failed export calls showToast with the export error sentence', async () => {
    listItamCustomReports.mockResolvedValue(SAVED_REPORTS);
    runItamCustomReport.mockResolvedValue(savedReportRunResult());
    generateItamReport.mockRejectedValue(new Error('boom'));
    render(<ReportsPanel />);
    await waitFor(() => expect(screen.getByText('My Custom Report')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Run My Custom Report' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('boom', 'error'));
  });

  it('a saved-report list load failure leaves the list unpopulated and raises the error toast', async () => {
    listItamCustomReports.mockRejectedValue(new Error('Failed to load saved reports'));
    render(<ReportsPanel />);
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('Failed to load saved reports', 'error'));
    expect(screen.getByText('Custom Reports')).toBeInTheDocument();
    expect(screen.getByText('No custom reports yet')).toBeInTheDocument();
  });
});
