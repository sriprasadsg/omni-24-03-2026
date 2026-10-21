import React, { useState, useMemo, useCallback } from 'react';
import { ComplianceFramework, ControlStatus, Asset, AssetCompliance } from '../types';
import { AssetComplianceList } from './AssetComplianceList';
import { ChainOfCustodyPanel } from './ChainOfCustodyPanel';
import { ControlCommentsPanel } from './ControlCommentsPanel';
import { BulkEvidenceUploadModal } from './BulkEvidenceUploadModal';
import { ControlEvidenceUploadModal } from './ControlEvidenceUploadModal';
import { AddControlModal } from './AddControlModal';
import { ReportsModal } from './ReportsModal';
import { FrameworkInfoBanner } from './FrameworkInfoBanner';
import { statusClasses, statusDots, categoryChip, categoryIcons, statusOptions } from './frameworkDetailStyles';
import { PaperclipIcon, ShieldCheckIcon, BinocularsIcon, PlusIcon, UploadIcon, BrainCircuitIcon, FileTextIcon, SearchIcon } from './icons';
import { useUser } from '../contexts/UserContext';
import * as api from '../services/apiService';
import { showToast } from '../utils/toast';

interface FrameworkDetailProps {
  framework: ComplianceFramework;
  assets: Asset[];
  assetComplianceData: AssetCompliance[];
  onRefresh?: () => void;
}

const toolButton = 'inline-flex items-center gap-1.5 whitespace-nowrap h-9 px-3 text-[13px] font-medium text-gray-700 dark:text-gray-200 glass rounded-xl transition-all hover:border-primary-500/40 active:scale-[0.98]';
const primaryButton = 'inline-flex items-center gap-1.5 whitespace-nowrap h-9 px-3.5 text-[13px] font-semibold text-white rounded-xl bg-primary-600 hover:bg-primary-700 transition-all active:scale-[0.98]';
const divider = <span className="hidden md:block h-6 w-px mx-1 bg-gray-200 dark:bg-white/10" aria-hidden="true" />;

export const FrameworkDetail: React.FC<FrameworkDetailProps> = ({ framework, assets, assetComplianceData: initialAssetComplianceData, onRefresh }) => {
  const [localAssetCompliance, setLocalAssetCompliance] = useState(initialAssetComplianceData);
  const assetComplianceData = localAssetCompliance;

  const refreshAssetCompliance = useCallback(async (assetId: string) => {
    const fresh = await api.fetchAssetCompliance(assetId);
    if (fresh) {
      setLocalAssetCompliance(prev => {
        const filtered = prev.filter(ac => ac.assetId !== assetId);
        return Array.isArray(fresh) ? [...filtered, ...fresh] : [...filtered, fresh];
      });
    }
    if (onRefresh) onRefresh();
  }, [onRefresh]);

  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<ControlStatus | 'All'>('All');
  const [expandedControlId, setExpandedControlId] = useState<string | null>(null);
  const [isAddControlModalOpen, setIsAddControlModalOpen] = useState(false);
  const [isReportsModalOpen, setIsReportsModalOpen] = useState(false);
  const [evidenceUploadControlId, setEvidenceUploadControlId] = useState<string | null>(null);
  const [isBulkUploadOpen, setIsBulkUploadOpen] = useState(false);
  const [reportFormat, setReportFormat] = useState<'csv' | 'excel' | 'pdf'>('csv');
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const { hasPermission } = useUser();
  const canManageEvidence = hasPermission('manage:compliance_evidence');
  const canViewCoC = hasPermission('view:audit_log');

  const handleAddControl = async (data: any) => {
    try {
      await api.addComplianceControl(framework.id, data);
      showToast('Control added successfully!', 'success');
      setIsAddControlModalOpen(false);
      // The new control lives on the framework, which the parent owns.
      if (onRefresh) onRefresh();
    } catch (e) {
      showToast(`Failed to add control: ${e instanceof Error ? e.message : 'Unknown error'}`, 'error');
    }
  };

  const handleImportDoc = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      try {
        const res = await api.importComplianceControls(framework.id, file);
        showToast(`Successfully imported ${res.count} controls from ${file.name}`, 'success');
        if (onRefresh) onRefresh();
      } catch (err: any) {
        showToast(`Import failed: ${err?.message ?? 'Unknown error'}`, 'error');
      }
      // Reset so the same file can be re-uploaded
      e.target.value = '';
    }
  };

  const handleCollectEvidence = async () => {
    try {
      // @ts-ignore
      const res = await api.triggerFrameworkScan(framework.id);
      if (res.success) {
        showToast(`Scan initiated! ${res.message}`, 'success');
      } else {
        showToast(`Failed to start scan: ${res.message}`, 'error');
      }
    } catch (e) {
      showToast('Error triggering scan.', 'error');
      console.error(e);
    }
  };

  const handleGenerateReport = async () => {
    try {
      let res;
      // Select API based on format
      if (reportFormat === 'excel') {
        res = await api.generateExcelComplianceReport(framework.id);
      } else if (reportFormat === 'pdf') {
        res = await api.generatePDFComplianceReport(framework.id);
      } else {
        res = await api.generateComplianceReport(framework.id);
      }

      // The report endpoints answer { success, report: { filename, ... } }.
      if (res?.report?.filename ?? res?.filename) {
        showToast(`${reportFormat.toUpperCase()} report generated successfully!`, 'success');
        setIsReportsModalOpen(true);
      } else {
        showToast('Report generation returned an unexpected response.', 'error');
      }
    } catch (e: any) {
      showToast(`Failed to generate report: ${e?.message || 'Unknown error'}`, 'error');
    }
  };

  const handleRunAiAuditor = async () => {
    if (confirm('Run local AI Auditor evaluation on all evidence for this framework? (This may take a few minutes depending on hardware)')) {
      try {
        const res = await api.runAIAuditor(framework.id);
        showToast(res.message, 'success');
        if (onRefresh) onRefresh();
      } catch (e) {
        showToast(`Failed to run AI Audit: ${e instanceof Error ? e.message : 'Unknown error'}`, 'error');
      }
    }
  };

  const statusSummary = useMemo(() => {
    const summary: Record<ControlStatus, number> = {
      'Implemented': 0,
      'In Progress': 0,
      'At Risk': 0,
      'Not Implemented': 0
    };
    (framework.controls ?? []).forEach(control => {
      if (summary[control.status] !== undefined) {
        summary[control.status]++;
      }
    });
    return summary;
  }, [framework.controls]);

  const filteredControls = useMemo(() => {
    return (framework.controls ?? []).filter(control => {
      const statusMatch = statusFilter === 'All' || control.status === statusFilter;
      const searchMatch = (
        control.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        control.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        control.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (control.category && control.category.toLowerCase().includes(searchTerm.toLowerCase()))
      );
      return statusMatch && searchMatch;
    });
  }, [framework.controls, searchTerm, statusFilter]);

  const totalControls = framework.controls?.length ?? 0;
  const progress = Math.max(0, Math.min(100, Number(framework.progress) || 0));
  const toggleControl = (id: string) => setExpandedControlId(expandedControlId === id ? null : id);

  return (
    <section aria-label={framework.name} className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card overflow-hidden">
      <div className="px-5 pt-5 pb-4 border-b border-gray-100 dark:border-white/[0.06]">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div className="min-w-0">
            <h3 className="text-xl font-semibold tracking-[-0.02em] text-gray-900 dark:text-white">{framework.name}</h3>
            {framework.description && <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{framework.description}</p>}
          </div>
          <div className="md:w-48 flex-shrink-0">
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-xs text-gray-500 dark:text-gray-400">Progress</span>
              <span className="text-2xl leading-none font-semibold tracking-[-0.03em] tabular-nums text-gray-900 dark:text-white">{progress}%</span>
            </div>
            <div className="mt-2 h-1.5 rounded-full overflow-hidden bg-gray-200 dark:bg-white/10" role="progressbar" aria-label="Framework progress" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
              <div className="h-full rounded-full bg-primary-500 dark:bg-primary-400 transition-all duration-500" style={{ width: `${progress}%` }} />
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button onClick={() => setIsAddControlModalOpen(true)} className={primaryButton}>
            <PlusIcon size={14} />
            Add control
          </button>
          <button onClick={() => fileInputRef.current?.click()} title="Import controls from CSV, Excel (.xlsx), PDF, or Word (.docx)" className={toolButton}>
            <UploadIcon size={14} />
            Import controls
          </button>
          {divider}
          <button onClick={handleCollectEvidence} title="Ask every agent in this organization to collect evidence for this framework" className={toolButton}>
            <BinocularsIcon size={14} className="text-primary-600 dark:text-primary-400" />
            Collect evidence
          </button>
          {canManageEvidence && (
            <button onClick={() => setIsBulkUploadOpen(true)} aria-label="Open bulk evidence upload modal" className={toolButton}>
              <UploadIcon size={14} />
              Bulk upload evidence
            </button>
          )}
          <button onClick={handleRunAiAuditor} className={toolButton}>
            <BrainCircuitIcon size={14} className="text-primary-600 dark:text-primary-400" />
            Evaluate with AI Auditor
          </button>
          {divider}
          <div className="inline-flex items-center gap-1.5">
            <select
              value={reportFormat}
              onChange={(e) => setReportFormat(e.target.value as 'csv' | 'excel' | 'pdf')}
              aria-label="Report format"
              className="h-9 pl-3 pr-8 text-[13px] font-medium rounded-xl text-gray-700 dark:text-gray-200 bg-white dark:bg-white/[0.04] border border-gray-200 dark:border-white/10 focus:outline-none focus:border-primary-500"
            >
              <option value="csv">CSV</option>
              <option value="excel">Excel (.xlsx)</option>
              <option value="pdf">PDF</option>
            </select>
            <button onClick={handleGenerateReport} className={toolButton}>
              <FileTextIcon size={14} />
              Generate report
            </button>
          </div>
          <button onClick={() => setIsReportsModalOpen(true)} className={toolButton}>
            <FileTextIcon size={14} />
            View reports
          </button>
          <input
            type="file"
            ref={fileInputRef}
            className="hidden"
            accept=".csv,.xlsx,.xls,.pdf,.docx"
            onChange={handleImportDoc}
          />
        </div>
      </div>

      <FrameworkInfoBanner framework={framework} />

      <div className="px-5 py-4 flex flex-col xl:flex-row xl:items-center gap-3">
        <div className="relative flex-grow min-w-0">
          <SearchIcon size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          <input
            type="text"
            placeholder="Search controls…"
            aria-label="Search controls by ID, name, category or description"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full h-9 pl-9 pr-3 text-sm rounded-xl text-gray-900 dark:text-white bg-white dark:bg-white/[0.04] border border-gray-200 dark:border-white/10 placeholder:text-gray-400 focus:outline-none focus:border-primary-500"
          />
        </div>
        <div role="group" aria-label="Filter by status" className="flex-shrink-0 inline-flex p-0.5 rounded-xl overflow-x-auto bg-gray-100 dark:bg-white/[0.05] ring-1 ring-inset ring-gray-200/70 dark:ring-white/[0.06]">
          {statusOptions.map(opt => {
            const active = statusFilter === opt;
            const count = opt === 'All' ? totalControls : statusSummary[opt];
            return (
              <button
                key={opt}
                onClick={() => setStatusFilter(opt)}
                aria-pressed={active}
                className={`flex items-center gap-1.5 whitespace-nowrap h-8 px-2.5 rounded-[10px] text-xs font-medium transition-colors ${active
                  ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'}`}
              >
                {opt !== 'All' && <span className={`h-1.5 w-1.5 rounded-full ${statusDots[opt]}`} aria-hidden="true" />}
                {opt}
                <span className="tabular-nums text-gray-500 dark:text-gray-400">{count}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="overflow-x-auto border-t border-gray-100 dark:border-white/[0.06]">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-white/[0.06]">
              <th scope="col" className="px-5 py-2.5">ID</th>
              <th scope="col" className="px-5 py-2.5">Control</th>
              <th scope="col" className="px-5 py-2.5">Status</th>
              <th scope="col" className="px-5 py-2.5 whitespace-nowrap">Last reviewed</th>
              <th scope="col" className="px-5 py-2.5">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {filteredControls.map(control => {
              const expanded = expandedControlId === control.id;
              const detailsId = `control-${control.id.replace(/[^A-Za-z0-9_-]/g, '_')}-details`;
              const evidenceCount = (control.evidence?.length || 0) +
                assetComplianceData
                  .filter(ac => ac.controlId === control.id)
                  .reduce((sum, ac) => sum + (ac.evidence?.length || 0), 0);
              return (
                <React.Fragment key={control.id}>
                  <tr
                    className={`border-b border-gray-100 dark:border-white/[0.05] cursor-pointer transition-colors ${expanded ? 'bg-primary-500/[0.04]' : 'hover:bg-gray-50 dark:hover:bg-white/[0.02]'}`}
                    onClick={() => toggleControl(control.id)}
                  >
                    <td className="px-5 py-3.5 align-top font-mono text-xs font-medium text-gray-900 dark:text-white whitespace-nowrap">{control.id}</td>
                    <td className="px-5 py-3.5 align-top min-w-[260px]">
                      <div className="font-semibold text-gray-900 dark:text-gray-100">{control.name}</div>
                      {control.category && (
                        <span className={`mt-1.5 inline-flex items-center px-2 py-0.5 text-[11px] font-medium rounded-full ${categoryChip}`}>
                          {categoryIcons[control.category]}
                          {control.category}
                        </span>
                      )}
                      {control.description && <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5">{control.description}</p>}
                    </td>
                    <td className="px-5 py-3.5 align-top">
                      <span className={`inline-block whitespace-nowrap px-2 py-0.5 text-[11px] font-semibold rounded-full ${statusClasses[control.status]}`}>
                        {control.status}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 align-top text-xs tabular-nums text-gray-600 dark:text-gray-300 whitespace-nowrap">{control.lastReviewed || '—'}</td>
                    <td className="px-5 py-3.5 align-top">
                      {control.manual_evidence_instructions && (
                        <div className="mb-2 p-2.5 rounded-lg text-xs text-blue-900 dark:text-blue-100 bg-blue-500/[0.06] ring-1 ring-inset ring-blue-500/20">
                          <strong className="block mb-0.5 font-semibold">Manual collection guide</strong>
                          {control.manual_evidence_instructions}
                        </div>
                      )}
                      <div className="flex items-center gap-2 flex-wrap">
                        <button
                          onClick={(e) => { e.stopPropagation(); toggleControl(control.id); }}
                          aria-expanded={expanded}
                          aria-controls={detailsId}
                          className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs font-medium text-primary-700 dark:text-primary-300 hover:bg-primary-500/10 transition-colors whitespace-nowrap"
                        >
                          <PaperclipIcon size={12} />
                          Evidence ({evidenceCount})
                        </button>
                        {canManageEvidence && (
                          <button
                            onClick={(e) => { e.stopPropagation(); setEvidenceUploadControlId(control.id); }}
                            className="inline-flex items-center gap-1 h-7 px-2.5 rounded-lg text-xs font-medium text-emerald-700 dark:text-emerald-300 ring-1 ring-inset ring-emerald-500/25 hover:bg-emerald-500/10 transition-colors"
                            title="Upload policy document, audit report, or other evidence for this control"
                          >
                            <UploadIcon size={11} />
                            Upload
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {expanded && (
                    <tr id={detailsId}>
                      <td colSpan={5} className="px-5 py-4 bg-gray-50/80 dark:bg-white/[0.02] border-b border-gray-100 dark:border-white/[0.05]">
                        <AssetComplianceList
                          control={control}
                          assets={assets}
                          complianceData={assetComplianceData}
                          onUpdateStatus={async (assetId, status) => {
                              try {
                                  await api.updateAssetComplianceStatus(assetId, control.id, status);
                                  await refreshAssetCompliance(assetId);
                              } catch (e) {
                                  console.error('Failed to update compliance status', e);
                                  showToast('Failed to update compliance status — please try again', 'error');
                              }
                          }}
                          onEvidenceReviewed={(assetId) => {
                            // Non-mutating refresh trigger (WR-04) — a review decision doesn't
                            // change the asset's overall compliance status, so this refetches
                            // directly instead of reusing onUpdateStatus's mutating write.
                            refreshAssetCompliance(assetId);
                          }}
                          onUploadEvidence={async (assetId, file, description) => {
                            try {
                              const res = await api.uploadComplianceEvidence(assetId, control.id, file, description);
                              if (res.success) {
                                showToast(`Successfully uploaded evidence: ${file.name}`, 'success');
                                await refreshAssetCompliance(assetId);
                              }
                            } catch (e) {
                              console.error("Upload Error", e);
                              showToast("Failed to upload evidence.", 'error');
                            }
                          }}
                          onIngestEvidence={async (assetId, fileName, content) => {
                            try {
                              const asset = assets.find(a => a.id === assetId);
                              const sourceName = `Compliance_Evidence_${control.id}_${asset?.hostname || assetId}_${fileName}`;
                              const res = await api.ingestKnowledge(content, sourceName);
                              if (!res.success) {
                                console.error('Ingest failed', res);
                              }
                            } catch (e) {
                              console.error("Ingest Exception", e);
                              showToast('Error ingesting evidence.', 'error');
                            }
                          }}
                          onDeleteEvidence={async (assetId, controlId, evidenceId) => {
                            try {
                              await api.deleteComplianceEvidence(assetId, controlId, evidenceId);
                              showToast('Evidence deleted.', 'success');
                              await refreshAssetCompliance(assetId);
                            } catch (e) {
                              console.error("Delete Error", e);
                              showToast("Failed to delete evidence.", 'error');
                            }
                          }}
                        />
                        {canViewCoC && <ChainOfCustodyPanel controlId={control.id} />}
                        <ControlCommentsPanel controlId={control.id} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
            {filteredControls.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-12 text-center">
                  <ShieldCheckIcon size={28} className="mx-auto text-gray-400" />
                  <p className="mt-3 text-sm font-medium text-gray-700 dark:text-gray-300">
                    {totalControls === 0 ? 'This framework has no controls yet' : 'No controls match these filters'}
                  </p>
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {totalControls === 0 ? 'Add a control or import them from a file.' : 'Clear the search or pick another status.'}
                  </p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <AddControlModal
        isOpen={isAddControlModalOpen}
        onClose={() => setIsAddControlModalOpen(false)}
        onAdd={handleAddControl}
      />
      <ReportsModal
        isOpen={isReportsModalOpen}
        onClose={() => setIsReportsModalOpen(false)}
        frameworkId={framework.id}
      />
      {evidenceUploadControlId && (
        <ControlEvidenceUploadModal
          controlId={evidenceUploadControlId}
          onClose={() => setEvidenceUploadControlId(null)}
          onUploaded={() => { if (onRefresh) onRefresh(); }}
        />
      )}
      {isBulkUploadOpen && (
        <BulkEvidenceUploadModal
          onClose={() => setIsBulkUploadOpen(false)}
          onUploaded={() => { setIsBulkUploadOpen(false); if (onRefresh) onRefresh(); }}
        />
      )}
    </section>
  );
};
