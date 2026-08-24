/**
 * Phase 71 gap closure (T-71-04 visibility half): purchase_order_id was
 * write-only — accepted and validated by the backend, but never displayed
 * anywhere in the reachable frontend. This proves the "Linked Purchase
 * Order" field on FinancePanel actually surfaces it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const fetchAssets = vi.fn();
const fetchPurchaseOrders = vi.fn();
const fetchAssetBookValue = vi.fn();
const fetchAssetWarranty = vi.fn();
const updateAssetPurchase = vi.fn();

vi.mock('../../services/apiService', () => ({
  fetchAssets: (...args: unknown[]) => fetchAssets(...args),
  fetchPurchaseOrders: (...args: unknown[]) => fetchPurchaseOrders(...args),
  fetchAssetBookValue: (...args: unknown[]) => fetchAssetBookValue(...args),
  fetchAssetWarranty: (...args: unknown[]) => fetchAssetWarranty(...args),
  updateAssetPurchase: (...args: unknown[]) => updateAssetPurchase(...args),
}));

vi.mock('../../utils/toast', () => ({
  showToast: vi.fn(),
}));

import { FinancePanel } from '../../components/itam/FinancePanel';

const PO = {
  id: 'po-1', tenantId: 'tenant-a', order_number: 'PO-001', supplier_name: 'Acme Supplies',
  order_date: '2026-08-01T00:00:00Z', total_cost: 250,
  items: [{ name: 'Laptop', quantity: 5, unit_price: 50 }],
  createdAt: '2026-08-01T00:00:00Z', updatedAt: '2026-08-01T00:00:00Z',
};

const assetWithLink = { id: 'a-1', hostname: 'host-1', purchase_order_id: 'po-1' };
const assetWithoutLink = { id: 'a-2', hostname: 'host-2' };
const assetWithDanglingLink = { id: 'a-3', hostname: 'host-3', purchase_order_id: 'po-missing' };

describe('FinancePanel — linked purchase order visibility', () => {
  beforeEach(() => {
    fetchAssets.mockReset();
    fetchPurchaseOrders.mockReset();
    fetchAssetBookValue.mockReset();
    fetchAssetWarranty.mockReset();
    updateAssetPurchase.mockReset();
    fetchAssetBookValue.mockResolvedValue({ purchaseCostCents: null, bookValueCents: null, reason: 'no_purchase_record' });
    fetchAssetWarranty.mockResolvedValue({ purchaseDate: null, warrantyMonths: null, warrantyStatus: 'none', warrantyExpiresAt: null, daysToExpiry: null });
  });

  it('shows the linked purchase order number for an asset with purchase_order_id set', async () => {
    fetchAssets.mockResolvedValue([assetWithLink]);
    fetchPurchaseOrders.mockResolvedValue([PO]);
    render(<FinancePanel />);

    await waitFor(() => expect(screen.getByLabelText('Asset')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Asset'), { target: { value: 'a-1' } });

    await waitFor(() => expect(screen.getByTestId('linked-purchase-order')).toHaveTextContent('PO-001'));
  });

  it('shows "None" for an asset with no purchase_order_id', async () => {
    fetchAssets.mockResolvedValue([assetWithoutLink]);
    fetchPurchaseOrders.mockResolvedValue([PO]);
    render(<FinancePanel />);

    await waitFor(() => expect(screen.getByLabelText('Asset')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Asset'), { target: { value: 'a-2' } });

    await waitFor(() => expect(screen.getByTestId('linked-purchase-order')).toHaveTextContent('None'));
  });

  it('falls back to the raw id if the linked purchase order is not found in the list', async () => {
    fetchAssets.mockResolvedValue([assetWithDanglingLink]);
    fetchPurchaseOrders.mockResolvedValue([PO]);
    render(<FinancePanel />);

    await waitFor(() => expect(screen.getByLabelText('Asset')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Asset'), { target: { value: 'a-3' } });

    await waitFor(() => expect(screen.getByTestId('linked-purchase-order')).toHaveTextContent('po-missing'));
  });
});
