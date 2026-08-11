/**
 * Phase 63 (plan 63-02) LifecyclePanel Label action behavior:
 *  1. Rendering the panel with one asset shows a Label trigger in that row.
 *  2. Clicking Label reveals a menu containing QR Code.
 *  3. Clicking QR Code calls fetchAssetQrLabel exactly once with that row's asset id.
 *  4. After choosing an item the menu closes — QR Code is no longer in the document.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const fetchAssets = vi.fn();
const createManualAsset = vi.fn().mockResolvedValue({ id: 'asset-1', assetTag: 'WS-0042', hostname: 'ws-42', lifecycleStatus: 'deployable' });
const fetchCatalogEntities = vi.fn().mockResolvedValue([]);
const checkoutAsset = vi.fn().mockResolvedValue({});
const checkinAsset = vi.fn().mockResolvedValue({});
const markAssetAudited = vi.fn().mockResolvedValue({});
const fetchAssetHistory = vi.fn().mockResolvedValue({ assetId: 'asset-1', history: [] });
const fetchAssetQrLabel = vi.fn().mockResolvedValue(undefined);

vi.mock('../../services/apiService', () => ({
  fetchAssets: (...args: unknown[]) => fetchAssets(...args),
  createManualAsset: (...args: unknown[]) => createManualAsset(...args),
  fetchCatalogEntities: (...args: unknown[]) => fetchCatalogEntities(...args),
  checkoutAsset: (...args: unknown[]) => checkoutAsset(...args),
  checkinAsset: (...args: unknown[]) => checkinAsset(...args),
  markAssetAudited: (...args: unknown[]) => markAssetAudited(...args),
  fetchAssetHistory: (...args: unknown[]) => fetchAssetHistory(...args),
  fetchAssetQrLabel: (...args: unknown[]) => fetchAssetQrLabel(...args),
}));

vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { LifecyclePanel } from '../../components/itam/LifecyclePanel';

describe('LifecyclePanel - Label action', () => {
  beforeEach(() => {
    fetchAssets.mockReset();
    fetchAssetQrLabel.mockClear();
  });

  it('shows a Label trigger in the row', async () => {
    fetchAssets.mockResolvedValue([{ id: 'asset-1', assetTag: 'WS-0042', hostname: 'ws-42', lifecycleStatus: 'deployable' }]);
    render(<LifecyclePanel />);
    await waitFor(() => expect(screen.getByText('Label')).toBeInTheDocument());
  });

  it('clicking Label reveals a menu containing QR Code', async () => {
    fetchAssets.mockResolvedValue([{ id: 'asset-1', assetTag: 'WS-0042', hostname: 'ws-42', lifecycleStatus: 'deployable' }]);
    render(<LifecyclePanel />);
    await waitFor(() => expect(screen.getByText('Label')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Label'));
    await waitFor(() => expect(screen.getByText('QR Code')).toBeInTheDocument());
  });

  it('clicking QR Code calls fetchAssetQrLabel once with the asset id', async () => {
    fetchAssets.mockResolvedValue([{ id: 'asset-1', assetTag: 'WS-0042', hostname: 'ws-42', lifecycleStatus: 'deployable' }]);
    render(<LifecyclePanel />);
    await waitFor(() => expect(screen.getByText('Label')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Label'));
    await waitFor(() => expect(screen.getByText('QR Code')).toBeInTheDocument());
    fireEvent.click(screen.getByText('QR Code'));
    await waitFor(() => expect(fetchAssetQrLabel).toHaveBeenCalledTimes(1));
    expect(fetchAssetQrLabel).toHaveBeenCalledWith('asset-1');
  });

  it('menu closes after choosing an item — QR Code is no longer in the document', async () => {
    fetchAssets.mockResolvedValue([{ id: 'asset-1', assetTag: 'WS-0042', hostname: 'ws-42', lifecycleStatus: 'deployable' }]);
    render(<LifecyclePanel />);
    await waitFor(() => expect(screen.getByText('Label')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Label'));
    await waitFor(() => expect(screen.getByText('QR Code')).toBeInTheDocument());
    fireEvent.click(screen.getByText('QR Code'));
    await waitFor(() => expect(screen.queryByText('QR Code')).not.toBeInTheDocument());
  });
});