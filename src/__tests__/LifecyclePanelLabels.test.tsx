/**
 * Phase 63 (plan 63-02) LifecyclePanel Label action behavior:
 *  1. Rendering the panel with one asset shows a Label trigger in that row.
 *  2. Clicking Label reveals a menu containing QR Code.
 *  3. Clicking QR Code calls fetchAssetQrLabel exactly once with that row's asset id.
 *  4. After choosing an item the menu closes — QR Code is no longer in the document.
 *  5. Clicking Label then Barcode calls fetchAssetBarcodeLabel once with the asset id.
 *  6. Clicking Label then the label-sheet item calls fetchAssetLabelSheet with [assetId].
 *  7. A rejecting label function surfaces an error toast and closes the menu.
 *  8. A mousedown outside the open menu closes it.
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
const fetchAssetBarcodeLabel = vi.fn().mockResolvedValue(undefined);
const fetchAssetLabelSheet = vi.fn().mockResolvedValue(undefined);

vi.mock('../../services/apiService', () => ({
  fetchAssets: (...args: unknown[]) => fetchAssets(...args),
  createManualAsset: (...args: unknown[]) => createManualAsset(...args),
  fetchCatalogEntities: (...args: unknown[]) => fetchCatalogEntities(...args),
  checkoutAsset: (...args: unknown[]) => checkoutAsset(...args),
  checkinAsset: (...args: unknown[]) => checkinAsset(...args),
  markAssetAudited: (...args: unknown[]) => markAssetAudited(...args),
  fetchAssetHistory: (...args: unknown[]) => fetchAssetHistory(...args),
  fetchAssetQrLabel: (...args: unknown[]) => fetchAssetQrLabel(...args),
  fetchAssetBarcodeLabel: (...args: unknown[]) => fetchAssetBarcodeLabel(...args),
  fetchAssetLabelSheet: (...args: unknown[]) => fetchAssetLabelSheet(...args),
}));

const showToast = vi.fn();
vi.mock('../../utils/toast', () => ({ showToast: (...args: unknown[]) => showToast(...args) }));

import { LifecyclePanel } from '../../components/itam/LifecyclePanel';

describe('LifecyclePanel - Label action', () => {
  beforeEach(() => {
    fetchAssets.mockReset();
    fetchAssetQrLabel.mockClear();
    fetchAssetQrLabel.mockResolvedValue(undefined);
    fetchAssetBarcodeLabel.mockClear();
    fetchAssetBarcodeLabel.mockResolvedValue(undefined);
    fetchAssetLabelSheet.mockClear();
    fetchAssetLabelSheet.mockResolvedValue(undefined);
    showToast.mockClear();
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

  it('clicking Label then Barcode calls fetchAssetBarcodeLabel once with the asset id', async () => {
    fetchAssets.mockResolvedValue([{ id: 'asset-1', assetTag: 'WS-0042', hostname: 'ws-42', lifecycleStatus: 'deployable' }]);
    render(<LifecyclePanel />);
    await waitFor(() => expect(screen.getByText('Label')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Label'));
    await waitFor(() => expect(screen.getByText('Barcode')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Barcode'));
    await waitFor(() => expect(fetchAssetBarcodeLabel).toHaveBeenCalledTimes(1));
    expect(fetchAssetBarcodeLabel).toHaveBeenCalledWith('asset-1');
  });

  it('clicking Label then Label Sheet calls fetchAssetLabelSheet with a single-element array', async () => {
    fetchAssets.mockResolvedValue([{ id: 'asset-1', assetTag: 'WS-0042', hostname: 'ws-42', lifecycleStatus: 'deployable' }]);
    render(<LifecyclePanel />);
    await waitFor(() => expect(screen.getByText('Label')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Label'));
    await waitFor(() => expect(screen.getByText('Label Sheet (this asset)')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Label Sheet (this asset)'));
    await waitFor(() => expect(fetchAssetLabelSheet).toHaveBeenCalledTimes(1));
    expect(fetchAssetLabelSheet).toHaveBeenCalledWith(['asset-1']);
  });

  it('a rejecting label function surfaces an error toast and closes the menu', async () => {
    fetchAssets.mockResolvedValue([{ id: 'asset-1', assetTag: 'WS-0042', hostname: 'ws-42', lifecycleStatus: 'deployable' }]);
    fetchAssetQrLabel.mockRejectedValue(new Error('Failed to generate QR label'));
    render(<LifecyclePanel />);
    await waitFor(() => expect(screen.getByText('Label')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Label'));
    await waitFor(() => expect(screen.getByText('QR Code')).toBeInTheDocument());
    fireEvent.click(screen.getByText('QR Code'));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('Failed to generate QR label', 'error'));
    expect(screen.queryByText('QR Code')).not.toBeInTheDocument();
  });

  it('a mousedown outside the open menu closes it', async () => {
    fetchAssets.mockResolvedValue([{ id: 'asset-1', assetTag: 'WS-0042', hostname: 'ws-42', lifecycleStatus: 'deployable' }]);
    render(<LifecyclePanel />);
    await waitFor(() => expect(screen.getByText('Label')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Label'));
    await waitFor(() => expect(screen.getByText('QR Code')).toBeInTheDocument());
    fireEvent.mouseDown(document.body);
    await waitFor(() => expect(screen.queryByText('QR Code')).not.toBeInTheDocument());
  });
});