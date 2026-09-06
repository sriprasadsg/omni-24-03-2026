/**
 * Phase 71 gap closure (ITAM-PRO-01, SC1): PurchaseOrdersPanel replaces the
 * disconnected frontend/ tree (never imported by App.tsx, and it didn't even
 * compile — react-router-dom was missing from package.json). This is the
 * real, reachable console tab.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const fetchPurchaseOrders = vi.fn();
const createPurchaseOrder = vi.fn();
const updatePurchaseOrder = vi.fn();
const deletePurchaseOrder = vi.fn();
const showToast = vi.fn();

vi.mock('../../services/apiService', () => ({
  fetchPurchaseOrders: (...args: unknown[]) => fetchPurchaseOrders(...args),
  createPurchaseOrder: (...args: unknown[]) => createPurchaseOrder(...args),
  updatePurchaseOrder: (...args: unknown[]) => updatePurchaseOrder(...args),
  deletePurchaseOrder: (...args: unknown[]) => deletePurchaseOrder(...args),
}));

vi.mock('../../utils/toast', () => ({
  showToast: (...args: unknown[]) => showToast(...args),
}));

import { PurchaseOrdersPanel } from '../../components/itam/PurchaseOrdersPanel';

const PO = {
  id: 'po-1', tenantId: 'tenant-a', order_number: 'PO-001', supplier_name: 'Acme Supplies',
  order_date: '2026-08-01T00:00:00Z', total_cost: 250, notes: 'Q3 restock',
  items: [{ name: 'Laptop', quantity: 5, unit_price: 50 }],
  createdAt: '2026-08-01T00:00:00Z', updatedAt: '2026-08-01T00:00:00Z',
};

describe('PurchaseOrdersPanel', () => {
  beforeEach(() => {
    fetchPurchaseOrders.mockReset();
    createPurchaseOrder.mockReset();
    updatePurchaseOrder.mockReset();
    deletePurchaseOrder.mockReset();
    showToast.mockReset();
    window.confirm = vi.fn(() => true);
  });

  it('lists purchase orders with order number, supplier, and total', async () => {
    fetchPurchaseOrders.mockResolvedValue([PO]);
    render(<PurchaseOrdersPanel />);
    await waitFor(() => expect(screen.getByText('PO-001')).toBeInTheDocument());
    expect(screen.getByText('Acme Supplies')).toBeInTheDocument();
    expect(screen.getByText('$250.00')).toBeInTheDocument();
  });

  it('empty state renders when there are no purchase orders', async () => {
    fetchPurchaseOrders.mockResolvedValue([]);
    render(<PurchaseOrdersPanel />);
    await waitFor(() => expect(screen.getByText('No purchase orders yet')).toBeInTheDocument());
  });

  it('create: submits order number, supplier, date, items, and a computed total', async () => {
    fetchPurchaseOrders.mockResolvedValue([]);
    createPurchaseOrder.mockResolvedValue(PO);
    render(<PurchaseOrdersPanel />);
    await waitFor(() => expect(screen.getByText('No purchase orders yet')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'New Purchase Order' }));
    fireEvent.change(screen.getByLabelText('Order Number'), { target: { value: 'PO-002' } });
    fireEvent.change(screen.getByLabelText('Supplier Name'), { target: { value: 'Beta Corp' } });
    fireEvent.change(screen.getByLabelText('Order Date'), { target: { value: '2026-08-20' } });
    fireEvent.change(screen.getByLabelText('Item 1 name'), { target: { value: 'Monitor' } });
    fireEvent.change(screen.getByLabelText('Item 1 quantity'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Item 1 unit price'), { target: { value: '100' } });

    expect(screen.getByText('Total: $200.00')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(createPurchaseOrder).toHaveBeenCalledTimes(1));
    expect(createPurchaseOrder).toHaveBeenCalledWith({
      order_number: 'PO-002',
      supplier_name: 'Beta Corp',
      order_date: '2026-08-20',
      total_cost: 200,
      items: [{ name: 'Monitor', quantity: 2, unit_price: 100 }],
      notes: undefined,
    });
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('Purchase order created.', 'success'));
  });

  it('add/remove item rows: cannot remove the last remaining row', async () => {
    fetchPurchaseOrders.mockResolvedValue([]);
    render(<PurchaseOrdersPanel />);
    await waitFor(() => expect(screen.getByText('No purchase orders yet')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'New Purchase Order' }));

    fireEvent.click(screen.getByRole('button', { name: 'Add item' }));
    expect(screen.getByLabelText('Item 2 name')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Remove item 2' }));
    expect(screen.queryByLabelText('Item 2 name')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove item 1' })).toBeDisabled();
  });

  it('edit: opens pre-filled and calls updatePurchaseOrder with the edited id', async () => {
    fetchPurchaseOrders.mockResolvedValue([PO]);
    updatePurchaseOrder.mockResolvedValue({ ...PO, supplier_name: 'Acme Supplies Inc.' });
    render(<PurchaseOrdersPanel />);
    await waitFor(() => expect(screen.getByText('PO-001')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    expect(screen.getByDisplayValue('PO-001')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Acme Supplies')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Supplier Name'), { target: { value: 'Acme Supplies Inc.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(updatePurchaseOrder).toHaveBeenCalledTimes(1));
    expect(updatePurchaseOrder).toHaveBeenCalledWith('po-1', expect.objectContaining({ supplier_name: 'Acme Supplies Inc.' }));
  });

  it('delete: confirms, calls deletePurchaseOrder, and reloads the list', async () => {
    fetchPurchaseOrders.mockResolvedValueOnce([PO]).mockResolvedValueOnce([]);
    deletePurchaseOrder.mockResolvedValue(undefined);
    render(<PurchaseOrdersPanel />);
    await waitFor(() => expect(screen.getByText('PO-001')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Delete purchase order PO-001' }));

    await waitFor(() => expect(deletePurchaseOrder).toHaveBeenCalledWith('po-1'));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('Purchase order deleted.', 'success'));
  });

  it('delete: a rejected call shows an error toast and never a success toast', async () => {
    fetchPurchaseOrders.mockResolvedValue([PO]);
    deletePurchaseOrder.mockRejectedValue(new Error('network error'));
    render(<PurchaseOrdersPanel />);
    await waitFor(() => expect(screen.getByText('PO-001')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Delete purchase order PO-001' }));

    await waitFor(() => expect(showToast).toHaveBeenCalledWith('network error', 'error'));
    expect(showToast).not.toHaveBeenCalledWith('Purchase order deleted.', 'success');
  });
});
