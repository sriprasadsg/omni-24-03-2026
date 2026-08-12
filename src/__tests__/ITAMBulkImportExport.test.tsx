/**
 * Phase 65 (plan 65-03) BulkImportExportPanel behavior.
 * Task 1: export section only —
 *  1. Clicking the export button calls exportItamAssetsCsv.
 *  2. A rejected export surfaces an error message in the panel.
 * Task 3 adds the import-section tests below this file's existing coverage.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const exportItamAssetsCsv = vi.fn();

vi.mock('../../services/apiService', () => ({
  exportItamAssetsCsv: (...args: unknown[]) => exportItamAssetsCsv(...args),
}));

vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { BulkImportExportPanel } from '../../components/itam/BulkImportExportPanel';

describe('BulkImportExportPanel', () => {
  beforeEach(() => {
    exportItamAssetsCsv.mockReset();
  });

  it('clicking the export button calls exportItamAssetsCsv', async () => {
    exportItamAssetsCsv.mockResolvedValue(undefined);

    render(<BulkImportExportPanel />);
    fireEvent.click(screen.getByRole('button', { name: 'Export assets CSV' }));

    await waitFor(() => expect(exportItamAssetsCsv).toHaveBeenCalledWith(undefined));
  });

  it('passes a trimmed model id filter through to exportItamAssetsCsv', async () => {
    exportItamAssetsCsv.mockResolvedValue(undefined);

    render(<BulkImportExportPanel />);
    fireEvent.change(screen.getByLabelText('Model ID filter'), { target: { value: '  model-abc12345  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Export assets CSV' }));

    await waitFor(() => expect(exportItamAssetsCsv).toHaveBeenCalledWith('model-abc12345'));
  });

  it('a rejected export surfaces an error message', async () => {
    exportItamAssetsCsv.mockRejectedValue(new Error('Failed to export assets'));

    render(<BulkImportExportPanel />);
    fireEvent.click(screen.getByRole('button', { name: 'Export assets CSV' }));

    await waitFor(() => expect(screen.getByText('Failed to export assets')).toBeInTheDocument());
  });
});
