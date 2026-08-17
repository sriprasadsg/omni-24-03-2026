/**
 * Phase 65 (plan 65-03) BulkImportExportPanel behavior.
 * Task 1: export section —
 *  1. Clicking the export button calls exportItamAssetsCsv.
 *  2. Passes a trimmed model id filter through.
 *  3. A rejected export surfaces an error message in the panel.
 * Task 3: import section —
 *  4. Choosing a file and clicking Import calls importItamAssetsCsv with
 *     that file and dryRun true by default.
 *  5. Unchecking dry run passes false.
 *  6. A result with two errors renders both row numbers and their problems.
 *  7. A rejected import renders the error message.
 *  8. The import button is disabled before a file is chosen.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const exportItamAssetsCsv = vi.fn();
const importItamAssetsCsv = vi.fn();

vi.mock('../../services/apiService', () => ({
  exportItamAssetsCsv: (...args: unknown[]) => exportItamAssetsCsv(...args),
  importItamAssetsCsv: (...args: unknown[]) => importItamAssetsCsv(...args),
}));

vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { BulkImportExportPanel } from '../../components/itam/BulkImportExportPanel';

function makeCsvFile(name = 'assets.csv'): File {
  return new File(['name,assetTag\nLaptop A,IT-0001\n'], name, { type: 'text/csv' });
}

describe('BulkImportExportPanel', () => {
  beforeEach(() => {
    exportItamAssetsCsv.mockReset();
    importItamAssetsCsv.mockReset();
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

  it('the import button is disabled before a file is chosen', () => {
    render(<BulkImportExportPanel />);
    expect(screen.getByRole('button', { name: 'Import assets' })).toBeDisabled();
  });

  it('choosing a file and clicking Import calls importItamAssetsCsv with dryRun true by default', async () => {
    importItamAssetsCsv.mockResolvedValue({ created: 0, skipped: 0, dryRun: true, errors: [] });
    const file = makeCsvFile();

    render(<BulkImportExportPanel />);
    fireEvent.change(screen.getByLabelText('CSV file'), { target: { files: [file] } });
    expect(screen.getByRole('button', { name: 'Import assets' })).not.toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Import assets' }));

    await waitFor(() => expect(importItamAssetsCsv).toHaveBeenCalledWith(file, true));
  });

  it('unchecking dry run passes false', async () => {
    importItamAssetsCsv.mockResolvedValue({ created: 1, skipped: 0, dryRun: false, errors: [] });
    const file = makeCsvFile();

    render(<BulkImportExportPanel />);
    fireEvent.change(screen.getByLabelText('CSV file'), { target: { files: [file] } });
    fireEvent.click(screen.getByLabelText('Validate only (dry run)'));
    fireEvent.click(screen.getByRole('button', { name: 'Import assets' }));

    await waitFor(() => expect(importItamAssetsCsv).toHaveBeenCalledWith(file, false));
  });

  it('a result with two errors renders both row numbers and their problems', async () => {
    importItamAssetsCsv.mockResolvedValue({
      created: 1,
      skipped: 2,
      dryRun: true,
      errors: [
        { row: 2, problems: ["modelId 'model-x' not found."] },
        { row: 3, problems: ["Value for 'os' is not one of the allowed options."] },
      ],
    });
    const file = makeCsvFile();

    render(<BulkImportExportPanel />);
    fireEvent.change(screen.getByLabelText('CSV file'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: 'Import assets' }));

    await waitFor(() => expect(screen.getByText("modelId 'model-x' not found.")).toBeInTheDocument());
    expect(screen.getByText("Value for 'os' is not one of the allowed options.")).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('a rejected import renders the error message', async () => {
    importItamAssetsCsv.mockRejectedValue(new Error('File is too large to import.'));
    const file = makeCsvFile();

    render(<BulkImportExportPanel />);
    fireEvent.change(screen.getByLabelText('CSV file'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: 'Import assets' }));

    await waitFor(() => expect(screen.getByText('File is too large to import.')).toBeInTheDocument());
  });
});
