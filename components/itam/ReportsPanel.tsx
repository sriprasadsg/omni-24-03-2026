import React, { useCallback, useEffect, useRef, useState } from 'react';
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
  ItamSavedCustomReport,
  ItamCustomReportDefinition,
} from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { BarChart3Icon, PlusIcon } from '../icons';
import { ITAM_KPI_COPY } from './ItamKpiPanel';
import { ReportResultView, type ExportFormat, type ShownReport } from './ReportResultView';

const PAGE_SIZE = 50;
const EXPORT_ERROR = "Couldn't export report. Try again, or contact an administrator if the problem continues.";

interface ReportsPanelProps {
  // The drill-down seam plan 72-07's KPI tiles attach to (D-18): when set,
  // the named report auto-runs on mount and onFocusHandled clears it so a
  // later re-render doesn't re-trigger the same run.
  focusReportKey?: string | null;
  onFocusHandled?: () => void;
  // The Platform Owner's selected tenant. Pre-built reports cover one organization
  // (D-13), so runs and exports carry it; needsTenant disables the Run buttons.
  tenantId?: string | null;
  needsTenant?: boolean;
}

const SELECT_TENANT_NOTE_ID = 'itam-reports-select-tenant-note';

export function ReportsPanel({ focusReportKey, onFocusHandled, tenantId, needsTenant }: ReportsPanelProps) {
  const [reports, setReports] = useState<ItamPrebuiltReportMeta[]>([]);

  // The shown report and its identity change together, and only the current request writes
  // them (WR-04); the run in flight is held apart so a failed run leaves the shown report intact.
  const [shown, setShown] = useState<ShownReport | null>(null);
  const [pending, setPending] = useState<{ kind: 'prebuilt' | 'custom'; key: string } | null>(null);
  const [exportingFormat, setExportingFormat] = useState<ExportFormat | null>(null);

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

  // R3: a result from the previous tenant must not stay on screen after a switch.
  // Skipped on first mount so a drill-down run started through focusReportKey is kept.
  // Only the latest request may write the result: every run takes a new value and a
  // tenant switch bumps it, so a late or superseded response is dropped.
  const runSeq = useRef(0);
  // Moves only on a tenant switch (not on every run), so an export started for one tenant
  // cannot land in another while an export in the same tenant still completes (IN-05).
  const tenantEpoch = useRef(0);
  const previousTenantId = useRef(tenantId);
  useEffect(() => {
    if (previousTenantId.current === tenantId) return;
    previousTenantId.current = tenantId;
    runSeq.current += 1;
    tenantEpoch.current += 1;
    setExportingFormat(null);
    setPending(null);
    setShown(null);
  }, [tenantId]);

  const runPrebuilt = useCallback(async (key: string, targetPage = 1) => {
    setPending({ kind: 'prebuilt', key });
    const seq = ++runSeq.current;
    try {
      const r = await runItamPrebuiltReport(key, targetPage, PAGE_SIZE, tenantId);
      if (seq !== runSeq.current) return;
      setShown({ kind: 'prebuilt', key, page: targetPage, data: r });
    } catch (e: any) {
      if (seq !== runSeq.current) return;
      showToast(e?.message || "Couldn't run report.", 'error');
    } finally {
      if (seq === runSeq.current) setPending(null);
    }
  }, [tenantId]);

  useEffect(() => {
    if (focusReportKey) {
      runPrebuilt(focusReportKey, 1).finally(() => onFocusHandled && onFocusHandled());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusReportKey]);

  const runSavedCustom = useCallback(async (reportId: string, targetPage = 1) => {
    setPending({ kind: 'custom', key: reportId });
    const seq = ++runSeq.current;
    try {
      const r = await runItamCustomReport(reportId, targetPage, PAGE_SIZE);
      if (seq !== runSeq.current) return;
      setShown({ kind: 'custom', key: reportId, page: targetPage, data: r });
    } catch (e: any) {
      if (seq !== runSeq.current) return;
      showToast(e?.message || "Couldn't run report.", 'error');
    } finally {
      if (seq === runSeq.current) setPending(null);
    }
  }, []);

  function runActivePage(targetPage: number) {
    if (shown?.kind === 'prebuilt' && shown.key) runPrebuilt(shown.key, targetPage);
    else if (shown?.kind === 'custom' && shown.key) runSavedCustom(shown.key, targetPage);
  }

  // Unsaved builder preview (D-02): shows on-screen results but carries no
  // stable id, so it is not exportable until the definition is saved — see
  // handleSaveCustom below, which runs the newly-saved report immediately so
  // its result becomes exportable in the same shared preview table.
  async function handlePreviewCustom(definition: ItamCustomReportDefinition, targetPage: number) {
    setBuilderBusy(true);
    // The preview supersedes any in-flight run, whose response is now dropped.
    const seq = ++runSeq.current;
    setPending(null);
    try {
      const r = await previewItamCustomReport(definition, targetPage, PAGE_SIZE);
      if (seq !== runSeq.current) return;
      setShown({ kind: null, key: null, page: targetPage, data: r });
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
      if (shown?.kind === 'custom' && shown.key === target.id) setShown(null);
      setDeleteTarget(null);
      loadSavedReports();
    } catch (e: any) {
      showToast(e?.message || "Couldn't delete report.", 'error');
      setDeleteTarget(null);
    }
  }

  async function handleExport(format: ExportFormat) {
    if (!shown?.kind || !shown.key) return;
    // The export target is fixed at click time, from the report on screen.
    const { kind, key } = shown;
    const epoch = tenantEpoch.current;
    setExportingFormat(format);
    try {
      const generated = kind === 'prebuilt'
        ? await generateItamReport(kind, key, format, tenantId)
        : await generateItamReport(kind, key, format);
      if (epoch !== tenantEpoch.current) return;
      await downloadItamReport(generated.filename);
    } catch (e: any) {
      if (epoch !== tenantEpoch.current) return;
      showToast(e?.message || EXPORT_ERROR, 'error');
    } finally {
      if (epoch === tenantEpoch.current) setExportingFormat(null);
    }
  }

  // Title of the run in flight: the loaded report's title, falling back to its key.
  let pendingTitle: string | null = null;
  if (pending) {
    pendingTitle = (pending.kind === 'prebuilt'
      ? reports.find((r) => r.key === pending.key)?.title
      : savedReports.find((r) => r.id === pending.key)?.name) || pending.key;
  }

  return (
    <div>
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">Pre-built Reports</h3>
        {needsTenant && (
          <p role="status" id={SELECT_TENANT_NOTE_ID} className="text-xs text-gray-500 dark:text-gray-400 mb-3">
            {ITAM_KPI_COPY.reportsSelectTenantNote}
          </p>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {reports.map((r) => (
            <div key={r.key} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-start gap-2 mb-2">
                <BarChart3Icon size={18} className="text-cyan-500 flex-shrink-0" />
                <div>
                  <h4 className="text-sm font-semibold text-gray-900 dark:text-white">{r.title}</h4>
                  <p className="text-xs text-gray-500 mt-0.5">{r.description}</p>
                </div>
              </div>
              <button
                onClick={() => runPrebuilt(r.key, 1)}
                disabled={needsTenant}
                aria-describedby={needsTenant ? SELECT_TENANT_NOTE_ID : undefined}
                className="mt-2 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
              >
                Run Report
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="mb-6">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Custom Reports</h3>
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

        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
          {savedLoading && <p className="text-gray-600 dark:text-gray-400 text-sm">Loading…</p>}
          {!savedLoading && savedReports.length === 0 && (
            <div className="text-center py-4">
              <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">No custom reports yet</h4>
              <p className="text-gray-500 text-xs">Build a report by picking fields and filters, then save it to reuse anytime.</p>
            </div>
          )}
          {!savedLoading && savedReports.length > 0 && (
            <div className="max-h-80 overflow-y-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 text-xs border-b border-gray-200 dark:border-gray-700">
                    <th className="py-2 pr-4">Name</th>
                    <th className="py-2 pr-4">Columns</th>
                    <th className="py-2 pr-4" />
                  </tr>
                </thead>
                <tbody>
                  {savedReports.map((r) => (
                    <tr key={r.id} className="border-b border-gray-200 dark:border-gray-800">
                      <td className="py-2 pr-4 text-gray-900 dark:text-white font-medium truncate max-w-xs" title={r.name}>{r.name}</td>
                      <td className="py-2 pr-4 text-gray-600 dark:text-gray-400">{r.columns.length}</td>
                      <td className="py-2 pr-4 text-right whitespace-nowrap">
                        <button
                          onClick={() => runSavedCustom(r.id, 1)}
                          className="text-cyan-600 dark:text-cyan-400 hover:text-cyan-700 dark:hover:text-cyan-300 text-xs font-medium mr-4"
                          aria-label={`Run ${r.name}`}
                        >
                          Run
                        </button>
                        <button
                          onClick={() => setDeleteTarget(r)}
                          className="text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 text-xs font-medium"
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

      <ReportResultView
        shown={shown}
        pendingTitle={pendingTitle}
        exportingFormat={exportingFormat}
        onExport={handleExport}
        onPage={runActivePage}
      />

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
