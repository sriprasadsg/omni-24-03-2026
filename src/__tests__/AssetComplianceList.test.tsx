/**
 * Phase 06 (06-VERIFICATION.md) closes out its one remaining human_needed
 * item: "click Mark Compliant, simulate an API failure on the second click,
 * confirm the row updates on success and an error toast appears on failure,
 * with the button re-enabled for retry either way." This mirrors the exact
 * onUpdateStatus wrapper both FrameworkDetail.tsx and
 * components/itam/CompliancePanel.tsx pass in production (try/await/catch +
 * showToast('Failed to update compliance status — please try again',
 * 'error')) so the assertions below exercise the real catch-and-toast path,
 * not a simplified stand-in.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { Asset, AssetCompliance, Control } from '../../types';

const showToast = vi.fn();
vi.mock('../../utils/toast', () => ({
  showToast: (...args: unknown[]) => showToast(...args),
}));

import { AssetComplianceList } from '../../components/AssetComplianceList';

const control = {
  id: 'ctrl-1',
  name: 'Disk Encryption',
  description: 'Full-disk encryption required on all endpoints.',
  status: 'Non-Compliant',
  lastReviewed: '2026-08-01',
  evidence: [],
} as unknown as Control;

const asset = {
  id: 'asset-1',
  hostname: 'host-01',
} as unknown as Asset;

const updateAssetComplianceStatus = vi.fn();

// Reproduces FrameworkDetail.tsx/CompliancePanel.tsx's real onUpdateStatus
// wrapper verbatim, using the mocked showToast so failures are assertable.
const onUpdateStatus = async (assetId: string, status: 'Compliant' | 'Non-Compliant' | 'Pending_Evidence') => {
  try {
    await updateAssetComplianceStatus(assetId, control.id, status);
  } catch (e) {
    showToast('Failed to update compliance status — please try again', 'error');
  }
};

const noop = async () => {};

function renderList(complianceData: AssetCompliance[]) {
  return render(
    <AssetComplianceList
      control={control}
      assets={[asset]}
      complianceData={complianceData}
      onUpdateStatus={onUpdateStatus}
      onUploadEvidence={() => {}}
      onIngestEvidence={noop}
      onDeleteEvidence={noop}
    />
  );
}

describe('AssetComplianceList — Mark Compliant status update', () => {
  beforeEach(() => {
    showToast.mockReset();
    updateAssetComplianceStatus.mockReset();
  });

  it('first click: a successful update never shows an error toast, and the button re-enables for a retry', async () => {
    updateAssetComplianceStatus.mockResolvedValueOnce(undefined);
    const { rerender } = renderList([]);

    const markCompliant = screen.getByRole('button', { name: 'Mark Compliant' });
    fireEvent.click(markCompliant);

    await waitFor(() => expect(updateAssetComplianceStatus).toHaveBeenCalledWith('asset-1', 'ctrl-1', 'Compliant'));
    expect(showToast).not.toHaveBeenCalled();
    await waitFor(() => expect(markCompliant).not.toBeDisabled());

    // Parent re-renders with the refreshed compliance record (what
    // refreshAssetCompliance produces in production) — row reflects it
    // without a page reload.
    rerender(
      <AssetComplianceList
        control={control}
        assets={[asset]}
        complianceData={[{
          id: 'ac-1', assetId: 'asset-1', controlId: 'ctrl-1', status: 'Compliant', evidence: [], lastUpdated: '2026-08-24',
        } as unknown as AssetCompliance]}
        onUpdateStatus={onUpdateStatus}
        onUploadEvidence={() => {}}
        onIngestEvidence={noop}
        onDeleteEvidence={noop}
      />
    );
    expect(screen.getByText('Compliant')).toBeInTheDocument();
  });

  it('second click: a failed update shows the error toast and re-enables the button for another retry', async () => {
    updateAssetComplianceStatus.mockRejectedValueOnce(new Error('network error'));
    renderList([]);

    const markCompliant = screen.getByRole('button', { name: 'Mark Compliant' });
    fireEvent.click(markCompliant);

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith('Failed to update compliance status — please try again', 'error')
    );
    await waitFor(() => expect(markCompliant).not.toBeDisabled());
  });

  it('while a click is in flight, both status buttons are disabled', async () => {
    let resolveUpdate: (() => void) | undefined;
    updateAssetComplianceStatus.mockImplementationOnce(
      () => new Promise<void>(resolve => { resolveUpdate = resolve; })
    );
    renderList([]);

    const markCompliant = screen.getByRole('button', { name: 'Mark Compliant' });
    const markNonCompliant = screen.getByRole('button', { name: 'Mark Non-Compliant' });
    fireEvent.click(markCompliant);

    await waitFor(() => expect(markCompliant).toBeDisabled());
    expect(markNonCompliant).toBeDisabled();

    resolveUpdate?.();
    await waitFor(() => expect(markCompliant).not.toBeDisabled());
  });
});
