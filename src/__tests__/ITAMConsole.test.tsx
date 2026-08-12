/**
 * Phase 61 (plan 61-01) smoke tests for the ITAM console shell:
 *  1. All 6 tabs render, defaulting to Catalog.
 *  2. Tab switching mounts the corresponding panel.
 *  3. Each panel renders without crashing given empty/loading API responses.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

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
  getItamSettings: vi.fn().mockResolvedValue({ branding: { companyName: '', logoUrl: '', primaryColor: '#0891b2' }, locale: 'en' }),
  saveItamSettings: vi.fn(),
  authFetch: vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
  API_BASE: '/api',
}));

vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import ITAMConsole from '../../components/itam/ITAMConsole';

describe('ITAMConsole', () => {
  it('renders all 9 tabs and defaults to Catalog', async () => {
    render(<ITAMConsole />);
    expect(screen.getByText('Catalog')).toBeInTheDocument();
    expect(screen.getByText('Check-Out/In')).toBeInTheDocument();
    expect(screen.getByText('Procurement & Finance')).toBeInTheDocument();
    expect(screen.getByText('Licenses & Consumables')).toBeInTheDocument();
    expect(screen.getByText('Compliance')).toBeInTheDocument();
    expect(screen.getByText('Software Inventory')).toBeInTheDocument();
    expect(screen.getByText('Activity')).toBeInTheDocument();
    expect(screen.getByText('Import / Export')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Manufacturers')).toBeInTheDocument());
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
});
