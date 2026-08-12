import React, { useState } from 'react';
import { exportItamAssetsCsv } from '../../services/apiService';
import { showToast } from '../../utils/toast';

// ITAM CSV Import / Export tab (Phase 65 Plan 03, ITAM-DAT-03). Task 1
// ships the Export section end-to-end; the Import section (upload, dry
// run, per-row failure report) lands in Task 3.
export function BulkImportExportPanel() {
  const [modelId, setModelId] = useState('');
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setExporting(true);
    setError(null);
    try {
      await exportItamAssetsCsv(modelId.trim() || undefined);
      showToast('Export started — your download should begin shortly.', 'success');
    } catch (e: any) {
      const message = e?.message || 'Export failed.';
      setError(message);
      showToast(message, 'error');
    } finally {
      setExporting(false);
    }
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
        {error && <p className="text-red-400 text-xs mt-3">{error}</p>}
      </div>
    </div>
  );
}
