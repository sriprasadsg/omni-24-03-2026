/**
 * Phase 61 (plan 61-01) smoke tests for the ITAM console shell, extended by
 * Phase 72 (plan 72-01) for the Reports tab:
 *  1. All 11 tabs render, defaulting to Catalog.
 *  2. Tab switching mounts the corresponding panel.
 *  3. Each panel renders without crashing given empty/loading API responses.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const getItamSettings = vi.fn();
const runItamPrebuiltReport = vi.fn();
const fetchItamKpis = vi.fn();

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
  fetchItamPrebuiltReports: vi.fn().mockResolvedValue([]),
  runItamPrebuiltReport: (...args: unknown[]) => runItamPrebuiltReport(...args),
  fetchItamKpis: (...args: unknown[]) => fetchItamKpis(...args),
  generateItamReport: vi.fn(),
  downloadItamReport: vi.fn(),
  fetchItamReportFields: vi.fn().mockResolvedValue([]),
  saveItamCustomReport: vi.fn(),
  listItamCustomReports: vi.fn().mockResolvedValue([]),
  deleteItamCustomReport: vi.fn(),
  previewItamCustomReport: vi.fn(),
  runItamCustomReport: vi.fn(),
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

    await waitFor(() => expect(runItamPrebuiltReport).toHaveBeenCalledWith('asset_value', 1, 50));
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
});
