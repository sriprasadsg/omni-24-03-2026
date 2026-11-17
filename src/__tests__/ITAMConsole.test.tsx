/**
 * Phase 61 (plan 61-01) smoke tests for the ITAM console shell, extended by
 * Phase 72 (plan 72-01) for the Reports tab:
 *  1. All 11 tabs render, defaulting to Catalog.
 *  2. Tab switching mounts the corresponding panel.
 *  3. Each panel renders without crashing given empty/loading API responses.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

const getItamSettings = vi.fn();
const runItamPrebuiltReport = vi.fn();
const fetchItamKpis = vi.fn();
const fetchItamPrebuiltReports = vi.fn();
const runItamCustomReport = vi.fn();
const generateItamReport = vi.fn();
const listItamCustomReports = vi.fn();

vi.mock('../../services/apiService', () => ({
  fetchAssets: vi.fn().mockResolvedValue([]),
  fetchCatalogEntities: vi.fn().mockResolvedValue([]),
  createCatalogEntity: vi.fn(),
  updateCatalogEntity: vi.fn(),
  deleteCatalogEntity: vi.fn(),
  createManualAsset: vi.fn(),
  checkoutAsset: vi.fn(),
  checkinAsset: vi.fn(),
  markAssetAudited: vi.fn(),
  fetchAssetBookValue: vi.fn().mockResolvedValue({ assetId: 'a1', bookValueCents: null, reason: 'no_purchase_record' }),
  fetchAssetWarranty: vi.fn().mockResolvedValue({ assetId: 'a1', alertWindowDays: 30, warrantyStatus: 'none', warrantyExpiresAt: null, daysToExpiry: null }),
  updateAssetPurchase: vi.fn(),
  fetchPurchaseOrders: vi.fn().mockResolvedValue([]),
  fetchLicenses: vi.fn().mockResolvedValue([]),
  createLicense: vi.fn(),
  assignLicenseSeat: vi.fn(),
  reclaimLicenseSeat: vi.fn(),
  fetchLicenseAssignments: vi.fn().mockResolvedValue([]),
  fetchConsumables: vi.fn().mockResolvedValue([]),
  createConsumable: vi.fn(),
  checkoutConsumable: vi.fn(),
  checkinConsumable: vi.fn(),
  fetchComponents: vi.fn().mockResolvedValue([]),
  createComponent: vi.fn(),
  attachComponent: vi.fn(),
  detachComponent: vi.fn(),
  fetchComplianceFrameworks: vi.fn().mockResolvedValue([]),
  fetchAssetCompliance: vi.fn().mockResolvedValue([]),
  updateAssetComplianceStatus: vi.fn(),
  uploadComplianceEvidence: vi.fn(),
  deleteComplianceEvidence: vi.fn(),
  ingestKnowledge: vi.fn(),
  fetchItamAuditLogs: vi.fn().mockResolvedValue([]),
  verifyAuditIntegrity: vi.fn().mockResolvedValue({ valid: true, total_records: 0 }),
  exportItamAssetsCsv: vi.fn(),
  fetchItamPrebuiltReports: (...args: unknown[]) => fetchItamPrebuiltReports(...args),
  runItamPrebuiltReport: (...args: unknown[]) => runItamPrebuiltReport(...args),
  fetchItamKpis: (...args: unknown[]) => fetchItamKpis(...args),
  generateItamReport: (...args: unknown[]) => generateItamReport(...args),
  downloadItamReport: vi.fn(),
  fetchItamReportFields: vi.fn().mockResolvedValue([]),
  saveItamCustomReport: vi.fn(),
  listItamCustomReports: (...args: unknown[]) => listItamCustomReports(...args),
  deleteItamCustomReport: vi.fn(),
  previewItamCustomReport: vi.fn(),
  runItamCustomReport: (...args: unknown[]) => runItamCustomReport(...args),
  getItamSettings: (...args: unknown[]) => getItamSettings(...args),
  saveItamSettings: vi.fn(),
  authFetch: vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
  API_BASE: '/api',
}));

vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import ITAMConsole from '../../components/itam/ITAMConsole';

describe('ITAMConsole', () => {
  beforeEach(() => {
    getItamSettings.mockReset();
    getItamSettings.mockResolvedValue({ branding: { companyName: '', logoUrl: '', primaryColor: '#0891b2' }, locale: 'en' });
    fetchItamPrebuiltReports.mockReset();
    fetchItamPrebuiltReports.mockResolvedValue([]);
    runItamCustomReport.mockReset();
    generateItamReport.mockReset();
    generateItamReport.mockResolvedValue({ filename: 'report.csv' });
    listItamCustomReports.mockReset();
    listItamCustomReports.mockResolvedValue([]);
    runItamPrebuiltReport.mockReset();
    runItamPrebuiltReport.mockResolvedValue({
      key: 'warranty_expiring', title: 'Warranty Expiring', columns: [], rows: [],
      rowCount: 0, page: 1, pageSize: 50, totalPages: 1, truncated: false,
    });
    // Phase 72 Plan 07: hasData=false on every KPI so ItamKpiPanel's tiles
    // render their empty states without chart geometry under jsdom.
    fetchItamKpis.mockReset();
    fetchItamKpis.mockResolvedValue({
      assetValue: { hasData: false, drilldownReportKey: 'asset_value' },
      licenseUtilization: { hasData: false, drilldownReportKey: 'license_utilization' },
      warrantyExpirations: { hasData: false, drilldownReportKey: 'warranty_expiring' },
      overdue: { hasData: false, drilldownReportKey: 'overdue_audits' },
    });
  });

  it('renders all 11 tabs and defaults to Catalog', async () => {
    render(<ITAMConsole />);
    expect(screen.getByText('Catalog')).toBeInTheDocument();
    expect(screen.getByText('Check-Out/In')).toBeInTheDocument();
    expect(screen.getByText('Procurement & Finance')).toBeInTheDocument();
    expect(screen.getByText('Licenses & Consumables')).toBeInTheDocument();
    expect(screen.getByText('Compliance')).toBeInTheDocument();
    expect(screen.getByText('Software Inventory')).toBeInTheDocument();
    expect(screen.getByText('Reports')).toBeInTheDocument();
    expect(screen.getByText('Activity')).toBeInTheDocument();
    expect(screen.getByText('Import / Export')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Manufacturers')).toBeInTheDocument());
  });

  it('switches to the Reports tab and mounts ReportsPanel', async () => {
    render(<ITAMConsole />);
    fireEvent.click(screen.getByText('Reports'));
    await waitFor(() => expect(screen.getByText('Pre-built Reports')).toBeInTheDocument());
  });

  it('renders the KPI grid above the pre-built report sections on the Reports tab (Phase 72 Plan 07)', async () => {
    render(<ITAMConsole />);
    fireEvent.click(screen.getByText('Reports'));

    await waitFor(() => expect(screen.getByText('Total Asset Value')).toBeInTheDocument());
    expect(screen.getByText('License Seat Utilization')).toBeInTheDocument();
    expect(screen.getByText('Warranty Expirations')).toBeInTheDocument();
    expect(screen.getByText('Overdue Audits & Check-ins')).toBeInTheDocument();
    expect(screen.getByText('Pre-built Reports')).toBeInTheDocument();

    // KPI grid must appear first in document order (UI-SPEC visual-hierarchy note).
    const kpiHeading = screen.getByText('Total Asset Value');
    const prebuiltHeading = screen.getByText('Pre-built Reports');
    // eslint-disable-next-line no-bitwise
    expect(kpiHeading.compareDocumentPosition(prebuiltHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('clicking a KPI tile sets reportFocus, driving ReportsPanel to auto-run that report through its focusReportKey seam', async () => {
    render(<ITAMConsole />);
    fireEvent.click(screen.getByText('Reports'));
    await waitFor(() => expect(screen.getByText('Total Asset Value')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /Total Asset Value/i }));

    await waitFor(() => expect(runItamPrebuiltReport).toHaveBeenCalledWith('asset_value', 1, 50, undefined));
  });

  it("clearing the drilled-into focus via ReportsPanel's onFocusHandled prevents a later tab switch from re-triggering the same run", async () => {
    render(<ITAMConsole />);
    fireEvent.click(screen.getByText('Reports'));
    await waitFor(() => expect(screen.getByText('Total Asset Value')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /Total Asset Value/i }));
    await waitFor(() => expect(runItamPrebuiltReport).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByText('Catalog'));
    fireEvent.click(screen.getByText('Reports'));
    await waitFor(() => expect(screen.getByText('Total Asset Value')).toBeInTheDocument());
    expect(runItamPrebuiltReport).toHaveBeenCalledTimes(1);
  });

  it("a Platform Owner's selected tenant reaches the KPI request on the Reports tab", async () => {
    render(<ITAMConsole isSuperAdminView tenantId="t-1" />);
    fireEvent.click(screen.getByText('Reports'));
    await waitFor(() => expect(fetchItamKpis).toHaveBeenCalledWith('t-1'));
    expect(screen.queryByText('Select a tenant')).not.toBeInTheDocument();
  });

  it('a Platform Owner with no tenant selected sees the Select a tenant block and no KPI request is sent', async () => {
    render(<ITAMConsole isSuperAdminView />);
    fireEvent.click(screen.getByText('Reports'));
    await waitFor(() => expect(screen.getByText('Select a tenant')).toBeInTheDocument());
    expect(fetchItamKpis).not.toHaveBeenCalled();
  });

  it('offers Go to Tenants in the Select block only when onGoToTenants is given', async () => {
    const onGoToTenants = vi.fn();
    const { unmount } = render(<ITAMConsole isSuperAdminView onGoToTenants={onGoToTenants} />);
    fireEvent.click(screen.getByText('Reports'));
    fireEvent.click(await screen.findByRole('button', { name: 'Go to Tenants' }));
    expect(onGoToTenants).toHaveBeenCalledTimes(1);
    unmount();

    render(<ITAMConsole isSuperAdminView />);
    fireEvent.click(screen.getByText('Reports'));
    await waitFor(() => expect(screen.getByText('Select a tenant')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Go to Tenants' })).not.toBeInTheDocument();
  });

  it("a tenant user's Reports tab still renders the KPI grid and requests with no tenant", async () => {
    render(<ITAMConsole />);
    fireEvent.click(screen.getByText('Reports'));
    await waitFor(() => expect(screen.getByText('Total Asset Value')).toBeInTheDocument());
    expect(fetchItamKpis).toHaveBeenCalledWith(undefined);
    expect(screen.queryByText('Select a tenant')).not.toBeInTheDocument();
  });

  it('switches to the Settings tab and shows the branding form', async () => {
    render(<ITAMConsole />);
    fireEvent.click(screen.getByText('Settings'));
    await waitFor(() => expect(screen.getByLabelText('Company name')).toBeInTheDocument());
    expect(screen.getByLabelText('Logo URL')).toBeInTheDocument();
  });

  it('switches to the Import / Export tab and shows the export button', async () => {
    render(<ITAMConsole />);
    fireEvent.click(screen.getByText('Import / Export'));
    await waitFor(() => expect(screen.getByText('Export assets CSV')).toBeInTheDocument());
  });

  it('switches to the Activity tab and shows the empty state', async () => {
    render(<ITAMConsole />);
    fireEvent.click(screen.getByText('Activity'));
    await waitFor(() => expect(screen.getByText('No activity recorded yet')).toBeInTheDocument());
  });

  it('switches to the Licenses & Consumables tab and shows its 3 sections', async () => {
    render(<ITAMConsole />);
    fireEvent.click(screen.getByText('Licenses & Consumables'));
    await waitFor(() => expect(screen.getByText('Software Licenses')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /^consumables$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^components$/i })).toBeInTheDocument();
  });

  it('switches to the Check-Out/In tab and shows the empty state', async () => {
    render(<ITAMConsole />);
    fireEvent.click(screen.getByText('Check-Out/In'));
    await waitFor(() => expect(screen.getByText('No assets yet')).toBeInTheDocument());
  });

  it('switches to the Procurement & Finance tab', async () => {
    render(<ITAMConsole />);
    fireEvent.click(screen.getByText('Procurement & Finance'));
    await waitFor(() => expect(screen.getByText('Select an asset')).toBeInTheDocument());
  });

  it('switches to the Software Inventory tab without crashing', async () => {
    render(<ITAMConsole />);
    fireEvent.click(screen.getByText('Software Inventory'));
    await waitFor(() => expect(screen.getByText('Software Inventory')).toBeInTheDocument());
  });

  it('switches to the Compliance tab and shows the no-controls state when no frameworks exist', async () => {
    render(<ITAMConsole />);
    fireEvent.click(screen.getByText('Compliance'));
    await waitFor(() => expect(screen.getByText('No controls available.')).toBeInTheDocument());
  });

  it('renders a configured logo with the company name as its alt text', async () => {
    getItamSettings.mockResolvedValue({
      branding: { companyName: 'Acme Corp', logoUrl: 'https://example.com/logo.png', primaryColor: '#ff00aa' },
      locale: 'en',
    });
    render(<ITAMConsole />);
    await waitFor(() => expect(screen.getByAltText('Acme Corp')).toBeInTheDocument());
    expect(screen.getByAltText('Acme Corp')).toHaveAttribute('src', 'https://example.com/logo.png');
  });

  it('a malformed colour value leaves the console rendering without throwing', async () => {
    getItamSettings.mockResolvedValue({
      branding: { companyName: '', logoUrl: '', primaryColor: 'not-a-color' },
      locale: 'en',
    });
    render(<ITAMConsole />);
    await waitFor(() => expect(screen.getByText('Catalog')).toBeInTheDocument());
    // Falls back to the built-in default rather than propagating the malformed value.
    const settingsButton = screen.getByLabelText('Open ITAM console settings');
    expect(settingsButton.style.backgroundColor).not.toBe('not-a-color');
  });

  it('mounting with a Spanish locale from getItamSettings renders the Spanish tab labels', async () => {
    getItamSettings.mockResolvedValue({
      branding: { companyName: '', logoUrl: '', primaryColor: '#0891b2' },
      locale: 'es',
    });
    render(<ITAMConsole />);
    await waitFor(() => expect(screen.getByText('Catálogo')).toBeInTheDocument());
    expect(screen.getByText('Cumplimiento')).toBeInTheDocument();
    expect(screen.getByText('Configuración')).toBeInTheDocument();
  });

  it('an unknown locale value renders the English labels rather than blanks', async () => {
    getItamSettings.mockResolvedValue({
      branding: { companyName: '', logoUrl: '', primaryColor: '#0891b2' },
      locale: 'fr' as any,
    });
    render(<ITAMConsole />);
    await waitFor(() => expect(screen.getByText('Catalog')).toBeInTheDocument());
    expect(screen.getByText('Compliance')).toBeInTheDocument();
  });
  describe('Reports tab under the tenant rule (Phase 78 plan 06)', () => {
    const assetValueMeta = { key: 'asset_value', title: 'Asset Value', description: 'Book value per asset' };
    const assetValueResult = {
      key: 'asset_value', title: 'Asset Value', columns: ['Name'], rows: [{ Name: 'Laptop 1' }],
      rowCount: 1, page: 1, pageSize: 50, totalPages: 1, truncated: false,
    };
    const NOTE = 'Select a tenant to run these reports. They cover one organization at a time.';

    beforeEach(() => {
      fetchItamPrebuiltReports.mockResolvedValue([assetValueMeta]);
      runItamPrebuiltReport.mockResolvedValue(assetValueResult);
    });

    async function openReports(ui: React.ReactElement) {
      const view = render(ui);
      fireEvent.click(screen.getByText('Reports'));
      await screen.findByText('Pre-built Reports');
      return view;
    }

    it('runs and exports a pre-built report for the selected tenant', async () => {
      await openReports(<ITAMConsole isSuperAdminView tenantId="t-1" />);
      fireEvent.click(await screen.findByRole('button', { name: 'Run Report' }));
      await waitFor(() => expect(runItamPrebuiltReport).toHaveBeenCalledWith('asset_value', 1, 50, 't-1'));
      fireEvent.click(await screen.findByRole('button', { name: /Export CSV/ }));
      await waitFor(() => expect(generateItamReport).toHaveBeenCalledWith('prebuilt', 'asset_value', 'csv', 't-1'));
    });

    it('runs and exports a saved custom report without any tenant argument', async () => {
      listItamCustomReports.mockResolvedValue([{ id: 'c-1', name: 'My report', columns: ['name'] }]);
      runItamCustomReport.mockResolvedValue({ ...assetValueResult, key: 'c-1', title: 'My report' });
      await openReports(<ITAMConsole isSuperAdminView tenantId="t-1" />);
      fireEvent.click(await screen.findByRole('button', { name: 'Run My report' }));
      await waitFor(() => expect(runItamCustomReport).toHaveBeenCalledWith('c-1', 1, 50));
      fireEvent.click(await screen.findByRole('button', { name: /Export CSV/ }));
      await waitFor(() => expect(generateItamReport).toHaveBeenCalledWith('custom', 'c-1', 'csv'));
    });

    it('disables Run Report with a described status note when a Platform Owner has no tenant', async () => {
      await openReports(<ITAMConsole isSuperAdminView />);
      const run = await screen.findByRole('button', { name: 'Run Report' });
      expect(run).toBeDisabled();
      const note = screen.getByText(NOTE);
      expect(note).toHaveAttribute('role', 'status');
      expect(run).toHaveAttribute('aria-describedby', note.id);
      fireEvent.click(run);
      expect(runItamPrebuiltReport).not.toHaveBeenCalled();
    });

    it("a tenant user sees enabled Run Report buttons and no note", async () => {
      await openReports(<ITAMConsole />);
      const run = await screen.findByRole('button', { name: 'Run Report' });
      expect(run).toBeEnabled();
      expect(screen.queryByText(NOTE)).not.toBeInTheDocument();
      fireEvent.click(run);
      await waitFor(() => expect(runItamPrebuiltReport).toHaveBeenCalledWith('asset_value', 1, 50, undefined));
    });

    it("clears the previous tenant's result when the tenant changes, and when none is selected", async () => {
      const { rerender } = await openReports(<ITAMConsole isSuperAdminView tenantId="t-1" />);
      fireEvent.click(await screen.findByRole('button', { name: 'Run Report' }));
      expect(await screen.findByText('Laptop 1')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Export CSV/ })).toBeInTheDocument();

      rerender(<ITAMConsole isSuperAdminView tenantId="t-2" />);
      await waitFor(() => expect(screen.queryByText('Laptop 1')).not.toBeInTheDocument());
      expect(screen.queryByRole('button', { name: /Export CSV/ })).not.toBeInTheDocument();
      expect(screen.queryByRole('heading', { name: 'Asset Value', level: 3 })).not.toBeInTheDocument();

      fireEvent.click(await screen.findByRole('button', { name: 'Run Report' }));
      expect(await screen.findByText('Laptop 1')).toBeInTheDocument();
      rerender(<ITAMConsole isSuperAdminView />);
      await waitFor(() => expect(screen.queryByText('Laptop 1')).not.toBeInTheDocument());
      expect(screen.queryByRole('button', { name: /Export CSV/ })).not.toBeInTheDocument();
    });

    it('does not clear a drill-down run started on first mount', async () => {
      render(<ITAMConsole isSuperAdminView tenantId="t-1" />);
      fireEvent.click(screen.getByText('Reports'));
      await waitFor(() => expect(screen.getByText('Total Asset Value')).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /Total Asset Value/i }));
      expect(await screen.findByText('Laptop 1')).toBeInTheDocument();
      expect(runItamPrebuiltReport).toHaveBeenCalledWith('asset_value', 1, 50, 't-1');
    });

    it('a pre-built run for the previous tenant that resolves after the switch renders nothing', async () => {
      let resolveHeld: (v: unknown) => void = () => {};
      runItamPrebuiltReport.mockImplementationOnce(() => new Promise((resolve) => { resolveHeld = resolve; }));

      const { rerender } = await openReports(<ITAMConsole isSuperAdminView tenantId="t-1" />);
      fireEvent.click(await screen.findByRole('button', { name: 'Run Report' }));
      await waitFor(() => expect(runItamPrebuiltReport).toHaveBeenCalledWith('asset_value', 1, 50, 't-1'));

      rerender(<ITAMConsole isSuperAdminView tenantId="t-2" />);
      // Flush whatever the late response writes before asserting absence.
      await act(async () => {
        resolveHeld(assetValueResult);
        await new Promise((r) => setTimeout(r, 20));
      });
      expect(screen.queryByText('Laptop 1')).not.toBeInTheDocument();
      expect(screen.queryByRole('heading', { name: 'Asset Value', level: 3 })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Export CSV/ })).not.toBeInTheDocument();

      runItamPrebuiltReport.mockResolvedValueOnce({ ...assetValueResult, rows: [{ Name: 'Laptop 2' }] });
      fireEvent.click(await screen.findByRole('button', { name: 'Run Report' }));
      expect(await screen.findByText('Laptop 2')).toBeInTheDocument();
      expect(runItamPrebuiltReport).toHaveBeenLastCalledWith('asset_value', 1, 50, 't-2');
      expect(screen.queryByText('Laptop 1')).not.toBeInTheDocument();
    });
  });
});
