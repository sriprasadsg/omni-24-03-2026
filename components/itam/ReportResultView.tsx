import React from 'react';
import type { ItamReportRunResult } from '../../services/apiService';
import { DownloadIcon } from '../icons';

export type ExportFormat = 'pdf' | 'xlsx' | 'csv';

// The one report on screen: its identity and its rows change together, so the title,
// export target and page controls can never describe a different report than the rows
// (WR-04). kind and key are null for the unsaved builder preview (Phase 72 D-02), which
// renders rows but has no stable id to export or page.
export interface ShownReport {
  kind: 'prebuilt' | 'custom' | null;
  key: string | null;
  page: number;
  data: ItamReportRunResult;
}

interface ReportResultViewProps {
  shown: ShownReport | null;
  // Title of the run in flight, or null when no run is in flight.
  pendingTitle: string | null;
  exportingFormat: ExportFormat | null;
  onExport: (format: ExportFormat) => void;
  onPage: (page: number) => void;
}

const EXPORT_BUTTONS: { format: ExportFormat; label: string }[] = [
  { format: 'pdf', label: 'Export PDF' },
  { format: 'xlsx', label: 'Export Excel' },
  { format: 'csv', label: 'Export CSV' },
];

function cellDisplay(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

export function ReportResultView({ shown, pendingTitle, exportingFormat, onExport, onPage }: ReportResultViewProps) {
  const inFlight = pendingTitle !== null;
  if (!shown && !inFlight) return null;

  const title = inFlight ? pendingTitle : (shown?.data.title || shown?.key || '');
  // Export buttons and page controls belong to the shown result, which the Loading line replaces.
  const canExport = !inFlight && Boolean(shown?.kind && shown?.key);
  const result = !inFlight && shown ? shown.data : null;

  return (
    <div>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h3>
        {canExport && (
          <div className="flex items-center gap-2">
            {EXPORT_BUTTONS.map(({ format, label }) => (
              <button
                key={format}
                onClick={() => onExport(format)}
                disabled={!!exportingFormat}
                className="flex items-center gap-1 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
              >
                <DownloadIcon size={14} />
                {exportingFormat === format ? 'Exporting…' : label}
              </button>
            ))}
          </div>
        )}
      </div>

      {inFlight && <p className="text-gray-600 dark:text-gray-400 text-sm">Loading…</p>}

      {result && result.rows.length === 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-8 text-center">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">No matching assets</h3>
          <p className="text-gray-500 text-xs">Adjust your filters and run the report again.</p>
        </div>
      )}

      {shown && result && result.rows.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 text-xs border-b border-gray-200 dark:border-gray-700">
                  {result.columns.map((c) => (
                    <th key={c} className="py-2 pr-4">{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, idx) => (
                  <tr key={idx} className="border-b border-gray-200 dark:border-gray-800">
                    {result.columns.map((c) => (
                      <td
                        key={c}
                        className="py-2 pr-4 text-gray-700 dark:text-gray-300 truncate max-w-xs"
                        title={cellDisplay(row[c])}
                      >
                        {cellDisplay(row[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {shown.kind && shown.key && result.totalPages > 1 && (
            <div className="flex items-center justify-between mt-3 text-xs text-gray-600 dark:text-gray-400">
              <button
                onClick={() => onPage(Math.max(1, shown.page - 1))}
                disabled={shown.page <= 1}
                className="disabled:opacity-40 hover:text-gray-900 dark:hover:text-white"
              >
                Previous
              </button>
              <span>Page {shown.page} of {result.totalPages}</span>
              <button
                onClick={() => onPage(Math.min(result.totalPages, shown.page + 1))}
                disabled={shown.page >= result.totalPages}
                className="disabled:opacity-40 hover:text-gray-900 dark:hover:text-white"
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
