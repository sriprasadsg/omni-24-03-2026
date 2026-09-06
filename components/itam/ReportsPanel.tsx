import React, { useCallback, useEffect, useState } from 'react';
import Modal from '../ui/Modal';
import { ReportBuilderForm } from './ReportBuilderForm';
import {
  fetchItamPrebuiltReports,
  runItamPrebuiltReport,
  generateItamReport,
  downloadItamReport,
  listItamCustomReports,
  saveItamCustomReport,
  deleteItamCustomReport,
  previewItamCustomReport,
  runItamCustomReport,
  ItamPrebuiltReportMeta,
  ItamReportRunResult,
  ItamSavedCustomReport,
  ItamCustomReportDefinition,
} from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { BarChart3Icon, DownloadIcon, PlusIcon } from '../icons';

const PAGE_SIZE = 50;
const EXPORT_ERROR = "Couldn't export report. Try again, or contact an administrator if the problem continues.";

function cellDisplay(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

type ActiveKind = 'prebuilt' | 'custom' | null;
type ExportFormat = 'pdf' | 'xlsx' | 'csv';

interface ReportsPanelProps {
  // The drill-down seam plan 72-07's KPI tiles attach to (D-18): when set,
  // the named report auto-runs on mount and onFocusHandled clears it so a
  // later re-render doesn't re-trigger the same run.
  focusReportKey?: string | null;
  onFocusHandled?: () => void;
}

export function ReportsPanel({ focusReportKey, onFocusHandled }: ReportsPanelProps) {
  const [reports, setReports] = useState<ItamPrebuiltReportMeta[]>([]);

  const [activeKind, setActiveKind] = useState<ActiveKind>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [result, setResult] = useState<ItamReportRunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [exportingFormat, setExportingFormat] = useState<ExportFormat | null>(null);
  const [page, setPage] = useState(1);

  const [builderOpen, setBuilderOpen] = useState(false);
  const [builderBusy, setBuilderBusy] = useState(false);
  const [savedReports, setSavedReports] = useState<ItamSavedCustomReport[]>([]);
  const [savedLoading, setSavedLoading] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<ItamSavedCustomReport | null>(null);

  useEffect(() => {
    fetchItamPrebuiltReports().then(setReports).catch(() => setReports([]));
  }, []);

  const loadSavedReports = useCallback(async () => {
    setSavedLoading(true);
    try {
      setSavedReports(await listItamCustomReports());
    } catch (e: any) {
      showToast(e?.message || 'Failed to load saved reports', 'error');
    } finally {
      setSavedLoading(false);
    }
  }, []);

  useEffect(() => { loadSavedReports(); }, [loadSavedReports]);

  const runPrebuilt = useCallback(async (key: string, targetPage = 1) => {
    setActiveKind('prebuilt');
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
      runPrebuilt(focusReportKey, 1).finally(() => onFocusHandled && onFocusHandled());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusReportKey]);

  const runSavedCustom = useCallback(async (reportId: string, targetPage = 1) => {
    setActiveKind('custom');
    setActiveKey(reportId);
    setRunning(true);
    try {
      const r = await runItamCustomReport(reportId, targetPage, PAGE_SIZE);
      setResult(r);
      setPage(targetPage);
    } catch (e: any) {
      showToast(e?.message || "Couldn't run report.", 'error');
    } finally {
      setRunning(false);
    }
  }, []);

  function runActivePage(targetPage: number) {
    if (activeKind === 'prebuilt' && activeKey) runPrebuilt(activeKey, targetPage);
    else if (activeKind === 'custom' && activeKey) runSavedCustom(activeKey, targetPage);
  }

  // Unsaved builder preview (D-02): shows on-screen results but carries no
  // stable id, so it is not exportable until the definition is saved — see
  // handleSaveCustom below, which runs the newly-saved report immediately so
  // its result becomes exportable in the same shared preview table.
  async function handlePreviewCustom(definition: ItamCustomReportDefinition, targetPage: number) {
    setBuilderBusy(true);
    try {
      const r = await previewItamCustomReport(definition, targetPage, PAGE_SIZE);
      setActiveKind(null);
      setActiveKey(null);
      setResult(r);
      setPage(targetPage);
    } finally {
      setBuilderBusy(false);
    }
  }

  async function handleSaveCustom(definition: ItamCustomReportDefinition) {
    setBuilderBusy(true);
    try {
      const saved = await saveItamCustomReport(definition);
      await loadSavedReports();
      showToast('Report saved.', 'success');
      await runSavedCustom(saved.id, 1);
    } finally {
      setBuilderBusy(false);
    }
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget) return;
    const target = deleteTarget;
    try {
      await deleteItamCustomReport(target.id);
      showToast('Report deleted.', 'success');
      if (activeKind === 'custom' && activeKey === target.id) {
        setResult(null);
        setActiveKind(null);
        setActiveKey(null);
      }
      setDeleteTarget(null);
      loadSavedReports();
    } catch (e: any) {
      showToast(e?.message || "Couldn't delete report.", 'error');
      setDeleteTarget(null);
    }
  }

  async function handleExport(format: ExportFormat) {
    if (!activeKind || !activeKey) return;
    setExportingFormat(format);
    try {
      const generated = await generateItamReport(activeKind, activeKey, format);
      await downloadItamReport(generated.filename);
    } catch (e: any) {
      showToast(e?.message || EXPORT_ERROR, 'error');
    } finally {
      setExportingFormat(null);
    }
  }

  const canExport = Boolean(activeKind && activeKey);

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
                onClick={() => runPrebuilt(r.key, 1)}
                className="mt-2 bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
              >
                Run Report
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="mb-6">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-semibold text-white">Custom Reports</h3>
          <button
            onClick={() => setBuilderOpen((v) => !v)}
            className="flex items-center gap-1 bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
          >
            <PlusIcon size={14} /> Create Custom Report
          </button>
        </div>

        {builderOpen && (
          <div className="mb-4">
            <ReportBuilderForm onPreview={handlePreviewCustom} onSave={handleSaveCustom} busy={builderBusy} />
          </div>
        )}

        <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
          {savedLoading && <p className="text-gray-400 text-sm">Loading…</p>}
          {!savedLoading && savedReports.length === 0 && (
            <div className="text-center py-4">
              <h4 className="text-sm font-semibold text-white mb-1">No custom reports yet</h4>
              <p className="text-gray-500 text-xs">Build a report by picking fields and filters, then save it to reuse anytime.</p>
            </div>
          )}
          {!savedLoading && savedReports.length > 0 && (
            <div className="max-h-80 overflow-y-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 text-xs border-b border-gray-700">
                    <th className="py-2 pr-4">Name</th>
                    <th className="py-2 pr-4">Columns</th>
                    <th className="py-2 pr-4" />
                  </tr>
                </thead>
                <tbody>
                  {savedReports.map((r) => (
                    <tr key={r.id} className="border-b border-gray-800">
                      <td className="py-2 pr-4 text-white font-medium truncate max-w-xs" title={r.name}>{r.name}</td>
                      <td className="py-2 pr-4 text-gray-400">{r.columns.length}</td>
                      <td className="py-2 pr-4 text-right whitespace-nowrap">
                        <button
                          onClick={() => runSavedCustom(r.id, 1)}
                          className="text-cyan-400 hover:text-cyan-300 text-xs font-medium mr-4"
                          aria-label={`Run ${r.name}`}
                        >
                          Run
                        </button>
                        <button
                          onClick={() => setDeleteTarget(r)}
                          className="text-red-400 hover:text-red-300 text-xs font-medium"
                          aria-label={`Delete ${r.name}`}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {(running || result) && (
        <div>
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <h3 className="text-lg font-semibold text-white">{result?.title || activeKey || ''}</h3>
            {canExport && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleExport('pdf')}
                  disabled={!!exportingFormat}
                  className="flex items-center gap-1 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
                >
                  <DownloadIcon size={14} />
                  {exportingFormat === 'pdf' ? 'Exporting…' : 'Export PDF'}
                </button>
                <button
                  onClick={() => handleExport('xlsx')}
                  disabled={!!exportingFormat}
                  className="flex items-center gap-1 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
                >
                  <DownloadIcon size={14} />
                  {exportingFormat === 'xlsx' ? 'Exporting…' : 'Export Excel'}
                </button>
                <button
                  onClick={() => handleExport('csv')}
                  disabled={!!exportingFormat}
                  className="flex items-center gap-1 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
                >
                  <DownloadIcon size={14} />
                  {exportingFormat === 'csv' ? 'Exporting…' : 'Export CSV'}
                </button>
              </div>
            )}
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

              {activeKind && activeKey && result.totalPages > 1 && (
                <div className="flex items-center justify-between mt-3 text-xs text-gray-400">
                  <button
                    onClick={() => runActivePage(Math.max(1, page - 1))}
                    disabled={page <= 1}
                    className="disabled:opacity-40 hover:text-white"
                  >
                    Previous
                  </button>
                  <span>Page {page} of {result.totalPages}</span>
                  <button
                    onClick={() => runActivePage(Math.min(result.totalPages, page + 1))}
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

      <Modal
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Delete report?"
        description="This can't be undone. The saved report definition will be permanently removed."
        confirmLabel="Delete"
        onConfirm={handleDeleteConfirm}
      />
    </div>
  );
}
