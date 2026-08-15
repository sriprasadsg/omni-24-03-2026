/**
 * Phase 61 (plan 61-01) CatalogPanel behavior:
 *  1. Lists entities for the default kind (manufacturers).
 *  2. Switching kind refetches the new kind.
 *  3. "Add Manufacturer" -> save calls createCatalogEntity and refreshes the list.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const fetchCatalogEntities = vi.fn();
const createCatalogEntity = vi.fn().mockResolvedValue({ id: 'mf-1', name: 'Dell', tenantId: 't1' });
const deleteCatalogEntity = vi.fn().mockResolvedValue(undefined);

vi.mock('../../services/apiService', () => ({
  fetchCatalogEntities: (...args: unknown[]) => fetchCatalogEntities(...args),
  createCatalogEntity: (...args: unknown[]) => createCatalogEntity(...args),
  deleteCatalogEntity: (...args: unknown[]) => deleteCatalogEntity(...args),
}));

vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { CatalogPanel } from '../../components/itam/CatalogPanel';

describe('CatalogPanel', () => {
  beforeEach(() => {
    fetchCatalogEntities.mockReset();
    createCatalogEntity.mockClear();
  });

  it('lists manufacturers by default', async () => {
    fetchCatalogEntities.mockResolvedValue([{ id: 'mf-1', name: 'Dell', tenantId: 't1' }]);
    render(<CatalogPanel />);
    await waitFor(() => expect(screen.getByText('Dell')).toBeInTheDocument());
    expect(fetchCatalogEntities).toHaveBeenCalledWith('manufacturers');
  });

  it('switching to Categories refetches that kind', async () => {
    fetchCatalogEntities.mockResolvedValue([]);
    render(<CatalogPanel />);
    await waitFor(() => expect(fetchCatalogEntities).toHaveBeenCalledWith('manufacturers'));
    fireEvent.click(screen.getByText('Categories'));
    await waitFor(() => expect(fetchCatalogEntities).toHaveBeenCalledWith('categories'));
  });

  it('creating a manufacturer calls createCatalogEntity and reloads the list', async () => {
    fetchCatalogEntities.mockResolvedValue([]);
    render(<CatalogPanel />);
    await waitFor(() => expect(screen.getByText('No manufacturers yet')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Add Manufacturer'));
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Dell' } });
    fireEvent.click(screen.getByText('Save'));

    await waitFor(() =>
      expect(createCatalogEntity).toHaveBeenCalledWith('manufacturers', { name: 'Dell', notes: undefined })
    );
    expect(fetchCatalogEntities).toHaveBeenCalledTimes(2);
  });
});
