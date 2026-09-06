import React, { useRef, useState } from 'react';
import { exportItamAssetsCsv, importItamAssetsCsv } from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { ItamImportResult } from '../../types';

// ITAM CSV Import / Export tab (Phase 65 Plan 03, ITAM-DAT-03). Task 1
// shipped the Export section end-to-end; this adds the Import section —
// upload, dry run, and a readable per-row failure report. There is no
// existing file-upload component anywhere in this frontend (65-PATTERNS.md
// "No Analog Found"), so this is a hand-rolled <input type="file"> plus
// FormData, no library.
export function BulkImportExportPanel() {
  const [modelId, setModelId] = useState('');
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [dryRun, setDryRun] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [result, setResult] = useState<ItamImportResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  async function handleExport() {
    setExporting(true);
    setExportError(null);
    try {
      const result = await exportItamAssetsCsv(modelId.trim() || undefined);
      if (result?.truncated) {
        showToast(
          'Export started, but your inventory exceeds the export row limit — the CSV is truncated and does not contain every asset.',
          'warning'
        );
      } else {
        showToast('Export started — your download should begin shortly.', 'success');
      }
    } catch (e: any) {
      const message = e?.message || 'Export failed.';
      setExportError(message);
      showToast(message, 'error');
    } finally {
      setExporting(false);
    }
  }

  async function handleImport() {
    if (!file) return;
    setImporting(true);
    setImportError(null);
    try {
      const importResult = await importItamAssetsCsv(file, dryRun);
      setResult(importResult);
      showToast(
        importResult.dryRun
          ? `Dry run: ${importResult.created} row(s) would be created, ${importResult.skipped} skipped.`
          : `Import complete: ${importResult.created} created, ${importResult.skipped} skipped.`,
        'success'
      );
    } catch (e: any) {
      const message = e?.message || 'Import failed.';
      setImportError(message);
      showToast(message, 'error');
    } finally {
      setImporting(false);
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    setFile(e.target.files && e.target.files[0] ? e.target.files[0] : null);
    setResult(null);
    setImportError(null);
  }

  function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  return (
    <div className="space-y-6">
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
        <h2 className="text-sm font-semibold text-white mb-1">Export assets</h2>
        <p className="text-gray-400 text-xs mb-4">
          Download every asset in your tenant as a CSV file, including one column per custom field.
          Leave the model filter blank to export the full inventory.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="itam-export-model-id" className="block text-xs text-gray-500 mb-1">
              Model ID (optional)
            </label>
            <input
              id="itam-export-model-id"
              className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white w-64"
              placeholder="e.g. model-abc12345"
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              aria-label="Model ID filter"
            />
          </div>
          <button
            onClick={handleExport}
            disabled={exporting}
            className="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
          >
            {exporting ? 'Exporting…' : 'Export assets CSV'}
          </button>
        </div>
        {exportError && <p className="text-red-400 text-xs mt-3">{exportError}</p>}
      </div>

      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
        <h2 className="text-sm font-semibold text-white mb-1">Import assets</h2>
        <p className="text-gray-400 text-xs mb-4">
          Upload a CSV of assets. Columns match an Export — use Export above to get a correctly-shaped
          template, then edit it and re-upload. Custom fields go in <code>customFields.&lt;key&gt;</code> columns.
        </p>

        <div className="space-y-3">
          <div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              aria-label="CSV file"
              onChange={handleFileChange}
              className="block w-full text-xs text-gray-400 file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:bg-gray-700 file:text-white file:text-xs file:font-semibold"
            />
            {file && (
              <p className="text-gray-500 text-xs mt-1">
                {file.name} ({formatSize(file.size)})
              </p>
            )}
          </div>

          <label className="flex items-center gap-2 text-xs text-gray-400">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              aria-label="Validate only (dry run)"
            />
            Validate only (dry run) — recommended for a first look at an unfamiliar file
          </label>

          <button
            onClick={handleImport}
            disabled={!file || importing}
            className="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
          >
            {importing ? 'Importing…' : 'Import assets'}
          </button>

          {importError && <p className="text-red-400 text-xs">{importError}</p>}

          {result && (
            <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 mt-3">
              {result.dryRun && (
                <p className="text-yellow-400 text-xs font-semibold mb-2">
                  Dry run — nothing was written.
                </p>
              )}
              <p className="text-white text-sm mb-2">
                Created: {result.created} · Skipped: {result.skipped}
              </p>
              {result.errors.length > 0 && (
                <div>
                  {result.errorsTruncated && (
                    <p className="text-gray-500 text-xs mb-1">
                      Showing the first {result.errors.length} error(s); the full list is longer.
                    </p>
                  )}
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-gray-500 border-b border-gray-800">
                        <th className="py-1 pr-3">Row</th>
                        <th className="py-1">Problems</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.errors.map((err) => (
                        <tr key={err.row} className="border-b border-gray-800">
                          <td className="py-1 pr-3 text-gray-300">{err.row}</td>
                          <td className="py-1 text-red-400">{err.problems.join('; ')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
