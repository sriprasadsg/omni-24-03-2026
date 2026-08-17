import React, { useCallback, useEffect, useState } from 'react';
import {
  fetchItamPrebuiltReports,
  runItamPrebuiltReport,
  generateItamReport,
  downloadItamReport,
  ItamPrebuiltReportMeta,
  ItamReportRunResult,
} from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { BarChart3Icon, DownloadIcon } from '../icons';

const PAGE_SIZE = 50;

function cellDisplay(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

interface ReportsPanelProps {
  // The drill-down seam plan 72-07's KPI tiles attach to (D-18): when set,
  // the named report auto-runs on mount and onFocusHandled clears it so a
  // later re-render doesn't re-trigger the same run.
  focusReportKey?: string | null;
  onFocusHandled?: () => void;
}

export function ReportsPanel({ focusReportKey, onFocusHandled }: ReportsPanelProps) {
  const [reports, setReports] = useState<ItamPrebuiltReportMeta[]>([]);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [result, setResult] = useState<ItamReportRunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [page, setPage] = useState(1);

  useEffect(() => {
    fetchItamPrebuiltReports().then(setReports).catch(() => setReports([]));
  }, []);

  const runReport = useCallback(async (key: string, targetPage = 1) => {
    setActiveKey(key);
    setRunning(true);
    try {
      const r = await runItamPrebuiltReport(key, targetPage, PAGE_SIZE);
      setResult(r);
      setPage(targetPage);
    } catch (e: any) {
      showToast(e?.message || "Couldn't run report.", 'error');
    } finally {
      setRunning(false);
    }
  }, []);

  useEffect(() => {
    if (focusReportKey) {
      runReport(focusReportKey, 1).finally(() => onFocusHandled && onFocusHandled());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusReportKey]);

  async function handleExportCsv() {
    if (!activeKey) return;
    setExporting(true);
    try {
      const generated = await generateItamReport('prebuilt', activeKey, 'csv');
      await downloadItamReport(generated.filename);
    } catch (e: any) {
      showToast(e?.message || "Couldn't export report. Try again, or contact an administrator if the problem continues.", 'error');
    } finally {
      setExporting(false);
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-white mb-3">Pre-built Reports</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {reports.map((r) => (
            <div key={r.key} className="bg-gray-800 rounded-xl border border-gray-700 p-4">
              <div className="flex items-start gap-2 mb-2">
                <BarChart3Icon size={18} className="text-cyan-500 flex-shrink-0" />
                <div>
                  <h4 className="text-sm font-semibold text-white">{r.title}</h4>
                  <p className="text-xs text-gray-500 mt-0.5">{r.description}</p>
                </div>
              </div>
              <button
                onClick={() => runReport(r.key, 1)}
                className="mt-2 bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
              >
                Run Report
              </button>
            </div>
          ))}
        </div>
      </div>

      {activeKey && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-lg font-semibold text-white">{result?.title || activeKey}</h3>
            <button
              onClick={handleExportCsv}
              disabled={!result || exporting}
              className="flex items-center gap-1 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
            >
              <DownloadIcon size={14} />
              {exporting ? 'Exporting…' : 'Export CSV'}
            </button>
          </div>

          {running && <p className="text-gray-400 text-sm">Loading…</p>}

          {!running && result && result.rows.length === 0 && (
            <div className="bg-gray-800 rounded-xl border border-gray-700 p-8 text-center">
              <h3 className="text-sm font-semibold text-white mb-1">No matching assets</h3>
              <p className="text-gray-500 text-xs">Adjust your filters and run the report again.</p>
            </div>
          )}

          {!running && result && result.rows.length > 0 && (
            <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-gray-500 text-xs border-b border-gray-700">
                      {result.columns.map((c) => (
                        <th key={c} className="py-2 pr-4">{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row, idx) => (
                      <tr key={idx} className="border-b border-gray-800">
                        {result.columns.map((c) => (
                          <td
                            key={c}
                            className="py-2 pr-4 text-gray-300 truncate max-w-xs"
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

              {result.totalPages > 1 && (
                <div className="flex items-center justify-between mt-3 text-xs text-gray-400">
                  <button
                    onClick={() => runReport(activeKey, Math.max(1, page - 1))}
                    disabled={page <= 1}
                    className="disabled:opacity-40 hover:text-white"
                  >
                    Previous
                  </button>
                  <span>Page {page} of {result.totalPages}</span>
                  <button
                    onClick={() => runReport(activeKey, Math.min(result.totalPages, page + 1))}
                    disabled={page >= result.totalPages}
                    className="disabled:opacity-40 hover:text-white"
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
