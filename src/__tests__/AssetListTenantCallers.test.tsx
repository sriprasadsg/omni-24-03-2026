/**
 * Screens that list assets ask for the tenant the Platform Owner selected: the ITAM console and
 * its Check-Out/In and Procurement & Finance tabs (tenantId prop), the Persistence Detection and
 * Security Simulation pickers (tenantId prop from App's viewingTenantId). Without a selected
 * tenant they still ask for the all-tenants list, and a changed selection asks again.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const fetchAssets = vi.fn();

vi.mock('../../services/apiService', () => ({
  fetchAssets: (...args: unknown[]) => fetchAssets(...args),
  fetchCatalogEntities: vi.fn().mockResolvedValue([]),
  getItamSettings: vi.fn().mockResolvedValue({ branding: { companyName: '', logoUrl: '', primaryColor: '#0891b2' }, locale: 'en' }),
  fetchPurchaseOrders: vi.fn().mockResolvedValue([]),
  fetchAssetBookValue: vi.fn().mockResolvedValue({}),
  fetchAssetWarranty: vi.fn().mockResolvedValue({}),
  updateAssetPurchase: vi.fn(),
  createManualAsset: vi.fn(),
  checkoutAsset: vi.fn(),
  checkinAsset: vi.fn(),
  markAssetAudited: vi.fn(),
  fetchAssetQrLabel: vi.fn(),
  fetchAssetBarcodeLabel: vi.fn(),
  fetchAssetLabelSheet: vi.fn(),
  getTicketingConfig: vi.fn().mockResolvedValue({}),
  createItamTicket: vi.fn(),
  fetchPersistenceResults: vi.fn().mockResolvedValue(null),
  triggerPersistenceScan: vi.fn(),
  fetchSimulationHistory: vi.fn().mockResolvedValue([]),
  triggerProcessInjectionSimulation: vi.fn(),
  authFetch: vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
  API_BASE: '/api',
}));

vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import ITAMConsole from '../../components/itam/ITAMConsole';
import { PersistenceDashboard } from '../../components/PersistenceDashboard';
import { SecuritySimulation } from '../../components/SecuritySimulation';

const lastCall = () => fetchAssets.mock.calls[fetchAssets.mock.calls.length - 1];

describe('asset list callers pass the selected tenant', () => {
  beforeEach(() => {
    fetchAssets.mockReset();
    fetchAssets.mockResolvedValue([]);
  });

  it('ITAMConsole asks for the selected tenant\'s assets', async () => {
    render(<ITAMConsole tenantId="tenant-a" />);
    await waitFor(() => expect(fetchAssets).toHaveBeenCalledWith('tenant-a'));
  });

  it('ITAMConsole asks for the all-tenants list when no tenant is selected', async () => {
    render(<ITAMConsole tenantId={null} />);
    await waitFor(() => expect(fetchAssets).toHaveBeenCalled());
    expect(lastCall()[0]).toBeUndefined();
  });

  it('ITAMConsole asks again when the selected tenant changes', async () => {
    const { rerender } = render(<ITAMConsole tenantId="tenant-a" />);
    await waitFor(() => expect(fetchAssets).toHaveBeenCalledWith('tenant-a'));
    rerender(<ITAMConsole tenantId="tenant-b" />);
    await waitFor(() => expect(fetchAssets).toHaveBeenCalledWith('tenant-b'));
  });

  it('the Check-Out/In tab asks for the selected tenant\'s assets', async () => {
    render(<ITAMConsole tenantId="tenant-a" />);
    await waitFor(() => expect(fetchAssets).toHaveBeenCalled());
    fetchAssets.mockClear();
    fireEvent.click(screen.getByText('Check-Out/In'));
    await waitFor(() => expect(fetchAssets).toHaveBeenCalledWith('tenant-a'));
  });

  it('the Procurement & Finance tab asks for the selected tenant\'s assets', async () => {
    render(<ITAMConsole tenantId="tenant-a" />);
    await waitFor(() => expect(fetchAssets).toHaveBeenCalled());
    fetchAssets.mockClear();
    fireEvent.click(screen.getByText('Procurement & Finance'));
    await waitFor(() => expect(fetchAssets).toHaveBeenCalledWith('tenant-a'));
  });

  it('Persistence Detection asks for the selected tenant\'s assets', async () => {
    render(<PersistenceDashboard tenantId="tenant-a" />);
    await waitFor(() => expect(fetchAssets).toHaveBeenCalledWith('tenant-a'));
  });

  it('Security Simulation asks for the selected tenant\'s assets', async () => {
    render(<SecuritySimulation tenantId="tenant-a" />);
    await waitFor(() => expect(fetchAssets).toHaveBeenCalledWith('tenant-a'));
  });

  it('Persistence Detection and Security Simulation ask for all tenants without a selection', async () => {
    render(<PersistenceDashboard />);
    await waitFor(() => expect(fetchAssets).toHaveBeenCalledTimes(1));
    expect(lastCall()[0]).toBeUndefined();
    fetchAssets.mockClear();
    render(<SecuritySimulation tenantId={null} />);
    await waitFor(() => expect(fetchAssets).toHaveBeenCalledTimes(1));
    expect(lastCall()[0]).toBeUndefined();
  });
});
